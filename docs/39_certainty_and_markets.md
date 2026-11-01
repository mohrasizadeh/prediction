# 39. Showing what is near-certain, and the markets to add next

Written 2026-11-01. The owner's question: "90%+ lines aren't showing, and those are the most important ones."
They were right, and it was three limits stacking, not a bug.

## 1. Why near-certain lines were invisible

Measured on a real engine run before the change: 306 forecasts stored, and of the lines at 90% or more:

| Band | Stored | Leading a card |
|---|---|---|
| 90–93% | 2 | 2 |
| 93–95% | 3 | **0** |
| 95%+ | **0** (19 computed and discarded) | – |

Three gates:

1. **`engine.line_band` = [0.5, 0.95].** `select_lines` deletes every line outside the band at engine time. The
   engine had computed **19 lines above 95% and stored none of them**. They survived only inside each card's hidden
   `ladder`, so the Finder could answer them but they were never a card, never in Insights, never saveable.
2. **`engine.feed_max_p` = 0.93.** A line above this never leads a card while the same player has another line. All
   three stored 93–95% lines were demoted into "+N more lines".
3. **Hard ceilings:** calibration caps the displayed number at 97% and `engine.p_cap` at 98.5%.

These were deliberate. docs/25 says: *"A 96% '1+ shot' could lead a card" → "Lines above 93% never lead while
another line can"*, and the Insights feed was deliberately sorted by **lift over usual** rather than by likelihood,
to move away from "near-certain picks on top". The reasoning was that a near-certainty carries little information.

**The owner's decision (2026-11-01): for an audience that bets, certainty is the point.** A low number does not
help someone decide; a near-certainty does. So the limits move.

## 2. What changed

| Setting | Was | Now | Effect |
|---|---|---|---|
| `engine.line_band` | `[0.5, 0.95]` | `[0.5, 0.985]` | A 96% line is stored as a real card: openable, followable, combinable. |
| `engine.feed_max_p` | `0.93` | `0.97` | A near-certain line leads its card instead of hiding behind "more lines". |

Unchanged on purpose: the **97% display cap** in `calibration.py`. Football always leaves room for a surprise, and
a number that reads 99% is a promise the engine cannot keep. This is the honesty guard, and it is separate from the
two limits above.

Same run after the change: 358 forecasts, **12 lines at 90% or more, 11 of them leading their card.**

`engine.feed_sort` is still `edge` (biggest lift over usual). Switch it to `likely` in Settings if Insights should
rank by likelihood instead. That is a one-setting change and needs no engine run.

## 3. Markets

The owner's priority list, against what the engine can do.

### Player

| Market | State | What it needs |
|---|---|---|
| **Shots on target over** | **Live.** Ladder 0.5–3.5. | – |
| **Tackles over** | **Live.** Ladder 1.5–5.5. | The PitchAPI key for `tackles` is `null` in the defaults (docs/08 check A was never finished). If your league shows no tackle lines, that is why: check Admin → Settings → `provider.pitchapi.player_keys` and the coverage for `player_match_stats.tackles`. |
| **Fouls won** | **Not built.** The `fouls_won` column exists in `normalize.py`; its provider key is `null`. | Map the key, then add the market. The player layer takes a share of a team total, so the team needs a `fouls` total as well (it has one through `extra_stats`). Moderate: `PLAYER_STATS` in `soccer_brain/engine.py` is a fixed list of three. |
| **Fouls committed over** | **Not built.** Same as above (`fouls_committed`). | As above. This would also sharpen the yellow-card model, which already blends a player's fouls. |
| **Passes over** | **Not built, and no data at all.** There is no `passes` column anywhere and no provider key. | Add the column to `normalize.PLAYER_COLS`, map the provider key, ingest it, then add the market. The largest of the five. |

### Team

| Market | State |
|---|---|
| **Goals** | **Built in this change.** Total goals in the match (0.5 to 4.5), read straight off the Dixon-Coles scoreline matrix, so the draw correction and match context are already inside the numbers. It needs **no statistics feed**, so it works in a league where shots or tackles are missing. Graded from the final score. |
| **Cards** | **Live.** `cards_model.py`: total yellows 3.5 and 4.5, plus per-player yellow cards. |
| **Corners** | **Live.** Ladder 1.5–10.5. |
| **Shots** | **Live.** Ladder 6.5–22.5. |
| **Shots on target** | **Added in this change.** The engine already modelled team shots on target; it had no ladder and no market flag. Ladder 1.5–8.5. |

Both new markets are on by default in `engine.markets_enabled`. Total goals is exempt from the coverage check
(`NO_COVERAGE_MARKETS`), because a finished match always has a score.

## 4. What this does not copy

The reference the owner shared (StatsHub) shows a price next to each line and a "Save pick" button. Neither can
appear here: prices and the word "pick" are both barred by docs/03 §2, and showing a price would make this a
betting product rather than an analysis one. What is worth taking from it, and is not built yet:

- **Sort by hit rate, and filter by a minimum hit rate and a minimum streak.** The Finder does this kind of query
  already; the Insights feed does not offer it as a sort.
- **A market tab strip** (All, Shots, On target, Tackles, …) above the feed.
- **The record line on the card** — "19 of 19, 100%, 1.99 per 90, season average 11.90, opponent allows 11.19".
  The card already shows "Hit in 20 of his last 20 games" and "Usually 91%", so this is mostly presentation.

## 5. Files

| File | Change |
|---|---|
| `backend/settings_registry.json`, `docs/11_settings_registry.json` | `line_band`, `feed_max_p`, `team_ladder` (sot, goals), `markets_enabled` (team.sot, team.goals). |
| `backend/soccer_brain/strength.py` | `outcome_probs` also returns `totals`: P(total goals ≥ line), off the same matrix. |
| `backend/engine_bridge.py` | `_goal_lines` writes the total-goals market; labels for it; `NO_COVERAGE_MARKETS`; `score_finished` grades it from the final score. |
| `backend/tests/selftest_markets.py` | New. Near-certain lines are stored and lead; total goals is monotone, stores, reads as a sentence, works without coverage and grades correctly; team shots on target exists. |

## 6. Open

- **Fouls won, fouls committed, passes** (section 3) need provider fields before any engine work is worth doing.
- **`engine.feed_sort`** is still `edge`. Decide whether Insights should rank by likelihood.
- The settings above are **defaults**. If a value was ever saved in Admin → Settings, the saved value wins and the
  new default will not apply. Check `engine.line_band` and `engine.feed_max_p` there after deploying.
