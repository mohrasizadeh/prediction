# 65 — The combo builder

The old combo answered *"give me a combo from this match"*. The builder answers the question people
actually arrive with: *"build me something across tonight that comes out around here."*

## The one change that matters

The control is a **target for the whole combo**, not a floor under each line.

A floor under each line is what every bet builder offers, and it is the wrong control, because
**four lines at 80% do not make an 80% combo — they make about a 41% one.** That is the number
nobody expects and nobody is shown. Here the reader says what the whole thing should be worth and
the engine finds lines that land there.

The search scores candidate sets with `combine()` **itself**, not with a product of percentages. It
has to: the same-player exponent (0.38) and the pre-lineup factors (1.11 / 1.19 / 1.25) move the
answer by more than anyone would forgive as rounding, and they move it *upward* — so solving
against a product would miss in the direction that flatters us. `selftest_combo_build` pins that:
every target it hits is checked back against `combine()` and asserted to differ from the naive
product.

## What the engine refuses to do

* **Build on a player we are unsure will play.** A combo multiplies its weakest assumption by
  everything else, so one doubtful starter quietly halves the whole thing.
* **Put the same player in twice** — unless the reader does it themselves, in which case
  `_one_match` already handles the dependence and the sheet says so.
* **Stack one match.** Lines from different matches share no team news, game state or referee, so
  they multiply plainly. Independent legs are the honest kind, and the builder prefers them.
* **Rank alternates by what flatters the number.** A list sorted by "makes your combo look best" is
  a list that teaches the reader to keep clicking until it lies to them. Alternates are ranked by
  line quality — confirmed over likely, a real departure over a truism — and each one *shows* what
  the combo would become, including when that is worse.

## The waiting screen

`candidates()` returns a tally: how many lines were read, how many were dropped for the lineup, how
many fell under the floor, how many matches were searched. That is what the waiting state shows.

A progress state that describes real work is worth having. One that counts to three while nothing
happens is theatre, and this product does not get to spend its credibility on theatre — it is the
only thing it sells. The search is real work (hundreds of lines, a local search re-scoring
candidate sets through `combine()`), so it should say what it is doing and stop when it is done.

## Failing out loud

* An impossible floor says which constraint emptied the pool and how close it got.
* A target the window cannot reach says so in the first note, rather than returning a number that
  looks like an answer to a question nobody asked.
* Fewer lines than asked for says that too.

## Known limits

`TESTED_ENTITIES = 4`: the 237,000-combination validation behind `combine()` covered up to four
players or teams. `combo.max_lines` allows six. Five and six are extrapolation and the report
already says so in its notes — the builder does not hide that to sell a longer combo.

## Vocabulary

The feature was described to me as choosing how many **picks**. `picks` is on this product's own
banned list and `frontend/scripts/check-copy.js` fails the build on it. The house word is **line**,
and the combo is made of lines. Nothing about the feature changes; the word does.

## Already built, and not rebuilt here

The tracking the brief asks for — *"in progress or finished, how many hits, how many didn't"* —
exists in `routes_me._combo_view`: four states (`upcoming` / `live` / `waiting` / `settled`),
per-line `reached`, `actual` and **`played`**, and live in-match evaluation that never shows a
false cross. A player who did not play is not a miss in the same sense as a player who played and
fell short, and the data already keeps them apart. What is missing is the screen and a rollup
across combos, not the engine.

## Still to build

The screen: how many lines → build it yourself or have it built → the constraints → the search →
the result, with per-line drop and swap. Rendered before it is written, as everything else on this
product now is.
