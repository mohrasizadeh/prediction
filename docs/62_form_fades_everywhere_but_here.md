# 62. Form fades everywhere but here

Written 2026-11-08. The owner asked whether the engine weights a player's recent form — the last 5,
the last 10 — more heavily than older games, "as the player has gained either momentum, or role may
have changed, or the team is performing better as a whole".

The answer was yes in three layers and **no in the fourth**, and the fourth takes up to 40% of every
player number.

## What was already right

**The player's own rate fades.** `core.recency_weights` is `0.5 ** (age / half_life)`, so a game
`half_life` appearances ago counts half. Since docs/37 the player layer has its own half-life
(`engine.player_half_life`, 0 = inherit the team's 20).

**Team form arrives on its own.** A player's number is a share of a team total — `mu_team[s] *
rate[pid] * minutes_share / Z` — and the team GLM refits each run on recency-weighted rows. When the
club's shot volume rises, every player's number rises with it. Nothing had to be added for this.

**Role change is partly handled.** `contrib["role"]` is his rate against his position's league mean,
and the run strip carries position per game. But a role change is only absorbed as his rate drifts,
at the half-life's pace — there is no change-point detection. A winger moved to a false nine takes
about twenty appearances to be half-believed.

**Momentum as a state is deliberately absent**, and should stay absent. A hot run is treated as
evidence about his rate, not as a thing that persists. Most "momentum" in football counts is
regression waiting to happen.

## What was wrong

`engine.py` built the record the anchor blends toward:

```python
rec_k=int((last40 > thr).sum()), rec_n=int(len(last40))
```

A **flat count over the last 40 appearances**. No decay at all. A game from thirty-nine appearances
ago counted exactly as much as last week's — in the one layer that takes up to 40% of the final
number (`engine.anchor_max_w`).

Everything else in the engine decays. This did not, and nobody had noticed because it is spelled as
an honest-looking pair of whole numbers.

The effect, with the shipped half-life of 20 on a full 40-appearance record:

| | last 5 | last 10 |
|---|---|---|
| effective weight on the final number | **18%** | **33%** |

Two-thirds of a player's number came from beyond his last ten games.

### The case that shows it

A player who was poor for twenty appearances and good for the next twenty. Flat, that record is 20
of 40 — exactly average — and the anchor moves his number **not at all**. It averaged his two halves
away. Weighted at half-life 20 the same forty games read 67%, which pulls his number up **6.5
points**. The reverse case moves it down by the same amount. `selftest_anchor.py` pins both.

## The change

`engine.anchor_recency`, **shipped off**, as docs/37 requires of anything that moves numbers.

* The engine computes `rec_rate` (the recency-weighted share) and `rec_neff` beside the flat pair,
  and stores all four on every forecast whether or not the switch is on — so the two anchors can be
  compared on settled results later.
* `rec_k`/`rec_n` stay exactly as they were, because they are also what the sheet prints. "19 of his
  last 20" has to remain two whole games a reader can count off the strip.
* `rec_neff` is Kish's effective sample size, `(Σw)² / Σw²`, **not** `Σw`. The anchor's own weight is
  `n/(n+K)`, so using the raw weight total would claim more games behind the rate than the weighting
  leaves. On a 40-game window at half-life 20 that is 34.6, not 40.

What it buys, on a full 40-appearance record:

| player half-life | last 5 | last 10 |
|---|---|---|
| flat anchor, 20 (today) | 18% | 33% |
| **weighted, 20** | **21%** | **39%** |
| weighted, 12 | 28% | 49% |
| weighted, 8 | 36% | 60% |

So the weighted anchor alone is a modest move. Getting a player's last ten games to be most of his
number needs the half-life shortened as well, and that is the lever docs/37 already added and has
never been able to test.

## Measured on real football (2026-11-08), and the answer is split

Five Premier League seasons of per-player per-match records, from the openly published Fantasy
Premier League dataset. 220,812 out-of-sample predictions: every match predicted from that player's
earlier matches only, walking forward. Log loss, lower better, with a bootstrap clustered on
**player** so one man's forty appearances are not counted as forty independent facts.
`scripts/measure/recency_on_real_football.py`.

**Where recency LOSES — what a player does in a match:**

| target | n | flat | half-life 20 | half-life 8 |
|---|---|---|---|---|
| 1+ goal | 31,827 | 0.2966 | −0.0007 **worse** | −0.0044 **worse** |
| 1+ card | 31,827 | 0.3881 | −0.0004 | −0.0030 **worse** |
| 3+ saves (GK) | 2,290 | 0.6887 | −0.0003 | −0.0038 **worse** |

**Where recency WINS — whether a player is available:**

| target | n | flat | half-life 20 | half-life 8 | half-life 5 |
|---|---|---|---|---|---|
| 60+ minutes | 95,224 | 0.3836 | **+0.0132** | **+0.0258** | **+0.0311** |
| starts | 59,644 | 0.3941 | **+0.0198** | **+0.0390** | **+0.0484** |

Every interval on those five excludes zero, and both directions are monotonic in the half-life:
shorter is steadily better for availability and steadily worse for output.

### What that means for `engine.anchor_recency`

**Leave it off.** The anchor blends toward a player's record on *shots, on target and tackles* —
performance counts. On the closest analogues this data can supply, recency weighting makes those
predictions **worse**, and worse faster the shorter the half-life. The mechanism this setting
implements is real, and it is pointed at the wrong record.

That is the honest outcome of building it: the switch exists, it is measured, and the measurement
says do not use it here. It stays in the codebase because the measurement could change on shots
themselves, and because `rec_rate`/`rec_neff` are now stored either way.

This also vindicates the original design. A flat forty-game record is not an oversight — for an
output count it is **better** than fading, because a hot run in goals or cards is mostly noise and
a longer window is a better estimate of the rate underneath. The engine was right and the reasoning
for it had simply never been written down.

### Where the win actually is

`engine.py` builds the lineup record as a **flat** count: `info["starts_recent"] = int(k)` over the
club's last `n_win` matches, and `starter_badge` reads `starts_recent / club_recent >= share`. The
"starts" row above *is that question*, measured: weighting it by recency is worth **+0.0198 at
half-life 20 and +0.0390 at half-life 8**, over 59,644 predictions.

So the recency idea belongs on the **availability** side — whether he plays and for how long, where
a role change is a fact about now — and not on the output side, where it is noise. That is the next
change worth making, and unlike the anchor it already has its evidence.

## What the simulated league cannot measure, and why

### The demo



`scripts/measure/anchor_recency.py` reports the mechanical effect: on the demo, 46% of lines move by
more than half a point, and where recent form disagrees with the whole window the new number follows
**recent form 76% of the time**. That is a fact about the change.

Nothing says the new numbers are **better**. Two reasons, both structural:

* `simulate.py` draws each player one fixed skill at league creation and allocates every match from
  it, so a simulated player's form never drifts. There is nothing for recency to catch. This is the
  same wall the player half-life hit in docs/37.
* `engine_ab.py` cannot score it and deliberately has no variant for it: that runner scores
  `expected`, the mean the engine predicts, and the anchor moves `p` afterwards in `engine_bridge`.
  A variant would run, report a z, and the z would be about nothing.

Those two limits are why the question went to real football instead, in the section above. The
demo scripts stay because they measure what the change DOES, which is still worth knowing; they just
cannot say whether it is right. `rec_rate` and `rec_neff` are stored on every forecast either way,
so once a few hundred shots lines have settled the anchor can be tested on the market it actually
serves, with `--mongo`.
