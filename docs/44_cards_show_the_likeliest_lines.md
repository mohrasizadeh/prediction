# 44. Cards were showing the long shots and hiding the near-certain ones

Written 2026-11-02. Reported, with a screenshot of Harry Kane's card: *"it doesn't show harry kane one shot and one
shot on target at all which has higher probabilities … and it happens across players."*

The card read:

| | |
|---|---|
| **4+ shots** | **52%** |
| 2+ shots on target | 49% |
| 5+ shots | 40% |
| 3+ shots on target | 27% |
| 6+ shots | 26% |
| 4+ shots on target | 16% |

His 1+ shot (~95%) and 1+ shot on target (~78%) were not hidden on the card. **They did not exist anywhere in the
app** — never written to `forecasts`, never in the feed, never available to follow or to put in a combo.

## The cause

One line, `engine_bridge.select_lines`:

```python
keep = sorted((d for d in g if lo <= d["p"] <= hi), key=lambda d: -d["thr"])[:max_lines]
```

For each player and stat it sorted the ladder by **descending threshold** — the docstring said "the `max_lines`
most ambitious" — and kept three. Sorting by threshold is sorting by *unlikelihood*, because a ladder is monotone:
`p(6+) ≤ p(5+) ≤ … ≤ p(1+)`. So the near-certain end was thrown away first, for every player, every team and every
stat, before anything reached the database.

It is the wrong way round for the people this app is for, and it quietly undid **docs/39**, where the band was
widened to `[0.5, 0.985]` precisely so that 90%+ lines could exist. They existed, and then this discarded them.

Two settings interact, and both were pulling the same way on the live install:

- `engine.max_lines_per_stat` = 3 — how many rungs survive.
- `engine.line_band` — which rungs are eligible. The reported card shows lines at 26% and 16%, which cannot pass
  the default floor of 0.5, so this install's floor has been lowered in Admin → Settings. That is what let the
  selection run all the way down to the ambitious tail. **Left as the owner has it**, on their instruction: the
  fix below makes the floor harmless.

## The rule now

```python
# -p first, then -thr: of two lines equally likely, the more ambitious one is worth more to the reader
keep = sorted((d for d in g if lo <= d["p"] <= hi), key=lambda d: (-d["p"], -d["thr"]))[:max_lines]
```

**Ambition is the band's job; likelihood is the slice's.** `engine.line_band`'s lower end decides how far down the
ladder we are willing to go, and the slice keeps the likeliest of whatever that leaves. The two settings now pull in
different directions instead of the same one, which is what makes each of them usable.

Kane's card becomes **1+ shot 95%**, 2+ shots 85%, 3+ shots 70% — and the same for his shots on target. The whole
ladder is still stored on every line (`ladder`), so the Finder still answers any threshold the band excluded;
nothing is lost, it is only no longer the thing a card leads with.

## The trade, stated plainly

Because a ladder is monotone, "the likeliest in band" is always **the lowest rungs in band**. So the thresholds stop
differing between teams and players, and it is the percentage that tells them apart:

| | before | after |
|---|---|---|
| team shots | 6+ · 7+ · 8+ (and higher for stronger teams) | 6+ · 7+ · 8+ for every team, 50%–91% |
| team corners | varied | 2+ · 3+ · 4+ for every team, 56%–91% |
| player shots | 4+ · 5+ · 6+ | 1+ · 2+ · 3+, 50%–97% |

This is a real cost: `engine.auto_lines` is described as giving "every player and team the lines that fit its own
numbers", and it now fits them rather less. Two things make it the right trade anyway: a consistent market read
across teams is how the statistics sites this app is measured against present one (the reference the owner sent for
docs/39 showed exactly that), and a near-certain line is never worth hiding behind a long shot for this audience.

If the ambitious end is wanted back on the same card, the fix is **not** to revert this: it is to keep more lines
per stat and spread them across the ladder — the likeliest, the middle, the long shot — which is a change to how
many rungs are kept, not to which end wins. Left undone; worth revisiting once the new cards have been seen.

## What else moved

Two test assertions encoded rules this change replaces, and both were rewritten rather than relaxed:

- `selftest_lines` asserted "team shot lines differ by team". They no longer do, by design; it now asserts the
  market is consistent across teams **and** that the same line reads differently for each of them.
- `selftest_calibration` asserted a blanket "no forecast shows more than 97%". There are two ceilings by design
  (docs/39): a line through the calibration map stops at `calibration.CAP` (97%), an anchored one at
  `engine.p_cap` (98.5%). The blanket check was never exercised before, because the old selection meant no stored
  line ever reached that gap. It now checks each ceiling against the thing that sets it.

## Files

| File | Change |
|---|---|
| `backend/engine_bridge.py` | `select_lines` keeps the most likely lines in band, not the most ambitious. |
| `backend/settings_registry.json` | `engine.max_lines_per_stat` and `engine.line_band` describe what they now do. |
| `backend/tests/selftest_lines.py` | The reported card as a regression: the three likeliest are kept, the near-certain line leads, the band floor only removes long shots, a band nothing reaches keeps nothing, and equally likely lines break the tie toward ambition. |
| `backend/tests/selftest_calibration.py` | The two ceilings, each against its own setting. |
