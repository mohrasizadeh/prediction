# 45. The sheet that opens on a forecast line

Written 2026-11-02. Reported, with a screenshot of Marcus Tavernier's 1+ shot sheet: *"It needs a serious uiux
upgrade. also improve last 10 games where it shows boxes, I'd rather see the opponent logo there and on top of the
box, how many minutes the player played. the next game top of the screen and the time both in one line with no
separation."*

## What was wrong

**The last-10-games strip was throwing its own data away.** The sheet fetched the player's history and then reduced
every game to a single true/false:

```js
const strip = (r) => setD((x) => ({ ...x, hits: (r.games || []).filter((g) => g[f.stat] != null)
                                                   .map((g) => g[f.stat] > f.thr).reverse() }));
```

`/players/{id}/history` already returns the opponent, the minutes played and the figure itself for every game. All
of it was discarded one line after it arrived, leaving ten plain squares. A square cannot say **who** the game was
against or **how long he was on the pitch** — and without the minutes, a quiet game and ten minutes off the bench
look identical, which is exactly the distinction a reader needs.

The player page had already been given the better strip (minutes above, figure in the middle, crest below), so the
app had two different answers to the same question, and the sheet had the worse one.

**Four more things, from the same screenshot:**

- The range was printed **twice** — "69 to 92" beside the percentage, then "Likely range 69 to 92%" below it.
- Three tiles were forced into a two-column grid, so *Lineup* sat alone beside a hole.
- "Usually 79%" and "Reached this line in 7 of his last 10 games" sat adrift **below** the strip they describe.
- The fixture and the kick-off were joined with a middot and could wrap apart on a narrow sheet.

## What it does now

**One strip, one implementation.** `GameStrip` moved into `components/ui/Marks.jsx` and both the player page and
the sheet use it, so they cannot drift apart again. It takes the API's rows exactly as they come — newest first —
and draws one column per game, oldest to newest: **minutes on top, the figure in the middle, the opponent's crest
below**, the column filled when the line was reached. Team rows carry no minutes, so that line is simply left off
for them, and the strip is not drawn at all unless the feed actually carries the stat; a row of dashes says
nothing.

**The fixture and the time are one line with nothing between them.** When the sheet is narrow the club names give
way first and the time never wraps or ellipses — a half-shown kick-off is worse than a half-shown club name.

**The rest of the sheet:**

- The range is stated once, beside the percentage. The sentence below explains what the range *means* instead of
  repeating it.
- Tiles fit three to a row where there is room; where there is not, the odd one out spans the width and reads as
  deliberate rather than broken.
- "Usually …" and the record line now sit together directly under the strip they describe.

Both new text colours were checked against their background: 5.23:1 in light, 5.94:1 in dark, against the 4.5:1
the rest of the app holds to.

## Files

| File | Change |
|---|---|
| `frontend/src/components/ui/Marks.jsx` | `GameStrip`: the shared minutes / figure / crest strip. `HitStrip` stays for the dense per-line lists, where a crest would not fit. |
| `frontend/src/components/ui/ForecastSheet.jsx` | Keeps the API's whole rows; draws `GameStrip`; fixture and time on one line; range stated once; context reattached to the strip. |
| `frontend/src/pages/Player.jsx` | Uses the shared strip instead of its own copy. |
| `frontend/src/components/ui/index.js` | Exports `GameStrip`. |
| `frontend/src/styles/hig.css` | Pass 4: the fixture line, the tile grid, the context block. |

## Still open

- The sheet is long: nine sections stacked, and on a phone the track-record line is well below the fold. Apple's
  guidance for sheets is "simple content or tasks", with progressive disclosure for the rest. Worth a medium
  detent, or folding "All lines" and the track record behind a disclosure, once this is in use.
- `HitStrip` still appears on the player page's compact per-line list. That is the right call for a dense list of
  four lines, but it means the app has two strips; the plain one should never be used for a main chart again.
