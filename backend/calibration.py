"""calibration.py -- turn the engine's raw likelihoods into the percentages people see (docs/21).

Why: a real-data audit (StatsBomb open data, 2015/16 Premier League, Serie A, Ligue 1; 351,098 forecasts,
walk-forward) found two biases.
  * player forecasts made WITH the confirmed eleven were under-confident: a stated 75% happened 80% of the time.
  * team forecasts were over-confident at the top: a stated 85% happened about 78% of the time.
  Player forecasts made BEFORE the lineup were nearly right; with the availability model (docs/22) a small map
  for them helps too (z about +2 in each league).

The shipped map (soccer_brain/calibration_default.json) was fitted on those three leagues and checked by
leaving each league out in turn: it never made a league worse and fixed both biases.

In production, `refit` builds a new map from our own scored forecasts (`forecast_outcomes`) once there are
enough of them, and keeps it only if it beats the current map on the newest 30% of results.
Every forecast keeps its raw number in `p_model`, so a map can always be judged or rolled back.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone

import numpy as np

import settings_store as S

_HERE = os.path.dirname(os.path.abspath(__file__))
_DEFAULT_PATH = os.path.join(os.environ.get("SOCCER_BRAIN_DIR") or os.path.join(_HERE, "soccer_brain"), "calibration_default.json")
CAP = (0.003, 0.97)            # never show more than 97%: football always leaves room for surprise
GRID = np.linspace(0, 1, 41)


def default_map() -> dict:
    with open(_DEFAULT_PATH) as f:
        m = json.load(f)
    m.setdefault("version", "default")
    return m


def current(db) -> dict | None:
    """The map in use, or None when calibration is switched off."""
    if not S.get(db, "engine.calibration"):
        return None
    doc = db.engine_calibration.find_one({"active": True}, {"_id": 0}, sort=[("created_at", -1)])
    return doc["map"] if doc else default_map()


def apply(cal: dict | None, p: float, state: str, scope: str) -> float:
    """state: 'lineup' (confirmed eleven) or 'pre'. scope: 'player' or 'team'."""
    if cal is None or p is None:
        return p
    if scope == "team":
        q = 0.5 + float(cal.get("team_shrink", 1.0)) * (p - 0.5)
    elif state == "lineup" and cal.get("lineup_player"):
        q = float(np.interp(p, cal["lineup_player"]["x"], cal["lineup_player"]["y"]))
    elif state == "pre" and cal.get("pre_player"):
        q = float(np.interp(p, cal["pre_player"]["x"], cal["pre_player"]["y"]))
    else:
        q = p
    return float(min(max(q, CAP[0]), CAP[1]))


# ------------------------------------------------------------------ refit from our own results
def _iso(p, y):
    """Pool-adjacent-violators, returned as a monotone map on a fixed grid."""
    p = np.asarray(p, float); y = np.asarray(y, float)
    o = np.argsort(p); p, y = p[o], y[o]
    blocks = []
    for pp, yy in zip(p, y):
        blocks.append([yy, 1.0, pp])
        while len(blocks) > 1 and blocks[-2][0] / blocks[-2][1] > blocks[-1][0] / blocks[-1][1]:
            b2 = blocks.pop(); b1 = blocks.pop()
            blocks.append([b1[0] + b2[0], b1[1] + b2[1], b1[2] + b2[2]])
    bx = np.array([b[2] / b[1] for b in blocks]); by = np.array([b[0] / b[1] for b in blocks])
    xs = np.unique(np.r_[GRID, np.quantile(p, np.linspace(0, 1, 24))])
    ys = np.maximum.accumulate(np.clip(np.interp(xs, bx, by), *CAP))
    return {"x": [round(float(v), 4) for v in xs], "y": [round(float(v), 4) for v in ys]}


def _fit(rows) -> dict:
    lp = [(r["p_model"], r["reached"]) for r in rows if r["scope"] == "player" and r["state"] == "lineup"]
    pp = [(r["p_model"], r["reached"]) for r in rows if r["scope"] == "player" and r["state"] == "pre"]
    tm = [(r["p_model"], r["reached"]) for r in rows if r["scope"] == "team"]
    out = {"team_shrink": 1.0}
    if len(lp) >= 2000:
        out["lineup_player"] = _iso(*zip(*lp))
    if len(pp) >= 2000:
        out["pre_player"] = _iso(*zip(*pp))
    if len(tm) >= 300:
        p = np.array([a for a, _ in tm]); y = np.array([b for _, b in tm], float)
        out["team_shrink"] = min(((_ll(0.5 + a * (p - 0.5), y), round(float(a), 2)) for a in np.arange(0.6, 1.01, 0.02)))[1]
    return out


def _ll(p, y):
    p = np.clip(np.asarray(p, float), 0.005, 0.995); y = np.asarray(y, float)
    return float(np.mean(-(y * np.log(p) + (1 - y) * np.log(1 - p))))


def _score(cal, rows):
    return _ll([apply(cal, r["p_model"], r["state"], r["scope"]) for r in rows], [float(r["reached"]) for r in rows])


def refit(db, now=None) -> dict:
    """Weekly. Fit a new map on older results, test it on the newest 30%. Keep it only if it is at least as good
    as the map in use. Needs `engine.calib_min_scored` scored forecasts that carry `p_model` and `state`."""
    now = now or datetime.now(timezone.utc)
    if not S.get(db, "engine.calibration_auto"):
        return {"status": "off"}
    rows = list(db.forecast_outcomes.find({"p_model": {"$ne": None}, "state": {"$in": ["pre", "lineup"]}},
                                          {"_id": 0, "p_model": 1, "reached": 1, "scope": 1, "state": 1, "scored_at": 1}).sort("scored_at", 1))
    need = int(S.get(db, "engine.calib_min_scored"))
    if len(rows) < need:
        return {"status": "waiting", "scored": len(rows), "needed": need}
    cut = int(len(rows) * 0.7)
    train, test = rows[:cut], rows[cut:]
    cand = _fit(train)
    cur = current(db) or {}
    s_new, s_cur = _score(cand, test), _score(cur, test)
    if s_new > s_cur:
        return {"status": "kept_current", "candidate": round(s_new, 5), "current": round(s_cur, 5), "scored": len(rows)}
    final = _fit(rows)                                  # same recipe on everything, now that it has earned its place
    final["version"] = now.strftime("own-%Y-%m-%d")
    db.engine_calibration.update_many({"active": True}, {"$set": {"active": False}})
    db.engine_calibration.insert_one({"map": final, "active": True, "created_at": now, "scored": len(rows),
                                      "test_logloss": {"new": round(s_new, 5), "previous": round(s_cur, 5)}})
    return {"status": "updated", "candidate": round(s_new, 5), "current": round(s_cur, 5), "scored": len(rows)}


def rollback(db) -> dict:
    """Back to the shipped default (admin action)."""
    db.engine_calibration.update_many({"active": True}, {"$set": {"active": False}})
    return {"status": "default"}
