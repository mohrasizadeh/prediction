# 52. A line for each player and team

Built 2026-11-03, out of docs/50 and docs/51. Asked for: stop using one line for everybody, give
each player and each team its own, and report where this fixture puts them against it.

`PSG 9+ shots` needs no engine. Every team in the league clears it. The engine was being asked a
question with no answer and was answering it correctly.

---

## 1. The method, as asked for, and the three places it breaks

> For each player and metric, work out a median for that player separately, and set the line there.

The instinct is exactly right and the naive form of it does not survive contact with the data.

**It breaks on small integers.** A count is 0, 1, 2, 3. If a player's median is 2 shots, is the line
1.5 or 2.5? `P(X>=2) = 0.65` and `P(X>=3) = 0.35` — the median exists but neither rung is anywhere
near a half, and the one you pick changes the answer by thirty points.

**It breaks on short histories.** Six appearances, and one busy afternoon moves the median by a
whole shot. The line would then move week to week for reasons that have nothing to do with the
player.

**It breaks on substitutes.** A player's appearances mix starts with twenty-minute cameos. A raw
median across all of them is dragged down by the cameos, so his line is set too low, and then he
"beats his usual" every time he starts. That is an artefact of the baseline, not a forecast.

## 2. What was built instead

All three problems disappear if the line is read off the **fitted distribution** the engine already
has, rather than from a fresh median.

The engine already computes, for every player, `shrunk_rate(...)` — his own per-90 rate, shrunk
toward the positional mean with a prior weight of 4 and a half-life decay — and already carries it
through this match's minutes scenarios as `mus_b`. `p_usual` is the survival function of that. For
teams the equivalent is `mu_usual`, the club's own normalised rate against an average opponent.

So:

> **The line is the count `k` where that entity's own distribution crosses a half:
> `k* = argmin |P_usual(X >= k) - 0.5|`.**

- Small integers: solved by construction. We never take a median; we invert the distribution and
  take the nearer of the two rungs either side of the crossing.
- Short histories: solved by the shrinkage that is already there.
- Substitutes: solved because `mus_b` is already mixed over this match's minutes, and docs/27
  already divides out the chance to play.

`personal_k` and `personal_thrs` in `soccer_brain/engine.py`. Two neighbours are kept either side
(`engine.personal_spread`) so the Finder still has a range to answer from.

### Why this beats anchoring on the forecast

An obvious alternative is to set the line at the median of the *forecast* for this match. Do not.
Then `p ≈ 0.5` by construction and the card says "it could go either way", which is no better than
what it replaced.

Anchoring on the entity's **own usual** instead makes the number carry the message:

| p at the entity's own line | what it says |
|---|---|
| ≈ 50% | this fixture looks like their normal game |
| 68% | likely to beat what they usually manage |
| 32% | likely to fall short of what they usually manage |

A departure below is as real a forecast as one above. "Well short of his normal game, against this
defence" is a sentence worth reading, and the old scheme could never produce it.

## 3. What it does to the numbers

Same league, same engine, the setting off and on:

| | off | on |
|---|---|---|
| Median likelihood of a stored line | 0.704 | **0.519** |
| Lines at 85% or more | 93/358 (26%) | **54/746 (7%)** |
| Lines whose usual sits in 35–65% | 119/358 (33%) | **360/746 (48%)** |
| Groups led by the entity's own line | — | **540/546 (99%)** |

And in the concrete:

| Before | After |
|---|---|
| `7+ shots` at 89% (team whose usual is 14.2) | **`14+ shots` at 47%** |
| `7+ shots` at 75% (team whose usual is 13.1) | **`13+ shots` at 24%** |
| `1+ shot` at 93% (player whose usual is 3.3) | **`3+ shots` at 58%** |

The second row is the point of the whole exercise: 24% against a usual of 13.1 is a real claim —
this team is likely to fall well short of its own normal game. Nothing in the old scheme could say
that.

## 4. The consequence nobody asked for: tiers stop working

This is the part worth reading twice.

The tiers grade **how likely** a line is: Strong needs `p >= 0.80`, Solid `p >= 0.65`. Set the line
at the entity's own half-way count and every entity lands near 0.5, so on the first run with this
on, **84 of 90 personal lines fell below even Watch** and the feed showed none of them. The feature
was invisible.

That is not a bug in the tiers. It is the tiers answering a question that has stopped being
interesting. At a personal line, "how likely" has the same answer for everybody by construction.

So a personal line is graded on the question it was built to ask — **is this fixture unlike their
normal game, and how sure are we?**

| Tier | Test |
|---|---|
| **Strong** | the likely range sits wholly on one side of their usual, and the gap is at least `engine.departure_strong` (0.12) |
| **Solid** | the gap is at least `engine.departure_solid` (0.06) |
| **Watch** | the gap is at least half of Solid |
| none | this fixture looks like any other for them — honest, and not worth a card |

`tiering._departure_tier`. The lineup rules are unchanged and still apply on top, through
`_lineup_caveat`, so "Strong once the lineup is confirmed" still works.

A tier of `none` is a feature. It is the engine saying *I have nothing to tell you about this one*,
which is the sentence that was missing.

## 5. Ranking between cards

`queries.prominence` multiplied by `p`, so among lines that cleared the lift gate the more certain
one still won — the certainty preference docs/48 removed from one term survived in another. With a
personal line that is actively wrong, because `p` is the message.

For a personal line the term is now `4p(1-p)`: normalised Bernoulli variance, "how much is actually
at stake in this sentence". It scores a 60% line at 0.96 and a 96% line at 0.15. Without a personal
line the old reading still holds and the code still uses `p`.

`group_cards` leads with the entity's own rung whenever the group has one, so the neighbours exist
only to answer follow-ups.

## 6. Filtering by player and by club

`/api/insights` takes `players=` and `teams=` (comma-separated public ids), and `insights_feed`
takes `player_iids` / `team_iids`. On the Insights screen the two pickers offer **only what the
current feed holds**, so a choice can never empty the list.

## 7. Settings

| Key | Default | What it does |
|---|---|---|
| `engine.personal_lines` | **off** | the whole feature |
| `engine.personal_spread` | 1 | neighbours kept either side, for the Finder |
| `engine.departure_strong` | 0.12 | gap from usual needed for Strong |
| `engine.departure_solid` | 0.06 | gap needed for Solid; half of it is the Watch floor |

Off by default, like every docs/37 upgrade, so `engine_ab.py` can judge it on real data first.

## 8. What is not settled

**The departure thresholds are guesses.** 0.12 and 0.06 were chosen to give a sensible spread of
tiers on the simulated league. They have no backing. They should be set from real data so that a
Strong line is right about as often as a Strong line used to be.

**The walk-forward gate cannot judge this**, for the reason docs/50 §7 gives: accuracy does not
change, the same ladder is computed either way. What changes is which rung is shown. The evidence
has to come from the calibration report once the lower bins fill, and from reader behaviour.

**Calibration in the 40–70% band is now load-bearing and has never been tested.** Nearly every
shown line used to sit above 80%, so `track_record`'s lower bins were empty. They will fill now.
If the engine turns out to be poorly calibrated there, this change exposes it rather than causing
it — but it does expose it, and that is worth knowing before switching the setting on in public.

**Teams and players may want different thresholds.** They share `departure_*` today. Team
aggregates are steadier, so the same gap probably means more for a team than for a player.
Measure before splitting.

## 9. Two things the first run exposed

Both were found by looking at the feed rather than at the code, and both would have made the
feature useless while appearing to work.

**The neighbours kept their tiers, so the feed fell back to them.** The rungs either side of the
personal line are there for the Finder. They were still being graded, so the moment an entity's own
line had nothing to say, the feed showed a near-certain neighbour instead — exactly the card this
change exists to stop. `is_personal` was also never passed into `tiering.assign`, so the departure
tier never fired at all. With both fixed, 20 of 20 cards lead with the entity's own line.

**The "At least 50% likely" filter threw away every downward forecast.** The floor existed because
no line below 50% used to exist: `engine.line_band` started there. A forecast *below* an entity's
usual is as real as one above, and on the first run the filter silently cut 20 cards to 8 — all of
the shortfalls. The floor is now 0 and the slider reaches it.

That second one is worth keeping in mind generally: **this change makes a forecast below a half
meaningful for the first time**, and anything in the product that assumed "higher is better" needs
looking at. `lift` was one such place — it returned `max(0, ...)`, so a shortfall was tiered Strong
and then sorted last. It now reads both ways, but only for a personal line.

After all three fixes, on the same league:

| | before | after |
|---|---|---|
| Median likelihood of a shown card | 0.887 | **0.447** |
| Cards at 85% or more | 14 of 20 | **0 of 20** |
| Cards led by the entity's own line | — | **20 of 20** |
| Forecasts of a shortfall | 0 | **14 of 20** |

What the cards now say:

```
Team 4   14+ shots              63%   They usually manage 13.5 · this line lands 48% of the time
Team 7   13+ shots              24%   They usually manage 13.1 · this line lands 53% of the time
Player 704  3+ shots            64%   His usual game is 2.6 · this line lands 51% of the time
Player 713  1+ shot             63%   His usual game is 0.6 · this line lands 50% of the time
```

The second line is the one to read twice. It is a claim that a team will fall well short of its own
normal game, and the old scheme had no way to make it.
