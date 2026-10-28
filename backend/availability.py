"""availability.py -- who cannot play: injuries and suspensions (docs/22).

Three sources, strongest first:
  1. the confirmed eleven (always wins, handled by the engine);
  2. this collection, `availability`: one row per player, status "out" or "doubtful", filled by
     a) the admin (Admin > Engine > Availability), or
     b) the optional API-Football sync below (`injuries.enabled`), which reuses the player mapping the image sync
        already built (`image_map`, docs/19), so no names are guessed;
  3. the engine's own availability model: a player who has not featured in his club's recent matches is very
     likely out (built into soccer_brain/engine.py, always on).

An "out" player gets no forecast, and his share of his club's shots and tackles goes to his team-mates.
A "doubtful" player's chance of playing is halved.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import settings_store as S

STATUSES = ("out", "doubtful", "available")
REASON_MAX = 80


def utcnow():
    return datetime.now(timezone.utc)


def _aware(dt):
    return dt if dt is None or dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def set_status(db, player_iid: int, status: str, *, source: str, reason: str = "", until=None, actor: str | None = None) -> dict:
    if status not in STATUSES:
        raise ValueError("status must be out, doubtful or available")
    p = db.players.find_one({"iid": int(player_iid)}, {"_id": 0, "iid": 1, "team_iid": 1})
    if not p:
        raise KeyError("player")
    if status == "available":
        db.availability.delete_one({"player_iid": p["iid"]})
        return {"player_iid": p["iid"], "status": "available"}
    row = {"player_iid": p["iid"], "team_iid": p.get("team_iid"), "status": status, "source": source,
           "reason": (reason or "")[:REASON_MAX], "until": _aware(until), "updated_at": utcnow(), "by": actor}
    db.availability.update_one({"player_iid": p["iid"]}, {"$set": row}, upsert=True)
    return row


def for_match(db, team_iids, kickoff) -> dict:
    """{player_iid: "out" | "doubtful"} for the clubs of one match, valid at kick-off."""
    kickoff = _aware(kickoff)
    out = {}
    for r in db.availability.find({"team_iid": {"$in": list(team_iids)}}, {"_id": 0}):
        until = _aware(r.get("until"))
        if until is not None and kickoff is not None and until < kickoff:
            continue
        out[int(r["player_iid"])] = r["status"]
    return out


def public_list(db, team_iids) -> list[dict]:
    """For the match page: who is out or doubtful, with a short reason. Names come from `players`."""
    rows = list(db.availability.find({"team_iid": {"$in": list(team_iids)}}, {"_id": 0, "player_iid": 1, "team_iid": 1, "status": 1, "reason": 1, "until": 1}))
    names = {p["iid"]: p for p in db.players.find({"iid": {"$in": [r["player_iid"] for r in rows]}}, {"_id": 0, "iid": 1, "id": 1, "name": 1})}
    for r in rows:
        p = names.get(r["player_iid"], {})
        r["player"] = {"id": p.get("id"), "name": p.get("name")}
    return rows


def expire(db, now=None) -> int:
    """Daily: remove rows whose `until` has passed, and feed rows not refreshed for `injuries.stale_days`."""
    now = now or utcnow()
    a = db.availability.delete_many({"until": {"$lt": now}}).deleted_count
    b = db.availability.delete_many({"source": "apifootball", "updated_at": {"$lt": now - timedelta(days=int(S.get(db, "injuries.stale_days")))}}).deleted_count
    return a + b


# ------------------------------------------------------------------ optional: API-Football injuries feed
# Endpoint as described by API-Football's guides: GET /injuries?league={id}&season={year}&date=YYYY-MM-DD
# Each item: player {id, name, type, reason}, team {id}, fixture {id, date}. `type` is "Missing Fixture" or
# "Questionable". NOT verified against the official page (it would not load for us, docs/19); run
# check_apifootball.py --injuries once before switching `injuries.enabled` on. Parsing is defensive.
TYPE_MAP = {"missing fixture": "out", "questionable": "doubtful"}


def sync_apifootball(db, client=None, now=None, days_ahead: int = 2) -> dict:
    """One call per enabled league per day ahead. Players are matched through `image_map` (approved/auto only)."""
    if not S.get(db, "injuries.enabled"):
        return {"status": "off"}
    import images as IMG
    now = now or utcnow()
    client = client or IMG.AFClient(db)
    table = S.get(db, "images.leagues") or {}
    af_to_ours = {m["af_id"]: m["our_iid"] for m in db.image_map.find({"kind": "player", "status": {"$in": ["auto", "approved"]}, "af_id": {"$ne": None}},
                                                                         {"_id": 0, "af_id": 1, "our_iid": 1})}
    calls = matched = unknown = 0
    for lg in db.leagues.find({"enabled": True}, {"_id": 0, "iid": 1, "current_season": 1}):
        af_league = table.get(str(lg["iid"]))
        if not af_league:
            continue
        season = int(str(lg.get("current_season") or now.year)[:4])
        for d in range(days_ahead + 1):
            day = (now + timedelta(days=d)).strftime("%Y-%m-%d")
            try:
                data = client.get("/injuries", {"league": int(af_league), "season": season, "date": day}, fresh=True)
            except IMG.BudgetExhausted:
                return {"status": "budget", "calls": calls, "matched": matched, "unknown": unknown}
            calls += 1
            for it in data.get("response") or []:
                pl = it.get("player") or {}
                ours = af_to_ours.get(pl.get("id"))
                status = TYPE_MAP.get(str(pl.get("type") or "").strip().lower())
                if not ours or not status:
                    unknown += 1
                    continue
                cur = db.availability.find_one({"player_iid": ours}, {"source": 1})
                if cur and cur.get("source") == "admin":
                    continue                                   # the admin's word wins over the feed
                fx_date = ((it.get("fixture") or {}).get("date") or "")[:10]
                until = datetime.fromisoformat(fx_date).replace(tzinfo=timezone.utc) + timedelta(days=1) if fx_date else now + timedelta(days=3)
                set_status(db, ours, status, source="apifootball", reason=str(pl.get("reason") or "")[:REASON_MAX], until=until)
                matched += 1
    return {"status": "done", "calls": calls, "matched": matched, "unknown": unknown}
