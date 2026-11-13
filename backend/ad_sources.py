"""ad_sources.py -- what the three match ads draw (docs/60 section 4).

The original templates draw from the public feed (/insights), which answers a reader's question:
the lines that differ most from usual, one card per player, across every match. Two of the new ads
ask questions that feed cannot answer, so they read the forecasts directly:

  * HEAD TO HEAD, before kick-off: one player from each side of ONE match, with his strongest
    lines -- or, when the owner picks a market, both players on that same market. That needs every
    published line of both squads for that match, not the feed's sixty best across all of them.

  * WE SAID / IT HAPPENED, after the whistle: forecasts that were published and then scored, with
    what actually happened. /proof already has this shape but returns ONLY the ones that came in,
    which is right for a landing-page strip and wrong for an ad series: a builder that can only
    show hits is a builder for cherry-picking. This returns the misses too, and the day's true
    count travels with every row, so the results ad prints "8 of 11 came in" even when the owner
    shows five of them.

What "published" means is the same everywhere: a current, visible, non-carrier line in a tier a
reader is shown, at 60% or more (the "we show nothing under 60%" promise on /waitlist).
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

import queries as Q
import settings_store as S

TIERS = ("Strong", "Solid", "Watch")
FLOOR = 0.6
LINES_PER_PLAYER = 3
CANDIDATES_PER_SIDE = 8
DAY_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _utc(d):
    if d is None:
        return None
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


def _line(f: dict) -> dict:
    """One forecast line, in the shape the ad templates and the card picker already read."""
    return {"fkey": f["fkey"], "market": f.get("market"), "stat": f.get("stat"), "scope": f.get("scope"),
            "thr": f.get("thr"), "p": round(float(f["p"]), 4), "lo": f.get("lo"), "hi": f.get("hi"),
            "p_usual": f.get("p_usual"), "tier": f.get("tier"), "run": f.get("run"), "pos": f.get("pos"),
            "noun": f.get("noun"), "verb": f.get("verb")}


def _side(f: dict) -> dict:
    return {"player": f.get("player"), "team": f.get("team"), "opp": f.get("opp"), "pos": f.get("pos"),
            "home_iid": f.get("home_iid"), "team_iid": f.get("team_iid"), "opp_iid": f.get("opp_iid"),
            "kickoff": f.get("kickoff"), "league_name": f.get("league_name"), "league_id": f.get("league_id"),
            "match_id": f.get("match_id")}


# ------------------------------------------------------------------ before kick-off
def matchups(db, now=None, limit: int = 30) -> list[dict]:
    """Upcoming matches that have published player lines on both sides, soonest first."""
    now = now or datetime.now(timezone.utc)
    q = {**Q.NOT_HIDDEN, "scope": "player", "tier": {"$in": list(TIERS)}, "p": {"$gte": FLOOR}, "kickoff": {"$gte": now}}
    by: dict = {}
    for f in db.forecasts.find(q, {"_id": 0, "match_iid": 1, "team_iid": 1, "opp_iid": 1, "stat": 1, "kickoff": 1, "league_iid": 1}).limit(20000):
        m = by.setdefault(f["match_iid"], {"match_iid": f["match_iid"], "kickoff": f["kickoff"], "league_iid": f.get("league_iid"),
                                           "teams": set(), "stats": set(), "n": 0})
        m["teams"].update([f["team_iid"], f["opp_iid"]])
        m["sides"] = m.get("sides", set()) | {f["team_iid"]}
        m["stats"].add(f["stat"]); m["n"] += 1
    rows = sorted((m for m in by.values() if len(m.get("sides", ())) == 2), key=lambda m: _utc(m["kickoff"]))[:limit]
    if not rows:
        return []
    ms = {m["iid"]: m for m in db.matches.find({"iid": {"$in": [r["match_iid"] for r in rows]}},
                                              {"_id": 0, "iid": 1, "id": 1, "home_iid": 1, "away_iid": 1})}
    tm = Q._names(db, "teams", [t for r in rows for t in r["teams"]])
    lg = Q._names(db, "leagues", [r["league_iid"] for r in rows if r.get("league_iid")])
    out = []
    for r in rows:
        m = ms.get(r["match_iid"])
        if not m:
            continue
        out.append({"match_id": m["id"], "kickoff": r["kickoff"], "home": tm.get(m["home_iid"]), "away": tm.get(m["away_iid"]),
                    "league_name": (lg.get(r.get("league_iid")) or {}).get("name"), "stats": sorted(r["stats"]), "lines": r["n"]})
    return out


def matchup(db, match_id: str, stat: str | None = None) -> dict | None:
    """Both squads' published lines for one match, as ranked candidates per side.

    With no `stat`, a player's lines are his strongest, one per market so "1+ shot" and "2+ shots"
    do not take two of his three rows, and players are ranked by their best line. With a `stat`,
    only that market counts, so the two players the ad puts side by side are on the same question.

    The ranking stops at engine.feed_max_p, the same guard the public feed uses: without it every
    player's "best" line is a 96% one-plus that says nothing. A player whose every line sits above
    it still appears, so a quiet match does not come back empty.
    """
    m = db.matches.find_one({"id": match_id}, {"_id": 0, "iid": 1, "id": 1, "home_iid": 1, "away_iid": 1, "kickoff": 1})
    if not m:
        return None
    q = {**Q.NOT_HIDDEN, "scope": "player", "match_iid": m["iid"], "tier": {"$in": list(TIERS)}, "p": {"$gte": FLOOR}}
    rows = list(db.forecasts.find(q, {"_id": 0, "contrib": 0}).limit(5000))
    stats = sorted({f["stat"] for f in rows})
    if stat:
        rows = [f for f in rows if f["stat"] == stat]
    Q._decorate(db, rows)
    cap = float(S.get(db, "engine.feed_max_p"))
    players: dict = {}
    for f in rows:
        players.setdefault((f["team_iid"], f.get("player_iid")), []).append(f)
    sides: dict = {m["home_iid"]: [], m["away_iid"]: []}
    for (team_iid, _pid), fs in players.items():
        if team_iid not in sides:
            continue
        under = [f for f in fs if f["p"] <= cap] or fs
        best: dict = {}
        for f in sorted(under, key=lambda f: -f["p"]):
            best.setdefault(f["stat"], f)                  # the strongest line per market
        lines = sorted(best.values(), key=lambda f: -f["p"])[:LINES_PER_PLAYER]
        sides[team_iid].append({**_side(lines[0]), "lines": [_line(f) for f in lines], "score": lines[0]["p"]})
    tm = Q._names(db, "teams", [m["home_iid"], m["away_iid"]])
    first = next(iter(rows), {})

    def pack(iid):
        cands = sorted(sides[iid], key=lambda c: -c["score"])[:CANDIDATES_PER_SIDE]
        return {"team": tm.get(iid), "candidates": cands}
    return {"match_id": m["id"], "kickoff": m.get("kickoff"), "home_iid": m["home_iid"],
            "league_name": first.get("league_name"), "league_id": first.get("league_id"),
            "stat": stat or None, "stats": stats, "home": pack(m["home_iid"]), "away": pack(m["away_iid"])}


# ------------------------------------------------------------------ after the whistle
def settled(db, day: str | None = None, now=None, days_back: int = 30, limit: int = 40) -> dict:
    """Every published forecast scored for one match day -- hits AND misses -- with what happened.

    The day is the kickoff's UTC date. With no `day`, the most recent day that has any. `days`
    lists the recent days with their own counts, so the screen can offer them.

    Only lines where the player PLAYED, as on /track-record and /proof: a forecast on someone who
    never came on was not a forecast about football, in either direction.
    """
    now = now or datetime.now(timezone.utc)
    since = now - timedelta(days=int(days_back))
    outs = list(db.forecast_outcomes.find({"player_played": True, "p": {"$gte": FLOOR}, "tier": {"$in": list(TIERS)},
                                           "scored_at": {"$gte": since}}, {"_id": 0}).limit(20000))
    if not outs:
        return {"day": None, "days": [], "n": 0, "came_in": 0, "rows": []}
    fc = {f["id"]: f for f in db.forecasts.find({"id": {"$in": [o["forecast_id"] for o in outs]}}, {"_id": 0, "contrib": 0})}
    per_day: dict = {}
    for o in outs:
        f = fc.get(o["forecast_id"])
        if not f or not f.get("kickoff"):
            continue
        d = _utc(f["kickoff"]).strftime("%Y-%m-%d")
        per_day.setdefault(d, []).append((o, f))
    days = [{"day": d, "n": len(v), "came_in": sum(1 for o, _ in v if o["reached"])} for d, v in sorted(per_day.items(), reverse=True)]
    pick = day if day in per_day else days[0]["day"]
    # Ordered the way the feed leads (engine.feed_max_p): each player's strongest line UNDER the
    # ceiling first, then everything else. Sorted by likelihood alone, a day opened on a column of
    # 96% one-pluses -- true, scored, and the least interesting thing that happened.
    cap = float(S.get(db, "engine.feed_max_p"))
    ranked = sorted(per_day[pick], key=lambda x: (x[0]["p"] > cap, -x[0]["p"]))
    lead, rest, seen = [], [], set()
    for o, f in ranked:
        who = f.get("player_iid") or ("t", f.get("team_iid"))
        (rest if who in seen else lead).append((o, f))
        seen.add(who)
    fs = [{**f, "_o": o} for o, f in lead + rest]
    Q._decorate(db, fs)
    rows = []
    for f in fs[:limit]:
        o = f["_o"]
        # The stored outcome is the line as it was PUBLISHED; the forecast row may have been
        # re-run since, so p and thr come from the outcome, never from the forecast.
        rows.append({**_side(f), **_line({**f, "p": o["p"], "thr": o["thr"]}), "actual": o["actual"], "reached": bool(o["reached"]),
                     "scored_at": o.get("scored_at")})
    v = per_day[pick]
    return {"day": pick, "days": days[:21], "n": len(v), "came_in": sum(1 for o, _ in v if o["reached"]), "rows": rows}


def valid_day(s: str) -> bool:
    return bool(DAY_RE.match(s or ""))
