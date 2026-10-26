"""Phase 2 admin data screens over HTTP: jobs status, issues + resolve, coverage matrix, mapping check."""
import sys, os
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE if os.path.basename(HERE) == "tests" else "/app/backend/tests")
sys.path.insert(0, HERE)
from testkit import *
import routes_ingest_admin as RIA
from cached_fetch import _pack
from datetime import datetime, timezone

if not any(getattr(r, "path", "") == "/api/admin/jobs" for r in srv.app.routes):
    srv.app.include_router(RIA.router)       # until server.py mounts it

with TestClient(srv.app) as owner:
    admin, support, analyst = boot(owner)
    anon = TestClient(srv.app)
    check(anon.get("/api/admin/jobs").status_code in (401, 403), "signed-out visitors cannot see jobs")
    check(support.get("/api/admin/issues").status_code == 403 and analyst.get("/api/admin/coverage").status_code == 403, "support and analyst have no data tools")

    now = datetime.now(timezone.utc)
    db.job_runs.insert_many([{"job": "reference_sync", "started_at": now, "status": "ok", "finished_at": now, "result": 77},
                             {"job": "queue", "started_at": now, "status": "error", "error": "boom"}])
    db.ingest_queue.insert_many([{"task": "match_ingest", "key": "1", "status": "pending"}, {"task": "match_ingest", "key": "2", "status": "done"}])
    admin.post("/api/admin/jobs/run", params={"job": "backfill"})
    j = admin.get("/api/admin/jobs").json()
    check(j["last"]["reference_sync"]["status"] == "ok" and j["last"]["queue"]["error"] == "boom", "last run per job with errors")
    check(j["queue"]["match_ingest"] == {"pending": 1, "done": 1} and j["tick"]["running"] is False, "queue counts and tick state")
    check(len(j["requests"]) == 1 and j["requests"][0]["job"] == "backfill" and isinstance(j["requests"][0]["id"], str), "pending manual requests listed")

    db.ingest_issues.insert_many([{"at": now, "kind": "unknown_key", "detail": "x", "resolved": False},
                                  {"at": now, "kind": "job_error", "detail": "y", "resolved": False}])
    i = admin.get("/api/admin/issues").json()
    check(i["total"] == 2 and i["kinds"] == ["job_error", "unknown_key"], "open issues and kinds")
    check(admin.get("/api/admin/issues", params={"kind": "job_error"}).json()["total"] == 1, "filter by kind")
    iid = i["rows"][0]["id"]
    check(admin.post(f"/api/admin/issues/{iid}/resolve", json={"note": "fixed mapping"}).status_code == 200, "resolve an issue")
    check(admin.get("/api/admin/issues").json()["total"] == 1 and admin.get("/api/admin/issues", params={"resolved": "true"}).json()["rows"][0]["note"] == "fixed mapping", "resolved list keeps the note")
    check(admin.post("/api/admin/issues/nope/resolve", json={}).status_code == 404, "bad id is 404")
    check(db.audit_log.find_one({"action": "issue.resolve"}) is not None, "resolve is audited")

    db.leagues.insert_one({"iid": 9, "ext_id": "L9", "name": "Test League", "enabled": True})
    db.data_coverage.insert_one({"league_iid": 9, "field": "team_match_stats.shots", "share": 0.9, "rows": 10})
    c = admin.get("/api/admin/coverage").json()
    check("team_match_stats.shots" in c["fields"] and c["leagues"][0]["cells"]["team_match_stats.shots"]["share"] == 0.9 and c["min_share"] is not None, "coverage matrix")

    stats = {"periods": [{"period": "ALL", "groups": [{"group_name": "Shots", "items": [{"key": "total_shots", "title": "Total shots", "home": "12", "away": "7"}]}]}]}
    db.api_cache.insert_one({"_id": "k1", "path": "/v1/matches/1/stats", "data_z": _pack(stats)})
    m = admin.post("/api/admin/mapping/check", json={"kind": "stats", "cache_key": "k1"}).json()
    check(m["available"][0]["key"] == "total_shots" and "home" in m["mapped"], "stats check lists the provider's keys")
    players = [{"team_id": "T1", "player": {"id": "P1", "name": "A", "position_id": 7}, "stats": [{"key": "attack", "stats": {"a": {"key": "shots_total", "stat": {"value": 3}}}}]}]
    m = admin.post("/api/admin/mapping/check", json={"kind": "players", "data": {"path": "/v1/matches/1/players", "data": players}}).json()
    check(m["available"][0]["key"] == "shots_total" and m["unmapped_positions"] == ["7"], "players check from an Explorer file shows keys and unmapped positions")
    check(admin.post("/api/admin/mapping/check", json={"kind": "stats"}).status_code == 400, "needs a key or data")
    check(admin.post("/api/admin/mapping/check", json={"kind": "stats", "cache_key": "zzz"}).status_code == 404, "unknown cache key is 404")
print("ingest admin self-test passed")
