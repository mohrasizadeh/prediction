"""The API-Football ingest, end to end: their JSON in, our tables out. docs/88.

The point of this file is that the thing it tests did not exist until now. `apifootball.py` could
talk to them and `normalize_af.py` could reshape their JSON, and nothing joined the two, so every
row in the database still came from PitchAPI. These checks are what "API-Football is the only
provider" means in practice: a fixture list becomes `matches` and `teams`, a bundle becomes
`team_match_stats`, `player_match_stats` and `lineups`, and the call count is the one we costed.
"""
import sys, os, base64
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
# Every test that saves a provider key seeds its own, because `security._master` reads this from the
# environment and raises KeyError without it. This file did not, so it passed by hand and failed in
# the sweep -- the one red in 58. setdefault, so a real key in the environment still wins.
os.environ.setdefault("APP_ENCRYPTION_KEY", base64.b64encode(os.urandom(32)).decode())

from datetime import timedelta

import httpx
import mongomock

import af_leagues as AFL
import apifootball as AF
import ingest_af as IA
import security
import settings_store as S

OK = []


def check(name, cond):
    cond = bool(cond)
    OK.append(cond)
    print(("  ok     " if cond else "  FAIL   ") + name)


HDR = {"x-ratelimit-requests-limit": "75000", "x-ratelimit-requests-remaining": "74999",
       "X-RateLimit-Limit": "450", "X-RateLimit-Remaining": "449"}


def env(body_for):
    def h(req):
        body = body_for(req)
        return httpx.Response(200, headers=HDR, json={
            "get": req.url.path.lstrip("/"), "parameters": dict(req.url.params), "errors": [],
            "results": len(body), "paging": {"current": 1, "total": 1}, "response": body})
    return h


def seed():
    db = mongomock.MongoClient()["af"]
    security.save_provider_key(db, AF.PROVIDER, "k" * 24)
    return db


def client(db, handler):
    return AF.Client(db, httpx.Client(base_url=AF.BASE_URL, transport=httpx.MockTransport(handler)),
                     sleep=lambda s: None)


# ------------------------------------------------------------------ fixtures
def fixture(fid, home, away, hg=None, ag=None, short="FT", season=2024, league=39,
            date="2024-08-17T14:00:00+00:00"):
    return {"fixture": {"id": fid, "date": date, "referee": "M. Oliver",
                        "venue": {"name": "Emirates"}, "status": {"short": short}},
            "league": {"id": league, "season": season, "round": "Regular Season - 1"},
            "teams": {"home": {"id": home[0], "name": home[1]}, "away": {"id": away[0], "name": away[1]}},
            "goals": {"home": hg, "away": ag}}


def detailed(fid, home, away, hg, ag):
    """A fixture as `/fixtures?ids=` returns it: statistics and players attached."""
    f = fixture(fid, home, away, hg, ag)
    def tstats(tid, shots, sot, corners, fouls):
        return {"team": {"id": tid}, "statistics": [
            {"type": "Total Shots", "value": shots}, {"type": "Shots on Goal", "value": sot},
            {"type": "Corner Kicks", "value": corners}, {"type": "Fouls", "value": fouls},
            {"type": "Ball Possession", "value": "55%"}]}
    def one(pid, nm, mins, pos, started, sh, on, tk):
        return {"player": {"id": pid, "name": nm},
                "statistics": [{"games": {"minutes": mins, "position": pos, "number": 7,
                                          "rating": "7.0", "captain": False,
                                          "substitute": not started},
                                "shots": {"total": sh, "on": on},
                                "tackles": {"total": tk, "blocks": 0, "interceptions": 1},
                                "fouls": {"committed": 1, "drawn": 2},
                                "cards": {"yellow": 0, "red": 0},
                                "goals": {"total": 0, "assists": 0, "saves": None}}]}

    def pblock(tid, players):
        return {"team": {"id": tid}, "players": [one(*p) for p in players]}
    f["statistics"] = [tstats(home[0], 14, 6, 7, 11), tstats(away[0], 9, 3, 4, 13)]
    f["players"] = [pblock(home[0], [(101, "A. One", 90, "M", True, 3, 2, 4),
                                     (102, "B. Two", 67, "D", True, 1, 0, 2)]),
                    pblock(away[0], [(201, "C. Three", 90, "F", True, 5, 3, 1)])]
    f["lineups"] = [
        {"team": {"id": home[0]}, "formation": "4-3-3",
         "startXI": [{"player": {"id": 101, "name": "A. One", "number": 7, "pos": "M", "grid": "2:1"}},
                     {"player": {"id": 102, "name": "B. Two", "number": 3, "pos": "D", "grid": "1:2"}}],
         "substitutes": []},
        {"team": {"id": away[0]}, "formation": "4-4-2",
         "startXI": [{"player": {"id": 201, "name": "C. Three", "number": 9, "pos": "F", "grid": "3:1"}}],
         "substitutes": []}]
    return f


def league_row(db, ext_id=39, role="forecast", seasons=(2024,)):
    iid = __import__("ingest").upsert_entity(
        db, "leagues", str(ext_id),
        {"name": "Premier League", "provider": "apifootball", "role": role, "kind": "league"},
        on_insert={"enabled": True, "backfill_seasons": list(seasons)})
    db.leagues.update_one({"iid": iid}, {"$set": {"enabled": True, "backfill_seasons": list(seasons),
                                                  "role": role}})
    db.af_catalog.insert_one({"_id": ext_id, "name": "Premier League", "years": [2023, 2024]})
    return db.leagues.find_one({"iid": iid})


# ------------------------------------------------------------------ 1. the schedule
def t_schedule():
    db = seed()
    lg = league_row(db)
    rows = [fixture(1001, (10, "Arsenal"), (20, "Chelsea"), 2, 1),
            fixture(1002, (20, "Chelsea"), (10, "Arsenal"), None, None, short="NS")]
    calls = []
    def body(req):
        calls.append(dict(req.url.params))
        return rows
    res = IA.sync_fixtures(client(db, env(body)), lg, 2024)

    check("one call fetches a whole league-season", len(calls) == 1)
    check("...asking for that league and season",
          calls[0].get("league") == "39" and calls[0].get("season") == "2024")
    check("every fixture becomes a match row", res["fixtures"] == 2 and db.matches.count_documents({}) == 2)
    check("both clubs are created once each", db.teams.count_documents({}) == 2)
    m = db.matches.find_one({"ext_id": "1001"})
    check("a finished match keeps its score and status", m["status"] == "final" and m["hg"] == 2 and m["ag"] == 1)
    check("a fixture that has not started is scheduled",
          db.matches.find_one({"ext_id": "1002"})["status"] == "scheduled")
    check("the referee arrives with the fixture, costing no extra call", m.get("referee") == "M. Oliver")
    check("only the finished one is queued for detail",
          res["queued"] == 1 and db.ingest_queue.count_documents({"task": IA.QUEUE_TASK}) == 1)


# ------------------------------------------------------------------ 2. the stamping rule
def t_only_a_forecast_competition_stamps_the_club():
    """A cup ingested after a league must not repoint every club at the cup.

    `teams.league_iid` is what `images.py` and the engine read a club back by, so a cup that stamps
    it puts English clubs in a Champions League frame and, worse, gives them its crest.
    """
    db = seed()
    lg = league_row(db, 39, role="forecast")
    IA.sync_fixtures(client(db, env(lambda r: [fixture(1, (10, "Arsenal"), (20, "Chelsea"), 1, 0)])), lg, 2024)
    before = db.teams.find_one({"ext_id": "10"})["league_iid"]

    cup = league_row(db, 2, role="calendar")
    db.leagues.update_one({"iid": cup["iid"]}, {"$set": {"role": "calendar"}})
    cup = db.leagues.find_one({"iid": cup["iid"]})
    IA.sync_fixtures(client(db, env(lambda r: [fixture(9, (10, "Arsenal"), (30, "Real"), 2, 2, league=2)])), cup, 2024)

    after = db.teams.find_one({"ext_id": "10"})["league_iid"]
    check(f"a calendar competition leaves the club's league alone ({before} -> {after})", after == before)
    check("...but still creates the clubs it needs for its own fixture",
          db.teams.find_one({"ext_id": "30"}) is not None)


# ------------------------------------------------------------------ 3. the detail, in bundles
def t_bundle_writes_our_tables():
    db = seed()
    lg = league_row(db)
    sched = [fixture(f, (10, "Arsenal"), (20, "Chelsea"), 2, 1) for f in (1, 2, 3)]
    IA.sync_fixtures(client(db, env(lambda r: sched)), lg, 2024)

    calls = []
    def body(req):
        calls.append(dict(req.url.params))
        if "ids" in req.url.params:
            return [detailed(int(i), (10, "Arsenal"), (20, "Chelsea"), 2, 1)
                    for i in req.url.params["ids"].split("-")]
        return sched
    matches = list(db.matches.find({}))
    res = IA.ingest_bundle(client(db, body and env(body)), matches)

    check(f"three matches cost ONE call, not three ({len(calls)})", len(calls) == 1)
    check("...asked for by id, twenty at a time", "ids" in (calls[0] if calls else {}))
    check("every match was written", res["written"] == 3 and res["failed"] == 0)
    check("team rows: two a match", db.team_match_stats.count_documents({}) == 6)
    check("player rows: three a match", db.player_match_stats.count_documents({}) == 9)
    check("lineups were saved", db.lineups.count_documents({}) > 0)
    t = db.team_match_stats.find_one({"team_iid": db.teams.find_one({"ext_id": "10"})["iid"]})
    check(f"the home side's shots came through ({t.get('shots')})", t.get("shots") == 14)
    check(f"...and what it faced ({t.get('shots_against')})", t.get("shots_against") == 9)
    p = db.player_match_stats.find_one({"player_iid": db.players.find_one({"ext_id": "101"})["iid"]})
    check(f"a player's tackles came through ({p.get('tackles')})", p.get("tackles") == 4)
    # NOT 14. `team_match_stats.shots` is the team STATISTICS block (14 shots), while the
    # `team_shots` on a player row is the sum over the players we have (3 + 1 = 4). They are
    # different numbers on purpose: the engine builds a player's rate as his SHARE of the second,
    # so the denominator has to be the total of the players it is sharing between, or the shares do
    # not sum to one. Both normalizers do this -- `normalize.py` says so at its own `totals`.
    check(f"...with his club's player-sum beside it, not its shot count ({p.get('team_shots')})",
          p.get("team_shots") == 4 and t.get("shots") == 14)
    check("the match is marked ingested",
          db.matches.find_one({"ext_id": "1"}).get("ingested_at") is not None)


# ------------------------------------------------------------------ 4. a bad fixture is not a bad batch
def t_one_bad_fixture_does_not_lose_the_batch():
    db = seed()
    lg = league_row(db)
    sched = [fixture(f, (10, "A"), (20, "B"), 1, 0) for f in (1, 2)]
    IA.sync_fixtures(client(db, env(lambda r: sched)), lg, 2024)

    def body(req):
        if "ids" in req.url.params:
            good = detailed(1, (10, "A"), (20, "B"), 1, 0)
            bad = detailed(2, (10, "A"), (20, "B"), 1, 0)
            bad["players"] = "not a list"          # the shape a normalizer cannot survive
            return [good, bad]
        return sched
    res = IA.ingest_bundle(client(db, env(body)), list(db.matches.find({})))
    check(f"the good fixture is still written ({res['written']})", res["written"] == 1)
    check(f"the bad one is counted, not raised ({res['failed']})", res["failed"] == 1)
    check("...and recorded as an issue a human can read",
          db.ingest_issues.count_documents({"kind": "normalize_failed"}) == 1)


# ------------------------------------------------------------------ 5. a fixture they did not return
def t_missing_fixture_is_reported():
    db = seed()
    lg = league_row(db)
    IA.sync_fixtures(client(db, env(lambda r: [fixture(1, (10, "A"), (20, "B"), 1, 0)])), lg, 2024)
    res = IA.ingest_bundle(client(db, env(lambda r: [])), list(db.matches.find({})))
    check(f"a fixture left out of the answer is counted missing ({res['missing']})", res["missing"] == 1)
    check("...and says so in the issues",
          db.ingest_issues.count_documents({"kind": "fixture_missing"}) == 1)


# ------------------------------------------------------------------ 6. the queue, and resuming
def t_backfill_resumes():
    db = seed()
    lg = league_row(db, seasons=(2023, 2024))
    sched = {2023: [fixture(f, (10, "A"), (20, "B"), 1, 0, season=2023) for f in (11, 12)],
             2024: [fixture(f, (10, "A"), (20, "B"), 2, 0, season=2024) for f in (21, 22)]}
    calls = []
    def body(req):
        p = dict(req.url.params)
        calls.append(p)
        if "ids" in p:
            return [detailed(int(i), (10, "A"), (20, "B"), 1, 0) for i in p["ids"].split("-")]
        return sched[int(p["season"])]

    out = IA.backfill_tick(client(db, env(body)), max_seconds=5)
    check(f"both queued seasons were synced ({len(out['synced'])})", len(out["synced"]) == 2)
    check(f"all four matches were written ({out['written']})", out["written"] == 4)
    fixture_calls = [c for c in calls if "season" in c]
    check(f"one call a season, not one a match ({len(fixture_calls)})", len(fixture_calls) == 2)

    before = len(calls)
    IA.backfill_tick(client(db, env(body)), max_seconds=5)
    check(f"a second tick re-syncs nothing ({len(calls) - before} new calls)", len(calls) == before)


# ------------------------------------------------------------------ 7. the switch really switches
def t_the_tick_runs_one_provider_only():
    """With `provider.source` on API-Football, NO PitchAPI call may escape.

    The two providers key entities on different ext_ids, so a league ingested by both is every club
    and player stored twice (docs/78 section 5.1). A half-switched tick is therefore not a
    degraded tick, it is a corrupted database, which is why the switch skips the old steps
    wholesale rather than one at a time.
    """
    import jobs as J
    db = seed()
    S.set(db, "provider.source", "apifootball", actor="test") if hasattr(S, "set") else \
        db.settings.update_one({"key": "provider.source"}, {"$set": {"value": "apifootball"}}, upsert=True)
    lg = league_row(db, seasons=(2024,))
    sched = [fixture(f, (10, "A"), (20, "B"), 1, 0) for f in (1, 2)]

    pitch_calls = []
    class LoudPitch:
        """Any use of the old client at all is the failure this test exists for."""
        def __init__(self, db): self.db = db
        def __getattr__(self, name):
            def boom(*a, **k):
                pitch_calls.append(name)
                raise AssertionError(f"PitchAPI was called ({name}) while the source is API-Football")
            return boom

    def body(req):
        p = dict(req.url.params)
        if "ids" in p:
            return [detailed(int(i), (10, "A"), (20, "B"), 1, 0) for i in p["ids"].split("-")]
        return sched
    # Capture the real constructor BEFORE patching: the test's own `client()` helper calls
    # AF.Client, so a patch that routes back through it recurses until the stack gives out.
    real = AF.Client
    def fake(d, *a, **k):
        return real(d, httpx.Client(base_url=AF.BASE_URL, transport=httpx.MockTransport(env(body))),
                    sleep=lambda x: None)
    AF.Client = fake
    try:
        out = J.tick(db, client=LoudPitch(db), max_seconds=20)
    finally:
        AF.Client = real

    check(f"no PitchAPI call was made ({pitch_calls or 'none'})", not pitch_calls)
    check(f"the API-Football steps ran ({out['ran']})",
          any(r.startswith("af_") for r in out["ran"]))
    check(f"and the matches landed ({db.matches.count_documents({})})",
          db.matches.count_documents({}) == 2)
    check(f"with their statistics ({db.team_match_stats.count_documents({})} team rows)",
          db.team_match_stats.count_documents({}) == 4)



for fn in (t_schedule, t_only_a_forecast_competition_stamps_the_club, t_bundle_writes_our_tables,
           t_one_bad_fixture_does_not_lose_the_batch, t_missing_fixture_is_reported,
           t_backfill_resumes, t_the_tick_runs_one_provider_only):
    print(fn.__name__)
    fn()

print()
print(f"{sum(OK)}/{len(OK)} passed")
sys.exit(0 if all(OK) else 1)
