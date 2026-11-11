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
           t_quota_headers, t_their_count_wins, t_minute_cooldown, t_status_is_free,
           t_bundle_chunks_at_20, t_cache_costs_nothing, t_paging,
           t_status_words, t_ns_after_kickoff, t_coverage):
    print(fn.__name__)
    fn()

print()
print(f"{sum(OK)}/{len(OK)} passed")
sys.exit(0 if all(OK) else 1)
