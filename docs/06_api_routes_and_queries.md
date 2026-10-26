# 06. API routes and database queries

Every page reads our database. No page request ever calls PitchAPI. The functions named below are in `backend/queries.py` and are tested (`selftest_queries.py`).

## 1. Conventions

- Base path `/api`. JSON in, JSON out. Dates are ISO-8601 with `Z`.
- URLs carry the public `id` (uuid). The handler turns it into the integer `iid` with `queries.iid_of(db, "teams", id)`. Return 404 when not found.
- Errors: `{"error": {"code": "NOT_FOUND", "message": "...", "request_id": "..."}}` with the right HTTP status. Never a stack trace. Validation errors (422) list field names only, never the values sent. Built by `security_mw.install`.
- Lists are capped (default 50, max 200). `?limit=` and `?cursor=` where a list can grow.
- Auth: *Public* = none. *User* = the session cookie (`__Host-sid`, `HttpOnly`, `Secure`, `SameSite=Lax`); there is no Bearer token and no JWT. *Staff* = a user whose role holds the route's permission (`deps.require_perm("…")`), full session, 2FA done; checked on every request. See doc 13 (people) and doc 10 (staff).
- Every `/api` request passes `security_mw`: request id, body cap, Origin check on writes, rate limit per IP, security headers, crash handler, log rows. See doc 15.
- Response headers: public data routes send `Cache-Control: public, max-age=60, stale-while-revalidate=300`. Routes with user data send `private, no-store`.
- Use plain `def` route functions with the synchronous `pymongo` client (see `05_database_mongodb.md`, rule 8).
- Every list route that shows forecasts uses `NOT_HIDDEN = {"is_current": True, "hidden": {"$ne": True}}`.

## 2. Public routes

| Route | Query params | Function | Notes |
|---|---|---|---|
| `GET /api/public/settings` | | `settings_store.public(db)` | Only settings flagged `public`. Cache 60 s. |
| `GET /api/public/pages/{slug}` | | `content_pages.find_one({slug, published: true})` | Learn, terms, privacy, about, FAQ |
| `GET /api/public/status` | | `job_runs` last ok per job, `data_coverage` | Footer "Data updated 3 hours ago" and the stale banner |
| `GET /api/fixtures` | `date=YYYY-MM-DD`, `tz=-300` (minutes east of UTC), `leagues=id,id` | `fixtures_for_date` | The Today screen |
| `GET /api/matches/{id}` | | `match_detail` | Match page: forecasts, styles, starters, head to head |
| `GET /api/insights` | `tiers=Strong,Solid`, `leagues`, `stat`, `scope`, `limit` | `insights_feed` | Sorted by tier, then likelihood |
| `GET /api/finder` | `mode=likelihood\|form\|run`, `stat`, `n` (1 to 5), `last`, `leagues` (max `finder.max_leagues`), `scope=player\|team`, `venue`, `started`, `min_minutes`, `positions`, `min_p`, `min_reached`, `date`, `tz` | `finder` | Counts a free search for signed-out users (section 4) |
| `GET /api/leagues` | `q=` | `leagues.find({enabled: true})` grouped by country | Leagues page and search |
| `GET /api/leagues/{id}` | | league doc + `league_matches` | |
| `GET /api/leagues/{id}/fixtures` | `status=scheduled\|final` | `league_matches` | |
| `GET /api/leagues/{id}/leaderboard` | `stat`, `per90`, `min_minutes`, `limit` | `leaderboard` | |
| `GET /api/leagues/{id}/referees` | | `referee_table` | Phase 2 |
| `GET /api/teams/{id}` | | `team_detail` | Style, tactic chips, form, next fixtures |
| `GET /api/teams/{id}/squad-grid` | `stat`, `last`, `venue`, `started`, `positions` | `squad_grid` | |
| `GET /api/teams/{id}/totals` | `stat`, `last` | `team_totals_grid` | For and against per game |
| `GET /api/teams/{id}/against` | `stat`, `last` | `against_by_position` | |
| `GET /api/players/{id}` | | `player_detail` | |
| `GET /api/players/{id}/history` | `last`, `venue`, `started`, `min_minutes` | `player_history` | Quick view and the history table |
| `GET /api/h2h` | `a={team id}`, `b={team id}` | `h2h` | |
| `GET /api/search` | `q` (min 2 characters) | `search` | Debounce 200 ms in the browser |
| `GET /api/track-record` | `league` | `track_record` | Returns `{ready: false}` until enough results |
| `POST /api/newsletter` | body `{email}` | upsert `newsletter` | Rate limited |

### Today, in detail

```python
# fixtures_for_date(db, "2026-10-25", tz_offset_min=-240)
d0 = datetime(2026,10,25,tzinfo=utc) - timedelta(minutes=tz_offset_min)     # local midnight in UTC
matches.find({"kickoff": {"$gte": d0, "$lt": d0 + 1 day}, "league_iid": {"$in": ...}}).sort("kickoff", 1)
match_probs.find({"match_iid": {"$in": ids}, "is_current": True})
forecasts.aggregate([{"$match": {"match_iid": {"$in": ids}, "is_current": True, "hidden": {"$ne": True}, "tier": {"$in": ["Strong","Solid"]}}},
                     {"$group": {"_id": "$match_iid", "n": {"$sum": 1}}}])
```

### Squad grid, in detail

```python
player_match_stats.aggregate([
  {"$match": {"team_iid": T}},
  {"$sort": {"kickoff": -1}},
  {"$group": {"_id": "$player_iid", "games": {"$push": {"match_iid": "$match_iid", "kickoff": "$kickoff", "opp_iid": "$opp_iid",
                                                         "v": "$shots", "minutes": "$minutes", "started": "$started"}}}},
  {"$project": {"games": {"$slice": ["$games", N]}}}])
```

A player's row has fewer than N cells if he played fewer games. The browser aligns cells to the **team's** last N matches by `match_iid`, and shows "–" where the player did not feature.

### Forecast Finder, in detail

- **Date:** `date` (the user's local day) and `tz` pick the day. Only players and teams whose match kicks off that day appear (`finder(..., day=date, tz_offset_min=tz)`).
- **Likelihood:** `forecasts.find({scope, stat, thr: n - 0.5, kickoff in the day, p >= min_p, pos in ...}).sort(p desc)`. "2 or more shots" is `thr = 1.5`.
- **Form:** one aggregation over `player_match_stats` (or `team_match_stats`): match filters, sort by `kickoff` desc, `$group` pushing the stat, `$slice` to `last`, then count values `>= n` in Python. Then attach the next fixture and its forecast.
- **Run:** same aggregation, then count consecutive values `>= n` from the newest.
- Only the engine's thresholds have a Likelihood row. If the user chooses an `n` the engine does not forecast (for example 5 or more shots), the Likelihood mode is disabled with the note "No forecast for this line yet" and Form/Run still work.

### Leaderboards, in detail

`player_match_stats.aggregate([{$match: {league_iid, stat: {$ne: null}}}, {$group: {_id: "$player_iid", total: {$sum: ...}, minutes: {$sum: "$minutes"}, games: {$sum: 1}, team: {$last: "$team_iid"}}}, {$match: {minutes: {$gte: min_minutes}}}])`, then per-90 and sort in Python.

### Track record, in detail

`forecast_outcomes.find({player_played: true})`. For each tier: count, average stated `p`, share with `reached = true`. Reliability bins by stated `p` in steps of 0.1 with at least 30 results. Returns `{ready: false, scored, needed}` below `track_record.min_scored`.

## 3. Account, billing and public-extra routes

Built and tested. Full table with limits and error codes: `13_accounts_and_user_features.md` §7. Billing: `14_billing_stripe_and_email_resend.md`.

| Group | Routes | File |
|---|---|---|
| Auth | `POST /auth/register`, `/auth/verify-email`, `/auth/resend-verification`, `/auth/login`, `/auth/login/2fa`, `/auth/logout`, `/auth/forgot-password`, `/auth/reset-password`; `GET /auth/me` | `routes_accounts.py` |
| Account | `PATCH /account/profile`, `POST /account/password`, `POST /account/email`, `POST /account/email/confirm`, `POST /account/2fa/begin\|confirm\|disable`, `GET /account/sessions`, `DELETE /account/sessions/{sid}`, `POST /account/sessions/revoke-others`, `GET /account/export`, `DELETE /account` | `routes_accounts.py` |
| Plans and billing | `GET /plans`, `GET /account/billing`, `POST /billing/checkout`, `POST /billing/portal` | `routes_billing.py` |
| Webhooks | `POST /webhooks/stripe`, `POST /webhooks/resend` (signature-checked, no cookie, no Origin check, no rate limit) | `routes_billing.py` |
| Public extras | `GET/POST /email/unsubscribe`, `POST /contact`, `POST /analytics/collect`, `GET /announcements`, `GET /content/{slug}` | `routes_accounts.py`, `server.py` |
| Site and growth (public) | `GET /site/config` (ETag; `?preview=` for staff), `GET /site/assets/{id}`, `GET /popups`, `POST /popups/{id}/event`, `POST /popups/{id}/submit`, `POST /newsletter/subscribe`, `GET/POST /newsletter/confirm` | `routes_site.py` |
| Data | `GET /public/settings`, `/fixtures`, `/insights`, `/search`, `/finder` in `server.py`; every other section-2 route in `routes_data.py` | `server.py`, `routes_data.py` |

### User data routes (built: `backend/routes_me.py`, tested by `tests/selftest_routes.py`; Telegram is phase 2 and not built)
| Route | Body / params | Collection |
|---|---|---|
| `GET /api/me/follows` | | `follows` joined to names |
| `PUT /api/me/follows` / `DELETE` | `{kind, ref_id}` | `follows` (unique). Count against `follows_max`; over the limit → `409 LIMIT_REACHED` |
| `GET /api/me/following-feed` | | upcoming fixtures and current forecasts for followed teams and players |
| `GET /api/me/saved` / `PUT` / `DELETE` | `{fkey}` | `saved_forecasts`; `saved_max` |
| `GET /api/me/notes/{player id}` / `PUT` / `DELETE` | `{text}` | `notes`; `notes_max` |
| `POST /api/me/alerts/telegram` | `{team_ids}` | `alert_subscriptions` (phase 2; needs the `alerts` entitlement) |
Use `plans.ent(db, user, "follows_max")` for the limit and `require_user` for auth. Every one of these must have a test that a signed-out request gets 401 and that user A cannot read user B's rows.

## 4. Search quotas and plan limits

`plans.consume(db, subject, name, limit)` is an atomic counter in `finder_usage` (one row per subject, day and name). A refused call is not counted.
```python
ep = plans.effective_plan(db, user)            # who is this, and what may they do?
if user: subject, cap = f"u:{user['id']}", ep["entitlements"]["finder_searches_per_day"]
else:    subject, cap = "ip:" + sha256(ip + ua)[:16], settings["plans.anonymous_finder_searches_per_day"]
ok, used = plans.consume(db, subject, "finder", cap)       # cap -1 = no limit
if not ok: 401 SIGN_IN_REQUIRED (signed out)  |  402 UPGRADE_REQUIRED (signed in)
```
With `features.billing` off, signed-in people have the top plan (no limit). Signed-out visitors always have the free plan: `finder_leagues` = 1, so the league is required (`400 PICK_A_LEAGUE`). `server.finder` is the working example.

## 5. Staff routes

All under `/api/admin`, all `deps.require_perm(...)`, all write `audit_log`. 67 routes in `routes_admin.py` and 56 in `routes_site.py` (Site Studio, popups, integrations, extra analytics, alerts, the menu). The new ones are listed in `16` §10. The full list with the permission each needs, grouped by screen, is in `10_admin_panel.md` §3. They live in `routes_admin.py`. Summary of groups:

| Group | Prefix | Permission(s) |
|---|---|---|
| Dashboard, analytics | `/dashboard`, `/analytics/*` | `analytics.read` (`billing.read` for revenue) |
| People | `/users`, `/users/{id}/…`, `/staff`, `/staff/invite`, `/inbox`, `/announcements` | `users.read/write`, `plans.write`, `staff.manage`, `users.purge`, `inbox.write`, `content.write` |
| Money | `/plans`, `/plans/{key}/sync`, `/subscriptions`, `/payments`, `/payments/{id}/refund`, `/coupons` | `plans.read/write`, `billing.read/write` |
| E-mail | `/email/templates*`, `/email/suppressions`, `/email/campaigns*` | `email.read/write` |
| Logs and health | `/logs/{audit,auth,app,api,webhooks,jobs,issues,email}`, `/health`, `/security` | `logs.read`, `security.read` |
| Keys and settings | `/keys*`, `/settings*` | `keys.write` (owner), `settings.read/write` |
| Data and jobs | `/jobs/run`, `/breaker/close` (reference). The data screens from the earlier plan (`/explorer`, `/cache`, `/usage`, `/leagues`, `/jobs`, `/issues`, `/coverage`, `/engine`, `/forecasts/{id}/hide`) are still for the builder: build them from the table below. | `jobs.run`, `settings.write` |
| Content | `/content/{slug}` | `content.write` |
| Menu | `/shell`, `/shell/tabs` | any staff role (filtered by permission) |
| Site Studio | `/site/draft*`, `/site/diff`, `/site/preview-token`, `/site/publish`, `/site/versions*`, `/site/rollback/{v}`, `/site/assets*` | `site.read`, `site.write`, `site.publish` (custom CSS: owner) |
| Popups | `/popups*`, `/popups-ab/{group}` | `popups.read`, `popups.write` |
| E-mail list | `/newsletter`, `/newsletter/export`, `/newsletter/remove` | `email.read`, `users.pii`, `email.write` |
| Integrations | `/integrations`, `/integrations/email*`, `/integrations/audience*`, `/integrations/webhooks*`, `/integrations/tracking` | `integrations.read/write`; tracking `tracking.write` (owner) |
| Analytics extras | `/analytics/realtime\|compare\|acquisition\|email\|popups\|newsletter\|export` | `analytics.read` (`email.read`, `popups.read` for two) |
| Alerts and digest | `/alerts*`, `/digest/preview`, `/digest/send` | `logs.read`, `settings.write`, `jobs.run`, `analytics.read` |

Data screens still to build (they read existing collections; no new logic):
| Route | Does |
|---|---|
| `POST /explorer` | `{path, params, force}` → `PitchClient.fetch`. Allow-list only the routes in doc 08. Returns `from_cache`, cost in calls, raw JSON. |
| `GET /cache` | Search `api_cache`; delete one, by prefix, or all |
| `GET /usage` | Calls today, budget, 14-day chart, error codes, breaker state |
| `GET/PUT /leagues` | Enable, choose `backfill_seasons`, coverage |
| `GET /jobs` | Last runs (also at `/logs/jobs`), queue counts, lock |
| `GET /issues`, `POST /issues/{id}/resolve` | `ingest_issues` |
| `GET /coverage` | `data_coverage` per league |
| `GET /engine`, `POST /forecasts/{id}/hide` | Runs, markets, hide with reason |
| `GET /images`, `GET /images/review` | Image counts, budget, last run; pairs waiting for a person (`logs.read`) |
| `POST /images/sync?refresh=` | Queue the image sync; `refresh=true` re-reads every squad (`jobs.run`) |
| `POST /images/{kind}/{iid}/approve`, `.../reject`, `PUT .../upload`, `DELETE /images/{kind}/{iid}` | Approve a candidate (body `{af_id?}`), reject, upload PNG / JPEG / WebP bytes, take down (`jobs.run`, audited) |
| `GET /brain` | Latest gate result per league and layer, brain settings, calendar coverage (`logs.read`) |
| `POST /calendar/import` | Cups and European fixtures for our clubs; body = list of `{team_iid, kickoff, comp, stage?}`; idempotent; unknown `comp` is refused (`jobs.run`) |
| `GET /export` | JSON of the small collections |

## 6. Job endpoint

`POST /api/jobs/tick` with header `X-CRON-SECRET: $CRON_SHARED_SECRET`. Returns `jobs.tick(db)` output. Compare the secret with `hmac.compare_digest`. 401 on mismatch. See `07_ingest_and_caching.md` section 6.
