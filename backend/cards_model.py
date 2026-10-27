"""cards_model.py -- yellow-card forecasts, kept apart from soccer_brain (owner's choice).

Player: P(at least one yellow) from a shrunk per-90 yellow rate x expected minutes x chance to play x referee factor.
Match: P(total yellows > 3.5 / 4.5) from Poisson team rates (cards for, cards drawn) x referee factor.
Referee factor = referee's yellows a game (shrunk to the league) / league average. Unknown referee -> 1.0.
Written into `forecasts` like engine output, so cards, the Finder and the Track Record treat them the same way.
"""
from __future__ import annotations

import math
import uuid

import settings_store as S
from engine_bridge import tier   # soccer_brain/core.tier, via the bridge's import path
from cached_fetch import utcnow

K_REF, K_TEAM, K_P90 = 6.0, 6.0, 8.0
MATCH_THR = (3.5, 4.5)


def _pois_sf(thr: float, lam: float) -> float:
    k = int(math.floor(thr))
    return max(0.0, 1.0 - sum(math.exp(-lam) * lam ** i / math.factorial(i) for i in range(k + 1)))


def league_numbers(db, league_iid: int) -> dict | None:
    ids = [d["match_iid"] for d in db.match_events.find({"league_iid": league_iid}, {"match_iid": 1})]
    if len(ids) < 30:
        return None
    rows = list(db.team_match_stats.find({"match_iid": {"$in": ids}, "yellow_cards": {"$ne": None}}, {"team_iid": 1, "yellow_cards": 1, "yellow_cards_against": 1}))
    if not rows:
        return None
    avg_t = sum(r["yellow_cards"] for r in rows) / len(rows)
    team = {}
    for r in rows:
        t = team.setdefault(r["team_iid"], [0, 0, 0])
        t[0] += r["yellow_cards"]; t[1] += r.get("yellow_cards_against") or 0; t[2] += 1
    ev_y = n_ev = 0
    for d in db.match_events.find({"league_iid": league_iid}, {"events.type": 1}):
        n_ev += 1; ev_y += sum(1 for e in d["events"] if e["type"] == "yellow")
    pm = list(db.player_match_stats.find({"match_iid": {"$in": ids}, "minutes": {"$gt": 0}}, {"pos": 1, "yellow_cards": 1, "minutes": 1}))
    pos = {}
    for r in pm:
        p = pos.setdefault(r.get("pos") or "?", [0, 0])
        p[0] += r.get("yellow_cards") or 0; p[1] += r["minutes"]
    return {"ids": set(ids), "avg_team": avg_t, "team": team, "ref_avg": ev_y / n_ev if n_ev else 2 * avg_t,
            "pos90": {k: v[0] / (v[1] / 90) for k, v in pos.items() if v[1] > 0}}


def ref_factor(db, league_iid, name, ln) -> tuple[float, str | None]:
    if not name:
        return 1.0, None
    r = db.referee_stats.find_one({"league_iid": league_iid, "referee": name})
    if not r or r.get("yellow_pg") is None:
        return 1.0, f"Referee {name} has no games on record here, so the league average is used."
    shr = (r["matches"] * r["yellow_pg"] + K_REF * ln["ref_avg"]) / (r["matches"] + K_REF)
    return shr / ln["ref_avg"], f"Referee {name} shows {r['yellow_pg']:.1f} yellows a game over {r['matches']} games (league {ln['ref_avg']:.1f})."


def _kept(db, fkey):
    last = db.forecasts.find_one({"fkey": fkey}, sort=[("created_at", -1)])
    return {k: last.get(k) for k in ("hidden_reason", "hidden_by", "hidden_at")} if last and last.get("hidden") else None


def _doc(db, m, run_id, now, scope, team, opp, player, pos, stat, thr, market, lam, p, play, confirmed, reasons, strong, solid):
    lo, hi = _pois_sf(thr, lam * 0.8), _pois_sf(thr, lam * 1.2)
    fkey = f"{m['iid']}:{scope}:{team}:{player or 0}:{stat}:{thr:g}"
    d = {"id": str(uuid.uuid4()), "fkey": fkey, "run_id": run_id, "match_iid": m["iid"], "league_iid": m["league_iid"], "kickoff": m["kickoff"],
         "scope": scope, "team_iid": int(team), "opp_iid": int(opp), "player_iid": player, "pos": pos, "stat": stat, "thr": float(thr),
         "market": market, "expected": float(lam), "p": float(p), "lo": float(min(lo, p)), "hi": float(max(hi, p)), "p_play": float(play),
         "lineup_confirmed": confirmed, "tier": tier(p, min(lo, p), confirmed, strong=strong, solid=solid), "reasons": reasons,
         "opp_tactics": [], "own_tactics": [], "opp_key_players": [], "contrib": {}, "rotation": None, "rotation_why": None,
         "p_play_usual": None, "p_raw": float(p), "p_base": float(p), "is_current": True, "hidden": False, "created_at": now, "model": "cards"}
    k = _kept(db, fkey)
    if k:
        d.update(k, hidden=True)
    return d


def run_match(db, m, run_id=None, now=None, ln=None) -> int:
    flags = S.get(db, "engine.markets_enabled")
    ln = ln or league_numbers(db, m["league_iid"])
    if not ln:
        return 0
    now = now or utcnow(); run_id = run_id or f"cards-{uuid.uuid4()}"
    strong = tuple(S.get(db, "engine.tier_strong")); solid = tuple(S.get(db, "engine.tier_solid"))
    rf, rwhy = ref_factor(db, m["league_iid"], m.get("referee"), ln)
    db.forecasts.update_many({"match_iid": m["iid"], "is_current": True, "stat": {"$in": ["yellow_cards", "match_yellow_cards"]}}, {"$set": {"is_current": False}})
    h, a, avg = m["home_iid"], m["away_iid"], ln["avg_team"]
    shr = lambda t, i: (ln["team"].get(t, [0, 0, 0])[i] + K_TEAM * avg) / (ln["team"].get(t, [0, 0, 0])[2] + K_TEAM) / avg
    lam_h, lam_a = avg * shr(h, 0) * shr(a, 1) * rf, avg * shr(a, 0) * shr(h, 1) * rf
    names = {t["iid"]: t["name"] for t in db.teams.find({"iid": {"$in": [h, a]}}, {"iid": 1, "name": 1})}
    docs = []
    if flags.get("match.yellow_cards", True):
        why = [f"{names.get(h)} average {ln['team'].get(h, [0, 0, 1])[0] / max(ln['team'].get(h, [0, 0, 1])[2], 1):.1f} yellows a game; {names.get(a)} {ln['team'].get(a, [0, 0, 1])[0] / max(ln['team'].get(a, [0, 0, 1])[2], 1):.1f}.",
               rwhy or "No referee named yet, so the league average is used."]
        for thr in MATCH_THR:
            lam = lam_h + lam_a
            docs.append(_doc(db, m, run_id, now, "team", h, a, None, None, "match_yellow_cards", thr, f"{thr + 0.5:g}+ yellow cards in the match",
                             lam, _pois_sf(thr, lam), 1.0, True, why, strong, solid))
    if flags.get("player.yellow_cards", True):
        seen = set()
        for f in db.forecasts.find({"match_iid": m["iid"], "is_current": True, "scope": "player", "model": {"$ne": "cards"}},
                                   {"player_iid": 1, "team_iid": 1, "opp_iid": 1, "pos": 1, "p_play": 1, "lineup_confirmed": 1}):
            pid = f["player_iid"]
            if pid in seen:
                continue
            seen.add(pid)
            g = list(db.player_match_stats.find({"player_iid": pid, "minutes": {"$gt": 0}}, {"match_iid": 1, "minutes": 1, "yellow_cards": 1}).sort("kickoff", -1).limit(30))
            ev = [r for r in g if r["match_iid"] in ln["ids"]]
            mins = sum(r["minutes"] for r in g[:10]) / max(len(g[:10]), 1)
            y, m90 = sum(r.get("yellow_cards") or 0 for r in ev), sum(r["minutes"] for r in ev) / 90
            prior = ln["pos90"].get(f.get("pos") or "?", sum(ln["pos90"].values()) / max(len(ln["pos90"]), 1))
            rate = (y + K_P90 * prior) / (m90 + K_P90)
            opp_f = math.sqrt(shr(f["opp_iid"], 1))
            lam = rate * mins / 90 * rf * opp_f
            p = f["p_play"] * (1 - math.exp(-lam))
            why = [f"{y} yellow card{'s' if y != 1 else ''} in his last {len(ev)} games with card data ({rate:.2f} a full game after blending with the {f.get('pos') or 'squad'} average).",
                   rwhy or "No referee named yet, so the league average is used."]
            d = _doc(db, m, run_id, now, "player", f["team_iid"], f["opp_iid"], pid, f.get("pos"), "yellow_cards", 0.5, "Gets a yellow card",
                     lam, p, f["p_play"], bool(f.get("lineup_confirmed")), why, strong, solid)
            d["lo"], d["hi"] = f["p_play"] * (1 - math.exp(-lam * 0.8)), f["p_play"] * (1 - math.exp(-lam * 1.2))
            d["tier"] = tier(p, d["lo"], d["lineup_confirmed"], strong=strong, solid=solid)
            docs.append(d)
    if docs:
        db.forecasts.insert_many(docs)
    return len(docs)


def run_league(db, league_iid: int, run_id=None, now=None) -> int:
    ln = league_numbers(db, league_iid)
    if not ln:
        return 0
    now = now or utcnow()
    from datetime import timedelta
    n = 0
    for m in db.matches.find({"league_iid": league_iid, "status": "scheduled", "kickoff": {"$gte": now - timedelta(hours=1),
                              "$lte": now + timedelta(days=S.get(db, "engine.window_days"))}}):
        n += run_match(db, m, run_id, now, ln)
    try:
        notify_bookings(db, league_iid)
    except Exception:   # an e-mail problem never blocks forecasts
        pass
    return n


TOP_N, MIN_P = 10, 0.2


def notify_bookings(db, league_iid: int) -> int:
    """E-mail followers once per player and match when the player is in the league's top 10 booking risks."""
    import emailer as E
    from queries import booking_risk
    rows = [f for f in booking_risk(db, league_iid, limit=TOP_N)["rows"] if f["p"] >= MIN_P and f.get("player")]
    if not rows:
        return 0
    per_user: dict = {}
    for f in rows:
        for fo in db.follows.find({"kind": "player", "ref_iid": f["player_iid"]}, {"user_id": 1}):
            key = f"{fo['user_id']}:{f['player_iid']}:{f['match_iid']}"
            if db.booking_alerts.find_one({"_id": key}):
                continue
            per_user.setdefault(fo["user_id"], []).append((key, f))
    sent = 0
    for uid, items in per_user.items():
        u = db.users.find_one({"id": uid, "disabled": {"$ne": True}})
        if not u or not u.get("email_verified") or (u.get("prefs") or {}).get("alert_emails", True) is False:
            continue
        names = ", ".join(f"{f['player']['name']} ({round(f['p'] * 100)}% v {f['opp']['name'] if f.get('opp') else 'next opponent'})" for _, f in items)
        r = E.send_template(db, "booking_alert", to=u["email"], user=u, vars={"players": names, "link": E.base_url() + "/following"},
                            idem=f"booking-{uid}-{items[0][1]['match_iid']}")
        for key, _ in items:
            db.booking_alerts.update_one({"_id": key}, {"$set": {"at": utcnow(), "status": r.get("status")}}, upsert=True)
        sent += r.get("status") == "sent"
    return sent


def fill_match_totals(db) -> int:
    """match_yellow_cards on both team rows = home + away yellows (feed), so the Track Record can grade it."""
    n = 0
    for m in db.matches.find({"status": "final", "ingested_at": {"$ne": None}}, {"iid": 1}):
        rows = list(db.team_match_stats.find({"match_iid": m["iid"]}, {"yellow_cards": 1}))
        if len(rows) == 2 and all(r.get("yellow_cards") is not None for r in rows):
            db.team_match_stats.update_many({"match_iid": m["iid"]}, {"$set": {"match_yellow_cards": rows[0]["yellow_cards"] + rows[1]["yellow_cards"]}})
            n += 1
    return n


def plan_referees(db, now=None) -> int:
    """Upcoming matches within 30 hours with no referee yet: check at most twice, 12 hours apart."""
    from datetime import timedelta
    from ingest import enqueue
    now = now or utcnow(); n = 0
    for m in db.matches.find({"status": "scheduled", "referee": {"$in": [None, ""]}, "kickoff": {"$gt": now, "$lte": now + timedelta(hours=30)},
                              "referee_checks": {"$not": {"$gte": 2}}}, {"ext_id": 1, "referee_checked_at": 1}):
        if m.get("referee_checked_at") and now - m["referee_checked_at"] < timedelta(hours=12):
            continue
        enqueue(db, "match_referee", m["ext_id"], priority=4, payload={})
        db.ingest_queue.update_one({"task": "match_referee", "key": m["ext_id"], "status": {"$ne": "pending"}},
                                   {"$set": {"status": "pending", "attempts": 0, "next_run_at": now}})
        n += 1
    return n


def check_referee(client, m) -> bool:
    from datetime import timedelta
    db = client.db
    d = client.fetch(f"/v1/matches/{m['ext_id']}", ttl=timedelta(hours=6), purpose="match_referee")
    ref = (d.get("referee") or "").strip() or None
    db.matches.update_one({"iid": m["iid"]}, {"$set": {"referee_checked_at": utcnow(), **({"referee": ref} if ref else {}),
                                                         **({"stadium": d.get("stadium")} if d.get("stadium") else {})}, "$inc": {"referee_checks": 1}})
    if ref and ref != m.get("referee"):
        run_match(db, {**m, "referee": ref})
    return True
