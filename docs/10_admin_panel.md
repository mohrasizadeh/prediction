# 10. Admin panel

The control room. Staff run the whole product from here: people, money, e-mail, data, **and how the site looks and behaves** (colours, fonts, buttons, menus, popups, e-mail list, integrations). Everything is also available as an API (`routes_admin.py` and `routes_site.py`), so the screens below only call routes that exist and are tested. There are 32 modules. The admin works on computers, tablets and phones; on a phone the menu is a bottom app bar (`17_admin_responsive_ui.md`). The site-control tools are specified in `16_site_studio_popups_integrations.md`.

## 1. Who can do what

Five roles. Checked on the server on every request (`deps.require_perm`). Hiding a button is not security.

| Role | Who | Can |
|---|---|---|
| `owner` | Moh | Everything. Only role that can save API keys, invite or change staff, purge a person, refund real money, change `security.*`, `billing.*`, `auth.*`, `features.billing`, **turn on tracking tags (`tracking.*`) and write custom CSS**. |
| `admin` | Trusted helper | Everything else: users, plans, subscriptions, refunds (test mode), coupons, e-mail, logs, analytics, settings, jobs, content, **Site Studio (edit and publish), Popups, Integrations (e-mail provider, list sync, webhooks)**. |
| `support` | Support person | Look up people (full e-mail), fix accounts (disable, enable, sign out, resend verify, send reset link, add notes), read the e-mail log, read the inbox and mark messages. No analytics, no plans, no money. |
| `analyst` | Marketing or finance | Read-only: analytics (including realtime, compare, sources), plans, subscriptions, payments, logs, e-mail health, popup results. Personal data masked (`j***@gmail.com`, `203.0.113.x`). Cannot search by e-mail. |
| `user` | Everyone else | No admin routes. |

The permission table is `accounts.PERMS`. The panel reads it from `GET /api/admin/staff` and hides what the role cannot use.

### Staff rules
- Staff must use two-factor sign-in (`security.require_staff_2fa`). A staff session without it can only reach the 2FA set-up screen. The API answers `ENROLL_2FA_REQUIRED`.
- Staff session lasts `auth.staff_session_minutes` (60) and ends after `auth.staff_idle_minutes` (20) of no use.
- No sign-in-as-user. No shared accounts. One person, one account.
- The last owner cannot be demoted, turned off or deleted.
- Staff cannot act on their own account for risky actions, or on other staff (owner only).
- Every write goes to `audit_log` with actor, role, action, target and reason. Notes and reasons are required for disable, refund and comp.
- A signed-out visitor who opens `/admin` sees the normal 404 page. A signed-in normal user sees the same.

## 2. Layout

The menu is drawn from `GET /api/admin/shell`, which lists only the modules the person may use (see `17`).

**Computer (1025 px and wider)**: left rail in nine groups. Top bar: data status chip ("Data updated 3 h ago"), environment chip (TEST or LIVE billing), search box (jump to a person by name or id), your role, light/dark switch, sign out. Tables: sticky header, sort, filter chips, page size 25/50/100, column picker, CSV export of what you see (masked for your role). Every settings form has a sticky save bar and a diff before saving. Destructive actions need a typed confirmation.

**Tablet and phone (1024 px and narrower)**: no rail. A bottom app bar with 4 icons and **More**. More opens a full-screen sheet with search and every tool in groups. Staff can pick which 4 tools sit in their bar. Tables become cards, side drawers become full-screen sheets, buttons are at least 44 px. See `17_admin_responsive_ui.md` and `prototype/admin_prototype.html`.

```
OVERVIEW   Dashboard · Analytics
PEOPLE     Users · Staff · Inbox · E-mail list
GROWTH     Popups · Announcements · Campaigns
SITE       Site Studio · Pages · Images
MONEY      Plans · Subscriptions · Payments · Coupons · Revenue
E-MAIL     Templates · Log · Blocked addresses
CONNECT    Integrations
DATA       Leagues · Jobs · Data quality · Engine · Endpoint explorer · Cache and usage
SYSTEM     Settings · Keys · Logs · Security · Health
```

## 3. Modules

### 3.1 Dashboard (`analytics.read`)
`GET /api/admin/dashboard`. Top row of stat tiles: people (total, free, paid, trial, comp), active today / 7 days / 30 days, new sign-ups (with change vs the last period), MRR, paying people, churn. Below: sign-ups per day, visitors per day, plan split. Right column: **Alerts** from `GET /api/admin/health` (red first). Alerts we raise: PitchAPI breaker open or key rejected, no job ran in 3 hours, API calls over 80% of the budget, failed webhooks in 24 h, more than 5 server errors in 24 h, staff without 2FA, billing on while e-mail is off, billing on in TEST mode.

### 3.2 Analytics (`analytics.read`; revenue needs `billing.read`)
Date range picker (7 / 30 / 90 / 400 days). Tabs:
- **Overview** `analytics/overview`: people counts, active users, sign-ups, page views, revenue, plan split.
- **Traffic** `analytics/traffic`: top pages (views, visitors), referrers (host only), devices.
- **Funnel** `analytics/funnel`: Visitors → Signed up → Verified → Started checkout → Paid, with step conversion. It is a count in the same window, not a strict cohort. Say so under the chart.
- **Finder** `analytics/finder`: searches per day, signed-in share, top stats, modes, searches per person.
- **Retention** `analytics/retention`: weekly sign-up cohorts, share active N weeks later (heat grid).
- **Revenue** `analytics/revenue`: per currency: MRR, ARR, ARPU, collected, refunded, failed payments, churn, trials, past due, scheduled to cancel. Never add currencies together.
- **Events** `analytics/series?name=`: any single event as a line.
Charts follow the data-viz rules in doc 04. Counting rules: `analytics.py` header.

### 3.3 Users (`users.read`)
`GET /api/admin/users`. Filters: search (name, id; e-mail if you may), role, plan (free / paid / trial / past due / comp), verified, disabled, created between. Columns: person, plan, role, created, last sign-in, flags (2FA, disabled, unverified).
**User drawer** `GET /api/admin/users/{id}`: profile, plan and limits in force, subscriptions, payments, devices (sessions), e-mails sent (template and status, never the body), sign-in history, recent events, notes, counts of follows / saved / notes. No hashes, secrets or tokens are ever in this payload (tested).
Actions (buttons with reason boxes where needed):
| Action | Perm | Route |
|---|---|---|
| Add note | users.write | `POST users/{id}/notes` |
| Disable / enable (reason required, signs them out) | users.write | `POST users/{id}/disable` · `enable` |
| Sign out everywhere | users.write | `POST users/{id}/logout` |
| Resend verification | users.write | `POST users/{id}/resend-verification` |
| Send password-reset e-mail (link never shown to staff) | users.write | `POST users/{id}/send-reset` |
| Give a plan free (comp), days and reason required | plans.write | `POST users/{id}/comp` · `comp/revoke` |
| Change role | staff.manage | `POST users/{id}/role` |
| Reset someone's 2FA | staff.manage | `POST users/{id}/reset-2fa` |
| Delete a person's data (GDPR) | users.purge | `DELETE users/{id}/purge` |
Free vs paid is a filter and a column, not a separate module: Free = no live subscription and no comp.

### 3.4 Staff (`security.read`; invite and roles need `staff.manage`)
List with role, 2FA status, last sign-in. **Invite** (e-mail + role admin / support / analyst): sends a set-password link by e-mail; if e-mail is off the link is shown once to the owner. Role matrix table (from `GET /api/admin/staff`). Role change signs that person out.

### 3.5 Plans (`plans.read` / `plans.write`)
Cards for each plan with subscriber count. Editor:
- Name, tagline, bullets, visible on pricing page, highlight, sort, trial days (blank = default `plans.trial_days`).
- **Entitlements grid** from the catalogue returned by `GET /api/admin/plans`: switches for on/off items, numbers for limits (`-1` = no limit). The catalogue is `plans.ENTITLEMENTS`: Finder searches per day, Finder leagues, grid games, insights per day, follows, saved forecasts, notes, alerts, tactical matchup tab, CSV export.
- **Prices**: id (monthly, yearly), interval, amount in cents shown as money, currency, active. A price change makes a NEW Stripe price and retires the old one. People already subscribed keep their old price. Show that warning.
- **Sync to Stripe** button (`billing.write`): creates the product and prices, shows which are synced.
- Archive (blocked while people are subscribed). The free plan cannot be archived and has no prices.
- Comp (free upgrade) is on the user drawer.
- Preview: "What a free user sees" and "What a Pro user sees" using the same endpoint the app uses.

### 3.6 Subscriptions and payments (`billing.read` / `billing.write`)
Subscriptions table: person, plan, price, status chip, period end, scheduled-to-cancel flag. Row actions: cancel at period end, cancel now, resume. Payments table: date, person, amount, status (paid, failed, partially refunded, refunded), invoice link, number. **Refund** dialog: amount (default full, max what is left), reason required. In live mode only an owner may refund. After any billing action the status changes when Stripe's webhook arrives; the screen says so.

### 3.7 Coupons (`billing.read` / `billing.write`)
Create a code: percent off OR amount off, duration (once, repeating N months, forever), max uses, expiry. List with active flag. Deactivate. Codes work at Stripe Checkout (`billing.allow_promo_codes`).

### 3.8 E-mail (`email.read` / `email.write`)
- **Templates**: the 15 system e-mails (list in doc 14 §4). Editor for subject, HTML, text. Shows allowed variables. Live preview in a sandboxed frame. Save refuses scripts, forms and event handlers. Reset to default. **Send test to me** (goes to the signed-in staff member only).
- **Log**: every send: time, template, category, recipient (masked by role), status (sent, delivered, delayed, bounced, complained, failed, skipped_*), provider error. No bodies are stored.
- **Suppressions**: addresses we will not mail (bounce, complaint, unsubscribe, manual). Remove one with a reason.
- **Campaigns** (marketing, opt-in only): subject, body, segment (all / free / paid), **Send**. Blocked until `email.enabled`, `email.marketing_enabled` and `email.footer_address` are set. Sends only to verified people who opted in. Stops at the daily cap and says how many are left; press Send again the next day to continue without duplicates.

### 3.9 Inbox and announcements (`users.read`, `inbox.write`, `content.write`)
- **Inbox**: contact-form messages with status new / read / replied / spam / closed and a private note. No auto-reply is sent.
- **Announcements**: banner text (240 chars), level (info / warn), audience (all, signed out, free, paid), start and end, on/off. Shown by `GET /api/announcements`.

### 3.10 Data modules (kept from the earlier version)
- **Leagues and seasons**: enable leagues, pick backfill seasons, coverage, run backfill, call estimate.
- **Jobs and queue**: each job's last run, **Run now** (`POST jobs/run`), queue counts, retry/skip, tick history, breaker state and **Close breaker** (`POST breaker/close`). Needs `jobs.run`.
- **Data quality**: `ingest_issues` with Resolve; coverage matrix league × field; mapping editor for `provider.pitchapi.*` with a "check against a saved fixture" button.
- **Engine**: runs, markets on/off with coverage, tuning (`engine.*`), tier cut-off preview, forecast browser with Hide / Unhide and a reason. Lineup effects shown read-only (locked off). **Images** (a tab inside Engine, doc 19 §6; `GET /images`, `/images/review`, `POST /images/sync`, approve / reject / upload / take down; writes need `jobs.run`): counts per kind, today's API calls against the budget, bytes stored, the review list with candidates side by side, Run sync, Refresh squads. **Brain layers** (a tab inside Engine, doc 18 §7; `GET /brain`, needs `logs.read`): the latest gate row per league and layer with its reason, the three switches (`context.start_model`, `engine.tactic_layers`, `engine.shape_layer`), the competition weights, calendar coverage, and the calendar import box (`POST /calendar/import`, needs `jobs.run`).
- **Endpoint explorer**: run an allowed PitchAPI route, see cached or real, cost, raw JSON tree, force refresh (shows cost), save as fixture. Used for check A.
- **Cache and usage**: cache table, delete by prefix, calls today vs budget, 14-day chart, by purpose and status.

### 3.11 Settings (`settings.read` / `settings.write`)
Generic editor built from `GET /api/admin/settings` (175 settings from `11_settings_registry.json`). Grouped and searchable. Each row: label, help, input by type, default, current value, when it applies, **Reset to default**, **History** (`settings/{key}/history`). Public settings are tagged. Owner-only settings show a padlock icon for other roles (`owner_only: true`). Locked settings are read-only. The server checks the value type and answers `BAD_VALUE` with the reason.

### 3.12 Keys (`settings.read` to see; `keys.write` owner only to change)
One card each, write-only inputs, shows "•••• 3456", date rotated, and where the value comes from (`admin`, `environment` or `none`):
| Key | Format | Test button |
|---|---|---|
| PitchAPI | `pk_live_…` / `pk_test_…` | one call to `/v1/leagues` |
| API-Football | 32 letters and numbers | none (a test call spends one of the day's 100); used only by the image sync, doc 19 |
| Stripe secret | `sk_test_…` / `sk_live_…` / `rk_…` | `GET /v1/balance`, shows live or test |
| Stripe webhook secret | `whsec_…` | shows when the last event arrived |
| Resend API key | `re_…` | lists verified domains (a send-only key is fine) |
| Resend webhook secret | `whsec_…` | shows when the last event arrived |
| Postmark server token | letters, numbers, dashes | read-only call to the server info route |
| SendGrid API key | `SG.…` | lists key scopes |
| Brevo API key | `xkeysib-…` | reads the account |
| SMTP password | any | opens a connection and signs in; sends nothing |
| Mailchimp API key | 32 characters, dash, data centre (`…-us21`) | reads the list |
| MailerLite token | long token | reads groups |
Only the key of the e-mail provider chosen in Integrations is used for sending. Mailchimp, Brevo and MailerLite keys are for list sync (§3.20).
A Stripe live key is refused while `billing.mode` is `test`, and the other way round. Saving the PitchAPI key closes the breaker and clears the red banner. Keys are encrypted at rest (AES-256-GCM) and never sent back to the browser. Changing an environment variable needs a redeploy, so use this screen.

### 3.13 Content (`content.write`)
Markdown pages (Terms, Privacy, About, FAQ, Learn) with preview. The panel must render Markdown with a sanitiser and never as raw HTML. A scan on save rejects banned words except the exact disclaimer. Brand, colours, fonts and buttons moved to Site Studio (§3.17).

### 3.14 Logs (`logs.read`)
One screen, tabs. Filters, time range, page size. Personal data masked unless `logs.pii`.
| Tab | Source | Shows |
|---|---|---|
| Audit | `audit_log` | every staff and system change: who, role, action, target, detail |
| Sign-ins | `auth_log` | sign-in, 2FA, reset, e-mail change, role change, with result and reason |
| Application | `app_logs` | 5xx errors with request id, blocked requests (401/403/429), admin writes. Stack traces for owner and admin only. |
| PitchAPI calls | `api_call_log` | path, status, cached, cost, purpose |
| Webhooks | `webhook_events` | Stripe and Resend events, status, attempts, error text |
| Jobs | `job_runs` | each job run and result |
| Data issues | `ingest_issues` | problems found while ingesting |
| E-mail | `email_log` | see 3.8 |
Support can quote a **request id** from an error page to find the exact log row.

### 3.15 Security (`security.read`)
`GET /api/admin/security`: failed sign-ins in 24 h by hour, accounts under a temporary lockout, rate-limited and blocked requests, staff list with 2FA flags, active staff sessions, last 15 staff actions. Plus a checklist card: staff without 2FA, live billing on, default owner password changed, e-mail domain verified.

### 3.16 Health (`logs.read`)
`GET /api/admin/health`: last job, queue by status, breaker, calls today vs budget, e-mails today vs cap, webhook errors, server errors, alerts list.

### 3.17 Site Studio (`site.read` / `site.write` / `site.publish`; custom CSS owner only)
Brand and logo, light and dark colours (23 tokens each) with a readability gate, fonts (14 self-hosted choices), corners, density, shadows, button style and size, navigation (desktop menu, phone bottom bar, More), footer, SEO and redirects, cookie banner, home page blocks, images. Everything is edited in a **draft** with a live preview (dark/light, desktop/phone), then **published** as a numbered version. Any of the last 50 versions can be rolled back. Full spec: `16` §2. Routes: `/api/admin/site/*`.

### 3.18 Popups (`popups.read` / `popups.write`)
Popup Maker: modal, corner slide-in, top or bottom banner; plain text; optional e-mail field with consent sentence; triggers (immediately, delay, scroll, exit intent, pages viewed, click); targeting by page, audience, device, new or returning; frequency; dates; A/B groups; stats per popup. Starter templates. Full spec: `16` §3. Routes: `/api/admin/popups*`.

### 3.19 E-mail list (`email.read` / `email.write`; export `users.pii`)
Counts (pending, confirmed, unsubscribed), the list with consent details hidden, remove an address, CSV export. Full spec: `16` §4.

### 3.20 Integrations (`integrations.read` / `integrations.write`; tracking tags owner only)
One page with four cards: **E-mail sending** (Resend, Postmark, SendGrid, Brevo, SMTP; test send), **List sync** (Mailchimp, Brevo, MailerLite; test, backfill, job list), **Webhooks** (add, test, rotate secret, delivery log), **Tracking tags** (owner only). Full spec: `16` §5 and §6. Routes: `/api/admin/integrations/*`.

### 3.21 Analytics extras (`analytics.read`; e-mail health `email.read`)
Realtime, period compare, sources by campaign tag, e-mail delivery health, popup comparison, list growth, CSV export. Spec: `16` §7. Shown as extra tabs in Analytics.

### 3.22 Alerts and weekly summary (`logs.read` to see; `settings.write` to dismiss or send)
Alerts on Health: sign-ups dropped, server errors rising, failed payments, list or webhook problems. The team is e-mailed once per alert. A weekly summary goes to staff who opt in. Spec: `16` §7.

## 4. Where staff can break things, and the guard

| Risk | Guard |
|---|---|
| Spending the whole API budget with Force refresh | Shows cost and remaining budget; blocked at the budget |
| Pasting a wrong key | Format check, Test button, mode check for Stripe |
| Switching billing to live by mistake | Owner-only; live key must match; banner shows TEST or LIVE |
| Refund by mistake | Reason required; amount capped; idempotency key stops a double click; live refunds owner-only |
| Giving away plans quietly | Comp needs days and a reason; every grant is in the audit log; comp ends on its date |
| Bad JSON or wrong type in a setting | Server type check; old value stays |
| Staff reading personal data they do not need | Masking by role; analyst cannot search by e-mail; export masked too |
| A stolen staff session | 2FA, 60-minute life, 20-minute idle end, sign-out-everywhere, `HttpOnly` cookie |
| Locking out the owner | `reset_admin.py` resets the owner password from the shell (see README) |
| Deleting the wrong person | Typed confirmation; owner only; the last owner is protected |
| Mail to people who opted out | Opt-in default, suppression list, cap, one-click unsubscribe |
| Publishing a look nobody can read | Publish is blocked when text pairs fall under 4.5:1; every preset passes; one-click rollback |
| A popup that nags or traps people | Plain text only, mandatory close, never on sign-in, checkout or admin pages, session limits, master switch |
| Custom CSS that loads outside code or hides the page | Owner only; no imports, fonts, outside addresses or markup; sits in a low-priority layer |
| Tracking tags added without telling people | Owner only, off by default, load only after consent, CSP sources and Privacy-page reminder shown |
| A webhook aimed at our own network | Public https only, private and metadata addresses refused (checked at save and at send), no redirects |
| A list-sync or webhook failure nobody notices | Retries with waits, then an alert in Health and an e-mail to the team |
