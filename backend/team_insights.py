"""team_insights.py -- every club in a league side by side, and two clubs compared (update pack part A).

Reads only our stored team_match_stats (PitchAPI data already in MongoDB). No provider calls.
"""
from __future__ import annotations

import queries as Q

# key, label, which way is better ("high" / "low" / None for neutral)
STATS = [
    ("goals", "Goals", "high"), ("goals_against", "Goals against", "low"),
    ("xg", "Expected goals", "high"), ("xg_against", "Expected goals against", "low"),
    ("shots", "Shots", "high"), ("shots_against", "Shots against", "low"),
    ("sot", "On target", "high"), ("sot_against", "On target against", "low"),
    ("corners", "Corners", "high"), ("corners_against", "Corners against", "low"),
    ("poss", "Possession %", "high"), ("tackles", "Tackles", None),
    ("fouls", "Fouls", None), ("yellow_cards", "Yellow cards", None),
]
KEYS = [k for k, _, _ in STATS]
WINDOWS = {"season": None, "last10": 10, "last5": 5}
RADAR = [("xg", "Attack"), ("shots", "Shots"), ("sot", "On target"), ("poss", "Possession"), ("xg_against", "Defence"), ("corners", "Corners")]
BETTER = {k: b for k, _, b in STATS}
LABEL = {k: l for k, l, _ in STATS}


def _season_matches(db, league_iid):
    lg = db.leagues.find_one({"iid": league_iid}, {"current_season": 1}) or {}
    q = {"league_iid": league_iid, "status": "final"}
    if lg.get("current_season"):
        q["season"] = lg["current_season"]
    return {m["iid"] for m in db.matches.find(q, {"iid": 1})}


def _rows(db, league_iid, window, venue):
    mids = _season_matches(db, league_iid)
    q = {"league_iid": league_iid, "match_iid": {"$in": list(mids)}}
    if venue in ("home", "away"):
        q["home"] = venue == "home"
    by = {}
    for r in db.team_match_stats.find(q, {"_id": 0}).sort("kickoff", -1):
        by.setdefault(r["team_iid"], []).append(r)
    n = WINDOWS.get(window)
    return {t: (rs[:n] if n else rs) for t, rs in by.items()}


def _avg(rs, k):
    vals = [r[k] for r in rs if r.get(k) is not None]
    return round(sum(vals) / len(vals), 2) if vals else None


def _form(rs):
    out = []
    for r in rs[:5]:
        g, ga = r.get("goals"), r.get("goals_against")
        if g is None or ga is None:
            continue
        out.append("W" if g > ga else "D" if g == ga else "L")
    return out


def _pcts(values: dict):
    """Per stat, 0..1 position in the league by value (1 = highest value)."""
    out = {t: {} for t in values}
    for k in KEYS:
        vs = sorted(v[k] for v in values.values() if v.get(k) is not None)
        for t, v in values.items():
            x = v.get(k)
            if x is None or len(vs) < 2:
                out[t][k] = None
                continue
            below = sum(1 for y in vs if y < x); eq = sum(1 for y in vs if y == x)
            out[t][k] = round((below + (eq - 1) / 2) / (len(vs) - 1), 3)
    return out


def matrix(db, league_iid, window="season", venue="all"):
    rows = _rows(db, league_iid, window, venue)
    values = {t: {k: _avg(rs, k) for k in KEYS} for t, rs in rows.items()}
    pcts = _pcts(values)
    names = Q._names(db, "teams", list(rows))
    teams = [{"team": {k: names[t].get(k) for k in ("id", "name", "image")}, "games": len(rs), "form": _form(rs),
              "values": values[t], "pct": pcts[t]} for t, rs in rows.items() if t in names]
    teams.sort(key=lambda x: x["team"]["name"])
    return {"window": window, "venue": venue, "stats": [{"key": k, "label": l, "better": b} for k, l, b in STATS], "teams": teams}


def _good(k, p):
    """League position turned so 1 = the better end (for low-is-better stats it flips)."""
    if p is None:
        return None
    return round(1 - p, 3) if BETTER.get(k) == "low" else p


def _side(db, team, window, venue):
    m = matrix(db, team["league_iid"], window, venue)
    row = next((r for r in m["teams"] if r["team"]["id"] == team["id"]), None)
    return row


def compare(db, a_id, b_id, window="season", as_fixture=False):
    ta = db.teams.find_one({"id": a_id}, {"_id": 0, "iid": 1, "id": 1, "league_iid": 1, "name": 1})
    tb = db.teams.find_one({"id": b_id}, {"_id": 0, "iid": 1, "id": 1, "league_iid": 1, "name": 1})
    if not ta or not tb:
        return None
    va, vb = ("home", "away") if as_fixture else ("all", "all")
    ra, rb = _side(db, ta, window, va), _side(db, tb, window, vb)
    names = Q._names(db, "teams", [ta["iid"], tb["iid"]])
    pub = lambda t: {k: names[t["iid"]].get(k) for k in ("id", "name", "image")}  # noqa: E731
    out = {"a": {"team": pub(ta), "row": ra, "venue": va}, "b": {"team": pub(tb), "row": rb, "venue": vb},
           "window": window, "as_fixture": as_fixture, "same_league": ta["league_iid"] == tb["league_iid"],
           "radar": [], "edges": [], "stands_out": []}
    if not ra or not rb:
        return out
    out["radar"] = [{"key": k, "label": l, "a": _good(k, ra["pct"].get(k)), "b": _good(k, rb["pct"].get(k))} for k, l in RADAR]
    gaps = []
    for k, l, b in STATS:
        x, y = ra["values"].get(k), rb["values"].get(k)
        if x is None or y is None:
            continue
        lean = None
        if b and x != y:
            lean = "a" if (x > y) == (b == "high") else "b"
        out["edges"].append({"key": k, "label": l, "a": x, "b": y, "lean": lean})
        ga, gb = _good(k, ra["pct"].get(k)), _good(k, rb["pct"].get(k))
        if b and ga is not None and gb is not None:
            gaps.append((abs(ga - gb), k, l, x, y))
    gaps.sort(reverse=True)
    an, bn = names[ta["iid"]]["name"], names[tb["iid"]]["name"]
    for gap, k, l, x, y in gaps[:4]:
        if gap < 0.25:
            break
        better = an if ((x > y) == (BETTER[k] == "high")) else bn
        out["stands_out"].append(f"{l}: {an} {x} a game, {bn} {y}. Clear edge to {better}.")
    return out
