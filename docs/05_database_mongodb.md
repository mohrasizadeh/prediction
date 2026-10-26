# 05. Database (MongoDB)

Emergent's default database is MongoDB. This package uses it. Run `python backend/mongo_init.py` once after the first deploy and after any change. It is safe to run many times.

## 1. Rules for every collection

1. **Ids.** Every entity has three ids:
   - `id`: a UUID string. Used in URLs and APIs the browser sees. Never an ObjectId.
   - `iid`: a small integer from the `counters` collection (`next_iid()`). The engine needs integers.
   - `ext_id`: the PitchAPI id (`m_xxxxxx`, `t_...`, `p_...`, `l_...`). Upsert by it. Never parse it.
2. **Never return `_id`.** Every `find` uses a projection `{"_id": 0}`. Every aggregation ends with `{"$project": {"_id": 0}}` or reshapes `_id`.
3. **Dates.** Store UTC `datetime`. Send ISO-8601 strings with `Z` to the browser. Convert to the user's time zone in the browser.
4. **Missing is `null`, never 0.** A stat the provider did not give is `null`.
5. **Upserts.** Every write is an upsert keyed by a unique index. Re-running anything is safe.
6. **No transactions.** Atlas free tiers and shared hosts may not allow them. `matches.ingested_at` is written last, so a half-finished match is redone.
7. **Field names.** No dots, no leading `$`. Raw PitchAPI JSON is never stored as documents (it uses display labels as keys). It is stored compressed in `api_cache.data_z`.
8. **Sync driver.** The jobs and queries in `backend/` use synchronous `pymongo`. Emergent's template creates an async `motor` client for the routes. Create one more `pymongo.MongoClient(MONGO_URL)[DB_NAME]` and use it inside plain `def` routes (FastAPI runs them in a thread pool), or add `await` and `motor` equivalents. Do not mix the two inside one function.

## 2. Collections

Types: s = string, i = integer, f = float, b = boolean, dt = UTC datetime, `?` = may be null.

### 2.1 Accounts and configuration

**users**
`id s`, `email s` (lower case, unique), `password_hash s` (bcrypt), `role s` ("user" or "admin"), `name s?`, `tz s` (IANA, default from browser), `theme s` ("system", "dark", "light"), `prefs {density, table_columns{}, hidden_games{}}`, `plan s` ("free"), `trial_ends_at dt?`, `totp_secret_enc {ciphertext, iv}?` (admin), `failed_logins i`, `locked_until dt?`, `must_change_password b`, `created_at dt`, `last_login_at dt?`.

**settings**: `key s` (unique), `value any`, `updated_at dt`, `updated_by s`. Missing row = registry default (`settings_store.get`).
**settings_history**: `key`, `old`, `new`, `by`, `at`.
**content_pages**: `slug s` (unique; "learn-how-to-read", "terms", "privacy", "about", "faq"), `title s`, `body_md s`, `published b`, `updated_at dt`.
**provider_keys**: `provider s` (unique, "pitchapi"), `ciphertext s`, `iv s`, `last4 s`, `created_at dt`, `rotated_at dt`. Never returned by any route except as `{set, masked}`.
**audit_log**: `actor s`, `action s`, `target s`, `detail any?`, `ip s?`, `at dt`.
**counters**: `_id s` (collection name), `seq i`.

### 2.2 Provider cache (see `07_ingest_and_caching.md`)

**api_cache**: `_id s` (sha256 of method, path, sorted params), `path s`, `params {}`, `data_z binary` (zlib JSON of `data`), `fetched_at dt`, `expires_at dt?` (absent = never expires), `error_code s?` (a cached 404). TTL index on `expires_at` removes rows by itself.
**api_call_log**: `at dt`, `path s`, `status i`, `code s?`, `ms i`, `purpose s`. Kept 45 days (TTL). The daily budget is `count(at >= today 00:00 UTC)`.

### 2.3 Reference data

**leagues**: `id`, `iid`, `ext_id`, `name`, `country_code`, `image_url`, `seasons [s]`, `current_season s` (largest label), `enabled b` (new leagues start **false**), `backfill_seasons [s]` (admin chooses), `created_at`, `updated_at`.
**seasons**: `league_iid i`, `label s` (unique together), `backfilled b`, `queued b`.
**teams**: `id`, `iid`, `ext_id`, `name`, `image_url s?` (the provider's link, never sent to the browser), `league_iid i`.
**players**: `id`, `iid`, `ext_id`, `name`, `team_iid i` (latest team), `pos s?` ("GK", "DEF", "MID", "FWD"), `pos_raw i?`, `image_url s?`.

### 2.4 Facts

**matches**: `id`, `iid`, `ext_id`, `league_iid`, `season s`, `kickoff dt`, `status s` ("scheduled", "final", "other"), `provider_status s`, `home_iid`, `away_iid`, `hg i?`, `ag i?`, `round i?` (dense rank of distinct UTC kickoff dates in the league; `assign_rounds`), `round_name s?`, `referee s?`, `stadium s?`, `ingested_at dt?`, `lineups_confirmed b`, `lineup_fetches i`, `lineups_at dt?`, `updated_at`.

**team_match_stats** (two rows per match): `match_iid`, `team_iid`, `opp_iid`, `league_iid`, `kickoff dt`, `home b`, `goals i`, `goals_against i`, `shots f?`, `sot f?`, `corners f?`, `tackles f?`, `poss f?`, `xg f?`, `fouls f?`, `yellow_cards f?`, `shots_against f?`, `sot_against f?`, `corners_against f?`, `tackles_against f?`, `xg_against f?`.

**player_match_stats** (one row per player who featured): `match_iid`, `player_iid`, `team_iid`, `opp_iid`, `league_iid`, `kickoff dt`, `pos s?`, `pos_raw i?`, `started b`, `minutes f`, `shots f`, `sot f?`, `tackles f?` (null for goalkeepers), `goals f?`, `assists f?`, `xg f?`, `saves f?`, `interceptions f?`, `clearances f?`, `fouls_committed f?`, `fouls_won f?`, `team_shots f?`, `team_sot f?`, `team_tackles f?` (sums over the team's players, same keys).

**lineups**: `match_iid`, `team_iid`, `player_iid`, `started b`, `confirmed b`, `formation s?`, `lineup_type s?`, `shirt_number s?`, `position_id i?`, `pitch_x f?`, `pitch_y f?` (0 to 1), `is_captain b`, `fetched_at dt`.
**match_events** (phase 2, `ingest.match_extra_events`): `match_iid`, `minute i`, `event_type s` ("goal", "yellowcard", "redcard", "substitution", "penalty"), `player_iid i?`, `team_iid i?`, `detail {}`.

### 2.5 Jobs and quality

**ingest_queue**: `task s` ("match_ingest"), `key s` (the match `ext_id`; unique with `task`), `status s` ("pending", "running", "done", "skipped", "failed"), `priority i` (lower first), `attempts i`, `payload {}`, `next_run_at dt`, `created_at`, `started_at?`, `finished_at?`.
**ingest_issues**: `at`, `kind s` ("missing_field", "unknown_status", "team_player_shots_gap", "team_stat_from_players", "player_team_unknown", "stale_served", "not_found_gave_up", "job_error", "team_not_in_history"), `detail s`, `match_iid?`, `league_iid?`, `resolved b`.
**job_runs**: `job s`, `started_at`, `finished_at?`, `status s` ("running", "ok", "stopped", "error"), `result any?`, `error s?`.
**job_requests**: `job s`, `status s` ("pending", "taken", "done"), `requested_at`, `requested_by s`. The Admin "Run now" button inserts one.
**job_locks**: `_id s` ("tick", "pitch_breaker"), `at`, `reason s?`, `expires_at dt` (TTL).
**data_coverage**: `league_iid`, `field s` (like "player_match_stats.tackles"), `share f` (0 to 1), `rows i`, `at`. A market is on only if `share >= engine.coverage_min`.

### 2.6 Engine output

**engine_runs**: `run_id s`, `league_iid`, `started_at`, `finished_at?`, `status s` ("running", "done", "skipped"), `note s?`, `as_of i?`, `matches_in_fit i?`, `fixtures i?`, `forecasts i?`.
**team_styles**: `league_iid`, `team_iid`, `as_of i`, `style [f x 8]`, `tactic_z {low_block, high_press, possession}`, `tactics [s]`, `at`.
**match_probs**: `match_iid`, `run_id`, `is_current b`, `xg_home f`, `xg_away f`, `p_home f`, `p_draw f`, `p_away f`, `at`.
**forecasts**: `id`, `fkey s` ("matchiid:scope:team:player:stat:thr"), `run_id`, `match_iid`, `league_iid`, `kickoff dt`, `scope s` ("player", "team"), `team_iid`, `opp_iid`, `player_iid i?`, `pos s?`, `stat s`, `thr f` (0.5 means "1 or more"), `market s` (label), `expected f`, `p f`, `lo f`, `hi f`, `p_play f`, `lineup_confirmed b`, `tier s?` ("Strong", "Solid", "Watch" or null), `reasons [s]`, `opp_tactics [s]`, `own_tactics [s]`, `opp_key_players [[i, f]]`, `rotation s` ("low", "medium", "high"), `rotation_why s`, `p_play_usual f?`, `contrib {}`, `p_raw f?` (plain last-10 rate), `p_base f?` (no-context baseline), `is_current b`, `hidden b` (admin can hide), `created_at`.
**media**: `kind s` ("league", "team", "player"), `iid i` (unique together), `mime s`, `data bin`, `sha256 s`, `size i`, `source s` ("apifootball" or "upload:<email>"), `af_id i?`, `fetched_at`. The image bytes. Keep forever; they are re-creatable but cost calls.
**image_map**: `kind s`, `our_iid i` (unique together), `af_id i?`, `our_name s`, `af_name s?`, `score f`, `status s` ("auto", "approved", "review", "none", "rejected"), `candidates [{af_id, name, score}]`, `league_iid i?`, `team_iid i?`, `missing s?`, `source s?`, `at`.
**image_api_cache**: `_id s` (path and query), `payload {}`, `expires_at` (TTL index, 30 days). **image_api_calls**: `_id s` (UTC day), `n i`, `at`. **image_runs**: `at`, `api_calls_before i`, `api_calls_after i`, `stored i?`, `missing i?`, `bad i?`, `stopped s?` ("budget" or "time"), `done b`.
**club_calendar**: `team_iid`, `kickoff dt`, `comp s` (key of `context.importance`), `stage s`, `source s`, `at`. Unique on (`team_iid`, `kickoff`, `comp`). Cups, Europe and super cups only; league matches come from `matches`.
**match_context**: `match_iid`, `team_iid` (unique pair), `league_iid`, `level s` ("low", "medium", "high"), `why s` (one plain sentence, empty when low), `rest_days f`, `next_gap f`, `next_comp s`, `n14 i`, `at`.
**engine_gates**: `league_iid`, `run_id`, `layer s` ("start_model"), `mode s`, `passed b`, `applied b`, `n_train i`, `n_test i`, `gain f?`, `se f?`, `z f?`, `reason s`, `coefficients {}`, `at`. Keep the last 90 days.
**forecast_outcomes**: `forecast_id` (unique), `fkey`, `run_id`, `league_iid`, `stat`, `scope`, `tier`, `p`, `thr`, `actual f`, `reached b`, `player_played b`, `scored_at`.
**referee_stats** (phase 2): `referee s`, `league_iid`, `matches i`, `fouls_pg f`, `yellow_pg f`, `red_pg f`, `penalties_pg f`, `at`.

### 2.7 User data

**follows**: `user_id`, `kind` ("player", "team", "league"), `ref_iid`, `created_at`. Unique on the three.
**saved_forecasts**: `user_id`, `fkey`, `created_at`.
**notes**: `user_id`, `player_iid`, `text s` (max 2,000), `updated_at`.
**alert_subscriptions**: `user_id`, `channel` ("telegram"), `chat_id s`, `team_iids [i]`, `active b`, `created_at`.
**newsletter**: `email` (unique), `consented_at dt`, `unsubscribed_at dt?`.
**finder_usage**: daily quota counters. `subject s` ("u:<user id>" or "ip:<hash of IP + user agent>"), `day s` ("2026-10-25" UTC), `name s` ("finder"), `count i`, `expires_at dt` (TTL, 3 days). Unique on `subject, day, name`. Written only by `plans.consume`.

### 2.8 Accounts and security

**users**: `id s` (public id, unique), `email s` (lower case, unique), `role s` ("owner", "admin", "support", "analyst", "user"), `password_hash s?` (bcrypt over a SHA-256 pre-hash; null for an invited person who has not set one), `display_name s`, `tz s`, `theme s`, `email_verified b`, `prefs {product_emails, marketing_emails, alert_emails}`, `failed_logins i`, `locked_until dt?`, `last_login_at dt?`, `last_login_ip s?`, `disabled b?`, `must_change_password b?`, `totp {enabled b, secret_enc {ciphertext, iv}, pending_enc?, last_counter i}`, `recovery_codes [sha256]`, `stripe_customer_id s?`, `had_trial b`, `comp {plan_key, until dt?, reason, by, at}?`, `created_at`, `deleted_at dt?` (a deleted person keeps only `id`, a placeholder e-mail `deleted+<id>@invalid`, and these two fields).
**sessions**: `_id` = SHA-256 of the cookie token (the token itself is never stored), `sid s` (public handle for "sign out this device"), `user_id`, `scope s` ("full" or "enroll_2fa"), `staff b`, `created_at`, `last_seen`, `expires_at dt` (TTL), `ip`, `ua`.
**auth_tokens**: one-time links and challenges. `_id` = SHA-256 of the token, `kind s` ("verify_email", "password_reset", "email_change", "2fa_challenge"), `user_id`, `data {}` (new e-mail, tries), `created_at`, `expires_at dt` (TTL), `used_at dt?`.
**rate_limits**: `_id` = "<key>:<window number>", `n i`, `expires_at dt` (TTL).
**auth_log**: `at`, `event s` ("login", "login_2fa", "register", "verify_email", "password_reset", "password_change", "email_change", "2fa_enabled", "2fa_disabled", "role_changed", "staff_invited", "disabled", "enabled", "account_deleted"), `ok b`, `user_id?`, `email?`, `ip?`, `ua?`, `reason?`, `by?`. TTL `security.auth_log_retention_days`.
**app_logs**: `at`, `level s` ("info", "warn", "error"), `request_id`, `method`, `path` (no query string), `status i`, `ms i`, `user_id?`, `ip`, `ua`, `trace s?` (errors only). TTL `security.log_retention_days`.
**audit_log**: `actor s` (e-mail), `actor_role?`, `action s`, `target s`, `detail any?`, `at`. Forever.
**admin_notes**: `user_id`, `text s`, `by s`, `at`.

### 2.9 Plans and billing

**plans**: `key s` (unique), `name`, `tagline`, `bullets [s]`, `entitlements {finder_searches_per_day i, finder_leagues i, grid_games i, insights_per_day i, follows_max i, saved_max i, notes_max i, alerts b, matchup_tab b, export b}` (−1 = no limit), `prices [{id, interval ("month"|"year"), amount_cents i, currency, active b, stripe_price_id?, retired_stripe_price_id?}]`, `is_default b`, `visible b`, `archived b`, `highlight b`, `sort i`, `trial_days i?`, `stripe_product_id?`, `stripe_mode?`, `stripe_synced_name?`, `synced_at?`.
**subscriptions**: `_id` = Stripe subscription id. `user_id`, `customer_id`, `status s` (Stripe's), `plan_key`, `price_key`, `stripe_price_id`, `interval`, `amount_cents`, `currency`, `current_period_start/end dt`, `cancel_at_period_end b`, `canceled_at?`, `ended_at?`, `trial_end?`, `past_due_since dt?`, `last_event_at i` (Stripe event time, for ordering), `created_at`, `updated_at`.
**payments**: `_id` = Stripe invoice id. `user_id?` (null after the person is deleted), `customer_id`, `subscription_id`, `status s` ("paid", "failed", "partially_refunded", "refunded"), `amount_paid i`, `amount_due i`, `refunded_cents i?`, `currency`, `number?`, `invoice_url?`, `billing_reason?`, `payment_intent?`, `charge?`, `period_end dt?`, `plan_key?`, `last_event_at i`, `created_at`.
**webhook_events**: `_id` = "stripe:<event id>" or "resend:<svix id>", `provider`, `type`, `status s` ("processing", "processed", "error"), `attempts i`, `error s?`, `received_at` (TTL 90 days).
**coupons**: `code s` (unique), `name`, `percent_off?`, `amount_off_cents?`, `currency?`, `duration`, `months?`, `max_redemptions?`, `expires_at?`, `active b`, `stripe_coupon_id`, `stripe_promo_id`, `created_by`, `created_at`.

### 2.10 E-mail

**email_templates**: `key s` (unique), `subject`, `html`, `text`, `updated_by`, `updated_at`. A row overrides the built-in default; deleting it restores the default.
**email_log**: `at`, `template s`, `category s`, `to s` (null after deletion), `to_hash s`, `user_id?`, `subject`, `status s` ("queued", "sent", "delivered", "delayed", "bounced", "complained", "failed", "skipped_*"), `provider_id?`, `error?`, `attempts i`, `campaign_id?`. No bodies, ever.
**email_suppressions**: `email s` (unique), `reason s` ("bounce", "complaint", "unsubscribe", "manual"), `source`, `at`.
**email_campaigns**: `subject`, `html`, `segment`, `status s` ("draft", "partial", "sent"), `sent i`, `skipped i`, `failed i`, `created_by`, `created_at`, `last_sent_at?`.

### 2.12 Site Studio, popups, e-mail list, integrations, alerts (see `16`)

**site_state**: one row, `_id` "state": `live_v i`, `draft {…all sections…}?`, `draft_base_v i`, `draft_by`, `draft_at`.
**site_versions**: `v i` (unique), `data {…all sections…}`, `css s` (compiled), `note`, `by`, `at`, `changed [section]`. The last 50 are kept.
**site_counter**: `_id` "version", `n i`.
**site_assets**: `id s`, `name`, `mime`, `size i`, `data bin` (up to 512 KB), `at`, `by`. Served by `GET /api/site/assets/{id}`.
**popups**: the popup document from `16` §3 (`name`, `status`, `kind`, `priority`, `content`, `form`, `design`, `trigger`, `targeting`, `frequency`, `schedule`, `ab`) plus `created_at`, `updated_at`, `created_by`, `updated_by`. At most 60.
**popup_stats**: `popup_id s`, `day s`, `view i`, `click i`, `dismiss i`, `submit i`, `expires_at dt` (800 days). One row per popup per day. No person is stored.
**newsletter**: `email s` (unique), `status s` ("pending", "confirmed", "unsubscribed"), `source s` ("footer", "popup:<id>"), `consent_text s`, `consent_at dt`, `confirmed_at dt?`, `unsub_at dt?`, `ip_hash s?`, `created_at dt`.
**integration_jobs**: `kind` "audience", `provider`, `action` ("upsert", "unsubscribe"), `email`, `status` ("pending", "done", "dead"), `attempts i`, `next_at dt`, `error?`, `created_at`, `expires_at` (30 days).
**webhook_endpoints**: `_id` ("ep_…"), `url`, `events [s]`, `active b`, `include_email b`, `note`, `secret {ciphertext, iv}`, `secret_last4`, `fail_streak i`, `last_status`, `last_at`, `created_at`, `created_by`.
**webhook_outbox**: `_id` ("<event id>:<endpoint id>"), `endpoint_id`, `type`, `event_id`, `body s`, `status` ("pending", "done", "dead"), `attempts i`, `next_at dt`, `error?`, `expires_at` (14 days).
**webhook_deliveries**: `endpoint_id`, `event_id`, `type`, `attempt i`, `ok b`, `status i`, `info`, `at`, `expires_at` (30 days).
**admin_alerts**: `key s`, `text s`, `resolved b`, `created_at`, `at`, `notified_at?`, `resolved_at?`, `resolved_by?`. One open row per key.

Also added to existing collections: `users.acq {source, medium, campaign, ref_host}` (first touch, set at sign-up), `users.admin_tabs [id]` (phone bar), `users.prefs.admin_alerts` and `users.prefs.admin_digest` (staff only), `events.utm {source, medium, campaign}`, `email_log.idem s?` (sparse index; stops the same e-mail being sent twice with any provider).

### 2.11 Analytics, inbox, announcements

**events**: `name s` ("page_view", "pricing_view", "paywall_view", "insight_view", "signup", "verified", "login", "finder_search", "checkout_started", "checkout_completed", "subscribed", "follow", "save", "contact"), `at`, `day s`, `actor s` ("u:<id>" or "a:<daily anonymous hash>"), `user_id?`, `path s?` (no query string, ids replaced by `:id`), `device s`, `ref_host s?`, `props {}` (max 8 short fields). No IP address. TTL `analytics.retention_days`.
**announcements**: `text`, `level`, `audience` ("all", "signed_out", "free", "paid"), `starts_at?`, `ends_at?`, `active b`, `by`, `created_at`.
**contact_messages**: `name`, `email`, `message`, `status s` ("new", "read", "replied", "spam", "closed"), `note?`, `handled_by?`, `handled_at?`, `ip`, `at`.

## 3. Indexes

All indexes are in `backend/mongo_init.py`. The ones that matter most for speed:

| Index | Serves |
|---|---|
| `matches (league_iid, kickoff)` | Today, League fixtures |
| `matches (status, kickoff)` | Upcoming and finished lists |
| `player_match_stats (player_iid, kickoff desc)` | Player page, Quick view |
| `player_match_stats (team_iid, kickoff desc)` | Squad grid |
| `player_match_stats (opp_iid, kickoff desc)` | Against view |
| `team_match_stats (team_iid, kickoff desc)` | Team totals grid |
| `forecasts (match_iid, is_current, hidden)` | Match page |
| `forecasts (is_current, tier, p desc)` | Insights feed |
| `forecasts (fkey, run_id)` unique | Re-run safety |
| `api_cache (expires_at)` TTL | Cache clean-up |
| `sessions (_id)`, `(expires_at)` TTL, `(user_id)` | Cookie lookup, auto-expiry, "sign out everywhere" |
| `users (email)` unique, `(id)` unique | Sign-in, public ids |
| `events (day, name)` | Analytics charts |
| `subscriptions (user_id, status)` | "What plan does this person have?" on every request |
| `rate_limits (expires_at)` TTL | Window clean-up |

Check each page's query with `explain()` once on real data. Slow queries can time out on shared hosting.

## 4. Size

Measured on simulated rows with the same shape as real rows (25 players per match):

| Collection | Per finished match |
|---|---|
| `matches` | 0.4 KB |
| `team_match_stats` | 0.7 KB |
| `player_match_stats` | 9 KB |
| `lineups` | 6 KB |
| Total, plus about 40% for indexes | **about 23 KB** |

One league-season (380 matches) is about **9 MB**. Real rows carry more fields (goals, assists, xG), so plan **12 MB**. Five leagues times five seasons is about **300 MB**. Raw cached responses are extra and short-lived (`cache.raw_retention_days` = 30).

Start with one league and one season. Measure with `db.command("dbstats")`. Widen only after.

## 5. Retention

| Data | Kept |
|---|---|
| `api_cache` raw responses | 30 days (`cache.raw_retention_days`); lists of finished seasons forever |
| `api_call_log` | 45 days |
| `forecasts` | `engine.keep_days` = 7 days after kickoff, then moved out. Outcomes are kept forever. |
| `forecast_outcomes`, facts, lineups | Forever |
| `audit_log`, `settings_history`, `payments`, `subscriptions` | Forever (payments lose the link to a deleted person) |
| `sessions`, `auth_tokens`, `rate_limits`, `finder_usage` | Until `expires_at` (TTL index) |
| `auth_log` | 90 days (`security.auth_log_retention_days`) |
| `app_logs` | 30 days (`security.log_retention_days`) |
| `events` | 400 days (`analytics.retention_days`) |
| `webhook_events` | 90 days |
| `email_log` | Forever (no bodies); recipient cleared when the person deletes their account |
| `popup_stats` | 800 days (TTL) |
| `integration_jobs`, `webhook_deliveries` | 30 days (TTL) |
| `webhook_outbox` | 14 days (TTL) |
| `site_versions` | Last 50 |
| `newsletter` | Until the person is removed; unsubscribed rows stay so we never re-add them without new consent |

A nightly clean-up job deletes `forecasts` older than `engine.keep_days` whose outcome is stored.

## 6. Backups

Ask the host how MongoDB is backed up and test a restore once. In addition, export the small, hard-to-rebuild collections to JSON every month: `settings`, `plans`, `email_templates`, `content_pages`, `coupons`, `users` (hashes included, store the file encrypted), `subscriptions`, `payments`, `follows`, `notes`, `newsletter`, `forecast_outcomes`. Never export `provider_keys`; re-enter keys by hand. Facts can be re-ingested from PitchAPI (at a cost in calls), so they are lower priority.
