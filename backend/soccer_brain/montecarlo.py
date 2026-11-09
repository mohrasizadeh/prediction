"""montecarlo.py -- draw whole matches from the fitted engine, and check them against it (docs/66).

NOT a second model. Every number here comes from the mixture the closed form already integrated:
`Forecast.mix` is `(scenario weights, their means, the dispersion)`, which is exactly what `p` is
the sum of. Drawing from it can therefore only agree with `p` or reveal a bug -- which is the
entire point of the first half of this file.

Why this exists at all. The engine answers marginal questions exactly: P(shots >= k) is a negative
binomial survival function, not an estimate. Simulating cannot improve that; it can only estimate
the same number with noise, and at the 100 runs people reach for first, a 7% event carries a
standard error of about 2.6 points. So this is not here to make the percentages better.

It is here for the questions the closed form cannot answer at all -- joint ones. P(A) and P(B) are
exact; P(A and B) is not available, which is why `combo.py` corrects the product with factors
MEASURED from 237,000 real combinations (1.11 / 1.19 / 1.25, and 0.38 for two lines on one
player). A draw of a whole match gives joints directly.

The trap, stated here because it decides whether any of this is worth shipping: a simulator that
draws every player independently reproduces the plain product and is WORSE than those measured
factors, because it would have replaced a measurement with an assumption. Correlation has to come
from something real -- shared game state, shared minutes, shared referee. `pair_factor()` below is
the test of whether it does: run it, and if it returns about 1.0 then this is multiplication with
extra steps and should be deleted rather than shipped.
"""
from __future__ import annotations

import numpy as np

from core import nb_sf


def draw(mix, n: int, rng) -> np.ndarray:
    """n draws of one entity's count, from the mixture its forecast integrated.

    The mixture is over LINEUP SCENARIOS: a player who might start or might come on has a mean for
    each case and a weight on each. Drawing the scenario first and the count second is what the
    closed form does by summing, so the two cannot disagree unless one of them is wrong.
    """
    w, mus, r = mix
    w = np.asarray(w, float); mus = np.asarray(mus, float)
    w = w / w.sum()
    pick = rng.choice(len(mus), size=n, p=w) if len(mus) > 1 else np.zeros(n, dtype=int)
    mu = np.maximum(mus[pick], 1e-9)
    # NB(mu, r) as a gamma-Poisson mixture: the shape numpy gives directly.
    lam = rng.gamma(shape=r, scale=mu / r)
    return rng.poisson(lam)


def check_marginals(forecasts, n: int = 50_000, seed: int = 7) -> dict:
    """Draw each forecast's own entity and compare the simulated P(N >= k) with its stored `p`.

    Returns the worst disagreement in units of MONTE CARLO STANDARD ERRORS, not percentage points.
    Two points of difference is nothing at 500 draws and a bug at 500,000, and only the first
    number tells you which.
    """
    rng = np.random.default_rng(seed)
    rows = []
    for f in forecasts:
        if not f.mix:
            continue
        k = int(np.floor(f.thr)) + 1
        counts = draw(f.mix, n, rng)
        got = float((counts >= k).mean())
        # The standard error comes from the ANALYTIC p, not the sampled proportion. A sample that
        # lands on exactly 0 or 1 -- which happens on every near-certain line -- has a sampled
        # variance of zero, and dividing by it reports thousands of standard errors for a rounding
        # difference. The floor of 1/n is the same guard for a p that is itself ~0 or ~1.
        q = float(f.p)
        se = float(np.sqrt(max(q * (1 - q), 1.0 / n) / n))
        rows.append({"scope": f.scope, "stat": f.stat, "thr": f.thr, "player": f.player,
                     "p": float(f.p), "sim": got, "diff": got - float(f.p),
                     "sigmas": abs(got - float(f.p)) / se})
    rows.sort(key=lambda r: -r["sigmas"])
    top = rows[0] if rows else None
    return {"n": n, "checked": len(rows), "worst": rows[:10],
            # the worst row's own numbers, so a caller cannot read the biggest gap and the biggest
            # sigma count as though they came from the same line
            "max_sigmas": top["sigmas"] if top else 0.0,
            "max_sigmas_diff": abs(top["diff"]) if top else 0.0,
            "max_diff": max((abs(r["diff"]) for r in rows), default=0.0)}


def analytic_check(forecasts) -> dict:
    """The same comparison with no randomness: rebuild `p` from the mixture by summing it.

    This separates two failures a simulation conflates. If this disagrees, the stored `p` and the
    mixture are not the same object and the bug is in the engine. If only the SAMPLED check
    disagrees, the bug is in the drawing.
    """
    worst, rows = 0.0, []
    for f in forecasts:
        if not f.mix:
            continue
        w, mus, r = f.mix
        w = np.asarray(w, float); w = w / w.sum()
        k = int(np.floor(f.thr)) + 1
        got = float(np.sum(w * nb_sf(k, np.asarray(mus, float), r)))
        d = abs(got - float(f.p))
        worst = max(worst, d)
        rows.append({"scope": f.scope, "stat": f.stat, "player": f.player, "p": float(f.p), "rebuilt": got, "diff": got - float(f.p)})
    rows.sort(key=lambda r: -abs(r["diff"]))
    return {"checked": len(rows), "max_diff": worst, "worst": rows[:10]}


def joint(forecasts, n: int = 50_000, seed: int = 11, independent: bool = True) -> dict:
    """P(every one of these lines happens), drawn rather than multiplied.

    `independent=True` draws each entity on its own, which is the NULL: it must reproduce the plain
    product, and if it does not then the drawing is broken. The version worth having is the one
    that shares game state between entities in the same match -- until that exists, this function's
    honest use is as the baseline the correlated version has to beat.
    """
    rng = np.random.default_rng(seed)
    mixes = [(f, int(np.floor(f.thr)) + 1) for f in forecasts if f.mix]
    if not mixes:
        return {"n": n, "joint": None, "product": None, "factor": None}
    hit = np.ones(n, dtype=bool)
    for f, k in mixes:
        hit &= draw(f.mix, n, rng) >= k
    got = float(hit.mean())
    prod = 1.0
    for f, _ in mixes:
        prod *= float(f.p)
    se = float(np.sqrt(max(got * (1 - got), 1e-12) / n))
    return {"n": n, "lines": len(mixes), "joint": got, "product": prod, "se": se,
            "factor": (got / prod) if prod > 0 else None, "independent": independent}


def pair_factor(fixtures_forecasts, n: int = 20_000, seed: int = 13, pairs_per_match: int = 40,
                min_expected: int = 50) -> dict:
    """The number that decides whether a simulator is worth shipping.

    `combo.py` multiplies two lines and then corrects by a factor measured on real football: 1.11
    for two entities before lineups. If this simulator produces that correction on its own, it has
    captured something real and can replace a measurement with a calculation. If it returns about
    1.00, it has captured nothing, and the measured factors are better than it is.

    Run it before building anything a reader can see.
    """
    rng = np.random.default_rng(seed)
    ratios, skipped = [], [0]
    for fcs in fixtures_forecasts:
        have = [f for f in fcs if f.mix]
        for _ in range(pairs_per_match):
            if len(have) < 2:
                break
            a, b = rng.choice(len(have), size=2, replace=False)
            fa, fb = have[a], have[b]
            if (fa.scope, fa.player, fa.team) == (fb.scope, fb.player, fb.team):
                continue
            j = joint([fa, fb], n=n, seed=int(rng.integers(1, 10 ** 9)))
            # A pair whose joint is rare enough that n draws expect a handful of hits cannot
            # produce a ratio worth averaging: it returns 0 most of the time and something wild the
            # rest, and a mean over those measures the sample size, not the football. Require the
            # product to be common enough that the estimate has a floor under it.
            if not j["product"] or j["product"] * n < min_expected or j["joint"] is None:
                skipped[0] += 1
                continue
            ratios.append(j["joint"] / j["product"])
    if not ratios:
        return {"pairs": 0, "skipped_too_rare": skipped[0], "factor": None}
    r = np.array(ratios)
    return {"pairs": len(r), "skipped_too_rare": skipped[0],
            "factor": float(r.mean()), "sd": float(r.std()),
            "p10": float(np.percentile(r, 10)), "p90": float(np.percentile(r, 90)),
            "measured_pre_2": 1.11,
            "verdict": ("captures correlation" if r.mean() > 1.03 else
                        "reproduces the plain product -- the measured factors are better")}
