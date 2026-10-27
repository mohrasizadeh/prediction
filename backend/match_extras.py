"""match_extras.py -- per finished match: referee and stadium (/v1/matches/{id}) and events (/v1/matches/{id}/events).

Turned on by ingest.match_extra_detail / ingest.match_extra_events. Two calls per match, cached forever (finished
matches don't change). Writes: matches.referee/stadium/first_goal_side/extras_at, match_events, card / penalty /
substitution fields on player_match_stats and team_match_stats, and the referee_stats table per league.
"""
from __future__ import annotations

import settings_store as S
from cached_fetch import FOREVER, PitchClient, utcnow

CARD = {"yellowcard": "yellow", "redcard": "red", "yellowredcard": "red", "secondyellow": "red", "second_yellow": "red"}


def _kind(t: str) -> str | None:
    t = (t or "").lower().replace(" ", "")
    if t == "goal" or t == "penalty_goal":
        return "goal"
    if t in CARD or "red" in t:
        return CARD.get(t, "red")
    if t.startswith("sub"):
        return "sub"
    return None


def normalize_events(data: dict, home_ext: str, away_ext: str) -> list[dict]:
    out = []
    for e in (data or {}).get("events") or []:
        k = _kind(e.get("event_type"))
        side = "home" if e.get("team_id") == home_ext else "away" if e.get("team_id") == away_ext else None
        if not k or not side:
            continue
        p, pin = e.get("player") or {}, e.get("sub_in_player") or {}
        out.append({"type": k, "minute": e.get("minute"), "added": e.get("minute_added") or 0, "side": side,
                    "player_ext": p.get("id"), "player_name": p.get("name"), "in_ext": pin.get("id"), "in_name": pin.get("name"),
                    "own_goal": bool(e.get("is_own_goal")), "penalty": bool(e.get("is_penalty"))})
    out.sort(key=lambda x: ((x["minute"] or 0), x["added"], x["type"] == "red"))
    return dedupe(out)


def dedupe(ev: list[dict]) -> list[dict]:
    """A second yellow arrives as a yellow and a red at the same minute: keep only the red."""
    reds = {(e.get("player_iid") or e.get("player_ext"), e["minute"], e["added"]) for e in ev if e["type"] == "red"}
    return [e for e in ev if not (e["type"] == "yellow" and (e.get("player_iid") or e.get("player_ext"), e["minute"], e["added"]) in reds)]


def _pid(db, ext, name, team_iid):
    if not ext:
        return None
    d = db.players.find_one({"ext_id": ext}, {"iid": 1})
    if d:
        return d["iid"]
    from ingest import upsert_entity
    return upsert_entity(db, "players", ext, {"name": name, "team_iid": team_iid, "pos": None, "pos_raw": None})


def ingest_extras(client: PitchClient, match: dict) -> bool:
    db = client.db
    ext = match["ext_id"]
    home = db.teams.find_one({"iid": match["home_iid"]}); away = db.teams.find_one({"iid": match["away_iid"]})
    sets = {"extras_at": utcnow()}
    if S.get(db, "ingest.match_extra_detail"):
        d = client.fetch(f"/v1/matches/{ext}", ttl=FOREVER, purpose="match_detail")
        sets.update({"referee": (d.get("referee") or "").strip() or None, "stadium": (d.get("stadium") or "").strip() or None})
    if S.get(db, "ingest.match_extra_events"):
        ev = normalize_events(client.fetch(f"/v1/matches/{ext}/events", ttl=FOREVER, purpose="match_events"), home["ext_id"], away["ext_id"])
        tid = {"home": home["iid"], "away": away["iid"]}
        for e in ev:
            e["team_iid"] = tid[e["side"]]
            e["player_iid"] = _pid(db, e.pop("player_ext"), e["player_name"], e["team_iid"])
            e["in_iid"] = _pid(db, e.pop("in_ext"), e["in_name"], e["team_iid"])
        db.match_events.update_one({"match_iid": match["iid"]}, {"$set": {"match_iid": match["iid"], "league_iid": match["league_iid"],
                                                                         "kickoff": match["kickoff"], "events": ev}}, upsert=True)
        _apply(db, match, ev, tid)
        goals = [e for e in ev if e["type"] == "goal"]
        if goals:
            g = goals[0]
            sets["first_goal_side"] = ("away" if g["side"] == "home" else "home") if g["own_goal"] else g["side"]
            sets["first_scorer_iid"] = None if g["own_goal"] else g["player_iid"]
        else:
            sets["first_goal_side"], sets["first_scorer_iid"] = "none", None
    db.matches.update_one({"iid": match["iid"]}, {"$set": sets})
    return True


def _apply(db, match, ev, tid):
    per = {}
    team = {s: {"yellow_cards_ev": 0, "red_cards": 0, "pen_goals": 0, "own_goals_for": 0} for s in ("home", "away")}
    for e in ev:
        p = per.setdefault(e["player_iid"], {"yellow_cards": 0, "red_cards": 0, "pen_goals": 0, "goal_minutes": []}) if e["player_iid"] else None
        if e["type"] == "yellow":
            team[e["side"]]["yellow_cards_ev"] += 1
            if p: p["yellow_cards"] += 1
        elif e["type"] == "red":
            team[e["side"]]["red_cards"] += 1
            if p: p["red_cards"] += 1
        elif e["type"] == "goal" and e["own_goal"]:
            team["away" if e["side"] == "home" else "home"]["own_goals_for"] += 1
        elif e["type"] == "goal":
            if e["penalty"]:
                team[e["side"]]["pen_goals"] += 1
                if p: p["pen_goals"] += 1
            if p: p["goal_minutes"].append(e["minute"])
        elif e["type"] == "sub" and e["player_iid"]:
            p["sub_off"], p["replaced_by_iid"] = e["minute"], e["in_iid"]
            if e["in_iid"]:
                per.setdefault(e["in_iid"], {"yellow_cards": 0, "red_cards": 0, "pen_goals": 0, "goal_minutes": []}).update(
                    {"sub_on": e["minute"], "replaced_iid": e["player_iid"]})
    db.player_match_stats.update_many({"match_iid": match["iid"]}, {"$set": {"yellow_cards": 0, "red_cards": 0, "pen_goals": 0, "goal_minutes": [],
                                                                            "sub_on": None, "sub_off": None, "replaced_iid": None, "replaced_by_iid": None}})
    for pid, v in per.items():
        db.player_match_stats.update_one({"match_iid": match["iid"], "player_iid": pid}, {"$set": v})
    for s, v in team.items():
        o = "away" if s == "home" else "home"
        opp = db.team_match_stats.find_one({"match_iid": match["iid"], "team_iid": tid[o]}, {"yellow_cards": 1}) or {}
        v.update({"red_cards_against": team[o]["red_cards"], "pen_goals_against": team[o]["pen_goals"],
                  "yellow_cards_against": opp.get("yellow_cards") if opp.get("yellow_cards") is not None else team[o]["yellow_cards_ev"]})
        db.team_match_stats.update_one({"match_iid": match["iid"], "team_iid": tid[s]}, {"$set": v})


def reapply_all(db) -> int:
    """Re-derive card/sub fields from saved events (no API calls)."""
    n = 0
    for doc in db.match_events.find({}):
        m = db.matches.find_one({"iid": doc["match_iid"]})
        ev = dedupe(doc["events"])
        db.match_events.update_one({"_id": doc["_id"]}, {"$set": {"events": ev}})
        _apply(db, m, ev, {"home": m["home_iid"], "away": m["away_iid"]})
        n += 1
    for lg in {d["league_iid"] for d in db.match_events.find({}, {"league_iid": 1})}:
        rebuild_referees(db, lg)
    return n


def rebuild_referees(db, league_iid: int) -> int:
    rows = {}
    for m in db.matches.find({"league_iid": league_iid, "referee": {"$nin": [None, ""]}, "hg": {"$ne": None}},
                             {"iid": 1, "referee": 1, "hg": 1, "ag": 1, "kickoff": 1}):
        r = rows.setdefault(m["referee"], {"matches": 0, "yellow": 0, "red": 0, "pens": 0, "home_wins": 0, "with_events": 0, "last": None})
        r["matches"] += 1
        r["home_wins"] += m["hg"] > m["ag"]
        r["last"] = max(filter(None, [r["last"], m["kickoff"]]))
        ev = db.match_events.find_one({"match_iid": m["iid"]}, {"events": 1})
        if ev:
            r["with_events"] += 1
            for e in ev["events"]:
                r["yellow"] += e["type"] == "yellow"
                r["red"] += e["type"] == "red"
                r["pens"] += e["type"] == "goal" and e["penalty"]
    db.referee_stats.delete_many({"league_iid": league_iid})
    for name, r in rows.items():
        n = r["with_events"] or None
        db.referee_stats.insert_one({"league_iid": league_iid, "referee": name, "name": name, "matches": r["matches"], "last_match": r["last"],
                                     "yellow_pg": r["yellow"] / n if n else None, "red_pg": r["red"] / n if n else None,
                                     "pens_pg": r["pens"] / n if n else None, "home_win_pct": r["home_wins"] / r["matches"]})
    return len(rows)


def backfill(db) -> int:
    """Queue every ingested match that has no extras yet. Newest first so recent games show soonest."""
    from ingest import enqueue
    n = 0
    for m in db.matches.find({"ingested_at": {"$ne": None}, "extras_at": None}, {"ext_id": 1, "iid": 1, "kickoff": 1}).sort("kickoff", -1):
        enqueue(db, "match_extras", m["ext_id"], priority=8, payload={"match_iid": m["iid"]})
        n += 1
    return n


def status(db) -> dict:
    on = bool(S.get(db, "ingest.match_extra_detail")) + bool(S.get(db, "ingest.match_extra_events"))
    left = db.ingest_queue.count_documents({"task": "match_extras", "status": "pending"})
    return {"detail": bool(S.get(db, "ingest.match_extra_detail")), "events": bool(S.get(db, "ingest.match_extra_events")),
            "done": db.matches.count_documents({"extras_at": {"$ne": None}}), "ingested": db.matches.count_documents({"ingested_at": {"$ne": None}}),
            "pending": left, "calls_needed": left * on, "calls_per_new_match": on,
            "daily_budget": S.get(db, "ingest.daily_call_budget")}
