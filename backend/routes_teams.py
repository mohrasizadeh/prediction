"""routes_teams.py -- public team views (update pack part A). Mounted before routes_data so /teams/compare wins."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Response

import deps as D
import queries as Q
import team_insights as TI

router = APIRouter(prefix="/api")
CACHE = "public, max-age=60, stale-while-revalidate=300"


@router.get("/leagues/{league_id}/team-matrix")
def team_matrix(league_id: str, response: Response, window: str = Query("season", pattern="^(season|last10|last5)$"),
                venue: str = Query("all", pattern="^(all|home|away)$"), db=Depends(D.get_db)):
    lid = Q.iid_of(db, "leagues", league_id)
    if not lid:
        raise D.err(404, "NOT_FOUND", "No such league.")
    response.headers["Cache-Control"] = CACHE
    return TI.matrix(db, lid, window, venue)


@router.get("/teams/compare")
def teams_compare(response: Response, a: str = Query(max_length=64), b: str = Query(max_length=64),
                  window: str = Query("season", pattern="^(season|last10|last5)$"), as_fixture: bool = False, db=Depends(D.get_db)):
    if a == b:
        raise D.err(400, "SAME_TEAM", "Pick two different clubs.")
    out = TI.compare(db, a, b, window, as_fixture)
    if out is None:
        raise D.err(404, "NOT_FOUND", "No such team.")
    response.headers["Cache-Control"] = CACHE
    return out
