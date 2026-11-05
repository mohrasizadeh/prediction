# 53. The Kane card

A real card, reported 2026-11-03: **Harry Kane, 1+ shot, 90%**, with a strip showing his last ten
games at 3, 6, 6, 5, 8, 5, 5, 4, 2, 6 — fifty shots, five a game, never fewer than two.

---

> ## RETRACTION, written after the sections below
>
> **The first version of this document said the model was wrong. That claim does not hold and I am
> withdrawing it.**
>
> I said it twice, with confidence, on the strength of a ratio audit comparing each player's
> forecast against his own recent mean. **That audit was invalid.** It included players the engine
> had correctly modelled as substitutes — every badly-wrong row in it turned out to have
> `ps = 0.00`, meaning a confirmed lineup had them on the bench — and compared their twenty-minute
> expectation against their starter history. Apples to oranges.
>
> Repeating it properly, on **confirmed starters only**, where the comparison is sound:
>
> | | median |
> |---|---|
> | engine's implied mean ÷ his own starter history | **1.20** |
> | `p_usual`'s implied mean ÷ his own starter history | **1.30** |
>
> Over 105 confirmed starters the engine runs **above** a player's own record, not below. There is
> no systematic under-call.
>
> **So what about Kane?** ~~`p_usual` of 92% at 1+ shot implies a mean of 3.53 shots. At his rate
> of 5.55 per 90 that is about 57 expected minutes — a reasonable allowance for rotation risk
> before a lineup is confirmed.~~ **WITHDRAWN 2026-11-05, and see docs/55 §2 for the measurement
> that kills it.** The minutes explanation does not hold for a player like Kane. With
> `engine.condition_on_play` on, which is the default, a settled starter's conditional expected
> minutes are already his *starting* minutes: measured across 116 players with a start rate of 0.80
> or better, the median "if he features" figure is 76.1 minutes against 77.3 for "if he starts" — a
> gap of **0.0%**. There is no 57-minute rotation allowance in his card to find. On a mean of 3.06,
> 2+ shots at 72% is still arithmetically right, so the fitted mean stands; what does not stand is
> my account of where it came from.
>
> This makes the gap identified in §4.1 **worse, not better**: it is real, it is about 36%, and it
> is still unlocated. The minutes story then filled that hole in this document and in the answers I
> gave on top of it. It should not have. What is left is the opponent adjustment, `Z` and the
> shrinkage, and locating it needs the engine instrumented against production.
>
> **What survives** is sections 2 and 2.1: the headline is the dullest rung he owns, his median is
> five shots, and the ladder stops at 3+. That is real, and docs/52 addresses it.
>
> **What this exposes instead** is a presentation fault I had not named: the card shows 90% without
> ever saying it rests on about 57 expected minutes rather than a full match. The number is
> defensible; its basis is invisible. A reader comparing it with a ten-game strip of 67-minute
> starts has no way to see why they disagree. That is worth fixing, and it is not an engine fix.
>
> Sections 3 to 5 below are kept so the reasoning can be audited, with their errors marked. Do not
> act on them.

---

## 1. What the card shows

| | |
|---|---|
| Headline | 1+ shot, **90%** (86 to 92) |
| His record on that line | 15 of his last 16 games |
| "A player like him in a fixture like this" | usually 92% |
| The strip | ten games, all green, "10 of 10 reached it" |
| The whole ladder | 1+ shot 90%, 1+ SOT 74%, 2+ shots 72%, 3+ shots 52%, 2+ SOT 45%, 3+ SOT 23% |

His last ten: **50 shots, mean 5.00 a game, 5.55 per 90**, lowest 2.

## 2. Problem one: the line is the dullest rung, and the ladder cannot reach a better one

The headline is the lowest rung he owns, which is docs/52's whole subject. But this card shows
something docs/52 only half covers:

> **His median is 5 shots. The ladder stops at 3+.**

There is no 4+ or 5+ shots rung anywhere in the card. So "show his own line instead" cannot be done
by re-ranking what exists — the engine never computed the rung that matters for him.
`PLAYER_THR = {"shots": [0.5, 1.5], ...}` is a global ladder, and `engine.player_ladder` only swaps
one global list for another. docs/52's `personal_thrs` generates the ladder **around** his own
half-way count, so for Kane it would produce 4+, 5+, 6+. That part of docs/52 is not a presentation
change; it is the only way the right rung comes to exist at all.

The strip has the same problem. Ten green boxes and "10 of 10 reached it" is a picture of nothing.
At his own line it would read 7 of 10 and the boxes would differ.

## 3. ~~Problem two, the serious one: the numbers disagree with his record~~ (WITHDRAWN - see the retraction)

Fit a negative binomial to the three shot percentages on the card:

| Shown | 1+ 90% | 2+ 72% | 3+ 52% |
|---|---|---|---|
| Fitted exactly by | **mean 3.06 shots, r = 4** | | |

The fit is exact — residual 0.0000. So the engine's central estimate for this match is **3.06 shots**
against a recent rate of **5.00 a game**: **39% below his own record.**

Set against what he has actually done:

| | his last 10 | the card | a negative binomial at *his* mean of 5.0 |
|---|---|---|---|
| 2+ shots | **10 of 10** | 72% | 87% |
| 3+ shots | **9 of 10** | 52% | 75% |
| 5+ shots | 7 of 10 | not offered | 49% |

**A striker who has taken two or more shots in ten consecutive games is given 72%.**

### 3.1 The record anchor is hiding how bad it is

docs/32 blends the model with the player's own record, weight `n/(n+30)` capped at 0.4. With 16
games that weight is 0.35. Backing the blend out of the 2+ line:

> before the anchor the model said about **48%** for 2+ shots, against a record of 16 in 16.

The anchor pulled 48% up to 72%. It is doing the work the rate model should be doing, and because
the weight is capped it can only ever recover about a third of the error. **A patch over a wrong
number looks like a working forecast until you back the patch out.**

## 4. Where the 39% goes — and a correction to my first answer

I first blamed `engine.player_prior`, which is 40 for shots, and produced a table showing it halved
his rate. **That table was wrong and I have deleted it.** I had read the exposure as games. It is
not: line 922 of `soccer_brain/engine.py` is

```python
E = (ap["team_" + s] * ap["minutes"] / 90.0).values
post[pid] = shrunk_rate(ap[s].values, E, self.rho[s][info["pos"]], self.player_prior.get(s, 40.0), self.hl)
```

so `post[pid]` is his **share of his team's shots** and the prior is 40 *team-shots* of exposure, not
40 games. Sixteen games at ~13 team shots is about 152 units of exposure after decay, so the prior
takes about 21% of the weight, and the pull is:

| prior | shrunk share | × 13 team shots |
|---|---|---|
| raw | 0.409 | 5.32 |
| 4 | 0.402 | 5.23 |
| **40 (current)** | **0.353** | **4.59** |
| 80 | 0.316 | 4.11 |

So shrinkage costs about 14%, not half. The remaining fall from 4.59 to 3.06 comes from the minutes
mixture, the opponent adjustment and the share renormalisation `Z`. **I could not attribute it
further from a screenshot, and I am not going to guess.** What is certain is that each step is
individually defensible and together they land 39% below the player's own record.

### 4.1 Three hypotheses, all rejected by measurement

I tried to locate the missing 39% and failed three times. Recording them so nobody repeats them:

| Hypothesis | Test | Result |
|---|---|---|
| `engine.player_prior` (40 for shots) halves his rate | recompute `shrunk_rate` with the real exposure | **Wrong.** I had read the exposure as games; it is team-shots. The pull is about 14%, not half. |
| `Z` is summed over the whole squad, so skipped players' shares are divided out and lost | change `Z` to sum over the players the loop keeps, re-measure | **No-op.** Instrumented: `squad=14, kept=14` on every call. Every squad member already clears the 15% threshold. Change reverted. |
| The players carried sum to only 0.87 of the team total, so shots leak | trace where the other 13% goes | **Not a leak.** Those are players whose forecasts are dropped later by `engine_bridge`'s `min_play` rule, which is documented behaviour (docs/36 H9). |

So the under-call is real and measured, and **its mechanism is still unlocated**. What is left is the
minutes mixture (`scen_all`), the opponent adjustment (`opp_pos_f`) and the team total (`mu_team`).
Finding it needs the engine instrumented against the real database, not a simulated league, and it
should not be guessed at again.

## 5. ~~Is it only Kane?~~ (WITHDRAWN - this audit is the invalid one)

Audited every player forecast in a full league run — 109 players with at least six games and a mean
above one shot — comparing the engine's `expected` against that player's own last-ten mean:

| | |
|---|---|
| Median `expected` / own mean | **1.06** |
| Mean | 1.05 |
| Below his own mean | 41 of 109 |
| Above | 55 of 109 |

**On average the engine is well centred.** But the tail is bad:

```
expected 0.86   own mean 3.10   ratio 0.28    shown: 1+ shot at 63%
expected 0.68   own mean 2.20   ratio 0.31    shown: 1+ shot at 53%
expected 1.66   own mean 4.70   ratio 0.35    shown: 1+ shot at 86%
expected 1.06   own mean 2.70   ratio 0.39    shown: 1+ shot at 68%
```

So this is not one number to retune. It is a minority of players being badly mis-served while the
average looks healthy — and those players are the ones anybody opens the app to read about. Kane's
ratio of 0.61 is not even the worst of them.

I did not establish **which** players, beyond that the tail exists. Whether it tracks volume,
minutes, position or squad size is the next question, and it needs the real database rather than a
simulated league.

## 6. What to do, in order (revised)

1. **Nothing in the engine.** Nothing has been shown to be wrong with it. The one valid measurement
   says it runs 20% above a confirmed starter's own record, if anything.
2. **Say what a number rests on.** When expected minutes are well below a full match, the card
   should say so. This still holds, but it is **not** what is happening on Kane's card — see the
   withdrawal in the retraction above and docs/55. It applies to rotated and fringe players, where
   the conditional minutes really do sit 15% and 39% below a start, and not to settled starters.
3. **Turn on `engine.personal_lines` (docs/52)** so the ladder reaches the rung that matters. That
   is the real answer to the original complaint.
4. **Keep the audit in the retraction as the standing check** — confirmed starters only, implied
   mean against own starter history. Run it on production. If it ever drifts below 1.0, that is the
   signal the first version of this document imagined it had found.

## 7. What this card got right

Worth saying, because the rest of this document is a list of faults. "A player like him in a fixture
like this: usually 92%" against a record of 15 in 16 is a good number, honestly presented. The band
`(86 to 92)` is there. The minutes are on the strip, so a 45-minute game is not silently counted as a
full one. The failure is not carelessness — it is a defensible chain of steps that compounds the
wrong way, and an anchor that hides the result.
