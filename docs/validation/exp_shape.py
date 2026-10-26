"""exp_shape.py -- refine: which part of the lineup shape matters, and what if the lineup is NOT yet known?"""
import sys, os, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "engine"))
import numpy as np, pandas as pd
import backtest_real as BR
import load_statsbomb as L

G = ("goals",)
VARIANTS = {
    "full": dict(extra_stats=G),
    "shape_df": dict(extra_stats=G, match_features=(("n_def", "shape"), ("n_fwd", "shape"))),
    "shape_dmf": dict(extra_stats=G, match_features=(("n_def", "shape"), ("n_mid", "shape"), ("n_fwd", "shape"))),
    "shape_d": dict(extra_stats=G, match_features=(("n_def", "shape"),)),
    "shape_f": dict(extra_stats=G, match_features=(("n_fwd", "shape"),)),
}
STATS = ("shots", "sot", "corners", "tackles", "goals")
if __name__ == "__main__":
    HERE = os.path.dirname(os.path.abspath(__file__))
    mode = sys.argv[1]
    for lg in sys.argv[2:]:
        t0 = time.time()
        matches, tg, pg, tid = L.load(lg)
        res = BR.run_counts(matches, tg, pg, VARIANTS, stats=STATS, burn=30, refit_every=4, verbose=False, oracle=(mode == "oracle"))
        res["league"] = lg
        res.to_pickle(os.path.join(HERE, "data", f"res_shape{mode}_{lg}.pkl"))
        print(lg, "done", round(time.time() - t0))
