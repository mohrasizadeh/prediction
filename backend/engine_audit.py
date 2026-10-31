"""engine_audit.py -- where is the engine losing accuracy? Run against the real database (read only).

    MONGO_URL=... DB_NAME=... python engine_audit.py [--days 14] [--league 3]

Prints, for the recent window and for everything before it:
  1. Match result chances (home, draw, away): log loss and Brier against "always the league average" (skill > 0 is good).
  2. Player and team lines: stated vs actual by stat, tier, lineup state, lineup badge, and "if he plays" basis.
  3. The cost of "did he play": how often a forecast was for a player who did not feature.
  4. Reliability by stated-chance band.
Nothing is written. Needs the fields stored by engine_bridge.score_finished (p_play and lineup_badge appear for new rows only).
"""
from __future__ import annotations

import argparse
import math
import os
from collections import defaultdict
from datetime import datetime, timedelta, timezone


def ll(p, y):
    p = min(max(p, 1e-4), 1 - 1e-4)
    return -(y * math.log(p) + (1 - y) * math.log(1 - p))


def mean(xs):
    xs = list(xs)
    return sum(xs) / len(xs) if xs else float("nan")


def _aware(d):
    return d.replace(tzinfo=timezone.utc) if d is not None and d.tzinfo is None else d


def match_skill(db, since, until, league=None):
    """Three-way result: log loss and Brier of our chances vs the base rate of the same window."""
    q = {"status": "final", "hg": {"$ne": None}, "kickoff": {"$gte": since, "$lt": until}}
    if league:
        q["league_iid"] = league
    rows = []
    for m in db.matches.find(q, {"iid": 1, "hg": 1, "ag": 1, "kickoff": 1}):
        p = db.match_probs.find_one({"match_iid": m["iid"]}, sort=[("at", -1)])
        if not p or p.get("p_home") is None:
            continue
        y = 0 if m["hg"] > m["ag"] else 1 if m["hg"] == m["ag"] else 2
        rows.append(((p["p_home"], p["p_draw"], p["p_away"]), y))
    if not rows:
        return None
    base = [mean(1 if y == k else 0 for _, y in rows) for k in range(3)]
    lm = mean(-math.log(max(p[y], 1e-4)) for p, y in rows)
    lb = mean(-math.log(max(base[y], 1e-4)) for _, y in rows)
    bm = mean(sum((p[k] - (1 if y == k else 0)) ** 2 for k in range(3)) for p, y in rows)
    bb = mean(sum((base[k] - (1 if y == k else 0)) ** 2 for k in range(3)) for _, y in rows)
    hit = mean(1 if max(range(3), key=lambda k: p[k]) == y else 0 for p, y in rows)
    return {"n": len(rows), "log_loss": lm, "base_log_loss": lb, "skill_ll": 1 - lm / lb, "brier": bm, "base_brier": bb,
            "skill_brier": 1 - bm / bb, "top_pick_hit": hit, "avg_home": mean(p[0] for p, _ in rows), "act_home": base[0],
            "avg_draw": mean(p[1] for p, _ in rows), "act_draw": base[1], "avg_away": mean(p[2] for p, _ in rows), "act_away": base[2]}


def table(rows, keyf, title, min_n=30):
    g = defaultdict(list)
    for r in rows:
        g[keyf(r)].append(r)
    print(f"\n  {title}")
    print(f"  {'group':<28}{'n':>6}{'stated':>9}{'actual':>9}{'gap':>8}{'brier':>8}")
    for k, v in sorted(g.items(), key=lambda kv: -len(kv[1])):
        if len(v) < min_n:
            continue
        s, a = mean(r["p"] for r in v), mean(1 if r["reached"] else 0 for r in v)
        b = mean((r["p"] - (1 if r["reached"] else 0)) ** 2 for r in v)
        print(f"  {str(k):<28}{len(v):>6}{s:>9.3f}{a:>9.3f}{a - s:>+8.3f}{b:>8.3f}")


def report(rows, label):
    print(f"\n=== Lines scored: {label}  (n={len(rows)}) ===")
    if not rows:
        return
    played = [r for r in rows if r.get("player_played") is not False]
    print(f"  all rows: stated {mean(r['p'] for r in rows):.3f}  actual {mean(1 if r['reached'] else 0 for r in rows):.3f}")
    pl = [r for r in rows if r["scope"] == "player"]
    if pl:
        dnp = sum(1 for r in pl if r.get("player_played") is False)
        print(f"  player lines: {len(pl)}, did not play: {dnp} ({dnp / len(pl):.1%}); if he plays -> counted on those who played: {len(pl) - dnp}")
        both = [r for r in pl if r.get("p_play") is not None]
        if both:
            exp_play = mean(r["p_play"] for r in both)
            act_play = mean(0 if r.get("player_played") is False else 1 for r in both)
            print(f"  chance to play: stated {exp_play:.3f}  actual {act_play:.3f}  (gap {act_play - exp_play:+.3f})")
            uncond = [dict(r, p=r["p"] * r["p_play"], reached=bool(r["reached"] and r.get("player_played") is not False)) for r in both]
            print(f"  whole-chance (p x p_play): stated {mean(r['p'] for r in uncond):.3f}  actual {mean(1 if r['reached'] else 0 for r in uncond):.3f}")
    table(played, lambda r: (r["scope"], r["stat"]), "by scope and stat (counted when the player played)")
    table(played, lambda r: r.get("tier"), "by tier")
    table(played, lambda r: r.get("state"), "by state (pre-lineup or lineup)")
    table(played, lambda r: r.get("lineup_badge") or "-", "by lineup badge")
    table(played, lambda r: r.get("p_basis"), "by basis")
    table(played, lambda r: f"{int(r['p'] * 10) / 10:.1f}-{int(r['p'] * 10) / 10 + 0.1:.1f}", "reliability by stated chance")
    table(played, lambda r: r.get("league_iid"), "by league")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=14)
    ap.add_argument("--league", type=int)
    a = ap.parse_args()
    from pymongo import MongoClient
    db = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
    now = datetime.now(timezone.utc)
    cut = now - timedelta(days=a.days)
    for label, lo, hi in ((f"last {a.days} days", cut, now), ("before that", datetime(2000, 1, 1, tzinfo=timezone.utc), cut)):
        s = match_skill(db, lo, hi, a.league)
        print(f"\n=== Match result chances: {label} ===")
        print("  no finished matches with stored chances" if not s else
              f"  n={s['n']}  log loss {s['log_loss']:.3f} (base {s['base_log_loss']:.3f}, skill {s['skill_ll']:+.1%})  brier {s['brier']:.3f} (base {s['base_brier']:.3f}, skill {s['skill_brier']:+.1%})\n"
              f"  top pick right {s['top_pick_hit']:.1%}   home {s['avg_home']:.2f} vs {s['act_home']:.2f}   draw {s['avg_draw']:.2f} vs {s['act_draw']:.2f}   away {s['avg_away']:.2f} vs {s['act_away']:.2f}")
    q = {"league_iid": a.league} if a.league else {}
    allrows = list(db.forecast_outcomes.find(q, {"_id": 0}))
    stamp = lambda r: _aware(r.get("kickoff") or r.get("scored_at"))
    recent = [r for r in allrows if stamp(r) and stamp(r) >= cut]
    older = [r for r in allrows if stamp(r) and stamp(r) < cut]
    report(recent, f"last {a.days} days")
    report(older, "before that")


if __name__ == "__main__":
    main()
