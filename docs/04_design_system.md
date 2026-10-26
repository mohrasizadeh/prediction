# 04. Design system: "calm control room"

Dark first. Quiet surfaces, one brand colour, three tier colours. The numbers are the hero. Machine-readable values are in `design_tokens.json`. Use that file as the single source: generate CSS variables from it.

## 1. Principles

1. **Numbers first.** Big tabular numerals. Labels small and quiet.
2. **One screen, one job.** Each page answers one question.
3. **Show why.** Every forecast has its reasons one tap away.
4. **Honest colour.** Colour never carries meaning alone. Name, dots, or a printed number always backs it.
5. **Fast.** Skeletons not spinners. Data arrives in under a second from our database.
6. **Mobile first.** Designed at 390 px wide, then widened.

## 2. Setup for Emergent's React template

- Load Inter (400, 500, 600, 700) with `font-display: swap`. Turn on tabular figures: `font-variant-numeric: tabular-nums`.
- Generate CSS variables from `design_tokens.json` on `:root` (dark) and `:root[data-theme="light"]`. Default theme follows `prefers-color-scheme`, user choice saved in the account and in `localStorage`.
- If the template uses Tailwind and shadcn/ui, map the tokens to the Tailwind theme and the shadcn CSS variables. Keep the component names. Do not add a second component library.
- Icons: one set (Lucide). 20 px, 1.75 px stroke.
- Charts: Recharts. Use `chart1..chart6` in order. Grid lines `border`. No gradients, no 3D.
- The brand name, logo, colours, font and radius come from settings (`brand.*`, `theme.*`) and override the tokens at runtime. Read them from `GET /api/public/settings`.

## 3. Colour roles

| Role | Dark | Light | Use |
|---|---|---|---|
| `bg` | #0A0E17 | #F5F7FB | Page |
| `surface1` | #111827 | #FFFFFF | Cards |
| `surface2` | #182033 | #F0F3F9 | Raised: inputs, table header |
| `surface3` | #212B42 | #E6EBF4 | Hover, selected row |
| `border` | #243049 | #E2E8F2 | Hairlines |
| `borderStrong` | #33415F | #C9D2E3 | Inputs, focus-adjacent |
| `text` | #E9EEF7 | #0B1220 | Body, numbers |
| `text2` | #A3AFC6 | #475269 | Secondary |
| `text3` | #75819B | #6B7690 | Captions (4.5:1 on surface1) |
| `brand` | #7C83FF | #4F46E5 | Primary button, links, selection |
| `tierStrong` | #2DD4BF | #0D9488 | Strong tier |
| `tierSolid` | #60A5FA | #2563EB | Solid tier |
| `tierWatch` | #FBBF24 | #B45309 | Watch tier |
| `up` / `down` | #34D399 / #F87171 | #059669 / #DC2626 | Reached / did not reach, change arrows |

Contrast rule. In **light mode** the tier and up/down colours are 3:1 on white. Use them for dots, bars, borders and icons only. Print the words in `text`.

## 4. Type

| Style | Size / weight | Use |
|---|---|---|
| Display | 36 / 700 | Likelihood on the Match hero |
| H1 | 28 / 700 | Page title |
| H2 | 22 / 600 | Section |
| H3 | 18 / 600 | Card title |
| Body | 16 / 400 | Reasons text |
| Small | 14 / 400 | Table cells, chips |
| Caption | 12 / 500 | Labels, measures |
| Number-L | 28 / 700 tabular | Likelihood on cards |
| Number-M | 16 / 600 tabular | Table numbers |

## 5. Space, shape, motion

- 4 px grid. Page gutter 16 px mobile, 24 px desktop. Max content width 1200 px.
- Radius: 8 (chips, inputs), 12 (cards), 16 (sheets, hero), 999 (pills).
- Card: `surface1`, 1 px `border`, radius 12, padding 16. One shadow level only.
- Motion: 150 ms for hover and press, 220 ms for sheets and tabs, 600 ms only for the likelihood ring filling once on first view. Easing in tokens. With `prefers-reduced-motion`: no motion, instant.

## 6. Layout

- **Mobile (below 768):** top bar 56 px (logo, search, avatar), content, bottom tab bar 64 px. The tabs are the first four ids in `nav.mobile_tabs` from Site Studio (default Today, Finder, Insights, Following) plus **More**, which opens a sheet with the rest of the menu. Filters open in a bottom sheet.
- **Tablet and desktop (768 and up):** left rail 72 px collapsed or 240 px open, content area, optional right panel 360 px (Quick view). Filters sit in a sticky bar above the list.
- Tables scroll horizontally inside their card. First column sticky.
- Safe-area padding on iOS.

## 7. Components

Build these once, reuse everywhere. Each has states: default, hover, focus, active, disabled, loading, empty, error.

### TierBadge
Pill, radius 999, height 24. Dots then name: `●●● Strong`. Dot colour = tier colour; text = `text`. `aria-label="Strong tier, 3 of 3"`.

### LikelihoodBar
Number-L value ("74%"), then a 6 px bar on `surface3`, fill in tier colour, and a thin band (10th to 90th percentile) drawn as a lighter overlay on the bar, with the text "66 to 81" in Caption below. A confirmed-lineup tick (✓ Confirmed) or "Predicted" label sits at the right.

### ForecastCard
Card. Top row: player avatar (or team crest), name, position chip, team v opponent, kickoff. Middle: market label ("2 or more shots") and LikelihoodBar. Chips: opponent tactic chips ("Opponent: low block"). Bottom: first reason sentence, "Why" button expands all reasons (max 2) and the numbers behind them: expected value, last-10 reached (e.g. "7 of 10"), minutes expected. Actions: Save (bookmark), Follow player.

### TacticChip
Pill 28 px, icon + label ("Low block", "High press", "Possession"). `surface2`, 1 px `border`. Tooltip with `copy.tactic_explanations`.

### ReasonList
Up to two sentences, 16 px, `text2`, each with a small icon (arrow up in `up`). Sentences come from the engine unchanged. Admin may override exact sentences (`copy.reason_overrides`).

### Crest, LeagueMark, PlayerAvatar
Images come from our own address (`image` on every team, league and player object; null means draw the fallback). `Crest` 20, 28, 40, 64 px, `object-fit: contain`, fallback a shield outline in `text3` on `surface2`. `LeagueMark` 20, 28, 40 px, fallback the league's two-letter code. `PlayerAvatar` 32, 48, 96 px, circle, `object-fit: cover; object-position: center top`, fallback two initials on a tint picked from the player's id. All: set width and height, `loading="lazy"` below the fold, 150 ms fade (none under reduced motion), swap to the fallback on error, `alt=""` when the name is printed beside it, otherwise `alt="Arsenal crest"`. In dark mode, put a crest on a `surface` chip with 4 px padding and a 1 px `border` ring. Details in `19_images_logos_photos.md` §5.

### FixtureRow
Two lines: teams (crests, names), kickoff right. Under: three-segment win/draw/loss bar (brand, `text3`, `border`) with the percentages in Caption; insight count chip ("12 insights"); lineup chip (Predicted / Confirmed / Not yet).

### SquadGrid
Sticky first column (player + position). Columns = the team's last N games, newest left, header = opponent crest + H/A. Cell shows the number (Number-M). Cell background: `up` at 16% when the stat reached the chosen line, else transparent. Cell with no appearance shows "–" in `text3`. Footer row: average. Header tap = popup with both lineups and formations. Column chooser and hide-game controls (P2).

### Chart (Quick view)
Bars for the last N games, a dashed line at the chosen threshold, bars at or above the line in `up`, others in `text3`. Controls: window (5, 10, 20), started only, home/away, line (N or more). "Show table" button.

### Filters
Segmented controls for small sets (mode, window), chips for multi-select (leagues, positions), sliders for minutes. The active filters appear as removable chips under the bar. "Reset" always visible. The state lives in the URL so a view can be shared.

### Tabs
Underline tabs, 44 px high. Active = `text` with a 2 px `brand` underline.

### Tables
Row height 44 (comfortable) or 36 (compact, `theme.density`). Header on `surface2`. Zebra off. Hover `surface3`. Numbers right-aligned, tabular.

### States
- **Loading:** skeleton blocks in `surface2` with a slow shimmer (off in reduced motion).
- **Empty:** icon, one sentence, one action. Example: "No insights for this date. Try another day."
- **Error:** inline card with the error in plain words and a Retry button. Never a raw stack trace.
- **Stale data:** thin banner under the header (see `03_rules_and_compliance.md`).
- **Not available yet:** grey chip with tooltip reason.

### Site-controlled look
Colours, fonts, corners, density, shadows, button style and menus come from the **Site Studio** config (`16` §2). Tokens in `design_tokens.json` are the **defaults** and the "Midnight" preset. The front end reads `GET /api/site/config` and injects its CSS, so every value here can change without a deploy. There are 23 colour tokens per mode (the earlier 16 plus `text3`, `tierStrong`, `tierSolid`, `tierWatch`, `up`, `down`, `onDown`, and six `chart` colours, as listed in the file). Use the classes `.btn`, `.btn--primary|secondary|ghost|danger`, `.btn--sm|md|lg`. Never hard-code a colour, radius or font in a component.
Readability gate (server-side, blocks Publish): text pairs 4.5:1; icons, dots and large marks 3:1 (warning only). Touch targets: buttons are at least 44 px tall on touch screens whatever the Studio says.

### Admin
The admin uses the components below plus the rules in `10_admin_panel.md` section 3. The admin has its **own** token set, independent of the Studio, so a bad public theme can never make the admin unreadable. On phones and tablets the admin menu is a bottom app bar with **More** (`17_admin_responsive_ui.md`).
- **DataTable / ResponsiveTable:** server-side paging, sortable headers, sticky header, column picker, row click opens a right-hand **Drawer** (480 px; a full-screen sheet below 1025 px). Below 1025 px rows become cards (main field bold, others as labelled chips). Export button shows the row count.
- **StatTile:** label, big number (tabular), delta vs the previous period with an arrow and a word ("up 4%"), optional 14-day sparkline. Never colour alone.
- **Chart:** line for time, bar for categories, funnel as horizontal bars with step drop-off. Max 6 colours from the chart tokens; direct labels; a data table toggle for screen readers. Revenue is one chart per currency.
- **FilterBar:** date range presets (today, 7, 30, 90 days, custom), segment chips, search. State in the URL.
- **RoleBadge / StatusBadge:** owner, admin, support, analyst, user; free, paid, trial, comp, past due, canceled. Text plus a tint, never colour alone.
- **ConfirmDialog:** normal (Confirm / Cancel), reason (required text), danger (type the word). Focus goes to the field; Esc cancels.
- **KeyField:** shows "•••• 3456", Replace, Test, Remove. Never fills the real key back into an input.
- **Toast / Alert:** success auto-hides in 4 s; errors stay and show the request id.
- **Empty / loading / error** states as in the list above on every screen.

Same system, `compact` density. Left menu, table-first screens, a sticky save bar ("Unsaved changes" / Save / Discard) on every settings form, a diff dialog before saving, a red "danger" button style only for destructive actions with a type-to-confirm dialog.

## 8. Copy style

Short sentences. Plain words. Active voice. Numbers as digits. No exclamation marks. No emoji in the interface.

| Do | Don't |
|---|---|
| "Likely to take 2 or more shots." | "Sure thing of the day!" |
| "The opponent plays a low block, which lifts corners." | "Value pick" |
| "No data" | "0" |
| "Predicted lineup" | "Lineup" (when not confirmed) |

## 9. Page titles and SEO

Page `<title>` uses `seo.title_template`. One `<h1>` per page. Meta description uses `seo.description_template`. Open Graph image: team crests on the brand background (optional, later).
