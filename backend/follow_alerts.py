"""follow_alerts.py -- e-mails for what people follow: confirmed lineups for followed teams and players,
and goals and red cards in followed matches (from SportAPI live events). Each alert is sent once (follow_alerts _id)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import queries as Q

LOOKAHEAD = timedelta(hours=3)


def Q_minute(s):
    from sportapi import _minute_num
    return _minute_num(s) if s else None


GOALS = {"goal": "Goal", "own_goal": "Own goal", "penalty": "Penalty goal"}
REDS = {"red_card": "Red card", "second_yellow": "Second yellow, sent off"}


def _users(db, uids, pref):
    import plans as P
    for u in db.users.find({"id": {"$in": list(uids)}, "disabled": {"$ne": True}, "email_verified": True}):
        p = u.get("prefs") or {}
        if p.get("alert_emails", True) is not False and p.get(pref, True) is not False and P.ent(db, u, "alerts"):
            yield u


def _send(db, key, u, template, vars) -> bool:
    import emailer as E
    if db.follow_alerts.find_one({"_id": key}):
        return False
    path = vars.pop("path", "/following")
    r = E.send_template(db, template, to=u["email"], user=u, vars={**vars, "link": E.base_url() + path}, idem=key)
    if r.get("status") not in ("sent", "duplicate"):
        return False
    db.follow_alerts.update_one({"_id": key}, {"$set": {"at": datetime.now(timezone.utc), "status": r.get("status"), "user_id": u["id"]}}, upsert=True)
    return r.get("status") == "sent"


def lineups(db, now) -> int:
    ms = list(db.matches.find({"status": "scheduled", "kickoff": {"$gte": now - timedelta(minutes=30), "$lte": now + LOOKAHEAD}},
                              {"_id": 0, "iid": 1, "id": 1, "home_iid": 1, "away_iid": 1}))
    sent = 0
    for m in ms:
        lu = list(db.lineups.find({"match_iid": m["iid"], "confirmed": True, "started": True}, {"_id": 0, "player_iid": 1, "team_iid": 1}))
        if not lu:
            continue
        teams = Q._names(db, "teams", [m["home_iid"], m["away_iid"]])
        title = f"{(teams.get(m['home_iid']) or {}).get('name', '?')} v {(teams.get(m['away_iid']) or {}).get('name', '?')}"
        starters = {x["player_iid"] for x in lu}
        per: dict = {}
        for fo in db.follows.find({"$or": [{"kind": "team", "ref_iid": {"$in": [m["home_iid"], m["away_iid"]]}}, {"kind": "match", "ref_iid": m["iid"]},
                                           {"kind": "player", "ref_iid": {"$in": list(starters)}}]}, {"user_id": 1, "kind": 1, "ref_iid": 1}):
            per.setdefault(fo["user_id"], set()).add((fo["kind"], fo["ref_iid"]))
        pn = Q._names(db, "players", list(starters))
        for u in _users(db, per, "alert_lineups"):
            mine = [pn[i]["name"] for k, i in per[u["id"]] if k == "player" and i in pn]
            line = f"Starting: {', '.join(mine)}." if mine else "The starting elevens are in."
            sent += _send(db, f"lineup:{u['id']}:{m['iid']}", u, "lineup_alert", {"match": title, "players": line, "path": f"/match/{m['id']}"})
    return sent


def goals(db, now) -> int:
    ms = {m["live"]["sid"]: m for m in db.matches.find({"live.sid": {"$exists": True}, "live.at": {"$gte": now - timedelta(hours=3)}},
                                                     {"_id": 0, "iid": 1, "id": 1, "home_iid": 1, "away_iid": 1, "live": 1})}
    if not ms:
        return 0
    sent = 0
    evs = db.live_events.find({"fixture_sid": {"$in": list(ms)}, "type": {"$in": [*GOALS, *REDS]}}, {"_id": 0})
    for e in evs:
        m = ms[e["fixture_sid"]]
        now_min = Q_minute(m["live"].get("minute"))
        if now_min is not None and e.get("minute_num") is not None and e["minute_num"] < now_min - 15:
            continue                                   # old news: a follower who joins late is not sent the whole match
        uids = {fo["user_id"] for fo in db.follows.find({"$or": [{"kind": "match", "ref_iid": m["iid"]},
                                                                  {"kind": "team", "ref_iid": {"$in": [m["home_iid"], m["away_iid"]]}}]}, {"user_id": 1})}
        if not uids:
            continue
        teams = Q._names(db, "teams", [m["home_iid"], m["away_iid"]])
        h, a = (teams.get(m["home_iid"]) or {}).get("name", "?"), (teams.get(m["away_iid"]) or {}).get("name", "?")
        what = GOALS.get(e["type"]) or REDS.get(e["type"])
        score = f"{h} {m['live'].get('hs', 0)}-{m['live'].get('as', 0)} {a}"
        for u in _users(db, uids, "alert_goals"):
            sent += _send(db, f"live:{u['id']}:{e['fixture_sid']}:{e['eid']}", u, "goal_alert",
                          {"what": what, "detail": f"{e.get('minute') or ''} {e.get('player_name') or ''}".strip(), "score": score, "path": f"/match/{m['id']}"})
    return sent


def run(db, now=None) -> dict:
    now = now or datetime.now(timezone.utc)
    return {"lineups": lineups(db, now), "goals": goals(db, now)}
