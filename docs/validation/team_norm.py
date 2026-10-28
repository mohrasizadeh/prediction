"""team_norm.py -- which way of averaging a team's past games best predicts its next game?

Walk-forward over 5 leagues x 15 seasons (football-data via the datasets/football-datasets mirror).
For every match we predict each side's count of a stat from data before that match only, then score the
real count with a negative binomial log likelihood. Same prediction shape for every variant:

    mu = league_mean(venue) * attack_rel(team) * defence_rel(opponent)

Variants change only how attack_rel / defence_rel are averaged from past games:
    raw      cumulative mean since history start, shrunk to the league with k prior games (the engine today)
    decay    + recent games count more (half-life h games)
    cap      + each game value is capped before averaging (one 22-shot game cannot drag the mean)
    opp      + each game is judged against what that opponent usually allows / produces
    all      decay + cap + opp
"""
import glob, os, sys
import numpy as np, pandas as pd
from scipy.special import gammaln
from scipy.optimize import minimize_scalar

HERE = os.path.dirname(os.path.abspath(__file__))
STATS = {"shots": ("HS", "AS"), "sot": ("HST", "AST"), "corners": ("HC", "AC"), "fouls": ("HF", "AF"), "yellow": ("HY", "AY")}


def load():
    rows = []
    for f in sorted(glob.glob(os.path.join(HERE, "data", "fd", "*.csv"))):
        lg, s = os.path.basename(f)[:-4].rsplit("_", 1)
        d = pd.read_csv(f)
        d["league"] = lg; d["season"] = int(s)
        rows.append(d)
    d = pd.concat(rows, ignore_index=True)
    d["Date"] = pd.to_datetime(d["Date"], errors="coerce")
    need = [c for v in STATS.values() for c in v]
    d = d.dropna(subset=["Date", "HomeTeam", "AwayTeam"] + need)
    return d.sort_values(["league", "Date"]).reset_index(drop=True)


def nb_ll(y, mu, r):
    mu = np.maximum(mu, 1e-9)
    return gammaln(y + r) - gammaln(r) - gammaln(y + 1) + r * np.log(r / (r + mu)) + y * np.log(mu / (r + mu))


class Avg:
    """Running, optionally decayed, sums per team for one stat."""

    def __init__(self, k=6.0, half=None, cap_q=None, opp=False, window=None):
        self.k, self.half, self.cap_q, self.opp, self.window = k, half, cap_q, opp, window
        self.hist = {}
        self.F, self.A, self.n = {}, {}, {}      # sums of (adjusted) for / against, weight
        self.vals = []                           # league values seen so far (for the cap)
        self.L = {1: [], 0: []}

    def lmean(self, home):
        v = self.L[home]
        return float(np.mean(v[-2000:])) if v else 10.0

    def lall(self):
        return 0.5 * (self.lmean(1) + self.lmean(0))

    def rel(self, t):
        L = self.lall()
        f, a, n = self.F.get(t, 0.0), self.A.get(t, 0.0), self.n.get(t, 0.0)
        return (f + self.k * L) / (n + self.k) / L, (a + self.k * L) / (n + self.k) / L

    def predict(self, team, opp, home):
        fr, _ = self.rel(team)
        _, ar = self.rel(opp)
        return self.lmean(home) * fr * ar

    def cap(self, x):
        if self.cap_q is None or len(self.vals) < 200:
            return x
        if len(self.vals) % 200 == 0 or not hasattr(self, "_c"):
            self._c = np.quantile(self.vals[-3000:], self.cap_q)
        return min(x, self._c)

    def update(self, team, opp, home, x_for, x_against):
        """x_for = what `team` did; x_against = what the opponent did. Called once per side."""
        if self.half:
            g = 0.5 ** (1.0 / self.half)
            for D in (self.F, self.A, self.n):
                if team in D:
                    D[team] *= g
        L = self.lall()
        xf, xa = self.cap(x_for), self.cap(x_against)
        if self.opp:
            _, opp_def = self.rel(opp)      # how much the opponent usually concedes vs league
            opp_att, _ = self.rel(opp)      # how much the opponent usually produces
            xf = xf / max(opp_def, 0.3)
            xa = xa / max(opp_att, 0.3)
        if self.window:
            h = self.hist.setdefault(team, []); h.append((xf, xa))
            if len(h) > self.window:
                of, oa = h.pop(0); self.F[team] -= of; self.A[team] -= oa; self.n[team] -= 1.0
        self.F[team] = self.F.get(team, 0.0) + xf
        self.A[team] = self.A.get(team, 0.0) + xa
        self.n[team] = self.n.get(team, 0.0) + 1.0


def run(d, stat, make):
    hc, ac = STATS[stat]
    out = []
    for lg, g in d.groupby("league"):
        m = make()
        seen = {}
        for r in g.itertuples(index=False):
            h, a = r.HomeTeam, r.AwayTeam
            yh, ya = float(getattr(r, hc)), float(getattr(r, ac))
            ok = seen.get(h, 0) >= 5 and seen.get(a, 0) >= 5
            if ok:
                out.append((lg, r.season, m.predict(h, a, 1), yh))
                out.append((lg, r.season, m.predict(a, h, 0), ya))
            m.L[1].append(yh); m.L[0].append(ya); m.vals += [yh, ya]
            m.update(h, a, 1, yh, ya)
            m.update(a, h, 0, ya, yh)
            seen[h] = seen.get(h, 0) + 1; seen[a] = seen.get(a, 0) + 1
    return pd.DataFrame(out, columns=["league", "season", "mu", "y"])


def fit_r(mu, y):
    res = minimize_scalar(lambda lr: -np.sum(nb_ll(y, mu, np.exp(lr))), bounds=(np.log(0.5), np.log(500)), method="bounded")
    return float(np.exp(res.x))


VARIANTS = {
    "raw (today)": lambda: Avg(k=6, window=114),
    "decay h=20": lambda: Avg(k=6, half=20),
    "decay h=30": lambda: Avg(k=6, half=30),
    "cap q97.5": lambda: Avg(k=6, window=114, cap_q=0.975),
    "opp-adjust": lambda: Avg(k=6, window=114, opp=True),
    "decay20+opp": lambda: Avg(k=6, half=20, opp=True),
    "decay20+cap97.5+opp": lambda: Avg(k=6, half=20, cap_q=0.975, opp=True),
    "decay20+cap99+opp": lambda: Avg(k=6, half=20, cap_q=0.99, opp=True),
}

if __name__ == "__main__":
    d = load()
    print("matches", len(d))
    stats = sys.argv[1:] or list(STATS)
    for stat in stats:
        res = {name: run(d, stat, mk) for name, mk in VARIANTS.items()}
        base = res["raw (today)"]
        r = fit_r(base["mu"].values, base["y"].values)
        b_ll = nb_ll(base["y"].values, base["mu"].values, r)
        print(f"\n== {stat}  (n={len(base)}, r={r:.1f}; gain = log-lik per team-game vs today, z over team-games)")
        for name, df in res.items():
            rr = fit_r(df["mu"].values, df["y"].values)
            ll = nb_ll(df["y"].values, df["mu"].values, rr)
            dif = ll - b_ll
            z = dif.mean() / (dif.std(ddof=1) / np.sqrt(len(dif)))
            per_lg = {lg: round(float((ll[df["league"] == lg] - b_ll[df["league"] == lg]).mean() * 1000), 2) for lg in sorted(df["league"].unique())}
            print(f"  {name:24s} gain {dif.mean()*1000:+7.2f} milli  z {z:+6.1f}   by league {per_lg}")
