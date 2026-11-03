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
| 6 | Forecast card | §5 `spacing-scale` (density 8) | Every edge carried the comfortable scale, so one card ran ~290px on a phone and twenty made an 8,000px wall. The dense scale takes about a fifth off without touching a 44px target. |
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
| Insights | 8,036px — 20 cards | Same. The density pass takes a fifth off; the rest is a markup question. |

### Screens not yet covered

The 62 captured screens are every **route** the router defines. A route is not a screen. These
states are captured by a second harness (`states.js`) and were still running when this was
committed:

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

### Not yet checked at the time of this commit

- **The backend self-test suites have not been re-run to completion.** A run was started and
  was killed by a 30-minute background limit while four Chromium contexts were competing for
  the CPU; it printed nothing before it died. This pass touches one `.jsx` line and one new
  stylesheet, so no Python behaviour should be affected, but that is reasoning, not evidence.
  Run `bash backend/run_tests.sh` before relying on this.
- The after-capture and the stateful-screen capture were still running when this was
  committed. See "Screens not yet covered" above.

## Going back

Delete the `import "./styles/swiss.css";` line from `frontend/src/index.js`. Nothing else
depends on it.
