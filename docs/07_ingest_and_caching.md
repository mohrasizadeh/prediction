# 07. Ingest and caching

The goal: **PitchAPI is called as little as possible, and never because a visitor opened a page.** Four layers keep it that way. The code is in `backend/` and passes `selftest.py` and `selftest_jobs.py`.

## 1. The four layers

| Layer | What | Where | Lifetime |
|---|---|---|---|
| 1. Browser and CDN | `Cache-Control` on public routes | HTTP headers | 60 s, then stale-while-revalidate 300 s |
| 2. Our tables | Normalised facts: matches, team and player stats, lineups | `matches`, `team_match_stats`, `player_match_stats`, `lineups` | Forever. This is the long-term store. |
| 3. Raw response cache | The exact PitchAPI JSON, compressed | `api_cache` | Per-call TTL (section 3) |
| 4. Forecast cache | Engine output | `forecasts`, `match_probs` | Until the next engine run |

A page view touches layers 1, 2 and 4 only. Layer 3 exists so a job that fails half-way can resume without paying again.

## 2. `PitchClient.fetch(path, params, ttl, purpose)`: the only door

Defined in `cached_fetch.py`. Every PitchAPI call in the whole app goes through it. Steps, in order:

1. **Key.** `sha256("GET path?sorted params")`.
2. **Cache hit.** If `api_cache` has the key and `expires_at` is absent or in the future, return it. **Cost: 0 calls.** A cached 404 raises `NotFound` without calling.
3. **Guards** (checked before every real attempt):
   - circuit breaker (`job_locks._id = "pitch_breaker"`, not expired) → `BreakerOpen`
   - today's calls (`api_call_log` since 00:00 UTC) ≥ `ingest.daily_call_budget` → `BudgetExhausted`
4. **Pace.** Wait so calls are at most `ingest.rps` per second. Default 3.
5. **Call** with header `X-API-KEY` from `get_provider_key` (admin key wins, `PITCH_KEY` env is the fallback). No key → `Unauthorized`.
6. **Log** one `api_call_log` row per real call (`path`, `status`, `code`, `ms`, `purpose`).
7. **Unwrap** the envelope: `{"data": ...}` is returned; `{"error": {"code"}}` is mapped by `error.code`, never by message text.
8. **Errors.**

   | HTTP / code | Action |
   |---|---|
   | 200 | Store (compressed) and return |
   | 401 `UNAUTHORIZED` | Set `ingest.paused_reason`, trip the breaker, raise `Unauthorized`. Admin shows a red banner. |
   | 429 `RATE_LIMIT_EXCEEDED` | Sleep `Retry-After` (or 2, 4, 8 s), retry up to 3 times, then trip the breaker for `ingest.breaker_minutes` |
   | 404 `RESOURCE_NOT_FOUND` | Cache the miss for `cache.ttl.error_minutes`, raise `NotFound` |
   | 400 `INVALID_PARAMETER` | Raise. It is our bug. No retry. |
   | 5xx | Back off 2, 4, 8 s, then raise |
   | network error | Same as 5xx |

9. **Stale if error.** If the real call fails with the breaker, budget, 5xx or other provider error and an **expired** cache row exists, return the old data and write an `ingest_issues` row (`stale_served`). A stale page is better than a blank one.

Do not use the PitchAPI SDKs. They retry silently and hide calls from the log and the budget.

## 3. TTL table

All values are settings (`cache.ttl.*`), editable in Admin, applied on the next ingest run. `FOREVER` = no `expires_at`.

| Call | TTL | Setting |
|---|---|---|
| `GET /v1/leagues` | 7 days | `cache.ttl.reference_days` |
| League matches, **finished season**, `status=all` | FOREVER | built in |
| League matches, current season, `status=all` or `upcoming` | 6 hours; 2 hours when a league match is within 24 h | `fixtures_future_hours`, `fixtures_matchday_hours` |
| `/stats`, `/players`, `/lineups` of a finished match | 30 days raw; our tables keep the data forever | `cache.raw_retention_days` |
| `/lineups` of an upcoming match, more than 3 h away | 6 hours | `lineups_far_hours` |
| `/lineups` of an upcoming match, within 3 h | 20 minutes, at most 6 refreshes | `lineups_near_minutes`, `lineups_near_max_refresh` |
| Any 404 | 10 minutes | `error_minutes` |

Why raw responses are not kept forever: they are bigger than the facts we extract, and the database is small. The `matches.ingested_at` flag is what stops a second download, not the cache.

## 4. Budget maths

PitchAPI is free with no published numeric limit except an unpublished burst guard. We set our own.

| Job | Calls |
|---|---|
| Reference sync (weekly) | 1 |
| One league-season backfill | 1 list + 3 per finished match ≈ **1,141** for 380 matches |
| Five leagues × five seasons | ≈ **28,500** → about 14 days at 2,000 a day |
| Steady state, one league, one week | ≈ 150 |
| Steady state, five leagues, one day | ≈ 110 |
| Optional extras per match | +1 `/events` (`ingest.match_extra_events`), +1 `/matches/{id}` (`ingest.match_extra_detail`) |

Defaults: `ingest.daily_call_budget` 2000, `ingest.rps` 3, `ingest.concurrency` 1. **Do not load-test PitchAPI.** Start with one league and one season. Check the Usage screen. Widen after.

## 4b. The daily update: only new, old stays in the database

Every day the app asks one question per league: "which matches finished since last time?" Then it fetches **only those**.

1. `results_sync` runs every 6 hours (`ingest.results_sync_hours`). It makes **1 call per enabled league** (the whole season list, always fresh). Five leagues, four runs a day: 20 calls.
2. It compares the list with our `matches` collection. A finished match with `ingested_at` empty is new. Nothing else is.
3. Each new match costs **3 calls** (stats, players, lineups). It is stored in `team_match_stats`, `player_match_stats` and `lineups`, then marked `ingested_at`.
4. A stored match is never fetched again. Its numbers live in our tables forever. The raw JSON is dropped after 30 days; the facts are not.
5. When new results arrive, the engine refits and rewrites the forecasts for the upcoming matches. Old forecasts stay until they are scored.

A normal day: 20 list calls + about 10 to 30 new matches × 3 = **80 to 110 calls**. Far under the 2,000 budget.

Late matches (finish after a run) are caught by the next run, at most 6 hours later. A result that is not ready on PitchAPI yet (404) is retried after 24 hours, three times.

**Proof.** `selftest_jobs.py` adds a round of results after the first ingest, runs a tick 7 hours later, and checks that exactly the 6 new matches were fetched (6 stats + 6 players calls), no stored match was fetched again, and a tick 10 minutes later makes zero calls.

**Not covered:** if PitchAPI later corrects a stored match's stats, we do not see it (the 24-hour re-check is not built). To refresh one match by hand: delete its `ingested_at` and click Run now.

## 5. What each job does

All in `ingest.py`; scheduled by `jobs.py`.

| Job | Trigger | Steps |
|---|---|---|
| `reference_sync` | every `ingest.reference_sync_days` | `GET /v1/leagues` → upsert `leagues` (new ones `enabled = false`), `seasons` |
| `fixtures_sync` | every `ingest.fixtures_sync_hours` | per enabled league: `GET /v1/leagues/{id}/matches?status=upcoming` → upsert `teams`, `matches`; `assign_rounds` |
| `results_sync` | every `ingest.results_sync_hours` (default 6) | per enabled league: 1 fresh list call (current season, `status=all`, never from cache); queue every finished match we have not stored yet |
| `backfill` | Admin chooses `backfill_seasons`, clicks Run | per season `status=all`; queue tasks (priority 7, below live results at 5) |
| `queue` | every tick | `match_ingest`: 3 calls → `normalize_match` → upserts → `ingested_at` last |
| `lineup_watch` | every tick | matches within 48 h: refresh lineups on the schedule in the TTL table. Both sides `confirmed` → stop. |
| `engine` | after new results or new confirmed lineups | `engine_bridge.run_league` |
| `score` | every tick | store outcomes for finished matches (feeds Track Record) |
| `cleanup` | daily | drop old forecasts that already have outcomes |

A `MissingField` skips the match and writes `ingest_issues`. A 404 retries after 24 hours, three times, then gives up. Budget, breaker or 401 puts the task back and stops the run; it continues on the next tick.

A re-check of each finished match 24 hours after full time (setting `ingest.recheck_final_hours`) is **not implemented** in the reference code. Add it only if PitchAPI is seen correcting stats.

## 6. Running the jobs (Emergent has no documented scheduler)

`jobs.tick(db)` is one function that decides what is due and does it. It takes a lock, stops after `max_seconds` (50), and is safe to call as often as you like. Pick one:

**A. External pinger (recommended).** A free service (for example cron-job.org) calls `POST https://<app>/api/jobs/tick` with header `X-CRON-SECRET` every 5 minutes.

**B. In-process thread.** At FastAPI startup, start a daemon thread that calls `tick()` every 300 seconds. It dies when the container sleeps, so use B only as a fallback.

```python
# server.py (sketch)
@app.post("/api/jobs/tick")
def tick_endpoint(x_cron_secret: str = Header(None)):
    if not hmac.compare_digest(x_cron_secret or "", os.environ["CRON_SHARED_SECRET"]):
        raise HTTPException(401)
    return jobs.tick(sync_db)
```

If Emergent's own scheduled jobs turn out to work, point one at that endpoint. Verify first.

## 7. Failure modes and what the admin sees

| Situation | What happens | Admin sees |
|---|---|---|
| Key missing or wrong | Breaker trips, jobs stop, pages keep serving stored data | Red banner: "PitchAPI key rejected" |
| Daily budget spent | Queue stops, resumes next UTC day | Usage bar full |
| 429 storm | Breaker for 15 min | Orange banner |
| A match has no shots in `/players` | That match is skipped | Issue: `missing_field` |
| Provider changes ids (26 leagues did on 2026-09-19) | New ids upsert as new rows | Coverage drops; Moh re-runs the league backfill |
| Stale data | Stale banner for visitors | Status shows last ok time per job |
| Engine has too little data | Run is `skipped` with a note | Engine screen note |

## 8. Runbook: first run

1. Deploy. Run `mongo_init.py`.
2. Admin → API Keys → paste the PitchAPI key → "Test" (calls `/v1/leagues`).
3. Admin → Explorer → run the three discovery calls on one finished Premier League match (`08_pitchapi_data_guide.md`, step 6.1). Save the JSON.
4. Do check A. Put the real keys in Settings → Provider (`provider.pitchapi.team_keys`, `provider.pitchapi.player_keys`, `provider.position_map`).
5. Admin → Leagues → enable the Premier League → choose one `backfill_seasons` → "Run backfill".
6. Watch Usage and Issues until the queue is empty. Zero `missing_field` issues is the target.
7. Check Coverage. Switch on the engine ("Run now"). Look at the Today screen.
8. Run the tick again. It must make **zero** calls for already-ingested matches.
