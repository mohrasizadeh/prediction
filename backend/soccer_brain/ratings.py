"""ratings.py -- team attack and defence ratings for one count (shots, corners, fouls, ...).

A ridge Poisson model fitted jointly on every game: log(home mean) = c + home + attack[home] + concede[away], and
log(away mean) = c + attack[away] + concede[home]. Older games count less (half-life in rounds). Because all teams are
solved together, a team's number is already adjusted for who it played.

Walk-forward test on 5 leagues x 11 seasons (docs/33): this beat the engine's regression on shots, shots on target,
corners, fouls and yellows (z +3 to +7 on 2,300 Premier League games), and a separate home/away rating per club made
every count worse. So there is ONE home factor for the league, not one per club.
"""
from __future__ import annotations

import numpy as np
from scipy.optimize import minimize

# half-life in rounds, ridge strength (found on the walk-forward test; tackles copy corners until tested)
HALF = {"shots": 48.0, "sot": 60.0, "corners": 70.0, "tackles": 60.0, "fouls": 36.0, "yellow": 70.0}
LAM = {"shots": 12.0, "sot": 10.0, "corners": 12.0, "tackles": 12.0, "fouls": 16.0, "yellow": 16.0}


class RatingsModel:
    def __init__(self, half=60.0, lam=12.0):
        self.half, self.lam = float(half), float(lam)
        self.ok = False

    def fit(self, H, A, yh, ya, age, n):
        H = np.asarray(H, int); A = np.asarray(A, int)
        yh = np.asarray(yh, float); ya = np.asarray(ya, float)
        if len(H) < 60:
            return self
        w = 0.5 ** (np.asarray(age, float) / self.half)
        lam = self.lam

        def f(t):
            c, h = t[0], t[1]; a = t[2:2 + n]; d = t[2 + n:]
            eh = c + h + a[H] + d[A]; ea = c + a[A] + d[H]
            mh, ma = np.exp(eh), np.exp(ea)
            ll = (w * (yh * eh - mh + ya * ea - ma)).sum() - lam * (a @ a + d @ d)
            gh, ga = w * (yh - mh), w * (ya - ma)
            g = np.zeros_like(t)
            g[0] = gh.sum() + ga.sum(); g[1] = gh.sum()
            g[2:2 + n] = np.bincount(H, gh, n) + np.bincount(A, ga, n) - 2 * lam * a
            g[2 + n:] = np.bincount(A, gh, n) + np.bincount(H, ga, n) - 2 * lam * d
            return -ll, -g

        t0 = np.zeros(2 + 2 * n)
        t0[0] = np.log(max((yh.mean() + ya.mean()) / 2, 0.05))
        r = minimize(f, t0, jac=True, method="L-BFGS-B", options={"maxiter": 200})
        self.c, self.h = r.x[0], r.x[1]; self.a = r.x[2:2 + n]; self.d = r.x[2 + n:]
        self.ok = True
        return self

    def mu(self, team, opp, is_home):
        """Expected count for `team` against `opp`."""
        if not self.ok:
            return None
        if is_home:
            return float(np.exp(self.c + self.h + self.a[team] + self.d[opp]))
        return float(np.exp(self.c + self.a[team] + self.d[opp]))
