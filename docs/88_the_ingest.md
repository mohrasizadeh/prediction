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

## What is still not done

* **The live tick is still SportAPI.** `apifootball.live_fixtures()` exists and nothing calls it.
  Same shape of gap as this one was, one layer up.
* PitchAPI and SportAPI are still present and still removable only after real data has landed
  through this path. docs/87 §0 has the order.
