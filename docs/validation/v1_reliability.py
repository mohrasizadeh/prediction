"""v1_reliability.py -- are tactical style measures stable team traits, or noise?

Split-half reliability: average each team's metric over odd-numbered games and over even-numbered games,
correlate across teams, then apply Spearman-Brown to get the reliability of the full-season mean.
Also: how much of a metric's variance sits between teams (ICC) vs. within a team (match to match, opponent).
"""
import numpy as np, pandas as pd, os
HERE = os.path.dirname(os.path.abspath(__file__))
METRICS = ["ppda", "ada", "field_tilt", "poss", "passes_per_seq", "direct_speed", "long_ball_pct",
           "high_turnovers", "pressures_opp_half", "crosses", "counter_xg", "quick_shots",
           "shots", "xg", "corners", "tackles", "fouls", "yellow", "n_def", "n_fwd"]


def split_half(tg, m, rng):
    rs = []
    for _ in range(200):
        a, b = [], []
        for t, g in tg.groupby("team"):
            v = g[m].dropna().values
            if len(v) < 10: continue
            p = rng.permutation(len(v)); h = len(v) // 2
            a.append(v[p[:h]].mean()); b.append(v[p[h:2 * h]].mean())
        rs.append(np.corrcoef(a, b)[0, 1])
    r = float(np.mean(rs))
    return r, 2 * r / (1 + r)


def icc(tg, m):
    g = tg.dropna(subset=[m]).groupby("team")[m]
    between = g.mean().var(ddof=1)
    within = g.var(ddof=1).mean()
    n = g.size().mean()
    return max((between - within / n) / (between + (n - 1) * within / n), 0.0)


if __name__ == "__main__":
    rng = np.random.default_rng(0)
    out = {}
    for lg in ("PL", "SA", "L1"):
        tg = pd.read_pickle(os.path.join(HERE, "data", "sb", f"tg_{lg}.pkl"))
        tg["ppda"] = np.log(tg["ppda"])
        out[lg] = {m: split_half(tg, m, rng) for m in METRICS}
        out[lg + "_icc"] = {m: icc(tg, m) for m in METRICS}
    print(f"{'metric':22s} " + "  ".join(f"{lg:>14s}" for lg in ("PL", "SA", "L1")) + "   (split-half r  ->  full-season reliability | share of variance that is team identity)")
    for m in METRICS:
        print(f"{m:22s} " + "  ".join(f"{out[lg][m][0]:+.2f}->{out[lg][m][1]:.2f}|{out[lg + '_icc'][m]:.2f}" for lg in ("PL", "SA", "L1")))
