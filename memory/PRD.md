# PRD: Prediciotn (football statistics and forecasts)

## Original problem statement
Hand-off zip (prediciotn.zip): a complete, tested football statistics and forecast web app (React + FastAPI + MongoDB). Backend and forecast engine finished and tested; frontend a working scaffold. Steps: read README, EMERGENT.md, docs/00, docs/03, docs/15 and summarise; put the project in place (replace backend/frontend, copy docs, keep MONGO_URL/DB_NAME/REACT_APP_BACKEND_URL, add APP_ENCRYPTION_KEY, CRON_SHARED_SECRET, PUBLIC_BASE_URL, ENV=development, COOKIE_SECURE=1, ADMIN_EMAIL=smj.rasizadeh@gmail.com, ADMIN_INITIAL_PASSWORD); prove it works (run_tests.sh 12 PASS, /api/public/settings, /api/auth/me, home page, yarn check-copy); build Phase 0 only (site config loader, account screens, admin shell with listed modules; features.billing false; no data screens; no outside services). Rules: do not touch backend/ or soccer_brain/, no own auth/JWT/CORS, API only via lib/api.js, HttpOnly cookie sessions, utc() for times, images only via Media.jsx, loading/empty/error states, mobile first at 390 px, analysis-only copy. User added: "the UIUX is super important to be world class".

## Architecture
- Backend: unchanged hand-off FastAPI (`backend/server.py`, sync pymongo). Env loaded in preview by `/root/.venv/.../sitecustomize.py` (reads backend/.env for the uvicorn process only, since server.py has no dotenv).
- Frontend: CRA + react-router 6, plain CSS. `lib/site.js` (config loader, CSS + font injection, theme), `components/Layout.jsx`, `components/Ui.jsx`, `components/Icon.jsx`, `pages/Auth.jsx`, `pages/Account.jsx`, `admin/*` (shell + 13 modules), `styles/base.css`, `styles/admin.css`. Fonts self-hosted (public/fonts + @fontsource-variable).

## User personas
Owner (Moh), staff (admin/support/analyst), signed-in users, visitors.

## Implemented (2026-10-26) — Phase 0
- Site config loader (ETag, 60 s + focus revalidation, preview token, maintenance, redirects aliases), Beta tag, config-driven rail/top nav, phone bottom bar + More, footer with disclaimer, cookie banner, announcements bar.
- Auth: sign in + 2FA code, sign up + resend, verify, forgot, reset, confirm new e-mail, 2FA enrolment with QR/manual key/recovery codes, forced first-password change, staff gates.
- Account: Profile, Security, Devices, Notifications, Plan and billing, Privacy.
- Admin shell (rail ≥1025 px, bottom bar + All tools sheet + Customize bar), modules: Dashboard, Users, Staff, Settings, Keys, Logs, Security, Health, Site Studio, Pages, Inbox, Announcements, Plans (Sync disabled). Others "Coming in the next phase".
- Tested end to end by testing agent (iteration_1); its 3 bugs fixed plus follow-ups (auth refresh on 429, fewer /auth/me calls, error boundary, sentence case).

## Implemented (2026-10-26) — Phase 1 (frontend) + header logo
- Admin → Endpoint explorer, Cache and usage, Leagues screens built (allow-listed call picker, JSON tree, force-refresh confirm, save as fixture; usage meter, 14-day chart, cache table with delete; league cards, season backfill picker with call estimate).
- Owner approved the backend change: routes_data_admin.py is mounted (2 lines in server.py) and tests/selftest_data_admin.py added; run_tests.sh now prints 13 PASS. Screens tested end to end on real routes (iteration_3).
- Header and footer logo: BrandLogo in Media.jsx (logo_light/logo_dark by mode, falls back to the brand mark); Site Studio image upload for logo/favicon/share image; logo in the Studio mini preview.

## Implemented (2026-10-26) — Phase 2 (ingest and jobs) + start of Phase 3
- Owner-approved backend additions: routes_ingest_admin.py (jobs, issues + resolve, coverage, mapping check), routes_cron.py (POST /api/cron/tick, bearer WEBHOOK_CRON_SECRET, background tick, 202) + .emergent/crons.yml every 15 min; normalize.py: players with no stats skipped, missing shots/sot = 0 for players who played (owner decision), missing minutes kept None and logged once per match. New tests: selftest_ingest_admin, selftest_cron, selftest_normalize_gaps (17 test files pass).
- provider.pitchapi.team_keys / player_keys set from real cached answers (check A).
- Admin screens: Jobs, Data quality (Issues, Coverage, Mapping check), Engine (Brain layers, Calendar import, Images review). api.js gained putFile for raw uploads.
- Real data flowing: 6 leagues on (owner), 200+ matches ingested, engine produced first forecasts; Today page shows real fixtures.
- Open: player positions 0% (position_id null in /players; needs lineups-based mapping, backend change); start_model gate reports "no kickoff times" (engine_bridge key mismatch, backend); engine runs list + forecast hide routes not built yet (Phase 3 backend proposal).

## Implemented (2026-10-26) — Engine screen finish (owner-approved)
- normalize.lineup_pos: position from lineups (starters by pitch_x depth, subs by provider.position_map); GK tackles None. Backfilled 11,789 player rows + 2,178 players from saved lineups; engine rerun on 6 leagues -> 2,280 player forecasts (Serie A). Rotation gate now reports real reason ("only N player-match rows", needs more data) instead of "no kickoff times".
- routes_ingest_admin.py: GET /api/admin/engine (runs + markets), GET /api/admin/forecasts (browser), POST /api/admin/forecasts/{id}/hide (reason required, audited). engine_bridge.py keeps Hide across reruns by fkey. Test selftest_engine_admin.py (18 test files pass).
- Frontend: Engine tabs Runs + Forecasts (EngineRuns.jsx). Testing agent iteration_5: backend 8/8, frontend all flows pass.
- Images: images.leagues set (78,2,3,140,39,135), images.enabled on (owner asked to pull logos/photos). First sync: 6 league logos, 74 crests, 74 player photos; stopped on API-Football daily budget; continues via Sync images.

## Implemented (2026-10-26) — Phase 4 public screens + twice-yearly image sync
- Public screens: Match (hero, Forecasts with filters + show more, Lineups pitch, Players, H2H, Matchup), League (Fixtures, Results, Leaderboards, Teams), Leagues (search), Team (Squad grid, Team totals, Against, Fixtures, plan-cap note), Player (next match forecasts, Quick view chart, history table). Shared components/Football.jsx, styles/football.css. Pages read only our database; images only /api/media.
- queries.py (owner-approved): names/crests added for opponents, H2H, team next matches, starters, player next match, team league. Also fixed: squad grid now uses the team's last N matches (plan cap + venue respected), match styles newest wins.
- routes_cron.py: POST /api/cron/images/{refresh|continue}; crons.yml: 1 Jan/Aug refresh, 2-5 Jan/Aug continue, 03:00 UTC. Tests selftest_public_names.py + cron tests (19 test files pass). Testing agent iteration_6: all flows pass.

## Implemented (2026-10-26) — Phase 4 finished + match share card
- Insights (stat/scope/tier filters), Forecast Finder (leagues per plan, Likelihood/Form/Run, filters in URL), Search (200 ms debounce), Following (Upcoming, Follows, Saved), Track record (collecting state until 300 scored). Save star on ForecastCards, Follow on Team/Player, private player notes.
- Share card: browser canvas PNG (1200x630) with both crests, kickoff, win/draw/loss and top forecast; Web Share or download. No server route (owner choice).
- Backend (owner-approved): finder rows get team + next match names; /me/saved and /me/following-feed forecasts decorated; GET /api/auth/me counted in the read rate limit (security_mw.py). auth.js retries /auth/me on 429.
- Testing agent iterations 7-8: all flows pass after fixes.

## Implemented (2026-10-26) — Phase 4b money and e-mail (test mode)
- Stripe claimable test sandbox provisioned; keys saved in the app key store (stripe_secret, stripe_webhook); features.billing on; Pro synced to Stripe (CAD 9.99/month, 79.99/year, 5-day trial). Webhook also at /api/stripe/webhook. billing.success_url=/account/plan?status=success.
- Pricing page, Stripe checkout, Confirming poll, Manage billing (portal), trial label. Admin Money: Plans Sync, Subscriptions, Payments + refund, Coupons, Revenue. Admin E-mail: Templates, Blocked addresses, Campaigns.
- Cards print home v away (home_iid added in queries._decorate and insights).
- Testing agent iteration_9: full checkout to Pro works; 5 display bugs fixed afterwards.
- Tax: owner chose to handle tax in Stripe directly (prices tax-included, not registered yet); no app change.
- 2026-10-26: Admin Subscriptions and Payments rows show the member's e-mail ("Deleted member" if the account is gone).
- 2026-10-26: Member Lookup: clicking an e-mail in Money opens a side panel (subscriptions + payments) with "Open full profile" -> /admin/users?open=id. Phone card lists fixed (in-row buttons work). E-mails masked for roles without users.pii.
- 2026-10-26: Emergent Managed Email (Resend) wired as e-mail provider "emergent" (transports.Emergent + email_gate safety check; .env EMERGENT_EMAIL_KEY, EMAIL_FROM_NAME=Forecast). email.enabled on. New template pro_welcome, sent once when a subscription first becomes active/trialing (plan, trial end, first renewal date). Campaigns are refused while the managed provider is active (account/payment e-mails only).

## Backlog
- P0: Phase 4c (popups, footer e-mail form, cookie/tag loader, growth admin screens).
- P1: Member e-mail in admin Subscriptions/Payments rows; turn off Stripe adaptive pricing (shows USD); e-mail key for sending.
- P2: ForecastCard shows home v away order; Finder rejects player-only stats for teams.
- P1: Index on forecasts.id; player_detail filter forecasts to next match.
- P2: Debounce market filter; started marker for past-kickoff forecasts; friendlier date pickers in Announcements.

## Next tasks
Wait for the owner's next phase prompt.
