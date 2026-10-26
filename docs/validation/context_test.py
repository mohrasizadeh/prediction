"""context_test.py -- does rest / fixture congestion / rotation pressure add to a Dixon-Coles baseline?

Baseline = the brain's Dixon-Coles expected goals (walk-forward, no future data).
Test    = Poisson regression of goals on those expected goals (as an offset) plus context features.
Score   = leave-one-season-out out-of-sample log-likelihood and 1X2 log loss.
"""
import os, sys, json
import numpy as np, pandas as pd
from scipy.optimize import minimize
from scipy.special import gammaln

HERE = os.path.dirname(os.path.abspath(__file__))
df = pd.read_pickle(os.path.join(HERE, "data", "all.pkl"))
pl = pd.read_pickle(os.path.join(HERE, "data", "pl_dc.pkl"))
pl = pl[(pl.season >= "2011-12")].copy()

EU = {"UCL", "UEL", "UECL"}
CUP = {"EFL", "FA"}

# ---------------------------------------------------------------- schedule per club
sched = []
for s, g in df[df.season >= "2011-12"].groupby("season"):
    plg = g[g.comp == "PL"]
    clubs = set(plg.home) | set(plg.away)
    for r in g.itertuples():
        if r.comp in ("CH", "L1", "L2"):
            continue
        for side, name in (("H", r.home), ("A", r.away)):
            if name in clubs:
                sched.append((name, r.dt, r.comp, r.stage, side, r.season))
sched = pd.DataFrame(sched, columns=["club", "dt", "comp", "stage", "side", "season"]).sort_values(["club", "dt"]).reset_index(drop=True)
by_club = {c: g.reset_index(drop=True) for c, g in sched.groupby("club")}


def neighbours(club, dt):
    g = by_club[club]
    i = int(np.searchsorted(g.dt.values, np.datetime64(dt)))
    prev = g.iloc[i - 1] if i > 0 else None
    # the row at i is the match itself (same dt); next is i+1
    nxt = g.iloc[i + 1] if i + 1 < len(g) else None
    return prev, nxt


# rough importance prior used ONLY by the "pressure" feature (tested, not trusted)
def importance(comp, stage):
    st = (stage or "").lower()
    late = any(k in st for k in ("quarter", "semi", "final"))
    if comp == "UCL":
        return 1.15 if ("finals" in st or "round of 16" in st or late or "knockout" in st or "playoff" in st) else 0.95
    if comp == "UEL":
        return 0.85 if late or "finals" in st else 0.7
    if comp == "UECL":
        return 0.7 if late or "finals" in st else 0.55
    if comp == "FA":
        return 0.75 if late or "round 5" in st or "round 4" in st else 0.55
    if comp == "EFL":
        return 0.7 if late else 0.4
    return 1.0


rows = []
for r in pl.itertuples():
    for side in ("H", "A"):
        club = r.home if side == "H" else r.away
        opp = r.away if side == "H" else r.home
        prev, nxt = neighbours(club, r.dt)
        pg = (r.dt - prev["dt"]).total_seconds() / 86400 if prev is not None else 14.0
        ng = (nxt["dt"] - r.dt).total_seconds() / 86400 if nxt is not None else 14.0
        rows.append(dict(
            idx=r.Index, season=r.season, dt=r.dt, side=side, club=club, opp=opp,
            y=r.hg if side == "H" else r.ag, y_opp=r.ag if side == "H" else r.hg,
            lam=r.lam_h if side == "H" else r.lam_a, lam_opp=r.lam_a if side == "H" else r.lam_h,
            rho=r.rho, home=1 if side == "H" else 0,
            known=(r.h_known if side == "H" else r.a_known),
            prev_gap=min(pg, 14.0), next_gap=min(ng, 14.0),
            prev_comp=prev.comp if prev is not None else "", next_comp=nxt.comp if nxt is not None else "",
            prev_stage=prev.stage if prev is not None else "", next_stage=nxt.stage if nxt is not None else "",
            next_imp=importance(nxt.comp, nxt.stage) if nxt is not None else 0.0,
        ))
T = pd.DataFrame(rows)
T["matchweek_ord"] = T.groupby("season")["dt"].rank(method="dense")
T.to_pickle(os.path.join(HERE, "data", "teamrows.pkl"))
print("team-rows", len(T), "seasons", T.season.nunique())
