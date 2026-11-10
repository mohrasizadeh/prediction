# 77. The standard card

> Reported against a settled match page, in the owner's words: *"It's very messy and unorganized…
> the market not clear — at a glance user doesn't know what market they are looking at."*
>
> This is the card the rest of the product follows. Anywhere a forecast is drawn as a row —
> Most likely, a match page, a player page, a team page, Explore, Compare — it is `ForecastRow`,
> and this document is what that row is for.

## The five faults, and the fix for each

| # | Reported | Why it happened | Now |
|---|---|---|---|
| 1 | The market is not clear at a glance | The market was the second half of a sentence: *"MID · 2+ tackles vs Atalanta 15:00"*, in body text, with nothing marking which word was the subject | The market is a **named control** at the head of the row: a button carrying the market and nothing else |
| 2 | *"no more +5 more markets — everything happens on the card"* | Changing market opened a **list below the row**, so the reader left the card, read a list, and came back | The control is a picker. Choosing a market **redraws the row in place**: its number, its range, its badge, its ten-game strip |
| 3 | The line should not be fixed at 1+, 2+, 3+ | Three chips, one per rung, in a strip that scrolled sideways | A **stepper**: − and +, walking the rungs the engine answered |
| 4 | Percentage, range, badge and result are not laid out properly | They were four objects of four widths sharing one column, re-ordered by whichever of them existed on that row | One column, one right edge, and the figure at **one height on every row** |
| 5 | Changing the number does not move the range | A real bug — `ForecastRow.jsx` fell back to the **lead line's** band whenever the rung stepped to had none | The range follows the rung, and says nothing where the rung has no band |

## What leads the card

Unchanged, and worth restating because fault 2 invites getting it wrong: *"whichever market has
the highest percentage **and makes sense for the player** leads the card — for a player that always
takes 3 shots in a match, taking one shot doesn't qualify."*

That is already `engine.lead_rule` with `engine.feed_max_p` and `engine.min_span` in front of it
(docs/56, docs/76). A near-certain rung is gated per rung, on a measured span, **before** the lead
is chosen. The picker does not touch this: the server still decides what the card opens on, and the
list is ordered likeliest-first from the same numbers.

## The server now sends every market, complete

`more_lines` was a **teaser**. It carried `fkey, stat, thr, market, p, lo, hi, tier, p_usual, edge,
ladder, pos, span` — enough to *list* what else a subject holds, not enough to **draw** it. A market
brings its own ten-game strip, its own ladder, a band per rung and a grade per rung, and none of
those were in it. A picker built on `more_lines` would have had to call the server on every change,
or show a market with another market's evidence underneath it.

So `queries.group_cards` adds `markets` (`queries._markets`): **one entry per stat**, each the rung
that stat leads with, carrying `_MARKET_KEYS` — the full set the row reads, `run`, `ladder`,
`ladder_band` and `ladder_tier` among them.

One entry per *stat*, not per rung, because the rungs are already inside each entry's `ladder`. A
row per rung was measured on a six-market card at eighteen rows against six, for data the ladder
already holds.

`more_lines` stays, for the callers that only ever wanted the teaser.

## The row, left to right

```
 who 21%   fx 8%   market 26%   likelihood 12%   last ten 20%   lineup 13%
```

**The strip out-measures the range.** It was the other way round, and that was the fault behind the
owner's rejection of two earlier attempts: *"I think it is in prioritizing the range line over the
past 10 graph bar."* The range had a drawn rail — a bar on a fixed 50–100 scale — and the ten games
had 14% of the row. The rail is gone; the range is a caption under the figure, in words; the column
it gave back went to the strip, which is the **evidence**, and now has 20%.

**One right edge, one height.** The badge sits **on top of** the number and the figure sits below it
at a fixed offset, because `.lk-tiercell` is a **22px slot rendered whether or not there is a badge
to put in it**. Anchored to the top instead, a row carrying a badge pushes its figure lower than a
row without one, and the percentages stop lining up down the column — the alignment docs/61 exists
to protect. The badge is above rather than beside for the same reason, measured: a badge sharing the
figure's line pushes the number left by the length of the word, so *Solid* and *Watch* put two rows'
figures at 651px and 639px.

That is where the owner asked for the badge, and it is why the figure could grow: *"percentage as
it's the most figure can become bigger and take that space."*

**The answer cell stays a table cell.** Caught during the final pass, after the thirty-odd browser
checks were already green: `.lk-lk` had been given `display: flex` to do the anchoring, and that
takes the `<td>` out of the table's column model. The 12% stopped applying and the cell shrink-wrapped
its contents — **28px of a 1078px table, with 103px unaccounted for across the row**. The figures
still *looked* aligned, and every check still passed, because all five fixture rows happened to
carry a range caption of the same number of digits. One row reading `9–14%` against another reading
`86–95%` would have moved the edge.

Two lessons worth keeping:

- It is the same family as the grid-item `<td>` that would not stretch to its track. **A table cell
  has a job; taking away `table-cell` takes away the job.** Flex was not needed — the fixed-height
  slot is what holds the alignment.
- **A passing check over a fixture that cannot fail it is not a check.** The harness now carries a
  sixth row with a one-digit range, and the run asserts both that every cell is still a `table-cell`
  and that the six columns account for the whole table width, so no cell can shrink-wrap unnoticed.

`.lk-rg` lost its fixed `158px` with the rail — that was the width of a drawn bar, and it was wider
than the column it sat in. As a caption it takes the width the column gives it.

## The two controls

**The picker** (`MarketPicker`) opens a listbox of every market this subject holds, likeliest first,
**each with its own percentage** beside it, so the choice is informed rather than a guess at a word.
With one market there is no control, just the name. It closes on outside `pointerdown` and on
Escape.

**The stepper** (`Stepper`) walks the rungs in `ladder`. It does **not** run past them. A rung we
hold no forecast for has no number, no range and no grade, and inventing one on a page about
uncertainty is the one thing this product must not do — so the ends are **disabled, with a reason in
the title**, rather than hidden. Hidden, the control would read as broken; absent, the line would
look fixed again.

Stepping to a rung that is not the lead one withdraws what belongs to the lead rung only: the
departure sentence (`p_usual` is *that rung's* usual), the result, the live tick. Changing market
resets the stepper, because a rung the reader chose in one market means nothing in another.

## What `cur` is, and why everything reads from it

`f` is what the server led with. `cur` is the forecast **on screen**. Every derived value in the
component reads `cur` — `p`, the band, the ladder, the strip, the departure, the lineup words, the
tier, the save and combo buttons. Reading `f` while showing another market is exactly how a card
ends up contradicting itself, and the five faults above include one instance of it.

`f` is still read for the things that belong to the **subject** rather than the market: the player,
the fixture, the position, the kick-off, the row id.

A feed that predates `markets` still works: `markets = f.markets?.length ? f.markets : [f]`, so the
lead forecast stands in as the only market and the picker renders as a plain name.

## Phone

The six columns fold into a grid. The number sits **top-right beside the controls** and the strip
spans the full width — the owner's markup, in his words: *"there's a big space above the percentage…
reasonable spacing between elements."*

Touch targets: the market button, both stepper buttons, Why, save and combo are all **44px** on a
coarse pointer (docs/12 F1). They measured 25px and 28px before.

**The CSS order trap, recorded because it cost an hour.** Every phone override was losing. The cause
was not specificity — the whole new control block had been appended **after** the
`@media (max-width: 760px)` query, and at equal specificity source order wins. Raising specificity
would have patched it; moving the block above the query fixed it. *Specificity is a patch, order is
the cause.*

## Where this is pinned

A Playwright harness renders the **real** `ForecastRow` out of the built app — not a mock-up — at
390px with touch emulated and at 1366px, over six rows: a settled hit, a settled miss, an untiered
bench player, a club line with no player and no markets, a row with no run data at all, and a row
whose range is one digit shorter than the rest.

Thirty-nine checks, all passing. The ones worth naming:

- no page errors and no horizontal overflow, at either width
- the market is a control, and `+N more markets` is gone
- the range rail is gone, the strip's column is at least the answer's, and the bars fill it
- every figure shares one right edge, badge or no badge, over captions of differing length
- on desktop, every cell is still a `table-cell`, and the six columns account for the whole table
- on desktop, every figure sits at one height from its row's top, within a pixel
- tap targets ≥ 44px on touch, ≥ 24px on a mouse
- **the stepper moves the line, the number follows, *and the range follows*** — fault 5
- the picker offers every market, and switching it changes both the market **and the ten-game strip**

## Still open

- **The ad builder's card template** (docs on the media and ad tooling) still draws the old
  layout. An ad and a card that look like different products is worse than either.
- **"He had 3"** on a club line. A team line has no *he*, and no one has decided what it says
  instead.

## Three faults the before/after comparison exposed

Found while rendering `main` and this branch side by side for review — after the browser checks
were green, which is the point of the section below.

**The strip was not using its column.** It had been widened from 14% to 20% and this document said
the evidence got the space. It did not: the bars were `width: 7px; flex: 0 0 auto`, so the strip
measured **88px whatever column it sat in**, and the extra 64px was whitespace. The claim was
false in the way that matters — it described an intention, not a render. The bars now grow from a
7px basis with a cap, so they stay bars rather than becoming blocks: **10.5px at 1366, 16px on a
phone**, and the strip is 123px of 215 and 248px of 312.

**The result wrapped.** `Happened — 3` broke across two lines inside the answer column and stood
42px instead of 24, so a settled row ran 154–175px against an unsettled row's 108. It fits on one
line in the width the column gives it; it only had to be allowed to.

**A row could show another row's number.** `cur` resolved through the `markets` list even for the
card's own market. In production the two agree — `group_cards` builds the card from the lead
forecast and lists that same forecast — so nothing was visibly wrong. But `f` is the copy the feed
ranked, sorted, filtered and counted on, and a row must never quietly display a number other than
the one the list used to place it. **On its own market, `f` wins.** A fixture that set `p` without
updating `markets` is what surfaced it: three rows that should have read 64%, 91% and 41% all read
64%.

The run is **39 checks** now. The ones added here: the bars fill more than half their column; the
result sits on one line; every row shows its own number.

## Deleted with the old layout

`.lk-band`, `.lk-band::before`, `.lk-band i`, `.lk-axis` and its children — the range rail and its
scale — along with `.lk-claim`, `.lk-morebtn`, `.lk-linesrow` and `.lk-pos-inline`, whose markup is
gone. A rule that styles nothing is the same class of thing as a setting that reaches nothing
(docs/67): it reads as a description of the product and is not one.
