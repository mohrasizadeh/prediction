"""End-to-end: the real engine, walk-forward on StatsBomb 2015/16, before vs after normalised averages.
Scores every forecast line (team shots/corners, player shots/sot/tackles) by log loss, both states."""
import os, sys, time
import numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(HERE, "..", "..", "backend", "soccer_brain"))
from load_statsbomb import load
import engine as E
from core import fit_dispersion
E.PLAYER_THR.clear(); E.PLAYER_THR.update({"shots": [0.5, 1.5, 2.5, 3.5], "sot": [0.5, 1.5], "tackles": [0.5, 1.5, 2.5, 3.5]})
E.TEAM_THR.clear(); E.TEAM_THR.update({"shots": [8.5, 10.5, 12.5, 14.5, 16.5], "corners": [2.5, 3.5, 4.5, 5.5, 6.5, 7.5], "tackles": [14.5, 17.5, 20.5]})
VAR = {"today": {}, "decay20": dict(style_half_life=20), "decay20+opp": dict(style_half_life=20, style_opp_adjust=("shots",)),
       "decay20+opp+cap99": dict(style_half_life=20, style_opp_adjust=("shots",), style_cap_q=0.99),
       "all+tackles80": dict(style_half_life=20, style_opp_adjust=("shots",), style_cap_q=0.99, player_prior={"tackles": 80.0})}
league, var = sys.argv[1], sys.argv[2]
matches, tg, pg_all, tid = load(league)
pg = pg_all[pg_all.minutes > 0].copy()
eng = E.SoccerEngine(interactions=True, lineup=False, n_draws=20, seed=1, **VAR[var])
eng.r_player = {"shots": 6.0, "sot": 5.0, "tackles": 10.0}
pgi = pg_all.set_index(["game_id", "player"]); tgi = tg.set_index(["game_id", "team"])
starters = pg_all[pg_all["started"] == 1].groupby(["game_id", "team"])["player"].apply(set).to_dict()
rounds = sorted(matches["round"].unique()); burn = rounds[len(rounds) // 3]
rows = []; last = None; t0 = time.time()
for r in rounds:
    if r < burn: continue
    if last is None or r - last >= 4:
        eng.fit(matches, tg, pg, r); last = r
    for m in matches[matches["round"] == r].itertuples():
        for state in ("pre", "lineup"):
            lu = {} if state == "pre" else {t: starters.get((m.game_id, t), set()) for t in (m.home, m.away)}
            fcs, _ = eng.predict_fixture(m.home, m.away, lu)
            for f in fcs:
                if f.scope == "player":
                    try: y = float(pgi.at[(m.game_id, f.player), f.stat])
                    except KeyError: y = 0.0
                else:
                    y = float(tgi.at[(m.game_id, f.team), f.stat])
                rows.append((league, var, r, m.game_id, state, f.scope, f.stat, f.thr, f.team, f.player or -1, f.p, float(y > f.thr)))
pd.DataFrame(rows, columns=["league", "var", "round", "game", "state", "scope", "stat", "thr", "team", "player", "p", "y"]).to_pickle(
    os.path.join(HERE, "data", f"e2e_{league}_{var}.pkl"))
print(league, var, "done", len(rows), f"{time.time()-t0:.0f}s")
