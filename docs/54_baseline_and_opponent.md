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
| Baseline per player and team, per metric | **Already built**, and better than proposed | §3 |
| A 10-match window | **Loses** to all-history with shrinkage | §3 |
| A median, so one good game does not move it | **Much worse** — costs 0.3 to 0.4 log-likelihood | §3 |
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
| `scripts/measure/baseline_choice.py` | §3, five estimators per metric |
| `scripts/measure/opponent_damping.py` | §4.1, four damping choices with paired z |
| `backend/engine_ab.py --only opp_pos` | §4.2, the project's own harness |
