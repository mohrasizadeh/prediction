# Swiss pass

A critical UI/UX pass over every screen, public and admin, driven by the **ui-ux-pro-max** skill
(`.claude/skills/ui-ux-pro-max`, vendored in commit `15df001`).

Everything lands in one stylesheet, `frontend/src/styles/swiss.css`, loaded last in
`frontend/src/index.js`. **No class name was added, renamed or removed**, so Site Studio, the copy
checker, the self-tests and the HIG layer all keep working untouched. Only `var(--...)` colours are
used, so an owner's palette still applies (docs/15).

## The direction

The skill's design-system generator was run against the product:

```
search.py "football statistics forecast data dashboard dense" --design-system \
          --density 8 --variance 3 --motion 2 -p "Prediciotn"
```

| Dial | Value | What it asked for |
|---|---|---|
| style | **Minimalism & Swiss Style** | "grid-based, high contrast, essential"; *avoid shadows and gradients* |
| density | 8/10 | the dense 8–32px spacing scale, not the 16–64px one |
| variance | 3/10 | centred and plain; no asymmetric or decorative layout |
| motion | 2/10 | subtle only; motion explains a change, it does not decorate one |

Two parts of its answer were **not** taken:

- **Pattern "Enterprise Gateway"** — a conversion layout for enterprise sales landing pages
  (hero video, solutions by industry, contact sales). It does not describe this product.
- **Its colour palette** (`#1E40AF` / `#D97706` on `#F8FAFC`) — a generic Tailwind blue-and-amber.
  The app already has an Apple-semantic palette with every text pair verified at 4.5:1 in both
  modes (docs/redesign/hig). Replacing a measured palette with an unmeasured one is a regression,
  not a redesign. The structure, rhythm and ornament rules were taken; the colour was left alone.

## What changed

| # | Area | Rule | Change |
|---|---|---|---|
| 1 | Type | §6 `font-scale`, `visual-hierarchy` | Section headings were set *smaller* than the body text under them, so a page arrived as one flat block. A single ramp now applies across public and admin, and the section head sits on a hairline. |
| 2 | Type | §6 `letter-spacing` | The all-caps kicker was tracked at `.1em`, a display mannerism. Reduced to `.04em`. |
| 3 | Figures | §6 `number-tabular` | Tabular lining figures on every number a reader compares down a column, so digits hold their place and rows do not shimmer when a value ticks over. |
| 4 | Ornament | style record: *avoid gradients* | Eleven decorative gradients flattened to a surface and a hairline: the two avatars, the admin brand mark, the auth aside, the plan hero, the match hero, the highlighted player and plan cards, the admin meter and bars, and the weekly-e-mail block. Gradients that carry information stay — skeleton shimmer, heat-map legend ramp, goal and substitution icons, media checkerboard, scroll mask fades. The brand mark is untouched: a logo is brand property, not the design system's to restyle. |
| 5 | Forecast card | §6 `truncation-strategy` | The tier note sat in a 14ch column beside its badge and broke into three or four ragged lines, colliding with the add button. The head is now a small explicit grid and the note takes a full-width row. `.k-fc-tier` carries no paint, only layout, so `display: contents` hands its two children to the head grid and nothing is lost. |
| 6 | Forecast card | §5 `spacing-scale` (density 8) | Every edge carried the comfortable scale, so one card ran ~290px on a phone and twenty made an 8,000px wall. The dense scale takes **about 17px off each card, roughly 6%** — see "What the density pass actually bought" below, which corrects a larger figure claimed earlier. |
| 7 | Data marks | §10 `contrast-data` | **Measured failure.** The draw segment of the win/draw/away bar was `--text3` at 60% opacity over `--surface1`: **2.98:1 in dark, 2.40:1 in light**, against the 3:1 a data mark needs. At full strength it reaches **5.94:1 and 5.23:1**. The segments stay tellable apart without colour because they keep their fixed home-draw-away order. |
| 8 | Data marks | §10 `data-density` | In a desktop fixture row the bar sat in a `1fr` column and stretched past 900px, so no two rows could be compared by eye. Capped at 340px, which turns the column into a small-multiple that reads down the page. |
| 9 | Lists | §5 `spacing-scale` | 76px fixture rows showed six matches on a phone screen; 64px rows show nine, and the tap target stays well over 44px. Same treatment for insight rows, event rows and stat cells. |
| 10 | Desktop rail | §5 `visual-hierarchy` | The rail is sticky and one viewport tall, so its right-hand border stopped in mid-air part way down any long page and left a line hanging in the middle of the screen. The rule is now painted on the row behind it and runs the full height of the document. |
| 11 | Motion | §7 `layout-shift-avoid`, `transform-performance` | Cards lifted on hover, which moves the row out from under the pointer and invites a jitter loop on a dense grid. Emphasis moves to the border: same affordance, no geometry change, nothing for the compositor to re-lay-out. Timing is in the 200–250ms the style record asks for. |
| 12 | Admin | §5 `spacing-scale` | The admin is a working tool read at a desk all day, so it takes the dense end of the scale. Settings rows also reach two columns at 768px instead of 1025px. |

### One earlier decision superseded

HIG pass 3 added a radial brand wash behind the weekly-e-mail block so it would read as an
invitation rather than another card. Swiss gets the same separation from a rule and a measure.
If the wash is wanted back, delete the `.nl, .nl2` rule in section 2 of `swiss.css`.

## Found on the way, fixed

`frontend/src/pages/League.jsx:79` crashed the whole League page with
`Cannot read properties of null (reading 'toFixed')`, reproducibly, in all four
viewport-and-theme combinations. The line guarded on `avg` being truthy but then read
`avg.yellow_pg.toFixed(2)`; the API returns the average object with `yellow_pg: null` when no
refereed games exist yet. The two sibling lines, 85 and 106, already guarded the field itself.
Now `avg?.yellow_pg != null`.

## Found on the way, not fixed

These need markup, not CSS, so they are written down rather than done.

| Screen | Measured | What it needs |
|---|---|---|
| Admin → Settings | **71,953px tall** on a phone at the default "All groups" — 243 rows, every one rendered | Groups collapsed by default. Search and a group filter already exist; what is missing is that the default view is everything. §3 `virtualize-lists` applies at 50+ items. |
| Admin → PitchAPI | 9,600px | Same shape. |
| Match | 9,249px — about 25 forecast cards, all identical in weight | Progressive disclosure: the reason line and the record line belong in the sheet, not on every card in the list. |
| Insights | 8,036px -> 7,693px, 20 cards | Same. The density pass takes 4.3% off; the rest is a markup question. |

### What the density pass actually bought

Measured, phone at 390px, every route before and after:

| Screen | Before | After | Delta |
|---|---|---|---|
| Admin -> Settings | 71,953 | 68,654 | **-3,299 (-4.6%)** |
| Match | 9,249 | 8,837 | **-412 (-4.5%)** |
| Insights | 8,036 | 7,693 | **-343 (-4.3%)** |
| Today | 2,630 | 2,671 | **+41 (+1.6%)** |
| **All 62 routes** | **193,770** | **190,044** | **-3,726 (-1.9%)** |

**This corrects a larger claim made while the work was in progress.** The density pass was described
as taking "about a fifth" off the card walls. It takes about 4.5%. The reason is that a forecast
card's height is governed by its content -- a header, a market line, a bar and three lines of prose --
not by its padding, so tightening the spacing scale saves roughly 17px on a 290px card and no more.

Today got 41px *taller*, and that is the intended trade: the tier note moved from a 14ch column into
a full-width row, which reads properly instead of breaking into four ragged lines, and costs a line
of height on the cards that carry one.

`pub-account-devices` shows +330px and is **not** comparable: it lists sign-in sessions, and the
capture harness itself signed in four times during each run, so the after page genuinely has more
rows. The measurement is confounded, not the design.

The real size problem on those screens was never the padding. It is that every card carries its
reason line and its record line in the list, and that Settings renders all 243 rows at once. Both
need markup, and both are in the table above.

### Screens beyond the routes

The 62 captured screens are every **route** the router defines. A route is not a screen, so a
second harness (`states.js`) captures the states a route can be in:

match tabs before kick-off (Forecasts, Lineups, Analysis) and after full time (Recap and the
rest); the forecast sheet a card opens; the player page and its table toggle; the six team tabs;
the five league tabs; the search overlay; the combo bar with a line added; Today, Following,
Combos, Track record and Account signed in; and the four PitchAPI admin sub-tabs.

Two gaps that harness cannot close:

- **No live match.** All twelve demo fixtures are scheduled and the rest are final, so the Live
  tab and the in-play card tracking are never rendered. Showing them needs `tests/live_mock.py`
  wired into `tests/demo_server.py`, which is backend work on a test helper.
- **No visitor popups.** All four kinds are admin-authored content that does not exist in demo
  data. `/dev/kit` shows their components, not the real popups.

### Still open

The win/draw/away bar still does not print the draw percentage visually. Screen readers get it
(the `aria-label` on `.k-wdl` carries all three), sighted readers do not. Adding it is a change
to `WdlBar` in `components/ui/Marks.jsx`.

## Checked

- Build passes. `yarn check-copy` passes.
- Contrast recomputed for every pair this file touches (the numbers in row 7 are measured,
  not estimated).
- Every route captured before and after at 390x844 and 1440x900, in dark and light:
  **62 screens x 4 contexts**, public and admin, signed in as the owner. The baseline run
  finished with zero page or console errors.

- **All 40 backend self-test suites pass**, including the new `selftest_pitch_images.py`.
  (An earlier run of this was killed by a background time limit while four Chromium contexts
  were competing for the CPU, and an earlier version of this file recorded it as unverified.
  It has since been run to completion: 40 pass, 0 fail.)
- The stateful screens are captured too: **34 states x 4 contexts = 136 screenshots**, listed
  below.

## Going back

Delete the `import "./styles/swiss.css";` line from `frontend/src/index.js`. Nothing else
depends on it.

## Pictures

- `sheet-routes.png` — all 62 routes, phone, dark, after the pass.
- `sheet-states.png` — all 34 states, phone, dark.
- `pairs/` — before and after side by side for the ten screens that changed most, phone and desktop.

The full set (248 route pairs and 136 state screenshots across phone/desktop x dark/light) is
produced by the two harnesses and is not committed; re-run them against a demo server to rebuild it.
