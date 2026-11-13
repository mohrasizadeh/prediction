# 90 — The audit: what the migration left broken, and how it was found

The move from PitchAPI + SportAPI to API-Football was finished and the product worked. This is the
pass that asked whether it worked *correctly*, end to end: ingest, engine, layers, players, teams,
admin, API calls, front end.

Nineteen defects. **Not one of them raised an exception, wrote a log line or moved a counter.** Every
existing test passed throughout. That is the finding behind the findings, and it says something
about the shape of this kind of migration: when two providers key the same concepts differently, the
failure mode is not a crash, it is a reader that quietly keeps answering the old question.

## The method, because reading did not work

Earlier in this pass an audit done by reading code produced six findings, **all six wrong**
(docs/87). A regex over JSX truncates at `=>`; "this file contains the string" is not "this file
defines it"; static analysis cannot see a theme injected at runtime. Those six were withdrawn.

What worked was mechanical and boring:

1. **Enumerate, then diff two sets.** Every market the engine computes against every market the
   publish loop accepts. Every column a frame requires against every column the normalizer can
   produce. The bugs live in the difference, and the difference is a set operation, not a judgement.
2. **Execute, do not read.** Build a realistic provider answer, push it through the real functions,
   and assert on what comes out the far end. Finding 1 below was measured as "104 of ~540 lines a
   fixture computes", not inferred.
3. **Never assert on source text.** Three times in this pass a check "passed" because its regex
   matched the comment explaining the removal it was testing for. Every check in
   `tests/selftest_audit_v11.py` runs code. Where a contract crosses languages -- the event
   vocabulary, shared between Python and the front end -- the test runs the front end through node
   rather than reading it.
4. **Suspect the fixture before the product.** The seam test below first reported "the engine can
   build no frames from API-Football rows", which would have been the most serious finding in this
   document. It was the test: the fixture helper hardcoded two club ids on the player blocks, so
   `_sum_team` was looking for players of a club that was not in the match. Every player row still
   landed and the normalizer still worked; only the team totals came out null. A test that is wrong
   in a plausible direction is worse than no test, because it spends the next hour on the wrong
   file.

## The dominant bug class: a null that means zero

API-Football sends `null` where a count is zero. PitchAPI sent `0`. Nearly half of what follows is
that one sentence, met in a different place each time.

The guard against fabricating data was asked **per leaf** and **per fixture**. Both are the wrong
scale:

* **Per block, not per leaf.** `goals.total`, `goals.assists` and `goals.saves` are three leaves of
  one object the provider either sends or does not — as are `shots.total` and `shots.on`. Asked leaf
  by leaf, a 3-1 in which no goal was credited with an assist read as *"this match did not track
  assists"*, and `goal_involvements` went null with it — for the goalscorers too, whose goal was not
  in doubt. Measured over a 96-match season: 10% of real involvements discarded, 28% of player rows
  carrying a NaN, the team total 10% low. And pandas sums an all-NaN group to `0.0`, not NaN, so the
  frame's own null guard could not see it: an untracked fixture became a *confident* team total of
  zero.
* **Per side, not per fixture.** The two teams are two separate answers and one can come back empty
  alone. When that happened, the other side's numbers stood as proof the statistic was tracked, and
  eleven starters were filled to zero — a side that made no tackles and a front line with no shots,
  fitted as though real, while its own team-statistics block plainly said ten shots.

The same sentence on the team side was worse, because `corners` and `poss` are in
`engine_bridge.TEAM_REQUIRED`: **one null corner count deleted the entire match** — both teams, all
26 player rows — from every frame. 96 matches in, 76 out, and `run_league` still returned
`status: done`. The bias runs one way: the matches it deletes are the low-corner ones, so every
model left behind reads high. When the column was null for *every* row — a provider renaming one of
its display strings is enough — `build_frames` did not return `None`, it raised `KeyError: 'pos'`,
after `run_league` had written its `engine_runs` row as `running` and before it could update it. The
league then sat "running" for ever, which made `jobs.tick`'s dirty check fire on every later tick.

## The worst one, which nothing could have revealed from the outside

`engine_bridge.MARKET_COVERAGE` listed six markets. The engine fits nine. `enabled_markets` builds
its answer by iterating that dict, and the publish loop reads `markets.get(mk, False)` — so **saves,
fouls and goal involvements were computed in full and then silently dropped**: no log, no counter,
nothing in `db.forecasts`. 19% of every fixture's output, binned. It read exactly like "the engine
does not support these markets" when the engine supported them fine and the gate had never heard of
them. Switching them on in `engine.markets_enabled` did nothing, because a key that never reaches
the loop cannot be enabled.

The saves market needed a second fix one layer down: `ingest.COVERAGE_FIELDS` had no `saves` row, and
`enabled_markets` tests `bool(cov)`, so the market would have been gated off by an *absent*
measurement even after being registered.

## Order dependence: keepers deleted on the first league of a fresh worker

`build_frames` decided whether to let keepers through by reading `E.PLAYER_THR` — module state that
only `configure_engine` fills, and `run_league` calls `configure_engine` **after** `build_frames`. So
on league 1 of a new process the saves market was not yet in it, the GK discard did nothing, and
every keeper was removed. Leagues 2..N in the same worker were fine. It also made the derived *team*
saves column all-zero rather than all-null, so the `isna()` guard could not see it and the team layer
fitted a saves model on zeros. A bug that disappears the moment you look at it twice in one process.

## Things that were stored but never derived from

* **Match events.** `ingest_af._write_events` wrote `match_events` and stopped. Almost nothing reads
  that archive; what the product reads is what `match_extras._apply` writes *out* of it — per-player
  cards, penalties, goal minutes, substitutions, and per-team cards-against. On the PitchAPI path
  `ingest_extras` called it; that path is `not af`-gated, so under API-Football nobody did.
  `cards_model` is built entirely on those fields, so it did not fail — it computed, confidently,
  from zeros. **Every player card forecast published at p = 0.0000** (47 lines a fixture), and the
  match card line read 0.390 where the same events give 0.572. And `extras_at` is what
  `score_finished` checks before grading a card forecast, so those worthless lines were never graded
  either: a permanently empty track record on top of a permanently wrong number.
* **Pitch coordinates.** `pitch_x`/`pitch_y` were written as a hard `None` with the provider's `grid`
  string stored beside them, unread. `Match.jsx` draws a player at `(pitch_x || 0) * 48`, so the
  whole eleven piled onto the goal line the moment a real teamsheet arrived. The predicted lineup
  looked right — `queries` computes its own coordinates — so the graphic worked until the lineup was
  published and then broke, which is the worst way round.

## Things that were never called at all

* **The pre-match lineup watch.** `jobs.tick` gates the PitchAPI one behind `not af` and nothing
  replaced it, so `db.lineups` was only ever written *after* a match, by `write_match`. Three
  features depended on a confirmed eleven and all three were dead: the engine fell back to its own
  `p_play` estimates even once the teamsheet was out, the "lineups are in" e-mail never went, and
  `lineups_at` never moved so no forecast was re-fit. `ingest_af.lineup_watch` now covers twenty
  fixtures a call, and a sheet already held is never paid for twice.
* **The injuries feed.** `availability.sync_apifootball` translated our league iid to theirs through
  `images.leagues` — a hand-kept table that defaults to `{}` and that nothing populates — so the
  loop `continue`d on every competition and the feed did nothing, reporting `{"calls": 0}`, which
  reads like a quiet day. Past that it recovered our player iid from an `image_map` row, so a
  player's availability depended on whether we had found his photograph. Both indirections date from
  when API-Football was only a source of pictures. Their ids **are** our `ext_id`s now.
* **Rounds, after a backfill.** `build_frames` filters `round != None` and only the `af_fixtures` job
  assigned them, so a freshly backfilled league had all 96 matches invisible and `run_league`
  recorded `skipped: "no data"` — on a league that had just been fully ingested. It healed itself up
  to six hours later, and until then the recorded reason was untrue.

## Two players, one club: the transfer and the national team

`refresh_player_clubs` moves a player to the club he last played for. It was called **once per
league, with that league's iid** — which scopes "last played for" to one competition. A player who
moved clubs in January, whose last European tie was in September for the old club, was moved *back*
by the European league's pass, and the two passes fought on every tick. It also had no `as_of`
comparison at all, unlike `upsert_player`, so an older match could overwrite a newer one. And when a
national-team competition is enabled, a player's most recent match is for his country — so his club
became **England**, on every screen, until he next played for his club.

It is now one unscoped pass, forward-only, that skips `kind == "international"` entirely.

## The admin was reporting the wrong provider's numbers

The user's own complaint — *"why backfill still showing PitchAPI limit"* — was four separate bugs:

* `routes_ingest_admin` read `ingest.daily_call_budget`, PitchAPI's 2,000, instead of the running
  provider's 75,000.
* `images.AFClient` incremented a private counter and never wrote `api_call_log`, so **every crest,
  photo and injury call was spent against the one real API-Football quota while being invisible in
  every screen that reports spending**. Two private budgets against one allowance, with the admin
  showing one of them.
* `apifootball.Client._calls_today` counted *every* row in the shared `api_call_log` with no provider
  filter, so another provider's calls could refuse this one's work for the rest of the day.
* `admin_home.feeds()` counted `status: "queued"`, a value nothing in the codebase writes
  (`enqueue` writes `pending`), so the one screen whose job is to answer "is the feed backed up"
  showed a hard-coded zero.

Plus: a transient image failure — a 503, a 429, a dropped connection — was recorded as permanently
`missing`, and the sync loop skips any row with `missing` set. **For ever.** One blip denied a club
its crest until an admin cleared the row by hand, and it looks exactly like a provider that has no
picture. A 404 is their answer and is worth remembering; nothing else is.

`purge.unknown()` permanently reported `alert_subscriptions` as a collection it had never been told
about — a warning no action could clear, sitting at the top of the admin. `features.live` still
described SportAPI. A live test asserted that `photo_plan`, a job deliberately removed, had run
successfully, so it could only ever fail, for the one reason that is not a bug.

## The one that was about to get worse: a vocabulary with four readers and three dialects

`normalize_af.events` is now the **single** translator for both the live and the historical path.
That was a deliberate simplification and the right one, but it doubled the blast radius of any
mistake in it and removed the second implementation that used to disagree visibly. It emits five
words -- `goal`, `missed_penalty`, `yellow`, `red`, `sub` -- and three of its four readers were
still speaking the retired provider's dialect:

* **`follow_alerts`** queried for `red_card` and `second_yellow` as event *types*. Those words are
  never written, so the Mongo `$in` matched nothing: **a sending-off reached no follower at all.**
  `own_goal` and `penalty` were likewise queried as types when they are now booleans on the row, so
  an own goal was e-mailed as a plain "Goal" **for the side that conceded it**.
* **`MatchEvents.jsx` and `LiveBits.jsx`** keyed on `yellow_card` / `red_card` / `second_yellow` /
  `substitution`. Of everything the writer actually produces, only `goal` had a label; `red` and
  `sub` fell through to the grey "unknown" fallback and were captioned with the raw column word.
  `Match.jsx` meanwhile counted cards with `e.type === "yellow" || e.type === "red"` -- correct, and
  on the same page. One screen, two vocabularies. And `e.type !== "substitution"` no longer excluded
  anything, so a substitution could become a live card's headline "last event".

And the translator itself mistranslated one event. **A missed penalty was stored as a scored goal.**
API-Football reports one as `{"type": "Goal", "detail": "Missed Penalty"}`, and keying on `type`
alone made it byte-identical to a converted penalty: same `type: "goal"`, same `penalty: True`. This
mattered far more after the `_apply` fix above than before it, because `_write_events` now derives
from these events: a 5th-minute miss became the match's **first goal**, named the man who missed as
`first_scorer_iid`, credited him `pen_goals += 1` and an entry in `goal_minutes`, and inflated the
referee's penalty rate -- on both paths, for every league. The front end has had a `missed_penalty`
label sitting there, waiting for a word the normalizer never produced.

The vocabulary now lives in one place on each side -- `normalize_af.EVENT_TYPES` and
`frontend/src/components/eventWords.js` -- and a test asserts that every reader understands every
word the writer can emit, by running the front end through node rather than grepping it. That single
assertion would have caught all three of these at once, and it is the same assertion that would have
caught the dead `team_saves` column.

## The branch with zero execution

`live_af`'s in-play statistics and lineups sat behind `apifootball.live_stats`, which shipped **off**
and which **no test anywhere switched on** -- so that whole branch had no execution in a 58-file,
2,810-check suite. It is where two of the live path's bugs were hiding, and with it off
`GET /api/live/{sid}/lineups` answered `{}` with no error: a feature that stopped existing quietly.
It is on by default now (one call per twenty matches actually producing statistics -- a few hundred
on a busy Saturday out of 75,000), and a test drives the real tick through a mocked transport and
asserts the endpoint serves eleven named starters a side.

`ingest_af.drain`'s stranded-task recovery also ran once, at entry, and `release_stuck` only frees a
task older than its own threshold -- so a batch that same drain left mid-flight was not recovered by
it, whatever the commit message claimed. It now re-checks as it goes.

## Tests that could not fail

Six assertions were found that pass for every possible input, each guarding something that had
already broken at least once:

* `len(SP.events_for(db, 1)) >= 0` -- true for every value. The surviving half only counted rows in
  Mongo and never looked at what the route returned. Before the live path was fixed, this exact line
  passed while the route handed the page `{'type': 'Card', 'side': None, 'minute_num': None}`.
* `thr <= {...}` -- `set() <= anything` is True, so it passed if `run_league` published **no
  forecast at all**, which is the failure it exists to catch. It was also a hand-written set that
  broke the moment a market was added, which registering the three markets promptly did. It now
  derives the expected set from the settings and requires it to be non-empty.
* `P.unknown(db) == []` against a fixture seeded from purge's own lists -- a tautology. Asked
  against the collections `mongo_init` really creates, it failed, which is how `alert_subscriptions`
  was found.
* `"saves" not in [m for m in ALL_PLAYER_STATS if m not in MARKET_POSITIONS]` -- every market
  *except* saves, so it restated the line above it and asserted nothing about the claim in its own
  message.
* `total >= 0` for a document count -- the `verified` filter was only asserted to return *a number*.
* Two assertions over-specified against their own messages (`phase_of("TBD") is None`,
  `status_text("HT") == "Live"`) and were blocking correct changes -- the first contradicted
  `selftest_normalize_af`, which has always asserted `TBD -> scheduled`.

## What is pinned

`tests/selftest_audit_v11.py`, 130 checks, every one of them executing the real function:
the involvements fix on a no-assist fixture, the sot fix, the untracked-block case that must
*still* read `None`, the bench man, the one-sided squad, the team zero-fill and the possession
mirror, a renamed display string that must still surface as missing, the pitch coordinates of a
4-4-2, the three markets reaching the publish loop, the GK decision no longer reading module state,
`build_frames` returning `None` instead of raising, the national team and the backwards transfer,
a 503 versus a 404, the provider's own budget, the derived card fields, and the lineup watch end to
end through a mocked transport -- including that a sheet already held is not fetched twice; the
five-word vocabulary against all four of its readers, the front end included, by running it; the
missed penalty that must not become the match's first goal; and the live tick storing lineups the
endpoint can actually serve.

Three of the existing files had assertions standing on the old, measured-wrong behaviour. Those were
reversed rather than deleted, each with a note on what it used to claim and why that was the bug --
`selftest_normalize_af` had asserted, in so many words, that an absent assist column should null a
scorer's goal involvement.

## The hole the whole suite had

Separately from the defects, the 58-file, 2,810-check suite had a structural gap: **nothing carried
API-Football rows into any product-level reader.** The provider boundary was tested
(`selftest_ingest_af`, `selftest_normalize_af`, `selftest_apifootball`) and the downstream was tested
(`selftest_lines`, `_queries`, `_markets`), and every test that drives `build_frames` seeds
PitchAPI-shaped documents. That seam is the mechanism behind every silent death in this document: a
column can be written correctly, read correctly, and still never arrive.

There is now a test that ingests 56 fixtures through the real `sync_fixtures` and `drain`, assigns
rounds, measures coverage, and then asks the engine what it can see. It asserts
`MARKETS_WITH_DATA == {shots, sot, tackles, fouls_committed, goal_involvements, saves}` — all six,
including the three the market gate was dropping — that keepers are in the frame, that the team
saves and goal-involvements columns are not columns of zeros, and that the card fields and
`extras_at` were derived. Not "the column exists", which is what the old tests checked.

## The six-hour delay on a finished match, and the page that never showed its numbers

Reported after the audit: *"the stats updated with a delay... I know that pitchapi is still serving
the match page final stats, because I had it on before, and it would show exactly the same and the
same delay after the game."* The delay was real. The provider was not the cause -- and the reason it
felt identical is that PitchAPI's `results_sync` ran on the same six-hour cadence.

**One place in the entire codebase queued a finished match's statistics:** `sync_fixtures`, called
from the `af_fixtures` job every `ingest.fixtures_sync_hours`, default **6**. And when it ran it
read `/fixtures` through a cache whose TTL is `cache.ttl.fixtures_future_hours` (6h) off a match
day -- so the job could run and still be handed a list in which the match was `scheduled`, and queue
nothing at all. `on_match_day`, which selects the short 1-hour TTL, counted only fixtures still
SCHEDULED in the next 24 hours, so the moment the last match of a round kicked off the league
stopped looking like a match day, exactly when the results were landing.

Meanwhile the live tick had known all along. `live_af` stamps `final_at` the instant a status flips
to a final short -- and did nothing with it. It now enqueues the match there, which turns six hours
into about a minute at no extra call, because that bundle was going to be fetched anyway. The
match-day window now counts the six hours *after* a kick-off as well as the twenty-four before.

**And the match page never showed the match's statistics at all.** `match_detail` returned
forecasts, events, lineups, a style model and a recap, and no `stats` key. `live_stats` had exactly
one reader in the whole codebase -- `live_track`, deciding whether a live forecast had landed -- and
no display. What the page labels as team style is `team_styles`, a historical model the engine
rebuilds, which by design does not move during a match. So on the one page a reader opens to find
out what happened, there was no way to see how many shots there had been.

`match_detail` now returns a `stats` block: `team_match_stats` once the match is ingested,
`live_stats` while it is being played, both carrying the same columns so no row appears for the
first time at the whistle. The live team block was widened from the four columns `live_track`
happened to need to all of `TEAM_COLS` plus saves, summed from the players the way the finished path
already does. `MatchStats.jsx` draws them as opposed bars, reusing the kit's own home/away pairing
and the flex-grow technique `FirstGoal` and `Momentum` already use -- a layout, not a new visual
language.

## The live snapshot that became the final result

Found while tidying up after a parallel session's match-page rewrite, and the most serious defect in
this document.

`/fixtures?ids=...` is **the same cache key for the live path and the final path** -- it is the same
request whether a match is in its 67th minute or over. `live_af` fetched it with `ttl=None`, which
`apifootball.fetch` documents as caching FOR EVER. So:

* the in-play statistics **froze at the first fetch of a match**. Every later tick was served the
  same cached answer, and a figure taken in the 20th minute stood for the whole ninety.
* that mid-match answer was then handed to `ingest_bundle` as the finished match, so
  `team_match_stats` recorded the 67th minute as full time -- permanently, because the entry never
  expired.

It was invisible while `apifootball.live_stats` shipped off, since nothing fetched the live bundle
at all. Turning that on, earlier in this same pass, is what made it reachable. The live bundle now
expires after 45 seconds, and `ingest_bundle` forces a fresh answer, which costs no extra call --
only a cache miss on a call it was going to make anyway.

Two smaller faults came out of the same investigation:

* **A match ingested at the whistle kept `status: "scheduled"`.** `sync_fixtures` used to be the
  only thing that queued a finished match and it sets the status as it goes; the new live-tick
  enqueue reached `write_match` without touching the match row. `queries._match_stats` returns
  `(None, [])` for anything that is not final, so the page showed **no statistics at all** on a
  match whose numbers were already in the database -- until the next six-hourly sweep corrected it.
  That is the delay this change set out to remove, one layer further up. The ingest now records the
  status and score from the bundle it already has.
* **`_live_stats` dropped the saves column**, because it maps `normalize.TEAM_COLS` and saves is not
  in it, while the finished row adds `team_saves`. The Saves row appeared for the first time at the
  whistle -- a number that looks as though it changed when all that changed is which document was
  read.

The dead code from the merge went with them: `_stats_block`, `MATCH_STAT_COLS`, the `stats` key in
`match_detail` (computed on every request, read by nothing) and fifteen orphaned CSS lines.

## Still open, and not ours to close

* **Credentials committed to the repository and present in git history** across 740 tracked files
  under `.emergent/`, `test_reports/` and `memory/`: an owner e-mail, `ADMIN_INITIAL_PASSWORD`, a
  post-setup password, a `__Host-sid` session cookie and a TOTP secret. These need rotating, 2FA
  reset, sessions revoked, then `git rm -r --cached`, `.gitignore`, and `git filter-repo`. Repeatedly
  flagged; still not done.
* **`ENV=production` is unset** on the deployed site, so `/docs` and `/openapi.json` are public and
  the CSP is not applied. **`PUBLIC_BASE_URL` is unset.**
* **Nobody has read API-Football's terms on storing and serving their images** (docs/19 §8).
