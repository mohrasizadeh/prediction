"""Real-data audit of the forecast engine's percentages (StatsBomb open data, 2015/16 PL, Serie A, Ligue 1).
Walk-forward: refit on earlier match dates only, forecast the next dates, score. Two states: before lineups
(no lineup) and with the real starting eleven (confirmed). Writes one row per forecast."""
import os, sys, time, pickle
import numpy as np, pandas as pd
T = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, T); sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "backend", "soccer_brain"))
from load_statsbomb import load
from engine import SoccerEngine, PLAYER_STATS, PLAYER_THR
from core import fit_dispersion, tier

league = sys.argv[1]
matches, tg, pg_all, tid = load(league)
pg = pg_all[pg_all.minutes > 0].copy()          # the engine sees only games a player featured in, like the live feed
COND = bool(int(os.environ.get("COND", "0")))     # 1 = forecasts "if he plays" (docs/27)
eng = SoccerEngine(interactions=True, lineup=False, n_draws=30, seed=1, cond_play=COND)
eng.r_player = {"shots": 6.0, "sot": 5.0, "tackles": 10.0}
pgi = pg_all.set_index(["game_id", "player"]); tgi = tg.set_index(["game_id", "team"])
starters = pg_all[pg_all["started"] == 1].groupby(["game_id", "team"])["player"].apply(set).to_dict()
rounds = sorted(matches["round"].unique()); burn = rounds[len(rounds) // 3]
pool = {s: ([], []) for s in PLAYER_STATS}
rows = []; t0 = time.time(); last_fit = None
for r in rounds:
    if r < burn: continue
    if last_fit is None or r - last_fit >= 4:
        eng.fit(matches, tg, pg, r); last_fit = r
        for s in PLAYER_STATS:
            mu, y = pool[s]
            if len(y) >= 200: eng.r_player[s] = fit_dispersion(np.array(mu), np.array(y))
        print(league, "refit", r, f"{time.time()-t0:.0f}s", file=sys.stderr, flush=True)
    for m in matches[matches["round"] == r].itertuples():
        for state in ("pre", "lineup"):
            lu = {} if state == "pre" else {t: starters.get((m.game_id, t), set()) for t in (m.home, m.away)}
            fcs, dcp = eng.predict_fixture(m.home, m.away, lu)
            for f in fcs:
                if f.scope == "player":
                    try: y_cnt = float(pgi.at[(m.game_id, f.player), f.stat])
                    except KeyError: y_cnt = 0.0              # not in the matchday squad: did not reach the line
                    played = (m.game_id, f.player) in pgi.index and float(pgi.at[(m.game_id, f.player), "minutes"]) > 0
                else:
                    y_cnt = float(tgi.at[(m.game_id, f.team), f.stat]); played = True
                rows.append(dict(league=league, round=r, state=state, scope=f.scope, stat=f.stat, thr=f.thr, team=f.team, player=f.player,
                                 p=f.p, lo=f.lo, p_raw=f.p_raw, p_base=f.p_base, p_play=f.p_play, expected=f.expected,
                                 y=float(y_cnt > f.thr), played=played, tier=tier(f.p, f.lo, state == "lineup" or f.scope == "team")))
                if state == "pre" and f.scope == "player" and f.thr == PLAYER_THR[f.stat][0] and played:
                    pool[f.stat][0].append(f.expected if COND else f.expected / max(f.p_play, 1e-3)); pool[f.stat][1].append(y_cnt)   # expected shots if he plays
pd.DataFrame(rows).to_pickle(os.path.join(T, "data", f"audit_rows_{league}{'_cond' if COND else ''}.pkl"))
print(league, "done", len(rows), f"{time.time()-t0:.0f}s", file=sys.stderr)
