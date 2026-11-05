# 57. Every screen the app has

Built 2026-11-05 by reading the route tables, not from memory:
`frontend/src/App.js` (public), `frontend/src/pages/Account.jsx` (account sections),
`frontend/src/pages/Match.jsx` (match tabs), `backend/admin_shell.py` `MODULES` (admin, which is
server-defined and role-filtered), and `frontend/src/admin/AdminApp.jsx` `WITH_TABS` / `MOVED`.

**IDs are assigned by this document.** They are a stable way to refer to a screen in a brief, a bug
report or a test plan. They are not in the code, so nothing breaks if they are renumbered — but the
`data-testid` column is in the code, and that is what a test should target.

Counted from the route tables, not estimated:

| | count |
|---|---|
| public route entries | **42** |
| of those, screens | **37** |
| of those, redirects | **5** |
| account sections (inside `/account/*`) | 6 |
| match tabs (inside `/match/:id`) | 5 |
| admin modules | **33** |
| admin sub-tabs | 5 |
| overlays (not routes) | 6 |

There is no meaningful grand total: `/account/*` expands into its six sections and `/match/:id`
into its five tabs, so adding the columns double-counts them.

---

## 1. Public screens

| ID | Route | Screen | What it is | `data-testid` |
|---|---|---|---|---|
| P-01 | `/` | Today | The front page. The day's fixtures with their leading forecast cards, and a date scroller to move between days | `today-page` |
| P-02 | `/match/:id` | Match | One fixture. Five tabs, see §3 | `match-page` |
| P-03 | `/live` | Live scores | Fixtures in play, with scores ticking. **Never rendered in review** — the demo data has no live fixture (docs/56 note, and §7 below) | `live-page` |
| P-04 | `/insights` | Insights | The forecast feed across all fixtures, filtered by tier, market, likelihood, league, player and club | `insights-page` |
| P-05 | `/finder` | Forecast Finder | Ask for a specific line — any player, any market, any count — and get the answer off the stored ladder | `finder-page` |
| P-06 | `/explore` | Explore | Browse by league, club or market as an entry point | `explore-page` |
| P-07 | `/compare` | Compare | Two players or two clubs side by side | `compare-page` |
| P-08 | `/combos` | My combos | Lines the reader has collected into a combination, with the combined likelihood | `combos-page` |
| P-09 | `/leagues` | Leagues | Every league the app covers | — |
| P-10 | `/teams` | Leagues (same screen) | Clubs, entered through the league list | — |
| P-11 | `/league/:id` | League | One league: table, form, league averages, its fixtures | — |
| P-12 | `/team/:id` | Team | One club: squad, form, style, its fixtures and forecasts | — |
| P-13 | `/player/:id` | Player | One player: his record, his per-market history, his forecasts | — |
| P-14 | `/referees` | Referees | Every referee with cards and fouls per game | `referees-page` |
| P-15 | `/referee/:name` | Referee | One referee's history and tendencies | — |
| P-16 | `/following` | You | What the reader follows — clubs, players, leagues — in one feed | `following-page` |
| P-17 | `/track-record` | Track record | How the forecasts have actually done, by likelihood band. The page whose whole job is to show whether the numbers can be trusted | `track-record-page` |
| P-18 | `/search` | Search | Search across clubs, players, leagues and referees | — |
| P-19 | `/learn` | Learn | Article index | `learn-page` |
| P-20 | `/learn/:slug` | Learn article | One article | — |
| P-21 | `/pricing` | Plans | What a subscription costs and what each plan includes | `pricing-page` |
| P-22 | `/welcome` | Welcome | First-run introduction after signing up | `welcome-page` |
| P-23 | `/contact` | Contact us | Message form to the owner | `contact-page` |
| P-24 | `/legal/:slug` | Legal page | Terms, Privacy, About — owner-authored markdown | — |
| P-25 | `/account/*` | Account | Six sections, see §2 | — |
| P-26 | `/dev/kit` | DevKit | **Developer only.** Every component in every state, for design review. Not linked from the app | — |
| P-27 | `*` | Not found | Anything unmatched | — |

### 1.1 Sign-in and e-mail journeys

| ID | Route | Screen | What it is |
|---|---|---|---|
| P-28 | `/sign-in` | Sign in | Password, then the second factor when the account has one |
| P-29 | `/sign-up` | Sign up | Create an account |
| P-30 | `/verify-email` | Verify e-mail | Prompt to confirm the address |
| P-31 | `/confirm-email` | Confirm e-mail | Lands here from the link in the e-mail |
| P-32 | `/forgot-password` | Forgot password | Ask for a reset link |
| P-33 | `/reset-password` | Reset password | Set a new one from the link |
| P-34 | `/change-password` | Change password | **Forced** change on first sign-in when an owner set a temporary password |
| P-35 | `/enroll-2fa` | Set up two-factor | Enrol an authenticator |
| P-36 | `/unsubscribe` | Unsubscribe | Leave the mailing list from an e-mail link |
| P-37 | `/newsletter/confirm` | Confirm subscription | Double opt-in from an e-mail link |

### 1.2 Redirects (kept so old links still work)

| From | To |
|---|---|
| `/signup` | `/sign-up` |
| `/sign-in/2fa` | `/sign-in` |
| `/terms` | `/legal/terms` |
| `/privacy` | `/legal/privacy` |
| `/about` | `/legal/about` |

## 2. Account sections

`/account/*`, defaulting to `profile`. Test ids are `account-tab-<id>`.

| ID | Route | Section | What it is |
|---|---|---|---|
| A-01 | `/account/profile` | Profile | Name, e-mail, display preferences |
| A-02 | `/account/security` | Security | Password, two-factor |
| A-03 | `/account/devices` | Devices | Signed-in sessions, and ending them |
| A-04 | `/account/notifications` | Notifications | Which alerts and e-mails to receive |
| A-05 | `/account/plan` | Plan | Current subscription, invoices, cancelling |
| A-06 | `/account/privacy` | Privacy | Data export and account deletion |

## 3. Match tabs

One fixture, `/match/:id`. The first tab is **Live** while the match is in play and **Recap**
once it is final — the same slot, so a fixture never shows both (docs/34, docs/38).

| ID | Tab | What it is |
|---|---|---|
| M-01 | Live | In-play events and statistics, with cards tracking against the live score |
| M-02 | Recap | The same slot after the whistle: what happened, and how each forecast finished |
| M-03 | Forecasts | Every line for this fixture, grouped into cards. Carries a count badge |
| M-04 | Lineups | Confirmed or likely elevens. Shows a tick when confirmed |
| M-05 | Analysis | Team strength, style, the matchup, referee, context |

## 4. Overlays

Not routes — they open over whatever screen the reader is on, which is why they are easy to miss
in a review. `BottomSheet` is the shared container on a phone.

| ID | Component | What it is |
|---|---|---|
| O-01 | `ForecastSheet` | The full detail of one forecast: the ladder, the reasons, the band, the ten-game strip. **This is the "player insight pop-up"** |
| O-02 | `QuickView` | A compact peek at a card without leaving the list |
| O-03 | `FilterSheet` | Filters on Insights and the Finder, on a phone |
| O-04 | `LockSheet` | What a non-subscriber sees instead of a locked number |
| O-05 | `BottomSheet` | The shared sheet container the others sit in |
| O-06 | Visitor popup | Owner-authored, scheduled in Admin → Popups. **Never rendered in review** — it does not exist in demo data (§7) |

## 5. Admin

33 modules, nine groups (Overview, Football data, Forecasts, People, Marketing, E-mail, Money,
Website, System), at `/admin/*`. The list is **server-defined** in
`backend/admin_shell.py` and **filtered by role**: each module names the permissions that reveal
it, so two staff accounts see different menus. Rail test ids are `admin-rail-<id>`, and the `id`
column below is the module id in the code — for admin, unlike the rest of this document, the ID is
real.

| ID | Module id | Route | What it is | Permissions |
|---|---|---|---|---|
| AD-01 | `dashboard` | `/admin` | Home. The overview | `analytics.read` |
| AD-02 | `needs` | `/admin/needs` | Needs you. What is waiting on a human | `logs.read` |
| AD-03 | `analytics` | `/admin/analytics` | Analytics. Two tabs, §6 | `analytics.read` |
| AD-04 | `feeds` | `/admin/data/feeds` | Feeds. Which provider supplies what | `logs.read`, `jobs.run` |
| AD-05 | `pitchapi` | `/admin/data/pitchapi` | PitchAPI: history, depth, images. Three tabs, §6 | `jobs.run` |
| AD-06 | `sportapi` | `/admin/data/sportapi` | SportAPI: everything live | `logs.read`, `jobs.run` |
| AD-07 | `leagues` | `/admin/data/leagues` | Which leagues and seasons are covered | `jobs.run` |
| AD-08 | `jobs` | `/admin/data/jobs` | Background jobs: run, watch, retry | `jobs.run` |
| AD-09 | `engine` | `/admin/data/engine` | Run the engine, see runs and gates | `jobs.run` |
| AD-10 | `users` | `/admin/users` | Readers: accounts, plans, support actions | `users.read` |
| AD-11 | `staff` | `/admin/staff` | Staff accounts and roles | `staff.manage` |
| AD-12 | `inbox` | `/admin/inbox` | Messages from the contact form | `inbox.write`, `users.read` |
| AD-13 | `popups` | `/admin/popups` | Visitor popups: write, target, schedule | `popups.read` |
| AD-14 | `announcements` | `/admin/announcements` | Site-wide notices | `content.write` |
| AD-15 | `campaigns` | `/admin/campaigns` | E-mail campaigns | `email.write` |
| AD-16 | `newsletter` | `/admin/newsletter` | The mailing list | `email.read` |
| AD-17 | `templates` | `/admin/email/templates` | E-mail templates | `email.read` |
| AD-18 | `email_log` | `/admin/email/log` | Every e-mail sent | `email.read` |
| AD-19 | `suppressions` | `/admin/email/suppressions` | Blocked addresses | `email.read` |
| AD-20 | `plans` | `/admin/plans` | Subscription plans and prices | `plans.read` |
| AD-21 | `subscriptions` | `/admin/subscriptions` | Who is subscribed to what | `billing.read` |
| AD-22 | `payments` | `/admin/payments` | Payments and refunds | `billing.read` |
| AD-23 | `coupons` | `/admin/coupons` | Discount coupons | `billing.write` |
| AD-24 | `revenue` | `/admin/revenue` | Revenue over time | `billing.read` |
| AD-25 | `studio` | `/admin/studio` | Site Studio: theme, palette, copy, layout | `site.read` |
| AD-26 | `pages` | `/admin/pages` | Authored pages: Terms, Privacy, About, Learn | `content.write` |
| AD-27 | `media` | `/admin/media` | Images: logos, crests, player photos | `site.read` |
| AD-28 | `settings` | `/admin/settings` | Every setting. **The densest screen in the product** — 251 rows, and "All groups" renders them all | `settings.read` |
| AD-29 | `keys` | `/admin/keys` | Provider API keys | `settings.read` |
| AD-30 | `integrations` | `/admin/integrations` | Outbound webhooks and integrations | `integrations.read` |
| AD-31 | `logs` | `/admin/logs` | Application logs | `logs.read` |
| AD-32 | `security` | `/admin/security` | Sign-in attempts, sessions, audit | `security.read` |
| AD-33 | `health` | `/admin/health` | System health. Carries the open-alert count as a badge | `logs.read` |

`AdminApp.jsx` carries a **"Soon" placeholder** for any module in `MODULES` with no component in
its `SCREENS` map. Checked: **every one of the 33 has a component, so no module renders the
placeholder today.** The mechanism is worth knowing about, because adding a module to
`admin_shell.py` without adding a screen puts a live, empty menu entry in front of staff.

| ID | Route | Note |
|---|---|---|
| AD-34 | `/admin/*` | Not here. Unmatched, or a tool this role cannot use (`admin-not-found`) |

## 6. Admin sub-tabs

| ID | Route | Tab | What it is |
|---|---|---|---|
| AD-03a | `/admin/analytics/overview` | Overview | The analytics dashboard |
| AD-03b | `/admin/analytics/audience` | Audience | Who is reading |
| AD-05a | `/admin/data/pitchapi/usage` | Usage and cache | Calls made, cache hits |
| AD-05b | `/admin/data/pitchapi/quality` | Quality and mapping | **Where `minutes`, `tackles`, `fouls_committed`, `fouls_won` and `passes` are mapped** (docs/47) |
| AD-05c | `/admin/data/pitchapi/explorer` | Endpoint explorer | Call an endpoint and read the raw answer |

Old routes that now redirect: `/admin/stats` → `/admin/analytics/overview`,
`/admin/data/cache` → `…/pitchapi/usage`, `/admin/data/quality` → `…/pitchapi/quality`,
`/admin/data/explorer` → `…/pitchapi/explorer`.

## 7. Two screens that have never been seen

Carried forward from docs/52 and `UPDATE_29_PROMPT.md` §5, because an inventory that lists them
beside the rest would imply they have been reviewed, and they have not:

- **P-03 Live** and **M-01 Live tab.** The demo data has no live fixture — all twelve are scheduled
  or final — so in-play rendering has never appeared in any review or screenshot set. Wiring
  `backend/tests/live_mock.py` into `backend/tests/demo_server.py` would close it.
- **O-06 Visitor popups.** Admin-authored content that does not exist in demo data, so the reader's
  side of it is unreviewed.

Both are built. Neither has been looked at.
