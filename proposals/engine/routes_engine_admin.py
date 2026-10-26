"""Proposed additions to routes_ingest_admin.py (docs/06 §5, docs/10 Engine): engine runs + markets, forecast browser,
hide / unhide with a reason. Reads existing collections; public lists already skip hidden rows via queries.NOT_HIDDEN."""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

import admin_queries as AQ
import deps as D
import engine_bridge as B

router = APIRouter(prefix="/api/admin")
perm = D.require_perm


def _iso(d):
    if isinstance(d, datetime):
        return (d if d.tzinfo else d.replace(tzinfo=timezone.utc)).isoformat()
    return d


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
