# v8 — the reference pass

The owner supplied a reference site (forest green / mint, a marketing theme) with four notes:
the design is dull; use these colours, in dark mode too; pay attention to spacing, styles,
colours, fonts and tabs; and no element should be left orphaned.

## What "dull" actually was

Not the hue. The light palette shipped with **no second colour in it at all**:

| token | light value | |
|---|---|---|
| `brand` | `#034737` | deep forest |
| `tierSolid` | `#034737` | deep forest |
| `tierStrong` | `#1B8962` | mid forest |
| `up` | `#106C4F` | mid forest |
| `chart1` / `chart2` | `#034737` / `#1B8962` | deep / mid forest |

Every coloured thing on a white page was the same colour at the same volume, so nothing could be
emphasised relative to anything else. The mint `#A9FF9B` from the owner's seven existed only in
the dark palette, where it was spent on a tier label.

In the reference the mint is never a text colour and never a shade of the brand — it is a **fill
that carries dark ink**, used two or three times a screen and nowhere else.

## The change

### 1. Two new palette tokens (`backend/site_studio.py`)

`accent` and `onAccent`, taking `COLOR_TOKENS` from 23 to 25. Forest sets them to
`#A9FF9B` / `#22281E` in **both** modes — 12.56:1 — which is what "the same palette in dark
mode" asks for. Every other preset got its own pair (Carbon lime, Chalk ice, Apple green,
Midnight lime, High-contrast amber) so a re-theme does not inherit a mint that clashes.

`("onAccent", "accent")` joins `BLOCK_PAIRS`, so an owner cannot publish an accent whose ink
fails 4.5:1. All ten presets were measured in both modes: no block failures.

The accent is spent on the marks that mean *this one is worth your eye*:

- the **highlighter** behind the subject of a section heading;
- the **departure chip** (`+10`), the one figure comparable down a whole feed;
- the **Strong tier** — the rarest of the three.

It is deliberately **not** on the Solid tier or on "Confirmed starter". Those sit on most cards,
so filling them mint makes mint the wallpaper and emphasises nothing: the first attempt put nine
mint marks on one screen, which is the same monotony as the all-forest palette it replaced. Solid
is a brand outline and the lineup tag is an `up` outline, which makes the tier ladder read as
three real weights rather than three colours.

### 2. The highlighter (`.v2-hl`, `Marks.jsx`)

The reference's signature move. Painted as a `background-image` on the span so it sits behind
the glyphs with no stacking work, and carrying `--on-accent`, because the band is opaque.

Mode-aware, and it has to be: a marker swipe works on a light page because the half of each
letter standing above the band still reads against the paper. On a dark page the swiped word
carries dark ink, which is the background colour, so the tops of the letters vanished and
"today" came out as a green smear. On dark the band covers the whole word instead — the same
mark the reference uses for a standout figure.

### 3. Tabs

- The Today filter row was four floating pills with nothing above or below: the orphan in the
  middle of the page. It is now text on a hairline with a 2px brand underline on the active item.
- `.k-seg` stretched to its container, so three words on the Finder sat in a 1000px bordered box
  with 800px of nothing beside them. Fitted to its buttons; the chosen segment is filled with the
  brand instead of tinted a slightly different grey.
- The day strip was seven bordered tiles competing with each other and with the cards below.
  Selection is now a brand fill and everything else is plain text.

### 4. No element left orphan

- Cards in a grid share a height (`grid-template-rows: 1fr auto`) so their feet — the same two
  facts on each — land on one line instead of three. `matchday.css` pinned `.ins-grid` to
  `align-items: start`, which had to be undone for the rule to reach Insights.
- Giving them a shared height handed the slack to each card's own auto rows, so the market line
  and the Usual row drifted apart differently per card: the same problem moved inside the card.
  `align-content: start` packs the rows and gives the slack to the foot.
- The Finder's eight starts push their chip rows to a shared bottom edge.
- Section heads were 13px — the size of the body under them. Now `clamp(21px, 2.3vw, 28px)` on a
  hairline, with the "See all" / "Match page" link as a pill on that rule rather than floating.
- A spacing rhythm: `--v2-gap-section` (40px, 56 on desktop, 26 on a phone) between blocks,
  `--v2-gap-block` (18px) inside them. The page had one medium gap everywhere, which is why
  nothing looked grouped and everything looked adrift.

## Bugs this pass introduced and fixed

- **Card overflow.** `.k-fc` is a one-column grid, and a grid column takes the min-content of its
  widest item. A `nowrap` foot therefore sized the column, the column overflowed the card, and the
  card — which clips — cut the percentage off the header above. Capped with `minmax(0, 1fr)`.
- **The departure chip never got the accent.** `.v2-cmp-d.is-up` already carried
  `color: ... !important`, one class more specific than the new rule, so the chip stayed a 3.27:1
  green-on-green tint. Fixed at the original rule rather than by stacking another `!important`.
- **A mint badge read straight through the phone's bottom bar** (78% over a 20px blur) and put a
  green smear behind "You". The blur stays; the bar is now 94%.

## Verified

- All 10 presets pass `BLOCK_PAIRS` in both modes.
- A contrast and touch-target sweep over `.k-chip`, `.k-seg button`, `.k-day`, `.btn`, `.k-link`,
  `.k-tier`, `.k-tag`, `.v2-cmp-d` and the start chips, on Today / Finder / Insights, light and
  dark, at 390 and 1280: no contrast failure, no touch target under 44px at touch widths.
  (`.v2-hl` reports 1:1 in that sweep — the probe reads `background-color` and the highlight is a
  `background-image`. Confirmed correct by screenshot in both modes.)
- 42/42 self-tests, `npm run build`, `npm run check-copy`.

## Not done, and why

The reference is a marketing site: full-bleed forest bands between white sections, a hero, an
alternating text/visual rhythm. Those are page-level devices for a page whose job is to persuade
once. This product's job is a dense feed a reader returns to daily, where a full-bleed band every
400px would be noise. The language was taken — the ground, the accent, the tab, the rhythm, the
hairline — and the layout devices were not.
