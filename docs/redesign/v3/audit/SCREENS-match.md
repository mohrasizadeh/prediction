# Audit — Match screen and every overlay

Screens M-01…M-05 (`/match/:id`) and overlays O-01…O-06.
Written 2026-11-06 against the running demo at `http://127.0.0.1:8011`, the code in
`frontend/src/pages/Match.jsx`, `frontend/src/components/MatchCentre.jsx`,
`frontend/src/components/ui/*`, and the styles in `frontend/src/styles/{matchday,v2,base}.css`
and `frontend/src/components/ui/kit.css`.

## How this was seen

`docs/redesign/v3/before/` held only `P-01` and `P-02` when this audit ran, so the M-0* captures
did not exist. I drove Chromium myself (390×844 and 1440×900, dark and light, scrim dismissed),
clicked each tab, opened each overlay, and probed focus order, URL state and overflow. Shots and
probe scripts live under the scratchpad, not in the repository.

Fixtures used: scheduled `b075aafd…` (Team 0 v Team 2, lineups confirmed, 23 cards) and final
`df09ffa4…` (Team 4 3–2 Team 2).

## What I could NOT see — do not mistake this audit for full coverage

| ID | Why not | What I did instead |
|---|---|---|
| **M-01 Live** | The demo holds no in-play fixture. `LiveTab` renders only when `d.live?.sid` exists; no demo match has a `live` object. **Zero pixels of this tab have ever been rendered, by me or by any prior review.** | Read `Match.jsx` `LiveTab`, `MatchEvents.jsx`, `LiveLineups.jsx`, `LiveStatus`, `live_track.py`. Findings below are **code-derived only** and are marked `[code]`. |
| **O-06 Visitor popup** | Owner-authored; no popup exists in demo data, and `GET /api/popups` returns nothing to trigger. | Read `frontend/src/components/Popups.jsx`, `backend/popups.py`, `frontend/src/styles/growth.css`. Findings `[code]`. |
| **M-02 Recap with real content** | The demo's finished round predates the engine run: `cards: 0`, `events: 0`, `recap.scored: 0`. I saw the tab's **empty state only**. | Read `queries.match_detail` / `_recap` and `live_track.evaluate` to work out what would render. Marked `[code]` where it matters. |
| **Forecast settled states (hit / missed chips)** | Require `live_fixtures` rows; none in demo. | `[code]` from `ForecastCard.Track` and `live_track.evaluate`. |
| **O-02 QuickView standalone** | Seen only in its embedded form inside O-01. Its player-page instance (`collapsible`) was not captured. | Partial. |
| **Locked matchup state on M-05** | Demo user is anonymous and `matchup_locked` was false for the fixtures loaded, so the `Empty + ProLock` branch in `Analysis` did not render. I saw `ProLock`/`LockSheet` from the Insights daily cap instead. | Partial. |

---

# Top 10 changes, ranked

Ranked by harm to the reader, then by cost.

| # | Change | Where | Why |
|---|---|---|---|
| **1** | **Draw one pitch, or draw none.** Give `Pitch` a formation-row fallback when `pitch_x`/`pitch_y` are absent, and clamp labels so they cannot overlap. | M-04 | Today all eleven players of each side render as a **single horizontal line of overlapping discs**, 9 of 11 visible, labels colliding ("9 213" over "207"). The tab's only job fails, on phone and desktop alike. Worst render fault in the set. |
| **2** | **Put focus trapping in `BottomSheet`.** `Ui.jsx` already exports `useFocusTrap`; `BottomSheet` does not use it, and nothing marks the page behind `inert`. | O-01…O-05 | Measured: 22 `Tab` presses walk focus out of the sheet and onto the page behind. Violates hard constraint 4 for **every overlay in the product**. One ~8-line fix clears five IDs. |
| **3** | **Make M-02 Recap show the settled forecasts.** The per-forecast outcome already exists in `forecast_outcomes`; `_recap` reduces it to one sentence in the hero and the Recap tab shows none of it. | M-02 | The product's whole claim is that its numbers can be checked. The tab named Recap currently shows a timeline and nothing else — and, with no feed, one sentence that says "still loading" forever. |
| **4** | **Stop telling the same story with five numbers.** One card currently carries `78%`, `USUAL 87%`, `his average 3.3`, `−8`, `8 cleared 2+`; open its sheet and it adds `13 of his last 16` and `usually 87%` again, plus `78%` three more times. | M-03, O-01 | Readers cannot tell which number answers their question. Pick one headline, one comparison, one run, and state the window once. |
| **5** | **Put the tab in the URL.** Measured: `?tab=analysis` is ignored on load; clicking a tab does not push history; Back leaves the page. | M-01…M-05 | No tab is linkable, shareable or back-navigable. It also means `scripts/shots3.js` has been silently capturing the *same* tab five times for every past review. |
| **6** | **Raise the micro-type floor in `CardRun`.** `.v2-cr-m` and `.v2-cr-o` are `font-size: .5rem` (8px) at `wdth 70`. | M-03 | The minutes row and opponent row — the two rows the caption promises explain the strip — are unreadable at 390px. Either make them legible or drop them from the card and keep them in the sheet. |
| **7** | **Give hit/miss a non-colour cue in the run strips.** `CardRun` distinguishes a cleared game from a missed one by `var(--up)` vs grey only. | M-03, O-01 | `Marks.jsx`'s own header comment says "Colour never carries meaning alone." It is the one component in the file that breaks the rule. |
| **8** | **Rebuild LockSheet around the specific thing that was blocked.** | O-04 | Generic "Part of Pro" + three plan bullets. It never names what the reader just reached for, never shows a sample, never says what the free tier keeps. It reads as a wall, not an invitation. |
| **9** | **Label the draw on `WdlBar`, and stop calling two different quantities "Expected goals".** | M-03/M-05 hero | `k-wdl-txt` prints home and away only; the draw share is in the `aria-label` and nowhere on screen. Separately the hero says "Expected goals 1.3 – 1.1" (this fixture) while Analysis says "Expected goals 2.0 – 1.6" (season per game) — same words, different measurement, one scroll apart. |
| **10** | **Make the Live tab show the live claim.** `[code]` The Live tab is events + lineups; the tracking chips that say whether a line has happened live in the **Forecasts** tab, and `/live/{sid}/lineups` is fetched once and never refreshed. | M-01 | During the only 95 minutes the product is urgent, the reader has to leave the Live tab to see whether the forecast is landing, and the lineups never pick up substitutions. |

---

# M-01 — Live `[code only, never rendered]`

**Purpose.** While the match is on, show what is happening and whether the fixture's forecasts are
coming true.

### Inventory

| Item | Verdict | Reason |
|---|---|---|
| `MatchEvents` timeline (`live_events`) | keep | The right spine for the tab. |
| `LiveLineups` (SportAPI starters + bench) | **move** to M-04 | Two lineup renderings in one product (`Pitch` on M-04, `LiveLineups` here) with different shapes and different data sources. The Live tab needs the *changes* (who came off), not a second static eleven. |
| In-play statistics | **missing** | `docs/57` says this tab is "in-play events **and statistics**". `db.live_stats` is populated and already read by `live_track.evaluate` — it is never rendered to a reader anywhere. |
| Live forecast tracking | **move here** | `Forecasts()` owns `track`, so the hit/miss chips only appear under the Forecasts tab. |
| Live score and minute | **add** | They exist only in the hero, which is not sticky; scroll three events down and the score is gone. |
| Empty state | change | `MatchEvents` returns a bare `<p class="muted small">No events yet.</p>` rather than the `Empty`/`EmptyState` component every other surface uses. |

### Hierarchy
As written: events, then a full second lineup listing. It should be: score + minute (sticky) →
what just happened → how our lines are doing → the match's numbers → squad changes.

### Faults
1. `[code]` **No live forecast tracking on the Live tab.** The one thing that makes this product's
   live view different from a free scoreboard sits on the next tab.
2. `[code]` **Lineups never refresh.** `useApi('/live/${sid}/lineups')` has no `{ every }` option
   while the match payload polls every 30 s. Substitutions never reach this panel.
3. `[code]` **Two event vocabularies for one slot.** `MatchEvents.KIND` understands
   `own_goal`, `penalty`, `missed_penalty`, `second_yellow`, `substitution`; the Recap `Events`
   map in `Match.jsx` understands only `goal`, `yellow`, `red`, `sub`. The same slot speaks two
   languages depending on which side of full time you are on, and the minute formatting differs
   too (`45` here vs `45+2'` there).
4. `[code]` **Own goals may be dropped on the Recap side.** `match_extras._kind` returns `None`
   for anything it does not recognise, so a provider that sends `event_type: "own_goal"` loses the
   event entirely while the Live tab would have shown it. Worth a test before this tab ships.
5. `[code]` No loading skeleton for the events list; `LiveLineups` returns `null` on empty, so a
   failed lineup fetch leaves blank space under a loaded timeline.

### Proposals, ranked
1. Move the tracking chips and a one-line "N of M lines we can follow have happened" summary into
   this tab, and leave a pointer on Forecasts. The data is already there (`/live-forecasts`).
2. Add a sticky score/minute strip inside the pane, not only in the hero.
3. Render `live_stats` as the split bars already used by `Form` — the component exists.
4. Replace the second eleven with a "Changes" list (on/off, minute) and let M-04 own the pitch.
5. Unify the two event maps into one module so Live and Recap cannot drift.
6. Poll the lineups endpoint at the same 30 s cadence.

**Before any of this is designed further, wire `backend/tests/live_mock.py` into
`demo_server.py`.** Five tabs, one of which has never been looked at, is not a reviewed screen.

---

# M-02 — Recap

**Purpose.** After the whistle: what happened, and whether the forecasts were right.

### Inventory

| Item | Verdict | Reason |
|---|---|---|
| `ev-sum` goals/cards/subs counters | keep | Cheap, scannable, correct shape. |
| `Seg` All / Goals / Cards / Subs filter | **delete** | Four filters over a list that is rarely longer than a dozen rows. It costs a 44px band and answers a question nobody asks of a finished match. |
| `ev-list` timeline | keep | |
| Half-time score | **move** | It is in the hero (`match-ht`) but not in the tab; the tab is where a recap reader looks. |
| "How our forecasts did: X of Y" | **move into the tab and expand** | Currently one grey sentence in the hero. |
| Per-forecast settled outcome | **add** | `forecast_outcomes` holds `reached` per forecast. Nothing renders it. |
| Empty state copy | **change** | See fault 1. |

### Hierarchy
Today: score (hero) → timeline → nothing. It should be: result → **how we did** → what happened →
the lines, settled.

### Faults (from the render)
1. **The empty state lies.** With no feed the tab says *"Goals, cards and substitutions for this
   match are still loading."* Nothing is loading; the request completed. For a match finished a
   week ago this is a permanent false statement, and it is the entire content of the tab.
2. **The tab delivers none of its stated purpose.** `docs/57`: "what happened, **and how each
   forecast finished**". Not one forecast outcome appears on this tab.
3. `[code]` **Settled chips are gated on live tracking.** `Forecasts()` asks for
   `/live-forecasts` only when `!!d.match.live`. `live_track.evaluate` deliberately keeps
   answering after full time ("still counts once it is over so a line can read missed") — but if
   SportAPI never followed the fixture, the frontend never asks, and the finished match shows no
   outcomes at all. The honesty machinery exists and is switched off by a frontend guard.
4. **Stale badges after full time.** The Lineups tab still carries the ✓ "confirmed" badge and
   the hero's "Lineups confirmed" chip on a match that finished days ago. "Confirmed" is
   pre-match information presented as current.
5. The newsletter block and footer sit directly under a one-paragraph empty state, so the tab
   reads as a marketing page.

### Proposals, ranked
1. Lead the tab with a settled scorecard: *"We published 14 lines. 11 came true."* then the lines
   themselves, each with its forecast percentage and a plain Happened / Did not happen mark, and a
   link to `/track-record`. This is the product's thesis, rendered.
2. Fix the empty-state copy: distinguish *loading*, *no events held for this match*, and *this
   provider does not cover this league*. Never say "loading" after a resolved request.
3. Drop the event filter; keep the three counters.
4. Ask `/live-forecasts` for any `status === "final"` match, not only one with a `live` object.
5. Suppress the lineup ✓ and the "Lineups confirmed" chip once `status === "final"`.
6. Put the half-time score on the timeline, at the 45' divider, where it means something.

---

# M-03 — Forecasts

**Purpose.** Every line we publish for this fixture, grouped so a reader can find the one they
care about.

### Inventory

| Item | Verdict | Reason |
|---|---|---|
| `BuildForMe` + "Tap + on a line to start a combo." | **move** to the foot of the list | A secondary tool is the first thing in the tab, above the content it operates on. |
| By team / By market `Segmented` | keep | Useful, and 32px tall — see fault 7. |
| Minimum-likelihood `RangeSlider` | **change** | Renders as a bare track with a floating black `50%+` pill and no visible label (the `label` prop is screen-reader only). Nobody can tell what it filters. |
| Group headings `Team 0 · 9` | change | The `· 9` count reads as a scoreline next to a club name. Use "9 lines". |
| `ForecastCard` headline % + range | keep | Right anchor, right place. |
| `USUAL / his average / ±N` comparison row | **change** | See faults 2 and 3. |
| `CardRun` LAST 10 strip | **change** | See faults 4–6. |
| Card subtitle (club · opponent · venue) | **fix — it is missing** | See fault 1. |
| `+N more lines · up to 93%` | keep | The single best control on the card. |
| Lineup badge | keep | |
| `k-fc-why` first reason | **change** | Templated and near-identical down the list ("Takes a larger/smaller share of the team's shots than most in the role"), so it reads as boilerplate. |
| Combo `+` button | keep, reposition | Sits beside the headline percentage; see fault 8. |

### Hierarchy
On a 390px phone the hero eats 660px and the tab bar lands at ~850px — **the navigation for the
whole screen is below the fold on first paint**. Then 23 cards at ~730px each make a 10 835px
page. There is no summary, no ordering control, and no way to see the shape of the fixture.

### Faults
1. **Every card on this tab has lost its subtitle.** `MatchCentre.Forecasts` renders
   `<ForecastCard f={f} homeIid={...} />` with **no `teams` prop**, so `fixtureOf` cannot resolve
   `fx.team`/`fx.opp` and the `sub` line comes out empty. Confirmed in the render: cards show
   "Player 1" with nothing beneath it. The same omission empties the fixture line inside the
   sheet (see O-01 fault 3).
2. **The `−8` / `+2` pill has no unit and no label.** Red for "eight points below his own usual",
   on a card whose headline is 78%. Red is the product's loss colour; here it marks a perfectly
   normal forecast.
3. **Three comparisons compete at one weight.** `USUAL 87%`, `his average 3.3` and the pill are
   three different quantities on one row in near-identical type.
4. **8px type.** `.v2-cr-m` (minutes) and `.v2-cr-o` (opponent) are `.5rem` at `wdth 70`. The
   caption promises "minutes above, opponent below" and then renders both illegibly.
5. **Colour-only hit encoding** in `CardRun` (`.v2-cr-g.on > b` green vs grey), against the
   component file's own stated rule.
6. **The headline percentage is repeated inside the strip.** The eleventh dashed column prints
   `78%` again, 120px below the 78% in the header.
7. **Sub-44px targets.** Measured: `fc-group-team` / `fc-group-market` 32px tall;
   `combo-build` 36px; `header-sign-in` 36px.
8. **The `+` combo button sits inside the card's top-right corner**, adjacent to the 2rem
   percentage and inside the main `k-fc-main` button's visual block. Mis-taps are likely.
9. **The wall problem.** 23 cards, most of them "1+ shot" at 86–93% for a different player. The
   brief's own test — *a number a counting tool could produce is table stakes* — is failed by
   roughly two thirds of this tab's content as currently ordered.
10. Light mode: the slider's value pill is solid black on a light background and reads as a stuck
    tooltip; "Build one for me" is a grey secondary button with no hierarchy against the page.

### Proposals, ranked
1. **Open with a fixture summary, not a tool.** Three or four lines: how many forecasts, the one
   that departs furthest from usual, the one with the widest band. Then the list. Move
   `BuildForMe` below.
2. **Sort by departure from usual by default**, not by likelihood. The product's own argument
   (docs/50, docs/56) is that distance from a player's normal game is the comparable quantity;
   today the list is ordered by group and `p`, which promotes truisms to the top.
3. **Collapse the card to one comparison.** Keep the headline % with its band; keep one line of
   the form "usually 87% — tonight 78%"; keep the run strip. Delete `his average` from the card
   (it belongs in the sheet) and give the ± pill a unit and a neutral colour.
4. **Rebuild the run strip for 390px.** Ten columns cannot carry four rows of text. Show value +
   bar on the card; put minutes and opponent in the sheet, where `GameStrip` already draws them at
   reading size with crests.
5. Add a pattern cue to cleared columns (filled vs outlined, or a baseline tick) so colour is not
   the only carrier.
6. Label the slider visibly ("Show lines at least __% likely") and shrink it to its content width
   as the code comment intends.
7. Raise all segmented controls and the combo `+` to 44px, and move `+` to the card footer beside
   "+N more lines".
8. Give the group headings a plain count ("Team 0 — 9 lines").
9. Vary or drop the templated first reason when it is the same sentence as the card above.

---

# M-04 — Lineups

**Purpose.** Who is starting, how likely each one is to start, and what else is worth knowing
before kick-off.

### Inventory

| Item | Verdict | Reason |
|---|---|---|
| `Pitch` | **rebuild** | Broken, see fault 1. |
| "Lineups confirmed" chip + formation string | **change** | Third statement of the same fact on one screen (hero chip, tab ✓, this chip). |
| Per-player chance-to-start `pp-pct` | keep | Genuinely forecast-flavoured; it is the only thing on this tab a scoreboard could not print. |
| `MatchNotes` → "Worth knowing" | **merge** | Duplicates `TeamNews` verbatim, see fault 2. |
| `TeamNews` per-club block | keep, merge the above into it | |
| "No absences known." | change | An empty state rendered as a content row, twice. |
| Referee sentence (`mc-ref`) | **move** to M-05 | `docs/57` places the referee on Analysis. It renders here instead. |

### Hierarchy
Pitch → notes. Correct order. The pitch simply does not work.

### Faults
1. **The pitch collapses to one row.** Confirmed at 390px *and* 1440px: all eleven players of a
   side render on a single horizontal line, two pairs fully overlapping so only nine discs are
   visible, and the shirt/name labels collide ("9 213" over "207", "9 5" over "9 10"). Cause:
   `Pitch` positions by `s.pitch_x` / `s.pitch_y`; when the feed carries neither, `top` resolves
   to one constant and `left` falls back to `pitch_y ?? 0.5` for every player, after which the
   collision nudge only spreads them sideways by 12% a time. There is **no fallback to the
   formation string**, which the page is already printing two lines above.
2. **The same sentence, four times.** "Team 0: In the race at the top." appears under "Worth
   knowing", then "In the race at the top." again under Team 0 in `TeamNews`; same for Team 2.
   `MatchNotes.why` and `TeamNews` read the same `context.why`.
3. **No side labels on the pitch.** Two elevens, distinguished only by the ring colour of the
   avatar. No home/away captions, no crests on the halves.
4. **60% of the pitch is empty** while the players are crushed into a 40px band — on desktop the
   pitch is a 490px-wide column in a 1440px viewport with dead space beside it.
5. The confirmed state is asserted three times and never after full time is it withdrawn (see
   M-02 fault 4).

### Proposals, ranked
1. **Fallback layout.** When coordinates are missing, lay the eleven out from the formation string
   (`4-3-3` → rows of 1/4/3/3). That alone fixes the tab, and the string is already in hand.
2. **Guarantee no label collision** — clamp by row, cap labels to the surname, and drop the shirt
   number to a badge on the avatar rather than a separate word.
3. Merge "Worth knowing" into the per-club block; one sentence, once.
4. Caption each half with the club crest and name, and keep the "chance to start" legend visible.
5. Say the lineup state once (the tab's ✓ is enough) and withdraw it after full time.
6. On desktop, run the pitch and the notes as two true columns instead of a narrow pitch and a
   gap.
7. Move the referee sentence to M-05, where the inventory already says it lives.

---

# M-05 — Analysis

**Purpose.** Everything about the two clubs that explains the forecasts: form, head to head, who
scores first, players, style.

### Inventory

| Item | Verdict | Reason |
|---|---|---|
| `an-jump` chip nav | **change** | See fault 1. |
| "Per game this season" split bars | keep | Clearest object on the tab. |
| `TeamRadar` "Style shape" + "What the spokes mean" | keep | Dashed vs solid distinguishes the teams without relying on colour — the right pattern, and the only place in the match screen that does it. |
| Head to head summary + match list | keep | |
| "Who scores first" pair | keep | |
| "Shots by player · last 10 games" table | **change** | Hard-coded to `stat: "shots"`; no column headers once scrolled; last column clipped at 390px. |
| "Playing style" tactic chips | keep | |
| Referee | **missing here** | Lives on M-04 and in the hero meta. The inventory says it belongs on this tab. |
| Context / stakes | **missing here** | Same: rendered on M-04 as "Worth knowing". |

### Hierarchy
Five sections behind a jump nav is the right idea. The nav is the weak part, and the tab's
promised contents (referee, context) are on another tab.

### Faults
1. **The jump nav clips.** Measured: `.chip` right edges at 418px and 493px in a 390px viewport.
   `.an-jump` is `overflow-x: auto` with `scrollbar-width: none`, so "Players" is cut mid-word as
   "Play…" and "Style" is entirely off screen with no affordance that anything is there.
2. **Three sticky bands.** Header 56px + `.mc-tabs` 48px + `.an-jump` ~46px ≈ 150px pinned, plus
   the 64px bottom bar: a quarter of a 390×844 phone is permanent chrome.
3. **Chip labels do not match their destinations.** "Form" scrolls to a card headed "Per game this
   season". The scent breaks on the first chip.
4. **"Expected goals" means two different things on one screen.** Hero: `1.3 – 1.1` (this
   fixture's forecast). This tab: `2.0 – 1.6` (season average per game). Identical label, one
   scroll apart, no qualifier on either.
5. **The players table loses its headers.** Column heads scroll under the sticky tabs, leaving
   fourteen rows of `5 | 3.4 | 17` with no key, and the last column touches the right edge at
   390px (`.tbl` measured to 425px inside `.tbl-wrap`).
6. The table's team `Seg` scrolls away with the headers, so a reader deep in the list cannot tell
   which club they are reading.
7. The table is shots-only and says so in the heading, but a reader on a cards or tackles forecast
   has no way to switch — while `QuickView`, which does exactly this, is two components away.

### Proposals, ranked
1. Make the jump nav either wrap to two rows or show a scroll affordance (gradient mask plus a
   visible scrollbar on pointer devices); never clip a label mid-word.
2. Unsticky the jump nav on phone, or fold it into the tab bar. Two sticky bands is the ceiling.
3. Rename the chips to their section headings, or the headings to the chips.
4. Qualify both expected-goals figures: "Expected goals tonight" vs "Expected goals per game this
   season".
5. Make the players table sticky-headed and stat-switchable (reuse the `STATS` select from
   `QuickView`), or replace it with a compact `QuickView`-style block.
6. Move referee and context here from M-04 so the tab matches its description, and give the
   referee his own section with the numbers behind the sentence.

---

# O-01 — ForecastSheet

**Purpose.** The full account of one line: who, what, how likely, why, and the run behind it.

### Inventory

| Item | Verdict | Reason |
|---|---|---|
| Sheet title "Player 1 · 2+ shots" | **delete or shorten** | Repeated verbatim 40px below in the head block. |
| `k-fs-head`: avatar, name link, position, club link, fixture, % + band | keep | The player-page link and club link are the right recent addition. |
| Band explainer sentence | keep | |
| "Why" reasons | keep | |
| Three tiles: chance he plays / if he plays / lineup | **change** | Two of three are tautological when `p_play = 100%`; "If he plays 78%" restates the headline. |
| Embedded `QuickView` | **keep, but see question 2** | The most valuable thing in the sheet and the reason the sheet has become a page. |
| "Open <name>'s page →" | **move** | Sits mid-sheet between the filter grid and the context sentences. |
| `rec_k of rec_n` sentence | **change** | Contradicts the QuickView summary above it — see fault 2. |
| `p_usual` sentence | **merge** with the card's USUAL | Same quantity, different words ("usually 87%" vs `USUAL 87%`). |
| "All lines" list | keep, **promote** | See fault 4. |
| Tier record sentence | keep | Honest, and the right place for it. |
| Footer: Save (star) / Note / Share | **change** | No primary action; the star is unlabelled. |
| Tier badge | **missing** | The card says "Watch"; the sheet never states the tier, then quotes "our record on Watch forecasts". |

### Hierarchy
Head → why → tiles → QuickView → page link → context → all lines → record → disclaimer. The
reader's actual next question ("is there a better line for this player?") is answered eighth.

### Faults
1. **The headline number appears four times** in one sheet: head block, "If he plays", the
   QuickView forecast line, and again in the "All lines" list.
2. **Two counts of the same claim disagree in appearance.** QuickView: *"2 or more in 8 of 10
   games."* Four lines later: *"Reached this line in 13 of his last 16 games."* Both are true
   (different windows) and nothing says so.
3. **The fixture line is incomplete.** Rendered: "Forward · Fri 07:00 PM" — no opponent, no
   Home/Away pill, no club. Caused by the missing `teams` prop on M-03 (see M-03 fault 1): inside
   a modal with no page context, the reader cannot tell which match this is.
4. **The sheet opens on a weaker line than the player's best.** Opened on 2+ shots at 78% while
   "All lines" shows 1+ shot at 93%, buried near the bottom.
5. **No focus trap.** Measured: 22 Tabs and focus is on the page behind. Escape and scrim-tap
   dismissal and focus restore all work correctly — only the trap is missing.
6. **The scrim is too thin.** `.k-scrim` is a literal `rgba(5,8,15,.5)` with no blur; page text
   reads clearly through the panel. It is also the same literal in light mode, where 50% near-black
   is too heavy and in dark too light.
7. **Two visual languages for ten games.** The card draws `CardRun` (bars, value, minutes,
   opponent, dashed eleventh column); the sheet draws `GameStrip` (value, bar, minutes, crest, no
   eleventh column). The component comment says "the two must agree, because a reader who taps a
   card expects the thing that grows to be the thing they tapped." They do not agree.
8. On desktop the sheet is `max-width: 560px` centred in a 1440px viewport, which makes the
   QuickView filter grid (a select plus three segmented rows plus a checkbox) cramped while the
   screen is two-thirds empty.
9. Footer has three equal-weight controls and no primary.

### Proposals, ranked
1. **Lead with the ladder, not one rung.** Put "All lines" directly under the head block with the
   opened line marked, so the first thing the reader sees is the shape of the player's night.
2. Trap focus (fix once in `BottomSheet`, clears O-01…O-05).
3. Delete the duplicate title and the "If he plays" tile when it equals the headline; keep
   "Chance he plays" and the lineup state.
4. State one window, once: if the sheet shows both 10 and 16 games, label each ("last 10", "this
   season").
5. Pass `teams` from M-03 so the fixture line and card subtitles resolve.
6. Move "Open <name>'s page" to the footer as the primary action, beside Save and Share.
7. Show the tier badge in the head, so the record sentence has a referent.
8. Make the two run renderings one component at two sizes.
9. Deepen the scrim and make it a token with separate light/dark values.
10. On ≥1024px, let the sheet take 720px and run the QuickView filters as a single row.

---

# O-02 — QuickView

**Purpose.** Change the market, the line, the window and the venue, and see the player's run
against that choice.

### Inventory

| Item | Verdict | Reason |
|---|---|---|
| Summary "N or more in H of K games." | keep | |
| `v2-qv-fc` next-match forecast line | keep | Resolving the percentage off the stored ladder rather than the one stored line is the right call and is well commented. |
| `v2-qv-fc--none` "No forecast for X next match" | keep | Correctly prefers an explicit absence to silence. |
| `GameStrip` | keep | |
| Stat `Select` | keep | |
| Line / Window / Venue `Seg` rows | **change** | Three stacked full-width segmented rows inside a modal; the line row can reach six options (1+…6+) and wraps. |
| "Started only" checkbox | keep | |
| `collapsible` toggle | keep (player page only) | |

### Hierarchy
Summary + forecast → strip → controls. Right order: the answer before the machinery.

### Faults
1. **It is a filter console inside a modal.** Inside O-01 at 390px the controls occupy roughly a
   third of the sheet's height, pushing the "All lines" ladder and the record below two scrolls.
2. **Six line options at 390px.** The `1+ … 6+` row fills the width edge to edge with ~52px
   targets; adjacent mis-taps re-fetch the history.
3. **It re-fetches on every control change** (`useApi` keyed on `last`/`started`/`venue`) with no
   optimistic state, so the strip blanks to `Loading` on each tap.
4. **Its summary can contradict the sheet around it** — see O-01 fault 2.
5. Changing the stat silently relocates the line (`useEffect` snaps to the nearest rung). Correct
   behaviour, but it happens with no notice, so the displayed percentage changes for two reasons
   at once.

### Proposals, ranked
1. Collapse the controls behind a single "Change the line" disclosure **inside the sheet** (the
   component already supports `collapsible`; the sheet passes the default `false`).
2. Keep the previous strip visible while refetching instead of swapping in `Loading`.
3. When the line snaps on a stat change, say so in the summary line for one render.
4. Cap the line row to five rungs with overflow into the select, or make it a stepper.

---

# O-03 — FilterSheet

**Purpose.** The phone filter surface for Insights and the Finder.

**Not used anywhere on the match screen.** M-03's grouping and likelihood floor sit in an inline
`v2-bar` instead. That is a deliberate divergence worth closing in one direction or the other.

### Inventory

| Item | Verdict | Reason |
|---|---|---|
| `FilterGroup` label + children | keep | |
| Footer: Reset / "Show N results" | keep | Live count in the primary action is the right pattern and the best-executed control in the overlay set. |
| Tier / Position chip groups | **change** | No visible selected state and no explicit "Any" option, so "none selected" and "all selected" look identical. |
| "At least 0% likely" slider | change | At its default of 0 it filters nothing and takes the most vertical space in the sheet. |
| "Lineup confirmed only" checkbox | keep | |

### Faults (render)
1. **Scrim too thin again** — the page's sentence filter reads straight through the panel
   ("Showing all markets for every player at every club…" is legible behind the controls).
2. **Selected state is invisible on the chip groups.** Strong / Solid / Watch and GK / DEF / MID /
   FWD render identically whether chosen or not; only Venue shows a filled "All".
3. No divider or consistent rhythm between groups; the "Tier" heading collides visually with a
   page chip bleeding through.
4. No focus trap (inherited from `BottomSheet`).
5. The sheet height floats to its content, so it opens at a different height from O-01 and O-04
   with no shared rule.

### Proposals, ranked
1. Give the chip groups a filled selected state and an explicit "Any" chip.
2. Deepen the scrim (shared fix with O-01).
3. Hide or demote the likelihood slider until it is moved off 0, or start it at a meaningful floor.
4. Adopt this sheet on M-03 — or drop it and make Insights use M-03's inline bar — so the product
   has one filtering idiom.

---

# O-04 — LockSheet

**Purpose.** What a non-subscriber sees instead of a number they cannot have.

### Inventory

| Item | Verdict | Reason |
|---|---|---|
| Title "Part of <plan>" | **change** | Says what the reader does not have, not what they were reaching for. |
| Plan tagline | keep | |
| Bullet list from `pro.bullets` | **change** | Generic plan bullets, identical whatever was locked. |
| Trial line | keep | |
| "See Pro · CA$9.99 a month" primary | keep | Honest to lead with the price. |
| "Not now" | keep | |
| What was actually blocked | **missing** | |
| A sample of the locked thing | **missing** | |

### Faults
1. **It never names the thing.** Triggered from "Your plan shows 20 insights a day", the sheet
   says "Part of Pro" and lists "Unlimited Finder / Tactical matchup tab / Alerts and CSV export"
   — one of which is unrelated to what was blocked. The reader has to remember what they tapped.
2. **No preview.** Nothing is shown, blurred, counted or sampled. There is no evidence that what
   is behind the wall is worth 9.99.
3. **No statement of what stays free.** For a product whose differentiator is honesty, the
   boundary is drawn with a padlock and a price and nothing else.
4. The sheet opens to roughly 40% of the viewport while O-01 opens to 88%; same container, no
   shared height rule, so the lock reads as a smaller, lesser interruption.
5. No focus trap (inherited).
6. `ProLock`'s inline tag is 14px with a padlock glyph and sits inside grey body copy; as a
   tappable control it is easy to miss and under 44px.

### Proposals, ranked
1. **Title the sheet after the thing.** "The tactical matchup for Team 0 v Team 2" / "14 more
   forecasts on this fixture". Pass the trigger's subject into `title` — the prop already exists
   and is mostly unused.
2. **Show a real sample, honestly.** One full locked forecast, complete, with the rest counted:
   "this is one of 14." Blurring a number implies a number exists; showing one proves it.
3. **State the free boundary in the sheet.** "Free: 20 lines a day, every fixture, the whole
   track record." A boundary a reader can respect converts better than a padlock.
4. Make the bullet list specific to the locked capability, with the rest of the plan behind "See
   everything in Pro".
5. Give lock sheets a consistent height and a consistent entry animation with the other sheets.
6. Raise `ProLock` to a 44px control with a visible affordance.

---

# O-05 — BottomSheet

**Purpose.** The shared container every sheet in the product sits in.

### Inventory

| Item | Verdict | Reason |
|---|---|---|
| Portal to `document.body` | keep | |
| Scrim mousedown-to-close | keep | Correctly checks `e.target === e.currentTarget`. |
| Escape to close | keep | |
| `document.body.style.overflow = "hidden"` | keep | |
| Focus into sheet on open, restore on close | keep | Measured working: focus returns to the opener. |
| `role="dialog" aria-modal="true" aria-label={title}` | keep | |
| Grab handle | keep | |
| Header h2 + close button | keep | |
| Scrolling body, optional footer | keep | |
| **Focus trap** | **missing — add** | |
| **`inert` / `aria-hidden` on the background** | **missing — add** | |

### Faults
1. **No focus trap.** Measured: 22 Tabs from an open ForecastSheet put focus on the document
   behind. `aria-modal="true"` tells assistive technology the rest of the page is inert while the
   keyboard proves it is not. `Ui.jsx` already contains a working `useFocusTrap` that this
   component does not call. **This is the single highest-leverage fix in the audit** — it clears
   O-01 through O-05 in one edit.
2. **Background is not inert.** `data-testid="match-page"` carries neither `inert` nor
   `aria-hidden` while a sheet is open; the page behind is clickable by keyboard.
3. **`body.style.overflow` is set directly**, so two overlapping sheets (a `ProLock` inside a
   ForecastSheet, which `Analysis` can produce) restore scrolling when the inner one closes.
4. **No scroll-position lock on iOS** — `overflow: hidden` alone does not hold the page on Safari;
   the background scrolls under the sheet.
5. **Scrim is a literal colour** (`rgba(5,8,15,.5)`) shared by both themes — too weak in dark, too
   heavy in light, and not a token.
6. **No height contract.** `max-height: 88vh` with content-sized panels means sheets open to wildly
   different heights (O-01 88%, O-04 40%) with no detent or snap.
7. `aria-label={title}` duplicates the visible `<h2>`; `aria-labelledby` pointing at the heading
   would be the correct wiring and avoids drift.
8. No swipe-to-dismiss, despite the grab handle promising it.

### Proposals, ranked
1. Call `useFocusTrap`, and set `inert` on the app root while open. One fix, five IDs.
2. Reference-count the body scroll lock so nested sheets behave.
3. Replace the literal scrim with light/dark tokens, and add a `backdrop-filter` (hig.css already
   disables it for `.overlay`; decide once and apply to both).
4. Define two heights — a compact detent for short sheets and the 88vh detent for long ones — and
   make `LockSheet` and `FilterSheet` use the compact one.
5. Make the handle do something, or remove it.
6. Switch to `aria-labelledby`.
7. Resolve the two overlay systems: `.overlay` (z 60, blur, `rgba(4,7,14,.62)`) and `.k-scrim`
   (z 80, no blur, `rgba(5,8,15,.5)`). As it stands a modal visitor popup (z 60) opens *beneath*
   an open forecast sheet (z 80) and a slide-in popup (z 55) beneath both.

---

# O-06 — Visitor popup `[code only, never rendered]`

**Purpose.** Owner-authored message to a visitor, triggered by path, delay, scroll, page count,
exit intent or a click target.

### Inventory (from `Popups.jsx`)

| Item | Verdict | Reason |
|---|---|---|
| `PopupHost` candidate fetch + frequency memory | keep | Sound; localStorage + sessionStorage caps are reasonable. |
| Trigger types | **change** | `exit_intent` is desktop-only in practice, see fault 3. |
| `PopupView` modal / banner / slide-in kinds | keep | |
| Close button (`d.show_close`) | **change** | Owner-disableable, see fault 1. |
| `backdrop_close` | **change** | Also owner-disableable. |
| Escape (`useEsc`) | keep | |
| `role="dialog" aria-modal` for modal kind only | **change** | Non-modal kinds get `role="region"`, which is not announced. |
| `PopupForm` with explicit consent checkbox | keep | Submit is disabled until consent — correct. |
| `track()` view / dismiss / click | keep | |
| Image with `alt` default `""` | keep | Correct for decorative. |
| Focus trap | **missing — add** | |

### Faults
1. **An owner can author an undismissable popup.** `show_close: false` plus
   `backdrop_close: false` plus no buttons leaves Escape as the only exit — which does not exist
   on a touch device. This is a hard-constraint-4 violation that the admin UI permits. It must be
   impossible to save.
2. **No focus trap, and no restore.** `ref.current?.querySelector("input,button,a")?.focus()`
   moves focus in; nothing brings it back on close, and Tab leaves immediately. A banner-kind
   popup is `role="region"` with no live-region announcement, so a screen-reader user may never
   learn it appeared.
3. **`exit_intent` never fires on a phone.** It listens on `mouseout` with `clientY <= 0`. An
   owner scheduling an exit-intent popup to a mobile audience gets silence and no warning.
4. **Z-order collision with sheets.** `.pop--slide_in` and the banners are z 55, the modal
   `.overlay` is z 60, `.k-scrim` is z 80. A popup firing while a forecast sheet is open appears
   underneath it: visible through the scrim, unclickable.
5. **`btn--${b.style}`** interpolates owner data into a class name; an empty value yields
   `btn--undefined` and an unstyled button.
6. `useEsc(true, onClose)` is unconditional, so Escape dismisses even a banner the owner marked
   non-dismissable — inconsistent with fault 1 but in the reader's favour; the inconsistency
   should be resolved deliberately.
7. Copy is textguard-checked (`popups.py:187` runs `textguard.find` over `content` and `form`) —
   **good**, and the one place the betting-vocabulary constraint is enforced on owner input. Worth
   keeping when this is reworked.

### Proposals, ranked
1. Make an undismissable configuration impossible at save time in Admin → Popups, and always
   render a close affordance on touch regardless of `show_close`.
2. Trap focus and restore it; use the same `BottomSheet` machinery rather than a second overlay
   implementation.
3. Give banner kinds `role="status"` or `aria-live="polite"` so they are announced.
4. Disable `exit_intent` on touch in the admin editor, with a visible note, and add a
   scroll-depth default in its place.
5. Suppress popups entirely while any sheet is open, or raise them above z 80 — decide, do not
   leave it to stacking order.
6. Whitelist `b.style` against the known button variants.
7. **Put a popup in the demo data so this screen can be reviewed like the rest.**

---

# Three cross-cutting questions

## 1. Five tabs on one fixture — is that right?

**No. It is three tabs with a fourth that only exists for ninety minutes.**

The real reading order is: **Forecasts** (the product), **Lineups** (the one pre-match fact that
changes a forecast), **Analysis** (the evidence, for the minority who want it). Live and Recap are
the same slot at two moments in time and should stay one slot — that part is right, and nobody is
confused by it, because a fixture is only ever in one state and the tab is simply named for it.

What *is* confusing is subtler and worse:

- **The default tab moves.** Before kick-off the reader lands on Forecasts; during the match on
  Live; after it on Recap. Three different first screens for the same URL. A reader who opens the
  same fixture twice gets different content and has to re-orient.
- **The tab set changes size.** Three tabs before kick-off, four during and after. The Forecasts
  tab physically moves left-to-right as the match starts. Muscle memory is destroyed exactly when
  the reader is checking most often.
- **Content sits on the wrong tab.** Referee and context are on Lineups though the inventory and
  the reader both expect them on Analysis. Live forecast tracking is on Forecasts though it
  belongs on Live. The Recap tab holds none of the recap.

Recommendation: keep one match-state slot (Live/Recap) but make it **always present and always
first**, showing kick-off time and the fixture summary before the match, the live state during,
and the settled scorecard after. Then Forecasts, Lineups, Analysis in fixed positions. The tab set
never changes shape; only the first tab's content does. And put the tab in the URL so a reader can
be sent to one.

## 2. The sheet versus the player page

**A modal is the wrong container for what this has become — but the answer is not "navigate instead".**

The code comment is honest: the sheet *is* the player page for most readers. That is exactly the
problem. It now carries identity, club, fixture, a reason list, three tiles, a full filterable
match-history console, a link out to the real player page, two context sentences, the whole ladder
of lines, the tier record and the disclaimer. On a 390px phone that is four screens of scrolling
inside a panel with no URL, no back button, no shareable state, no title in history, and — today —
no focus trap. Everything a reader does inside it (switch to 3+, filter to away games) is lost the
moment they close it. And on desktop all of it is squeezed into 560px while two-thirds of the
viewport is dimmed and empty.

But navigating on tap would be worse for the common case, which is genuinely a peek: *is this 78%
interesting or not?* Make the reader lose their place in a 23-card list to find out and they stop
tapping.

**Split it by question.**

- **The sheet answers "is this line interesting?"** Identity, the number with its band, the tier,
  why, the run, and the ladder of other lines for this player. Six objects, one screen, no
  controls. That is a peek, and it is what a bottom sheet is for.
- **The player page answers "tell me about this player."** The QuickView console, the window and
  venue filters, the season, notes, every market. It has a URL, so a filtered view is linkable and
  survives the back button.
- **Move "Open <name>'s page" into the sheet footer as the primary action**, so the escalation is
  obvious rather than buried mid-scroll.

The one thing that must not happen is what happens now: the sheet grows a second copy of the
player page, the two drift apart in how they draw the same ten games, and the modal becomes the
primary surface of the product while remaining unaddressable.

## 3. The locked state

**It makes a reader feel blocked. It does not make them want to subscribe.**

What they get is a padlock, a generic title, three bullets that may have nothing to do with what
they reached for, and a price. Nothing shown, nothing counted, nothing sampled. The reader is asked
to pay 9.99 a month on the strength of the phrase "The full picture."

This is a particularly bad fit for *this* product, because its whole pitch is that it is honest
about uncertainty and shows its record. The lock screen is the one place it refuses to show
anything.

**A better boundary, consistent with the honesty constraints:**

1. **Name what was blocked, in the title.** Not "Part of Pro" but "The tactical matchup for Team 0
   v Team 2" or "14 more forecasts on this fixture". The `title` prop already exists.
2. **Give one away, whole.** One complete locked forecast — number, band, reasons, run — and then
   count the rest: "this is 1 of 14." A real example is the only honest proof that the rest is
   worth having. Blurring a number asserts a value without showing it; showing one proves it.
3. **State what stays free, plainly.** "Free gives you 20 lines a day, every fixture, and the whole
   track record." A boundary a reader can respect is more persuasive than a boundary that pretends
   the free tier is a trap.
4. **Point at the track record, not at adjectives.** The product has a page whose entire job is to
   show whether the numbers can be trusted. The strongest sentence on this sheet is a measured
   one: "Strong forecasts came true 79 of the last 100 times" with a link to `/track-record`. No
   superlatives, no betting vocabulary, and nothing a competitor can copy without the record to
   back it.
5. **Match the ask to the moment.** Hitting a daily cap at line 21 is not the same as opening the
   matchup tab. Today both get the same sheet.

---

## Appendix — hard-constraint compliance of what is there now

| Constraint | Status |
|---|---|
| 1. No betting vocabulary in reader copy | **Pass** in everything I read on these screens. `popups.py` runs `textguard.find` over owner-authored popup copy, which is the right place for it. |
| 2. Colours as `var(--token)` in components | **Pass** in components. The scrim literal `rgba(5,8,15,.5)` lives in `kit.css`, not a component, but it is the one colour in these screens that should be a token and is not. |
| 3. No renamed/removed class names or `data-testid` | Nothing in this audit proposes a rename; everything is additive. |
| 4. 390px, no horizontal scroll, light and dark; overlays trap focus and dismiss | **Partial fail.** Document `scrollWidth` stays 390 on all tabs, and light/dark both render — but M-05's jump chips (to 493px) and players table (to 425px) sit outside the viewport behind hidden scrollbars, and **no overlay in the product traps focus**. |
| 5. The product FORECASTS | **Partial fail on M-03.** Roughly two thirds of the 23 cards on the demo fixture are "1+ shot" at 86–93% — numbers a counting tool produces. The departure-from-usual machinery that would distinguish a finding from a truism exists on every card and is not used to order the list. |
