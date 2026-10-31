# 27. Player lines are "if he plays", with a lineup badge

**Why.** A card said "1+ shot 82%" for a striker who had a shot in 9 of 9 games against a weak side. The 82% mixed two questions: will he play, and will he shoot if he does. The first question hid the second one.

**What changed.**
1. A player's percentage now assumes he plays. We divide out his chance to play.
2. His chance to play moves to a **lineup badge** on the card.
3. Players who are unlikely to play get no card.
4. The calibration map is refitted for these numbers.

Team lines do not change.

## 1. The test (real data, walk-forward)

Data: StatsBomb open data, 2015/16 Premier League, Serie A, Ligue 1. We refit on earlier dates only, forecast the next dates, and compare each percentage with what happened. 140,195 player forecasts before lineups. Scripts: `docs/validation/audit_real.py` (set `COND=1` for the new number) and `fit_calibration27.py`.

**Before the change (chance to play folded in), 1+ shot, forecast 80 to 85%:**

| Forecasts | We said | It happened |
|---|---|---|
| 98 | 81.6% | 89.8% |

Of those 98 players, 92% played, and 97.8% of those who played had a shot. The 82% was low because of the 8% who did not play.

**After the change ("if he plays"), players who played, 1+ shot:**

| We said | n | We said (avg) | It happened |
|---|---|---|---|
| 50 to 60% | 2,754 | 55.1% | 54.8% |
| 60 to 70% | 2,679 | 65.0% | 66.4% |
| 70 to 80% | 2,336 | 74.7% | 75.6% |
| 80 to 85% | 820 | 82.3% | 84.4% |
| 85 to 90% | 591 | 87.2% | 87.1% |
| 90 to 95% | 301 | 92.2% | 95.3% |
| 95 to 100% | 63 | 96.3% | 96.8% |

The number is accurate, so **before lineups we ship it with no correction map**. The same check for 2+ shots and 1+ shot on target is accurate up to 70%. Above that, the engine is a little cautious (2+ shots, 70 to 80%: said 74%, happened 80%, n 327).

**Confirmed lineups.** A map helps: log loss improves in each league when it is held out (z +10 in Premier League, Serie A and Ligue 1). The map is in `soccer_brain/calibration_default.json`.

**Limits, said plainly:**
- One season of three leagues. The sample above 90% is small.
- "Played" means at least one minute. A player who comes on for two minutes counts.
- The test checks the number, not whether a card is useful. Card order is unchanged (doc 25).

## 2. Lineup badge

Field on each forecast: `lineup_badge`.

| Value | When | Card text | Tiers allowed |
|---|---|---|---|
| `confirmed` | He is in the announced eleven | Confirmed starter | up to Strong |
| `likely` | No lineup yet, chance to play 85% or more (`engine.likely_starter_p`) | Likely lineup | up to Strong |
| `unsure` | No lineup yet, chance to play under 85% | Lineup not sure | Watch only |
| `bench` | Lineup is out and he is not in it | On the bench | Watch only |
| `null` | Team forecast | none | as before |

`tier_note` says why a card is Watch: "Watch until lineups are out" or "On the bench: Watch only".

`p_play` is still on every forecast. Use it for the badge detail and the pitch view. Do not use it to change the percentage.

## 3. Who gets a card

Before lineups, a player with a chance to play under 50% (`engine.min_p_play`) gets no card. Confirmed lineups always show. Without this rule, a rarely used player could show a high "if he plays" number.

## 4. Settings (two new, 216 in all)

- `engine.condition_on_play`, on. Off brings back the old all-in number, and the old calibration map (`calibration_default_allin.json`).
- `engine.min_p_play`, 0.5.

## 5. Calibration and outcomes

- Each stored forecast has `p_basis`: `played` for player lines under the new rule, `all` otherwise.
- `forecast_outcomes` keeps `p_basis`. The weekly refit uses only matching rows. New-style player rows are judged on players who played. Old rows are never mixed in.
- Until enough new rows exist (`engine.calib_min_scored`), the shipped map stays.

## 6. Screen changes

1. **Lineup badge on every player card**, from `lineup_badge`, using the table above. It replaces the "Likely starter" chip from update 25. One small chip, muted for `unsure` and `bench`. Team cards show no badge.
2. **Caption under the percentage on player cards:** "if he plays", small and muted. Team cards show nothing.
3. **Detail sheet:** add a line "Chance he plays: {p_play}%". Show it only here. Never write your own reason text.
4. **Finder rows:** show the same small badge next to "Next {p}%". Use `forecast.lineup_badge`. Hide it if missing.
5. **Insights filter:** add a filter chip "Confirmed or likely lineup" that passes nothing new to the API. Filter on `lineup_badge` in the response.

## 7. Known gap (not in this update)

A forecast above 95% is still dropped by `engine.line_band`. A "1+ shot" line for a regular starter can fall there, so the Finder shows no "Next" for him. See the answer in chat: save all lines, flag the ones outside the band, and show "95%+". We will build it if you ask.

## 8. Done when

- 18 PASS lines, including the new "if he plays" block in `selftest_lines.py`.
- A regular starter with a long run of games at the line shows a higher percentage than before for the same line, with the "Likely lineup" badge. (An 82% card becomes about 90% when his chance to play was about 90%.)
- A player with a 40% chance to play has no card before lineups.
- A player on the bench of a confirmed lineup shows "On the bench" and Watch at most.
