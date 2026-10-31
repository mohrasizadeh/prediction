# 30. SportAPI owns the match, a better matches page, and the engine audit

## 1. What changed

### SportAPI is now the source for the match itself
Kick-off time, status (not started, live, full time, postponed, cancelled) and score come from SportAPI for every match it follows. PitchAPI keeps the statistics, history and everything the engine learns from.

- `sportapi.overlay(db, matches)` puts the SportAPI values on a match row. It runs inside `fixtures_for_date`, `_with_teams` (team, league and head-to-head lists) and `match_detail`.
- A match that SportAPI moves to another day leaves the old day and shows on the new one.
- A match that SportAPI finishes shows the final score at once. PitchAPI statistics follow when its ingest catches up. The engine still waits for PitchAPI.
- A postponed or cancelled match shows that state on Today and on the match page.
- A match SportAPI does not follow keeps the PitchAPI values.
- `match_days` (the date strip) includes days only SportAPI knows. It now groups the days in Python. The old database query failed on the in-memory test database, which is the error we saw in the demo.

### Upcoming fixtures from SportAPI
The minute job now loads the next days one call each: `sportapi.upcoming_days` (default 7) and `sportapi.upcoming_interval_h` (default 6). That is about 7 calls every 6 hours: roughly 28 a day of the 2,000. It stops when only the live reserve is left.

Live events and lineups already came from SportAPI (doc 23). No change there.

### Matches page
- Today refreshes itself every 30 seconds on the current day (`useApi(path, query, { every })`, paused when the tab is hidden).
- Rows: status column (live minute, FT, kick-off and "in 2h 10m", Postponed), a score column, the win/draw/loss bar under the teams, the insight chip on the right.
- Live matches sort first inside a league, leagues with live matches sort first on the page, and the league header shows "2 live".
- Postponed rows are muted and struck through, with no insight chip.
- Match page: date line on top, one action row (Follow, Share) at the bottom, a Postponed state, no countdown or "Lineups confirmed" on a postponed match, and a 30 second refresh while live.

## 2. Engine audit (new)
`backend/engine_audit.py` reads the real database and prints where accuracy is lost. Read only.

```
MONGO_URL=... DB_NAME=... python engine_audit.py --days 14
```
It prints, for the last N days and for everything before:
1. Match result chances: log loss and Brier against "always the league average", with the skill percentage, top pick hit rate, and average chance vs actual for home, draw, away.
2. Lines: stated vs actual by scope and stat, tier, state (before or after lineups), lineup badge, basis, stated-chance band and league.
3. The cost of "did he play": share of player lines where the player did not feature, stated vs actual chance to play, and the whole chance (p x p_play) against what happened.

`score_finished` now stores `p_play`, `lineup_badge` and `kickoff` with each scored result. Older rows lack them, so the badge and chance-to-play tables fill up from now on.

### What we tested on the engine
The likely-starter setting (80%) sets a player's minutes to a starter's and drops the chance-to-play discount before lineups. We suspected this made pre-lineup chances too high. We tested it on a simulated league: the shortcut gave 34.7% stated against 33.3% actual, and the exact "if he plays" figure gave 37.8%. So on simulated data the shortcut is closer, not further. Simulated minutes are not real minutes, so this does not settle it. Run the audit on real results and look at the `likely` rows in "by lineup badge". If stated runs more than 3 points above actual there, raise `engine.likely_starter_p` (for example to 0.9) first. It is one setting and it is reversible.

## 3. Tests
`selftest_overlay.py` (moved kick-off, live and final score, postponed, date list, upcoming loading) and `selftest_audit.py`. The suite now has 23 files.

## 4. Not done, and why
- Real engine accuracy on your last matches. We have no access to your database from here. Run the audit and send the output, or export `forecast_outcomes` and `match_probs`.
- SportAPI behaviour on your real plan. The overlay and polling are tested against a fake client. Check Admin > Data > Cache and usage after a day for the call count.
