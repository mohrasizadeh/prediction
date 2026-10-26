# 00. Start here

> **In the GitHub repo** the code is already in place: `backend/` holds every module, `backend/soccer_brain/` the engine, `backend/tests/` the self-tests, `frontend/` a working React scaffold. Where a prompt below says "copy X unchanged", it means "keep `backend/X` as it is". Use the prompts in `/EMERGENT.md` at the repo root; they are the same phases, written for the repo.

This folder is a complete hand-off for Emergent. It has the product plan, every screen, the design system, the database, every query, the caching rules, the data guide, the engine, accounts and security, plans and billing (Stripe), e-mail (Resend), a full admin panel that controls the whole site (look, menus, popups, e-mail list, integrations) and works on phones, tested code, a clickable admin prototype, and a checklist.

**Product in one line.** A football statistics app that shows every player and team stat, and forecasts the chance a player or team reaches a stat line, with the reasons, including the opponent's tactics. Analysis only.

## 1. Folder map

| File | What it is | Read it |
|---|---|---|
| `00_START_HERE.md` | This file: order of work and the prompts | First |
| `01_masterplan_and_features.md` | Vision, scope by phase, 16 screens, flows | Before phase 0 |
| `02_playerstats_parity.md` | Every PlayerStats.football feature, our version, data check, phase | Before phase 4 |
| `03_rules_and_compliance.md` | Banned words, locked settings, honest labels, security | **Before everything** |
| `04_design_system.md` + `design_tokens.json` | Colours, type, components, states | Before phase 0 |
| `05_database_mongodb.md` | Every collection, field, index, size | Before phase 1 |
| `06_api_routes_and_queries.md` | Every route and the query behind it | Before phase 3 |
| `07_ingest_and_caching.md` | The four cache layers, TTLs, budget, jobs, runbook | Before phase 2 |
| `08_pitchapi_data_guide.md` | PitchAPI endpoints, fields, checks | Before phase 2 |
| `09_engine_integration.md` | How to install and call the forecast engine | Before phase 3 |
| `10_admin_panel.md` | The admin panel: 5 roles, 32 modules, every route and permission | Before phase 0 and 1 |
| `11_settings_registry.json` | 175 settings with defaults | Phase 0 |
| `12_acceptance_checklist.md` | What "done" means (A to L) | Every phase end |
| `13_accounts_and_user_features.md` | Sign-up, sign-in, account area, plan limits in the UI, error copy, route map | Before phase 0 and 4 |
| `14_billing_stripe_and_email_resend.md` | Stripe and Resend set-up, flows, webhooks, e-mail templates, what is unverified | Before phase 4b |
| `15_security_and_privacy.md` | Controls and where they live, do-not list, CSP, launch checklist, incident steps, known limits | **Before everything** (with 03) |
| `16_site_studio_popups_integrations.md` | Site Studio (colours, fonts, buttons, menus, footer, SEO, cookie banner, home, images), Popup Maker, e-mail list, e-mail providers, list sync, webhooks, tracking tags, extra analytics, alerts | Before phase 0 (Studio) and phase 4c |
| `18_brain_tactics_and_context.md` | What we tested about tactics, formations, competition importance and rotation; what ships on, what ships gated; how to re-run the proof | Before phase 3 |
| `19_images_logos_photos.md` | League logos, club crests and player photos: one-time sync from API-Football, matching, review, storage, components, rights | Before phase 3 |
| `17_admin_responsive_ui.md` | The admin on phones and tablets: bottom app bar, More sheet, cards instead of tables | Before phase 0 |
| `prototype/admin_prototype.html` | A clickable, responsive admin prototype (open in a browser; fake data). Shows the shell, Studio, Popups, Integrations | Before phase 0 |
| `backend/` | Tested Python to copy in. See its README. | Phases 0 to 3 |
| `backend/soccer_brain/` | The forecast engine | Phase 3 |

## 2. What Emergent gives us, and what it does not

| Fact (from Emergent's pages, read 2026-10-25) | Consequence |
|---|---|
| Default stack: React frontend, FastAPI backend, managed MongoDB | We use MongoDB. All files here are written for it. Supabase or Postgres can be connected, but we do not need them. |
| Secrets live in `.env`; changes take effect only after a redeploy | Put the PitchAPI, Stripe and Resend keys in Admin → Keys, not in `.env`. Only `APP_ENCRYPTION_KEY`, `CRON_SHARED_SECRET`, `PUBLIC_BASE_URL`, the owner e-mail and first password go in `.env` (see `backend/.env.example`). |
| Preview and production use **separate databases** | After the first deploy: run `mongo_init.py`, create the admin, enter the key, enable the league **again in production**. |
| Redeploying updates code, not the database | Schema changes need `mongo_init.py` re-run. |
| First deploy costs about 50 credits; redeploy is free; credits drain fast | Work in phases. Test in preview. Do not ask the agent to rebuild big parts. |
| Scheduled jobs are not documented | We do not rely on them. `POST /api/jobs/tick` is called by a free external pinger (`07`, section 6). |
| GitHub export is on a paid plan | Check your plan before you depend on it. Keep a zip of the project after each phase. |
| Slow queries can time out | Check indexes with `explain()`; keep result lists capped. |
| The agent cannot see the deployed database unless you share logs | Paste logs and error text into chat. |

## 3. How to work with the agent

1. Attach the files for the phase to the chat (or paste them if attachments are not possible). Start every phase with: "Read these files completely before you write code."
2. One phase per conversation turn group. Do not ask for the next phase until the checklist lines for this one pass in preview.
3. When something fails, paste the full error.
4. After each phase, run the self-tests (`backend/MODULES.md`) and the phase's checklist lines.
5. Before deploying: all of checklist A and F6.
6. Never let the agent invent a PitchAPI key name. Unknown keys stay `null` until check A is done.

## 4. The prompts

### Phase 0: foundation, accounts, security, admin shell (no PitchAPI yet)

> You are building a football statistics and forecasting web app on React, FastAPI and MongoDB. Read these files completely first: `00_START_HERE.md`, `01_masterplan_and_features.md`, `03_rules_and_compliance.md`, `15_security_and_privacy.md`, `04_design_system.md`, `design_tokens.json`, `05_database_mongodb.md`, `10_admin_panel.md`, `11_settings_registry.json`, `13_accounts_and_user_features.md`, `16_site_studio_popups_integrations.md`, `17_admin_responsive_ui.md`, and `backend/MODULES.md`. Open `prototype/admin_prototype.html` in a browser and match its layout and behaviour. The rules in `03` and `15` override everything.
>
> Build only Phase 0:
> 1. App shell with the design system: tokens as CSS variables, dark first with a light theme, responsive layout (bottom tab bar on phones, left rail on desktop), the components in `04` as empty-state versions. **The look is not hard-coded:** at start the app calls `GET /api/site/config`, injects the CSS it returns, sets the light/dark mode, loads the self-hosted fonts and draws the menus, footer and cookie banner from it (`16` §2.7). Install the fonts as `16` §2.4 says.
> 2. Copy these backend files into the backend **unchanged**: `settings_registry.json`, `settings_store.py`, `security.py`, `mongo_init.py`, `ratelimit.py`, `accounts.py`, `security_mw.py`, `deps.py`, `plans.py`, `analytics.py`, `admin_queries.py`, `emailer.py`, `stripe_billing.py`, `routes_accounts.py`, `routes_billing.py`, `routes_admin.py`, `server.py` (use it as `server.py`), `reset_admin.py`, `textguard.py`, `site_studio.py`, `newsletter.py`, `popups.py`, `transports.py`, `integrations.py`, `reports.py`, `alerts.py`, `admin_shell.py`, `routes_site.py`, `requirements.txt`. Do not change their logic. Remove the template's own auth, JWT and CORS code; ours replaces it. Mount `routes_site.public` and `routes_site.admin` (they carry their own `/api` and `/api/admin` prefixes) as `server.py` does. Run `selftest_accounts.py`, `selftest_billing.py`, `selftest_server.py`, `selftest_admin.py`, `selftest_studio.py` and `selftest_growth.py` and show me they pass.
> 3. Front end for sign-up, verify e-mail, sign-in, 2FA code, forgot and reset password, and the Account area (Profile, Security, Devices, Notifications, Plan and billing, Privacy), exactly as in `13` sections 2 to 6. The app reads `GET /api/auth/me` on load.
> 4. Admin at `/admin` (404 for everyone else) with the responsive shell from `17` (left rail on computers; on phones and tablets a bottom app bar with 4 icons and More, drawn from `GET /api/admin/shell`) and these working modules: Dashboard, Users, Staff, Settings, Keys, Logs, Security, Health, Site Studio, Content, Inbox, Announcements, and Plans (editing only; Sync to Stripe stays disabled until phase 4b). Staff 2FA enrolment screen. Everything else "Coming in the next phase". Call only the routes listed in `10` and `16`. Tables become cards and drawers become full-screen sheets below 1025 px.
> 5. The public settings route; the UI reads brand, theme, nav and copy from it.
> 6. Footer with the exact disclaimer from `copy.disclaimer`. A "Beta" tag in the header.
> Keep `features.billing` false. Do not build data screens. Do not call PitchAPI, Stripe or Resend yet (e-mail stays off). Show me how to test each item.

### Phase 1: data layer and key intake

> Read `07_ingest_and_caching.md`, `08_pitchapi_data_guide.md`, and the files `cached_fetch.py`, `normalize.py`, `ingest.py`, `fake_pitchapi.py`, `selftest.py` in `backend/`. Copy `cached_fetch.py`, `normalize.py`, `ingest.py` unchanged. Build: Admin → Endpoint explorer (allow-list in `10`, section 3.3), Admin → Cache and usage, Admin → Leagues (list from `/v1/leagues`, enable toggle, backfill seasons). Every PitchAPI call must go through `PitchClient.fetch`. Run `selftest.py` and fix only integration problems.
>
> **Stop after this phase.** Moh will paste the real key, run the three discovery calls in the explorer, and do check A.

### Phase 2: ingest and jobs

> Read `07` again. Copy `jobs.py`. Build the tick endpoint, Admin → Ingest and jobs, Admin → Data quality (issues, coverage, mapping editor). Set the three `provider.*` settings from the answers to check A (Moh will give them). Backfill one season of one league. Show the queue, issues and coverage. Success is the "Done when" list at the end of `08` and checklist B.

### Phase 3: engine and forecast routes

> Read `09_engine_integration.md` and `06_api_routes_and_queries.md`. Copy `backend/soccer_brain/` to `backend/soccer_brain/` and `engine_bridge.py`, `queries.py`. Build Admin → Engine. Build the routes `fixtures`, `matches/{id}`, `insights`, `finder`, `leagues/*`, `teams/*`, `players/*`, `h2h`, `search`, `track-record` by calling the functions in `queries.py`. Run `selftest_queries.py` against the real database. Do not change the engine code. Do not turn on lineup effects.

### Phase 4: user screens

> Read `01` section 5, `02_playerstats_parity.md` (phase P1 rows only), `04`. Build screens 1 to 8, 10 to 16, one at a time, in this order: Today, Match, Insights, Forecast Finder, Team (Squad grid, Team totals, Against), Player, League, Search, Following, Track Record, Learn, Account. Use only the routes in `06`. Mobile first. Every list has loading, empty and error states. After each screen, tell me which checklist D line it covers.

### Phase 4b: money and e-mail (test mode only)

> Read `14_billing_stripe_and_email_resend.md` completely and `15_security_and_privacy.md` section 3. Build the front end for: Pricing page (from `GET /api/plans`), the checkout redirect and the "Confirming your payment" return page (poll `GET /api/account/billing`, never grant access from the URL), Manage billing button, upgrade prompts wherever `13` section 5 says, and the admin screens Plans (with Sync), Subscriptions, Payments (with refund), Coupons, Revenue, E-mail (Templates with preview and test send, Log, Suppressions, Campaigns), Analytics (all tabs). Wire the page-view beacon (`POST /api/analytics/collect`) with no third-party scripts. Moh will enter Stripe **test** keys and Resend keys. Run doc 12 sections H, I and J. Billing stays in `test` mode and `features.billing` stays false in production until Moh says so.

### Phase 4c: growth and site control

> Read `16_site_studio_popups_integrations.md` §3 to §7 and `17_admin_responsive_ui.md` again. Build the front end for: the popup display logic (the public `GET /api/popups` call, the trigger, frequency and session rules, focus trap, Esc, the three events), the footer e-mail form and the Confirm page (`16` §4), the cookie banner with "Allow optional" and the tracking-tag loader that waits for it (`16` §6.3), and the admin screens Popups (list, editor with live preview, stats, A/B), E-mail list, Integrations (the four cards), Analytics extras (realtime, compare, sources, e-mail health, CSV), and the alert list in Health. Every screen must work on a 390 px phone. Do not load any third-party script unless the owner has turned tracking on. Run doc 12 section L.

### Phase 5: parity extras (only when the data keys are verified)

> Read `02` (P2 rows) and `08` section 7. Build only what the verified keys allow: fouls, interceptions, clearances, saves, xG in grids and leaderboards; referees, cards and penalties (needs `ingest.match_extra_events` and `ingest.match_extra_detail`, which cost extra calls: show the cost in Admin before enabling); super sub; column chooser; hide-game; Telegram lineup alerts.

### Phase 6: polish and launch

> Run checklist A to G. Fix every failing line. Report the Lighthouse scores. Deploy. Then, in production: run `mongo_init.py`, create the admin, enter the key, enable the league, start the tick pinger.

## 5. What Moh does (not the agent)

| # | Task | When |
|---|---|---|
| 1 | Get a PitchAPI key at pitchapi.dev/get-api-key | Before phase 1 |
| 2 | Generate secrets: `python -c "import os,base64;print(base64.b64encode(os.urandom(32)).decode())"` for `APP_ENCRYPTION_KEY` (keep a copy in a password manager) and a long random `CRON_SHARED_SECRET`. Set `PUBLIC_BASE_URL`, `ADMIN_EMAIL`, `ADMIN_INITIAL_PASSWORD`. | Phase 0 |
| 3 | Run the three discovery calls and answer check A (12 items) | After phase 1 |
| 4 | Ask PitchAPI B1 to B4 (public use, paid use, images, credit, real burst limit) | Before launch |
| 5 | Set up a free pinger (for example cron-job.org) to call `POST /api/jobs/tick` every 5 minutes with header `X-CRON-SECRET` | After phase 2 |
| 6 | Sign in to PlayerStats.football (trial) and fill the G1 to G7 table in `02` | Before phase 4 |
| 7 | Choose app name, logo, domain | Before launch |
| 8 | Edit the claude.ai Project description. It still has the old wording from before we went analysis-only | Anytime |
| 9 | First sign-in as owner: change the password, set up 2FA, store the recovery codes offline. Then remove `ADMIN_INITIAL_PASSWORD` from the secrets. | Phase 0 |
| 10 | Resend: add your domain, DNS records, API key, webhook (doc 14 §4) | Phase 4b |
| 11 | Stripe: account in test mode, keys, webhook, portal settings (doc 14 §2) | Phase 4b |
| 12 | Write the Terms, Privacy, refund and cookie-free analytics wording; have a lawyer look at them (Canada: PIPEDA and CASL) | Before launch |
| 13 | Add team members from Admin → Staff, each with their own 2FA | When needed |
| 14 | Run the eleven self-tests on the real MongoDB once (doc 12 §K) | Before launch |
| 15 | Pick the e-mail provider (Resend is the default and the only one with automatic bounce handling), save its key in Admin → Keys, send a test mail (doc 16 §5) | Phase 4b |
| 16 | If you want list sync: pick Mailchimp, Brevo or MailerLite, save the key, set the list id, press Test (doc 16 §6.1) | Phase 4c |
| 17 | Decide about GA4, Meta pixel or Google Ads. Default is none. If yes: update the Privacy page first, add the CSP sources the screen lists, then switch on (owner only, doc 16 §6.3) | Before launch, optional |
| 18 | Look through every Site Studio section once, pick a starting look, upload the logo, check the menu and the phone bottom bar on your own phone, then press Publish | Phase 4c |
| 19 | Write the consent sentence for the e-mail list and have a lawyer look at it (CASL) | Before launch |

## 6. Known gaps (be honest with the agent and with users)

- The engine was tested on **simulated** data only. The Beta tag stays until a real-data backtest passes.
- Several PitchAPI keys are **unverified**: team shots, shots on target, corners, tackles, player minutes, position mapping, fouls, saves, interceptions, clearances, goals, assists.
- PitchAPI's terms for public and paid use are **not on its page**.
- Win/draw/loss probabilities did not beat plain frequencies in the simulated test. They are marked experimental.
- Reference tests use an in-memory database and a fake PitchAPI. Run them once on the real stack.
- Phase 2 pieces (events, referees, super sub, Telegram) are specified but **not coded**.
- **Stripe and Resend are tested with mock HTTP only**, never against live accounts. Doc 14 §7 lists seven things to confirm in Stripe test mode.
- Billing stays **off** until PitchAPI's terms allow paid use.
- No CAPTCHA, no WAF, no Google sign-in, no passkeys, no automatic Stripe reconcile job, no breached-password check (doc 15 §9).
- Plan limits on follows, saved forecasts, notes and grid games are defined and returned by the API, but only the Finder and Insights routes enforce them in the reference. The builder adds the rest (doc 06 §3).
- The Admin data screens (explorer, cache, leagues, engine, data quality) are specified in `10` and `06` but not coded; the people, money, e-mail, logs, keys and settings screens have tested APIs.
- **Site Studio, Popups, Integrations, e-mail list, extra analytics and alerts have tested server code (`selftest_studio.py`, `selftest_growth.py`) but no real front end.** The prototype shows the intended screens. The builder makes them.
- **Postmark, SendGrid, Brevo, SMTP, Mailchimp and MailerLite were written from public docs and tested with mocks only.** Bounces and complaints are automatic for Resend only.
- Tracking tags (GA4, Meta, Google Ads) are an owner-only, off-by-default exception to "no third-party scripts". They need the Privacy page and CSP updated first.
- The phone-friendly admin was checked in a real browser on the prototype (sizes 320 to 1280 px). It has not been checked with a screen reader, nor on a real phone.
- Popup stats count views and actions per day, not per person. There are no open or click rates for e-mail (no tracking pixels).
