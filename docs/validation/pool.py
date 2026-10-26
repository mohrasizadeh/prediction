import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "engine"))
import numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__))
def pooled(prefix, ref="full"):
    res = pd.concat([pd.read_pickle(os.path.join(HERE, "data", f"res_{prefix}_{lg}.pkl")) for lg in ("PL", "SA", "L1")], ignore_index=True)
    res["key"] = res.league + "|" + res.game_id.astype(str) + "|" + res.team.astype(str) + "|" + res.stat
    rows = []
    for stat, g in res.groupby("stat"):
        base = g[g.variant == ref].set_index("key")["ll"]
        for v, gg in g.groupby("variant"):
            a = gg.set_index("key")["ll"]; d = (a - base.loc[a.index]).values
            se = d.std(ddof=1) / np.sqrt(len(d)) if len(d) > 2 else np.nan
            rows.append((stat, v, len(d), a.mean(), d.mean(), se, d.mean() / se if se else 0.0))
    out = pd.DataFrame(rows, columns=["stat", "variant", "n", "mean_ll", "gain", "se", "z"])
    # all four core metrics together
    allm = []
    core = res[res.stat.isin(["shots", "sot", "corners", "tackles"])]
    base = core[core.variant == ref].set_index("key")["ll"]
    for v, gg in core.groupby("variant"):
        a = gg.set_index("key")["ll"]; d = (a - base.loc[a.index]).values
        se = d.std(ddof=1) / np.sqrt(len(d)); allm.append(("ALL 4 core", v, len(d), a.mean(), d.mean(), se, d.mean() / se))
    return pd.concat([out, pd.DataFrame(allm, columns=out.columns)], ignore_index=True)
if __name__ == "__main__":
    pd.set_option("display.width", 200)
    for prefix in ("tactics", "oracle"):
        try:
            t = pooled(prefix)
        except FileNotFoundError as e:
            print(prefix, "missing", e); continue
        print(f"\n=== POOLED over Premier League, Serie A, Ligue 1 (2015/16): {prefix}")
        print(t.round(4).to_string(index=False))
