# 02. PlayerStats.football: feature inventory and parity matrix

**Goal.** Our app offers every analysis feature PlayerStats.football offers. It also does what they do not: forecasts, reasons, tactics, uncertainty and a public track record.

**Our line.** We are analysis only. We do not show prices, do not link to sellers, do not promote wagering. Their price features are out. See section 5.

## 1. How this was built

Read on 2026-10-25: their home page, Features page, Prop Finder page, In-Play page, About page, full changelog (38 entries, 21/06/2024 to 03/10/2025), and a Sportmonks case study about them.
The pages were read through a summarising tool. Their Stats Hub page is a landing page with no tables. Their screenshots and logged-in views were not seen. Anything marked **Check** needs a look at the live site while signed in (Moh has the trial).

## 2. Words we use (use them everywhere)

| They say | We say | Why |
|---|---|---|
| Prop, player prop | Market | No wagering words |
| Prop Finder | **Forecast Finder** | Our name |
| Hit rate, % hit rate | **Reached X of last N** | Plain, factual |
| Streak | **Run** | Plain |
| Threshold mode | **Form** mode | Past games only |
| (none) | **Likelihood** mode | Our forecast: the chance it happens next game |
| 1+, 2+, 3+ | "N or more" | Same idea |
| Odds, Odds Builder | (not offered) | Out of scope |

The full list of words we never use is in `03_rules_and_compliance.md`.

## 3. Parity matrix

Columns. **Ours** = what we build. **Data** = whether PitchAPI can feed it (see `08_pitchapi_data_guide.md`): *Yes* = confirmed in their docs, *Likely* = group exists but key unverified, *Extra call* = needs `/events` or `/matches/{id}` (settings `ingest.match_extra_events`, `ingest.match_extra_detail`), *No* = not available. **Phase** = P1 MVP, P2 next, P3 later.

### 3.1 Navigation and home

| # | PlayerStats feature | Ours | Data | Phase |
|---|---|---|---|---|
| 1 | Date strip (about two weeks), "Today" highlighted | Date strip, `home.date_back_days` and `home.date_forward_days` | Yes | P1 |
| 2 | Fixtures grouped by league and country | Same, collapsible league groups | Yes | P1 |
| 3 | Fixture row: teams, referee, kickoff, live score | Teams, kickoff in user time zone, final score, **win/draw/loss bar**, **insight count**. Referee shows when known. | Yes. Referee: Extra call | P1 (referee P2) |
| 4 | "Lineups not available" status | Lineup chip: Predicted / Confirmed / Not yet | Yes | P1 |
| 5 | Links: Lineups, View Fixture, View Stats | One tap to Match page, tabs inside | Yes | P1 |
| 6 | Previous fixtures on the home page (20/02/2025) | Date strip goes back; Results tab on League page | Yes | P1 |
| 7 | Favourite leagues and fixtures shown first (25/09/2024) | "Following" leagues sort first | Yes | P1 |
| 8 | Time zone setting (11/02/2025) | Time zone in Account, default from browser | n/a | P1 |
| 9 | League search, country grouping (31/07/2024) | Leagues page with country groups and search | Yes (`/v1/leagues`) | P1 |
| 10 | 100+ competitions | Up to 77 leagues in PitchAPI. Admin switches them on. We start with top 5. | Yes | P1 |
| 11 | Top-bar nav: Fixtures, In-Play, Leagues, Prop Finder, Referees, Learn, Favourites | Today, Finder, Insights, Leagues, Following (+ Referees and Learn under More) | n/a | P1 |
| 12 | Free tag on some fixtures | Not needed while everything is free. Plan entitlements (doc 13) decide it when `features.billing` is on. | n/a | P3 |

### 3.2 Player stats (squad view)

| # | PlayerStats feature | Ours | Data | Phase |
|---|---|---|---|---|
| 13 | Whole squad across 30+ games in one grid | **Squad grid**: rows = players, columns = last N games (up to `grid.max_games` = 30), cell = stat value, colour by whether it reached the line | Yes | P1 |
| 14 | Stats in the grid: shots, SoT, tackles, fouls, passes, offsides, cards, goals, assists, interceptions, clearances, saves, xG | Shots, SoT, tackles, goals, assists, minutes in P1. Interceptions, clearances, saves, fouls, xG when keys are verified. Cards from `/events`. Passes, offsides, dispossessed: only if a key exists. | Shots: Yes. SoT: Likely. Tackles, goals, assists, minutes: Likely. Fouls, interceptions, clearances, saves, xG: Likely. Cards: Extra call. Passes, offsides, dispossessed: Check | P1 / P2 |
| 15 | Last 5 to 30 fixtures, whole season, or head-to-head only | Window picker: 5, 10, 15, 20, 30, Season, H2H | Yes | P1 |
| 16 | Filter by competition and home/away | Same | Yes | P1 |
| 17 | Started-only filter | "Started" toggle | Yes (lineups) | P1 |
| 18 | Minutes filter: 1+, 2+, 3+, custom | Minimum minutes filter | Likely | P1 |
| 19 | Position filter: GK, DEF, MID, ATT | Same, from `provider.position_map` | Likely (map unverified) | P1 |
| 20 | Recently played: hide players with 0 minutes in last 5 games (08/08/2024) | "Hide inactive" toggle | Yes | P1 |
| 21 | Super Sub: add the substitute's stat to the player they replaced (10/03/2025) | **Super sub** toggle. Needs substitution minute and who replaced whom. | Extra call (`/events`) | P2 |
| 22 | Full Player History: all teams and national team | "All teams" toggle | Only for leagues we ingest | P2 |
| 23 | Exclude finished matches | Not needed. Our grid only shows played games; the Finder only shows upcoming fixtures. | n/a | P1 |
| 24 | Remove specific fixtures from tables (10/09/2024) | Tap a column header to hide that game. Saved per user. | n/a | P2 |
| 25 | Customisable table rows (23/08/2024) | Column chooser on every table. Saved per user. | n/a | P2 |
| 26 | Formation and lineup popup on stat tables (15/10/2024) | Tap a game column: popup with both lineups and formations | Yes | P1 |
| 27 | Manager history filter (03/10/2025) | "By manager" filter | No manager data in the endpoints we read | P3 |

### 3.3 Team stats

| # | PlayerStats feature | Ours | Data | Phase |
|---|---|---|---|---|
| 28 | Team totals for shots, corners, others; 30+ games in one view | **Team totals grid**: for and against, last N games | Shots: Likely. SoT, corners, tackles, possession: Likely. xG: Yes. | P1 |
| 29 | Goals, possession, fouls, passes across games | Goals, possession P1. Fouls and passes when keys are verified. | Goals: Yes. Possession: Yes. Fouls, passes: Check | P1 / P2 |
| 30 | Unique stats: 1st/2nd half cards, scored first | Scored first from `/events`. Half cards from `/events`. | Extra call | P2 |
| 31 | Team xG with goals for comparison (11/07/2024) | xG vs goals columns | Yes | P1 |
| 32 | Penalties | From `/events` | Extra call | P2 |

### 3.4 Season leaderboards

| # | PlayerStats feature | Ours | Data | Phase |
|---|---|---|---|---|
| 33 | "Who tops the charts" per stat per season | **Leaderboards**: total and per 90, minimum minutes, by league and season | Yes (our own tables) | P1 |
| 34 | Goals page with goal minute and type (10/09/2024) | Goal minute and type | Extra call | P2 |
| 35 | Yellow card reason and minute (27/08/2024) | Same | Extra call | P2 |
| 36 | Goal involvements = goals + assists (08/10/2024) | Computed | Likely | P1 |
| 37 | Foul involvements = committed + drawn (17/09/2024) | Computed | Likely | P2 |

### 3.5 Opposition ("Against") stats

| # | PlayerStats feature | Ours | Data | Phase |
|---|---|---|---|---|
| 38 | Opposition formation stats in one view: shots, tackles, passes, fouls, cards | **Against view**: what opponents' players did against this team, **by position**, last N games | Yes (our own tables) | P1 |
| 39 | Highlight tool for positional trends | Heat colouring by position plus a "most conceded to" line | Yes | P1 |
| 40 | More opposition foul stats (17/09/2024) | When fouls verified | Likely | P2 |

### 3.6 Head to head

| # | PlayerStats feature | Ours | Data | Phase |
|---|---|---|---|---|
| 41 | Snapshot of the upcoming fixture stats | Match page, **Overview** tab | Yes | P1 |
| 42 | Top player stats from the last 10 games | Match page, **Players** tab | Yes | P1 |
| 43 | Recent games: cards and penalties | Cards and penalties | Extra call | P2 |
| 44 | H2H last 10 games of player shots, SoT, minutes (10/07/2024) | Same, from our tables at no call cost | Yes | P1 |
| 45 | Quick Look: raw player stat history from H2H and lineup popups (25/04/2025, 26/04/2025) | **Quick view** popup on any player name | Yes | P1 |

### 3.7 Prop Finder → Forecast Finder

| # | PlayerStats feature | Ours | Data | Phase |
|---|---|---|---|---|
| 46 | Select date: Today, Tomorrow, next days | Day picker. Only players whose team plays that day. (`finder` takes `day` and `tz`; tested.) | Yes | P1 |
| 47 | Up to 5 leagues, multi-select (14/03/2025) | `finder.max_leagues` = 5 | Yes | P1 |
| 48 | Stat dropdown (19 markets, see 3.7a) | `finder.stats` setting; a stat shows only if its coverage passes `engine.coverage_min` | See 3.7a | P1 / P2 |
| 49 | Value: 1+ to 5+ | `finder.thresholds` = 1 to 5 | n/a | P1 |
| 50 | Mode: Threshold, Streak, % Hit Rate | Mode: **Likelihood** (new), **Form**, **Run** | Yes | P1 |
| 51 | Last X games: 2 to 10, 15 (default 10); quick Last 10 / Last 20 | `finder.last_options` | Yes | P1 |
| 52 | Started game; Played more than N minutes | Same | Yes | P1 |
| 53 | Position filter | Same | Likely | P1 |
| 54 | Home / Away | Same | Yes | P1 |
| 55 | Super Sub, Full Player History | See rows 21 and 22 | Extra call | P2 |
| 56 | "Exclude FT" | Not needed (upcoming only) | n/a | n/a |
| 57 | Data view: "data only, no fluff" | **Compact** density switch (`theme.density`) | n/a | P1 |
| 58 | 3 free searches a day without an account | `plans.anonymous_finder_searches_per_day` = 3, counted in `finder_usage` | n/a | P1 |
| 59 | Player cards with rates and detail (22/01/2025); hit-rate criteria filter (26/01/2025) | Result card: player, next fixture, Likelihood with band, tier, Form (reached X of N), reasons. Filter: minimum Form and minimum Likelihood. | Yes | P1 |
| 60 | Detailed info and league filter in the tool (28/11/2024) | Expand a card for the full reasons and the opponent's tactic | Yes | P1 |
| 61 | Quick links: Fouls, Fouls Drawn, Shots, SoT | Preset chips: Shots, SoT, Tackles (+ more as verified) | Yes | P1 |

**3.7a Market availability.** PlayerStats offers 19 markets. For each, can we offer it?

| Market | Form / Run (past games) | Likelihood (our forecast) | Data |
|---|---|---|---|
| Shots | Yes | **Yes** | Yes |
| Shots on target | Yes | **Yes** | Likely |
| Tackles | Yes | **Yes** | Likely |
| Goals, Assists, Goal involvements | Yes | Later (needs a goals model) | Likely |
| Fouls committed, Fouls drawn, Foul involvements | Yes | Later | Likely |
| Interceptions, Clearances, Duels, Dispossessed | Yes | Later | Likely / Check |
| Goalkeeper saves | Yes | Later | Likely |
| Yellow cards | Yes | Later | Extra call |
| Passes, Offsides | Only if a key exists | Later | Check |
| Shots (first half), Fouls (first half) | No. Per-half endpoints exist (`/players/halves`) but cost a call per match. | No | Extra call |
| Team: corners, shots | Yes | **Yes** | Likely / Likely |

"Later" means the engine has no model for that stat yet. The Finder shows Form and Run for it and hides the Likelihood mode. New engine markets are added in `engine.py` (see `09_engine_integration.md`, section 8).

### 3.8 Player page

| # | PlayerStats feature | Ours | Data | Phase |
|---|---|---|---|---|
| 62 | Player page with filters, graphs, detail (13/01/2025) | **Player page**: hero, next-fixture forecasts, stat chart, history table | Yes | P1 |
| 63 | Last-20-games graph in a popup (12/09/2024) | Bar chart, last N games, with the line drawn | Yes | P1 |
| 64 | Quick-view charts: team/full history, minutes filter, started toggle, 5/10/20 windows, custom line (29/07/2025) | Same controls. Custom line = any N or more. | Yes | P1 |
| 65 | Player history pop-up across all games (21/06/2024) | History table, all ingested games | Yes | P1 |
| 66 | Player xG (12/08/2024) | xG column when verified | Likely | P2 |
| 67 | Saves and clearances stats (27/01/2025) | Same | Likely | P2 |

### 3.9 Lineups

| # | PlayerStats feature | Ours | Data | Phase |
|---|---|---|---|---|
| 68 | Lineups tool: expected or confirmed | Match page, **Lineups** tab: pitch view, Predicted / Confirmed label, formation | Yes | P1 |
| 69 | Telegram Lineup Alerts | Telegram bot message when a followed team's lineup is confirmed. Setting `alerts.telegram_enabled`. | Yes | P2 |

### 3.10 Referees

| # | PlayerStats feature | Ours | Data | Phase |
|---|---|---|---|---|
| 70 | Referee stats index, by competition (16/12/2024) | **Referees** page: matches, fouls, cards, penalties per match | Extra call (`/matches/{id}` for the name, `/events` for cards) | P2 |
| 71 | Referee name on the fixture row | Same | Extra call | P2 |

### 3.11 Favourites, notes, accounts

| # | PlayerStats feature | Ours | Data | Phase |
|---|---|---|---|---|
| 72 | Favourite players, with custom notes (01/11/2024) | **Following**: players, teams, leagues. Private notes on players. | n/a | P1 |
| 73 | Login / sign up | Email + password; Google when `auth.google_enabled` | n/a | P1 |
| 74 | Weekly newsletter | Sign-up box; Admin exports the list | n/a | P1 |
| 75 | Referral programme | Later | n/a | P3 |
| 76 | Learn pages | **Learn**: how to read a forecast, tiers, tactics, glossary. Edited in Admin. | n/a | P1 |
| 77 | Mobile UI | Mobile first; bottom tab bar | n/a | P1 |
| 78 | 5-day trial, then £7.99 a month | Billing is **off** in the MVP (`features.billing` = false). Settings `plans.*` exist. Turn on only after PitchAPI confirms commercial use. | n/a | P3 |
| 79 | Basketball stats (footer link) | NBA, NFL later. Soccer first. | n/a | P3 |

## 4. What they do not have and we do (this is the product)

| Ours | Where |
|---|---|
| **Likelihood** for each market, with a 10th to 90th percentile band | Finder, Match, Player |
| **Tier** (Strong, Solid, Watch) with the tier name and dot count, never colour alone | Everywhere |
| **Reasons** in plain sentences, naming the opponent's tactic | Cards |
| **Opponent tactic chips** (low block, high press, possession-based) | Match, Team |
| **Matchup tab**: how the two styles interact | Match |
| **Lineup-aware**: confirmed lineups sharpen the forecast, predicted lineups are labelled | Cards |
| **Track Record**: stated chance versus what happened, public | Track Record |
| **Beta tag** until a real-data backtest is stored | Header, Track Record |
| **Match win/draw/loss** from the strength model | Today, Match |

## 5. Excluded on purpose

| PlayerStats feature | Why |
|---|---|
| Pre-match odds on fixture rows | Pricing from sellers. Not our product. |
| Odds Integration (15/08/2025), Odds Explorer (20/09/2025) | Same |
| Odds Builder side panel | Same |
| In-Play Dashboard and its Telegram foul alerts | PitchAPI has no live data. The page lists none. Locked off (`features.live` = false). If a live source is added later, the dashboard and alerts return here. |
| Links or banners to sellers | Never |

## 6. Gaps to close with a PlayerStats look (Check items)

Moh signs in to the trial and answers these once. Write answers under this table.

| # | Question | Answer |
|---|---|---|
| G1 | Which columns does the squad grid show, and which cell colours? | |
| G2 | What does "Season Stats" show beyond the top lists? | |
| G3 | What are the exact Against-stats positions (formation lines, or GK/DEF/MID/ATT)? | |
| G4 | What is on the Player page, tab by tab? | |
| G5 | What does the Referees page list? | |
| G6 | Which features stay behind the paywall after the trial? | |
| G7 | Does the Lineup Alerts bot need an account link? | |
