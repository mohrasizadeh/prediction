# 01. Masterplan and features

## 1. What we are building

A football (soccer) statistics app that does two jobs:

1. **Shows the numbers fast.** Every player and team stat across the last 5 to 30 games, in grids that are easy to scan. This matches what PlayerStats.football offers (`02_playerstats_parity.md`).
2. **Forecasts and explains.** For each upcoming match it gives the chance that a player or team reaches a stat line (for example "2 or more shots"), a range around that chance, a tier, and plain reasons. The reasons name the opponent's tactic and, where known, the lineup. **This is the difference.**

Football first. NBA and NFL come later with their own engines and data providers. Build nothing for them now, but keep sport-specific words out of table and route names where it is free to do so.

## 2. Who it is for

Football fans and analysts who want to understand a match through numbers: fantasy players, writers, podcasters, coaches' assistants, students of the game. We write for them. We do not write for or market to gamblers. Words and rules: `03_rules_and_compliance.md`.

## 3. Principles

1. Analysis only. No prices, no links to sellers, no advice about money.
2. $0 API cost to start. PitchAPI is free; cache hard (`07_ingest_and_caching.md`).
3. Great experience first: fast, clear, calm (`04_design_system.md`).
4. Honest. Beta tag until a real-data test passes. Show bands. Show "No data" not 0.
5. Everything adjustable in the Admin by the owner (`10_admin_panel.md`).
6. The browser never calls PitchAPI.

## 4. Scope by phase

| Phase | Contents |
|---|---|
| **P1 (MVP)** | Accounts (sign-up, e-mail verification, sign-in, reset, account settings, devices, optional 2FA, export and delete: `13`); security layer (`15`); Admin with roles (people, staff, settings, keys, logs, security, health, brand, content, inbox, announcements, plans editing, data screens: `10`); first-party analytics; ingest of one league; engine; screens: Today, Match, Insights, Forecast Finder, Team (squad grid, team totals, against, form), Player (quick view, history), League (fixtures, leaderboards), Search, Following (follows, saved, notes), Track Record, Learn, Account. Stats: shots, shots on target, tackles, goals, assists, minutes, possession, xG, corners (as verified). |
| **P2** | Referees; cards, penalties, scored first, goal minute and type (extra calls); fouls, interceptions, clearances, saves (once keys are verified); super sub; column chooser and hide-game; Telegram lineup alerts; newsletter send; player xG; more leagues. |
| **P2b** | Stripe plans and Resend e-mail built and tested in **test mode** (`14`): pricing page, checkout, billing portal, receipts, coupons, revenue, campaigns. Stays switched off in production. |
| **P3** | Switch billing on (only after PitchAPI confirms commercial use and a security review); referral programme; manager history; NBA and NFL. |
| **Never** | Prices, seller links, live in-play (no data), anything listed in `02`, section 5. |

## 5. Screens (user side)

| # | Screen | Question it answers | Main parts | Routes |
|---|---|---|---|---|
| 1 | **Today** | What is on, and where is the best insight? | Date strip; Top insights row; fixtures grouped by league (FixtureRow) | `/api/fixtures`, `/api/insights` |
| 2 | **Match** | What should I expect in this game? | Hero (teams, kickoff, win/draw/loss bar, tactic chips). Tabs: **Forecasts** (ForecastCards, filter by team/market/tier), **Lineups** (pitch, Predicted/Confirmed), **Matchup** (style comparison, tactic explanations), **Players** (last-10 table), **H2H** | `/api/matches/{id}` |
| 3 | **Insights** | What are the strongest forecasts across leagues? | Filters (league, stat, scope, tier); ForecastCard list | `/api/insights` |
| 4 | **Forecast Finder** | Which players meet my criteria? | Filter panel (date, ≤5 leagues, stat, N or more, mode Likelihood/Form/Run, last N, position, home/away, started, minutes); result cards | `/api/finder` |
| 5 | **Leagues** | Which competitions? | Country-grouped list with search | `/api/leagues` |
| 6 | **League** | How is this league doing? | Tabs: Fixtures, Results, Leaderboards, Teams, Referees (P2) | `/api/leagues/{id}/*` |
| 7 | **Team** | How does this team play? | Header (crest, form, tactic chips). Tabs: **Squad grid**, **Team totals**, **Against**, Fixtures | `/api/teams/{id}/*` |
| 8 | **Player** | How does this player perform? | Hero, next-fixture forecasts, Quick view chart (window, line, home/away, started), history table, Follow, Note | `/api/players/{id}` |
| 9 | **Referees** (P2) | Who whistles what? | Table by league | `/api/leagues/{id}/referees` |
| 10 | **Following** | What about my players and teams? | Follows, saved forecasts, notes, upcoming fixtures for followed teams | `/api/me/*` |
| 11 | **Track Record** | Does the model deliver what it says? | Tier table (stated vs actual), reliability chart, Beta explanation | `/api/track-record` |
| 12 | **Learn** | How do I read this? | Articles: how to read a forecast, tiers, tactics, glossary | `/api/public/pages/{slug}` |
| 13 | **Search** | Find a player, team, league | Overlay with grouped results | `/api/search` |
| 14 | **Account** | My settings | Time zone, theme, density, newsletter, alerts (P2), export, delete | `/api/me` |
| 15 | **Auth** | Sign in / create account | Forms; reset (later) | `/api/auth/*` |
| 16 | **Legal** | Terms, privacy, about, FAQ | Markdown pages | `/api/public/pages/{slug}` |

Admin screens: `10_admin_panel.md`.

## 6. Key flows

1. **Open the app → see today.** Land on Today for the user's local date. Top insights row shows up to `home.top_insights_count` Strong and Solid forecasts. Tap a match → Match page.
2. **Read a forecast.** ForecastCard → LikelihoodBar, tier, tactic chips, first reason → "Why" expands the rest and the numbers behind it → Save or Follow.
3. **Find players.** Finder → choose date and leagues → stat and line → mode → Run → cards sorted. Signed-out visitors get `plans.anonymous_finder_searches_per_day` searches a day, then a sign-in prompt.
4. **Scan a squad.** Team → Squad grid → pick stat and window → colour shows which games reached the line → tap a column for the lineups of that game.
5. **Judge the model.** Track Record → see how stated chances compare with results.
6. **Owner runs it.** Admin → key → explorer → leagues → backfill → watch usage and issues → engine run.

## 7. Data the screens need (and where it comes from)

Everything comes from our tables. The sources of those tables are PitchAPI (facts) and the engine (forecasts). The data map is `08_pitchapi_data_guide.md`, section 5.

| Screen part | Needs | Verified? |
|---|---|---|
| Fixtures, scores, kickoff | `matches` | Yes (confirmed in the docs) |
| Shots, minutes (players) | `player_match_stats` | Shots: yes. Minutes: key unverified |
| Shots on target | `player_match_stats.sot` | Inferred from an example |
| Tackles, fouls, saves, interceptions, clearances | `player_match_stats` | Groups exist; keys unverified |
| Team corners, tackles, SoT | `team_match_stats` | Keys unverified |
| Possession, xG | `team_match_stats` | Keys confirmed |
| Lineups, formations | `lineups` | Yes |
| Referee, cards, penalties | `/matches/{id}`, `/events` | Extra calls, phase 2 |

## 8. Success measures (first 90 days)

- Data: one league ingested with zero `missing_field` issues; second ingest run makes zero calls.
- Speed: Today loads in under 1 second on a phone on 4G; any grid under 1.5 seconds.
- Model: the real-data backtest exists and is on the Track Record page.
- Use: weekly returning users, Finder searches per user, forecasts saved.

## 9. Open questions (owner decisions)

| # | Question | Needed for |
|---|---|---|
| Q1 | May we show PitchAPI data in a public product, and a paid one? Is credit required? Images? (guide checks B1 to B3) | Public launch, billing |
| Q2 | Plan names, prices, trial days, free-plan limits (placeholders: Free, Pro 9.99 / 79.99 CAD) | Billing |
| Q3 | Who gets staff roles besides the owner | Admin |
| Q2 | Which leagues first? Suggested: Premier League, then La Liga, Bundesliga, Serie A, Ligue 1. | Backfill |
| Q3 | App name and logo | Brand |
| Q4 | Domain | Deploy |
| Q5 | Is Telegram alerts worth building in P2? | P2 |
