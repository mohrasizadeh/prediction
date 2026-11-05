# 56. A line that can move

Built 2026-11-05. Asked for, more than once and in plain terms:

> If the app provides an obvious useless forecast, nobody wants to pay for something they can
> already look at online.

docs/50 and docs/52 answered half of this: give each entity its own line, so the count on the card
is a claim rather than a description. This is the other half, and it works whether or not personal
lines are on.

---

## 1. The idea in one sentence

**What makes `9+ shots, 88%` useless is not that it is likely. It is that it cannot move.**

Likelihood was the wrong thing to diagnose. A high percentage is not a fault — a reader is entitled
to want near-certainties, and docs/44 restored them deliberately after an earlier change threw them
away. The fault is **insensitivity**: if every opponent in the league produces nearly the same
number, then the number carries no information about *this* fixture, and the engine that produced it
was not needed.

So the test is not "is this percentage high?" but **"could this have come out differently against a
different opponent?"**

## 2. The measure: `span`

For a rung at count `k`, with the league's spread of defences:

```
span  =  | P(X >= k | the leakiest defence)  -  P(X >= k | the meanest defence) |
```

in likelihood points. The range is **the league's own**, not a chosen constant: half the 10-to-90
range of the concession strengths the engine already keeps in its snapshot
(`Engine._opp_log_spread`). Team lines measure it on `mu_team`; player lines measure it through the
whole minutes mixture, because the opponent reaches a player through the team total (docs/54 §5).
When the chance to play is divided out, the span is scaled with it, so it stays in the same units
as `p`.

A snapshot too thin to say gives `span = None`. **Unknown is never read as small**, because a
missing field must never silently hide a card.

For a five-shot striker, measured:

| rung | span |
|---|---|
| 1+ shots | **3.7 points** |
| 2+ | 12.4 |
| 3+ | 21.7 |
| 5+ (his own level) | **31.3 points** |

Eight times the movement at his own line. That ratio is the whole argument.

## 3. What it finds on a full run

358 lines, 342 with a span. Sorted by lowest span, the top of the list is the complaint itself,
with nothing hand-picked:

```
span  0.43pts  p 91.9%  team   7+ shots
span  0.61pts  p 91.7%  team   2+ shots on target
span  0.94pts  p 91.7%  team   8+ shots
span  1.19pts  p 96.5%  player 1+ shot
span  1.81pts  p 91.4%  team   9+ shots
span  2.05pts  p 90.8%  team   2+ corners
```

The distribution:

| percentile | span |
|---|---|
| p5 | 2.77 |
| p10 | 5.26 |
| p25 | 8.12 |
| **p50** | **9.52** |
| p75 | 12.90 |
| p90 | 15.32 |

| scope | stat | n | median span | under 8 points |
|---|---|---|---|---|
| player | shots | 136 | 9.00 | 26.5% |
| player | sot | 28 | 8.98 | 7.1% |
| player | tackles | 72 | 12.91 | **0.0%** |
| team | corners | 36 | 9.29 | **44.4%** |
| team | shots | 36 | 10.40 | **44.4%** |
| team | sot | 34 | 12.93 | 35.3% |

Two things worth noting. **Team lines are the insensitive ones** — 44% of team corners and shots
lines move less than 8 points, against 0% of player tackles lines. That matches the original
report, which was about teams (`PSG 9+ shots`) before it was about players. And **player tackles
are never trivial**, so the gate will not touch that market at all.

## 4. The gate

`queries.is_trivial` and `group_cards`: an insensitive rung does not lead a card while any other
line in the group can.

It is a **demotion, not a deletion**. The line keeps its place in `more_lines`, in the ladder, in
the Finder, and available to a combo. Nothing is lost and nothing is hidden; what changes is which
true statement gets said first. That is deliberate — a reader who wants the near-certainty is one
tap away, and the only thing taken from them is having it shouted.

Two floors keep it from doing harm:

1. **A group whose every rung is insensitive still produces a card.** An empty feed is not an
   improvement on a dull one.
2. **An unknown span never gates.**

### 4.1 The threshold, and a trap in it

`engine.min_span`, **default 0.06**, chosen from §3 rather than guessed:

| min_span | cards | leads changed | median lead likelihood |
|---|---|---|---|
| 0.00 | 134 | 0 | 68.3% |
| 0.04 | 134 | 1 | 68.3% |
| **0.06** | 134 | **10** | 68.1% |
| 0.08 | 134 | 28 | 66.0% |
| 0.12 | 134 | 51 | 62.2% |
| 0.20 | 134 | **3** | 67.9% |

0.06 catches every line in the §3 list — all of them move under 2.3 points — while reshuffling the
lead of only 10 cards in 134. 0.08 is a reasonable next step once this has been watched on
production.

**Read the last row carefully.** At 0.20 only three leads change, *fewer than at 0.06*. That is not
noise: above the 90th percentile of spans, nearly every rung in a group is insensitive, so floor 1
takes over and the lead reverts to what it would have been. **Setting the threshold too high
switches the gate off in effect, while looking like the strictest setting available.** Anyone tuning
this needs to know that, which is why it is in the setting's own help text too.

## 5. Why this is not the same as the earlier fixes

| | what it changes | needs calibration first? |
|---|---|---|
| `engine.personal_lines` (docs/52) | **which rungs exist** — generates 4+, 5+, 6+ for a five-shot striker | **Yes.** It makes the 40–70% band load-bearing and that band has never been tested |
| `engine.min_span` (this doc) | **which existing rung leads** | **No.** Accuracy is untouched; no number changes |

They are complements, and neither alone is enough. Personal lines create the rung worth leading
with; the span gate stops a trivial rung leading when personal lines are off, or when the
entity's own rung has nothing to say. Shipping the gate first is deliberate: it carries no
calibration risk, so it can go on now while the other waits for evidence.

The docs/37 walk-forward gate **cannot judge either of them**, for the reason docs/50 §7 gives:
accuracy does not change, the same ladder is computed either way. What changes is which true
statement gets said out loud.

## 6. What this does not do

- **It does not fix a wrong number.** Nothing here changes any likelihood. If the engine is
  mis-centred on a player, the span gate will faithfully promote a mis-centred rung that happens to
  be sensitive. docs/53 §4.1's unlocated 36% is untouched by this and still needs production
  instrumentation.
- **It does not create the right rung.** For a five-shot striker with the ladder stopping at 3+, the
  gate can only promote 3+. docs/52 is what makes 5+ exist.
- **The thresholds and the distribution in §3 are from the simulated league.** The shape should hold
  — it comes from the spread of defences, which every league has — but re-run
  `scripts/measure/span_choice.py` on production before moving the setting off its default.

## 7. Scripts and settings

| | |
|---|---|
| `scripts/measure/span_choice.py` | §3 and §4.1: the distribution, and what each threshold does |
| `backend/tests/selftest_triviality.py` | the seven ways this can fail, including the two silent ones |
| `engine.min_span` | 0.06, on. The gate |
| `engine.min_p_start` | 0, off. docs/55 §2.1, the other gate this work found missing |
