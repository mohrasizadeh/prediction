"""ref_norm.py -- how should a referee's card history enter the forecast of a match's yellow cards?

Premier League 2010/11 to 2024/25 (football-data, referee named for every match). Walk-forward.
Team part (same for all variants): each side's yellow cards from the decayed, opponent-adjusted team model.
Referee part:
    none          teams only
    raw mean      the referee's plain average cards per game (what a referee table shows); ignores the teams
    raw ratio     teams x (cards he gave / cards the teams predicted), no shrinkage
    shrunk        teams x (O + c) / (E + c): few games -> close to 1
    shrunk+cap    same, each game's cards capped (an 8-card game counts as at most the cap)
    shrunk+cap+decay
"""
import os, sys
import numpy as np, pandas as pd
from team_norm import load, Avg, nb_ll, fit_r

def run(c=20.0, cap=None, half=None, mode="shrunk"):
    d = load()
    d = d[d["league"] == "premier-league"].dropna(subset=["Referee"]).copy()
    tm = Avg(k=6, half=20, opp=True)
    O, E, N = {}, {}, {}
    out = []
    seen = {}
    allc = []
    for r in d.itertuples(index=False):
        h, a, ref = r.HomeTeam, r.AwayTeam, str(r.Referee).strip()
        y = float(r.HY + r.AY)
        ok = seen.get(h, 0) >= 5 and seen.get(a, 0) >= 5 and len(allc) > 300
        mu_t = tm.predict(h, a, 1) + tm.predict(a, h, 0)
        if ok:
            n = N.get(ref, 0.0); o = O.get(ref, 0.0); e = E.get(ref, 0.0)
            if mode == "none":
                mu = mu_t
            elif mode == "raw mean":
                mu = o / n if n >= 3 else mu_t
            elif mode == "raw ratio":
                mu = mu_t * (o / e) if e > 0 and n >= 3 else mu_t
            else:
                mu = mu_t * (o + c) / (e + c)
            out.append((r.season, ref, n, mu, y, mu_t))
        # update referee with what happened vs what the teams predicted
        yy = min(y, np.quantile(allc[-3000:], cap)) if (cap and len(allc) > 300) else y
        if half:
            g = 0.5 ** (1.0 / half)
            if ref in O:
                O[ref] *= g; E[ref] *= g; N[ref] *= g
        O[ref] = O.get(ref, 0.0) + yy
        E[ref] = E.get(ref, 0.0) + mu_t
        N[ref] = N.get(ref, 0.0) + 1.0
        allc.append(y)
        tm.L[1].append(float(r.HY)); tm.L[0].append(float(r.AY)); tm.vals += [float(r.HY), float(r.AY)]
        tm.update(h, a, 1, float(r.HY), float(r.AY)); tm.update(a, h, 0, float(r.AY), float(r.HY))
        seen[h] = seen.get(h, 0) + 1; seen[a] = seen.get(a, 0) + 1
    return pd.DataFrame(out, columns=["season", "ref", "n", "mu", "y", "mu_t"])


if __name__ == "__main__":
    V = {"none": dict(mode="none"), "raw mean": dict(mode="raw mean"), "raw ratio": dict(mode="raw ratio"),
         "shrunk c=10": dict(c=10), "shrunk c=20": dict(c=20), "shrunk c=40": dict(c=40),
         "shrunk20+cap97.5": dict(c=20, cap=0.975), "shrunk20+cap95": dict(c=20, cap=0.95),
         "shrunk20+cap97.5+decay60": dict(c=20, cap=0.975, half=60), "shrunk20+decay60": dict(c=20, half=60)}
    res = {k: run(**v) for k, v in V.items()}
    base = res["none"]
    rb = fit_r(base["mu"].values, base["y"].values)
    bll = nb_ll(base["y"].values, base["mu"].values, rb)
    print(f"match yellow cards, n={len(base)} matches; gain vs teams-only, milli log-lik per match")
    for k, df in res.items():
        rr = fit_r(df["mu"].values, df["y"].values)
        ll = nb_ll(df["y"].values, df["mu"].values, rr)
        dif = ll - bll
        z = dif.mean() / (dif.std(ddof=1) / np.sqrt(len(dif))) if dif.std() > 0 else 0
        # over 4.5 cards, log loss
        from scipy import stats
        p = stats.nbinom.sf(4, rr, rr / (rr + df["mu"].values)); yy = (df["y"].values >= 5).astype(float)
        p = np.clip(p, 1e-6, 1 - 1e-6); lls = -np.mean(yy * np.log(p) + (1 - yy) * np.log(1 - p))
        print(f"  {k:26s} gain {dif.mean()*1000:+7.2f}  z {z:+5.1f}   r {rr:5.1f}   log-loss 5+ cards {lls:.4f}")
