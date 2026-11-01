"""strength.py -- Dixon-Coles team strength with time decay.

Gives expected goals, scoreline probabilities and win/draw/loss for a fixture.
The engine uses the expected margin as its game-state signal.
"""
from __future__ import annotations

import numpy as np
from scipy.optimize import minimize
from scipy.special import gammaln


def _tau(x, y, lh, la, rho):
    t = np.ones_like(lh)
    t = np.where((x == 0) & (y == 0), 1 - lh * la * rho, t)
    t = np.where((x == 0) & (y == 1), 1 + lh * rho, t)
    t = np.where((x == 1) & (y == 0), 1 + la * rho, t)
    t = np.where((x == 1) & (y == 1), 1 - rho, t)
    return t


class DixonColes:
    def __init__(self, xi=0.02, reg=1.0):
        self.xi = xi        # time decay per round
        self.reg = reg      # ridge on attack/defence
        self.teams = None

    def fit(self, home, away, hg, ag, age):
        home = np.asarray(home); away = np.asarray(away)
        hg = np.asarray(hg, float); ag = np.asarray(ag, float)
        self.teams = sorted(set(home) | set(away))
        idx = {t: i for i, t in enumerate(self.teams)}
        n = len(self.teams)
        hi = np.array([idx[t] for t in home]); ai = np.array([idx[t] for t in away])
        w = np.exp(-self.xi * np.asarray(age, float))

        def unpack(th):
            return th[0], th[1], 0.2 * np.tanh(th[2]), th[3:3 + n], th[3 + n:]

        def nll(th):
            mu0, gam, rho, att, dfn = unpack(th)
            lh = np.exp(mu0 + gam + att[hi] - dfn[ai])
            la = np.exp(mu0 + att[ai] - dfn[hi])
            ll = (np.log(np.maximum(_tau(hg, ag, lh, la, rho), 1e-9))
                  + hg * np.log(lh) - lh + ag * np.log(la) - la
                  - gammaln(hg + 1) - gammaln(ag + 1))
            pen = self.reg * (np.sum(att ** 2) + np.sum(dfn ** 2)) + 50.0 * (att.sum() ** 2 + dfn.sum() ** 2)
            return -np.sum(w * ll) + pen

        th0 = np.zeros(3 + 2 * n)
        th0[0] = 0.1; th0[1] = 0.25
        res = minimize(nll, th0, method="L-BFGS-B", options={"maxiter": 200})
        self.mu0, self.gam, self.rho, att, dfn = unpack(res.x)
        self.att = dict(zip(self.teams, att)); self.dfn = dict(zip(self.teams, dfn))
        return self

    def expected_goals(self, home, away):
        lh = np.exp(self.mu0 + self.gam + self.att.get(home, 0.0) - self.dfn.get(away, 0.0))
        la = np.exp(self.mu0 + self.att.get(away, 0.0) - self.dfn.get(home, 0.0))
        return float(lh), float(la)

    def outcome_probs(self, home, away, max_goals=9, mult_h=1.0, mult_a=1.0):
        """`mult_h`, `mult_a`: match-context multipliers on expected goals (form, stakes; docs/22)."""
        lh, la = self.expected_goals(home, away)
        lh, la = lh * float(mult_h), la * float(mult_a)
        g = np.arange(max_goals + 1)
        from scipy.stats import poisson
        M = np.outer(poisson.pmf(g, lh), poisson.pmf(g, la))
        for (x, y) in [(0, 0), (0, 1), (1, 0), (1, 1)]:
            M[x, y] *= float(_tau(np.array(x), np.array(y), np.array(lh), np.array(la), self.rho))
        M /= M.sum()
        # Total goals in the match, straight off the same scoreline matrix: P(total >= k) for each line.
        # No new data and no second model: the draw correction and the context multipliers are already in M.
        tot = np.zeros(2 * max_goals + 1)
        for i in range(max_goals + 1):
            for j in range(max_goals + 1):
                tot[i + j] += M[i, j]
        # keyed by the line itself ("2.5" = three or more goals), so it stores and reads as a plain document
        over = {f"{k - 0.5:g}": float(tot[k:].sum()) for k in range(1, max_goals + 1)}
        return {"xg_home": lh, "xg_away": la,
                "p_home": float(np.tril(M, -1).sum()),
                "p_draw": float(np.trace(M)),
                "p_away": float(np.triu(M, 1).sum()),
                "totals": over}
