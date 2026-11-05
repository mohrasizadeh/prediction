# 55. What a player's number assumes

Asked 2026-11-05:

> The chance of play must have nothing to do with whether the player is going to take a shot. We
> show that to users through the likely lineup. The calculation must be based only on the player's
> performance, and the chance to play must be completely removed from the forecast for any market.

The first half of this is **already built, on by default, and calibrated on real data**. The second
half is not, and measuring it found a defect worth fixing — in a different place from the one the
question points at.

---

## 1. What the engine already does

`engine.condition_on_play`, **default on**. From its own help text: on 93,000 real forecasts, with
it on, players rated 80–85% reached the line 84% of the time, where the all-in number sat 8 points
low at the top. `calibration_default.json` is fitted to this definition
(`version: default-2026-10-29-play`).

```python
mus   = [mu_team * rate * m/90 / Z  for _, m in sc]    # sc = [(ps, m_start), ((1-ps)*p_sub, m_sub)]
p     = sum(probs * nb_sf(k, mus, r))
if cond_play:
    p /= pplay                                          # pplay = ps + (1-ps)*p_sub
```

So the chance to play is divided out and shown as a lineup badge instead, which is exactly what was
asked for. `engine.min_p_play` (0.5) additionally withholds a card from a player unlikely to appear.

## 2. What is still folded in, and what it costs

Dividing by `pplay` renormalises the two-scenario mixture so it sums to one. It conditions on
**appearing**. The number is still a weighted blend of "starts about 75 minutes" and "comes on for
about 20". A card therefore means *if he features*, not *if he starts* — while the ten-game strip
beside it is made of starts.

Analytically, for one player:

```
Em_c / m_start  =  1 - (1-ps) * p_sub * (1 - m_sub/m_start) / pplay
```

Measured on every player with at least twelve appearances, rebuilding `_scenarios` exactly
(`scripts/measure/conditioning.py`):

| class | n | median start rate | median chance to **feature** | Em_c "if features" | m_start "if starts" | gap |
|---|---|---|---|---|---|---|
| settled starters (≥ 0.80) | 116 | 0.930 | 0.930 | 76.1 min | 77.3 min | **0.0%** (max 10.2) |
| rotated (0.50–0.80) | 29 | 0.733 | 0.932 | 66.0 min | 78.2 min | **15.2%** (max 30.7) |
| fringe (< 0.50) | 20 | 0.410 | 0.924 | 46.0 min | 77.2 min | **39.4%** (max 52.5) |

**For a settled starter the blend costs nothing.** His conditional minutes already *are* his
starting minutes. Conditioning on starting instead of on featuring would not move his card.

**For a rotated or fringe player it costs 15% to 39%**, and those are the cards where today's
number is a blend of a start and a cameo that describes neither of them.

### 2.1 The defect this exposes: the gate filters the wrong quantity

Look down the third and fourth columns of that table. **The median chance to feature is 0.93 in
every class, including the fringe players whose chance to start is 0.41.** A substitute who always
gets twenty minutes features in almost every match.

`engine.min_p_play` compares against the chance to **feature**. So a 41%-start player clears a
50% gate comfortably, gets a card built from a 46-minute blend, and that card is presented beside a
strip of his starts. The setting is doing much less than its label — "Hide players unlikely to
play" — promises, because a fringe player is not unlikely to play. He is unlikely to *start*.

This is the concrete thing to fix, and it is independent of everything else in this document.

## 3. The correction this measurement forces on docs/53

docs/53's retraction block explained Kane's card by saying its 90% rested on about 57 expected
minutes, as a rotation allowance. **That is withdrawn.** Kane is a settled starter, and the table
above shows a settled starter's conditional minutes sit 0.0% below his starting minutes. There is
no 57-minute allowance in his card.

The 57 was never a value the engine stores. It was back-solved from the screenshot: `p_usual` 92%
at 1+ shot implies a mean of 3.53, and 3.53 ÷ 5.55 per 90 × 90 ≈ 57. That arithmetic is right and
its interpretation was wrong — the same gap also absorbs the opponent adjustment and `Z`, so
attributing it to minutes was an assumption dressed as a reading.

The consequence is that **docs/53 §4.1's unlocated 36% is still unlocated**, and for a while the
minutes story was standing in for it. It needs the engine instrumented against production.

## 4. What to do

1. **Fix the gate first.** `engine.min_p_play` should test the chance to **start**, or gain a
   companion `engine.min_p_start`, so a fringe player stops clearing it on a 0.93 chance to
   feature. Smallest change here, no recalibration, and it removes the cards where the blend does
   real damage. §2.1.
2. **Then consider conditioning on starting** rather than on featuring, for the cards that remain.
   This is a definition change, so it cannot just be switched on: `calibration_default.json` is
   fitted against "if he plays", and changing what the number means without refitting the map would
   decalibrate every player percentage silently. It needs the docs/37 walk-forward gate and a
   refit, in that order.
3. **Do not expect either to change a settled starter's card**, and in particular do not expect
   them to change Kane's. The measurement is unambiguous on that point, and the temptation to
   present this work as the Kane fix is exactly the mistake §3 is correcting.
4. **A substitute's card should be its own claim, not a blend.** "About 1 shot if he comes on for
   twenty minutes" and "about 5 if he starts" are two statements; their weighted average describes
   neither. Worth doing after 1 and 2, and it needs a presentation decision, not only an engine one.
