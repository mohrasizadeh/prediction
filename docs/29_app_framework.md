# 29. The app framework: features, admin menus and data points

This is the map of Prediciotn as it stands in `main` today. It lists what the app does, every admin menu, and every data point we pull or work out. Section 8 lists the gaps we see, so we can pick what to improve next.

Where a number comes from code (for example 77 collections), it was counted from the code on the day of writing.

## 1. The app in one page

Prediciotn is a soccer stats and forecast web app. Visitors browse matches, teams, players and referees. Our engine turns past data into chances for player and team lines (for example "2+ shots", "5+ corners"). Visitors can also combine lines into one chance with the combo builder.

| Layer | What we use |
|---|---|
| Frontend | React 18 (Create React App), react-router 6, plain JavaScript, tokens in `styles/base.css` |
| Backend | FastAPI, about 14,000 lines in `backend/`, about 180 routes |
| Database | MongoDB, 77 collections with indexes (`mongo_init.py`) |
| Engine | Python in `backend/soccer_brain`: Dixon-Coles team strength, negative-binomial player lines, scenario mixture, isotonic calibration |
| Data providers | PitchAPI (statistics), SportAPI (live scores, events, lineups), image sources for logos and photos |
| Money and mail | Stripe (billing), Resend (e-mail) |
| Work that runs by itself | One job runner, `POST /api/cron/tick`, called by an outside pinger; `POST /api/jobs/live` for live scores |
| Tests | `backend/run_tests.sh` (21 suites) and `frontend/scripts/check-copy.js` (word check) |

Scope today: **soccer only**. The project brief also names NBA and NFL. Nothing for them exists yet (see section 8).

Leagues are chosen in the admin (Data > Leagues). The brief names the EPL; the app supports any league PitchAPI offers.

## 2. What visitors can do (screens)

Routes from `frontend/src/App.js`.

### 2.1 Browse and forecast
| Screen | Route | What it does |
|---|---|---|
| Today | `/` | Match days with a date strip; top insights; matches for the day |
| Match | `/match/:id` | Match centre: win/draw/loss chances, expected goals, forecasts for both teams, lineups with a badge (confirmed, likely, unsure, bench), form, head to head, referee, tactics and context, "Build one for me" |
| Live | `/live` | Live scores, minute, events (goals, cards, substitutions), lineups |
| Insights | `/insights` | Cards of the strongest forecasts of the day, tiers Strong, Solid, Watch |
| Finder | `/finder` | Search a stat and line across a league (for example "2+ shots, 70% or more"); filters for last N games, position, home or away; shows "95%+" or "under 50%" from the ladder when no line sits in the band |
| Explore | `/explore` | Entry page to leagues, teams, players, referees, compare (shown on desktop nav and in the footer on phone) |
| Compare | `/compare` | Two teams side by side from the team matrix |
| Leagues and League | `/leagues`, `/league/:id` | Table, fixtures, leaderboards, booking risk, referee assignments, team matrix |
| Team | `/team/:id`, `/teams` | History, squad grid (last games per player), totals, first goal, "against" (what opponents do vs this team), tactics |
| Player | `/player/:id` | Per-game history, ranks, forecasts, personal note |
| Referees and Referee | `/referees`, `/referee/:name` | Cards and fouls per game, league assignments |
| Track record | `/track-record` | How our forecasts did: scored outcomes by tier and by stat |
| Search | `/search` | Teams and players by name |
| Learn | `/learn`, `/learn/:slug` | Short articles (managed in the admin) |

### 2.2 Combo builder (update 28)
- A + button on every forecast card and Finder row. One match per combo, up to 6 lines, one line per stat for each player or team.
- A floating bar shows the combined chance. The review sheet shows the range, the weakest line, swap alternatives, notes, Save, Copy as text and Share image.
- "Build one for me" gives three combos: Safer (2 lines, each 80%+), Balanced (3, 65%+), Bolder (4, 55%+). It never includes a player we are unsure will play.
- My combos (`/combos`): coming up (chance now vs when saved) and finished (which lines were reached), plus "How our combined chances did".

### 2.3 Account and personal tools
| Feature | Where | Notes |
|---|---|---|
| Sign up, sign in, 2-step sign-in (2FA), verify e-mail, forgot and reset password, change password | `/sign-up`, `/sign-in`, `/sign-in/2fa`, `/enroll-2fa`, `/verify-email`, `/forgot-password`, `/reset-password`, `/change-password` | Cookie sessions, tokens in `auth_tokens` |
| Following | `/following` | Follow teams and players; feed of their next forecasts |
| Saved forecasts | You area | Save a card by its `fkey`; results shown once scored |
| Player notes | Player page | Private note per player |
| Finder presets | Finder | Saved filter sets |
| Alerts and daily digest | Account | E-mail alerts for followed items and a digest (Pro) |
| Account area | `/account/*` | Profile, billing, plan, security, data export and delete |
| Pricing | `/pricing` | Plans from the admin; Stripe checkout and portal |
| Contact | `/contact` | Form to the admin inbox |
| Newsletter | footer and popups | Sign up, confirm, unsubscribe |
| Welcome, About, Terms, Privacy, Legal pages | `/welcome`, `/about`, `/terms`, `/privacy`, `/legal/:slug` | Text comes from admin Pages |
| Dev kit | `/dev/kit` | Component gallery for builders |

### 2.4 Plans and limits (`plans.py`)
Free and Pro are created on first start; prices are set in the admin.

| Entitlement | Free | Pro |
|---|---|---|
| Finder searches per day | 10 | unlimited |
| Leagues the Finder can search at once | 1 | unlimited |
| Games in squad and team grids | 5 | 10 |
| Insight cards per day | 20 | unlimited |
| Followed teams and players | 10 | unlimited |
| Saved forecasts | 20 | unlimited |
| Player notes | 20 | unlimited |
| Alerts | no | yes |
| Tactical matchup tab | no | yes |
| Export to CSV | no | yes |

Saved combos use the saved-forecasts limit (`saved_max`). Staff can grant a comped plan for a number of days.

### 2.5 Feature switches (`features.*` settings, 24)
insights, finder, squad_grid, team_totals, against, referees, leaderboards, learn, favourites, alerts, newsletter, track_record, following, saved, search, beta_tag, show_xg, show_lineups, show_tactics, require_signin_to_follow, billing, maintenance, live, show_match_probs. Each can be turned off without a release.

## 3. Admin menus (`admin_shell.py`, `/admin/...`)

Nine groups, 34 menu items. Access is by role and permission; the phone layout shows up to 4 tabs plus More.

| Group | Menu | Route | What is in it |
|---|---|---|---|
| Overview | Home | `/admin` | Attention cards, key numbers, what needs doing |
| | Needs you | `/admin/needs` | Open alerts (`admin_alerts`): failed jobs, payment problems, unread mail |
| | Dashboard | `/admin/stats` | Users, sign-ups, plan mix, forecasts served |
| | Analytics | `/admin/analytics` | Realtime, compare periods, acquisition, e-mail, popups, newsletter; CSV export |
| People | Users | `/admin/users` | Search, profile, plan, comp grant, sessions, admin notes, suspend, delete |
| | Staff | `/admin/staff` | Staff accounts, roles, permissions |
| | Inbox | `/admin/inbox` | Contact messages with status |
| | E-mail list | `/admin/newsletter` | Subscribers, export, remove |
| Growth | Popups | `/admin/popups` | Build, schedule, A/B test, per-day stats |
| | Announcements | `/admin/announcements` | Site banners with start and end |
| | Campaigns | `/admin/campaigns` | E-mail campaigns to groups |
| Site | Site Studio | `/admin/studio` | Draft, preview link, diff, publish, versions, rollback, presets, assets |
| | Pages | `/admin/pages` | Legal and content pages (`content_pages`), Learn articles |
| | Images | `/admin/media` | Team logos and player photos: matches, scores, review queue, run sync |
| Money | Plans | `/admin/plans` | Create and edit plans, entitlements, prices |
| | Subscriptions | `/admin/subscriptions` | Status, period end, cancel |
| | Payments | `/admin/payments` | Charges and refunds from Stripe |
| | Coupons | `/admin/coupons` | Codes and limits |
| | Revenue | `/admin/revenue` | Revenue and churn views |
| E-mail | E-mail templates | `/admin/email/templates` | Edit each message |
| | E-mail log | `/admin/email/log` | Sent, delivered, bounced (from Resend webhooks) |
| | Blocked addresses | `/admin/email/blocked` | Suppression list |
| Connect | Integrations | `/admin/integrations` | E-mail provider, audience sync, outgoing webhooks (rotate secret, test, deliveries), tracking tags |
| Data | Leagues | `/admin/data/leagues` | Switch leagues on, sync status, SportAPI team mapping |
| | Jobs | `/admin/data/jobs` | Job runs, request a run, queue |
| | Data quality | `/admin/data/quality` | Coverage per field, ingest issues, resolve |
| | Engine | `/admin/data/engine` | Engine runs, gates, calibration, run now |
| | Endpoint explorer | `/admin/data/explorer` | Try provider endpoints and view raw answers |
| | Cache and usage | `/admin/data/cache` | API cache, daily call budget, call log |
| System | Settings | `/admin/settings` | 218 settings in 29 groups with history |
| | Keys | `/admin/keys` | Provider keys (PitchAPI, SportAPI, Stripe, Resend), stored apart from settings |
| | Logs | `/admin/logs` | App logs, audit log |
| | Security | `/admin/security` | Sign-in log, rate limits, 2FA status |
| | Health | `/admin/health` | Database, jobs, providers, versions |

Also in the admin code: Availability (`Availability.jsx`, injuries and absences) and EngineRuns.

### 3.1 Settings groups (218 settings)
engine 41, features 24, ingest 14, sportapi 14, auth 12, email 12, images 10, security 9, cache 8, context 8, billing 8, copy 7, admin 6, finder 5, tracking 5, home 4, plans 3, referees 3, provider 3, analytics 3, popups 3, integrations 3, grid 2, alerts 2, combo 2, injuries 2, site 2, newsletter 2, track_record 1.

Every change is written to `settings_history` and `audit_log`.

## 4. Data we pull (inputs)

### 4.1 PitchAPI (statistics; the engine learns from this)
Pulled by the ingest queue (`ingest.py`, `cached_fetch.py`). Every call is counted against `ingest.daily_call_budget`, rate-limited (`ingest.rps`, `ingest.concurrency`) and protected by a breaker.

| Pulled | Endpoint idea | Stored in |
|---|---|---|
| Leagues | `/v1/leagues` | `leagues`, `seasons` |
| Teams and players | league and match answers | `teams`, `players` |
| Fixtures (future and past) | fixtures sync | `matches` |
| Match team stats ("All" period) | match stats | `team_match_stats` |
| Match player stats | match players | `player_match_stats` |
| Lineups | lineup watch before kick-off | `lineups` |
| Match events | optional (`ingest.match_extra_events`) | `match_events` |
| Referee for each match | match answer | `matches`, `referee_stats` |

**Team stat columns** (`normalize.TEAM_COLS`): shots, shots on target (sot), corners, tackles, possession (poss), expected goals (xg), fouls, yellow cards.

**Player stat columns** (`normalize.PLAYER_COLS`): minutes, shots, sot, tackles, goals, assists, xg, saves, interceptions, clearances, fouls committed, fouls won; plus position (mapped by `provider.position_map`).

Rules we keep: a missing value stays empty, it is never turned into zero (except shots and sot for a player who played). Goalkeepers have no tackles. The key names are read from `provider.pitchapi.team_keys` and `provider.pitchapi.player_keys`. In the registry defaults many keys are still empty (team shots, sot, corners, tackles, fouls, yellow cards; player minutes, xg, saves, tackles, interceptions, clearances, fouls). A column with no key shows up in `data_coverage` and its market switches off. **Check the live settings to see which are mapped** (section 8).

### 4.2 SportAPI (speed: live and lineups)
Used for nothing else (`sportapi.py`, `docs/23`). Visitors never cause a call.
| Pulled | Stored in |
|---|---|
| Fixtures of a day (live score, minute) | `live_fixtures` |
| Match events (goals, cards, subs), live matches only | `live_events` |
| Lineups (starting XI and bench) at set minutes before kick-off | `live_lineups`, then to the engine (`sportapi.lineups_to_engine`) |
| Final details (half-time score) | `live_fixtures` |
| Past results by date | `live_fixtures` |
| League list for mapping | `sportapi_cache`, `sportapi_team_map` |

Budget: 2,000 calls a day on the plan; we stop at `sportapi.daily_calls` (1,800).

### 4.3 Images
`images.py`, `pitch_photos.py`: team logos and player photos matched by name score into `image_map`, `media`, `image_api_cache`, `image_runs`. Low scores wait in the Images review queue.

### 4.4 Other inputs
- Club calendar (other competitions) into `club_calendar`, used for rest and rotation.
- Injuries and absences into `availability`.
- Match context into `match_context`: what is at play for each side (league places), importance, rest days, referee (`context.*` settings).
- Referee history into `referee_stats`.

### 4.5 Data from visitors and the business
Users, sessions, auth tokens, follows, saved forecasts, combos, notes, presets, alert subscriptions, finder usage, events (site analytics), contact messages, newsletter, popup stats, Stripe webhook events, subscriptions, payments, e-mail log. See section 5.

## 5. MongoDB collections (77)

### Soccer data
leagues, seasons, teams, players, matches, team_match_stats, player_match_stats, lineups, match_events, club_calendar, match_context, referee_stats, availability, team_styles

### Engine output
match_probs, forecasts (with `fkey`, `tier`, `p`, `p_play`, `lineup_badge`, `p_basis`, `ladder`, `is_current`, `hidden`), forecast_outcomes (scored results), engine_runs, engine_gates (walk-forward checks per layer), engine_calibration

### Live
live_fixtures, live_events, live_lineups, sportapi_team_map, sportapi_cache

### Ingest and jobs
ingest_queue, ingest_issues, data_coverage, api_cache, api_call_log, job_runs, job_requests, job_locks

### Images
media, image_map, image_api_cache, image_runs

### Users and sessions
users, sessions, auth_tokens, auth_log, rate_limits, admin_notes

### User features
follows, saved_forecasts, combos, notes, alert_subscriptions, finder_usage

### Money
plans, subscriptions, payments, coupons, webhook_events

### E-mail and growth
email_templates, email_log, email_suppressions, email_campaigns, newsletter, popups, popup_stats, announcements, events, contact_messages

### Site and system
settings, settings_history, provider_keys, content_pages, site_versions, site_assets, audit_log, app_logs, admin_alerts

### Outgoing integrations
integration_jobs, webhook_endpoints, webhook_outbox, webhook_deliveries

Self-cleaning (TTL) collections: api_cache, api_call_log, job_locks, image_api_cache, sportapi_cache, finder_usage, sessions, auth_tokens, rate_limits, auth_log, app_logs, events, popup_stats, integration_jobs, webhook_outbox, webhook_deliveries, webhook_events.

User data removed on account delete (`accounts.USER_DATA`): follows, saved_forecasts, notes, alert_subscriptions, follow_alerts, combos.

## 6. What we work out (engine outputs)

### 6.1 Match level
- Team strength (Dixon-Coles) with time decay (`engine.half_life_rounds`).
- Expected goals and win/draw/loss chances (`match_probs`).
- Team style vectors from past games only; named tactics (low block, high press, possession-based) and matchups.
- Team totals by negative-binomial regression: goals, shots, shots on target, corners, tackles. Default team lines: corners 4.5, shots 11.5.
- Lineup layer: how much each starter moves team output (ridge regression), applied to expected lineups.
- Normalised corner averages (`team_norm`), referee card and foul tendencies, rest and competition importance (optional layers, each behind a walk-forward gate).

### 6.2 Player level
- Each player's shrunk share of the team total, times a minutes mixture (starts, comes on, does not play).
- Player markets today (`PLAYER_STATS`): shots, shots on target, tackles. Default lines: shots 0.5 and 1.5, sot 0.5, tackles 1.5 and 2.5. More lines come from `engine.player_ladder`.
- "If he plays" chance (`condition_on_play`), chance to play (`p_play`), lineup badge: confirmed, likely (cut-off 80%), unsure, bench.
- Credible range for each chance; plain reasons that name the opponent's tactic and personnel.

### 6.3 Forecast cards
- Calibration with isotonic fit (`engine_calibration`), tiers Strong, Solid, Watch (`engine.tier_strong`, `engine.tier_solid`).
- Lines kept in the band 50% to 95% (`engine.line_band`); a ladder of other lines stored on each card.
- Scored after the match into `forecast_outcomes`, which feeds the Track record page and the calibration refit.

### 6.4 Combos
Chance of a line = p x p_play for a player, p for a team. Product across entities; before lineups a small correction (`combo.pre_factors`: 1.0, 1.11, 1.19, 1.25 for 1 to 4 entities); two stats for one player use a joint rule; the same stat twice is refused; cap 97%. Up to 6 lines (`combo.max_lines`).

## 7. Jobs that run by themselves (`jobs.py`, one tick)

reference_sync, fixtures_sync, results_sync, backfill, lineup_watch, referee_watch, photo_plan, queue (ingest), score, referees, integrations (audience sync and webhook delivery), images, follow_alerts, alerts, digest, cleanup, calibration, injuries. The engine run and live tick have their own entry points. A run guard (`job_locks`) stops two ticks overlapping.

## 8. Gaps and improvement ideas

Ordered roughly by how much they change the product.

### Product
1. **NBA and NFL are missing.** The brief names them. The data model has `league_iid` but the stats columns, engine markets and screens are soccer shaped. Doing them is a project of its own: new providers, new stat columns, new engine per sport.
2. **Only three player markets** (shots, shots on target, tackles) and few team markets. Goals, assists, cards, fouls, saves, and team cards or fouls are in the stats columns but not forecast.
3. **Finder gap:** a group with no line in the 50% to 95% band still has no row.
4. **No market prices.** We show chances, not prices. Adding outside prices would let us show where our chance is above the implied one. This needs a source and a licence, and a check against the word rules in doc 03.
5. **No push alerts.** Alerts go by e-mail only.
6. **Combos:** no price, no history of what we suggested versus what users saved; correction tested up to 4 entities on one season of three leagues.
7. **Phone nav** dropped Explore from the bottom bar; reach it from the footer.
8. **Share image and Copy as text** are not yet tested on real phones.
9. **Compare** covers teams only; players cannot be compared.
10. **Languages:** English only.

### Data
1. **Confirm the live PitchAPI key map.** Many registry defaults are empty. Open Admin > Data > Data quality and look for fields at 0% coverage.
2. **Market prices, weather, pitch, referee strictness history, travel** are not pulled.
3. **Lineups:** two sources (PitchAPI watch and SportAPI). Pick one as the truth for the badge and log disagreements.
4. **`/api/match-days` returned an error in the demo.** Check it on real data.
5. **Player ids across providers** are matched by name score; a wrong match shows a wrong photo or lineup. Keep the review queue short.
6. **Backfill depth:** `engine.history_rounds` and `ingest.fixture_window_days` decide how much history the engine sees. Confirm there are at least two seasons per league.

### Engine
1. Pre-lineup correction is fitted on one season; refit as outcomes grow.
2. Optional layers (tactics, shape, context, extra stats) are off until they pass the gate; list which have passed in Admin > Engine.
3. Player minutes model: use starter history and rest days more.
4. A per-league report of calibration error by tier on the Track record page.

### Admin
1. A single "Data health" page that joins coverage, issues, job failures and provider budget.
2. Role templates for staff (support, content, finance).
3. Scheduled reports by e-mail.
4. An undo for bulk actions (image approvals, user suspends).

### Code
1. `routes_site.py` (about 670 lines) and `routes_admin.py` (74 routes) are large; split by menu group.
2. Frontend has no TypeScript; add types to `lib/api.js` and the combo files first.
3. Add end-to-end browser tests for the combo flow (the 21 suites are backend only).
4. One long-running worker would replace the outside pinger for jobs.

## 9. How to use this file
Pick items from section 8, write one line for each in the next update document (30, 31, ...), and keep this map current: when a menu, collection or stat column is added, edit sections 3 to 5 in the same change.
