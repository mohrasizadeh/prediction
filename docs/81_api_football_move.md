# 81. The move to API-Football

Decided in docs/80. This is the build: what exists, what each piece knows, and what is still missing
before a backfill can run. One provider replaces three — PitchAPI (history and statistics), SportAPI
(live and lineups) and API-Football's own image and injury feeds, which we were already using.

---

## 1. The client: `apifootball.py`

The only module that talks to `v3.football.api-sports.io`. Modelled on `cached_fetch.py`, so the
house rules carry over: cache first, budget and breaker, log every call, unwrap the envelope in one
place, no vendor SDK.

Three things about this provider belong here and nowhere else.

**Errors arrive as HTTP 200.** A bad key, a season the plan cannot read, a wrong parameter: all of
them are `200 OK` with a populated `errors`, which is a **list when empty and an object when not**.
`_unwrap` sorts them: a rejected key pauses ingest and trips the breaker; a plan limit raises
`PlanLimited` and does neither, because one unreadable league is not a reason to stop reading the
others.

**Their count wins over ours.** Every answer carries the remaining daily and per-minute quota in
headers, which we store and obey. docs/19 settled that rule for the image sync; it is the same rule
here.

**A spike gets the key blocked, not throttled.** Their rate-limit policy says abnormal traffic may be
blocked "without prior notice", permanently. So an empty per-minute allowance is a full stop
(`apifootball.minute_cooldown_s`), not a shrug.

**`/status` is free** and does not count against the quota, which makes it the right key test: the
test never spends the budget it reports on.

### The budget and the pace are the plan's, not ours

The owner is on **Ultra: 75,000 calls a day, 450 a minute**, at
`https://v3.football.api-sports.io`. Neither number is typed into the code as a fact.

**The budget follows the subscription.** `x-ratelimit-requests-limit` arrives on every answer, so
`day_budget()` reads it and subtracts `apifootball.daily_reserve` (500). `apifootball.daily_cap`
(75,000) is only the fallback for before the first answer of the day. It is deliberately **not**
`ingest.daily_call_budget`, which is 2,000 — PitchAPI's figure, and sharing it would cap an Ultra
plan at under 3% of what it allows. We stop at the reserve rather than at zero, so a live tick or a
key test still has calls on a day a backfill has eaten.

**The pace follows the per-minute ceiling.** `X-RateLimit-Limit` is the calls-a-minute cap, and
`_gap()` spreads requests at `apifootball.minute_safety` (0.8) of it — 360 a minute, 6 a second, on
Ultra. Below `apifootball.minute_headroom` (25% of the bucket) the gap stretches in proportion,
because sprinting to zero and then stalling for a cooldown is the same burst with a pause after it.
A 429 waits as long as `Retry-After` says, capped at a minute.

`ingest.rps` is **not** consulted. It is 3, which would cap Ultra at 180 a minute out of 450 — a
backfill two and a half times slower than it needs to be, for another provider's limit.
`apifootball.rps_unknown` (2 a second) covers only the gap before the first answer teaches us the
real ceiling, and is conservative because a free key allows ten calls a minute and a spike gets a
key blocked rather than throttled.

At those settings the whole three-season backfill — twelve forecast leagues, 13,680 matches, 720
calls after bundling — takes about **two minutes and 1% of a day's budget**.

### One call replaces sixty

`/fixtures?ids=a-b-c` takes **twenty** fixture ids and answers with events, lineups, statistics *and*
player statistics for all of them (changelog 3.9.2). PitchAPI needed three calls per match.

| | PitchAPI | API-Football |
|---|---|---|
| one finished match | 3 calls | 0.05 |
| a 380-match season | 1,140 | 19 |
| 3 seasons, 12 leagues | ~41,000 | **~1,000** |

`CALLS_PER_MATCH_BY_PROVIDER` holds this, and the leagues screen reads it through the API. It was
hard-coded as `3` in the route **and again** as a literal `* 3` in the seasons drawer; left alone it
would have overstated every backfill estimate by sixty times.

### The status vocabulary, and the NS trap

Their vocabulary is documented, unlike SportAPI's (docs/23), so `FINAL`, `DEAD`, `NOT_YET` and
`IN_PLAY` are facts. The docs/42 fallback stays anyway: a word we have never seen counts as in play.
`SUSP` and `INT` are in play by their own classification, which suits us.

The trap has its own function. Their documentation: a competition without livescore *"remains in NS
and will be updated in the minutes/hours following the match (this can take up to 48 hours)"*. So
**after kick-off, NS means unknown, not scheduled** — believing it would park a played match in the
upcoming list for two days and never ingest its statistics. `stale_not_started()` names that case so
the ingest re-checks instead.

## 2. Competitions have a role: `af_leagues.py`

The owner's list is about forty competitions across three tiers. Carrying them is free — every plan
has every league — but carrying them the same way would break the engine twice, both times silently.

**A team would change league every time a cup is ingested.** `ingest.sync_league_matches` stamps
`teams.league_iid` from whichever competition the match came from, and `images.py` and the live team
mapper both look clubs up **by that field**. Ingest the FA Cup and every English club belongs to the
FA Cup: the crest sync finds no clubs in the Premier League and the mapper has nobody to match
against.

**And the engine fits one frame per `league_iid`.** A Champions League "league" is 32 clubs playing
eight games each with no common baseline, while those clubs' league frames silently lose those
matches. A Premier League club's shots against a fourth-tier side are not Premier League shots.

So:

| role | what it does |
|---|---|
| `forecast` | fit models, publish cards — **and only these set a club's league** |
| `calendar` | fixtures, results, lineups. Feeds `context.py`'s rotation model and the club page. No cards, no rows in the engine's frames. |
| `off` | known, listed in admin, not ingested |

Domestic divisions are `forecast`; cups, continental and national-team competitions are `calendar`.
That is not a limitation imposed here: docs/18 §3 measured that the midweek tie moves **who starts**
and not team totals, so carrying the cups is exactly how the one layer with a positive signal gets
fed.

**National-team tournaments are `calendar` at best.** The engine has no national-team history, a
player's share of his club's shots says little about his share of his country's, squads turn over
between tournaments, and a team plays three group games. They are a fixtures and content feature
until national-team support is built.

**No league id is written down.** Ids resolve against `/leagues` and are confirmed in admin, because
an id that is quietly wrong maps one competition to another and nothing downstream can tell.
`auto_pick` needs 0.95 and a clear margin; same-name-other-country is scored **down**, because
Serie A is Italian and Brazilian and Premiership is Scottish and not only Scottish.

**Coverage can demote a role.** `supportable_role()` returns what the data supports, not what we
asked for. A forecast league whose seasons carry no `statistics_players` is a calendar competition
whether we like it or not, and saying so in admin beats publishing empty markets and calling it a
quiet week.

The `leagues` collection is the source of truth. It already carried `enabled` and `backfill_seasons`;
`role`, `kind`, `tier` and `catalog_key` join them there rather than in a parallel settings map,
which would be a second place to look and a first place to drift.

## 3. Admin

**Leagues became Competitions.** The screen keeps its shape — switch on, pick seasons, see the cost —
and what changed is where its rows come from. `GET /admin/apifootball/catalog` resolves every
catalogue entry with per-season coverage; `POST /admin/apifootball/confirm` writes the chosen one
into `leagues` with its seasons, so the existing backfill picker works on it unchanged. A confirmed
competition arrives **switched off with nothing queued**: confirming says which competition it is,
not that it has started spending.

The role is a control on every card. Moving a cup or a national-team competition **to** `forecast`
opens a dialog saying what it would do and is audited as `league.role.forced`. The other direction
goes through unasked.

**A new screen, API-Football**, with three tabs: the key and quota (from the free `/status`, with the
provider's own header numbers), the statistic names, and the endpoint explorer.

**`GET /admin/apifootball/types` checks the map against a real answer.** This exists because the
provider identifies a statistic by a **display string** — `"Total Shots"`, `"Ball Possession"` — and
not by a stable id. A rename is invisible: the column goes null, the market drops under
`engine.coverage_min`, and the feed looks like a quiet week. That is the same fragility that left
half of `provider.pitchapi.team_keys` as `null`, with `MODULES.md` admitting the tests proved nothing
about the real names. So the screen reads a finished fixture and lists, by name, everything we map
that was not in it and everything in it that we map to nothing.

`tackles` is `null` on purpose: there is no team tackles statistic, and `normalize.normalize_match`
already sums the players' instead — a fallback written for PitchAPI that covers this exactly.

**The menu has THREE provider entries, on purpose and not for long.** API-Football is there because
its key, quota and mapping screens are how the move gets set up. PitchAPI and SportAPI are still
there because the jobs still call them (§4): the live tick's status and its team-mapping review
queue are controls for a feed running right now, and taking them out of the menu before the
pipeline moves would leave them reachable only by typing a URL. The Home tiles and the feeds panel
name the provider actually serving each one, so the health board never claims a feed we have not
moved. All of that goes in the same change that moves the pipeline.

`provider.source` defaults to `pitchapi` for the same reason. It only feeds the admin's cost
estimate today, and pointing it at API-Football while the ingest still spends three calls a match
would understate every backfill by sixty times — the exact inverse of the bug the estimate already
had.

## 4. What is NOT built yet

Honest list, because the admin is ready and the pipeline is not.

1. **`normalize_af.py`.** Their JSON into the same dicts `normalize.py` returns, so `ingest.py`
   changes only in which client it calls. **The absent-or-zero guard is rebuilt here** (docs/78
   §5.2): absent still means zero-or-untracked, and the new rule is whether the type is present for
   any *other* player in the same fixture. Nested objects help — `tackles: {total: null}`
   present-but-null is distinguishable from the object being absent.
2. **The extra-time rule.** Flat `statistics` sums extra time into the match total with no marker, so
   a 120-minute cup tie inflates every team-total model. Decide before the first backfill, because it
   is baked into every row afterwards.
3. **The purge.** Clearing the PitchAPI and SportAPI collections. Dry run with per-collection counts
   first, and the owner runs it: a cloud session has no database access.
4. **The backfill runner**, on `fixtures_bundle`, paced against the per-minute allowance.
5. **Per-league coverage.** `engine.coverage_min` measured globally would let one well-covered league
   carry a market that is empty in nine others.
6. **The images question.** docs/19 §8 is still open and now matters more: we store and serve their
   crests and photos, their own documentation says they do not own the images, and nobody has read
   their terms.

## 5. What this costs, and what it does not buy

**~$19/mo (Pro, 7,500 calls a day)** is enough: the whole three-season backfill is about a thousand
calls and an afternoon. Every league is included on every plan, so there is no league budget to
spend — which is why the rotation layer is better fed here than on a thirty-league cap (docs/80 §4).

It does not buy accuracy. docs/80 §9 has the measured reasons: the layers that richer data would
feed were tested on real football and returned −0.0016 (z −3.1) for style indices, and about zero
even when handed the true lineup shape and the true number of changes. The provider decision is
accuracy-neutral by construction. What moves accuracy here is the absent-or-zero guard, settling
`engine.interactions`, and getting 5,000 scored forecasts on the board so the calibration map makes
"Strong" mean what it says.
