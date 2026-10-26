"""backtest_real.py -- walk-forward test of the brain on REAL matches, any provider.

Same rule as backtest.py: for each round, refit on earlier rounds only, forecast the round, score it.
This file does not download anything. Feed it three frames in the format of 09_engine_integration.md
(`matches`, `team_game`, `player_game`). `validation/load_statsbomb.py` builds them from open data.

Two scores:
  1. TEAM COUNTS   mean log-likelihood of the observed team total (negative binomial) for each metric.
                   Uses the whole distribution, so it has more power than one threshold.
  2. PLAYER AND TEAM THRESHOLDS   log loss of "reaches the line" forecasts (optional, slower).

A variant is a dict of SoccerEngine keyword arguments. The first variant is the reference.
`oracle=True` hands each variant its match-specific columns (shape of the eleven, how first-choice it is)
at forecast time, as if the lineup were already out. That measures what knowing the lineup is worth.
A layer passes the gate when it beats the reference on the count score in the pooled sample AND
the gain is larger than twice its paired standard error.
"""
from __future__ import annotations

import sys
import time
import numpy as np
import pandas as pd
from scipy.special import gammaln

from core import nb_loglik, log_loss
from engine import SoccerEngine, PLAYER_STATS, PLAYER_THR, TEAM_THR


def run_counts(matches, tg, pg, variants: dict, stats=("shots", "sot", "corners", "tackles"),
               burn=30, refit_every=4, n_draws=30, verbose=True, seed=1, oracle=True):
    """Returns a tidy frame: one row per variant x team-game x stat."""
    engines = {}
    rows = []
    t0 = time.time()
    rounds = sorted(matches["round"].unique())
    tgi = tg.set_index(["game_id", "team"])
    for r in rounds:
        if r < burn:
            continue
        if (r - rounds[0]) % refit_every == 0 or not engines:
            for name, kw in variants.items():
                eng = SoccerEngine(n_draws=n_draws, seed=seed, **kw)
                eng.fit(matches, tg, pg, r)
                engines[name] = eng
            if verbose:
                print(f"  refit at round {r} ({time.time() - t0:.0f}s)", file=sys.stderr)
        for m in matches[matches["round"] == r].itertuples():
            if m.home not in engines[next(iter(engines))].tidx or m.away not in engines[next(iter(engines))].tidx:
                continue
            for name, eng in engines.items():
                # match-specific features: the values the page would know at lineup time
                cols = [c for c, _ in variants[name].get("match_features", ())]
                xf = ({t: {c: tgi.at[(m.game_id, t), c] for c in cols} for t in (m.home, m.away)}
                      if cols and oracle else None)
                mu = eng.team_means(m.home, m.away, xf)
                for team in (m.home, m.away):
                    for s in stats:
                        if s not in mu[team]:
                            continue
                        y = float(tgi.at[(m.game_id, team), s])
                        m_, rr, mb = mu[team][s]
                        rows.append((name, m.game_id, int(r), team, s, y, m_, rr,
                                     float(nb_loglik(np.array(y), np.array(m_), rr))))
                        if name == next(iter(engines)):          # naive baseline, scored once
                            rows.append(("base", m.game_id, int(r), team, s, y, mb, rr,
                                         float(nb_loglik(np.array(y), np.array(mb), rr))))
    return pd.DataFrame(rows, columns=["variant", "game_id", "round", "team", "stat", "y", "mu", "r", "ll"])


def summarize_counts(res: pd.DataFrame, ref: str | None = None, title=""):
    """Mean log-likelihood per variant and metric, and the paired gain over the reference."""
    ref = ref or res["variant"].iloc[0]
    out = []
    pr = lambda *a: out.append(" ".join(str(x) for x in a))
    pr(title)
    pr(f"{'metric':10s}{'variant':22s}{'n':>6s}{'mean ll':>10s}{'gain vs ' + ref:>16s}{'se':>8s}{'z':>7s}")
    base = res[res["variant"] == ref].set_index(["game_id", "team", "stat"])["ll"]
    for stat, g in res.groupby("stat"):
        for v, gg in g.groupby("variant"):
            a = gg.set_index(["game_id", "team", "stat"])["ll"]
            d = (a - base.loc[a.index]).values
            se = d.std(ddof=1) / np.sqrt(len(d)) if len(d) > 2 else float("nan")
            z = d.mean() / se if se and se > 0 else 0.0
            pr(f"{stat:10s}{v:22s}{len(a):>6d}{a.mean():>10.4f}{d.mean():>+16.4f}{se:>8.4f}{z:>+7.2f}")
        pr("")
    return "\n".join(out)


def gate(res: pd.DataFrame, variant: str, ref: str, stat: str | None = None, z_min: float = 2.0):
    """True when `variant` beats `ref` on the pooled count score by more than z_min paired standard errors."""
    g = res if stat is None else res[res["stat"] == stat]
    a = g[g["variant"] == variant].set_index(["game_id", "team", "stat"])["ll"]
    b = g[g["variant"] == ref].set_index(["game_id", "team", "stat"])["ll"]
    d = (a - b.loc[a.index]).values
    se = d.std(ddof=1) / np.sqrt(len(d))
    return bool(d.mean() > 0 and d.mean() / se > z_min), float(d.mean()), float(se)
