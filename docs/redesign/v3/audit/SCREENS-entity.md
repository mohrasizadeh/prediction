# Entity screens — design audit

**Scope:** P-09/P-10 Leagues, P-11 League, P-12 Team, P-13 Player, P-14 Referees, P-15 Referee, P-18 Search.
**Date:** 2026-11-06. **Method:** read the page components, the backend queries behind them, and the
390 px and 1440 px renders.

## A note on the material

The capture harness `scripts/shots3.js` does not substitute its `:league`, `:team`, `:player`,
`:referee` and `:learn` placeholders — line 114 pushes `path` straight out of the `PUBLIC` map with
no lookup against the `ids` it resolved twenty lines earlier. So **P-11, P-12, P-13, P-15 and P-20
are never captured**; `docs/redesign/v3/before/` has no file for any of them. Separately,
`before/P-14-phone-dark.png` is not the Referees page — it is the two-factor enrolment screen,
because the harness signs in once per context before running the public jobs and the owner account
is held at the `enroll_2fa` gate.

I captured the five missing entity screens myself at 390×844 and 1440×900, dark and light, against
the same demo server, and those renders are what §"Faults visible in the render" below describes.

**Two of these seven screens have never been rendered with content.** `GET /api/referees` returns
`[]` on demo data, so P-14 shows its empty state and P-15 404s for every name. They belong in the
docs/57 §7 list beside P-03 Live and O-06, and should not be signed off until the demo set has a
referee.

---

## The ten changes, ranked

Each is ranked by how much of the page's job it restores, not by effort.

| # | Change | Screens | Reason |
|---|---|---|---|
| 1 | **Give the club page a forecast.** `queries.team_detail` returns `team`, `league`, `style`, `next`, `form` and nothing else, so P-12's default view is fourteen cards of season totals and not one number the engine produced. Mirror `player_detail`: load the current team-scope forecasts for `next[0]`, run them through `group_cards(..., "team")`, and render them with the existing `ForecastCard` above the squad. | P-12 | The product forecasts. A club page whose first 2,800 px is Apps/Min/Goals/Shots/Tackles/Cards is a counting tool, which constraint 5 says is table stakes, not the product. `ForecastCard` already handles `scope: "team"` and `match_*` stats — no new component. |
| 2 | **Attach `probs` and `best_line` to `team_detail.next`.** `league_matches` decorates its rows with `match_probs`, `insight_count` and `_best_line`; `team_detail` calls only `_with_teams`. | P-12 | The *same* `MatchRow` component renders a win/draw/loss bar and a named line on `/league/:id` and two club names and a "v" on `/team/:id`. The club page shows a strictly worse view of the club's own fixture than the league page does. Three fields close it. |
| 3 | **Put the next fixture in the Team header**, in the shape the Player header already uses (`v2-nextfx`: home/away word, both crests, kick-off). | P-12 | Two entity pages, the same question, and only one answers it above the fold. On P-12 you must find and tap a third tab to learn who the club plays next. |
| 4 | **Reverse the Player page order: forecast card first, Quick view second**, and stop drawing the same ten games twice. | P-13 | The visitor arrives asking what we expect; today they meet a control panel ~600 px tall and the answer is below the fold. Worse, Quick view's header already says "1+ shots next match 89% Solid" over a `GameStrip` of the last ten, and the card below says "1+ shot 89%" over a `CardRun` of the same ten — one number and one run, twice, in two different graphic languages, inside one screenful. |
| 5 | **Point P-14 at `GET /api/referees` and delete the per-league chip.** `queries.referee_leaderboard` is cross-league, already built, and called by nothing. | P-14 | The page's own entry point — League → Leaders → Referees → "Compare referees across all leagues" (`League.jsx:112`) — lands on a screen that can only show one league at a time. The link is a promise the destination breaks. |
| 6 | **Collapse three referee tables into one.** `Referees.jsx` shows matches / cards-per-game-normalised / vs-usual; `League.jsx`'s `Referees` shows games / yellow / red / pens / home wins; `Referee.jsx`'s by-league table shows a fifth set. | P-11, P-14, P-15 | Three tables about one subject, no two sharing a column set, so no number a reader learns on one is findable on another. Pick the four-column set from P-14, use it everywhere, and make the League sub-tab a link rather than a fourth rendering. |
| 7 | **Delete P-09/P-10; redirect `/leagues` and `/teams` to `/explore`.** | P-09, P-10 | `/teams` renders a component titled **"Leagues"** that lists leagues — and Explore's "Add [a club]" tile points straight at it. Meanwhile Explore is the same list done better: crest tiles, followed leagues first, country, and what each league has next. Two surfaces, one strictly dominated. |
| 8 | **Decide what `/search` is.** Today it is a modal in a trenchcoat: `aria-modal="true"`, no site header, `body.overflow = hidden`, and a Cancel that calls `history.back()`. Either make it a real destination (rows that carry what distinguishes them) or drop the route and send `/search?q=` to `/explore?q=`. | P-18 | A shared or bookmarked `/search?q=…` link opens a dialog over nothing and offers no way forward but "Cancel". And the rows are eight identical "Team N / Club" lines — a disambiguation list with nothing to disambiguate by. |
| 9 | **One header for all four entity types.** Player uses `v2-ph2` (crest wash, 84 px avatar, display-weight name, metadata row, next fixture, Follow). Team, League and Referee use bare `.phead`. | P-11, P-12, P-13, P-15 | Four pages of one family wearing two headers, and the better one is on exactly one of them. Unifying also fixes P-12's broken 390 px head, where the 64 px crest centres itself against a three-row column and ends up level with the form pills while the club name floats with nothing to its left. |
| 10 | **Tokenise the card colours.** `#f5c518` and `#e5484d` are hard-coded in six rules in `football.css` (`.card-dot--y`, `.card-dot--r`, `.ref-badge`, `.book-bar`, `.bell-badge`, `.ra-tag.is-high`, `.book-alert`). | P-11, P-13, P-14, P-15 | Constraint 2. These are the dominant colour of every referee and bookings surface in the app, they are identical in light and dark, and the owner's palette cannot touch them. Add `--card-y` / `--card-r` to `tokens.css` with a per-mode value. Note the owner cannot theme them until they also join `COLOR_TOKENS` in `site_studio.py`, which is a separate, larger change — the token pair alone is the in-bounds fix. |

---

## P-09 / P-10 — Leagues (`/leagues`, `/teams`)

**Purpose.** Get the visitor from "a league" to a specific league.

**Inventory.**

| Section | Verdict | Reason |
|---|---|---|
| H1 "Leagues" | **change** on `/teams` | `/teams` renders the same component, so a reader who asked for clubs is told they are looking at leagues. |
| `leagues-search` input | **delete** | The site header carries a global search on every page, and Explore's filter box already does this job *and* says it only filters the list. This is the third search box on the journey. |
| Country cards → league rows | **move** to Explore | Explore's `ex-grid` shows the same leagues with the crest, the country, followed-first ordering, and what each one has next. This shows the name and the season string, which answers nothing. |

**Hierarchy.** The first screenful is an H1, an empty search box and one card. Below that, a
newsletter block takes more vertical space than the page's whole content. Nothing here is wrong;
there is simply nothing here.

**Consistency.** This is the only entity *list* that is a flat `<ul>` of names. The Referees list is
a table, the squad list is a card grid, the Explore list is a tile grid. Four list idioms.

**Faults in the render.** On a 12-league set this is a long alphabetical wall with no favourites and
no "what's on". On the demo set it is one row.

**Missing.** Which leagues have matches today — the data is already in the response (`today`, `next`)
and Explore uses it. This page drops both fields on the floor.

**Proposals.**
1. Delete both routes and redirect to `/explore`. (#7 above.) Keeps every existing link working,
   removes a screen, and upgrades the destination.
2. If they must stay, at minimum relabel `/teams` and render `nextLabel(l)` as Explore does.

---

## P-11 — League (`/league/:id`)

**Purpose.** Everything about one competition: who plays next and what we expect, where everyone
stands, and who the standouts are.

**The best of the four.** `MatchRow` carries the win/draw/loss bar and a named leading line
("Player 204 · 2+ tackles · 82%"), so the first screenful is genuinely forecast-led. The tab
consolidation noted in the source comment (Overview absorbed into Fixtures) was right.

**Inventory.**

| Section | Verdict | Reason |
|---|---|---|
| `.phead` — mark, name, country · season | **change** | No Follow button, though `routes_me.py:46` accepts `kind: "league"`. The one entity you cannot follow from its own page. |
| Tabs: Fixtures / Table / Teams / Leaders | **keep** | Four is right, and each answers a different question. |
| Upcoming / Results segmented | **keep** | |
| Fixture list | **change** | Repeats "Fri, Nov 6" six times then "Fri, Nov 13" six times instead of grouping under a date heading, and ignores `round`, which is in the data (`round: 20`). |
| — the later round's rows | **change** | They carry no bar and no line, because forecasts only exist near kick-off. The list goes from rich to bare halfway down with no explanation, which reads as a broken page rather than an honest one. One line — "Forecasts open closer to kick-off" — fixes it. |
| `Assignments` "Next round referees" | **keep**, **move** | Correct, well-handled stub ("Not named yet…" instead of six cards saying one thing). But it is below twelve fixtures, at the page's foot. It belongs under the round it describes. |
| Table (`Standings`) | **change** | Built client-side from `/leagues/:id/fixtures?status=final&limit=400`. See faults. |
| Teams (`TeamMatrix`) | **keep** | Genuinely good: ranked bars on a phone, heat map behind a control, tick-two-to-compare. |
| Leaders → Players | **change** | A 30-row table of season totals, uncapped. The only sub-tab here with no forecast in it. |
| Leaders → Bookings | **keep** | Ranked list of who is most likely to be carded next round, with the opponent and the referee. This is what the Players sub-tab should look like. |
| Leaders → Referees | **move** | A third referee table (see #6). Make it a link to P-14 filtered to this league. |

**Hierarchy.** Yes — the first screenful is the next round with a forecast on each row. Good.

**Consistency.** Diverges from P-12/P-13 on the header (no wash, no Follow, small mark) and on
stat presentation: Leaders is an HTML table where Team's equivalent is `tbar` bars and
`tiles4` tiles and Player's is `GameStrip`.

**Faults in the render (390 px, dark).**
1. `MatchRow` wraps to three lines and the "v" lands at the **far right of the home team's line**,
   not between the clubs: `Team 0 ————————— v` / `————————— Team 2`. Reads as a typo.
2. The second round of fixtures is visually identical to the first but has no bar and no line — a
   cliff with no sign.
3. Two tab strips stack inside Leaders (main tabs, then Players/Bookings/Referees, then a Stat
   select and a Total/Per 90 segment): three control rows before any content, on a 390 px screen.
4. "Next round referees" is one grey sentence hanging at the bottom of a 2,900 px page.
5. **Three overlapping fetches of the same collection.** `/leagues/:id` ships `recent` — twenty
   fully decorated final matches, with `match_probs`, forecast counts and `_best_line` computed for
   each — and `League.jsx` never reads `d.recent`. The Results view then refetches 60, and
   `Standings` refetches 400. The expensive one is the one that is thrown away.

**Missing.**
- **League averages.** docs/57 says this page shows them; it does not. `referee_assignments`
  computes `league_avg` and spends it on half a sentence. Goals, cards and corners per game,
  with each club's position against them, is the context every other number on the page needs.
- Where the league sits in its season — round 20 of 38, nothing says so.
- Any league-level forecast: who is most likely to win it, who is most likely to go down. The
  `zones` data is already there for the table bands.

**Proposals, ranked.**
1. Group fixtures under date headings and label the round; mark where forecasts stop. *Twelve
   repetitions of a date string are twelve lines of nothing, and the forecast cliff reads as a bug.*
2. Read `d.recent` instead of refetching, and move the table off a 400-row client-side build. *The
   work is already done and paid for; and a table derived from whatever fixtures happen to be
   cached is a table that can be quietly wrong.*
3. Add a league-averages strip under the header. *It is the denominator for every number on this
   page and on every club page that links here.*
4. Add Follow. *Supported by the API, offered on two of four entity pages.*
5. Give Leaders → Players a forecast column or a forecast sort, as Bookings has. *Otherwise one
   sub-tab is the product and its sibling is a spreadsheet.*

---

## P-12 — Team (`/team/:id`)

**Purpose.** What this club does, who plays for it, and what we expect of them next.

**It does not do the third thing at all.** This is the worst page in the set.

**Inventory.**

| Section | Verdict | Reason |
|---|---|---|
| `.phead` — crest, name, league link | **change** | Breaks at 390 px (see faults). No next fixture, no league position, no record. |
| `FormPills` W L D D L | **change** | The scoreline and the opponent are in `title`, which does not exist on touch. Five letters with no referent. |
| `TacticChip`s | **keep** | |
| Follow | **keep** | |
| "Compare with…" | **move** | A secondary destination sitting above the fold while the forecast is absent. Move it beside the Numbers tab. |
| Tabs: Squad / Numbers / Fixtures | **change** | The three-from-six consolidation was right, but the default landing is Squad. |
| Squad → Cards (default) | **move below the forecast** | Fourteen cards, each a six-column `dl` of season totals, ~2,800 px. On demo data the Goals column is `0` for all fourteen — a fixed stat set that cannot adapt to what the club actually does. |
| Squad → Grid | **keep** | The hide-a-game-from-the-average control is a real idea and well executed. |
| Numbers → Match by match / Against / Who scores first | **keep**, **change presentation** | Right content, three bespoke chart idioms (`tbar`, `tiles4`, `fg-stats`), none of them the shared run graphic. |
| Fixtures | **change** | Two bare rows. See #2. |
| *A forecast section* | **add** | Does not exist. |

**Hierarchy.** No. The question a visitor brings to a club page — "what happens when they play
next, and what do we expect?" — is answered by nothing in the first ten screenfuls. What they get
is a season appearance table.

**Consistency — the headline finding.** A club page and a player page do **not** tell the same kind
of story in the same shapes:

| | Player (P-13) | Team (P-12) |
|---|---|---|
| Header | `v2-ph2`: crest wash, 84 px avatar, display name, club chip, position chip | `.phead`: 64 px crest, plain name |
| Next fixture | in the header, both crests, home/away, kick-off | nowhere; third tab, undecorated |
| Forecast | "What we expect next match", shared `ForecastCard` | **none** |
| Interrogation | Quick view: market × line × window × venue × started | none |
| Standing | `Ranks` — "47th of 168 for shots" | none |
| Run graphic | `GameStrip` / `CardRun` | `tbar`, `tiles4` bars |
| Private note | yes | no |

Six of seven rows differ. These are the same kind of object — a thing that plays football next
Saturday — and only one of them is treated as one.

**Faults in the render (390 px, dark).**
1. **The header is broken.** `.phead` is `display:flex; align-items:center`. The right column runs
   name → league → (form + chips + Follow + Compare), so the 64 px crest centres itself against the
   whole column and ends up level with the form pills, while "Team 4" sits at the top with empty
   space to its left. The crest reads as belonging to the form row.
2. Fourteen near-identical cards with no grouping beyond an implicit position sort, no section
   headings, and an all-zero column.
3. The Fixtures tab: two rows, no bar, no line, no venue word, no round.
4. No horizontal scroll at 390 px. Light mode renders correctly.

**Missing.**
- The forecast. (#1.)
- League position and points — the club's own standing, which the league page already computes.
- Who is doubtful or suspended for the next match. `_availability` exists in `queries.py`.
- Home/away split anywhere in the header or Numbers tab.
- An equivalent of Player's `Ranks`: where this club sits in the league for the stats it is
  judged on.

**Proposals, ranked.**
1. Add "What we expect next match" with team-scope `ForecastCard`s, directly under the header,
   above the tabs. *The product forecasts; this page does not.*
2. Decorate `team_detail.next` so the shared `MatchRow` works. *A three-field backend gap is making
   a shared component render worse on one page than another.*
3. Move the next fixture into the header and rebuild the header on `v2-ph2`. *Fixes the question
   order and the 390 px layout in one move.*
4. Add league position + points + goal difference to the header metadata row. *Needs `team_detail`
   to carry the standings row, or a client-side read of the league table the page already links to.*
5. Make the squad cards' stat columns follow the club's position mix, or cut them to three and send
   the rest to the Grid view. *Six fixed columns including one that is always zero is a template,
   not a presentation.*
6. Give form pills a readable scoreline on touch. *A `title` attribute is not an interface.*

---

## P-13 — Player (`/player/:id`)

**Purpose.** What we expect from this player in his next match, and whether his record supports it.

**Recently reworked and much the strongest of the four on craft.** The header does its job: name,
club chip, position, next fixture with both crests and home/away, Follow. The Quick view resolving
any market and line off the stored ladder is the single best idea in the set. The reason sentence
("Takes a larger share of the team's shots than usual in the role") is exactly the register the
product wants.

**Inventory.**

| Section | Verdict | Reason |
|---|---|---|
| `v2-ph2` header | **keep**, one change | `text-transform: uppercase` on `.v2-ph2-name`. Fine for "PLAYER 405"; wrong for "VIRGIL VAN DIJK" and "RASMUS HØJLUND", and applied on no other entity page. |
| Quick view (`History`) | **keep**, **move below the forecast** | The interrogation tool, not the answer. |
| — its forecast line ("1+ shots next match 89% Solid") | **keep** | The right bridge between the run and the expectation. |
| — "Show table" / `ColumnPicker` / history table | **keep** | Correctly progressive. |
| "What we expect next match" | **keep**, **move to first** | This is the page. |
| `Ranks` | **keep**, **change layout** | Three tiles in a two-column grid leaves an orphan. Four stats, or a single row. |
| `Note` | **keep** | |

**Hierarchy.** No — inverted. The control panel is first and the answer is second, which also
contradicts the source comment at `Player.jsx:143` that says the page leads with Quick view *because*
the old overview box was redundant. The redundancy was not removed, it was swapped: the forecast
card and the Quick view now draw the same ten games and print the same percentage within one
screenful, in two different idioms (`CardRun`'s eleven-column strip ending in TONIGHT vs
`GameStrip`'s minutes-above-crest-below columns).

**Consistency.** The run graphic appears here in two forms; everywhere else in the entity family it
appears in none. `RunStrip` in `Marks.jsx` — described in its own comment as "the signature graphic
of the product" — is **imported by nothing in the application**; only `DevKit` renders `HitStrip`.

**Faults in the render (390 px, dark).**
1. The next-fixture block in the header wraps so that the "v" is orphaned at the end of the first
   line: `Home | Team 4 v` / `Team 11`. Same defect as `MatchRow` on P-11, different component.
2. The forecast card is below the fold on a 390×844 screen; the first screenful ends inside the
   Quick view's Line segment.
3. `pl-ranks` leaves a visible hole in the grid.
4. No horizontal scroll. Light mode renders correctly.

**Missing.**
- Nothing about **who he is** beyond the name and position. Flagged in the brief: the player
  document holds only `name`, `pos`, `image`, `team_iid`. Shirt number, age, height and foot all
  need an ingest change, and I am not proposing them. But two things do not: **minutes trend**
  (whether he has been starting, which `player_history` already returns and which the forecast's
  own "Assumes he plays" caveat depends on) and **season totals** (which `squad_season` already
  computes for the club page and which this page, oddly, does not show).
- Whether he is injured, suspended or doubtful.
- What he did in the reverse fixture against this opponent.

**Proposals, ranked.**
1. Forecast card first; Quick view second, retitled to what it is ("Check another line"). *The
   visitor's question first, the tool to interrogate the answer second.*
2. Pick one run graphic for this page. Keep `CardRun` on the card and let the Quick view's
   `GameStrip` be the only full-size run — or drop `CardRun` here and let the card link into the
   Quick view set to its line. *Drawing one run twice in two languages makes the reader check
   whether they agree.*
3. Drop `text-transform: uppercase`, or apply it to Team and League too. *Either is a family;
   one page shouting is not.*
4. Add a minutes/starts line to the header metadata. *The number on the card is conditional on his
   playing, and the page makes the reader take that on trust.*
5. Four rank tiles, or one row. *An orphan tile in a two-column grid reads as a missing one.*

---

## P-14 — Referees (`/referees`) and P-15 — Referee (`/referee/:name`)

**Purpose.** P-14: which officials give the most cards. P-15: one official's record and tendencies.

**Do they justify being two screens?** In principle yes — a ranked comparison and a single record
are different jobs. **As built, no**, for three reasons: they share no number (P-14 shows
cards-per-game *normalised* and a vs-usual factor; P-15 shows raw yellows, reds, pens, home-win and
draw rates, and never mentions normalisation); P-14 cannot be read across leagues, so it is not a
comparison; and neither answers the one question a forecast reader brings — *who is refereeing the
matches I am about to read about, and what does that do to the card lines?* That answer exists, on a
third page: `League.jsx`'s `Assignments`.

**Inventory — P-14.**

| Section | Verdict | Reason |
|---|---|---|
| H1 + lead paragraph | **keep** | The explanation of "vs teams' usual" is good, honest copy. |
| `ChipsRow` league filter | **delete** | It is the reason the page cannot do the job its own inbound link promises. `referee_leaderboard` is cross-league and unused. |
| Table: Referee / Matches / Cards per game / vs usual | **keep** | Four well-chosen columns, and the normalisation is the page's one real idea. |
| *Next assignment* | **add** | The only forward-looking fact about a referee, and the only one a forecast reader needs. `referee_assignments` already computes it per league. |

**Inventory — P-15.**

| Section | Verdict | Reason |
|---|---|---|
| `.phead` + `.ref-badge` | **change** | A 64 px yellow/red gradient rectangle standing in for a person. It is also the hex-literal offender (#10). |
| `ref-tiles` — 6 metrics | **change** | Three columns on a phone, six on desktop; "Home wins" and "Draws" as referee attributes are a counting-tool number with no causal claim behind them, presented at the same weight as the card rates. |
| "Next matches" | **keep**, **promote** | The most useful block on the page, below the tiles. |
| "By league" table | **keep** | |
| "Matches" table | **keep** | |
| *Normalised cards / vs usual* | **add** | The number P-14 ranks him by does not appear on his own page. |

**Hierarchy.** P-14: yes, for the comparison question. P-15: no — it opens with six equally-weighted
tiles, two of which (home wins, draws) are noise, and buries the fixtures.

**Consistency.** The referee is the only entity with no crest or photo, no Follow, no forecast and
no run graphic. Its header is a third variant. `kind: "referee"` is not in the follows `Literal`, so
following one needs a backend change — worth doing, since a reader who follows a club has a direct
interest in who officiates it.

**Faults in the render.** P-14 renders its empty state; P-15 404s for every name, because demo data
has no referees. Nothing else can be said from the render, which is itself the finding.

**Missing.**
- Any link between a referee and a forecast. A reader on P-15 cannot see which of this weekend's
  card lines his appointment moves — though `booking_risk` already factors the referee in and
  `Assignments` already prints "Cards above average".
- Home/away card split, and cards by half — the two tendencies that would justify the page.
- On P-14, a sense of scale: 4.2 cards a game means nothing without the league average beside it.

**Proposals, ranked.**
1. Point P-14 at `/api/referees` and drop the league chip. (#5.)
2. Put each referee's next appointment on his P-14 row and at the top of P-15, with the
   above/below-average tag `Assignments` already computes. *Turns two record pages into one
   forward-looking surface.*
3. Make P-15 open with the same four numbers P-14 ranked him by, then the fixtures, then history.
   *A reader arriving from the list should find the number that brought them there.*
4. Collapse the League page's Referees sub-tab into a link. (#6.)
5. Tokenise `#f5c518` / `#e5484d`, and replace `.ref-badge` with the referee's initials on a neutral
   surface. *A yellow-and-red rectangle is the only avatar in the app that is a graphic of a concept
   rather than of the entity.*
6. Add a referee to the demo set so these two screens can be reviewed at all.

---

## P-18 — Search (`/search`)

**Purpose.** Stated: search clubs, players, leagues and referees. Actual: a URL that opens the
global overlay.

**Is it a real destination or a redirect in disguise?** A redirect in disguise, and the code says so
plainly — `Following.jsx:247` renders `<SearchOverlay open … onClose={() => nav(-1)} />` and nothing
else.

**Inventory.**

| Section | Verdict | Reason |
|---|---|---|
| The route itself | **change or delete** | It renders `role="dialog" aria-modal="true"`, sets `document.body.style.overflow = "hidden"`, hides the site header and the bottom bar, and its only exit is a "Cancel" that calls `history.back()`. Arriving from a shared link, a bookmark, or Explore's "Search everything", a reader lands in a modal over nothing with no forward path. |
| Query grouping: Players / Teams / Leagues | **keep** | |
| Result rows | **change** | Eight rows reading "Team 0 / Club", "Team 11 / Club". Nothing to choose between them: no league, no form, no next fixture, no forecast. The `so-next` percentage chip exists **for players only**. |
| Fuzzy fallback | **keep** | Good: retries on the first three letters and ranks by edit distance. |
| Recent + Following chips | **keep** | Right content for the pre-typing state. |
| Referees | **add** or correct the docs | `queries.search` queries `players` and `teams` only. docs/57 says this screen searches referees; it never has. Leagues come from a *second* endpoint (`/leagues?q=`) with a different matching rule — a substring match on name or country, so a typo finds players but not leagues. |

**Hierarchy.** For the overlay, yes. For the page, there is no hierarchy because there is no page.

**Consistency.** The one entity surface with no header, no footer and no navigation. Every other
screen in this audit lives inside `Layout`.

**Faults in the render (390 px, dark).** The capture at `/search?q=Team` shows the modal with no app
chrome at all, the disclaimer bar floating at the bottom of an otherwise empty column, and eight
visually identical rows. `document.body.style.overflow = "hidden"` is set on mount and only cleaned
up by the effect's teardown, so a route-rendered overlay leaves the body locked for as long as it is
mounted — which on this route is the whole visit.

**Missing.** Everything that would make a result choosable: the club's league, the player's club and
next fixture, the leading line on each. The data for the last of those is already fetched for
players and thrown away for teams.

**Proposals, ranked.**
1. Pick one. Either (a) delete the route and send `/search?q=` to `/explore?q=`, which already
   filters and already links out to the overlay; or (b) build a real results page inside `Layout`
   with the overlay reserved for the header button. *The current state is the overlay pretending to
   be a page and failing at both.*
2. If it stays: put the leading line on team rows too, and the club on player rows. *A search result
   list with no distinguishing attribute is a list of names.*
3. Either add referees to `queries.search` or correct docs/57. *A documented capability the code has
   never had.*
4. Fold the league lookup into `/api/search` so one matching rule covers all three kinds. *Two
   endpoints with two matching rules means a query can find a club and miss its league.*

---

## Cross-cutting notes

**One family, four grammars.** Compare the four headers (`v2-ph2`, `.phead`×2, `.phead` + a
gradient badge), the four fixture renderings (decorated `MatchRow`, bare `MatchRow`, `v2-nextfx`,
bespoke `ref-row`), and the five stat idioms (`GameStrip`, `CardRun`, `tbar`, `tiles4`, `tbl`).
Every one of these has a single shared component available; most pages do not use it.

**The signature graphic is not deployed.** `RunStrip` — "the signature graphic of the product, and
the answer to the thing HitStrip could never show" — is imported by no page. `HitStrip` survives on
the Finder and in DevKit. The one place the run idea lands is the player page, twice.

**The forecast is on one of four entity pages.** Player has it. League has it, obliquely, as a chip
on a fixture row. Team has none. Referee has none. For a product whose thesis is that a number a
counting tool could produce is table stakes, three of four entity pages are the counting tool.

**Data that exists and is not shown.** `league_detail.recent` (fetched, unused). `referee_leaderboard`
(built, uncalled). `league_avg` in `referee_assignments` (half a sentence). `_availability`
(unused on entity pages). `round` on every match (never printed). `kind: "league"` follows
(supported, no button).

**Nothing proposed here needs an ingest change** except, explicitly: shirt number / age / height /
foot on P-13 (not proposed), `kind: "referee"` follows on P-15 (proposed, flagged), and a referee in
the demo data set (required before P-14 and P-15 can be signed off at all).
