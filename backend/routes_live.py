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


@public.post("/jobs/live")
def jobs_live(x_cron_secret: str | None = Header(default=None), db=Depends(D.get_db)):
    """Call every minute from an external pinger. Spends SportAPI calls only when something is due."""
    if not hmac.compare_digest(x_cron_secret or "", os.environ.get("CRON_SHARED_SECRET", "\0")):
        raise D.err(401, "BAD_SECRET", "Bad secret.")
    return SP.live_tick(db)


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
        raise D.err(502, "PROVIDER_ERROR", str(e))


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
    return SP.live_tick(db)


@admin.get("/stats-probe/{sid}")
def sportapi_stats_probe(sid: int, user=Depends(D.require_perm("jobs.run")), db=Depends(D.get_db)):
    """One call: the raw live statistics answer and what we read from it. Use it to check the answer shape before turning on live statistics."""
    try:
        client = SP.Client(db)
        raw = client.get(f"/api/fixtures/{sid}/stats", "stats")
    except SP.NoKey as e:
        raise D.err(400, "NO_KEY", str(e))
    except SP.SportAPIError as e:
        raise D.err(502, "PROVIDER_ERROR", str(e))
    AQ.audit(db, user, "sportapi.stats_probe", str(sid), {})
    return {"raw": raw, "read": SP.parse_stats(raw, S.get(db, "sportapi.stats_keys"))}
