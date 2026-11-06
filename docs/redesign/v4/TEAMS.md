# Following a club — every surface, designed

**Scope.** The journey a reader takes when a card is about a **club** rather than a player:
the team `ForecastCard` → the team `ForecastSheet` → **P-12** the club page → **P-11** the league
page where clubs are listed → **M-05** Analysis and the match hero.

**Date.** 2026-11-06. **Branch.** `v4-teams-and-sheet`.
**Method.** Read the components and `backend/queries.py`; then rendered every screen myself against
the demo server on `127.0.0.1:8011` at 390×844 and 1440×1000, dark and light, with Playwright, and
measured the DOM. Every measurement below was taken from those renders, not estimated.

---

## 0. What the club page is for

> **The club page says what we expect this club to do in its next match, and shows the season
> behind that expectation.**

That sentence is writable today only because of work already in the working tree (§0.1). Before it,
the honest sentence was *"the club page is a squad list with a style chip on top"*, and that was the
first finding of `docs/redesign/v3/audit/SCREENS-entity.md`.

Everything in this document is measured against that one sentence. A block earns its place if it
helps a reader answer **what will they do next** or **why should I believe it**. A block that
answers neither is the season archive, and the season archive goes below the fold.

### 0.1 What has already landed, and is not re-proposed

`git diff` on this branch (uncommitted) already contains a first pass at audit items #1 and #2:

| File | Change | Status |
|---|---|---|
| `backend/queries.py` `team_detail` | loads `scope:"team"` forecasts for `next[0]`, `_decorate`s them, `group_cards(..., "team")`, returns `forecasts` + `cards`; attaches `probs` and `best_line` to every `next` row | **keep**, extend per §8 |
| `frontend/src/pages/Team.jsx` | a `<section data-testid="team-next">` with `<h2>What we expect next match</h2>` and a `fgrid` of `ForecastCard`s, placed between the head and the tabs | **keep**, restructure per §5 |
| `frontend/src/components/ui/Marks.jsx` | `CardRun`'s caption hint now says `"opponent below"` when no game carries minutes | **keep**, extend per §3 |

The renders in this document are of that state, so the faults listed are the *remaining* ones.

Two notes on the demo data, so nobody chases ghosts:

- **No `match_*` forecast exists in the demo set.** `GET /api/insights?stat=match_corners` returns
  `[]`; the whole set is `{(player,shots):6, (player,tackles):2, (team,corners):4, (team,shots):4,
  (team,sot):4}`. So **the two-crest branch of `ForecastCard`'s `Who` has never been rendered** and
  cannot be signed off here. It belongs beside P-03 and P-14 on the docs/57 §7 "never seen with
  content" list.
- **No club in the demo set has a crest image.** Every `Crest` renders the generic shield, which is
  why §4 can state as fact that `GameStrip` cannot name an opponent without one.

---

## 1. The ranked change list

Ranked by how much of the journey each one repairs, not by effort. **C** = correctness (the screen
is currently saying something untrue or unreadable); **G** = gap.

| # | Change | Surface | Kind | Reason |
|---|---|---|---|---|
| 1 | **Fix `GameStrip` when there are no minutes.** `.pgs-g` declares `grid-template-rows: auto auto var(--bar-h) var(--foot-h)`, and `GameStrip` only renders `.pgs-min` when some game has minutes. A club never has minutes, so every child shifts up one row: the crest lands in the 54 px bar row and the `sr-only` span takes the 26 px foot row. `.v2-gs-rule` is positioned `bottom: calc(var(--foot-h) + var(--rule) * var(--bar-h))` from the bottom of `.pgs-row`, so **on every team sheet the line is drawn below all ten columns**. The strip says ten games out of ten cleared 3+; the caption under it says six. | Sheet, and any club `GameStrip` | **C** | The one evidence graphic on the team sheet currently contradicts its own caption, in the reader's favour. Verified at 390 and 1440, dark and light. |
| 2 | **Stop the team sheet calling a club "him".** `ForecastSheet` prints `A player like him in a fixture like this: usually 79%` for `f.p_usual` with no scope test. Rendered verbatim on the Team 9 sheet. | Sheet | **C** | One line of copy that tells the reader the product does not know what it is looking at. |
| 3 | **Give the club the interrogation the player has.** `QuickView` takes `playerId` only, so `ForecastSheet` falls back to a fixed `GameStrip` and the club page has no evidence block at all. Add `teamId` (§4.3, §5.4) and `venue` to `/teams/{id}/history`. | Sheet, P-12 | **G** | The reader's next question after "3+ corners, 87%" is "what about 4+, and only away" — the single biggest asymmetry between the two entity types, and the reason the club sheet is a dead end. |
| 4 | **Rebuild the club head as `v2-ph2`,** with the next fixture, league position and form-against-expectation in it. Today `.phead` is `align-items:center`, so the 45 px crest centres against a three-row column and sits level with the form pills while the name floats with nothing beside it. Measured: club head **141 px** at 390 against the player head's **261 px**. | P-12 | **G** | Two entity pages, one family, and only one answers "who do they play next" above the fold. Every class needed already exists. |
| 5 | **Fill the team card's empty slots with three fields the engine already stores and nobody draws:** the venue of each past game (`run[].home`) in the blank minutes row, `expected` beside `expected_usual`, and `span` as a named chip. | Card (and sheet) | **G** | The team card is 358×367 px against the player card's 358×384 px — it reserves the whole frame and draws one row fewer. `span` is, per `docs/redesign/v3/audit/METRICS.md` finding 2, "the single most valuable number in the engine", computed on every line, used only as a hidden gate. |
| 6 | **Move the club page's "what we expect" above everything and demote the squad.** Default view today is 4,767 px at 390 of which the forecast block is ~1,100 px and the 14 season-total squad cards are **2,242 px**, with the Goals and Cards columns `0` on all fourteen. | P-12 | **G** | 47 % of the page is a table where a third of the cells are a zero. |
| 7 | **Fix `MatchRow` at 390.** Grid areas `"t t t" / "h s a"` put the `v` at the far right of the home club's line: `Team 0 ———— v` / `———— Team 2`. Row height **162 px** at 390 (81 px at 1440), and the date string repeats on all six rows of a round. | P-11, P-12 Fixtures | **C** | Reads as a typo on the first screenful of the league page, and the club page now inherits it. |
| 8 | **Give P-11's Teams tab a forecast and a route onward.** 14 stat chips over 7 rows plus two segmented controls plus a legend = **~470 px of controls before the first club row** on a 2,386 px page, and the list is one season average per club. | P-11 | **G** | The only screen in the app whose job is "here are the clubs" says nothing about any of them that the engine produced. |
| 9 | **Put the club's own line into M-05 Analysis, and make the club names there links.** Analysis is **4,072 px** at 390; the club appears five times (Form caption, radar legend, H2H tiles, first-goal empty states, the Shots-by-player tab strip) and is a link in none of them, while `scope:"team"` forecasts for that exact match sit one tab away. | M-05 | **G** | The deepest club surface in the app has no club forecast and no way to the club page. |
| 10 | **Serve the league table from the server** (`queries.league_table`) and read the club's row on P-12. | P-11, P-12 | **G** | `Standings` fetches 400 fixtures to the browser to compute what one `$group` does; P-12 needs one row of it and currently cannot have it at any price. |

---

## 2. Design principles this uses

1. **One card object everywhere.** A card a reader taps on Insights must be the same object on the
   club page and inside the sheet. Changes to `ForecastCard` are *additive props*, never a second
   component. (`frontend/src/pages/Player.jsx` carries the scar of the alternative in a comment.)
2. **Fill empty slots with fields that exist and are drawn nowhere**, before inventing anything.
   §8 lists them. Three of them (`span`, `expected`, `run[].home`) close the whole of
   the team card's deficit without a line of new modelling.
3. **A number a counting tool could produce is table stakes.** `Apps / Min / Goals / Shots /
   Tackles / Cards` is a counting tool. `span`, `p_usual`, `expected`, `form_fp` and the radar
   percentile are not, and all five are already stored.
4. **Reuse before invention.** Everything in §3–§6 is built from `ForecastCard`, `CardRun`,
   `GameStrip`, `QuickView`, `WdlBar`, `MatchRow`, `TierBadge`, `v2-ph2`, `v2-nextfx`, `Empty` /
   `Loading` / `ErrorBox`, `Tabs`, `Segmented`. Four things are invented and each is flagged
   **[NEW]** with its reason.

---

## 3. Surface A — the team forecast card

### 3.1 Current state, measured

Rendered from `/insights`, the Team 9 `3+ corners` card.

| | Team card | Player card |
|---|---|---|
| Size at 390 | **358 × 367 px** | 358 × 384 px |
| Size at 1440 (3-up `fgrid`) | 375 × 367 px | 375 × 384 px |
| Avatar slot | `Crest` 44 px (generic shield in demo) | `PlayerAvatar` 44 px |
| Subtitle | `vs Team 6 · away` — truncates to `vs Team 6 · aw…` inside the club page's `fgrid` at 390 | `Team 4 · vs Team 11` |
| `.v2-cmp` row | `USUAL 79%` · `their average 4.8` · `+7` | `USUAL 79%` · `his average 1.5` · `+10` |
| `CardRun` minutes row (`.v2-cr-m`) | **empty for all ten past columns** (~10 px blank band); holds the likelihood only in the eleventh | `81' 79' 90' …`, `.low` amber under 70' |
| `CardRun` caption | `LAST 10 · 6 cleared 3+ · opponent below` | `LAST 10 · 9 cleared 1+ · minutes above, opponent below` |
| Footer right slot | **empty** | `Confirmed starter` |
| `k-fc-vs` basis line | absent (`f.scope === "player"` gate) | `Assumes he plays` |

So the team card reserves 96 % of the player card's height and draws two fewer rows of
information. Three things are true at once: there is room, there is nothing in it, and the engine
is already shipping fields that would fill it.

Two further faults visible in the render:

- **`abbr()` vs `Crest` disagree.** `CardRun` falls back to `abbr(opp.name)` and shows `T4 T2 T11
  T0 T7 T5 T3 T1 T10 T8`. `GameStrip`, in the sheet the same card opens, has no fallback and shows
  ten identical blank shields. Same ten opponents, two components, one of them mute.
- **On the club page, the identity row is pure repetition.** At 1440 the club name appears four
  times in one screenful (H1 + three cards) and the subtitle is identical on all three cards,
  because all three share the club, the opponent and the kick-off. Only the market differs.

### 3.2 The design

Three additions, all driven by fields already on the row. No class renamed, no `data-testid`
removed; everything below adds.

**A1 — venue marks in the empty minutes row.** `queries._usual` already builds
`run[] = {opp_iid, m, v, home, opp}` and `home` is drawn nowhere.

```jsx
// Marks.jsx, CardRun, inside the games.map
<i className={"v2-cr-m" + (g.m != null && g.m < 70 ? " low" : "")}>
  {g.m != null ? `${Math.round(g.m)}'` : g.home == null ? "" : (g.home ? "H" : "A")}
</i>
```

- Caption hint becomes `minutes above, opponent below` / **`home or away above, opponent below`** /
  `opponent below`, chosen by which of `m` and `home` is present.
- `aria-label` gains `"…, at home"` / `"…, away"` per game.
- **Why.** A club's corner and shot counts swing with venue more than with anything else on the
  card. The strip today offers `2 1 3 2 4 4 1 6 4 10` with no way to see that the four biggest were
  away, which is exactly the kind of misreading the minutes row was added to prevent for players.
  Zero backend cost; the field is already over the wire.
- **New CSS:** none. `.v2-cr-m` is `font-size:.5rem; font-variation-settings:"wdth" 70,"wght" 600`
  and a single letter fits in the 44 px-wide column at 390 with room to spare. Add one rule for the
  away state so colour is never the only signal:
  `.v2-cr-m[data-at="a"] { text-decoration: underline; text-underline-offset: 2px; }` — and set
  `data-at` alongside the text.

**A2 — close the count sentence: `tonight` beside `usually`.** `f.expected` (the expected count
*for this fixture*, opponent and all) is stored on every forecast, is in the API payload today
(`expected: 6.0586`), and is rendered nowhere. `f.expected_usual` is rendered as *"their average"*.

```jsx
{f.expected_usual != null && <span className="v2-cmp-a" data-testid={`${id}-usual`}>
  {f.expected != null && <><b>{f.expected.toFixed(1)}</b> tonight · </>}
  usually <b>{f.expected_usual.toFixed(1)}</b>
</span>}
```

- Reader copy: `6.1 tonight · usually 4.8`.
- **Why.** `METRICS.md` §4.2 and its row on `expected_usual`: *"'his average' is wrong. It is not
  an average of anything he has done"*. The current label invites the reader to compare 4.8 with
  the strip's own numbers (2, 1, 3, 2, 4, 4, 1, 6, 4, 10 — mean 3.7) and find they disagree. With
  `tonight` beside it the pair is a claim in the same units as the strip, and it is the `p` vs
  `p_usual` claim restated in counts, which is what a club-level market is actually about.
- This improves the player card identically. Ship it for both; the team card is where the room is.

**A3 — the span chip. [NEW element, existing field]** `span` is computed on every row
(`0.072` on the card above), used only by `queries.is_trivial` behind `engine.min_span` (default
**0.06**), and shown nowhere in the app.

```jsx
{f.span_pts != null && <span className={`v2-cmp-s is-${f.span_band}`} data-testid={`${id}-span`}
      aria-label={`This line moves about ${f.span_pts} points depending on the opponent.`}>
  Opponent <b>{f.span_pts} pts</b>
</span>}
```

- Sits on the existing `.v2-cmp` flex row, between `.v2-cmp-a` and `.v2-cmp-d`. The row is
  `flex-wrap: wrap`, so at 390 it becomes two lines: `USUAL 79% · 6.1 tonight · usually 4.8` /
  `Opponent 7 pts · +7`. Measured spare height: the `.v2-cmp` row is 18 px; a second line costs
  28 px, which the card can afford twice over against the player card.
- `span_band` comes from the backend (§8, **B2**) so the threshold lives beside the gate that uses
  it and the two cannot drift: `low` (< `min_span`), `normal` (1–2×), `high` (≥ 2×).
  `.v2-cmp-s.is-high { color: var(--text2); }` and a 1 px `var(--border-strong)` outline; `is-low`
  renders nothing at all — a line that cannot move is the gate's business, not the reader's
  (`METRICS.md` §4.1 form 3).
- **Why.** `docs/56` is the product's argument: insensitivity, not likelihood, is what makes a line
  useless. The app acts on that belief silently on every card. The chip is the smallest honest way
  to let the reader see the argument, and it is the one number on the card a counting tool cannot
  produce. For clubs it is also the most load-bearing: `3+ corners` reads as a truism until the
  card says the line moves 7 points by opponent.

**A4 — give `GameStrip` the `abbr` fallback `CardRun` already has**, so the two drawings of the
same ten games agree when crests are missing (§4.2).

### 3.3 What is deliberately *not* changed

- The identity row stays. It repeats the club name on the club page, and that is the cheaper of the
  two costs: breaking "the card is the same object on every screen" is the dearer one. The
  truncation is fixed by shortening the string, not by removing the row — see **A5**.
- **A5 — subtitle.** `ForecastCard`'s `sub` for a team currently joins `vs ${opp.name}` and a
  bare lowercase `home`/`away`. Change to one phrase: `Away at Team 6` / `At home to Team 6`.
  Shorter, grammatical, and it no longer truncates at 390 inside a three-up `fgrid`.

### 3.4 Components

| Block | Component | Change |
|---|---|---|
| the card | `components/ui/ForecastCard.jsx` | A2, A3, A5 — all additive |
| the run | `components/ui/Marks.jsx` `CardRun` | A1 |
| the sheet's run | `components/ui/Marks.jsx` `GameStrip` | A4, and the §4.1 grid fix |
| tier | `Marks.jsx` `TierBadge` | none |

### 3.5 Backend fields required

`span_pts`, `span_band` (§8 **B2**). Everything else is already on the wire.

---

## 4. Surface B — the team detail sheet

### 4.1 Current state, measured

`ForecastSheet` for Team 9 · 3+ corners. **390 × 743 px** (88 % of an 844 px viewport);
**560 × 759 px** at 1440. Contents, top to bottom, with measured heights at 390:

| Block | h | Verdict |
|---|---|---|
| `.k-fs-head` — shield 52 px, `Away`, `Team 6 v Team 9`, `Fri 07:00 PM`, `87%`, `85 to 88` | 58 | keep |
| range note | 44 | keep |
| `Why` — one reason | 45 | keep |
| `Last 10 games · 3+ corners` + `GameStrip` | 211 | **broken, see below** |
| `A player like him in a fixture like this: usually 79%.` | 26 | **wrong** |
| `All lines` — 2 rows | 100 | keep |
| footer: Save ★, Share | 56 | keep |
| **absent** | | the three `k-fs-tiles` (player-only), `QuickView` (player-only), the club link, the "open the page" link, the track-record line |

**Fault B1 — the strip's line is drawn in the wrong place, and it flatters the forecast.**
`GameStrip` renders `.pgs-min` only when `games.some(g => g.minutes != null)`. A club has no
minutes, so a club column contains three visible children, not four, while `.pgs-g` declares four
grid rows (`auto auto var(--bar-h) var(--foot-h)`). Every child shifts up: `.pgs-opp` (the crest)
lands in the 54 px bar row and the `sr-only` span takes the 26 px foot row. `.v2-gs-rule` is
positioned from the bottom of `.pgs-row` at `calc(var(--foot-h) + var(--rule) * var(--bar-h))`, so
it lands **beneath every column**. The reader sees ten bars all above the line and a caption that
says six of ten. Confirmed in all four renders.

**Fix (Marks.jsx, `GameStrip`):** stop relying on auto-placement. Give each child an explicit row
and keep the grid at four rows always.

```jsx
// always render the minutes cell; it is empty when there are none, so the geometry never shifts
<span className="pgs-min" style={{ gridRow: 1 }} title="Minutes played">
  {!anyMins ? "" : mins == null ? "–" : `${Math.round(mins)}'`}
</span>
<span className="pgs-v"     style={{ gridRow: 2 }} …/>
<span className="v2-gs-bar" style={{ gridRow: 3 }} …/>
<span className="pgs-opp"   style={{ gridRow: 4 }} …/>
<span className="sr-only"   style={{ gridRow: 4 }} …/>
```

Equivalently in CSS, which is cleaner and touches no JSX:
`.pgs-g > .pgs-min { grid-row: 1 } .pgs-g > .pgs-v { grid-row: 2 } .pgs-g > .v2-gs-bar { grid-row: 3 }
.pgs-g > .pgs-opp, .pgs-g > .sr-only { grid-row: 4 }` in `v2.css` §"the player run". Prefer this:
no component changes, no risk to the player path, and it is correct for any future column that
omits a cell. Add a selftest asserting that a games array with `minutes: null` throughout produces
the same `.pgs-g` row template as one with minutes.

**Fault B2 — "A player like him".** `ForecastSheet` line:
`{f.p_usual != null && <span …>A player like him in a fixture like this: usually {pct(f.p_usual)}.</span>}`
with no scope test. `METRICS.md` already records that this sentence is wrong twice even for a
player (it is *him*, not a player like him; and it is an *average* opponent, not a fixture like
this). For a club it is wrong three times.

**One sentence, both scopes, matching the card's `USUAL` label:**
`Their own normal game, before this opponent: 79%.` / `His own normal game, before this opponent: 79%.`

**Fault B3 — the sheet cannot be interrogated.** For a player the sheet carries the whole
`QuickView` opened on the tapped line, plus `Open ⟨name⟩'s page`. For a club it carries a fixed
ten-game strip of one stat at one line and no link anywhere — not to the club page, not to the
match. The sheet *is* the club page for most readers, and it is a cul-de-sac.

**Fault B4 — three blank tiles' worth of room.** `k-fs-tiles` is gated on
`f.scope === "player"`, so the row that carries *Chance he plays / If he plays / Lineup* is absent
and nothing takes its place.

**Fault B5 — a duplicate fetch.** `useSheetData` calls `/teams/{id}/history` itself. Once the club
sheet carries `QuickView` (which fetches history with the reader's filters) that call is the same
request twice, which is precisely the duplication `docs/48` removed from the player path.

### 4.2 The design

```
┌ Team 9 · 3+ corners                                      ✕ ┐
│ ⬡  Away  Team 6 v Team 9  Fri 19:00            87%  85 to 88│   .k-fs-head  (+ club link)
│ That range is how sure we are: …                            │
│                                                             │
│  Tonight 6.1     Usually 4.8      Opponent 7 pts            │   k-fs-tiles, team variant  [NEW content]
│                                                             │
│ Why                                                         │
│  • The opponent's style allows more corners.                │
│                                                             │
│ ── Quick view ────────────────────────────────────────────  │   QuickView(teamId)
│  3+ corners next match                        87%  Solid    │
│  [ GameStrip, 10 columns, rule at 3+ ]                      │
│  3 of 10 reached this line. Opponent below each column.     │
│  Stat ▾ Corners   Line (2+ 3+ 4+ 5+)   Window (5 10 20)     │
│  Venue (All Home Away)                                      │
│                                                             │
│ Their own normal game, before this opponent: 79%.           │
│ This line moves about 7 points depending on the opponent —  │
│ between the league's leakiest and meanest defence.          │
│                                                             │
│ All lines                                                   │
│  3+ corners                        87% (85 to 88)           │
│  2+ corners                        91% (90 to 91)           │
│                                                             │
│ Our record on Solid team corners forecasts: 41 of 50 …      │
│ Statistical analysis for information and entertainment. …   │
├─────────────────────────────────────────────────────────────┤
│ ★   Open Team 9's page            Share                     │
└─────────────────────────────────────────────────────────────┘
```

**B-a. A tiles row for a club.** Reuse `.k-fs-tiles` / `.k-fs-tile` exactly; change only the gate
and the contents.

```jsx
{f.scope !== "player" && (f.expected != null || f.span_pts != null) && (
  <div className="k-fs-tiles">
    {f.expected != null && <div className="k-fs-tile"><small>Tonight</small>
      <b data-testid={`${testid}-expected`}>{f.expected.toFixed(1)}</b></div>}
    {f.expected_usual != null && <div className="k-fs-tile"><small>Usually</small>
      <b>{f.expected_usual.toFixed(1)}</b></div>}
    {f.span_pts != null && <div className="k-fs-tile"><small>Opponent</small>
      <b data-testid={`${testid}-span`}>{f.span_pts} pts</b></div>}
  </div>
)}
```

Reason: the three facts a club line has that a player line does not need, in the slot the player's
three occupy. Nothing invented; `expected`, `expected_usual` and `span` are all stored.

**B-b. `QuickView` takes a club.** See §4.3. It replaces the fixed `GameStrip` block **and** the
`useSheetData` history fetch (fault B5), so `useSheetData` shrinks to the track-record call only.

**B-c. The span sentence.** Under the "own normal game" line, only when `span_band !== "low"`:

> **This line moves about 7 points depending on the opponent** — between the league's leakiest and
> meanest defence. Many lines barely move at all; those are the ones we leave out.

This is `METRICS.md` §4.1 form 1, written from `span` alone so it needs no new engine number.

**B-d. Links out.** `.v2-fs-who` is player-only. Add the team equivalent:
- the club name in `.k-fs-head` becomes `<Link to={`/team/${fx.team.id}`} className="v2-fs-name">`;
- a `.v2-fs-open` link `Open Team 9's page`, the same component the player sheet uses;
- the fixture text keeps its `Match page` route via the existing `f.match_id` on Share.

**B-e. The track-record line already works for clubs** — `track_record(scope, stat)` takes
`scope="team"` and `STAT_WORD` already maps `corners`. It renders today only when
`d.record.ready`; demo data is below the threshold. Nothing to change; worth saying so, because it
looks absent.

### 4.3 `QuickView` for a club — the exact change

`components/ui/QuickView.jsx` today: `QuickView({ playerId, stat, line, title, collapsible,
forecasts, children, testid })`, fetching `/players/{id}/history?last&started&venue`.

```jsx
export function QuickView({ playerId, teamId, stat: stat0, line: line0 = 1, … }) {
  const isTeam = !playerId && !!teamId;
  const OPTS = isTeam ? TEAM_STATS : STATS;                    // TEAM_STATS already exported from Football.jsx
  const [stat, setStat] = useState(OPTS.some(s => s.id === stat0) ? stat0 : (isTeam ? "corners" : "shots"));
  const q = useApi(playerId ? `/players/${playerId}/history` : teamId ? `/teams/${teamId}/history` : null,
                   playerId ? { last, started, ...(venue !== "all" ? { venue } : {}) }
                            : { stat, last, ...(venue !== "all" ? { venue } : {}) });
  …
}
```

Three rules:

1. **`stat` is a query parameter for a club and not for a player.** `/players/{id}/history` returns
   every stat per game; `/teams/{id}/history` returns one. That is why `stat` joins the club query
   and why changing the Stat control refetches for a club and does not for a player. Say so in a
   comment or the next reader will "optimise" it away.
2. **Drop "Started only" for a club.** Guard the control on `!isTeam`.
3. **`venue` must be added to `/teams/{id}/history`** (§8 **B3**). Without it the Venue control is a
   lie, and "only when they are at home" is the most-asked question a club line has.

Line options continue to come from `fcAny.ladder`, which team forecasts carry
(`{"1.5":0.9052,"2.5":0.8678,…,"10.5":0.1201}` on the demo card) — so a club gets 10 real rungs
where a player gets 3–5. Cap the control at the rungs within `engine.line_band`, as today.

### 4.4 Components

| Block | Component | Change |
|---|---|---|
| sheet shell | `ui/BottomSheet.jsx` | none |
| head | `ui/ForecastSheet.jsx` `.k-fs-head` | B-d |
| tiles | `ui/ForecastSheet.jsx` `.k-fs-tiles` | B-a (new gate, new contents) |
| evidence | `ui/QuickView.jsx` | §4.3 |
| run | `ui/Marks.jsx` `GameStrip` | §4.1 grid fix + `abbr` fallback |
| copy | `ui/ForecastSheet.jsx` | B2, B-c |

### 4.5 Backend fields required

`span_pts` / `span_band` (§8 **B2**); `venue` on `/teams/{id}/history` (§8 **B3**). Nothing else.

---

## 5. Surface C — P-12, the club page

### 5.1 Current state, measured

390 × 844, dark, Squad (default):

| | px |
|---|---|
| total page height | **4,767** |
| `.phead` | 141 (crest rendered 45 × 45) |
| `What we expect next match` — 3 cards | ~1,100 |
| `[data-testid=team-tabs]` top | 1,455 |
| `[data-testid=squad-cards]` | **2,242** (14 × 133 px + gaps) |
| newsletter + footer | ~900 |
| horizontal scroll at 390 | none (`scrollWidth` 390) |

1440 × 1000: 2,019 px total, head 110 px. Numbers tab at 390: **3,583 px**. Fixtures tab at 390:
**2,733 px**. For comparison the player page at 390 is **2,646 px** with a **261 px** head.

What the renders show, beyond the audit:

1. **The head is still `.phead`.** `display:flex; align-items:center` centres the crest against a
   column running name → league → (form + chips + Follow + Compare), so at both widths the crest
   sits level with the form pills and the name has empty space to its left. No next fixture, no
   league position, no record.
2. **Form pills are `title`-only.** `.fp` is 26 × 26 px, not focusable, and the scoreline and
   opponent live in a `title` attribute that does not exist on touch. Five coloured letters with no
   referent, below the 44 px floor if they ever become interactive.
3. **The forecast block repeats the page.** At 1440 the club name appears four times in one
   screenful; all three cards carry the identical subtitle; at 390 that subtitle truncates to
   `vs Team 6 · aw…`.
4. **Two of three lead cards are `Watch`.** Nothing orders or explains the block — a `Watch` card
   sits above a `Solid` one because `group_cards` returns per-stat cards in no particular order.
5. **The squad table's fixed column set cannot adapt.** `SEASON_KEYS` is hard-coded
   `Apps/Min/Goals/Shots/Tackles/Cards`; on this club Goals is `0` and Cards is `0` for all
   fourteen players — **28 of 84 cells are a zero**.
6. **`Compare with…` is a `btn--sm`, 36 px high** — below the 44 px floor, and it sits above the
   fold while the forecast is below it.

### 5.2 The shape: the player page's four movements, for a club

| Movement | Player page (P-13) | Club page (P-12), proposed |
|---|---|---|
| **Who, and what's next** | `v2-ph2` head: wash, 84 px avatar, display name, club + position chips, `v2-nextfx`, Follow | `v2-ph2` head: wash from the crest, 84 px `Crest`, display name, league + **position** + **form-vs-expected** chips, `v2-nextfx`, Follow |
| **What we expect next** | `What we expect next match` → `fgrid` of `ForecastCard` | identical, ordered, with a one-line opponent note |
| **The evidence** | `Quick view` (`QuickView`) | `Quick view` (`QuickView` with `teamId`) |
| **The season behind it** | `Ranks`, history table, `Note` | `Where they stand`, then the Squad / Numbers / Fixtures tabs |

### 5.3 The head — `v2-ph2`, adopted

Audit item #9 says all four entity heads should take it. Here is the club's, element for element.
Every class already exists in `v2.css` §25; the only substitution is `PlayerAvatar` → `Crest`.

```jsx
<header className="phead v2-phead v2-ph2">
  <span className={"v2-phead-wash" + (d.team.image ? "" : " is-plain")} aria-hidden="true"
        style={d.team.image ? { backgroundImage: `url(${d.team.image})` } : undefined} />
  <Crest team={d.team} size={84} decorative={false} eager />
  <div className="phead-main">
    <h1 className="v2-ph2-name">{d.team.name}</h1>
    <p className="v2-phead-sub v2-ph2-meta">
      {d.league && <Link to={`/league/${d.league.id}`} className="v2-club">
        <LeagueMark league={d.league} size={20} /> {d.league.name}</Link>}
      {d.standing && <span className="v2-pos" data-testid="team-standing">
        {nth(d.standing.pos)} of {d.standing.of} · {d.standing.pts} pts</span>}
      {(d.style?.tactics || []).map((t) => <TacticChip key={t} t={t} />)}
    </p>
    {d.next[0] && (
      <Link to={`/match/${d.next[0].id}`} className="v2-nextfx" data-testid="team-next-fixture">
        <span className="v2-nextfx-at">{d.next[0].home_iid === d.team.iid ? "Home" : "Away"}</span>
        <span className="v2-nextfx-t"><Crest team={d.next[0].home} size={24} />{d.next[0].home?.name}</span>
        <span className="v2-nextfx-v">v</span>
        <span className="v2-nextfx-t"><Crest team={d.next[0].away} size={24} />{d.next[0].away?.name}</span>
        <time>{kickoff(d.next[0].kickoff)}</time>
      </Link>
    )}
    {d.context?.why?.[0] && <p className="v2-ph2-why" data-testid="team-context">{d.context.why[0]}</p>}
    <div><FollowButton kind="team" refId={d.team.id} name={d.team.name} /></div>
  </div>
</header>
```

- **`v2-ph2-why` [NEW class, existing data].** `backend/match_context.py` already composes the
  sentence and stores it in `match_context.context_why`:
  *"Above expectations lately: 4 points more than expected in the last 5."* / *"In a relegation
  fight."* `queries.match_detail` already serves it as `context[iid].why`; `team_detail` does not.
  **Reason to show it:** `METRICS.md` §4.4 — this is the forecasting statement the W/D/L pills are
  the counting version of, it is already written in plain English, and it is the single best use of
  one line in the club's head. Style: `font-size:.8125rem; color: var(--text2); margin: 0 0 11px;`.
- **Form pills move out of the head** into §5.6's "Where they stand", and become links to
  `/match/{match_id}` (`team_form` already returns `match_id`). `.fp` grows to 44 × 44 px inside
  a list of `<Link>`s and the `title` becomes visible text: `W 2–1 v Team 4`. Keep the existing
  `.fp--W/D/L` classes and colours; add `.form-pills--linked .fp { width:44px; height:44px; }`.
  **Reason:** five letters whose only explanation is a `title` are inaccessible on the device 390 px
  describes, and they are not head material: they are evidence.
- `Compare with…` moves to the Numbers tab (audit P-12 inventory) and becomes `btn` (44 px), not
  `btn--sm`.
- 390: `.v2-ph2` already has a media query dropping the avatar to 64 px and the name to
  `clamp(1.6rem, 8vw, 2.2rem)`. Expected head height at 390: ~250 px, i.e. the player page's.

### 5.4 The page body

```
v2-ph2 head                                      ~250 px @390

section.card[data-testid=team-next]
  h2  What we expect next match
  p   Away at Team 6, Friday 19:00. Three lines worth reading.     [one line, replaces three subtitles]
  div.fgrid                                                         ForecastCard × n, ordered

section.card[data-testid=team-quick]
  h2  Quick view                                                    QuickView teamId
  (stat / line / window / venue, one GameStrip)

section.card[data-testid=team-ranks]
  h2  Where they stand in Test League
  ul  Corners won 2nd of 12 · Shots 4th of 12 · Defence 9th of 12   [league_radar percentiles]
  ol.form-pills--linked  W 2–1 v Team 4 …                           [the five results, as links]

Tabs  Squad | Numbers | Fixtures                                    unchanged component
```

**C1 — order the cards.** `group_cards(fc, …, "team")` returns one card per stat in dict order.
Sort by `prominence` descending in `team_detail` before returning, so the same rule that picks the
lead *line* picks the lead *card*, and a `Watch` never sits above a `Solid`.
`cards.sort(key=lambda c: -Q.prominence(c, weights, scale))` — free.

**C2 — one fixture line, not three subtitles.** With **A5** the card subtitle shortens; the block
gains a single `<p className="k-faint k-small">` naming the fixture once. If `d.next[0]` is more
than 7 days away, say so: *"Their next match is on Friday 13 November. Forecasts open closer to
kick-off."* — the same sentence the league page needs (§6).

**C3 — Quick view, second not first.** Audit #4 asks the player page to put the forecast first and
Quick view second. The club page is being written now, so write it in the fixed order and let P-13
be reordered to match. The forecast is the answer; the Quick view is the working.

**C4 — "Where they stand". [NEW block, existing computation]** `team_insights.league_radar(db,
league_iid)` already returns `{team_iid: {axes: {attack, shots, sot, poss, defence, corners} →
0..1 percentile, games: n}}`, cached 600 s per league and computed opponent-adjusted (so a soft run
of fixtures does not flatter a club). Turn each axis into `nth(round((1-p) * (n-1)) + 1) of n`.

Render with the **existing** `.pl-ranks` markup from `Player.jsx`'s `Ranks`:
```jsx
<section className="card pl-ranks" data-testid="team-ranks">
  <h2 className="k-sec">{d.league.name} rank this season</h2>
  <ul>{d.ranks.map(x => <li key={x.key} data-testid={`team-rank-${x.key}`}>
    <b>{nth(x.rank)}</b><span> of {x.of}</span><small className="k-faint">{x.label}</small></li>)}</ul>
  <p className="k-faint k-small">Each one is their place in the league against an average opponent,
     not a raw per-game average.</p>
</section>
```
**Reason:** it is the exact analogue of the player page's `Ranks` ("47th of 168 for shots"), it uses
a component that already exists, and unlike the Numbers tab's `tbar`/`tiles4` it is not a count —
it is the opponent-adjusted rating, which is the kind of number the product is for.

**C5 — the squad list, demoted and de-zeroed.** Keep `SquadCards` and `Grid` behind the Squad tab,
below everything above. Two changes:
- Replace the hard-coded `SEASON_KEYS` with the **four non-empty** keys for this club, chosen
  server-side: `squad_season` returns `columns: ["apps","minutes","shots","tackles"]`, dropping any
  key whose column sums to 0 across the squad and keeping `apps` and `minutes` always. Cost: the
  aggregation already computes every total; it is one pass over the result list.
  **Reason:** 28 of 84 cells are currently a zero because the column set cannot adapt to what the
  club does; four honest columns are 4 × 133 px shorter and say more.
- Group the cards under `GK / Defenders / Midfielders / Forwards` headings. `squad_season` already
  sorts by `order = {"GK":0,"DEF":1,"MID":2,"FWD":3}`; the grouping is a `reduce` in the component.

**C6 — the Fixtures tab.** Now that `probs` and `best_line` arrive (WIP), `MatchRow` draws the bar
and the line. Three remaining:
- group under a date heading and print `Round 20`, as P-11 needs (§6, **D1**);
- a `MatchRow` that has no `probs` gets the one-line note *"Forecasts open closer to kick-off"*
  under the group, not per row;
- `best_line` should prefer this club's own line (§8 **B4**) — on the club's page, a row that leads
  with the opponent's striker is the wrong line.

### 5.5 States

| State | Treatment |
|---|---|
| **Loading** | `Loading rows={5}` for the whole page as today, then per-block: head renders from `d` immediately; `team-next` shows `Loading rows={3}`; `QuickView` keeps its own `Loading`. Never a full-page spinner once the head can render — the reader asked for *this club*. |
| **No upcoming match** | head drops `v2-nextfx`; `team-next` shows `<Empty icon="calendar">No upcoming match loaded.</Empty>`; Quick view still renders (history does not need a fixture). |
| **Fixture exists, no forecasts** | `<Empty icon="target">Forecasts for this match open closer to kick-off.</Empty>` — not the current bare `No forecasts for this club yet`, which reads as a defect rather than a schedule. |
| **Fewer than 3 games of history** | `CardRun` already returns `null` under 3 known games and the card falls back to `.k-fc-bar`. `QuickView` shows `<Empty icon="activity">No games match these filters.</Empty>`. "Where they stand" renders nothing when `league_radar` returns `{}` (it needs ≥ 40 league pairs) — silence, not an empty card. |
| **Error** | `ErrorBox` with `onRetry={q.reload}` per block, as elsewhere. A failed `/teams/{id}/history` must not take the forecast block down: they are separate `useApi` calls already. |
| **Crest missing** (every demo club) | `v2-phead-wash.is-plain` already handles the head. `CardRun` uses `abbr()`; `GameStrip` must too (**A4**). |

### 5.6 390 px, light and dark, touch

- No horizontal scroll today (`scrollWidth` 390) and nothing proposed adds a fixed width. The
  `.v2-cmp` row wraps; `.pgs-row` wraps; `.fgrid` is one column under 768 px.
- Dark and light both render correctly today; the head change inherits `.v2-ph2`'s existing
  per-mode wash opacity (`.38` in light, guarded for both `prefers-color-scheme` and
  `[data-theme]`).
- Touch floor: `.fp` 26 → 44 px when linked; `Compare with…` `btn--sm` 36 → `btn` 44 px; `.chip`
  is 40 px and `.chip--sm` 34 px — raise both to 44 px wherever they are the primary control of a
  block (the Analysis jump nav, the Teams-tab stat chips). `.cb-add` is already 44 × 44.
- Expected page height at 390 after the change: head ~250 + forecast ~1,100 + Quick view ~400 +
  ranks ~220 + tabs and squad ~2,000 = **~4,000 px**, with the answer inside the first 1,350 px
  instead of the first 1,455 px being a head and three cards with no context.

### 5.7 Components

| Block | Component | New or reused |
|---|---|---|
| head | `.v2-ph2` markup + `Crest`, `LeagueMark`, `TacticChip`, `FollowButton` | **reused** (classes from `v2.css` §25, written for P-13) |
| next fixture | `.v2-nextfx` | **reused** |
| context sentence | `.v2-ph2-why` | **[NEW class]**, data from `match_context.context_why` |
| forecast block | `ForecastCard` in `.fgrid` | **reused** |
| evidence | `QuickView` + `GameStrip` | **reused**, with `teamId` |
| where they stand | `.pl-ranks` markup | **reused** from `Player.jsx` `Ranks` |
| form | `FormPills` | **reused**, linked variant |
| tabs | `Tabs`, `Seg`, `Select` | **reused** |
| fixtures | `MatchRow` | **reused**, with §6 **D1** |
| squad | `SquadCards`, `Grid` | **reused**, column set from the API |

---

## 6. Surface D — P-11, the league page

### 6.1 Current state, measured

390 dark, Fixtures: **2,943 px**. Teams tab: **2,386 px**.

| Fault | Measurement |
|---|---|
| **D-a. `MatchRow` wraps wrong.** `.mrow` grid areas are `"t t t" / "h s a"` under 768 px, so the score cell `v` sits at the right end of the home club's line: `Team 0 ———— v` / `———— Team 2`. | row height **162 px** at 390, 81 px at 1440 |
| **D-b. The date repeats.** `Fri, Nov 6, 07:00 PM` on all six rows of round 20, then again on round 21. `round` is in the data (`round: 20`) and is never printed. | 6 × 18 px of nothing per round |
| **D-c. The forecast cliff.** Round 21 rows carry no bar and no line, visually identical to round 20's, with no explanation. | |
| **D-d. No route from a league fixture to a club.** The whole `.mrow` is one `<Link to={/match/:id}>`; the club names inside are not links. | |
| **D-e. `best_line` never names a club.** `_best_line` ranks all scopes by `prominence`; in the demo set every winner is a player (`Player 204 · 2+ tackles · 82%`), even on fixtures that have four team lines. | 3 of 3 visible rows |
| **D-f. The Teams tab buries the clubs.** 14 stat chips in 7 rows + `Season/Last 10/Last 5` + `All/Home/Away` + a gradient legend = **~470 px before the first club row**, on a tab whose content is a one-stat ranked bar list. | first row at ~600 px of 2,386 |
| **D-g. `recent` is computed and thrown away.** `/leagues/{id}` returns 20 fully decorated final matches (`probs`, `insight_count`, `_best_line` each); `League.jsx` never reads `d.recent`, then `Results` refetches 60 and `Standings` refetches 400. | 3 overlapping fetches |

### 6.2 The design

**D1 — group fixtures, name the round, mark the cliff.** In `League.jsx`'s `List` (and reused by
P-12's Fixtures tab), group `rows` by `shortDay(kickoff)` and render
`<h3 className="k-sec">Round 20 · Friday 6 November</h3>` per group. Under a group where no row has
`probs`, one line: *"Forecasts open closer to kick-off."* Saves 5 × 18 px per round and removes the
thing that reads as a broken page.

**D2 — fix `.mrow` at 390.** The three-column `"h s a"` row cannot hold two club names and a `v`
at 390. Make the sub-768 layout two rows of club + crest with the `v` as a centred rule between
them, which is also what the match hero does:

```css
@media (max-width: 767px) {
  .mrow { grid-template-areas: "time time" "home v" "away v"; grid-template-columns: minmax(0,1fr) 36px; }
  .mrow-score { grid-area: v; align-self: center; text-align: center; }
  .mrow .team--end { justify-content: flex-start; }   /* both clubs read left-aligned, as a pair */
}
```
Reason: the `v` currently reads as a typo on the first screenful of the league page, and P-12's
Fixtures tab has just inherited it.

**D3 — club names become links.** Inside `.mrow`, wrap each `.team` in `<Link to={/team/:id}>` with
`onClick={e => e.stopPropagation()}`; the row link stays. There is currently **no path from a
league fixture to a club page**, which is the journey this document is about.
Touch: each club line is already ≥ 44 px tall in the two-row layout.

**D4 — `best_line` honours the scope mix.** §8 **B4**: `_best_line` gains `prefer_scope` /
`prefer_team_iid`. On P-11 leave it as is (the most prominent line is the right one for a league
row). On P-12's Fixtures tab pass the club. Also surface the scope in the row so a club line reads
as one: `<b>Team 9</b> 3+ corners <em>87%</em>` already works — `_best_line` fills `who` from
`teams` for a team row today.

**D5 — the Teams tab becomes the club list it claims to be.** Order:
1. one row per club: crest, name, **what they have next** (`Away at Team 6 · Fri 19:00`), and
   **their leading line** (`3+ corners 87%`), the whole row a link to `/team/{id}`;
2. the stat chooser and the ranked bars **below**, behind a `<details>` or a `Show the numbers`
   toggle — they are the archive, not the list.

Data: §8 **B6** adds `teams[]` to `league_detail`, each with `next` and `best_line`, computed from
one `_best_line` call over the next round's match iids (already computed for `out["next"]` in the
same request — reuse it, do not call twice).
Reason: the only screen in the app whose job is "here are the clubs in this league" currently says
nothing about any of them that the engine produced, and offers no onward step but a name.

**D6 — read `d.recent`.** `Results` drops its own fetch and renders `d.recent`;
`Standings` is fed from §8 **B7**'s server-side table. Two fetches of 60 and 400 rows go away.

### 6.3 Components

`MatchRow` (CSS + two links, no API change), `WdlBar` (unchanged), `Segmented`, `Empty`, plus a
small `TeamRow` for D5 — **[NEW component]**, ~20 lines, because no existing row carries
crest + name + next fixture + leading line. Model it on `.mrow-best`'s typography
(`.td-ins, .mrow-best` in `v2.css`) so the league page's two row types read as one family.

---

## 7. Surface E — M-05 Analysis, and the match hero

### 7.1 Current state, measured

**Hero.** `Side` already renders `<Link to={/team/${team.id}}>` with a 64 px crest and the club
name — **this is the one place in the app that gets the club link right**, and it should not
change. `WdlBar` + `Expected goals 1.3 – 1.1` sit under it. Keep.

**Analysis, 390: 4,072 px.** The club appears five times and is a link in none:

| Block | h @390 | The club's presence |
|---|---|---|
| `an-jump` chip nav | 56 | — |
| `Form` — `Per game this season`, paired bars | ~280 | `Team 0 at home, Team 2 away.` as caption text |
| `Style shape` radar | ~560 | club names in the legend |
| `Head to head` | ~260 | club names in three tiles |
| `Who scores first` | **~400** | **two empty states**, `No first-goal records yet for Team 0.` and the same for Team 2 |
| `Shots by player · last 10 games` | ~780 | club names as a two-tab strip; a 13-row count table |
| `Playing style` | ~200 | Pro lock |

### 7.2 The design

**E1 — lead Analysis with the two clubs' own lines. [reuses `ForecastCard`]** `match_detail`
already carries every forecast for the match, team-scope included (the Forecasts tab groups them
under `Team 0 · 9`). Put a two-column strip at the very top of `Analysis`, above `an-jump`:

```jsx
<section className="an-sec" id="an-clubs">
  <h2 className="k-sec">What we expect from each club</h2>
  <div className="split2">{[d.home, d.away].map((t) => (
    <div key={t.id}>
      <h3 className="h3"><Link to={`/team/${t.id}`} className="v2-club"><Crest team={t} size={20} /> {t.name}</Link></h3>
      {leadTeamCard(d, t) ? <ForecastCard f={leadTeamCard(d, t)} teams={fxTeams} homeIid={d.match.home_iid} showTime={false} />
        : <Empty icon="target">No club lines for this match yet.</Empty>}
    </div>))}</div>
</section>
```
`leadTeamCard` = the highest-`prominence` card with `scope === "team" && team_iid === t.iid`, from
`cardsOf(d)` — the same helper the Forecasts tab uses. No new data.
**Reason:** Analysis is 4,072 px of club material with no club forecast in it, while the engine's
club lines for this exact fixture are one tab away. It also gives the reader the entry to the club
page that the rest of the tab never offers.

**E2 — make every club name in Analysis a link.** `Form`'s caption, the radar legend
(`TeamRadar`'s `figcaption`), the H2H tiles and the `Shots by player` tab labels. Use `.v2-club`,
which already styles crest + name as a chip-link and is used in the player head and sheet. Touch:
`.v2-club` has padding and a border; set `min-height: 44px` where it is a tab label.

**E3 — collapse "Who scores first" when it is empty.** Two ~200 px empty states saying the same
thing is the same fault `Assignments` already fixed on P-11 ("before the round is named, every row
said *Referee not named yet* — six cards and about 600 px of page to say one thing six times").
When neither club has records, render one line: *"No first-goal records yet for either club."*
Saves ~330 px.

**E4 — `Shots by player` gets the club's own line above it.** The table is a count; put the club's
`sot`/`shots` team line (same object as E1) above it as one sentence so the table has a claim to
sit under. No new data.

**E5 — the radar is the club page's "Where they stand", seen from the match.** `TeamRadar`'s axes
come from `league_radar`, the same source as §5.4 **C4**. Say so once, in the club page's rank
block: *"The same six measures the match page draws as a shape."* Consistency is free here and it
is the only place in the app where the club's standing is already drawn well.

---

## 8. Backend — every change, diff-level

All against `backend/queries.py` unless stated. Costs are per request, against the demo set
(12 clubs, 126 matches) and the indexes in `mongo_init.py`.

### B1. `team_detail(db, team_iid, now=None)` — extend the WIP

Keep the uncommitted block. Add, after `cards = group_cards(...)`:

```python
    weights, scale = S.get(db, "engine.market_weights"), S.get(db, "engine.lift_scale")
    # The lead CARD is chosen by the same rule as the lead LINE, so a Watch never sits above a Solid.
    cards.sort(key=lambda c: -prominence(c, weights, scale))
```

Add to the returned dict:

| Field | Contents | How | Cost |
|---|---|---|---|
| `standing` | `{"pos": 9, "of": 12, "pts": 21, "played": 20, "gd": -4, "zone": None}` | `league_table(db, t["league_iid"])`, take this club's row | **B7**: one `find` over `matches` with `status:"final"` + season, ~126 docs here, ~380 for a 20-club league. Indexed on `league_iid`. Replaces a 400-row client fetch. |
| `ranks` | `[{"key":"corners","label":"Corners","rank":2,"of":12}, …]`, one per radar axis the club has | `team_insights.league_radar(db, league_iid)[team_iid]["axes"]`, percentile → `round((1-p)*(of-1))+1` | **free on a warm cache** (`_RADAR_CACHE`, 600 s, keyed on league + row count). Cold: one pass over `team_match_stats` for the league + 5 ridge fits. The league page already warms it. |
| `context` | `{"form_vs_expected": 0.8, "situation": {...}, "games_left": 16, "why": ["Above expectations lately: 4 points more than expected in the last 5."]}` | `db.match_context.find_one({"match_iid": nxt[0]["iid"], "team_iid": team_iid})` | one indexed `find_one`. |
| `availability` | `_availability(db, [team_iid])` | existing helper | one `find` on `availability`, tiny collection. |
| `next[].round` | already on the match doc; stop dropping it | `_with_teams` keeps the doc whole — it is already there, the component ignores it | free |

Also change the `group_cards` call's third argument. `group_cards(fc, …, "team")` works today only
because `_card_key` falls through to the `player_market` branch for any unknown group name. Pass
`"player_market"` and add a one-line comment, or add `"team"` as a named alias in `_card_key`.
Silent fall-through is how a future `group="club"` returns one card for a whole club.

### B2. `_decorate(db, fc)` — attach the span fields

```python
def _decorate(db, fc):
    _usual(db, fc)
    min_span = float(S.get(db, "engine.min_span"))
    for f in fc:
        sp = f.get("span")
        if sp is None:
            f["span_pts"], f["span_band"] = None, None
            continue
        pts = abs(float(sp)) * 100.0
        f["span_pts"] = int(round(pts))
        # the band pivots on the SAME setting the triviality gate uses, so the words the reader
        # sees and the rule that hides a line can never drift apart
        f["span_band"] = ("low" if min_span > 0 and abs(float(sp)) < min_span
                          else "high" if min_span > 0 and abs(float(sp)) >= 2 * min_span
                          else "normal")
    …
```

**Cost:** one settings read and `O(len(fc))` arithmetic. No query. Reaches every screen that draws
a card, because `_decorate` is the single decoration path (`insights_feed`, `match_detail`,
`player_detail`, `team_detail`, `_from_ladder`).

With `min_span = 0.06` (the default, from `docs/56` §3) and the measured median span of 9.5 points,
most lines land in `normal`, a striker's `1+` rung (3.7 pts) in `low` and his `5+` (31.3 pts) in
`high`. `span_band === "low"` renders nothing — see §3.2 **A3**.

### B3. `team_history(db, team_iid, stat, last_n=10, venue=None)`

```python
def team_history(db, team_iid: int, stat: str, last_n: int = 10, venue: str | None = None) -> dict:
    q = {"team_iid": team_iid, stat: {"$ne": None}}
    if venue in ("home", "away"):
        q["home"] = venue == "home"
    rows = list(db.team_match_stats.find(q, {"_id": 0, "kickoff": 1, "opp_iid": 1, "home": 1, stat: 1})
                .sort("kickoff", -1).limit(last_n))
    …
```
and in `routes_data.py`:
```python
@router.get("/teams/{team_id}/history")
def team_history(team_id: str, response: Response, stat: str = Query(..., pattern="…"),
                 last: int = Query(10, ge=1, le=40),
                 venue: str | None = Query(None, pattern="^(home|away)$"), db=Depends(D.get_db)):
    return Q.team_history(db, _iid(db, "teams", team_id), stat, last, venue)
```
**Cost:** one more equality term on an already-indexed query. Nothing else.
**Why it is required:** without it the Quick view's Venue control is decoration, and "only when
they are at home" is the first follow-up a club line invites.

### B4. `_best_line(db, match_iids, prefer_team_iid=None)`

```python
    for r in rows:
        score = prominence(r)
        if prefer_team_iid is not None and r.get("team_iid") == prefer_team_iid:
            score *= 1.0 + PREFER_OWN            # module constant, 0.25; a tie-break, not an override
        …
```
`team_detail` passes the club; `league_matches` does not. **Cost:** nil — one multiplication inside
a loop that already runs.
**Why:** on a club's own Fixtures tab, a row that leads with the opponent's striker is the wrong
line for that page. A 25 % tie-break keeps a genuinely better opposition line in place.

### B5. `squad_season(db, team_iid)` — return the columns that carry data

```python
    KEYS = ("apps", "minutes", "goals", "assists", "shots", "sot", "tackles", "yellow_cards")
    totals = {k: sum(r.get(k) or 0 for r in out) for k in KEYS}
    cols = ["apps", "minutes"] + [k for k in ("goals", "shots", "sot", "tackles", "yellow_cards")
                                  if totals[k] > 0][:4]
    return {"since": start, "players": out, "columns": cols}
```
**Cost:** one pass over ≤ 30 rows already in memory. Removes 28 zero cells and ~530 px at 390 on
this club.

### B6. `league_detail` (`routes_data.py` `league()`) — a club list worth the name

```python
    nxt = Q.league_matches(db, iid, "scheduled", limit=20)
    out["next"] = nxt
    out["teams"] = Q.league_teams(db, iid, nxt)      # NEW
```
with a new `queries.league_teams(db, league_iid, scheduled)`:
- clubs: one `find` on `teams` by `league_iid` (12 docs) + `attach_images`;
- each club's next fixture: a dict walk over `scheduled`, already fetched — **no query**;
- each club's leading line: `_best_line(db, [iids of the next round], prefer_team_iid=t)` —
  `_best_line` already runs for `out["next"]` in the same request, so pass that result in rather
  than calling again.

**Cost:** one extra `find` over `teams`. The expensive part is already paid for.

### B7. `queries.league_table(db, league_iid, season=None)` — **[NEW function]**

```python
def league_table(db, league_iid: int, season: str | None = None) -> list[dict]:
    """Points, goal difference and position from the finished matches we already store.

    Standings.jsx builds this in the browser from /leagues/:id/fixtures?status=final&limit=400 --
    four hundred decorated rows over the wire to produce twelve. The club page needs exactly one of
    those rows and cannot have it at any price, because the fixtures route is per league.
    """
```
One `find` on `matches` (`league_iid`, `status:"final"`, season), project
`home_iid/away_iid/hg/ag`, accumulate, sort by `pts, gd, gf, name`. **Cost:** ~126 docs here, ~380
for a 20-club league, four small fields each — far less than the 400 fully decorated rows the
client fetches today. Memoise per `(league_iid, count)` for 60 s if it shows up in profiling.

Consumers: `team_detail.standing` (**B1**), and `Standings.jsx` via a new
`GET /leagues/{id}/table`, which lets P-11 drop its 400-row fetch (audit P-11 proposal 2).

### B8. Not required, explicitly

- No engine change. `span`, `expected`, `expected_usual`, `run[].home`, `ladder`, `form_fp`,
  `p_usual` are all already written by `engine_bridge`.
- No new collection.
- `track_record(scope="team", stat=…)` already works; it is gated on `ready` and the demo set is
  below the threshold.

---

## 9. States, breakpoints and the touch floor — the checklist

| | Card | Sheet | P-12 | P-11 | M-05 |
|---|---|---|---|---|---|
| **Loading** | n/a (rendered from the parent's data) | `useSheetData` returns `{games:null}`; `QuickView` owns `Loading` | per block, never full-page once the head can draw | `Loading` per tab, as today | `Skeleton shape="row"` as today |
| **Empty** | `CardRun` returns `null` under 3 known games → `.k-fc-bar` fallback. Keep. | `Empty icon="activity"` inside `QuickView`; tiles row hidden when `expected` and `span` are both null | `Empty icon="target"` + *"Forecasts for this match open closer to kick-off."*; ranks block renders nothing when `league_radar` is cold | *"Forecasts open closer to kick-off"* once per date group | one line for both clubs, not two empty states |
| **Error** | n/a | `ErrorBox` inside `QuickView`; the sheet still shows head, Why and All lines | `ErrorBox onRetry` per block; a failed history call must not remove the forecast | as today | as today |
| **390 px** | 358 px wide, `.v2-cmp` wraps to 2 lines, `.v2-cr` is an 11-column `1fr` grid — no scroll | sheet 390 × ~800; `.pgs-row` wraps at 44 px per column (10 columns → 2 rows; the grid fix in §4.1 is what makes the wrapped rule land correctly) | no horizontal scroll today (`scrollWidth` 390); nothing proposed adds a fixed width | `.mrow` two-row layout (**D2**) | `.split2` stacks |
| **Light** | verified: `.v2-cmp-d.is-up` uses `color-mix(in srgb, var(--up) 15%, transparent)`, legible in both | verified | verified | verified | verified |
| **Dark** | verified | verified | verified | verified | verified |
| **Touch ≥ 44 px** | `.cb-add` 44 ✓; `.k-fc-main` full card ✓; `.k-link` "+2 more lines" — **raise to 44 px**, it is 20 px today | footer buttons 44 ✓; `QuickView`'s `Seg` buttons — check against `.chip--sm` 34 px | `.fp` 26 → 44 when linked; `Compare with…` 36 → 44 | club links inside `.mrow` ≥ 44 in the two-row layout | `an-jump` `.chip` 40 → 44; `.v2-club` tab labels 44 |

**Colour rule.** Every value named above is a token: `var(--up)`, `var(--down)`, `var(--text)`,
`var(--text2)`, `var(--text3)`, `var(--surface1..3)`, `var(--border)`, `var(--border-strong)`,
`var(--brand)`, `var(--tier-strong|solid|watch)`. No literal appears in anything specified here.
Separately, and out of scope but still true: `#f5c518` and `#e5484d` remain hard-coded in six
`football.css` rules (audit item #10) and two of them (`.card-dot--y/--r`) render inside the club
page's squad Grid.

**Copy rule.** Every string proposed here was checked against `backend/textguard.py`'s `BANNED`
pattern. Two near-misses worth naming for whoever writes the final strings: **"stakes"** is banned
(so `match_context`'s `stakes` field must never be echoed as a label — use *"situation"*), and
**"units"** is banned (so a span chip must say *"7 pts"*, never *"7 units"*).

---

## 10. Build order

1. **§4.1 `GameStrip` grid fix** + **§4 B2 copy fix.** Two CSS rules and one string; they stop the
   team sheet from stating something false. Add the selftest.
2. **§8 B2 `span_pts`/`span_band`** then **§3 A1–A3, A5.** The card is the object the whole journey
   is built on; everything downstream renders it.
3. **§4.3 `QuickView` with `teamId`** + **§8 B3 `venue`.** Unlocks the sheet and the club page's
   evidence block in one change.
4. **§5.3 the `v2-ph2` head** + **§8 B1 `standing` / `ranks` / `context`** + **§8 B7
   `league_table`.** The club page becomes the page the one-sentence purpose describes.
5. **§6 D1–D3 `MatchRow` and fixture grouping.** Shared by P-11 and P-12; fixes the typo on the
   league page's first screenful and the club page's Fixtures tab at once.

Then: §5.4 C5 squad columns, §6 D5 the Teams tab, §7 E1–E4 Analysis.
