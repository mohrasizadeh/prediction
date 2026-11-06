"""routes_ingest_admin.py -- Phase 2 admin screens (docs/06 §5 table, docs/10 §3.10): Ingest and jobs, Data quality
(issues with Resolve, coverage matrix, mapping check against a saved answer). Reads existing collections; no new logic.
Writes need jobs.run and are audited."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from bson import ObjectId
from bson.errors import InvalidId
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

import admin_queries as AQ
import deps as D
import engine_bridge as B
import ingest as I
import normalize as N
import settings_store as S
from cached_fetch import _unpack
# The same two numbers AD-07 Leagues costs its backfill estimate with. Imported rather than copied:
# two definitions of "a season costs about this much" would drift, and then two screens would quote
# different prices for the same press.
from routes_data_admin import CALLS_PER_MATCH, DEFAULT_SEASON_MATCHES

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
            "enabled_leagues": db.leagues.count_documents({"enabled": True}),
            # The six Run-now buttons shared one dialog that said the same sentence for a 1-call
            # league-list refresh and a season backfill of a thousand or more. These are what each
            # press actually costs, so the dialog can say it (docs/redesign/v3/audit §3).
            "costs": _job_costs(db),
            "budget": {"cap": S.get(db, "ingest.daily_call_budget"), "left": _calls_left(db)}}


def _calls_left(db) -> int:
    # Same source as AD-05a's "Calls today": one row per provider call in api_call_log.
    cap = int(S.get(db, "ingest.daily_call_budget") or 0)
    midnight = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    used = db.api_call_log.count_documents({"at": {"$gte": midnight}})
    return max(0, cap - used)


def _job_costs(db) -> dict:
    """About how many provider calls one press of each Run-now button spends."""
    n_lg = db.leagues.count_documents({"enabled": True})
    backfill = 0
    for lg in db.leagues.find({"enabled": True}, {"iid": 1, "backfill_seasons": 1}):
        for label in lg.get("backfill_seasons", []):
            s = db.seasons.find_one({"league_iid": lg["iid"], "label": label})
            if s and not s.get("backfilled"):
                n = db.matches.count_documents({"league_iid": lg["iid"], "season": label}) or DEFAULT_SEASON_MATCHES
                backfill += 1 + n * CALLS_PER_MATCH
    return {"reference_sync": 1, "fixtures_sync": n_lg, "results_sync": n_lg, "backfill": backfill,
            "engine": 0, "images": None}         # the engine reads what we hold; images is unknown up front


@router.get("/ingest/extras")
def extras_status(user=Depends(perm("jobs.run")), db=Depends(D.get_db)):
    import match_extras as MX
    return MX.status(db)


@router.post("/ingest/extras/backfill")
def extras_backfill(user=Depends(perm("jobs.run")), db=Depends(D.get_db)):
    import match_extras as MX
    n = MX.backfill(db)
    db.audit_log.insert_one({"actor": user["email"], "action": "ingest.extras_backfill", "target": str(n), "at": datetime.now(timezone.utc)})
    return {"queued": n}


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


class ManyBody(BaseModel):
    ids: list[str] = Field(max_length=1000)


@router.post("/issues/resolve-many")
def issues_resolve_many(body: ManyBody, user=Depends(perm("jobs.run")), db=Depends(D.get_db)):
    oids = []
    for i in body.ids:
        try:
            oids.append(ObjectId(i))
        except InvalidId:
            continue
    r = db.ingest_issues.update_many({"_id": {"$in": oids}}, {"$set": {"resolved": True, "resolved_at": datetime.now(timezone.utc), "resolved_by": user["email"], "note": ""}})
    AQ.audit(db, user, "issue.resolve_many", str(r.modified_count))
    return {"resolved": r.modified_count}


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


def _plain(doc: dict) -> dict:
    return {k: _iso(v) for k, v in doc.items() if k != "_id"}


@router.get("/engine")
def engine_status(league_iid: int = 0, limit: int = 30, user=Depends(perm("jobs.run")), db=Depends(D.get_db)):
    q = {"league_iid": league_iid} if league_iid else {}
    runs = [_plain(r) for r in db.engine_runs.find(q).sort("started_at", -1).limit(max(1, min(limit, 200)))]
    names = {lg["iid"]: lg.get("name") for lg in db.leagues.find({}, {"iid": 1, "name": 1})}
    for r in runs:
        r["league_name"] = names.get(r.get("league_iid"))
    leagues = [{"league_iid": lg["iid"], "name": lg.get("name"), "markets": B.enabled_markets(db, lg["iid"]),
                "forecasts": db.forecasts.count_documents({"league_iid": lg["iid"], "is_current": True}),
                "hidden": db.forecasts.count_documents({"league_iid": lg["iid"], "is_current": True, "hidden": True})}
               for lg in db.leagues.find({"enabled": True}, {"iid": 1, "name": 1}).sort("name", 1)]
    return {"runs": runs, "leagues": leagues}


@router.get("/forecasts")
def forecasts(league_iid: int = 0, scope: str = "", hidden: str = "", market: str = "", page: int = 1, limit: int = 50,
              user=Depends(perm("jobs.run")), db=Depends(D.get_db)):
    q = {"is_current": True}
    if league_iid:
        q["league_iid"] = league_iid
    if scope in ("team", "player"):
        q["scope"] = scope
    if hidden in ("yes", "no"):
        q["hidden"] = True if hidden == "yes" else {"$ne": True}
    if market:
        q["market"] = {"$regex": "^" + "".join("\\" + c if not c.isalnum() else c for c in market), "$options": "i"}
    limit = max(1, min(limit, 100)); page = max(1, page)
    fields = {"_id": 0, "id": 1, "match_iid": 1, "league_iid": 1, "kickoff": 1, "scope": 1, "team_iid": 1, "player_iid": 1,
              "market": 1, "p": 1, "tier": 1, "hidden": 1, "hidden_reason": 1, "hidden_by": 1, "hidden_at": 1}
    rows = list(db.forecasts.find(q, fields).sort([("kickoff", 1), ("p", -1)]).skip((page - 1) * limit).limit(limit))
    teams = {t["iid"]: t.get("name") for t in db.teams.find({"iid": {"$in": list({r.get("team_iid") for r in rows})}}, {"iid": 1, "name": 1})}
    players = {p["iid"]: p.get("name") for p in db.players.find({"iid": {"$in": [r["player_iid"] for r in rows if r.get("player_iid")]}}, {"iid": 1, "name": 1})}
    for r in rows:
        r["team_name"] = teams.get(r.get("team_iid")); r["player_name"] = players.get(r.get("player_iid"))
    return {"rows": [_plain(r) for r in rows], "total": db.forecasts.count_documents(q), "page": page, "limit": limit}


class HideBody(BaseModel):
    hidden: bool = True
    reason: str = Field("", max_length=300)


@router.post("/forecasts/{fid}/hide")
def forecast_hide(fid: str, body: HideBody, user=Depends(perm("jobs.run")), db=Depends(D.get_db)):
    reason = body.reason.strip()
    if body.hidden and not reason:
        raise HTTPException(400, {"code": "REASON_REQUIRED", "message": "Give a reason for hiding this forecast."})
    f = db.forecasts.find_one({"id": fid}, {"fkey": 1})
    if not f:
        raise HTTPException(404, {"code": "NOT_FOUND", "message": "Forecast not found."})
    upd = ({"hidden": True, "hidden_reason": reason, "hidden_by": user["email"], "hidden_at": datetime.now(timezone.utc)}
           if body.hidden else {"hidden": False, "hidden_reason": None, "hidden_by": None, "hidden_at": None})
    db.forecasts.update_one({"id": fid}, {"$set": upd})
    AQ.audit(db, user, "forecast.hide" if body.hidden else "forecast.unhide", fid, {"reason": reason, "fkey": f.get("fkey")})
    return {"ok": True, "hidden": body.hidden}
