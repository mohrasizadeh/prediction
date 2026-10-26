"""exp_startmodel.py -- does calendar context improve the forecast of WHO STARTS?

Baseline = the engine's usual-start-rate (past only). Model = baseline + context terms learned on the
first part of the season, scored on the rest. Squad rows include unused substitutes.
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "engine"))
import numpy as np, pandas as pd
import load_statsbomb as L
import context as C

HERE = os.path.dirname(os.path.abspath(__file__))


def ll(p, y):
    p = np.clip(p, 1e-4, 1 - 1e-4)
    return y * np.log(p) + (1 - y) * np.log(1 - p)


def build(lg, ctx_all):
    matches, tg, pg, tid = L.load(lg)
    pg = C.prior_and_regularity(pg)
    ctx = ctx_all[ctx_all["league"] == lg][["game_id", "team", "next_bigger", "europe_soon", "low_stakes", "congestion", "short"]]
    rows = pg.merge(ctx, on=["game_id", "team"], how="left")
    rows["league"] = lg
    return rows


if __name__ == "__main__":
    ctx_all = pd.read_pickle(os.path.join(HERE, "data", "ctx_rows.pkl"))
    parts = []
    for lg in ("PL", "SA", "L1"):
        parts.append(build(lg, ctx_all))
    R = pd.concat(parts, ignore_index=True)
    R = R[R["regular"].notna()]
    # only rows where the club had at least 5 earlier matches
    R = R[R["round"] >= 8].copy()
    print("squad rows", len(R), "start rate", round(R.started.mean(), 3))
    res = []
    for cut_frac in (0.5, 0.6, 0.7):
        tr_mask = np.zeros(len(R), bool)
        for lg, g in R.groupby("league"):
            cut = g["round"].quantile(cut_frac)
            tr_mask[R.index.get_indexer(g.index)] = (g["round"] <= cut).values
        tr, te = R[tr_mask], R[~tr_mask]
        m = C.StartModel(l2=8.0).fit(tr)
        X = m.design(te, te["regular"].values)
        p0 = te["prior"].values
        eta = m._logit(p0) + X @ m.w
        p1 = 1 / (1 + np.exp(-eta))
        y = te["started"].values.astype(float)
        d = ll(p1, y) - ll(p0, y)
        # baseline adjusted only for regularity (is context better than just a recalibration?)
        res.append((cut_frac, len(tr), len(te), ll(p0, y).mean(), ll(p1, y).mean(), d.mean(), d.std(ddof=1) / np.sqrt(len(d))))
        print(f"train up to {cut_frac:.0%} of the season: n_train {len(tr)} n_test {len(te)}  log-lik base {ll(p0, y).mean():.4f} model {ll(p1, y).mean():.4f}  gain {d.mean():+.5f} +/- {d.std(ddof=1)/np.sqrt(len(d)):.5f}")
        print("   coefficients:", {k: round(v, 3) for k, v in m.coefficients().items()})
    # squad-level sanity: starters per club per match
    print("\nstarts per club per match (should be 10 outfield):", R.groupby(["game_id", "team"])["started"].sum().mean().round(2))
