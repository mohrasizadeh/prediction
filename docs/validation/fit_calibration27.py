"""Calibrate the "if he plays" player forecasts (docs/27) and check it leave-one-league-out.
Run first:  COND=1 python audit_real.py PL SA L1   (one league per run). Reads data/audit_rows_<L>_cond.pkl.
Player rows are judged on players who played (the forecast is "if he plays"). Team rows are unchanged and keep the
shipped team_shrink. Writes data/calibration_default27.json."""
import glob, os, sys, json, numpy as np, pandas as pd
T = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(T, "..", "..", "backend", "soccer_brain"))
from core import Isotonic
D = os.path.join(T, "data") + os.sep
df = pd.concat([pd.read_pickle(f) for f in sorted(glob.glob(D + "audit_rows_*_cond.pkl"))], ignore_index=True)
df = df[(df.scope == "player") & df.played]
c = lambda p: np.clip(np.asarray(p, float), 0.005, 0.995)
nll = lambda p, y: -(y * np.log(c(p)) + (1 - y) * np.log(1 - c(p)))
CAP = (0.003, 0.97)

def knots(p, y, n=24):
    iso = Isotonic().fit(p, y)
    xs = np.unique(np.r_[np.linspace(0, 1, 41), np.quantile(p, np.linspace(0, 1, n))])
    ys = np.maximum.accumulate(np.clip(iso.predict(xs), *CAP))
    return {"x": [round(float(v), 4) for v in xs], "y": [round(float(v), 4) for v in ys]}

def fit(tr):
    return {st: knots(g.p.values, g.y.values) for st, g in tr.groupby("state")}

o = []
for test in sorted(df.league.unique()):
    cal = fit(df[df.league != test]); te = df[df.league == test].copy(); te["pc"] = te.p
    for st in ("pre", "lineup"):
        m = te.state == st; te.loc[m, "pc"] = np.interp(te.loc[m, "p"], cal[st]["x"], cal[st]["y"])
    o.append(te)
o = pd.concat(o)
print("leave-one-league-out, players who played: log loss as forecast -> after map (z of gain)")
for (lg, st), g in o.groupby(["league", "state"]):
    d = nll(g.pc, g.y) - nll(g.p, g.y); z = -d.mean() / (d.std() / np.sqrt(len(d)))
    print(f"  {lg} {st:6s} n={len(g):6d} {nll(g.p, g.y).mean():.4f} -> {nll(g.pc, g.y).mean():.4f}  z {z:+.1f}")
for st in ("pre", "lineup"):
    g = o[o.state == st]; g = g.assign(b=pd.cut(g.pc, [0, .3, .5, .6, .7, .8, .9, 1.01], right=False))
    print(f"reliability after ({st}): " + "; ".join(f"{b}: {x.pc.mean():.3f}->{x.y.mean():.3f}" for b, x in g.groupby("b", observed=True)))
final = fit(df)
old = json.load(open(os.path.join(T, "..", "..", "backend", "soccer_brain", "calibration_default.json")))
out = {"lineup_player": final["lineup"], "pre_player": final["pre"], "team_shrink": old["team_shrink"]}
json.dump(out, open(D + "calibration_default27.json", "w"))
print("\nshipped:", json.dumps(out)[:200], "...")
