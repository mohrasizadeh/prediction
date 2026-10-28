"""player_norm.py -- does capping a player's big games, or shrinking harder, predict his next game better?

StatsBomb 2015/16, Premier League, Serie A, Ligue 1. Walk-forward by match date.
The engine's player number is his share of the team's total: mu = team_total x share x minutes / 90.
To isolate the averaging, this test uses the real team total and the real minutes of the next game
(the same for every variant), so only the share estimate differs.
    today      shrunk share, prior strength 40 (team-stat units), half-life 20 games  (engine.py)
    capS       each past game's count capped at the position's q-quantile per 90 before averaging
    strength   prior strength 20 / 80
Score: negative binomial log likelihood (engine dispersion), per player-game with minutes >= 15.
"""
import os, sys
import numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "backend", "soccer_brain"))
from core import shrunk_rate, nb_sf
from team_norm import nb_ll

SB = os.path.join(HERE, "data", "sb")
R = {"shots": 6.0, "sot": 5.0, "tackles": 10.0}


def frames(lg):
    pg = pd.read_pickle(os.path.join(SB, f"pg_{lg}.pkl"))
    tg = pd.read_pickle(os.path.join(SB, f"tg_{lg}.pkl"))
    mt = pd.read_pickle(os.path.join(SB, f"mt_{lg}.pkl"))
    date = dict(zip(mt["match_id"], pd.to_datetime(mt["date"])))
    tot = tg.set_index(["match_id", "team"])[["shots", "sot", "tackles"]]
    pg = pg.join(tot, on=["match_id", "team"], rsuffix="_team")
    pg["date"] = pg["match_id"].map(date)
    return pg.dropna(subset=["shots_team"]).sort_values("date")


def run(pg, s, strength=40.0, half=20.0, cap_q=None):
    played = pg[pg["minutes"] > 0]
    out = []
    hist = {}
    pos_vals = {}
    rho = {}
    for d, day in played.groupby("date", sort=True):
        # league share by position from the past
        for r in day.itertuples(index=False):
            h = hist.get(r.player)
            if h is not None and len(h["c"]) >= 3 and r.minutes >= 15:
                c = np.array(h["c"]); e = np.array(h["e"])
                if cap_q is not None:
                    pv = pos_vals.get(r.pos, [])
                    if len(pv) > 200:
                        cap90 = np.quantile(pv, cap_q)
                        c = np.minimum(c, np.maximum(1.0, cap90 * np.array(h["m"]) / 90.0))
                prior = rho.get(r.pos, (1.0, 1.0)); prior = prior[0] / max(prior[1], 1e-9)
                post = shrunk_rate(c, e, prior, strength, half)
                mu = getattr(r, s + "_team") * post.mean * r.minutes / 90.0
                out.append((r.pos, mu, float(getattr(r, s))))
        for r in day.itertuples(index=False):
            h = hist.setdefault(r.player, {"c": [], "e": [], "m": []})
            E = getattr(r, s + "_team") * r.minutes / 90.0
            h["c"].append(float(getattr(r, s))); h["e"].append(E); h["m"].append(r.minutes)
            if r.minutes >= 30:
                pos_vals.setdefault(r.pos, []).append(float(getattr(r, s)) * 90.0 / r.minutes)
            a, b = rho.get(r.pos, (0.0, 0.0)); rho[r.pos] = (a + float(getattr(r, s)), b + E)
    return pd.DataFrame(out, columns=["pos", "mu", "y"])


if __name__ == "__main__":
    V = {"today (S40,h20)": {}, "S20": dict(strength=20), "S80": dict(strength=80),
         "cap q99": dict(cap_q=0.99), "cap q97.5": dict(cap_q=0.975), "cap q99 + S60": dict(cap_q=0.99, strength=60)}
    for s in ("shots", "sot", "tackles"):
        print(f"\n== player {s}")
        tot = {k: [] for k in V}
        for lg in ("PL", "SA", "L1"):
            pg = frames(lg)
            res = {k: run(pg, s, **v) for k, v in V.items()}
            b = res["today (S40,h20)"]; bll = nb_ll(b["y"].values, b["mu"].values, R[s])
            for k, df in res.items():
                tot[k].append(nb_ll(df["y"].values, df["mu"].values, R[s]) - bll)
        for k in V:
            dif = np.concatenate(tot[k])
            z = dif.mean() / (dif.std(ddof=1) / np.sqrt(len(dif))) if dif.std() > 0 else 0.0
            per = [round(float(x.mean() * 1000), 2) for x in tot[k]]
            print(f"  {k:18s} gain {dif.mean()*1000:+6.2f} milli  z {z:+5.1f}   PL/SA/L1 {per}  n={len(dif)}")
