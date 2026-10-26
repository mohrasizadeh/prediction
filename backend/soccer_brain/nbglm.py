"""nbglm.py -- regularized negative binomial regression with a log link.

Fit by L-BFGS with an analytic gradient. Per-feature ridge penalties let
us punish interaction terms harder than main effects, so the model only
keeps a matchup effect when the data insists.
"""
from __future__ import annotations

import numpy as np
from scipy.optimize import minimize, minimize_scalar
from scipy.special import gammaln


class NBGLM:
    def __init__(self, l2=3.0):
        self.l2 = l2          # float or per-feature array (no intercept entry)
        self.beta = None
        self.r = 20.0
        self.mean_ = None
        self.std_ = None

    # ---- helpers
    def _z(self, X):
        return (X - self.mean_) / self.std_

    def _design(self, X):
        Z = self._z(np.atleast_2d(X))
        return np.hstack([np.ones((len(Z), 1)), Z])

    def fit(self, X, y, w=None, n_outer=3, offset=None):
        X = np.asarray(X, float); y = np.asarray(y, float)
        n, p = X.shape
        w = np.ones(n) if w is None else np.asarray(w, float)
        off = np.zeros(n) if offset is None else np.asarray(offset, float)
        self.mean_ = X.mean(0)
        self.std_ = X.std(0) + 1e-9
        D = self._design(X)
        # Relative ridge: l2 = 1 shrinks a coefficient to about half its
        # unpenalised size, l2 = 8 to about one ninth. Scaled by the data's
        # own information so it means the same at 700 rows or 7,000.
        ybar = max(float(np.average(y, weights=w)), 1e-6)
        info_unit = float(np.sum(w)) * ybar * 20.0 / (20.0 + ybar)
        pen = np.zeros(p + 1)
        pen[1:] = (self.l2 if np.ndim(self.l2) else np.full(p, self.l2)) * info_unit
        beta = np.zeros(p + 1)
        beta[0] = np.log(max(np.average(y / np.exp(off), weights=w), 1e-3))
        r = self.r

        for _ in range(n_outer):
            def nll(b, r=r):
                eta = np.clip(D @ b + off, -20, 20)
                mu = np.exp(eta)
                ll = (gammaln(y + r) - gammaln(r) - gammaln(y + 1)
                      + r * np.log(r / (r + mu)) + y * np.log(mu / (r + mu)))
                val = -np.sum(w * ll) + 0.5 * np.sum(pen * b * b)
                g = -D.T @ (w * (y - mu) * r / (r + mu)) + pen * b
                return val, g
            res = minimize(nll, beta, jac=True, method="L-BFGS-B")
            beta = res.x
            mu = np.exp(np.clip(D @ beta + off, -20, 20))

            def nll_r(lr):
                rr = np.exp(lr)
                ll = (gammaln(y + rr) - gammaln(rr) - gammaln(y + 1)
                      + rr * np.log(rr / (rr + mu)) + y * np.log(mu / (rr + mu)))
                return -np.sum(w * ll)
            rs = minimize_scalar(nll_r, bounds=(np.log(0.5), np.log(500.0)), method="bounded")
            r = float(np.exp(rs.x))
        self.beta, self.r = beta, r
        return self

    def predict_mu(self, X, offset=None):
        D = self._design(X)
        off = 0.0 if offset is None else np.asarray(offset, float)
        return np.exp(np.clip(D @ self.beta + off, -20, 20))

    def contributions(self, x):
        """Per-feature log-mean contribution for ONE row, relative to an average row."""
        z = self._z(np.atleast_2d(x))[0]
        return self.beta[1:] * z
