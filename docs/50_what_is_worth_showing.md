# 50. What is worth showing

Research, 2026-11-03. Asked: how does StatsHub pick what to show, and what actually carries weight
for the reader — because "PSG 2+ shots on target, 91%" is true, and useless.

**Nothing in here is built yet.** It is the case for a change and the evidence behind it.

---

## 1. The finding, first

The app already holds the data to say something meaningful on **every single card**, and shows the
dullest rung on every single one.

Measured on the live Insights feed, 20 cards:

| | |
|---|---|
| Median likelihood of the shown line | **0.873** |
| Shown lines at 85% or above | **14 of 20** |
| Shown lines at 90% or above | 5 of 20 |
| Rungs on a typical ladder | 9.1 |
| Position of the shown rung in its own ladder (0 = lowest) | **0.9** — always the first or second |
| Rungs per ladder in the 35–65% zone | 2.3 |
| **Cards whose ladder contains a 35–65% rung** | **20 of 20** |
| **Cards currently showing one** | **0 of 20** |

The same ladders, side by side:

| Shown | On the same ladder, unshown |
|---|---|
| 1+ shot at **96%** | 2.5+ shots at **60%** |
| 1+ shot at **95%** | 3.5+ shots at **43%** |
| 9+ shots at **88%** | 15.5+ shots at **49%** |
| 4+ shots on target at **89%** | 8.5+ shots on target at **47%** |
| 4+ corners at **81%** | 6.5+ corners at **46%** |

This is not a modelling gap. `select_lines` stores the whole ladder on every line. It is a
selection rule, and the rule is working exactly as written.

## 2. Why it does this

Two decisions, each defensible alone, combine badly.

**docs/44 reversed the selection.** `select_lines` used to keep the most *ambitious* lines and now
keeps the most *likely* ones inside `engine.line_band`. Its own docstring says why: a striker with
1+ shot at 95% was showing "4+ shots 52%, 5+ 40%, 6+ 26%" and his near-certain lines existed
nowhere in the app. That was a real problem. The fix overshot: the band's default is
`[0.5, 0.985]`, and "the most likely in that band" is, for a 9-rung ladder, nearly always the
bottom rung.

**docs/46 ranks by `weight × lift × p`.** docs/48 moved lift to a log-odds scale precisely so
low-base-rate markets would stop winning on an arithmetic artefact. But the formula still
multiplies by `p` at the end. Lift only acts as a *gate* — a line with zero lift scores zero — and
among lines that pass the gate, the more certain one still wins. The certainty preference docs/48
removed from one term is still present in another.

## 3. What StatsHub does

`statshub.com` — PropHunter, Prop Screener, Player Trends, Team Screener, free, 100+ leagues.
Both the site and its mirror are blocked by this environment's network policy, so this is from
search results, not from reading their pages. **Treat it as second-hand.**

PropHunter is a **hit-rate screener**, not a forecaster. You choose a day, a stat, leagues, a line
(default `Over 0.5`) and a minimum hit rate (default `50%+`), and it counts how many of a player's
recent games cleared that line — their own worked example is "Shots over 0.5 in 5 of the last 10
games (50%)". Filters cover stat type (shots, shots on target, fouls committed, fouls won,
tackles), position, venue, bookmaker, minimum games played, and lineup handling (starts only, or
a substitute's stats combined with the player he replaced). Prop Screener is the same idea with
odds and recent form alongside.

**They do not decide what is meaningful. They hand the reader a filter and let them decide.** The
hit rate is descriptive — it is the raw frequency, with no opponent adjustment, no minutes model
and no statement about what is *expected* this week.

That is a genuinely different product from this one, and it is worth being clear about the
trade: their approach cannot be wrong, because it never makes a claim. It also cannot be useful
beyond what the reader brings. This app makes a claim; the claim just needs to be about something
in doubt.

The wider tool market splits the same way. Props.Cash popularised the L5/L10/L20 hit-rate view and
most of the category copies it. OddsJam and Outlier's paid tiers take the other route: they compare
a book's price against the market consensus and surface the gap. Neither computes what this engine
computes — a calibrated probability from a model of the player. That is this app's actual asset,
and it is being spent on describing near-certainties.

## 4. Why a 91% line cannot pay, even when it is right

Three separate reasons, which compound.

**The margin is worst exactly there.** Player props carry roughly **6–15%** margin against about
**4%** on main markets, because the markets are thin and harder to price. On a short price the
margin is a far larger fraction of the available return: at a true 91%, fair is about 1.10, and a
typical priced-up prop at that end leaves a return in the low single digits against a full loss
when it misses. The margin does not shrink because the event is likely — it just becomes a bigger
share of what is left.

**The line is not where the market is.** Books set a prop line at the **median** — the point where
roughly half the outcomes fall either side — then add the margin and usually a half-point to avoid
a push. A 91% statement is therefore, by construction, not the line anyone is offering. For that
player the offered line sits two or three rungs further up, which is exactly the rung the table in
section 1 shows this app is not displaying.

**It carries almost no information.** "1+ shot at 96%, usually 93%" is a three-point statement
about something the reader already assumed. The log-odds lift on that line is 0.30, which the
ranking treats as real, but the reader does not experience log-odds — they see 96 against 93 and
correctly conclude nothing happened.

## 5. What the evidence says about which markets deserve the weight

This bears on `engine.market_weights`, and it raises a question rather than settling one.

StatsBomb's repeatability work on Premier League strikers found **shot volume the most repeatable**
metric tested (reported as R² ≈ 0.435 for shots per 90), **shots on target second but much weaker**
(reported as a correlation of 0.242, and note the two figures are on different scales so the gap is
directional, not exact), and **scoring percentage effectively random** — the author's conclusion was
that no striker metric was particularly repeatable year to year.

Current weights are `player: sot 1.40, tackles 1.30, passes 1.25, fouls_won 1.20, fouls 1.15,
shots 1.00`.

**Shots on target is weighted highest and is the less repeatable of the two shooting markets.** If
repeatability is what makes a forecast trustworthy, that ordering is backwards. I am not confident
enough to flip it from one study on one league and one position — but it is a clean question for
the walk-forward gate in docs/37, and it is cheap to ask.

No comparable repeatability figures exist in the literature I could reach for tackles, fouls or
cards. Those weights are currently guesses, and should be labelled as such until measured.

## 6. What to change

Four changes, in the order I would do them.

### 6.1 Select the rung where the outcome is in doubt

Replace "the most likely rung inside the band" with "the rung where the statement is a claim".
A rung is worth showing when **both** hold:

- the outcome is genuinely uncertain there — roughly `0.35 ≤ p ≤ 0.75`; and
- the model disagrees with the baseline there — lift above a floor.

Note what this is *not*: it is not "show the 50% rung". A pure 50% forecast says nothing either
("it could go either way"). The informative object is **a confident departure from the usual, at a
rung where the outcome is still open**. Uncertainty is the stage; lift is the performance.

This means `p_usual` has to be computed per rung, not only for the rung that happens to be shown.
The ladder is already stored; the baseline needs to follow it.

### 6.2 Stop multiplying by `p`

In `queries.prominence`, replace the `× p` term with one that peaks where the outcome is open and
falls away at both ends. `4p(1-p)` is the natural choice — normalised Bernoulli variance, "how much
is actually at stake in this sentence". It scores a 60% line at 0.96 and a 96% line at 0.15, a
roughly six-fold swing towards the live rung, and it needs no new setting.

Keep the existing gate: zero lift still scores zero.

### 6.3 Re-open `engine.line_band`

The default `[0.5, 0.985]` exists to let 90%+ lines through (docs/39). If selection targets the
open zone, the headline band should narrow — something like `[0.25, 0.80]` — with near-certainties
still reachable through the full ladder and the Finder, which is where docs/44's original
complaint is properly answered. Make this a setting change, not a code change, so it can be
reverted in one flip.

### 6.4 Treat teams and players differently

Team aggregates are far more predictable than individual returns, so their ladders are steeper and
their low rungs are flatly certain — "9+ shots at 88%" is a description of a football match, not a
forecast. Team markets need a **higher** rung to reach the open zone. The measurements in section 1
bear this out: every team line shown sat at 81–88% while its ladder held a rung near 50% four to
six thresholds further up.

Player markets have the opposite problem — minutes risk means even a good player's ladder tops out
lower — so the open zone arrives sooner and the lineup badge carries more of the meaning.

One band for both is the wrong shape. This probably wants `engine.line_band` split into a team band
and a player band.

## 7. How to know whether this worked

The honest answer is that **this is a presentation question and the walk-forward gate in docs/37
cannot settle it.** That gate measures whether a forecast is more accurate. Nothing here changes
accuracy — the numbers are the same numbers, the ladder is the same ladder. It changes which true
statement gets said out loud.

What can settle it is the reader's own behaviour, which this app already records: lines added to a
combo, players followed, cards opened, return visits. Run it as an A/B on selection with the
existing feed, and read those four. If the open-zone feed is not opened and acted on more than the
near-certain feed, the argument in this document is wrong and the measurement should win.

Until that runs, section 6 is reasoning from market structure and from one afternoon of
measurement on 20 simulated cards. It is a good case. It is not yet a proven one.

## 8. Sources

Read directly:

- The app's own Insights feed and `ladder` payloads (section 1), `engine_bridge.select_lines`,
  `queries.prominence`, `settings_registry.json`.

From search, not read firsthand (statshub.com and its mirror are blocked by this environment's
network policy):

- StatsHub — PropHunter, Prop Screener, free tools and features pages.
- Player-prop margin figures (6–15% against ~4% on main markets) — betting-industry explainers;
  figures vary by source and none publish a method, so treat the range as indicative.
- Line setting at the median, with margin and a half-point added — several prop-strategy sources,
  consistent with each other; none soccer-specific, so the application to shots on target is
  inference.
- Closing line value as the standard measure of bet quality, and its unreliability in thin prop
  markets — betting-industry sources, consistent on the caveat.
- StatsBomb, Premier League strikers and repeatability — shot volume most repeatable, shots on
  target second and weaker, scoring percentage random.

---

# 9. The actual test for "this did not need an engine"

Added after the first draft. Section 1 measured *where on the ladder* the shown rung sits. That was
only half the problem. This is the other half, and it is the one that answers "PSG 9+ shots in a
match doesn't need an engine".

## 9.1 Spread is the diagnostic

For any market rung, compute the **spread**: the standard deviation, across every entity in the
league, of that entity's own base rate at that rung.

Spread says whether the question has an answer. If every team in the league reaches 9+ shots about
83% of the time, no model can tell them apart at that rung — not because the model is weak, but
because the teams genuinely are not different there. The engine is being asked a question with no
answer, and it dutifully returns 88%.

Measured on 358 forecast rows across 12 matches (simulated league, so read the ordering rather
than the absolute values):

| Market rung | League base | **Spread** | |
|---|---|---|---|
| team corners 1.5+ | 89.2% | **0.013** | flat |
| team shots 6.5+ | 88.9% | **0.018** | flat |
| team sot 1.5+ | 86.5% | **0.030** | flat |
| team shots 7.5+ | 86.3% | **0.031** | flat |
| team corners 2.5+ | 83.2% | **0.034** | flat |
| team shots 8.5+ | 82.6% | **0.047** | flat |
| team corners 3.5+ | 73.1% | 0.059 | thin |
| team sot 2.5+ | 77.4% | 0.067 | thin |
| player tackles 1.5+ | 66.2% | 0.083 | real |
| team sot 3.5+ | 66.4% | 0.100 | real |
| player shots 1.5+ | 70.0% | 0.118 | real |
| player shots 2.5+ | 68.2% | 0.124 | real |
| player shots 0.5+ | 75.6% | **0.146** | real |
| team match_goals (any) | — | **0.000** | identical by construction |

**Every flat rung is a team market.** Player rungs run 0.083–0.146; team rungs at the bottom of
their ladders run 0.013–0.047. That is the whole of the complaint, in one column.

Note what this is *not*. It is not "high likelihood is bad". `player shots 0.5+` has a 75.6% league
base and a spread of 0.146 — some players sit at 95%, some near 50%. A 95% shots line for a
specific player can be worth saying, because that player is genuinely unlike the rest. The same
number for a team at the bottom of its ladder cannot be, because the team is not.

## 9.2 Two kinds of information, and you need one of them

A forecast earns its place if it can answer at least one of these:

- **who** — this entity differs from the league. `|p_usual − league_base|`. "This player shoots more
  than most in his role."
- **when** — this fixture differs from the entity's own norm. `|p − p_usual|`. "And this week more
  than he usually does."

If the rung is flat, neither question has an answer and nothing else matters. If the rung has
spread but both gaps are small, the statement is a league fact wearing a forecast's clothes.

## 9.3 Scoring the current feed

Every one of the 20 headline cards, against its own rung's league baseline and spread:

| | |
|---|---|
| **Trivial** — flat rung, or neither *who* nor *when* | **8 of 20** |
| *who* only | 9 of 20 |
| *when* only | 2 of 20 |
| **both** | **1 of 20** |

Eight of twenty cards say nothing a league table could not. Only one card in twenty manages to say
both who is unusual and that today is unusual for them — which is the sentence the whole engine
exists to produce.

## 9.4 What to build

Three things, and the first two are small.

**Store the baseline.** Compute `league_base` and `spread` per `(scope, stat, thr)` per league per
season, on the same run that writes forecasts. It is one aggregation over
`player_match_stats` / `team_match_stats` and it is the input every rule below needs. Nothing can
be filtered on information that is not recorded.

**Gate on spread.** A rung with `spread < 0.05` is not a forecast and should never lead a card or
appear in a feed. Keep it reachable in the full ladder and the Finder — somebody checking "does
this team ever fail to reach 2 corners" deserves an answer — but it is not an insight. On the
measurements above this alone removes the six flattest team rungs.

**Require who or when.** After the spread gate, a headline needs `|p_usual − league_base| ≥ 0.05`
or `|p − p_usual| ≥ 0.05`. Make both floors settings so they can be tuned without a deploy.

Then say which one it is, in the card's own words. "Shoots more than most in his role" is *who*.
"More than he usually manages, against this defence" is *when*. A card that can say both should say
both, and should outrank every card that can only say one.

## 9.5 What this means for the engine itself

The engine is not the thing that is broken. Across 358 rows it calibrated, anchored and banded
exactly as designed. It is being pointed at questions that have no answer, and it answers them
correctly.

So the engine work that would pay is not more features. It is:

1. **Per-rung `p_usual`.** Today the baseline is computed only for the rung that happens to be
   shown. Every rule above needs it for the whole ladder.
2. **`league_base` and `spread` as first-class stored fields**, per the above.
3. **Then, and only then, more features** — and aimed at the markets where spread shows there is
   variance to explain. Chasing accuracy on `team shots 6.5+` is chasing a quantity that does not
   vary.

And one correction to make while there: `engine.market_weights` puts shots on target (1.40) above
shots (1.00), while the repeatability evidence in section 5 and the spread column above both point
the other way — `player shots 0.5+` has the widest spread of any market measured. Worth running
through the docs/37 gate before trusting either ordering.
