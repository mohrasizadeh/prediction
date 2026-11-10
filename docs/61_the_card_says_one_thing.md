# 61. The card says one thing

Written 2026-11-08, after the owner said of a five-card screen: *"when I look at these cards, it
won't help me decide anything — it just gives me some %s"*, and *"57% watch, what does it mean, and
then 56% solid. It confuses users."*

Five reviews were run against that screen: three people reading it cold (a casual follower, a
complete newcomer, and someone who has used statistical football tools for six years), a product
manager, and a conversion specialist. Everything below that is a number was measured here, not
asserted by a reviewer.

## 1. The departure was mostly an artefact

This is the finding that reframed the rest, and it is a correctness bug, not a design one.

`engine_bridge.py` applied the record anchor — the blend toward a player's own clear rate over his
last 40 appearances — to `p`, `lo` and `hi`. It did **not** apply it to `p_usual`. So

    edge = p − p_usual = (fixture effect) + (the whole anchor)

and `edge` is the number the departure chip prints and the **only** quantity
`tiering._departure_tier` grades. Measured over 653 player cards before the fix:

| | |
|---|---|
| cards the anchor moved | 78% |
| the anchor's share of the departure shown, median | **84%** |
| anchor larger than the fixture effect | 53% |
| **anchor reversed the sign** — "above his usual" when the fixture said below | **27%** |

The structural test is the one from `scripts/measure/departure_calibration.py`: over a whole round
every club plays once, so the average fixture is average and the mean departure must sit at zero.
It sat at **−1.8 points**. After the fix: **−0.1**.

The fix is that the shift belongs to the **player**, not to the fixture, so everything describing
that player moves by it together. `tiering.anchor_shift()` now returns the log-odds shift and
`shift_one()` applies it, so `p`, `lo`, `hi` **and** `p_usual` all move by the same `d`. In log-odds
the shift then cancels exactly in the difference and what is left is the fixture and nothing else.

This is the same class of error the engine caught and fixed once already — `engine.py` corrected a
bias where "four in ten points of a sot card's 'above his usual' were an artefact". It was fixed in
the engine and reintroduced in the bridge. `selftest_anchor.py` now pins it with the case that would
have caught it: a neutral fixture, where the old code reported **+10.2 points** of departure.

## 2. The badge graded a different quantity from the number beside it

> **Superseded by docs/76.** This section is why that change happened, and the measurements in it
> are the case for it. There is one grading rule now — the tier grades the number, always — so the
> fix recorded below (the badge sitting with the gap it grades) was the half-measure and docs/76 is
> the rest of it. `_departure_tier` no longer exists.

`tiering.py` runs two systems. On an ordinary line the tier grades `p`. On a personal line
(`_departure_tier`, docs/52) it grades the **gap** from that player's usual game. The badge sat
immediately beside the percentage in both cases.

Measured across 200 cards in the production configuration: the correlation between the badge and the
percentage it sits next to is **+0.09**. A Watch card shows a higher percentage than a Solid one in
**46%** of all such comparisons; Solid beats Strong in 52%. The owner's "57% Watch beside 56% Solid"
was not bad luck — it is a coin flip on every screen.

Both readers who met it cold concluded the same thing, independently, and neither guessed at two
systems: *"the app knows something it isn't saying"*. It cost trust in every card, not the odd one.

So the four elements that said one thing in four units — the badge, its note, `USUAL 48%` and the
`+8 pts` pill — are now one sentence, and the badge sits with the gap it actually grades:

    ▲ 8 points above his usual 48% · the likely range still reaches it   ●●○

Nothing is lost. The usual is still printed, the gap is still in points, and the Strong/Solid
distinction — *does the likely range clear their usual, or still reach it* — is said in words rather
than left for a reader to derive by holding `43 to 64` against `48`. That test is the best thing in
the tier system and it was encoded in a dot count.

The badge was **not** deleted. The feed sorts on `CONFIDENT[tier]` first, so without it the column
reads 71, 56, 50, 57, 57 with nothing on screen explaining the order — and both readers complained
about exactly that ordering. The grid now says what it is sorted by.

## 3. The Learn page said this screen was impossible

> **Superseded by docs/76.** `/learn/tiers` describes one rule again, because there is one rule
> again. "Both systems are now described" below was true of this pass only.

`/learn/tiers` read, verbatim: *"Strong: 90% or more. Solid: 80% or more… **That is the whole
rule.**"* No card on the reviewed screen was above 71% and three carried Solid or Strong. A reader
who did the diligent thing and went to check was told, in the product's own voice, that what they
were looking at could not exist. docs/52 overrode docs/58 for personal lines and this page was never
updated. Both systems are now described, and the card says which kind it is.

## 4. The record mixed the two systems

> **Refined by docs/76.** "The tier figures are computed over ordinary lines only" was right while
> two rules existed. With one rule a personal line's Solid is the same promise as any other and
> belongs in the bucket; what does not belong is a row *scored under the old rule*. Rows now carry
> `tier_rule`, and `track_record` counts a personal row only when it has it. The reasoning, and why
> no other test is exact, is in docs/76.

`track_record` bucketed outcomes by the tier **string**. Personal lines sit at about 50% by
construction; an ordinary line had to clear 80% to be Solid. Pooled, "our record on Solid forecasts"
described neither population. Outcomes now carry `is_personal`, the tier figures are computed over
ordinary lines only, and the payload says how many rows that covers.

## 5. The rest of the card

* **The headline rendered at 28px, not 46.** `.v2-fch-p .k-fc-p` (0-2-0) beat the 46px rule below
  it, so the number a reader came for was barely larger than the player's name. Now 36px.
* **The range was the least legible thing on the card** — 11px `--text3` under a 28px `--text`
  number. On four of the five cards reviewed the finding was *smaller than the band around it*,
  which is the most decision-relevant fact on the screen. Now 13px `--text2`.
* **`DEP_BIG` is gone.** A saturated fill at ≥8 points and a hairline at 7 invented a category
  boundary the model does not have, between two adjacent cards, on a threshold no reader can see.
* **The hidden line is named.** `+13 more lines · up to 94%` gave a bigger number with no market and
  no explanation, in the smallest text on the card; 27% of cards lead with something lower than they
  hold, median gap 14 points. Both readers called it burying the good one. The card now says *"Their
  likeliest line here is 2+ shots on target at 94% — much the same against any defence."* Leading on
  prominence is **right** and did not change: a line that barely moves against any defence is a fact
  about the league, not a forecast. The card just has to say so out loud.
* **One legend for the grid, not one per card.** The strip's key was printed under every card,
  twenty times a screen, to explain a graphic that needs explaining once.
* **Cut from the caption:** the streak (the comment beside it already argued it was a counting
  tool's trick, and it was suppressed half the time anyway) and "all at FWD" (the position is in the
  subject line directly above).

## What was not done, and why

The experienced reader asked for the engine's contribution vector on the face of the card — the
additive log-scale terms that are stored on every forecast and reach the card as one adjective. It
is the product's thesis and it is the strongest remaining idea. It is not here because it adds
numbers to a card the owner asked to simplify, and because it should land after this pass is
measured rather than on top of it.

The band's coverage has still never been checked: `forecast_outcomes` stores `p` and `reached` but
not `lo`/`hi`, so "43 to 64" has no measured meaning. That is the next measurement worth running.
