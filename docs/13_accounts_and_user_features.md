# 13. Accounts and user features

Simple sign-up, sign-in and an account area. Built and tested in `accounts.py`, `routes_accounts.py`, `deps.py`. This file is what the front end builds against.

## 1. Principles
- Sign-up takes e-mail + password. Nothing else is required.
- Everything useful for reading stays open without an account. An account adds follows, saved forecasts, notes, alerts, more Finder searches.
- One answer for "this e-mail exists" and "it does not". Sign-up, forgot-password and resend always say: "If that address can be used, we sent a link."
- No password rules theatre. Minimum length (`auth.password_min_length`, 10), a short common-password list, no letter-case or symbol rules.
- Sign in with Google is NOT built. The setting `auth.google_enabled` is a placeholder for later (P3). Do not add a button.
- Billing off (`features.billing` = false) means every signed-in person gets the top plan. Free-vs-paid only starts to matter when billing is on.

## 2. Screens

| Screen | Route | Notes |
|---|---|---|
| Sign up | `/sign-up` | E-mail, password (show/hide), name optional. Terms and privacy links. After submit: "Check your inbox" page with a Resend button (60 s wait). |
| Confirm e-mail | `/verify-email?token=` | Calls `POST /api/auth/verify-email`. Success → "You're in" → sign-in. Expired → "Send a new link". |
| Sign in | `/sign-in` | E-mail, password, "Forgot password?". If the API answers `needs_2fa`, show the code screen with a "Use a recovery code" link. |
| Two-factor code | `/sign-in/2fa` | One 6-digit field, auto-submit at 6. Recovery code accepted in the same field. Challenge lasts 5 minutes and 5 wrong codes end it. |
| Forgot password | `/forgot-password` | E-mail → always the same confirmation. |
| Reset password | `/reset-password?token=` | New password twice. Link works once, for `auth.reset_token_minutes` (60). Success signs out every device, then go to sign-in. The same page sets a first password for invited staff. |
| Confirm new e-mail | `/confirm-email?token=` | From the account page flow. |
| Account | `/account` | Tabs below. |
| Pricing | `/pricing` | From `GET /api/plans`. Hidden or shows "Coming soon" when `billing_enabled` is false. |
| Unsubscribe | `/unsubscribe?t=` | `GET /api/email/unsubscribe?t=` shows the masked address; the button calls `POST`. A GET never changes anything. |
| Contact | `/contact` | Name, e-mail, message → `POST /api/contact`. |
| Enrol in 2FA (staff) | `/enroll-2fa` | Shown when `GET /api/auth/me` returns `scope: "enroll_2fa"`. QR + manual key, confirm with a code, then show 10 recovery codes once with "I saved them" required. |

### Account tabs
1. **Profile**: name, time zone (auto-detected, editable), theme (system / dark / light). `PATCH /api/account/profile`.
2. **Security**: change password (current + new; other devices are signed out); change e-mail (password + new address; link goes to the new address; old address is told); two-factor on/off (off needs password + code; staff cannot turn it off); recovery codes are shown once at set-up.
3. **Devices**: list of sessions (device, last seen, "This device"), Sign out one, Sign out all others. `GET /api/account/sessions`.
4. **Notifications**: three switches: product e-mails (default on), marketing e-mails (default off), alert e-mails (default on). Receipts and security e-mails cannot be turned off; say so under the switches. **Staff** see two more: "E-mail me when something looks wrong" (`prefs.admin_alerts`, default on for owner and admin) and "Weekly summary" (`prefs.admin_digest`, default off). Sent through `PATCH /api/account/profile` with `prefs`; the server ignores these two for non-staff.
5. **Plan and billing**: current plan, status chip, next renewal or end date, "Manage billing" (opens Stripe's portal), invoice list with links, "Change plan" (opens pricing). A comp shows "Included until {date}". Past due shows an amber notice with the grace days left.
6. **Privacy**: "Download my data" (`GET /api/account/export`, JSON file). "Delete my account" (type your password; says what is removed and what is kept: payment records, unlinked from your name). Cancels any subscription first; if Stripe is down the delete is refused with a clear message.

## 3. Bootstrapping the app
On load call `GET /api/auth/me`. It never fails for signed-out visitors.
```
{ "user": null, "plan": {"plan_key": "free", ...}, "entitlements": {...}, "limits": {"anonymous_finder_searches_per_day": 3} }
{ "user": {id, email, role, display_name, tz, theme, email_verified, two_factor, prefs, ...},
  "plan": {plan_key, plan_name, source: "billing_off|comp|subscription|free", status, period_end, cancel_at_period_end},
  "entitlements": {finder_searches_per_day, finder_leagues, grid_games, insights_per_day, follows_max, saved_max, notes_max, alerts, matchup_tab, export},
  "usage": {"finder_today": 4}, "billing_enabled": true }
{ "user": {...}, "scope": "enroll_2fa" }      // staff who still must set up 2FA
```
Use `entitlements` to draw the UI (disable, show padlock icons, upgrade prompts). The server enforces the same limits, so the UI is only a hint.

## 4. Sessions in the browser
- The API sets one cookie: `__Host-sid` (`sid` without HTTPS): `HttpOnly`, `Secure`, `SameSite=Lax`, `Path=/`. JavaScript cannot read it.
- Send every request with `credentials: "include"` (same site) and `Content-Type: application/json` on writes.
- Never store a token, password or code in `localStorage`, `sessionStorage` or the URL. Theme and filter preferences may be stored.
- On `401 SIGN_IN_REQUIRED` anywhere: clear state, go to sign-in with a `next` path. On `403 ENROLL_2FA_REQUIRED`: go to `/enroll-2fa`.
- The app and the API should share one domain (Emergent serves `/api` on the app domain). If not, put the app URL in `ALLOWED_ORIGINS` and `security.allowed_origins`, and use a parent domain cookie plan before launch.

## 5. Plan limits in the UI

| Limit | Where it shows | Free (seed) | Pro (seed) | Server error when over |
|---|---|---|---|---|
| Finder searches per day | Finder header "4 of 10 today" | 10 | no limit | `402 UPGRADE_REQUIRED` (signed in), `401 SIGN_IN_REQUIRED` (signed out, 3/day) |
| Leagues per Finder search | League picker | 1 | no limit | `403 UPGRADE_REQUIRED`, `400 PICK_A_LEAGUE` |
| Games in grids | Squad and team grids | 5 | 10 | the builder trims the list in the grid routes with `plans.ent(db, user, "grid_games")` (not in the reference server) |
| Insight cards per day | Home feed | 20 | no limit | the list is shorter (done in `/api/insights`) |
| Follows / saved / notes | Favourites, saved, player notes | 10 / 20 / 20 | no limit | `409 LIMIT_REACHED` (builder adds in the follow/save/note routes with `plans.ent`) |
| Alerts, matchup tab, CSV export | Feature entry points | off | on | `403 UPGRADE_REQUIRED` |

Upgrade prompt copy (plain, no pressure): "That is part of Pro. See plans." One button. No countdowns, no fake scarcity, no confetti. The seed numbers are placeholders. Moh sets real ones in Admin > Plans.

## 6. Error codes → what to say
All errors are `{"error": {"code", "message", "request_id"}}`. Show `message` as is for these codes; for `SERVER_ERROR` add "Reference: {request_id}".

| Code | HTTP | Where | Say |
|---|---|---|---|
| `BAD_CREDENTIALS` | 401 | sign-in | Wrong e-mail or password. |
| `EMAIL_NOT_VERIFIED` | 403 | sign-in | Check your inbox and confirm your e-mail first. (show Resend) |
| `ACCOUNT_DISABLED` | 403 | sign-in | This account is turned off. Contact support. |
| `LOCKED` | 429 | sign-in | Too many attempts. Try again later. |
| `RATE_LIMITED` | 429 | any | Too many requests. Try again in {Retry-After} seconds. |
| `BAD_CODE` / `CHALLENGE_EXPIRED` | 401 | 2FA | That code is not right. / Sign in again. |
| `TOKEN_INVALID` | 400 | verify, reset, confirm | This link is not valid any more. Ask for a new one. |
| `PASSWORD_TOO_SHORT` / `TOO_COMMON` / `TOO_LONG` | 400 | sign-up, reset, change | Use at least 10 characters. / That password is too easy to guess. |
| `BAD_EMAIL` | 400 | forms | Enter a valid e-mail address. |
| `SIGNUP_CLOSED` | 403 | sign-up | Sign-up is closed right now. |
| `BAD_ORIGIN` | 403 | any write | Reload the page and try again. |
| `TOO_LARGE` | 413 | any write | That request is too large. |
| `BILLING_OFF` / `BILLING_UNAVAILABLE` / `BILLING_ERROR` | 409/503/502 | checkout | Paid plans are not open yet. / Payments are not available right now. |
| `ALREADY_SUBSCRIBED` | 409 | checkout | You already have a plan. Use Manage billing to change it. |
| `UPGRADE_REQUIRED` | 402/403 | gated feature | That is part of Pro. See plans. |
| `SERVER_ERROR` | 500 | any | Something went wrong on our side. |

## 7. Route map (all under `/api`)

| Method | Path | Auth | Extra limit | Does |
|---|---|---|---|---|
| POST | `/auth/register` | none | 5/h per IP | 202 always; sends the verify e-mail |
| POST | `/auth/verify-email` | none |  | confirms; sends welcome |
| POST | `/auth/resend-verification` | none | 5/h IP, 3/h e-mail | 202 always |
| POST | `/auth/login` | none | 10 per 15 min per e-mail, lockout after `auth.max_failed_logins` | sets cookie, or `needs_2fa` + `challenge` |
| POST | `/auth/login/2fa` | challenge | 10 per 15 min per IP | sets cookie |
| POST | `/auth/logout` | cookie |  | ends session |
| POST | `/auth/forgot-password` | none | 5/h IP, 3/h e-mail | 202 always |
| POST | `/auth/reset-password` | token | 10/h IP | sets password; signs out all devices; security e-mail |
| GET | `/auth/me` | optional |  | bootstrap payload |
| PATCH | `/account/profile` | user |  | name, tz, theme, e-mail preferences |
| POST | `/account/password` | user | 5 per 15 min | change; other devices signed out |
| POST | `/account/email` · `/account/email/confirm` | user · token | 5/h | change e-mail |
| POST | `/account/2fa/begin` · `/confirm` · `/disable` | user or enrol-only session | 10 per 15 min | two-factor |
| GET/DELETE | `/account/sessions` · `/account/sessions/{sid}` · POST `/revoke-others` | user |  | devices |
| GET | `/account/export` | user | 3/day | JSON of the person's data |
| DELETE | `/account` | user + password | 3/h | cancels billing, deletes data |
| GET | `/account/billing` | user |  | plan, subscription, last 12 payments |
| GET | `/plans` | none |  | pricing page data (no Stripe ids) |
| POST | `/billing/checkout` · `/billing/portal` | user (verified e-mail for checkout) | 10/h · 20/h | Stripe-hosted pages |
| GET/POST | `/email/unsubscribe` | token |  | preview / unsubscribe |
| POST | `/contact` | none | 3/h per IP | stores the message |
| POST | `/analytics/collect` | optional |  | page_view, pricing_view, paywall_view, insight_view |
| GET | `/announcements` | optional |  | active banners for this audience |
| GET | `/content/{slug}` | none |  | Markdown page |

Per-IP limits from the middleware apply on top: `security.rate_limit_auth_per_minute` (10), `_write_` (60), `_read_` (240).

## 8. E-mails the person receives
Verify e-mail · Welcome · Password reset · Password changed · New e-mail confirm · E-mail changed · Receipt · Payment failed · Trial ending · Subscription ended · Account deleted. Staff also get: invite, alert, weekly summary. Visitors who join the e-mail list get the confirm message (`newsletter_confirm`). 15 templates in all. Full table and variables: doc 14 §4.

## 9. Accessibility and states for every form
Labels above fields, errors under fields and in a summary, `autocomplete` attributes (`email`, `current-password`, `new-password`, `one-time-code`), password show/hide with an accessible name, disabled button while sending, focus moves to the first error, nothing relies on colour alone, works with a keyboard only, 44 px touch targets.
