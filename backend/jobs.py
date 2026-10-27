"""jobs.py -- one entry point, `tick()`, called every 5 to 10 minutes.

Emergent's scheduled-job support is not documented, so we do not depend on it.
Two ways to call tick():
  1. POST /api/jobs/tick with header X-CRON-SECRET (an external pinger: cron-job.org is free).
  2. A background thread started at app startup (see 07_ingest_and_caching.md, section 6).
A lock makes overlapping calls harmless. tick() stops by itself after `max_seconds`.
Everything it does is resumable.
"""
from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone

from pymongo.errors import DuplicateKeyError

import engine_bridge as B
import ingest as I
import settings_store as S
from cached_fetch import BreakerOpen, BudgetExhausted, PitchClient, Unauthorized, utcnow

LOCK_MINUTES = 5
MANUAL = {"reference_sync", "fixtures_sync", "results_sync", "backfill", "engine", "alerts", "digest", "images"}


def _lock(db, now) -> bool:
    db.job_locks.delete_many({"_id": "tick", "expires_at": {"$lt": now}})
    try:
        db.job_locks.insert_one({"_id": "tick", "at": now, "expires_at": now + timedelta(minutes=LOCK_MINUTES)})
        return True
    except DuplicateKeyError:
        return False


def _last(db, job):
    return db.job_runs.find_one({"job": job, "status": "ok"}, sort=[("started_at", -1)])


def _due_every(db, job, delta: timedelta, now) -> bool:
    last = _last(db, job)
    return last is None or (now - last["started_at"].replace(tzinfo=timezone.utc)) >= delta


def _run(db, job, fn, now):
    row = {"job": job, "started_at": now, "status": "running"}
    rid = db.job_runs.insert_one(row).inserted_id
    try:
        result = fn()
        db.job_runs.update_one({"_id": rid}, {"$set": {"status": "ok", "finished_at": utcnow(), "result": result}})
        return result
    except (BudgetExhausted, BreakerOpen, Unauthorized) as e:
        db.job_runs.update_one({"_id": rid}, {"$set": {"status": "stopped", "finished_at": utcnow(), "result": type(e).__name__}})
        return None
    except Exception as e:                       # a bug must not kill the tick
        db.job_runs.update_one({"_id": rid}, {"$set": {"status": "error", "finished_at": utcnow(), "error": repr(e)[:500]}})
        db.ingest_issues.insert_one({"at": utcnow(), "kind": "job_error", "detail": f"{job}: {e!r}"[:500], "resolved": False})
        return None


def tick(db, client: PitchClient | None = None, max_seconds: float = 50.0, now: datetime | None = None) -> dict:
    now = now or utcnow()
    t0 = time.monotonic()
    out = {"ran": [], "skipped": None}
    if not _lock(db, now):
        out["skipped"] = "another tick is running"; return out
    try:
        client = client or PitchClient(db)
        pend = list(db.job_requests.find({"status": "pending"}))
        forced = {r["job"] for r in pend}
        img_refresh = any(r.get("refresh") for r in pend if r["job"] == "images")
        db.job_requests.update_many({"status": "pending"}, {"$set": {"status": "taken", "taken_at": now}})
        leagues = list(db.leagues.find({"enabled": True}))
        left = lambda: time.monotonic() - t0 < max_seconds

        if "reference_sync" in forced or _due_every(db, "reference_sync", timedelta(days=S.get(db, "ingest.reference_sync_days")), now):
            if _run(db, "reference_sync", lambda: I.sync_leagues(client), now) is not None: out["ran"].append("reference_sync")

        if "fixtures_sync" in forced or _due_every(db, "fixtures_sync", timedelta(hours=S.get(db, "ingest.fixtures_sync_hours")), now):
            def fx():
                for lg in leagues:
                    I.sync_league_matches(client, lg, lg.get("current_season"), "upcoming"); I.assign_rounds(db, lg["iid"])
                return len(leagues)
            if leagues and _run(db, "fixtures_sync", fx, now) is not None: out["ran"].append("fixtures_sync")

        if "results_sync" in forced or _due_every(db, "results_sync", timedelta(hours=S.get(db, "ingest.results_sync_hours")), now):
            def rs():
                before = db.ingest_queue.count_documents({"task": "match_ingest"})
                for lg in leagues:        # force=True: one list call per league, always fresh, so new results are seen
                    I.sync_league_matches(client, lg, lg.get("current_season"), "all", force=True); I.assign_rounds(db, lg["iid"])
                return {"leagues": len(leagues), "new_matches_queued": db.ingest_queue.count_documents({"task": "match_ingest"}) - before}
            if leagues and _run(db, "results_sync", rs, now) is not None: out["ran"].append("results_sync")

        if "backfill" in forced or db.seasons.count_documents({"backfilled": False, "queued": True}):
            def bf():
                n = 0
                for lg in leagues:
                    for label in lg.get("backfill_seasons", []):
                        s = db.seasons.find_one({"league_iid": lg["iid"], "label": label})
                        if s and not s.get("backfilled"):
                            I.sync_league_matches(client, lg, label, "all"); I.assign_rounds(db, lg["iid"])
                            db.seasons.update_one({"_id": s["_id"]}, {"$set": {"backfilled": True}}); n += 1
                return n
            if leagues and _run(db, "backfill", bf, now): out["ran"].append("backfill")

        if left() and S.get(db, "ingest.lineups_watch_enabled"):
            if _run(db, "lineup_watch", lambda: I.lineup_watch(client, now), now) is not None: out["ran"].append("lineup_watch")

        if left() and S.get(db, "ingest.match_extra_detail"):
            import cards_model as CM
            _run(db, "referee_watch", lambda: CM.plan_referees(db, now), now)
        if left():
            res = _run(db, "queue", lambda: I.process_queue(client, max_tasks=200), now)
            if res and (res["done"] or res["skipped"]): out["ran"].append("queue")

        for lg in leagues:
            if not left(): break
            last = db.engine_runs.find_one({"league_iid": lg["iid"], "status": {"$in": ["done", "skipped"]}}, sort=[("started_at", -1)])
            since = last["started_at"] if last else datetime(1970, 1, 1)
            dirty = (last is None
                     or db.matches.count_documents({"league_iid": lg["iid"], "ingested_at": {"$gt": since}}) > 0
                     or db.matches.count_documents({"league_iid": lg["iid"], "lineups_at": {"$gt": since}}) > 0)
            I.update_coverage(db, lg["iid"])
            if "engine" in forced or dirty:
                if _run(db, f"engine:{lg['iid']}", lambda: B.run_league(db, lg["iid"], now), now) is not None: out["ran"].append(f"engine:{lg['iid']}")
        if left():
            if _run(db, "score", lambda: B.score_finished(db), now) is not None: out["ran"].append("score")
        if left():                                                       # copy list members out, deliver webhooks (both retry on their own)
            import integrations as INT
            res = _run(db, "integrations", lambda: {**INT.process_audience(db, now=now), **INT.deliver_pending(db, now=now)}, now)
            if res and any(res.values()): out["ran"].append("integrations")
        if left() and "images" in forced:
            import images as IMG
            if _run(db, "images", lambda: IMG.run_sync(db, max_seconds=max(5.0, min(40.0, max_seconds - (time.monotonic() - t0))), refresh=img_refresh), now) is not None: out["ran"].append("images")
        if left() and ("alerts" in forced or _due_every(db, "alerts", timedelta(minutes=15), now)):
            import alerts as AL
            if _run(db, "alerts", lambda: AL.run(db, now), now) is not None: out["ran"].append("alerts")
        if left() and ("digest" in forced or (now.weekday() == 0 and now.hour >= 12 and _due_every(db, "digest", timedelta(days=6), now))):
            import alerts as AL
            if _run(db, "digest", lambda: AL.send_digest(db, now), now) is not None: out["ran"].append("digest")
        if left() and _due_every(db, "cleanup", timedelta(hours=24), now):
            if _run(db, "cleanup", lambda: B.cleanup(db, now), now) is not None: out["ran"].append("cleanup")
        db.job_requests.update_many({"status": "taken"}, {"$set": {"status": "done"}})
    finally:
        db.job_locks.delete_one({"_id": "tick"})
    out["seconds"] = round(time.monotonic() - t0, 1)
    return out
