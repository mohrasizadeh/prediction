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
# ------------------------------------------------------------------ the SportAPI admin surface, removed
#
# Eight endpoints lived here: the status root, /leagues, /teams/{sid} (the name-matching review
# queue), /backfill, /live-stats, /stats-probe/{sid} and /stats-keys. The screen that called them
# was deleted with the provider, and I reported that as done -- but a route is not gone because no
# menu entry points at it. They stayed mounted, took a session, and /stats-probe built an
# SP.Client(db) and SPENT A CALL on a provider nothing else uses. "Unreachable from the menu" is not
# "removed"; a route that can spend money is reachable (docs/89 section 3).
#
# /tick survives because it goes through `_tick`, which is API-Football, and running the minute job
# by hand is still worth a button.


@admin.post("/tick")
def sportapi_tick(user=Depends(D.require_perm("jobs.run")), db=Depends(D.get_db)):
    """Run the minute job now (same rules, same budget)."""
    return _tick(db)


# ------------------------------------------------------------------ live statistics: see it, fix it, switch it on
