"""routes_data.py -- the public data routes from doc 06 section 2 that server.py does not already carry.

Every route reads our own database through queries.py. No route ever calls PitchAPI.
URLs carry the public `id` (uuid); we turn it into the integer `iid` with Q.iid_of and answer 404 when it is unknown.
Public data answers carry `Cache-Control: public, max-age=60, stale-while-revalidate=300`.
Tested by tests/selftest_routes.py.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Query, Response

import deps as D
import plans as P
import queries as Q
import settings_store as S

router = APIRouter(prefix="/api")
CACHE = "public, max-age=60, stale-while-revalidate=300"
STATS_MAX = 40          # longest stat key we accept; the engine's keys are short snake_case words


def _cache(resp: Response) -> None:
    resp.headers["Cache-Control"] = CACHE


def _iid(db, coll: str, public_id: str) -> int:
    i = Q.iid_of(db, coll, public_id)
    if not i:
        raise D.err(404, "NOT_FOUND", "We could not find that.")
    return i


def _stat(stat: str) -> str:
    s = (stat or "").strip()
    if not s or len(s) > STATS_MAX or not all(c.isalnum() or c == "_" for c in s):
        raise D.err(400, "BAD_STAT", "Unknown stat.")
    return s


def _venue(v: str | None) -> str | None:
    if v in (None, "", "all"):
        return None
    if v not in ("home", "away"):
        raise D.err(400, "BAD_VENUE", "Venue is home, away or all.")
    return v


# ------------------------------------------------------------------ status and pages
@router.get("/public/status")
def public_status(response: Response, db=Depends(D.get_db)):
    """Footer line "Data updated 3 hours ago" and the stale banner."""
    _cache(response)
    last = {}
    for job in ("fixtures_sync", "results_sync", "engine", "reference_sync"):
        r = db.job_runs.find_one({"job": job, "status": "ok"}, {"_id": 0, "finished_at": 1, "started_at": 1}, sort=[("started_at", -1)])
        last[job] = (r.get("finished_at") or r.get("started_at")) if r else None
    stamps = [v for v in last.values() if v]
    return {"last_ok": last, "data_updated_at": max(stamps) if stamps else None}


@router.get("/public/pages/{slug}")
def public_page(slug: str, response: Response, db=Depends(D.get_db)):
    page = db.content_pages.find_one({"slug": slug, "published": {"$ne": False}}, {"_id": 0, "slug": 1, "title": 1, "body_md": 1, "updated_at": 1})
    if not page:
        raise D.err(404, "NOT_FOUND", "No such page.")
    _cache(response)
    return page          # Markdown. The browser renders it with a sanitizer, never as raw HTML.


# ------------------------------------------------------------------ leagues
@router.get("/leagues")
def leagues(response: Response, q: str = "", db=Depends(D.get_db)):
    _cache(response)
    rows = list(db.leagues.find({"enabled": True}, {"_id": 0, "iid": 1, "id": 1, "name": 1, "country": 1, "current_season": 1}).sort("name", 1))
    if q.strip():
        ql = q.strip().lower()
        rows = [r for r in rows if ql in (r.get("name") or "").lower() or ql in (r.get("country") or "").lower()]
    rows = Q.attach_images(db, "leagues", rows)
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    day0 = now.replace(hour=0, minute=0, second=0, microsecond=0)
    nxt = {g["_id"]: g for g in db.matches.aggregate([{"$match": {"status": "scheduled", "kickoff": {"$gte": now}}}, {"$sort": {"kickoff": 1}},
                                                       {"$group": {"_id": "$league_iid", "kickoff": {"$first": "$kickoff"}, "round": {"$first": "$round"}}}])}
    today = {g["_id"]: g["n"] for g in db.matches.aggregate([{"$match": {"kickoff": {"$gte": day0, "$lt": day0 + timedelta(days=1)}}},
                                                             {"$group": {"_id": "$league_iid", "n": {"$sum": 1}}}])}
    groups: dict[str, list] = {}
    for r in rows:
        g = nxt.get(r.get("iid"))
        r["next"] = {"kickoff": g["kickoff"], "round": g.get("round")} if g else None
        r["today"] = today.get(r.get("iid"), 0)
        r.pop("iid", None)
        groups.setdefault(r.get("country") or "Other", []).append(r)
    return {"countries": [{"country": c, "leagues": ls} for c, ls in sorted(groups.items())]}


def _league(db, league_id: str) -> dict:
    lg = db.leagues.find_one({"id": league_id, "enabled": True}, {"_id": 0})
    if not lg:
        raise D.err(404, "NOT_FOUND", "We could not find that league.")
    return lg


@router.get("/leagues/{league_id}")
def league(league_id: str, response: Response, db=Depends(D.get_db)):
    lg = _league(db, league_id)
    _cache(response)
    iid = lg["iid"]
    out = {k: lg.get(k) for k in ("id", "name", "country", "current_season")}
    out["image"] = Q.attach_images(db, "leagues", [dict(lg)])[0].get("image")
    out["next"] = Q.league_matches(db, iid, "scheduled", limit=20)
    out["recent"] = Q.league_matches(db, iid, "final", limit=20)
    out["zones"] = lg.get("zones") or []
    return out


@router.get("/teams/{team_id}/history")
def team_history(team_id: str, response: Response, stat: str = Query(..., pattern="^(shots|sot|tackles|corners|yellow_cards|match_yellow_cards|goals|fouls)$"),
                 last: int = Query(10, ge=1, le=40), db=Depends(D.get_db)):
    tid = _iid(db, "teams", team_id)
    _cache(response)
    return Q.team_history(db, tid, stat, last)


@router.get("/teams/{team_id}/squad-season")
def squad_season(team_id: str, response: Response, db=Depends(D.get_db)):
    tid = _iid(db, "teams", team_id)
    _cache(response)
    return Q.squad_season(db, tid)


@router.get("/players/{player_id}/ranks")
def player_ranks(player_id: str, response: Response, db=Depends(D.get_db)):
    _cache(response)
    return Q.player_ranks(db, _iid(db, "players", player_id))


@router.get("/match-days")
def match_days(response: Response, start: str = Query(..., pattern=r"^\d{4}-\d{2}-\d{2}$"), days: int = Query(14, ge=1, le=31),
               tz_offset_min: int = Query(0, ge=-840, le=840), db=Depends(D.get_db)):
    _cache(response)
    d0 = datetime.fromisoformat(start).replace(tzinfo=timezone.utc) - timedelta(minutes=tz_offset_min)
    return {"days": Q.match_days(db, d0, days, tz_offset_min)}


@router.get("/leagues/{league_id}/fixtures")
def league_fixtures(league_id: str, response: Response, status: str = Query("scheduled", pattern="^(scheduled|final)$"),
                    limit: int = Query(50, ge=1, le=400), db=Depends(D.get_db)):
    lg = _league(db, league_id)
    _cache(response)
    return Q.league_matches(db, lg["iid"], status, limit=limit)


@router.get("/leagues/{league_id}/leaderboard")
def league_leaderboard(league_id: str, response: Response, stat: str = "shots", per90: bool = False,
                       min_minutes: int = Query(450, ge=0, le=5000), limit: int = Query(50, ge=1, le=200), db=Depends(D.get_db)):
    lg = _league(db, league_id)
    _cache(response)
    return Q.leaderboard(db, lg["iid"], _stat(stat), per90=per90, min_minutes=min_minutes, limit=limit)


@router.get("/leagues/{league_id}/booking-risk")
def league_booking_risk(league_id: str, response: Response, db=Depends(D.get_db)):
    lg = _league(db, league_id)
    _cache(response)
    return Q.booking_risk(db, lg["iid"])


@router.get("/leagues/{league_id}/referee-assignments")
def league_referee_assignments(league_id: str, response: Response, db=Depends(D.get_db)):
    lg = _league(db, league_id)
    _cache(response)
    return Q.referee_assignments(db, lg["iid"])


@router.get("/referees")
def referees(response: Response, min_matches: int = Query(3, ge=1, le=20), db=Depends(D.get_db)):
    _cache(response)
    return Q.referee_leaderboard(db, min_matches)


@router.get("/referees/{name}")
def referee(name: str, response: Response, db=Depends(D.get_db)):
    n = name.strip()[:80]
    out = Q.referee_detail(db, n) if n else None
    if not out:
        raise D.err(404, "NOT_FOUND", "We could not find that referee.")
    _cache(response)
    return out


@router.get("/leagues/{league_id}/referees")
def league_referees(league_id: str, response: Response, db=Depends(D.get_db)):
    lg = _league(db, league_id)
    _cache(response)
    return Q.referee_table(db, lg["iid"])


# ------------------------------------------------------------------ matches
@router.get("/matches/{match_id}")
def match(match_id: str, response: Response, user=Depends(D.optional_user), db=Depends(D.get_db)):
    out = Q.match_detail(db, _iid(db, "matches", match_id))
    if not out:
        raise D.err(404, "NOT_FOUND", "We could not find that match.")
    if not P.ent(db, user, "matchup_tab"):
        out["styles"] = {}                           # the tactical matchup tab is a plan feature (doc 13, `matchup_tab`)
        out["matchup_locked"] = True
    else:
        out["matchup_locked"] = False
    response.headers["Cache-Control"] = "private, no-store" if user else CACHE
    return out


@router.get("/h2h")
def head_to_head(a: str, b: str, response: Response, limit: int = Query(10, ge=1, le=50), db=Depends(D.get_db)):
    _cache(response)
    return Q.h2h(db, _iid(db, "teams", a), _iid(db, "teams", b), limit=limit)


# ------------------------------------------------------------------ teams
def _grid_cap(db, user, last: int) -> int:
    cap = P.ent(db, user, "grid_games")
    return last if cap is None or cap < 0 else min(last, int(cap))


@router.get("/teams/{team_id}")
def team(team_id: str, response: Response, db=Depends(D.get_db)):
    out = Q.team_detail(db, _iid(db, "teams", team_id))
    if not out:
        raise D.err(404, "NOT_FOUND", "We could not find that team.")
    _cache(response)
    return out


@router.get("/teams/{team_id}/squad-grid")
def team_squad_grid(team_id: str, response: Response, stat: str = "shots", last: int = Query(10, ge=1, le=38), venue: str | None = None,
                    user=Depends(D.optional_user), db=Depends(D.get_db)):
    response.headers["Cache-Control"] = "private, no-store" if user else CACHE
    n = _grid_cap(db, user, last)
    return {"last": n, "capped": n < last, "rows": Q.squad_grid(db, _iid(db, "teams", team_id), _stat(stat), last_n=n, venue=_venue(venue))}


@router.get("/teams/{team_id}/totals")
def team_totals(team_id: str, response: Response, stat: str = "shots", last: int = Query(10, ge=1, le=38),
                user=Depends(D.optional_user), db=Depends(D.get_db)):
    response.headers["Cache-Control"] = "private, no-store" if user else CACHE
    n = _grid_cap(db, user, last)
    return {"last": n, "capped": n < last, "rows": Q.team_totals_grid(db, _iid(db, "teams", team_id), _stat(stat), last_n=n)}


@router.get("/teams/{team_id}/first-goal")
def team_first_goal(team_id: str, response: Response, last: int = Query(20, ge=5, le=38), db=Depends(D.get_db)):
    _cache(response)
    return Q.team_first_goal(db, _iid(db, "teams", team_id), last_n=last)


@router.get("/teams/{team_id}/against")
def team_against(team_id: str, response: Response, stat: str = "shots", last: int = Query(10, ge=1, le=38), db=Depends(D.get_db)):
    _cache(response)
    return Q.against_by_position(db, _iid(db, "teams", team_id), _stat(stat), last_n=last)


# ------------------------------------------------------------------ players
@router.get("/players/{player_id}")
def player(player_id: str, response: Response, db=Depends(D.get_db)):
    out = Q.player_detail(db, _iid(db, "players", player_id))
    if not out:
        raise D.err(404, "NOT_FOUND", "We could not find that player.")
    _cache(response)
    return out


@router.get("/players/{player_id}/history")
def player_history(player_id: str, response: Response, last: int = Query(20, ge=1, le=60), venue: str | None = None,
                   started: bool = False, min_minutes: float = Query(0, ge=0, le=120), db=Depends(D.get_db)):
    _cache(response)
    return Q.player_history(db, _iid(db, "players", player_id), last_n=last, venue=_venue(venue), started=started, min_minutes=min_minutes)


# ------------------------------------------------------------------ track record
@router.get("/track-record")
def track_record(response: Response, league: str | None = None,
                 stat: str | None = Query(None, pattern="^(shots|sot|tackles|corners|yellow_cards|match_yellow_cards)$"),
                 scope: str | None = Query(None, pattern="^(player|team)$"), db=Depends(D.get_db)):
    _cache(response)
    lg = _iid(db, "leagues", league) if league else None
    return Q.track_record(db, lg, min_n=int(S.get(db, "track_record.min_scored")), stat=stat, scope=scope)
