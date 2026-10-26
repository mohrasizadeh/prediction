# 16. Site Studio, Popup Maker, e-mail tools and integrations

This adds the "control everything without code" layer to the admin: look and feel, menus, popups, e-mail list, e-mail providers, list sync, webhooks, tracking tags, extra analytics and alerts. All of it has tested reference code (see `backend/MODULES.md`). The screens are for the builder to make. The responsive shell is in `17_admin_responsive_ui.md`. A clickable prototype is in `prototype/admin_prototype.html`.

Rules in `03` and `15` still win. Nothing here touches betting words, odds or promotion. Every text field below is checked server-side for the banned words (`textguard.py`). The only exception is the exact disclaimer sentence.

## 1. What each tool is

| Tool | Admin module | Who may open it | Code | Test |
|---|---|---|---|---|
| Site Studio (colours, fonts, buttons, menus, footer, SEO, cookie banner, home blocks, logo) | Site Studio | admin, owner (`site.read`); publish needs `site.publish` | `site_studio.py`, `routes_site.py` | `selftest_studio.py` |
| Custom CSS | inside Site Studio | owner only (`site.custom_css`) | same | same |
| Popup Maker | Popups | read: admin, owner, analyst; change: admin, owner | `popups.py` | `selftest_growth.py` |
| E-mail list | E-mail list | read: admin, owner, support, analyst; export needs `users.pii` | `newsletter.py` | same |
| E-mail provider switch | Integrations | admin, owner | `transports.py` | same |
| List sync (Mailchimp, Brevo, MailerLite) | Integrations | admin, owner | `integrations.py` | same |
| Webhooks | Integrations | admin, owner | same | same |
| Tracking tags (GA4, Meta, Google Ads) | Integrations | **owner only** (`tracking.write`) | same | same |
| Extra analytics (realtime, compare, sources, e-mail health, CSV) | Analytics | `analytics.read` (e-mail health needs `email.read`) | `reports.py` | same |
| Alerts and weekly summary | Health, Settings | see §8 | `alerts.py` | same |
| Mobile menu | the admin shell | everyone with admin access | `admin_shell.py` | `selftest_studio.py` |

Support gets none of Site Studio, Popups, Integrations or analytics. The server checks every route. Hiding a menu item is only a convenience.

## 2. Site Studio

### 2.1 How editing works

One site configuration, stored in versions.

1. Staff edit a **draft**. Visitors do not see it.
2. Every save is checked on the server. A bad value answers `422 SITE_INVALID` with `problems: [{path, message}]`. Show each message beside its field.
3. **Preview**: `POST /api/admin/site/preview-token` returns a link good for 30 minutes. The public app reads `GET /api/site/config?preview=<token>` and shows the draft (`preview: true`, never cached, `X-Robots-Tag: noindex`).
4. **Publish** (`POST /api/admin/site/publish {note, force?}`) makes the draft live as the next version. Nothing to publish answers 422. If someone else published after this draft started, it answers `409 PUBLISH_CONFLICT`; show "Someone published a newer version. Review, then override" and send `force: true` only after the person confirms.
5. **Rollback** (`POST /api/admin/site/rollback/{v}`) publishes an old version again as a new version. History is never rewritten. The last 50 versions are kept.
6. **Discard** drops the draft. **Reset a section** sets one section back to `live` or `default`.
7. Everything is in the audit log.

Screen layout: left a form (tabs for each section), right a live preview with a Dark/Light switch and a Desktop/Phone switch. A bar at the top shows "Unsaved draft" or "Live: version N", with **Preview link** and **Publish** buttons. On phones the form is first and the preview below it. See the prototype.

### 2.2 Sections and fields

`PUT /api/admin/site/draft/{section}` with `{data: {...}}`. Unknown fields are refused, so a typo never silently does nothing. Sections: `brand`, `theme`, `buttons`, `nav`, `footer`, `seo`, `cookies`, `home`, `custom_css`.

| Section | Fields | Rules |
|---|---|---|
| `brand` | `name`, `tagline`, `logo_light`, `logo_dark`, `favicon`, `og_image` | Name 1 to 30 characters. Images are an uploaded image path (`/api/site/assets/<id>`) or an `https://` address. No `javascript:` or `data:`. |
| `theme` | `default_mode` (`system`, `light`, `dark`), `allow_toggle`, `colors.dark.*`, `colors.light.*` (23 tokens each), `font_body`, `font_heading`, `base_px` (14 to 18), `heading_weight` (500 to 800), `radius` (`sharp`, `default`, `round`), `density` (`comfortable`, `compact`), `shadows` (`none`, `soft`, `strong`), `motion` (`full`, `reduced`), `max_width_px` (960 to 1600) | Colours are `#RRGGBB`. Every token is required. Fonts come from the list in §2.4. **Text pairs under 4.5:1 block Publish** (text on page, text on cards, soft text, button text on brand, text on the red "down" colour). Icons and large marks use 3:1 and only warn. |
| `buttons` | `radius_px`, `height_px.{sm,md,lg}` (each 28 to 64, growing), `font_weight`, `uppercase`, `shadow` (`none`, `soft`), `hover` (`lift`, `darken`, `none`), `press`, `focus_ring_px` (2 to 5), `variants.{primary,secondary,ghost,danger}` | Style is `solid`, `outline`, `soft` or `ghost`. The main button cannot be `ghost`. The normal height is at least 40 px. The focus ring cannot be turned off. On touch screens every button is at least 44 px tall, whatever is set. |
| `nav` | `items[]` (`id`, `label`, `icon`, `route`, `enabled`, `audience`, `badge`), `mobile_tabs[]` | Ids are unique. Route is `/path` or `https://…`; no `javascript:`, no `//host`. Icon is from the list (35 icons). Audience is `all`, `signed_out`, `signed_in`, `free`, `paid`. `mobile_tabs` are at most 4 ids of enabled items (the 5th slot on phones is always **More**). |
| `footer` | `columns[]` (`title`, `links[]`), `social[]` (`kind`, `url`), `legal_line`, `show_data_credit` | Social links are `https`. Missing Terms or Privacy link is a warning, not an error. The disclaimer sentence is always shown (not editable here; it is `copy.disclaimer`). |
| `seo` | `title_template`, `description_template`, `og_image`, `robots_index`, `sitemap`, `redirects[]` (`from`, `to`, `code` 301 or 302) | Placeholders allowed: `{name}`, `{team1}`, `{team2}`, `{page}`, `{player}`, `{league}`. Up to 200 redirects. Redirects cannot loop and cannot start from `/admin` or `/api`. |
| `cookies` | `banner`, `text`, `accept_label`, `reject_label`, `policy_route` | The banner must have a "no" button. |
| `home` | `blocks[]` (`id`, `enabled`), order = array order | Ids: `today_fixtures`, `top_insights`, `finder_shortcut`, `track_record`, `following`, `learn`, `newsletter`. At least one enabled. |
| `custom_css` | `css` | Owner only. See §2.5. |

`GET /api/admin/site/draft` returns `{draft, live_v, dirty, updated_by, meta}`. `meta` holds the lists the form needs (fonts, icons, presets, colour tokens, audiences, home blocks).

### 2.3 Presets

`POST /api/admin/site/draft/preset {key}` sets colours, radius, default mode and button shape in the draft. Keys: `midnight` (default), `daylight`, `pitch`, `sunset`, `ocean`, `contrast`. All six pass the readability rules (tested). Show them as chips above the colour pickers.

### 2.4 Fonts

Self-hosted only. No Google Fonts, no third-party request. This keeps the Content-Security-Policy at `font-src 'self'`.

Install once, in the front end:

```
npm i @fontsource-variable/inter @fontsource-variable/manrope @fontsource-variable/dm-sans @fontsource-variable/plus-jakarta-sans \
      @fontsource-variable/nunito @fontsource-variable/work-sans @fontsource-variable/source-sans-3 @fontsource-variable/open-sans \
      @fontsource-variable/roboto @fontsource-variable/space-grotesk @fontsource-variable/outfit @fontsource-variable/merriweather \
      @fontsource-variable/playfair-display @fontsource-variable/lora
```

Copy each package's `files/<name>-latin-wght-normal.woff2` into `public/fonts/` (the names are in `site_studio.FONTS[slug]["file"]`). "System default" needs no file. The public config lists only the fonts in use, each as `{slug, family, url: "/fonts/<file>"}`; write `@font-face` rules from that list (`font-display: swap`).

### 2.5 Custom CSS (owner only)

For people who know CSS. Saved into `@layer custom{…}`, so it can adjust but cannot break the base rules. Blocked: `@import`, `@font-face`, any `url()` that is not a local `/api/site/assets/…` path, `expression(`, `javascript:`, `<` or `>`, unbalanced braces, over 20 KB. Banned words are blocked as everywhere. Admins see the tab locked.

### 2.6 Images

`POST /api/admin/site/assets {name, data_b64}` (send as JSON; the body limit for this one route is 900 KB, others stay small). PNG, JPEG, GIF, WebP, ICO only, up to 512 KB, **checked by file content, not by name**. SVG is refused (it can carry script). Served from `GET /api/site/assets/<id>` with the right type, `nosniff`, `Content-Security-Policy: sandbox`, one year cache. An image in use (draft or live) cannot be deleted (`409`). Stored in MongoDB.

### 2.7 What the public app does with the config

`GET /api/site/config` (no sign-in, ETag, `Cache-Control: public, max-age=30`). The front end:

1. Fetches it before first paint; answers `304` when unchanged. Caches it in memory, revalidates every 60 s and on focus.
2. Injects `theme.css` into a `<style id="site-theme">` element. It already holds both modes: `:root{…dark…}` and `[data-theme="light"]{…}`.
3. Sets `document.documentElement.dataset.theme` to `light` or `dark`: from the person's saved choice, else `default_mode`, else the system setting (`prefers-color-scheme`). If `allow_toggle` is false, hide the toggle.
4. Writes `@font-face` from `theme.fonts`.
5. Draws menus from `nav` (desktop top or side bar; phone bottom bar from `mobile_tabs`, then **More** with the rest). Hide items whose `audience` does not match the person.
6. Draws the footer, the cookie banner and the home blocks from their sections. Always draw `disclaimer`.
7. Applies `redirects` in the router (client side), and the same list at the server for crawlers.
8. Uses `seo.title_template` for page titles.
9. If `maintenance.on`, shows the maintenance page.
10. Never trusts the CSS string for anything except a `<style>` element's text.

Buttons: the CSS defines `.btn`, `.btn--primary`, `.btn--secondary`, `.btn--ghost`, `.btn--danger` and sizes `.btn--sm`, `.btn--md`, `.btn--lg`. Use those class names everywhere, so the Studio changes every button at once.

## 3. Popup Maker

A popup is a small message: a centred modal, a corner slide-in, or a top or bottom banner. Staff build it in a form with a live preview (see the prototype).

### 3.1 Fields

`POST /api/admin/popups {data}` or `{template: "<id>"}` (starter templates: `newsletter_modal`, `newsletter_slide`, `upgrade_banner`, `announcement_bar`, `feature_slide_in`; the list is in `GET /api/admin/popups/meta`). `GET /api/admin/popups/meta` also returns a `blank` object with every field and default.

| Group | Fields | Rules |
|---|---|---|
| Basics | `name` (staff only), `status` (`draft`, `live`, `paused`), `kind` (`modal`, `slide_in`, `banner_top`, `banner_bottom`), `priority` 0 to 100 | At most 60 popups. |
| Content | `title` (80), `body` (400, plain text), `image` + `image_alt`, `buttons[]` (max 2: `label`, `action` link or close, `route`, `style`) | **No HTML.** A picture needs alt text. Banned words refused. |
| Form | `enabled`, `placeholder`, `button_label`, `consent_text`, `success_text` | If on, the consent sentence (20 to 240 characters) is required. The form sends people to the e-mail list (§4). |
| Look | `design.size`, `align`, `tone`, `position`, `show_close`, `backdrop_close` | A modal or slide-in must have a close button or a close action. |
| When | `trigger.type` (`immediate`, `delay`, `scroll`, `exit_intent`, `pageviews`, `click`), `delay_s`, `scroll_pct`, `pageviews` | Warnings (not errors) for a modal that opens at once, under 3 seconds, or exit intent (never shows on phones). |
| Who | `targeting.pages_include`, `pages_exclude` (patterns like `/teams/*`), `audience` (`all`, `signed_out`, `signed_in`, `free`, `paid`, `trial`), `devices`, `visitors` (`all`, `new`, `returning`) | |
| How often | `frequency.mode` (`once`, `every_n_days`, `every_session`, `until_action`), `n_days`, `after_action_days` | |
| Dates | `schedule.starts_at`, `ends_at` | End after start. States shown: draft, scheduled, running, paused, ended. |
| A/B | `ab.group`, `ab.weight` | Popups sharing a group name compete. Each visitor sees one, picked by weight and stable for that visitor. |

`POST /api/admin/popups/{id}/status {status}` sets live, paused or draft (going live re-checks everything). Also: duplicate, delete, per-popup stats (`GET …/stats?days=30` → totals and a daily series), A/B report (`GET /api/admin/popups-ab/{group}`).

### 3.2 The split of work (important)

**The server decides who may see it.** `GET /api/popups?path=&device=desktop|mobile&visitor=new|returning&vid=` returns at most 3 popups that are live, inside their dates, match the page, audience, device and new/returning, and won the A/B draw. It also returns `limits: {max_per_session, min_gap_seconds}`. It never returns the targeting rules, the name or the A/B weights. It returns nothing on admin, sign-in, sign-up, reset, verify, checkout, billing, confirm and maintenance pages, nor when `popups.enabled` is off.

**The browser decides when.** For each returned popup the front end applies:

```
if (shownThisSession >= limits.max_per_session) skip
if (now - lastShownAt < limits.min_gap_seconds) skip
if (frequency says "not yet") skip      // remembered in localStorage per popup id
wait for the trigger (timer, scroll %, mouse leaves the window, Nth page view, or a click on [data-popup="<id>"])
show it. Trap focus inside a modal, close on Esc, return focus when closed, respect prefers-reduced-motion.
POST /api/popups/<id>/event {event: "view"}   // then "click", "dismiss", "submit"
```

`vid` is a random id made by the front end and kept in localStorage. It is not tied to a person. It makes the A/B pick stable. If storage is blocked, use a new id each page; nothing breaks.

Exit intent only runs when the device is `desktop`. On phones use delay or scroll.

Staff preview: `GET /api/popups?path=/&preview=<token>&popup=<id>` returns that one popup (even a draft) with no targeting.

### 3.3 Form submit

`POST /api/popups/<id>/submit {email, consent}`. The person must tick the box. The popup's own consent sentence is saved with the sign-up. Same generic answer for everyone (§4). Rate limits: 10 per hour per address of the browser, 3 per hour per e-mail.

## 4. E-mail list (newsletter)

Built to Canada's CASL rules and good practice anywhere.

- **Express consent**: a tick box next to the exact sentence (`newsletter.consent_text` for the footer, the popup's own sentence for a popup). We save the sentence, the time, the source and a hashed network address.
- **Double opt-in** by default (`newsletter.double_optin`): the person is "pending" until they press **Confirm** on the page the e-mail links to.
- The confirm link opens a page that calls `GET /api/newsletter/confirm?token=` (it only shows a masked e-mail, **it changes nothing**, because mail scanners open links). The page's button calls `POST /api/newsletter/confirm {token}`.
- **One generic answer** for new, existing and blocked addresses, so nobody can probe the list.
- **Unsubscribe**: one click, from every marketing e-mail (`GET` shows a masked address, `POST /api/email/unsubscribe?t=` does it). Synced to the list provider.
- Bounced and complained addresses are never added.
- Admin: counts, list (consent text and hashed address are hidden), remove (also blocks it), export (CSV, `users.pii`, audited).

Public routes: `POST /api/newsletter/subscribe {email, consent}` (footer form), the two confirm routes above.

## 5. E-mail providers

Choose in Admin → Integrations → E-mail sending (`PUT /api/admin/integrations/email`). The key goes in Admin → Keys (encrypted), never in the browser. All providers receive the same neutral message; the app never needs to know which is active.

| Provider | Key name in Keys | Format | Bounces and complaints | Status |
|---|---|---|---|---|
| Resend (default) | `resend` | `re_…` | **Automatic** through the webhook | Request shape checked against docs; not run on a live account |
| Postmark | `postmark` | Server API token | By hand (Blocked addresses screen) | Written from public docs, **not run live** |
| SendGrid | `sendgrid` | `SG.…` | By hand | same |
| Brevo | `brevo` | `xkeysib-…` | By hand | same |
| SMTP server | `smtp_password` + host, port, user, security (`starttls` or `ssl`) | | By hand | Tested with a fake server only. Plain, unencrypted SMTP is refused. |

Test: `POST /api/admin/integrations/email/test-send` sends only to a team member's address. The same e-mail is never sent twice (we keep our own "already sent" check, so it works for every provider).

## 6. Integrations

### 6.1 List sync

Confirmed sign-ups are copied to **Mailchimp**, **Brevo** or **MailerLite**; unsubscribes are copied too. Choose a provider and a list id (`PUT /api/admin/integrations/audience`), save its key in Keys, press **Test**. Work is queued and done by the tick (§7): 6 tries with waits of 1 min, 5 min, 30 min, 2 h and 12 h. A refused key or list stops that job at once and raises an alert. **Backfill** queues everyone already confirmed. Request shapes are from public docs and **not run on live accounts**.

### 6.2 Webhooks (signed events to any URL)

For Zapier, Make, n8n or a Slack relay. Events: `user.signed_up`, `user.verified`, `subscription.started`, `subscription.canceled`, `payment.succeeded`, `payment.failed`, `newsletter.subscribed`, `newsletter.unsubscribed`, `popup.submitted`, `contact.received`.

- Up to 10 endpoints. The address must be public `https` on port 443 or 8443, no user name or password. Private, loopback, link-local and cloud-metadata addresses are refused, both typed as numbers and by name, and **checked again at send time**. Redirects are not followed.
- The secret (`whsec_…`) is shown **once** at creation or rotation. It is encrypted in the database.
- E-mail addresses are **not** in events unless the endpoint is set to include them.
- Delivery: queued, sent by the tick, 6 tries with the waits above. `410 Gone` switches the endpoint off. 20 failures in a row switch it off and raise an alert. Every try is logged for 30 days.
- Test button sends a sample event now.

Receiver check (give this to whoever builds the receiving side):

```
header  X-Webhook-Signature: t=<unix seconds>,v1=<hex>
v1 = HMAC-SHA256(secret, "<t>." + raw_body)  // compare in constant time; reject if |now - t| > 5 minutes
```

Other headers: `X-Webhook-Id` (use it to ignore repeats), `X-Webhook-Event`.

### 6.3 Tracking tags (owner only, off by default)

GA4, Meta pixel and Google Ads ids (`PUT /api/admin/integrations/tracking`, owner only; the generic settings route refuses `tracking.*` for admins too). This is the **one exception** to "no third-party scripts" in `15`. Rules for the front end:

1. Do nothing unless `site config → tracking.enabled`.
2. If `require_consent` (default true), load nothing until the person pressed **Allow optional** in the cookie banner. Remember the choice. Let them change it from the footer.
3. Respect Do Not Track and Global Privacy Control: treat them as "no".
4. Never load tags on `/admin` or on sign-in, reset or checkout pages.
5. When the owner turns tags on, the response lists the extra **Content-Security-Policy sources** needed and reminds them to update the Privacy page. Add those sources to the CSP in the front-end host's headers (the app does not add them for you).

## 7. Analytics extras, alerts, weekly summary

All first-party. No tracking pixels, so there are **no open or click rates** (the e-mail report says so).

| Screen | Route | What |
|---|---|---|
| Realtime | `GET /api/admin/analytics/realtime` | People in the last 5 minutes, top pages, devices. No identities. |
| Compare | `GET …/compare?days=7` | This period against the one before, with % change. Revenue per currency, never added across currencies; hidden without `billing.read`. |
| Sources | `GET …/acquisition?days=30` | Visitors, sign-ups, paying people and rates by `utm_source / utm_medium / utm_campaign`; plain referrers grouped by site. Sign-ups use the **first** campaign tag the person arrived with. |
| E-mail health | `GET …/email?days=30` | Sent, delivered, bounced, complained, by template. Aim: bounces under 2%, complaints under 0.1%. |
| Popups | `GET …/popups` | Every popup side by side. |
| List growth | `GET …/newsletter?days=30` | Counts and joins by source. |
| CSV | `GET …/export?report=pages|referrers|acquisition|popups|signups|visitors&days=` | Audited. Cells that start with `=`, `+`, `-` or `@` get a leading apostrophe so a spreadsheet never runs them. |

The front end sends campaign tags with the page-view beacon (`utm` object: `source`, `medium`, `campaign`, read from the landing URL) and with sign-up (`acq`). The server cleans and length-limits them.

**Alerts** (`admin.alerts_enabled`): sign-ups fell by `admin.alert_signup_drop_pct` or more (needs at least 10 in the earlier week), server errors per hour over `admin.alert_errors_per_hour`, failed payments today over `admin.alert_failed_payments`, plus alerts raised by list sync or webhooks. One open alert per problem. It clears itself when the numbers recover. The team gets one e-mail per alert, and again only after `admin.alert_cooldown_hours` if still open. Owners and admins who did not switch off `prefs.admin_alerts` get them. Staff dismiss alerts in Health (`POST /api/admin/alerts/{id}/resolve`).

**Weekly summary** (`admin.digest_enabled`): Mondays, to staff who turned on `prefs.admin_digest` in their Account (off until they do).

**The tick** (`POST /api/jobs/tick`, header `X-CRON-SECRET`) now also copies list contacts, delivers webhooks (every call), runs alerts (every 15 minutes) and sends the digest. **Call it every 5 minutes**, so webhooks and list sync are never more than a few minutes late.

## 8. New permissions

| Permission | Owner | Admin | Support | Analyst |
|---|---|---|---|---|
| `site.read`, `site.write`, `site.publish` | yes | yes | no | no |
| `popups.read` | yes | yes | no | yes |
| `popups.write` | yes | yes | no | no |
| `integrations.read`, `integrations.write` | yes | yes | no | no |
| `site.custom_css` (owner only) | yes | no | no | no |
| `tracking.write` (owner only) | yes | no | no | no |

Existing permissions used by the new routes: `analytics.read`, `email.read`, `email.write`, `users.pii` (CSV of e-mail addresses), `logs.read` (see alerts), `settings.write` (resolve alerts, send digest), `jobs.run` (run alerts by hand).

## 9. New settings (156 at this point; 165 after doc 18)

`popups.enabled`, `popups.max_per_session`, `popups.min_gap_seconds`, `newsletter.double_optin`, `newsletter.consent_text`, `email.provider`, `email.smtp_host`, `email.smtp_port`, `email.smtp_user`, `email.smtp_security`, `integrations.audience_provider`, `integrations.audience_list_id`, `integrations.webhooks_enabled`, `tracking.enabled`, `tracking.ga4_id`, `tracking.meta_pixel_id`, `tracking.google_ads_id`, `tracking.require_consent`, `admin.alerts_enabled`, `admin.digest_enabled`, `admin.alert_signup_drop_pct`, `admin.alert_errors_per_hour`, `admin.alert_failed_payments`, `admin.alert_cooldown_hours`. Definitions are in `11_settings_registry.json`.

## 10. Routes added (64)

- Public (8): `GET /api/site/config`, `GET /api/site/assets/{id}`, `GET /api/popups`, `POST /api/popups/{id}/event`, `POST /api/popups/{id}/submit`, `POST /api/newsletter/subscribe`, `GET` and `POST /api/newsletter/confirm`.
- Admin (56), all under `/api/admin`: menu (2), Site Studio (14: draft read, save, reset, preset, discard, diff, preview link, publish, versions ×2, rollback, images ×3), popups (10), e-mail list (3), integrations (15: overview, provider, test send, list sync ×4, webhooks ×7, tracking), analytics extras (7), alerts (3), weekly summary (2).

## 11. Honest limits

- **Not run against live accounts**: Resend (shape checked only), Postmark, SendGrid, Brevo (sending and list), Mailchimp, MailerLite, SMTP, Stripe. Mocks prove our side only. Try each once in its test or sandbox mode before using it.
- Bounces and complaints are automatic for **Resend only**. For the others, add bad addresses by hand in Blocked addresses.
- Tracking tags change a privacy promise. Turn them on only after the Privacy page names them and the CSP lists their sources.
- The studio keeps one draft for the whole site. Two people editing at once means the last save of a section wins. The publish conflict check protects against overwriting a newer live version, not against two drafts.
- Images live in MongoDB (512 KB each). Fine for a logo and a few banners. Use a CDN if the library grows.
- Chunked requests with no `Content-Length` are not size-capped by our middleware (the host's proxy limit applies). The reference body caps are for normal browsers.
- A DNS name that changes to a private address in the milliseconds between the check and the send is a residual risk for webhooks (we check twice, and refuse redirects). Run the app with no access to private networks if you can.
- The reference tests use an in-memory MongoDB and mocked HTTP. Run them once on the real stack.
- Popup counts are totals per day, not per person. They show how a popup performs, not who saw it.
- The admin front-end screens are for the builder to make. The server side and the rules are done and tested.
