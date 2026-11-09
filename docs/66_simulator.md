# 66 — The simulator, as a check on the engine

Built internal, kept internal. Nothing here is on a screen, and nothing should be until the
question at the bottom of this page is answered on real football.

## What it is

`soccer_brain/montecarlo.py` draws whole matches from the fitted engine. It is **not a second
model**: `Forecast.mix` is `(scenario weights, their means, the dispersion)` — exactly what the
closed form sums to get `p` — and the simulator draws from that. So it can only agree with the
engine or reveal a bug in it.

`engine.keep_mixture` is off by default and costs nothing when off.

## Why a simulator cannot improve a percentage

The engine answers marginal questions **exactly**. `P(shots ≥ k)` is a negative binomial survival
function with fitted dispersion, not an estimate. Simulating can only estimate the same number
with noise.

The test measures that rather than asserting it. Over 120 lines:

| draws | largest gap from the analytic answer |
|---|---|
| 40,000 | **0.63 points** (worst line 2.5 standard errors out) |
| 200 | **5.9 points** |

So the instinct to "run it 100 times" is the one thing not to do. At that size you are not
estimating the forecast, you are adding a few points of noise to a number you already had.

## Two checks, deliberately separate

* `analytic_check()` rebuilds `p` from its own mixture with **no randomness**. On a full fixture
  list it matched to **1.1 × 10⁻¹⁶** across 1,952 forecasts — so `p` and the mixture really are one
  object, and any later disagreement is the dice rather than the engine.
* `check_marginals()` draws. Keeping these apart is what lets a failure be attributed; a single
  combined check would have said only "something is wrong".

Both of those were worth having before anything else: the first thing this validator found was a
bug **in its own statistics**. The standard error was computed from the sampled proportion, so any
line whose sample landed on exactly 0 or 1 — which is every near-certain line — had a variance of
zero and reported thousands of standard errors for a rounding difference. The error now comes from
the analytic `p`, with a floor of `1/n`. That is the argument for building a validator before
building a feature, in one paragraph.

## The question that decides whether this ever ships

`combo.py` multiplies two lines and then corrects by a factor **measured on 237,000 real
combinations**: 1.11 for two entities before lineups (docs/28, `docs/validation/pairs27.py`). If a
simulator reproduces that correction on its own, it has captured something real and can replace a
measurement with a calculation. If it returns 1.00, it has captured nothing.

`pair_factor()` asks exactly that. As built — every entity drawn independently — it returns:

> **1.016** (sd 0.073, 10th–90th 0.951–1.096) over 36 pairs, against a measured 1.11

which is the answer it had to give. **Independent draws reproduce the plain product.** A simulator
without shared game state is multiplication with extra steps, and `combo.py`'s measured factors
are strictly better than it.

Two honest caveats on that number. It was run on the synthetic league the tests use, so it is a
statement about the simulator's own structure — which is independent *by construction* — and not
about football. And `min_expected` exists because the first run returned 0.863: pairs whose joint
is rare enough that the draws usually return exactly zero were being averaged in, so the mean was
measuring the sample size rather than the game. Pairs now need an estimable joint to count, and 60
of 96 were skipped on that rule.

## What would have to change for it to be worth showing anyone

Correlation has to come from something real, drawn once per match and shared by every entity in
it: game state (a chasing team shoots more, a team two up takes fewer risks), shared minutes,
shared referee. The engine already has game-script features, so there is a path. Until that exists
and `pair_factor()` moves toward 1.11 **on real matches**, this stays where it is.

If it ever does ship, the number of draws and the margin of error belong next to every figure.
"We simulated it 100 times" invites more confidence than the arithmetic supports, which is the one
thing this product cannot afford to spend.

## What it is already good for

* A consistency check on every engine change: if `p` and its mixture ever stop being the same
  object, `analytic_check()` says so immediately and exactly.
* Joint questions the closed form cannot answer at all — scoreline distributions, first scorer,
  "this and that" — as soon as the correlation is real.
