# 14. Billing (Stripe) and e-mail (Resend)

Code: `plans.py`, `stripe_billing.py`, `emailer.py`, `routes_billing.py`. Tested with mock HTTP (no live account was used). Read §7 for what is unverified.

## 1. Rules first
1. **Billing is OFF by default** (`features.billing` = false). While off, every signed-in person gets the top plan, checkout answers `BILLING_OFF`, and nothing is charged. Turn it on only after: PitchAPI's written OK for paid use (guide check B1), a Terms page, a Privacy page, a refund policy page, and a full run in Stripe **test mode**.
2. **No card data ever touches our server.** Checkout and the billing portal are Stripe-hosted pages. We keep Stripe ids, status, amounts and invoice links.
3. **Stripe is the source of truth for money.** Our `subscriptions` and `payments` collections follow Stripe's webhooks. If they disagree, Stripe wins.
4. **Keys:** the Stripe key prefix must match `billing.mode` (test or live). Mismatch = the app refuses to call Stripe.
5. **Marketing e-mail is opt-in only** (default off) and sends only when the postal address and unsubscribe link are in place. See §5 on Canada's anti-spam law.

## 2. Moh's Stripe set-up (about 30 minutes)
1. Create a Stripe account. Stay in **Test mode** (toggle top right).
2. Developers → API keys → copy the **Secret key** (`sk_test_…`). Better: create a **Restricted key** with write access to Customers, Checkout Sessions, Billing Portal, Subscriptions, Products, Prices, Coupons, Promotion Codes, Refunds, and read access to Balance, Invoices, Charges. (`rk_test_…` is accepted.)
3. Settings → Billing → **Customer portal**: turn on update payment method, view invoices, cancel subscription (at end of period). Save. The portal button fails until this is saved.
4. Developers → Webhooks → Add endpoint: URL `https://YOUR-DOMAIN/api/webhooks/stripe`. Events (exactly these): `checkout.session.completed`, `customer.subscription.created`, `customer.subscription.updated`, `customer.subscription.deleted`, `customer.subscription.trial_will_end`, `invoice.paid`, `invoice.payment_failed`, `charge.refunded`. Copy the **Signing secret** (`whsec_…`).
5. In Admin → Keys paste the secret key and the webhook secret.
6. Admin → Plans → set names, prices, limits → **Sync to Stripe** (creates the product and prices; no need to make them in Stripe by hand).
7. Admin → Settings → Billing: set `billing.mode` = test, success/cancel/portal return paths (defaults are fine), trial days, past-due grace days. Turn on `features.billing`.
8. Test with card `4242 4242 4242 4242`, any future date, any CVC. Failed payment: `4000 0000 0000 0341` (attaches, then fails on renewal). Run the checklist in doc 12 §I.
9. Going live: Stripe account activated → live keys → set `billing.mode` = live (owner) → save the live key → create the live webhook endpoint → new `whsec_` → Sync plans again (live mode has its own products) → one real purchase and refund of your own.
10. Optional: Stripe Tax (`billing.automatic_tax`), receipts from Stripe (we also send ours), Radar defaults on.

## 3. How it works

### Data
- `plans`: key, name, tagline, bullets, `entitlements`, `prices[]` (id, interval, amount_cents, currency, active, `stripe_price_id`), `stripe_product_id`, `trial_days`, `visible`, `archived`, `is_default`.
- `subscriptions` (`_id` = Stripe subscription id): user_id, status, plan_key, price_key, amounts, period start/end, cancel_at_period_end, trial_end, `past_due_since`, `last_event_at`.
- `payments` (`_id` = Stripe invoice id): user_id, status (paid, failed, partially_refunded, refunded), amount_paid, refunded_cents, invoice_url, payment_intent/charge, period_end.
- `webhook_events` (`_id` = `stripe:<event id>` or `resend:<svix id>`): status processing / processed / error, attempts, error text. TTL 90 days.
- `coupons`: our mirror of promotion codes.

### What plan does a person have? (`plans.effective_plan`)
1. Billing off → top plan.
2. Comp (admin gift) not yet ended → that plan.
3. Live subscription: `active`, `trialing`, or `past_due` within `billing.past_due_grace_days` (7). An `active` one whose period ended more than 2 days ago (missed webhook) does not count.
4. Else the free plan.
Prices: yearly counts as amount ÷ 12 in MRR. Trials count as 0 MRR.

### Buying
`POST /api/billing/checkout {plan, price}` → checks billing is on, e-mail verified, not already subscribed → makes/reuses the Stripe customer (`metadata.user_id`) → creates a Checkout Session in subscription mode with our user id on the session and the subscription, success URL with `{CHECKOUT_SESSION_ID}`, trial days if the person never had one, promotion codes allowed → returns `{url}`. A double click makes one session (idempotency key per user, plan, price, minute).
The person returns to the success page. **The success page must not grant access.** It shows "Confirming your payment…" and polls `GET /api/account/billing` until `plan.source` is `subscription` (the webhook usually lands in seconds). After 30 s with no change say: "Your payment is received. Access can take a minute to switch on."

### Changing and cancelling
Everything goes through Stripe's portal (`POST /api/billing/portal`). Plan switches made there flow back by `customer.subscription.updated`. Admin can also cancel (period end or now) and resume.

### Failed payments
`invoice.payment_failed` → payment row "failed", `past_due_since` set, e-mail "We could not take your payment" with a link to billing. Access continues for the grace days. Stripe's retry schedule (Smart Retries, set in the Stripe dashboard) and the final cancel come by webhook. `invoice.paid` clears the clock.

### Refunds
Admin → Payments → Refund (amount + reason). Idempotency key = payment + amount + already-refunded. Status updates on `charge.refunded`. Live-mode refunds: owner only.

### Webhook safety (`stripe_billing.verify_webhook`, `handle_event`)
- Signature: header `t=…,v1=…`; HMAC-SHA256 of `t.payload` with the signing secret; constant-time compare; 5-minute tolerance. Bad signature → 400, nothing parsed.
- Event id is stored; a repeat returns `duplicate` and does nothing. A failed event is stored as `error` and retried by Stripe.
- Older events are ignored (`last_event_at`). A late "paid" does not undo a refund we already saw.
- An event we cannot apply (price not in any plan, no matching person) returns 500 so Stripe retries and the admin sees a red alert. Fix the plan mapping (sync) and the next retry succeeds.
- The route reads the raw body. Do not put a JSON-parsing layer in front of it.

## 4. E-mail with Resend

### Other e-mail providers
Resend is the default and the only one with automatic bounce handling. Admin → Integrations can switch to Postmark, SendGrid, Brevo or any SMTP server (`16` §5). Their request shapes are written from public docs and **have not been run against live accounts**. With them, bounces and complaints are **not** processed automatically: add bad addresses in Blocked addresses by hand or use the provider's dashboard. The same e-mail is never sent twice (our own check on `email_log.idem`).

### Set-up for Moh
1. Create a Resend account. Add your sending domain (use a subdomain like `mail.yourdomain.com`). Add the DNS records Resend shows (SPF, DKIM, and the return path). Wait for "Verified". Add a DMARC record (`v=DMARC1; p=none; rua=mailto:you@yourdomain.com`) and tighten later.
2. API Keys → create a key with **Sending access** for your domain (`re_…`). Paste in Admin → Keys.
3. Webhooks → add `https://YOUR-DOMAIN/api/webhooks/resend`. Events: `email.delivered`, `email.bounced`, `email.complained`, `email.delivery_delayed`. Copy the signing secret (`whsec_…`) into Admin → Keys. Leave open and click tracking OFF (we do not track opens).
4. Admin → Settings → E-mail: `email.from_address` (on the verified domain), `email.from_name`, `email.reply_to`, then turn on `email.enabled`.
5. Admin → E-mail → Templates → **Send test to me** on `verify_email` and `password_reset`. Check the inbox AND the spam folder.
6. Plan limits: Resend's free tier has a daily and monthly cap (check the current numbers on their pricing page). Set `email.daily_send_cap` at or below the daily cap. Security and receipt e-mails are never held back by our cap, but Resend itself will refuse past its own limit.

### The 15 system e-mails
| Key | Category | Sent when | Variables |
|---|---|---|---|
| `verify_email` | transactional | sign-up, resend, admin resend | name, link, hours |
| `password_reset` | transactional | forgot-password, admin "send reset" | name, link, minutes |
| `password_changed` | transactional | password changed or reset | name |
| `email_change_confirm` | transactional | to the NEW address | name, link, new_email |
| `email_changed` | transactional | to the OLD address after the change | name, new_email |
| `staff_invite` | transactional | owner invites staff | link, role |
| `welcome` | product | after e-mail is verified | name, link |
| `receipt` | transactional | `invoice.paid` with an amount | name, amount, plan, period_end, invoice_url |
| `payment_failed` | transactional | `invoice.payment_failed` | name, plan, link, days |
| `trial_ending` | transactional | `customer.subscription.trial_will_end` | name, plan, date, link |
| `subscription_canceled` | transactional | `customer.subscription.deleted` | name, plan |
| `account_deleted` | transactional | after deletion, to the old address | name |
| `admin_alert` | transactional | an alert opens (staff who have alerts on) | text, link |
| `team_digest` | product | Monday weekly summary (staff who opted in) | summary, link |
| `newsletter_confirm` | transactional | someone joins the e-mail list (double opt-in) | link |
Common variables on every template: `brand`, `support`, `name`. `{{button}}` inserts the button style. Variables are HTML-escaped. The footer always carries the standard disclaimer.

### Rules in code (`emailer.py`)
- A send never raises into the page. The result is logged with a status: `sent`, `failed`, `skipped_disabled`, `skipped_unconfigured`, `skipped_suppressed`, `skipped_optout`, `skipped_cap`. Webhooks then move `sent` to `delivered`, `delayed`, `bounced`, `complained`.
- **No bodies in the log.** Reset and verify e-mails carry secret links.
- **Suppression:** a hard bounce or complaint blocks ALL mail to that address. An unsubscribe blocks only non-essential mail (security and receipts still go).
- **Categories:** transactional ignores opt-outs and the daily cap; product respects `prefs.product_emails`; marketing needs `prefs.marketing_emails` = true.
- Non-transactional mail carries `List-Unsubscribe` and `List-Unsubscribe-Post: List-Unsubscribe=One-Click` plus a visible footer link and the postal address.
- Retries: 429 and 5xx up to 3 tries with the same idempotency key (Resend remembers keys for 24 hours). A rejected address (422) is logged as failed, not retried.
- Soft bounces ("transient") do not suppress.
- No auto-reply to the contact form (strangers could use it to make us e-mail anyone).

### Campaigns
Admin → E-mail → Campaigns. Needs `email.enabled`, `email.marketing_enabled`, `email.footer_address`. Recipients: verified, not disabled, marketing opt-in on, not suppressed; segment all / free / paid. Idempotency key per campaign and person; running it again never double-sends. Stops at the daily cap; the result says how many are left.

### Canada (CASL) and privacy, plain version
Moh is in Ontario. Canada's anti-spam law needs consent before marketing e-mail, your identity and postal address in the message, and a working unsubscribe honoured within 10 business days. The design above does that: opt-in default off, address in the footer, one-click unsubscribe applied at once. Transactional mail (receipts, security) is allowed without opt-in. This is a design note, not legal advice. Ask a lawyer before the first campaign, and before taking payments in other countries (tax, consumer rules).

## 5. Environment variables (all optional when the key is saved in Admin)
`STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET`, `RESEND_API_KEY`, `RESEND_WEBHOOK_SECRET`, and for the other providers `POSTMARK_SERVER_TOKEN`, `SENDGRID_API_KEY`, `BREVO_API_KEY`, `SMTP_PASSWORD`, and for list sync `MAILCHIMP_API_KEY`, `MAILERLITE_API_KEY` (Brevo reuses `BREVO_API_KEY`) — development fallbacks only; the admin-saved key wins. `PUBLIC_BASE_URL` (required for links in e-mails and Stripe return URLs, e.g. `https://app.example.com`, no trailing slash).

## 6. Money display
Store cents and a currency code. Format with `Intl.NumberFormat`. Show tax-inclusive wording only if Stripe Tax is on. Never add amounts in different currencies. Show prices with the interval ("CA$12.99 / month"). Yearly shows the monthly equivalent in small text.

## 7. Not verified against a live account (test these in Stripe test mode first)
1. Newer API versions moved `current_period_end` to the subscription item and the invoice's subscription id under `parent.subscription_details`. We read both places. Confirm with a real test event, and pin a version in `billing.stripe_api_version` once it works.
2. Promotion-code creation changed shape in newer versions (`promotion[type]=coupon`). We try the new form, then the old.
3. Newest invoices may not carry `payment_intent`. If so, refunds from the panel say "refund it in the Stripe dashboard".
4. Resend's bounce payload shape (`data.bounce.type`) and restricted-key behaviour on `GET /domains` were taken from public docs, not tested.
5. The billing portal needs its settings saved in the Stripe dashboard first.
6. No automatic "reconcile with Stripe" job exists. If webhooks were down for days, use the Stripe dashboard "resend event" button, or add a nightly job that lists recent events. Listed in doc 00 as a known gap.
7. Taxes, invoices in other currencies, and proration rules for plan switches are Stripe settings we have not tuned.
8. Postmark, SendGrid, Brevo and SMTP sending, and Mailchimp, Brevo and MailerLite list sync, were written from public docs and tested with mock servers only (`16` §11).
