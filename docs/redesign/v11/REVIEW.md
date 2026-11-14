# v11 — UI/UX review

Reviewed from `fold/*.png` (first viewport, real height), `shots/*.png` where I needed to see
below the fold, and `html/*.html` re-rendered in Chromium at 390×844 and 1440×900. Numbers below
are measured, not estimated: computed styles and bounding boxes come from the rendered DOM,
contrast ratios from composited colour (alpha resolved against the real ancestor stack), and the
surface contrasts in §3.4 from sampling the actual pixels of the capture PNGs.

Scratch scripts: `/tmp/claude-0/-home-user-prediction/2bfe3db5-981d-538c-8ca7-af9e11a3f551/scratchpad/m*.js`.

---

## 0. Two corrections to the brief, before anything else

**0.1 The capture ran with a fine pointer, so every `@media (pointer: coarse)` rule was off.**
`scripts/capture.js:138` creates the context as `newContext({ viewport, deviceScaleFactor: 2 })` —
no `hasTouch`, no `isMobile`. Chromium therefore matched `(pointer: fine)` and `(hover: hover)`.
The stylesheet has a coarse-pointer block that exists precisely to fix touch targets:

| selector | captured (fine pointer) | real phone (`pointer: coarse`) |
|---|---|---|
| `a.btn--sm` Sign in / Sign up | 72×**36** | 72×**44** |
| `.k-chip` (match filters) | 76×**40** | 76×**44** |
| `.k-seg button` (By team / By market, Upcoming / Results, Cards / List) | 67×**32** | 67×**44** |
| `.k-link` ("See all 72") | 93×**36** | 93×**44** |

Two of the four items the brief lists as "REAL misses" are therefore artefacts of the harness, not
design faults. Re-run `capture.js` with `hasTouch: true, isMobile: true` and `inventory.json`'s
`smallTapTargets` count drops sharply on every screen.

**0.2 `.lk-tk` / `.lk-mkt` are not misses either — they carry their own 44px hit area.**
Top level, not inside any media query:

```css
.lk-mkt::after, .lk-tk::after { content:""; position:absolute; height:44px; left:-6px; right:-6px; top:50%; transform:translateY(-50%); }
```

Verified by hit test, not by reading: the visual box is 38×33, `position: relative`, the pseudo is
`pointer-events: auto`, and `document.elementFromPoint` returns the button from −21px to +18px
around its centre — i.e. ≈43×50 of live target. The remaining 1–2px at the bottom edge is taken by
the next row's own overlay, which is a stacking nit, not a missed target.

So the genuinely small targets are a different, shorter list — §3.1.

---

## 1. First-impression failures

Ordered by how much damage the first second does.

### 1.1 `waitlist.phone` / `waitlist.desk` — the acquisition page renders `undefined` and `NaN%`

`fold/waitlist.phone.png`, just below the headline, inside the stat card:

> **0** forecasts scored and published · **undefined** of them at **NaN%** or higher ·
> **NaN%** between what we said and what happened, at **NaN%+**

Four broken values in the first viewport of the one page whose only job is to convert a cold
visitor. Present in both viewports; confirmed in the DOM (`grep -c NaN waitlist.phone.html` → 4
text nodes), and present on no other screen.

This is **not** a demo-data artefact. It is a missing divide-by-zero guard, and the product already
has the correct pattern for exactly this state: `track-record.phone` shows *"Collecting results —
We show the record once 300 forecasts have been scored… 0 so far."* The waitlist page needed the
same guard and did not get it.

### 1.2 The consent banner takes 21% of the usable phone viewport on 33 of 38 screens

Measured: `.cookie` is `position: fixed`, `z-index: 70`, **150px tall**, top edge at y=643 of an
844px viewport. Usable band on phone = 844 − 57 (sticky header) − 64 (fixed tab bar) = **723px**,
so the banner eats **20.7%** of it. Its background is `color(srgb 1 1 1 / 0.88)` — 12% of the
content behind bleeds through, so neither layer reads cleanly (visible as ghosted text in every
fold image).

What it covers is the point. On `today`, `live`, `combos`, `insights`, `match`, `player` and
`league` it sits on live forecast rows (`a.lk-name "Player 701"`, `span.lk-claim`, `td.lk-cell-run`,
`tr`) — the product's core object. On `likely` it covers the standard disclaimer line. On
`pricing`, `teams`, `leagues`, `track-record`, `welcome` and the nine admin/404 screens it only
covers the newsletter block and footer, which is harmless.

Present on 33 phone pages; absent on the five auth pages (`sign-in`, `sign-up`, `account`,
`forgot-password`, `waitlist`).

### 1.3 Twelve of the 38 screens are another screen

Byte-identical fold PNGs, identical element counts in `inventory.json`, identical headings:

| route | renders | evidence |
|---|---|---|
| `/live` | the Today page | md5-identical folds, 454 elements each, `h1(sr-only): "Today"`, `h2: "Furthest from usual today"` |
| `/teams` | the Leagues page | md5-identical folds, 94 elements each, `h1: "Leagues"`, `<title>Leagues · Forecast Zone` |
| `/account` | the Sign in page | md5-identical folds, 98 elements each, `h1: "Sign in"` |
| `/admin/*` (9 routes) | the 404 page | md5-identical folds, 84 elements each, no `h1` |

`/live` and `/teams` are reachable from Explore's "The rest of the app" list ("Live scores — What
is happening right now", and the clubs entry). A reader taps a named destination and lands on a
page with a different title and no acknowledgement that they asked for something else. The admin
404 is a defensible posture for a signed-out visitor, but it means nine of the 38 "screens" have no
design to review.

### 1.4 `match.phone` — the first thing in the first viewport is "Follow", above the match itself

`fold/match.phone.png` vs `fold/match.desk.png`, same component, opposite priority. Measured
visual order inside `.mc-hero`:

| | phone (390) | desktop (1440) |
|---|---|---|
| `.mc-actions` (Follow, Share) | **y=90 — first** | y=334 — **last**, bottom-right |
| `.mc-when` (Test League · Round 20 · Sat, Nov 14) | y=142 | y=108 |
| `.mc-row` (Team 0 / 07:00 PM / Team 2) | y=174 | y=140 |

Caused by `@media (max-width: 520px) { .mc-page .mc-hero { padding-top: 60px } .mc-page .mc-foot
.mc-actions { position: absolute; top: 8px; left: 8px; right: 8px } }`. The phone reserves 60px at
the top of the hero to float an account action above the identity of the page. A first-time reader
sees a dark-filled "Follow" pill before they see who is playing.

### 1.5 `today.phone` — the product never says what it is

`fold/today.phone.png`. On phone the wordmark is suppressed (`a.brand` is 22px wide: the ring glyph
only — the "Forecast Zone" text is there for screen readers), the `h1` is `sr-only`, and the first
visible words of the product are the section heading **"Furthest from usual today"**. That phrase
assumes the reader already knows there is a "usual" and that distance from it is the product's
thesis. Compare `today.desk.png`, where the wordmark, the sidebar and a labelled table header row
(FORECAST / LAST 10 / RESULT / CHANCE / GRADE / WHY / LINEUP) do most of that work.

### 1.6 `welcome.phone` — asks before it tells

Step 1 of 3, *"Which leagues do you watch?"*, is the entire first viewport. Nothing above it says
what the thing is or what answering buys. The answer to that is one line further down the page
("We put them first in Explore"), in 15px grey.

### 1.7 `search.phone` — 92% empty

`fold/search.phone.png`: header replaced by the search field, one 15px line of instruction, and
~1500px of nothing. No recent searches, no leagues, no suggested clubs — and no `h1` and no page
title beyond "Search · Forecast Zone". The one blue pixel in the product is here too (§2.5).

### 1.8 `pricing.phone` — the highest-intent page has no action on it

"Plans" → "Paid plans are not open yet — Every signed-in person gets the full plan for now." There
is no button. The only way to act on that sentence is the header's "Sign up free", 600px away at
the top of the screen.

### 1.9 `notfound.phone` — no way back

"404 / We could not find that page." and then the newsletter block. No link home, no search box.
Recovery is the bottom tab bar only. Also: the "404" is an 80px `<p class="big-404">`, so the page
has no `h1` at all.

### 1.10 `likely.phone` — the legend renders when there is nothing to read

The lede says "the likeliest things to happen in the **0 matches** kicking off in the next 4
hours", then a 3-paragraph how-to-read-the-bars legend occupies 340px, and only then the empty
state ("Nothing here reaches 60%"). Teach the chart when there is a chart.

---

## 2. Systemic inconsistency

The 39-font-size figure is partly an illusion and partly real; this section separates the two and
names where a reader actually sees it.

### 2.1 The honest font-size count

41 distinct sizes across the phone pages. Nine of them are *computed fractions of a parent*, not
authored choices:

- 6.84 / 7.56 / 10.08 / 11.76 / 13.44 / 16.8 / 18.24 / 31.92px — all `span.media-fallback`, the
  placeholder avatar initials, sized as an em fraction of the avatar. These go away with real
  images (the brief's caveat #1).
- 18.48px (56 uses) — the `%` in `<span class="lk-figure">84<u>%</u></span>`, i.e. `0.44em` of 42px.

That leaves ~32 authored sizes, and the drift is concentrated in one band:

| job | sizes in use |
|---|---|
| micro-label | 9, 10, 10.5, 11, 11.5 |
| meta / caption | 12, 12.5, 13, 13.26, 13.5 |
| body | 14, 14.5, 15, 15.5, 16, 16.5 |
| section heading | 17, 18, 19, 20, 20.28 |
| page title | 25, 26, 28.56, 29.6, 34 |

Four to five values per step is not a scale. The two that cost the most are **10.5px (197 uses)**
and **12.5px (256 uses)** — the two workhorse meta sizes are both half-pixel values, and both sit
next to a whole-pixel sibling doing the same job (11px, 290 uses; 13px, 178 uses).

### 2.2 Where it hurts: the first viewport of the two most important screens

Counted inside the 844px fold only, excluding the consent banner and the placeholder avatars:

| | font sizes | radii | background colours | gap values |
|---|---|---|---|---|
| `today.phone` | **13** | **8** | 9 | **11** |
| `match.phone` | **15** | 5 | 13 | **13** |

`today.phone`'s eight radii in one screen: 5px (`.lk-ava-cr`), 7px (`.brand-mark`), 10px
(`.k-day`), 12px (`.lk-cell-run`), 16px (`tr`), 50%, 999px, and `2px 2px 0 0` (chart bars). The
tokens `--radius-sm: 8px / --radius-md: 12px / --radius-lg: 16px / --btn-radius: 999px` exist in
`:root` — **none of 5, 7, 10 is one of them.**

### 2.3 The page-title block is spaced differently on every page

Same pattern everywhere — `h1` 28.56px, then a 15px lede — and the measured gap between them:

| gap | screens |
|---|---|
| −4px | contact |
| 0px | learn, leagues, teams |
| 4px | likely, league, referees |
| 6px | player, team |
| 8px | insights, welcome |
| 12px | pricing |
| 14px | sign-in, sign-up, account, forgot-password |
| 16px | finder, terms |
| 18px | compare |
| 20px | track-record |
| 24px | explore |
| 48px | waitlist |

Twelve values for one relationship. Flick Explore → Learn → Insights and the lede jumps 24px, 0px,
8px. The `h1` size itself is 28.56px everywhere except `player`/`team` (29.6px) and `waitlist`
(34px) — a 1px difference nobody can have intended.

### 2.4 One control, four input treatments

| where | height | radius | fill | border | font |
|---|---|---|---|---|---|
| auth forms (sign-in, sign-up, contact, forgot-password) | 48px | **10px** | #FFF | `text3 @24%` | 16px |
| newsletter field (all 37 pages) | 48px | **12px** | #FFF | `text3 @24%` | 16px |
| search/filter (leagues, teams) | **44px** | 12px | **#EBEEEA** | #D3D7D2 | **15px** |
| search/filter (compare) | **44px** | 12px | **#EBEEEA** | **#AAAEA7** | 16px |
| waitlist | **46px** | 10px | #FFF | #AAAEA7 | 16px |

Three heights, two radii, two fills, three border colours. And `explore`'s "Filter leagues" is a
*fifth* treatment — a borderless 26px field inside a bordered wrapper — doing the same job as
`leagues`' "Search leagues", with different wording for the same action.

**The 15px one is a bug, not just drift:** iOS Safari auto-zooms the page when a focused input's
font-size is below 16px. Tapping "Search leagues" on `/leagues` or `/teams` will zoom an iPhone.

### 2.5 Surfaces: five off-whites inside 1.07:1 of each other, and one blue

Sampled from `fold/today.phone.png` directly:

- page `#F4F7F3` → card `#FFFFFF` = **1.08:1**
- card `#FFFFFF` → "LAST 10" chart tray `#F5F8F7` = **1.069:1**
- tray `#F5F8F7` → page `#F4F7F3` = **1.008:1**

`#F4F7F3` and `#FFFFFF` and `#EBEEEA` are tokens (`--bg`, `--surface1`, `--surface2`). `#F5F8F7`
(the chart tray, 54 uses) and `#EFF7F4` (`span.td-ins`, 12 uses) are not. The result is that the
tray inside the card is the same lightness as the page behind the card — it reads as a hole, not a
tray.

Of the 42 background colours: 5 are placeholder avatar tints (pink/lavender/mint — brief caveat
#1), ~10 are alpha variants of white or `#22281E`, and the rest resolve to about 8 real surfaces.
"42" overstates the problem; "two off-token off-whites and three semantically identical trays"
is the actual problem.

**The blue:** `search.phone`'s clear control is the browser's native
`input[type=search]::-webkit-search-cancel-button`. Sampled from the capture, its core pixels are
≈`rgb(46,80,137)`. It is the only blue in the product, it is not in any stylesheet, and it appears
on the one screen that has nothing else on it.

### 2.6 One component, two button languages

`Follow` is the same action with the same label on three screens:

| screen | fill | surface behind | separation |
|---|---|---|---|
| `match.phone` | `#034737` | white card | **10.71:1** |
| `team.phone` | `#034737` | hero gradient `rgb(2,62,48)` | **1.13:1** |
| `player.phone` | `#034737` | hero gradient `rgb(2,61,47)` | **1.15:1** |

(Pixel-sampled from the fold PNGs, not computed from CSS.) On the hero the brand-green fill is
within 1.2:1 of the brand-green background, so the button reads as floating white text.
`Compare with…` on `team.phone` is worse: fill `rgb(7,56,43)` on `rgb(2,60,46)` = **1.05:1**, with
`border-color: transparent`. It is a button with no visible boundary at all.

### 2.7 Two chip families in one row

`insights.phone`, the date strip, side by side in the same flex row:

- `button.k-chip.on` "Any day" — 81×**64**, radius **14px**, top at y=**165**
- `button.k-day` "Today / Tmrw / Mon…" — 43×**70**, radius **10px**, top at y=**162**

6px of height difference, 3px of vertical offset, 4px of radius difference, visible in
`fold/insights.phone.png` as a row that does not line up. `today.phone` uses only the `k-day`
family and is clean.

### 2.8 `team.phone` is on a different component set from `match` and `league`

| control | `match` / `league` | `team` |
|---|---|---|
| section tabs | `.tab` 44–48px | `button.tab` **40px** |
| value / range / filter buttons | `.k-chip` 44px, `.k-seg button` 44px | 20 × `button` at **34px** |

The team page carries its own bank of ~20 controls at 34px (`7+ 8+ 9+ … 14+`, `Last 5/10/20`,
`All/Home/Away`, `Cards/Grid`) that the coarse-pointer block never reaches. Same product, same
viewport, 10px shorter controls.

### 2.9 Fifteen pages have no page name in the title

`<title>Forecast Zone</title>` with nothing else on: `account`, `admin-*` (9), `forgot-password`,
`notfound`, `sign-in`, `sign-up`, `terms`. Everywhere else the pattern is `Insights · Forecast
Zone`. This is what a screen reader announces on load and what a tab or a bookmark shows.
(`compare` has the opposite problem: `<title>Team 0 v Team 2 · Forecast Zone</title>` under an
`h1` that says "Compare".)

---

## 3. Accessibility

Each item verified against the rendered DOM under `hasTouch: true, isMobile: true` — i.e. what a
phone actually computes — and contrast against the composited background, not the declared one.

### 3.1 Tap targets — the real list

After correcting for §0, these are under 44×44 on a real phone. "min" is the smaller dimension of
the effective hit box; WCAG 2.5.8 (AA) needs 24×24, WCAG 2.5.5 (AAA) needs 44×44.

| min | element | box | where | verdict |
|---|---|---|---|---|
| **20px** | `input[type=checkbox]` | 20×20 | compare ("As a fixture"), newsletter consent on 8 pages | **fails 2.5.8 AA** |
| **21px** | `a.v2-sh-fx` "Home · Team 0 v Team 2" | 218×21 | team hero | **fails 2.5.8 AA** |
| **22px** | `a.brand` (home link) | **22**×44 | 37 pages | **fails 2.5.8 AA on width** |
| **22px** | `a.lk-name` "Player 701" | 170×22 | today, live, combos, insights, match, player | **fails 2.5.8 AA** |
| **23px** | `a.team.mrow-club` | 146×23 | league fixture rows | **fails 2.5.8 AA** |
| **23px** | `a.v2-club` "TL Test League" | 108×23 | team, player heroes | **fails 2.5.8 AA** |
| 26px | `button.fs-word` | 26×44 | finder sentence tokens | passes AA, fails AAA |
| 27px | `select` | 95×27 | insights, team | passes AA, fails AAA |
| 31px | `button.linkish` "Privacy choices" | 109×31 | footer, 37 pages | passes AA, fails AAA |
| 34px | `button.k-day--cal` (calendar) | **34**×74 | today, live, insights | passes AA, fails AAA |
| 34px | `button` ×20 (`7+`…`14+`, `Last 5/10/20`, `All/Home/Away`, `Cards/Grid`) | 41–71×34 | team | passes AA, fails AAA |
| 40px | `button.tab` Squad / Stats / Fixtures | 63–83×40 | team | passes AA, fails AAA |

Inline links inside sentences (e.g. "Head to head, last 1 meeting: 1 draw") are excluded — 2.5.8
exempts them — and so is the visually-hidden skip link.

The six AA failures are the ones to fix, and five of the six are the same root cause: a text link
whose line-height sets its height. `a.lk-name` is the one that matters most — it is the player's
name on the primary card, on six screens.

### 3.2 Text size

`inventory.json` flags 28 sub-12px strings on `today.phone` and 40 on `match.phone`. Removing the
placeholder avatar initials (brief caveat #1), the real ones are:

- **`span.lk-evlabel` — "LAST 10 · DID HE REACH IT", 10px / weight 800 / uppercase / 0.7px
  tracking.** 54 instances on `today.phone` alone; present on today, live, combos, insights, match,
  player. Contrast is fine (`#62685F` on `#F5F8F7` = **5.35:1**); the problem is purely size. This
  is the caption that explains the product's signature chart.
- `i.k-day-mon` "Nov" — **9px**, the smallest real text in the product.
- `span.beta` "BETA" — 10px uppercase, on all 37 pages.
- `li.fp` (W/D/L form chips on match) — 10px glyphs in **17×17px** boxes.
- `span.pgs-min` — 10px, and it carries data (minutes played).

### 3.3 Text contrast — one real failure in 38 screens

I walked every text node on all 38 phone pages, composited every alpha layer up the ancestor
chain, and compared. **Exactly one authored failure:**

| screen | element | foreground | background | ratio | needs |
|---|---|---|---|---|---|
| `compare.phone` | `b` "4.35" (15px / 700) | `#1B8962` (`--tier-strong`) | `#FFFFFF` | **4.37:1** | 4.5:1 |

It misses by 0.13. `--tier-strong` is safe as a fill behind white text and safe for text ≥18.66px
bold, but not for 15px body text on white.

Everything else passes, often comfortably: `Solid` tier pill white-on-`#034737` **10.71:1**;
`.k-link` "See all 72" `#3C4238` on `#F4F7F3` **9.59:1**; the disclaimer line `#22281E` on
`#EBEEEA` **12.91:1**; hero white-on-gradient **≈10.7:1**; the `Home`/`Away` badge `#F4F7F3` on
`#22281E` **14.0:1**. This is a well-behaved palette and it deserves saying.

*(Not assessed: the dark theme. `html` is pinned to `data-theme="light"` in every capture and the
theme toggle only exists in the desktop header, so nothing in `v11` shows the dark or
`#22281E` themes that `:root` defines. That is a gap in the capture set, not a finding.)*

### 3.4 Non-text contrast (WCAG 1.4.11) — the systemic one

Component boundaries need 3:1. Measured by sampling the capture pixels:

| boundary | measured | needs |
|---|---|---|
| `.k-day` date chip border `#D3D7D2` vs page `#F4F7F3` | **1.35:1** | 3:1 |
| `.k-day` chip fill `#FFF` vs page `#F4F7F3` | **1.08:1** | — |
| `.k-link` / `.k-chip` border (`--v2-hair` = `text3 @24%`, composites to `#D1D5CF`) vs page | **1.38:1** | 3:1 |
| `Follow` fill vs hero, `team.phone` | **1.13:1** | 3:1 |
| `Follow` fill vs hero, `player.phone` | **1.15:1** | 3:1 |
| `Compare with…` fill vs hero, `team.phone` (border transparent) | **1.05:1** | 3:1 |

For the date strip this is the whole affordance: a white chip on an off-white page, outlined by a
1.35:1 hairline, is the only signal that it is a control. `--border-strong` (`#AAAEA7`) already
exists and would take it to **2.08:1** — a 54% improvement using a token that is already in the
system. True 3:1 needs roughly `#8F948D`, which is a visible change to the settled v10 look; I
would take the `--border-strong` step now and treat `#8F948D` as a decision, not a bug fix.

### 3.5 Focus order and focus visibility

- **Focus rings: 100%.** Every focusable on `today` (62/62), `match` (174/174), `team` (91/91) and
  `finder` (51/51) gets an outline or box-shadow on focus. No exceptions found. Good.
- **The consent banner is last in the tab order on every page it appears on.** It is focusable stop
  **171 of 174** on `match`, **151 of 154** on `insights`, 44/47 on `combos`. It is visually the
  most prominent thing in the first viewport and the last thing a keyboard or switch user can
  reach. It is `role="region"` with no `aria-modal` and no focus management, so nothing pulls focus
  to it either. Visual prominence and sequence point in opposite directions (2.4.3).
- Skip links work: `a.skip href="#main"` and the target exists on 37 of 38 pages. `waitlist` has no
  skip link.
- Every page has exactly one `<main>`.

### 3.6 Heading structure

- **No `h1`:** `search`, `notfound`, and the nine `admin-*` routes (11 screens).
- **`h1` is `sr-only`:** `today`, `live`, `match` — the visible hierarchy starts at `h2`.
- **Level skipped (h1 → h3):** `league` ("Next round referees"), `likely` ("Nothing here reaches
  60%."), `pricing` ("Paid plans are not open yet"), `referees` ("No referee numbers yet").
- **Size inverted on `match.phone`:** four `h2`s render at **10px** ("Match info", "Table", "Worth
  knowing", "Next match") while an `h3` beneath one of them renders at **15px** and the body text
  around them is 15px. A section heading smaller than its own body copy, and smaller than its
  child heading, is not a hierarchy.
- `h2` is 19px on most pages, 17px on `match`/`player`/`team`, 16px on `insights`.

### 3.7 Other

- `input[type=search]` on `leagues` / `teams` is 15px → iOS auto-zoom on focus (§2.4).
- `div.lk-bar` on `likely.phone` scrolls horizontally (`clientWidth 358`, `scrollWidth 431`) with
  no fade, arrow or peek: "Next 24h" is entirely off-screen and "Next 12h" is cut at the viewport
  edge. 17% of the filter row is undiscoverable.
- No image lacks `alt`, no button lacks an accessible name, no JS errors, no horizontal page
  overflow — confirmed, and all four hold under touch emulation too.

---

## 4. Per-screen notes

Phone unless stated. "Fine" means I found nothing worth a reader's time.

**today** — No visible product name and an `sr-only` `h1`; the first words are "Furthest from usual
today". 13 font sizes and 8 radii inside the fold. Chart tray `#F5F8F7` sits at 1.069:1 against its
own card.
**today.desk** — Much stronger: wordmark, sidebar, a labelled table header row. 56px of dead space
between the date strip and the first section heading.
**live** — Pixel-identical to `today` (454 elements, same `h1`, same `h2`). Not a screen.
**insights** — Good lede ("20 lines worth reading across 6 matches"). Date strip mixes two chip
families (64px/14px radius beside 70px/10px, 3px out of line). Token underlines are as wide as the
widest option in each dropdown (226px for "in any run of games"), so the sentence reads ragged.
**likely** — The how-to-read legend renders above an empty state in a 0-match window. Filter row
hides 73px of chips off the right edge with no affordance.
**finder** — The natural-language builder is the best idea in the product. The submit control is
disabled and labelled with the blocker ("Pick a league first", `#62685F` on `#F4F7F3` = 5.31:1, so
legible) while the token that needs attention ("pick a league") looks exactly like the five already
set. Quota ("3 of 3 free searches left today") appears before any value is delivered.
**explore** — Clean. The 24px `h1`→lede gap is the widest in the app (vs 0px on `learn`).
**combos** — Good explanation of what a combo is. The promised "combined chance" is not visible in
the first viewport; two sample cards are.
**compare** — The only `h1` with no lede. Two 240px team cards consume the fold before any
comparison appears. Its search fields are the grey-filled variant; `explore`'s is white. The one
text-contrast failure in the product lives here (4.37:1).
**leagues** — Fine, except the "Search leagues" field is 15px → iOS zoom.
**teams** — Renders the Leagues page: same 94 elements, same `h1` "Leagues", same title.
**referees** — Good honest empty state ("Referee numbers appear once matches with a named referee
and cards are in"). `h1`→`h3` level skip.
**track-record** — Best empty state in the product. The 0-of-300 progress bar has no fill and no
label, so it reads as a skeleton rather than progress.
**search** — No `h1`, no suggestions, no recent searches; ~92% of the viewport is blank. The native
`::-webkit-search-cancel-button` puts the product's only blue here.
**pricing** — No action on the page with the highest intent. `h1`→`h3` level skip.
**learn** — Fine. 0px `h1`→lede gap.
**contact** — Fine; the character counter is a nice touch. `h1` and lede overlap by 4px.
**welcome** — Asks for leagues before saying what the product is; the reason is below the question
in 15px grey.
**waitlist** — `undefined` and `NaN%` ×3 in the first viewport. Also: a second brand mark (square,
rising line) unlike the app's ring glyph, a different `h1` size (34px), a 48px `h1`→lede gap, and
no skip link. On desktop the left hero column is ~60% empty below the stat pill.
**terms** — Fine. Carries the standard disclaimer.
**sign-in / sign-up / forgot-password** — The three cleanest screens in the set. No consent banner
to fight. Titles are bare "Forecast Zone".
**notfound** — No `h1`, no route back, no search; the next thing offered is a newsletter.
**match** — §1.4 (Follow above the scoreline on phone only). Four `h2`s at 10px with a 15px `h3`
beneath them. 15 font sizes and 13 background colours inside the fold. Home and away are encoded as
two shades of the same green either side of a grey draw bar, which is a weak distinction at the
32px bar height.
**match.desk** — Strong. Actions correctly demoted to bottom-right; the table header row does real
explanatory work.
**league** — Clean phone layout; the 3-way bar drops its "Draw" label here but keeps it on `match`.
`h1`→`h3` skip. On desktop each `.mrow-club` cell is 474px wide, so the two clubs sit ~490px apart
with a lone 8px "v" between them.
**team** — Owns a parallel control set: 20 buttons at 34px and tabs at 40px where `match`/`league`
use 44–48px. `Follow` at 1.13:1 and `Compare with…` at 1.05:1 against the hero. Two sub-24px links
in the hero (`a.v2-sh-fx` 21px, `a.v2-club` 23px).
**player** — The best page in the product: the claim, the number, the range, the usual, the delta,
and the reasons, in that order. `Follow` is invisible on the hero (1.15:1). `Away` badge and club
link inherit the hero's target/contrast problems.
**following** — Fine. Honest about needing an account.
**account** — Renders the Sign in page (98 elements, identical fold).
**admin-home, admin-feeds, admin-apifootball, admin-leagues, admin-jobs, admin-engine,
admin-settings, admin-logs, admin-users** — All nine render the 404 page (84 elements each,
byte-identical folds). Reasonable for a signed-out visitor; nothing to review.

---

## 5. The five changes I would make first

### 1. `waitlist` — guard the zero state

- **Screen:** `waitlist.phone` / `waitlist.desk`, the stat card under the headline.
- **Current:** `0` / `undefined` / `NaN%` / `NaN%` / `NaN%+`.
- **Proposed:** when the scored count is 0, render the card the way `track-record` already does —
  one line, no derived numbers: *"No forecasts have been scored yet. We publish the record once 300
  have been."*
- **Why:** it is the only page a cold visitor sees before deciding, and it currently shows four
  broken values above the fold.

### 2. `.cookie` — one row, not five lines

- **Screen:** 33 of 38 phone screens.
- **Current:** `height: 150px` (20.7% of the usable viewport), `background: color(srgb 1 1 1 /
  0.88)`, `display: grid`, text wrapping to 3 lines with the buttons on a 4th; last in the tab
  order on every page.
- **Proposed:** `display: flex; align-items: center; flex-wrap: wrap` so the text and the two
  buttons share one row (≈64px at 390px wide), and let the full-opacity `--surface1` stand (the
  `backdrop-filter` version only applies where `prefers-reduced-transparency` is not set). Move the
  node to immediately after the skip link so its sequence matches its prominence.
- **Why:** it currently covers the first forecast card — the exact object the product wants a new
  reader to look at — on today, live, match, player, combos, insights and league, at 88% opacity so
  neither layer is readable.

### 3. `/teams` and `/live` — stop serving another page

- **Screen:** `teams.phone` (and `.desk`), `live.phone` (and `.desk`).
- **Current:** `/teams` returns the Leagues page (`h1` "Leagues", 94 elements, fold byte-identical
  to `/leagues`); `/live` returns the Today page (`h1` "Today", 454 elements, fold byte-identical
  to `/`).
- **Proposed:** give each its own view, or remove the two entries from Explore's "The rest of the
  app" list until they exist.
- **Why:** two named destinations in the product's own index take the reader somewhere else and do
  not say so.

### 4. `match.phone` hero — put the match first

- **Screen:** `match.phone`, `.mc-hero`.
- **Current:** `@media (max-width: 520px) { .mc-page .mc-hero { padding-top: 60px } .mc-page
  .mc-foot .mc-actions { position: absolute; top: 8px; left: 8px; right: 8px } }` — Follow and
  Share render at y=90, above the competition line (y=142) and the scoreline (y=174).
- **Proposed:** delete both rules. `.mc-actions` then falls back to its place in `.mc-foot`, which
  is where desktop already puts it (y=334, after the win/draw bar and expected goals).
- **Why:** the first element in the first viewport of the most-visited deep page is an account
  action a signed-out reader cannot use, ahead of the identity of the page.

### 5. Hero controls — make the buttons visible

- **Screen:** `team.phone`, `player.phone`, the `.v2-sh` hero.
- **Current:** `Follow` fill `#034737` on hero `rgb(2,62,48)` = **1.13:1**; `Compare with…` fill
  `rgb(34,40,30) @14%` on `rgb(2,60,46)` = **1.05:1** with `border-color: transparent`.
- **Proposed:** on the hero only, invert the primary — fill `--surface1` with `--brand` text (white
  on the dark gradient gives ≈10.7:1 for the fill boundary) — and give the secondary a visible
  `1px solid color(srgb 1 1 1 / 0.45)` outline. Two rules scoped to `.v2-sh .btn`.
- **Why:** WCAG 1.4.11 asks for 3:1 on a control's boundary; these are at 1.05–1.15:1, so the
  primary action on two of the four main entity pages reads as floating text rather than a button.

**Runners-up, in order:** the six sub-24px tap targets in §3.1 (`a.lk-name` first, it is the player
name on six screens); the `h1`→lede spacing token (twelve values for one relationship, §2.3); the
15px search input that zooms iOS (§2.4); `match.phone`'s 10px `h2`s (§3.6); the 10px uppercase
chart caption (§3.2); and re-running `capture.js` with `hasTouch: true` so the next inventory
measures what a phone actually renders (§0.1).
