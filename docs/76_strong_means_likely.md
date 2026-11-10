# 76 — Strong means likely

## The decision

**Strong, Solid and Watch grade the likelihood. Always. There is no second rule.**

| Badge | Needs |
|---|---|
| Strong | p ≥ 90%, and the low end of the likely range ≥ 84% |
| Solid | p ≥ 80%, and the low end ≥ 70% |
| Watch | p ≥ 60% |
| *(none)* | under 60% |

Our own track record can still pull a tier **down** and can never raise one (docs/31). That is
unchanged.

## What was there before, and why it went

There were two rules. With `engine.personal_lines` on, every line sits where that player or club
lands about half the time — so likelihood says the same thing about everybody, and the badge graded
the **departure** from their usual game instead (docs/52):

> Strong — the likely range sits wholly on one side of what they usually do, and the gap is big
> Solid — the gap is worth saying, but the range still touches their usual
> Watch — there is a gap, but a small one

That rule was defensible, measured, and it answered a real problem: `_departure_tier`'s own
docstring records that **84 of 90** personal lines fell below even Watch on likelihood, so grading
them on the number would have left the feed untiered.

It had one cost, and the cost turned out to be bigger than the problem: **"Strong" stopped meaning
"strong chance."** A reader who reads it that way is right and the product was wrong. A 57% card
reading Watch beside a 56% one reading Solid is what that looked like from the outside, and it is
the single most confusing thing a newcomer could meet.

Renaming the badge to its axis was tried — *Well above usual / Above usual / Near usual* — and
rejected. Moving the label to fit the rule is the wrong way round. Run the rule the label promises.

## The three changes

Grading on likelihood is only worth anything if the card shows a line whose likelihood is **worth
grading**. All three of these were needed; any one alone makes things worse.

### 1. `tiering.assign` — one rule

The `is_personal` branch and `_departure_tier` are gone, along with the settings that fed them
(`engine.departure_strong`, `engine.departure_solid`). Deleted rather than left unreachable: a
setting that reaches nothing is the bug class docs/67 is about.

### 2. `engine_bridge` — every rung is graded

A rule used to blank the tier on every rung that was *not* the entity's own line. Under the
departure grading that was right — only the own rung could be asked that question, and a tiered
neighbour let the feed fall back to a near-certain line.

Under likelihood grading it inverts exactly: **the neighbours are where a real likelihood lives.**
The own rung sits at about a half and can never earn a badge. Keeping that rule would have left the
whole feed untiered.

### 3. `queries.group_cards` — the half-way line no longer wins the card

It used to win automatically. Now `lead_score` picks between all the rungs on the configured rule,
and the own line takes its chances with the rest. It is still on the card, one tap away in
`more_lines`.

## The risk this takes on, and what covers it

Both removed rules were guarding against the same thing: **a near-certain, useless line leading a
card** — "1+ shot" for a striker at 97%.

That guard still exists, and it is better than either of them:

- **`engine.feed_max_p`** — a line above it cannot lead while any other line can.
- **`engine.min_span`** (docs/56) — a rung that answers the same against every defence in the league
  is demoted, per rung, on a measured span.

Both run *before* the lead is chosen, both are per rung, and both are measured. The rules removed
here were neither — they were structural proxies for "this line is probably dull".

**Watch the feed for a week after this ships.** If near-certain lines start leading cards, raise
`engine.min_span` and lower `engine.feed_max_p`. Those are the levers; bringing the departure
grading back is not.

## What did not change

- **The departure is still shown**, in words, on its own line of the card: *"8 points above his
  usual 48%"*. It was always the more useful half of what the badge was compressing. It is no longer
  hidden inside a word that means something else.
- **`engine.personal_lines` still works** and still does what it says: each player and club gets a
  line of its own, which stops "PSG 9+ shots" and "1+ shot". It no longer changes what the badge
  means — that was never really its business.
- **Stored tier values**, the palette tokens and every filter are untouched. The published track
  record is *not* untouched, and could not be — see below.

## The published record had to change with it

Dropped from the first draft of this change, and wrong: *"`forecast_outcomes` is untouched, so the
track record stays comparable across the change."*

The record page breaks its figures down by badge — *"on Solid forecasts we said 84%, it happened
82%"*. That sentence is only a sentence if every row in the bucket earned its badge by answering the
same question. Under the two-rule engine, a personal line could be badged Solid while sitting at
about a half, because it was graded on the **departure**. Those rows are already stored, with the
badge, and they carry nothing that says which rule produced it.

So `score_finished` now writes **`tier_rule: "likelihood"`** on every row it stores, and
`track_record` counts a personal row only when it carries that. The reasoning:

- **An ordinary row needs no marker.** It was graded on the number under both engines, and always
  belonged in the bucket.
- **A personal row with the marker belongs too.** One rule grades everything now, so its Solid is
  the same promise as any other Solid. The old code excluded *every* personal row, which from here
  on quietly drops rows that earned their badge honestly.
- **A personal row without the marker is from the old rule, and the absence is the only exact
  test.** The tier cannot be recomputed — `lo` is not stored, and `tiering.assign` needs it — and a
  date cutoff would mean hard-coding a deploy into a query. The filter empties itself as those rows
  age out of `engine.keep_days`.

`tiers_scope` on the response already carried `counted` / `left_out` so the page can say what the
breakdown covers rather than imply it covers everything published; it now counts the right rows.

## Where this is pinned

`selftest_tiering.py`: a personal line 18 points above usual earns no badge at 56% and earns Strong
at 93%; the 57%/56% pair that started this now agrees with itself; the departure grader is gone
rather than unreachable; both settings are out of the registry; and `group_cards` leads with the
line that has a real likelihood while keeping the half-way line one tap away.

Worth noting: **deleting the departure grading broke no existing test.** Nothing covered that path,
which is why the tests above exist now.

`selftest_queries.py`: a Solid bucket holding ordinary rows, same-rule personal rows and legacy
departure-graded personal rows counts the first two and only those, so the stated figure is not
dragged down by lines graded on a different question, and `tiers_scope` reports what was left out.
