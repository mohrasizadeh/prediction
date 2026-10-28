import glob, numpy as np, pandas as pd
import os
P = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data") + "/"
d = pd.concat([pd.read_pickle(f) for f in glob.glob(P + "e2e_*.pkl")])
eps = 1e-6
d["ll"] = -(d.y * np.log(np.clip(d.p, eps, 1 - eps)) + (1 - d.y) * np.log(np.clip(1 - d.p, eps, 1 - eps)))
key = ["league", "game", "state", "scope", "stat", "thr", "team", "player"]
base = d[d["var"] == "today"].set_index(key)["ll"]
for v in sorted(set(d["var"]) - {"today"}):
    x = d[d["var"] == v].set_index(key)["ll"]
    j = pd.concat([base.rename("b"), x.rename("x")], axis=1, join="inner")
    j["g"] = j["b"] - j["x"]                       # positive = better than today
    print(f"\n== {v}  (gain in log loss per forecast x1000, positive = better)")
    for (sc, st), g in j.groupby(level=["scope", "stat"]):
        z = g["g"].mean() / (g["g"].std(ddof=1) / np.sqrt(len(g)))
        per = {lg: round(float(h["g"].mean() * 1000), 2) for lg, h in g.groupby(level="league")}
        print(f"  {sc:6s} {st:8s} {g['g'].mean()*1000:+7.2f}  z {z:+5.1f}  {per}  n={len(g)}")
