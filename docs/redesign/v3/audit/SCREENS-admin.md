# Admin panel audit — 33 modules, 5 sub-tabs

Read against `backend/admin_shell.py` (the module list is server-defined and role-filtered),
`frontend/src/admin/*`, `backend/admin_home.py`, `backend/settings_registry.json`,
`frontend/src/styles/admin.css`, and the dark screenshots in `docs/redesign/v3/before/AD-*`.
Every page was also opened live against a throwaway demo server at 1440×900 and 390×844 and measured
(DOM node counts, page heights, rendered h1).

Judged on **speed and error-avoidance**, not beauty. This is an internal tool.

Scope note: the admin does **not** use `v2.css`. It defines its own token set at `.admin` scope in
`admin.css` (and a light variant at `.admin[data-admin-theme="light"]`), deliberately separate from the
visitor's Site Studio theme. Colour discipline is already clean — there is **not one literal hex in any
file under `frontend/src/admin/`**; the only hex in the admin CSS is in the two token blocks themselves,
which is where it belongs. Every recommendation below therefore spends tokens that already exist.

---

## Top 10 changes, ranked

| # | Change | Where | Why |
|---|---|---|---|
| 1 | **Make "never ran" and "ran too long ago" red.** `admin_home.py:_tone()` colours the Data tile by budget use alone and the Engine tile by last-run *status* only. `(run or {}).get("status")` is `None` when the engine has never run, which falls through to `"green"`. The screenshots prove it: AD-01 shows "Engine · Run never · 358 forecasts" badged **OK**, and "Data · sync never" badged **OK**, while AD-33 Health on the same data says *"No background job has run in the last 3 hours."* | `backend/admin_home.py` `tiles()` | A dead feed uses zero calls, so the one tile that watches the feeds paints a dead feed green. This is the single largest error-avoidance defect in the product: the home screen actively reassures you while the pipeline is stopped. |
| 2 | **One alert count, one source of truth.** The rail badge on Health reads `db.admin_alerts.count_documents({"resolved": False})` (growth/money alerts). AD-33 renders *two* cards both called alerts: `h.alerts` (computed health checks) and `/admin/alerts` (the stored ones). In the captured state the rail badge is **0**, the stored list is **empty**, and the computed list has **two warnings**. Fold the computed checks into the same count and badge. | `admin_shell.py:shell()`, `SecurityHealth.jsx`, `Home.jsx` | Three screens disagree about whether anything is wrong. An owner learns to ignore all three. |
| 3 | **Give AD-28 Settings a sticky filter bar with a "Changed" toggle, and virtualise or collapse the list.** 252 rows render as **38,825 px on desktop and 68,964 px on phone** — 43 and 82 screens. The search box is in normal flow and scrolls away after ten rows. | `Settings.jsx`, `admin.css` | Finding one setting is the job; the screen makes it a scroll. Detail and the full design in §AD-28. |
| 4 | **Let AD-05b fix the mapping it diagnoses.** The Mapping check reports `missing: [minutes, tackles, …]` and then tells you in prose to go to Settings, group Provider. Those three settings (`provider.pitchapi.team_keys`, `provider.pitchapi.player_keys`, `provider.position_map`) are nested JSON blobs in an 8-row textarea among 252 rows. Put a per-column key picker in the result card, writing the same `PUT /admin/settings/{key}`. | `Quality.jsx` `Mapping()` | The brief is right that a wrong mapping silently corrupts forecasts. The repair loop today is: read result → leave the screen → scroll → hand-edit JSON → come back → re-paste the fixture → re-run. Each step is a chance to get it wrong, and nothing verifies the fix except running it again. |
| 5 | **Grade the guards by cost, not by habit.** Today a 1-call job and a ~1,140-call backfill share one dialog, while `POST /admin/sportapi/tick`, `POST /admin/sportapi/backfill`, `POST /admin/images/sync`, `POST /admin/integrations/audience/backfill`, popup **go live**, Studio **Discard** / **Reset section**, and webhook **New secret** have no dialog at all. Full inventory in §3. | 9 files | A guard that is the same everywhere teaches people to click through it, which is worse than no guard. |
| 6 | **Put every tab in the URL.** AD-03 and AD-05 do it correctly with `useParams`/`useNavigate`. AD-09 Engine (7 tabs), AD-25 Studio (9), AD-31 Logs (8), AD-12 Inbox (6) and AD-05b's own second tab row (3) use `useState`. `/admin/data/pitchapi/quality` therefore always lands on **Issues** — the mapping tool the brief names cannot be linked to at all. | `Engine.jsx`, `Studio.jsx`, `Logs.jsx`, `Inbox.jsx`, `Quality.jsx` | A tab you cannot link is a tab you cannot put in a runbook, a bug report or an e-mail at 3am. Back behaves differently on five screens than on two. |
| 7 | **Stop rendering buttons the signed-in role cannot use.** `admin_home.py:needs()` gates the whole list on `logs.read`, but image approve/reject needs `jobs.run`, "Run again" needs `jobs.run`, issue resolve needs `jobs.run`, and alert "Mark fixed" needs `settings.write`. `support` and `analyst` both have `logs.read` and neither of those. They get buttons that always 403. | `admin_home.py:needs()`, `Home.jsx` `NeedItem` | Admin is role-filtered by design (`PERMS` in `accounts.py`); the Needs list is the one place that forgot. |
| 8 | **Give `support` a landing page.** `support` lacks `analytics.read`, so module `dashboard` is filtered out, so no route matches `/admin`, so signing in lands on `admin-not-found` — *"This tool does not exist or your role cannot use it."* The rail's own "Control room" brand link points at `/admin` too, so it is permanently dead for them. Redirect `/admin` to the first module the role can see. | `AdminApp.jsx` | A whole staff role's front door is a 404. |
| 9 | **Put the engine's run button on the Engine screen.** AD-09's stated purpose is "Run the engine, see runs and gates". There is no run call anywhere in `Engine.jsx`; running it lives on AD-08 Jobs. The default tab is instead four settings rows cloned from AD-28. | `Engine.jsx` | The screen named after the action cannot perform it, and opens on the least urgent thing it holds. |
| 10 | **Mark destructive buttons as destructive.** `btn--danger` appears exactly once in the whole admin (Cache → Delete all). Delete an image, remove a list member, take an image down, discard a draft, reset a section, switch off a coupon, unblock an address, remove a key — all `btn--ghost`, visually identical to "History" and "Preview". | all screens; `admin.css` already defines `btn--danger` | The class exists and is unused. This is the cheapest error-avoidance win in the audit. |

---

## Every module

Verdict counts over the 39 rows below: **good 18 · needs work 14 · broken 4 · should not exist 3**.

The verdict judges the screen as built. It is not the same question as "should this be a module" — §5 also
proposes merging AD-23, AD-24 and AD-19 away, and those three are fine screens.

| ID | Module | Purpose in one line | Verdict | Single most valuable change |
|---|---|---|---|---|
| AD-01 | `dashboard` | Six health tiles plus the top eight Needs items — the screen the owner opens first. | **broken** | Make tile tone depend on *age* and not only on budget-use and last-run status: "Run never" and "sync never" must not read OK (§AD-01). |
| AD-02 | `needs` | Everything waiting on a person: clubs to match, images, failed jobs, alerts, ingest issues, inbox. | **should not exist** | It is `<NeedsList q={useApi("/admin/home")} />` — the same component on the same endpoint as AD-01's block, minus `limit={8}`. Delete the module; make AD-01's "See all N" expand in place. Keep the route as a redirect. |
| AD-03 | `analytics` | Two tabs over the visitor numbers. | needs work | The parent renders only a `PageHead` and a `Tabs`; the period/export controls appear and vanish between tabs. Move the period control into the Audience tab's own body so the head stops reflowing. |
| AD-03a | — | Overview: people, active, sign-ups, views, MRR, churn, two bar charts, an alerts card. | **should not exist** | Every number here is already on AD-01 or AD-33, and its alerts card is the same `AlertList` on the same `h.alerts` as AD-33. Fold the two charts into Audience and drop the tab. |
| AD-03b | — | Audience: realtime, period-vs-period, sources, list growth, e-mail health, popups, CSV export. | good | Six independent `useApi` calls fire at once with six independent spinners; give the card grid one skeleton so the page stops jumping. |
| AD-04 | `feeds` | Both providers side by side, plus a symptom → feed table. | good | Its two "Open PitchAPI / Open SportAPI" buttons and its help table point at routes that `support` and `analyst` cannot open (`jobs.run`). Hide the link when the module is absent from `shell.modules`. |
| AD-05 | `pitchapi` | Three tabs: usage and cache, quality and mapping, endpoint explorer. | needs work | Tab one is in the URL and tab two's own three tabs are not, so the two rows of identical blue pills are different kinds of thing (§AD-05b). |
| AD-05a | — | Calls today vs budget, 14-day chart, by purpose and status, breaker, cache table. | good | 3,787 px desktop / 9,468 px phone because the 50-row cache table has no collapse. Put the cache table behind a `<details>` — the usage numbers are what people come for. |
| AD-05b | — | Ingest issues, league × field coverage matrix, and the provider field-mapping check. | **broken** | Make the mapping check write the mapping (top-10 #4), and put its sub-tab in the URL so `/…/quality` can land on it. |
| AD-05c | — | Run one allowed PitchAPI call through the cache, see cached-or-real and the cost. | good | Best-guarded screen in the admin: cached by default, "Force refresh" confirmed with the exact cost, "From cache"/"Real call" chip on the result. Only gap: no history of what you ran. |
| AD-06 | `sportapi` | Live provider: status, calls, fixture matching, live stats, league mapping, team review, backfill. | needs work | Six cards, 279 lines, 2,674 px on phone, and the two quota-spending buttons (`tick`, `backfill`) have no confirm while the identical action on AD-08 does. Add the confirm and split the screen with a tab row. |
| AD-07 | `leagues` | Switch leagues on, pick seasons to backfill, see coverage and the call estimate. | needs work | "Refresh league list" posts `jobs/run?job=reference_sync` **with no confirm**, and AD-08 confirms the same job. Also: the on/off switch commits a recurring daily cost with no estimate, while the estimate exists one drawer deeper. Show the per-league daily call cost next to the switch. |
| AD-08 | `jobs` | Last run per job, queue, lock state, manual runs, recent runs. | needs work | Scale the guard to the job: the confirm body is the same sentence for a 1-call sync and a season backfill (§AD-08). |
| AD-09 | `engine` | Seven tabs: switches, runs, forecasts, brain layers, availability, calendar import, images. | needs work | Add the run button, default to Runs, put the tab in the URL (§AD-09). |
| AD-10 | `users` | Search and filter readers; a drawer with thirteen support actions. | good | Three of those actions send real e-mail to a real person (`send-reset`, `resend-verification`) or sign them out everywhere, with no dialog at all, while "Add note" opens one. Add a confirm to the three that touch the member. |
| AD-11 | `staff` | Staff list with 2FA state, owner-only invite, and the role × permission matrix. | good | The matrix is a raw `<table>` in `.a-matrix` with `overflow:auto`; on a phone only three of five role columns fit and the permission name scrolls away. Make the first column sticky. |
| AD-12 | `inbox` | Contact-form messages with a status and a private note. | good | Status tabs are `useState`, so you cannot link "the spam queue". Put the status in the URL. |
| AD-13 | `popups` | Write, target, schedule and A/B visitor popups, with a live preview. | needs work | Setting a popup **live** — which shows a modal to every matching visitor — has no confirm, while deleting a draft does. Invert that. |
| AD-14 | `announcements` | Site-wide notices with a date window. | **should not exist** | A popup with `kind: banner_top` and no targeting is an announcement. Merge into AD-13 as a template; two modules maintain two schedulers for one idea. |
| AD-15 | `campaigns` | One-off e-mails to people who opted in. | needs work | The send guard is right (`typed="SEND"`, `danger`). Nothing else is: no recipient count before sending, no preview, no test send, and the HTML body is a bare 10-row textarea — while AD-17 Templates, which sends to nobody, has preview *and* "send test to me". Give Campaigns the Templates editor. |
| AD-16 | `newsletter` | The confirmed mailing list, counts, filter, CSV export, remove-with-suppression. | good | Export silently needs `users.pii`; the error is only discovered on click. Disable the button for roles without it. |
| AD-17 | `templates` | The messages the site sends; edit, preview, test-send, reset. | good | "Reset" wipes a customised template back to default with no dialog, sitting in the same ghost row as "Preview". Confirm it. |
| AD-18 | `email_log` | Every e-mail attempted, with a plain-English reason for each skip. | good | The clearest table in the admin. Nothing needed. |
| AD-19 | `suppressions` | Bounced, complained and unsubscribed addresses. | good | A filtered view of AD-18 with one extra action; fine as a module, but it is the first candidate to merge if the menu is cut. |
| AD-20 | `plans` | Plan cards with subscriber counts; a drawer for entitlements and prices. | needs work | The header comment says Stripe sync "stays disabled until phase 4b" but `SyncButton` renders live and unguarded, and it creates real Stripe prices. Either disable it or confirm it. |
| AD-21 | `subscriptions` | Who pays, on what, when it renews; cancel and resume. | good | Nothing needed. |
| AD-22 | `payments` | Every charge; partial or full refund with a required reason. | good | `billing.live_refund` is an owner-only permission the UI never checks, so `billing.write` roles see an enabled Refund in live mode and learn otherwise from a 403. Check it client-side too. |
| AD-23 | `coupons` | Percentage discount codes. | needs work | Four fields and a list. Make it a card inside AD-20 Plans; it does not earn a menu entry. |
| AD-24 | `revenue` | MRR, collected, refunded, per currency. | needs work | Duplicates the revenue block on AD-03a and AD-01's Money tile. Keep the module but make it the only place revenue is stated. |
| AD-25 | `studio` | Theme, palette, copy and layout as a draft, with a preview and publish. | needs work | The two irreversible buttons ("Discard", "Reset section") are the only *enabled* buttons in the save bar when nothing has changed, and neither confirms (§AD-25). |
| AD-26 | `pages` | Terms, Privacy, About, Learn as Markdown with a preview. | good | Nothing needed. |
| AD-27 | `media` | Uploaded site images: upload, copy address, delete. | good | Renders every asset with no pagination and no search. Fine at today's volume; add a filter before it passes ~100. |
| AD-28 | `settings` | All 252 settings, grouped, searchable, typed, resettable, with history. | **broken** | Sticky filter bar, a "Changed only" toggle and collapsed-by-default groups (§AD-28). |
| AD-29 | `keys` | Provider API keys, write-only, owner-only to change. | good | Model screen: never returns the key, masks it, "Test" before you trust it, removal confirmed with the consequence stated. Leave alone. |
| AD-30 | `integrations` | E-mail provider, list sync, outbound webhooks, tracking tags. | needs work | "Send everyone now" pushes the whole confirmed list to an external tool and "New secret" instantly breaks a live webhook — both unguarded ghost buttons; Delete beside them is guarded. |
| AD-31 | `logs` | Eight log sources, time range, paged, with PII masked server-side. | good | Eight `useState` tabs plus a range filter, none in the URL, on the one screen whose whole purpose is quoting a row to someone else. Put `kind`, `since` and `page` in the query string. |
| AD-32 | `security` | 24 h of failed sign-ins, locks, rate limits, staff 2FA, recent staff actions. | good | "Last staff actions" renders raw `KV` dumps of each audit row. Give it the same `ResponsiveTable` the rest of the screen uses. |
| AD-33 | `health` | Database, last job, breaker, API and e-mail budgets, webhook and server errors, queue. | **broken** | Two cards named for alerts, from two different sources, and neither feeds the rail badge (§AD-33). |
| AD-34 | — | Unmatched route, or a tool this role cannot use. | needs work | It conflates "typo" with "your role cannot use this", and it is what `support` sees at `/admin`. Split the two messages and list the modules the role *can* open. |

---

## Deep reads

### AD-01 Home — the tiles lie by omission

What is right: six tiles on one row-and-a-half, each a link to the module that owns the problem; a
plain-English line under each; a budget bar with the reset time; and the Needs list immediately below,
with the action on the item rather than behind a navigation. That shape is correct and should survive.

What is wrong:

1. **Tone ignores time.** `_tone(used, cap)` is `red ≥ cap`, `amber ≥ 0.8 cap`, else `green`. A feed that
   has stopped uses *no* calls, so a stopped feed is the greenest thing on the screen. The Engine tile is
   `red` only if the last run errored and `amber` only if an engine run errored in the last 24 h — a
   never-run engine and an engine that last ran nine days ago are both green. The captured screenshot
   shows exactly this: "sync never" and "Run never", both badged **OK**.
   Fix: add a staleness term. `data` amber when the last successful `fixtures_sync`/`results_sync` is older
   than two ticks and red when older than an hour; `engine` amber over 24 h and red over 48 h, with
   "never" treated as red, not as absent.
2. **It disagrees with AD-33.** Same moment, same data: Home says nothing needs you, Health says no job has
   run in three hours. `h["alerts"]` is already computed by `AQ.health()` and is already on the home payload
   via the Money tile's `webhook_errors_24h`. Surface the same list on Home.
3. **"Needs you · N" is not N.** `needs()` caps match review at 20, images at 20, issue *groups* at 20, and
   silently drops the rest. The heading counts what came back. 300 open ingest issues read as 20.
4. **No order of severity.** The list is built in source order — team matching, then images, then failed
   jobs, then alerts, then issues, then inbox. A failed engine run sits below twenty player-photo
   approvals. Sort by kind weight first (alert, job, issue, match, image, inbox) and by age second.
5. **Dismissal is a lie.** `NeedsList` keeps a local `gone` array. Reload and the item is back; and acting
   on an item removes it from the list without reloading `q`, so the count above it is now wrong.
6. **It is a single fetch.** `useApi("/admin/home")` with no `every`. Only AD-04 Feeds polls (60 s). A Home
   tab left open overnight shows last night's green. Either poll at 60 s like Feeds, or stamp the tiles
   with "as of HH:MM" so stale is visible.
7. **Space.** At 1440×900 the content ends 420 px above the fold with an empty half-screen below. On the
   one screen that should carry the most information, half the laptop is blank.

### AD-02 Needs — the same list twice

`Needs()` is `PageHead` + `<NeedsList q={useApi("/admin/home")} />`. `AdminHome` is tiles +
`<NeedsList q={useApi("/admin/home")} limit={8} />`. One component, one endpoint, two menu entries, two
rail rows, one of the four default phone tabs. The only difference is the eight-item cap, and AD-01
already has "See all N" to lift it.

It also inherits every defect above, plus one of its own: it renders action buttons that the role reading
it cannot use. The list is gated on `logs.read`; approve/reject/run/resolve need `jobs.run`; "Mark fixed"
needs `settings.write`. `support` = `{users.*, billing.read, email.read, logs.read, inbox.write, plans.read}`
and `analyst` = `{analytics.read, users.read, billing.read, logs.read, plans.read, email.read, popups.read}`
— both see the list, neither can act on four of its six kinds.

Recommendation: delete the module, redirect `/admin/needs` → `/admin`, make "See all" expand in place, and
filter each need kind by the viewer's permission in `needs()` rather than in the component.

### AD-28 Settings — a search problem, as the brief says

Measured: **252 rows, 25 groups, 4,028 DOM nodes under `.a-main`, 38,825 px at 1440 wide and 68,964 px at
390 wide.** Engine alone is 85 settings (34%); Features 24; Live (SportAPI) 19; Ingest 14; Auth 12; Email 12.
Seven groups have three settings or fewer.

What already exists and is good: a text search over key + label + help; a group `<select>`; typed inputs per
`type`; `Reset to default` per row; a `History` drawer; a `changed` chip; and a provenance line
(`Default: … · changed by X on DATE`). The ingredients are all here. The assembly is wrong.

Concrete problems, each with its own fix:

1. **The filter bar is not sticky.** `.a-filters` is a plain flex row in normal flow. After ten rows the only
   way to refine is to scroll 38,000 px back. → `position: sticky; top: 60px` (the `.a-top` height), with
   `background: var(--surface1)` and the existing `--border` underline. One CSS rule, biggest single win.
2. **No "changed only" filter.** The data is already on every row (`s.is_default`), and a `changed` chip is
   already rendered. There is no way to ask the one question an owner actually asks — *what have we changed?*
   → Add a three-state segmented control beside the group select: **All · Changed · Default**. In the captured
   demo that would cut 252 rows to a handful.
3. **No recently-changed view.** `GET /admin/settings/{key}/history` exists per key, so the history rows exist;
   there is no list across keys. → Add `GET /admin/settings/history` (newest 25 across all keys) and render it
   as a collapsed "Changed lately" card above the groups: *key · old → new · who · when · Undo*. That card is
   the answer to "the site started behaving differently on Tuesday" and there is no answer today.
4. **Diff-from-default is per-row prose.** `Default: true` is a 12 px `<small>` under four other lines. →
   When a row is not default, render the pair inline on the value side — `was <code>0.01</code> → now
   <code>0.03</code>` — and keep the long provenance in the History drawer where it belongs.
5. **Groups are always fully expanded.** 25 `<section>`s, all open, all 252 rows in the DOM. → Collapse every
   group to a header row carrying `name · n settings · k changed`, and open only the group that matches the
   current filter, or the one the URL names. Keep the "All groups" option but make expanded-all an explicit
   choice, not the default. If a group must stay open at 85 rows (Engine), virtualise it.
6. **No deep links to a row.** Five screens tell you in prose to "change it in Settings (group Provider)" —
   AD-05b, AD-04, AD-08's Extras card, AD-09's Switches card, AD-30. None of them can link. → Read the group
   and a `key` from the URL (`/admin/settings?group=Provider#provider.pitchapi.player_keys`), scroll to the
   row and flash it. Then every one of those five prose instructions becomes a link.
7. **The enum renderer silently degrades.** `enumOpts()` looks for a `|` in `help.split(".")[0]`. Ten settings
   are `type: "enum"`; only **six** match. The other four — `engine.feed_sort`, `engine.feed_group`,
   `engine.lift_scale` and **`billing.mode`** — render as a free-text box. The setting that puts real money
   into live mode is a text field whose legal values are buried in a sentence. → Add an `options` array to
   the registry and read that, instead of parsing prose.
8. **35 settings are raw JSON textareas**, including `provider.pitchapi.player_keys`, `engine.player_ladder`,
   `engine.markets_enabled`, `copy.strings` and `copy.market_labels`. The whole public copy of the site and
   the engine's ladders are hand-edited JSON with "That is not valid JSON." as the only feedback. → Give the
   three or four shapes that recur (a string map, a key list, a numeric ladder) a small typed editor; leave
   the genuine one-offs as JSON but show the parse error against the line.
9. **`owner_only` is dead code.** `Settings.jsx` draws a padlock and makes a row read-only when `s.owner_only`;
   **zero of the 252 registry entries set it.** Meanwhile the UI never checks `settings.write` at all, so a
   read-only role sees 252 enabled Save buttons and finds out on click. → Drop `owner_only` or populate it,
   and disable the inputs when the viewer lacks `settings.write`.
10. **`applies_at` has four spellings for two meanings** — `next_engine_run` (51) and `next engine run` (24)
    are the same thing. The chip hides it because the component does `.replace(/_/g, " ")`. Normalise the
    registry; the chip is load-bearing (it tells you whether the change takes effect now or at the next run).
11. **138 of 252 settings have no `help` at all.** For those the owner has a label, a dotted key and nothing
    else. That is the real search problem underneath the layout problem: you cannot search for what a setting
    does if nobody wrote down what it does.
12. **Every save refetches all 252 rows** (`onSaved={q.reload}`), and the row key is
    `s.key + JSON.stringify(s.value)`, which remounts the row and drops focus. Patch the single row instead.

**The shape I would build:** a sticky bar holding `search · group · All/Changed/Default`; under it a
collapsed "Changed lately" card; under that 25 collapsed group headers with counts. Typing in search expands
only matching groups and shows the matching rows. A boolean renders as one line with the switch on the right
— not a 114 px two-column block with a disabled Reset and a History button. That alone removes roughly two
thirds of the height, before any filtering.

### AD-33 Health — the screen you check at 3am, and it has three answers

The captured state: **Alerts** card shows two amber warnings ("No background job has run in the last 3 hours.
Check the scheduler ping." and "1 staff account(s) have no two-factor sign-in."); **Growth and money alerts**
card shows "No open alerts."; the rail badge beside Health shows nothing.

Three problems:

1. **Two cards, both about alerts, from two different places.** `h.alerts` is computed live by
   `AQ.health()`; `/admin/alerts` reads the stored `admin_alerts` collection, which is what gets e-mailed and
   what the rail badge counts. Nothing on the screen explains that one is "checks we just ran" and the other
   is "problems we recorded and mailed you about". Rename them to say so, and make the rail badge count both.
2. **Neutral tiles hide the worst state.** "Last job · None yet" carries no `tone`, so it renders with the
   same neutral bar as "People · 7". "API calls today 368 / 2,000" only turns red at 90 %; "Server errors 24 h"
   only at >5. The eye scans a wall of green and neutral and concludes fine. "Last job" in particular must be
   red when it is older than two ticks — it is the single number that says whether anything at all is running.
3. **The 3am path is e-mail, and e-mail can be capped.** "it is e-mailed to owners and admins" is the stated
   escalation. The same screen shows "E-mails today 0 / 100". When the cap is reached the alert e-mail is
   skipped — the skip reason lands in AD-18 as `skipped_cap` and nowhere else. An alert that can be silently
   suppressed by an unrelated counter is not an escalation path. At minimum, exempt alert e-mails from the
   cap and show "alerts are being skipped" on this screen when they are.

Minor: "Check now" calls `POST /admin/alerts/run` with no confirm, which is correct — it is cheap and
idempotent. That is the right calibration, and the rest of the admin should match it rather than the reverse.

### AD-08 Jobs — six buttons, one guard, no sense of cost

The layout is sound: a tick state, a queue, six job cards, recent runs. Three things are wrong.

1. **Cost is not in the guard.** `Confirm` body is `${hint} Calls count toward today's budget.` for all six.
   The hints are honest on their own ("1 call", "1 call per league that is on") but the dialog never states a
   number, and **Backfill** — which AD-07 itself estimates at `1 + matches × 3` calls per season, roughly 1,140
   for a 380-match season — gets the same sentence as the 1-call league sync. → Compute the estimate server-side
   per job and put it in the dialog: *"About 1,140 calls. Today's budget is 2,000, of which 368 are used. This
   will take 1 day."* AD-07's season drawer already does exactly this; copy its wording.
2. **The dead scheduler is invisible on the screen that owns it.** The tile reads "Tick · Idle · No tick in
   progress" in neutral, all six jobs read "Never run", and AD-33 is simultaneously warning that nothing has run
   for three hours. Jobs is where you would go to check. → "Idle" is fine; "no tick in the last N minutes" is an
   error state and must be red here, with the last tick time.
3. **The Extras card is first.** "Referees, cards and substitutions" sits above the tiles and the job cards,
   and its "Queue missing matches" button — which queues an unbounded number of PitchAPI calls — is the only
   top-right action on the screen and has no confirm. Move the card below Recent runs and guard the button.

Also: `requests` are shown as a count ("Waiting requests 0") but never listed, so a queued manual run is
invisible except as the disabled state of the button that queued it.

### AD-09 Engine — the screen that cannot run the engine

Seven tabs, none in the URL, defaulting to **Switches**. Three findings:

1. **No run.** `Engine.jsx` contains no `jobs/run` call. The purpose line in the inventory says "Run the
   engine, see runs and gates". Running happens on AD-08. → Put a guarded "Run the engine now" in the page
   head, showing which leagues are on and how many forecasts the last run produced, and default the screen to
   **Runs**.
2. **The default tab is four cloned settings rows.** `Switches` reuses `SettingRow` from AD-28 for
   `engine.absence_model`, `engine.match_context`, `engine.calibration` and `context.start_model`. Reusing the
   component is right. Opening on it is not: these are set once and left alone, while "did it run, and what
   came out" is the daily question.
3. **Three toggles change every public percentage, with no confirm and no blast radius.** Turning
   `engine.calibration` off makes the site show raw likelihoods instead of calibrated ones to every reader at
   the next run. The screen says "Each change applies when the next engine run starts" — correct and useful —
   but says nothing about how many current forecasts that is. → Add the count: *"Affects 358 current forecasts
   at the next run."* The `Calibration` card below already does this well for the rollback ("New forecasts use
   the shipped map from the next engine run"), so the pattern exists one card away.

Credit where due: `Forecasts` → Hide is the best-guarded action in the admin — `danger`, a **required**
reason, the consequence spelled out, and the stored reason/by/at shown when unhiding. That is the model the
other destructive actions should copy.

### AD-25 Site Studio — good model, dangerous save bar

The draft → preview → publish → version → rollback model is right, and the publish conflict check
(`PUBLISH_CONFLICT` → "Someone published a newer version" → "Override and publish" as a `danger` button) is the
most careful piece of interaction design in the product. Keep all of it.

1. **The save bar's only live button is the destructive one.** With nothing changed, "Save to draft" and "Undo
   changes" are disabled and **"Reset section"** is enabled — the captured screenshot shows two greyed buttons
   and one bright one. It posts `/admin/site/draft/{section}/reset` with no dialog. "Discard" (the whole draft)
   also has no dialog, and neither does applying a theme **preset**, which overwrites the entire theme section.
   → Confirm all three. Reset and Discard are not recoverable from the Versions drawer, because the drawer only
   holds *published* versions; an unpublished draft that is discarded is gone.
2. **The editor is reflection over JSON.** `Node`/`Leaf` walk the draft object and label each field with
   `key.replace(/_/g, " ")`. That is why the Brand tab reads "Og image" and "Logo light". There is no field
   order, no grouping, no help, no indication of what is required. Whatever shape the server sends is the form.
   → Drive the form from `d.meta` with a per-field label, help and order, as the registry does for AD-28.
3. **Colour fields are detected by regex on the value.** `isHex(v)` matches `/^#[0-9a-fA-F]{6}$/`. A palette
   entry that is `transparent`, a 3-digit hex, or `rgb(…)` falls through to a plain text box with no swatch.
   → Type the field in `meta` rather than sniffing the value.
4. **No contrast check.** The owner is choosing foreground and background pairs for the whole public site in a
   `<input type="color">` grid, and nothing tells them when a pair fails. → Show the contrast ratio beside each
   text-on-surface pair and flag below 4.5:1. This is a one-function addition and it protects every reader.
5. **The preview is an imitation.** The `Preview` component is a hand-built mock — one insight card, three
   buttons, a fake nav — not the real site. It cannot show what custom CSS does, or how the palette reads on a
   real Today page. The honest preview is the "Preview link" button, which opens the real site with a token,
   and it is styled as a secondary action next to a 300 px mock. → Promote the preview link, and label the mock
   "Sample" so nobody treats it as proof.
6. **Nine section tabs on a phone.** `.tabs` is `overflow-x: auto` with `scrollbar-width: none`, so on the 390 px
   capture the strip reads "Brand Look Buttons Menus Foo" and nothing indicates that SEO, Cookie banner, Home
   page and Custom CSS exist. → Add a right-edge fade. This applies to AD-09 (7), AD-31 (8) and AD-12 (6) too.

### AD-05b PitchAPI → Quality and mapping — the highest-stakes screen is the hardest to reach

The brief is right about the stakes: `provider.pitchapi.player_keys` is what turns the provider's JSON into
`minutes`, `tackles`, `fouls_committed`, `fouls_won` and `passes`, and a wrong entry produces zeros that the
engine treats as real. Five problems, in order of cost:

1. **It diagnoses but cannot repair.** `POST /admin/mapping/check` returns `missing`, `unmapped_positions`,
   `mapped` and `available` (every key the provider actually sent, with its group and its home/away value).
   Everything needed to fix the mapping is on screen. The screen then says, in prose, *"Change the mappings in
   Settings (group Provider)"*. → Put a `<select>` on each missing column, populated from `res.available`, and
   a "Save mapping" that writes the same `PUT /admin/settings/provider.pitchapi.player_keys`. Re-run the check
   automatically afterwards and show green. That turns a six-step cross-screen loop into two clicks, and makes
   the fix verifiable at the moment it is made.
2. **It cannot be linked to.** The outer tab is in the URL (`/admin/data/pitchapi/quality`); the inner three
   are `useState` defaulting to **Issues**. So the route named "quality" never lands on the mapping tool, and no
   runbook, bug report or e-mail can point at it. Two clicks deep, zero addressability.
3. **Two rows of identical pills at two different levels.** The captured screenshot shows
   `Usage and cache / Quality and mapping / Endpoint explorer` directly above `Issues / Coverage / Mapping check`,
   same size, same radius, same blue active state. Nothing says one changes the URL and the other does not. →
   Make the inner row a segmented control or an underline tab, and put it in the URL.
4. **Its own links leave the screen and lose your work.** The help paragraph links to `/admin/data/explorer`
   and `/admin/data/cache` — the pre-`docs/43` routes, which still work through `MOVED` but land on a sibling tab
   of the *same* screen, unmounting the form and discarding whatever JSON you pasted. → Link to the current
   routes, and keep the pasted fixture in state across tab changes.
5. **Coverage and Mapping do not talk to each other.** The Coverage matrix marks a cell `is-low` when a field's
   share is under the minimum — which is exactly the symptom of a bad mapping (AD-04's own help table says so:
   *"A statistic reads zero for everyone → PitchAPI — the field mapping on its Quality tab"*). → Make a low cell
   clickable, straight into the mapping check for that field.

---

## The five questions

### 1. Does the owner know what needs doing?

**No, and worse: the panel tells him everything is fine while it is not.**

In the captured state, at the same moment, on the same data: AD-01 Home shows six tiles, five badged **OK**
and one **Off**, and "Needs you · 0 — Nothing needs you right now." AD-33 Health shows *"No background job has
run in the last 3 hours. Check the scheduler ping."* The rail badge that is supposed to surface open alerts
shows nothing, because it counts a different collection. The Engine tile reads "Run never" and is green; the
Data tile reads "sync never" and is green. The cause is in `admin_home.py`: tile tone is a function of budget
use and last-run *status*, never of time, so a stopped pipeline — which by definition uses no quota and logs no
errors — is the greenest state the screen can show.

AD-01 and AD-02 are the same list twice, so judging them together is literally judging one component. Its
behaviour is good — the action is on the item, the wording is plain, the empty state is a tick — and its
accounting is not: it silently caps each kind at 20, orders by source code rather than severity, shows a count
that is the capped number, forgets dismissals on reload, and renders buttons that `support` and `analyst` will
always be refused.

**At 3am the panel does nothing.** It is a pull surface with no polling except AD-04 (60 s). The only push is
`alerts.py` e-mailing owners and admins — and that e-mail passes through the same daily cap the Health screen
reports as "E-mails today 0 / 100", so a busy day can swallow the alert and record it as `skipped_cap` in AD-18.
There is no SMS, no webhook on alert (the webhook events are product events, not health events), and no
unacknowledged-alert escalation.

Minimum to fix, in order: (a) make tone time-aware so "never" and "stale" are red; (b) one alert count shared by
the Home tiles, the Health cards and the rail badge; (c) exempt alert e-mail from the cap and say on AD-33 when
alerts are being skipped; (d) poll Home at 60 s or stamp it "as of HH:MM"; (e) add a webhook event for open
alerts so the owner can route them to a phone — AD-30 already has the delivery machinery.

### 2. AD-28 Settings

Right design, concretely: a **sticky** filter bar (`search · group · All/Changed/Default`) pinned under the
60 px top bar; a collapsed **"Changed lately"** card above the groups, fed by a new cross-key history endpoint,
each row `key · old → new · who · when · Undo`; the 25 groups **collapsed by default** to a header carrying
`name · n settings · k changed`, expanding on search match or on a URL fragment; **deep links** so the five
screens that today say "change it in Settings, group Provider" can link to the row and flash it;
**diff-from-default inline** on the value side (`was 0.01 → now 0.03`) with the long provenance moved into the
History drawer; **one-line rows for booleans** instead of 114 px two-column blocks with a disabled Reset and a
History button; `options` in the registry so the **four enums that currently render as free text** — including
`billing.mode` — become selects; small typed editors for the recurring JSON shapes so the field mapping and the
site copy stop being hand-edited blobs; and `settings.write` checked client-side so a read-only role does not
see 252 enabled Save buttons. Write the 138 missing `help` strings — that is the actual search problem under
the layout problem.

### 3. Dangerous actions

Every destructive or expensive action, with its guard today:

| Action | Cost | Guard today | Proportionate? |
|---|---|---|---|
| Cache → **Delete all** | every later call is a real call | `danger` + typed `DELETE` | yes |
| Users → **Delete their data** | irreversible | `danger` + typed `DELETE` | yes |
| Campaigns → **Send** | real e-mail to the whole opted-in list | `danger` + typed `SEND` | yes — but no recipient count, no preview, no test |
| Payments → **Refund** | real money | `danger` + required reason | yes (UI omits the owner-only `billing.live_refund` check) |
| Engine → **Hide forecast** | removes it from every public page | `danger` + required reason + consequence | yes — the model for the rest |
| Users → **Turn off** / **Remove free plan** / **Reset 2FA** | user-visible | `danger` + required reason | yes |
| Studio → **Publish** | the live site | confirm + note; conflict → `danger` override | yes |
| Studio → **Roll back** | the live site | confirm | yes |
| Jobs → **Run now** (×6) | 1 call … ~1,140 calls | one confirm, same sentence for all six | **no — flat** |
| Explorer → **Force refresh** | 1 real call | confirm stating the cost | yes — best-calibrated in the admin |
| Leagues → **Refresh league list** | 1 call, queues `reference_sync` | **none** | **no — AD-08 confirms the same job** |
| Leagues → **switch a league on** | recurring daily calls, forever | **none** | **no — estimate exists one drawer deeper** |
| Jobs → **Queue missing matches** | unbounded PitchAPI calls | **none** | **no** |
| SportAPI → **Run now** (`/sportapi/tick`) | SportAPI quota, synchronous | **none** | **no** |
| SportAPI → **Backfill** | SportAPI quota | **none** | **no** |
| Engine → **Sync images** / **Sync and re-read squads** | PitchAPI quota | **none** | **no** |
| Engine → three switches (`calibration`, `absence_model`, `match_context`) | every public percentage at the next run | **none** | **no** |
| Settings → any boolean or enum | up to and including `billing.mode` | **none** — saves on change | **no** |
| Users → **Send password-reset e-mail** | real e-mail to a real reader | **none** | **no — "Add note" beside it has a dialog** |
| Users → **Resend verification** | real e-mail to a real reader | **none** | **no** |
| Users → **Sign out everywhere** | ends the reader's sessions | **none** | **no** |
| Integrations → **Send everyone now** | pushes the whole list to a third party | **none** | **no** |
| Integrations → **New secret** (webhook rotate) | instantly breaks a live integration | **none** — Delete beside it is guarded | **no** |
| Plans → **Sync to Stripe** | creates real Stripe prices | **none** (and the file comment says it is disabled) | **no** |
| Popups → set **live** | a modal to every matching visitor | **none** — Delete is guarded | **no** |
| Studio → **Discard draft** / **Reset section** / apply **preset** | unrecoverable: Versions holds only published versions | **none** | **no** |
| Templates → **Reset** | discards a customised template | **none** | **no** |
| Media / Announcements / Popups / Webhooks → **Delete** | content loss | `danger` confirm | yes |
| Newsletter → **Remove** / Suppressions → **Unblock** | consent state | confirm with the consequence | yes |
| Keys → **Remove** | breaks the provider | confirm with the consequence | yes |

So: the guarded half is guarded well and consistently — `Confirm` supports `danger`, a required `reason` and a
typed phrase, and the three tiers are used sensibly where they are used at all. The problem is the other half.
**Eighteen actions that spend money, send mail to real people, change what every reader sees, or destroy
unrecoverable work have no dialog at all**, and several of them sit next to a guarded action of *lower*
consequence: Delete-a-webhook is guarded and rotate-its-secret is not; delete-a-popup is guarded and
publish-it-to-everyone is not; add-a-note is guarded and e-mail-the-member is not.

Compounding it: **`btn--danger` is used exactly once in the whole admin** (Cache → Delete all). Every other
destructive trigger is `btn--ghost`, pixel-identical to "History", "Preview" and "Test" beside it.

Proposed ladder, applied uniformly: **no dialog** for cheap, reversible, self-scoped (Explorer cached run,
alerts "Check now", "Send me a test"); **plain confirm stating the consequence** for reversible but visible
(popup live, template reset, webhook rotate, league on/off, e-mail to one member); **confirm with the number**
for anything that spends quota or money (every job run, every sync, every backfill — with the estimate and
today's remaining budget in the body); **confirm + required reason** for anything a reader sees or that touches
their account; **typed phrase** only for irreversible destruction and bulk sends. And give every destructive
trigger `btn--danger`.

### 4. Consistency

There **is** a shared grammar — `parts.jsx` gives the whole admin `PageHead`, `Card`, `StatTile`,
`ResponsiveTable` (table ≥1025 px, cards below), `Pager`, `DataState`, `Chip`, `Budget`, `KV`, `Bars`,
`JsonTree`, `Empty`/`ErrorBox`/`Loading`, and `Ui.jsx` gives `Tabs`, `Drawer`, `Confirm`, `Field`, `Switch`,
`useToast`. That is better than most admin panels and it should be said plainly. The divergences are where
screens step outside it:

1. **Tabs in the URL, or not.** AD-03 and AD-05 use `useParams`/`useNavigate`. AD-09 (7 tabs), AD-25 (9),
   AD-31 (8), AD-12 (6) and AD-05b's inner row (3) use `useState`. Back and deep-linking behave differently on
   five screens than on two.
2. **Four list idioms.** `ResponsiveTable` (14 screens); raw `<table class="a-matrix">` (AD-11 role matrix,
   AD-05b coverage); `<ul class="a-plan-ents">` key/value rows (AD-08 queue, AD-05a counts, AD-09 brain,
   AD-20 entitlements); `<dl class="a-dl">` (AD-04, AD-33 queue, AD-18 drawer). Only the first is responsive.
3. **Pagination on half the screens.** `Pager` on 10. AD-07, AD-11, AD-13, AD-15, AD-20, AD-23, AD-27, AD-29
   render everything; AD-28 renders 252 rows and 38,825 px.
4. **Five save models.** Explicit Save with a dirty check (AD-28 text rows, AD-25 section, AD-20, AD-12);
   save-on-change with no confirm (AD-28 booleans and enums, AD-09 switches, AD-07 league toggle, AD-09
   Availability tap-to-cycle); Confirm-then-act; the two-tap arming button `TwoTap`, which exists **only** in
   `Home.jsx` and nowhere else; and typed confirmation. Three of these can appear on one screen.
5. **Empty states.** Most use `<Empty>` from `States.jsx`. `EngineRuns.jsx` uses bare
   `<p className="a-muted small">No league is switched on.</p>`; `Analytics.jsx` uses `<p className="muted">`.
6. **Two classes for one colour.** `.muted` (base.css) and `.a-muted` (admin.css) both declare
   `color: var(--text2)`, used 33 and 34 times respectively across the same 33 files — eight admin screens use
   the public one. They have *already* diverged: `hig-admin.css` applies a `text-transform`/`letter-spacing`
   reset to `.a-muted` only.
7. **Refresh.** A manual button on AD-01, AD-04, AD-08, AD-33, AD-03a, AD-03b-realtime. Automatic polling on
   AD-04 only (`{every: 60000}`). Nothing else refreshes, including the two operational screens where staleness
   is most dangerous.
8. **Search.** The `.a-search` pattern with its icon on AD-28, AD-10, AD-07, AD-05a and the More sheet. A bare
   `<input className="a-input">` for the market filter in `EngineRuns`. No search at all on AD-31 Logs, AD-18
   E-mail log, AD-27 Media, AD-13 Popups or AD-17 Templates.
9. **`MissingRoutes`** (the "waiting for the server routes" card) is honoured by AD-08, AD-07, AD-05a, AD-05b
   and AD-05c and by nothing else, so the same backend gap renders as a friendly card on five screens and as a
   raw error box everywhere else.
10. **Destructive styling**, as above: one `btn--danger` in the entire admin.
11. **Two "Images".** AD-09's Images tab is a review queue; AD-27 Images is the media library. `docs/43`
    records this and leaves it. It is still two menu-reachable things with one name.

### 5. What should not exist

- **AD-02 Needs — delete.** It is `NeedsList` on `/admin/home`, the same component and endpoint as AD-01's
  block without the `limit={8}`. Two modules, two rail rows, one of four default phone tabs, one list. Make
  AD-01's "See all N" expand in place and redirect the route.
- **AD-03a Analytics → Overview — delete the tab.** Its six tiles restate AD-01's tiles and AD-33's numbers,
  and its alerts card is the same `AlertList` on the same `h.alerts` as AD-33. Move its two bar charts into
  Audience and drop the tab; Analytics becomes one screen, which is what `docs/43` was reaching for when it
  merged the old Dashboard.
- **AD-14 Announcements — merge into AD-13 Popups.** A top banner with a date window and no targeting is a
  popup of kind `banner_top`. Two modules run two schedulers and two editors for one idea.
- **AD-23 Coupons — merge into AD-20 Plans.** Four fields, one list, one action. It is a card, not a module.
- **AD-19 Blocked addresses — merge into AD-18 E-mail log** as a saved filter plus the Unblock action. Lowest
  priority of the five; it is coherent as it stands.
- **AD-24 Revenue — keep, but make it the only place revenue is stated.** Today MRR appears on AD-01's Money
  tile, AD-03a and AD-24.

Net: 33 modules → 28, with no capability lost, two fewer Overview entries competing to be the thing you check
first, and one fewer place where a number can disagree with itself.

### Genuinely unusable on a phone

Measured from `docs/redesign/v3/before/AD-*-phone-dark.png` at 390×844 (1 screen = 844 px):

- **AD-28 Settings — 68,964 px, 82 screens.** Unusable in any sense. The two-column row collapses to one
  stacked column below 1025 px, the search bar is not sticky, and nothing is collapsed.
- **AD-05a PitchAPI usage and cache — 9,468 px, 11 screens.** Usable only to read the top three tiles; the
  50-row cache table below is not a phone surface.
- **AD-29 Keys — 3,391 px, 4 screens** of write-only cards. Works, but it is the wrong device for pasting
  secrets.
- **AD-11 Staff** and **AD-05b Coverage** — the role matrix and the coverage matrix are raw tables in
  `overflow: auto` with no sticky first column: scroll right and you lose the row label. Three of five role
  columns are visible at 390 px.
- **AD-25 Site Studio** — works but is not the device: nine section tabs in a scroller with
  `scrollbar-width: none` and no fade, so four of them are invisible; a colour-picker grid; and a 300 px mock
  preview.
- **AD-09 Engine (7 tabs)**, **AD-31 Logs (8)** and **AD-12 Inbox (6)** share the hidden-tab-scroller problem.

Everything else fits in one to three phone screens and genuinely works, because `ResponsiveTable` switches to
cards below 1025 px and the bottom app bar with its pinnable four tabs and searchable "All tools" sheet is a
well-built phone shell. The laptop is the priority and the laptop is fine; the phone failures are concentrated
in exactly the dense screens where a phone was never the point.

---

## Evidence

- Screenshots read: `docs/redesign/v3/before/AD-*-{desk,phone}-dark.png` (152 files).
- Live pass over all 33 modules and 5 sub-tabs at 1440×900 and 390×844 against a throwaway demo server, signed
  in as the demo owner; per-screen DOM node counts, card/row/setting counts, rendered `h1` and horizontal-scroll
  checks. No job was run, no setting changed, no e-mail sent, nothing deleted. The run was done on a private
  server instance on a spare port so that the shared demo server on 8011 and its capture job were untouched.
- `backend/settings_registry.json` counted directly: 252 settings, 25 groups, 67 boolean / 64 number / 37 int /
  24 string / 23 json / 15 float / 12 list / 10 enum; 138 with no `help`; 0 with `owner_only`; 35 json-or-list.
- `backend/accounts.py` `PERMS` read for the role-filtering claims.
