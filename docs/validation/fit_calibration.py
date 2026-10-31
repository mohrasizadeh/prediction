"""Fit the shipped default calibration and validate it leave-one-league-out.
 - player forecasts WITH the confirmed eleven: isotonic map (fixes under-confidence)
 - team forecasts: shrink toward 0.5 by factor a (fixes over-confidence at the top)
 - player forecasts BEFORE lineups: unchanged (already calibrated)"""
import glob, os, sys, json, numpy as np, pandas as pd
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "backend", "soccer_brain"))
from core import Isotonic
D = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data") + os.sep
df = pd.concat([pd.read_pickle(f) for f in sorted(glob.glob(D + "audit_rows_??.pkl"))], ignore_index=True)
c = lambda p: np.clip(np.asarray(p, float), 0.005, 0.995)
nll = lambda p, y: -(y * np.log(c(p)) + (1 - y) * np.log(1 - c(p)))
CAP = (0.003, 0.97)

def knots(p, y, n=24):
    iso = Isotonic().fit(p, y)
    xs = np.unique(np.r_[np.linspace(0, 1, 41), np.quantile(p, np.linspace(0, 1, n))])
    ys = np.clip(iso.predict(xs), *CAP)
    ys = np.maximum.accumulate(ys)
    return [round(float(v), 4) for v in xs], [round(float(v), 4) for v in ys]

def fit(tr):
    lp = tr[(tr.state == "lineup") & (tr.scope == "player")]
    kx, ky = knots(lp.p.values, lp.y.values)
    pp = tr[(tr.state == "pre") & (tr.scope == "player")]
    px, py = knots(pp.p.values, pp.y.values)
    tm = tr[tr.scope == "team"]
    best = min((float(np.mean(nll(0.5 + a * (tm.p - 0.5), tm.y))), a) for a in np.arange(0.6, 1.01, 0.02))[1]
    return {"lineup_player": {"x": kx, "y": ky}, "pre_player": {"x": px, "y": py}, "team_shrink": round(float(best), 2)}

def apply(cal, p, state, scope):
    p = np.asarray(p, float)
    if scope == "team":
        return 0.5 + cal["team_shrink"] * (p - 0.5)
    if state == "lineup":
        return np.interp(p, cal["lineup_player"]["x"], cal["lineup_player"]["y"])
    return np.interp(p, cal["pre_player"]["x"], cal["pre_player"]["y"])

res = []
for test in ("PL", "SA", "L1"):
    cal = fit(df[df.league != test])
    te = df[df.league == test].copy()
    te["pc"] = np.nan
    for (st, sc), idx in te.groupby(["state", "scope"]).groups.items():
        te.loc[idx, "pc"] = apply(cal, te.loc[idx, "p"].values, st, sc)
    res.append(te)
    print(test, "held out; team shrink fitted on the other two:", cal["team_shrink"])
o = pd.concat(res)
print("\nleave-one-league-out, per league and group: log loss before -> after (z of gain)")
for (lg, st, sc), g in o.groupby(["league", "state", "scope"]):
    d = nll(g.pc, g.y) - nll(g.p, g.y)
    z = -d.mean() / (d.std() / np.sqrt(len(d))) if d.std() > 0 else 0
    print(f"  {lg} {st:6s} {sc:6s} n={len(g):6d} {nll(g.p, g.y).mean():.4f} -> {nll(g.pc, g.y).mean():.4f}  z {z:+.1f}")
o["b"] = pd.cut(o.pc, [0, .5, .6, .7, .8, .9, 1.01], right=False)
for st in ("pre", "lineup"):
    print(f"reliability after ({st}): " + "; ".join(f"{b}: {g.pc.mean():.3f}->{g.y.mean():.3f}" for b, g in o[o.state == st].groupby("b", observed=True)))
final = fit(df)
json.dump(final, open(D + "calibration_default.json", "w"))
print("\nshipped:", json.dumps(final))
