"""routes_me.py -- the signed-in user's own data (doc 06 section 3, "Still for the builder").

Follows, saved forecasts and player notes. Every route needs a full session (deps.require_user) and every query is
scoped to that user's id, so user A can never read or change user B's rows. Limits come from the plan
(`follows_max`, `saved_max`, `notes_max`; -1 = no limit). Over the limit: 409 LIMIT_REACHED.
Telegram alerts (`POST /api/me/alerts/telegram`) are phase 2 and are not built here.
Tested by tests/selftest_routes.py.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel, Field
from pymongo.errors import DuplicateKeyError

import deps as D
import plans as P
import queries as Q

router = APIRouter(prefix="/api/me")
KIND_COLL = {"player": "players", "team": "teams", "league": "leagues"}
NOTE_MAX = 2000


def utcnow():
    return datetime.now(timezone.utc)


def _private(resp: Response) -> None:
    resp.headers["Cache-Control"] = "private, no-store"


def _room(db, user, key: str, used: int) -> None:
    cap = P.ent(db, user, key)
    if cap is not None and cap >= 0 and used >= cap:
        raise D.err(409, "LIMIT_REACHED", f"Your plan allows {cap}. Remove one or upgrade.")


# ------------------------------------------------------------------ follows
class FollowBody(BaseModel):
    kind: Literal["player", "team", "league"]
    ref_id: str = Field(min_length=1, max_length=64)


@router.get("/follows")
def follows(response: Response, user=Depends(D.require_user), db=Depends(D.get_db)):
    _private(response)
    rows = list(db.follows.find({"user_id": user["id"]}, {"_id": 0, "kind": 1, "ref_iid": 1, "created_at": 1}).sort("created_at", -1))
    out = []
    for kind, coll in KIND_COLL.items():
        iids = [r["ref_iid"] for r in rows if r["kind"] == kind]
        names = Q._names(db, coll, iids) if iids else {}
        for r in rows:
            if r["kind"] == kind and r["ref_iid"] in names:
                n = names[r["ref_iid"]]
                out.append({"kind": kind, "id": n.get("id"), "name": n.get("name"), "image": n.get("image"), "created_at": r["created_at"]})
    return {"items": out, "limit": P.ent(db, user, "follows_max")}


@router.put("/follows", status_code=201)
def follow(body: FollowBody, user=Depends(D.require_user), db=Depends(D.get_db)):
    iid = Q.iid_of(db, KIND_COLL[body.kind], body.ref_id)
    if not iid:
        raise D.err(404, "NOT_FOUND", "We could not find that.")
    if db.follows.find_one({"user_id": user["id"], "kind": body.kind, "ref_iid": iid}):
        return {"ok": True, "already": True}
    _room(db, user, "follows_max", db.follows.count_documents({"user_id": user["id"]}))
    try:
        db.follows.insert_one({"user_id": user["id"], "kind": body.kind, "ref_iid": iid, "created_at": utcnow()})
    except DuplicateKeyError:
        return {"ok": True, "already": True}
    return {"ok": True}


@router.delete("/follows")
def unfollow(body: FollowBody, user=Depends(D.require_user), db=Depends(D.get_db)):
    iid = Q.iid_of(db, KIND_COLL[body.kind], body.ref_id)
    n = db.follows.delete_one({"user_id": user["id"], "kind": body.kind, "ref_iid": iid}).deleted_count if iid else 0
    return {"ok": True, "removed": n}


@router.get("/following-feed")
def following_feed(response: Response, user=Depends(D.require_user), db=Depends(D.get_db)):
    """Upcoming fixtures and current forecasts for the teams and players this user follows."""
    _private(response)
    rows = list(db.follows.find({"user_id": user["id"]}, {"_id": 0, "kind": 1, "ref_iid": 1}))
    teams = {r["ref_iid"] for r in rows if r["kind"] == "team"}
    players = [r["ref_iid"] for r in rows if r["kind"] == "player"]
    for p in db.players.find({"iid": {"$in": players}}, {"_id": 0, "team_iid": 1}):
        teams.add(p["team_iid"])
    leagues = [r["ref_iid"] for r in rows if r["kind"] == "league"]
    now = utcnow()
    q = {"status": "scheduled", "kickoff": {"$gte": now}, "$or": [{"home_iid": {"$in": list(teams)}}, {"away_iid": {"$in": list(teams)}},
                                                                  {"league_iid": {"$in": leagues}}]}
    ms = list(db.matches.find(q, {"_id": 0}).sort("kickoff", 1).limit(30))
    names = Q._names(db, "teams", [m["home_iid"] for m in ms] + [m["away_iid"] for m in ms])
    for m in ms:
        m["home"], m["away"] = names.get(m["home_iid"]), names.get(m["away_iid"])
    fc = list(db.forecasts.find({**Q.NOT_HIDDEN, "match_iid": {"$in": [m["iid"] for m in ms]},
                                 "$or": [{"player_iid": {"$in": players}}, {"scope": "team", "team_iid": {"$in": list(teams)}}]},
                                {"_id": 0, "contrib": 0}).sort("p", -1).limit(100))
    return {"matches": ms, "forecasts": Q._decorate(db, fc)}


# ------------------------------------------------------------------ saved forecasts
class SavedBody(BaseModel):
    fkey: str = Field(min_length=3, max_length=120)


@router.get("/saved")
def saved(response: Response, user=Depends(D.require_user), db=Depends(D.get_db)):
    _private(response)
    rows = list(db.saved_forecasts.find({"user_id": user["id"]}, {"_id": 0, "fkey": 1, "created_at": 1}).sort("created_at", -1))
    current = {f["fkey"]: f for f in Q._decorate(db, list(db.forecasts.find({"fkey": {"$in": [r["fkey"] for r in rows]}, **Q.NOT_HIDDEN}, {"_id": 0, "contrib": 0})))}
    for r in rows:
        r["forecast"] = current.get(r["fkey"])                 # null once the match is played and the forecast is replaced
    return {"items": rows, "limit": P.ent(db, user, "saved_max")}


@router.put("/saved", status_code=201)
def save(body: SavedBody, user=Depends(D.require_user), db=Depends(D.get_db)):
    if not db.forecasts.find_one({"fkey": body.fkey, **Q.NOT_HIDDEN}, {"_id": 1}):
        raise D.err(404, "NOT_FOUND", "That forecast is not available.")
    if db.saved_forecasts.find_one({"user_id": user["id"], "fkey": body.fkey}):
        return {"ok": True, "already": True}
    _room(db, user, "saved_max", db.saved_forecasts.count_documents({"user_id": user["id"]}))
    try:
        db.saved_forecasts.insert_one({"user_id": user["id"], "fkey": body.fkey, "created_at": utcnow()})
    except DuplicateKeyError:
        return {"ok": True, "already": True}
    return {"ok": True}


@router.delete("/saved")
def unsave(body: SavedBody, user=Depends(D.require_user), db=Depends(D.get_db)):
    return {"ok": True, "removed": db.saved_forecasts.delete_one({"user_id": user["id"], "fkey": body.fkey}).deleted_count}


# ------------------------------------------------------------------ notes
class NoteBody(BaseModel):
    text: str = Field(min_length=1, max_length=NOTE_MAX)


def _player(db, player_id: str) -> int:
    iid = Q.iid_of(db, "players", player_id)
    if not iid:
        raise D.err(404, "NOT_FOUND", "We could not find that player.")
    return iid


@router.get("/notes/{player_id}")
def note(player_id: str, response: Response, user=Depends(D.require_user), db=Depends(D.get_db)):
    _private(response)
    n = db.notes.find_one({"user_id": user["id"], "player_iid": _player(db, player_id)}, {"_id": 0, "text": 1, "updated_at": 1})
    return n or {"text": None}


@router.put("/notes/{player_id}")
def put_note(player_id: str, body: NoteBody, user=Depends(D.require_user), db=Depends(D.get_db)):
    iid = _player(db, player_id)
    text = body.text.strip()
    if not text:
        raise D.err(400, "EMPTY", "Write something first.")
    if not db.notes.find_one({"user_id": user["id"], "player_iid": iid}):
        _room(db, user, "notes_max", db.notes.count_documents({"user_id": user["id"]}))
    db.notes.update_one({"user_id": user["id"], "player_iid": iid}, {"$set": {"text": text, "updated_at": utcnow()}}, upsert=True)
    return {"ok": True}


@router.delete("/notes/{player_id}")
def delete_note(player_id: str, user=Depends(D.require_user), db=Depends(D.get_db)):
    return {"ok": True, "removed": db.notes.delete_one({"user_id": user["id"], "player_iid": _player(db, player_id)}).deleted_count}
