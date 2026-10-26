# 15. Security and privacy

What protects the app, where it lives in code, how to test it, and what is still on you. Read with doc 03 (rules) and doc 14 (billing and e-mail).

## 1. What we protect, and from whom

| Asset | Threat | Main controls |
|---|---|---|
| Accounts and passwords | Guessing, stuffing from other leaks, phishing, enumeration | bcrypt, lockout, per-IP and per-e-mail limits, same answer for known and unknown, 2FA, session revocation |
| Staff powers (admin) | A stolen staff login, over-wide access | Forced 2FA, short sessions, roles, audit log, owner-only keys and staff |
| Money | Fake webhooks, double charges, wrong refunds | Signature check, event-id dedupe, idempotency keys, reason + role on refunds, hosted checkout |
| API keys (PitchAPI, Stripe, Resend) | Leak to browser, logs or repo | AES-256-GCM at rest, write-only screen, never logged, never in responses |
| Personal data | Over-sharing to staff, leaks in logs, no way to delete | Masking by role, no bodies in e-mail log, export and delete, retention TTLs |
| Availability | Floods, big bodies, crash loops | Rate limits, body cap, generic errors, request ids, health alerts |
| Browser users | CSRF, XSS, clickjacking, mixed content | HttpOnly SameSite cookie, Origin check, CSP, `frame-ancestors 'none'`, HSTS, no raw HTML |

## 2. Controls and where they live

| # | Control | File / function | Proven by |
|---|---|---|---|
| 1 | Passwords: bcrypt cost 12 over a SHA-256 pre-hash (no 72-byte cut), min 10 chars, common-password list | `accounts.hash_password`, `check_password_policy` | selftest_accounts |
| 2 | Timing: a dummy hash is compared when the e-mail is unknown | `accounts.verify_password` | selftest_accounts |
| 3 | No enumeration on sign-up, forgot-password, resend | `routes_accounts` (always 202, same body) | selftest_server |
| 4 | Lockout after N failures (default 5, 15 min) and a per-e-mail limit (10 per 15 min) | `accounts.login`, `RL.check` in the route | selftest_accounts, selftest_server |
| 5 | Sessions: random 256-bit token, stored only as SHA-256, absolute expiry, staff idle expiry, revoke one/all, sliding `last_seen` | `accounts.create_session`, `load_session` | selftest_accounts |
| 6 | Cookie: `__Host-sid`, `HttpOnly`, `Secure`, `SameSite=Lax`, `Path=/`, no `Domain` | `deps.set_session_cookie` | selftest_server |
| 7 | One-time tokens (verify, reset, e-mail change, invite): hashed, single use (atomic), expire, TTL index | `accounts.issue_token`, `consume_token` | selftest_accounts |
| 8 | Reset signs out all devices; password change signs out other devices; role change signs the person out | `confirm_reset`, `change_password`, `set_role` | selftest_accounts, selftest_admin |
| 9 | 2FA (TOTP): secret encrypted, ±1 step window, replay guard, 10 hashed single-use recovery codes, 5 tries per challenge | `accounts.twofa_*`, `_match_counter` | selftest_accounts |
| 10 | Staff must have 2FA: unenrolled staff session has scope `enroll_2fa` and every admin route refuses it | `accounts._finish_login`, `deps.require_user` | selftest_admin |
| 11 | Roles and permissions, checked per route on the server | `accounts.PERMS`, `deps.require_perm` | selftest_admin |
| 12 | Staff cannot act on themselves or on other staff (owner only); last owner protected | `admin_queries.guard_target`, `accounts.set_role` | selftest_admin, selftest_accounts |
| 13 | CSRF: Origin must match (or be listed), `Sec-Fetch-Site: cross-site` refused, JSON bodies, SameSite=Lax | `security_mw._origin_ok` | selftest_server |
| 14 | Rate limits per IP (auth 10/min, write 60/min, read 240/min), shared across workers in MongoDB | `security_mw`, `ratelimit.py` | selftest_server, selftest_accounts |
| 15 | Real client IP: Nth address from the right of `X-Forwarded-For` (N = `security.trusted_proxy_count`); spoofed left entries are ignored | `security_mw.client_ip` | selftest_server |
| 16 | Body cap (`security.max_body_kb`, default 256) | `security_mw` | selftest_server |
| 17 | Security headers: `nosniff`, CSP `default-src 'none'; frame-ancestors 'none'`, `X-Frame-Options: DENY`, Referrer-Policy, Permissions-Policy, COOP, HSTS on HTTPS, `no-store` on auth/account/admin/billing | `security_mw._headers` | selftest_server |
| 18 | Generic 500 with request id; detail only in `app_logs` | `security_mw.dispatch` | selftest_server |
| 19 | Keys encrypted (AES-256-GCM), write-only, masked, never in audit or app logs, format and mode checks | `security.py`, `routes_admin.key_save` | selftest_admin |
| 20 | Stripe webhook: HMAC, tolerance, dedupe, ordering, retry on failure | `stripe_billing.verify_webhook`, `handle_event` | selftest_billing, selftest_admin |
| 21 | Resend webhook: Svix signature, dedupe, suppression | `emailer.verify_svix`, `handle_resend_event` | selftest_billing, selftest_admin |
| 22 | Settings: type-checked on write, locked values refused, owner-only for security/billing/auth | `settings_store.validate`, `routes_admin.OWNER_ONLY_SETTINGS` | selftest_admin |
| 23 | E-mail templates: scripts, forms, handlers refused; variables HTML-escaped; subject is one line (no header injection) | `emailer.save_template`, `render` | selftest_billing |
| 24 | PII masking by role in lists, drawers, logs | `admin_queries.mask_row` | selftest_admin |
| 25 | Analytics: no cookies, no IP stored, daily-rotating anonymous hash, DNT/GPC respected, bots skipped, paths stripped of queries | `analytics.track` | selftest_server |
| 26 | Account export and delete; payments kept but unlinked | `accounts.export_account`, `delete_account` | selftest_accounts, selftest_server |
| 27 | Retention by TTL: sessions, tokens, rate limits, finder counters, webhooks 90 d, sign-in log 90 d, app log 30 d, events 400 d | `mongo_init.py` | selftest (index list) |
| 28 | Audit log for every staff write | `admin_queries.audit`, route code | selftest_admin |

## 3. Things the builder must NOT do
1. No JWT in `localStorage` or in a non-HttpOnly cookie. No tokens in URLs except the one-time e-mail links (which are single use).
2. Do not add `Access-Control-Allow-Origin: *`, and never with credentials. Use `ALLOWED_ORIGINS`.
3. Do not add a "login as user" feature.
4. Do not log request bodies, headers, cookies, e-mail bodies, or keys. The app logs method, path (no query), status, time, user id, IP.
5. Do not render Markdown or admin-written HTML with `dangerouslySetInnerHTML` unless it passes a sanitiser (DOMPurify). Prefer a Markdown renderer with HTML disabled.
6. Do not turn on third-party analytics, chat widgets or tag managers on your own. They break the privacy promise and the CSP. **One exception, owner-controlled:** the GA4, Meta pixel and Google Ads ids in Admin → Integrations → Tracking tags. Off by default, owner only, loaded only after the visitor allows optional tools, never on admin, sign-in or checkout pages (`16` §6.3). When the owner turns them on, add the CSP sources the screen lists and update the Privacy page.
7. Do not return `password_hash`, `totp`, `recovery_codes`, session ids/tokens, `provider_keys` or `stripe_*` secrets from any route. Tests check the user detail and export.
8. Do not catch and hide errors in the middleware to "make tests pass". Crashes must reach `app_logs`.
9. Do not store card numbers, CVC or bank details anywhere. There is no field for them.
10. Do not weaken a limit to make a demo easier. Change a setting in Admin instead, and put it back.
11. Do not add routes that skip `deps.require_perm` under `/api/admin`. Add a test that signs in as `analyst` and expects 403.
12. Do not use `eval`, `pickle`, `yaml.load`, shell commands built from input, or `$where` in Mongo queries. Build every query from typed values. Escape user text before using it in a regex (`re.escape`, as in `admin_queries.list_users`).

## 4. The front end's side
- Serve over HTTPS only. Redirect HTTP to HTTPS at the host. HSTS comes from the API; add the same header on the app host.
- Content-Security-Policy for the app host (a starting point; adjust for the build):
  `default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: https:; font-src 'self'; connect-src 'self'; frame-src https://checkout.stripe.com; frame-ancestors 'none'; base-uri 'self'; form-action 'self' https://checkout.stripe.com`
  Checkout and the portal are full-page redirects, so no Stripe script is loaded on our pages. Do not load Stripe.js unless you add embedded elements later.
- Self-host fonts and icons (the Site Studio fonts are `@fontsource-variable` files in `/public/fonts/`). No third-party scripts, except the owner-enabled tracking tags above (add their CSP sources only then).
- Forms: `autocomplete` values, no password in query strings, `type=password`, paste allowed (password managers).
- Escape everything shown from the API. React does this by default; keep it that way.
- `rel="noopener noreferrer"` on external links.

**Images (doc 19).** Club, league and player pictures are served from our own address, so the public app can use `img-src 'self' data:`; keep `https:` only while `images.use_provider_urls` is on. The admin pages alone also allow `https://media.api-sports.io` for the review cards. The image sync downloads only from `media.api-sports.io`, builds the address itself from a number (never from text it was given), refuses redirects, accepts only PNG, JPEG and WebP by their first bytes, refuses SVG, and caps the size (`images.max_bytes`). The API-Football key is a stored provider key like the others.

## 5. Secrets and environment
| Secret | Where | Rotate |
|---|---|---|
| `APP_ENCRYPTION_KEY` (32 bytes, base64) | Emergent secret | Rotating it makes every stored provider key unreadable. Re-enter all five keys in Admin after a rotation. Keep a copy in your password manager. |
| `ADMIN_INITIAL_PASSWORD` | Emergent secret, first start only | Remove after first sign-in (the owner is forced to change it) |
| `CRON_SHARED_SECRET` | Emergent secret + the pinger | Change both together |
| Provider keys | Admin > Keys (encrypted in MongoDB) | When staff leave, or on any doubt |
| `JWT_SECRET` | Not used by the new code. Remove it from the template. | n/a |
Never commit `.env` files. Never paste a key in chat, e-mail or a ticket.

## 6. Privacy
- **What we hold about a person:** e-mail, optional name, time zone, theme, notification choices, follows/saved/notes, plan and payment records, sign-in history (IP, device, time) for 90 days, e-mails sent (template, status, time), anonymous usage events (no IP, daily-rotating hash for signed-out visitors).
- **Who else sees it (sub-processors):** the host (Emergent) and MongoDB, Stripe (payments), Resend (e-mail), PitchAPI (we send no personal data). Name them on the Privacy page.
- **Rights:** export (Account > Privacy), delete (Account > Privacy; staff can also purge from Admin), correct (Account > Profile), unsubscribe (every non-essential e-mail). Payment records stay for tax law, unlinked from the name.
- **Staff access:** need-to-know by role, masked by default, every action audited.
- **Children:** the app is for adults 18+ (state it in the Terms). Do not collect date of birth.
- **Law:** Canadian PIPEDA and CASL apply to Moh in Ontario; Quebec, GDPR (EU/UK) and US state laws may apply depending on who signs up. The privacy and terms pages need a lawyer's eye. Ask whether gambling-adjacent content has extra rules where you advertise. Our wording stays analysis-only (doc 03).
- **Breach plan:** see §8.

## 7. Deployment checklist (do before launch)
1. HTTPS on, HTTP redirects. `COOKIE_SECURE=1`. `ENV=production` (hides `/docs` and the OpenAPI file).
2. `PUBLIC_BASE_URL` set to the real https address.
3. `security.trusted_proxy_count` matches the hosting (Emergent: 1 — verify by calling `/api/auth/me` with a fake `X-Forwarded-For` and checking the rate-limit key in `rate_limits`).
4. Owner account created, password changed, 2FA on, recovery codes stored offline. Remove `ADMIN_INITIAL_PASSWORD` from the secrets.
5. Staff accounts: one per person, each with 2FA. No shared logins.
6. `security.require_staff_2fa` on (default). `auth.require_email_verification` on (default).
7. Stripe: live mode only after a full test-mode pass and PitchAPI's written OK. Webhook endpoints created and a test event received (Admin > Logs > Webhooks shows `processed`).
8. Resend: domain verified, DMARC added, webhook working, test e-mails reach the inbox.
9. Backups: ask the host how MongoDB is backed up and how to restore. Do a restore drill once. Export `plans`, `settings`, `email_templates`, `content_pages` from Admin monthly.
10. Run all ten self-tests against a real MongoDB (doc 12 §K).
11. Dependency check: `pip audit` and `npm audit`; update pinned versions.
12. Ask a security person for a one-day review or a penetration test before taking payments.

## 8. If something goes wrong
| Event | Do this |
|---|---|
| Staff laptop lost or login suspected | Admin > Users > the person > Sign out everywhere; owner resets their 2FA; change their password |
| A key leaked | Revoke it at the provider first, create a new one, paste it in Admin > Keys, check Logs for use in the leak window |
| Many failed sign-ins | Security screen shows by hour. Raise lockout minutes; lower `security.rate_limit_auth_per_minute`; consider turning `auth.allow_signup` off for a while |
| Webhooks failing | Health shows a red alert. Logs > Webhooks shows the reason. Fix the mapping or secret. Stripe retries for up to 3 days; use "Resend" in the Stripe dashboard after the fix |
| Spam sign-ups | Turn on `auth.require_email_verification` (default on), lower `security.rate_limit_auth_per_minute`, add a CAPTCHA (not built, see §9) |
| Data breach (personal data exposed) | Contain, record what and who, tell the people affected and the Privacy Commissioner of Canada when there is a real risk of significant harm (PIPEDA), keep a breach record for 24 months. Ask a lawyer the same day. |
| Owner locked out | `python reset_admin.py` from the backend shell (uses `ADMIN_EMAIL` and `ADMIN_INITIAL_PASSWORD`; it also turns 2FA off and signs out all owner sessions, so enrol again) |

## 9. Known limits (be honest with yourself)
- **No CAPTCHA or bot challenge** on sign-up. The rate limits, verification e-mail and per-IP caps are the defence. Add Cloudflare Turnstile if spam appears.
- **No web application firewall.** Put the app behind the host's or Cloudflare's if available.
- **Body-size check uses the `Content-Length` header.** A chunked upload without it is not capped by our code. The host proxy usually caps it too; confirm. The image upload route (`POST /api/admin/site/assets`) accepts up to 900 KB; every other route keeps `security.max_body_kb`.
- **Webhook targets.** Staff-entered webhook addresses are checked (public https only, private and metadata addresses refused, checked again at send time, no redirects). A DNS name that flips to a private address between the check and the send is a narrow residual risk. Prefer hosting with no route to private networks.
- **Custom CSS** is owner-only and filtered, but CSS can still make a page look wrong. Rollback is one click.
- **Uploaded images** are checked by content (not name), SVG is refused, and they are served with `nosniff` and `sandbox`.
- **Popups and site text** are rendered as text. The front end must never use `dangerouslySetInnerHTML` for them.
- **Fixed-window rate limits** allow up to twice the limit across a window edge. Fine for abuse control, not for hard quotas (those use `plans.consume`).
- **Tests use `mongomock`**, not a real MongoDB. TTL indexes, unique-index races and some aggregation behaviour differ. Run them against a real database once.
- **TOTP seeds are encrypted with one app key.** Someone with both the database and `APP_ENCRYPTION_KEY` can read them. Keep the key out of the database host.
- **A password reset by e-mail does not ask for the 2FA code.** It signs out every device, and the next sign-in still asks for the code, so someone who only controls the mailbox cannot get in. But whoever controls the mailbox can lock the real person out. Protect the e-mail account with 2FA too.
- **No device or location risk scoring**, no breached-password check. Possible later (haveibeenpwned k-anonymity).
- **No SSO or passkeys.** Possible later.
- Not independently audited. Treat this as a solid baseline, not a certificate.
