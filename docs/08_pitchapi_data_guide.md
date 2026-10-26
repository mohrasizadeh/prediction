
# 08. PitchAPI data guide

Ported from the Docs guide "PitchAPI Data Guide for the Builder" (read from pitchapi.dev on 2026-10-25) and changed for Emergent: Python, MongoDB, settings instead of a mapping file. The code that follows this guide is `backend/normalize.py` and `ingest.py`, tested against a fake PitchAPI with invented key names. **The real key names are still unverified. Do check A first.**


## 1. The short answer

One finished match costs 3 calls: team stats, player stats and lineups. One league season costs 1 list call to find all its matches. That is everything the engine needs. This guide comes from a full read of pitchapi.dev on 2026-10-25. Where the page is silent, this guide says Verify and tells you how.

| We need | Call | Where it sits in the response |
|---|---|---|
| League ids and seasons | `GET /v1/leagues` | `data.leagues[]` with `id`, `name`, `country_code`, `seasons[]` |
| Every match of a season: id, kickoff, status, score | `GET /v1/leagues/{id}/matches?season=2025/2026&status=all` | `data.matches[]` |
| Upcoming matches for the next days | `GET /v1/date/{date}?status=upcoming` | `data.matches[]` |
| Team shots, shots on target, possession, xG, corners, tackles | `GET /v1/matches/{id}/stats` | `data.periods[period = All].groups[].items[]`, read by `key` |
| Player shots, shots on target, tackles, minutes | `GET /v1/matches/{id}/players` | `data[].stats[].stats{label: {key, stat}}`, read by `stat.key` |
| Who started, formation, confirmed or predicted | `GET /v1/matches/{id}/lineups` | `data.home` and `data.away`: `starters[]`, `subs[]`, `confirmed` |

Three traps to know first

- The default is played matches only. `/v1/date/{date}` and `/v1/leagues/{id}/matches` skip upcoming matches unless you pass `status=upcoming` or `status=all`.
- Team stats are strings. `/stats` returns values like `"329 (82%)"`. Parse them with `format_type` (section 5).
- Read by `key`, never by the display label. Labels are for humans and may change.

Never call these. They return large shot, heatmap or pass data that would fill the database and add nothing to the forecasts: `/shots`, `/shots/{shot_id}`, `/players/{player_id}/shots`, `/heatmaps`, `/advanced/network`, `/momentum`, `/events`. Use `/advanced` and `/advanced/players` only if the Verify step in section 7 shows we need them for tackles.

Step 0, before any code: run the calls in section 6, step 6.1, on one finished Premier League match in the admin endpoint explorer. Save the three full JSON responses. Every Verify item in this guide is answered by those three files.


## 2. How the API works

PitchAPI is a read-only REST API for football data. Every call is a `GET`.

```
curl https://api.pitchapi.dev/v1/leagues -H "X-API-KEY: $PITCH_KEY"
```

| Topic | What the page says | What we do |
|---|---|---|
| Base URL | `https://api.pitchapi.dev`. Plain HTTP is refused, not redirected. | Always HTTPS. |
| Auth | Header `X-API-KEY`. Keys start `pk_live_` (production) or `pk_test_`. PitchAPI stores only a SHA-256 hash, so a lost key cannot be recovered. | Key is entered in admin and stored encrypted. Keep it server-side only. A free key comes from pitchapi.dev/get-api-key. |
| Envelope | Every response is one JSON object with either `data` or `error`, never both. | Unwrap in one place (`PitchClient.fetch`). |
| Time | Timestamps are RFC 3339 in UTC. Dates are `YYYY-MM-DD`. | Store UTC datetimes. |
| Missing values | Optional fields are omitted when unavailable. `null` means "undefined", not zero. | Treat omitted and null as missing. Never write zero. |
| IDs | Opaque: a prefix, an underscore and six base62 characters. `m_` match, `s_` shot, `p_` player, `t_` team, `l_` league. Shot ids are unique only inside their match. | Store as text in `ext_id`. Never parse them. |
| Images | Responses carry `image_url` on `https://cdn.pitchapi.dev/...` for leagues, teams and players. | Store the URL. Hot-linking terms are not stated; Verify before launch. |


### Errors

Branch on `error.code`, never on the message text.

| HTTP | Code | Meaning | What the worker does |
|---|---|---|---|
| 401 | `UNAUTHORIZED` | Key missing or invalid | Stop all jobs, show a red banner in admin |
| 429 | `RATE_LIMIT_EXCEEDED` | Fair-use burst limit hit. A `Retry-After` header says how long to wait. | Wait, retry up to 3 times, then open the circuit breaker |
| 400 | `INVALID_PARAMETER` | A parameter has the wrong format | Log as a bug. Do not retry. |
| 404 | `RESOURCE_NOT_FOUND` | No resource with that id | Store as a 10-minute negative cache entry |
| 404 | `ANALYTICS_UNAVAILABLE` | Match exists but was never rated (only on `/advanced` routes) | Mark the match as having no advanced data. Do not retry. |
| 404 | `HALVES_UNAVAILABLE` | Match exists but has no per-half player stats (only on `/halves` routes) | Same as above |
| 500 | `INTERNAL_SERVER_ERROR` | Server fault | Back off 2 s, 4 s, 8 s, then stop for this run |


### Official SDKs

The page offers a Python package (`pip install pitchapi`, PyPI page) and a TypeScript client (released 2026-10-24). They unwrap the envelope, raise typed errors and retry 429 and 5xx responses.

Do not use the SDKs in the worker. They retry on their own, which would hide calls from our call log and our daily budget. Use plain `httpx` inside `PitchClient.fetch`. Use the SDKs only in scratch scripts.


## 3. Plan, limits and coverage

There is one plan and it is free. The page states:

- No card, no trial, no request allowance. All endpoints are included.
- 77 leagues, with history back to 2021. (An earlier third-party review said 42. Trust the page, and confirm the real count with `GET /v1/leagues`.)
- No `X-RateLimit` headers. The only limit is an unpublished fair-use burst guard. Hitting it returns HTTP 429 `RATE_LIMIT_EXCEEDED` with a `Retry-After` header.
- Not on the page: a numeric burst limit, commercial-use terms, an uptime promise. Verify the terms with PitchAPI before charging users.


### Recent changes that matter to us (from the page's changelog)

| Date | Change | What it means for the build |
|---|---|---|
| 2026-10-24 | TypeScript SDK released | Optional. See section 2. |
| 2026-09-30 | Per-half player endpoints added | We do not use them. |
| 2026-09-19 | 26 leagues restored. Their match ids changed, and momentum, player ratings and predicted lineups differ for them. | Never assume ids are stable. Upsert by `ext_id`. If a league's ids change, re-run its backfill instead of patching rows. |
| 2026-08-31 | Predicted lineups and the `confirmed` flag added | Always read `confirmed` before using a lineup. |
| 2026-08-31 | Upcoming fixtures and the `status` filter added | Upcoming data needs `status=upcoming` or `status=all`. |


### What a call budget looks like

These are our own estimates, for one 380-match league season.

| Job | Calls | Notes |
|---|---|---|
| Backfill one league-season | about 1,141 | 1 list call, plus 3 per finished match (stats, players, lineups) |
| Backfill 5 leagues, 5 seasons | about 28,500 | About 14 days at a 2,000-call daily budget |
| Steady state, one league, one week | about 150 | New results at 3 calls each, plus fixture refreshes and up to 6 lineup checks per upcoming match |
| Steady state, 5 leagues, one day | about 110 | Far below the 2,000 default budget |

Start with one league and one season, measure the real database size and call count, then widen. Default pacing: 3 requests per second, 2 in flight, and honour every `Retry-After`.


## 4. Endpoint reference: all 24 calls

Base URL `https://api.pitchapi.dev`, header `X-API-KEY`. Use = the worker calls it. Optional = only when a feature needs it. Never = do not call it (size or no value for us).

| # | Call | Parameters | Returns (top level) | Our use |
|---|---|---|---|---|
| 1 | `GET /v1/date/{date}` | `date` as YYYY-MM-DD. Query `status`: `played` (default), `upcoming`, `all`. | `date`, `matches[]`: `id`, `league{id,name}`, `home_team{id,name}`, `away_team{id,name}`, `time_utc`, `status`, `score_home`, `score_away`. Covered matches only. | Use: upcoming fixtures (`status=upcoming`) |
| 2 | `GET /v1/leagues` | none | `leagues[]`: `id`, `name`, `country_code`, `image_url`, `seasons[]`, `is_free` (always true) | Use: find league ids and seasons |
| 3 | `GET /v1/leagues/{id}` | `id` | `id`, `name`, `country_code`, `season` (current), `image_url` | Optional |
| 4 | `GET /v1/leagues/{id}/matches` | `id`. Query `season` (`2025/2026`, or `2025` for calendar-year leagues; default current). Query `status`: `played` (default), `upcoming`, `all`. | `league{id,name,season,image_url}`, `matches[]`: `id`, `date`, `time_utc`, `status`, `home_team{id,name}`, `away_team{id,name}`, `score_home`, `score_away` | Use: backfill and fixtures |
| 5 | `GET /v1/teams/{id}` | `id` | `id`, `name`, `image_url` | Optional |
| 6 | `GET /v1/players/{id}` | `id` | `id`, `name`, `short_name`, `shirt_number` (string), `position_id`, `country_code`, `image_url` | Optional: only for players we display |
| 7 | `GET /v1/matches/{id}` | `id` | `id`, `league`, `home_team`, `away_team` (with `image_url`), `date`, `time_utc`, `status`, `score_home`, `score_away`, `round_name`, `has_playoff`, `referee`, `stadium` | Optional: referee, stadium, crests |
| 8 | `GET /v1/matches/{id}/shots` | `id` | `match_id`, `periods[]` of `shots[]` | Never |
| 9 | `GET /v1/matches/{id}/shots/{shot_id}` | `id`, `shot_id` | one shot | Never |
| 10 | `GET /v1/matches/{id}/momentum` | `id` | `points[]`: `minute`, `value` (can be empty) | Never |
| 11 | `GET /v1/matches/{id}/events` | `id` | `events[]`: goals, substitutions, `yellowcard`, `redcard` | Never now. Phase 2 for a cards market. |
| 12 | `GET /v1/matches/{id}/players` | `id` | `data[]`: `player`, `team_id`, `stats[]` groups | Use: player stats |
| 13 | `GET /v1/matches/{id}/players/{player_id}` | `id`, `player_id` | one player's stats | Never (use #12) |
| 14 | `GET /v1/matches/{id}/players/halves` | `id` | `players[]` with `periods[]`. Can return `HALVES_UNAVAILABLE`. | Never |
| 15 | `GET /v1/matches/{id}/players/{player_id}/halves` | `id`, `player_id` | one player by half | Never |
| 16 | `GET /v1/matches/{id}/players/{player_id}/shots` | `id`, `player_id` | `player`, `shots[]` | Never |
| 17 | `GET /v1/matches/{id}/lineups` | `id` | `match_id`, teams, `home` and `away` lineups | Use: starters, confirmed flag |
| 18 | `GET /v1/matches/{id}/h2h` | `id` | `home_wins`, `draws`, `away_wins`, `total_matches`, `recent_matches[]` | Optional. We compute head-to-head from our own database at no call cost. |
| 19 | `GET /v1/matches/{id}/stats` | `id` | `match_id`, `periods[]` of `groups[]` of `items[]` | Use: team stats |
| 20 | `GET /v1/matches/{id}/heatmaps` | `id`. Query `frame`: `acting_ltr` (default) or `home_ltr`. | grid plus sparse cells for teams and players | Never |
| 21 | `GET /v1/matches/{id}/advanced` | `id` | `teams[]` (home first): `actions`, `possession_value`, `passing`, `carrying`, `creation`, `defending`, `territory`, `tempo`. `ANALYTICS_UNAVAILABLE` if never rated. | Only if section 7 check A fails |
| 22 | `GET /v1/matches/{id}/advanced/players` | `id` | `players[]` with `minutes_played`, metric groups, `goalkeeping` (null for outfielders) | Only if section 7 check A fails |
| 23 | `GET /v1/matches/{id}/advanced/network` | `id` | pass network nodes and edges | Never |
| 24 | `GET /v1/matches/{id}/advanced/players/{player_id}` | `id`, `player_id` | one player's advanced metrics | Never |


### Status values

The page shows `finished` (played) and `not_started` (upcoming, with null scores). It lists no others. Verify what a postponed, abandoned or live match returns. Until then, treat only `finished` as final, `not_started` as scheduled, and anything else as "skip and log an ingest issue".


### Page-ordering gotcha

The page says groups inside `/stats` come back in alphabetical order and periods are separate entries. Never rely on position in an array. Find things by `group_name`, `period` and `key`.


## 5. Field maps: PitchAPI to our database

Status tags: Confirmed = shown in the page's own example. Inferred = read from an example, not stated. Verify = the page does not give it. Resolve every Verify with check A in section 7 and write the answer into the settings `provider.pitchapi.team_keys`, `provider.pitchapi.player_keys` and `provider.position_map` (Admin → Settings → Provider).


### Match list to `matches`

| Our column | PitchAPI field (`/v1/leagues/{id}/matches`, `/v1/date/{date}`) | Status |
|---|---|---|
| `ext_id` | `matches[].id` | Confirmed |
| `kickoff` | `time_utc` (RFC 3339 UTC) | Confirmed |
| `status` | `status`: `finished` becomes `final`, `not_started` becomes `scheduled` | Confirmed for these two. Others Verify. |
| `hg`, `ag` | `score_home`, `score_away` (null while upcoming) | Confirmed |
| teams | `home_team.id`, `home_team.name`, `away_team.id`, `away_team.name` into `teams.external_id`, `teams.name` | Confirmed |
| league | `league.id` and `league.name` (date endpoint) or the `{id}` you called (league endpoint) | Confirmed |
| `round_name` (new optional column) | Only on `/v1/matches/{id}`. A label like `11`. We build our own numeric `round` (`07_ingest_and_caching.md`, section 5). | Confirmed |


### Team stats to `team_match_stats` (from `/v1/matches/{id}/stats`)

Structure: `data.periods[]` has one entry per half plus the whole match. Use the entry whose `period` is `All`. Inside it, `groups[]` hold `items[]`. Each item has `title`, `key`, `home`, `away`, `format_type`.

| Our column | `key` to read | `format_type` | Status |
|---|---|---|---|
| `poss` | `BallPossesion` (spelled exactly like this, one "s" missing in "Possession") | `integer` | Key Confirmed. What it measures Verify: the page says its own `territory.possession_pct` is a pass share, not standard possession. |
| `xg` | `expected_goals` | `double` | Confirmed |
| `shots` | a key under a Shots group | `integer` | Verify. Search items whose `title` is "Total shots". |
| `sot` | a key under a Shots group | `integer` | Verify. Search "Shots on target". The page warns the definition varies between sources. |
| `corners` | not documented anywhere on the page | `integer` | Verify. Search "Corners". If absent, the corners market stays off. |
| `tackles` | not documented for `/stats` | `integer` | Verify. Search "Tackles". Fallback: sum of player tackles (below). |
| `*_against` columns | The other side's value from the same item |  | Derived: for the home team use `away`, and the reverse |

Team values are strings. Parse with `format_type`:

| `format_type` | Example | Parse as |
|---|---|---|
| `integer` | `"45"` | whole number |
| `integerWithPercentage` | `"329 (82%)"` | the number before the first space: 329 |
| `double` | `"2.92"` | decimal |
| `distance` | metres | decimal |
| empty string | `"37"` | plain number |

```python
def parse_team_value(v):
    if v is None or v == "":
        return None
    try:
        return float(str(v).split(" ")[0])      # "329 (82%)" -> 329.0
    except ValueError:
        return None                              # missing stays None, never 0
```


### Player stats to `player_match_stats` (from `/v1/matches/{id}/players`)

Structure: `data[]` has one entry per player who featured (players who did not play are absent). Each has `player{id,name,position_id,image_url}`, `team_id`, and `stats[]`. Each element of `stats[]` is a group (`top_stats`, `attack`, `defense`, `duels`, `physical_metrics`). Inside a group, `stats` is an object keyed by display label; each value is `{ key, stat: { type, value, total? } }`. Read by `key`.

| Our column | Group and `key` | `stat.type` | Status |
|---|---|---|---|
| `shots` | `top_stats`, `total_shots` | `integer` | Confirmed |
| `sot` | `top_stats`, `shot_accuracy`, use `value` | `fractionWithPercentage` (`value` = made, `total` = attempts) | Inferred from the example (value 3, total 5, with 5 total shots). Verify. |
| `minutes` | `top_stats`. The page says it holds minutes. | `integer` | Key Verify |
| `tackles` | `defense`. The page says it holds tackles. | likely `integer` or a fraction | Key and type Verify. If it is a fraction, use `value` (won) everywhere. |
| `pos` | `player.position_id` (integer) |  | Meaning Verify. See below. |
| `started` | From lineups (below), not from this endpoint |  | Derived |
| `team_shots`, `team_sot`, `team_tackles` | Sum of the same keys over that team's players in this match |  | Derived. Keep team and player definitions identical. If the sum differs from the `/stats` team value by more than 1 for shots, write an `ingest_issues` row. |

```python
def player_stat(p, group, key, use="value"):
    for g in p.get("stats", []):
        if g.get("key") != group:
            continue
        for entry in (g.get("stats") or {}).values():
            if entry.get("key") == key:
                st = entry.get("stat") or {}
                if st.get("type") == "boolean":
                    return None
                return st.get(use, st.get("value"))    # for fraction types, value = made count
    return None
```

Rules for gaps. Goalkeepers have no `attack`, `defense` or `duels` groups. Store `null` for their tackles, never 0, and the engine drops goalkeepers from those markets. An outfielder with minutes but no `defense` group means missing data. Skip that match for the tackles market and log an issue.

Position. The page defines `position_id` only for substitutes in lineups: 0 goalkeeper, 1 defender, 2 midfielder, 3 attacker, -1 unclassified. For starters it is a slot on the formation grid, and the examples show 4 for a striker. Store the raw number. Keep the mapping to our `GK/DEF/MID/FWD` in a setting (`provider.position_map`, JSON, editable in admin) and fill it after check A.


### Lineups to `lineups` (from `/v1/matches/{id}/lineups`)

| Our column | PitchAPI field | Status |
|---|---|---|
| `confirmed` | `data.home.confirmed` and `data.away.confirmed` (false means predicted, up to 48 h before kickoff; true once confirmed, and for the actual lineup of a played match) | Confirmed |
| `lineup_type` | `lineup_type` (for example `lastStarting11`). Omitted once confirmed. | Confirmed |
| `started` = true | each `starters[].player_id` | Confirmed |
| `started` = false | each `subs[].player_id` | Confirmed. Whether `subs` is the whole bench or only used substitutes: Verify. |
| extra columns to add in the migration | `formation`, `shirt_number`, `position_id`, `pitch_x`, `pitch_y` (0 to 1, not metres), `is_captain` | Confirmed |

The engine receives only confirmed lineups (`confirmed = true`) and only for matches not yet played. For finished matches, the starters from this endpoint fill `player_match_stats.started`.


## 6. Recipes: how to get the stats, step by step

Every call below goes through `PitchClient.fetch` (`07_ingest_and_caching.md`, section 2). A call that is fresh in `api_cache` costs nothing.


### 6.1 Discovery (Step 0, run once by hand)

Use Admin → Explorer, or `curl` with your key:

```
curl https://api.pitchapi.dev/v1/leagues -H "X-API-KEY: $PITCH_KEY"
curl "https://api.pitchapi.dev/v1/leagues/{league_id}/matches?season=2025%2F2026" -H "X-API-KEY: $PITCH_KEY"
curl https://api.pitchapi.dev/v1/matches/{match_id}/stats   -H "X-API-KEY: $PITCH_KEY"
curl https://api.pitchapi.dev/v1/matches/{match_id}/players -H "X-API-KEY: $PITCH_KEY"
curl https://api.pitchapi.dev/v1/matches/{match_id}/lineups -H "X-API-KEY: $PITCH_KEY"
```

- Call `/v1/leagues`. Find the Premier League (`country_code` `ENG`). Note its `id` and its `seasons`.
- Call its matches for the latest completed season. Pick any `finished` match.
- Call `/stats`, `/players`, `/lineups` for it. Save the three full responses as `backend/tests/fixtures/` (private; never public).
- Do check A in section 7 against those files. Write the answers into the `provider.*` settings.

The `season` value contains a slash. URL-encode it as `%2F` in code.


### 6.2 Reference sync (weekly)

`GET /v1/leagues` once. Upsert leagues and their season lists. New leagues arrive disabled; Moh switches them on in admin. Cache 7 days.


### 6.3 Season backfill (resumable, newest season first)

- For each enabled league and season, call `GET /v1/leagues/{id}/matches?season=S&status=all`. One call returns the whole season.
- Upsert `teams` and `matches` by `ext_id`. Map status as in section 5.
- For each match whose status is `finished` and `ingested_at` is null, add a `match_ingest` task to `ingest_queue`.
- The queue runs tasks until the daily call budget is spent, then stops. It resumes the next day.
- A finished season's list is cached forever. The current season's list is cached 6 hours.


### 6.4 Ingest one finished match (3 calls)

```python
def ingest_match(client, match):                # ingest.py
    ext = match["ext_id"]
    stats   = client.fetch(f"/v1/matches/{ext}/stats",   ttl=raw_ttl, purpose="stats")
    players = client.fetch(f"/v1/matches/{ext}/players", ttl=raw_ttl, purpose="players")
    lineups = client.fetch(f"/v1/matches/{ext}/lineups", ttl=raw_ttl, purpose="lineups")
    out = normalize_match(...)                  # raises MissingField on a required gap
    # idempotent upserts into team_match_stats, player_match_stats, lineups
    db.matches.update_one({"iid": match["iid"]}, {"$set": {"ingested_at": now}})   # LAST
```

- A `MissingField` error writes an `ingest_issues` row and skips the match. It never writes zero. Nothing is wrapped in a transaction: every write is an upsert and `ingested_at` is written last, so a crash means the match is simply redone.
- A 404 `RESOURCE_NOT_FOUND` on any of the three calls: write an issue, retry once after 24 hours.
- Re-check each finished match once, 24 hours after full time, in case the provider corrected stats. This is one extra set of 3 calls, set by `ingest.recheck_final_hours` (not implemented in the reference code).


### 6.5 Upcoming fixtures (every 6 hours)

Call `GET /v1/leagues/{id}/matches?status=upcoming` once per enabled league. This is cheaper than calling `/v1/date/{date}` for each of the next 7 days (5 calls instead of 40 for five leagues). Upsert matches with status `scheduled`. Verify what the `season` default does at a season rollover, when the old season has ended and the new one has no fixtures yet.

Use `/v1/date/{date}?status=upcoming` only for a quick "today" refresh on match days.


### 6.6 Lineups watch

- Matches kicking off within 48 hours: fetch `/lineups` every 6 hours. These are usually predicted (`confirmed` false).
- Matches within 3 hours: fetch every 20 minutes, at most 6 times.
- When both `home.confirmed` and `away.confirmed` are true, set `matches.lineups_confirmed = true` and stop fetching.
- Write lineup rows with `confirmed` exactly as received.


### 6.7 Nightly results

- Call `/v1/leagues/{id}/matches?status=all` for the current season (1 call per league).
- Any match now `finished` and not ingested gets the 3-call ingest in 6.4.
- Then start the engine job (`07_ingest_and_caching.md`, section 5).


### 6.8 Cache rules per call

| Call | Cache time |
|---|---|
| `/v1/leagues` | 7 days |
| League matches, a finished season | Forever |
| League matches, current season, `status=all` or `upcoming` | 6 hours (2 hours on match days) |
| `/stats`, `/players` of a finished match | Forever, plus one re-check at 24 hours |
| `/lineups` of an upcoming match | 6 hours when more than 3 hours away, 20 minutes when closer |
| `/lineups` of a finished match | Forever |
| `/v1/matches/{id}` of a finished match | Forever |
| Any error response | 10 minutes |

All of these are editable in admin (`11_settings_registry.json`).


## 7. Gaps and checks

The page documents the structure of every response, but not every key name or meaning. These are the open items. Do all of check A before writing the normalizers. Record each answer in `08_pitchapi_verified.md` (copy the template at the end of this file) and in the `provider.*` settings.


### Check A: answer from the three saved fixtures (and a second league)

| # | Question | How to answer it |
|---|---|---|
| A1 | What are the `key` and `title` of team shots, shots on target, corners and tackles in `/stats`? | Print every `group_name`, `title` and `key` of the `All` period. Search titles for "shots", "on target", "corner", "tackle". |
| A2 | What does `BallPossesion` measure? | Check that `home + away` is 100 for several matches. |
| A3 | Which `top_stats` key holds minutes played? | List every `key` in `top_stats` for one player. |
| A4 | Which `defense` key is tackles, and is its type `integer` or a fraction? | List the `defense` group for an outfield player. If it is a fraction, decide that `value` (won) is our tackle count, and use it for team totals too. |
| A5 | Is `shot_accuracy.value` shots on target and `.total` all shots? | Compare with `total_shots` for several players. `value` must never exceed `total`. |
| A6 | What do starter `position_id` values mean? | For one lineup, list every starter's `position_id`, `pitch_y` and name. Build the `provider.position_map` setting from it. |
| A7 | Does `subs` list the whole bench or only used substitutes, in a finished match? | Compare `subs` with players who have minutes and were not starters. |
| A8 | Which `status` values exist besides `finished` and `not_started`? | Collect distinct `status` values over one full season list and over a postponed fixture. |
| A9 | Do team shots in `/stats` equal the sum of player shots? | Compare for 20 matches. Small gaps are fine. Large gaps mean the definitions differ. |
| A10 | What does the `season` default return at a rollover? | Call `/v1/leagues/{id}/matches?status=upcoming` in a gap between seasons, or ask PitchAPI. |
| A11 | Does every league we want have `/stats` with corners and tackles, back to 2021? | Run A1 on one match per league and per season. Write the result into `data_coverage`. Switch off any market whose key is missing. |
| A12 | Are our target leagues among the 26 whose ids changed on 2026-09-19? | Compare the ids of a stored league match with a fresh call. If different, re-run that league's backfill. |


### Check B: ask PitchAPI or read their terms (Moh does this)

| # | Question | Why |
|---|---|---|
| B1 | May we show their data in a public, possibly paid, product? | Not stated on the page. |
| B2 | May we show their images from `cdn.pitchapi.dev`, or must we copy them? | Not stated. |
| B3 | Is credit required? | If yes, set `copy.data_credit` in admin. |
| B4 | What is the real burst limit? | Not published. Never load-test it. Stay at 3 requests per second and honour `Retry-After`. |


### If a key is missing

| Missing | Result |
|---|---|
| Corners in `/stats` | The corners market is switched off automatically. Show it as "Not available yet". |
| Team tackles in `/stats` | Use the sum of player tackles. Player tackles are all we forecast. |
| Tackles in `/players` | The tackles market is off. Shots and shots on target still work. |
| Shots on target (neither `/stats` nor `shot_accuracy`) | The shots-on-target market is off. |
| `/advanced` is the only source of tackles | Call `/v1/matches/{id}/advanced/players` for finished matches only, one call per match. Expect `ANALYTICS_UNAVAILABLE` on some. Add it to the budget estimate in section 3. |


### Done when

- All twelve A items have written answers in `08_pitchapi_verified.md` (copy the template at the end of this file).
- the `provider.*` settings has no guess left. Each field points to a confirmed key.
- One league, one season ingests with zero `ingest_issues` for missing required fields.
- A second run of the same ingest makes zero API calls.
- The `data_coverage` table shows shots, shots on target, corners, tackles, possession, minutes, started and position for that league.
- Moh has the answers to B1 to B3 and has set `copy.data_credit` if credit is required.


### Source

Everything on this page was read from pitchapi.dev on 2026-10-25: the quickstart, authentication, responses, ids, plans, errors, data model, metrics, reference and changelog sections. The reading was done through a summarising tool, so check any exact key or path against the live page before relying on it.


## 8. Where each rule lives in the code

| Rule from this guide | File and function |
|---|---|
| Parse `"329 (82%)"` | `normalize.parse_team_value` |
| Read team stats by `key`, period `All` | `normalize.team_items`, `normalize.team_stats` |
| Read player stats by group and `key` | `normalize.player_stat`, `normalize.players` |
| Goalkeepers: tackles null | `normalize.players` |
| Team totals = sum of players | `normalize.normalize_match` (`_sum_team`) |
| Shots gap over 1 → issue | `normalize.normalize_match` |
| Status `finished` / `not_started` / other | `normalize.status_of` |
| 3 calls per match | `ingest.ingest_match` |
| Upcoming lineups schedule | `ingest.lineup_watch` |
| Round numbers | `ingest.assign_rounds` |
| Coverage per field | `ingest.update_coverage` |
| Errors, 429 retry, breaker, budget | `cached_fetch.PitchClient` |

## 9. Template for `08_pitchapi_verified.md`

The template is in the separate file `08_pitchapi_verified.md`. Fill it from the saved JSON, then put the answers into Admin → Settings → Provider.
