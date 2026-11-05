# v2 redesign — design plan

Branch `redesign/world-class`. `main` is untouched.

## 0. The brief, stated before anything is drawn

**Subject.** Forecasts for football statistics: how many shots, cards, corners, tackles a named
player or club is likely to record in a named fixture.

**Audience.** People who follow football closely and act on specific numbers. They already know the
sport. They do not need a number explained; they need to know **whether it is worth their
attention**, and whether this source has been right before.

**The job of the design.** Not "present data attractively". The product's own thesis, argued across
docs/50 to docs/56 and in the owner's words, is sharper than that:

> A forecast is only worth showing if it could have come out differently.

`9+ shots, 88%` is true and useless. The design's job is therefore to make **"could have come out
differently" visible at a glance** — and to make a claim look like a claim, not like a description.
If a reader can tell a real forecast from a truism without reading a word, the design has done its
work.

## 1. What is wrong with what exists

The current app is a competent Apple HIG clone with a Swiss typographic pass on top. Both passes
were real improvements and both are *conventions*, not an identity:

| | |
|---|---|
| Palette | iOS system blue `#409CFF` / `#0066CC` on iOS greys. This is Apple's palette, not the product's |
| Type | `-apple-system` stack. The default on every Apple surface in the world |
| Form | Rounded cards, uniform radius, one grey shadow, in a vertical stack |
| The number | 28px, in a row with the market name. Sized like a label, not like the subject |
| The evidence | Ten green boxes reading "10 of 10 reached it" — which is a picture of nothing |

Nothing here is *bad*. Nothing here is *this product*. And the last two rows actively work against
the thesis: a near-certainty and a real claim are drawn identically.

## 2. Concept: the run, and the next mark

The signature of the product becomes the thing the product is actually about.

Every player and club has a **run**: its last ten in this metric, drawn as actual counts. The
forecast is **the next position in that run** — drawn not as another bar but as a *band*, the
10-to-90 range, with the line marked across it.

```
        his last ten                     this match
   ┌───────────────────────────────┐   ┌───────────┐
 8 │              ▐                │   │           │
 6 │     ▐  ▐              ▐     ▐ │   │   ░░░░░   │   band = 10-90 range
 5 │  ▐        ▐     ▐  ▐          │   │ ──░░░░░── │   rule = the line
 4 │                          ▐    │   │   ░░░░░   │
 2 │                       ▐       │   │           │
   └───────────────────────────────┘   └───────────┘
      3  6  6  5  8  5  5  4  2  6          5+
```

Read it once and you know three things with no text: **his own level** (how tall the run is),
**where the line sits against it** (the rule), and **how sure we are** (how deep the band is).

Now the same player at `1+ shot`:

```
 8 │              ▐                │   │           │
 6 │     ▐  ▐              ▐     ▐ │   │  ░░░░░░░  │
 4 │                          ▐    │   │  ░░░░░░░  │
 2 │                       ▐       │   │  ░░░░░░░  │
 1 │ ─────────────────────────────── ──░░░░░░░░░── │   the rule sits under everything
```

**The rule falls below every bar in the run.** The uselessness is visible, instantly, without a
percentage, without a tier badge, without reading. That is the whole argument of docs/56 made into
a picture, and it is a graphic no other product in this space is drawing, because no other product
has made that argument.

This is where all the boldness goes. Everything else gets quieter to pay for it.

## 3. Tokens

### Colour — "chalk on slate"

The vernacular is the tactics board, not the scoreboard and not the newspaper. Its discipline is
the point: **a chalk board has no decorative colour, so colour can be reserved entirely for
meaning.**

Dark (primary):

| Token | Hex | Role |
|---|---|---|
| `--bg` | `#0D1620` | slate ground — a blue slate, deliberately hued, not a tinted black |
| `--surface1` | `#13202C` | raised |
| `--surface2` | `#1A2938` | raised twice |
| `--border` | `#243546` | chalk-dust rule |
| `--text` | `#E8EEF2` | chalk |
| `--text3` | `#9FB0BE` | chalk, worn |

Light ("graphite on paper", cool, not cream):

| Token | Hex |
|---|---|
| `--bg` | `#EEF2F5` |
| `--surface1` | `#FFFFFF` |
| `--text` | `#111A22` |
| `--text3` | `#55646F` |

Semantic, and **used nowhere else** — these three are the only colours in the product:

| Token | Dark | Light | Means |
|---|---|---|---|
| `--up` | `#35C27E` | `#0F7A4A` | above the entity's usual |
| `--down` | `#FF6B6B` | `#C0392B` | below it |
| `--warn` | `#E8B23A` | `#8A6100` | conditional — lineup not out |

There is **no brand accent colour.** That is the risk in this plan and it is taken deliberately: in
a product whose entire job is to signal "is this meaningful", spending a colour on identity steals
it from meaning. Identity comes from the type, the ground and the run graphic instead.

### Type — one family, width as the variable

**Archivo** (variable, `wght` 100–900 and `wdth` 62–125), self-hosted at
`public/fonts/archivo-latin-var.woff2`. The CSP is `default-src 'self'` with no `font-src`, so a
web-font CDN would be blocked; self-hosting is required, not a preference.

One family, because two would be a costume. Personality comes from the **width axis**, which almost
no product uses and which is native to sports typography — the condensed scoreline, the extended
headline.

| Role | Setting |
|---|---|
| The number | `wdth 112`, `wght 600`, 56px, `-0.03em`, tabular |
| Page title | `wdth 108`, `wght 600`, 28px, `-0.02em` |
| Section head | `wdth 100`, `wght 600`, 17px |
| Body | `wdth 100`, `wght 400`, 15px / 1.5 |
| Data and labels | `wdth 92`, `wght 500`, 13px, tabular — condensed so a column of figures is narrow, **not** monospace |

Rejected: a monospace face for data labels. It is on the list of generated-page tells, and a
condensed grotesque with tabular figures does the same job with more character.

### Layout

A single measured column on a phone; on a desktop, a content column with a quiet rail. Content is
**left-aligned throughout** — a run reads left to right, and centring it would fight the one
graphic the design is built on. No centred hero, no centred section heads.

Radius varies with hierarchy rather than being one value everywhere: `0` on data marks and runs
(they are measurements), `10px` on raised surfaces, `999px` only on controls that are genuinely
pill-shaped.

## 4. Principles

1. **Colour means something, or it is not used.** Three semantic colours; no decorative hue.
2. **The number is the subject.** It is set like a scoreline, and everything near it annotates it.
3. **Every forecast shows the run it came from.** A number with no evidence beside it is not shown.
4. **A truism must look different from a claim.** This is the test the design is judged against.
5. **Motion answers an action.** One reveal when a sheet opens. Nothing moves on scroll or hover.

## 5. Review against the brief, before building

The skill asks whether any of this is a default I would produce for any similar brief. Working
through it honestly:

| Axis | First instinct | Kept or changed |
|---|---|---|
| Palette | Dark ground + one bright accent | **Changed.** That is listed tell #2. Dropping the brand accent entirely is the harder and more defensible choice for a product about signal |
| Palette | Pitch green | **Rejected.** Green is the obvious football cliché *and* it collides with `--up`. Colour cannot mean "football" and "above usual" at once |
| Type | System stack, or Inter | **Changed.** Both are invisible defaults. Archivo's width axis is the specific choice, and it is native to sports setting |
| Type | A condensed display face like Oswald or Barlow | **Rejected.** That is the generic "sports product" costume |
| Form | Rounded cards in a stack | **Changed.** Tell #4. The card becomes a run-line |
| Chrome | ALL-CAPS eyebrow, `A · B · C` meta, `→` on links | **Removed.** The current app uses the middle-dot meta string heavily; it goes |
| Hero | Big number, small label, supporting stats | **Changed.** The hero is the run graphic, which is a big number *with its evidence* — the default treatment plus the only part that makes it trustworthy |
| Layout | Broadsheet hairlines, zero radius, dense columns | **Rejected.** The Swiss pass already went there; going further is another default, and the run graphic needs air |

The one thing I will not claim: this is still a dark, dense, data-led interface, which is the house
style of the category. The departures are the width axis, the absence of a brand colour, and the
run graphic. If the result reads as "a very good version of the category" rather than "unlike
anything else", that is the honest ceiling for a product whose readers need familiarity to scan
quickly — and I would rather say so than oversell it.

## 6. Constraints this must not break

- **Class names already in the markup keep working.** Site Studio injects an owner's theme by class
  (docs/15, docs/16), the copy checker and 42 self-tests run against the markup, and `data-testid`
  attributes are the test contract. New classes may be added; existing ones are not renamed.
- **Only `var(--…)` colours**, so an owner's palette still applies.
- **docs/03 banned words.** No exceptions, including in any new copy.
- **Contrast.** Every text pair at 4.5:1, every data mark at 3:1, in both modes, measured not
  assumed — the draw-segment failure in the Swiss pass was found by measuring.
