# O-01 `ForecastSheet` × P-13 Player — one spine, two sizes

**Brief:** *"in insights when click on the player it shows up like this — this must look and feel
like the player page of sorts."*

**Date:** 2026-11-06. **Branch:** `v4-teams-and-sheet`. **Method:** both surfaces driven in
Chromium at 390×844 and 1440×900, light and dark, against a demo server I started myself on
`:8031` (port 8011 was being restarted by a parallel job). Every number below is measured off the
running build, not read off the source. Scripts and captures are in the scratchpad, not the repo.

---

## 1. Recommendation — (a), with one amendment

**Build (a): the sheet becomes a compact edition of the player page. One head, one answer, one
run, one ladder, in the same order, rendered at two sizes. The page adds only what cannot fit in a
panel.**

**And the amendment the previous audit will not like: the player page moves to that same order
too.** This is not "make the sheet look like the page". The page does not currently deserve to be
copied. It is "give both surfaces one spine and render it at two sizes".

### Why (a)

The sheet and the page are not two products that drifted. They are **the same content already**,
drawn in two graphic languages. Measured on Player 704, the same fixture, the same minute:

| Material | Sheet | Page |
|---|---|---|
| Who, club, position, next fixture | `k-fs-head`, 52px square avatar, name as a 15px link | `v2-ph2`, 84px round portrait, display-axis `<h1>`, chips, fixture block |
| One headline percentage | yes, y=8 | yes, y=982 |
| Reasons | yes | inside the card |
| Ten games, same values, same minutes | `GameStrip` | `GameStrip` **and** `CardRun`, 550px apart |
| The ladder of other lines | "All lines", y=1101 | hidden behind `+4 more lines` in a card footer |
| Track record on this tier | yes | **absent** |
| Season ranks, history table, note | absent / partial | yes |

The overlap is near total. The divergence is entirely in **presentation**. That is exactly what the
owner is reporting, and it is a consistency defect, not an information-architecture one.

### Why not (b) — "keep the sheet for the one line, move everything player-shaped to the page"

This is what the v3 audit argued and what the source comment in `ForecastSheet.jsx` already asserts
("the sheet is the player page for most readers… everything else lives on the player page"). I
disagree, for three measured reasons.

1. **(b) fixes length, not likeness.** The owner did not say the sheet is too long. Under (b) the
   sheet still opens with a 52px rounded-rect avatar and a 15px link where the page opens with an
   84px round portrait and a display-weight name. It would be a shorter panel that still looks
   like a different product.
2. **(b) sends readers to a worse screen.** Making the page the destination is only sound if the
   destination answers first. It does not: the engine's headline percentage sits at **y=982, 1.16
   phone screens down**, behind a 570px control panel, and the first number the reader meets on
   the page (y=429, `95%`) is for a *different line* than the card below it (`84%`). Promoting the
   page before fixing it moves the problem rather than solving it.
3. **(b) costs the one thing the embedded `QuickView` bought.** On Insights the reader has a day,
   a say-sentence of filters, a tier filter and a `showN` pager in play. Sending them to a route on
   every "what about 2+, or only at home" discards all of it. The sheet exists to let a reader
   interrogate one card without losing twenty.

The audit's underlying instinct — *the sheet has grown into a page* — is right as an observation
and wrong as a diagnosis. A panel that is 2.3 screenfuls of a player's night is not a fault. A
panel that teaches a second graphic language for a claim the reader has already read once is.

### Why not (c) — "replace the sheet with navigation"

(c) is the cheapest consistency fix and buys the three things the sheet can never have: a URL, a
back button, a shareable state. Rejected anyway, on two hard grounds:

- **It destroys feed state.** See (b)(3). Insights, Finder and Combos are all filtered feeds.
- **A third of the panel's openings have no player page to navigate to.** The same component opens
  for team lines (`scope: "team"`) and for match stats (`stat: "match_*"`). On the demo set,
  insight #93 of ~100 is a team corners line. (c) would need `/team/:id` and `/match/:id` as the
  destinations, which are different screens with different anchors — i.e. three navigation targets
  where today there is one panel. That is more divergence, not less.

### What (a) loses — stated plainly

1. **The sheet does not get much shorter.** Removing the duplicates (the repeated title, the "If
   he plays" tile, the `QuickView` forecast line, the second window sentence) and collapsing the
   filter console takes the body from **1397px to roughly 980px** — about a 30% cut. It is still a
   panel you scroll. Accepted: scrolling is not the complaint.
2. **Still no URL, no back, no share target.** Mitigated, not solved: "Open his page" becomes the
   footer's primary action and the page is the shareable twin. If the owner later wants the sheet
   addressable, `?line=<fkey>` on the host route is the cheap version and is out of scope here.
3. **One deliberate divergence remains.** The `QuickView` filter grid is open on the page and
   closed behind one control in the sheet. The page can afford 190px of controls; a panel capped at
   88vh cannot. This is the only block that is allowed to differ, and it differs in *disclosure
   state*, not in shape.

---

## 2. What I measured

### O-01 ForecastSheet — Player 704, "2+ shots", Insights → card → sheet, 390×844 dark

| Measure | Value |
|---|---|
| Panel height | 743px (capped at 88vh) — head 44, body 606, footer 57 |
| Body scroll height | **1397px = 2.31 body screenfuls**; 1.77 phone screens if unclipped |
| Depth of the answer | **0px.** The headline is in the first block. The sheet gets this right. |
| `QuickView` block | 497px = **36% of the panel's content**; its filter console alone 190px |
| The headline number `84%` | **4 occurrences**: head; "If he plays"; `QuickView`'s forecast line; "All lines" row 1 |
| The subject's name | 3 occurrences: sheet title, head link, "Open Player 704's page" |
| The window | stated twice and disagreeing in appearance: *"2 or more in 8 of 10 games"* (y=510) vs *"Reached this line in 17 of his last 20 games"* (y=1045) |
| The player's best line | 1+ shot at 95%, at y≈1140 — below two screenfuls |
| "Open his page" link | y=983, mid-panel, between the filter grid and two grey sentences |
| Desktop 1440×900 | panel 560px wide, body 976px, two-thirds of the viewport empty |
| Focus trap | **trapped.** 40+ Tab presses stayed inside. The v3 audit's #2 has landed. Do not undo it. |
| Horizontal scroll | none, both themes, both widths |

Block offsets inside the body, in order: head 8 (104h) · range note 130 (36) · Why 184 (96) ·
tiles 298 (152) · QuickView 468 (497) · page link 983 (44) · context sentences 1045 (38) ·
All lines 1101 (229) · disclaimer 1349 (36).

### P-13 Player — same player, 390×844 dark

| Measure | Value |
|---|---|
| Page height | **2627px = 3.11 phone screens** |
| Head `v2-ph2` | y 81→322 (241px) |
| Quick view card | y 342→912 (570px); its filter console 190px |
| "What we expect next match" | y 928→1371 (443px) |
| Depth of the answer | **y=982 = 1.16 screens.** The engine's headline is below the fold. |
| First number on the page | `95%` at y=429 — `QuickView`'s resolution of the *default* line (1+), not the card's line (2+ at 84%). Two percentages for one player, 550px apart, nothing says they answer different questions. |
| Same ten games, twice | `GameStrip` y≈520–790 and `CardRun` y≈1150–1290. Identical values (5 3 3 4 0 2 3 1 2 2) and identical minutes (88 75 84 88 63 87 77 68 68 78). |
| `95%` on the page | twice: the QuickView line, and `+4 more lines up to 95%` in the card footer |
| Ladder of all lines | none — buried behind a disclosure |
| Track record | none |
| Ranks | 3 tiles in a 2-column grid: one orphan |

### Two faults found in the render that the briefing did not list

1. **The crest wash on the player head has never worked.** `Player.jsx:111` tests
   `team?.image_url`; `queries.attach_images` (`backend/queries.py:39`) pops `image_url` and
   re-emits it as **`image`**. `team.image_url` is therefore always undefined and `v2-phead-wash`
   is permanently `.is-plain`. The signature treatment of the head described in the brief has
   never rendered a crest.
2. **`QuickView` no longer blanks to `Loading` on a control tap.** Measured 60ms after tapping
   `3+`: the strip is still in the DOM, no loading view, block height unchanged (497→505px).
   `useApi` keeps `data` across a key change (`setState(s => ({...s, loading: true}))`) and
   `QuickView`'s guard is `q.loading && !q.data`. The "blanks on every tap" item in the brief is
   **stale** — the only blank is first mount. Do not spend a change on it.

### Team variant — "4+ corners", Team 8

| Measure | Value |
|---|---|
| Body scroll height | 707px = 1.17 body screenfuls |
| Head | 58px: a bare crest placeholder and the fixture string. **The club is never named in the head and never links to `/team/:id`.** |
| Copy | renders **"A player like him in a fixture like this: usually 80%."** on a *club* line. `f.p_usual != null` is not gated on `scope`. |
| `GameStrip` rule | drawn **below the crest row** instead of through the bars. `.pgs-g` is `grid-template-rows: auto auto var(--bar-h) var(--foot-h)`; team rows carry no minutes so `anyMins` is false, the minutes `<span>` is not rendered, every child shifts up one row and `--foot-h` no longer describes the footer. |
| Screen-reader text | `"Against Team 5: 7 4+ corners"` — `GameStrip` composes `label` into the unit slot. |
| "All lines" | present, and shows 2+ corners at **91%** above the opened 85%. |

### Locked variant

`LockSheet` body is 186px: a tagline, three plan bullets, a trial line. It never names what the
reader just reached for, shows no sample of it, and never says what the free tier keeps. It shares
`BottomSheet` with O-01 and nothing else — no subject, no head, no shape in common.

---

## 3. The spine — block-by-block

One order, both surfaces. Sheet column = where it sits in `k-sheet-body`. Page column = where it
sits in `[data-testid="player-page"]`.

| # | Block | Component | Sheet | Page |
|---|---|---|---|---|
| 1 | Subject head | **`SubjectHead`** (new, shared) | 1st, `size="sheet"` | 1st, `size="page"` |
| 2 | The answer | **`AnswerBlock`** (new, shared) | 2nd | 2nd |
| 3 | Why | **`WhyList`** (new, shared; markup lifted from `k-fs-why`) | 3rd | 3rd |
| 4 | The run + the tool | `QuickView` (existing, two new props) | 4th, filters closed | 4th, filters open |
| 5 | The ladder | **`LadderList`** (new, shared; markup lifted from `k-fc-lines`) | 5th | 5th |
| 6 | Our record on this tier | **`RecordLine`** (new, shared; lifted from `k-fs-record`) | 6th | 6th |
| 7 | Disclaimer + "How to read this" | existing `<p class="k-faint k-small">` | 7th | 7th |
| 8 | Season ranks | `Ranks` (existing, page-local) | — | 8th |
| 9 | Your note | `Note` (existing, page-local) | footer control only | 9th |
| 10 | Actions | footer / head | `k-sheet-foot` | head + card |

### 1. `SubjectHead`

**What it shows.** Portrait · name · club · position · next fixture · (page) Follow.

**Sheet (`size="sheet"`).**
- `PlayerAvatar size={56}` round, or `Crest size={56}` when there is no player.
- The name as the panel's `<h2>` at the display end of the variable axis — the same
  `font-variation-settings` as `.v2-ph2-name`, stepped down to 24px. **This name becomes
  `BottomSheet`'s visible title**, so the duplicated `k-sheet-head h2` string ("Player 704 · 2+
  shots", repeated 40px above the same name) is replaced, not merely hidden. `BottomSheet` keeps
  `aria-label={title}` for the dialog; the head's `<h2>` carries the readable name.
  *Reason: measured, the subject's name appears three times in one panel; one of them is a title
  bar that says nothing the next 40px do not.*
- Metadata row: club chip (`.v2-club`, links `/team/:id`) + position chip (`.v2-pos`). Same chips
  as the page, one size down — the existing `.v2-fs-who .v2-club` / `.v2-pos` rules already do
  this; keep them.
- Fixture line: the Home/Away pill (`.v2-nextfx-at`), both club names, kick-off time. Not a link
  in the sheet — it is a modal; a link out would strand the reader. *Page keeps it as a link to
  `/match/:id`.*
- Crest wash behind, at the sheet's lower opacity. **Read `team.image`, not `team.image_url`.**
- No Follow in the sheet head. It is a commitment control and belongs with the other actions.

**Page (`size="page"`).** Exactly today's `v2-ph2`, unchanged in look, with four fixes:
- `team.image` for the wash (see §2 fault 1).
- Drop `text-transform: uppercase` from `.v2-ph2-name`. *Reason: correct for "PLAYER 405", wrong
  for "RASMUS HØJLUND", and applied on no other entity page.*
- The next-fixture block must not orphan the "v": give `.v2-nextfx` `flex-wrap: wrap` with the
  two `.v2-nextfx-t` spans and the `v` in one non-wrapping group. *Measured: at 390px the "v"
  lands at the far right of the home club's line.*
- `FollowButton` stays in the head.

**Degrades.**
- No player (`scope: "team"`): portrait slot renders `Crest team={fx.team} size={56}`; the **name
  is the club name**, linking `/team/:id`; no position chip. *This is the single largest fix in the
  team case — today a club line opens a panel that never names the club.*
- No position (`f.pos == null`): chip omitted, not rendered empty.
- Match-stat line (`stat` starts `match_`): portrait slot renders the two crests side by side (the
  `k-fc-crests` treatment `ForecastCard.Who` already has); the name is `"{Home} v {Away}"`; no club
  chip, no position chip.
- No fixture (`f.kickoff == null` and no team/opp): fixture line omitted entirely.

**Team-case assumptions** (another agent owns the team surfaces): I assume `/team/:id` gains a head
of this shape, and that `SubjectHead` is the component they adopt. I am specifying the player and
degrade paths only; if the team head needs a form chip or a league chip, it is an extra slot in
this component, not a second component.

### 2. `AnswerBlock` — the one claim, stated once

Replaces, in the sheet: the `k-fc-pwrap` percentage inside `k-fs-head`, the whole `k-fs-tiles`
grid, and the standalone range-explainer paragraph. Replaces, on the page: the headline portion of
the `ForecastCard` that currently carries it.

Layout, one block:

```
2+ shots                                    ●●○ Solid
84%   74 to 88
Usual 75%  ·  +9
Confirmed starter
```

- **Market** as the label, top-left. **`TierBadge`** top-right. *Reason: the sheet never stated the
  tier and then quoted "our record on Solid forecasts" — the record sentence had no referent.*
- **The percentage** as the display number (same scale as `.k-fc-p`), with the range beside it.
  The explainer sentence ("That range is how sure we are…") becomes the `title`/`aria-describedby`
  of the range and a one-line `<small>` only on the page. *Reason: measured 36px of permanent grey
  prose in a 606px panel to explain a bracket the reader sees twenty times a day.*
- **One comparison**: `Usual {pct(p_usual)}` and the signed departure `+9`. **Drop "his average
  2.6"** from this row and move it to the page's `Ranks` block. *Reason: measured, three
  comparisons at one weight in near-identical type, and one of them is a count while the other two
  are likelihoods. One count beside two likelihoods is why none of the three reads.*
- **Lineup state**, one line, from `f.lineup_badge`. The *only* place "chance he plays" appears,
  and **only when `p_play < 1`**: `"Likely lineup · he plays 78% of the time"`.
  *Reason: measured, "Chance he plays 100%" next to "If he plays 84%" is a tautology beside a
  restatement of the number 40px above. On this demo set `p_play` is 1.0 for every player line.*
- `--tone` on the block from the tier, as `k-fs-head` already does.

**Degrades.** `scope: "team"` → no lineup line, no "he plays". `p_usual == null` → no comparison
row (the block is then market + number + range + tier). `f.p_display` set (ladder answers) → no
range, no comparison.

**Number audit for this block.** The headline percentage appears here and once more, in block 5,
as its own row in the ladder. That is the only repeat in the design, and it is justified: the
ladder's job is comparison and a comparison with a hole in it cannot be read. The row is marked
`aria-current="true"` with a visual dot so it reads as "you are here", not as a second claim.
Every other number appears exactly once: `p_usual` here, the run count in block 4's caption, the
window as block 4's tag, the record in block 6.

### 3. `WhyList`

`f.reasons`, capped at two, as `<ul class="k-fs-why">`. Identical on both surfaces. On the page it
moves out of the card and becomes a sibling of the answer. No heading on the sheet ("Why" as a
`.k-sec` is fine on the page where it sits among other sections; in a 606px panel it is a 96px
block of which 30px is a one-word heading).

*Reason to keep it at all: it is the register the product wants and the one thing a counting tool
cannot produce.*

### 4. The run + the tool — `QuickView`

**One run graphic per surface, and the two must agree.**

- `GameStrip` is the reading-size run. It stays inside `QuickView` and is the **only** full-size
  run on either surface.
- `CardRun` stays on feed cards (Insights, Today, Finder, Combos, Match) — it is the glanceable
  one and the feed needs a 160px object.
- **`CardRun` is not rendered on P-13.** The page's own card is being replaced by blocks 1–6; there
  is no card left to carry it. *Reason: measured, the identical ten games and identical minutes
  drawn twice, 550px apart, in two idioms.*
- To stop the two from ever disagreeing again, extract the arithmetic (normalise rows → `{v, m,
  opp}`, compute `known`, `hits`, `vmax`, `need`, `rule`) into **`useRun(games, stat, line)`** and
  have both `GameStrip` and `CardRun` consume it. *Reason: the component comment already asserts
  "the two must agree"; today nothing enforces it and they compute `hits` from different inputs.*

**Inside the sheet.** `QuickView` with `collapsible` and a new `defaultOpen={false}`:
summary → strip → one control, `"Change the line or filters"`. Saves the 190px console.
**Delete the `v2-qv-fc` forecast line when the sheet supplies the answer above** — new prop
`showForecast={false}`. *Reason: measured, that line is the third of four printings of `84%`, and
it sits 460px below the first.*

**On the page.** `QuickView` with filters open, `showForecast={false}` (block 2 is now above it),
`title="Check another line"`. *Reason: the heading "Quick view" names the widget, not the question;
the block is a tool and should say what it is for.*

**One window, once.** The caption is the only statement of the window and the run:
`"Last 10 · 8 of 10 reached 2+"`. **Delete the `rec_k of rec_n` sentence from the sheet.**
*Reason: measured, "2 or more in 8 of 10 games" and "Reached this line in 17 of his last 20 games"
are both true over different windows and nothing said so; the reader reads it as the panel
contradicting itself.* If the season figure is wanted it belongs in block 6 beside the record,
labelled "this season".

**Line options.** Cap the segmented row at five rungs and overflow the rest into the stat select, or
make it a stepper. *Measured: six rungs edge to edge at 390px, ~52px targets, and a mis-tap
re-fetches.*

### 5. `LadderList` — "All lines"

Promoted from 8th to 5th, directly under the run, on both surfaces. On the page it **replaces** the
`+N more lines` disclosure. On the sheet it replaces the current bottom-of-panel section.

- One row per line: market · percentage · range. The opened line is marked, first, with
  `aria-current="true"`.
- Rows ordered by the ladder, not by likelihood, so the reader can see the shape of the night
  (1+ 95%, 2+ 84%, 3+ 64% reads as a curve; sorted by `p` it reads as a leaderboard).
- Markup is the existing `<ul class="k-fc-lines">` lifted out of both `ForecastCard` and
  `ForecastSheet`, where it is duplicated today.

*Reason for the promotion: measured, the sheet opened on 2+ shots at 84% while the player's best
line (1+ shot, 95%) sat at y≈1140, below two screenfuls. The reader's actual next question — "is
there a better line for this player?" — was answered eighth.*

### 6. `RecordLine`

The tier track-record sentence, on **both** surfaces (today sheet-only). Shown only when
`record.ready && tier.n > 0`.

*Reason: it is the product's thesis rendered — a claim that can be checked — and the page, which
has the most room of any surface, does not show it.*

### 7. Footer / actions

**Sheet `k-sheet-foot`**, left to right:
`SaveButton` (star, with a visible label) · `NoteBox` (unchanged, keeps `ui-fsheet-note*` testids) ·
Share (icon-only, `aria-label="Share"`) · **"Open his page" as `btn btn--primary`, right-aligned.**

- *Reason for the primary: measured, the link sat at y=983 mid-panel between the filter grid and
  two grey sentences, and the footer had three equal-weight controls and no primary.*
- *Reason for keeping `NoteBox` in the panel despite preferring to move it: removing it would
  remove `data-testid` values, which the constraints forbid. Share loses its label instead.*
- Label the star. *Measured: it is an unlabelled icon with no text.*
- For a team line the link reads **"Open the club's page"** → `/team/:id`; for a match stat,
  **"Open the match"** → `/match/:id`. Never a dead footer.

**Page.** `FollowButton` in the head, `SaveButton` beside the answer, Share from the site header.
No change beyond not duplicating the sheet's footer.

### 8. Scrim

`.k-scrim` is a literal `rgba(5,8,15,.5)` with no blur, identical in both themes. Measured on the
1440 capture: the Insights card *behind* the sheet, showing the same run, reads clearly through the
panel. Replace the literal with `var(--scrim)` — a new token with a per-mode value — and add
`backdrop-filter: blur(6px)` behind a `@supports`. *Reason: constraint 2 forbids literal hex/rgba
in a component, and a reader comparing the panel to the card bleeding through it is the clearest
possible demonstration that the two disagree.*

---

## 4. Components — reuse, extract, new

### Reused unchanged

| Component | Where | Note |
|---|---|---|
| `BottomSheet` | `ui/BottomSheet.jsx` | Keeps `useFocusTrap`. **Verified trapped at 40+ Tab presses — do not undo.** |
| `TierBadge` | `ui/Marks.jsx` | Now used in `AnswerBlock` on both surfaces |
| `GameStrip` | `ui/Marks.jsx` | One rendering-size run, both surfaces |
| `CardRun` | `ui/Marks.jsx` | Feed cards only; not on P-13 |
| `Crest`, `PlayerAvatar` | `components/Media.jsx` | `team.image`, never `image_url` |
| `SaveButton`, `FollowButton` | `components/Actions.jsx` | |
| `Skeleton`, `EmptyState`, `ErrorState` | `ui/StateViews.jsx` | See §5 |
| `Loading`, `Empty`, `ErrorBox` | `components/States.jsx` | Used inside `QuickView` |
| `ForecastCard` | `ui/ForecastCard.jsx` | Feed surfaces only. Keeps its own `k-fc-lines` disclosure. |
| `Ranks`, `Note` | `pages/Player.jsx` | Page-local, unchanged; `Ranks` gains the per-90 average moved out of the comparison row and a four-tile layout |

### Changed

| Component | Change | Reason |
|---|---|---|
| `QuickView` | New props `defaultOpen` (bool) and `showForecast` (bool, default true). Retitle on the page. Cap the line row at five rungs. | Sheet needs filters closed; both surfaces need the forecast line suppressed once `AnswerBlock` states it |
| `GameStrip` | Always render the minutes `<span>`, empty when `!anyMins`; fix the `label` composition in the SR text (`"7 corners"`, not `"7 4+ corners"`) | The team strip's line rule renders below the crest row because the 4-row grid loses a row (§2) |
| `BottomSheet` | Allow `title` to be screen-reader-only when a `headed` prop is set, so `SubjectHead`'s `<h2>` is the visible title | Kills the duplicated title string without removing the `aria-label` |
| `.k-scrim` | `var(--scrim)` + blur | §3.8 |
| `.v2-ph2-name` | drop `text-transform: uppercase` | §3.1 |
| `Player.jsx` head | `team.image` | §2 fault 1 |

### New shared — one file, `frontend/src/components/ui/Subject.jsx`

| Export | Lifted from | Props |
|---|---|---|
| `SubjectHead` | `pages/Player.jsx` `v2-ph2` header + `ui/ForecastSheet.jsx` `k-fs-head` | `{ player, team, pos, fixture, size: "page" \| "sheet", action, testid }` |
| `AnswerBlock` | new; absorbs `k-fc-pwrap`, `k-fs-tiles`, `v2-cmp` | `{ f, size, testid }` |
| `WhyList` | `ui/ForecastSheet.jsx` `k-fs-why` | `{ reasons, max = 2, heading, testid }` |
| `LadderList` | `ui/ForecastCard.jsx` + `ui/ForecastSheet.jsx` `k-fc-lines` (duplicated today) | `{ lines, current, testid }` |
| `RecordLine` | `ui/ForecastSheet.jsx` `k-fs-record` | `{ record, tier, scope, stat, testid }` |

And `frontend/src/components/ui/useRun.js` exporting `useRun(games, stat, line)` — the shared
arithmetic for `GameStrip` and `CardRun`.

**All new classes are additions** (`v2-sh-*` for `SubjectHead`, `v2-ans-*` for `AnswerBlock`).
No existing class or `data-testid` is renamed or removed anywhere in this spec. New testids:
`ui-subject-head`, `ui-answer`, `ui-ladder`, `ui-record`.

### Not extracted, deliberately

`ForecastCard` is **not** refactored onto this spine. It is a 160px object in a grid of twenty and
its job is ranking, not answering. Forcing it to share `AnswerBlock` would either bloat the card or
starve the answer. The contract between them is the `useRun` helper and the tokens, nothing more.

---

## 5. States

### Loading

| Surface | Today | Spec |
|---|---|---|
| Sheet, blocks 1–3, 5 | instant — `f` is handed in by the card | unchanged; **never show a skeleton for material you already hold** |
| Sheet, block 4 | `Loading` on first mount only (verified; the "blanks on every tap" report is stale) | keep the strip mounted across refetches; add `aria-busy="true"` on `.qv` while `q.loading` |
| Sheet, block 6 | silent until `/track-record` resolves | unchanged — a record that is not ready should say nothing, not reserve space |
| Page | `<Loading rows={5} />` for the whole page | replace with `Skeleton` shaped to the spine: head bar, answer bar, three rows. *Reason: a five-row generic skeleton gives no sense of what is arriving.* |

### Empty

| Case | Spec |
|---|---|
| No reasons | `WhyList` returns `null`. Already correct. |
| No run (fewer than 3 known games) | `QuickView`'s `Empty icon="activity"` — "No games match these filters." Keep. Add, when `started` or `venue` is narrowing: "Try All venues or a longer window." *Reason: an empty state that caused itself should say how to undo itself.* |
| No other lines | `LadderList` returns `null`. The answer block already carries the only line. |
| No forecast for the chosen market | `v2-qv-fc--none` already handles this and is right. With `showForecast={false}` this disappears; re-enable the *absence* line only (`"No forecast for tackles next match"`) so switching to an unmodelled market still reads as absence, not breakage. |
| No next match (page) | Head renders without the fixture block; blocks 2–6 replaced by one `EmptyState`: "No upcoming match for {name} yet." Keeps the head, which is the page's identity. |
| Record not ready | block 6 absent. |

### Error

| Case | Spec |
|---|---|
| History fetch fails | `QuickView`'s `ErrorBox` with `onRetry`. Already correct; it replaces only block 4, so the answer survives a failed run. |
| `/track-record` fails | silent (`.catch(() => {})`). Correct — a missing record is not an error the reader can act on. |
| `/players/:id` fails (page) | `ErrorBox` with retry, full page. Unchanged. |
| The sheet cannot fail as a whole | it holds no required fetch. Keep it that way: **never add a blocking fetch to `ForecastSheet`**. Everything it needs arrives in `f`. |

### Team variant (`scope !== "player"`)

Assumptions stated, since the team surfaces are being designed in parallel:

- **Assumed:** `/team/:id` adopts `SubjectHead` at `size="page"` and gains forecast cards, so the
  sheet's "Open the club's page" lands somewhere worth landing. If it does not, the footer primary
  for a team line should fall back to "Open the match" → `/match/:id`.
- **Assumed:** team rows continue to carry no `minutes` and no `p_play`.

Degrade rules, all testable:

1. `SubjectHead`: crest in the portrait slot, **club name as the name, linking `/team/:id`**, no
   position chip. Fixes the measured defect that a club line never names the club.
2. `AnswerBlock`: no lineup line, no "chance he plays". Comparison row shows `Usual` and the
   departure only if `p_usual != null`.
3. Block 4: **no `QuickView`** — it is player-history-shaped. Render `GameStrip` directly off
   `/teams/:id/history`, as `useSheetData` already does, with the same caption grammar
   (`"Last 10 · 9 of 10 reached 4+"`). Suppress the whole block when no row carries the stat —
   already correct.
4. **Gate `p_usual`'s sentence on scope.** Today a club line renders *"A player like him in a
   fixture like this: usually 80%."* Under this spec the sentence is gone entirely (the comparison
   is in `AnswerBlock`), which closes the bug; if any prose form survives, it must read
   *"A club like them in a fixture like this: usually 80%."*
5. `NoteBox` is player-only. Already gated on `f.scope === "player"`; keep.
6. Fix the `GameStrip` grid so the line rule lands through the bars on minute-less rows (§4).
7. Match stats (`stat` starts `match_`): two crests, `"{Home} v {Away}"` as the name, no club chip;
   everything else as the team case.

### Locked variant (`LockSheet` / `ProLock`)

Today's panel is 186px of generic plan copy that never names what was reached for. Rebuild it on
the same spine, at the shortest possible length:

1. **`SubjectHead`** at `size="sheet"` for the subject the reader just reached for, when there is
   one. *Reason: the lock currently opens over nothing. A reader who tapped a player should see
   that player at the top of whatever opens.*
2. **`AnswerBlock` with the number withheld**: market, tier badge, and the percentage rendered as a
   redacted block of the same size and weight — not a blur of a real number, an explicit placeholder
   with `aria-label="Part of Pro"`. *Reason: a sample is an invitation; an empty wall is not.
   Rendering a blurred real value would leak it to anyone with devtools.*
3. **One sentence naming the limit that was reached**, from the caller: *"You have read today's 20
   insights."* `ProLock`/`LockSheet` gain a `reached` prop. *Reason: measured — the panel never
   says what triggered it, so "Part of Pro" reads as a wall rather than a boundary.*
4. **What the free tier keeps**, one line: *"20 a day stays free, every day."* *Reason: the panel
   currently reads as a removal.*
5. Then today's `lk-list` bullets and the trial line, unchanged.
6. Footer unchanged: `See {plan} · {price} a month` primary, `Not now` ghost.

Vocabulary check: none of the above uses a banned word. Avoid "unlock" / "locked" in reader copy —
`\block s?\b` does not match them, but the register is wrong for a product that sells analysis.
Use "Part of Pro" and "stays free".

---

## 6. Build order

Each step is shippable on its own and none depends on a later one.

1. **`SubjectHead`** — extract from `v2-ph2`, render in both surfaces, fix `team.image`, drop the
   uppercase, make it the sheet's visible title. *This alone is most of what the owner asked for:
   the panel now opens with the page's own head.*
2. **`AnswerBlock`** — one claim, one comparison, one lineup line. Deletes `k-fs-tiles`, the second
   and third printings of the headline number, and the `his average` third comparison.
3. **`QuickView` `defaultOpen` + `showForecast`, and drop `CardRun` from P-13.** Takes 190px out of
   the panel, removes the fourth printing of the number, and ends the two-idiom run.
4. **Promote `LadderList` to 5th on both surfaces**, replacing the page's `+N more lines`
   disclosure. The reader's second question stops being answered eighth.
5. **Footer primary + `RecordLine` on the page + the scrim token.** Finishes the likeness and gives
   the record sentence a referent.

Then, as a separate pass: the team degrade fixes (§5), `useRun`, and the locked rebuild.
