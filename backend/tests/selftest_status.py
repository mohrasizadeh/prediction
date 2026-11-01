"""Stale-data banner (docs/03 section 4.7, docs/36 H10): /api/public/status says when the provider data is older than
ingest.stale_limit_hours, and finds the engine's per-league runs ("engine:<league>")."""
from testkit import *
from datetime import datetime, timedelta, timezone

UTC = timezone.utc
now = datetime.now(UTC)


def status():
    return TestClient(srv.app).get("/api/public/status").json()


with TestClient(srv.app) as owner:
    s = status()
    check(s["stale"] is False and s["data_updated_at"] is None, "no syncs yet: no banner (nothing to call stale)")

    limit = S.get(db, "ingest.stale_limit_hours")
    db.job_runs.insert_many([
        {"job": "results_sync", "status": "ok", "started_at": now - timedelta(hours=limit + 8), "finished_at": now - timedelta(hours=limit + 8)},
        {"job": "fixtures_sync", "status": "ok", "started_at": now - timedelta(hours=limit + 6), "finished_at": now - timedelta(hours=limit + 6)},
        {"job": "engine:3", "status": "ok", "started_at": now - timedelta(minutes=5), "finished_at": now - timedelta(minutes=4)},
    ])
    s = status()
    check(s["last_ok"]["engine"] is not None, "the engine's per-league runs ('engine:3') are found")
    check(s["stale"] is True and s["stale_hours"] == round(limit + 6), f"provider data older than {limit} h: stale, with its age")
    check(s["stale_limit_hours"] == limit, "...and the limit it was judged against")

    db.job_runs.insert_one({"job": "fixtures_sync", "status": "ok", "started_at": now - timedelta(hours=1), "finished_at": now - timedelta(hours=1)})
    check(status()["stale"] is False, "a fresh provider pull clears the banner")

    db.job_runs.delete_many({"job": {"$in": ["fixtures_sync", "results_sync"]}})
    db.job_runs.insert_one({"job": "fixtures_sync", "status": "error", "started_at": now - timedelta(minutes=10)})
    db.job_runs.insert_one({"job": "fixtures_sync", "status": "ok", "started_at": now - timedelta(hours=limit + 2), "finished_at": now - timedelta(hours=limit + 2)})
    check(status()["stale"] is True, "failed pulls do not count as fresh; the engine re-running on old data does not either")

print("\nALL STATUS CHECKS PASSED")
