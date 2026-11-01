# 41. A player on loan showed his old club

Written 2026-11-01. Reported: a Real Madrid player on loan at Fiorentina still showed Real Madrid on his profile,
with Real Madrid's next fixture and "No forecasts for this player yet" — while the same page correctly headed his
ranks **"Serie A rank this season"**, because his stats came from Serie A. The club was wrong; the stats were right.

## What was wrong

`players.team_iid` had exactly one writer, in `ingest.ingest_match`:

```python
pid = upsert_entity(db, "players", p["ext_id"], {"name": ..., "team_iid": tid, ...})
```

It set the club from whatever match was being processed, with no regard to when that match was played. **The queue
does not run in date order**: `process_queue` sorts by `priority, next_run_at`, a backfill walks dates in its own
order, and since docs/36 H4 a failed task is retried later with a back-off. So an older match ingested after a
recent one put the player back at the club he had left, and he stayed there until some later match happened to
overwrite it again.

The page that showed the symptom, `queries.player_detail`, reads `players.team_iid` for both the club and the next
fixture:

```python
nxt = db.matches.find_one({"status": "scheduled", "kickoff": {"$gte": now},
                           "$or": [{"home_iid": p["team_iid"]}, {"away_iid": p["team_iid"]}]}, ...)
```

so a stale club also produced the wrong next match — and then "No forecasts for this player yet", because the
engine had (correctly) made his forecasts for his **new** club's fixture, not the one being displayed.

The engine itself was never wrong: `soccer_brain/engine.py` takes a player's club from his latest row
(`g["team"].iloc[-1]` after sorting), which is the rule the rest of the app should have followed.

## The fix

**`ingest.upsert_player`** replaces the blind write. It records `team_as_of`, the kick-off of the match the club
came from, and only moves the club when the new match is at least as recent:

- a later match moves him, so a real transfer or loan is followed;
- an earlier match arriving afterwards leaves the club alone;
- name and position still update from any match.

**`ingest.refresh_player_clubs(league_iid=None)`** repairs rows written before this existed: one pass over
`player_match_stats`, newest first, putting each player at the club he last played for. It runs per league in the
daily job next to `update_coverage`, and is idempotent — a second run changes nothing.

## What this does not fix

A loan is only noticed **once the player has played a match for the new club**. If he moves in the window and has
not featured yet, the profile still shows the old club, because match stats are the only source of a player's club
we have. Fixing that needs squad or transfer data from the provider, which is not mapped (docs/08). Worth knowing
before the next transfer window: expect a lag of one appearance.

## Files

| File | Change |
|---|---|
| `backend/ingest.py` | `upsert_player` with `team_as_of`; `refresh_player_clubs` to repair existing rows. |
| `backend/jobs.py` | The repair runs per league in the daily job. |
| `backend/tests/selftest_player_club.py` | New. An older match ingested afterwards does not move him back; a later one does; the repair pass fixes an already-wrong row and is idempotent; the profile then names the right club and the right next match. |
