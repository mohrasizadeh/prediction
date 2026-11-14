"""match_context.py -- results form and what is at stake, per club and match (docs/22).

Both were tested on 46,000 English league matches and improve the win/draw/loss forecast a little but reliably:
  * results form: points in the last 5 league games minus the points we expected (from our own stored pre-match
    probabilities, so it measures over- or under-performance, not just good or bad results);
  * stakes, late in the season (8 games or fewer left): nothing left to play for, in a relegation fight, in the race
    at the top. A side facing a club with nothing to play for scores about 10% more.
The engine applies them to expected goals (soccer_brain/engine.py, MATCH_CONTEXT_COEF). Here we only compute the
inputs from our database, using information known before kick-off.
"""
from __future__ import annotations

import settings_store as S

FORM_N = 5
LATE = 8


def _xpts(prob: dict | None, home: bool) -> float | None:
    if not prob or prob.get("p_home") is None:
        return None
    return 3 * prob["p_home"] + prob["p_draw"] if home else 3 * prob["p_away"] + prob["p_draw"]


def _places(db, league: dict) -> tuple[int, int]:
    cfg = (S.get(db, "context.stakes_places") or {}).get(str(league.get("iid")), {})
    return int(cfg.get("upper", 6)), int(cfg.get("relegation", 3))


def league_context(db, league: dict, before) -> dict:
    """{team_iid: {fp, dead, rel, race, why}} for every club of the league, from matches finished before `before`."""
    season = league.get("current_season")
    ms = list(db.matches.find({"league_iid": league["iid"], "season": season, "status": "final", "kickoff": {"$lt": before},
                               "hg": {"$ne": None}}, {"_id": 0, "iid": 1, "kickoff": 1, "home_iid": 1, "away_iid": 1, "hg": 1, "ag": 1}).sort("kickoff", 1))
    teams = {t for m in ms for t in (m["home_iid"], m["away_iid"])}
    teams |= {t for m in db.matches.find({"league_iid": league["iid"], "season": season}, {"home_iid": 1, "away_iid": 1}) for t in (m["home_iid"], m["away_iid"])}
    probs = {}
    for p in db.match_probs.find({"match_iid": {"$in": [m["iid"] for m in ms]}}, {"_id": 0, "match_iid": 1, "p_home": 1, "p_draw": 1, "p_away": 1, "at": 1}).sort("at", 1):
        probs[p["match_iid"]] = p                                  # the last forecast made before the match
    hist = {t: [] for t in teams}
    table = {t: [0, 0] for t in teams}
    for m in ms:
        for t, gf, ga, home in ((m["home_iid"], m["hg"], m["ag"], True), (m["away_iid"], m["ag"], m["hg"], False)):
            pts = 3 if gf > ga else 1 if gf == ga else 0
            hist[t].append((pts, _xpts(probs.get(m["iid"]), home)))
            table[t][0] += pts; table[t][1] += 1
    n = len(teams)
    total = 2 * (n - 1)
    # Games left, counted from the fixture list where it is stored. `2 * (n - 1)` assumes a plain
    # double round robin: Scotland (12 clubs, 38 games) was "late season" after 14 and flagged
    # mid-table sides as having nothing to play for in autumn, and MLS never reached late season.
    # API-Football lists a season's fixtures in full, so each club's remaining scheduled matches
    # are the real number; the formula is only the fallback for a season whose list is not stored.
    remaining = {t: 0 for t in teams}
    for m in db.matches.find({"league_iid": league["iid"], "season": season, "status": "scheduled"},
                             {"_id": 0, "home_iid": 1, "away_iid": 1}):
        for t in (m["home_iid"], m["away_iid"]):
            if t in remaining:
                remaining[t] += 1
    listed = any(remaining.values())
    # Stakes are a league's question. A cup or a group stage has no "nothing left to play for".
    if league.get("kind") not in (None, "league"):
        n = 0
    upper, releg = _places(db, league)
    order = sorted((v[0] for v in table.values()), reverse=True)
    out = {}
    for t in teams:
        last = [x for x in hist[t] if x[1] is not None][-FORM_N:]
        fp = (sum(p for p, _ in last) - sum(x for _, x in last)) / len(last) if len(last) >= 3 else 0.0
        pts, played = table[t]
        left = remaining.get(t, 0) if listed else total - played
        dead = rel = race = 0
        why = []
        if 0 < left <= LATE and n >= upper + releg + 2 and len(order) == n:
            upper_pts = order[upper - 1]; safe_pts = order[n - releg - 1]
            can_up = pts + 3 * left >= upper_pts
            in_danger = (pts - safe_pts) <= 1.5 * left and pts <= order[n // 2]
            rel = int(in_danger)
            race = int(pts >= upper_pts - 3 and pts + 3 * left >= order[0])
            dead = int(not can_up and not in_danger)
            if dead: why.append("Nothing left to play for this season.")
            if rel: why.append("In a relegation fight.")
            if race: why.append("In the race at the top.")
        if len(last) >= 3 and abs(fp) >= 0.5:
            why.append(f"{'Above' if fp > 0 else 'Below'} expectations lately: {abs(fp) * len(last):.0f} points {'more' if fp > 0 else 'fewer'} than expected in the last {len(last)}.")
        out[t] = {"fp": round(fp, 3), "dead": dead, "rel": rel, "race": race, "left": left, "why": why}
    return out
