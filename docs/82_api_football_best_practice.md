# 82. API-Football's own best practice, against what we built

The owner supplied five API-SPORTS tutorials. This is what they change. Checked against the client
in `apifootball.py` as of `0a3d5b9`, not taken on trust: the two faults below were reproduced before
being written down.

**Two of the five are v2-era and their response shapes do not apply.** "How to use API-Football with
Python" (2019) and "How to save calls to the API" (2020) both use `api-football-v1.p.rapidapi.com`,
the `x-rapidapi-key` header, and a `{"api": {"results": N, "fixtures": [...]}}` envelope. v3 is a
different host, a different auth header, and `{"response": [...], "errors": ..., "paging": ...}`.
Their **strategy** is still current and is most of what follows; their **JSON** is not. In
particular v2 returned fixture statistics as an object keyed by name
(`"Shots on Goal": {"home": "1", "away": "1"}`) where v3 returns an array of `{type, value}` per
team. Anyone porting the 2020 examples literally would write a parser for a shape that no longer
exists.

The July 2026 piece, "How to optimize API-SPORTS calls and quota usage", is the authoritative one
and is newer than anything a web search surfaced.

---

## 1. A rate-limit error arrives as HTTP 200, and we mishandled it

**This is a bug, and the worst one here.** Their doc shows the per-minute limit being reported as:

```json
{"get": "", "parameters": [], "results": 0, "paging": {"current": 1, "total": 1},
 "errors": {"rateLimit": "Too many requests. You have reached your per-minute request limit..."},
 "response": []}
```

HTTP **200**, with the problem in `errors.rateLimit`. `_unwrap` sorted `token`, `plan`,
`subscription` and `requests`, and had no case for `rateLimit`, so it fell through to the generic
`APIFootballError`. Reproduced: **one call, no backoff, no breaker, no retry** — and a cached answer
served stale as though the request had simply failed.

Why that is the dangerous one rather than a cosmetic one: the job carries on at the same pace,
because nothing told it to slow down. Their doc is explicit about where that ends — *"Repeated limit
violations or abnormal traffic spikes can lead to a temporary or permanent firewall block. This block
can affect the API key, but also the IP address being used."* A block on the key is recoverable by
asking them; a block on the Emergent egress IP is not something we control.

**Fix:** `rateLimit` in `errors` is treated as a 429 — cool down for a minute, retry with backoff,
and trip the breaker on repetition. Same handling, two transports.

## 2. There is a per-SECOND limit, and it is in no header

Their plan table, which no page I found while researching docs/80 carried:

| Plan | per day | per minute | **per second** |
|---|---|---|---|
| Free | 100 | 10 | — |
| Pro | 7,500 | 300 | **5** |
| **Ultra** | **75,000** | **450** | **7.5** |
| Mega | 150,000 | 900 | 15 |
| Custom | up to 1.5M | 1,200 | 20 |

The headers carry the daily and per-minute figures. **The per-second ceiling is published nowhere in
the response**, so a client that paces only from `X-RateLimit-Limit` is working blind on it.

Ours happens to comply: `minute_safety` 0.8 gives a gap of 0.1667s, which is 6 calls a second
against the 7.5 allowed. But that is arithmetic coincidence, not design — at `minute_safety` 1.0 we
would sit exactly on the limit, with nothing to warn us, and the per-minute and per-second limits
are consistent (450 ÷ 60 = 7.5) only because they chose them that way.

**Fix:** an explicit per-second ceiling the pace is clamped to, derived from the plan rather than
typed: `/status` reports the plan name, so Pro → 5, Ultra → 7.5, Mega → 15. Even pacing already
respects it; what is missing is something that *enforces* it if the safety factor is ever raised.

## 3. One live call returns the events too

Their recommendation, and it changes the live design rather than fixing it, because the new client
has no live path yet:

> To update fixtures and events, a single call to the `fixtures/live` endpoint is enough as it
> returns all current fixtures and their events, this avoids calling the endpoint events for each
> fixtures.

`/fixtures?live=all`, or `/fixtures?live=39-61-48` to limit it to our leagues, returns every in-play
fixture **with its events inline**. The SportAPI design it replaces polls a fixture list and then
calls events per live match (`sportapi.events_refresh_s`, 600s). On a busy Saturday with twenty live
matches that is one call where the old shape wanted twenty-one.

It also means the live tick and the finished-match backfill want different calls: `live=all` while
matches are on, `?ids=` (twenty at a time) once they are over.

## 4. Statistics are not worth refreshing at half time

> The fixtures and players statistics are updated every minute, so it's a good idea to update them
> as regularly as possible **but only if the fixture is in progress**, it's not necessary to update
> them when the fixture status is at half time for example.

Their own trigger set is `1H`, `2H`, `ET`. Ours is `IN_PLAY`, which also holds `HT`, `BT`, `SUSP`
and `INT` — and that set is *right* for the question it was built for, "is this match live" (docs/42,
where treating half time as not-live stopped forecasts ticking). It is the wrong set for "is this
match generating new statistics". Two questions, one constant.

**Fix:** a second set, `PLAYING`, for the stats trigger, leaving `in_play()` alone.

## 5. A lineup never changes once published

> As the lineups are updated only once and do not change during the fixture, once you have retrieved
> the data it is no longer necessary to update them.

Plus, from the endpoint docs: lineups appear 20–40 minutes before kick-off, and for some
competitions only *after* the match.

Our TTLs still carry PitchAPI's shape — `cache.ttl.lineups_near_minutes` 20,
`cache.ttl.lineups_near_max_refresh` 6 — which keeps re-fetching something that cannot change.

**Fix:** once a non-empty lineup is stored for a fixture, cache it forever. Keep polling only while
it is still absent.

## 6. Their update frequencies, as a TTL table

Stated across the two newer docs, and worth copying rather than guessing:

| Data | Changes | What that means for us |
|---|---|---|
| fixtures, events | every 15s | live tick only, and only while something is on |
| fixture + player statistics | every minute | refresh while `PLAYING`, never at half time |
| lineups | once, 20–40 min before kick-off | poll until present, then never |
| standings | hourly, **only for leagues with a fixture that day** | §7 |
| leagues + coverage | **at least weekly** | `cache.ttl.reference_days` is already 7 ✓ |
| teams, coaches, sidelined, transfers | once or twice a month | we re-fetch far more often than needed |

`cache.ttl.fixtures_matchday_hours` is 2 hours, which was right for a provider we polled sparingly
and is far too long for a feed that moves every 15 seconds.

## 7. Standings: today's leagues only, and only where covered

Their pattern, which is exactly the input the stakes layer wants (docs/79 §3.6): read today's
fixtures once, collect the distinct league ids, and call standings for those leagues only — skipping
any whose `coverage.standings` is false. Twelve leagues on a Saturday, two on a Tuesday, instead of
twelve every hour.

## 8. An unstarted season reports everything false

> a competition that hasn't started yet will have all the fields in FALSE, that's why you have to
> call this endpoint at least once a week

And, from the 2026 piece: even with a coverage field enabled, *"the data may not be available
immediately for every match"*.

`af_leagues.supportable_role` already asks whether **any** carried season has statistics, so the
*role* it returns is right. But `plan_row` writes the warning "no player statistics — player markets
cannot run" against a season that simply has not kicked off yet, which on the Competitions screen
reads as "this league is thin" when it means "come back in August". The season's `start` and `end`
dates are in the same response, so the two cases are easy to tell apart.

**Fix:** warn "season has not started" when today is before `start`, and keep the coverage warning
for a season that is under way.

## 9. Confirmations, not changes

- **Twenty ids per `?ids=` call** — confirmed, matches what `fixtures_bundle` chunks at.
- **`/status` is free** — confirmed.
- **Read `paging.total` before asking for another page** — `fetch_all` already does.
- **Team ids are permanent**: *"team data may also change (name, venue, etc.), but their ID will
  always remain the same."* Good for keying `ext_id` on it.
- **Images do not count against the daily quota** but are rate limited per second and minute.

## 10. Two things we should NOT do

**BunnyCDN.** One whole tutorial sets up a pull zone in front of `media.api-sports.io`. We do not
need it: `images.py` already downloads each file **once** into our own `media` collection and serves
it from our own address, which is what their other doc recommends anyway (*"it is recommended to save
this data on your side in order not to slow down or impact the user experience"*). A CDN proxy would
be a monthly bill to solve a problem we solved by storing the bytes. If image delivery ever needs a
CDN it should sit in front of **our** address, not theirs.

**The `/teams?country=` sweep.** 231 calls gets every team in the API, against 5,000 by
league-and-season. Clever, and irrelevant at twelve leagues — we want the teams of our competitions,
not all of them. Worth remembering only if the league list grows into the hundreds.

And the licence note is worth repeating because it is now stated by the provider in their own words:
they do not own the logos and images, some are subject to third-party trademark rights, and *"you are
fully responsible for ensuring that your usage ... complies with applicable laws"*. docs/19 §8 has
been open on exactly this since the image sync was built, and we are already storing and serving
them.

---

## What to do, in order

| | Change | Why |
|---|---|---|
| 1 | Handle `errors.rateLimit` as a rate limit | **Bug.** Proven: no backoff, no retry, and carrying on at the same pace is what gets a key or an IP blocked. |
| 2 | Clamp the pace to a per-second ceiling from the plan | A real limit that no header reports. We comply by coincidence today. |
| 3 | `live=all` for the live tick, `?ids=` for finished matches | One call instead of twenty-one on a busy Saturday. Their own recommendation. |
| 4 | A `PLAYING` set for the stats trigger | Half time generates no statistics; `in_play` must keep meaning what docs/42 made it mean. |
| 5 | Cache a lineup forever once seen | It cannot change. We re-fetch it. |
| 6 | Retune the TTLs to their published frequencies | Ours were set for a provider we polled sparingly. |
| 7 | Standings for today's leagues only | Feeds the stakes layer at a fraction of the calls. |
| 8 | Tell "season not started" from "not covered" | Stops a new season looking like a thin league on the mapping screen. |

1 and 2 are defects. 3 to 8 are the live and backfill design, and all of it lands before the first
real call, so none of it is rework.

---

## Built

All eight, in `apifootball.py` and `af_leagues.py`, pinned by **77 checks** in
`selftest_apifootball.py` (up from 45) and **37** in `selftest_af_leagues.py`.

| | What landed |
|---|---|
| 1 | `RateLimited`, raised from `_unwrap` on `errors.rateLimit` and handled in the retry loop exactly as a 429: cool down, retry, trip the breaker on repetition. `min_remaining` is forced to 0 so the pace drops even if the answer omitted the header. It is deliberately *not* confused with a spent quota or a bad key — neither pauses ingest. |
| 2 | `per_second_limit()` derives the ceiling as the per-minute limit over sixty, which matches their table for every plan (300/5, 450/7.5, 900/15, 1200/20), so it needs no plan-name lookup. `min_gap()` clamps the pace between **consecutive** calls, not over a window — an average can be legal while two calls 10ms apart are not. The clamp is tested at `minute_safety` 1.0, which is where the old code would have sat exactly on the limit. |
| 3 | `live_fixtures()` calls `/fixtures?live=…` and is never cached. `needs_stats()` reads the inline events and returns only the fixtures worth a statistics call. |
| 4 | `PLAYING` beside `IN_PLAY`, and `worth_refreshing_stats()`. The test asserts both halves: `HT`, `BT`, `SUSP` and `INT` stay live for the forecast (docs/42) *and* are skipped for statistics. |
| 5 | `lineup_ttl()` returns `FOREVER` once a non-empty lineup is present, and the short poll only while it is absent. |
| 6 | `cache.ttl.standings_hours` (1), `cache.ttl.live_stats_s` (60), `cache.ttl.squads_days` (21); `cache.ttl.fixtures_matchday_hours` 2 → 1, with its help text now saying the live tick does not read it. |
| 7 | `leagues_playing_on()` and `standings()`, which skips a league whose `coverage.standings` is false rather than asking and being answered empty. |
| 8 | `_has_started()` reads the season's `start` date out of the same coverage answer, so "has not started" and "not covered" are told apart. A season under way with no statistics is still called out and still demoted. |

One thing the work surfaced that was not in their docs: `check()` in the test harness accepted a
truthy non-boolean, and `a and b` over two lists returns a list, which broke the pass tally rather
than failing a check. It coerces now.
