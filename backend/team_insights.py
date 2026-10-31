"""team_insights.py -- every club in a league side by side, and two clubs compared (update pack part A).

Reads only our stored team_match_stats (PitchAPI data already in MongoDB). No provider calls.
"""
from __future__ import annotations

import os
import sys
import time

import numpy as np

import queries as Q

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "soccer_brain"))
from ratings import RatingsModel  # noqa: E402

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


# ---------------------------------------------------------------- radar (docs/35)
# Each axis is the club's place in its league, 0 = bottom, 1 = top, from an opponent-adjusted rating, not a raw average.
# A raw per-game average rewards a soft schedule, jumps around early in the season, and leaves a club with a missing
# number (no expected goals from the feed) as an empty spoke. Here every club is rated together from all stored
# matches (older games count less, a few games pull a club towards the league average), and goals stand in for expected goals
# when most clubs have none.
RADAR_AXES = [("attack", "Attack", "Goals we would expect against an average side, adjusted for who they played."),
              ("shots", "Shots", "Shots a game against an average side."),
              ("sot", "On target", "Shots on target a game against an average side."),
              ("poss", "Possession", "Share of the ball against an average side."),
              ("defence", "Defence", "Goals we would expect an average side to score against them. Outward is tighter."),
              ("corners", "Corners", "Corners won a game against an average side.")]
RADAR_HALF = {"attack": 90.0, "shots": 48.0, "sot": 60.0, "poss": 60.0, "corners": 70.0}
RADAR_LAM = {"attack": 6.0, "shots": 12.0, "sot": 10.0, "poss": 12.0, "corners": 12.0}
_RADAR_CACHE: dict = {}


def _league_pairs(db, league_iid):
    """[(round, season, home_row, away_row)] for every stored match with both sides, oldest first."""
    by = {}
    for r in db.team_match_stats.find({"league_iid": league_iid}, {"_id": 0}):
        by.setdefault(r["match_iid"], []).append(r)
    g = [v for v in by.values() if len(v) == 2 and any(x.get("home") for x in v) and not all(x.get("home") for x in v)]
    g.sort(key=lambda v: str(v[0].get("kickoff") or ""))
    return g


def league_radar(db, league_iid):
    """{team_iid: {"axes": {key: 0..1}, "games": n}} for the clubs in the current season, or {} when there is too little data."""
    sig = (league_iid, db.team_match_stats.count_documents({"league_iid": league_iid}))
    hit = _RADAR_CACHE.get(league_iid)
    if hit and hit[0] == sig and time.time() - hit[1] < 600:
        return hit[2]
    g = _league_pairs(db, league_iid)
    out = {}
    if len(g) >= 40:
        days = sorted({str(v[0].get("kickoff") or "")[:10] for v in g})
        rank = {d: i for i, d in enumerate(days)}
        rd = np.array([rank[str(v[0].get("kickoff") or "")[:10]] for v in g], float)
        age = rd.max() - rd
        teams = sorted({x["team_iid"] for v in g for x in v})
        ti = {t: i for i, t in enumerate(teams)}
        home = [next(x for x in v if x.get("home")) for v in g]
        away = [next(x for x in v if not x.get("home")) for v in g]
        H = np.array([ti[x["team_iid"]] for x in home]); A = np.array([ti[x["team_iid"]] for x in away])
        lg = db.leagues.find_one({"iid": league_iid}, {"current_season": 1}) or {}
        season = {m["iid"] for m in db.matches.find({"league_iid": league_iid, "season": lg.get("current_season")}, {"iid": 1})} if lg.get("current_season") else None
        live_teams = {x["team_iid"] for x in home + away if season is None or x["match_iid"] in season}
        games = {}
        for x in home + away:
            if season is None or x["match_iid"] in season:
                games[x["team_iid"]] = games.get(x["team_iid"], 0) + 1

        def fit(col, key):
            yh = np.array([x.get(col) if x.get(col) is not None else np.nan for x in home], float)
            ya = np.array([x.get(col) if x.get(col) is not None else np.nan for x in away], float)
            ok = ~np.isnan(yh) & ~np.isnan(ya)
            if ok.sum() < 40:
                return None
            m = RatingsModel(RADAR_HALF[key], RADAR_LAM[key]).fit(H[ok], A[ok], yh[ok], ya[ok], age[ok], len(teams))
            return m if m.ok else None

        xg_cov = np.mean([x.get("xg") is not None for x in home])
        col_for = "xg" if xg_cov >= 0.8 else "goals"
        models = {k: fit(c, k) for k, c in (("attack", col_for), ("shots", "shots"), ("sot", "sot"), ("poss", "poss"), ("corners", "corners"))}
        raw = {}
        for k, m in models.items():
            if m is not None:
                raw[k] = m.a
                if k == "attack":
                    raw["defence"] = -m.d                       # a lower concession rating is the better defence
        for k, vals in raw.items():
            xs = np.array([vals[ti[t]] for t in live_teams if t in ti])
            n = len(xs)
            for t in live_teams:
                v = vals[ti[t]]
                p = ((xs < v - 1e-12).sum() + ((np.abs(xs - v) <= 1e-12).sum() - 1) / 2) / max(n - 1, 1) if n > 1 else None
                out.setdefault(t, {"axes": {}, "games": games.get(t, 0)})["axes"][k] = None if p is None else round(float(p), 3)
    _RADAR_CACHE[league_iid] = (sig, time.time(), out)
    return out


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
    la, lb = league_radar(db, ta["league_iid"]).get(ta["iid"]), league_radar(db, tb["league_iid"]).get(tb["iid"])
    if la and lb:
        out["radar"] = [{"key": k, "label": l, "a": la["axes"].get(k), "b": lb["axes"].get(k), "means": m} for k, l, m in RADAR_AXES]
        out["radar_games"] = {"a": la["games"], "b": lb["games"]}
    else:                                                         # too little history: the old league-place view
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
        unit = "%" if k == "poss" else " a game"
        out["stands_out"].append(f"{l.replace(' %', '')}: {an} {x:.1f}{unit}, {bn} {y:.1f}{unit}. Clear edge to {better}.")
    return out
