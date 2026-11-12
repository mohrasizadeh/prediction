"""routes_data_admin.py -- Phase 1 admin data screens (docs/06 §5 table, docs/10 §3.10): endpoint explorer,
cache and usage, leagues. Every PitchAPI call goes through PitchClient.fetch. Every write needs jobs.run and is audited."""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from typing import Literal, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

import admin_queries as AQ
import af_leagues as AFL
import deps as D
import queries as Q
import security
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
# What a finished match costs to ingest. PitchAPI needed three calls per match (players, stats,
# lineups). API-Football answers twenty fixtures at a time, WITH events, lineups, statistics and
# player statistics in the same response, so the real figure is a twentieth of one call -- sixty
# times cheaper. The screen's estimate reads this, so it has to come from the provider in use and
# not from a constant that quietly means PitchAPI (docs/81).
CALLS_PER_MATCH_BY_PROVIDER = {"pitchapi": 3.0, "apifootball": 1.0 / 20}
CALLS_PER_MATCH = 3          # legacy default; use calls_per_match(db)
DEFAULT_SEASON_MATCHES = 380


def calls_per_match(db) -> float:
    return CALLS_PER_MATCH_BY_PROVIDER.get(S.get(db, "provider.source") or "pitchapi", 3.0)


def utcnow():
    return datetime.now(timezone.utc)


def make_client(db) -> PitchClient:
    return PitchClient(db)


# API-Football's own surface. The explorer had ONE allow-list -- PitchAPI's `/v1/...` paths -- and
# built a PitchClient, on a tab that lives on the API-Football screen. So the Endpoint explorer
# there sent PitchAPI requests, judged them against PitchAPI's allow-list, and reported PitchAPI
# errors. Nothing hid it; it was never looked at (docs/89 §1).
#
# Read-only endpoints only, and no write path exists on their API anyway. `?live=` is here because
# it is the one call worth watching by hand during a match.
AF_ALLOWED = [
    (r"/status", ()),
    (r"/leagues", ("id", "name", "country", "season", "current", "type", "search")),
    (r"/teams", ("id", "league", "season", "name", "country", "search")),
    (r"/teams/statistics", ("league", "season", "team", "date")),
    (r"/players", ("id", "team", "league", "season", "search", "page")),
    (r"/players/squads", ("team", "player")),
    (r"/fixtures", ("id", "ids", "live", "date", "league", "season", "team", "last", "next",
                    "from", "to", "round", "status", "timezone")),
    (r"/fixtures/events", ("fixture", "team", "player", "type")),
    (r"/fixtures/lineups", ("fixture", "team", "player", "type")),
    (r"/fixtures/statistics", ("fixture", "team", "type")),
    (r"/fixtures/players", ("fixture", "team")),
    (r"/fixtures/headtohead", ("h2h", "date", "league", "season", "last", "next")),
    (r"/standings", ("league", "season", "team")),
    (r"/injuries", ("league", "season", "fixture", "team", "player", "date")),
]


def _lists(db):
    """The allow-list of the provider actually in use."""
    return AF_ALLOWED if S.get(db, "provider.source") == "apifootball" else ALLOWED


def _allowed(path: str, params: dict, db=None) -> bool:
    for pattern, keys in (_lists(db) if db is not None else ALLOWED):
        if re.fullmatch(pattern, path):
            return all(k in keys for k in params)
    return False


def _af_explore(db, user, body, params):
    """The same screen, against API-Football. Its errors are theirs, not PitchAPI's."""
    import apifootball as AF
    client = AF.Client(db)
    try:
        data = client.fetch(body.path, params or None, ttl=timedelta(days=1),
                            purpose="explorer", force=body.force)
    except AF.Unauthorized as e:
        raise D.upstream("AF_KEY", f"API-Football did not accept the key: {e}")
    except AF.PlanLimited as e:
        raise D.upstream("AF_PLAN", f"Not on your plan: {e}")
    except AF.BudgetExhausted as e:
        raise D.upstream("BUDGET_SPENT", str(e))
    except AF.BreakerOpen as e:
        raise D.upstream("BREAKER_OPEN", f"Calls are paused: {e}")
    except AF.APIFootballError as e:
        raise D.upstream("PROVIDER", str(e))
    if body.force:
        AQ.audit(db, user, "explorer.force", body.path)
    return {"path": body.path, "params": params, "from_cache": client.calls_made == 0,
            "cost": client.calls_made, "data": data}


class ExplorerBody(BaseModel):
    path: str = Field(max_length=200)
    params: dict[str, str] = Field(default_factory=dict)
    force: bool = False


@router.post("/explorer")
def explorer(body: ExplorerBody, user=Depends(perm("jobs.run")), db=Depends(D.get_db)):
    params = {k: v for k, v in body.params.items() if v != ""}
    if not _allowed(body.path, params, db):
        raise D.err(400, "NOT_ALLOWED", "That call or parameter is not on the allow-list.")
    if S.get(db, "provider.source") == "apifootball":
        return _af_explore(db, user, body, params)
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
        raise D.upstream("PITCH_ERROR", f"PitchAPI error {e.code} ({e.status}).")
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
        cpm = calls_per_match(db)
        cost = sum(1 + (s["matches"] or DEFAULT_SEASON_MATCHES) * cpm for s in pending)
        cov = list(db.data_coverage.find({"league_iid": lg["iid"]}, {"_id": 0, "league_iid": 0}))
        out.append({"iid": lg["iid"], "ext_id": lg.get("ext_id"), "name": lg.get("name"), "country_code": lg.get("country_code"),
                    "image": lg.get("image"), "enabled": bool(lg.get("enabled")),
                    "current_season": lg.get("current_season"), "backfill_seasons": lg.get("backfill_seasons", []), "zones": lg.get("zones") or [],
                    "seasons": seasons, "estimate_calls": round(cost, 1), "coverage": cov,
                    # the competition's job, and what it is: only a forecast league fits models,
                    # publishes cards and stamps a club's league (docs/81)
                    "role": lg.get("role") or AFL.OFF, "kind": lg.get("kind"), "tier": lg.get("tier"),
                    "country": lg.get("country"),
                    # A row with no `provider` predates the move: ingest.sync_leagues never wrote
                    # the field, so every league already in the database came from PitchAPI and its
                    # `ext_id` is a PitchAPI id. Reported, not migrated -- these rows go with the
                    # purge, and writing to them to tidy a label would be a write for nothing.
                    "provider": lg.get("provider") or "pitchapi"})
    # Switching a league on commits a daily cost for as long as it stays on, and the screen could
    # only show the one-off backfill estimate. The list calls are exact and come straight from the
    # two sync intervals; the per-match three are stated separately rather than guessed at.
    fx_h = max(1, int(S.get(db, "ingest.fixtures_sync_hours") or 24))
    rs_h = max(1, int(S.get(db, "ingest.results_sync_hours") or 24))
    daily = max(1, round(24 / fx_h)) + max(1, round(24 / rs_h))
    by_provider = {}
    for r in out:
        by_provider[r["provider"]] = by_provider.get(r["provider"], 0) + 1
    return {"leagues": out, "budget": S.get(db, "ingest.daily_call_budget"),
            "daily_calls_per_league": daily, "calls_per_match": calls_per_match(db),
            "provider": S.get(db, "provider.source"),
            "by_provider": by_provider,
            "providers_on": {"apifootball": bool(security.get_provider_key(db, "apifootball", env_fallback="APIFOOTBALL_KEY")),
                             "pitchapi": bool(S.get(db, "pitchapi.enabled")),
                             "sportapi": False},   # retired; the field stays so an older screen does not crash on its absence
            "roles": {"forecast": AFL.FORECAST, "calendar": AFL.CALENDAR, "off": AFL.OFF}}


class Zone(BaseModel):
    start: int = Field(ge=1, le=40)
    end: int = Field(ge=1, le=40)
    label: str = Field(min_length=1, max_length=40)
    tone: Literal["top", "mid", "bottom"]


class LeagueBody(BaseModel):
    enabled: Optional[bool] = None
    backfill_seasons: Optional[list[str]] = Field(default=None, max_length=30)
    zones: Optional[list[Zone]] = Field(default=None, max_length=8)
    role: Optional[Literal["forecast", "calendar", "off"]] = None


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
    if body.role is not None:
        # Promoting a cup or a national-team competition to `forecast` is allowed but called out,
        # because it is the decision that pools matches of different standard into one frame and
        # lets a cup restamp a club's league (docs/81 §2). The screen warns; this records it.
        if body.role == AFL.FORECAST and (lg.get("kind") or "league") != "league":
            AQ.audit(db, user, "league.role.forced", str(iid),
                     {"kind": lg.get("kind"), "note": "forecast role on a non-division competition"})
        upd["role"] = body.role
    if upd:
        db.leagues.update_one({"iid": iid}, {"$set": upd})
        AQ.audit(db, user, "league.update", str(iid), upd)
    return {"ok": True, **upd}


# ------------------------------------------------------------------ API-Football: the catalogue
# The leagues screen is the same screen it has always been -- enable, pick seasons, see the cost.
# What changes is where its rows COME from: the catalogue in af_leagues is resolved against
# /leagues, the owner confirms each match, and confirming writes a real `leagues` row. So there is
# one list of competitions in the product, not a provider list beside ours (docs/81).
def _af_client(db):
    import apifootball as AF
    return AF.Client(db)


@router.get("/apifootball/status")
def af_status(user=Depends(perm("jobs.run")), db=Depends(D.get_db)):
    """Key test and quota, from the one call that is free and does not touch the daily budget."""
    import apifootball as AF
    try:
        st = _af_client(db).status()
    except AF.Unauthorized as e:
        return {"ok": False, "reason": "key", "detail": e.detail}
    except Exception as e:
        return {"ok": False, "reason": type(e).__name__, "detail": str(e)}
    sub, req = st.get("subscription") or {}, st.get("requests") or {}
    return {"ok": True, "plan": sub.get("plan"), "active": sub.get("active"), "ends": sub.get("end"),
            "used_today": req.get("current"), "limit_day": req.get("limit_day"),
            "quota": {k: v for k, v in (db.job_state.find_one({"_id": "apifootball_quota"}) or {}).items() if k != "_id"}}


@router.post("/apifootball/catalog/sync")
def af_catalog_sync(user=Depends(perm("jobs.run")), db=Depends(D.get_db)):
    """Fetch every competition the provider carries and store it. One call, refreshed weekly.

    Their own advice: save the league list your side rather than calling for it per view (docs/82
    §6). So the screen reads the stored copy and this is the only thing that calls out.
    """
    import apifootball as AF
    try:
        return AFL.sync_catalog(_af_client(db))
    except (AF.BudgetExhausted, AF.BreakerOpen, AF.Unauthorized, AF.PlanLimited) as e:
        raise D.err(409, "PROVIDER", str(e))
    except AF.APIFootballError as e:
        raise D.upstream("PROVIDER", str(e))


@router.get("/apifootball/catalog")
def af_catalog(q: str = "", country: str = "", kind: str = "", only: str = "",
               page: int = 1, user=Depends(perm("jobs.run")), db=Depends(D.get_db)):
    """A page of the stored catalogue, with on/off state. Reads the database, calls nothing."""
    return {**AFL.catalog_page(db, q=q, country=country, kind=kind, only=only, page=page),
            "meta": AFL.catalog_meta(db)}


class AfSwitch(BaseModel):
    league_id: int = Field(ge=1)
    on: bool
    seasons: Optional[list[int]] = Field(default=None, max_length=20)
    role: Optional[Literal["forecast", "calendar", "off"]] = None


@router.post("/apifootball/competitions")
def af_switch(body: AfSwitch, user=Depends(perm("jobs.run")), db=Depends(D.get_db)):
    """Turn a competition on or off. Creates its league row the first time, from the stored
    catalogue, so switching one on costs no provider call."""
    try:
        res = AFL.switch(db, body.league_id, body.on, body.seasons, body.role)
    except KeyError as e:
        raise D.err(404, "NOT_SYNCED", str(e))
    AQ.audit(db, user, "competition.switch", str(body.league_id),
             {"on": body.on, "role": res["role"]})
    return res


@router.get("/apifootball/types")
def af_types(league: int = 0, season: int = 0, user=Depends(perm("jobs.run")), db=Depends(D.get_db)):
    """The statistic names a REAL answer carries, diffed against our map.

    This exists because API-Football identifies a statistic by a DISPLAY STRING -- "Total Shots",
    "Ball Possession" -- and not by a stable id. A rename is therefore invisible: the column goes
    null, the market falls under `engine.coverage_min`, and the feed looks like a quiet week. So
    the map is never trusted silently; it is checked against a finished fixture and anything the
    provider sent that we do not recognise is listed by name.

    Two calls: one to find a finished fixture, one to read its statistics.
    """
    import apifootball as AF
    c = _af_client(db)
    lgs = [r for r in db.leagues.find({"provider": AFL.PROVIDER_KEY, "role": AFL.FORECAST}, {"_id": 0, "iid": 1, "ext_id": 1, "name": 1, "current_season": 1})]
    if not league:
        if not lgs:
            return {"ok": False, "reason": "no_forecast_league",
                    "detail": "Add and confirm a forecast competition first (Add competitions)."}
        league, season = int(lgs[0]["ext_id"]), season or int(lgs[0].get("current_season") or 0)
    season = season or _default_seasons(db)[0]
    try:
        fx = c.fetch("/fixtures", {"league": int(league), "season": int(season), "status": "FT", "last": 1},
                     ttl=timedelta(hours=12), purpose="types_probe")
        if not fx:
            return {"ok": False, "reason": "no_finished_fixture", "league": league, "season": season}
        fid = (fx[0].get("fixture") or {}).get("id")
        rows = c.fetch("/fixtures/statistics", {"fixture": int(fid)}, ttl=AF.FOREVER, purpose="types_probe")
    except (AF.BudgetExhausted, AF.BreakerOpen, AF.PlanLimited, AF.APIFootballError) as e:
        return {"ok": False, "reason": type(e).__name__, "detail": str(e)}
    seen = []
    for side in rows:
        for st in side.get("statistics") or []:
            if st.get("type") and st["type"] not in seen:
                seen.append(st["type"])
    mapped = {k: v for k, v in (S.get(db, "provider.apifootball.team_keys") or {}).items()}
    used = {v for v in mapped.values() if v}
    return {"ok": True, "league": league, "season": season, "fixture": fid,
            "seen": seen,
            # a name we map that the fixture did not carry: either renamed, or not tracked here
            "missing": sorted(n for n in used if n not in seen),
            # a name the fixture carried that we map to nothing: a free column, or a rename
            "unmapped": [n for n in seen if n not in used],
            "columns_unmapped": sorted(k for k, v in mapped.items() if not v),
            "map": mapped}


# ------------------------------------------------------------------ fresh start
# Clearing the football data and nothing else. The owner's instinct was to ask the host to discard
# the database; purge.py's header says why that costs a re-setup of the product to solve a problem
# that lives in about thirty known collections (docs/83).
@router.get("/purge/plan")
def purge_plan(include_mine: bool = False, user=Depends(perm("settings.write")), db=Depends(D.get_db)):
    """Every collection a purge would clear, counted, plus what it would keep. Changes nothing."""
    import purge as P
    return {**P.plan(db, include_mine), "confirm_phrase": P.CONFIRM}


class PurgeBody(BaseModel):
    confirm: str = Field(min_length=1, max_length=64)
    include_mine: bool = False


@router.post("/purge")
def purge_run(body: PurgeBody, user=Depends(perm("settings.write")), db=Depends(D.get_db)):
    """Clear it. Owner-level, typed confirmation, audited, and the counts are reported back."""
    import purge as P
    try:
        res = P.run(db, body.confirm, body.include_mine, actor=user.get("email", ""))
    except ValueError as e:
        raise D.err(400, "CONFIRM_REQUIRED", str(e))
    AQ.audit(db, user, "data.purge", "football",
             {"documents": res["documents"], "include_mine": body.include_mine})
    return res


@router.get("/apifootball/usage")
def af_usage(user=Depends(perm("jobs.run")), db=Depends(D.get_db)):
    """Calls, cache and breaker for THIS provider.

    The existing /usage counts every row in `api_call_log` and reads PitchAPI's breaker, which was
    right while one provider wrote that log. API-Football tags its rows with `provider`, so this
    answers the same questions about it alone -- and says how many untagged rows are in there, which
    is PitchAPI's history and will stop growing once the ingest moves.
    """
    import apifootball as AF
    now = utcnow()
    today = now.replace(hour=0, minute=0, second=0, microsecond=0)
    start = today - timedelta(days=13)
    by_day = {(start + timedelta(days=i)).strftime("%Y-%m-%d"): 0 for i in range(14)}
    purpose, status, codes, ms = {}, {}, {}, []
    today_n = 0
    for r in db.api_call_log.find({"at": {"$gte": start}, "provider": AF.PROVIDER},
                                  {"at": 1, "purpose": 1, "status": 1, "code": 1, "ms": 1}):
        at = r["at"] if r["at"].tzinfo else r["at"].replace(tzinfo=timezone.utc)
        key = at.strftime("%Y-%m-%d")
        by_day[key] = by_day.get(key, 0) + 1
        if at >= today:
            today_n += 1
            purpose[r.get("purpose") or "other"] = purpose.get(r.get("purpose") or "other", 0) + 1
            status[str(r.get("status"))] = status.get(str(r.get("status")), 0) + 1
            if r.get("code"):
                codes[r["code"]] = codes.get(r["code"], 0) + 1
            if r.get("ms"):
                ms.append(int(r["ms"]))
    br = db.job_locks.find_one({"_id": "af_breaker"})
    exp = br and (br["expires_at"] if br["expires_at"].tzinfo else br["expires_at"].replace(tzinfo=timezone.utc))
    q = {k: v for k, v in (db.job_state.find_one({"_id": "apifootball_quota"}) or {}).items() if k != "_id"}
    client = _af_client(db)
    return {
        "calls_today": today_n, "by_day": by_day, "by_purpose": purpose, "by_status": status,
        "error_codes": codes,
        "ms": {"n": len(ms), "median": sorted(ms)[len(ms) // 2] if ms else None, "max": max(ms) if ms else None},
        "quota": q,
        "budget": {"today": client.day_budget(),
                   "reserve": int(S.get(db, "apifootball.daily_reserve")),
                   "per_minute": q.get("min_limit"),
                   "per_second": client.per_second_limit()},
        "breaker": {"open": bool(exp and exp > now), "reason": (br or {}).get("reason"), "until": exp},
        "cache": {"rows": db.api_cache.count_documents({}),
                  "forever": db.api_cache.count_documents({"expires_at": {"$exists": False}}),
                  "expired": db.api_cache.count_documents({"expires_at": {"$lt": now.replace(tzinfo=None)}})},
        "other_provider_rows": db.api_call_log.count_documents({"provider": {"$exists": False}}),
        "paused_reason": S.get(db, "ingest.paused_reason") or None,
    }
