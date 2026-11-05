# v2 — the UX questions, asked before anything is drawn again

The first v2 pass changed the palette, the typeface and one data mark. That is a skin. It did not
ask whether the elements should exist, whether they are in the right place, or whether the page
helps anyone do anything. This document asks those questions and answers them with what is actually
on screen. The redesign follows from the answers, not from taste.

---

## 1. What is this product for, and what is a reader here to do?

The product sells one thing: **"here is something about this match you would not have guessed."**
Everything else is supporting evidence for that sentence.

Readers arrive with one of four jobs, and they are not equally common:

| Job | How often | Where it is served today |
|---|---|---|
| "Anything worth knowing today?" | **most visits** | Today, Insights |
| "I care about this match — what do you have?" | often | Match |
| "I care about this player" | regular | Player |
| "Can I trust you?" | once, early, then rarely | Track record |

**The test every screen must pass: does it answer the reader's question before asking them
anything?** The first job is the common one, and it is the one the current design serves worst.

## 2. Insights — the questions

### Q. How much does a reader have to get past before they see one forecast?

Measured on a 390x844 phone, with the DOM rather than by eye: the first card's top is at
**913px**, against a viewport of **844px**. **The first forecast is below the fold.** The filter
panel alone is **542px** tall. The order is: title, count, date
scroller, a likelihood slider, Tier chips, Market chips, a Player menu, a Club menu, a "League and
more" button, a sort control, a Cards/List toggle. **Eleven controls before one forecast.**

A page whose promise is "we tell you what is worth knowing" opens by asking the reader to configure
a query. That is backwards, and it is the single biggest failure on the screen.

### Q. Is a likelihood floor a filter anyone sets?

It defaults to 0, which means it does nothing, and it occupies a full row with a floating bubble
reading "0%". A control whose default is a no-op should not hold permanent space on the first
screen. It is a refinement for someone who has already looked — it belongs behind "more".

### Q. Why are Tier and Market chips, but Player and Club dropdowns?

Four filters, two control vocabularies, no reason for the split. Chips for the short lists and
native menus for the long ones is defensible in principle, but sitting adjacent and stacked they
read as four unrelated widgets rather than one filter.

### Q. Why are filters in two places?

Five sit in an open panel; League, Position and "lineup confirmed only" sit in a sheet behind
"League and more". Nothing tells a reader which filters are in which place, so finding "Position"
means opening a sheet you had no reason to suspect. **One filter surface, or a clear rule for the
split. Not an arbitrary five and three.**

### Q. Is "20 forecasts · biggest change first" enough orientation?

No. It says how many and in what order, not **what they are about**. A reader thinks in matches
and kick-off times: "the 7pm games". The feed is a flat grid of twenty tiles with no grouping, so
finding everything about one fixture means scanning all twenty.

### Q. Does every card need twelve elements?

Count what repeats on each of twenty cards: crest, name, club, opponent, tier badge, add button,
market, percentage, range, the bar, "Usually 79%", "Hit in 19 of his last 20 games", a sentence of
reasoning, "+2 more lines", "Confirmed starter", kick-off time. **Sixteen.** Twenty cards × sixteen
is three hundred elements competing on one screen, and the parts that differ — who, what line, how
big the claim — are no louder than the parts that are identical on every card.

### Q. Do "Usually 79%", "Hit in 19 of his last 20 games" and the bar say the same thing?

Largely, yes — three statements of "this is normal for him", in three formats, stacked. One of them
should carry it. The bar is the one that can do it without words, now that it draws the claim.

### Q. Is the add-to-combo button as important as it looks?

It is a circled "+" in the top-right corner of every card, the position of highest visual priority
after the name, competing directly with the tier badge. It is a secondary action for a minority of
readers and it is drawn like a primary one.

### Q. Is pagination right for a feed?

"Per page: 25" with page buttons is a table control. A reader scanning for something interesting
wants to keep going, not to administer a result set.

## 3. Today — the questions

### Q. Does a horizontally scrolling carousel belong inside a vertically scrolling page?

"Top 3 for today" is a horizontal carousel in which the second card is visibly clipped at the right
edge. The reader must scroll sideways inside a page that scrolls down, and the clipped card is the
only clue that more exists. Three items do not need a carousel — they need three rows.

### Q. Does "14 insights ›" tell a reader anything?

It is a count, not a value. Fourteen insights about a match says nothing about whether any of them
is worth opening; every match has a similar number. The chip should say the most interesting thing
in that match, or say nothing.

### Q. What is the fixture row actually for?

Time, two clubs, a win/draw/away bar, a count chip. The bar is good and earns its place. But the
row is the main navigation of the whole product and it leads with kick-off time, which is the least
differentiating thing on it.

## 4. Match — the questions

### Q. Does the page lead with the match?

The hero is a thin strip: two crests, kick-off, a result bar, expected goals. On a page about one
fixture, the fixture is the smallest thing on screen.

### Q. Is a three-column grid of twenty-three near-identical tiles a good way to read a match?

No. They are grouped by team, which is right, but the group headers are smaller than the card
titles inside them, and within a group nothing distinguishes the best line from the twentieth. A
reader cannot answer "what is the one thing to know about this match" — the page refuses to rank.

### Q. Why is there a second likelihood slider here?

The same control as Insights, defaulting to 50% instead of 0, with the same problem.

## 5. Navigation — the question nobody asks

Today, Insights, Finder, Explore, Combos, You. **Four of those six are ways to find a forecast.**
A new reader cannot tell Insights from Finder from Explore without trying each. That is an
information-architecture problem, not a visual one, and no amount of restyling fixes it.

It is out of scope for a redesign pass — renaming or merging destinations changes routes, tests and
analytics — but it is the largest navigation issue in the product and it is recorded here so it is
not mistaken for something the redesign addressed.

## 6. What follows from all this

| # | Decision | From |
|---|---|---|
| 1 | **Answer first, filter second.** The feed opens with forecasts. Filters collapse into one compact bar that states the current view in words and opens a single sheet | §2 |
| 2 | **One filter surface.** Everything in one sheet, grouped; nothing split between an open panel and a hidden one | §2 |
| 3 | **Drop the likelihood floor from the default surface** | §2 |
| 4 | **Group the feed by match**, with kick-off and clubs as the header, because that is the unit a reader thinks in | §2 |
| 5 | **Rank inside each match** and show the best few, with the rest one tap away | §2, §4 |
| 6 | **Put the card on a diet.** Who, the line, the claim, the number, one reason, the lineup caveat. The three ways of saying "this is normal for him" collapse into the bar | §2 |
| 7 | **Demote the add button** to a quiet action, and let the tier badge stop competing with it | §2 |
| 8 | **"Show more" instead of pagination** | §2 |
| 9 | **Three rows instead of a carousel** on Today | §3 |
| 10 | **The fixture row leads with the clubs**, and the chip says the best line in that match rather than a count | §3 |
| 11 | **The match hero gets the weight the page is about** | §4 |
| 12 | Navigation overlap **recorded, not fixed** | §5 |
