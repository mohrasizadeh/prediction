# 31. Live tracking and earned tiers

## 1. Live tracking: forecasts tick green as they happen

### What it does
On a live match, the Forecasts tab shows for every line we can follow how far it is. A line that has passed its mark turns green with "Happened". A line still counting shows "2 of 4 so far". After full time, a line that did not reach shows "Did not happen". A line we cannot count shows nothing. We never show a tick we cannot back.

- Page: `Forecasts` in `MatchCentre.jsx`, `ForecastCard` (`track` prop), refreshes every 30 seconds while the match is live.
- API: `GET /api/matches/{id}/live-forecasts`. Reads our database only. Returns `{active, final, items: {fkey: {state, current, needed, source}}}`. `state` is `live`, `hit`, `missed` or `unknown`.
- Code: `backend/live_track.py`.

### Where the counts come from
| Line | Count from | Works today |
|---|---|---|
| Match yellow cards (for example 4+) | SportAPI events (`live_events`) | Yes |
| Player yellow card (1+, 2+) | SportAPI events, matched to our player inside the right club | Yes, when the name matches with confidence |
| Team and player shots, shots on target, corners, tackles | SportAPI live statistics (`GET /api/fixtures/{id}/stats`), stored in `live_stats` | **Not verified** |

The statistics endpoint is listed in SportAPI's endpoint list (doc 23) but we have never called it, and we do not know the exact answer shape. So it is built, tested on three plausible shapes, and **switched off**.

### To turn on live statistics (needs your key)
1. Admin > Keys: SportAPI key saved.
2. Find a live fixture id (`sid`) in Admin > Data > Leagues or `GET /api/live`.
3. Call `GET /api/admin/sportapi/stats-probe/{sid}` (permission `jobs.run`). It returns the raw answer and what we read from it.
4. If a statistic is missing in `read`, add the name SportAPI uses to `sportapi.stats_keys` (lower case) and probe again. If the shape is different from all three we accept, send us the raw answer and we add it.
5. Turn on `sportapi.live_stats`. It costs one call per live match every `sportapi.stats_refresh_s` (180) seconds, and it stops at the live reserve. Ten matches at once for 100 minutes is about 330 calls.

If the statistics answer has no player rows, player shots stay "unknown" and team lines still work.

### Notes and assumptions
- A second yellow counts as a booking for card lines. Check this against PitchAPI's yellow count (the score of a finished match).
- A statistics call that fails is reported in the job result (`stats_error`) and never stops events, full-time details or lineups.
- If an event's player cannot be matched to ours with confidence, that card is not given to any player. A player line is then marked hit only if his own events already passed the line.
- Not yet on: Following, My combos and Insights cards. The same endpoint feeds them when we add it.

## 2. Earned tiers

### Why
In your last results, 1 of 4 Strong and 3 of 8 Solid happened. If a true 90% line were tested four times, 1 or fewer hits would happen about 4 times in 1,000. For a true 73% line, 3 or fewer of 8 is about 4 in 100. The sample is small, but both numbers point the same way. We found four causes in the code:

1. **Strong was 80%, not 90%.** `engine.tier_strong` was [0.80, 0.70]: p of 80% and a low end of 70%. Our own test (doc 21) had Strong lines stated at 91% on average and happening 88% of the time, because lines at 80% to 85% were in the group.
2. **Likely starters could be Strong before lineups.** A line is "if he plays". With the 80% likely-starter setting, a player with an 82% chance to play and a 93% "if he plays" chance was Strong. His whole chance is 76%, and a non-starter is a miss for you. Track Record hides that, because it only counts players who played.
3. **The yellow-card model dropped the chance to play for likely starters** (`play = 1.0`), so player card lines were too high in the same way.
4. **Nothing checked a label against results.** The calibration map is fitted on 2015/16 StatsBomb data for three leagues. We run eight leagues on PitchAPI numbers.

### The rule now (`engine.tier_mode = earned`, new default)

> **Superseded by `58_the_tier_grades_the_number.md`.** The whole-chance rule and the three
> lineup caps below were removed: the tier grades `p`, the number on the card. The track-record
> check survives, re-keyed on `p` over matches the player played. Kept here for the history.

- **Whole chance.** Player lines before the lineup: p x chance to play. Confirmed starters and team lines: p.
- **Strong:** whole chance 90% or more and low end 84% or more. For a player it also needs a confirmed eleven (`engine.strong_needs_lineup`).
- **Solid:** 80% or more and low end 70% or more.
- **Watch:** 60% or more. An unsure lineup is Watch at most. A bench player has no tier.
- **Track record check** (`backend/tiering.py`). For each market (scope and stat) we look at finished lines with a whole chance close to this one. If they happened clearly less often than the tier promises, the line drops a tier and the card says why ("Similar lines happened 84% of the time"). Not enough finished lines (`engine.earned_min_n`, 40): Strong drops to Solid. The record can only lower a tier. A player who did not feature counts as a miss for lines we stored a chance to play for.
- The percentage on the card does not change. Only the label does.
- `engine.tier_mode = classic` restores the old rule. All cut-offs are settings (Admin > Settings > Engine).

### What to expect
Far fewer Strong lines, and some Solid lines become Watch. That is the point: a Strong should happen about 9 times in 10. After a week of results, run `engine_audit.py` and compare "stated vs actual" per tier. If Strong delivers less than 88%, raise `engine.strong_min` or `engine.earned_min_n`.

## 3. Engine research: what else can move accuracy

What we checked in the engine code and what the research says.

### Factors in the engine today (docs 18, 22, 25)
Dixon-Coles team strength with time decay, style vectors and named tactics, team-total negative-binomial models, lineup effects, player share of team total with a minutes mixture, rest and competition importance, results form and what is at play for each side in the league table, absences, referee card and foul rates, normalised corner averages. Calibration map, then tiers.

### Findings
1. **Calibration is the weak link, not the model.** The map came from three leagues of old event data. It is replaced by a map fitted on our own results once 5,000 results exist (`engine.calib_min_scored`), checked on the newest 30%. Isotonic maps overfit where data is thin, and the top of the range (90%+) is always thin. Earned tiers now protect the top. Action: lower `engine.calib_min_scored` to 2,000 once the audit shows enough results, and keep the 97% cap.
2. **Check the shots on target key.** The registry default maps player `sot` to PitchAPI's `shot_accuracy` (`provider.pitchapi.player_keys`). If that key is an accuracy percentage and not a count, every shots-on-target forecast learned from the wrong number. Open Admin > Settings > provider and Admin > Data > Data quality and confirm with one finished match. This is the first thing to verify.
3. **Game state matters for shots.** A 2025 study of minute-by-minute data (Leveraging Minute-by-Minute Soccer Match Event Data to Adjust Team's Offensive Production for Game Context, arXiv 2508.04008) found teams shoot less when leading and more when trailing, a red card has the largest effect (a team a player up takes about 0.75 of its shots, a team a player down 1.7 to 1.9 times), stronger favourites take more shots, and a negative binomial model beat Poisson. Ours is negative binomial. A heavy favourite who leads early shoots less, so their 4+ corners and 15+ shots lines are less safe than their season average says. Action: add an expected-game-state term (favourite strength) to team shots and corners.
4. **The audit script is the tool.** `engine_audit.py` shows stated vs actual by stat, tier, lineup badge, basis and league, and the cost of "did he play". Run it weekly.
5. **Chance to play is the other half.** `p_play` is a model in itself. The audit prints stated vs actual chance to play. Confirmed lineups from SportAPI arrive earlier than PitchAPI's; the earlier they come, the fewer lines carry that risk.

### Plan, in order
1. Verify the `sot` key and the other registry key maps (data check, no code).
2. Run `engine_audit.py --days 14` on production. Look at lineup badge `likely`, stat `sot`, and the league table. Send us the output.
3. After a week with earned tiers: tier table (stated vs actual). Adjust `strong_min` and `earned_min_n`.
4. Refit the calibration map per stat family and per league once there are 1,500 results each.
5. Add the game-state term for team shots and corners and back-test it with `docs/validation` scripts before enabling it.
6. Add a weekly drift alert in Admin > Needs you: a market whose last 100 results fall 8 points or more under what was stated.

## 4. Tests
`selftest_livetrack.py` (cards, hit, missed, unknown, statistics shapes, route, failing statistics call) and `selftest_tiering.py`. The suite is now 25 files.
