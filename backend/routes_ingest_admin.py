"""routes_ingest_admin.py -- Phase 2 admin screens (docs/06 §5 table, docs/10 §3.10): Ingest and jobs, Data quality
(issues with Resolve, coverage matrix, mapping check against a saved answer). Reads existing collections; no new logic.
Writes need jobs.run and are audited."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from bson import ObjectId
from bson.errors import InvalidId
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

import admin_queries as AQ
import deps as D
import ingest as I
import normalize as N
import settings_store as S
from cached_fetch import _unpack

router = APIRouter(prefix="/api/admin")
perm = D.require_perm


def _iso(d):
    if isinstance(d, datetime):
        return (d if d.tzinfo else d.replace(tzinfo=timezone.utc)).isoformat()
    return d


def _clean(doc: dict) -> dict:
    out = {k: _iso(v) for k, v in doc.items() if k != "_id"}
    out["id"] = str(doc["_id"])
    return out


@router.get("/jobs")
def jobs_status(user=Depends(perm("jobs.run")), db=Depends(D.get_db)):
    last = {}
    for r in db.job_runs.aggregate([{"$sort": {"started_at": -1}}, {"$group": {"_id": "$job", "row": {"$first": "$$ROOT"}}}]):
        row = r["row"]
        last[r["_id"]] = {"status": row.get("status"), "started_at": _iso(row.get("started_at")), "finished_at": _iso(row.get("finished_at")),
                          "result": row.get("result"), "error": row.get("error")}
    queue = {}
    for r in db.ingest_queue.aggregate([{"$group": {"_id": {"task": "$task", "status": "$status"}, "n": {"$sum": 1}}}]):
        queue.setdefault(r["_id"]["task"], {})[r["_id"]["status"] or "pending"] = r["n"]
    lock = db.job_locks.find_one({"_id": "tick"})
    pending = [_clean(r) for r in db.job_requests.find({"status": {"$in": ["pending", "taken"]}}).sort("requested_at", -1).limit(20)]
    recent = [_clean(r) for r in db.job_runs.find({}, {"result": 0}).sort("started_at", -1).limit(30)]
    return {"last": last, "queue": queue, "tick": {"running": bool(lock), "since": _iso(lock["at"]) if lock else None},
            "requests": pending, "recent": recent, "paused_reason": S.get(db, "ingest.paused_reason"),
            "seasons_queued": db.seasons.count_documents({"backfilled": False, "queued": True}),
            "enabled_leagues": db.leagues.count_documents({"enabled": True})}


@router.get("/issues")
def issues(resolved: bool = False, kind: str = "", page: int = 1, limit: int = 50, user=Depends(perm("jobs.run")), db=Depends(D.get_db)):
    page, limit = max(1, page), max(1, min(limit, 100))
    flt: dict[str, Any] = {"resolved": True} if resolved else {"resolved": {"$ne": True}}
    if kind:
        flt["kind"] = kind
    rows = [_clean(r) for r in db.ingest_issues.find(flt).sort("at", -1).skip((page - 1) * limit).limit(limit)]
    kinds = sorted(k for k in db.ingest_issues.distinct("kind") if k)
    return {"rows": rows, "total": db.ingest_issues.count_documents(flt), "page": page, "limit": limit, "kinds": kinds}


class ResolveBody(BaseModel):
    note: str = Field(default="", max_length=300)


@router.post("/issues/{iid}/resolve")
def issue_resolve(iid: str, body: ResolveBody, user=Depends(perm("jobs.run")), db=Depends(D.get_db)):
    try:
        oid = ObjectId(iid)
    except InvalidId:
        raise D.err(404, "NOT_FOUND", "No such issue.")
    r = db.ingest_issues.update_one({"_id": oid}, {"$set": {"resolved": True, "resolved_at": datetime.now(timezone.utc), "resolved_by": user["email"], "note": body.note}})
    if not r.matched_count:
        raise D.err(404, "NOT_FOUND", "No such issue.")
    AQ.audit(db, user, "issue.resolve", iid, {"note": body.note})
    return {"ok": True}


@router.get("/coverage")
def coverage(user=Depends(perm("jobs.run")), db=Depends(D.get_db)):
    leagues = {lg["iid"]: lg.get("name") for lg in db.leagues.find({"enabled": True}, {"iid": 1, "name": 1})}
    fields = [f"{c}.{f}" for c, fs in I.COVERAGE_FIELDS.items() for f in fs]
    cells = {}
    for r in db.data_coverage.find({"league_iid": {"$in": list(leagues)}}):
        cells.setdefault(str(r["league_iid"]), {})[r["field"]] = {"share": r.get("share"), "rows": r.get("rows")}
    return {"fields": fields, "min_share": S.get(db, "engine.coverage_min"),
            "leagues": [{"iid": i, "name": n, "cells": cells.get(str(i), {})} for i, n in sorted(leagues.items(), key=lambda x: x[1] or "")]}


class MappingCheck(BaseModel):
    kind: str = Field(pattern="^(stats|players)$")
    cache_key: Optional[str] = Field(default=None, max_length=100)
    data: Optional[Any] = None


@router.post("/mapping/check")
def mapping_check(body: MappingCheck, user=Depends(perm("jobs.run")), db=Depends(D.get_db)):
    data = body.data
    if body.cache_key:
        row = db.api_cache.find_one({"_id": body.cache_key})
        if not row or "data_z" not in row:
            raise D.err(404, "NOT_FOUND", "No saved answer with that key.")
        data = _unpack(row["data_z"])
    if data is None:
        raise D.err(400, "BAD_VALUE", "Give a cache key or paste a saved answer.")
    if isinstance(data, dict) and "data" in data and body.cache_key is None:
        data = data["data"]                      # a file saved by the Explorer: {path, params, data}
    if body.kind == "stats":
        if not isinstance(data, dict):
            raise D.err(400, "BAD_VALUE", "Team stats must be an object with periods.")
        items = N.team_items(data)
        keys = S.get(db, "provider.pitchapi.team_keys")
        mapped = N.team_stats(data, keys)
        return {"kind": "stats", "mapped": mapped, "keys": keys,
                "missing": [c for c in N.TEAM_COLS if mapped["home"][c] is None and mapped["away"][c] is None],
                "available": [{"key": k, "title": v["title"], "group": v["group"], "home": v["home"], "away": v["away"]} for k, v in items.items()]}
    plist = data.get("players") if isinstance(data, dict) else data
    if not isinstance(plist, list):
        raise D.err(400, "BAD_VALUE", "Player stats must be a list of players.")
    keys, pos = S.get(db, "provider.pitchapi.player_keys"), S.get(db, "provider.position_map")
    rows = N.players(plist[:60], keys, pos)
    avail = {}
    for p in plist[:60]:
        for g in p.get("stats", []) or []:
            for e in (g.get("stats") or {}).values():
                if e.get("key"):
                    avail.setdefault(f"{g.get('key')}.{e['key']}", {"group": g.get("key"), "key": e["key"], "title": e.get("title") or e.get("name")})
    return {"kind": "players", "mapped": rows[:30], "keys": keys, "position_map": pos,
            "missing": [c for c in N.PLAYER_COLS if all(r.get(c) is None for r in rows)],
            "unmapped_positions": sorted({str(r["pos_raw"]) for r in rows if r["pos"] is None and r["pos_raw"] is not None}),
            "available": sorted(avail.values(), key=lambda x: (x["group"] or "", x["key"]))}
