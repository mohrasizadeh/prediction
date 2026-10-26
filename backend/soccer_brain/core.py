"""core.py -- shared statistical building blocks (numpy + scipy only)."""
from __future__ import annotations

from dataclasses import dataclass
import numpy as np
from scipy import stats
from scipy.optimize import minimize_scalar
from scipy.special import gammaln


# ---------------------------------------------------------------- weights
def recency_weights(n: int, half_life: float) -> np.ndarray:
    """Oldest first, newest last. A game `half_life` games ago counts half."""
    age = np.arange(n)[::-1]
    return 0.5 ** (age / half_life)


# ------------------------------------------------------ gamma-Poisson rate
@dataclass
class RatePosterior:
    alpha: float
    beta: float

    @property
    def mean(self) -> float:
        return self.alpha / self.beta

    @property
    def cv(self) -> float:
        """Relative uncertainty of the rate (1 / sqrt(alpha))."""
        return 1.0 / np.sqrt(max(self.alpha, 1e-9))


def shrunk_rate(counts, exposures, prior_rate, prior_strength, half_life=None) -> RatePosterior:
    counts = np.asarray(counts, float)
    exposures = np.asarray(exposures, float)
    w = recency_weights(len(counts), half_life) if half_life and len(counts) else np.ones(len(counts))
    alpha = prior_rate * prior_strength + float(np.sum(w * counts))
    beta = prior_strength + float(np.sum(w * exposures))
    return RatePosterior(alpha, beta)


# --------------------------------------------------------- negative binomial
def nb_sf(k, mu, r):
    """P(N >= k) for a negative binomial with mean mu, dispersion r (var = mu + mu^2/r)."""
    mu = np.maximum(np.asarray(mu, float), 1e-9)
    return stats.nbinom.sf(np.asarray(k) - 1, r, r / (r + mu))


def nb_loglik(y, mu, r):
    mu = np.maximum(mu, 1e-9)
    return (gammaln(y + r) - gammaln(r) - gammaln(y + 1)
            + r * np.log(r / (r + mu)) + y * np.log(mu / (r + mu)))


def fit_dispersion(mu, y, lo=0.5, hi=400.0, default=10.0):
    """Maximum likelihood dispersion r for given means. Needs enough data."""
    mu = np.asarray(mu, float); y = np.asarray(y, float)
    if len(y) < 200:
        return default
    res = minimize_scalar(lambda lr: -np.sum(nb_loglik(y, mu, np.exp(lr))),
                          bounds=(np.log(lo), np.log(hi)), method="bounded")
    return float(np.exp(res.x))


# --------------------------------------------------------- isotonic calibration
class Isotonic:
    """Pool-adjacent-violators calibration. Monotone map from stated to actual."""

    def __init__(self):
        self.x = None
        self.y = None

    def fit(self, p, y):
        p = np.asarray(p, float); y = np.asarray(y, float)
        order = np.argsort(p)
        p, y = p[order], y[order]
        # blocks of [sum_y, weight, sum_p]
        blocks = [[yy, 1.0, pp] for pp, yy in zip(p, y)]
        out = []
        for b in blocks:
            out.append(b)
            while len(out) > 1 and out[-2][0] / out[-2][1] > out[-1][0] / out[-1][1]:
                b2 = out.pop(); b1 = out.pop()
                out.append([b1[0] + b2[0], b1[1] + b2[1], b1[2] + b2[2]])
        self.x = np.array([b[2] / b[1] for b in out])
        self.y = np.clip(np.array([b[0] / b[1] for b in out]), 0.01, 0.99)
        return self

    def predict(self, p):
        if self.x is None:
            return np.asarray(p, float)
        return np.interp(np.asarray(p, float), self.x, self.y)


# ---------------------------------------------------------------- tiers
def tier(p, p_lo, lineup_confirmed, strong=(0.80, 0.70), solid=(0.65, 0.55)):
    """Starting cutoffs from the spec. Tune on the backtest."""
    if p >= strong[0] and p_lo >= strong[1] and lineup_confirmed:
        return "Strong"
    if p >= solid[0] and p_lo >= solid[1]:
        return "Solid" if lineup_confirmed else "Watch"
    if p >= 0.55:
        return "Watch"
    return None


STAT_WORDS = {"shots": "shots", "sot": "shots on target",
              "tackles": "tackles", "corners": "corners",
              "fouls": "fouls", "yellow": "yellow cards"}

REASONS = {
    "own_style": ("The team's own style produces more {s}.", "The team's own style produces fewer {s}."),
    "opponent": ("The opponent's style allows more {s}.", "The opponent's style restricts {s}."),
    "style": ("This matchup of styles lifts {s}.", "This matchup of styles holds {s} down."),
    "own_tactic": ("The team's way of playing produces more {s}.", "The team's way of playing produces fewer {s}."),
    "opp_tactic": ("The opponent's way of playing allows more {s}.", "The opponent's way of playing restricts {s}."),
    "tactic_matchup": ("The clash of playing styles lifts {s}.", "The clash of playing styles holds {s} down."),
    "own_shape": ("The team's usual shape creates more {s}.", "The team's usual shape creates fewer {s}."),
    "opp_shape": ("The opponent's usual shape allows more {s}.", "The opponent's usual shape restricts {s}."),
    "venue": ("Home advantage helps.", "Playing away lowers this."),
    "game_script": ("The expected game state lifts {s}.", "The expected game state lowers {s}."),
    "minutes": ("Expected minutes are high.", "Expected minutes are limited."),
    "opp_lineup": ("The opponent's expected lineup is weaker at preventing {s}.",
                   "The opponent's expected lineup is strong at preventing {s}."),
    "own_lineup": ("The team's expected lineup creates more {s}.",
                   "The team's expected lineup creates fewer {s}."),
    "role": ("Takes a larger share of the team's {s} than most in the role.",
             "Takes a smaller share of the team's {s} than most in the role."),
}


def top_reasons(contrib: dict, stat: str, n=2, floor=0.04):
    """Reasons for an 'over' forecast. Lead with the factors that push the
    count UP, largest first. Only if none do, show the largest drag."""
    items = [(k, v) for k, v in contrib.items() if abs(v) >= floor and k in REASONS]
    ups = sorted([kv for kv in items if kv[1] > 0], key=lambda kv: -kv[1])
    downs = sorted([kv for kv in items if kv[1] < 0], key=lambda kv: kv[1])
    chosen = ups[:n] if ups else downs[:1]
    word = STAT_WORDS.get(stat, stat)
    return [(REASONS[k][0] if v > 0 else REASONS[k][1]).format(s=word) for k, v in chosen]


# ---------------------------------------------------------------- metrics
def log_loss(p, y, eps=1e-6):
    p = np.clip(np.asarray(p, float), eps, 1 - eps); y = np.asarray(y, float)
    return float(-np.mean(y * np.log(p) + (1 - y) * np.log(1 - p)))


def brier(p, y):
    return float(np.mean((np.asarray(p, float) - np.asarray(y, float)) ** 2))
