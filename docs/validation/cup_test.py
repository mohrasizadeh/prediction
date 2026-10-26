"""cup_test.py -- how do Premier League clubs do in the League Cup and FA Cup against lower-division clubs?

If clubs rotate in less important games, then at the same strength and venue they should score
a lower goal difference in the EFL Cup than in the FA Cup, and lower when a bigger game follows.
"""
import os, sys
import numpy as np, pandas as pd
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "engine"))
from strength import DixonColes

HERE = os.path.dirname(os.path.abspath(__file__))
df = pd.read_pickle(os.path.join(HERE, "data", "all.pkl"))
pl = df[(df.comp == "PL") & (df.season <= "2024-25")].sort_values("dt").reset_index(drop=True)
pl["day"] = pl.dt.dt.normalize()
days = sorted(pl.day.unique()); rnd = {d: i for i, d in enumerate(days)}; pl["round"] = pl.day.map(rnd)
seasons = sorted(pl.season.unique())

cups = df[df.comp.isin(["EFL", "FA"]) & (df.season >= "2018-19") & (df.season <= "2024-25")].copy()
tier_of = {}
for comp, t in (("CH", 2), ("L1", 3), ("L2", 4), ("NL", 5)):
    for r in df[(df.comp == comp)].itertuples():
        tier_of[(r.season, r.home)] = t; tier_of[(r.season, r.away)] = t
pl_set = {}
for s, g in pl.groupby("season"):
    pl_set[s] = set(g.home) | set(g.away)

rows = []
for r in cups.itertuples():
    ph, pa = r.home in pl_set[r.season], r.away in pl_set[r.season]
    if ph == pa:                       # both PL or neither: skip
        continue
    top, other = (r.home, r.away) if ph else (r.away, r.home)
    top_home = 1 if ph else 0
    gd = (r.hg - r.ag) if ph else (r.ag - r.hg)
    rows.append(dict(season=r.season, comp=r.comp, stage=r.stage, dt=r.dt, top=top, other=other, home=top_home,
                     gd=gd, win=int(gd > 0), loss=int(gd < 0), tier=tier_of.get((r.season, other), 6)))
C = pd.DataFrame(rows)

# strength of the PL club at the cup date (Dixon-Coles on PL games before that day, last 3 seasons)
cache = {}
sstart = {s: pl[pl.season == s].dt.min() for s in seasons}
def fit_at(day):
    if day in cache: return cache[day]
    cur = max(s for s in seasons if sstart[s] - pd.Timedelta(days=60) <= day)
    k = seasons.index(cur)
    tr = pl[(pl.dt < day) & (pl.season >= seasons[max(0, k - 3)])]
    dc = DixonColes().fit(tr.home, tr.away, tr.hg, tr.ag, tr["round"].max() - tr["round"].values)
    cache[day] = dc
    return dc

S = []
for r in C.itertuples():
    day = r.dt.normalize()
    dc = fit_at(day)
    S.append(dc.att.get(r.top, 0.0) + dc.dfn.get(r.top, 0.0))
C["strength"] = S

# what is next for the club?
EU = {"UCL", "UEL", "UECL"}
allm = df[(df.season >= "2018-19") & (df.season <= "2024-25") & df.comp.isin(["PL", "EFL", "FA"] + list(EU))]
by = {}
for r in allm.itertuples():
    for n in (r.home, r.away):
        by.setdefault((r.season, n), []).append((r.dt, r.comp, r.stage))
for k in by: by[k].sort()
nxt_gap, nxt_comp, prv_gap = [], [], []
for r in C.itertuples():
    L = by.get((r.season, r.top), [])
    after = [x for x in L if x[0] > r.dt]; before = [x for x in L if x[0] < r.dt]
    nxt_gap.append((after[0][0] - r.dt).total_seconds() / 86400 if after else 14.0)
    nxt_comp.append(after[0][1] if after else "")
    prv_gap.append((r.dt - before[-1][0]).total_seconds() / 86400 if before else 14.0)
C["next_gap"], C["next_comp"], C["prev_gap"] = nxt_gap, nxt_comp, prv_gap
C["eu_next"] = (C.next_comp.isin(EU) & (C.next_gap <= 4.5)).astype(float)
C["pl_next"] = ((C.next_comp == "PL") & (C.next_gap <= 3.5)).astype(float)
C["short"] = (C.prev_gap < 3.5).astype(float)
C["efl"] = (C.comp == "EFL").astype(float)
st = C.stage.str.lower()
C["late"] = st.str.contains("quarter|semi|final|round 5|fifth|round 4|fourth|round of|last 16").astype(float)
C.to_pickle(os.path.join(HERE, "data", "cups.pkl"))
print(C.groupby(["comp", "tier"]).agg(n=("gd", "size"), gd=("gd", "mean"), win=("win", "mean"), loss=("loss", "mean")).round(3))
print(C.groupby("comp").agg(n=("gd", "size"), gd=("gd", "mean"), win=("win", "mean"), strength=("strength", "mean")).round(3))
