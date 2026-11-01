# 40. The combo builder: one line, several matches, and the right number

Written 2026-11-01. Three things the owner reported: the builder changed the number for a single line, it refused
lines from different matches, and the combined number had to be right.

## 1. A single line is no longer touched

Before, every combo went through the same path, so a one-line "combo" was still multiplied and capped.

| Case | Card said | Combo said | Now |
|---|---|---|---|
| Confirmed starter, 92% | 92% | 92% | unchanged |
| Line at 98% | 98% | **97%** (the combo's own cap clipped it) | **98%** |
| Player who may not play: 92% if he plays, 70% to play | 92% | 64% | **64%, and the screen says why** |

Two different things were happening:

- **A real bug.** `CAP = 0.97` was applied to a single line. One line is not a combination, so there is nothing to
  be cautious about beyond what the forecast already says. It now comes back exactly as it is. This mattered more
  after docs/39, which allowed lines above 97% to exist.
- **Not a bug, but invisible.** A card reads *"92%, if he plays"*; a combo answers *"how likely is this to actually
  happen"*, which also counts the chance he plays. For a doubtful player those are very different numbers, and
  nothing on screen said so. The sheet now spells it out for a one-line combo:
  *"The card says 92% if he plays. Here we also count the 70% chance he plays, which is why this reads 64%."*
  For a confirmed or likely starter the chance to play is 1, so the two numbers agree and no note appears.

## 2. Lines from different matches

The old rule was "a combo holds lines from one match", enforced in `combo.estimate`, in the save route and in the
browser (which offered to start a new combo instead). All three are gone.

**The maths, and why it is not just "multiply everything".** Lines in the *same* match lean on each other: the same
team news, the same game state, the same referee, the same weather. That dependence is what we measured on 237,000
real combinations (docs/28), and it is what the same-player exponent and the pre-lineup factors correct for. Lines
in *different* matches share none of those causes.

So the combined chance is now built in two steps:

```
combined = Π over matches of  joint_chance(the lines in that match)
```

where `joint_chance` is the tested within-match formula, unchanged. Across matches, plain multiplication.

| Combo | Chance |
|---|---|
| Two players, same match, before lineups | 0.92 × 0.80 × **1.11** = 0.817 |
| Two players, different matches, before lineups | 0.92 × 0.80 = **0.736** |
| Three matches, one line each | 0.92 × 0.80 × 0.90 = 0.662 |
| Two players in one match plus one in another | (0.92 × 0.80 × 1.11) × 0.90 |

A cross-match combo is therefore **never inflated by a dependence that is not there**. Stretching the within-match
correction across matches would have been the easy mistake and would have overstated every such combo.

**Honest limit:** matches in the same round are not perfectly independent either — a league-wide refereeing
instruction, a weekend of heavy pitches. That shared part is far smaller than the within-match one, and we have not
measured it. Plain multiplication is the conservative choice: it understates rather than overstates.

## 3. What else had to change

- **A saved combo is not over until its last match has started.** `_combo_view` decided "upcoming" from a single
  kick-off; with two matches it would have settled the combo as soon as the first began. Saved combos now carry
  `last_kickoff` and are judged on that.
- **Every line says which match it is from,** and the estimate carries a `matches` list, each with its own label,
  kick-off and joint chance. The sheet groups the lines under a fixture heading when a combo spans more than one,
  and shows what each match contributes.
- **Older screens still work.** The estimate keeps `match_iid`, `match_id` and `label`; with more than one match
  the label counts them ("2 matches") instead of naming one.
- **Pluralisation.** `_s()` produced "2 matchs". Words that hiss now take "es".

## 4. Files

| File | Change |
|---|---|
| `backend/combo.py` | `_one_match` holds the tested within-match formula; `combine` groups by match and multiplies across; a single line is returned untouched; the report lists every match and carries `last_kickoff`; `_s` pluralises properly. |
| `backend/routes_me.py` | Saving a combo keeps every match and the last kick-off; the list judges "upcoming" on that; the `MIXED_MATCHES` branch is gone. |
| `frontend/src/lib/combo.jsx` | A line from another match no longer triggers "start a new combo"; each line keeps its own match. |
| `frontend/src/components/ComboHost.jsx` | A fixture heading per match with its contribution; the one-line explanation; the switch sheet reworded. |
| `frontend/src/styles/hig.css` | The fixture heading. |
| `backend/tests/selftest_combo_cross.py` | New. One line untouched and uncapped; same-match correction applies; different matches multiply plainly; the correction is per match; same-player dependence survives; a real combination is still capped; the report names every match. |
| `backend/tests/selftest_combo.py` | The three "one match only" assertions now assert the new behaviour. |

## 5. Open

- The independence assumption across matches in the same round is untested (section 2). Worth measuring once there
  are enough scored cross-match combos to compare predicted against actual.
- `combo.max_lines` is still 6 for every combo, whether the lines come from one match or six.
