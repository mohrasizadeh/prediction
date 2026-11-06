# v3 audit — the six core screens

P-01 Today, P-04 Insights, P-05 Finder, P-06 Explore, P-07 Compare, P-08 Combos.

Written by reading `frontend/src/pages/{Today,Insights,Finder,Explore,Compare,Combos}.jsx`,
`frontend/src/components/ui/*`, `frontend/src/styles/{v2,matchday,hig}.css`,
`frontend/src/components/ui/kit.css` and `backend/site_studio.py`, and by **rendering all six at
390×844 and 1440×900 in both schemes against the live demo server** and measuring the DOM. Every
pixel figure below is measured, not estimated. Companion file: `GLOBAL.md` (chrome and IA), which
defers the Insights/Finder merge ruling to §8 of this document.

---

## 0. First, the screenshot set in `../before/` is unusable

`scripts/shots3.js` signs in as the demo owner **once per browser context** and then captures every
screen in that same context, public screens included. The owner account is on a forced password /
2FA journey, so `/` redirects to `/enroll-2fa`. The committed `before/P-01-phone-dark.png` is not
Today — it is the two-factor enrolment form. Every file that run produces will be the same wall.

**Fix (one line, before any further capture):** use two contexts — a signed-out one for `PUBLIC`,
the signed-in one for `ACCOUNT` and `ADMIN` — or clear cookies before the public loop. All renders
cited below were taken signed-out in a clean context.

---

## 1. The ten changes that matter, ranked

“Cheap” = a change inside one file, no API field, no new component, no test-id churn.

| # | Change | Screen | Why | Cost |
|---|---|---|---|---|
| 1 | **Rank Top 3 by `span`, not by likelihood**, and apply the `span ≥ 0.05` gate docs/50 §9.4 already specifies | P-01 | Today's flagship module currently promotes the *least* informative cards in the feed. Measured: the three it chose have edges of **+1.5, +1.0 and +1.9 points** over their own usual, and one has **span 0.018** — below the gate the product's own spec says must never lead a card. `span` and `edge` are already on every `/api/insights` row. | **Cheap** (2 lines in `topRated`) |
| 2 | **Stop the day strip wrapping on a phone** — restore `overflow-x: auto` below 480px | P-01, P-04 | `v2.css:748-749` overrides `kit.css:37` with `flex-wrap: wrap; overflow-x: visible`. On desk the seven days fit one 74px row; on a 390px phone they wrap to three rows. Costs **230px on Today** and **317px on Insights**, and it is why Insights' first card sits at **778px**, below the usable fold (844 − 70px tab bar = 774). v2's headline win (913 → 476) has silently regressed. | **Cheap** (3 lines of CSS) |
| 3 | **Move the fixture list above Top 3 on Today**, or cut Top 3 to one card | P-01 | The day's fixtures — the thing the screen is named for — begin at **1713px**, two full viewports down. Top 3 occupies **1244px**. | **Cheap** (reorder two JSX nodes) |
| 4 | **Name the stat in the history clause on Insights, and disable the clause until a market is chosen** | P-04 | `hStat` silently falls back to `"shots"` when market is "all markets". The sentence reads “…and have had **2+** **in 6 of their last 10**” with no noun, and filters on shots without saying so. The entire case for the sentence (CONSOLIDATION §2) was “no hidden state”. | **Cheap** |
| 5 | **Give Finder a default result** — seed a league and run on load | P-05 | The whole screen is an empty state: a disabled button reading “Pick a league first”, and 170px below it an empty box reading “Pick a league”. The same instruction twice, nothing answered. Compare was fixed this exact way in v2; Finder was not. | Medium |
| 6 | **Redraw Compare's per-game bars as two independent bars on a shared scale**, not a split of one track | P-07 | Today the same mark means the opposite thing on adjacent rows: on “Goals” longer = better, on “Goals against” longer = worse. And “Possession %, 61.85 vs 36.6” is drawn as a 63/37 split of one whole, which looks like a head-to-head possession split and is not one. | Medium |
| 7 | **Show an actual combo on the signed-out Combos page** | P-08 | A page titled “My combos” that promises “we work out the combined chance” and then shows three unrelated single cards. The one thing the feature does is never demonstrated. | Medium |
| 8 | **Raise `.v2-cr-m` and `.v2-cr-o` from 8px to 11px**, or drop the opponent row on phones | P-01, P-04, P-08 | Minutes and opponent are rendered at **8px** (`font-size: .5rem`) under eleven columns in a 358px card. The league fallback chip in the date strip is **5.88px**. Contrast passes AA everywhere; size does not. | **Cheap** |
| 9 | **Merge Finder into Insights as a mode of the sentence, and redirect `/finder`** | P-04, P-05 | Ruling in §8. Finder's `likelihood` mode *is* Insights, by its own code comment. Two of five phone tabs spent on one job. | Large |
| 10 | **Fix the “More filters” badge to count only what is in the sheet** | P-04 | `nAll` counts market, player, club and the history clause — all of which are visible in the sentence — and excludes the day. The badge therefore says “4” about filters the reader can already see, and says nothing about the six that are hidden. This is the exact fault v2 claimed to have removed, inverted. | **Cheap** |

Also cheap and worth doing, below the top ten: delete the `td-time` overflow (`70 > 64px`,
measured) by dropping “in 10h 43m”; remove Explore's five footer-duplicate links; give Combos'
`ErrorState` a written sentence instead of `q.error.message`.

---

## 2. P-01 Today — `/`

### Purpose

> **What is on today, and which single line in each match is worth opening.**

That sentence is writable, and the fixture row genuinely serves it: clubs, a win/draw/away bar, and
`best_line` naming the one line worth reading. That row is the best object in these six screens.
The page's problem is that this sentence is answered at 1713px.

### Inventory

| Element | Earns it? | Verdict |
|---|---|---|
| Date scroller (230px, three wrapped rows) | Yes, at 74px | **Change** — stop the wrap (§1.2) |
| Orphaned calendar button on its own row | No | **Change** — it is the third row of the wrap; fixing the wrap fixes it |
| “Top 3 for today” + “See all 20” | The section yes, **its contents no** | **Change** — see Hierarchy |
| Three `ForecastCard`s (1244px) | Not at this size or this position | **Change** — one card, or move below the fixtures |
| `tier_note` “Held at Solid until our record on these lines is measured” | No | **Delete from the card face.** It is identical on all three cards and on most of the feed. A constant is not information; it belongs in the sheet or in Learn |
| Live strip | Yes | Keep (never rendered — no live fixture in demo, docs/57 §7) |
| Chips: All 6 / With insights 6 | **No** | **Delete or hide.** Both options returned the same six fixtures in the render. Two controls, one result |
| League group header (crest, name, count, chevron) | Yes | Keep |
| Fixture row: time + “in 10h 43m” | Time yes, countdown no | **Change** — the countdown overflows its column (`td-time` 70 > 64px, measured) and is near-identical on every row |
| Fixture row: crests + names | Yes | Keep |
| Win/draw/away bar | Yes — **but the draw number is invisible** | **Change** — prints “Team 0 42% … Team 2 31%”; the missing 27 is unexplained. Draw is in the aria-label only |
| `best_line` chip | **Yes — the best decision on the page** | Keep |
| “Percentages are our win, draw and loss likelihoods for each match.” | Marginal | Keep, move under the first group |
| Newsletter card + footer (≈900px) | Site furniture | Keep |

### Hierarchy

Eye hits: **(1)** the three-row date grid, **(2)** “Top 3 for today”, **(3)** a 92% in 32px type.
The job wants: **(1)** today's matches, **(2)** the one line worth opening in each, **(3)** the day
control. The order is inverted, and the thing in slot 3 is the worst-chosen content on the screen.

**The 92% is the finding.** `topRated()` sorts by `RANK[tier]` then `whole(f) = p × p_play` — raw
likelihood. Measured against the live feed:

| Today's Top 3 | p | own usual | edge | span |
|---|---|---|---|---|
| Player 2, 1+ shot | 92.2% | 90.7% | **+1.5 pts** | 0.070 |
| Team 7, 9+ shots | 91.4% | 90.4% | **+1.0 pt** | **0.018** |
| Player 701, 3+ shots | 88.8% | 86.9% | **+1.9 pts** | 0.085 |

| What `span` would pick | p | own usual | span |
|---|---|---|---|
| Team 9, 9+ shots | 82.3% | 76.3% | 0.151 |
| Team 5, 4+ corners | 81.4% | 74.7% | 0.128 |
| Team 7, 4+ corners | 81.4% | 78.7% | 0.128 |

Feed median span is 0.085; Today picked one at 0.018. docs/50 §9.4: *“a rung with spread < 0.05 is
not a forecast and should never lead a card.”* Today leads with one. docs/56 §1: *“what makes
`9+ shots, 88%` useless is not that it is likely — it is that it cannot move.”* Today's #2 card is
literally `9+ shots, 91%`. **The front page promotes exactly the thing two internal documents were
written to stop.** The card is built to show this — it computes `dep`, draws the departure segment,
prints `+2` — and the ranker above it ignores all of it.

Meanwhile `/combos` renders three cards straight off `/api/insights?limit=3` (default sort) with
edges of **+10, +9, +7**. A plain unsorted API call beats Today's curation by five times.

### The filters

Four dimensions on offer: day, All / Following / Live now / With insights.

- **Day:** right dimension, wrong control at this width (§1.2).
- **All vs With insights:** returned identical sets. Hide a chip whose count equals `all`.
- **Following:** right, and correctly hidden when signed out.
- **Live now:** right, correctly hidden at zero.
- **Missing:** league. The page groups by league and collapses groups, but there is no way to say
  “only the leagues I follow”. `favFirst` reorders; it does not filter.

Default state is useful (all of today's matches). That is the one thing the filter layer gets right.

### Empty, loading, error

**Designed, and the best set of the six.** `Skeleton shape="match"` matches the row shape; the
empty state branches on whether a filter is active and offers the correct next action (“See the
next day” vs “Show all matches”); the error state keeps a retry. No change needed.

### Faults visible in the render

1. Date strip wraps to **three rows, 230px**; the calendar button is orphaned on row three, left-aligned under nothing.
2. Fixtures begin at **1713px** — two viewports.
3. `tier_note` repeats verbatim on all three Top-3 cards.
4. `.v2-cr-m` / `.v2-cr-o` at **8px**; the date strip's league fallback chip at **5.88px**.
5. `td-time` overflows its column (70 > 64px).
6. Every fixture reads “07:00 PM · in 10h 43m” — the countdown adds nothing when it is the same on every row.
7. Draw likelihood is never shown, only home and away.
8. `+2` / `+10` departure badges carry no unit. On a card about shots, “+2” reads as two shots, not two likelihood points.

### Proposals, ranked

1. **Rank Top 3 by `span` with a `span ≥ 0.05` gate.** *Reason:* docs/50 §9.4 and docs/56 §2; the field is already on the row. *Effect:* the module starts earning its 1244px — and if the gate empties it, the honest outcome is that the module hides itself, which is also correct.
2. **Restore the horizontal day scroller below 480px.** *Effect:* −160px, first card at ~220px.
3. **Fixtures above Top 3**, retitled “Worth opening today” and cut to one card. *Reason:* the screen is named Today, not Top 3. *Effect:* the page answers its own question in the first viewport.
4. **Move `tier_note` to the forecast sheet.** *Reason:* a sentence identical on every card is chrome.
5. **Label the departure badge** — “+2 pts vs usual”, or put the unit once in the card's `v2-cmp` row. *Reason:* the comparison is the product's whole claim and it is currently ambiguous.
6. **Print the draw figure** in `WdlBar`'s visible text. *Reason:* three numbers that do not sum to 100 look like an error.
7. **Drop the countdown**, keep kick-off. *Effect:* removes the only measured overflow on the screen.
8. **Hide the `With insights` chip when its count equals `All`.** `ChipsRow` already hides `count === 0`; extend the same rule.

---

## 3. P-04 Insights — `/insights`

### Purpose

> **Everything worth reading today, across all matches, narrowed however the reader wants.**

Writable, and the page largely does it. The grouping by fixture (v2 decision 4) is right, and the
sentence is the best filter control in the product. This screen is the strongest of the six in
concept and the most damaged in execution at phone width.

### Inventory

| Element | Earns it? | Verdict |
|---|---|---|
| `h1` “Insights” | Yes | Keep |
| “20 lines worth reading across 6 matches” | **Yes** | Keep — this is the orientation line v2 asked for and it works |
| “Any day” chip (64px, floating left of a wrapped grid) | The option yes, this treatment no | **Change** — it is the default; it should be the strip's own first cell, not a separate pill |
| DateScroller (317px with the chip) | Yes at one row | **Change** (§1.2) |
| The sentence: market / player / club / sort | **Yes. Keep and protect.** | Keep |
| The sentence: “and have had 2+ in any run of games” | **No, as written** | **Change** — see below |
| “More filters N” | Yes, badge wrong | **Change** (§1.10) |
| “Clear” | Yes | Keep |
| Cards / List `Segmented` | **No** | **Delete.** List view flattens `shown` and silently discards the fixture grouping the page is built around. It is a second rendering of the same data for no stated reader need |
| Fixture group header + “Match page” link | Yes | Keep |
| 20 `ForecastCard`s at 384px each | Yes | Keep |
| “Show more matches” + “6 of 6 matches” | Yes | Keep — correctly replaced pagination |
| Plan cap notice | Yes | Keep |
| FilterSheet: tier, league, position, venue, min likelihood, confirmed | Yes | Keep |

### Hierarchy

Measured, phone: `h1` 81 → answer line 123 → day block **160–477** → sentence 490–683 → first group
header 713 → **first card 778**. Usable fold is 774px.

**The first forecast is below the fold again.** v2's single proudest number — 913 → 476 — has
regressed to 778, and the whole of the regression is the 317px day block. The irony is complete:
the fix was “answer first, filter second”, and a filter whose default is “Any day” now consumes 38%
of the first screen.

Desktop is fine: first card at 446px, three-up grid, clean.

### The filters

**v2 promised one filter surface. There are four.**

1. The day strip + “Any day” chip (317px, above the sentence, not counted in the badge).
2. The sentence — market, player, club, sort, history threshold, history window.
3. The `FilterSheet` — tier, league, position, venue, minimum likelihood, lineup confirmed.
4. The Cards/List toggle.

Nothing tells a reader which filter is where. “Position” is in the sheet; “player” is in the
sentence. “Tier” is in the sheet; “market” is in the sentence. There is no rule — it is an
arbitrary six and six, which is the same fault v2 recorded as “an arbitrary five and three”.

**The history clause is broken in a way the render shows.** `hStat` resolves to
`MARKETS.find(m => m.id === mk)?.q?.stat || "shots"`. With the default “all markets”, the sentence
reads:

> …and have had **2+** **in 6 of their last 10**.

Two-plus *what*? The noun is absent, and the query silently runs on shots. A sentence that was
justified on the grounds that it “states the entire query in words, in place, with no hidden
state” now has hidden state in its newest clause. Also: the sentence renders a stray space before
its full stop (“…in any run of games .”), visible at both widths.

**Default state:** useful — 20 lines across 6 matches, no filter applied. Correct.

### Empty, loading, error

**Designed.** Skeleton in card shape, `EmptyState` with “Clear all filters”, `ErrorState` with
retry. The one gap: when the history clause is active, `hq` has its **own** loading and error states
that are not surfaced at all — `hIds` is `null` while `hq` loads, so the feed shows unfiltered
results for a beat and then shrinks, with no indication that a second query is running. A filter
that briefly shows the wrong answer is worse than one that shows a spinner.

### Faults visible in the render

1. Day block **317px**; first card at **778px**, below the fold.
2. “Any day” pill vertically centred against a three-row wrapped grid with large dead space above and below it — reads as a broken layout, not a choice.
3. Every `<select>` in the sentence is **27px tall** (measured: 96×27, 108×27, 91×27, 133×27, 26×27, 247×27). Below the 44px HIG target and below the 24px WCAG 2.2 minimum in one dimension.
4. The 26×27 select is the “2+” threshold — a 26px-wide tap target.
5. Sentence wraps mid-clause: “…at **every club**, **biggest change** first, and have had **2+** / **in any run of games** .”
6. `.v2-cr-m` / `.v2-cr-o` at 8px on all 20 cards.
7. A fixture group with four cards leaves two empty columns on desk — ragged, no rule for short groups.

### Proposals, ranked

1. **Horizontal day strip, and fold “Any day” into it as the leading cell.** *Reason:* it is one dimension; it should be one control. *Effect:* −250px, first card back above the fold.
2. **Name the stat in the history clause, and disable the clause until a market is picked.** Read: “…and have had **2+ shots** **in 6 of their last 10**.” *Reason:* removes the only hidden state in the product's best control.
3. **Make the sentence's tokens buttons, not `<select>`s** — reuse Finder's `Part` popover, which is already 44px tall and already styled as underlined words. *Reason:* one pattern instead of two for the same idea, and it fixes six tap targets at once. *Effect:* Insights and Finder become visibly the same control, which is the groundwork for §8.
4. **Fix the “More filters” badge** to count only sheet contents, and show the day in the sentence (“…playing **any day**”) so the day stops being a fourth surface.
5. **Delete Cards/List.** *Reason:* it discards the grouping without saying so, and no stated job needs it.
6. **Show a loading state while `hq` runs**, and disable “Show more” until it resolves.
7. **Fill short fixture groups** to the grid width, or drop to a two-up grid for groups of ≤ 2.

---

## 4. P-05 Finder — `/finder`

### Purpose

Attempted: *“Ask for a specific line and get the answer.”* But I cannot write a sentence that
distinguishes it from Insights, and that is the first finding. Its third mode, `likelihood`, is
Insights — Insights' own source comment says so: *“Its third mode, ‘Our forecast’, was dropped: it
ranked upcoming forecasts by likelihood, which is what this page already is.”* It was dropped from
Insights. It is still here, as one of three top-level tabs on this page.

What Finder uniquely offers is **two clauses over past games** — “in 6 of the last 10” and “in a row
right now”. Both already exist on Insights. The unique part of this screen is a feature of another
screen.

### Inventory

| Element | Earns it? | Verdict |
|---|---|---|
| `h1` “Forecast Finder” | — | Dies with the page (§8) |
| Mode `Segmented`: How often / Streak / **Our forecast** | Two yes, one no | **Delete “Our forecast”** — it is Insights, duplicated |
| Saved searches `ChipsRow` | Yes | **Move** to Insights with the merge. The only reader-owned state here |
| **The sentence** | **Yes — the best interaction in the product** | **Move to Insights intact** |
| “Pick a league first” (disabled primary) | No | **Delete** — see below |
| “Reset” link | Yes | Keep |
| Usage meter “3 of 3 free searches left today” | Needed, wrongly placed | **Move** — it greets a visitor with a countdown before they have done anything |
| `EmptyState` “Pick a league / Tap any underlined word to change it” | **No** | **Delete** — same instruction as the disabled button, 170px apart |
| Results list / cards | Yes | Keep |
| `Wall` (quota exhausted) | Yes, well made | Keep |
| `Reminder` “Your searches come back at 00:00, in about 15h 42m” | Yes | Keep |

### Hierarchy

Eye hits: **(1)** “Forecast Finder”, **(2)** three mode tabs, **(3)** the sentence. Then a disabled
button, a quota meter, and an empty box. The job wants the answer first; the screen has no answer
to give, by construction.

Measured: page height 1624px, of which **~900px is the newsletter card and the footer**. More than
half of the Forecast Finder is site furniture.

### The filters

The sentence *is* the filter, and its dimensions are right: who (players/teams), threshold, stat,
window, venue, position, league, day. The control is right too — a clause in place beats a modal.
Two faults:

- **League is required and has no default.** Nothing else on the page can act until it is set, and
  the reason (`finder_leagues` entitlement caps how many leagues a plan may query) is a billing
  rule leaking into the opening state. Seed the reader's first followed league, or the only league
  the demo has, and run.
- **Clause order does not match how anyone asks.** It reads *who → how many → what → window →
  venue → position → league → day*. A reader asks *who → what → when*; venue and position are
  refinements and should trail, behind a “more” token, not sit between the stat and the league.

**Default state is empty and the screen says so twice.** This is the “answer first” rule broken
harder than anywhere else in the product — which is precisely the sentence CRITIQUE §1 wrote about
Compare before Compare was fixed. Compare was fixed. Finder was not.

### Empty, loading, error

The states are *built* — `Skeleton shape="row"`, `ErrorState` with retry, two distinct empty states
(“Ready when you are” with a league picked, “Pick a league” without), the `Wall`, the reset
`Reminder`. The craft is high. **But the default state is one of them**, which means the designed
empty state is doing the job of the designed screen. A loading/empty/error set is only good if it
is an exception.

### Faults visible in the render

1. The page's entire body above the newsletter is six controls and an empty box.
2. “Pick a league first” (disabled button) and “Pick a league” (empty state heading) within one screen.
3. The sentence wraps across four lines on breaks that are not clause breaks: “…**2+ shots** in / **6 of the last 10** games, / **home or away**, **any position** in / **pick a league** playing **today**”.
4. The “2+” token is a **27px-wide** tap target (`fs-word: 27×44`).
5. `Segmented` buttons are 32px tall.
6. The quota meter is shown before any search is made.

### Proposals, ranked

1. **Merge into Insights (§8).** Everything below is what to do in the meantime, or during.
2. **Seed a league and run on load.** *Reason:* parity with the Compare fix. *Effect:* the screen answers before it asks.
3. **Delete the “Our forecast” mode.** *Reason:* it is Insights. *Effect:* removes a third of the mode control and one of the two doors onto the same room.
4. **Delete the redundant empty state**; let the disabled button carry the instruction.
5. **Move the quota meter beside the results**, shown after the first search. *Reason:* a countdown is a consequence, not a greeting.
6. **Reorder the clauses** to who → what → when, with venue and position behind a “more” token.
7. **Widen `.fs-word` to a 44px minimum** (`min-width: 44px`), which also fixes the Insights selects if proposal §3.3 lands.

---

## 5. P-06 Explore — `/explore`

### Purpose

> **Every league we cover, and what each one has next.**

The subtitle already says it, honestly, and it is a real job nothing else does. Explore is the only
one of these six whose stated purpose, content and name agree.

**But it has no phone tab** (`GLOBAL.md` §2: `NAV5` renders Explore on desk only). A browse surface
with no entry point on the device most readers use is a browse surface that does not exist. That is
an IA finding, owned by `GLOBAL.md`, and it changes the weight of everything below: on a phone this
screen is reached only from the footer.

### Inventory

| Element | Earns it? | Verdict |
|---|---|---|
| `h1` + subtitle | Yes | Keep |
| “Filter leagues” search box | **Not at this count** | **Change** — render only above ~12 leagues. A filter over a list of one is furniture |
| “Your teams” (signed in only) | Yes | Keep |
| League grid | **Yes — this is the page** | Keep |
| League tile: mark, country, name, “6 today” | Yes | Keep. “6 today” is the right kind of label — a state, not a count of nothing |
| “Search players and teams for ‘x’” link | Yes | Keep |
| **“The rest of the app” — 6 links** | **No** | **Delete five of six** |

### The “rest of the app” list

The v2 CONSOLIDATION removed this. The current code restores it with a stated reason: *“a footer is
where links go to be unfindable, and Explore is the browse surface, so this is the right home for
them.”*

**The render refutes the reason.** In the phone capture, the six-item list and the footer are
visible in the same scroll, ~300px apart, and five of the six — Track record, Compare, Referees,
Learn, Plans — appear in both. Only “Live scores” is unique to the list. The footer is not
unfindable here; it is directly below. What the render shows is one navigation menu printed twice.

The *other* half of the reason is right, though, and `GLOBAL.md` finding 1 is the same point: Track
record has no primary entry point. **The answer is not a duplicate list on a desk-only page — it is
a tab** (`GLOBAL.md` proposes exactly that). Explore should not be where the product hides its
evidence screen.

**Verdict: delete the list. Keep one link — Live scores — only until it has a home elsewhere.** If
the product disagrees, then the blurbs are the thing worth keeping and the duplication is not:
promote the blurbs into the footer and delete the list.

### Hierarchy

Eye hits: **(1)** “Explore”, **(2)** the filter box, **(3)** the one league tile. Slot 2 is a
control over a list of one. The grid should be first.

With real league counts the hierarchy is correct and the page is fine. **With demo data it is 90%
navigation**, which is a demo-data artifact and should not be over-read — but the duplicate link
list is not, and the unconditional filter box is not.

### The filters

One dimension (text over league name and country), right control, right default (empty = show all).
The only fault is that it is unconditional. Missing dimension: nothing. A league browser does not
need more.

### Empty, loading, error

**Designed, and the best empty state in these six.** `No league matches “x”` with a real next step
(“Looking for a club or a player? Search everything”) that routes the reader's existing query to the
place that can answer it. Skeleton and `ErrorState` present, and `YourTeams` has its own scoped
error state rather than failing the page. Nothing to change.

### Faults visible in the render

1. Five of six “rest of the app” links are repeated in the footer in the same screenshot.
2. The league grid shows one half-width tile with a large empty cell beside it — no single-item layout rule.
3. The filter `<input>` is **26px tall** (measured) — below any tap-target minimum.
4. “Your teams” is hidden entirely when signed out, so a visitor sees title, subtitle, filter, one tile, and a duplicate menu.

### Proposals, ranked

1. **Delete “The rest of the app”** (keep Live scores until it is routed). *Reason:* measured duplication, visible in one screen. *Effect:* −380px and one fewer navigation vocabulary.
2. **Render the filter box only above ~12 leagues.** *Reason:* a control that cannot change the result is noise.
3. **Raise the filter input to 44px** when it is rendered.
4. **Give the grid a single-item rule** — full width, or a different tile shape.
5. **Signed out, show the followed-teams slot as an invitation** (“Follow a club to see it here”) rather than removing it, so the page does not lose a third of its structure for visitors.
6. **Owned by `GLOBAL.md`, restated here because it is why this page exists in this shape:** give Explore a phone tab or accept that it is a desk feature and stop putting unique links on it.

---

## 6. P-07 Compare — `/compare`

### Purpose

> **Two clubs side by side: where one is better, and by how much.**

Writable. And the seeding fix from v2 works — the page opens with Team 0 v Team 2 from today's
fixture and a full comparison, not a form.

### Inventory

| Element | Earns it? | Verdict |
|---|---|---|
| `h1` “Compare” | Yes | Keep |
| Two `Picker` cards (crest, name, search box) | Yes | **Change** — see below |
| Swap button | Yes | Keep |
| Season / Last 5 `Segmented` | Yes | Keep |
| “As a fixture” checkbox | Yes | **Change** — 20×20px target |
| Radar (6 spokes, 270px) | **Questionable** | **Move** below “What stands out” |
| “What the spokes mean” disclosure | **No — it is an admission** | A chart whose axes need an explainer has the wrong axes |
| **“What stands out” (4 sentences)** | **Yes — the best thing on the page** | **Move to first** |
| “Per game” table (11 rows) | The data yes, **the mark no** | **Change** — see below |
| Different-leagues note | Yes | Keep |

### Hierarchy

Eye hits: **(1)** two pickers (290px before any content on phone), **(2)** a radar, **(3)** the
answer. The answer is third. “What stands out” is four plain sentences that say who is better at
what and by how much; it is what a reader came for and it is 900px down the phone render.

**Nothing explains the seeded clubs.** They simply appear. A reader has no way to know these are
today's next fixture rather than something they chose or something the product recommends. One line
— “Starting with today's fixture” — closes it.

### The per-game bars: the worst mark in these six screens

Each row renders `a` and `b` as two segments of one 100% track.

- **“Goals, edge to Team 2”** — 1.4 / 1.8. The right segment is longer and the right club is better.
- **“Goals against, edge to Team 0”** — 1.1 / 1.25. The right segment is longer and the right club is **worse**.

Same mark, adjacent rows, opposite meaning. Nothing in the bar distinguishes them; only the “edge
to X” text does, and the reader has already read the bar by then.

Second fault, in the same mark: the winner's number is coloured, but the colour is positional
(`--chart1` blue on the left, `--up` lime on the right), so the winner changes colour by side. In
row 1 the winner is lime; in row 2 the winner is blue. Colour is carrying two meanings at once and
neither reliably.

Third fault: **“Possession %, 61.85 vs 36.6”** drawn as a 63/37 split of one track. Those are two
clubs' season averages from different matches. Rendering them as a split of one whole states a
head-to-head possession share that does not exist — and they do not even sum to 100. This is the
one mark here that is not merely confusing but wrong.

Fourth: four significant figures throughout — 61.85, 1.56, 12.65, 16.15. Spurious precision on
per-game averages. One decimal is the honest resolution and matches “What stands out”, which
already writes “1.6 a game”.

Fifth: the “Tackles” row has no “edge to” and both numbers plain — a twelfth grammar in an
eleven-row table.

### The radar

Six spokes, two overlapping polygons, a collapsed legend explaining the axes, and a note that each
club is placed within its own league. In the desk render Team 0's polygon is visibly larger on most
axes while “What stands out” gives Team 2 the edge in three of the four stats it names. Both can be
true — the radar normalises within league and inverts the “against” axes — but a reader cannot
reconcile them, and the page offers no help. **A radar that needs a disclosure to read its axes and
a footnote to read its scale is doing less work than four sentences.** Demote it.

### Duplication

“What stands out” prints “Goals: Team 0 1.4 a game, Team 2 1.8 a game. Clear edge to Team 2.” The
table row 200px below prints `1.4 | Goals, edge to Team 2 | 1.8`. **The same statement twice,
adjacent, in two formats.** CRITIQUE §2 pattern 2, intact.

### The filters

Two clubs, a window (Season / Last 5), and an “as a fixture” switch. Right dimensions. Right
controls, except the checkbox. Default state is useful (seeded). Missing: nothing — a comparison
of two clubs over a window is the whole space.

### Empty, loading, error

Mostly designed, two gaps:

- **The seed has no loading state.** On a cold load the reader sees `EmptyState` “Pick two clubs”
  while `/fixtures` resolves, then the page swaps to a comparison. A flash of an empty state that
  tells the reader to do something, immediately followed by it being done for them.
- **If there are no fixtures today the seed never fires**, and the reader gets an empty state whose
  advice is to go to another screen — the exact fault CRITIQUE flagged and this fix was meant to
  remove. It is not removed, only hidden on days with fixtures.
- `Not enough matches yet` is well written and correctly distinguished from the error state.

### Faults visible in the render

1. 290px of pickers before any content on phone; answer at ~900px.
2. The per-game bar reverses meaning between adjacent rows (above).
3. Possession drawn as a split of one whole (above).
4. Four significant figures throughout.
5. “As a fixture” checkbox is **20×20px** (measured).
6. The “As a fixture: Team 0 at home vs Team 2 away” label wraps to two lines beside the tiny box on phone.
7. `Segmented` buttons 32px tall.
8. Two SVG label overflows in the radar (51 > 48px, 49 > 47px) — axis labels clipping their boxes.
9. Nothing says the clubs were chosen for the reader.

### Proposals, ranked

1. **Redraw the per-game rows as two bars on a shared axis**, one per club, with “lower is better” rows marked. *Reason:* the current mark means opposite things on adjacent rows. *Effect:* the table becomes readable without reading the labels.
2. **Order: “What stands out” → per-game → radar.** *Reason:* the sentences are the answer; the radar is the illustration.
3. **Drop the possession bar**, or draw it as two gauges against 50%. *Reason:* it states a relationship that does not exist.
4. **One decimal everywhere**, matching the prose. *Reason:* four significant figures imply a precision the data does not have.
5. **Say “Starting with today's fixture — change either side”** above the pickers. *Reason:* an unexplained default reads as the reader's own choice.
6. **Collapse the pickers to one row** on phone (crest + name + a small “change” affordance), expanding on tap. *Effect:* ~180px, answer above the fold.
7. **Give the seed a skeleton**, and give the no-fixtures case a real fallback (two most-followed clubs, or the first two in the default league).
8. **44px checkbox**, and cut the label to “As a fixture” with the detail as help text.
9. **Delete “What stands out” sentences that the table already prints**, or cut the table rows the sentences name. One of the two.

---

## 7. P-08 Combos — `/combos`

### Purpose

> **The lines you have collected, and how likely they are together.**

Writable, and the signed-in page does it well. The `Card` component is good work: a faces strip, a
status pill that distinguishes Waiting / Counting up / Reached n of m, a live count, and a settled
list with a dash — never a cross — for unknown (docs/03 §4.6). The `Summary` is honest about small
samples. **Signed in, this screen is in good shape.** Most of what follows is about the signed-out
state, which is what most first-time traffic sees.

### Inventory

| Element | Earns it? | Verdict |
|---|---|---|
| `h1` “My combos” + “n saved · room for N” | Yes | Keep |
| “Your open combo · n lines · Review” | Yes | Keep |
| **Signed out: explainer paragraph** | Yes | Keep |
| **Signed out: three single `ForecastCard`s** | **No** | **Change** — see below |
| Signed out: “Create a free account” (secondary) + “See all lines” | Yes, wrong weight | **Change** |
| Signed in: Coming up / In play / Finished `Segmented` | Yes | Keep |
| Signed in: `Summary` | Yes | Keep |
| `Card`: faces, label, kick-off, status pill | Yes | Keep |
| `Card`: “Now” vs “When saved” | **Yes — a genuinely good idea** | Keep, and give it more room |
| `Card`: per-line result list | Yes | Keep |
| `Card`: Open match / Delete | Yes | Keep |

### The signed-out page does not show the feature

The copy says: *“Add lines from any card to build a combo, and we work out the combined chance.”*
The page then renders **three unrelated single forecast cards**. There is no combination, no
combined chance, no grouping — the one thing the product does on this screen is described in prose
and never shown.

CRITIQUE §1 asked for exactly this fix and it was half-made: the page stopped being a wall, but
what replaced the wall is a sample of the *input*, not the *output*. A visitor leaves knowing there
are forecast cards — which they already saw on Today — and not knowing what a combo is.

**Fix:** render one worked example. Two or three of today's lines, grouped in the real `Card`
chrome, with a real combined figure, labelled “An example”. The data is already there — `useCombo`
computes combined likelihood client-side, and `/api/insights?limit=3` is already being fetched.
*Effect:* the page demonstrates its feature in the space it currently spends describing it.

### Hierarchy and the two conversion asks

Eye hits: **(1)** “My combos”, **(2)** the first card's 89%, **(3)** the explainer. Then, at the
bottom: “Create a free account” as a **secondary grey button**, immediately above the newsletter
card whose “Send me the e-mail” is the **primary blue button**.

**The page's own conversion ask is drawn weaker than the newsletter's.** Three asks stack within
300px — account, see all lines, newsletter — and the loudest is the one that is not this page's
job. Make the account button primary, or suppress the newsletter card on this screen.

### The filters

Signed in: one dimension (Coming up / In play / Finished), right control, counts in the labels, and
the In-play tab correctly hidden at zero. Default (Coming up) is the useful one. **Nothing to
change.** This is the cleanest filter layer of the six.

### Empty, loading, error

Mostly designed, one real gap and one small one:

- **`ErrorState message={q.error.message}`** — every other screen in this set passes a written
  sentence (“We could not load the fixtures.”). This one passes the raw API message, with no
  fallback and no `testid`. **Change it** to “We could not load your combos.”
- The empty state (“No saved combos yet… Open any match and tap + on the lines you like.
  [Find a match]”) is good, and correctly sends the reader to a screen that can act.
- Skeletons present and correctly shaped.
- The `tab === "done"` branch with nothing finished renders a bare `<p class="muted">Nothing
  finished yet.</p>` rather than an `EmptyState` — a third empty-state grammar on one screen.

### Faults visible in the render

1. Signed out, no combo is ever shown on a page called “My combos”.
2. “Create a free account” is secondary; the newsletter's CTA directly below it is primary.
3. `.v2-cr-m` / `.v2-cr-o` at 8px on all three sample cards.
4. `+10` / `+9` / `+7` departure badges with no unit (same as Today).
5. Page is 2378px for three cards; ~1100px is newsletter plus footer.
6. Three different empty-state treatments: `EmptyState`, bare `<p class="muted">`, and the `SignedOut` block.

### Proposals, ranked

1. **Show one real worked combo signed out**, in the real `Card`, with a real combined figure. *Reason:* the feature is currently described, not shown.
2. **Make “Create a free account” the primary button**, and suppress the newsletter card on this screen. *Reason:* two conversion asks, and the wrong one is loud.
3. **Write the combos error sentence** and add a `testid`. *Reason:* one screen out of six leaks an API string.
4. **Use `EmptyState` for the per-tab empty cases.** *Reason:* one grammar per product.
5. **Give the “Now vs when saved” row more weight** on the upcoming card. *Reason:* a combination whose likelihood has moved since it was saved is the most interesting thing this screen owns, and it is currently set in small grey text beside a large one.
6. **Label the departure badge** (shared with Today §2.5).

---

## 8. Consolidation — do all six need to exist?

### The ruling on Insights and Finder: **merge. Finder goes.**

v2's CONSOLIDATION §2 argued for this and built half of it — Finder's sentence is on Insights, and
Finder's two historical clauses are on Insights. It then stopped, blocked on an entitlement rule.
**The result is the worst of both:** the sentence exists twice, in two different control
vocabularies (`<select>` on Insights, popover buttons on Finder), the historical clauses exist
twice, and Finder's `likelihood` mode is Insights outright — a fact Insights' own source comment
states while Finder still ships it.

The split now costs:

- **A phone tab** — two of five, on one job (`GLOBAL.md` finding 2).
- **A screen whose default state is empty**, when the merged destination's default is useful.
- **Two implementations of one control** that will drift. They already have: Finder's tokens are
  44px tall; Insights' are 27px.
- **A reader having to know that “show me players with 3+ shots in 6 of 10” lives on Finder when
  the same clause is on Insights.**

**How:**

1. Finder's `likelihood` mode is deleted. It is Insights.
2. Finder's `Part` popover replaces Insights' `<select>` tokens. One control, the better one, and
   six tap targets fixed.
3. Finder's remaining clauses — window, venue, position, scope (players/teams), threshold stepper —
   become tokens in the Insights sentence, behind a “more” token so the default sentence stays
   short. The clause must name its stat (§3, proposal 2).
4. Saved searches move to Insights, keyed on the sentence.
5. **The entitlement rule, which is the owner's call and the only real blocker:** a search is
   counted when a clause that queries past games is *changed* — i.e. when `/finder` is actually
   called. Editing market, player, club, day, sort, tier, league, position or venue filters the
   already-loaded feed and costs nothing. That rule is mechanically exact (it is literally "did
   `hWhen` change"), explainable in one sentence to a reader, and does not change what any plan buys.
6. `/finder` redirects to `/insights`, carrying its query as parameters. It is in the footer, in
   bookmarks and in analytics.
7. The freed tab goes to Track record (`GLOBAL.md` §2).

**What is lost:** the Finder's results *list* — a compact row with an avatar, the run strip and
“Next 84%” — which is denser than a card grid for a 300-row answer. Keep it as the merged page's
list rendering when a history clause is active. That is a better use for the Cards/List toggle than
its present one, and it is the one argument for keeping that toggle rather than deleting it (§3).

### The other four

| Screen | Verdict | Why |
|---|---|---|
| **P-01 Today** | **Keep.** The only day-shaped view, and the fixture row is the best object in the product. Its content ranking is wrong, not its existence | — |
| **P-06 Explore** | **Keep the league browser; delete the link list.** It is the only league-shaped entry point and `/leagues` and `/teams` should point at it. But it has no phone tab, so on a phone it is currently a footer destination that happens to hold six unique-looking links. Either give it a tab or stop putting anything unique on it — not both as now | — |
| **P-07 Compare** | **Keep, on probation, and fix the bars.** It answers “which of these two is better at what”, which nothing else does. Its weakness is still the one CONSOLIDATION named — it is most natural as “Compare with…” from a club page, and whether the destination earns a route is an analytics question. **But that question is unanswerable while the page's central mark is unreadable.** Fix the bars first, then ask | — |
| **P-08 Combos** | **Keep, and move it out of the discovery group.** CONSOLIDATION was right: this is a saved-items page and belongs beside You, not among the ways to find a forecast. After the Insights/Finder merge the phone bar is Today / Find / Record / Combos / You, which is one discovery door, one evidence door, and two “your stuff” doors — a vocabulary a reader can actually learn | — |

### What the six become

**Before:** Today, Insights, Finder, Explore, Compare, Combos — three of six are ways to find a
forecast, and a reader cannot tell them apart by name.

**After:** Today (what is on), Find (what is worth reading, Finder inside it), Explore (the league
browser), Compare (two clubs), Combos (your saved lines). **Five screens, five distinguishable
questions, one fewer phone tab spent on a duplicate door.**

---

## 9. Two things that are already good

Said plainly so they are not changed by accident.

- **`ForecastCard`'s departure mark.** The bar that draws from a player's usual to this fixture's
  number, with the tick at usual, is the right mark for this product's argument, and the reasoning
  in its source comments is correct. The card's problem is that Today's ranker ignores the quantity
  the card is built to show. Fix the ranker, not the card.
- **The state views.** `StateViews.jsx` is well made and well adopted: skeletons match the shape of
  what is loading, empty states say why and offer a next step, error states keep the last good data
  and a retry. Three gaps are named above (Finder's default *is* an empty state, Insights' second
  query has no state, Combos leaks an API string). The grammar itself is sound.

---

## 10. Compliance check on everything proposed here

- **Reader copy.** No proposal uses a word in `backend/textguard.py`'s `BANNED` set. The proposed
  strings are: “+2 pts vs usual”, “Worth opening today”, “An example”, “Starting with today's
  fixture — change either side”, “We could not load your combos.”, “Follow a club to see it here”,
  “…and have had 2+ shots in 6 of their last 10”, “lower is better”. Note that `units` is banned, so
  the departure badge is labelled **pts**, never “units”.
- **Colour.** Every proposal reuses existing tokens: `--up`, `--down`, `--chart1`…`--chart6`,
  `--text`/`--text2`/`--text3`, `--surface1`…`--surface3`, `--tier-*`. No literal hex.
- **Names.** No existing class or `data-testid` is renamed or removed. Deletions proposed —
  Explore's `ex-more`, Insights' `ins-view`, Finder's `finder-idle`, Today's `today-filter`
  `insights` chip — each remove a node and its id together; if the 42 self-tests assert on any of
  them, keep the node and hide it, or update the test in the same change. Everything else is
  additive.
- **390px.** Measured: no horizontal page scroll on any of the six, at either width, in either
  scheme (`scrollWidth === clientWidth` on all twelve renders). The proposals reduce height; none
  adds width. The one measured overflow, `td-time` 70 > 64px, is inside a row and is fixed by
  proposal §2.7.
- **Both schemes.** Contrast measured on the smallest text in both: every pair passes AA
  (5.94–13.36 dark, 4.50–12.96 light). The faults are **size, not contrast** — `.v2-cr-m` and
  `.v2-cr-o` at 8px, and `.media-fallback` at 5.88px in the date strip. `.v2-cr-v` in light sits at
  exactly 4.50, so any future darkening of `--up` breaks it.
