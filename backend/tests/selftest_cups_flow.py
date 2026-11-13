"""Cup formats, match momentum, the final whistle, every season, and pictures on their own clock.

Each block runs the real function on a mongomock database and checks what came out.
"""
import sys, os, base64
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("APP_ENCRYPTION_KEY", base64.b64encode(os.urandom(32)).decode())

from datetime import datetime, timedelta, timezone

import mongomock

OK = []


def check(name, cond):
    cond = bool(cond)
    OK.append(cond)
    print(("  ok     " if cond else "  FAIL   ") + name)


NOW = datetime(2026, 11, 13, 21, 0, tzinfo=timezone.utc)


def team_row(rank, tid, name, group, pts, desc=None):
    return {"rank": rank, "team": {"id": tid, "name": name}, "points": pts, "goalsDiff": pts - 3, "group": group,
            "form": "WWDLW", "description": desc, "all": {"played": 4, "win": 2, "draw": 1, "lose": 1, "goals": {"for": 6, "against": 4}}}


# ------------------------------------------------------------------ 1. cup formats
print("standings: a cup is drawn the way it is played")
import standings as ST

check("group and league-phase matchdays are table rounds",
      all(ST.is_table_round(x) for x in ["Regular Season - 12", "Group Stage - 2", "Group A - 3", "League A - 4", "League Stage - 8"]))
check("knockout rounds are not", not any(ST.is_table_round(x) for x in ["Round of 16", "Quarter-finals", "Final", "1st Qualifying Round", "Play-offs", None, ""]))

nations = [{"league": {"standings": [
    [team_row(1, 9, "Spain", "League A - Group 4", 10, "Promotion - Nations League Finals"), team_row(2, 10, "Denmark", "League A - Group 4", 7)],
    [team_row(1, 11, "Portugal", "League A - Group 1", 9), team_row(2, 12, "Croatia", "League A - Group 1", 6)],
    [team_row(1, 13, "San Marino", "League D - Group 1", 4, "Promotion - League C")],
]}}]
groups = ST.parse(nations)
check("Nations League: three groups, not one table", len(groups) == 3)
check("each group named by the provider", [g["name"] for g in groups] == ["League A - Group 4", "League A - Group 1", "League D - Group 1"])
check("Spain and San Marino are never ranked together",
      not any({r["team_name"] for r in g["rows"]} >= {"Spain", "San Marino"} for g in groups))
check("a row carries played, points, form and the provider's note",
      groups[0]["rows"][0]["p"] == 4 and groups[0]["rows"][0]["pts"] == 10 and groups[0]["rows"][0]["form"] == "WWDLW"
      and groups[0]["rows"][0]["description"].startswith("Promotion"))
check("an empty answer (a knockout-only cup) is no groups", ST.parse([]) == [] and ST.parse([{"league": {"standings": []}}]) == [])

db = mongomock.MongoClient().db
db.leagues.insert_one({"iid": 5, "id": "L5", "ext_id": "5", "kind": "international", "current_season": "2026", "enabled": True})
for i, (tid, name) in enumerate([(9, "Spain"), (10, "Denmark"), (11, "Portugal"), (12, "Croatia"), (13, "San Marino")]):
    db.teams.insert_one({"iid": 100 + i, "id": f"t{tid}", "ext_id": str(tid), "name": name})
db.league_standings.insert_one({"league_iid": 5, "season": "2026", "groups": groups, "at": NOW})
db.matches.insert_many([
    {"iid": 1, "id": "m1", "league_iid": 5, "season": "2026", "stage": "League A - 4", "kickoff": datetime(2026, 10, 1), "home_iid": 100, "away_iid": 101, "status": "final", "hg": 2, "ag": 0},
    {"iid": 2, "id": "m2", "league_iid": 5, "season": "2026", "stage": "Quarter-finals", "kickoff": datetime(2027, 3, 20), "home_iid": 100, "away_iid": 102, "status": "final", "hg": 1, "ag": 1, "pen_home": 4, "pen_away": 3},
    {"iid": 3, "id": "m3", "league_iid": 5, "season": "2026", "stage": "Final", "kickoff": datetime(2027, 6, 8), "home_iid": 100, "away_iid": 103, "status": "scheduled"},
])
r = ST.read(db, db.leagues.find_one({"iid": 5}))
check("read: format is groups", r["format"] == "groups" and len(r["groups"]) == 3)
check("read: rows point at our team pages", r["groups"][0]["rows"][0]["team"]["id"] == "t9")
check("read: knockout rounds come from the fixtures, oldest first", [x["name"] for x in r["rounds"]] == ["Quarter-finals", "Final"])
check("read: a group matchday is not a knockout round", all(x["name"] != "League A - 4" for x in r["rounds"]))
check("read: a shoot-out carries its score", r["rounds"][0]["matches"][0]["pen_home"] == 4)

db.leagues.insert_one({"iid": 6, "id": "L6", "ext_id": "6", "kind": "cup", "current_season": "2026", "enabled": True})
db.matches.insert_one({"iid": 9, "id": "m9", "league_iid": 6, "season": "2026", "stage": "3rd Round", "kickoff": datetime(2026, 1, 9), "home_iid": 100, "away_iid": 101, "status": "final", "hg": 3, "ag": 1})
r = ST.read(db, db.leagues.find_one({"iid": 6}))
check("an FA-Cup-like competition: knockout, no table", r["format"] == "knockout" and not r["groups"])
db.leagues.insert_one({"iid": 7, "id": "L7", "ext_id": "7", "kind": "league", "current_season": "2026", "enabled": True})
check("a league with nothing stored says 'none' so the page builds from results", ST.read(db, db.leagues.find_one({"iid": 7}))["format"] == "none")

check("due: no table stored yet", ST.due(db, {"iid": 7}, "2026", NOW))
check("due: stored a minute ago is not", not ST.due(db, {"iid": 5}, "2026", NOW + timedelta(minutes=1)))

# ------------------------------------------------------------------ 2. momentum
print("match_flow: momentum and possession from our own snapshots")
import match_flow as MF
db = mongomock.MongoClient().db
check("no snapshots: nothing drawn", MF.flow(db, 77) is None)
tot = {"home": {"shots": 0, "sot": 0, "corners": 0, "poss": 50}, "away": {"shots": 0, "sot": 0, "corners": 0, "poss": 50}}
for minute in range(1, 61):
    # home pushes in the first half hour, away after
    side = "home" if minute <= 30 else "away"
    if minute % 3 == 0:
        tot[side]["shots"] += 1
    if minute % 9 == 0:
        tot[side]["sot"] += 1
    tot["home"]["poss"] = 60 if minute <= 30 else round((60 * 30 + 40 * (minute - 30)) / minute, 1)
    tot["away"]["poss"] = 100 - tot["home"]["poss"]
    MF.record(db, 77, 1, minute, {s: dict(v) for s, v in tot.items()}, NOW)
MF.record(db, 77, 1, 60, {s: dict(v) for s, v in tot.items()}, NOW)          # the same minute twice
check("one row a minute, however often it is polled", db.live_stats_series.count_documents({"fixture_sid": 77}) == 60)
f = MF.flow(db, 77, [{"minute": 12, "side": "home"}])
known = [w for w in f["windows"] if w["known"]]
check("twelve five-minute windows known for an hour followed", len(known) == 12)
check("the first half hour leans home", all(w["pressure"] >= 0 for w in known[:6]) and sum(w["pressure"] for w in known[:6]) > 0)
check("the next half hour leans away", all(w["pressure"] <= 0 for w in known[6:]) and sum(w["pressure"] for w in known[6:]) < 0)
check("possession per window is recovered from the running average",
      abs(known[2]["poss_home"] - 60) < 0.5 and abs(known[8]["poss_home"] - 40) < 0.5)
check("goals ride along", f["goals"] == [{"minute": 12, "side": "home"}])
db.live_stats_series.update_one({"fixture_sid": 77, "minute": 40}, {"$set": {"away.shots": 0}})   # provider corrects a total down
check("a total that falls never makes a negative window",
      all(w[s][c] >= 0 for w in MF.flow(db, 77)["windows"] if w["known"] for s in ("home", "away") for c in ("shots", "sot", "corners")))
for m in range(1, 5):
    MF.record(db, 78, 2, m, tot, NOW)
check("four minutes followed is not a timeline", MF.flow(db, 78) is None)

# ------------------------------------------------------------------ 3. the final whistle
print("live_af: a match that left the live feed is asked for by id")
import live_af as LA
import apifootball as AF
import settings_store as S
db = mongomock.MongoClient().db
S.put(db, "features.live", True, "test")
db.leagues.insert_one({"iid": 1, "ext_id": "39", "enabled": True, "provider": "apifootball"})
db.matches.insert_one({"iid": 500, "ext_id": "9001", "league_iid": 1, "home_iid": 1, "away_iid": 2, "status": "scheduled", "ingested_at": None})
db.live_fixtures.insert_one({"sid": 9001, "provider": "apifootball", "in_play": True, "status": "2H", "minute": 90,
                             "kickoff": (NOW - timedelta(hours=2)).replace(tzinfo=None), "match_iid": 500})


def fx(fid, short, elapsed, hs=2, as_=1):
    return {"fixture": {"id": fid, "date": "2026-11-13T19:00:00+00:00", "status": {"short": short, "elapsed": elapsed}},
            "league": {"id": 39}, "teams": {"home": {"id": 1, "name": "A"}, "away": {"id": 2, "name": "B"}},
            "goals": {"home": hs, "away": as_}, "score": {}, "events": []}


asked = []
orig_live, orig_bundle = AF.live_fixtures, AF.fixtures_bundle
AF.live_fixtures = lambda client, leagues: []                     # the match is over: it left the feed
AF.fixtures_bundle = lambda client, ids, **k: (asked.append((list(ids), k.get("force"))) or {9001: fx(9001, "FT", 90)})
try:
    out = LA.live_tick(db, client=object(), now=NOW)
finally:
    AF.live_fixtures, AF.fixtures_bundle = orig_live, orig_bundle
row = db.live_fixtures.find_one({"sid": 9001})
check("the dropped fixture was asked for, past the cache", asked == [([9001], True)])
check("it is full time now, not 90 minutes", row["status"] == "FT" and row["in_play"] is False and out["finished"] == 1)
check("the match page's mirror says FT too", db.matches.find_one({"iid": 500})["live"]["status"] == "FT")

db.live_fixtures.update_one({"sid": 9001}, {"$set": {"in_play": True, "status": "2H"}})
AF.live_fixtures = lambda client, leagues: []
AF.fixtures_bundle = lambda client, ids, **k: {9001: fx(9001, "2H", 90)}
try:
    LA.live_tick(db, client=object(), now=NOW)
finally:
    AF.live_fixtures, AF.fixtures_bundle = orig_live, orig_bundle
check("a fixture still in play (the feed was late) is left alone", db.live_fixtures.find_one({"sid": 9001})["status"] == "2H")

db.live_fixtures.update_one({"sid": 9001}, {"$set": {"kickoff": (NOW - timedelta(hours=20)).replace(tzinfo=None)}})
asked.clear()
AF.live_fixtures = lambda client, leagues: []
AF.fixtures_bundle = lambda client, ids, **k: (asked.append(ids) or {})
try:
    LA.live_tick(db, client=object(), now=NOW)
finally:
    AF.live_fixtures, AF.fixtures_bundle = orig_live, orig_bundle
check("a row stuck for twenty hours is no longer asked about", asked == [])

# ------------------------------------------------------------------ 4. every season
print("af_leagues: every season the provider carries")
import af_leagues as AFL
db = mongomock.MongoClient().db
db.leagues.insert_one({"iid": 3, "ext_id": "39", "provider": "apifootball"})
db.af_catalog.insert_one({"_id": 39, "years": list(range(2010, 2027))})
for y in (2024, 2025, 2026):
    db.seasons.insert_one({"league_iid": 3, "label": str(y), "backfilled": y == 2024})
added = AFL.ensure_seasons(db)
check("a league born with three seasons gets the other fourteen", added == 14 and db.seasons.count_documents({"league_iid": 3}) == 17)
check("an existing row keeps its flags", db.seasons.find_one({"league_iid": 3, "label": "2024"})["backfilled"] is True)
check("running it again adds nothing", AFL.ensure_seasons(db) == 0)

# ------------------------------------------------------------------ 5. pictures on their own clock
print("jobs: the picture run is not starved by the backfill")
import jobs as J
import images as IMG
db = mongomock.MongoClient().db
ran = []
J._SPAWN = lambda fn: fn()
orig_sync = IMG.run_sync
IMG.run_sync = lambda db_, max_seconds=40.0, refresh=False: (ran.append(max_seconds) or {"done": False, "stopped": "time"})
try:
    check("first run is due", J._images_due(db, NOW))
    check("it starts", J._spawn_images(db, now=NOW))
    check("it gets its own budget, not the tick's leftovers", ran == [600.0])
    check("the lock is released afterwards", db.job_locks.count_documents({"_id": "images"}) == 0)
    check("pictures still missing: due again on the next tick", J._images_due(db, NOW + timedelta(minutes=15)))
    IMG.run_sync = lambda db_, max_seconds=40.0, refresh=False: {"done": True}
    J._spawn_images(db, now=NOW + timedelta(minutes=15))
    check("all fetched: back to the schedule", not J._images_due(db, NOW + timedelta(minutes=30)))
    db.job_locks.insert_one({"_id": "images", "at": NOW, "expires_at": NOW + timedelta(minutes=10)})
    check("two runs never overlap", J._spawn_images(db, now=NOW + timedelta(minutes=1)) is False)
finally:
    IMG.run_sync = orig_sync

print("images: a mapped row is not rewritten every run")
db = mongomock.MongoClient().db
db.leagues.insert_one({"iid": 1, "ext_id": "39", "provider": "apifootball", "name": "PL"})
db.teams.insert_one({"iid": 2, "ext_id": "33", "name": "Club", "league_iid": 1})
db.players.insert_one({"iid": 3, "ext_id": "276", "name": "Player", "team_iid": 2})
IMG.identity_map(db)
stamp = {m["kind"]: m["at"] for m in db.image_map.find()}
IMG.identity_map(db)
check("second pass leaves every row as it was", {m["kind"]: m["at"] for m in db.image_map.find()} == stamp)
check("and the player row has its club", db.image_map.find_one({"kind": "player"})["team_iid"] == 2)

print(f"\n{sum(OK)}/{len(OK)} passed")
sys.exit(0 if all(OK) else 1)
