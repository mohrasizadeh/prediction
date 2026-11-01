"""routes_me.py -- the signed-in user's own data (doc 06 section 3, "Still for the builder").

Follows, saved forecasts and player notes. Every route needs a full session (deps.require_user) and every query is
scoped to that user's id, so user A can never read or change user B's rows. Limits come from the plan
(`follows_max`, `saved_max`, `notes_max`; -1 = no limit). Over the limit: 409 LIMIT_REACHED.
Telegram alerts (`POST /api/me/alerts/telegram`) are phase 2 and are not built here.
Tested by tests/selftest_routes.py.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Literal

from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel, Field
from pymongo.errors import DuplicateKeyError

import combo as CB
import live_track as LT
import deps as D
import plans as P
import queries as Q

router = APIRouter(prefix="/api/me")
KIND_COLL = {"player": "players", "team": "teams", "league": "leagues", "match": "matches"}
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
    kind: Literal["player", "team", "league", "match"]
    ref_id: str = Field(min_length=1, max_length=64)


@router.get("/booking-risk")
def my_booking_risk(response: Response, user=Depends(D.require_user), db=Depends(D.get_db)):
    """Followed players who are in their league's top 10 booking risks for the next round."""
    _private(response)
    mine = {r["ref_iid"] for r in db.follows.find({"user_id": user["id"], "kind": "player"}, {"ref_iid": 1})}
    if not mine:
        return {"rows": []}
    out = []
    for lg in db.leagues.find({"enabled": True}, {"iid": 1}):
        rows = Q.booking_risk(db, lg["iid"], limit=10)["rows"]
        out += [{**f, "rank": i + 1} for i, f in enumerate(rows) if f["player_iid"] in mine]
    return {"rows": sorted(out, key=lambda f: -f["p"])}


@router.get("/follows")
def follows(response: Response, user=Depends(D.require_user), db=Depends(D.get_db)):
    _private(response)
    rows = list(db.follows.find({"user_id": user["id"]}, {"_id": 0, "kind": 1, "ref_iid": 1, "created_at": 1}).sort("created_at", -1))
    out = []
    for kind, coll in KIND_COLL.items():
        iids = [r["ref_iid"] for r in rows if r["kind"] == kind]
        if kind == "match":
            ms = {m["iid"]: m for m in db.matches.find({"iid": {"$in": iids}}, {"_id": 0, "iid": 1, "id": 1, "home_iid": 1, "away_iid": 1, "kickoff": 1})} if iids else {}
            tn = Q._names(db, "teams", [i for m in ms.values() for i in (m["home_iid"], m["away_iid"])]) if ms else {}
            names = {i: {"id": m["id"], "name": f"{(tn.get(m['home_iid']) or {}).get('name', '?')} v {(tn.get(m['away_iid']) or {}).get('name', '?')}",
                         "image": (tn.get(m["home_iid"]) or {}).get("image"), "kickoff": m["kickoff"]} for i, m in ms.items()}
        else:
            names = Q._names(db, coll, iids) if iids else {}
        for r in rows:
            if r["kind"] == kind and r["ref_iid"] in names:
                n = names[r["ref_iid"]]
                out.append({"kind": kind, "id": n.get("id"), "name": n.get("name"), "image": n.get("image"), "kickoff": n.get("kickoff"), "created_at": r["created_at"]})
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
    followed_ms = [r["ref_iid"] for r in rows if r["kind"] == "match"]
    now = utcnow()
    q = {"status": "scheduled", "kickoff": {"$gte": now}, "$or": [{"home_iid": {"$in": list(teams)}}, {"away_iid": {"$in": list(teams)}},
                                                                  {"league_iid": {"$in": leagues}}, {"iid": {"$in": followed_ms}}]}
    ms = list(db.matches.find(q, {"_id": 0}).sort("kickoff", 1).limit(30))
    done = list(db.matches.find({"status": "final", "kickoff": {"$gte": now - timedelta(days=7)},
                                 "$or": [{"home_iid": {"$in": list(teams)}}, {"away_iid": {"$in": list(teams)}}]},
                                {"_id": 0, "id": 1, "home_iid": 1, "away_iid": 1, "hg": 1, "ag": 1, "kickoff": 1}).sort("kickoff", -1).limit(10))
    names = Q._names(db, "teams", [m["home_iid"] for m in ms + done] + [m["away_iid"] for m in ms + done])
    for m in ms:
        m["home"], m["away"] = names.get(m["home_iid"]), names.get(m["away_iid"])
    for m in done:
        m["home"], m["away"] = names.get(m.pop("home_iid")), names.get(m.pop("away_iid"))
    fc = list(db.forecasts.find({**Q.NOT_HIDDEN, "match_iid": {"$in": [m["iid"] for m in ms]},
                                 "$or": [{"player_iid": {"$in": players}}, {"scope": "team", "team_iid": {"$in": list(teams)}}]},
                                {"_id": 0, "contrib": 0}).sort("p", -1).limit(100))
    return {"matches": ms, "forecasts": Q._decorate(db, fc), "results": done, "lineups": _lineup_news(db, ms, players)}


def _lineup_news(db, ms, players) -> list[dict]:
    """Followed players in a confirmed lineup: starts, or is not in the starting eleven."""
    by_iid = {m["iid"]: m for m in ms}
    lu = list(db.lineups.find({"match_iid": {"$in": list(by_iid)}, "confirmed": True}, {"_id": 0, "match_iid": 1, "team_iid": 1, "player_iid": 1, "started": 1}))
    if not lu or not players:
        return []
    started = {(x["match_iid"], x["player_iid"]) for x in lu if x.get("started")}
    sides = {(x["match_iid"], x["team_iid"]) for x in lu}
    pl = {p["iid"]: p for p in db.players.find({"iid": {"$in": players}}, {"_id": 0, "iid": 1, "team_iid": 1})}
    names = Q._names(db, "players", players)
    out = []
    for mi, m in by_iid.items():
        for pid in players:
            team = (pl.get(pid) or {}).get("team_iid")
            if team in (m["home_iid"], m["away_iid"]) and (mi, team) in sides and pid in names:
                out.append({"match_id": m["id"], "kickoff": m["kickoff"], "player": names[pid], "started": (mi, pid) in started})
    return out


# ------------------------------------------------------------------ Finder presets (per account)
class Preset(BaseModel):
    name: str = Field(min_length=1, max_length=40)
    q: str = Field(max_length=600)


class PresetsBody(BaseModel):
    items: list[Preset] = Field(max_length=8)


@router.get("/presets")
def presets(response: Response, user=Depends(D.require_user), db=Depends(D.get_db)):
    _private(response)
    return {"items": (db.users.find_one({"id": user["id"]}, {"finder_presets": 1}) or {}).get("finder_presets") or []}


@router.put("/presets")
def put_presets(body: PresetsBody, user=Depends(D.require_user), db=Depends(D.get_db)):
    items = [p.model_dump() for p in body.items]
    db.users.update_one({"id": user["id"]}, {"$set": {"finder_presets": items}})
    return {"items": items}


# ------------------------------------------------------------------ saved forecasts
class SavedBody(BaseModel):
    fkey: str = Field(min_length=3, max_length=120)


@router.get("/saved")
def saved(response: Response, user=Depends(D.require_user), db=Depends(D.get_db)):
    _private(response)
    rows = list(db.saved_forecasts.find({"user_id": user["id"]}, {"_id": 0, "fkey": 1, "created_at": 1}).sort("created_at", -1))
    current = {f["fkey"]: f for f in Q._decorate(db, list(db.forecasts.find({"fkey": {"$in": [r["fkey"] for r in rows]}, **Q.NOT_HIDDEN}, {"_id": 0, "contrib": 0})))}
    outs = {o["fkey"]: o for o in db.forecast_outcomes.find({"fkey": {"$in": [r["fkey"] for r in rows]}},
                                                             {"_id": 0, "fkey": 1, "reached": 1, "actual": 1, "player_played": 1}).sort("scored_at", 1)}
    for r in rows:
        r["forecast"] = current.get(r["fkey"])                 # null once the match is played and the forecast is replaced
        r["outcome"] = outs.get(r["fkey"])
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


# ------------------------------------------------------------------ my combos (docs/28)
class ComboSaveBody(BaseModel):
    ids: list[str] = Field(default_factory=list, max_length=12)
    fkeys: list[str] = Field(default_factory=list, max_length=12)       # the screens send fkeys: they survive an engine re-run


def _combo_view(db, c: dict) -> dict:
    """One saved combo for the list.

    Four states, because a match being under way is not the same as it being over (docs/40):
      upcoming  nothing has kicked off yet          -> today's estimate
      live      at least one match is under way     -> what has happened so far, from live tracking
      waiting   every match is over, results still arriving
      settled   every line has been graded
    """
    now = utcnow()
    out = {k: c[k] for k in ("id", "label", "kickoff", "combined", "state", "lines", "created_at")}
    out["match_id"] = c.get("match_id")
    out["matches"] = c.get("matches") or []
    # a combo that spans matches is still upcoming until the LAST of them has kicked off
    ko = c.get("last_kickoff") or c["kickoff"]
    ko = ko if ko.tzinfo else ko.replace(tzinfo=timezone.utc)
    outs = {o["fkey"]: o for o in db.forecast_outcomes.find({"fkey": {"$in": [l["fkey"] for l in c["lines"]]}}, {"_id": 0})}
    if ko > now:
        out["status"] = "upcoming"
        try:
            est = CB.estimate(db, fkeys=[l["fkey"] for l in c["lines"]])
            out["now"] = {"combined": est["combined"], "plain": est["plain"], "state": est["state"], "range": est["range"], "notes": est["notes"]}
        except CB.ComboError:
            out["now"] = None                                           # a line left the feed (for example the player is out)
        return out

    iids = [m["match_iid"] for m in out["matches"]] or [i for i in {l.get("match_iid") for l in c["lines"]} if i] or [c.get("match_iid")]
    iids = [i for i in iids if i is not None]
    statuses = {m["iid"]: m.get("status") for m in db.matches.find({"iid": {"$in": iids}}, {"_id": 0, "iid": 1, "status": 1})}
    over = bool(statuses) and all(v == "final" for v in statuses.values())

    res = []
    for l in c["lines"]:
        o = outs.get(l["fkey"])
        res.append({"fkey": l["fkey"], "reached": None if not o else bool(o["reached"]), "actual": None if not o else o["actual"],
                    "played": None if not o else bool(o.get("player_played", True))})
    graded = all(r["reached"] is not None for r in res)

    if not over:
        # under way: show what has happened so far. A line we cannot count stays unknown, never a false cross.
        out["status"] = "live"
        live = {}
        for iid in iids:
            if statuses.get(iid) == "final":
                continue
            try:
                ev = LT.evaluate(db, iid)
            except Exception:
                continue
            live.update(ev.get("items") or {})
        for r in res:
            it = live.get(r["fkey"]) or {}
            r["live"] = it.get("state")                                 # hit | live | missed | unknown | None
            r["current"], r["needed"] = it.get("current"), it.get("needed")
            if r["reached"] is None and it.get("state") == "hit":
                r["reached"] = True                                     # already happened: say so now, not after full time
        out["lines"] = [{**l, **r} for l, r in zip(c["lines"], res)]
        hit = sum(1 for r in res if r["reached"] is True)
        out["result"] = {"reached": hit, "of": len(res), "all": False,
                         "unknown": sum(1 for r in res if r["reached"] is None)}
        return out

    out["lines"] = [{**l, **r} for l, r in zip(c["lines"], res)]
    out["status"] = "settled" if graded else "waiting"
    out["result"] = {"reached": sum(1 for r in res if r["reached"]), "of": len(res), "all": graded and all(r["reached"] for r in res),
                     "unknown": sum(1 for r in res if r["reached"] is None)}
    return out


@router.get("/combos")
def combos(response: Response, user=Depends(D.require_user), db=Depends(D.get_db)):
    _private(response)
    rows = list(db.combos.find({"user_id": user["id"]}, {"_id": 0}).sort("created_at", -1).limit(100))
    return {"items": [_combo_view(db, c) for c in rows], "limit": P.ent(db, user, "saved_max")}


@router.put("/combos", status_code=201)
def save_combo(body: ComboSaveBody, user=Depends(D.require_user), db=Depends(D.get_db)):
    try:
        est = CB.estimate(db, ids=body.ids, fkeys=body.fkeys)
    except CB.ComboError as e:
        raise D.err(409 if e.code in ("SAME_STAT", "TOO_MANY") else 404 if e.code == "NOT_FOUND" else 400, e.code, e.message)
    _room(db, user, "saved_max", db.combos.count_documents({"user_id": user["id"]}))
    # a combo may span matches (docs/40): keep the first for the link, and the LAST kick-off, because the combo is
    # not over until its last match has started
    doc = {"id": str(uuid.uuid4()), "user_id": user["id"], "match_iid": est["match_iid"], "match_id": est.get("match_id"),
           "kickoff": est["kickoff"], "last_kickoff": est.get("last_kickoff") or est["kickoff"],
           "matches": [{k: m[k] for k in ("match_iid", "match_id", "label", "kickoff", "combined") if k in m} for m in est.get("matches", [])],
           "label": est.get("label"), "combined": est["combined"], "state": est["state"],
           "lines": [{k: l[k] for k in ("fkey", "player", "team", "market", "stat", "thr", "chance", "badge", "match_iid")} for l in est["lines"]],
           "created_at": utcnow()}
    db.combos.insert_one(dict(doc))
    return {"ok": True, "id": doc["id"], "estimate": est}


@router.delete("/combos/{combo_id}")
def delete_combo(combo_id: str, user=Depends(D.require_user), db=Depends(D.get_db)):
    return {"ok": True, "removed": db.combos.delete_one({"id": combo_id, "user_id": user["id"]}).deleted_count}


# ------------------------------------------------------------------ notes
class NoteBody(BaseModel):
    text: str = Field(min_length=1, max_length=NOTE_MAX)


def _player(db, player_id: str) -> int:
    iid = Q.iid_of(db, "players", player_id)
    if not iid:
        raise D.err(404, "NOT_FOUND", "We could not find that player.")
    return iid


@router.get("/notes")
def notes(response: Response, user=Depends(D.require_user), db=Depends(D.get_db)):
    _private(response)
    rows = list(db.notes.find({"user_id": user["id"]}, {"_id": 0, "player_iid": 1, "text": 1, "updated_at": 1}).sort("updated_at", -1).limit(100))
    names = Q._names(db, "players", [r["player_iid"] for r in rows])
    return {"items": [{"player": names.get(r["player_iid"]), "text": r["text"], "updated_at": r.get("updated_at")} for r in rows if r["player_iid"] in names]}


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
