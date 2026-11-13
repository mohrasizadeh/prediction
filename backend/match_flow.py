"""match_flow.py -- momentum and possession across a match, from our own minute-by-minute snapshots.

API-Football publishes a match's statistics as running totals (shots so far, possession so far) and
nothing per minute: no momentum graph, no possession timeline. What it does give is the running
total WHENEVER WE ASK, and the live tick asks every minute while the ball is moving. `live_stats`
kept only the latest answer, overwriting the one before. Keeping each answer instead turns those
totals into a timeline we computed ourselves:

  * MOMENTUM per five-minute window: the shots, shots on target and corners each side added in that
    window. A shot on target counts twice (it is a shot, and a better one) and a corner half. It is
    the same idea as FotMob's attacking-threat graph, built only from numbers the provider gives us,
    and it is labelled as what it is.
  * POSSESSION per window: possession is a running average, so the share inside a window is
    recovered from two snapshots -- (p2 * m2 - p1 * m1) / (m2 - m1) -- which is exact when the
    provider's average is time-weighted, and close enough to read when it is not.

What this replaced: goals and cards counted by quarter-hour. Three yellow cards in a quarter does
not mean a side was pushing, and a match with two goals drew a chart of two bars.

Only matches the live tick followed have snapshots. A match with too few of them -- before this
existed, a league the live tick does not cover, a feed that dropped out for half an hour -- returns
None and the page draws nothing, rather than a chart with holes in it.
"""
from __future__ import annotations

from datetime import datetime

COLS = ("shots", "sot", "corners", "poss")
WINDOW = 5
MIN_SNAPSHOTS = 6          # about six minutes of play followed; less is not a timeline
MIN_SPAN = 20              # and spanning at least twenty minutes of the match


def record(db, fixture_sid: int, match_iid: int | None, minute, teams: dict, now: datetime) -> bool:
    """Keep this minute's running totals. One row a fixture a minute: a second poll in the same
    minute replaces the first, so a quick re-tick cannot double a window."""
    if minute is None or not teams:
        return False
    try:
        minute = int(minute)
    except (TypeError, ValueError):
        return False
    row = {"fixture_sid": int(fixture_sid), "match_iid": match_iid, "minute": minute, "at": now}
    for side in ("home", "away"):
        t = teams.get(side) or {}
        row[side] = {c: t.get(c) for c in COLS}
    db.live_stats_series.update_one({"fixture_sid": int(fixture_sid), "minute": minute}, {"$set": row}, upsert=True)
    return True


def _n(v) -> float:
    try:
        return float(v) if v is not None else 0.0
    except (TypeError, ValueError):
        return 0.0


def _threat(d: dict) -> float:
    return d["shots"] + d["sot"] + 0.5 * d["corners"]


def flow(db, fixture_sid: int | None, goals: list[dict] | None = None) -> dict | None:
    """Five-minute windows of momentum and possession, or None when the match was not followed."""
    if fixture_sid is None:
        return None
    snaps = list(db.live_stats_series.find({"fixture_sid": int(fixture_sid)}, {"_id": 0}).sort("minute", 1))
    if len(snaps) < MIN_SNAPSHOTS or snaps[-1]["minute"] - snaps[0]["minute"] < MIN_SPAN:
        return None
    # A running total cannot fall. When the provider corrects one down (a shot reclassified as
    # blocked), carry the highest figure so far, so a window never shows a negative shot.
    best = {s: {c: 0.0 for c in COLS if c != "poss"} for s in ("home", "away")}
    for r in snaps:
        for s in ("home", "away"):
            for c in best[s]:
                best[s][c] = max(best[s][c], _n((r.get(s) or {}).get(c)))
                (r.setdefault(s, {}))[c] = best[s][c]
    last = max(90, snaps[-1]["minute"])
    windows = []
    prev = {"minute": 0, "home": {c: 0.0 for c in COLS}, "away": {c: 0.0 for c in COLS}}
    i = 0
    for a in range(0, last, WINDOW):
        b = min(a + WINDOW, last)
        cur = None
        while i < len(snaps) and snaps[i]["minute"] <= b:
            cur = snaps[i]; i += 1
        if cur is None or cur["minute"] <= prev["minute"]:
            windows.append({"from": a, "to": b, "known": False})
            continue
        w = {"from": a, "to": b, "known": True}
        for s in ("home", "away"):
            w[s] = {c: round(_n(cur[s].get(c)) - _n(prev[s].get(c)), 2) for c in ("shots", "sot", "corners")}
        w["pressure"] = round(_threat(w["home"]) - _threat(w["away"]), 2)
        p2, m2 = (cur.get("home") or {}).get("poss"), cur["minute"]
        p1, m1 = (prev.get("home") or {}).get("poss"), prev["minute"]
        if p2 is not None and m2 > 0:
            share = (_n(p2) * m2 - (_n(p1) * m1 if p1 is not None else _n(p2) * m1)) / max(1, m2 - m1)
            w["poss_home"] = round(min(100.0, max(0.0, share)), 1)
        windows.append(w)
        prev = cur
    known = [w for w in windows if w["known"]]
    if len(known) < 3:
        return None
    peak = max(1.0, max(abs(w["pressure"]) for w in known))
    return {"window": WINDOW, "minutes": last, "windows": windows, "peak": peak, "snapshots": len(snaps),
            "goals": [{"minute": g.get("minute"), "side": g.get("side")} for g in (goals or []) if g.get("side")]}
