"""stakes_test.py -- do clubs with 'nothing to play for' late in the season underperform the baseline?"""
import os
import numpy as np, pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
pl = pd.read_pickle(os.path.join(HERE, "data", "pl_dc.pkl"))
pl = pl[pl.season >= "2011-12"].sort_values("dt").reset_index(drop=True)
rows = []
for season, g in pl.groupby("season"):
    teams = sorted(set(g.home) | set(g.away))
    pts = {t: 0 for t in teams}; played = {t: 0 for t in teams}
    days = sorted(g.dt.dt.normalize().unique())
    for d in days:
        today = g[g.dt.dt.normalize() == d]
        # table BEFORE today's matches
        rem = {t: 38 - played[t] for t in teams}
        order = sorted(teams, key=lambda t: -pts[t])
        rank = {t: i + 1 for i, t in enumerate(order)}
        p7 = pts[order[6]]
        leader = order[0]
        for r in today.itertuples():
            for side, t in (("H", r.home), ("A", r.away)):
                mx = pts[t] + 3 * rem[t]
                below = [j for j in teams if pts[j] < pts[t] or (pts[j] == pts[t] and rank[j] > rank[t])]
                catch = sum(1 for j in below if pts[j] + 3 * rem[j] >= pts[t])
                safe = rank[t] + catch <= 17
                no_europe = mx < p7 and rank[t] > 7
                title_gone = pts[leader] > mx and t != leader
                second_max = max(pts[j] + 3 * rem[j] for j in teams if j != leader)
                champ_clinched = t == leader and pts[t] > second_max
                rows.append(dict(season=season, dt=r.dt, idx=r.Index, side=side, team=t, rem=rem[t],
                                 dead=bool(safe and no_europe and title_gone) and rem[t] <= 8,
                                 champ=bool(champ_clinched), relegated=bool(mx < pts[order[16]] and rank[t] >= 18)))
        for r in today.itertuples():
            pts[r.home] += 3 if r.hg > r.ag else (1 if r.hg == r.ag else 0)
            pts[r.away] += 3 if r.ag > r.hg else (1 if r.hg == r.ag else 0)
            played[r.home] += 1; played[r.away] += 1
S = pd.DataFrame(rows)
T = pd.read_pickle(os.path.join(HERE, "data", "teamrows.pkl"))
T = T.merge(S[["idx", "side", "dead", "champ", "relegated"]], on=["idx", "side"], how="left")
T = T[(T.known == 1) & (T.matchweek_ord > 4)]
T["res_gd"] = (T.y - T.y_opp) - (T.lam - T.lam_opp)
T["res"] = T.y - T.lam
def s(x): return f"{x.mean():+.3f} +/- {x.std(ddof=1) / np.sqrt(len(x)):.3f} (n={len(x)})"
print("Goal difference above the Dixon-Coles baseline")
for lab, m in (("mid-table, nothing to play for (last 8 games)", T.dead == True), ("champion already clinched", T.champ == True),
               ("already relegated", T.relegated == True), ("everyone else, same last-8-games window", (T.dead != True) & (T.champ != True) & (T.relegated != True) & (T.matchweek_ord > 0))):
    if m.sum() > 2:
        print(f"  {lab:50s} {s(T[m].res_gd)}   own goals {s(T[m].res)}")
d = T[T.dead == True]; o = T[(T.dead != True) & (T.champ != True) & (T.relegated != True)]
print("  opponent of a no-stakes club (their view):")
opp = T.merge(T[T.dead == True][["idx"]].drop_duplicates(), on="idx")
opp = opp[opp.dead != True]
print("   ", s(opp.res_gd))
