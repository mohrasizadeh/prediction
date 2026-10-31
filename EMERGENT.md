# Building Prediciotn on Emergent

> **Update 27 ("if he plays" and the lineup badge):** already merged in this branch. Spec `docs/27_if_he_plays_and_lineup_badge.md`; screens to build are in `UPDATE_27_PROMPT.md` step 3.
> **Update 28 (the combo builder):** backend merged. Build the screens with `UPDATE_28_PROMPT.md` (spec `docs/28_combo_builder.md`, pictures `docs/28_boards/`).

This repo is the full hand-off. The backend and the engine are built and tested. The frontend is a working scaffold. Emergent's job is to finish the screens and the admin panel, and to connect the real data.

## How to work

1. Import this repo into Emergent (GitHub import), or upload it as a zip.
2. One phase per conversation. Paste the phase prompt below. Do not start the next phase until this one's checklist lines pass in preview (`docs/12_acceptance_checklist.md`).
3. When something fails, paste the full error text and logs. The agent cannot see the deployed database.
4. After each phase: `cd backend && bash run_tests.sh` must print 21 PASS lines. Keep a zip of the project.
5. Preview and production have separate databases. Indexes and the first owner are created when the server starts. After the first deploy: sign in as the owner, enter keys in Admin → Keys, enable the league again in production.

## The prompt to paste first, in every phase

> This repo is a complete, tested hand-off. Read `README.md`, `EMERGENT.md`, `docs/00_START_HERE.md`, `docs/03_rules_and_compliance.md` and `docs/15_security_and_privacy.md` completely before writing code. The rules in 03 and 15 override everything, including your template's defaults.
> Rules for the whole project:
> - Keep `backend/` as it is. Do not rewrite, rename or "simplify" any backend module or the engine in `backend/soccer_brain/`. Do not add your own auth, JWT, CORS, or user model; ours replaces the template's. If a backend change is truly needed, show me the diff and the test that proves it first.
> - The backend entry point is `backend/server.py` (`uvicorn server:app`). Every route lives under `/api`. Use plain `def` routes with the synchronous `pymongo` client.
> - The frontend talks to the API only through `frontend/src/lib/api.js` (cookie session, `credentials: "include"`). Never store a token, password or code in localStorage, sessionStorage or the URL.
> - Parse every time from the API with `utc()` from `frontend/src/lib/time.js`.
> - Images only through `Crest`, `LeagueMark`, `PlayerAvatar` in `frontend/src/components/Media.jsx`.
> - Every list has loading, empty and error states (`components/States.jsx`). Mobile first; test at 390 px.
> - Run `yarn check-copy` in `frontend/` before you finish. It must pass.
> - After your work: `cd backend && bash run_tests.sh` must show 21 PASS lines.

## Phase 0: foundation, accounts, admin shell

> Read also `docs/01`, `docs/04` with `docs/design_tokens.json`, `docs/10`, `docs/13`, `docs/16`, `docs/17`, and open `docs/prototype/admin_prototype.html` in a browser.
> 1. Set the environment from `backend/.env.example` (secrets in Emergent's env). Confirm the server starts and `GET /api/public/settings` answers.
> 2. Frontend: keep the scaffold. Add the site config loader (`GET /api/site/config`, inject its CSS, theme, menus, footer, cookie banner) per `docs/16` §2.7. Add a "Beta" tag in the header.
> 3. Finish the account screens in `docs/13` §2 to §6: forgot and reset password, confirm new e-mail, 2FA enrolment, and the Account area (Profile, Security, Devices, Notifications, Plan and billing, Privacy). Sign-in, sign-up and verify already work; restyle them, keep their logic.
> 4. Admin at `/admin` with the responsive shell from `docs/17` (left rail on computers; on phones a bottom bar with 4 icons and More, from `GET /api/admin/shell`). Working modules: Dashboard, Users, Staff, Settings, Keys, Logs, Security, Health, Site Studio, Content, Inbox, Announcements, Plans (Sync to Stripe disabled). Everything else "Coming in the next phase". Call only routes listed in `docs/10` and `docs/16`.
> Keep `features.billing` false. Do not build data screens yet.

## Phase 1: data layer and key intake (no screens for visitors)

> Read `docs/07` and `docs/08`. Build Admin → Endpoint explorer (allow-list in `docs/10` §3.3), Admin → Cache and usage, Admin → Leagues (enable toggle, backfill seasons). Every PitchAPI call goes through `PitchClient.fetch` in `backend/cached_fetch.py`.
> **Stop after this phase.** The owner pastes the real PitchAPI key, runs the three discovery calls, and does check A in `docs/08`.

## Phase 2: ingest and jobs

> Read `docs/07` again. Build Admin → Ingest and jobs and Admin → Data quality (issues, coverage, mapping editor) on `backend/jobs.py` and `backend/ingest.py`. Set the three `provider.*` settings from the owner's check-A answers. Backfill one season of one league. `POST /api/jobs/tick` is called by an external pinger every 5 minutes (`docs/07` §6) with the `X-CRON-SECRET` header. Success: the "Done when" list in `docs/08` and checklist B.

## Phase 3: engine

> Read `docs/09`, `docs/18`, `docs/19`. Build Admin → Engine (runs, gates, brain status from `GET /api/admin/brain`, calendar import) and Admin → Images (sync, review list, upload, take down). All data routes in `docs/06` §2 already exist in `backend/server.py`, `routes_data.py` and `routes_me.py`. Do not change the engine. Do not turn on lineup effects.

## Phase 4: user screens

> Read `docs/01` §5, `docs/02` (P1 rows), `docs/04`. In `frontend/src/App.js` every screen is a route; replace each `<Spec>` placeholder with the real screen, one at a time: Match, Insights, Forecast Finder, Team (Squad grid, Team totals, Against), Player, League, Leagues, Search overlay, Following, Track Record, Pricing (hidden while billing is off). `pages/Today.jsx` is the working example: follow its patterns. The placeholder for each screen names its spec and shows the live answer of its route. Show plan limits from `GET /api/auth/me` entitlements (`docs/13` §5); the server enforces them.

## Phase 4b: money and e-mail (test mode only)

> Read `docs/14` completely and `docs/15` §3. Build Pricing, checkout redirect, the "Confirming your payment" page (poll `GET /api/account/billing`; never grant access from the URL), Manage billing, upgrade prompts, and the admin Money and E-mail screens. Wire the page-view beacon (`POST /api/analytics/collect`), no third-party scripts. The owner enters Stripe **test** keys and Resend keys. Run checklist H, I, J.

## Phase 4c: growth and site control

> Read `docs/16` §3 to §7 and `docs/17`. Build popups (display rules, focus trap, Esc, events), the footer e-mail form and confirm page, the cookie banner and tracking-tag loader that waits for consent, and the admin screens Popups, E-mail list, Integrations, Analytics extras, alerts. Everything works at 390 px. Run checklist L.

## Phase 5: parity extras (only after the data keys are verified)

> Read `docs/02` (P2 rows) and `docs/08` §7. Build only what the verified keys allow.

## Phase 6: launch

> Run checklist A to G in `docs/12`. Fix every failing line. Report Lighthouse scores. Deploy. In production: sign in as the owner, change the first password, set up 2FA, enter keys, enable the league, start the tick pinger.
