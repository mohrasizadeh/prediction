# 88 — The ingest that was missing

## What was wrong

`apifootball.py` could talk to them. `normalize_af.py` could turn their JSON into our shapes. Both
were written, both were tested, and **nothing joined the two**:

```
who calls fixtures_bundle() outside apifootball.py  ->  NOBODY
who calls normalize_af                              ->  NOBODY
```

So every fixture, lineup and player row in the database still came from PitchAPI, and the live tick
still came from SportAPI. "Move to API-Football" had been half-done for long enough that the admin
menu carried a comment explaining why the old provider screens could not be removed yet.

This is the half that was missing.

## The two calls, and why the shape of this module follows from them

```
the schedule   GET /fixtures?league=&season=    one call per league-season, no statistics
the detail     GET /fixtures?ids=a-b-c...       TWENTY fixtures a call, everything attached
```

`/fixtures?ids=` returns events, lineups, team statistics and player statistics inline for up to
twenty fixtures at once (docs/82 §4). **0.05 calls a match, where PitchAPI needed three.** That is a
sixtyfold difference and it is the only reason a three-season backfill is affordable.

So `ingest_bundle` takes a **list**, never a match. A caller holding one match passes `[match]`. The
saving is real only in bulk and the interface should not tempt anyone to loop.

## One writer, two providers

`ingest.write_match(db, match, out)` was extracted out of `ingest_match` and is now the only thing
that writes `team_match_stats`, `player_match_stats` and `lineups`.

Everything in it is about our schema and none of it is about a provider: the per-side team rows, the
`_against` columns, `team_goals`, `team_fouls_committed`, `team_goal_involvements`. A second copy for
API-Football would have been sixty lines of that drifting quietly out of step with the first — and
the comments in it explain that these columns must ACCUMULATE, because the engine reads
`engine.history_rounds` back and a column added later starts empty. Two copies, and half the history
would have been written with one set of columns and half with another.

The normalizers return the same shape on purpose (docs/85). That is what makes one writer possible.

### A distinction worth keeping straight

Two different numbers are both called a team's shots, and both are right:

| | |
|---|---|
| `team_match_stats.shots` | the team STATISTICS block — 14 |
| `player_match_stats.team_shots` | the sum over the players we have — 4 |

The engine builds a player's rate as his **share** of the second, so the denominator has to be the
total of the players it is sharing between or the shares do not sum to one. `normalize.py` says so
at its own `totals`. A test pins both, because the first time this was written the expectation was
the other one.

## The stamping rule

`teams.league_iid` is stamped by whichever competition ingested a club last, and `images.py` and the
engine both read clubs back by it. Ingest the Champions League after the Premier League and every
English club points at the Champions League — wrong frame, and wearing the wrong crest.

So **only a forecast competition stamps it** (`af_leagues.is_forecast`). A cup or calendar-only
competition upserts the clubs it needs to write a fixture and leaves the stamp alone. Pinned by a
test that ingests a league, then a cup, and asserts the club did not move.

## The switch

`provider.source` decides, read once at the top of the tick. The PitchAPI steps are skipped
**wholesale**, not one at a time, because the two providers key entities on different `ext_id`s: a
league ingested by both is every club and player stored twice (docs/78 §5.1). A half-switched tick
is not a degraded tick, it is a corrupted database.

`selftest_ingest_af.t_the_tick_runs_one_provider_only` passes a PitchAPI client whose every method
raises, and runs a whole tick. Any call at all fails the test.

Images follow the same switch. API-Football carries the logo as a URL on the entity, so `images.py`
needs no provider call at all; `pitch_photos.py` (one call per player, `cdn.pitchapi.dev`) is not
merely redundant there, it is a second source of truth for the same crest.

## Two bugs the tests caught

* **`drain` queried `run_at`; `ingest.enqueue` writes `next_run_at`.** The query matched nothing, so
  the drain reported an empty queue while the queue was full. A silent no-op, not an error — the
  kind of bug a test catches and a run does not.
* The `team_shots` expectation above, which was wrong in the test rather than in the code.

## Live: a lookup, not a guess

`live_af.py` replaces `sportapi.live_tick`, and most of it is about what it no longer has to do.

SportAPI was a SECOND provider beside the data provider, so nothing it said could be joined to
anything we held without guessing. `map_team` matched club names; `link_match` then guessed which of
our fixtures that was from two club ids and a kick-off time; `sportapi_team_map` cached the guesses;
the admin carried a review queue for the ones it could not make. Every one of those exists because
the two sides had different ids for the same club.

API-Football's live feed returns OUR fixtures, with the id already stored as `matches.ext_id`:

    db.matches.find_one({"ext_id": str(fixture_id)})

No name matching, no cached guesses, no review queue, and no bug where a live score lands on the
wrong match because two clubs in a league share a short name.

**Events come free.** `GET /fixtures?live=a-b-c` returns every in-play fixture in those leagues with
its events INLINE -- one call a tick whatever the number of matches, with goals and cards arriving
beside the score. SportAPI needed a call per fixture for events. The feed restates the whole event
list each poll, so events are replaced rather than appended; appending would rewrite a goal on every
tick for the rest of the match, which a test pins.

Statistics are the exception -- not on the live payload -- so a fixture actually producing them is
refreshed through `fixtures_bundle`, twenty at a time, and only when `needs_stats` agrees: half time
is live and barren, and a call spent then buys nothing.

`routes_live._tick` switches on the same `provider.source`. Two live feeds writing `live_fixtures`
at once would be two rows a match keyed differently -- SportAPI by its `sid`, API-Football by our
`ext_id` -- and the pages would read whichever they found first.

## Images: the map is an identity

`images.py` scored our club names against a league's squad list to find an API-Football id, at a
call per league and per club, with a review queue for what it could not decide. That whole apparatus
-- `images.leagues`, `images.team_aliases`, `images.min_confidence`, the scoring, the queue -- exists
for one reason: the entities came from PitchAPI and carried no API-Football id.

Ingested from API-Football, `leagues.ext_id`, `teams.ext_id` and `players.ext_id` **are** those ids.
So `identity_map()` writes the map directly: no calls, no scoring, nothing to review, and no bug
where two clubs with similar names swap crests. It touches only rows whose provider is
API-Football, so a database still holding PitchAPI entities keeps the matching path for those.

## What is still not done

PitchAPI and SportAPI are still present. They are now unreachable whenever `provider.source` is
`apifootball` -- the job tick, the live route and the image mapping all switch on it -- but the code
is still there and still removable only after real data has landed through this path. docs/87 §0 has
the order.
