# 23. Update pack: everything new since the hand-off, plus SportAPI live data

**For the builder (Emergent).** This one document covers every change since the first hand-off zip:
- **A:** team matrix, radar and Compare;
- **B:** forecast fixes;
- **C:** brain upgrade;
- **D:** SportAPI for live scores, match events, lineups and historical results.

Every file it mentions is in `update_pack.zip`, at the path where it belongs. The SportAPI code is also printed in full in the appendix, so this document can be read on its own.

**How to work:**
- Do the parts in order: A, B, C, D.
- After each part, run the checks in its section and stop if anything fails.
- Our backend files are tested. Copy them as they are, and do not rewrite them.
- If a file you are about to replace was changed in this project since the hand-off, show the owner the difference first.

---

## 0. The whole change in one table

| Part | What the user gets | Backend | Frontend | Spec |
|---|---|---|---|---|
| A. Team views | League "Teams" tab: every club side by side (heat-map table). A radar chart of two clubs. Compare page: form first, then the season; home/away "as a fixture" mode | `team_insights.py`, `routes_teams.py` | `TeamMatrix.jsx`, `TeamRadar.jsx`, `League.jsx`, `Leagues.jsx`, `Compare.jsx`, `teams.css` | docs/20 |
| B. Forecast fixes | No duplicate forecasts; one card per player per match; percentages that mean what they say | `calibration.py`, `engine_bridge.py`, `queries.py`, `jobs.py` | Forecast lists show `cards` | docs/21 |
| C. Brain upgrade | Injuries and absences count; results form and late-season stakes; old results fade more slowly | `soccer_brain/engine.py`, `strength.py`, `availability.py`, `match_context.py` | Match page: who is out, context sentences. Admin: Availability | docs/22 |
| D. Live (SportAPI) | Live scores with the match clock, goals, cards and substitutions, lineups before kick-off, historical results | `sportapi.py`, `routes_live.py` | `Live.jsx`, `LiveStatus.jsx`, `MatchEvents.jsx`, `live.css`, live score on Today | this doc, section 7 |

Tests: 17 self-test suites, all passing (`cd backend && bash run_tests.sh`).

---

## 1. Files

### 1.1 New files (copy to the same path)

```
backend/team_insights.py            backend/routes_teams.py
backend/calibration.py              backend/availability.py
backend/match_context.py            backend/sportapi.py
backend/routes_live.py              backend/soccer_brain/calibration_default.json
backend/tests/selftest_teams.py     backend/tests/selftest_calibration.py
backend/tests/selftest_availability.py  backend/tests/selftest_matchctx.py
backend/tests/selftest_sportapi.py
frontend/src/components/TeamMatrix.jsx  frontend/src/components/TeamRadar.jsx
frontend/src/components/LiveStatus.jsx  frontend/src/components/MatchEvents.jsx
frontend/src/pages/League.jsx       frontend/src/pages/Leagues.jsx
frontend/src/pages/Compare.jsx      frontend/src/pages/Live.jsx
frontend/src/styles/teams.css       frontend/src/styles/live.css
docs/20_team_matrix_and_compare.md  docs/21_forecast_audit_and_fixes.md
docs/22_engine_factors.md           docs/23_update_pack_and_sportapi.md
docs/validation/*.py                (research scripts, not used by the app)
```

### 1.2 Replaced backend files (take ours whole)

| File | Why |
|---|---|
| `backend/soccer_brain/engine.py` | Availability model, `availability=` and `match_ctx=` on `predict_fixture`, `strength_decay` |
| `backend/soccer_brain/strength.py` | `outcome_probs(..., mult_h, mult_a)` |
| `backend/engine_bridge.py` | Calibration; one row per forecast; deduplicated scoring; availability and match context passed to the engine |
| `backend/queries.py` | `group_cards`; match page gets `cards`, `availability`, `context`, `live`, `live_events` |
| `backend/jobs.py` | Weekly `calibration`, twice-daily `injuries` |
| `backend/mongo_init.py` | New indexes (section 3) |
| `backend/admin_queries.py`, `backend/routes_admin.py` | Brain status with calibration; availability routes; SportAPI key in Admin → Keys |
| `backend/settings_store.py`, `backend/settings_registry.json`, `docs/11_settings_registry.json` | 199 settings (section 2) |
| `backend/security_mw.py` | `/api/jobs/live` is exempt from the browser origin check and the rate limit (like `/api/jobs/tick`) |
| `backend/server.py` | Mounts `routes_live` (public and admin) and `routes_teams` **before** `routes_data` |
| `backend/check_apifootball.py` | `--injuries` check |
| `backend/run_tests.sh`, `backend/tests/selftest_admin.py`, `backend/tests/demo_server.py` | 17 suites; the demo shows live scores |

### 1.3 Small edits to frontend files you may have changed

Make only these edits. Do not replace the files.

**`frontend/src/index.js`:** after the other style imports
```js
import "./styles/teams.css";
import "./styles/live.css";
```

**`frontend/src/App.js`:** imports and routes
```js
import League from "./pages/League";
import Leagues from "./pages/Leagues";
import Compare from "./pages/Compare";
import Live from "./pages/Live";
// inside <Route element={<Layout />}>  (replace any existing leagues or league/:id route)
<Route path="leagues" element={<Leagues />} />
<Route path="league/:id" element={<League />} />
<Route path="compare" element={<Compare />} />
<Route path="live" element={<Live />} />
```

**`frontend/src/components/Layout.jsx`:** the menu. Add Live after Today in the tab list, and Compare in the top menu.
```js
const TABS = [
  { to: "/", label: "Today", end: true },
  { to: "/live", label: "Live" },
  { to: "/insights", label: "Insights" },
  { to: "/finder", label: "Finder" },
  { to: "/leagues", label: "Leagues" },
  { to: "/following", label: "Following" },
];
// top nav, after the tabs:
<NavLink to="/compare">Compare</NavLink>
```

**`frontend/src/pages/Today.jsx`:** show the live score in the time column.
```jsx
import LiveStatus from "../components/LiveStatus";
// in the fixture row, replace the <time> element with:
{m.live && m.live.status !== "Scheduled"
  ? <span className="fx-live"><LiveStatus status={m.live.status} minute={m.live.minute} kickoff={m.kickoff} /> <strong>{m.live.hs} - {m.live.as}</strong></span>
  : <time>{utc(m.kickoff).toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" })}</time>}
```

**`frontend/src/styles/base.css`:** the fixture row's first column goes from 56px to 76px (two places: the base rule and the `min-width: 768px` rule).

---

## 2. New settings (all in `settings_registry.json`; 199 in all)

| Key | Default | Part | Meaning |
|---|---|---|---|
| `engine.calibration` | true | B | Show calibrated percentages (off = raw) |
| `engine.calibration_auto` | true | B | Weekly refit from our own results, kept only if better |
| `engine.calib_min_scored` | 5000 | B | Scored forecasts needed before a refit |
| `engine.feed_one_per_player` | true | B | One card per player per match |
| `engine.absence_model` | true | C | Missed recent matches → likely out |
| `engine.match_context` | true | C | Results form and stakes on the match forecast |
| `context.stakes_places` | `{}` | C | `{league iid: {"upper": 6, "relegation": 3}}` |
| `engine.strength_decay` | 0.01 | C | How fast old results fade (was 0.02) |
| `engine.history_rounds` | **320** (was 150) | C | About three seasons of match dates |
| `injuries.enabled` | false | C | API-Football injuries feed (check first) |
| `injuries.stale_days` | 3 | C | Feed rows expire if not refreshed |
| `sportapi.enabled` | false | D | Master switch for live data |
| `sportapi.daily_calls` | 1800 | D | Hard stop per UTC day (plan: 2,000) |
| `sportapi.leagues` | `{}` | D | `{our league iid: SportAPI league id}`. Only these are followed |
| `sportapi.live_interval_s` | 60 | D | Scoreboard refresh while live or about to start |
| `sportapi.idle_interval_s` | 900 | D | Scoreboard refresh when followed matches are later today |
| `sportapi.quiet_interval_s` | 10800 | D | Scoreboard refresh on days with nothing followed |
| `sportapi.events_refresh_s` | 600 | D | Events refresh per live match (plus at once on any goal or status change) |
| `sportapi.window_before_min` | 15 | D | Fast polling starts this long before kick-off |
| `sportapi.lineups_minutes` | [75, 40, 15] | D | When to ask for lineups, until they arrive |
| `sportapi.lineups_to_engine` | true | D | A fully matched SportAPI eleven becomes the engine's confirmed lineup (only if PitchAPI has none) |
| `sportapi.team_aliases` | `{}` | D | Extra club-name pairs for matching |
| `sportapi.min_confidence` | 0.9 | D | Name-match score needed without review |
| `sportapi.backfill_max_days` | 60 | D | Most dates per backfill request |
| `sportapi.reserve_for_live` | 600 | D | Calls a backfill always leaves for live scores |

---

## 3. Database (MongoDB)

**New collections:**
- `availability`: `player_iid` (unique), `team_iid`, `status` (out or doubtful), `source` (admin or apifootball), `reason` (max 80, public), `until`, `updated_at`, `by`.
- `engine_calibration`: `map`, `active`, `created_at`, `scored`, `test_logloss`.
- `live_fixtures`: one row per SportAPI fixture of a followed league.
  - `sid` (unique), `league_sid`, `league_iid`, `league_name`, `date`, `kickoff`, `status`, `minute`;
  - `hs`, `as`, `ht_home`, `ht_away`, `pen_home`, `pen_away`, `result`, `winner`;
  - `home_sid`, `away_sid`, `home_name`, `away_name`, `home_short`, `away_short`;
  - `home_iid`, `away_iid`, `match_iid` (links to ours, or null);
  - `polled_at`, `events_at`, `events_n`, `lineups_at`, `lineups_ok`, `lineup_slots`, `final_at`, `final_done`.
- `live_events`: `fixture_sid`, `eid`, `type`, `side`, `player_name`, `minute` (as given, for example "90+2'"), `minute_num` (92), `extra`, `team_iid`.
- `live_lineups`: `fixture_sid` and `side` (unique), `team_iid`, `players` [{`name`, `position`, `pos`, `shirt`, `captain`, `mins`, `started`, `player_iid`, `score`}], `starters`, `matched_starters`, `fetched_at`.
- `sportapi_team_map`: `sid` (unique), `name`, `league_iid`, `status` (auto, approved, review, none or rejected), `our_iid`, `score`, `candidates`.
- `sportapi_calls`: `_id` = UTC date, `n`, `by_kind` {date, events, final, lineups, backfill, leagues}. **The budget counter.**
- `sportapi_cache`: `_id` = path, `payload`, `expires_at` (TTL). Used for the league list.
- `sportapi_dates`: `_id` = date, `complete`, `tracked`. Backfill progress; complete dates are never called again.
- `sportapi_state`: `_id` = "live", `date_polls` {date: last poll}, `last_tick`, `last_result`.

**New fields:**
- `forecasts`: `p_model`, `state` (pre or lineup), `calibration`.
- `forecast_outcomes`: `p_model`, `state`.
- `match_context`: `form_fp`, `stakes`, `games_left`, `context_why`.
- `matches.live`: `{status, minute, hs, as, pen_home, pen_away, sid, at}`, a light mirror for the Today and match pages.
- `lineups.source` = "sportapi" when the eleven came from SportAPI.

**Indexes:** `mongo_init.ensure_indexes` creates all of them on server start. There is nothing to run by hand.

---

## 4. API routes added

| Route | Who | What |
|---|---|---|
| `GET /api/leagues/{id}/team-matrix?window=season\|last10\|last5&venue=all\|home\|away` | public | Part A |
| `GET /api/teams/compare?a=&b=&as_fixture=` | public | Part A (with `radar`) |
| `GET /api/live?date=YYYY-MM-DD&tz=-240` | public | Scoreboard for the user's local day, grouped by league, live first. Cache 15 s. |
| `GET /api/live/{sid}/events` | public | Goals, cards and substitutions, sorted by minute |
| `GET /api/live/{sid}/lineups` | public | Starters and bench, linked to our player pages where matched |
| `GET /api/results?date=YYYY-MM-DD` | public | Finished matches of followed leagues on that date |
| `GET /api/matches/{id}` | public | Now also `cards`, `availability`, `context`, `live`, `live_events` |
| `POST /api/jobs/live` | external pinger, `X-CRON-SECRET` | **Every minute.** Runs the SportAPI schedule (section 7.3) |
| `GET /api/admin/sportapi` | `logs.read` | Status: switch, key, calls today by kind, budget, last run, live now, team mapping, review list |
| `GET /api/admin/sportapi/leagues` | `settings.read` | SportAPI league list for the mapping screen (1 call a week) |
| `POST /api/admin/sportapi/teams/{sid}` `{team_id}` | `jobs.run` | Approve a SportAPI team as one of ours (empty `team_id` = reject). Audited |
| `POST /api/admin/sportapi/backfill` `{start, end}` | `jobs.run` | Historical results, one call per date, resumable. Audited |
| `POST /api/admin/sportapi/tick` | `jobs.run` | Run the minute job now |
| `GET /api/admin/availability?team=` / `PUT /api/admin/availability` | `logs.read` / `jobs.run` | Part C |
| `POST /api/admin/calibration/rollback` | `settings.write` | Part B |

---

## 5. Screens

| Screen | Status | What to do |
|---|---|---|
| Leagues, League → Teams, Compare | Built (`Leagues.jsx`, `League.jsx`, `TeamMatrix.jsx`, `TeamRadar.jsx`, `Compare.jsx`) | Restyle only. Keep behaviour (docs/20) |
| Live | Built (`Live.jsx`, `LiveStatus.jsx`, `MatchEvents.jsx`) | Restyle only. It polls our own `GET /api/live` every 30 s while the tab is visible and never calls SportAPI |
| Today | Edit (section 1.3) | Live score and clock in the time column |
| Match page | To build | Live header (status chip, score, half-time); `MatchEvents` with `live_events`; lineups (`GET /api/live/{sid}/lineups`, sid = `live.sid`); "Out / Doubtful" list from `availability`; context sentences per club from `context`; forecast **cards** (`cards`, with `more_lines` inside each card) |
| Insights, player page | Edit | Show `cards`, never raw forecast rows |
| Admin → Engine → Brain | Edit | Calibration in use (`GET /api/admin/brain` → `calibration`), "Back to default map" button; switches `engine.absence_model`, `engine.match_context`, `engine.strength_decay` |
| Admin → Engine → Availability | New | Per club list; set out, doubtful or available with reason and end date |
| Admin → Integrations → **SportAPI** | New | See 7.7: status card, calls today / limit bar, league mapping, team review list, backfill form, "Run now" |
| Admin → Keys | Automatic | "SportAPI key" appears (owner only) |

All copy follows docs/03: analysis only, no betting words. `yarn check-copy` must pass.

---

## 6. One-time steps after deploying (preview first, then production)

1. **Remove old duplicate forecast rows** (Part B; safe to run twice):
```python
latest = {}
for f in db.forecasts.find({}, {"match_iid": 1, "run_id": 1, "created_at": 1}):
    k = f["match_iid"]
    if k not in latest or f["created_at"] > latest[k][1]:
        latest[k] = (f["run_id"], f["created_at"])
for mid, (rid, _) in latest.items():
    db.forecasts.delete_many({"match_iid": mid, "run_id": {"$ne": rid}})
seen = set()
for o in db.forecast_outcomes.find({}, {"fkey": 1}).sort("scored_at", 1):
    if o["fkey"] in seen:
        db.forecast_outcomes.delete_one({"_id": o["_id"]})
    seen.add(o["fkey"])
```
2. **Restart the server.** Indexes and the 199 settings load on start.
3. **Backfill about three seasons** of PitchAPI history per league (Admin → Leagues). The slower fade (Part C) uses it.
4. **Trigger one engine run** (Admin → Jobs → engine).
5. **SportAPI** (Part D): follow 7.7.

---

## 7. SportAPI: live scores, events, lineups, historical results

### 7.1 Which calls we use, and which we do not

SportAPI: base `https://sportapi.ai`, header `X-Api-Key: <key>`. Every answer has `success: true|false`.

| Call | Use? | When | Why |
|---|---|---|---|
| `GET /api/fixtures/date/{date}` | **Yes** | Every 60 s while a followed match is live or about to start; 15 min earlier in the day; 3 h on quiet days. Past dates for the backfill | **One call returns every fixture of the day** with status, minute, score, penalties and kick-off in UTC. That is the live scoreboard and the historical results in one call. |
| `GET /api/fixtures/{id}/events` | **Yes** | For each live followed match: at once when its score or status changes, and every 10 min while live (cards, substitutions) | Goals, cards, substitutions |
| `GET /api/fixtures/{id}` | **Yes, once per match** | When a followed match first shows FT, AET or PENS | Half-time score and the final event list |
| `GET /api/fixtures/{id}/lineups` | **Yes** | 75, 40 and 15 min before kick-off, **until** `available: true`, then never again | Starting XI and bench, shirt numbers, captain |
| `GET /api/leagues` | **Yes, rarely** | Admin mapping screen, cached 7 days | Find SportAPI league ids (Premier League = 24) |
| `GET /api/fixtures/{id}/stats` | Not now | n/a | PitchAPI is our stats source (the engine learns from it). Add later only if PitchAPI lacks a stat; one call per finished match |
| `GET /api/standings/{leagueId}` | Not now | n/a | We compute the table from our own results (docs/22) |
| `GET /api/fixtures/h2h/{a}/{b}` | No | n/a | We compute head-to-head from our database at no cost |
| `GET /api/teams/*`, `/api/players/*`, `/api/leagues/{id}/top*` | No | n/a | Not needed for live scores; PitchAPI and API-Football cover teams and players |
| `GET /api/teams/{id}/logo` | No | n/a | Logos come from the image sync (docs/19) |

Status values: `Scheduled`, `LIVE`, `FT`, `AET`, `PENS`, `Postponed`, `Cancelled`, `Suspended`. While live, `minute` holds the clock ("HT" at half-time).

### 7.2 The 2,000-call budget, worked through

**Our limit is 1,800 a day** (`sportapi.daily_calls`), counted per UTC day in `sportapi_calls`. That leaves 200 spare for retries and manual checks.

**Busy Saturday, 5 leagues, 40 followed matches across four kick-off waves (12:30 to 22:00 UTC):**

| What | How many calls |
|---|---|
| Scoreboard, 60 s from 12:15 to 22:00 (585 min) | 585 |
| Scoreboard before and after (15 min / 3 h intervals) | about 20 |
| Events: 40 matches × (12 refreshes + about 5 changes) | about 680 |
| Full-time detail: 1 per match | 40 |
| Lineups: 2 to 3 per match | about 100 |
| **Total** | **about 1,425**, under the 1,800 limit |

- A weekday with 10 matches uses about 300.
- **Safety valves:**
  1. When less than a quarter of the day's limit is left (fewer than 450), every interval doubles automatically.
  2. At the limit, nothing more is called until midnight UTC. The pages keep showing the last known scores with "Updated hh:mm".
  3. A `429` from SportAPI closes the day at once (no retry storm).
  4. A backfill always leaves `sportapi.reserve_for_live` (600) calls for live scores.
- **Following more leagues?** Raise `sportapi.events_refresh_s` to 900 first, then `live_interval_s` to 90.

**Visitors never cause a SportAPI call.** Pages read our database; only the minute job calls SportAPI. A million page views cost zero calls.

### 7.3 The minute job (`sportapi.live_tick`)

An external pinger calls `POST /api/jobs/live` every minute with the `X-CRON-SECRET` header. A free service such as cron-job.org can do 1-minute intervals. The job decides what is due. Calling it more often costs nothing.

1. **Scoreboard.**
   - Find the followed fixtures from 30 h ago to 24 h ahead.
   - **Hot** = live now, or not finished and between 15 min before and 3 h after kick-off.
   - Interval: 60 s if anything is hot; 15 min if a followed match is within 12 h; otherwise 3 h. All doubled when the budget is tight.
   - Poll today's date, plus the date of any hot match, so a late match that started yesterday is still followed.
   - Store fixtures of followed leagues only. Note which ones changed score or status.
2. **Events.** For every followed match that is live:
   - fetch `/events` if its score or status just changed, or if its events are older than 10 min;
   - replace the stored list (the provider sends the full list each time).
3. **Full time.** For a followed match that has just finished (`final_done` not set, kicked off within 2 days): one `GET /api/fixtures/{id}`, store the half-time score and events, set `final_done`.
4. **Lineups.**
   - For followed scheduled matches inside the largest lineup window: ask once per slot (75, 40, 15 min before) until `available: true`.
   - Match names to our players inside the linked club, with the same matcher as the image sync (surname, initial, position; accents folded; two names claiming one player → neither).
   - If all 11 starters match, PitchAPI has no confirmed eleven, and `sportapi.lineups_to_engine` is on: write them into `lineups` (source "sportapi", confirmed) and set `matches.lineups_at`. The engine re-runs on the next tick with the confirmed lineup.
   - Otherwise the lineup is shown on the page but never used by the engine.
5. **Record** the result in `sportapi_state` for the admin screen.

### 7.4 Linking SportAPI to our data

- **Leagues:** set `sportapi.leagues` to `{our league iid: SportAPI league id}` in Admin → Settings. Find the ids on the mapping screen. Only these leagues are stored or followed.
- **Teams:** matched by name **inside the mapped league only**, using the image sync's scoring (aliases such as "Man Utd", accents, "FC" ignored, plus `sportapi.team_aliases`).
  - At least 0.9 and 0.04 ahead of the next candidate → `auto`.
  - 0.7 up to 0.9 → `review`. The admin approves, and stored fixtures pick up the link.
  - Below 0.7 → `none`.
  - Nothing is guessed.
- **Matches:** our match with the same league, home club and away club, kicking off within 36 h of SportAPI's time.
- **Players** (lineups only): see 7.3 step 4.
- **What SportAPI never overwrites:** our results, scores or statistics in `matches`, `team_match_stats` and `player_match_stats`. PitchAPI stays the source the engine learns from. SportAPI writes only:
  - its own collections;
  - the light `matches.live` mirror;
  - a confirmed eleven when PitchAPI has none.

### 7.5 Historical results

- Admin → Integrations → SportAPI → **Backfill**: pick a start and end date (at most 60 days per request).
- **One call per date.** A past date whose followed fixtures are all final is marked complete and **never called again**.
- It stops itself after 40 s or when only `sportapi.reserve_for_live` calls are left, and says "paused". Run it again to continue, the next day if the budget was the reason.
- **Cost:** a season is about 300 match dates, so backfill it over a few days (for example 3 × 100 dates outside match days).
- **Pages:** `GET /api/results?date=` shows those results. The team and league pages may also use them for "recent results".

### 7.6 What the pages show

- **Live** (`/live`): Yesterday, Today and Tomorrow; followed matches grouped by league; live first, then upcoming, then finished.
  - Each row shows a status chip ("Live 63'" with a pulsing dot, "HT", "Full time", "Postponed"), crests and the score (with penalties if any).
  - Tap a row: half-time score, events (home on the left, away on the right), lineups with links to our player pages, and a link to our match page.
  - The page refreshes every 30 s while visible and shows "Updated hh:mm".
- **Today:** the live clock and score replace the kick-off time once a match starts.
- **Match page:** a live header, events and lineups (section 5).

### 7.7 Setting it up (owner)

1. Admin → Keys → **SportAPI key** → paste → save.
2. Admin → Integrations → SportAPI → **League mapping**. The screen lists SportAPI leagues (1 call a week). Set `sportapi.leagues`, for example `{"1": 24}` if our Premier League is iid 1.
3. Set `sportapi.enabled = true`.
4. Create a pinger: `POST https://<your app>/api/jobs/live` every **1 minute**, header `X-CRON-SECRET: <CRON_SHARED_SECRET>`. Keep the existing 5-minute pinger for `/api/jobs/tick`.
5. Press **Run now** once. Check the status card: calls today, fixtures stored, teams `auto` vs `review`.
6. Approve any teams in **Review**.
7. Optional: **Backfill** the last 30 days.

**The admin screen:**
- **Status card:** on/off, key saved, last run and its result, live now, calls today against the 1,800 limit (bar, with a split by kind: date, events, final, lineups, backfill), and "Plan limit 2,000".
- **League mapping:** SportAPI leagues (id, name, country) beside our leagues, saved into `sportapi.leagues`.
- **Team review:** SportAPI name, our best candidates with scores, **Approve** (choose one) or **Reject**.
- **Backfill:** two date fields, **Start**, and the result (done, paused with "next date", calls left).
- **Run now** button.

Every write is audited. Roles follow section 4.

### 7.8 When things go wrong

| Symptom | Cause | What happens | Fix |
|---|---|---|---|
| Status "no_key" | No key saved | Nothing is called | Admin → Keys |
| Status "no_leagues" | `sportapi.leagues` empty | Nothing is called | Map leagues |
| "SportAPI refused the key" | Wrong or expired key | The run stops with that message | Re-enter key |
| Status "budget" | Our 1,800 limit reached, or SportAPI answered 429 | No calls until midnight UTC; pages show the last scores | Lower `events_refresh_s`; follow fewer leagues |
| A followed match never appears | Teams in review, or a different league id | Fixture stored without link | Approve teams; check the mapping |
| Live score missing on our match page | Match not linked (kick-off moved more than 36 h) | The Live page still shows it | Approve teams; the link fills on the next poll |
| Lineup shown but not used by the engine | Fewer than 11 starters matched, or PitchAPI already confirmed | By design | Nothing (or add aliases) |
| `success: false` | Provider error | The run stops with a plain note and tries again next minute | Nothing |

### 7.9 Not verified, and how the code copes

- **Rate-limit headers:** SportAPI's page does not list any, so we count every call ourselves.
- **The date in `/fixtures/date/{date}`:** whether it is UTC or the league's local day is not stated. We poll the UTC date plus the date of any match still live, so evening and late matches are not lost.
- **The full list of `event_type` values:** the page shows `goal` and `yellow_card`, and says cards and substitutions. The page component has labels for goal, own goal, penalty, missed penalty, yellow, red, second yellow and substitution, and shows any other type in plain words.
- **Lineup `position` names for substitutes:** they are "Substitute", so substitutes are matched by name only.
- **The ids SportAPI shows in its examples** (Premier League = 24, Arsenal = 311) come from its documentation. Confirm them on the mapping screen.

### 7.10 Tests (`backend/tests/selftest_sportapi.py`, fake SportAPI)

They prove:
- off by default;
- mapped leagues only;
- teams and matches linked by name, never guessed;
- 60 s polling only around live matches, 15 min otherwise;
- events at once on a goal and every 10 min while live;
- one detail call at full time, never again;
- lineups asked at 75 and 40 min until they arrive, with a fully matched eleven becoming the engine's confirmed lineup;
- the budget a hard stop, intervals doubled when tight, and a 429 closing the day;
- the backfill one call per date, complete dates never repeated, the live reserve kept;
- pages never calling SportAPI;
- the minute job needing the secret;
- admin permissions;
- the league list cached.

---

## 8. Acceptance checks

- [ ] `cd backend && bash run_tests.sh` → 17 PASS.
- [ ] `cd frontend && yarn check-copy && yarn build` → passes.
- [ ] League → Teams shows the matrix; ticking two clubs shows the radar; Compare opens with form first.
- [ ] Insights: no player twice within one match; each card shows its other lines.
- [ ] Match page shows Out / Doubtful, context sentences, and forecast cards.
- [ ] Admin → Engine → Brain shows the percentage map in use; "Back to default map" works.
- [ ] With SportAPI on, a key saved and leagues mapped: Admin → SportAPI → **Run now** stores today's fixtures; calls today goes up by 1.
- [ ] During a live match: `/live` shows "Live 23'" and the score, events appear within a minute of a goal, and the Today page shows the clock.
- [ ] Calls today on a match day stays under 1,800 (check the bar in the evening).
- [ ] Visiting `/live` 100 times does not change calls today.
- [ ] Backfill of 3 past dates costs 3 calls; repeating it costs 0.

---

## 9. The prompt to give Emergent

> I have attached update_pack.zip and docs/23_update_pack_and_sportapi.md. Read docs/23 completely, then docs/20, 21 and 22, before changing anything.
>
> Do the parts in order A, B, C, D. For each part:
> 1. Copy the new files to the same paths (section 1.1).
> 2. Replace the backend files listed in section 1.2 with ours. If any of them was changed in this project since the hand-off, show me the difference first and wait.
> 3. Make only the small frontend edits in section 1.3.
> 4. Run `cd backend && bash run_tests.sh` and `cd frontend && yarn check-copy && yarn build`, and show me the output.
>
> Then:
> - Run the one-time steps in section 6 in preview, and show me how many duplicate rows were removed.
> - Build the screens in section 5 that are marked "To build", "Edit" or "New": the match page live header, events, lineups, availability, context and cards; the Insights and player-page cards; the Brain and Availability admin screens; and Admin → Integrations → SportAPI exactly as in section 7.7.
> - Restyle the built screens only (Leagues, League → Teams, Compare, Live). Keep their behaviour.
>
> Rules:
> - Visitors must never cause a SportAPI call. Only `POST /api/jobs/live` calls SportAPI.
> - Do not change `sportapi.py`, `routes_live.py`, the engine (`backend/soccer_brain/`), `engine_bridge.py`, `calibration.py`, `availability.py`, `match_context.py`, `team_insights.py` or `queries.py`.
> - Keep `sportapi.enabled` and `injuries.enabled` off until I have done section 7.7 and docs/22 §4.
> - Analysis only (docs/03).
>
> At the end, show me every acceptance check in section 8.

---

## Appendix: the SportAPI code, in full

The same files are in the zip. They are printed here so this document stands alone.

### `backend/sportapi.py`

```python
"""sportapi.py -- live scores, match events, lineups and historical results from SportAPI (sportapi.ai). docs/23.

What we use SportAPI for (and nothing else):
  * live scores and match clock          GET /api/fixtures/date/{date}        one call = every fixture of the day
  * match events (goals, cards, subs)    GET /api/fixtures/{id}/events        only for live matches we track, on change
  * final details (half-time score)      GET /api/fixtures/{id}               once, when a match finishes
  * lineups (starting XI and bench)      GET /api/fixtures/{id}/lineups       a few times before kick-off, then stop
  * historical results                   GET /api/fixtures/date/{date}        past dates, cached for good once all are final
  * league list for the admin mapping    GET /api/leagues                     cached 7 days
PitchAPI stays the source of the statistics the engine learns from. SportAPI adds speed (live) and lineups.

The plan allows 2,000 calls a day. We count every call ourselves (`sportapi_calls`, per UTC day), stop at
`sportapi.daily_calls` (default 1,800, keeping 200 spare), and slow everything down when less than a quarter is left.
Visitors never cause a call: pages read our database; only the job below calls SportAPI.

Run `live_tick(db)` every minute (POST /api/jobs/live, called by an external pinger). It decides by itself whether a
call is due, so calling it more often costs nothing.
"""
from __future__ import annotations

import hashlib
import re
from datetime import datetime, timedelta, timezone

import httpx

import security
import settings_store as S
from images import team_score, player_score            # the same careful name matching as the image sync (docs/19)

BASE = "https://sportapi.ai"
PROVIDER = "sportapi"
KEY_RE = r"^[A-Za-z0-9_\-]{16,128}$"
LIVE = "LIVE"
FINAL = {"FT", "AET", "PENS"}
DEAD = {"Postponed", "Cancelled"}
POS = {"goalkeeper": "GK", "defender": "DEF", "midfielder": "MID", "forward": "FWD", "attacker": "FWD", "attacking midfielder": "MID"}

_FACTORY = lambda: httpx.Client(timeout=15.0, follow_redirects=False)


def set_http_factory(f):
    global _FACTORY
    _FACTORY = f


def utcnow():
    return datetime.now(timezone.utc)


def _aware(d):
    return d if d is None or d.tzinfo else d.replace(tzinfo=timezone.utc)


class SportAPIError(Exception):
    pass


class BudgetExhausted(SportAPIError):
    pass


class NoKey(SportAPIError):
    pass


# ------------------------------------------------------------------ client with a hard daily budget
def calls_today(db, now=None) -> dict:
    d = db.sportapi_calls.find_one({"_id": (now or utcnow()).strftime("%Y-%m-%d")}) or {}
    return {"n": int(d.get("n", 0)), "by_kind": d.get("by_kind", {})}


class Client:
    def __init__(self, db, http: httpx.Client | None = None, now=None):
        self.db = db
        self.now = now or utcnow()
        self.http = http or _FACTORY()
        self.key = security.get_provider_key(db, PROVIDER, env_fallback="SPORTAPI_KEY")
        if not self.key:
            raise NoKey("No SportAPI key saved (Admin > Keys).")

    def used(self) -> int:
        return calls_today(self.db, self.now)["n"]

    def cap(self) -> int:
        return int(S.get(self.db, "sportapi.daily_calls"))

    def left(self) -> int:
        return self.cap() - self.used()

    def tight(self) -> bool:
        """Less than a quarter of today's budget left: everything polls half as often."""
        return self.left() < self.cap() * 0.25

    def get(self, path: str, kind: str, cache_days: float | None = None) -> dict:
        if cache_days:
            hit = self.db.sportapi_cache.find_one({"_id": path, "expires_at": {"$gt": self.now.replace(tzinfo=None)}})
            if hit:
                return hit["payload"]
        if self.left() <= 0:
            raise BudgetExhausted("Today's SportAPI budget is used.")
        try:
            r = self.http.get(BASE + path, headers={"X-Api-Key": self.key, "accept": "application/json"})
        except httpx.HTTPError as e:
            self._count(kind)
            raise SportAPIError(f"SportAPI could not be reached ({type(e).__name__}).")
        self._count(kind)
        if r.status_code in (401, 403):
            raise SportAPIError("SportAPI refused the key.")
        if r.status_code == 429:
            self.db.sportapi_calls.update_one({"_id": self.now.strftime("%Y-%m-%d")}, {"$set": {"n": self.cap()}}, upsert=True)
            raise BudgetExhausted("SportAPI says the daily limit is reached.")
        if r.status_code == 404:
            return {"success": False, "not_found": True}
        if r.status_code != 200:
            raise SportAPIError(f"SportAPI answered {r.status_code}.")
        data = r.json()
        if not isinstance(data, dict) or data.get("success") is False:
            raise SportAPIError("SportAPI answered without success.")
        if cache_days:
            self.db.sportapi_cache.update_one({"_id": path}, {"$set": {"payload": data, "expires_at": (self.now + timedelta(days=cache_days)).replace(tzinfo=None)}}, upsert=True)
        return data

    def _count(self, kind):
        self.db.sportapi_calls.update_one({"_id": self.now.strftime("%Y-%m-%d")},
                                          {"$inc": {"n": 1, f"by_kind.{kind}": 1}, "$set": {"at": self.now}}, upsert=True)


# ------------------------------------------------------------------ mapping SportAPI ids to ours
def tracked_leagues(db) -> dict:
    """{sportapi league id: our league iid} from `sportapi.leagues` ({our iid: sportapi id})."""
    return {int(v): int(k) for k, v in (S.get(db, "sportapi.leagues") or {}).items() if v}


def map_team(db, sid: int, name: str, league_iid: int | None) -> int | None:
    """Our team iid for a SportAPI team, matched by name inside the mapped league only. Never guesses."""
    m = db.sportapi_team_map.find_one({"sid": sid})
    if m and m.get("status") in ("auto", "approved"):
        return m.get("our_iid")
    if m and m.get("status") in ("rejected", "review"):
        return None
    if league_iid is None:
        return None
    aliases = S.get(db, "sportapi.team_aliases") or {}
    cands = sorted(((team_score(t["name"], name, aliases), t) for t in db.teams.find({"league_iid": league_iid}, {"_id": 0, "iid": 1, "name": 1})),
                   key=lambda x: -x[0])
    best = cands[0] if cands else (0.0, None)
    runner = cands[1][0] if len(cands) > 1 else 0.0
    conf = float(S.get(db, "sportapi.min_confidence"))
    status = "auto" if best[0] >= conf and best[0] - runner >= 0.04 else ("review" if best[0] >= 0.7 else "none")
    db.sportapi_team_map.update_one({"sid": sid}, {"$set": {"sid": sid, "name": name, "league_iid": league_iid, "status": status, "score": round(best[0], 3),
                                                            "our_iid": best[1]["iid"] if best[1] and status != "none" else None,
                                                            "candidates": [{"iid": t["iid"], "name": t["name"], "score": round(s, 3)} for s, t in cands[:3]],
                                                            "at": utcnow()}}, upsert=True)
    return best[1]["iid"] if status == "auto" else None


def link_match(db, league_iid, home_iid, away_iid, kickoff) -> int | None:
    if not (league_iid and home_iid and away_iid and kickoff):
        return None
    m = db.matches.find_one({"league_iid": league_iid, "home_iid": home_iid, "away_iid": away_iid,
                             "kickoff": {"$gte": kickoff - timedelta(hours=36), "$lte": kickoff + timedelta(hours=36)}}, {"iid": 1})
    return m["iid"] if m else None


def _kickoff(f) -> datetime | None:
    k = f.get("kickoff_utc")
    if not k:
        return None
    try:
        return datetime.fromisoformat(k.replace("Z", "+00:00"))
    except ValueError:
        return None


def _minute_num(label) -> float:
    """"55'" -> 55, "90+3'" -> 93, "HT" -> 45. Used to sort events."""
    if label is None:
        return 0.0
    s = str(label)
    if s.upper() == "HT":
        return 45.0
    m = re.match(r"(\d+)(?:\s*\+\s*(\d+))?", s)
    return float(int(m.group(1)) + (int(m.group(2)) if m.group(2) else 0)) if m else 0.0


# ------------------------------------------------------------------ storing what we read
def upsert_fixture(db, f: dict, leagues: dict, now) -> dict | None:
    """Store one fixture of a tracked league. Returns {"changed": bool, "doc": ...} or None if not tracked."""
    lsid = f.get("league_id")
    if lsid not in leagues:
        return None
    league_iid = leagues[lsid]
    sid = int(f["id"])
    old = db.live_fixtures.find_one({"sid": sid}) or {}
    ko = _kickoff(f)
    home_iid = old.get("home_iid") or map_team(db, f.get("home_id"), f.get("home_team") or "", league_iid)
    away_iid = old.get("away_iid") or map_team(db, f.get("away_id"), f.get("away_team") or "", league_iid)
    match_iid = old.get("match_iid") or link_match(db, league_iid, home_iid, away_iid, ko)
    doc = {"sid": sid, "league_sid": lsid, "league_iid": league_iid, "league_name": f.get("league_name"),
           "date": f.get("date"), "kickoff": ko, "status": f.get("status"), "minute": f.get("minute"),
           "hs": f.get("home_score"), "as": f.get("away_score"), "result": f.get("result"), "winner": f.get("winner"),
           "pen_home": f.get("penalty_home"), "pen_away": f.get("penalty_away"), "stage": f.get("stage"),
           "home_sid": f.get("home_id"), "away_sid": f.get("away_id"), "home_name": f.get("home_team"), "away_name": f.get("away_team"),
           "home_short": f.get("home_short"), "away_short": f.get("away_short"),
           "home_iid": home_iid, "away_iid": away_iid, "match_iid": match_iid,
           "provider_updated_at": f.get("updated_at"), "polled_at": now}
    for k in ("ht_home", "ht_away"):
        if k in f:
            doc[k] = f[k]
    changed = any(old.get(k) != doc[k] for k in ("status", "hs", "as", "minute")) if old else True
    if old.get("status") != doc["status"] and doc["status"] in FINAL:
        doc["final_at"] = now
    db.live_fixtures.update_one({"sid": sid}, {"$set": doc}, upsert=True)
    if match_iid:                                           # a light mirror on our match, for the Today and match pages
        db.matches.update_one({"iid": match_iid}, {"$set": {"live": {k: doc[k] for k in ("status", "minute", "hs", "as", "pen_home", "pen_away")} | {"sid": sid, "at": now}}})
    return {"changed": changed, "doc": doc, "score_changed": bool(old) and (old.get("hs"), old.get("as")) != (doc["hs"], doc["as"]),
            "status_changed": bool(old) and old.get("status") != doc["status"]}


def store_events(db, fixture_sid: int, events: list, now) -> int:
    """Replace the fixture's events with the provider's list (it is the full list each time)."""
    fx = db.live_fixtures.find_one({"sid": fixture_sid}, {"home_iid": 1, "away_iid": 1}) or {}
    rows = []
    for e in events or []:
        eid = e.get("id") or int(hashlib.sha1(f"{fixture_sid}|{e.get('event_type')}|{e.get('player_name')}|{e.get('minute')}".encode()).hexdigest()[:12], 16)
        side = e.get("team_side")
        rows.append({"fixture_sid": fixture_sid, "eid": int(eid), "type": e.get("event_type"), "side": side,
                     "player_name": e.get("player_name"), "minute": e.get("minute"), "minute_num": _minute_num(e.get("minute")),
                     "extra": e.get("extra_info"), "team_iid": fx.get("home_iid") if side == "home" else fx.get("away_iid") if side == "away" else None,
                     "at": now})
    db.live_events.delete_many({"fixture_sid": fixture_sid})
    if rows:
        db.live_events.insert_many(rows)
    db.live_fixtures.update_one({"sid": fixture_sid}, {"$set": {"events_at": now, "events_n": len(rows)}})
    return len(rows)


def store_lineups(db, fixture_sid: int, data: dict, now) -> dict:
    """Keep the lineups; match names to our players inside the mapped club. If enough starters match with confidence,
    write them as a confirmed eleven so the engine can use them (only when PitchAPI has none). docs/23 §5."""
    fx = db.live_fixtures.find_one({"sid": fixture_sid}) or {}
    conf = float(S.get(db, "sportapi.min_confidence"))
    out = {}
    for side in ("home", "away"):
        team_iid = fx.get(f"{side}_iid")
        squad = list(db.players.find({"team_iid": team_iid}, {"_id": 0, "iid": 1, "name": 1, "pos": 1})) if team_iid else []
        block = (data or {}).get(side) or {}
        rows, claimed = [], {}
        for started, lst in ((True, block.get("starters") or []), (False, block.get("subs") or [])):
            for p in lst:
                pos = POS.get(str(p.get("position") or "").lower())
                scored = sorted(((player_score(q["name"], q.get("pos"), p.get("name") or "", p.get("position")), q) for q in squad), key=lambda x: -x[0])
                best = scored[0] if scored else (0.0, None)
                runner = scored[1][0] if len(scored) > 1 else 0.0
                ok = best[1] is not None and best[0] >= conf and best[0] - runner >= 0.04
                row = {"name": p.get("name"), "position": p.get("position"), "pos": pos, "shirt": p.get("shirt"), "captain": bool(p.get("is_captain")),
                       "mins": p.get("mins_played"), "started": started, "player_iid": best[1]["iid"] if ok else None, "score": round(best[0], 3)}
                if ok:
                    claimed.setdefault(best[1]["iid"], []).append(row)
                rows.append(row)
        for iid, rs in claimed.items():                    # two names claiming one player: trust neither
            if len(rs) > 1:
                for r in rs:
                    r["player_iid"] = None
        matched = sum(1 for r in rows if r["started"] and r["player_iid"])
        n_start = sum(1 for r in rows if r["started"])
        db.live_lineups.update_one({"fixture_sid": fixture_sid, "side": side},
                                   {"$set": {"fixture_sid": fixture_sid, "side": side, "team_iid": team_iid, "players": rows,
                                             "starters": n_start, "matched_starters": matched, "fetched_at": now}}, upsert=True)
        out[side] = {"starters": n_start, "matched": matched}
        if (S.get(db, "sportapi.lineups_to_engine") and fx.get("match_iid") and team_iid and n_start == 11 and matched == 11
                and not db.lineups.find_one({"match_iid": fx["match_iid"], "team_iid": team_iid, "confirmed": True, "source": {"$ne": "sportapi"}})):
            db.lineups.delete_many({"match_iid": fx["match_iid"], "team_iid": team_iid, "source": "sportapi"})
            db.lineups.insert_many([{"match_iid": fx["match_iid"], "team_iid": team_iid, "player_iid": r["player_iid"], "started": r["started"],
                                     "confirmed": True, "source": "sportapi", "shirt_number": str(r["shirt"] or ""), "is_captain": r["captain"],
                                     "fetched_at": now} for r in rows if r["player_iid"]])
            db.matches.update_one({"iid": fx["match_iid"]}, {"$set": {"lineups_at": now, "lineups_confirmed": True}})   # the engine re-runs on this
            out[side]["to_engine"] = True
    db.live_fixtures.update_one({"sid": fixture_sid}, {"$set": {"lineups_at": now, "lineups_ok": bool(out.get("home", {}).get("starters"))}})
    return out


# ------------------------------------------------------------------ the minute job
def _due(last, seconds, now) -> bool:
    return last is None or (now - _aware(last)).total_seconds() >= seconds


def live_tick(db, client: Client | None = None, now=None) -> dict:
    """Call every minute. Spends calls only when something is due. Returns what it did."""
    now = now or utcnow()
    if not S.get(db, "sportapi.enabled"):
        return {"status": "off"}
    leagues = tracked_leagues(db)
    if not leagues:
        return {"status": "no_leagues", "note": "Map leagues in sportapi.leagues first."}
    try:
        client = client or Client(db, now=now)
    except NoKey as e:
        return {"status": "no_key", "note": str(e)}
    slow = 2 if client.tight() else 1
    st = db.sportapi_state.find_one({"_id": "live"}) or {}
    today = now.strftime("%Y-%m-%d")
    out = {"status": "ok", "calls": 0, "date_polls": [], "events": 0, "lineups": 0, "finals": 0}
    try:
        # 1) the scoreboard: one call per date. Fast while anything is live or about to start.
        window = timedelta(minutes=int(S.get(db, "sportapi.window_before_min")))
        tracked_today = list(db.live_fixtures.find({"league_iid": {"$in": list(leagues.values())},
                                                    "kickoff": {"$gte": now - timedelta(hours=30), "$lte": now + timedelta(hours=24)}},
                                                   {"_id": 0, "sid": 1, "status": 1, "kickoff": 1, "date": 1}))
        hot = [f for f in tracked_today if f["status"] == LIVE or (f["status"] not in FINAL | DEAD and f.get("kickoff")
               and _aware(f["kickoff"]) - window <= now <= _aware(f["kickoff"]) + timedelta(hours=3))]
        if hot:
            interval = int(S.get(db, "sportapi.live_interval_s")) * slow
        elif any(f.get("kickoff") and now <= _aware(f["kickoff"]) <= now + timedelta(hours=12) for f in tracked_today):
            interval = int(S.get(db, "sportapi.idle_interval_s")) * slow
        else:
            interval = int(S.get(db, "sportapi.quiet_interval_s")) * slow
        dates = {today} | {f["date"] for f in hot if f.get("date")}          # a match that started late yesterday stays followed
        changed = []
        for d in sorted(dates):
            if _due((st.get("date_polls") or {}).get(d), interval, now):
                data = client.get(f"/api/fixtures/date/{d}", "date")
                out["calls"] += 1; out["date_polls"].append(d)
                for f in data.get("data") or []:
                    r = upsert_fixture(db, f, leagues, now)
                    if r and (r["score_changed"] or r["status_changed"]):
                        changed.append(r["doc"])
                db.sportapi_state.update_one({"_id": "live"}, {"$set": {f"date_polls.{d}": now}}, upsert=True)

        # 2) events: on every score or status change, and every few minutes while live (cards, subs)
        refresh = int(S.get(db, "sportapi.events_refresh_s")) * slow
        live_now = list(db.live_fixtures.find({"league_iid": {"$in": list(leagues.values())}, "status": LIVE}, {"_id": 0, "sid": 1, "events_at": 1}))
        want = {f["sid"] for f in changed if f["status"] == LIVE} | {f["sid"] for f in live_now if _due(f.get("events_at"), refresh, now)}
        for sid in sorted(want):
            ev = client.get(f"/api/fixtures/{sid}/events", "events")
            out["calls"] += 1
            if ev.get("data") is not None:
                store_events(db, sid, ev["data"], now); out["events"] += 1

        # 3) a match just finished: one detail call (half-time score, final events), then never again
        for f in db.live_fixtures.find({"league_iid": {"$in": list(leagues.values())}, "status": {"$in": list(FINAL)}, "final_done": {"$ne": True},
                                        "kickoff": {"$gte": now - timedelta(days=2)}}, {"_id": 0, "sid": 1}):
            det = client.get(f"/api/fixtures/{f['sid']}", "final")
            out["calls"] += 1
            fx = det.get("fixture") or {}
            if fx:
                upsert_fixture(db, fx, leagues, now)
                store_events(db, f["sid"], fx.get("events") or [], now)
            db.live_fixtures.update_one({"sid": f["sid"]}, {"$set": {"final_done": True}})
            out["finals"] += 1

        # 4) lineups: at each of the configured minutes before kick-off, until the provider has them
        slots = sorted(int(x) for x in S.get(db, "sportapi.lineups_minutes"))
        for f in db.live_fixtures.find({"league_iid": {"$in": list(leagues.values())}, "status": "Scheduled", "lineups_ok": {"$ne": True},
                                        "kickoff": {"$gte": now, "$lte": now + timedelta(minutes=max(slots) if slots else 0)}},
                                       {"_id": 0, "sid": 1, "kickoff": 1, "lineup_slots": 1}):
            mins = (_aware(f["kickoff"]) - now).total_seconds() / 60
            slot = next((s for s in slots if mins <= s and s not in (f.get("lineup_slots") or [])), None)
            if slot is None:
                continue
            lu = client.get(f"/api/fixtures/{f['sid']}/lineups", "lineups")
            out["calls"] += 1
            db.live_fixtures.update_one({"sid": f["sid"]}, {"$addToSet": {"lineup_slots": slot}})
            if lu.get("available") and lu.get("data"):
                store_lineups(db, f["sid"], lu["data"], now); out["lineups"] += 1
    except BudgetExhausted as e:
        out["status"] = "budget"; out["note"] = str(e)
    except SportAPIError as e:
        out["status"] = "error"; out["note"] = str(e)
    db.sportapi_state.update_one({"_id": "live"}, {"$set": {"last_tick": now, "last_result": {k: v for k, v in out.items() if k != "date_polls"}}}, upsert=True)
    return out


# ------------------------------------------------------------------ historical results
def backfill(db, start: str, end: str, client: Client | None = None, now=None, max_seconds: float = 40.0) -> dict:
    """One call per date, oldest first. A date whose fixtures are all final is cached for good and never called again.
    Keeps `sportapi.reserve_for_live` calls spare for today's live scores. Resumable: call again to continue."""
    import time
    now = now or utcnow()
    client = client or Client(db, now=now)
    leagues = tracked_leagues(db)
    d0, d1 = datetime.fromisoformat(start).date(), datetime.fromisoformat(end).date()
    if d1 < d0:
        d0, d1 = d1, d0
    if (d1 - d0).days + 1 > int(S.get(db, "sportapi.backfill_max_days")):
        raise ValueError(f"At most {S.get(db, 'sportapi.backfill_max_days')} days per request.")
    reserve = int(S.get(db, "sportapi.reserve_for_live"))
    t0 = time.monotonic()
    done, stored, skipped = [], 0, []
    d = d0
    while d <= d1:
        ds = d.isoformat()
        if db.sportapi_dates.find_one({"_id": ds, "complete": True}):
            skipped.append(ds); d += timedelta(days=1); continue
        if client.left() <= reserve or time.monotonic() - t0 > max_seconds:
            return {"status": "paused", "done": done, "stored": stored, "next": ds, "calls_left": client.left(),
                    "note": "Budget reserve or time limit reached. Run again (tomorrow if the budget is the reason)."}
        data = client.get(f"/api/fixtures/date/{ds}", "backfill")
        n = 0
        rows = data.get("data") or []
        for f in rows:
            if upsert_fixture(db, f, leagues, now):
                n += 1
        complete = all((f.get("status") in FINAL | DEAD) for f in rows if f.get("league_id") in leagues)
        db.sportapi_dates.update_one({"_id": ds}, {"$set": {"complete": complete and d < now.date(), "tracked": n, "at": now}}, upsert=True)
        done.append(ds); stored += n
        d += timedelta(days=1)
    return {"status": "done", "done": done, "skipped": skipped, "stored": stored, "calls_left": client.left()}


def league_list(db, client: Client | None = None) -> list:
    """For the admin mapping screen. Cached 7 days (1 call a week)."""
    client = client or Client(db)
    data = client.get("/api/leagues", "leagues", cache_days=7)
    out = []
    for c in data.get("data") or []:
        for lg in c.get("leagues") or []:
            out.append({"id": lg.get("id"), "name": lg.get("name"), "country": c.get("country"), "fixtures": lg.get("fixtures_count"), "teams": lg.get("teams_count")})
    return out


# ------------------------------------------------------------------ reads for the pages (no external calls)
STATUS_WORDS = {"Scheduled": "Not started", "LIVE": "Live", "FT": "Full time", "AET": "After extra time", "PENS": "After penalties",
                "Postponed": "Postponed", "Cancelled": "Cancelled", "Suspended": "Suspended"}


def public_fixture(f: dict, names=None) -> dict:
    return {"sid": f["sid"], "match_id": (names or {}).get(("m", f.get("match_iid"))), "league_iid": f.get("league_iid"), "league_name": f.get("league_name"),
            "kickoff": f.get("kickoff"), "status": f.get("status"), "status_text": STATUS_WORDS.get(f.get("status"), f.get("status")),
            "minute": f.get("minute"), "home": {"name": f.get("home_name"), "short": f.get("home_short"), "team": (names or {}).get(("t", f.get("home_iid")))},
            "away": {"name": f.get("away_name"), "short": f.get("away_short"), "team": (names or {}).get(("t", f.get("away_iid")))},
            "score": {"home": f.get("hs"), "away": f.get("as"), "ht_home": f.get("ht_home"), "ht_away": f.get("ht_away"),
                      "pen_home": f.get("pen_home"), "pen_away": f.get("pen_away")}, "winner": f.get("winner"),
            "events_n": f.get("events_n", 0), "updated": f.get("polled_at")}


def _names(db, fixtures):
    import queries as Q
    t = Q._names(db, "teams", [x for f in fixtures for x in (f.get("home_iid"), f.get("away_iid")) if x])
    ms = {m["iid"]: m["id"] for m in db.matches.find({"iid": {"$in": [f["match_iid"] for f in fixtures if f.get("match_iid")]}}, {"_id": 0, "iid": 1, "id": 1})}
    out = {("t", k): v for k, v in t.items()}
    out.update({("m", k): v for k, v in ms.items()})
    return out


def scoreboard(db, day: str | None = None, tz_offset_min: int = 0, now=None) -> dict:
    """Tracked fixtures for the user's local day, grouped by league, live first."""
    now = now or utcnow()
    d = datetime.fromisoformat(day).replace(tzinfo=timezone.utc) if day else now.replace(hour=0, minute=0, second=0, microsecond=0)
    d0 = d - timedelta(minutes=tz_offset_min)
    rows = list(db.live_fixtures.find({"kickoff": {"$gte": d0, "$lt": d0 + timedelta(days=1)}}, {"_id": 0}).sort("kickoff", 1))
    names = _names(db, rows)
    order = {LIVE: 0, "Scheduled": 1}
    rows.sort(key=lambda f: (order.get(f.get("status"), 2), f.get("kickoff") or now))
    groups = {}
    for f in rows:
        groups.setdefault(f.get("league_name") or "Other", []).append(public_fixture(f, names))
    st = db.sportapi_state.find_one({"_id": "live"}) or {}
    return {"leagues": [{"league": k, "fixtures": v} for k, v in groups.items()], "live_count": sum(1 for f in rows if f.get("status") == LIVE),
            "updated": st.get("last_tick")}


def events_for(db, sid: int) -> list:
    return [{k: e.get(k) for k in ("type", "side", "player_name", "minute", "minute_num", "extra")}
            for e in db.live_events.find({"fixture_sid": sid}, {"_id": 0}).sort("minute_num", 1)]


def lineups_for(db, sid: int) -> dict:
    out = {}
    for l in db.live_lineups.find({"fixture_sid": sid}, {"_id": 0}):
        ids = {p["iid"]: p["id"] for p in db.players.find({"iid": {"$in": [r["player_iid"] for r in l["players"] if r.get("player_iid")]}}, {"_id": 0, "iid": 1, "id": 1})}
        out[l["side"]] = {"starters": [dict({k: r.get(k) for k in ("name", "position", "shirt", "captain", "mins")}, player_id=ids.get(r.get("player_iid"))) for r in l["players"] if r["started"]],
                          "subs": [dict({k: r.get(k) for k in ("name", "position", "shirt", "captain", "mins")}, player_id=ids.get(r.get("player_iid"))) for r in l["players"] if not r["started"]]}
    return out


def results(db, day: str) -> dict:
    """Finished fixtures of tracked leagues on a date (from live polling or backfill). No external call."""
    rows = list(db.live_fixtures.find({"date": day, "status": {"$in": list(FINAL)}}, {"_id": 0}).sort("kickoff", 1))
    names = _names(db, rows)
    loaded = bool(db.sportapi_dates.find_one({"_id": day})) or bool(rows)
    return {"date": day, "loaded": loaded, "results": [public_fixture(f, names) for f in rows]}


def status(db, now=None) -> dict:
    now = now or utcnow()
    c = calls_today(db, now)
    st = db.sportapi_state.find_one({"_id": "live"}) or {}
    return {"enabled": bool(S.get(db, "sportapi.enabled")), "key_saved": bool(security.get_provider_key(db, PROVIDER, env_fallback="SPORTAPI_KEY")),
            "calls_today": c["n"], "by_kind": c["by_kind"], "cap": int(S.get(db, "sportapi.daily_calls")), "plan_limit": 2000,
            "leagues": S.get(db, "sportapi.leagues"), "last_tick": st.get("last_tick"), "last_result": st.get("last_result"),
            "live_now": db.live_fixtures.count_documents({"status": LIVE}),
            "teams": {s: db.sportapi_team_map.count_documents({"status": s}) for s in ("auto", "approved", "review", "none", "rejected")},
            "review": list(db.sportapi_team_map.find({"status": "review"}, {"_id": 0}).limit(50)),
            "dates_backfilled": db.sportapi_dates.count_documents({"complete": True})}
```

### `backend/routes_live.py`

```python
"""routes_live.py -- live scores, events, lineups and results from SportAPI (docs/23).

Public routes read our database only: visitors never cause a SportAPI call. The minute job is POST /api/jobs/live
(external pinger, X-CRON-SECRET), which calls sportapi.live_tick.
"""
from __future__ import annotations

import hmac
import os
import re
from typing import Optional

from fastapi import APIRouter, Depends, Header, Query, Response
from pydantic import BaseModel, Field

import admin_queries as AQ
import deps as D
import queries as Q
import sportapi as SP

public = APIRouter(prefix="/api")
admin = APIRouter(prefix="/api/admin/sportapi")
LIVE_CACHE = "public, max-age=15, stale-while-revalidate=30"
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _date(d: str | None) -> str | None:
    if d is not None and not DATE_RE.match(d):
        raise D.err(400, "BAD_DATE", "Use YYYY-MM-DD.")
    return d


@public.get("/live")
def live(response: Response, date: str | None = None, tz: int = Query(0, ge=-840, le=840), db=Depends(D.get_db)):
    """Scoreboard for the user's local day: live first, then upcoming, then finished. Refresh every 30 s in the browser."""
    response.headers["Cache-Control"] = LIVE_CACHE
    return SP.scoreboard(db, _date(date), tz)


@public.get("/live/{sid}/events")
def live_events(sid: int, response: Response, db=Depends(D.get_db)):
    if not db.live_fixtures.find_one({"sid": sid}, {"_id": 1}):
        raise D.err(404, "NOT_FOUND", "No such match.")
    response.headers["Cache-Control"] = LIVE_CACHE
    return {"sid": sid, "events": SP.events_for(db, sid)}


@public.get("/live/{sid}/lineups")
def live_lineups(sid: int, response: Response, db=Depends(D.get_db)):
    if not db.live_fixtures.find_one({"sid": sid}, {"_id": 1}):
        raise D.err(404, "NOT_FOUND", "No such match.")
    response.headers["Cache-Control"] = LIVE_CACHE
    return {"sid": sid, "lineups": SP.lineups_for(db, sid)}


@public.get("/results")
def results(date: str, response: Response, db=Depends(D.get_db)):
    response.headers["Cache-Control"] = "public, max-age=300"
    return SP.results(db, _date(date))


@public.post("/jobs/live")
def jobs_live(x_cron_secret: str | None = Header(default=None), db=Depends(D.get_db)):
    """Call every minute from an external pinger. Spends SportAPI calls only when something is due."""
    if not hmac.compare_digest(x_cron_secret or "", os.environ.get("CRON_SHARED_SECRET", "\0")):
        raise D.err(401, "BAD_SECRET", "Bad secret.")
    return SP.live_tick(db)


# ------------------------------------------------------------------ admin
@admin.get("")
def sportapi_status(user=Depends(D.require_perm("logs.read")), db=Depends(D.get_db)):
    return SP.status(db)


@admin.get("/leagues")
def sportapi_leagues(user=Depends(D.require_perm("settings.read")), db=Depends(D.get_db)):
    """SportAPI's league list for the mapping screen (1 call a week, cached)."""
    try:
        return {"leagues": SP.league_list(db)}
    except SP.NoKey as e:
        raise D.err(400, "NO_KEY", str(e))
    except SP.SportAPIError as e:
        raise D.err(502, "PROVIDER_ERROR", str(e))


class TeamDecision(BaseModel):
    team_id: Optional[str] = Field(default=None, max_length=64)     # our team's public id; empty = reject


@admin.post("/teams/{sid}")
def sportapi_team(sid: int, body: TeamDecision, user=Depends(D.require_perm("jobs.run")), db=Depends(D.get_db)):
    m = db.sportapi_team_map.find_one({"sid": sid})
    if not m:
        raise D.err(404, "NOT_FOUND", "No such SportAPI team.")
    if body.team_id:
        iid = Q.iid_of(db, "teams", body.team_id)
        if not iid:
            raise D.err(404, "NOT_FOUND", "No such team.")
        db.sportapi_team_map.update_one({"sid": sid}, {"$set": {"status": "approved", "our_iid": iid}})
        for side in ("home", "away"):                                       # fixtures already stored pick up the link
            db.live_fixtures.update_many({f"{side}_sid": sid}, {"$set": {f"{side}_iid": iid}})
    else:
        db.sportapi_team_map.update_one({"sid": sid}, {"$set": {"status": "rejected", "our_iid": None}})
    AQ.audit(db, user, "sportapi.team", str(sid), {"team_id": body.team_id})
    return {"ok": True}


class Backfill(BaseModel):
    start: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    end: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")


@admin.post("/backfill")
def sportapi_backfill(body: Backfill, user=Depends(D.require_perm("jobs.run")), db=Depends(D.get_db)):
    """Historical results: one call per date, resumable, keeps the live reserve. Run again to continue."""
    try:
        out = SP.backfill(db, body.start, body.end)
    except ValueError as e:
        raise D.err(400, "TOO_MANY_DAYS", str(e))
    except SP.NoKey as e:
        raise D.err(400, "NO_KEY", str(e))
    except SP.BudgetExhausted as e:
        raise D.err(429, "BUDGET", str(e))
    AQ.audit(db, user, "sportapi.backfill", None, {"start": body.start, "end": body.end, "status": out["status"]})
    return out


@admin.post("/tick")
def sportapi_tick(user=Depends(D.require_perm("jobs.run")), db=Depends(D.get_db)):
    """Run the minute job now (same rules, same budget)."""
    return SP.live_tick(db)
```

### `frontend/src/pages/Live.jsx`

```jsx
// Live scores (docs/23). Reads GET /api/live from our own server every 30 seconds while the tab is visible.
// The server refreshes from SportAPI on its own schedule; this page never talks to SportAPI.
import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { get } from "../lib/api";
import { utc } from "../lib/time";
import { Crest } from "../components/Media";
import LiveStatus from "../components/LiveStatus";
import MatchEvents from "../components/MatchEvents";
import { Empty, ErrorBox, Loading } from "../components/States";

const iso = (d) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;

function useLive(date) {
  const [state, setState] = useState({ data: null, error: null, loading: true });
  useEffect(() => {
    let stop = false, timer = null;
    const tz = -new Date().getTimezoneOffset();
    const load = () => get("/live", { date, tz })
      .then((data) => !stop && setState({ data, error: null, loading: false }))
      .catch((error) => !stop && setState((s) => ({ ...s, error, loading: false })));
    const loop = () => { if (document.visibilityState === "visible") load(); timer = setTimeout(loop, 30000); };
    load(); timer = setTimeout(loop, 30000);
    const onVis = () => document.visibilityState === "visible" && load();
    document.addEventListener("visibilitychange", onVis);
    return () => { stop = true; clearTimeout(timer); document.removeEventListener("visibilitychange", onVis); };
  }, [date]);
  return state;
}

function Row({ f }) {
  const [open, setOpen] = useState(false);
  const [events, setEvents] = useState(null);
  const [lineups, setLineups] = useState(null);
  useEffect(() => {
    if (!open) return;
    get(`/live/${f.sid}/events`).then((r) => setEvents(r.events)).catch(() => setEvents([]));
    get(`/live/${f.sid}/lineups`).then((r) => setLineups(r.lineups)).catch(() => setLineups({}));
  }, [open, f.sid, f.events_n]);
  const sc = f.score || {};
  const show = f.status !== "Scheduled" && sc.home != null;
  return (
    <li className={`live-row ${f.status === "LIVE" ? "is-live" : ""}`}>
      <button className="live-main" aria-expanded={open} onClick={() => setOpen((o) => !o)}>
        <span className="live-status"><LiveStatus status={f.status} minute={f.minute} kickoff={f.kickoff} text={f.status_text} /></span>
        <span className="team"><Crest team={f.home.team} size={20} /> {f.home.team?.name || f.home.name}</span>
        <span className="live-score" aria-label={show ? `${sc.home} to ${sc.away}` : "not started"}>
          {show ? `${sc.home} - ${sc.away}` : "v"}
          {sc.pen_home != null && <span className="muted small"> ({sc.pen_home}-{sc.pen_away} pens)</span>}
        </span>
        <span className="team team-away">{f.away.team?.name || f.away.name} <Crest team={f.away.team} size={20} /></span>
      </button>
      {open && (
        <div className="live-detail">
          {sc.ht_home != null && <p className="muted small">Half-time {sc.ht_home} - {sc.ht_away}</p>}
          {events === null ? <Loading label="Events" /> : <MatchEvents events={events} />}
          {lineups && (lineups.home || lineups.away) && (
            <div className="lineups">
              {["home", "away"].map((side) => lineups[side] && (
                <div key={side}>
                  <h3 className="small">{side === "home" ? f.home.name : f.away.name}</h3>
                  <ol className="plain small">{lineups[side].starters.map((p, i) => (
                    <li key={i}>{p.shirt} {p.player_id ? <Link to={`/player/${p.player_id}`}>{p.name}</Link> : p.name}{p.captain ? " (C)" : ""}</li>
                  ))}</ol>
                </div>
              ))}
            </div>
          )}
          {f.match_id && <p><Link to={`/match/${f.match_id}`}>Forecasts and stats for this match</Link></p>}
        </div>
      )}
    </li>
  );
}

export default function Live() {
  const [day, setDay] = useState(iso(new Date()));
  const days = useMemo(() => [-1, 0, 1].map((i) => { const d = new Date(); d.setDate(d.getDate() + i); return d; }), []);
  const q = useLive(day);
  return (
    <section>
      <h1>Live scores {q.data?.live_count > 0 && <span className="live-chip"><span className="live-dot" aria-hidden="true" />{q.data.live_count} live</span>}</h1>
      <div className="date-strip" role="tablist" aria-label="Day">
        {days.map((d) => (
          <button key={iso(d)} role="tab" aria-selected={iso(d) === day} className={iso(d) === day ? "chip chip-on" : "chip"} onClick={() => setDay(iso(d))}>
            {["Yesterday", "Today", "Tomorrow"][days.indexOf(d)]}
          </button>
        ))}
      </div>
      {q.loading ? <Loading /> : q.error && !q.data ? <ErrorBox error={q.error} /> : !q.data.leagues.length ? (
        <Empty>No matches in the leagues we follow on this day.</Empty>
      ) : q.data.leagues.map((g) => (
        <div key={g.league} className="card">
          <h2>{g.league}</h2>
          <ul className="plain">{g.fixtures.map((f) => <Row key={f.sid} f={f} />)}</ul>
        </div>
      ))}
      {q.data?.updated && <p className="muted small">Updated {utc(q.data.updated).toLocaleTimeString()}. Scores refresh every 30 seconds.</p>}
    </section>
  );
}
```

### `frontend/src/components/LiveStatus.jsx`

```jsx
// Status chip for a match (docs/23): "Live 67'", "HT", "Full time", or the kick-off time.
import { utc } from "../lib/time";

const WORDS = { FT: "Full time", AET: "After extra time", PENS: "After penalties", Postponed: "Postponed", Cancelled: "Cancelled", Suspended: "Suspended" };

export default function LiveStatus({ status, minute, kickoff, text }) {
  if (status === "LIVE") {
    const m = minute === "HT" ? "HT" : minute || "";
    return <span className="live-chip" aria-label={`Live, ${m === "HT" ? "half-time" : `minute ${m}`}`}><span className="live-dot" aria-hidden="true" />{m === "HT" ? "HT" : `Live ${m}`}</span>;
  }
  if (status === "Scheduled" || !status) {
    return <time className="muted">{kickoff ? utc(kickoff).toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" }) : "–"}</time>;
  }
  return <span className={`status-chip ${["Postponed", "Cancelled", "Suspended"].includes(status) ? "status-warn" : ""}`}>{text || WORDS[status] || status}</span>;
}
```

### `frontend/src/components/MatchEvents.jsx`

```jsx
// Match events timeline (docs/23): goals, cards, substitutions from SportAPI, sorted by minute.
// Home events on the left, away on the right. Text labels as well as symbols, so colour and icons never carry meaning alone.
const KIND = {
  goal: { icon: "●", label: "Goal" },
  own_goal: { icon: "●", label: "Own goal" },
  penalty: { icon: "●", label: "Penalty goal" },
  missed_penalty: { icon: "○", label: "Penalty missed" },
  yellow_card: { icon: "▮", label: "Yellow card", cls: "ev-yellow" },
  red_card: { icon: "▮", label: "Red card", cls: "ev-red" },
  second_yellow: { icon: "▮", label: "Second yellow", cls: "ev-red" },
  substitution: { icon: "⇄", label: "Substitution" },
};

export default function MatchEvents({ events = [], compact = false }) {
  if (!events.length) return <p className="muted small">No events yet.</p>;
  return (
    <ol className={"events" + (compact ? " events-compact" : "")} aria-label="Match events">
      {events.map((e, i) => {
        const k = KIND[e.type] || { icon: "•", label: (e.type || "Event").replace(/_/g, " ") };
        return (
          <li key={i} className={`ev ev-${e.side || "none"} ${k.cls || ""}`}>
            <span className="ev-min">{e.minute}</span>
            <span className="ev-icon" aria-hidden="true">{k.icon}</span>
            <span className="ev-text"><strong>{e.player_name || ""}</strong> <span className="muted">{k.label}{e.extra && e.extra !== k.label ? ` · ${e.extra}` : ""}</span></span>
          </li>
        );
      })}
    </ol>
  );
}
```

### `frontend/src/styles/live.css`

```css
/* Live scores (docs/23) */
.live-chip { white-space: nowrap; display: inline-flex; align-items: center; gap: 6px; padding: 2px 8px; border-radius: var(--r-pill); background: color-mix(in srgb, var(--c-down) 18%, transparent); color: var(--c-text); font-size: var(--fs-xs); font-weight: 700; vertical-align: middle; }
.live-dot { width: 8px; height: 8px; border-radius: 50%; background: var(--c-down); }
@media (prefers-reduced-motion: no-preference) { .live-dot { animation: pulse 1.6s ease-in-out infinite; } }
@keyframes pulse { 50% { opacity: 0.35; } }
.status-chip { font-size: var(--fs-xs); color: var(--c-text2); }
.status-warn { color: var(--c-tier-watch); }
.live-row { border-top: 1px solid var(--c-border); }
.live-main { width: 100%; display: grid; grid-template-columns: 72px 1fr 64px 1fr; align-items: center; gap: var(--s-2); min-height: 52px; background: none; border: 0; color: var(--c-text); font: inherit; text-align: left; cursor: pointer; padding: var(--s-2) 0; }
.live-score { text-align: center; font-weight: 700; font-variant-numeric: tabular-nums; }
.team-away { justify-content: flex-end; text-align: right; }
.is-live .live-score { color: var(--c-text); }
.live-detail { padding: 0 0 var(--s-3); }
.events { list-style: none; margin: 0; padding: 0; display: grid; gap: 4px; }
.ev { display: grid; grid-template-columns: 44px 18px 1fr; gap: var(--s-2); align-items: baseline; font-size: var(--fs-sm); }
.ev-away { direction: rtl; text-align: right; }
.ev-away > * { direction: ltr; }
.ev-min { color: var(--c-text2); font-variant-numeric: tabular-nums; }
.ev-yellow .ev-icon { color: var(--c-tier-watch); }
.ev-red .ev-icon { color: var(--c-down); }
.lineups { display: grid; grid-template-columns: 1fr 1fr; gap: var(--s-4); margin-top: var(--s-3); }
.fixture-row .live-chip { justify-self: start; }
@media (max-width: 480px) { .live-main { grid-template-columns: 56px 1fr 48px 1fr; } }
.fx-live { display: flex; flex-direction: column; gap: 2px; font-size: var(--fs-xs); }
```

### Mounting (already in `backend/server.py`)

```python
import routes_live
...
app.include_router(routes_live.public)
app.include_router(routes_live.admin)
app.include_router(routes_teams.router)     # before routes_data
app.include_router(routes_data.router)
```

### Indexes (already in `backend/mongo_init.py`)

```python
ix("live_fixtures", [("sid", ASC)], unique=True)
ix("live_fixtures", [("kickoff", ASC)])
ix("live_fixtures", [("status", ASC), ("league_iid", ASC)])
ix("live_fixtures", [("date", ASC), ("status", ASC)])
ix("live_fixtures", [("match_iid", ASC)])
ix("live_events", [("fixture_sid", ASC), ("minute_num", ASC)])
ix("live_lineups", [("fixture_sid", ASC), ("side", ASC)], unique=True)
ix("sportapi_team_map", [("sid", ASC)], unique=True)
ix("sportapi_team_map", [("status", ASC)])
ix("sportapi_cache", [("expires_at", ASC)], expireAfterSeconds=0)
```
