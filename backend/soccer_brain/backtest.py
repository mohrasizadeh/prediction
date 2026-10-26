"""backtest.py -- walk-forward test of the soccer brain.

For each round: refit on past rounds only, forecast the round, then score it.
Compares five forecasters on the same questions:
  raw       last-10 rate (what a basic stats site shows)
  base      simple model with no team or matchup context
  plain     engine WITHOUT tactical matchup terms and WITHOUT lineup effects
  full      shipped engine: style matchups, no lineup effects
  lineup    experiment: full + opponent/own lineup effects
Then layers expanding-window calibration and tiers on top of `full`.

Run on simulated data now; the same harness runs on real data later.
"""
from __future__ import annotations

import sys
import time
import numpy as np
import pandas as pd

from core import Isotonic, fit_dispersion, log_loss, brier, tier
from engine import SoccerEngine, PLAYER_STATS, PLAYER_THR
from simulate import simulate_league


def run(seed=11, burn=10, refit_every=4, n_draws=60, verbose=True):
    matches, tg, pg, truth = simulate_league(seed=seed)
    full = SoccerEngine(interactions=True, lineup=False, n_draws=n_draws, seed=1)
    nolu = SoccerEngine(interactions=True, lineup=True, n_draws=n_draws, seed=1)
    plain = SoccerEngine(interactions=False, lineup=False, n_draws=n_draws, seed=1)
    rng = np.random.default_rng(5)

    pg_idx = pg.set_index(["game_id", "player"])
    tg_idx = tg.set_index(["game_id", "team"])
    starters = pg[pg["started"] == 1].groupby(["game_id", "team"])["player"].apply(set).to_dict()

    rows, fixture_rows = [], []
    pool = {s: ([], []) for s in PLAYER_STATS}
    t0 = time.time()
    n_rounds = int(matches["round"].max()) + 1

    for r in range(burn, n_rounds):
        if (r - burn) % refit_every == 0:
            full.fit(matches, tg, pg, r)
            nolu.fit(matches, tg, pg, r)
            plain.fit(matches, tg, pg, r)
            for s in PLAYER_STATS:
                mu, y = pool[s]
                rn = fit_dispersion(np.array(mu), np.array(y))
                full.r_player[s] = nolu.r_player[s] = plain.r_player[s] = rn
            if verbose:
                print(f"  refit at round {r}  ({time.time() - t0:.0f}s)", file=sys.stderr)

        for m in matches[matches["round"] == r].itertuples():
            lineups = {}
            for team in (m.home, m.away):
                if rng.random() < 0.6:
                    lineups[team] = starters[(m.game_id, team)]
            f_full, dcp = full.predict_fixture(m.home, m.away, lineups)
            f_nolu, _ = nolu.predict_fixture(m.home, m.away, lineups)
            f_plain, _ = plain.predict_fixture(m.home, m.away, lineups)
            res = 0 if m.hg > m.ag else (1 if m.hg == m.ag else 2)
            fixture_rows.append((dcp["p_home"], dcp["p_draw"], dcp["p_away"], res))

            for a, b, n in zip(f_full, f_plain, f_nolu):
                assert (a.player, a.stat, a.thr, a.team) == (b.player, b.stat, b.thr, b.team) == (n.player, n.stat, n.thr, n.team)
                if a.scope == "player":
                    y_cnt = pg_idx.loc[(m.game_id, a.player), a.stat]
                else:
                    y_cnt = tg_idx.loc[(m.game_id, a.team), a.stat]
                y = float(y_cnt > a.thr)
                rows.append(dict(round=r, scope=a.scope, stat=a.stat, thr=a.thr, team=a.team,
                                 player=a.player, p_full=a.p, lo_full=a.lo, p_plain=b.p, p_lineup=n.p,
                                 p_raw=a.p_raw, p_base=a.p_base, y=y, count=float(y_cnt),
                                 expected=a.expected, p_play=a.p_play, confirmed=a.confirmed,
                                 reasons=" | ".join(a.reasons),
                                 opp_tac=",".join(a.opp_tactics), opp_key=len(a.opp_key_players)))
                if a.scope == "player" and a.thr == PLAYER_THR[a.stat][0]:
                    pool[a.stat][0].append(a.expected); pool[a.stat][1].append(float(y_cnt))
    df = pd.DataFrame(rows)
    fx = np.array(fixture_rows)
    return df, fx, full, nolu, truth


def calibrate_expanding(df, start_round=20, min_n=400):
    """Fit isotonic on earlier rounds only, apply to the current round."""
    df = df.copy()
    df["p_cal"] = np.nan; df["lo_cal"] = np.nan
    for key, g in df.groupby(["scope", "stat", "thr"]):
        idx = g.index.values; rnd = g["round"].values
        for r in range(start_round, int(df["round"].max()) + 1):
            past = rnd < r; now = rnd == r
            if not now.any():
                continue
            if past.sum() >= min_n:
                iso = Isotonic().fit(g["p_full"].values[past], g["y"].values[past])
                df.loc[idx[now], "p_cal"] = iso.predict(g["p_full"].values[now])
                df.loc[idx[now], "lo_cal"] = iso.predict(g["lo_full"].values[now])
    return df


def report(df, fx, engine, truth, start_round=20, lu_engine=None):
    out = []
    pr = lambda *a: out.append(" ".join(str(x) for x in a))

    # ---- team strength sanity
    dc = engine.dc
    est = np.array([dc.att[t] - dc.dfn[t] for t in dc.teams])
    tru = np.array([truth["att"][t] - truth["dfn"][t] for t in dc.teams])
    base = np.bincount(fx[:, 3].astype(int), minlength=3) / len(fx)
    ll_dc = -np.mean(np.log(np.maximum(fx[np.arange(len(fx)), fx[:, 3].astype(int)], 1e-6)))
    ll_fr = -np.mean(np.log(base[fx[:, 3].astype(int)]))
    pr("TEAM STRENGTH (Dixon-Coles)")
    pr(f"  correlation of fitted vs true strength: {np.corrcoef(est, tru)[0, 1]:.2f}")
    pr(f"  match outcome log loss: engine {ll_dc:.4f}  vs league frequencies {ll_fr:.4f}  ({len(fx)} matches)")

    # ---- evaluation set: players expected to play
    ev = df[(df["scope"] == "team") | (df["p_play"] >= 0.5)].copy()
    pr("\nFORECAST QUALITY (log loss, lower is better)")
    pr(f"{'market':<22}{'n':>6}{'rate':>7}{'raw':>8}{'base':>8}{'plain':>8}{'full':>8}{'lineup':>8}")
    for key, g in ev.groupby(["scope", "stat", "thr"]):
        name = f"{key[0]} {key[1]} {key[2]:g}+"
        pr(f"{name:<22}{len(g):>6}{g['y'].mean():>7.2f}"
           f"{log_loss(g['p_raw'], g['y']):>8.3f}{log_loss(g['p_base'], g['y']):>8.3f}"
           f"{log_loss(g['p_plain'], g['y']):>8.3f}{log_loss(g['p_full'], g['y']):>8.3f}{log_loss(g['p_lineup'], g['y']):>8.3f}")
    for scope in ("player", "team"):
        g = ev[ev["scope"] == scope]
        pr(f"{'ALL ' + scope:<22}{len(g):>6}{g['y'].mean():>7.2f}"
           f"{log_loss(g['p_raw'], g['y']):>8.3f}{log_loss(g['p_base'], g['y']):>8.3f}"
           f"{log_loss(g['p_plain'], g['y']):>8.3f}{log_loss(g['p_full'], g['y']):>8.3f}{log_loss(g['p_lineup'], g['y']):>8.3f}")
    pr("  raw=last-10 rate | base=no team context | plain=no matchup terms")
    pr("  full=shipped engine | lineup=full + lineup effects (opponent and own personnel)")

    # ---- does the opponent-tactic / lineup layer help where it should?
    pr("\nOPPONENT TACTIC AND PERSONNEL (team shots 11.5+, log loss full -> lineup)")
    t = ev[(ev["scope"] == "team") & (ev["stat"] == "shots")]
    for label, mask in (("opponent plays a low block", t["opp_tac"].str.contains("low_block")),
                        ("opponent plays a high press", t["opp_tac"].str.contains("high_press")),
                        ("opponent is possession-based", t["opp_tac"].str.contains("possession")),
                        ("no named opponent tactic", t["opp_tac"] == "")):
        g = t[mask]
        if len(g) >= 30:
            pr(f"  {label:<30} n={len(g):4d}  full {log_loss(g['p_full'], g['y']):.3f}  lineup {log_loss(g['p_lineup'], g['y']):.3f}")
    # recovery of hidden star effects
    P = lu_engine.pidx
    qd = np.array([truth["q_def"][p] for p in P]); qa = np.array([truth["q_att"][p] for p in P])
    posn = np.array([lu_engine.pl[p]["pos"] for p in P])
    own_c, opp_c = lu_engine.lu["shots"]
    d_mask = np.isin(posn, ["DEF", "MID"]); a_mask = np.isin(posn, ["FWD", "MID"])
    pr(f"  recovery (shots): opponent-side coefficient vs true defender quality  r = {np.corrcoef(opp_c[d_mask], qd[d_mask])[0, 1]:+.2f} (expect negative)")
    pr(f"  recovery (shots): own-side coefficient vs true attacker quality        r = {np.corrcoef(own_c[a_mask], qa[a_mask])[0, 1]:+.2f} (expect positive)")

    # ---- calibration and tiers
    cal = calibrate_expanding(df, start_round=start_round)
    c = cal[((cal["scope"] == "team") | (cal["p_play"] >= 0.5)) & cal["p_cal"].notna()].copy()
    pr(f"\nCALIBRATION (rounds {start_round}+, isotonic fitted on earlier rounds only)")
    pr(f"  log loss  full {log_loss(c['p_full'], c['y']):.4f}  calibrated {log_loss(c['p_cal'], c['y']):.4f}  raw {log_loss(c['p_raw'], c['y']):.4f}")
    pr(f"  brier     full {brier(c['p_full'], c['y']):.4f}  calibrated {brier(c['p_cal'], c['y']):.4f}  raw {brier(c['p_raw'], c['y']):.4f}")
    pr("\nRELIABILITY (calibrated)")
    bins = [0, 0.3, 0.5, 0.6, 0.7, 0.8, 0.9, 1.01]
    for a, b in zip(bins[:-1], bins[1:]):
        g = c[(c["p_cal"] >= a) & (c["p_cal"] < b)]
        if len(g) >= 40:
            pr(f"  stated {a:.1f}-{min(b, 1):.1f}  n={len(g):5d}  stated avg {g['p_cal'].mean():.3f}  actual {g['y'].mean():.3f}")

    c["tier"] = [tier(p, lo, cf if sc == "player" else True)
                 for p, lo, cf, sc in zip(c["p_cal"], c["lo_cal"], c["confirmed"], c["scope"])]
    pr("\nTIERS (calibrated forecasts)")
    for t in ("Strong", "Solid", "Watch"):
        g = c[c["tier"] == t]
        if len(g):
            pr(f"  {t:<7} n={len(g):5d}  stated avg {g['p_cal'].mean():.3f}  actual {g['y'].mean():.3f}")
    ex = c[(c["tier"] == "Strong") & (c["scope"] == "player")].head(3)
    if len(ex):
        pr("\nSAMPLE REASONS (Strong, player)")
        for r in ex.itertuples():
            pr(f"  {r.stat} {r.thr:g}+  p={r.p_cal:.2f}  {r.reasons}")
    return "\n".join(out)


if __name__ == "__main__":
    df, fx, eng, lu_eng, truth = run()
    print(report(df, fx, eng, truth, lu_engine=lu_eng))
