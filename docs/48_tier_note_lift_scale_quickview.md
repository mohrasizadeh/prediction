# 48. Why a 97% line reads Solid, which market keeps winning, and the Quick view in the sheet

Written 2026-11-02, from three things reported on one screenshot of Kylian Mbappé's 1+ shot sheet.

## 1. "Why is 97% Solid and not Strong?"

Because the tier is not judged on the 97%. A player line is tiered on the **whole chance** — what the card calls
"if he plays", times the chance he plays:

```
whole = 0.97 × 0.84 = 0.815        strong_min 0.90   solid_min 0.80
```

81.5% clears Solid and misses Strong. Confirm the lineup and the whole chance becomes 0.97, so the line *is*
Strong. The maths is right and deliberate (docs/31): a forecast you cannot act on because the player may not start
is not a strong forecast.

**What was wrong is that nothing said so.** The card printed 97%, "Chance he plays 84%", "If he plays 97%" and
"Solid", and left the reader to multiply three numbers to work out why. `tier_note` exists for exactly this and
only fired on one of the two routes to "not Strong yet" — the branch where a line *reached* Strong and was held
back by `strong_needs_lineup`. Mbappé's line never reached Strong, so it got no note at all.

`tiering.assign` now sets the note whenever the chance to play is the only thing between this tier and a better
one: **"Strong once the lineup is confirmed"**, or "Solid once the lineup is confirmed" a tier lower. On the test
league that is 17 of 140 pre-lineup lines that previously explained nothing.

## 2. "SOT always takes precedent"

My first guess was the market weights from docs/46. **Measured: they change which line leads on 0 of 90 cards.**
A 1.4× only breaks near-ties, and lifts vary far more than 40%.

The real cause is the `edge` sort. Ranking on `p − p_usual` — plain percentage points — is not fair between
markets, because how far a line *can* move depends on where it sits:

| line is usually… | median \|lift\| | room to move |
|---|---|---|
| 0–40% | **0.196** | 0.37 |
| 40–60% | 0.069 | 0.44 |
| 60–80% | 0.057 | 0.28 |
| 80–95% | **0.029** | 0.14 |

A line usually at 90% cannot gain more than 10 points however remarkable it is; one usually at 30% has 70 to play
with. Shots on target sit lower than shots (median usual 0.62 against 0.69) and show correspondingly larger lift
(0.079 against 0.061), so they win — systematically, whatever the weights say.

`queries.lift()` now measures the change in **log-odds**, so "twice as likely as usual" counts the same wherever
it starts. A 97%-against-96% line scores 0.298 instead of 0.010. `engine.lift_scale` keeps `points` available in
one flip.

**What this does not change:** the `edge` field itself, and so the "usually X%" every card shows. That is a plain
percentage-point difference and should stay one — it is the honest thing to *read*. This changes only what lines
are *compared* on. Mbappé's card leads are unchanged (`3+ shots`, `2+ shots on target`); `1+ shot` correctly moves
from last of five to third.

## 3. The Quick view in the sheet

The sheet showed a fixed last-10 strip for the line you tapped. The reader's next question is almost always *"what
about 2+, or only at home, or only when he started"* — and answering it meant leaving the sheet for the player
page.

`components/ui/QuickView.jsx` now holds the controls and the strip, and both screens use it, so they cannot drift
apart — the same move as `GameStrip` in docs/45. The sheet opens it **already set to the line being looked at**,
so it is useful before you touch anything.

Two things came out of seeing it on a phone rather than trusting the build:

- Five rows of controls stacked above the strip pushed the strip clean off the screen. The strip comes first now,
  and in a sheet the controls fold behind *"Change the line or filters"*. The player page keeps them open — there
  is room, and filtering is that page's purpose.
- The sheet had been fetching the player's history for its own strip while the Quick view fetched it again. The
  sheet now fetches only for **team** lines, which have no Quick view and keep the plain strip.

Checked in a browser at 390 px: the toggle opens, the stat is seeded from the line, and changing 1+ to 3+ re-reads
the strip ("10 of 10" to "7 of 10"). No page errors.

## Files

| File | Change |
|---|---|
| `backend/tiering.py` | The note fires whenever the chance to play is what is holding a tier back. |
| `backend/queries.py` | `lift()` on a log-odds scale, used by `prominence` and the feed's `edge` sort. |
| `backend/settings_registry.json` | `engine.lift_scale`. |
| `frontend/src/components/ui/QuickView.jsx` | New, shared by the sheet and the player page. |
| `frontend/src/components/ui/ForecastSheet.jsx` | Quick view for players, seeded and collapsible; the duplicate fetch is gone. |
| `frontend/src/pages/Player.jsx` | Uses the shared Quick view; keeps its table. |
| `backend/tests/selftest_lines.py`, `selftest_queries.py` | Three assertions pinned the old measure or listed notes by hand; the note check now matches shapes so the next note does not break it. |

## Open

- **The log-odds scale is reasoned, not fitted.** It removes a bias I could measure; whether it ranks what readers
  actually open is a different question, and the follow and combo-add data could answer it the way docs/37 answers
  engine questions.
- The sheet is still long. docs/45 left "fold All lines and the track record behind a disclosure"; the Quick view
  has now taken the same treatment, which is an argument for giving the rest of the sheet the same.
