# 43. Organising the admin: one place per job, and one group for the data feeds

Written 2026-11-01. The owner's report, in full: *"sportapi settings is under integration and pitchapi is somewhere
else … make sure admin is very organized and as userfriendly as possible."*

## What was wrong

**SportAPI had no menu entry at all.** A 262-line screen with six cards — status, calls today, which fixtures are
matched, live statistics, league mapping, team review, backfill — was appended to the foot of **Integrations**,
under a bare `<h2>`, below e-mail sending, list sync, webhooks and ad tags:

```jsx
<PageHead title="Integrations" lead="Connect e-mail, your marketing list, automation tools and ad tags." />
...
<h2 className="h3 a-section-title">SportAPI</h2>
<SportAPI />
```

Because it was not a module it had no route, so it could not be linked to, could not be searched for in the "More"
sheet, could not be pinned to the phone bar, and the browser's Back button could not return to it. The Home screen's
own **Live** tile — the SportAPI health tile — sent you to `integrations`, i.e. to the e-mail screen.

**PitchAPI was the opposite problem: five entries, no heading that named it.** Its controls were spread across a
group called *Data* as *Leagues*, *Jobs*, *Data quality*, *Endpoint explorer* and *Cache and usage*, none of which
says "PitchAPI", plus its key under *Keys* and its field mapping under *Settings*. The *Engine* sat in the same
group, although it consumes football data rather than fetching any.

So the first question in any live problem — **which feed is at fault** — had no screen that answered it, and the two
providers' controls were as far apart in the menu as two things can be.

Three smaller things came out of the same read-through:

- **"Connect" was a group of one**, holding a screen that mixed four unrelated services.
- **Three names for roughly one job**: *Home*, *Dashboard* (`/admin/stats`) and *Analytics*, the last two both
  showing visitor and sign-up numbers, with the same `bar-chart` icon.
- **Labels repeating their own group**: *E-mail templates*, *E-mail log* under a group called **E-mail**.

## The menu now

| Group | Modules |
|---|---|
| **Overview** | Home · Needs you · Analytics |
| **Football data** | Feeds · PitchAPI · SportAPI · Leagues · Jobs |
| **Forecasts** | Engine |
| **People** | Users · Staff · Inbox |
| **Marketing** | Popups · Announcements · Campaigns · E-mail list |
| **E-mail** | Templates · Log · Blocked addresses |
| **Money** | Plans · Subscriptions · Payments · Coupons · Revenue |
| **Website** | Site Studio · Pages · Images |
| **System** | Settings · Keys · Integrations · Logs · Security · Health |

33 modules in 9 groups, down from 34 in 9. The group is named after the **provider** where one exists, because that
is the word the owner thinks in, and the two providers come first in their group — ahead of the screens that use
what they fetch.

## The three new or changed screens

**Feeds** (`/admin/data/feeds`, new) answers "which feed is at fault" on one page: a card per provider with what it
is *for*, whether it is on, whether its key is saved, calls used against today's cap, when it last ran, and the
numbers that matter for that provider only — PitchAPI's queue and breaker; SportAPI's matches being played, clubs
awaiting review, and fixtures reaching no page. Below them, a plain table of symptom → feed, so a problem can be
taken to the right screen without knowing the architecture.

**PitchAPI** (`/admin/data/pitchapi`, new) is one screen with three tabs — *Usage and cache*, *Quality and mapping*,
*Endpoint explorer* — holding the three screens that were three separate menu entries. The tab is in the URL, so a
link to one tab works and Back leaves the screen rather than cycling tabs.

**SportAPI** (`/admin/data/sportapi`) is the same screen as before, now a module in its own right with its own
heading, and removed from Integrations.

**Analytics** gains two tabs, *Overview* (what *Dashboard* was) and *Audience* (what Analytics was), which is why
the menu has one audience entry instead of two. The period and CSV-export controls belong to the Audience tab and
only appear there.

## Nothing breaks

A screen folded into a tab keeps its old address, which now redirects:

| Old | New |
|---|---|
| `/admin/stats` | `/admin/analytics/overview` |
| `/admin/data/cache` | `/admin/data/pitchapi/usage` |
| `/admin/data/quality` | `/admin/data/pitchapi/quality` |
| `/admin/data/explorer` | `/admin/data/pitchapi/explorer` |

Every other route is unchanged, so existing bookmarks and the owner's pinned phone tabs keep working. No API route
changed. A folded screen still renders standalone if it is ever given its own route again: it takes `head={false}`
to drop its heading when it is a tab, and nothing else about it changed.

## What this does not do

- **The settings are still one long list.** `provider.*`, `ingest.*` and `cache.*` (PitchAPI) and `sportapi.*` sit
  in *Settings* under groups of their own, which is right, but a provider's screen does not yet show its own
  settings inline — you still go to Settings to change a number you just read on a feed screen. Worth doing; it
  needs each setting to declare which screen owns it.
- **Keys are still central.** Both providers' keys live under *Keys*, not on the provider's own screen. That is
  deliberate for now: *Keys* is owner-only and write-only, and spreading key entry across screens would spread that
  rule too.
- **`Engine → Images`** is a review queue while **`Website → Images`** is the media library. Two different things
  with one name, left as they are because renaming either would churn the image pipeline's wording; noted so the
  next person knows.

## Files

| File | Change |
|---|---|
| `backend/admin_shell.py` | The module list regrouped and reordered, with `MOVED` for the folded screens; `Football data`, `Forecasts`, `Marketing`, `Website` groups; labels no longer repeat their group; no icon repeats inside a group. |
| `backend/admin_home.py` | New `feeds()`: both providers side by side. The Data and Live tiles point at `pitchapi` and `sportapi` instead of `jobs` and `integrations`. |
| `backend/routes_admin.py` | `GET /api/admin/feeds`. |
| `frontend/src/admin/Feeds.jsx` | New. |
| `frontend/src/admin/PitchAPI.jsx` | New: the three PitchAPI screens as tabs. |
| `frontend/src/admin/SportAPI.jsx` | Its own page and heading. |
| `frontend/src/admin/Integrations.jsx` | SportAPI removed; the lead says where football data went. |
| `frontend/src/admin/Analytics.jsx`, `Dashboard.jsx` | Two tabs; `Dashboard` is the Overview tab. |
| `frontend/src/admin/Cache.jsx`, `Quality.jsx`, `Explorer.jsx` | `head={false}` when used as a tab. |
| `frontend/src/admin/AdminApp.jsx` | Tabbed routes, redirects for the old addresses, shorter phone labels. |
| `frontend/src/admin/Home.jsx` | The charts link follows Analytics. |
| `backend/tests/selftest_admin_menu.py` | New. The menu is well formed; the football group holds every pull, providers first; every module has a screen; the home tiles point at the right screens; both providers are described in one place. |
