"""Engine admin: runs list, forecast browser, hide/unhide with reason (audited), Hide kept across runs; lineup positions."""
import sys, os
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE if os.path.basename(HERE) == "tests" else "/app/backend/tests")
sys.path.insert(0, HERE)
from testkit import *
import routes_ingest_admin as RIA
import normalize as N
import queries as Q
from datetime import datetime, timezone
import importlib, importlib.util
if not hasattr(N, "lineup_pos"):          # running from /app/proposals/engine before it is applied
    _s = importlib.util.spec_from_file_location("normalize_proposed", os.path.join(os.path.dirname(os.path.abspath(__file__)), "normalize.py"))
    N = importlib.util.module_from_spec(_s); _s.loader.exec_module(N)

if not any(getattr(r, "path", "") == "/api/admin/engine" for r in srv.app.routes):
    srv.app.include_router(getattr(RIA, "router") if hasattr(RIA, "forecast_hide") else __import__("routes_engine_admin").router)

pm = {"0": "GK", "1": "DEF", "2": "MID", "3": "FWD"}
check([N.lineup_pos({"started": True, "pitch_x": x, "position_id": 99}, pm) for x in (0.1, 0.3, 0.4, 0.5, 0.7, 0.9)]
      == ["GK", "DEF", "DEF", "MID", "MID", "FWD"], "starters: line from depth on the pitch")
check(N.lineup_pos({"started": False, "pitch_x": 0, "position_id": 2}, pm) == "MID" and N.lineup_pos({"started": False, "position_id": None}, pm) is None,
      "subs: position_map, unknown stays None")
lu = {"home": {"starters": [{"player_id": "g", "position_id": 11, "pitch_x": 0.1}], "subs": [{"player_id": "s", "position_id": 3, "pitch_x": 0}]}, "away": {}}
stat = lambda k, v: {k: {"key": k, "stat": {"type": "integer", "value": v}}}
pl = [{"player": {"id": i}, "team_id": "h", "stats": [{"key": "top_stats", "stats": {**stat("minutes_played", 90), **stat("total_shots", 1)}},
                                                     {"key": "defense", "stats": stat("tackles_won", 2)}]} for i in ("g", "s")]
keys = {"minutes": {"group": "top_stats", "key": "minutes_played"}, "shots": {"group": "top_stats", "key": "total_shots"},
        "tackles": {"group": "defense", "key": "tackles_won"}}
st = {"periods": [{"period": "ALL", "groups": [{"group_name": "g", "items": [{"key": "total_shots", "home": "5", "away": "4"}]}]}]}
out = N.normalize_match({"home_ext": "h", "away_ext": "a"}, st, pl, lu, {"team_keys": {"shots": "total_shots"}, "player_keys": keys, "position_map": pm})
by = {p["ext_id"]: p for p in out["players"]}
check(by["g"]["pos"] == "GK" and by["g"]["tackles"] is None and by["s"]["pos"] == "FWD" and by["s"]["tackles"] == 2,
      "match rows get the lineup position; goalkeeper tackles None")

with TestClient(srv.app) as owner:
    admin, support, analyst = boot(owner)
    anon = TestClient(srv.app)
    check(anon.get("/api/admin/engine").status_code in (401, 403) and support.get("/api/admin/forecasts").status_code == 403, "engine screens need jobs.run")
    now = datetime.now(timezone.utc)
    db.leagues.insert_one({"iid": 7, "ext_id": "L7", "name": "Test League", "enabled": True})
    db.teams.insert_one({"iid": 70, "name": "Club A"})
    db.engine_runs.insert_many([{"run_id": "r1", "league_iid": 7, "started_at": now, "status": "done", "forecasts": 2},
                                {"run_id": "r0", "league_iid": 7, "started_at": now.replace(year=2020), "status": "skipped", "note": "no data"}])
    db.forecasts.insert_many([{"id": "f1", "fkey": "1:team:70:0:shots:9.5", "match_iid": 1, "league_iid": 7, "kickoff": now, "scope": "team",
                               "team_iid": 70, "player_iid": None, "market": "10+ shots", "p": 0.6, "tier": "Solid", "is_current": True, "hidden": False},
                              {"id": "f2", "fkey": "1:team:70:0:corners:4.5", "match_iid": 1, "league_iid": 7, "kickoff": now, "scope": "team",
                               "team_iid": 70, "player_iid": None, "market": "5+ corners", "p": 0.4, "tier": None, "is_current": True, "hidden": False}])
    e = admin.get("/api/admin/engine").json()
    check([r["run_id"] for r in e["runs"]] == ["r1", "r0"] and e["runs"][0]["league_name"] == "Test League", "runs newest first with league name")
    check(e["leagues"][0]["forecasts"] == 2 and "team.shots" in e["leagues"][0]["markets"], "markets and counts per switched-on league")
    f = admin.get("/api/admin/forecasts", params={"league_iid": 7}).json()
    check(f["total"] == 2 and f["rows"][0]["team_name"] == "Club A", "forecast browser lists current forecasts")
    check(admin.post("/api/admin/forecasts/f1/hide", json={"hidden": True, "reason": " "}).status_code == 400, "hiding needs a reason")
    check(admin.post("/api/admin/forecasts/nope/hide", json={"hidden": True, "reason": "x"}).status_code == 404, "unknown forecast is 404")
    r = admin.post("/api/admin/forecasts/f1/hide", json={"hidden": True, "reason": "bad data"})
    check(r.status_code == 200 and db.forecasts.find_one({"id": "f1"})["hidden_reason"] == "bad data", "hide stores the reason")
    check(db.audit_log.find_one({"action": "forecast.hide", "target": "f1"}) is not None, "hide is audited")
    check(db.forecasts.count_documents({**Q.NOT_HIDDEN, "match_iid": 1}) == 1, "public reads skip the hidden forecast")
    check(admin.get("/api/admin/forecasts", params={"hidden": "yes"}).json()["total"] == 1, "filter by hidden")
    admin.post("/api/admin/forecasts/f1/hide", json={"hidden": False})
    check(db.forecasts.find_one({"id": "f1"})["hidden"] is False and db.audit_log.find_one({"action": "forecast.unhide"}), "unhide works and is audited")

print("engine admin self-test passed")
