"""cards_model.py -- yellow-card forecasts, kept apart from soccer_brain (owner's choice).

Player: P(at least one yellow) from a shrunk per-90 yellow rate x expected minutes x chance to play x referee factor,
blended with his normalised fouls a game. Likely starters (tier_basis likely_starter) count as playing.
Match: P(total yellows > 3.5 / 4.5) from Poisson team rates: card history blended with normalised fouls
(opponent-adjusted), x referee factor x importance of the game x the team's next matches.
Referee factor = referee's yellows per foul (shrunk to the league) / league yellows per foul; if fouls are missing,
yellows a game. Unknown referee -> 1.0.
Written into `forecasts` like engine output, so cards, the Finder and the Track Record treat them the same way.
"""
from __future__ import annotations

import math
import uuid

import numpy as np

import settings_store as S
import team_norm as TN
from engine_bridge import tier   # soccer_brain/core.tier, via the bridge's import path
from cached_fetch import utcnow

K_REF, K_TEAM, K_P90 = 6.0, 6.0, 8.0
MATCH_THR = (3.5, 4.5)
IMP_UP, IMP_DOWN = 1.08, 0.92                       # relegation fight / title race vs nothing left to play for
NEXT_MULT = {"high": 0.92, "medium": 0.96}          # a bigger match soon or a busy run: players avoid a booking


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
    pm = list(db.player_match_stats.find({"match_iid": {"$in": ids}, "minutes": {"$gt": 0}}, {"pos": 1, "yellow_cards": 1, "minutes": 1, "fouls_committed": 1}))
    pos = {}
    for r in pm:
        p = pos.setdefault(r.get("pos") or "?", [0, 0, 0, 0])
        p[0] += r.get("yellow_cards") or 0; p[1] += r["minutes"]
        if r.get("fouls_committed") is not None:
            p[2] += r["fouls_committed"]; p[3] += r["minutes"]
    # referee yellows per foul, from finished matches with both sides' yellows and fouls
    per_match = {}
    for r in db.team_match_stats.find({"league_iid": league_iid, "yellow_cards": {"$ne": None}, "fouls": {"$ne": None}}, {"match_iid": 1, "yellow_cards": 1, "fouls": 1}):
        s = per_match.setdefault(r["match_iid"], [0, 0, 0]); s[0] += r["yellow_cards"]; s[1] += r["fouls"]; s[2] += 1
    refs, ty, tf, nm = {}, 0.0, 0.0, 0
    for mm in db.matches.find({"iid": {"$in": [k for k, v in per_match.items() if v[2] == 2]}, "status": "final"}, {"iid": 1, "referee": 1}):
        y, f, _ = per_match[mm["iid"]]
        ty += y; tf += f; nm += 1
        if mm.get("referee"):
            rr = refs.setdefault(str(mm["referee"]).strip(), [0.0, 0.0, 0]); rr[0] += y; rr[1] += f; rr[2] += 1
    return {"ids": set(ids), "avg_team": avg_t, "team": team, "ref_avg": ev_y / n_ev if n_ev else 2 * avg_t,
            "pos90": {k: v[0] / (v[1] / 90) for k, v in pos.items() if v[1] > 0},
            "posf90": {k: v[2] / (v[3] / 90) for k, v in pos.items() if v[3] > 0 and v[2] > 0},
            "fouls": TN.build(db, league_iid, "fouls", half=float(S.get(db, "engine.style_half_life")) or 20.0),
            "ref_cpf": refs, "cpf": ty / tf if tf else None, "fouls_pg": tf / nm if nm else None,
            "ratings": ratings_fit(db, league_iid)}


def ratings_fit(db, league_iid: int):
    """Attack/defence ratings for yellows (docs/33): ridge Poisson, older games count less, one home factor.
    Returns (model, {team_iid: index}) or None when there is too little data."""
    import sys, os
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "soccer_brain"))
    from ratings import RatingsModel, HALF, LAM
    by = {}
    for r in db.team_match_stats.find({"league_iid": league_iid, "yellow_cards": {"$ne": None}},
                                      {"_id": 0, "match_iid": 1, "team_iid": 1, "home": 1, "kickoff": 1, "yellow_cards": 1}):
        by.setdefault(r["match_iid"], []).append(r)
    g = [v for v in by.values() if len(v) == 2 and any(x.get("home") for x in v)]
    if len(g) < 60:
        return None
    days = sorted({str(v[0]["kickoff"])[:10] for v in g})
    rank = {d: i for i, d in enumerate(days)}
    teams = sorted({x["team_iid"] for v in g for x in v})
    ti = {t: i for i, t in enumerate(teams)}
    H, A, yh, ya, rd = [], [], [], [], []
    for v in g:
        h = next(x for x in v if x.get("home")); a = next(x for x in v if x is not h)
        H.append(ti[h["team_iid"]]); A.append(ti[a["team_iid"]]); yh.append(h["yellow_cards"]); ya.append(a["yellow_cards"])
        rd.append(rank[str(v[0]["kickoff"])[:10]])
    age = max(rd) - np.array(rd)
    m = RatingsModel(HALF["yellow"], LAM["yellow"]).fit(H, A, yh, ya, age, len(teams))
    return (m, ti) if m.ok else None


def ref_factor(db, league_iid, name, ln) -> tuple[float, str | None]:
    if not name:
        return 1.0, None
    rc = (ln.get("ref_cpf") or {}).get(name.strip())
    if rc and ln.get("cpf") and rc[1] > 0:                 # yellows per foul, shrunk to the league
        kf = K_REF * ln["fouls_pg"]
        shr = (rc[0] + kf * ln["cpf"]) / (rc[1] + kf)
        per = f"one yellow every {rc[1] / rc[0]:.1f} fouls" if rc[0] else "no yellows yet"
        return shr / ln["cpf"], f"Referee {name} shows {per} over {rc[2]} game{'s' if rc[2] != 1 else ''} (league: one every {1 / ln['cpf']:.1f})."
    r = db.referee_stats.find_one({"league_iid": league_iid, "referee": name})
    if not r or r.get("yellow_pg") is None:
        return 1.0, f"Referee {name} has no games on record here, so the league average is used."
    shr = (r["matches"] * r["yellow_pg"] + K_REF * ln["ref_avg"]) / (r["matches"] + K_REF)
    return shr / ln["ref_avg"], f"Referee {name} shows {r['yellow_pg']:.1f} yellows a game over {r['matches']} games (league {ln['ref_avg']:.1f})."


def team_context(db, m, team, name) -> tuple[float, float, list[str]]:
    """Importance of the game (stakes) and the team's next matches (rotation level), from match_context."""
    c = db.match_context.find_one({"match_iid": m["iid"], "team_iid": team}) or {}
    st = c.get("stakes") or {}
    imp, why = 1.0, []
    if st.get("rel") or st.get("race"):
        imp = IMP_UP
        why.append(f"{name} are {'in a relegation fight' if st.get('rel') else 'in the race at the top'}, so challenges tend to be sharper.")
    elif st.get("dead"):
        imp = IMP_DOWN
        why.append(f"{name} have nothing left to play for, which usually means fewer cards.")
    nxt = NEXT_MULT.get(c.get("level"), 1.0)
    if nxt < 1.0:
        gap = c.get("next_gap")
        why.append(f"{name} play again in {gap:.0f} days, so players often avoid a booking." if gap is not None else f"{name} have a busy run of matches, so players often avoid a booking.")
    return imp, nxt, why


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
    db.forecasts.delete_many({"match_iid": m["iid"], "stat": {"$in": ["yellow_cards", "match_yellow_cards"]}})   # one row per forecast (docs/21)
    h, a, avg = m["home_iid"], m["away_iid"], ln["avg_team"]
    shr = lambda t, i: (ln["team"].get(t, [0, 0, 0])[i] + K_TEAM * avg) / (ln["team"].get(t, [0, 0, 0])[2] + K_TEAM) / avg
    names = {t["iid"]: t["name"] for t in db.teams.find({"iid": {"$in": [h, a]}}, {"iid": 1, "name": 1})}
    fz = ln.get("fouls")
    fouls_ok = fz is not None and fz.cnt >= 20
    frel = lambda t, o: fz.predict(t, o) / fz.L() if fouls_ok else 1.0     # normalised fouls vs the league
    ctx = {t: team_context(db, m, t, names.get(t, "The team")) for t in (h, a)}
    lam_t = {t: avg * math.sqrt(shr(t, 0) * shr(o, 1) * frel(t, o)) * rf * ctx[t][0] * ctx[t][1] for t, o in ((h, a), (a, h))}
    if not fouls_ok:
        lam_t = {t: avg * shr(t, 0) * shr(o, 1) * rf * ctx[t][0] * ctx[t][1] for t, o in ((h, a), (a, h))}
    rb = float(S.get(db, "engine.cards_ratings_blend"))
    rat = ln.get("ratings") if rb > 0 else None
    if rat:
        rm, ti = rat
        if h in ti and a in ti:
            for t, o, is_h in ((h, a, True), (a, h, False)):
                base = avg * math.sqrt(shr(t, 0) * shr(o, 1) * (frel(t, o) if fouls_ok else 1.0))
                lam_t[t] *= (rm.mu(ti[t], ti[o], is_h) / max(base, 1e-6)) ** rb
    lam_h, lam_a = lam_t[h], lam_t[a]
    fouls_why = (f"Fouls a game, adjusted for opponents: {names.get(h)} {fz.usual(h):.1f}, {names.get(a)} {fz.usual(a):.1f} (league {fz.L():.1f})."
                 if fouls_ok else None)
    ctx_why = ctx[h][2] + ctx[a][2]
    docs = []
    if flags.get("match.yellow_cards", True):
        why = [f"{names.get(h)} average {ln['team'].get(h, [0, 0, 1])[0] / max(ln['team'].get(h, [0, 0, 1])[2], 1):.1f} yellows a game; {names.get(a)} {ln['team'].get(a, [0, 0, 1])[0] / max(ln['team'].get(a, [0, 0, 1])[2], 1):.1f}.",
               rwhy or "No referee named yet, so the league average is used.", *([fouls_why] if fouls_why else []), *ctx_why]
        for thr in MATCH_THR:
            lam = lam_h + lam_a
            docs.append(_doc(db, m, run_id, now, "team", h, a, None, None, "match_yellow_cards", thr, f"{thr + 0.5:g}+ yellow cards in the match",
                             lam, _pois_sf(thr, lam), 1.0, True, why, strong, solid))
    if flags.get("player.yellow_cards", True):
        seen = set()
        for f in db.forecasts.find({"match_iid": m["iid"], "is_current": True, "scope": "player", "model": {"$ne": "cards"}},
                                   {"player_iid": 1, "team_iid": 1, "opp_iid": 1, "pos": 1, "p_play": 1, "lineup_confirmed": 1, "tier_basis": 1}):
            pid = f["player_iid"]
            if pid in seen:
                continue
            seen.add(pid)
            g = list(db.player_match_stats.find({"player_iid": pid, "minutes": {"$gt": 0}}, {"match_iid": 1, "minutes": 1, "yellow_cards": 1, "fouls_committed": 1}).sort("kickoff", -1).limit(30))
            ev = [r for r in g if r["match_iid"] in ln["ids"]]
            mins = sum(r["minutes"] for r in g[:10]) / max(len(g[:10]), 1)
            y, m90 = sum(r.get("yellow_cards") or 0 for r in ev), sum(r["minutes"] for r in ev) / 90
            prior = ln["pos90"].get(f.get("pos") or "?", sum(ln["pos90"].values()) / max(len(ln["pos90"]), 1))
            rate = (y + K_P90 * prior) / (m90 + K_P90)
            opp_f = math.sqrt(shr(f["opp_iid"], 1))
            pf90 = ln.get("posf90", {}).get(f.get("pos") or "?")
            fe = [r for r in ev if r.get("fouls_committed") is not None]
            fm90 = sum(r["minutes"] for r in fe) / 90
            pfr = ((sum(r["fouls_committed"] for r in fe) + K_P90 * pf90) / (fm90 + K_P90) / pf90) if pf90 else 1.0
            imp, nxt, _ = ctx.get(f["team_iid"], (1.0, 1.0, []))
            lam = rate * mins / 90 * rf * opp_f * math.sqrt(pfr) * imp * nxt
            likely = f.get("tier_basis") == "likely_starter"
            earned = S.get(db, "engine.tier_mode") == "earned"
            play = 1.0 if (likely and not earned) else f["p_play"]    # classic: a likely starter has no discount. Earned tiers use the real chance to play (docs/31)
            p = play * (1 - math.exp(-lam))
            why = [f"{y} yellow card{'s' if y != 1 else ''} in his last {len(ev)} games with card data ({rate:.2f} a full game after blending with the {f.get('pos') or 'squad'} average).",
                   rwhy or "No referee named yet, so the league average is used."]
            if fe and pf90:
                why.append(f"He commits {(pfr * pf90):.1f} fouls a full game (the {f.get('pos') or 'squad'} average is {pf90:.1f}).")
            why += ctx.get(f["team_iid"], (1, 1, []))[2][:1]
            d = _doc(db, m, run_id, now, "player", f["team_iid"], f["opp_iid"], pid, f.get("pos"), "yellow_cards", 0.5, "Gets a yellow card",
                     lam, p, play, bool(f.get("lineup_confirmed")), why, strong, solid)
            d["lo"], d["hi"] = play * (1 - math.exp(-lam * 0.8)), play * (1 - math.exp(-lam * 1.2))
            d["tier"] = tier(p, d["lo"], d["lineup_confirmed"] or likely, strong=strong, solid=solid)
            d["tier_basis"] = "lineup" if d["lineup_confirmed"] else ("likely_starter" if likely else "pre")
            docs.append(d)
    if docs and S.get(db, "engine.tier_mode") == "earned":
        _retier(db, run_id, docs)
    if docs:
        db.forecasts.insert_many(docs)
    return len(docs)


_REC: dict = {}


def _retier(db, run_id, docs):
    """Earned tiers (docs/31). A card line's p already includes his chance to play, so it is the whole chance."""
    import tiering as TI
    if _REC.get("run") != run_id:
        _REC.update(run=run_id, rec=TI.Record(db, min_n=int(S.get(db, "engine.earned_min_n")), k=float(S.get(db, "engine.earned_prior_k"))))
    lineup = bool(S.get(db, "engine.strong_needs_lineup"))
    for d in docs:
        badge = None if d["scope"] == "team" else ("confirmed" if d["lineup_confirmed"] else "likely" if d.get("tier_basis") == "likely_starter" else "unsure")
        d["tier"], d["tier_note"] = TI.assign(db, _REC["rec"], {"p": d["p"], "lo": d["lo"], "scope": d["scope"], "stat": d["stat"], "p_play": None, "lineup_badge": badge}, lineup)


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
                            idem="booking-" + uid + "-" + "-".join(sorted(k.split(":", 1)[1] for k, _ in items)))
        if r.get("status") not in ("sent", "duplicate"):
            continue                                        # e-mail off, over the cap or failed: try again next run
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
