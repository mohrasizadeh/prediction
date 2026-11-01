# 36. Audit: code foundation and market position

Date: 2026-11-01. Findings only: nothing in the app was changed. The owner picks what gets fixed.

**Agreed frame.**
- **Position:** analysis only. No betting words, no bookmaker prices, no links to sellers (docs/03).
- **Audience:** bettors first, then fantasy managers, then writers and podcasters.
- **Markets:** Canada and the US, adults only, English at launch.
- **Business model:** free with paid extras.
- **Edge to win on:** transparency, led by public calibration. Depth of stats is the minimum to match.

**How Part 1 was done.**
- Four parallel reviews: security, correctness, speed and reliability, and frontend/accessibility/privacy.
- Every Critical and High finding below was re-checked by reading the code, and most were reproduced. Reproduction scripts were run against the in-memory demo (`backend/tests/demo_server.py`); no live deployment was available.
- Speed numbers come from that demo with a throttled phone (4x CPU, ~1.6 Mbps, 150 ms latency). Re-measure on the real host after deployment.

**Severity:**
- **Critical:** data breach, account takeover, payment error, legal launch blocker or site down.
- **High:** wrong numbers or labels shown to users, a broken core flow, or badly over a speed target.
- **Medium:** a real problem in limited cases.
- **Low:** hardening or polish.

---

## Summary

| | Critical | High | Medium | Low |
|---|---|---|---|---|
| Security | 1 | 3 | 4 | 7 |
| Correctness (numbers users see) | 0 | 7 | 9 | 4 |
| Privacy, compliance and copy | 1 | 1 | 5 | 5 |
| Speed and reliability | 0 | 2 | 8 | 5 |
| Accessibility and frontend | 0 | 1 | 6 | 7 |

**Read first.**
1. **Critical C1:** a non-owner admin can take over every account through the e-mail settings.
2. **Critical C2:** Terms, Privacy and About pages do not exist, but sign-up says users accept the Terms.
3. **Seven High bugs show wrong or misleading numbers** (H4–H10). Several sit in modules with little or no test coverage (`match_extras.py` 0%, `cards_model.py` 13%).
4. **Pages take 5.7–6.9 s** to show their main content on a phone, against a 2.5 s target (H13).

**Strong foundations.** The basics are solid and were checked: permission checks on all ~190 admin routes, password and session handling, 2FA, webhook signatures, injection and outbound-URL defences, keyboard access, copy rules and the honest-labelling core. The full list is in "Checked and fine" at the end of Part 1.

---

# Part 1: Code foundation

## Critical

### C1. An admin (not the owner) can steal the owner-only SMTP password and receive every user's password-reset link
- **Where:**
  - `backend/routes_site.py:432-445`: `PUT /api/admin/integrations/email` only needs `integrations.write`.
  - `backend/routes_admin.py:37`: `OWNER_ONLY_SETTINGS` does not include `email.*`.
  - `backend/routes_admin.py:546-568`: the key test.
  - `backend/transports.py:213-256`.
- **Scenario:**
  1. An admin points `email.smtp_host` at a server they control, then presses "test key".
  2. The app logs in to that server with the owner's stored SMTP password.
  3. From then on every e-mail goes there, including password resets.
  4. The admin requests a reset for any user and takes the account. Only accounts with 2FA survive.
  5. The same setting can also probe internal hosts and ports (SSRF).
- **Evidence:** reproduced. The fake SMTP server received `login('x', 'Owner-Smtp-Secret-1')` and then "Reset your Forecast password" for a victim's address.
- **Fix:** make `email.provider` and `email.smtp_*` owner-only (`keys.write`). Clear the stored password whenever the host changes. Apply the public-host check from `integrations.check_url` to `smtp_host`.

### C2. There are no Terms, Privacy or About pages, but sign-up says users accept the Terms
- **Where:**
  - `/legal/terms`, `/legal/privacy` and `/legal/about` all return 404 "No such page" in the demo.
  - Linked from the footer, from sign-up (`frontend/src/pages/Auth.jsx:123`) and from the cookie banner's "Read more".
  - The backend seeds no default content for these pages.
- **Why it is Critical:**
  - Both of your markets require a visible privacy policy: CalOPPA in California and PIPEDA in Canada.
  - The adults-only rule (18+) has to live in the Terms.
  - The sub-processor list required by docs/03 §6 has nowhere to appear.
  - Production may differ if the owner already wrote these pages in Admin → Pages. Check that.
- **Fix:** seed starter Terms (with the 18+ clause), a Privacy page (sub-processors, CCPA and PIPEDA sections, a contact) and an About page. Add a launch check that fails while any of the three is missing.

## High

### H1. Deleting an account with the wrong password still cancels the paid subscription, effective immediately
- **Where:** `backend/routes_accounts.py:289-302`. The subscription is cancelled before `A.delete_account` checks the password.
- **Evidence:** reproduced. The response was 403 `BAD_CREDENTIALS`, Stripe still received `DELETE /v1/subscriptions/...`, and the account remained.
- **Effect:** a typo costs the user the plan they paid for. Anyone holding a session can cancel a paid plan without knowing the password.
- **Fix:** check the password first, then cancel billing.

### H2. Making an existing member staff gives their current session admin rights, skipping 2FA
- **Where:** `backend/accounts.py:576-594`. `invite_staff` changes the role but never calls `revoke_all`. `set_role` at line 597 does revoke.
- **Evidence:** reproduced. The same old session got 403 on admin routes before the invite and 200 after, including on `/api/admin/keys`.
- **Effect:** a stolen or shared member session becomes an admin session with no 2FA and a 14-day life.
- **Fix:** revoke the user's sessions in `invite_staff`. In `require_perm`, also refuse staff sessions that were not created as staff sessions.

### H3. Two checkouts started more than a minute apart can create two paid subscriptions
- **Where:** `backend/stripe_billing.py:160-182`. The idempotency key changes every minute. The `ALREADY_SUBSCRIBED` guard only looks at subscriptions that already exist.
- **Evidence:** reproduced against a mocked Stripe. Two checkouts 61 s apart created two Checkout sessions, each valid about 24 h.
- **Effect:** a user who pays in two tabs, or returns to an old checkout tab, is billed twice every period.
- **Fix:** store each user's open checkout session and expire it before creating another. On `customer.subscription.created`, detect a second live subscription and cancel it or alert staff.

### H4. A failed import task stays "running" forever, so that match is never imported
- **Where:** `backend/ingest.py:219-271`. Only budget, breaker, 401 and 404 errors are caught. `enqueue()` cannot reset a stuck task, and nothing sweeps old "running" tasks.
- **Evidence:** reproduced. After a PitchAPI 503 the task was still "running" after re-queueing, and the next run reported `done 0`.
- **Effect:** the match's stats, player rows and outcomes stay missing for good. That silently skews the engine's history, the grids and the track record, which is your headline feature.
- **Related:** an HTTP-date `Retry-After` header raises `ValueError` and lands in the same trap (`cached_fetch.py:149`).
- **Fix:** catch every exception per task and retry with back-off, marking the task failed after N tries. At the start of each run, reset "running" tasks older than about 15 minutes.

### H5. The likelihood range is never shown on the forecast cards people actually use
- **Where:** `frontend/src/components/ui/ForecastCard.jsx:60-73` and `ForecastSheet.jsx:66-76`. They show only `pct(f.p)`. The range appears only on the old card on the Player page (`Football.jsx:68-80`).
- **Rule broken:** docs/03 §4.4 requires "74% (66 to 81)".
- **Why it matters:** the uncertainty range is part of the transparency edge, and right now nobody sees it.
- **Fix:** render "p% (lo to hi)" on the card and in the sheet.

### H6. The combo builder counts the chance to play twice for "gets a yellow card" lines
- **Where:** `backend/combo.py:43-48` together with `backend/cards_model.py:229-237`. Card lines already include the chance to play in `p`, and `combo.chance()` multiplies by `p_play` again.
- **Evidence:** reproduced. A line at 16%, with a 60% chance to play, became 9.6% in the combo.
- **Effect:** every combo that contains a card line shows a combined chance that is too low. The "Build one for me" ranking is wrong too.
- **Fix:** skip the `p_play` multiply for card rows. Also store card lines on the same "if he plays" basis as the other lines.

### H7. Referee history disappears after every result is imported
- **Where:** `backend/match_extras.py:136-157` (`rebuild_referees` deletes all rows and re-inserts them without `factor`) together with `backend/referees.py:143-153`.
- **Evidence:** reproduced. Before a rebuild: "Ref A gives about 5% more cards…". After: "No history with Ref A yet, so we treat this referee as average."
- **Effect:** for most of every match day, match pages wrongly say the referee has no history, and the referee input to the card forecasts is lost.
- **Fix:** update rows in place (`$set`) instead of delete-and-insert, or re-run the referee refresh straight after.

### H8. The player page lists lines from matches already played under "next match"
- **Where:** `backend/queries.py:743-756` (`player_detail` does not filter by kick-off) and `frontend/src/pages/Player.jsx:134-153`.
- **Evidence:** reproduced. The next match was m2, but the cards came from finished match 1.
- **Fix:** add `kickoff >= now` (or `match_iid` = the next match) to that query.

### H9. The "his own record" adjustment inflates the chances shown for bench and doubtful players
- **Where:** `backend/engine_bridge.py:263-265` and `backend/tiering.py:153-161`. A substitute's "if he plays" chance is blended toward his full-game hit rate, which comes mostly from games he started.
- **Evidence:** on the demo, 8 of 238 player lines moved by more than 10 points (for example 40% → 57%).
- **Fix:** skip the adjustment when the lineup badge is "bench" or "unsure". Alternatively, build the record only from games with similar minutes.

### H10. There is no stale-data banner
- **Where:** `ingest.stale_limit_hours` is never read. The only sign is a footer line in `frontend/src/components/Layout.jsx:145,193-194`.
- **Related bug:** `backend/routes_data.py:58` looks up a job named `"engine"`, but `jobs.py:126` logs `"engine:{iid}"`, so `last_ok.engine` is always empty.
- **Rule broken:** docs/03 §4.7. If PitchAPI is down for a day, visitors see yesterday's forecasts with no warning.
- **Fix:** compute `stale` in `/api/public/status`, show a top banner, and fix the job name.

### H11. The League page crashes the whole site, because the public site has no error boundary
- **Where:**
  - `frontend/src/pages/League.jsx:79` calls `avg.yellow_pg.toFixed(2)` when `yellow_pg` is null, which the API returns when there is no card data (`queries.py:609`).
  - Only the admin has an error boundary (`AdminApp.jsx:63`).
- **Evidence:** reproduced. The page went blank with the error "Cannot read properties of null (reading 'toFixed')". A null `home` in a match answer blanks the match page the same way.
- **Effect:** any unexpected null blanks the entire app, including the navigation and the required disclaimer.
- **Fix:** guard the null and show "No data". Wrap the public `<Outlet/>` in an error boundary that shows the existing error box.

### H12. Marketing-email consent given on the account page stores no time, wording or source
- **Where:** `backend/accounts.py:505-507` stores only a true/false. Campaigns select on that alone (`emailer.py:410`).
- **Rule broken:** docs/03 §6 and CASL, which requires the sender to prove consent. The newsletter route already does this correctly (`newsletter.py:39`).
- **Fix:** store `marketing_consent_at`, the consent text and the source on opt-in, and `withdrawn_at` on opt-out. Include them in the data export.

### H13. Pages take 5.7–6.9 s to show their main content on a phone (target 2.5 s)
- **Cause:**
  - The server sends nothing compressed (no `GZipMiddleware`).
  - All the JavaScript ships as one 833 KB file with no code splitting (`frontend/src/App.js`). The admin alone is 25% of it.
  - Page data only starts loading after `/api/site/config` answers (`App.js:91`).
- **Evidence:** measured; see the table below. With compression alone, content appears in 2.2–3.1 s, still over target on 5 of 7 pages.
- **Fix:**
  - Turn on gzip or brotli, in the app or on the host.
  - Lazy-load the admin, the Markdown pages, the 2FA screens (the QR library) and Studio, which is about 45% of the JavaScript.
  - Start loading page data at the same time as the site config.
  - Remove the two unused font imports (`index.js:9-10`).

### H14. Finder searches and player pages run slow full-collection queries that will get much worse with real data
- **Finder:** `backend/queries.py:309-347`. One aggregation runs over every player row in the league with no index, then 1–3 queries per result: about 220–320 database calls per search. Measured at p50 424 ms and p95 590 ms on demo data of only 3,000 rows (target 300 ms).
- **Player page and leaderboard:** `queries.py:704` (player ranks) and `queries.py:523-528` (leaderboard) scan the whole `player_match_stats` collection on every request. `mongo_init.py:63-66` has no `league_iid` index.
- **Scale:** five leagues × five seasons is about 240,000 rows.
- **Fix:**
  - Add a `(league_iid, kickoff)` index on `player_match_stats` and `team_match_stats`.
  - Limit the time window.
  - Batch the per-row lookups into one query each.
  - Precompute ranks and leaderboards once per engine run.

## Medium

**Security**
- **Lockout leaks and locks accounts.** The lock check runs before the password check (`accounts.py:247-249`). After 5 wrong tries a real account answers "locked" and an unknown one does not, which reveals which e-mails have accounts. Anyone can keep any account locked, including the owner's (reproduced). Fix: check the lock only after a correct password, or rate-limit per IP and account instead.
- **2FA can be set up without the password** (`routes_accounts.py:242-250`; reproduced). Someone with brief access to a session can lock the real member out. Fix: ask for the current password, and e-mail the user when 2FA is turned on.
- **The paid Matchup data is free through `/api/teams/{id}`.** `queries.py:773-778` returns `team_styles`; the gate exists only on the match route (`routes_data.py:207-209`; reproduced). Fix: apply the same plan check.
- **Roles without access to personal data can still see it.** Analysts and support receive raw Stripe invoice links and customer ids (`admin_queries.py:130-131, 200-210`), and an invoice page shows the customer's name and address. Fix: drop these fields for roles without `users.pii`.

**Correctness**
- **A hidden card forecast reappears after every engine run** (`cards_model.py:154-177`; reproduced). The test `test_iter21_cards_hide_survives.py` covers this, but it is outside the self-test suite.
- **"Confirmed lineup" is set for bench players.** The flag means the team's lineup is out, not that this player starts (`engine.py:775`). The Insights "Confirmed lineup only" filter keeps bench players (15 rows in the demo), and card lines can label a bench player "Confirmed starter". Fix: filter and label on `lineup_badge == "confirmed"`.
- **The "If he plays" tile is wrong for card lines** (`ForecastSheet.jsx:72`). For example it shows 16% where the true figure is about 27%.
- **The track record for card lines mixes two scales** (`tiering.py:34-44`, `cards_model.py:262-271`). As a result card tiers come out too generous.
- **The SportAPI lineup bridge marks a match confirmed when only one side matched** (`sportapi.py:284-291`). The other side's lineup is then never fetched, and up to 22 "starters" can show for one team.
- **Missing values show as 0.** Season squad cards show "0 Tackles" and "0 Cards" when the data is missing (`queries.py:744-746`, `Team.jsx:109`); player ranks also count missing values as 0 (`queries.py:690`). This breaks "No data, never 0" (docs/03 §4.6).
- **Live tracking can mark a line "Did not happen" from an old snapshot** (`sportapi.py:366-381`, `live_track.py:75-77`). This only applies when `sportapi.live_stats` is on.
- **The anonymous Finder limit is keyed on IP plus User-Agent** (`deps.py:19-21`). Changing the browser or the header gives a fresh quota.
- **Postponed or cancelled matches still show forecasts** in the Insights feed, the Finder and Top 3 (`queries.py:207-209, 307, 322`).

**Privacy and compliance**
- **One-click unsubscribe fails.** Mail apps send a form body, and the endpoint expects JSON (`routes_accounts.py:320-325`; reproduced: 400). This breaks Gmail and Yahoo bulk-sender rules and weakens the CASL "one click" claim.
- **Tracker consent cannot be withdrawn** once given. The owner can also switch consent off (`tracking.require_consent`). And there is no US "Do not sell or share" link if Meta or Google Ads tags are used (`Layout.jsx:103`, `growth.js:73`). Fix: add a "Privacy choices" footer link, lock consent on, and show the link when ad tags exist.
- **"Download my data" is incomplete** (`accounts.py:527-536`). It leaves out analytics events, the newsletter row, contact messages, admin notes and Finder usage. Deletion also leaves the newsletter subscription active (a deleted user keeps getting e-mail), along with auth-log and contact rows.
- **The banned-word scanners miss the "also avoid" list and obvious variants** (`backend/textguard.py:13-15`, `frontend/scripts/check-copy.js`). "Top tips today", "Guaranteed value", "free money", "Try bet365", "betslip" and a Cyrillic "оdds" all pass, and admin-written text can ship them. Fix: add the words, match prefixes, and normalise Unicode.
- **SEO settings are stored but never used.** No meta description, titles without the brand name, and several pages never set a title.

**Speed and reliability**
- **The match, player and team pages jump while loading.** Layout shift (CLS) is 0.38–0.43 against a 0.1 target: the footer shows under a short skeleton and is then pushed down (`Layout.jsx:254`, `base.css:100`).
- **There is no index on the public `id`** for matches, teams, players and leagues (`mongo_init.py:43-55`). So every URL and every crest or avatar request scans a whole collection.
- **The busiest public reads (Today, Insights) send no cache header** (`server.py:109-124`). Every page also loads 30 insight rows just for the footer newsletter preview (`Newsletter.jsx:10`).
- **Each player's "usual" number reads their whole history** with no limit (`queries.py:358-376`).
- **Settings are read from the database on every request**, with no cache (`settings_store.py:23-29`).
- **The job lock can expire mid-run and the next job's lock gets deleted** (`jobs.py:22-33, 115, 163`). Two engine runs at once can leave a match with no forecasts (`engine_bridge.py:307-309`).
- **Sending e-mail blocks sign-up and reset requests** for up to about 47 s when the provider is slow (`transports.py:69-89`). It also gives a timing signal for which e-mails have accounts.
- **The engine and the job runner run inside the web process** (`routes_cron.py:20-21`). Request time tripled while an engine run was going.

**Accessibility (WCAG 2.2 AA)**
- **Text contrast fails in light mode on tinted chips,** at 3.96–4.46:1. Affected: tier chips (`kit.css:16-18`), "Lineups confirmed" tags and `.lk-tag`. Two of these were introduced by the Apple HIG redesign: the Beta badge and the faded label on the selected day (`hig.css:35, 67`). This gives 39–41 failing elements on Insights and Match. Fix: print chip words in the normal text colour.
- **Dialogs do not trap focus, and focus is lost on close:** the bottom sheets, search and the Finder popovers (`BottomSheet.jsx`, `SearchOverlay.jsx`, `Finder.jsx:26-39`).
- **Focused controls hide behind the tab bar and cookie banner:** 11 of 45 tab stops on a phone. The CSS has no `scroll-padding`.
- **Accessible names do not match the visible labels.** Day buttons show "Sat 31" but are named "Saturday, October 31". The forecast card's `aria-label` hides the reason sentence from screen readers.
- **Sideways scrolling:** Insights at 320 px wide, and every page at 200% text (the header actions overflow).
- **Some controls are below the project's 44 px touch-target rule.** The HIG segmented control is set to 40 px (`hig.css:76`, from the redesign). Other examples: Player page buttons at 34 px, and a sign-in link only 23 px tall.

## Low

- **Security:**
  - "Must change password" is enforced only in the browser.
  - The `/api/stripe/webhook` alias is rate-limited like a normal write.
  - "Insights per day" only caps one response, so it is not a daily limit.
  - The cron check passes if the secret is set but empty (`server.py:165`, `routes_live.py:66`).
  - The response time on sign-up and reset reveals which e-mails have accounts.
  - Anyone can lift another person's unsubscribe.
  - The custom-CSS filter can be bypassed with CSS escapes or `image-set()`. Only the owner can enter custom CSS.
- **Correctness:**
  - Classic tier mode (not the default) allows Strong without a confirmed lineup.
  - A plan limit of 0 still allows one use.
  - A finished match with no score makes the match, team and referee pages return 500.
  - Deletion leaves auth-log rows.
- **Privacy:**
  - The plain-text version of marketing e-mails lacks the address and the unsubscribe link.
  - The pricing page does not say plans renew automatically (US auto-renewal laws).
  - The 18+ notice is only a footnote.
  - French for Quebec is a known gap (Bill 96, Law 25).
- **Copy:** "edge to {team}" on Compare, and "to back it" and "Hit in k of n" on cards are close to the avoid-list.
- **Accessibility and frontend:**
  - The ARIA tabs lack arrow-key support.
  - Heading order skips a level on Finder and Pricing.
  - The radar legend tells the teams apart by colour only.
  - The input focus ring is not the documented 2 px.
  - Route changes are not announced.
  - The previous match's data flashes briefly when moving between matches.
  - Two lint warnings.
- **Reliability:**
  - Forecast scoring re-checks every past forecast on each run.
  - The "use stale data if the provider fails" cache never triggers, because the TTL index deletes expired rows at once.
  - Forced job requests are lost when the time budget runs out.
  - There is no public health check, and a slow database fails startup.
  - Unused font packages.

## To verify before turning billing on

- **Stripe.** Stripe's restricted-business list covers "sports forecasting or odds making" when a money or material prize is involved ([Stripe list](https://stripe.com/legal/restricted-businesses), [FAQ](https://support.stripe.com/questions/prohibited-and-restricted-businesses-list-faqs)). A forecast subscription with no prizes looks outside it. But your main audience is bettors, so confirm with Stripe in writing before going live, and describe the product exactly as docs/03 does.
- **Data provider terms** (PitchAPI, SportAPI, API-Football): confirm that use by an analysis product whose audience bets is allowed. Doc 19 already flags API-Football.

## Test coverage

- **Backend:** the 28 self-test suites cover **80%** of statements. The weak spots match where the bugs are:
  - `match_extras.py` 0% (H7)
  - `cards_model.py` 13% (H6 and the hidden-card bug)
  - `follow_alerts.py` 31%
  - `availability.py` 35%
  - `routes_live.py` 43%
  - `sportapi.py` 46% (the lineup bridge bug)
  - `routes_teams.py` 48%
  - `soccer_brain/core.py` 62%
  - `queries.py` 70%
- **Untested files:** `admin_home.py` and `email_gate.py` have no coverage.
- **Frontend:** no automated tests. The two crashes (H11) would have been caught by a basic "every route renders" test.
- **Recommendation:** add tests for each fixed High bug, a render test per route, and move `test_iter21_cards_hide_survives.py` into the self-test suite.

## Measurements

**Pages.** Phone 390×844, 4x CPU, ~1.6 Mbps and 150 ms latency, cold load. Targets: LCP ≤ 2,500 ms and CLS ≤ 0.1.

| Page | LCP as served | LCP with gzip | CLS | Slowest tap |
|---|---|---|---|---|
| Today | 6,732 ms | 3,116 ms | 0.043 | 144 ms |
| Insights | 6,884 ms | 2,816 ms | 0.026 | 104 ms |
| Finder | 5,744 ms | 2,164 ms | 0.033 | 80 ms |
| Match | 6,168 ms | 2,624 ms | **0.434** | – |
| Player | 6,240 ms | 2,672 ms | **0.377** | – |
| Team | 6,068 ms | 2,500 ms | **0.434** | – |
| Sign in | 6,180 ms | 2,540 ms | 0.092 | – |

Taps respond within the 200 ms target everywhere measured.

**API.** Demo database (mongomock); use these only to compare routes. Target: p95 ≤ 300 ms.

| Route | p50 | p95 |
|---|---|---|
| Finder, form mode | 424–482 ms | **581–592 ms** |
| Finder, run mode | 357 ms | **430 ms** |
| Player ranks | 184 ms | 213 ms |
| League leaderboard | 174 ms | 238 ms |
| Match | 56 ms | 64 ms (116 KB answer) |
| Insights | 43–61 ms | 61–84 ms |
| Most others | 3–30 ms | under 55 ms |

**Bundle:** one JavaScript file of 833 KB (232 KB gzipped) and CSS of 172 KB (31 KB gzipped). Inside the JavaScript: admin 25%, Markdown stack ~100 KB, QR code library 16 KB.

## Checked and fine

- **Permissions:** all ~190 admin routes check permissions on the server. Owner-only gates hold except C1. User data routes are scoped to the signed-in user, with no cross-user access.
- **Passwords:** bcrypt over SHA-256, plus a dummy hash for unknown users.
- **Sessions:** random 256-bit tokens stored hashed, `__Host-` cookie set HttpOnly, Secure and SameSite=Lax, and revoked on reset, password change and role change.
- **Tokens and 2FA:** one-time tokens are hashed and single use. The 2FA secret is encrypted, replay is guarded, and recovery codes are hashed.
- **Request protection:** CSRF Origin check, CORS limited to your own origins, strict security headers, and generic 500 errors with no stack traces.
- **Payments:** Stripe and Resend webhooks check signatures and dedupe events. The price is resolved on the server, and plans change only via webhooks.
- **Injection and outbound requests:** no Mongo operator injection found, and no eval, pickle or shell. Outbound URLs refuse private addresses and redirects. Uploads are checked by content, and SVG is refused.
- **Front-end security:** no `dangerouslySetInnerHTML`, no raw HTML in Markdown, and no tokens in localStorage.
- **Forecast maths:**
  - Every forecast has lo ≤ p ≤ hi within valid bounds, and the calibration maps are monotone and capped at 97%.
  - "N or more" lines are consistent from engine to scoring.
  - Calibration is applied once.
  - The track record is hidden below 300 scored forecasts.
  - Same-player dependence in combos is handled.
- **Rules that hold:** the copy check passes, and no banned word was found in 31 crawled pages. The exact disclaimer is on every page except the crashed League page. The Beta tag shows.
- **Accessibility basics:** keyboard access works with a visible focus ring. Reduced motion is respected. Charts have text alternatives. Tiers show name and dots.
- **Privacy defaults:** deletion covers everything docs/03 §6 lists and cancels Stripe first. Marketing is off by default. The newsletter uses double opt-in with consent stored. Trackers load only after consent and never with DNT or GPC.
- **Server:** provider calls have timeouts and bounded retries. Routes are threadpool-safe. Module caches are bounded.

---

# Part 2: Product and market

**Limits of this part.**
- This environment's network blocks direct visits to the rival sites, so this part relies on web search results and press or app-store descriptions. Nothing here comes from using the rivals' products.
- Anything marked **Check** needs a hands-on look, ideally signed in.
- Prices and features change; treat them as of 2026-11-01.

## The market in one paragraph

Bettors who look at football player lines have three kinds of tools:
1. **Hit-rate screeners** such as PlayerStats (about £7.99 a month) and StatsHub (free). They answer "how often did he reach 2+ shots lately?" with filters.
2. **Match prediction sites** such as Forebet and FootyStats. They give team-level probabilities across hundreds of leagues, with little or no published accuracy.
3. **Score apps** such as FotMob and Sofascore, which bettors open for live scores, lineups, alerts and ratings.

Almost nobody offers player-level probabilities with reasons and a public calibration record. A few new sites (MatchMind, FP Oracle) publish calibration, but for match outcomes, not player lines. That gap is where Prediciotn can stand out.

## Feature comparison

For each feature, the first column gives your status, then what each rival offers. "?" means not confirmed from public sources (**Check**).

| Feature | Prediciotn | PlayerStats | StatsHub | FootyStats | Forebet | FotMob / Sofascore |
|---|---|---|---|---|---|---|
| Player stat history (shots, tackles, cards…) | **Level.** Grids, history, ranks | Yes, the core product | Yes, free | Team-level mostly; player ? | No | Yes, per match |
| Hit-rate finder with filters (last N, home/away, position, starts) | **Level.** Finder; free tier limited | Yes, rich filters, trial then paid | Yes, free | Team markets | No | No |
| Probability for a player line | **Ahead.** Model with "if he plays" | No (hit rates only) ? | "Statistical models" ? | Team markets only | Team only | No |
| Reasons behind each number | **Ahead.** Every card | No | No | No | No | No |
| Uncertainty range | **Behind its own spec.** Computed but not shown (H5) | No | No | No | No | No |
| Public track record and calibration | **Ahead on paper, invisible today.** Hidden until 300 real scored forecasts; calibration fitted on 2015/16 data | No | No | No | No (none published) | No |
| Lineup-aware forecasts | **Ahead.** Lineup badge, earned tiers | Starts-only filter | ? | No | No | Lineups, predicted XI (FotMob) |
| Lineup / goal alerts | **Behind.** E-mail alerts for Pro only, no push | Telegram fouls alerts | ? | ? | ? | Push alerts per match |
| Live in-play | **Level.** Live scores, events, tracking | In-play alerts | Real-time | ? | Live ? | **Ahead of you.** Fast live data, ratings |
| League coverage | **Behind.** 8 leagues | ? | ? | 1,500+ | 850+ | Hundreds |
| Combos with correlation | **Ahead.** Combo builder, same-player dependence (bug H6) | No | No | No | No | No |
| Referee and booking context | **Ahead.** Referee factor, booking risk (bug H7) | Partial ? | ? | Cards stats | No | No |
| Speed on a phone | **Behind.** 5.7–6.9 s (H13) | ? | ? | ? | ? | Native apps, fast |
| Mobile app or push | **Behind.** Web only | Web | App (Expo) ? | iOS app | iOS app | Native apps |
| Price | Free + Pro (billing off) | ~£7.99/month after trial | Free | Free + premium ? | Free + premium ? | Free + ads/subscription |

**What the table says:**
- You are ahead on the things that are hard to copy: player-line probabilities, reasons, lineup awareness, correlation-aware combos and referee context.
- You are behind on what users notice first: speed, push alerts, an app, league coverage, and a visible proof of accuracy.
- StatsHub gives hit rates away free, so a hit-rate finder on its own cannot be what people pay for.

## Ten moves to stand out

Ranked by value to bettors (then fantasy managers) against effort. Each one names the edge it supports.

1. **Make every number trustworthy before launch.** *Effort: medium. Edge: transparency is worthless if numbers are wrong.* Fix C1–C2 and H1–H14, starting with the wrong-number bugs (H4–H10). Add tests for each. One screenshot of a wrong number on social media undoes any calibration claim.

2. **Start the public record now, and show calibration per stat line.** *Effort: medium. Edge: the core differentiator.*
   - Today the Track Record page is hidden until 300 real forecasts are scored, and calibration was fitted on 2015/16 data (doc 31).
   - Run the real-data backtest (doc 18) and start scoring live forecasts as soon as real data flows.
   - Then show it per stat ("when we said 70% for 2+ shots, it happened 71% of the time, 1,240 lines") with a reliability chart.
   - No rival shows this for player lines. Put it in the header of every card ("Our 70% lines: 71% reached").

3. **Show the range on every card (H5) and explain it in one tap.** *Effort: low. Edge: honesty.* "74% (66 to 81)" tells a bettor how firm a number is, which rivals never say.

4. **Lineup-time alerts with push.** *Effort: medium. Edge: lineup awareness.*
   - Bettors and fantasy managers act in the hour before kick-off.
   - When lineups confirm, send a push (installable web app first, PWA) for followed players: "Saka starts: 2+ shots now 68% (was 61%)".
   - FotMob sends lineup alerts but no forecasts; nobody sends the changed forecast.
   - Consider including one alert in the free plan, as a hook.

5. **Show how each forecast moved, and why.** *Effort: low.* The data already exists (`p_prev`). Show "up from 61% after confirmed lineups" or "down: referee gives fewer cards" in neutral words. This answers "is now the time to look?" without betting language.

6. **Fast on a phone.** *Effort: low to medium.* Compression, code splitting and parallel data loading (H13), plus the CLS fix. Target content under 2.5 s; users at kick-off time will not wait 6 s when FotMob opens instantly.

7. **Rethink what is free.** *Effort: low (settings). Business-model decision for you.*
   - StatsHub's hit-rate screener is free, and yours is limited to 3 searches a day signed out and 10 signed in.
   - Suggestion: make the Finder generous or unlimited for free (it draws people in), and charge for what nobody else has. That means unlimited forecast cards with reasons and ranges, lineup-time push alerts, the combo builder, per-stat calibration detail, the tactical matchup and CSV export.
   - Fix the leak of Matchup data first (Medium, security).

8. **Cover the leagues your North American audience follows.** *Effort: depends on the provider.*
   - You run 8 leagues; Forebet and FootyStats cover 850–1,500. Don't chase breadth: depth plus calibration beats breadth.
   - Make sure the 8 include what Canadian and US users follow most: Premier League, Champions League, the other top European leagues, MLS and Liga MX.
   - **Check** the current league list and whether PitchAPI covers MLS and Liga MX player stats.

9. **Make the combo builder a showcase.** *Effort: low after the H6 fix.* Same-match combos are popular, and correlation is where naive tools go wrong. Show the combined chance with its reason ("these two lines tend to happen together, so the combined chance is higher than multiplying them"). No rival explains this.

10. **Share cards and embeds for writers and podcasters.** *Effort: low to medium. Edge: transparency spreads itself.*
    - A share card exists. Add the line's track-record stat to it ("our 70% shot lines: 71% reached") and a short link back.
    - Offer an embeddable "forecast of the day" widget with the disclaimer.
    - Every share becomes proof of accuracy and free distribution, and it is a growth loop rivals cannot easily copy.

**Not recommended now:**
- Matching FotMob or Sofascore on live speed or league breadth: very expensive, and not your edge.
- Showing bookmaker prices, even without betting words: ruled out with you, and the main payment and ad-platform risk.

## Check items for a hands-on look

- PlayerStats signed in (the owner has a trial, doc 02): do they show any probability or accuracy figures? How fast is the Finder?
- StatsHub: confirm it is still fully free and which player stats it covers for MLS.
- FootyStats and Forebet: what premium adds, and whether either publishes calibration.
- FotMob and Sofascore: current lineup-alert timing (minutes before kick-off) and predicted-lineup accuracy.

## Sources (Part 2)

- PlayerStats: [features](https://playerstats.football/features), [about](https://playerstats.football/about), [changelog](https://playerstats.football/changelog), [props finder](https://playerstats.football/player-props-finder)
- StatsHub: [free tools](https://www.statshub.com/free-tools), [features](https://statshub.com/es/features), [about](https://statshub.com/about)
- FootyStats: [about and FAQ](https://footystats.org/about-and-faq), [predictions](https://footystats.org/se/predictions/over-35-goals), [iOS app](https://apps.apple.com/app/id1590091942)
- Forebet: [review on method and limits](https://www.valuethemarkets.com/prediction-markets/forebet-review-how-data-driven-football-forecasts-work-and-their-limits), [iOS app](https://apps.apple.com/app/id6443482854)
- FotMob and Sofascore: [comparison](https://marlvel.ai/intel-report/sports/com-mobilefootie-fotmobpro), [AlternativeTo](https://alternativeto.net/software/soccer-scores--fotmob/about), [FotMob alerts](https://en.androidayuda.com/fotmob-follows-football-matches-live/), [Sofascore listing](https://mwm.ai/>/apps/sofascore-live-sports-scores/1176147574)
- Calibration publishers: [MatchMind](https://hunted.space/product/matchmind-2), [FP Oracle](https://www.footballparadise.com/oracle)
- Stripe: [restricted businesses](https://stripe.com/legal/restricted-businesses), [FAQ](https://support.stripe.com/questions/prohibited-and-restricted-businesses-list-faqs)
