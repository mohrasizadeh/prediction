"""selftest_apifootball.py -- the API-Football client, against a fake transport. docs/81.

What this pins, in the order the provider is likely to surprise us:
  1. an error arrives as HTTP 200 with a populated `errors`, and `errors` is a list when empty and
     an object when not;
  2. a rejected key pauses ingest and trips the breaker, a plan limit does not;
  3. the quota headers are stored and THEIR number stops us, before ours does;
  4. `/status` is free: it is not blocked by a spent budget;
  5. only `x-apisports-key` is sent;
  6. `?ids=` is chunked at 20 and the bundle carries everything;
  7. the status vocabulary, including the NS-after-kick-off trap.

    python3 tests/selftest_apifootball.py
"""
import os, sys, base64
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
os.environ.setdefault("APP_ENCRYPTION_KEY", base64.b64encode(os.urandom(32)).decode())

from datetime import datetime, timedelta, timezone

import httpx
import mongomock

import apifootball as AF
import security
import settings_store as S

OK = []
def check(name, cond):
    cond = bool(cond)          # a `a and b` over two lists returns a list, which breaks sum(OK)
    OK.append(cond)
    print(("  ok     " if cond else "  FAIL   ") + name)


def seed():
    db = mongomock.MongoClient()["af"]
    S.seed(db) if hasattr(S, "seed") else None
    security.save_provider_key(db, AF.PROVIDER, "k" * 24)
    return db


def transport(handler):
    return httpx.Client(base_url=AF.BASE_URL, transport=httpx.MockTransport(handler))


def envelope(response, errors=None, paging=None):
    return {"get": "x", "parameters": {}, "errors": errors if errors is not None else [],
            "results": len(response), "paging": paging or {"current": 1, "total": 1},
            "response": response}


HDR = {"x-ratelimit-requests-limit": "7500", "x-ratelimit-requests-remaining": "7499",
       "X-RateLimit-Limit": "300", "X-RateLimit-Remaining": "299"}


# ---------------------------------------------------------------- 1. the envelope
def t_envelope():
    db = seed()
    seen = {}
    def h(req):
        seen["headers"] = dict(req.headers)
        return httpx.Response(200, json=envelope([{"a": 1}]), headers=HDR)
    c = AF.Client(db, transport(h), sleep=lambda s: None)
    rows = c.fetch("/leagues", {"id": 39}, purpose="t")
    check("a good answer unwraps to `response`", rows == [{"a": 1}])
    check("only x-apisports-key is sent (no accept, no custom extras)",
          "x-apisports-key" in seen["headers"] and
          not any(k.lower().startswith(("x-rapid", "authorization")) for k in seen["headers"]))


def t_errors_are_200():
    db = seed()
    def h(req):
        return httpx.Response(200, json=envelope([], errors={"plan": "Your plan does not allow this"}), headers=HDR)
    c = AF.Client(db, transport(h), sleep=lambda s: None)
    try:
        c.fetch("/fixtures", {"league": 39, "season": 2015}, purpose="t")
        check("a plan limit raises even though HTTP said 200", False)
    except AF.PlanLimited:
        check("a plan limit raises even though HTTP said 200", True)
    except Exception as e:
        check(f"a plan limit raises even though HTTP said 200 (got {type(e).__name__})", False)
    check("a plan limit does NOT pause ingest", not (db.settings.find_one({"key": "ingest.paused_reason"}) or {}).get("value"))
    check("a plan limit does NOT trip the breaker", db.job_locks.find_one({"_id": "af_breaker"}) is None)


def t_bad_key():
    db = seed()
    def h(req):
        return httpx.Response(200, json=envelope([], errors={"token": "invalid api key"}), headers=HDR)
    c = AF.Client(db, transport(h), sleep=lambda s: None)
    try:
        c.fetch("/leagues", purpose="t")
    except AF.Unauthorized:
        pass
    paused = (db.settings.find_one({"key": "ingest.paused_reason"}) or {}).get("value") or ""
    check("a rejected key pauses ingest with a reason", "key" in paused.lower())
    check("a rejected key trips the breaker", db.job_locks.find_one({"_id": "af_breaker"}) is not None)


def t_empty_errors_list():
    db = seed()
    def h(req):
        return httpx.Response(200, json={"response": [{"ok": 1}], "errors": [], "paging": {"current": 1, "total": 1}},
                              headers=HDR)
    c = AF.Client(db, transport(h), sleep=lambda s: None)
    check("`errors: []` is not an error", c.fetch("/teams", {"id": 33}, purpose="t") == [{"ok": 1}])


# ---------------------------------------------------------------- 2. quota
def t_quota_headers():
    db = seed()
    def h(req):
        return httpx.Response(200, json=envelope([{"a": 1}]),
                              headers={**HDR, "x-ratelimit-requests-remaining": "41", "X-RateLimit-Remaining": "7"})
    c = AF.Client(db, transport(h), sleep=lambda s: None)
    c.fetch("/leagues", {"id": 1}, purpose="t")
    q = c.quota()
    check("the daily and per-minute quota headers are stored",
          q.get("day_remaining") == 41 and q.get("min_remaining") == 7 and q.get("day_limit") == 7500)


# ---------------------------------------------------------------- docs/82: their own best practice
def t_ratelimit_arrives_as_200():
    """THE BUG docs/82 section 1 found. Their per-minute limit is reported as HTTP 200 with
    errors.rateLimit; before this case existed it fell through to a generic error with no backoff,
    no retry and no breaker, and the job carried on at the same pace -- which is how their
    documentation says a key, and the IP behind it, gets firewalled."""
    db = seed()
    slept, calls = [], {"n": 0}
    limited = {"get": "", "parameters": [], "results": 0, "paging": {"current": 1, "total": 1},
               "errors": {"rateLimit": "Too many requests. You have reached your per-minute request limit."},
               "response": []}
    def h(req):
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(200, json=limited, headers={**ULTRA, "X-RateLimit-Remaining": "0"})
        return httpx.Response(200, json=envelope([{"a": 1}]), headers=ULTRA)
    c = AF.Client(db, transport(h), sleep=lambda s: slept.append(s))
    rows = c.fetch("/fixtures", {"live": "all"}, purpose="t")
    check("a 200 carrying errors.rateLimit is retried, not raised as a generic failure", rows == [{"a": 1}])
    check("...after a cooldown, not immediately", any(s >= 10 for s in slept))
    check("...and it is not mistaken for a spent quota or a bad key",
          db.job_locks.find_one({"_id": "af_breaker"}) is None
          and not (db.settings.find_one({"key": "ingest.paused_reason"}) or {}).get("value"))


def t_ratelimit_repeated_trips_the_breaker():
    db = seed()
    limited = {"errors": {"rateLimit": "Too many requests."}, "response": [], "paging": {}}
    def h(req):
        return httpx.Response(200, json=limited, headers={**ULTRA, "X-RateLimit-Remaining": "0"})
    c = AF.Client(db, transport(h), sleep=lambda s: None)
    try:
        c.fetch("/fixtures", {"live": "all"}, purpose="t")
        check("a rate limit that will not clear trips the breaker rather than hammering on", False)
    except AF.BreakerOpen:
        check("a rate limit that will not clear trips the breaker rather than hammering on", True)
    check("...and stops after a bounded number of tries", c.calls_made <= 4)


def t_per_second_ceiling():
    """docs/82 section 2: the per-second limit is in NO header. Across their whole plan table it is
    the per-minute figure over sixty, so it is derived rather than typed."""
    db = seed()
    def h(req):
        return httpx.Response(200, json=envelope([{"a": 1}]), headers=ULTRA)
    c = AF.Client(db, transport(h), sleep=lambda s: None)
    c.fetch("/leagues", {"id": 1}, purpose="t")
    check(f"Ultra's 450/min yields the documented 7.5 calls a second ({c.per_second_limit()})",
          abs(c.per_second_limit() - 7.5) < 1e-9)
    check("the pace is clamped so no two consecutive calls can break it",
          c._gap() >= c.min_gap() - 1e-9)
    # the clamp has to bite even if someone turns the safety factor off
    db.settings.insert_one({"key": "apifootball.minute_safety", "value": 1.0})
    check("...even at a safety factor of 1.0, which would otherwise sit exactly on the limit",
          1.0 / c._gap() <= 7.5 + 1e-9)


def t_per_second_for_other_plans():
    for per_min, per_sec in ((300, 5.0), (450, 7.5), (900, 15.0), (1200, 20.0)):
        db = seed()
        def h(req, pm=per_min):
            return httpx.Response(200, json=envelope([{"a": 1}]),
                                  headers={**ULTRA, "X-RateLimit-Limit": str(pm)})
        c = AF.Client(db, transport(h), sleep=lambda s: None)
        c.fetch("/leagues", {"id": 1}, purpose="t")
        check(f"{per_min}/min derives {per_sec}/s, matching their plan table",
              abs(c.per_second_limit() - per_sec) < 1e-9)


def t_stats_not_at_half_time():
    """docs/82 section 4. in_play must keep meaning what docs/42 made it mean -- a forecast ticks
    through a break -- while the stats trigger asks a different question."""
    for st in ("1H", "2H", "ET"):
        check(f"{st}: statistics are worth asking for", AF.worth_refreshing_stats(st))
    for st in ("HT", "BT", "SUSP", "INT"):
        check(f"{st}: live for the forecast, but no new statistics to fetch",
              AF.in_play(st) and not AF.worth_refreshing_stats(st))
    for st in ("FT", "NS", "PST"):
        check(f"{st}: neither", not AF.worth_refreshing_stats(st))


def t_live_returns_events_inline():
    """docs/82 section 3: one call, not one per match."""
    db = seed()
    asked = []
    def h(req):
        asked.append(dict(req.url.params))
        return httpx.Response(200, json=envelope([
            {"fixture": {"id": 1, "status": {"short": "1H"}}, "events": [{"type": "Goal"}]},
            {"fixture": {"id": 2, "status": {"short": "HT"}}, "events": []},
            {"fixture": {"id": 3, "status": {"short": "2H"}}, "events": [{"type": "Card"}]},
        ]), headers=ULTRA)
    c = AF.Client(db, transport(h), sleep=lambda s: None)
    rows = AF.live_fixtures(c, [39, 61])
    check("one call gets every live fixture", len(rows) == 3 and c.calls_made == 1)
    check("...with its events inline, so no per-match events call is needed",
          bool(rows[0]["events"]) and bool(rows[2]["events"]))
    check("...narrowed to our leagues", asked[0].get("live") == "39-61")
    check("only the fixtures actually playing are queued for statistics: half time is skipped",
          AF.needs_stats(rows) == [1, 3])
    AF.live_fixtures(c, [39, 61])
    check("live is never served from cache -- freshness is the whole point", c.calls_made == 2)


def t_lineup_cached_once_present():
    db = seed()
    def h(req):
        return httpx.Response(200, json=envelope([{"a": 1}]), headers=ULTRA)
    c = AF.Client(db, transport(h), sleep=lambda s: None)
    check("a fixture with no lineup yet is polled again",
          AF.lineup_ttl(c, {"lineups": []}) is not AF.FOREVER)
    check("a lineup we already have is cached for ever: it cannot change (docs/82 section 5)",
          AF.lineup_ttl(c, {"lineups": [{"team": {"id": 1}}]}) is AF.FOREVER)


def t_standings_only_where_covered():
    db = seed()
    paths = []
    def h(req):
        paths.append(req.url.path)
        if req.url.path == "/fixtures":
            return httpx.Response(200, json=envelope([
                {"league": {"id": 39}}, {"league": {"id": 61}}, {"league": {"id": 39}}]), headers=ULTRA)
        if req.url.path == "/leagues":
            lid = int(req.url.params.get("id"))
            return httpx.Response(200, json=envelope([{"league": {"id": lid}, "seasons": [
                {"year": 2024, "start": "2024-08-01",
                 "coverage": {"fixtures": {}, "standings": lid == 39}}]}]), headers=ULTRA)
        return httpx.Response(200, json=envelope([{"table": "x"}]), headers=ULTRA)
    c = AF.Client(db, transport(h), sleep=lambda s: None)
    ids = AF.leagues_playing_on(c, "2026-03-07")
    check("one call gives the distinct leagues playing today, no duplicates", ids == [39, 61])
    check("a covered league's table is fetched", AF.standings(c, 39, 2024) == [{"table": "x"}])
    check("an uncovered league is skipped rather than asked and answered empty",
          AF.standings(c, 61, 2024) == [] and paths.count("/standings") == 1)


# ---------------------------------------------------------------- the Ultra plan's limits
ULTRA = {"x-ratelimit-requests-limit": "75000", "x-ratelimit-requests-remaining": "74999",
         "X-RateLimit-Limit": "450", "X-RateLimit-Remaining": "449"}


def t_budget_follows_the_plan():
    db = seed()
    def h(req):
        return httpx.Response(200, json=envelope([{"a": 1}]), headers=ULTRA)
    c = AF.Client(db, transport(h), sleep=lambda s: None)
    before = c.day_budget()
    check("before any answer, the budget is the fallback cap minus the reserve",
          before == 75000 - 500)
    c.fetch("/leagues", {"id": 1}, purpose="t")
    check("after one answer the budget comes from the PLAN's own header, not a setting we typed",
          c.day_budget() == 75000 - 500)
    # and the point of not sharing PitchAPI's budget
    check("the budget is not ingest.daily_call_budget, which is PitchAPI's 2,000",
          c.day_budget() > 70000 and int(S.get(db, "ingest.daily_call_budget")) == 2000)


def t_reserve_is_kept():
    db = seed()
    def h(req):
        return httpx.Response(200, json=envelope([{"a": 1}]),
                              headers={**ULTRA, "x-ratelimit-requests-remaining": "500"})
    c = AF.Client(db, transport(h), sleep=lambda s: None)
    c.fetch("/leagues", {"id": 1}, purpose="t")
    try:
        c.fetch("/leagues", {"id": 2}, purpose="t")
        check("we stop at the reserve, not at zero, so a live tick still has calls", False)
    except AF.BudgetExhausted as e:
        check("we stop at the reserve, not at zero, so a live tick still has calls", "reserve" in str(e))


def t_pacing_respects_the_minute():
    db = seed()
    def h(req):
        return httpx.Response(200, json=envelope([{"a": 1}]), headers=ULTRA)
    c = AF.Client(db, transport(h), sleep=lambda s: None)
    check("with nothing learned yet, the pace is the conservative starting rate", abs(c._gap() - 0.5) < 1e-6)
    c.fetch("/leagues", {"id": 1}, purpose="t")
    # 450 a minute at 80% is 360, which is 6 a second: a gap of 1/6 s.
    check(f"once the plan's 450/min is known, the gap paces to 80% of it ({c._gap():.4f}s)",
          abs(c._gap() - 60.0 / (450 * 0.8)) < 1e-6)
    rate = 1.0 / c._gap()
    check(f"...which is {rate:.0f} calls a second, under the {450 / 60:.1f} the plan allows",
          rate < 450 / 60)


def t_pitchapi_rps_does_not_govern_here():
    """ingest.rps is PitchAPI's 3/s. Letting it govern would cap Ultra at 180 calls a minute out
    of 450 -- a backfill two and a half times slower than it needs to be, for another provider's
    limit. Neither raising it nor lowering it may move this client's pace."""
    for rps in (50, 1):
        db = seed()
        db.settings.insert_one({"key": "ingest.rps", "value": rps})
        def h(req):
            return httpx.Response(200, json=envelope([{"a": 1}]), headers=ULTRA)
        c = AF.Client(db, transport(h), sleep=lambda s: None)
        c.fetch("/leagues", {"id": 1}, purpose="t")
        check(f"ingest.rps={rps} does not move the pace: the plan's ceiling decides",
              abs(c._gap() - 60.0 / (450 * 0.8)) < 1e-6)


def t_slows_as_the_bucket_empties():
    db = seed()
    state = {"left": 449}
    def h(req):
        return httpx.Response(200, json=envelope([{"a": 1}]),
                              headers={**ULTRA, "X-RateLimit-Remaining": str(state["left"])})
    c = AF.Client(db, transport(h), sleep=lambda s: None)
    c.fetch("/leagues", {"id": 1}, purpose="t")
    full = c._gap()
    state["left"] = 45                                               # 10% left, under the headroom
    c.fetch("/leagues", {"id": 2}, purpose="t")
    low = c._gap()
    check(f"the last of the minute is spent slowest ({full:.3f}s -> {low:.3f}s)", low > full * 1.5)
    state["left"] = 9                                                # 2% left
    c.fetch("/leagues", {"id": 3}, purpose="t")
    check("and slower still as it runs out", c._gap() > low)


def t_retry_after_is_obeyed():
    db = seed()
    slept, calls = [], {"n": 0}
    def h(req):
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(429, json={}, headers={**ULTRA, "Retry-After": "12"})
        return httpx.Response(200, json=envelope([{"a": 1}]), headers=ULTRA)
    c = AF.Client(db, transport(h), sleep=lambda s: slept.append(s))
    c.fetch("/leagues", {"id": 1}, purpose="t")
    check("a 429 waits as long as Retry-After says, not a guess of our own", 12 in slept)
    check("...and the call is then retried and succeeds", calls["n"] == 2)
    check("a Retry-After is capped, so one answer cannot hold a job lock for an hour",
          AF._retry_after("99999", default=2) == 60.0)


def t_their_count_wins():
    db = seed()
    def h(req):
        return httpx.Response(200, json=envelope([{"a": 1}]), headers={**HDR, "x-ratelimit-requests-remaining": "0"})
    c = AF.Client(db, transport(h), sleep=lambda s: None)
    c.fetch("/leagues", {"id": 1}, purpose="t")          # one call, which reports zero left
    try:
        c.fetch("/leagues", {"id": 2}, purpose="t")
        check("when the provider says zero left, the next call is not sent", False)
    except AF.BudgetExhausted:
        check("when the provider says zero left, the next call is not sent", True)
    check("...and that is their number, not ours (we had made 1 call of 2000)", c.calls_made == 1)


def t_minute_cooldown():
    db = seed()
    slept = []
    def h(req):
        return httpx.Response(200, json=envelope([{"a": 1}]), headers={**HDR, "X-RateLimit-Remaining": "0"})
    c = AF.Client(db, transport(h), sleep=lambda s: slept.append(s))
    c.fetch("/leagues", {"id": 1}, purpose="t")
    c.fetch("/leagues", {"id": 2}, purpose="t")
    check("an empty per-minute bucket makes the next call wait (their firewall, not their throttle)",
          any(s >= 10 for s in slept))


def t_status_is_free():
    db = seed()
    db.job_state.update_one({"_id": "apifootball_quota"},
                            {"$set": {"day": AF.utcnow().strftime("%Y-%m-%d"), "day_remaining": 0}}, upsert=True)
    # The headers say the day is spent, which is the whole point: /status is the one call that
    # still answers, and it REFRESHES the quota from the provider rather than trusting our row.
    spent = {**HDR, "x-ratelimit-requests-remaining": "0"}
    def h(req):
        return httpx.Response(200, json=envelope([{"account": {}, "requests": {"current": 100, "limit_day": 100}}]),
                              headers=spent)
    c = AF.Client(db, transport(h), sleep=lambda s: None)
    try:
        st = c.status()
        check("/status still answers when the budget is spent (it is free)", st.get("requests", {}).get("limit_day") == 100)
    except Exception as e:
        check(f"/status still answers when the budget is spent (got {type(e).__name__})", False)
    try:
        c.fetch("/leagues", {"id": 1}, purpose="t")
        check("...but an ordinary call is still blocked", False)
    except AF.BudgetExhausted:
        check("...but an ordinary call is still blocked", True)


# ---------------------------------------------------------------- 3. the bundle
def t_bundle_chunks_at_20():
    db = seed()
    asked = []
    def h(req):
        ids = req.url.params.get("ids", "").split("-")
        asked.append(len(ids))
        return httpx.Response(200, json=envelope([{"fixture": {"id": int(i)}, "statistics": [], "players": [],
                                                   "lineups": [], "events": []} for i in ids]), headers=HDR)
    c = AF.Client(db, transport(h), sleep=lambda s: None)
    out = AF.fixtures_bundle(c, list(range(1, 46)))
    check("45 fixtures are asked for in 3 calls of at most 20", asked == [20, 20, 5])
    check("the bundle is keyed by fixture id and holds all 45", len(out) == 45 and 45 in out)
    check("one call carries statistics, players, lineups and events together",
          all(k in out[1] for k in ("statistics", "players", "lineups", "events")))


def t_cache_costs_nothing():
    db = seed()
    def h(req):
        return httpx.Response(200, json=envelope([{"a": 1}]), headers=HDR)
    c = AF.Client(db, transport(h), sleep=lambda s: None)
    c.fetch("/fixtures", {"id": 1}, ttl=AF.FOREVER, purpose="t")
    c.fetch("/fixtures", {"id": 1}, ttl=AF.FOREVER, purpose="t")
    check("a cached answer costs no call", c.calls_made == 1)


def t_paging():
    db = seed()
    def h(req):
        page = int(req.url.params.get("page", 1))
        return httpx.Response(200, json=envelope([{"p": page}], paging={"current": page, "total": 3}), headers=HDR)
    c = AF.Client(db, transport(h), sleep=lambda s: None)
    rows = c.fetch_all("/players", {"league": 39, "season": 2024}, purpose="t")
    check("fetch_all follows paging.total to the last page", [r["p"] for r in rows] == [1, 2, 3])


# ---------------------------------------------------------------- 4. the vocabulary
def t_status_words():
    check("FT, AET and PEN are final", all(AF.is_final(s) for s in ("FT", "AET", "PEN")))
    check("NS and TBD are not in play", not AF.in_play("NS") and not AF.in_play("TBD"))
    check("1H, HT, 2H, ET, BT and P are in play", all(AF.in_play(s) for s in ("1H", "HT", "2H", "ET", "BT", "P")))
    check("SUSP and INT count as in play, so a forecast keeps ticking", AF.in_play("SUSP") and AF.in_play("INT"))
    check("a word we have never seen counts as in play (docs/42)", AF.in_play("WEIRD"))
    check("PST, CANC, ABD, AWD and WO are over for good",
          all(AF.is_over(s) for s in ("PST", "CANC", "ABD", "AWD", "WO")) and not AF.is_final("PST"))


def t_ns_after_kickoff():
    now = datetime(2026, 3, 1, 20, 0, tzinfo=timezone.utc)
    check("NS an hour before kick-off is just scheduled",
          not AF.stale_not_started("NS", now + timedelta(hours=1), now))
    check("NS five hours AFTER kick-off is a match to re-check, not an upcoming one",
          AF.stale_not_started("NS", now - timedelta(hours=5), now))
    check("a finished match is never 'stale NS'", not AF.stale_not_started("FT", now - timedelta(hours=5), now))


# ---------------------------------------------------------------- 5. coverage
def t_coverage():
    db = seed()
    def h(req):
        return httpx.Response(200, json=envelope([{"league": {"id": 39}, "seasons": [
            {"year": 2024, "current": True, "start": "2024-08-16", "end": "2025-05-25",
             "coverage": {"fixtures": {"events": True, "lineups": True, "statistics_fixtures": True,
                                       "statistics_players": True},
                          "standings": True, "players": True, "injuries": True, "top_scorers": True, "odds": False}},
            {"year": 2015, "current": False, "coverage": {"fixtures": {"events": True, "lineups": False,
                                                                       "statistics_fixtures": False,
                                                                       "statistics_players": False},
                                                          "standings": True, "players": True, "injuries": False}},
        ]}]), headers=HDR)
    c = AF.Client(db, transport(h), sleep=lambda s: None)
    good = AF.coverage(c, 39, 2024)
    thin = AF.coverage(c, 39, 2015)
    missing = AF.coverage(c, 39, 1999)
    check("coverage reads the season we asked for, not the first one",
          good["players_statistics"] is True and good["season"] == 2024)
    check("a season without player statistics is reported as such, per season not per league",
          thin["fixtures_statistics"] is False and thin["players_statistics"] is False)
    check("a season the plan cannot see is 'not found', with the seasons that exist",
          missing["found"] is False and 2024 in (missing.get("seasons") or []))


for fn in (t_envelope, t_errors_are_200, t_bad_key, t_empty_errors_list,
           t_ratelimit_arrives_as_200, t_ratelimit_repeated_trips_the_breaker,
           t_per_second_ceiling, t_per_second_for_other_plans, t_stats_not_at_half_time,
           t_live_returns_events_inline, t_lineup_cached_once_present, t_standings_only_where_covered,
           t_budget_follows_the_plan, t_reserve_is_kept, t_pacing_respects_the_minute,
           t_pitchapi_rps_does_not_govern_here, t_slows_as_the_bucket_empties, t_retry_after_is_obeyed,
           t_quota_headers, t_their_count_wins, t_minute_cooldown, t_status_is_free,
           t_bundle_chunks_at_20, t_cache_costs_nothing, t_paging,
           t_status_words, t_ns_after_kickoff, t_coverage):
    print(fn.__name__)
    fn()

print()
print(f"{sum(OK)}/{len(OK)} passed")
sys.exit(0 if all(OK) else 1)
