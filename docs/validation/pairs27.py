import pandas as pd, numpy as np, glob
from load_statsbomb import load
rng = np.random.default_rng(7)
out = []
for lg in ("PL", "SA", "L1"):
    m, *_ = load(lg)
    opp = {}
    for r in m.itertuples():
        opp[(r.round, r.home)] = r.away; opp[(r.round, r.away)] = r.home
    d = pd.read_pickle(f"data/audit_rows_{lg}_cond.pkl")
    d = d[d.state.isin(["pre", "lineup"])].copy()
    d["q"] = np.where(d.scope == "team", d.p, d.p * d.p_play).clip(0, 1)
    d = d[(d.q >= 0.35) & (d.q <= 0.97)]
    d["opp"] = [opp.get((r, t), -1) for r, t in zip(d["round"], d.team)]
    d["mkey"] = [(r, min(t, o), max(t, o)) for r, t, o in zip(d["round"], d.team, d.opp)]
    for (state, mk), g in d.groupby(["state", "mkey"]):
        if len(g) < 2: continue
        g = g.reset_index(drop=True)
        n = len(g); idx = rng.integers(0, n, size=(500, 2)); idx = idx[idx[:, 0] != idx[:, 1]]
        a = g.iloc[idx[:, 0]].reset_index(drop=True); b = g.iloc[idx[:, 1]].reset_index(drop=True)
        same_team = a.team.values == b.team.values
        same_pl = (a.scope.values == "player") & (b.scope.values == "player") & (a.player.values == b.player.values)
        same_stat_pl = same_pl & (a.stat.values == b.stat.values)
        both_pl = (a.scope.values == "player") & (b.scope.values == "player")
        tp = same_team & (a.scope.values != b.scope.values)
        typ = np.select([same_stat_pl, same_pl, same_team & both_pl & (a.stat.values == b.stat.values), same_team & both_pl, tp,
                         same_team & (a.scope.values == "team") & (b.scope.values == "team"), ~same_team & (a.scope.values == "team") & (b.scope.values == "team"), ~same_team],
                        ["nested", "same_player", "teammates_same_stat", "teammates_other_stat", "team_and_own_player", "team_team_own", "opp_team_team", "opposing_sides"], "other")
        same_line_team = (a.scope.values == "team") & (b.scope.values == "team") & same_team
        o = pd.DataFrame({"league": lg, "state": state, "type": typ, "qa": a.q.values, "qb": b.q.values, "ya": a.y.values, "yb": b.y.values,
                          "sa": a.stat.values, "sb": b.stat.values})
        out.append(o)
P = pd.concat(out, ignore_index=True)
P = P[P.type != "nested"]
P["pred"] = P.qa * P.qb; P["act"] = P.ya * P.yb
P.to_pickle("pairs27.pkl")
print(len(P))
for st in ("pre", "lineup"):
    print("\n", st)
    g = P[P.state == st].groupby("type").agg(n=("pred", "size"), pred=("pred", "mean"), act=("act", "mean"))
    g["ratio"] = g.act / g.pred
    print(g.round(3).to_string())
