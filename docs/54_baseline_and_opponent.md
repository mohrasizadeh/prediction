# 54. Baseline and opponent: the idea, tested

Proposed 2026-11-04:

> Look at 10 past matches for players and teams. Set a baseline for every metric — shots, shots on
> target, tackles, fouls committed, fouls won, yellow cards, corners for and against, goals for and
> against — an average or a median, something robust so one good game does not move it. For
> goalkeepers the key metric is saves, which should be paired with the opponent's shots on target
> and how many their own team allows. Then look at the next opponent and compare the baseline with
> what that opponent allows. Hold both numbers and you can tell the user something worth knowing.

Everything below is measured, not argued. **All measurements are on the simulated league**
(`soccer_brain/simulate.py`), because that is the only data this session can reach. Read the
direction and the size of each effect, treat the absolute values as indicative, and re-run on
production before changing a setting. Section 7 says how.

---

## 1. The verdict in one table

| Part of the idea | Status | Evidence |
|---|---|---|
| Baseline per player and team, per metric | **Already built**, and better than proposed | §3, §9 |
| A 10-match window | **Loses** to all-history with shrinkage, on both sides | §3 (players), §9 (teams) |
| A median, so one good game does not move it | **Much worse**, and it has now lost twice | §3, §9 |
| Corners / goals for and against, as teams | **Tested in §9.** Same answer: window loses, shrinkage wins | §9 |
| Fouls and cards, as teams | **Cannot be answered on this data.** The columns are all zero | §9.2 |
| Venue | Worth more than the choice of window, and already in the engine | §9.1 |
| "Model the rate, not the count" (the goalkeeper idea) | **Tested and it wins**, but only its volume half | §10 |
| Per-90 and scale by minutes | **Wins** for shots, SOT, tackles. **Loses** for fouls | §3 |
| Multiply the baseline by what the opponent allows | **Right, but only at half strength** | §4 |
| …applied at player level | **Cannot work** — it cancels exactly. Algebra in §5 | §5 |
| …applied by opponent **and position** (`engine.opp_pos_k`, built, off) | **Significantly worse**: z = −3.08 | §4.2 |
| Goalkeeper saves | **Does not exist at all.** The best idea in the proposal | §6 |
| Player fouls committed / fouls won / cards | **Do not exist.** The data does | §6 |

## 2. What the engine already does

| Piece | Where | State |
|---|---|---|
| Per-player baseline, shrunk to the positional mean, recency-decayed | `shrunk_rate` in `core.py` | on |
| Per-team baseline against an average opponent | `mu_usual` in `engine.py` | on |
| Team stats judged against what the opponent allows | `engine.style_opp_adjust` = `["shots","fouls","yellow"]` | **on** |
| What an opponent allows **to each position** | `engine.opp_pos_k` | **off (0)** |
| Opponent strength in the team total | the GLM offsets and Dixon-Coles | on |
| Minutes model, start vs substitute | `_scenarios` | on |

Modelled stats: `STATS = ["shots", "sot", "corners", "tackles"]`, plus `fouls` and `yellow` for
teams. Players get shots, SOT and tackles only.

So the first half of the proposal is built, and most of the second half is too.

## 3. Tested: which baseline?

Walk-forward over every player-match with at least ten earlier appearances (n = 1343 per metric).
Each method sees **only earlier matches**. Score is the negative-binomial log-likelihood of what
actually happened; higher is better.

| metric | A. last-10 mean **per game** | B. last-10 mean per 90 × minutes | C. last-10 **median** per 90 | D. **all history, shrunk** | E. shrunk + half-life 12 |
|---|---|---|---|---|---|
| shots | −1.289 | −1.261 | −1.654 | **−1.244** | −1.255 |
| sot | −0.779 | −0.765 | −1.106 | **−0.730** | −0.735 |
| tackles | −1.570 | −1.519 | −1.777 | **−1.508** | −1.511 |
| fouls committed | **−1.570** | −1.648 | −1.810 | −1.635 | −1.633 |
| fouls won | **−1.815** | −1.915 | −2.170 | −1.895 | −1.892 |

Three things fall out.

**The 10-match window loses.** For the three metrics the engine actually models, using all of a
player's history shrunk toward the positional mean beats a ten-game window. Ten matches throws
away information that shrinkage uses properly.

**The median is much worse — by 0.3 to 0.4, which is a large margin here.** This matters because
the median was the proposal's answer to "one good game should not move the baseline". It is the
wrong tool: it discards the magnitude of every observation. The right answer to that worry is
shrinkage, which is already in the engine: a prior pulls an outlier back in proportion to how
little evidence stands behind it, without throwing the evidence away.

**Fouls behave differently from shots.** For fouls, the plain per-game mean beats both the per-90
version and shrinkage. That is a real result and it is the most useful thing in this table: it says
**the right baseline is not the same for every metric**, so the proposal's "one rule for all of
them" is the part to drop. Fouls are probably not minutes-proportional in the way shots are, and the
league mean is a poor prior for them. Each metric should have its baseline chosen by measurement.

## 4. Tested: does the opponent adjustment help?

### 4.1 At the level of the whole team's concession

Same walk-forward. The opponent factor is what that opponent has allowed per match, relative to the
league, built from **earlier matches only**, and multiplied into the baseline.

| metric | baseline only | × opponent (cap 1.5) | × opponent (cap 1.25) | **× √opponent** |
|---|---|---|---|---|
| shots | −1.244 | −1.239 | −1.239 | **−1.240** |
| sot | −0.730 | −0.726 | −0.725 | **−0.726** |
| tackles | −1.508 | −1.505 | −1.505 | **−1.503** |

Paired against the baseline, at the project's 2-standard-error gate (docs/37):

| metric | cap 1.5 | cap 1.25 | **√opponent** |
|---|---|---|---|
| shots | z +1.54 | z +1.69 | **z +2.86 PASS** |
| sot | z +1.45 | z +2.04 PASS | **z +2.65 PASS** |
| tackles | z +0.68 | z +1.01 | **z +2.26 PASS** |

**The instinct is right and the naive form of it is not.** Multiplying by what the opponent allows
helps, but the raw factor over-corrects and the gain drowns in its own variance. Taking the square
root — half the adjustment, in log space — passes the gate on all three. A weak signal applied
gently beats the same signal applied hard.

### 4.2 By opponent **and** position

This is `engine.opp_pos_k`, which already exists and is off. Run through the project's own
walk-forward A/B (`engine_ab.py`, 16 rounds):

```
player shots     z -2.26
player sot       z -0.95
player tackles   z -1.90
player ALL       z -3.08      -> leave engine.opp_pos_k off
```

**Significantly worse.** Slicing by opponent *and* position cuts the data so thin that each cell is
noise. The pooled version in §4.1 gains because it has far more observations behind each estimate.

## 5. The algebra that settles where the opponent can act

A player's forecast is his share of his team's expected count:

```
mus_i = mu_team × rate_i × m_i/90 / Z        where Z = Σ_j rate_j × m_j/90
```

Multiply **every** player's `rate` by the same opponent factor `f`. The numerator scales by `f`;
so does `Z`. They cancel exactly — verified numerically, identical to 12 decimal places.

> **A pooled opponent factor applied at player level is a no-op. It can only enter through
> `mu_team`, which is exactly where the engine already puts it** (the GLM offsets, and
> `style_opp_adjust` for shots, fouls and yellows).

This also explains §4.2: `opp_pos` is written to redistribute between players while holding the team
total fixed — its own docstring says so. Position-specific is the *only* shape that does anything at
player level, and that is the shape the data cannot support.

And it explains why §4.1 gained: that test used a crude player-only baseline with **no team model at
all**. Against a naive baseline the opponent factor adds real information. Against the engine, which
already carries the opponent in `mu_team`, most of that information is already present. **§4.1 is a
fair test of the proposal against a simpler version of the proposal. It is not evidence that the
engine would improve.**

## 6. What is genuinely missing — and the best idea in the proposal

The proposal's strongest part is the goalkeeper, and it is a principle the rest of the engine only
half uses:

> **Model the rate, not the count, and take the volume from somewhere that knows it.**

Saves are not a keeper property. **Shots on target faced** is a property of the opponent and of his
own defence; **save percentage** is a property of the keeper. They have different drivers and need
different amounts of data to estimate. Averaging saves over ten games mixes them and gets a noisy
number that moves when the defence changes, not when the keeper does.

```
expected saves  =  expected SOT faced  ×  save rate
                   (already modelled:        (keeper property, bounded,
                    sot is in STATS)          stable, few observations needed)
```

The same decomposition generalises:

| Market | Volume, from the team or opponent model | Rate, from the player |
|---|---|---|
| **Saves** | opponent's SOT | save % |
| Player SOT | his shots | his accuracy |
| Player shots | team shots | his share — **the engine already does this** |
| Yellow card | his fouls | foul-to-card conversion |
| Fouls won | opponent's fouls committed | his share of them drawn |

The engine already uses this shape for shots. Extending it is a real improvement, and it is the part
of the proposal that is not already built.

What is missing, with the data already in the database:

| Market | Data | Model |
|---|---|---|
| Goalkeeper saves | `saves` in `PLAYER_COLS`; **0 rows in the simulator**, and no GK in it | none |
| Player fouls committed | **2,269 rows** | none |
| Player fouls won | **2,427 rows** | none |
| Player cards | not collected per player | none |
| Team corners / shots / SOT / goals **against** | `corners_against`, `shots_against`, `sot_against`, `goals_against` all present | not offered as markets |

## 7. What to do

1. **Leave `engine.opp_pos_k` off.** Tested twice, worse both times. Record it in docs/37.
2. **Re-run §3 and §4 on production.** The scripts are small and read-only. If §4's √-damped
   opponent factor still passes there *against the full engine* rather than against a naive
   baseline, it is worth adding as a setting. On this data that comparison was not made, and §5
   suggests the gain will be much smaller.
3. **Build the keeper model** as `saves = expected SOT faced × save rate`. It is the one piece of
   the proposal with no counterpart in the engine, it uses a decomposition the engine already trusts
   elsewhere, and goalkeepers currently have no market at all.
4. **Add player fouls committed and fouls won.** The data is there; the models are not.
5. **Offer the "against" team markets.** The columns exist.
6. **Do not adopt one baseline rule for every metric.** §3 shows fouls want a different estimator
   from shots. Fit the choice per metric and let the gate decide.

## 8. Scripts

In `scripts/measure/`, kept out of `run_tests.sh` on purpose: they answer a question, they do not
assert anything, so they are measurements rather than tests. Each runs against the simulated league
as written; swap `demo_server.build()` for a read-only `MongoClient` to run them on production.

| Script | Section |
|---|---|
| `scripts/measure/baseline_choice.py` | §3, five estimators per player metric |
| `scripts/measure/opponent_damping.py` | §4.1, four damping choices with paired z |
| `backend/engine_ab.py --only opp_pos` | §4.2, the project's own harness |
| `scripts/measure/team_baseline.py` | §9, six estimators per team metric |
| `scripts/measure/rate_decomposition.py` | §10, the goalkeeper principle, and the diagnostic in §10.2 |


---

## 9. The team side of the same question

§3 answered "which baseline?" for the metrics that belong to a player. The proposal also named
corners for and against, goals for and against, fouls and cards, which belong to a club. Same
walk-forward method, same rule that every prediction sees earlier matches only, `team_baseline.py`.
The dispersion `r` is fitted once per metric by moments and then held fixed across methods, so
what is being compared is baselines and not dispersions.

| metric | A. last-10 mean **(as proposed)** | B. last-5 | C. last-10 median | D. all history, shrunk | E. shrunk + half-life | F. **shrunk × venue** |
|---|---|---|---|---|---|---|
| shots | −3.034 | −3.060 | −3.074 | −2.992 | −2.997 | **−2.981** |
| sot | −2.354 | −2.402 | −2.384 | −2.308 | −2.314 | **−2.297** |
| corners | −2.339 | −2.375 | −2.377 | −2.296 | −2.295 | **−2.295** |
| corners against | −2.359 | −2.415 | −2.393 | −2.311 | −2.314 | **−2.311** |
| shots against | −3.058 | −3.105 | −3.095 | −3.032 | −3.035 | **−3.024** |
| sot against | −2.370 | −2.402 | −2.373 | −2.342 | −2.346 | **−2.333** |
| tackles | −3.202 | −3.269 | −3.234 | **−3.197** | −3.201 | −3.201 |
| goals | −1.693 | −1.757 | −1.768 | −1.648 | −1.644 | **−1.638** |
| goals against | −1.692 | −1.744 | −1.800 | −1.646 | −1.646 | **−1.639** |

Paired against A, the form the proposal asked for, at the project's 2-standard-error gate:

| metric | B. last-5 | C. median | **D. shrunk** | E. + half-life | **F. × venue** |
|---|---|---|---|---|---|
| shots | −1.14 | −2.48 | **+2.32** | +2.07 | **+2.41** |
| sot | −2.01 | −1.23 | **+2.84** | +2.42 | **+2.72** |
| corners | −1.35 | −2.23 | **+2.09** | +2.15 | **+2.09** |
| corners against | −1.74 | −1.52 | **+2.87** | +2.74 | **+2.76** |
| shots against | −1.71 | −1.98 | +1.66 | +1.55 | +1.99 |
| sot against | −1.41 | −0.17 | **+2.09** | +1.74 | **+2.21** |
| tackles | −2.49 | −1.73 | +0.42 | +0.07 | +0.12 |
| goals | −1.78 | −2.19 | +1.98 | **+2.43** | **+2.27** |
| goals against | −1.58 | −1.90 | **+2.59** | **+2.61** | +1.89 |

n = 120 team-matches per cell.

**The ten-match window loses on the team side too, and here it loses significantly.** Shrinkage
clears the gate on six of the nine measurable metrics and is ahead on all nine. This is the same
result as §3 and it is now the second independent confirmation of it.

**The median has now been measured twice and lost twice.** It is worse than the mean on every
single team metric, z −0.17 to −2.48. The proposal reached for it to stop one good game moving the
baseline; shrinkage does that job without throwing away the magnitude of every observation.

### 9.1 Venue is worth more than the window

| metric | home factor | away factor |
|---|---|---|
| goals | **1.159** | **0.841** |
| sot | 1.066 | 0.934 |
| shots | 1.036 | 0.964 |
| corners | 0.988 | 1.012 |

Goals swing 38% between home and away. Nothing in the choice of window or estimator is worth
anything like that. The engine already carries it — venue is a GLM feature (`r.home` in the team
fit) — so this is a confirmation and not a change. It is worth stating because a bare "ten-match
average" has no way to express it, and the proposal's form of the baseline would quietly throw it
away.

### 9.2 Two metrics the proposal named cannot be answered here

Team **fouls** and **yellow cards** are zero in every row of this data. All six methods scored an
identical −0.020, which is the likelihood floor, and the paired z came back as `nan`.

That is an absence, not a tie, and the script now says so in those words rather than printing a
row of equal numbers that would read as agreement. Player fouls do exist — 2,269 committed and
2,427 won (§6) — so the player side of fouls was measurable in §3 while the team side is not.
**On this data the proposal's cards and fouls baselines are untested in both directions.**

## 10. Tested: "model the rate, not the count"

§6 argued that the best part of the proposal is the goalkeeper, and that the principle generalises:
expected saves is expected shots on target faced multiplied by a save percentage, because volume
and rate have different drivers and need different amounts of data. §6 asserted that. This tests it.

The simulator has no goalkeeper and no saves rows, and team cards are zero (§9.2), so the one
market with the same shape and real data here is **player shots on target = his shots × his
accuracy**. Three forecasts, same rows, same distribution, same dispersion, paired:

| | log-likelihood | paired z vs direct |
|---|---|---|
| **direct** — his own shrunk SOT rate (what the engine does today) | −0.7302 | — |
| **decomposed** — expected shots × his shrunk accuracy | −0.7254 | **+4.58** |
| **decomposed, league conversion** — expected shots × the league rate | **−0.7199** | **+2.08** |

n = 1343 player-matches.

**The principle holds: decomposing beats modelling the count directly, z +4.58.** That is the
clearest single result in this document and it is the part of the proposal §6 identified as new.

**But the whole gain comes from the volume, not from the player's rate.** Replacing his own
accuracy with the flat league rate scores *better*, not worse (−0.7199 against −0.7254), and his
own conversion is worth z **−1.36** — nothing, pointing slightly the wrong way. The mechanism is
not "recover a player-specific conversion". It is that **shots is estimated on three times as many
events as shots on target, so its rate is less noisy, and multiplying a well-estimated volume by a
flat rate beats estimating the noisy count directly.**

### 10.1 What this does and does not say about the keeper model

It says: build it as `expected SOT faced × save rate`, and **shrink the save rate hard toward the
league** until a keeper's own figure has earned its weight. Expected SOT faced is a team quantity
the engine already models from plenty of events; save percentage is one number per keeper over a
few dozen shots. The measured result is that the volume half carries the value, which is an
argument for leaning on the part the engine is already good at.

It does **not** say a keeper's own save percentage is worthless, and the reason is a limit of this
data rather than a finding. In `soccer_brain/simulate.py:99` accuracy is generated as

```python
acc = _sigmoid(-0.85 + 0.9 * (att[X] - dfn[Y]))   # a property of the TEAM matchup
sot = rng.binomial(shots, acc)
```

and the per-player split reuses the *shots* weights with fresh lognormal noise at sd 0.1. **There
is no persistent per-player finishing skill in this simulator at all.** So "his own conversion adds
nothing" is true by construction, and it would be measured here whether or not it is true of real
football, where finishing and shot-stopping plainly do persist. The volume-side result does not
depend on that: it follows from one quantity having more events behind it than the other.

### 10.2 A discarded row, and why

An earlier version of this test reported an **oracle**: the actual shot count, known, times a
shrunk conversion, as a ceiling on what the decomposition could achieve. It is not reported,
because it is not a ceiling.

Scored first as a negative binomial it came out at z −6.83, below the forecast it was meant to
bound. That was the wrong distribution: once the volume is known the count cannot exceed it, which
is a binomial, and the negative binomial charged the ceiling for variance it does not have.
Rescored as a binomial it improved to z −4.44 and was still below. Conditioning on the truth cannot
make a forecast worse, so something else was being measured. On the same rows, with the volume
known throughout:

| volume known, scored as | log-likelihood |
|---|---|
| binomial, league conversion | **−0.8136** |
| binomial, shrunk conversion | −0.8474 |
| binomial, unshrunk conversion | −1.2661 |
| beta-binomial, concentration 4 | −0.8231 |
| beta-binomial, concentration 12 | −0.8331 |

Every one of them sits below the direct negative binomial at −0.7302. No beta-binomial beats the
plain league-rate binomial, so overconfidence about the conversion is not the explanation either.
What that row was measuring is a **change of distribution family**, not the value of knowing the
volume, and a cross-family comparison at this granularity says nothing about the question.

Also visible in that table: per-player accuracy has an apparent spread of 0.110 sd over players
with 20 shots or more, and yet estimating it loses to ignoring it. Most of that spread is sampling
noise. It is the same lesson as the median in §3 and §9 — **an estimate that looks like signal
because it varies is still noise if it does not predict.**

The oracle variants stay in `rate_decomposition.py` as a diagnostic, with the reasoning in the
output, so the next person does not reach for the same row and read it the same wrong way.

## 11. What to do, revised after §9 and §10

The six items in §7 stand. These three replace nothing and are what the new measurements add:

7. **Build the keeper model as `expected SOT faced × save rate`, with the save rate shrunk hard to
   the league.** §10 measured the decomposition winning and the volume half carrying all of it.
   Treat the keeper's own save percentage as a small correction to be earned on real data, not as
   the model's main term.
8. **Do not adopt a ten-match window anywhere.** It has now lost on the player side (§3) and the
   team side (§9), and on the team side it loses at the project's gate on six metrics.
9. **Get team fouls and cards into the database before promising anything about them.** §9.2: both
   columns are empty here, so neither the baseline nor the opponent question can be asked of the
   two metrics a reader is most likely to want next.
