# 12. Acceptance checklist

Tick every line before launch. "Evidence" is how to check.

## A. Rules

| # | Check | Evidence |
|---|---|---|
| A1 | No page makes a request to `api.pitchapi.dev` from the browser | Network tab on every screen |
| A2 | The PitchAPI key never appears in any response, log, or source file | Search source and network; `provider_keys` holds ciphertext |
| A3 | No banned word (`03_rules_and_compliance.md`) in any string a user can see: UI text, seed data, settings defaults, page titles, e-mails, errors | Run the regex over the visible strings (not identifiers). Crawl every screen and search the text. |
| A4 | The footer shows the exact disclaimer | Visual |
| A5 | `features.live` and `engine.lineup_effects` cannot be turned on | Try in Admin and by API |
| A6 | Beta tag visible in header and on Track Record | Visual |
| A7 | No stat shows 0 where the data is missing | Check a goalkeeper's tackles, a league without corners |

## B. Data and cache

| # | Check | Evidence |
|---|---|---|
| B1 | Check A (12 items) answered and saved in `08_pitchapi_verified.md` and in Settings → Provider | File and settings |
| B2 | One league, one season ingests with zero `missing_field` issues | Issues screen |
| B3 | A second run makes zero API calls | Usage screen: calls today unchanged |
| B4 | Budget stop works: set `ingest.daily_call_budget` low, the queue stops and resumes next day | Jobs screen |
| B5 | A 401 trips the breaker and shows a red banner; pages still serve stored data | Test with a wrong key |
| B6 | Stale banner appears when no sync for longer than `ingest.stale_limit_hours` | Change the setting to 0 temporarily |
| B7 | `data_coverage` shows shots, SoT, corners, tackles, possession, minutes, started, position | Coverage screen |
| B8 | A market with coverage under `engine.coverage_min` is hidden with "Not available yet" | Set the setting to 1.01 temporarily |
| B9 | Database size measured after the first league-season | `dbstats`; record in the Dashboard |

## C. Engine

| # | Check | Evidence |
|---|---|---|
| C1 | `selftest.py`, `selftest_queries.py`, `selftest_jobs.py` pass in the deployed environment | Command output |
| C2 | Engine run completes and writes forecasts for matches in the next `engine.window_days` | Engine screen |
| C3 | A re-run does not double forecasts | Count `is_current` per match |
| C4 | Confirmed lineups change a player's `p_play` and `lineup_confirmed` | Compare before and after |
| C5 | Strong tier only with a confirmed lineup | Query: no Strong with `lineup_confirmed = false` |
| C6 | Tactic chips and reasons name the opponent's tactic when one applies | Match page |
| C7 | Real-data backtest stored, or the Beta tag stays | Track Record page |

## D. Screens (each must work on a 390 px phone and a 1280 px desktop)

| # | Check |
|---|---|
| D1 | Today: date strip, grouped fixtures, win/draw/loss bar, insight counts, lineup chips |
| D2 | Match: all five tabs, forecast filters, Predicted/Confirmed labels |
| D3 | Insights: filters and sort by tier then likelihood |
| D4 | Finder: all three modes, all filters, up to 5 leagues, 3 free searches then sign-in prompt |
| D5 | Squad grid: 5 to 30 games, home/away, started, hide inactive, column tap shows lineups |
| D6 | Team totals and Against views |
| D7 | Player: Quick view chart, line control, history table, follow, note |
| D8 | League: fixtures, results, leaderboards (total and per 90) |
| D9 | Search finds players and teams in two keystrokes |
| D10 | Following, saved forecasts, notes persist per user |
| D11 | Track Record shows "not enough results" below the threshold |
| D12 | Learn pages edited in Admin appear live |
| D13 | Time zone setting changes kickoff times and the date strip |

## E. Admin

| # | Check |
|---|---|
| E1 | `/admin` is unreachable signed out (404) and signed in as a normal user (403 on API). Detailed role checks are in section J |
| E2 | Key save, test, remove for all five keys; only the last 4 characters ever shown; owner only |
| E3 | Explorer shows cache or real, cost, raw JSON; blocks "Never" routes |
| E4 | Every setting in `11_settings_registry.json` is editable, resettable, with history |
| E5 | Changing a colour in Site Studio and pressing Publish updates the app without a deploy; the readability gate blocks failing pairs |
| E6 | Every admin write appears in the audit log |
| E7 | Lockout after `auth.max_failed_logins` failed sign-ins; sign-in log shows them |
| E8 | Export and import of the small collections |

## F. Quality

| # | Check |
|---|---|
| F1 | WCAG 2.2 AA: contrast, keyboard, focus ring, 44 px targets, reduced motion |
| F2 | Tier is never colour-only (name and dots) |
| F3 | Lighthouse mobile: performance 85+, accessibility 95+ |
| F4 | No console errors on any screen |
| F5 | Empty, loading and error state on every list |
| F6 | Production environment: indexes created, key entered, `.env` set, tick pinger running (preview and production databases are separate) |

## G. Business

| # | Check |
|---|---|
| G1 | PitchAPI answered B1 to B3, and `copy.data_credit` is set if needed |
| G2 | `features.billing` stays false until G1 allows it |
| G3 | Terms, privacy, about pages written and published |

## H. Accounts (doc 13)

| # | Check |
|---|---|
| H1 | Sign-up gives the same answer for a new and a taken e-mail; only the new one gets a verify e-mail |
| H2 | Cannot sign in before confirming e-mail; the link works once and expires |
| H3 | Cookie is `HttpOnly`, `SameSite=Lax`, `Path=/`, `Secure` on HTTPS, name `__Host-sid`; nothing sensitive in `localStorage` |
| H4 | Wrong password and unknown e-mail give the same message and similar timing |
| H5 | Lockout works; the per-e-mail brake works; the 429 page shows the wait time |
| H6 | Forgot password: same answer for known and unknown; link works once; all devices are signed out; the security e-mail arrives |
| H7 | Change password signs out other devices and keeps this one; change e-mail sends the link to the NEW address and a notice to the old |
| H8 | 2FA: set up with an authenticator app, recovery codes shown once, a code cannot be used twice, 5 wrong codes end the sign-in |
| H9 | Devices list shows this device; sign out one, sign out all others |
| H10 | Export downloads JSON with no hashes or secrets; delete needs the password, cancels billing first, signs out, and the e-mail cannot sign in again |
| H11 | `GET /api/auth/me` works signed out and drives the UI; staff without 2FA see the enrolment screen |
| H12 | Finder: signed-out visitors get 3 searches a day then a sign-in prompt; a free-plan user gets their plan's limit and an upgrade prompt; with billing off, signed-in users are unlimited |
| H13 | Every account form meets the accessibility list in doc 13 §9 |

## I. Billing and e-mail (docs 14, test mode)

| # | Check |
|---|---|
| I1 | Sync plan creates the Stripe product and prices; running it again changes nothing; changing a price makes a new price and retires the old |
| I2 | Test card 4242 completes checkout; the return page waits for the webhook; the person becomes Pro; a receipt e-mail arrives |
| I3 | The same webhook sent twice does nothing the second time; a bad signature gets 400 |
| I4 | Card 4000 0000 0000 0341 fails on renewal: status past due, e-mail sent, access stays for the grace days, then drops to Free |
| I5 | Cancel in the portal: access stays to period end, then Free; the "ended" e-mail arrives |
| I6 | Refund from Admin (test mode): the payment shows refunded; a second click does not refund twice |
| I7 | A coupon code works at checkout |
| I8 | Trial: first subscription gets trial days, the "trial ending" e-mail arrives, a second subscription gets none |
| I9 | Stripe key of the wrong mode is refused; live refunds are owner-only |
| I10 | Resend: verify and reset e-mails reach the inbox, not spam (SPF, DKIM, DMARC pass); a bounce adds a suppression; an unsubscribe link works from the mail client in one click |
| I11 | A person on a comp plan sees "Included until {date}"; it ends on the date |
| I12 | With `features.billing` off: no pricing prices shown as buyable, checkout returns `BILLING_OFF`, everyone signed in has full access |
| I13 | Failed webhook (for example an unknown price) shows a red alert in Admin → Health and the Webhooks log; after fixing the plan the retry succeeds |

## J. Admin panel (doc 10)

| # | Check |
|---|---|
| J1 | Each role sees only its menu and gets 403 from the API on the rest: owner, admin, support, analyst, user. A test signs in as each and tries three forbidden routes |
| J2 | Staff cannot reach any admin route until 2FA is enrolled; sessions end at 60 minutes and after 20 idle |
| J3 | Analyst sees masked e-mails and IPs and cannot search by e-mail; support sees full e-mails but not analytics or money |
| J4 | Disable, comp, refund, role change, key save, purge each need a reason or typed confirmation and appear in the audit log with the actor |
| J5 | Staff cannot disable themselves or another staff member; the last owner cannot be demoted, turned off or deleted |
| J6 | The user drawer, export and log views contain no hash, secret, token or e-mail body |
| J7 | Dashboard numbers match the lists they summarise (free + paid + trial + comp = total people) |
| J8 | Analytics: bots and Do Not Track visits are not counted; no IP is stored; revenue is never summed across currencies |
| J9 | Settings: wrong type refused; locked settings refused; owner-only settings refused for admin; history shows who changed what |
| J10 | Campaigns are blocked until marketing e-mail, the footer address and consent exist; re-sending does not duplicate; the cap is respected |
| J11 | Announcements show to the chosen audience only and disappear when switched off |
| J12 | Inbox: contact messages appear, can be marked, and nothing is auto-sent to the sender |

## L. Site Studio, popups, integrations, analytics extras (docs 16 and 17)

| # | Check |
|---|---|
| L1 | Draft, preview link, Publish, Rollback all work. A draft is invisible to visitors. Publishing over a newer live version answers 409 until overridden |
| L2 | A text colour under 4.5:1 blocks Publish and names the pair; all six presets publish |
| L3 | Fonts load from `/fonts/` only (no request to any other site in the browser's Network tab); CSP `font-src 'self'` holds |
| L4 | Changing the button style, corner size, menu items and the phone bottom bar changes the live site after Publish; buttons are at least 44 px tall on a phone |
| L5 | Dark, light and system modes work; the visitor's choice is remembered; `allow_toggle` off hides the switch |
| L6 | Custom CSS: owner can save safe CSS; admin gets 403; `@import`, outside `url()`, `<` are refused |
| L7 | Logo upload accepts a PNG and refuses an SVG and a renamed text file; an image in use cannot be deleted |
| L8 | A banned word in any site text, menu label, popup, announcement or e-mail template is refused with 400 or 422 and names the word |
| L9 | A popup appears only to the audience, page, device and dates chosen; never on admin, sign-in, sign-up, reset, verify, checkout or billing pages; session limits and frequency hold; the close button works with the keyboard and Esc |
| L10 | Popup sign-up: needs the tick; sends a confirmation e-mail; the list row stays "pending" until Confirm is pressed (opening the link alone does nothing); the consent sentence and time are stored |
| L11 | Unsubscribe link: opening it changes nothing; pressing the button unsubscribes; the address is not added again by a popup |
| L12 | E-mail provider switch: a test mail goes through each provider you have a key for; with no key nothing is sent and the status says why |
| L13 | List sync: a confirmed sign-up reaches the chosen provider within two ticks; an unsubscribe follows; a refused key raises an alert |
| L14 | Webhooks: a test event arrives with a valid signature; a private or `http://` address is refused; 20 failures switch the endpoint off and alert |
| L15 | Tracking tags: admin cannot enable them; with the owner's switch on, nothing loads before the banner's "Allow optional"; with Do Not Track nothing loads |
| L16 | Analytics extras: realtime, compare, sources by campaign tag, e-mail health, CSV (a cell starting with `=` opens as text in a spreadsheet) |
| L17 | Alerts: a sign-up drop opens one alert and one e-mail; it clears itself; people who switched alerts off get nothing |
| L18 | The admin on a 390 px phone: bottom bar with 4 icons and More; More sheet with search; no sideways scroll on any screen; tables are cards; every target at least 44 px; the bar shows only tools the role may use |
| L19 | `selftest_studio.py` and `selftest_growth.py` pass on the real stack |

## K. Security (doc 15)

| # | Check |
|---|---|
| K1 | All eleven self-tests pass on the real stack: `selftest.py`, `selftest_queries.py`, `selftest_jobs.py`, `selftest_accounts.py`, `selftest_billing.py`, `selftest_server.py`, `selftest_admin.py`, `selftest_studio.py`, `selftest_growth.py`, `selftest_brain.py`, `selftest_images.py` (replace `mongomock` with a throw-away real database once) |
| K2 | Security headers present on API responses; CSP set on the app host; HSTS on HTTPS |
| K3 | A POST with a foreign `Origin` gets 403 `BAD_ORIGIN` |
| K4 | A forged `X-Forwarded-For` does not dodge the rate limit (check the real hop count, doc 15 §7) |
| K5 | A forced crash returns the generic error with a request id and writes a row to `app_logs` |
| K6 | `/docs` and `/openapi.json` are off in production |
| K7 | No secret appears in any response, log or audit row (search the database for the test key after saving it) |
| K8 | `pip audit` and `npm audit` show no high-severity issues |
| K9 | A backup restore was tested once |
| K10 | A security review or penetration test was booked before taking payments |

## M. Brain: tactics, rotation, gates (doc 18)

| # | Check |
|---|---|
| M1 | `selftest_brain.py` passes, and `python backtest.py` prints the same report as `backend/soccer_brain/backtest_report.txt` (the defaults did not change) |
| M2 | Admin → Engine → Brain layers opens. With no calendar imported it shows 0 clubs covered, no rotation chip appears, and nothing else changes |
| M3 | Import 5 cup or European fixtures for one club. Its next league match shows a rotation chip with the right competition named and the right number of days |
| M4 | After an engine run, `engine_gates` has a `start_model` row for each league with `reason` filled in. On thin data `applied` is false |
| M5 | With `context.start_model = off`, forecasts for the same match are identical before and after importing a calendar (only the chip fields differ) |
| M6 | A confirmed lineup for a club makes its player forecasts ignore the start model |
| M7 | The real-data walk-forward (doc 18 §8) was run on PitchAPI history. The result for the style-matchup terms, the tactics layer and the shape layer is written down, and `engine.interactions`, `engine.tactic_layers` and `engine.shape_layer` match it |
| M8 | Matches with an empty event feed (all-zero shots, tackles and corners for a side) are excluded before fitting; the count excluded is shown in Data quality |
| M9 | The rotation sentence passes the banned-word scan and never says what a person should do |

## N. Logos, crests and photos (doc 19)

| # | Check |
|---|---|
| N1 | `selftest_images.py` passes |
| N2 | With `images.enabled` off, every screen shows initials and shields, `GET /api/media/team/{id}` is 404, and no API answer contains a provider image link |
| N3 | The API-Football key saved in Admin → Keys is not visible anywhere afterwards (masked), and not in `audit_log` or `app_logs` |
| N4 | **Run sync** on one league stops at `images.daily_calls`, says `done: false`, and the next run continues without repeating calls (compare the call counter) |
| N5 | In the review list, every row shows our name, the candidate name, the score and the candidate picture; Approve stores the picture, Reject removes it |
| N6 | Ten random players and all clubs of one league were checked by eye: no wrong face, no wrong crest |
| N7 | Take down one crest: it disappears from all pages at once and a second sync does not bring it back |
| N8 | Upload a PNG for a club: it shows. Uploading an SVG, a GIF or a text file renamed `.png` is refused |
| N9 | Images load lazily, keep their space (no layout jump), fall back to initials or a shield when blocked, and are readable in dark mode |
| N10 | Response headers on an image: `Cache-Control: public, max-age=31536000, immutable`, `ETag`, `nosniff`; a repeat visit with `If-None-Match` gets 304 |
| N11 | The footer shows `images.credit_text` when images are on |
| N12 | The owner has read API-Football's terms and has their written answer on storing and serving images on our plan. `images.players` stays off until then |
| N13 | The public app's CSP is `img-src 'self' data:` (plus `https:` only if `images.use_provider_urls` is on) |
