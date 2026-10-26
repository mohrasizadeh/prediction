# 03. Rules and compliance

Read this before you write any screen text, seed data or prompt. These rules override anything else in the package.

## 1. What this product is

A statistics and forecasting tool for football (soccer). It shows how likely a player or team is to reach a stat line, and why. It is for information and entertainment.

It is **not** a betting product. It never shows prices from sellers, never links to sellers, and never tells anyone what to wager.

## 2. Words you must never use

In the interface, in code strings, in seed data, in emails, in alt text, in error messages, in the Learn pages, and in the page title and meta tags.

`bet`, `bets`, `betting`, `bettor`, `bookie`, `bookmaker`, `sportsbook`, `odds`, `wager`, `parlay`, `accumulator`, `stake`, `punt`, `tipster`, `lock`, `banker`, `units`, `hit rate`, `picks`, `props`

Also avoid: "tip", "tips", "value", "edge", "sure thing", "guaranteed", "can't lose", "free money", "fade", "lay", "back".

Words to use: forecast, likelihood, chance, form, run, market, line, insight, tier, reason, reached, "N or more".

Only exception, exactly as written, in the footer: **"Statistical analysis for information and entertainment. Not betting advice."** Stored in the setting `copy.disclaimer`.

This file and `02_playerstats_parity.md` name banned words only to ban them. Never copy a banned word from these two files into the app.

The scan: `selftest.py` fails if any public setting, market label or reason contains a banned word. Run the same regex over every **string a user can see** before release: React text, seed data, settings defaults, page titles, e-mails, error messages (acceptance checklist, item A3). Do not scan identifiers. Developer words such as `lock` (a database lock) or `units` in code are fine as long as no user ever sees them.

## 3. Locked settings

| Setting | Locked value | Why |
|---|---|---|
| `features.live` | false | PitchAPI has no live data. |
| `engine.lineup_effects` | false | The lineup-effects layer failed its test on simulated data. It stays off until a real-data backtest passes. `settings_store.put()` refuses `true`. |

Do not add UI to unlock them. The Admin shows them as read-only with the reason.

## 4. Honest-labelling rules

1. **Beta tag.** The header shows "Beta" and the Track Record page says why, until an admin stores a real-data backtest (setting `track_record.min_scored` is met by real scored forecasts). The engine has been tested on simulated data only.
2. **Track Record.** Show it only when at least `track_record.min_scored` (300) forecasts have been scored. Before that: "Not enough results yet. We show this page when we have 300 scored forecasts."
3. **Predicted vs confirmed lineups.** Every forecast for a player shows whether the lineup is predicted or confirmed. Strong tier requires a confirmed lineup. The engine already enforces this.
4. **Bands, not single numbers.** Show the likelihood with its band: "74% (66 to 81)".
5. **No guarantees.** Never say a forecast "will" happen. Say "is likely to".
6. **Missing data.** If a value is missing, show "No data". Never show 0. Never hide a market silently: show "Not available yet" and the reason in a tooltip.
7. **Stale data.** If the last successful sync is older than `ingest.stale_limit_hours`, show a banner: "Data last updated 14 hours ago."
8. **Data credit.** Show `copy.data_credit` in the footer when set. Moh sets it after PitchAPI answers questions B1 to B3 (`08_pitchapi_data_guide.md`).

## 5. Security rules

The full list, with the file for each control and the do-not list, is `15_security_and_privacy.md`. The rules that never bend:

1. The PitchAPI, Stripe and Resend keys are never sent to the browser, never logged, never in a URL, never in git. They are stored encrypted (`security.py`) and shown as "•••• 3456".
2. The browser never calls PitchAPI, Stripe's API, or Resend. Pages read our database only. Checkout and the billing portal are Stripe-hosted redirects.
3. Staff routes check the role's permission on the server on **every** request (`deps.require_perm`). Hiding a menu item is not security.
4. Staff must use two-factor sign-in. There is no "sign in as user". The first owner is created from `ADMIN_EMAIL` and `ADMIN_INITIAL_PASSWORD` and must change the password at first sign-in.
5. Passwords: bcrypt over a SHA-256 pre-hash. Never log request bodies on auth routes. One generic answer for unknown e-mail and wrong password.
6. Sessions: opaque random token in an `HttpOnly`, `Secure`, `SameSite=Lax` cookie; stored hashed; revocable. No tokens in `localStorage`.
7. Every staff change writes an `audit_log` row (who, role, what, target, reason).
8. Public text is rendered as text, never as raw HTML. Admin-edited Markdown and e-mail HTML are sanitised or restricted.
9. CORS: only the app's own origins (`ALLOWED_ORIGINS`). Never `*` with credentials.
10. Rate limit everything (auth 10/min, writes 60/min, reads 240/min per IP) plus per-e-mail limits on sign-in, reset and resend.
11. Never put the cron secret, webhook secrets or any key in the browser.
12. Webhooks (Stripe, Resend) are accepted only with a valid signature, and each event id is applied once.
13. No card data on our servers. No third-party scripts or trackers, with **one owner-controlled exception**: GA4, Meta pixel and Google Ads tags (`16` §6.3). They are off by default, can be turned on by the owner only, load only after a visitor allows them, and need the Privacy page and the CSP updated first.
14. Every text an admin can write (site text, menus, popups, announcements, e-mail templates, campaigns, pages, plan text, settings) is scanned on the server for the words in section 2. The only allowed use is the exact disclaimer sentence. The check is in `textguard.py`; a failure answers 400 `BANNED_WORDS` with the words found.
15. Admin-built popups are plain text with a close control, and never appear on sign-in, sign-up, reset, verify, checkout, billing or admin pages. An e-mail field in a popup needs a consent sentence and uses double opt-in.
16. Visitors can always read the text. A look change that makes text unreadable (under 4.5:1) cannot be published.

## 6. Privacy

- Collect: e-mail, password hash, optional name, time zone, theme, notification choices, follows, notes, saved forecasts, plan and payment records (ids, amounts, status; never card data), sign-in history (90 days), anonymous usage events (no IP, no cookies).
- Do not collect: card numbers, location, device ids, date of birth, contacts.
- Provide: delete my account (removes `users`, `follows`, `notes`, `saved_forecasts`, `alert_subscriptions`, sessions, tokens; payment records stay unlinked), export my data (JSON), unsubscribe from non-essential e-mail with one click.
- Marketing e-mail: opt-in only, default off. Postal address and unsubscribe link in every one (Canada's CASL). Time of consent stored.
- Name the sub-processors on the Privacy page: host, MongoDB, Stripe, Resend.

## 7. Accessibility (WCAG 2.2 AA)

- Text contrast 4.5:1, large text and icons 3:1. The tokens in `04_design_system.md` pass for their stated use (checked by computing the ratios); do not change them without re-checking. In light mode the tier and up/down colours are 3:1 (icons, dots, bars only), so their words are printed in the normal text colour.
- Tier is shown by **name and dot count**, plus colour. Strong ●●●, Solid ●●○, Watch ●○○.
- All controls reachable by keyboard, visible focus ring (2 px, brand colour).
- Touch targets at least 44 by 44 px.
- Respect `prefers-reduced-motion`: no animation, only instant state changes.
- Charts have a text alternative (a data table behind a "Show table" button).
- Grid cells are not colour-only: the number is always printed.

## 8. Things the builder must not do

- Do not write 0 for a missing stat.
- Do not call PitchAPI from the browser or from a page request.
- Do not use the PitchAPI SDKs.
- Do not call `/shots`, `/heatmaps`, `/momentum`, `/advanced/network` (they are huge and unused).
- Do not hard-code a number that exists in `11_settings_registry.json`.
- Do not add seller links, price columns, or "value" labels.
- Do not enable `SoccerEngine(lineup=True)`.
- Do not add `__init__.py` to the engine's parent folder.
- Do not rename the engine files. They import each other by flat name.
- Do not commit `.env`.
- Do not store tokens in `localStorage`, add a login-as-user feature, load third-party scripts (except the owner-enabled tags above), or return any hash, secret or token from a route (`15` section 3).
- Do not load fonts from Google or any other site. Fonts are self-hosted (`16` §2.4).
- Do not render popup or site-config text as HTML. It is text.
- Do not grant paid access from a redirect URL. Only the signed Stripe webhook changes who is subscribed.
- Do not put banned words in e-mail templates, plan names, plan bullets, announcements or coupon names. The scan in Admin → Content also covers them.
