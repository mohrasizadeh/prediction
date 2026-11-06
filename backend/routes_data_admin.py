"""routes_data_admin.py -- Phase 1 admin data screens (docs/06 §5 table, docs/10 §3.10): endpoint explorer,
cache and usage, leagues. Every PitchAPI call goes through PitchClient.fetch. Every write needs jobs.run and is audited."""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from typing import Literal, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

import admin_queries as AQ
import deps as D
import queries as Q
import settings_store as S
from cached_fetch import BreakerOpen, BudgetExhausted, NotFound, PitchClient, PitchError, Unauthorized, _unpack

router = APIRouter(prefix="/api/admin")
perm = D.require_perm

# Calls marked Use or Optional in docs/08 §4. "Never" calls are refused.
ALLOWED = [
    (r"/v1/date/\d{4}-\d{2}-\d{2}", ("status",)),
    (r"/v1/leagues", ()),
    (r"/v1/leagues/[A-Za-z0-9_-]+", ()),
    (r"/v1/leagues/[A-Za-z0-9_-]+/matches", ("season", "status")),
    (r"/v1/teams/[A-Za-z0-9_-]+", ()),
    (r"/v1/players/[A-Za-z0-9_-]+", ()),
    (r"/v1/matches/[A-Za-z0-9_-]+", ()),
    (r"/v1/matches/[A-Za-z0-9_-]+/(players|lineups|stats|h2h|advanced|advanced/players)", ()),
]
CALLS_PER_MATCH = 3          # players + stats + lineups per finished match (docs/08 §5)
DEFAULT_SEASON_MATCHES = 380


def utcnow():
    return datetime.now(timezone.utc)


def make_client(db) -> PitchClient:
    return PitchClient(db)


def _allowed(path: str, params: dict) -> bool:
    for pattern, keys in ALLOWED:
        if re.fullmatch(pattern, path):
            return all(k in keys for k in params)
    return False


class ExplorerBody(BaseModel):
    path: str = Field(max_length=200)
    params: dict[str, str] = Field(default_factory=dict)
    force: bool = False


@router.post("/explorer")
def explorer(body: ExplorerBody, user=Depends(perm("jobs.run")), db=Depends(D.get_db)):
    params = {k: v for k, v in body.params.items() if v != ""}
    if not _allowed(body.path, params):
        raise D.err(400, "NOT_ALLOWED", "That call or parameter is not on the allow-list.")
    client = make_client(db)
    try:
        data = client.fetch(body.path, params or None, ttl=timedelta(days=1), purpose="explorer", force=body.force)
    except Unauthorized as e:
        raise D.err(400, "PITCH_KEY", "PitchAPI did not accept the key (or none is saved)." if e.code != "NO_KEY" else "No PitchAPI key is saved yet. Add it in Keys.")
    except NotFound as e:
        raise D.err(404, "PITCH_NOT_FOUND", f"PitchAPI says not found ({e.code}).")
    except BreakerOpen as e:
        raise D.err(503, "BREAKER_OPEN", f"Calls are paused: {e}.")
    except BudgetExhausted:
        raise D.err(503, "BUDGET_SPENT", "Today's call budget is spent.")
    except PitchError as e:
        raise D.err(502, "PITCH_ERROR", f"PitchAPI error {e.code} ({e.status}).")
    if body.force:
        AQ.audit(db, user, "explorer.force", body.path)
    return {"path": body.path, "params": params, "from_cache": client.calls_made == 0, "cost": client.calls_made, "data": data}


@router.get("/cache")
def cache_list(q: str = "", page: int = 1, limit: int = 50, user=Depends(perm("jobs.run")), db=Depends(D.get_db)):
    limit = max(1, min(limit, 100))
    page = max(1, page)
    flt = {"path": {"$regex": "^" + re.escape(q)}} if q else {}
    now = utcnow()
    rows = []
    for d in db.api_cache.find(flt, {"data_z": 0}).sort("fetched_at", -1).skip((page - 1) * limit).limit(limit):
        exp = d.get("expires_at")
        if exp is not None and exp.tzinfo is None:
            exp = exp.replace(tzinfo=timezone.utc)
        rows.append({"id": d["_id"], "path": d.get("path"), "params": d.get("params") or {}, "fetched_at": d.get("fetched_at"),
                     "expires_at": exp, "forever": exp is None, "expired": exp is not None and exp <= now, "error_code": d.get("error_code")})
    return {"rows": rows, "total": db.api_cache.count_documents(flt), "page": page, "limit": limit}


@router.get("/cache/{key}")
def cache_one(key: str, user=Depends(perm("jobs.run")), db=Depends(D.get_db)):
    d = db.api_cache.find_one({"_id": key})
    if not d:
        raise D.err(404, "NOT_FOUND", "No such cache row.")
    return {"id": key, "path": d.get("path"), "params": d.get("params") or {}, "error_code": d.get("error_code"),
            "data": _unpack(d["data_z"]) if "data_z" in d else None}


@router.delete("/cache")
def cache_delete(key: str = "", prefix: str = "", all: bool = False, user=Depends(perm("jobs.run")), db=Depends(D.get_db)):
    if key:
        n = db.api_cache.delete_one({"_id": key}).deleted_count
    elif prefix:
        n = db.api_cache.delete_many({"path": {"$regex": "^" + re.escape(prefix)}}).deleted_count
    elif all:
        n = db.api_cache.delete_many({}).deleted_count
    else:
        raise D.err(400, "BAD_VALUE", "Give a key, a prefix, or all=true.")
    AQ.audit(db, user, "cache.delete", key or prefix or "all", {"deleted": n})
    return {"deleted": n}


@router.get("/usage")
def usage(user=Depends(perm("jobs.run")), db=Depends(D.get_db)):
    now = utcnow()
    today = now.replace(hour=0, minute=0, second=0, microsecond=0)
    start = today - timedelta(days=13)
    by_day = {(start + timedelta(days=i)).strftime("%Y-%m-%d"): 0 for i in range(14)}
    purpose, status, codes = {}, {}, {}
    today_n = 0
    for r in db.api_call_log.find({"at": {"$gte": start}}, {"at": 1, "purpose": 1, "status": 1, "code": 1}):
        at = r["at"] if r["at"].tzinfo else r["at"].replace(tzinfo=timezone.utc)
        by_day[at.strftime("%Y-%m-%d")] = by_day.get(at.strftime("%Y-%m-%d"), 0) + 1
        if at >= today:
            today_n += 1
            p = r.get("purpose") or "other"
            purpose[p] = purpose.get(p, 0) + 1
            s = str(r.get("status"))
            status[s] = status.get(s, 0) + 1
            if r.get("code"):
                codes[r["code"]] = codes.get(r["code"], 0) + 1
    br = db.job_locks.find_one({"_id": "pitch_breaker"})
    exp = br and (br["expires_at"] if br["expires_at"].tzinfo else br["expires_at"].replace(tzinfo=timezone.utc))
    return {"calls_today": today_n, "budget": S.get(db, "ingest.daily_call_budget"),
            "by_day": [{"day": k, "count": v} for k, v in sorted(by_day.items())],
            "by_purpose": purpose, "by_status": status, "error_codes": codes,
            "breaker": {"open": bool(exp and exp > now), "reason": br.get("reason") if br else None, "until": exp if exp and exp > now else None},
            "cache_rows": db.api_cache.estimated_document_count()}


def _season_matches(db, league_iid, label):
    return db.matches.count_documents({"league_iid": league_iid, "season": label})


@router.get("/leagues")
def leagues(user=Depends(perm("jobs.run")), db=Depends(D.get_db)):
    out = []
    for lg in Q.attach_images(db, "leagues", db.leagues.find({}, {"_id": 0}).sort([("enabled", -1), ("name", 1)])):
        seasons = []
        for s in db.seasons.find({"league_iid": lg["iid"]}, {"_id": 0}).sort("label", -1):
            n = _season_matches(db, lg["iid"], s["label"])
            seasons.append({"label": s["label"], "backfilled": bool(s.get("backfilled")), "queued": bool(s.get("queued")), "matches": n})
        pending = [s for s in seasons if s["label"] in lg.get("backfill_seasons", []) and not s["backfilled"]]
        cost = sum(1 + (s["matches"] or DEFAULT_SEASON_MATCHES) * CALLS_PER_MATCH for s in pending)
        cov = list(db.data_coverage.find({"league_iid": lg["iid"]}, {"_id": 0, "league_iid": 0}))
        out.append({"iid": lg["iid"], "ext_id": lg.get("ext_id"), "name": lg.get("name"), "country_code": lg.get("country_code"),
                    "image": lg.get("image"), "enabled": bool(lg.get("enabled")),
                    "current_season": lg.get("current_season"), "backfill_seasons": lg.get("backfill_seasons", []), "zones": lg.get("zones") or [],
                    "seasons": seasons, "estimate_calls": cost, "coverage": cov})
    # Switching a league on commits a daily cost for as long as it stays on, and the screen could
    # only show the one-off backfill estimate. The list calls are exact and come straight from the
    # two sync intervals; the per-match three are stated separately rather than guessed at.
    fx_h = max(1, int(S.get(db, "ingest.fixtures_sync_hours") or 24))
    rs_h = max(1, int(S.get(db, "ingest.results_sync_hours") or 24))
    daily = max(1, round(24 / fx_h)) + max(1, round(24 / rs_h))
    return {"leagues": out, "budget": S.get(db, "ingest.daily_call_budget"),
            "daily_calls_per_league": daily, "calls_per_match": CALLS_PER_MATCH}


class Zone(BaseModel):
    start: int = Field(ge=1, le=40)
    end: int = Field(ge=1, le=40)
    label: str = Field(min_length=1, max_length=40)
    tone: Literal["top", "mid", "bottom"]


class LeagueBody(BaseModel):
    enabled: Optional[bool] = None
    backfill_seasons: Optional[list[str]] = Field(default=None, max_length=30)
    zones: Optional[list[Zone]] = Field(default=None, max_length=8)


@router.put("/leagues/{iid}")
def league_put(iid: int, body: LeagueBody, user=Depends(perm("jobs.run")), db=Depends(D.get_db)):
    lg = db.leagues.find_one({"iid": iid})
    if not lg:
        raise D.err(404, "NOT_FOUND", "No such league.")
    upd = {}
    if body.enabled is not None:
        upd["enabled"] = body.enabled
    if body.backfill_seasons is not None:
        known = {s["label"] for s in db.seasons.find({"league_iid": iid}, {"label": 1})}
        bad = [s for s in body.backfill_seasons if s not in known]
        if bad:
            raise D.err(400, "BAD_VALUE", f"Unknown season: {', '.join(bad)}.")
        upd["backfill_seasons"] = sorted(set(body.backfill_seasons), reverse=True)
        db.seasons.update_many({"league_iid": iid, "label": {"$in": upd["backfill_seasons"]}, "backfilled": False}, {"$set": {"queued": True}})
        db.seasons.update_many({"league_iid": iid, "label": {"$nin": upd["backfill_seasons"]}}, {"$set": {"queued": False}})
    if body.zones is not None:
        upd["zones"] = sorted(({**z.model_dump(), "end": max(z.start, z.end)} for z in body.zones), key=lambda z: z["start"])
    if upd:
        db.leagues.update_one({"iid": iid}, {"$set": upd})
        AQ.audit(db, user, "league.update", str(iid), upd)
    return {"ok": True, **upd}
