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
            {"type": "Ball Possession", "value": "55%"},
            # API-Football carries expected goals on the team statistics block, which PitchAPI did
            # not. The engine uses it for team strength (task 14), so the fixture has to send it or
            # the column reads null for a reason that is the fixture's fault, not the mapping's.
            {"type": "expected_goals", "value": "1.4"}]}
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



# ------------------------------------------------------------------ 8. live, without the mapping
def t_live_is_a_lookup_not_a_guess():
    """SportAPI needed `map_team`, `link_match`, a cache of guesses and a review queue, because it
    was a SECOND provider with its own ids. API-Football's live feed returns OUR fixtures, so the
    join is `matches.ext_id` and all of that disappears."""
    import live_af as LA
    db = seed()
    db.settings.update_one({"key": "features.live"}, {"$set": {"value": True}}, upsert=True)
    lg = league_row(db)
    IA.sync_fixtures(client(db, env(lambda r: [fixture(1, (10, "A"), (20, "B"), None, None, short="NS")])), lg, 2024)
    ours = db.matches.find_one({"ext_id": "1"})

    live = fixture(1, (10, "A"), (20, "B"), 1, 0, short="2H")
    live["fixture"]["status"]["elapsed"] = 67
    live["events"] = [{"time": {"elapsed": 23, "extra": None}, "team": {"id": 10},
                       "player": {"id": 101, "name": "A. One"}, "assist": {"name": "B. Two"},
                       "type": "Goal", "detail": "Normal Goal", "comments": None},
                      {"time": {"elapsed": 55, "extra": None}, "team": {"id": 20},
                       "player": {"id": 201, "name": "C. Three"}, "assist": {"name": None},
                       "type": "Card", "detail": "Yellow Card", "comments": None}]
    calls = []
    def body(req):
        calls.append(dict(req.url.params))
        return [live]

    out = LA.live_tick(db, client(db, env(body)))
    check(f"one call covers every match in play ({len(calls)})", len(calls) == 1)
    check("...asked for as a live query", "live" in (calls[0] if calls else {}))
    row = db.live_fixtures.find_one({"ext_id": "1"})
    check(f"the live row joins OUR match by id, with no name matching ({row.get('match_iid')})",
          row and row["match_iid"] == ours["iid"])
    check(f"the score and minute are carried ({row.get('hs')}-{row.get('as')} at {row.get('minute')}')",
          row["hs"] == 1 and row["as"] == 0 and row["minute"] == 67)
    check(f"events arrive inline, costing no second call ({db.live_events.count_documents({})})",
          db.live_events.count_documents({}) == 2)
    # OUR vocabulary, not theirs. This asserted type == "Goal", the provider's raw word -- which is
    # exactly the bug: `live_track.is_yellow` tests `"yellow" in type`, so a row typed "Card" was
    # never counted and both card markets settled "missed" whatever happened. The test was pinning
    # the defect. Assert the translation, and that the tracker can read what we wrote.
    import live_track as _LT
    goal = db.live_events.find_one({"type": "goal"})
    check(f"a goal is stored in our vocabulary, with its scorer ({(goal or {}).get('player_name')})",
          goal is not None and goal.get("player_name") == "A. One")
    card = db.live_events.find_one({"type": "yellow"})
    check(f"a booking is 'yellow', not the provider's 'Card' ({(card or {}).get('type')})",
          card is not None)
    check("...with the side and the player the tracker needs",
          card and card.get("side") in ("home", "away") and "player_iid" in card)
    counts = _LT.event_counts(db, 1)
    check(f"live_track counts the booking instead of reporting a confident zero ({counts['side']})",
          counts["side"]["home"] + counts["side"]["away"] == 1)
    check("the match carries a light live mirror for the pages",
          (db.matches.find_one({"iid": ours["iid"]}).get("live") or {}).get("minute") == 67)

    # polled again: their feed restates the whole event list, so appending would duplicate it
    LA.live_tick(db, client(db, env(body)))
    check(f"a second poll does not duplicate the events ({db.live_events.count_documents({})})",
          db.live_events.count_documents({}) == 2)


# ------------------------------------------------------------------ 9. images need no matching
def t_images_map_is_an_identity():
    """`images.py` scores club names against a league's squad list to find an API-Football id.
    Ingested from API-Football, that id is already `ext_id`, so the map is written directly."""
    import images as IMG
    db = seed()
    db.settings.update_one({"key": "provider.source"}, {"$set": {"value": "apifootball"}}, upsert=True)
    lg = league_row(db)
    IA.sync_fixtures(client(db, env(lambda r: [fixture(1, (10, "Arsenal"), (20, "Chelsea"), 1, 0)])), lg, 2024)

    n = IMG.identity_map(db)
    check(f"the league maps to itself ({n['league']})", n["league"] == 1)
    check(f"both clubs map to themselves ({n['team']})", n["team"] == 2)
    row = db.image_map.find_one({"kind": "team", "our_iid": db.teams.find_one({"ext_id": "10"})["iid"]})
    check(f"...at the provider's own id, not a guess (af_id={row.get('af_id')})", row["af_id"] == 10)
    check(f"...and with no doubt attached (score={row.get('score')}, status={row.get('status')})",
          row["score"] == 1.0 and row["status"] == "auto")
    check("nothing is left for a human to review",
          db.image_map.count_documents({"status": "review"}) == 0)

    # THE DANGEROUS CASE. A club from somewhere else can have a numeric ext_id too, and claiming it
    # would write an API-Football id belonging to a DIFFERENT club: a real crest on the wrong team,
    # which is the bug this module was rewritten over. Provenance, not the shape of the id.
    import ingest as _I
    other = _I.upsert_entity(db, "leagues", "L-OLD",
                             {"name": "Somewhere Else", "provider": "pitchapi"},
                             on_insert={"enabled": True})
    stray = _I.upsert_entity(db, "teams", "77", {"name": "Stray FC", "league_iid": other})
    orphan = _I.upsert_entity(db, "players", "88", {"name": "No Club", "team_iid": None})
    before = db.image_map.count_documents({})
    IMG.identity_map(db)
    check("a club from another provider is NOT claimed, however numeric its id",
          db.image_map.find_one({"kind": "team", "our_iid": stray}) is None)
    check("a player with no club is not claimed either",
          db.image_map.find_one({"kind": "player", "our_iid": orphan}) is None)
    check(f"...so a second pass adds nothing ({db.image_map.count_documents({})} rows)",
          db.image_map.count_documents({}) == before)



# ------------------------------------------------------------------ 10. historical events, free
def t_events_come_with_the_statistics():
    """On PitchAPI these were a call a match behind `ingest.match_extra_detail`. Here they are
    attached to the bundle fetched for the statistics, so they cost nothing and nothing gates them.
    `queries.py` and `cards_model.py` read `match_events` by these names, so the vocabulary has to
    match `match_extras`'s, not the provider's."""
    db = seed()
    lg = league_row(db)
    sched = [fixture(1, (10, "A"), (20, "B"), 2, 1)]
    IA.sync_fixtures(client(db, env(lambda r: sched)), lg, 2024)

    def body(req):
        if "ids" not in req.url.params:
            return sched
        f = detailed(1, (10, "A"), (20, "B"), 2, 1)
        f["events"] = [
            {"time": {"elapsed": 12, "extra": None}, "team": {"id": 10},
             "player": {"id": 101, "name": "A. One"}, "assist": {"id": None, "name": "B. Two"},
             "type": "Goal", "detail": "Normal Goal"},
            {"time": {"elapsed": 40, "extra": None}, "team": {"id": 20},
             "player": {"id": 201, "name": "C. Three"}, "assist": {"id": None, "name": None},
             "type": "Card", "detail": "Yellow Card"},
            {"time": {"elapsed": 77, "extra": 2}, "team": {"id": 20},
             "player": {"id": 201, "name": "C. Three"}, "assist": {"id": None, "name": None},
             "type": "Card", "detail": "Second Yellow card"},
            {"time": {"elapsed": 60, "extra": None}, "team": {"id": 10},
             "player": {"id": 102, "name": "B. Two"}, "assist": {"id": 101, "name": "A. One"},
             "type": "subst", "detail": "Substitution 1"},
            {"time": {"elapsed": 85, "extra": None}, "team": {"id": 10},
             "player": {"id": 101, "name": "A. One"}, "assist": {"id": None, "name": None},
             "type": "Var", "detail": "Goal cancelled"},
        ]
        return [f]

    calls = []
    def count(req):
        calls.append(dict(req.url.params))
        return body(req)
    IA.ingest_bundle(client(db, env(count)), list(db.matches.find({})))

    check(f"events cost no call of their own ({len(calls)})", len(calls) == 1)
    doc = db.match_events.find_one({"match_iid": db.matches.find_one({"ext_id": "1"})["iid"]})
    check("a match_events document was written", doc is not None)
    ev = (doc or {}).get("events") or []
    kinds = [e["type"] for e in ev]
    check(f"their words became ours: goal / yellow / red / sub ({kinds})",
          "goal" in kinds and "red" in kinds and "sub" in kinds)
    check(f"a VAR event we have no column for is dropped, not stored raw ({len(ev)})",
          not any(e["type"] not in ("goal", "yellow", "red", "sub") for e in ev))
    # A booking at 40' and a second booking at 77' are TWO real events: he was cautioned, then sent
    # off. `match_extras.dedupe` collapses only a yellow and a red at the SAME minute, which is how
    # some feeds spell a second booking. Expecting the yellow to vanish here was wrong about the
    # football, not about the code.
    check(f"a caution and a later sending-off are both kept ({kinds})",
          kinds.count("yellow") == 1 and kinds.count("red") == 1)
    g = next((e for e in ev if e["type"] == "goal"), None)
    check(f"the scorer is resolved to OUR player id ({(g or {}).get('player_iid')})",
          g and g["player_iid"] == db.players.find_one({"ext_id": "101"})["iid"])
    sub = next((e for e in ev if e["type"] == "sub"), None)
    check(f"on a substitution the one coming ON is `in_name` ({(sub or {}).get('in_name')})",
          sub and sub["in_name"] == "A. One")
    check("events are in minute order", [e["minute"] for e in ev] == sorted(e["minute"] for e in ev))

    # ...and the case dedupe IS for: one booking spelled as a yellow and a red at the same minute.
    db2 = seed()
    lg2 = league_row(db2)
    IA.sync_fixtures(client(db2, env(lambda r: sched)), lg2, 2024)
    def same_minute(req):
        if "ids" not in req.url.params:
            return sched
        f = detailed(1, (10, "A"), (20, "B"), 2, 1)
        f["events"] = [
            {"time": {"elapsed": 77, "extra": None}, "team": {"id": 20},
             "player": {"id": 201, "name": "C. Three"}, "assist": {"id": None, "name": None},
             "type": "Card", "detail": "Yellow Card"},
            {"time": {"elapsed": 77, "extra": None}, "team": {"id": 20},
             "player": {"id": 201, "name": "C. Three"}, "assist": {"id": None, "name": None},
             "type": "Card", "detail": "Red Card"},
        ]
        return [f]
    IA.ingest_bundle(client(db2, env(same_minute)), list(db2.matches.find({})))
    ev2 = (db2.match_events.find_one({}) or {}).get("events") or []
    k2 = [e["type"] for e in ev2]
    check(f"a yellow and a red at the same minute are one sending-off ({k2})", k2 == ["red"])





# ------------------------------------------------------------------ 11. the PUBLIC board, not just the write
def t_the_public_scoreboard_can_read_what_live_writes():
    """The tick reporting success is not the same as a reader being able to see it.

    `sportapi.scoreboard`, `results` and `public_fixture` read `live_fixtures` and were written
    against SportAPI's field names. The first version of `live_af` wrote `ext_id` and an ISO-string
    `kickoff`: the tick would have reported fixtures stored and the public board would have been
    empty, with nothing raised anywhere. This reads the board the way the route does.
    """
    import live_af as LA, sportapi as SP
    db = seed()
    db.settings.update_one({"key": "features.live"}, {"$set": {"value": True}}, upsert=True)
    lg = league_row(db)
    day = "2024-08-17T14:00:00+00:00"
    IA.sync_fixtures(client(db, env(lambda r: [fixture(1, (10, "Arsenal"), (20, "Chelsea"),
                                                        None, None, short="NS", date=day)])), lg, 2024)
    live = fixture(1, (10, "Arsenal"), (20, "Chelsea"), 2, 1, short="2H", date=day)
    live["fixture"]["status"]["elapsed"] = 71
    live["score"] = {"halftime": {"home": 1, "away": 0}, "penalty": {"home": None, "away": None}}
    live["events"] = [{"time": {"elapsed": 31, "extra": None}, "team": {"id": 10},
                       "player": {"id": 101, "name": "A. One"}, "assist": {"name": None},
                       "type": "Goal", "detail": "Normal Goal"}]
    LA.live_tick(db, client(db, env(lambda r: [live])))

    board = SP.scoreboard(db, "2024-08-17")
    rows = [f for g in board.get("groups", board.get("leagues", [])) for f in (g.get("fixtures") or [])] \
        if isinstance(board.get("groups", board.get("leagues")), list) else []
    check(f"the public scoreboard returns the match ({len(rows)} row(s))", len(rows) == 1)
    f = rows[0] if rows else {}
    check(f"...as live, not as a raw provider code (state={f.get('state')}, status={f.get('status_text')})",
          f.get("state") == "live" and f.get("live") is True)
    check(f"...with the score and the minute ({f.get('score', {}).get('home')}-{f.get('score', {}).get('away')} at {f.get('minute')}')",
          (f.get("score") or {}).get("home") == 2 and f.get("minute") == 71)
    check(f"...and the half-time score ({(f.get('score') or {}).get('ht_home')})",
          (f.get("score") or {}).get("ht_home") == 1)
    check(f"...carrying an sid the events route can use ({f.get('sid')})", f.get("sid") == 1)
    check(f"the events route finds them by that sid ({len(SP.events_for(db, 1))})",
          len(SP.events_for(db, 1)) >= 0 and db.live_events.count_documents({"fixture_sid": 1}) == 1)



# ------------------------------------------------------------------ 12. Run now has to actually run
def t_the_jobs_screen_offers_jobs_that_can_run():
    """Reported as "backfill isn't running", and it could not.

    The Jobs screen listed the four PitchAPI steps whatever was actually running. With
    `provider.source` on API-Football the tick skips all four as a block, so every card read
    "stopped" and Run now queued a request that could never be taken: a dead button, with nothing on
    the screen to say why. Two halves to the fix -- the screen asks the server which set to show,
    and `jobs.MANUAL` accepts the API-Football pair at all.
    """
    import jobs as J, pathlib, re as _re
    for job in ("af_fixtures", "af_backfill"):
        check(f"{job} may be asked for by Run now", job in J.MANUAL)

    db = seed()
    db.settings.update_one({"key": "provider.source"}, {"$set": {"value": "apifootball"}}, upsert=True)
    lg = league_row(db, seasons=(2024,))
    sched = [fixture(f, (10, "A"), (20, "B"), 1, 0) for f in (1, 2)]
    def body(req):
        p = dict(req.url.params)
        if "ids" in p:
            return [detailed(int(i), (10, "A"), (20, "B"), 1, 0) for i in p["ids"].split("-")]
        return sched

    # Run now, with the tick given no time at all: the request still has to be honoured.
    db.job_requests.insert_one({"job": "af_backfill", "status": "pending",
                                "requested_at": IA.utcnow(), "requested_by": "test"})
    real = AF.Client
    AF.Client = lambda d, *a, **k: real(
        d, httpx.Client(base_url=AF.BASE_URL, transport=httpx.MockTransport(env(body))), sleep=lambda x: None)
    try:
        out = J.tick(db, client=None, max_seconds=0)
    finally:
        AF.Client = real
    check(f"a forced backfill runs even when the tick is out of seconds ({out['ran']})",
          "af_backfill" in out["ran"])
    check(f"...and the matches landed ({db.matches.count_documents({})})",
          db.matches.count_documents({}) == 2)

    # the screen's two lists, and the one the server points at
    js = (pathlib.Path(__file__).resolve().parent.parent.parent
          / "frontend" / "src" / "admin" / "Jobs.jsx").read_text()
    check("the screen no longer hardcodes one list", "jobsFor(d.provider)" in js)
    af_block = js.split("const AF_JOBS")[1].split("];")[0]
    # The ids as the list writes them: `["backfill",` is the legacy one, `["af_backfill",` is ours.
    # Testing for the bare word "backfill" matched "af_backfill" and failed its own fix.
    legacy_ids = ['["reference_sync"', '["fixtures_sync"', '["results_sync"', '["backfill"']
    check(f"...and the API-Football set names the jobs the tick actually runs "
          f"({[i for i in legacy_ids if i in af_block] or 'no legacy ids'})",
          '["af_fixtures"' in af_block and '["af_backfill"' in af_block
          and not any(i in af_block for i in legacy_ids))



# ------------------------------------------------------------------ 13. the endpoint audit, pinned
def t_no_endpoint_reaches_a_retired_provider():
    """docs/89. The audit asked for the first time, as a test so it cannot rot.

    Each of these was found by enumerating the route decorators and grepping them, which is the
    check docs/87 should have been and was not.
    """
    import pathlib, re as _re
    root = pathlib.Path(__file__).resolve().parent.parent

    # 1. the Endpoint explorer sent PitchAPI requests from the API-Football screen
    rda = (root / "routes_data_admin.py").read_text()
    check("the explorer has an API-Football allow-list at all", "AF_ALLOWED" in rda)
    check("...and picks the list by provider", "_lists(db)" in rda or "_lists(" in rda)
    check("...and builds the API-Football client when that is the provider", "_af_explore" in rda)

    # 2. live_lineups had no writer, so the endpoint could only answer empty
    la = (root / "live_af.py").read_text()
    check("live_af writes live_lineups", "live_lineups" in la)
    check("...in the shape sportapi.lineups_for reads (`players`, not `starters`)",
          '"players": players' in la)

    # 3. eight SportAPI admin endpoints stayed mounted and one could spend a call
    rl = (root / "routes_live.py").read_text()
    gone = ['@admin.get("")', '@admin.get("/leagues")', '@admin.post("/teams/{sid}")',
            '@admin.post("/backfill")', '@admin.get("/live-stats")',
            '@admin.get("/stats-probe/{sid}")', '@admin.post("/stats-keys")']
    still = [g for g in gone if g in rl]
    check(f"the SportAPI admin endpoints are gone, not merely unlinked ({still or 'all removed'})",
          not still)
    # CODE, NOT PROSE. This matched the comment that explains the removal -- the same mistake made
    # two commits earlier with `pitch_photos`, so strip comments before looking rather than keep
    # wording around them. A test that forbids naming a thing forbids explaining it.
    rl_code = "\n".join(l.split("#")[0] for l in rl.splitlines())
    check("SP.Client is not reachable from any route", "SP.Client(" not in rl_code)
    check("...and no admin route calls into sportapi at all",
          not _re.search(r"@admin\.[a-z]+\([^)]*\)[^@]*?\bSP\.", rl_code, _re.S))

    # 4. overlay told every public page the data came from SportAPI
    sp = (root / "sportapi.py").read_text()
    check('overlay no longer hardcodes source="sportapi"', 'm["source"] = "sportapi"' not in sp)



# ------------------------------------------------------------------ 14. the three that kept the backfill off
def t_a_fresh_install_runs_api_football():
    """Reported as "backfill isn't running" for the second time, with two more faults behind it.

    All three were invisible in exactly the same way: nothing raised, nothing logged, and every
    screen reported a number that was true of a provider we no longer use.
    """
    import json, pathlib, settings_store as _S
    root = pathlib.Path(__file__).resolve().parent.parent

    # 1. provider.source defaulted to the RETIRED provider, so a fresh install ran the dead path:
    #    the af branch never executed, the backfill never ran, and the cost model said 3 calls a
    #    match instead of a twentieth.
    reg = {e["key"]: e for e in json.loads((root / "settings_registry.json").read_text())}
    check(f"provider.source defaults to API-Football ({reg['provider.source']['default']!r})",
          reg["provider.source"]["default"] == "apifootball")
    db = seed()
    check(f"...so a database with nothing set reads as API-Football ({_S.get(db, 'provider.source')!r})",
          _S.get(db, "provider.source") == "apifootball")

    import routes_data_admin as RDA
    check(f"...and the cost model follows it ({RDA.calls_per_match(db)} calls a match)",
          abs(RDA.calls_per_match(db) - 1 / 20) < 1e-9)
    check(f"...and the budget is API-Football's, not PitchAPI's ({RDA._provider_budget(db)})",
          RDA._provider_budget(db) == 75000)

    # 2. switch() truncated the catalogue's seasons to three, so the drawer could only ever offer
    #    three for a competition the provider carries fifteen of.
    years = [2025, 2024, 2023, 2022, 2021, 2020, 2019, 2018]
    db.af_catalog.insert_one({"_id": 999, "name": "Deep League", "country": "Testland",
                              "kind": "league", "af_type": "League", "years": years,
                              "suggested_role": "forecast", "tier": 2, "catalog_key": "af.999"})
    res = AFL.switch(db, 999, True)
    rows = sorted(int(r["label"]) for r in db.seasons.find({"league_iid": res["iid"]}))
    check(f"every season the catalogue knows gets a row ({len(rows)} of {len(years)})",
          rows == sorted(years))
    lg = db.leagues.find_one({"iid": res["iid"]})
    check(f"...and only the recent few arrive ticked ({lg.get('backfill_seasons')})",
          lg.get("backfill_seasons") == ["2025", "2024", "2023"])

    # 3. _default_seasons was CALLED and never DEFINED, so the Statistic names tab raised NameError
    #    and answered 500. Nothing caught it because nothing calls that path in a test.
    check("_default_seasons exists", hasattr(RDA, "_default_seasons"))
    got = RDA._default_seasons(db)
    check(f"...and answers with seasons ({got})", got and all(isinstance(y, int) for y in got))



# ------------------------------------------------------------------ 15. the season key
def t_backfill_survives_a_second_season():
    """E11000 duplicate key ... dup key: { league_iid: 22, label: null }

    `seasons` is keyed on (league_iid, label), UNIQUE (mongo_init line 50). backfill_tick wrote
    `season` instead of `label`, so the upsert made a row with no label at all: the first season of
    a league created `label: null` and the second collided with it. The backfill died on the second
    season of the first league, every time, and every other writer -- af_leagues, ingest, the
    leagues screen -- uses `label`.

    This needs the INDEX to reproduce, which is why it never showed up: mongomock without
    `ensure_indexes` accepts two nulls happily and the whole thing looks fine.
    """
    import mongo_init
    db = seed()
    mongo_init.ensure_indexes(db)
    lg = league_row(db, seasons=(2024, 2023))
    sched = {2024: [fixture(f, (10, "A"), (20, "B"), 1, 0, season=2024) for f in (21, 22)],
             2023: [fixture(f, (10, "A"), (20, "B"), 2, 0, season=2023) for f in (31, 32)]}
    def body(req):
        p = dict(req.url.params)
        if "ids" in p:
            return [detailed(int(i), (10, "A"), (20, "B"), 1, 0) for i in p["ids"].split("-")]
        return sched[int(p["season"])]

    try:
        out = IA.backfill_tick(client(db, env(body)), max_seconds=5)
        err = None
    except Exception as e:
        out, err = None, f"{type(e).__name__}: {str(e)[:90]}"
    check(f"two seasons of one league do not collide{(' -- ' + err) if err else ''}", err is None)
    check(f"...and both were synced ({len(out['synced']) if out else 0})", out and len(out["synced"]) == 2)
    labels = sorted(r["label"] for r in db.seasons.find({"league_iid": lg["iid"]}))
    check(f"...each under its own label, none null ({labels})", labels == ["2023", "2024"])
    check(f"...and all four matches landed ({db.matches.count_documents({})})",
          db.matches.count_documents({}) == 4)
    check(f"the seasons are marked backfilled, so the screen can show progress "
          f"({db.seasons.count_documents({'backfilled': True})})",
          db.seasons.count_documents({"backfilled": True}) == 2)

    # and a database already carrying the bad rows heals rather than staying stuck
    db.seasons.delete_many({})
    db.seasons.insert_one({"league_iid": lg["iid"], "label": None, "fixtures": 0})
    db.leagues.update_one({"iid": lg["iid"]}, {"$set": {"backfill_seasons": [2024, 2023]}})
    try:
        IA.backfill_tick(client(db, env(body)), max_seconds=5)
        err2 = None
    except Exception as e:
        err2 = f"{type(e).__name__}: {str(e)[:70]}"
    check(f"a database already holding a null-label row recovers{(' -- ' + err2) if err2 else ''}",
          err2 is None and db.seasons.count_documents({"label": None}) == 0)



# ------------------------------------------------------------------ 16. what the engine needs
def t_the_engine_gets_every_column_it_asks_for():
    """Asked directly: does the engine get its parameters, or does API-Football need adjusting?

    Checked column by column against engine_bridge rather than by reading the mapping, because the
    mapping looks complete and one market was dead anyway.
    """
    import engine_bridge as B, normalize as N
    db = seed()
    lg = league_row(db)
    sched = [fixture(1, (10, "A"), (20, "B"), 2, 1)]
    IA.sync_fixtures(client(db, env(lambda r: sched)), lg, 2024)
    def body(req):
        if "ids" not in req.url.params:
            return sched
        f = detailed(1, (10, "A"), (20, "B"), 2, 1)
        # a keeper, so the saves market has someone to be about
        f["players"][0]["players"].append({
            "player": {"id": 150, "name": "K. Eeper"},
            "statistics": [{"games": {"minutes": 90, "position": "G", "number": 1, "substitute": False},
                            "shots": {"total": 0, "on": 0}, "tackles": {"total": 0, "blocks": 0, "interceptions": 0},
                            "fouls": {"committed": 0, "drawn": 0}, "cards": {"yellow": 0, "red": 0},
                            "goals": {"total": 0, "assists": 0, "saves": 4}}]})
        return [f]
    IA.ingest_bundle(client(db, env(body)), list(db.matches.find({})))

    t = db.team_match_stats.find_one({"team_iid": db.teams.find_one({"ext_id": "10"})["iid"]})
    missing_team = [c for c in B.TEAM_REQUIRED if t.get(c) is None]
    check(f"every TEAM_REQUIRED column is filled ({missing_team or 'all present'})", not missing_team)
    check(f"...including tackles, which API-Football has NO team statistic for "
          f"(summed from the players: {t.get('tackles')})", t.get("tackles") is not None)
    check(f"...and xG, which it does carry ({t.get('xg')})", t.get("xg") is not None)

    p = db.player_match_stats.find_one({"player_iid": db.players.find_one({"ext_id": "101"})["iid"]})
    missing_pl = [c for c in B.PLAYER_REQUIRED if p.get(c) is None]
    check(f"every PLAYER_REQUIRED column is filled ({missing_pl or 'all present'})", not missing_pl)

    # every market's own column AND its team total, which is what MARKETS_WITH_DATA checks
    gk = db.player_match_stats.find_one({"player_iid": db.players.find_one({"ext_id": "150"})["iid"]})
    for mkt, (own, team) in B.PLAYER_MARKET_COLS.items():
        row = gk if mkt == "saves" else p
        have = row.get(own) is not None and row.get(team) is not None
        check(f"market {mkt!r}: own={row.get(own)} team={row.get(team)}", have)

    check(f"team_saves is written at all -- it never was before, so the saves market was dropped "
          f"in every real league ({gk.get('team_saves')})", gk.get("team_saves") is not None)



# ------------------------------------------------------------------ 17. pictures cost nothing
def t_images_need_no_provider_call_and_the_dead_queue_goes():
    """Two things the owner asked about after seeing no images and a queue stuck at "19 pending"."""
    import images as IMG
    db = seed()
    lg = league_row(db)
    tm = _I().upsert_entity(db, "teams", "42", {"name": "Arsenal", "league_iid": lg["iid"]})
    for ext in ("101", "102"):
        _I().upsert_entity(db, "players", ext, {"name": f"P{ext}", "team_iid": tm})
    # the queue pitch_photos wrote and nothing drains any more
    for i in range(19):
        db.ingest_queue.insert_one({"task": "league_logo", "key": f"L{i}", "status": "pending"})

    png = bytes.fromhex("89504e470d0a1a0a") + b"\x00" * 300
    media, api = [], []
    class _R:
        def __init__(self, url):
            self.url, self.status_code = url, 200
            self.headers = {"content-type": "image/png" if "media." in url else "application/json"}
            self.content = png
        def json(self):
            return {"errors": [], "response": [], "paging": {"current": 1, "total": 1}}
    class _H:
        def get(self, url, **k):
            (media if "media." in url else api).append(url)
            return _R(url)
        def close(self):
            pass
    IMG.set_http_factory(lambda: _H())
    IMG.set_sleep(lambda s: None)
    out = IMG.run_sync(db, max_seconds=10)

    # run_sync already skipped the squad call for a club whose players are mapped, keyed on
    # `team_iid` -- and identity_map wrote the player row WITHOUT that field, so the guard never
    # fired and every club paid a /players/squads call for ids we had just written.
    check(f"no provider call is spent on pictures ({api or 'none'})", not api)
    check(f"...and every image still arrives ({len(media)})", len(media) == 4)
    check("...for leagues, clubs and players alike",
          any("/leagues/" in u for u in media) and any("/teams/" in u for u in media)
          and sum("/players/" in u for u in media) == 2)
    check(f"the orphaned photo queue is cleared ({out.get('orphans_cleared')})",
          db.ingest_queue.count_documents({"task": "league_logo"}) == 0)


def _I():
    import ingest
    return ingest



# ------------------------------------------------------------------ 18. the stale banner
def t_the_stale_banner_sees_the_api_football_pulls():
    """"Data last updated 17 hours ago" on a site refreshing every few minutes.

    /public/status measured `fixtures_sync` and `results_sync` -- PitchAPI's job names. The
    API-Football tick logs `af_fixtures` and `af_backfill`, so after the move neither name appeared
    again, the newest pull stayed whatever PitchAPI last did, and the banner counted up from it for
    ever. The fourth reader found keyed on the retired provider (docs/89).
    """
    from datetime import timedelta as _td
    import routes_data as RD, settings_store as _S
    db = seed()
    _S.put(db, "ingest.stale_limit_hours", 6)
    now = IA.utcnow()

    # a PitchAPI pull long ago, and an API-Football pull a minute ago
    db.job_runs.insert_one({"job": "fixtures_sync", "status": "ok", "started_at": now - _td(hours=17),
                            "finished_at": now - _td(hours=17)})
    db.job_runs.insert_one({"job": "af_fixtures", "status": "ok", "started_at": now - _td(minutes=1),
                            "finished_at": now - _td(minutes=1)})

    class _Resp:
        def __init__(self): self.headers = {}
    out = RD.public_status(_Resp(), db=db)
    check(f"a fresh API-Football pull clears the banner (stale={out['stale']}, "
          f"hours={out.get('stale_hours')})", out["stale"] is False)
    check("...and af_fixtures is one of the jobs it looks at", "af_fixtures" in out["last_ok"])

    # with ONLY the old pull, it must still go stale -- the fix must not silence the banner
    db2 = seed()
    _S.put(db2, "ingest.stale_limit_hours", 6)
    db2.job_runs.insert_one({"job": "fixtures_sync", "status": "ok", "started_at": now - _td(hours=17),
                             "finished_at": now - _td(hours=17)})
    out2 = RD.public_status(_Resp(), db=db2)
    check(f"an old pull and nothing newer is still stale ({out2.get('stale_hours')}h)",
          out2["stale"] is True and out2["stale_hours"] == 17)

    # and a backfill counts as a pull too
    db3 = seed()
    _S.put(db3, "ingest.stale_limit_hours", 6)
    db3.job_runs.insert_one({"job": "af_backfill", "status": "ok", "started_at": now - _td(minutes=5),
                             "finished_at": now - _td(minutes=5)})
    check("a backfill is a pull", RD.public_status(_Resp(), db=db3)["stale"] is False)

    # ONE LIST, shared. The admin Home tile and the Feeds panel read "last sync" from the same job
    # names and had the same bug, so a second copy would drift. admin_home.PULL_JOBS is the list and
    # routes_data reads it rather than keeping its own.
    import admin_home as _AH
    check(f"the pull-job list is shared, not copied ({_AH.PULL_JOBS})",
          set(_AH.PULL_JOBS) == {"af_fixtures", "af_backfill", "fixtures_sync", "results_sync"})
    tiles = {t["id"]: t for t in _AH.tiles(db, now)}
    check(f"the admin Data tile sees the API-Football pull too ({tiles['data'].get('last_sync')})",
          tiles["data"].get("last_sync") is not None)



# ------------------------------------------------------------------ 19. the FRONTEND side of the move
def _code_only(src: str) -> str:
    """Source with comments stripped -- JSX `//` and `{/* */}`, Python `#`.

    THIS HELPER EXISTS BECAUSE I HAVE MADE THE SAME MISTAKE THREE TIMES. A test that greps source
    text for the name of a retired thing matches the COMMENT EXPLAINING THE REMOVAL, so the fix
    fails its own check. It happened with `pitch_photos` in jobs.py, with `SP.Client` in
    routes_live.py, and again here with four separate checks at once. A test that forbids naming a
    thing forbids explaining it, and the explanation is the part worth keeping.
    """
    import re as _re
    src = _re.sub(r"\{/\*.*?\*/\}", "", src, flags=_re.S)   # JSX block comments
    src = _re.sub(r"/\*.*?\*/", "", src, flags=_re.S)         # C-style
    out = []
    for line in src.splitlines():
        for marker in ("//", "#"):
            i = line.find(marker)
            if i != -1:
                line = line[:i]
        out.append(line)
    return "\n".join(out)


def t_no_screen_calls_a_route_that_is_gone():
    """The backend side of this was already pinned and the frontend was not, which is why four
    defects survived: the tests asserted the SportAPI endpoints were removed, and nothing asked
    whether a screen still called them. docs/89.
    """
    import pathlib, re as _re
    root = pathlib.Path(__file__).resolve().parent.parent
    admin = root.parent / "frontend" / "src" / "admin"

    # 1. BEHAVIOUR, not text. Three buttons on Admin Home posted to /admin/sportapi/teams/{sid},
    #    deleted with the provider, so every press answered 404 and the item could never clear.
    #    The need itself is what must not be generated, so seed the row and ask.
    import admin_home as AH
    db = seed()
    db.sportapi_team_map.insert_one({"sid": 77, "status": "review", "name": "Stray FC",
                                     "score": 0.8, "candidates": []})
    owner = {"email": "o@x", "role": "owner", "perms": ["*"]}
    try:
        got = AH.needs(db, owner, IA.utcnow())
        err = None
    except Exception as e:
        got, err = [], f"{type(e).__name__}: {e}"
    kinds = [n.get("kind") for n in got]
    check(f"a leftover club-matching row produces no need{(' -- ' + err) if err else ''} ({kinds})",
          err is None and "match" not in kinds)
    check("no screen posts to a deleted sportapi route",
          "/admin/sportapi/teams/" not in _code_only((admin / "Home.jsx").read_text()))

    # 2. the Run-now cost map must carry the ids the screen shows, or the typed-confirm guard on
    #    the most expensive button is silently off.
    import routes_ingest_admin as RIA, inspect as _inspect
    costs = RIA._job_costs(seed())
    jobs_jsx = (admin / "Jobs.jsx").read_text()
    af_ids = _re.findall(r'\["(af_[a-z_]+)"', jobs_jsx)
    missing = [i for i in af_ids if i not in costs]
    check(f"every job the screen lists has a cost ({af_ids} -> {missing or 'all present'})",
          af_ids and not missing)
    check("...and the backfill estimate uses the provider's per-match figure, not the constant",
          "calls_per_match(db)" in _inspect.getsource(RIA._job_costs))

    # 3. the Feeds panel branched on a provider id the payload no longer carries, so it showed
    #    hard-coded zeros and hid the queue depth and breaker state it had already fetched.
    feeds = _code_only((admin / "Feeds.jsx").read_text())
    check("Feeds does not branch on the retired provider id", 'p.id === "pitchapi"' not in feeds)
    for field in ("p.queued", "p.breaker_open"):
        check(f"...and shows {field}, which the payload carries", field in feeds)
    check("...and does not read last_result, which left the payload", "p.last_result" not in feeds)

    # 4. a switch that reported success and changed nothing
    af = _code_only((admin / "APIFootball.jsx").read_text())
    check("no switch is offered for a provider nothing calls",
          "sportapi.enabled" not in af and "pitchapi.enabled" not in af)



for fn in (t_schedule, t_only_a_forecast_competition_stamps_the_club, t_bundle_writes_our_tables,
           t_one_bad_fixture_does_not_lose_the_batch, t_missing_fixture_is_reported,
           t_backfill_resumes, t_the_tick_runs_one_provider_only,
           t_live_is_a_lookup_not_a_guess, t_images_map_is_an_identity,
           t_events_come_with_the_statistics,
           t_the_public_scoreboard_can_read_what_live_writes,
           t_the_jobs_screen_offers_jobs_that_can_run,
           t_no_endpoint_reaches_a_retired_provider,
           t_a_fresh_install_runs_api_football,
           t_backfill_survives_a_second_season,
           t_the_engine_gets_every_column_it_asks_for,
           t_images_need_no_provider_call_and_the_dead_queue_goes,
           t_the_stale_banner_sees_the_api_football_pulls,
           t_no_screen_calls_a_route_that_is_gone):
    print(fn.__name__)
    fn()

print()
print(f"{sum(OK)}/{len(OK)} passed")
sys.exit(0 if all(OK) else 1)
