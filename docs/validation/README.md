# validation/

The scripts that produced every number in `../18_brain_tactics_and_context.md`. They are research code, not part of the app. Nothing in `backend_reference/` imports them.

**Attribution.** Event and lineup data: "Data provided by StatsBomb" (StatsBomb open data, 2015/16 Premier League, Serie A, Ligue 1; <https://github.com/statsbomb/open-data>). Fixtures and results: openfootball (public domain, CC0; <https://github.com/openfootball>). Keep this line wherever results derived from the StatsBomb files are shown. Do not ship the raw files.

## Set up

```
pip install numpy scipy pandas
mkdir data                      # the scripts read and write ./data
python sb_extract.py            # downloads StatsBomb events for the 3 leagues, writes data/sb/*.pkl (slow: one request per match, many matches)
git clone --depth 1 https://github.com/openfootball/england data/openfootball_england
git clone --depth 1 https://github.com/openfootball/europe-champions-league data/openfootball_champions-league
```

Run every script from this folder, for example `python exp_tactics.py PL SA L1`.

## Run order and what each one answers

| Script | Question | Output |
|---|---|---|
| `load.py` | Parses openfootball text files into one match table (club names normalised) | used by the others |
| `load_statsbomb.py` | Builds the engine's three frames from `data/sb`. **Drops matches with an empty event feed** | used by the others |
| `dc_oos.py` | Is the Dixon-Coles baseline sound out of sample on 14 Premier League seasons? | `data/pl_dc.pkl` |
| `context_test.py`, `fit_ctx.py` | Do rest days, a European match behind or ahead, or a cup match ahead move goals? | `data/ctx_results.json` |
| `cup_test.py` | Do Premier League clubs do worse in the League Cup than the FA Cup? | table |
| `stakes_test.py` | Do clubs with nothing to play for underperform late in the season? | table |
| `v1_reliability.py` | Are the style metrics stable enough to use? (split-half, ICC) | table |
| `exp_rotation.py` | Does the calendar change how many players are changed in the eleven? | `data/ctx_rows.pkl` |
| `exp_startmodel.py`, `exp_startmodel2.py` | Does the calendar improve the forecast of **who starts**? | table |
| `exp_tactics.py` | Do tactical indices and shape improve team-metric forecasts? | `data/res_tactics_*.pkl` |
| `exp_oracle.py` | What if the model were handed the real lineup shape and rotation? (upper bound) | `data/res_oracle_*.pkl` |
| `exp_shape.py oracle\|blind` | Which part of the shape matters? | `data/res_shape*_*.pkl` |
| `pool.py`, `show_pool.py` | Pool the three leagues; paired z; z clustered by team-match | printed |

## How to read the output

- `gain` is the mean improvement in log-likelihood per scored count over the engine as shipped (`full`). Positive is better.
- `z` is gain divided by its standard error. Use **at least 2.0, clustered by team-match**.
- Always read the per-league lines before the pooled line.

## Results (as of 2026-10-26, clean data)

Pooled over three leagues, 1,588 team-matches, four core metrics (shots, shots on target, corners, tackles), z clustered by team-match:

| Variant | Gain | z |
|---|---|---|
| Naive baseline (league x team x opponent, no regression) | -0.027 | -8.5 |
| Engine without style-matchup terms | +0.0010 | +1.3 |
| Engine with tactical indices | -0.0016 | -3.1 |
| Engine with tactical indices and shape | -0.0018 | -2.9 |
| Real lineup shape handed to the model | -0.0002 | -0.4 |
| Real first-choice score handed to the model | -0.0001 | -0.4 |
| Real number of changes handed to the model | -0.0001 | -0.3 |

Start model (who starts), 34,763 squad rows, held out later part of each season: gain +0.0004 to +0.0010 per row (z 0.9 to 2.1).

## Known limits

- One season of event data (2015/16). Cups and the Europa League are missing from that season's calendar.
- The first version of the oracle test pooled a data hole and reported a large false gain (see doc 18 §1). `load_statsbomb.py` now drops those matches. If you extend the data, keep that filter and check every per-league line.
