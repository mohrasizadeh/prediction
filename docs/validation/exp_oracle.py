"""exp_oracle.py -- what is it worth to KNOW the lineup?

Oracle variants get the real shape of the eleven and how first-choice it is, as the page would once the
lineup is confirmed. If these do not beat the shipped engine, no rule built on lineup shape or on
rotation can help team-level forecasts, however well we predict the lineup.
"""
import sys, os, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "engine"))
import numpy as np, pandas as pd
import backtest_real as BR
import load_statsbomb as L

VARIANTS = {
    "full": dict(),
    "shape_known": dict(match_features=(("n_def", "shape"), ("n_fwd", "shape"))),
    "firstchoice_known": dict(match_features=(("xi_reg", "rotation"),)),
    "changes_known": dict(match_features=(("changes", "rotation"),)),
    "all_known": dict(match_features=(("n_def", "shape"), ("n_fwd", "shape"), ("xi_reg", "rotation"), ("changes", "rotation"))),
}
STATS = ("shots", "sot", "corners", "tackles")

if __name__ == "__main__":
    HERE = os.path.dirname(os.path.abspath(__file__))
    for lg in sys.argv[1:] or ["PL"]:
        t0 = time.time()
        matches, tg, pg, tid = L.load(lg)
        res = BR.run_counts(matches, tg, pg, VARIANTS, stats=STATS, burn=30, refit_every=4, verbose=False)
        res["league"] = lg
        res.to_pickle(os.path.join(HERE, "data", f"res_oracle_{lg}.pkl"))
        print(BR.summarize_counts(res, ref="full", title=f"=== {lg} oracle  ({time.time() - t0:.0f}s)"), flush=True)
