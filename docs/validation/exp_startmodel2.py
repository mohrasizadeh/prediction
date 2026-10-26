import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "engine"))
import numpy as np, pandas as pd
import context as C
from exp_startmodel import build, ll, HERE
ctx_all = pd.read_pickle(os.path.join(HERE, "data", "ctx_rows.pkl"))
R = pd.concat([build(lg, ctx_all) for lg in ("PL", "SA", "L1")], ignore_index=True)
R = R[R["regular"].notna() & (R["round"] >= 8)].copy()
tr_mask = np.zeros(len(R), bool)
for lg, g in R.groupby("league"):
    tr_mask[R.index.get_indexer(g.index)] = (g["round"] <= g["round"].quantile(0.6)).values
tr, te = R[tr_mask], R[~tr_mask].copy()
m = C.StartModel(l2=8.0).fit(tr)
X = m.design(te, te["regular"].values); p0 = te["prior"].values
p1 = 1 / (1 + np.exp(-(m._logit(p0) + X @ m.w))); y = te["started"].values.astype(float)
te["d"] = ll(p1, y) - ll(p0, y)
def s(x): return f"{x.mean():+.5f} +/- {x.std(ddof=1)/np.sqrt(len(x)):.5f} (n={len(x)})"
print("gain in log-likelihood per player-row, by calendar situation (test = last 40% of each season)")
for lab, mask in (("short rest (<= 3.5 days)", te.short == 1), ("normal rest", te.short == 0),
                  ("short rest AND regular starter (>= 0.7)", (te.short == 1) & (te.regular >= 0.7)),
                  ("short rest AND fringe player (<= 0.3)", (te.short == 1) & (te.regular <= 0.3)),
                  ("many matches lately (congestion >= 0.5)", te.congestion >= 0.5)):
    print(f"  {lab:46s} {s(te[mask].d)}")
# what the club-level sum looks like: predicted starters among regulars in short rest vs reality
sub = te[(te.short == 1) & (te.regular >= 0.7)]
print("\nregular starters on short rest: actual start rate", round(sub.started.mean(), 3), "| baseline said", round(sub.prior.mean(), 3), "| model said", round(pd.Series(1/(1+np.exp(-(m._logit(sub.prior.values) + m.design(sub, sub.regular.values) @ m.w)))).mean(), 3))
sub = te[(te.short == 0) & (te.regular >= 0.7)]
print("regular starters on normal rest:   actual start rate", round(sub.started.mean(), 3), "| baseline said", round(sub.prior.mean(), 3))
