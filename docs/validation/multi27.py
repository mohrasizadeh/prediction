import pandas as pd, numpy as np
from load_statsbomb import load
rng = np.random.default_rng(11)
rows = []
for lg in ("PL", "SA", "L1"):
    m, *_ = load(lg); opp = {}
    for r in m.itertuples():
        opp[(r.round, r.home)] = r.away; opp[(r.round, r.away)] = r.home
    d = pd.read_pickle(f"data/audit_rows_{lg}_cond.pkl")
    d = d[d.state.isin(["pre", "lineup"])].copy()
    d["q"] = np.where(d.scope == "team", d.p, d.p * d.p_play).clip(0, 1)
    d = d[(d.q >= 0.5) & (d.q <= 0.97)]          # the kind of legs people combine
    d["opp"] = [opp.get((r, t), -1) for r, t in zip(d["round"], d.team)]
    d["mkey"] = [(r, min(t, o), max(t, o)) for r, t, o in zip(d["round"], d.team, d.opp)]
    d["ent"] = np.where(d.scope == "team", -d.team - 1, d.player)     # entity: player id or team
    for (state, mk), g in d.groupby(["state", "mkey"]):
        g = g.reset_index(drop=True)
        if g.ent.nunique() < 4: continue
        for k in (2, 3, 4):
            for _ in range(60):
                ids = rng.choice(len(g), size=k, replace=False)
                s = g.iloc[ids]
                if s.ent.nunique() < k: continue          # one line per player or team
                rows.append((lg, state, k, float(np.prod(s.q)), float(np.prod(s.y)), float(s.q.min())))
M = pd.DataFrame(rows, columns=["league", "state", "k", "pred", "act", "minq"])
M.to_pickle("multi27.pkl")
print(len(M))
for st in ("pre", "lineup"):
    print("\n", st)
    g = M[M.state == st].groupby("k").agg(n=("pred", "size"), pred=("pred", "mean"), act=("act", "mean")); g["ratio"] = g.act / g.pred
    print(g.round(3).to_string())
    # what factor per pair fits? joint = pred * f^(k choose 2)
    for k in (2, 3, 4):
        x = M[(M.state == st) & (M.k == k)]; pairs = k * (k - 1) / 2
        f = (x.act.mean() / x.pred.mean()) ** (1 / pairs); print(f"  k={k}: per-pair factor {f:.3f}")
