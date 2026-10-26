# backend modules

Tested Python you copy into the Emergent backend. Plain modules, no framework magic. Synchronous `pymongo`.

| File | Job | Tested by |
|---|---|---|
| `settings_registry.json` | 156 settings with defaults (copy of `../11_settings_registry.json`) | all |
| `settings_store.py` | `get`, `get_many`, `put` (type-checked, history + audit, refuses locked), `reset`, `public`, `validate` | selftest, selftest_server, selftest_admin |
| `security.py` | AES-256-GCM encrypt/decrypt of keys and 2FA secrets; masked view | selftest, selftest_accounts |
| `mongo_init.py` | Creates every index and TTL (idempotent) | selftest |
| `ratelimit.py` | Mongo fixed-window rate limiter: `hit`, `check`, `peek` | selftest_accounts, selftest_server |
| `accounts.py` | Sign-up, sign-in, sessions, tokens, reset, change password/e-mail, 2FA (TOTP + recovery codes), export, delete, staff invite, roles, `PERMS`/`can` | selftest_accounts, selftest_admin |
| `security_mw.py` | Request id, trusted-proxy IP, body cap, CSRF origin check, headers/CSP, generic 500, CORS | selftest_server |
| `deps.py` | `current_user`, `require_perm`, `require_staff`, cookie helpers | selftest_server, selftest_admin |
| `plans.py` | Plans, entitlements, `effective_plan`, daily quotas (`consume`), comp grants | selftest_billing, selftest_server |
| `stripe_billing.py` | Stripe client (httpx), checkout, portal, plan sync, cancel/resume, refund, coupons, webhook verify and handling | selftest_billing, selftest_admin |
| `emailer.py` | Sender (any provider), 15 templates, suppression, unsubscribe tokens, Svix verify, campaigns, duplicate-send check | selftest_billing, selftest_growth |
| `transports.py` | The e-mail providers: Resend, Postmark, SendGrid, Brevo, SMTP; key test | selftest_growth |
| `textguard.py` | The banned-word scan every admin-written text goes through; one global 400 handler | all, selftest_growth |
| `site_studio.py` | Site config in versions: draft, validation, readability gate, CSS compiler, presets, publish, rollback, preview token, images | selftest_studio |
| `popups.py` | Popup Maker: validation, who-sees-what, A/B, stats, form submit, templates | selftest_growth |
| `newsletter.py` | E-mail list with proof of consent, double opt-in, unsubscribe | selftest_growth |
| `integrations.py` | List sync (Mailchimp, Brevo, MailerLite), signed webhooks with retries, tracking-tag settings and CSP, status | selftest_growth |
| `reports.py` | Realtime, compare, sources by campaign tag, e-mail health, safe CSV | selftest_growth |
| `alerts.py` | Alert rules, e-mail to the team, weekly summary | selftest_growth |
| `admin_shell.py` | The 32 admin modules, what each role sees, the phone bottom bar | selftest_studio |
| `routes_site.py` | 8 public and 56 `/api/admin/*` routes for the items above | selftest_studio, selftest_growth |
| `testkit.py` | Shared set-up for the two new tests (app, in-memory database, mocked providers, an owner and one staff member per role) | selftest_studio, selftest_growth |
| `analytics.py` | First-party events and reports (overview, funnel, traffic, retention, revenue, people) | selftest_admin |
| `admin_queries.py` | Dashboard, user list/drawer, logs, health, exports for the admin | selftest_admin |
| `routes_accounts.py` | `/api/auth/*`, `/api/account/*`, `/api/analytics/collect` | selftest_server |
| `routes_billing.py` | `/api/plans`, checkout, portal, `/api/webhooks/stripe`, `/api/webhooks/resend`, unsubscribe | selftest_billing, selftest_server |
| `routes_admin.py` | 67 `/api/admin/*` routes, each behind `require_perm` | selftest_admin |
| `cached_fetch.py` | `PitchClient.fetch`: cache, budget, pacing, 429/5xx retry, breaker, stale-if-error; `next_iid` | selftest |
| `normalize.py` | PitchAPI JSON → plain dicts; reads by `key`; missing = `None` | selftest |
| `ingest.py` | Leagues, season lists, match ingest (3 calls), lineup watch, queue, rounds, coverage | selftest, selftest_jobs |
| `engine_bridge.py` | Mongo → frames → engine → `forecasts`; calendar import and build; the start-model gate; scoring; cleanup | selftest, selftest_brain |
| `images.py` | One-time image sync from API-Football: client with cache and budget, name matching, download and checks, run, approve / reject / take down | selftest_images |
| `routes_images.py` | Public `GET /api/media/{kind}/{id}` and the admin image routes | selftest_images, selftest_admin |
| `queries.py` | Every read the data pages need (match detail carries the rotation chip) | selftest_queries |
| `jobs.py` | `tick()`: what is due, in order, with a lock | selftest_jobs |
| `routes_data.py` | The public data routes of docs/06 §2 (leagues, matches, teams, players, h2h, track record, status, pages) | selftest_routes |
| `routes_me.py` | Follows, saved forecasts, notes, following feed; per-user, plan limits | selftest_routes |
| `server.py` | FastAPI app: mounts all routers, middleware, startup (indexes, plan seed, first owner), Finder and Insights with plan limits, tick | selftest_server |
| `reset_admin.py` | Command line: reset the owner password, turn off 2FA, sign out all devices | by hand |
| `fake_pitchapi.py` | A stand-in PitchAPI built from simulated data (**invented key names**) | used by tests |
| `.env.example` | Every environment variable | n/a |

## Run the tests

```
pip install -r requirements.txt
export APP_ENCRYPTION_KEY=$(python -c "import os,base64;print(base64.b64encode(os.urandom(32)).decode())")
python tests/selftest.py            # about 1 minute
python tests/selftest_queries.py
python tests/selftest_jobs.py
python tests/selftest_accounts.py
python tests/selftest_billing.py
python tests/selftest_server.py
python tests/selftest_admin.py
python tests/selftest_studio.py
python tests/selftest_growth.py
python tests/selftest_brain.py       # calendar, rotation, gates (doc 18)
python tests/selftest_images.py      # image sync, matching, serving (doc 19)
```

All eleven print `ALL ... PASSED`. They use `mongomock` (an in-memory MongoDB look-alike). **Run them once against the real MongoDB too** (set `MONGO_URL` and a throw-away `DB_NAME`, replace `mongomock.MongoClient()` with `MongoClient(...)`). Some aggregation stages behave a little differently on real MongoDB.

## What the tests prove, and what they do not

They prove: caching (second pass = 0 calls), budget stop, 429 retry, idempotent upserts, no zeros for missing data, forecasts written and replaced not doubled, scoring, all page queries, job order and lock; sign-up, sign-in, lockout, reset, 2FA, sessions and role checks; plan limits and quotas; Stripe webhook signature, replay and ordering; Resend suppression and unsubscribe; every admin route's permission; key masking; no banned words in stored text.

They do **not** prove: how Stripe and Resend really answer (both are mocked; see `../14_billing_stripe_and_email_resend.md` section 7), the real PitchAPI key names (the fake uses invented ones, see `fake_pitchapi.py`), that the engine is accurate on real football (it was tested on simulated data only), speed on a large real database, or behaviour on Emergent's hosting.

## Wiring into the Emergent template

1. Copy these files into `backend/` (flat). Copy `soccer_brain/` to `backend/soccer_brain/`.
2. `pip install -r requirements.txt` (no new package is needed for the site-control files). Install the fonts in the front end (`../16_site_studio_popups_integrations.md` §2.4).
3. Remove the template's own auth, JWT and CORS code. Use `server.py` (already in place). It calls `security_mw.install(app, get_db)`, mounts `routes_accounts`, `routes_billing`, `routes_admin`, and `routes_site` (two routers, `public` and `admin`, with their own prefixes), and sets the database with `deps.set_db`. Add the data routes from `../06_api_routes_and_queries.md` and guard each with `deps.current_user` or `deps.require_perm`.
4. Set the `.env` values from `.env.example` (a change needs a redeploy).
5. Start. The startup hook creates indexes, seeds the Free and Pro plans, and creates the first owner from `ADMIN_EMAIL` and `ADMIN_INITIAL_PASSWORD`.
6. Sign in, change the password, set up 2FA. Then remove `ADMIN_INITIAL_PASSWORD`.
7. Point an external pinger at `POST /api/jobs/tick` with header `X-CRON-SECRET`, **every 5 minutes** (it also delivers webhooks, copies list contacts and runs alerts).
8. Lost owner access: `python reset_admin.py` on the server.
