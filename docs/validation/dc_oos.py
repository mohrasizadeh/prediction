"""dc_oos.py -- walk-forward Dixon-Coles (the brain's own strength model) for every EPL match.

For each block of matches, refit on PL matches strictly before the block (last 3 seasons),
then store expected goals for each match in the block. Nothing from the future is used.
"""
import sys, os, time
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "engine"))
import numpy as np, pandas as pd
from strength import DixonColes

df = pd.read_pickle(os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "all.pkl"))
pl = df[(df.comp == "PL") & (df.season <= "2024-25")].sort_values("dt").reset_index(drop=True)
pl["day"] = pl.dt.dt.normalize()
days = sorted(pl.day.unique())
rnd = {d: i for i, d in enumerate(days)}            # dense rank of distinct dates (same rule as the engine)
pl["round"] = pl.day.map(rnd)

BLOCK = 6                                            # distinct match dates per refit
out = []
t0 = time.time()
dates = np.array(days)
start_i = int(np.searchsorted(dates, np.datetime64("2011-08-01")))
seasons_list = sorted(pl.season.unique())
for b0 in range(start_i, len(days), BLOCK):
    blk_days = days[b0:b0 + BLOCK]
    first_round = rnd[blk_days[0]]
    blk = pl[pl["round"].isin([rnd[d] for d in blk_days])]
    cur_season = blk.season.iloc[0]
    k = seasons_list.index(cur_season)
    train = pl[(pl["round"] < first_round) & (pl.season >= seasons_list[max(0, k - 3)])]
    dc = DixonColes().fit(train.home, train.away, train.hg, train.ag, first_round - 1 - train["round"].values)
    for r in blk.itertuples():
        lh, la = dc.expected_goals(r.home, r.away)
        out.append((r.Index, lh, la, dc.rho, r.home in dc.att and 1 or 0, r.away in dc.att and 1 or 0))
    if (b0 // BLOCK) % 10 == 0:
        print(cur_season, b0, len(days), f"{time.time() - t0:.0f}s", flush=True)
o = pd.DataFrame(out, columns=["idx", "lam_h", "lam_a", "rho", "h_known", "a_known"]).set_index("idx")
res = pl.join(o)
res.to_pickle(os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "pl_dc.pkl"))
print("done", len(res), f"{time.time() - t0:.0f}s")
