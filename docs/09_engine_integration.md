# 09. Engine integration (the forecast brain)

The engine is plain Python (numpy, scipy, pandas). It is in `backend/soccer_brain/`. It reads data frames, learns from past games, and returns forecasts with a likelihood, a band, a tier, and reasons. `backend/engine_bridge.py` connects it to MongoDB. The bridge passes `selftest.py`.

## 1. Files

| File | Job |
|---|---|
| `core.py` | Recency weights, shrinkage, negative-binomial probabilities, tiers, reason sentences, metrics |
| `nbglm.py` | Negative-binomial regression with an offset and relative ridge penalties |
| `strength.py` | Dixon-Coles team strength → expected goals and win/draw/loss |
| `engine.py` | Style vectors, named tactics, team totals, player share and minutes layer, forecasts |
| `simulate.py` | Synthetic league for tests |
| `backtest.py` | Walk-forward test harness |
| `README.md`, `backtest_report.txt` | Method and the simulated-data results |

## 2. Install

1. Copy the folder `backend/soccer_brain/` into the backend as `backend/soccer_brain/` (or set `SOCCER_BRAIN_DIR`).
2. `pip install numpy scipy pandas` (in `backend/requirements.txt`).
3. **Import rule.** The files import each other by flat name (`from core import ...`). `engine_bridge.py` puts the folder on `sys.path`, then runs `import engine`. Rules:
   - Do **not** add `__init__.py` to the folder's parent.
   - Do **not** rename the files.
   - `import engine` means `soccer_brain/engine.py`. Do not create another module called `engine` or `core` on the path ahead of it.
4. Smoke test: `cd soccer_brain && python3 backtest.py` (about 2.5 minutes). It prints the simulated-data report.
5. Integration test: `cd backend && python3 tests/selftest.py`.

Cost: fitting 20 teams and 380 matches takes under 1 second. One fixture takes 0.2 second. Memory about 140 MB. It runs inside the web server process or in the job tick without trouble.

## 3. Inputs

`engine_bridge.build_frames(db, league_iid, history_rounds)` builds three data frames from MongoDB. Ids must be integers (`iid`).

| Frame | Columns |
|---|---|
| `matches` | `game_id`, `round`, `home`, `away`, `hg`, `ag` |
| `team_game` | `game_id`, `round`, `team`, `opp`, `home` (0 or 1), `goals`, `goals_against`, `shots`, `sot`, `corners`, `tackles`, `poss`, `shots_against`, `corners_against`, `tackles_against` |
| `player_game` | `game_id`, `round`, `team`, `opp`, `player`, `pos` ("GK", "DEF", "MID", "FWD"), `started` (0 or 1), `minutes`, `shots`, `sot`, `tackles`, `team_shots`, `team_sot`, `team_tackles` |

- `round` = dense rank of distinct UTC kickoff dates in the league (`ingest.assign_rounds`). `as_of` = the largest finished round + 1.
- Rows with a null in a required column are dropped; a match stays only if **both** team rows are complete.
- Goalkeepers are excluded from player markets (`engine.exclude_positions`). A player with no mapped position is dropped.
- Only **confirmed** lineups are passed at prediction time: `lineups = {team_iid: {player_iid, ...}}`. A team with fewer than 11 confirmed starters is treated as not confirmed.

## 4. Calling it

```python
eng = SoccerEngine(interactions=True, lineup=False, half_life_rounds=20.0, style_k=6.0,
                   min_round=3, n_draws=60, sigma_team=0.07, seed=0)
eng.r_player = {"shots": 6.0, "sot": 5.0, "tackles": 10.0}
eng.fit(matches, team_game, player_game, as_of)
forecasts, outcome = eng.predict_fixture(home_iid, away_iid, lineups)    # list[Forecast], {xg_home, xg_away, p_home, p_draw, p_away}
```

Before `fit`, thresholds are set **in place** on the module dictionaries (`engine.PLAYER_THR`, `engine.TEAM_THR`) from the settings `engine.player_thresholds` and `engine.team_thresholds`. `configure_engine()` does it.

A `Forecast` has: `scope` ("player" or "team"), `team`, `opp`, `stat`, `thr`, `expected`, `p`, `lo`, `hi` (10th to 90th percentile), `player`, `pos`, `p_play`, `confirmed`, `contrib`, `reasons`, `opp_tactics`, `own_tactics`, `opp_key_players`, `p_raw` (plain last-10 rate), `p_base` (no-context baseline).

`thr` is the line. `thr = 1.5` means "2 or more". The label is `copy.market_labels["shots:1.5"]`.

## 5. Tiers

`core.tier(p, lo, confirmed, strong=(0.80, 0.70), solid=(0.65, 0.55))` (settings `engine.tier_strong`, `engine.tier_solid`):

- **Strong**: `p ≥ 0.80`, band lower end `≥ 0.70`, lineup confirmed.
- **Solid**: `p ≥ 0.65` and lower end `≥ 0.55`; if the lineup is not confirmed it drops to Watch.
- **Watch**: `p ≥ 0.55`.
- Below 0.55: no tier (`null`). The forecast still exists for the Finder.

Team markets count as confirmed.

## 6. Tactics

Every team gets an 8-number style vector from past games only (shots, shots on target rate, corners, tackles, possession, for and against; shrunk toward the league mean by `engine.style_k`). Three named tactics come from it. A team gets a label when it is at least one standard deviation above the league on that index:

| Label | Index |
|---|---|
| `low_block` | few shots allowed, more corners allowed, less possession |
| `high_press` | many tackles |
| `possession` | high possession |

`opp_tactics` and `own_tactics` ride on every forecast and are stored in `team_styles`. Reasons name the opponent's tactic when it matters ("The opponent plays a low block, which lifts corners."). A 4×4 matchup term lets the opponent's style change how our team's style plays out.

## 7. What the simulated test showed, and what it did not

From `backtest_report.txt` (a simulated 20-team league, 280 scored matches, tested walk-forward):

- **Player markets** (shots, shots on target, tackles): log loss 0.469 for the engine, 0.478 for the no-context baseline, 0.694 for the plain last-10 rate (lower is better). The engine beats both.
- **Team markets** (corners, team shots): 0.592 for the engine and 0.592 for the baseline. **No gain over the baseline** in this test. They beat the last-10 rate (0.766) by a lot.
- Stated chance matched what happened: Strong tier stated 0.906, actual 0.880; Solid 0.727 versus 0.734.
- **Win/draw/loss did not beat the plain league frequencies** (log loss 1.082 versus 1.074). Treat the win/draw/loss bar as experimental. It has its own switch: `features.show_match_probs`.
- The lineup-effects layer did not recover the hidden star effects (correlation −0.11 and +0.18) and made team forecasts worse. It is **off** and locked (`engine.lineup_effects`).

**All of this is simulated data. Nothing here proves the engine works on real football.** That is why the Beta tag exists.

## 8. The real-data test (do this before removing "Beta")

The harness is built: `backend/soccer_brain/backtest_real.py` (`run_counts`, `summarize_counts`, `gate`). It was run on free data for three leagues (doc 18), **not yet on PitchAPI history**. Plan for the PitchAPI run:

1. Ingest at least two full seasons of one league.
2. Build the frames with `build_frames` (use a large `history_rounds`).
3. Run the same walk-forward loop as `backtest.py`: for each round, refit on earlier rounds, forecast that round, score against what happened.
4. Compare the engine with the raw last-10 rate and the no-context baseline, by market, on log loss. Check tier calibration.
5. Gate: the engine must beat both comparisons in every market it shows, and each tier must come within about 3 points of its stated chance. A market that fails is switched off in `engine.markets_enabled`.
6. Store the result (a `backtest_runs` document) and show it on the Track Record page. Only then remove the Beta tag.

Also test the lineup-effects layer on real data. The simulated test failed it, but real starters rotate differently. Only if it passes the gate may `engine.lineup_effects` be unlocked, and that is a code change, not a setting.

## 8b. Tactics, formations, calendar and rotation (new)

See `18_brain_tactics_and_context.md`. Short version: `predict_fixture(home, away, lineups, ctx=...)` takes the calendar numbers for both clubs and returns `rotation` and `rotation_why` on every forecast; with a start model attached and its gate open it also re-weights who is expected to start. The tactics and lineup-shape layers exist behind switches and are **off**, because they did not improve forecasts on real matches.

## 9. Adding a market (for example fouls committed)

1. Make sure the stat is stored in both `player_match_stats` and a `team_*` total, and passes `engine.coverage_min`.
2. In `engine.py`: add the stat to `STATS` and `PLAYER_STATS`, add its default dispersion to `DEFAULT_R_PLAYER`, add thresholds to `PLAYER_THR`, add a wording to `core.STAT_WORDS`.
3. Add the columns to `build_frames` (`TEAM_REQUIRED`, `PLAYER_REQUIRED`) and the market to `MARKET_COVERAGE` in `engine_bridge.py`.
4. Add settings: `engine.player_thresholds`, `engine.markets_enabled` ("player.fouls"), `engine.r_player`, and `copy.market_labels`.
5. Run the walk-forward test for the new market. Ship it only if it passes the gate.

## 10. How a run is scheduled

`jobs.tick` runs `run_league` when new matches were ingested or new confirmed lineups were fetched since the last run. Each run:

1. Checks which markets are on (admin switch **and** coverage).
2. Builds frames, fits, saves `team_styles`.
3. For each upcoming match inside `engine.window_days`: predicts, writes `match_probs` and `forecasts`, marks the previous rows `is_current = false`.
4. Writes an `engine_runs` row.

A re-run replaces the current forecasts. It never doubles them (checked by `selftest.py`).
