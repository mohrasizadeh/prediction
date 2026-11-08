"""Are we underconfident at the top of the range? (asked 2026-11-08)

A document arguing for a "corrected quant model" claimed a third-party engine understates high
player lines -- 41% where the honest number is 56% -- and validated that by matching a bookmaker's
implied price. Matching a price is not a test: a price carries the margin and is shaded by where
money landed, so fitting to it means inheriting both.

But the claim underneath it IS falsifiable, and this is the test. If we are underconfident at the
top, then among the forecasts where we said 80-90%, more than 80-90% of them happened, by more than
sampling noise.

Two ways in, because they answer different questions:

  --mongo URI   reads your own `forecast_outcomes`: every forecast the product has published and
                then scored after the match. This is the answer about REAL football.
  (default)     walks forward over a simulated league, refitting as it goes, and tests the stated
                probability against what the simulator did. Every prediction is out of sample. This
                cannot tell you about real football, but it CAN tell you whether the probability
                machinery itself -- negative binomial, dispersion, minute scenarios, the ladder --
                is internally honest. If it is biased here, the bug is in the maths rather than the
                football.

Two things about the statistics, because the naive version of this test lies:

  * The right null is Poisson-binomial, not binomial: each row has its own p, so the expected number
    of hits is the SUM of the p's and the variance is the sum of p(1-p). Comparing a mean to a mean
    with a binomial standard error understates the spread.
  * The rungs of one player's ladder are not independent -- 1+ shot and 2+ shots are the same
    underlying count asked twice -- so the rows come in clusters. The z below is reported, but the
    interval that should be believed is the CLUSTERED BOOTSTRAP, which resamples whole player-matches.

Read-only. Run: python scripts/measure/high_band_calibration.py [--mongo URI] [--rounds N]
"""
import argparse
import base64
import collections
import math
import os
import sys

os.environ.setdefault("APP_ENCRYPTION_KEY", base64.b64encode(os.urandom(32)).decode())
os.environ.setdefault("ADMIN_EMAIL", "owner@example.com")
os.environ.setdefault("ADMIN_INITIAL_PASSWORD", "demo-owner-pass-1")
HERE = "/home/user/prediction/backend"
os.environ.setdefault("SOCCER_BRAIN_DIR", os.path.join(HERE, "soccer_brain"))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "tests"))
sys.path.insert(0, os.environ["SOCCER_BRAIN_DIR"])

import numpy as np  # noqa: E402

import engine_bridge as B  # noqa: E402
import settings_store as S  # noqa: E402
from core import nb_sf  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("--mongo", default="", help="MongoDB URI of the real database; omit to use a simulated league")
ap.add_argument("--db", default="prediction", help="database name, with --mongo")
ap.add_argument("--rounds", type=int, default=16, help="rounds to walk forward on the simulated league")
ap.add_argument("--boot", type=int, default=2000, help="clustered bootstrap resamples")
ap.add_argument("--fit-r", action="store_true",
                help="fit the player dispersion from data (engine.fit_player_r) instead of the fixed defaults. "
                     "The shape of an underconfidence at the top is what assuming TOO MUCH dispersion looks like, "
                     "so this is the switch that should remove it if that is the cause.")
args = ap.parse_args()

BANDS = [(0.5, 0.6), (0.6, 0.7), (0.7, 0.8), (0.8, 0.9), (0.9, 1.0001)]


# ---------------------------------------------------------------- gathering (p, reached, cluster)
def from_outcomes(uri, name):
    """The real answer: what the product published, and what then happened."""
    from pymongo import MongoClient
    db = MongoClient(uri)[name]
    rows = []
    for o in db.forecast_outcomes.find({"player_played": True},
                                       {"_id": 0, "p": 1, "reached": 1, "stat": 1, "fkey": 1, "scope": 1}):
        if o.get("p") is None:
            continue
        # The cluster is the player-match: every rung of one ladder asks about the same count.
        cluster = str(o.get("fkey", "")).rsplit(":", 1)[0] or str(o.get("fkey"))
        rows.append((float(o["p"]), bool(o.get("reached")), o.get("stat") or "?", cluster))
    return rows, db


def from_simulation(rounds):
    """Walk forward over a simulated league, exactly as engine_ab does, and read the stated
    probability of every rung against what actually happened."""
    from demo_server import build
    db = build()
    lg = db.leagues.find_one({})
    hist = int(S.get(db, "engine.history_rounds"))
    frames = B.build_frames(db, lg["iid"], hist)
    ms, tg, pg, apf, _ = frames
    ladders = S.get(db, "engine.player_ladder") or {}
    stats = tuple(k for k in ("shots", "sot", "tackles") if k in ladders)
    all_rounds = sorted(ms["round"].unique())
    play = all_rounds[-rounds:] if rounds else all_rounds
    pgi = {gid: g for gid, g in pg.groupby("game_id")}
    rows, eng = [], None
    print(f"  simulated league: {len(ms)} matches, walking rounds {play[0]}..{play[-1]}", flush=True)
    for i, r in enumerate(play):
        if i % 4 == 0:
            eng = B.configure_engine(db)
            if args.fit_r:
                eng.fit_player_r = True
            eng = eng.fit(ms, tg, pg, r, appearances=apf)
            print(f"    refit at round {r}", flush=True)
        for m in ms[ms["round"] == r].itertuples():
            if m.home not in eng.tidx or m.away not in eng.tidx:
                continue
            prs = pgi.get(m.game_id)
            if prs is None:
                continue
            starters = {}
            for tm in (m.home, m.away):
                st = prs[(prs["team"] == tm) & (prs["started"] == 1)]
                if len(st) >= 7:
                    starters[tm] = set(int(x) for x in st["player"])
            actual = {(int(x.team), int(x.player)): x for x in prs.itertuples()}
            try:
                fcs, _ = eng.predict_fixture(m.home, m.away, lineups=starters or None)
            except Exception:
                continue
            seen = set()
            for f in fcs:
                if f.scope != "player" or f.stat not in stats:
                    continue
                key = (m.game_id, int(f.player), f.stat)
                if key in seen:
                    continue
                seen.add(key)
                a = actual.get((int(f.team), int(f.player)))
                # Started and played: the published number is "if he plays" (docs/27), so the test
                # has to be the same question. A non-appearance is a different measurement.
                if a is None or not getattr(a, "started", 0) or getattr(a, "minutes", 0) <= 0:
                    continue
                y = getattr(a, f.stat, None)
                if y is None or y != y:
                    continue
                mu, rr = float(f.expected), float(eng.r_player[f.stat])
                for thr in ladders.get(f.stat, []):
                    k = int(float(thr) + 0.5)
                    p = float(nb_sf(k, mu, rr))
                    if p < 0.5 or p > 0.9999:
                        continue                              # the product only publishes above the floor
                    rows.append((p, bool(y >= k), f.stat, f"{m.game_id}:{int(f.player)}"))
    return rows, db


# ---------------------------------------------------------------- the test
def poisson_binomial(rows):
    """Observed hits against the sum of the stated probabilities. The honest null for a set of rows
    each with its own p."""
    p = np.array([r[0] for r in rows], float)
    y = np.array([1.0 if r[1] else 0.0 for r in rows])
    exp = p.sum()
    var = float((p * (1 - p)).sum())
    z = (y.sum() - exp) / math.sqrt(var) if var > 0 else 0.0
    return {"n": len(rows), "stated": float(p.mean()), "actual": float(y.mean()),
            "gap": float(y.mean() - p.mean()), "z": float(z)}


def clustered_ci(rows, n_boot, seed=7):
    """Resample whole player-matches, not rows: the rungs of one ladder are the same count asked
    several times, and treating them as independent makes any gap look more certain than it is."""
    by = collections.defaultdict(list)
    for r in rows:
        by[r[3]].append(r)
    keys = list(by)
    if len(keys) < 20:
        return None
    rng = np.random.default_rng(seed)
    gaps = []
    for _ in range(n_boot):
        pick = rng.integers(0, len(keys), len(keys))
        p = s = n = 0.0
        for i in pick:
            for q, hit, _st, _c in by[keys[i]]:
                p += q; s += 1.0 if hit else 0.0; n += 1
        if n:
            gaps.append((s - p) / n)
    lo, hi = np.percentile(gaps, [2.5, 97.5])
    return {"clusters": len(keys), "lo": float(lo), "hi": float(hi), "mid": float(np.median(gaps))}


def table(title, rows, high_p):
    print(f"\n{title}")
    print(f"  {'band':<12}{'n':>7}{'we said':>10}{'happened':>11}{'gap':>9}{'z':>8}")
    for lo, hi in BANDS:
        g = [r for r in rows if lo <= r[0] < hi]
        if len(g) < 30:
            continue
        s = poisson_binomial(g)
        print(f"  {f'{lo:.0%}-{hi if hi <= 1 else 1:.0%}':<12}{s['n']:>7}{s['stated']:>9.1%}{s['actual']:>11.1%}"
              f"{s['gap'] * 100:>+8.1f}p{s['z']:>8.2f}")
    hiRows = [r for r in rows if r[0] >= high_p]
    if len(hiRows) >= 30:
        s = poisson_binomial(hiRows)
        ci = clustered_ci(hiRows, args.boot)
        print(f"  {'HIGH ' + f'(>={high_p:.0%})':<12}{s['n']:>7}{s['stated']:>9.1%}{s['actual']:>11.1%}"
              f"{s['gap'] * 100:>+8.1f}p{s['z']:>8.2f}")
        if ci:
            print(f"    clustered 95% interval for the gap: {ci['lo'] * 100:+.1f}p to {ci['hi'] * 100:+.1f}p"
                  f"   over {ci['clusters']:,} player-matches")
            verdict = ("UNDERCONFIDENT: it happened more often than we said"
                       if ci["lo"] > 0 else
                       "OVERCONFIDENT: it happened less often than we said" if ci["hi"] < 0 else
                       "NO BIAS FOUND: the interval contains zero")
            print(f"    verdict: {verdict}")
    return rows


def main():
    if args.mongo:
        rows, db = from_outcomes(args.mongo, args.db)
        src = f"your own scored forecasts ({args.db})"
    else:
        rows, db = from_simulation(args.rounds)
        src = "a simulated league, walked forward out of sample" + (", dispersion fitted" if args.fit_r else ", dispersion at the fixed defaults")
    if len(rows) < 100:
        print(f"\nOnly {len(rows)} scored rows. Not enough to say anything; come back when the engine "
              f"has scored a few hundred.")
        return
    high_p = float(S.get(db, "engine.record_high_p") or 0.8)
    print(f"\nsource: {src}")
    print(f"rows: {len(rows):,}   distinct player-matches: {len({r[3] for r in rows}):,}")
    table("ALL MARKETS", rows, high_p)
    for stat in sorted({r[2] for r in rows}):
        g = [r for r in rows if r[2] == stat]
        if len(g) >= 150:
            table(f"MARKET: {stat}", g, high_p)
    print("\n--- how to read it")
    print("  A gap of +3p in a band means that line happened three points MORE often than we said,")
    print("  which is underconfidence. The z is the Poisson-binomial null and treats every rung as")
    print("  independent, which they are not; believe the clustered interval, which does not.")
    print("  Only the HIGH row answers the question that was asked.")


main()
