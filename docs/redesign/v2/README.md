# v2 redesign — "chalk on slate"

Branch `redesign/world-class`. `main` untouched. Driven by the **frontend-design** skill, which asks
for a written plan reviewed against the brief before any code is written.

Read in this order:

| | |
|---|---|
| `PLAN.md` | the design plan: brief, concept, tokens, and the alternatives rejected with reasons |
| `UX_AUDIT.md` | the questions asked of the existing design, answered from what is on screen |
| this file | what changed, and what is deliberately not done |

## The argument

The product sells one sentence: *here is something about this match you would not have guessed.*
Its own thesis, argued across docs/50 to docs/56, is sharper than "show data nicely":

> A forecast is only worth showing if it could have come out differently.

So the design's job is to make **"could have come out differently" visible without words**. If a
reader can tell a real claim from a truism before reading anything, the design has worked. That is
the test every decision below was judged against.

## What was there

A competent Apple HIG clone with a Swiss typographic pass over it. Both were real improvements.
Neither was *this product*:

| | before |
|---|---|
| Palette | Apple system blue on Apple greys |
| Type | the `-apple-system` stack |
| Form | rounded cards, one radius, one grey shadow, in a vertical stack |
| The number | 28px, beside a 17px label — sized like a label, not like the subject |
| The evidence | ten green boxes reading "10 of 10 reached it" |

The last two actively fought the thesis: a near-certainty and a real claim were drawn identically.

## What changed

### 1. Ground and ink
"Chalk on slate": a deliberately hued blue slate, chalk ink, and **three semantic colours that are
the only hues in the interface**. No brand accent — in a product whose job is to signal whether a
number means something, spending a colour on identity steals it from meaning.

Measured, both modes, before committing: lowest text pair 5.38:1 against a 3.0 threshold, every
BLOCK_PAIR and WARN_PAIR passing. The palette lives in Site Studio as the **Chalk** preset and the
new default; the Apple palette is kept as a preset, exactly as Midnight was when it was replaced.

### 2. Type
**Archivo**, self-hosted, one family, with the **width axis** carrying hierarchy from a condensed
data label to an extended headline. A second family would be a costume; a monospace face for data
labels is a generated-page tell.

### 3. The evidence mark
The card's bar was a filled likelihood meter. **A filled meter says "this number is big", which is
the one conclusion a reader must not draw, because a big number is exactly what a truism looks
like.** It now reads as a measurement: the band is the likely range, a segment runs from what the
entity usually does to what it does in this fixture — length is the size of the claim, colour is
the direction — and a chalk tick marks the usual.

### 4. The run
`RunStrip`. A column per game standing to its own figure, with the line drawn across as a dashed
rule. Where the rule falls is the message:

- **through the middle of the run** — a real question, worth a forecast;
- **flat along the bottom** — every column clears it; a truism.

This replaces ten filled-or-empty squares that could not tell a quiet game from a busy one, and it
is now on the player page rather than only inside two overlays.

### 5. Structure (from UX_AUDIT)
Measured: on a 390×844 phone the first forecast on Insights sat at **913px — below the fold**,
behind eleven controls and a 542px filter panel. **Now 476px**, a 48% reduction.

| Decision | Change |
|---|---|
| Answer first, filter second | one compact bar; every filter in one grouped sheet |
| Drop the no-op control | the likelihood floor defaulted to 0 and held a full row |
| Group by the unit readers think in | the feed groups by fixture, with clubs and kick-off |
| Reading, not administering | "Show more matches" replaces "Per page 25" and page buttons |
| Card diet | "Usually 79%" and "Hit in 19 of his last 20" both restated what the bar now draws |
| Demote the secondary action | the add-to-combo "+" held the best corner of every card |
| No carousel inside a scrolling page | Today's Top 3 became three rows; the second was clipped before |
| The page is about the match | the match hero takes weight; group headings outrank their cards |
| The trust page gets the size | "when we say 78%, it happens 81%" is now the largest type in the product |

### 6. What the 96-shot sweep found
Sweeping all 24 routes × 2 widths × 2 schemes turns up what three pages cannot:

- **Light mode had no identity.** It had inherited white cards on near-white with a shadow under
  each — the page every product in this category ships. It now earns it the way a printed results
  page does: paper is the surface, panels are separated by rules, a card inside a card loses its
  second border.
- **Track record had no visible title** — its `h1` was `sr-only`, so the one page whose job is trust
  opened with a small centred caption.
- **Chip rows clipped their last option** instead of wrapping, so filters existed that a reader
  could not see or reach.
- **Every short page had a ~500px dead band.** `.main` carried `min-height: 62vh`, so Plans,
  Combos and Track record each showed a short card, a screenful of nothing, then the e-mail block.

## What is deliberately not done

- **The navigation overlap.** Today, Insights, Finder, Explore and Combos — four of six
  destinations are ways to find a forecast, and a new reader cannot tell them apart. It is the
  largest navigation problem in the product and it is an information-architecture change: it moves
  routes, tests and analytics. It should not be smuggled into a redesign pass.
- **The Finder's query sentence is the best interaction in the product** — plain English where every
  underlined word is editable — and it is buried on a secondary page. Same reason.
- **The content levers.** The feed is full of near-certainties because of `engine.min_span` and
  `engine.personal_lines`, not because of the stylesheet. Asked to keep this branch visual.
- **Admin.** Public screens only so far.

## Checks

| | |
|---|---|
| Backend self-tests | **42 PASS, 0 FAIL** |
| Copy checker | passes |
| Class names | none renamed or removed; new ones prefixed `v2-` |
| Colour | only `var(--…)`, so an owner's palette still applies |

## Shots

| Folder | What it holds |
|---|---|
| `before/` | the screens as they were before the v2 pass |
| `after/` | the v2 pass, on the Chalk palette it was designed against |
| `carbon/` | the Carbon palette (commit `329342e`): Today, Match, Insights and Track record, phone and desk, dark and light |
