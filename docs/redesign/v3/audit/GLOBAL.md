# v3 audit — the global chrome, the information architecture, the design system

Written by reading `frontend/src/components/Layout.jsx`, `frontend/src/styles/v2.css`,
`backend/site_studio.py` and the route table, not from memory. This file covers what no
per-screen audit owns: the navigation every screen sits inside, and the system every screen is
drawn with. The per-screen audits are the other files in this folder.

---

## 1. The ten findings, ranked

| # | Finding | Why it matters | Cost |
|---|---|---|---|
| 1 | **Track record has no primary entry point.** It is in the footer and inside the desk-only Explore tab. On a phone the only routes to it are the footer and search. | This product's moat is that it publishes how its own forecasts performed. The screen that proves it is the hardest one to reach. | Small |
| 2 | **Insights and Finder are both primary tabs and answer the same question.** Two of five phone tabs spent on "show me lines". | Costs a tab, and makes a visitor choose between two doors to one room before they know what is behind either. | Medium |
| 3 | **Explore is desk-only, and it is the parent of eight screens.** Leagues, Teams, Compare, Referees, Track record, Learn, Plans and Live have no phone tab. | Most readers are on a phone. Eight screens with no entry point are eight screens that do not exist. | Small |
| 4 | **Plans has no primary entry point either.** Same footer-only fate as Track record. | The conversion screen is as buried as the trust screen. | Small |
| 5 | **The tab bar is five tabs with no room, and one of them is a power tool.** Combos is a build-a-combination workspace. | Not wrong to keep — the count badge is live state, which earns placement — but it is the first thing to question when a tab is needed. | — |
| 6 | **`NAV5.also` is a regex over paths.** The highlighted tab is computed by pattern-matching the URL. | It works, but it is a second, invisible route table that will drift from the first one. Any new route silently highlights nothing. | Small |
| 7 | **The theme toggle lives in the footer.** | A person who finds the product too bright has to reach the bottom of the page to fix it. It is also in the header on desk only. | Small |
| 8 | **Search is a `/` keyboard shortcut and a phone-only icon button.** On desk there is no visible search affordance in the header. | Search is the escape hatch for an IA with eight orphaned screens. Hiding it compounds finding 3. | Small |
| 9 | **The design system is genuinely good and under-used.** One variable family carrying hierarchy on the width axis, tabular figures wherever digits align, palette owned by Site Studio, motion tokens with a reduced-motion guard. | The system is better than some of the screens drawn with it. The gap is application, not foundation. | — |
| 10 | **No empty/loading/error grammar is enforced across screens.** `StateViews.jsx` exists; adoption is uneven. | Every screen inventing its own empty state is how a product stops feeling like one product. | Medium |

---

## 2. Navigation

### What exists

`Layout.jsx` `NAV5`:

| id | Label | Route | Phone | Desk |
|---|---|---|---|---|
| today | Today | `/` | ✅ | ✅ |
| insights | Insights | `/insights` | ✅ | ✅ |
| finder | Finder | `/finder` | ✅ | ✅ |
| combos | Combos | `/combos` | ✅ (badge) | ✅ |
| explore | Explore | `/explore` | ❌ | ✅ |
| you | You | `/following` | ✅ | ✅ |

Footer carries: Explore, Learn, Track record, Plans, Teams, Referees, Compare.

### What is wrong with it

**The product's argument is not in its navigation.** The pitch is "we forecast, and here is our
record". A visitor can use this app for a week and never find `/track-record`. Everything else in
this section follows from that.

**Two doors to one room.** Insights is a filtered feed of forecasts. Finder is a query over the
same forecasts. A reader who wants "Rabiot, shots, 3+" can get there through either, and nothing
on either screen explains why they are separate. The core-screens audit has been asked to rule on
whether they should merge; this file only records the cost of the split at the navigation level,
which is one of five phone tabs.

**Explore is a desk-only container for the half of the product nobody sees.** Its `also` regex
claims leagues, teams, compare, referees, track-record, learn, pricing and live. On a phone that
tab is not rendered, so those eight have no tab-level route.

### Proposal

Phone tab bar, five slots:

| Slot | Was | Becomes | Reason |
|---|---|---|---|
| 1 | Today | **Today** | Unchanged. The default destination. |
| 2 | Insights | **Find** | Insights and Finder merged behind one door. One room, one door. |
| 3 | Finder | **Record** | `/track-record`. The product's own evidence, one tap from anywhere. |
| 4 | Combos | **Combos** | Unchanged. Live state, earns its place. |
| 5 | You | **You** | Unchanged. |

Explore becomes a section header inside **You** on a phone (it is a browse surface, not a daily
destination), and stays a desk tab. Plans moves to the account menu and the lock states, where a
visitor meets it at the moment it is relevant rather than as a tab they must choose to press.

If the core-screens audit argues against merging Insights and Finder, the fallback is to demote
Combos to the Explore/You surface and give slot 4 to Record — because the ranking that matters is
*what makes a visitor believe the numbers*, and that is not a combination builder.

**Replace the `also` regex with an explicit map** from route to owning tab, derived from the same
table the routes come from, so adding a route cannot silently orphan it.

---

## 3. The shell

- **Header**: brand, nav (desk), search (phone icon / `/` shortcut), bell, theme (desk), account or sign-in, CTA.
- **Rail**: desk-only vertical nav, same `NAV5`.
- **Bottom tabs**: phone, `NAV5` minus `desk: true`.
- **Footer**: newsletter form, link set, theme toggle, disclaimer, data-updated line.
- **Announcements**, **cookie banner**, **maintenance page**.

Specific faults:

1. **The theme toggle is in two places on desk and only the footer on phone.** Put it in one place reachable from everywhere — the account menu — and keep the footer one.
2. **No visible search on desk.** The `/` shortcut is a power-user affordance. Add the field.
3. **The newsletter form sits inside the footer on every screen.** On a page whose job is conversion that is fine; on a settings screen it is noise. Consider rendering it only on reader-facing routes.
4. **`data-updated` in the footer is a trust signal buried in the least-read element on the page.** It belongs near the forecasts it describes.

---

## 4. The design system

This is the strongest part of the product and it is not the problem. Recorded so later work does
not undo it:

- **One family.** Archivo variable, self-hosted (the CSP is `default-src 'self'` with no
  `font-src`, so self-hosting is a requirement, not a preference). Hierarchy is carried by the
  **width** axis — condensed for data labels, extended for headlines — which is native to sports
  setting and rare in this category.
- **Tabular figures** on every number a reader compares down a column.
- **No all-caps kickers.** Position signals instead. Correct: the all-caps label is a template tell.
- **Palette lives in `backend/site_studio.py`**, not in CSS, so an owner can re-theme and every
  token is measured in one place. The live palette is Carbon; Chalk, Apple and Midnight are presets.
- **Motion** is three tokens (`--v2-quick` 140ms, `--v2-move` 260ms, one ease) inside a
  `prefers-reduced-motion` guard, and only where something actually moved.
- **Contrast** is measured in both modes against BLOCK (4.5:1) and WARN (3.0:1) pairs.

Gaps worth closing:

| Gap | Proposal |
|---|---|
| **Spacing** has no named scale; values are written inline per component. | Name the ramp as tokens and use it. Spacing drift is the commonest way a system stops looking systematic. |
| **Radius** has three tokens (`--radius-sm/md/lg`) but components also hardcode radii. | Audit and route all of them through the tokens. |
| **Icons** — `Icon.jsx` is one set, but sizes are passed per call site. | A named size scale (14/16/20/24) so icon weight is consistent beside text. |
| **State views** — `StateViews.jsx` exists but adoption is uneven. | One empty, one loading, one error grammar, adopted everywhere. Each empty state must say what would fill it and offer the action that does. |

---

## 5. Cross-screen consistency questions for the per-screen audits

Recorded here so the separate audits can be compared against one checklist:

1. Does the screen's first viewport answer the question the visitor arrived with?
2. Is every number on it defined somewhere a reader can reach in one tap?
3. Do two numbers on the screen ever answer the same question differently? (This has already
   happened once in production, on the forecast card, with `p_usual` and a counted run both
   labelled "usually".)
4. Does the empty state name what would fill it?
5. Does it work at 390px with no horizontal scroll, in both modes?
6. Is every destructive or outward-facing action guarded in proportion to its consequence?
7. Could a counting tool produce everything on this screen? If yes, the screen is not yet carrying
   the product's argument.
