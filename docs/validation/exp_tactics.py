"""exp_tactics.py -- does the tactics layer improve forecasts of team metrics on real matches?"""
import sys, os, time, pickle
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "engine"))
import numpy as np, pandas as pd
import backtest_real as BR
import load_statsbomb as L

X = ("fouls", "yellow")
VARIANTS = {
    "full": dict(extra_stats=X),
    "plain": dict(interactions=False, extra_stats=X),
    "tact_main": dict(tactics=True, tactic_interactions=False, extra_stats=X),
    "tact": dict(tactics=True, extra_stats=X),
    "tact_shape": dict(tactics=True, shape=True, extra_stats=X),
}
STATS = ("shots", "sot", "corners", "tackles", "fouls", "yellow")

if __name__ == "__main__":
    leagues = sys.argv[1:] or ["PL"]
    HERE = os.path.dirname(os.path.abspath(__file__))
    for lg in leagues:
        t0 = time.time()
        matches, tg, pg, tid = L.load(lg)
        res = BR.run_counts(matches, tg, pg, VARIANTS, stats=STATS, burn=30, refit_every=4, verbose=False)
        res["league"] = lg
        res.to_pickle(os.path.join(HERE, "data", f"res_tactics_{lg}.pkl"))
        print(BR.summarize_counts(res, ref="full", title=f"=== {lg}  ({time.time() - t0:.0f}s)"), flush=True)
