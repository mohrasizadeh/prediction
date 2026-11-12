"""routes_live.py -- live scores, events, lineups and results from SportAPI (docs/23).

Public routes read our database only: visitors never cause a SportAPI call. The minute job is POST /api/jobs/live
(external pinger, X-CRON-SECRET), which calls sportapi.live_tick.
"""
from __future__ import annotations

import hmac
import os
import re
from typing import Optional

from fastapi import APIRouter, Depends, Header, Query, Response
from pydantic import BaseModel, Field

import admin_queries as AQ
import deps as D
import queries as Q
import settings_store as S
import sportapi as SP

public = APIRouter(prefix="/api")
admin = APIRouter(prefix="/api/admin/sportapi")
LIVE_CACHE = "public, max-age=15, stale-while-revalidate=30"
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _date(d: str | None) -> str | None:
    if d is not None and not DATE_RE.match(d):
        raise D.err(400, "BAD_DATE", "Use YYYY-MM-DD.")
    return d


@public.get("/live")
def live(response: Response, date: str | None = None, tz: int = Query(0, ge=-840, le=840), db=Depends(D.get_db)):
    """Scoreboard for the user's local day: live first, then upcoming, then finished. Refresh every 30 s in the browser."""
    response.headers["Cache-Control"] = LIVE_CACHE
    return SP.scoreboard(db, _date(date), tz)


@public.get("/live/{sid}/events")
def live_events(sid: int, response: Response, db=Depends(D.get_db)):
    if not db.live_fixtures.find_one({"sid": sid}, {"_id": 1}):
        raise D.err(404, "NOT_FOUND", "No such match.")
    response.headers["Cache-Control"] = LIVE_CACHE
    return {"sid": sid, "events": SP.events_for(db, sid)}


@public.get("/live/{sid}/lineups")
def live_lineups(sid: int, response: Response, db=Depends(D.get_db)):
    if not db.live_fixtures.find_one({"sid": sid}, {"_id": 1}):
        raise D.err(404, "NOT_FOUND", "No such match.")
    response.headers["Cache-Control"] = LIVE_CACHE
    return {"sid": sid, "lineups": SP.lineups_for(db, sid)}


@public.get("/results")
def results(date: str, response: Response, db=Depends(D.get_db)):
    response.headers["Cache-Control"] = "public, max-age=300"
    return SP.results(db, _date(date))


# ------------------------------------------------------------------ which provider ticks
def _tick(db):
    """One live tick. API-Football, and nothing else.

    There is no provider switch here on purpose. Live scores and live events come from
    api-football.com or they do not come at all: a second feed writing `live_fixtures` would be two
    rows a match keyed differently -- SportAPI by its own `sid`, API-Football by our `ext_id` --
    and the pages would read whichever they found first.
    """
    import live_af as LA
    return LA.live_tick(db)


@public.post("/jobs/live")
def jobs_live(x_cron_secret: str | None = Header(default=None), db=Depends(D.get_db)):
    """Call every minute from an external pinger. Spends SportAPI calls only when something is due."""
    if not hmac.compare_digest(x_cron_secret or "", os.environ.get("CRON_SHARED_SECRET", "\0")):
        raise D.err(401, "BAD_SECRET", "Bad secret.")
    return _tick(db)


# ------------------------------------------------------------------ admin
@admin.get("")
def sportapi_status(user=Depends(D.require_perm("logs.read")), db=Depends(D.get_db)):
    return SP.status(db)


@admin.get("/leagues")
def sportapi_leagues(user=Depends(D.require_perm("settings.read")), db=Depends(D.get_db)):
    """SportAPI's league list for the mapping screen (1 call a week, cached)."""
    try:
        return {"leagues": SP.league_list(db)}
    except SP.NoKey as e:
        raise D.err(400, "NO_KEY", str(e))
    except SP.SportAPIError as e:
        raise D.upstream("PROVIDER_ERROR", str(e))


class TeamDecision(BaseModel):
    team_id: Optional[str] = Field(default=None, max_length=64)     # our team's public id; empty = reject


@admin.post("/teams/{sid}")
def sportapi_team(sid: int, body: TeamDecision, user=Depends(D.require_perm("jobs.run")), db=Depends(D.get_db)):
    m = db.sportapi_team_map.find_one({"sid": sid})
    if not m:
        raise D.err(404, "NOT_FOUND", "No such SportAPI team.")
    if body.team_id:
        iid = Q.iid_of(db, "teams", body.team_id)
        if not iid:
            raise D.err(404, "NOT_FOUND", "No such team.")
        db.sportapi_team_map.update_one({"sid": sid}, {"$set": {"status": "approved", "our_iid": iid}})
        for side in ("home", "away"):                                       # fixtures already stored pick up the link
            db.live_fixtures.update_many({f"{side}_sid": sid}, {"$set": {f"{side}_iid": iid}})
    else:
        db.sportapi_team_map.update_one({"sid": sid}, {"$set": {"status": "rejected", "our_iid": None}})
    AQ.audit(db, user, "sportapi.team", str(sid), {"team_id": body.team_id})
    return {"ok": True}


class Backfill(BaseModel):
    start: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    end: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")


@admin.post("/backfill")
def sportapi_backfill(body: Backfill, user=Depends(D.require_perm("jobs.run")), db=Depends(D.get_db)):
    """Historical results: one call per date, resumable, keeps the live reserve. Run again to continue."""
    try:
        out = SP.backfill(db, body.start, body.end)
    except ValueError as e:
        raise D.err(400, "TOO_MANY_DAYS", str(e))
    except SP.NoKey as e:
        raise D.err(400, "NO_KEY", str(e))
    except SP.BudgetExhausted as e:
        raise D.err(429, "BUDGET", str(e))
    AQ.audit(db, user, "sportapi.backfill", None, {"start": body.start, "end": body.end, "status": out["status"]})
    return out


@admin.post("/tick")
def sportapi_tick(user=Depends(D.require_perm("jobs.run")), db=Depends(D.get_db)):
    """Run the minute job now (same rules, same budget)."""
    return _tick(db)


# ------------------------------------------------------------------ live statistics: see it, fix it, switch it on
@admin.get("/live-stats")
def sportapi_live_stats(user=Depends(D.require_perm("settings.read")), db=Depends(D.get_db)):
    """What the live-statistics layer is doing, with no provider call: is it on, which of the four counts the last
    answers contained, which provider names we could not place, and which fixtures can be probed right now."""
    cov = SP.stats_coverage(db)
    fx = [{"sid": f["sid"], "status": f.get("status"), "minute": f.get("minute"),
           "home": f.get("home_name"), "away": f.get("away_name"), "kickoff": f.get("kickoff"),
           "live": SP.in_play(f.get("status")), "stats_at": (db.live_stats.find_one({"fixture_sid": f["sid"]}, {"at": 1}) or {}).get("at")}
          for f in db.live_fixtures.find({}, {"_id": 0, "sid": 1, "status": 1, "minute": 1, "home_name": 1, "away_name": 1, "kickoff": 1})
          .sort("kickoff", -1).limit(25)]
    return {"enabled": bool(S.get(db, "sportapi.live_stats")), "refresh_s": S.get(db, "sportapi.stats_refresh_s"),
            "events_refresh_s": S.get(db, "sportapi.events_refresh_s"),
            "stats": list(SP.BUILTIN_STAT_NAMES), "coverage": cov, "extra_names": S.get(db, "sportapi.stats_keys"),
            "fixtures": fx, "status_seen": (db.sportapi_state.find_one({"_id": "live"}) or {}).get("status_seen") or {}}


@admin.get("/stats-probe/{sid}")
def sportapi_stats_probe(sid: int, user=Depends(D.require_perm("jobs.run")), db=Depends(D.get_db)):
    """One call: the live statistics answer for a fixture, what we read from it, and the provider names we could not
    place. Use it to check a fixture before switching live statistics on, or when a count is missing."""
    try:
        client = SP.Client(db)
        raw = client.get(f"/api/fixtures/{sid}/stats", "stats")
    except SP.NoKey as e:
        raise D.err(400, "NO_KEY", str(e))
    except SP.SportAPIError as e:
        raise D.upstream("PROVIDER_ERROR", str(e))
    AQ.audit(db, user, "sportapi.stats_probe", str(sid), {})
    read = SP.parse_stats(raw, S.get(db, "sportapi.stats_keys"))
    found = sorted({k for side in read["teams"].values() for k in side} | {k for p in read["players"] for k in p if k in SP.BUILTIN_STAT_NAMES})
    return {"sid": sid, "read": read, "raw": raw,
            "found": {k: (k in found) for k in SP.BUILTIN_STAT_NAMES},
            "unmatched": read.get("unmatched") or [], "players": len(read["players"])}


class StatName(BaseModel):
    stat: str = Field(max_length=20)
    name: str = Field(min_length=1, max_length=60)


@admin.post("/stats-keys")
def sportapi_stats_keys(body: StatName, user=Depends(D.require_perm("settings.write")), db=Depends(D.get_db)):
    """Teach us one of the provider's names ('Goal Attempts' is shots). Appends to sportapi.stats_keys."""
    if body.stat not in SP.BUILTIN_STAT_NAMES:
        raise D.err(400, "BAD_STAT", f"One of {', '.join(SP.BUILTIN_STAT_NAMES)}.")
    keys = dict(S.get(db, "sportapi.stats_keys") or {})
    names = list(keys.get(body.stat) or [])
    if SP._canon(body.name) in {SP._canon(n) for n in names}:
        return {"ok": True, "stats_keys": keys, "note": "already known"}
    names.append(body.name.strip())
    keys[body.stat] = names
    S.put(db, "sportapi.stats_keys", keys, actor=user["email"])
    AQ.audit(db, user, "sportapi.stats_key_add", body.stat, {"name": body.name.strip()})
    return {"ok": True, "stats_keys": keys}
