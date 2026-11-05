# v2 — which screens should exist at all

The audit asked whether elements were in the right place. This asks the harder question: **should
this section, or this whole page, exist?** Nine public destinations are examined. Three should
merge, one should lose half its content, and the rest earn their place.

---

## 1. The test

A destination earns its place if it answers a question **no other destination answers**, and a
reader can tell from its name which question that is. Two destinations that answer the same
question with different controls are not two features. They are one feature and a missing
decision.

## 2. Finder and Insights — yes, merge, and here is how

### What each one is

| | Insights | Finder |
|---|---|---|
| Who chooses | **we do** — the engine ranks what is worth reading | **the reader does** |
| The question | "anything worth knowing?" | "show me players with 2+ shots in 6 of their last 10" |
| The controls | a filter sheet: market, tier, player, club, league, position, venue, likelihood floor | **one sentence in plain English, every underlined word editable** |
| What comes back | forecast cards | forecast cards |

**They return the same object through two unrelated control systems.** That is the definition of
one feature with a missing decision.

### The asymmetry that decides it

The Finder's control is *better*. A sentence —

> Players with **2+ shots** in **6 of the last 10** games, **home or away**, **any position**, in
> **pick a league**, playing **today**

— states the entire query in words, in place, with no hidden state. Insights' filter sheet states
its query as a number on a button ("Filters 3"), and a reader has to open a modal to find out what
those three are.

So the merge is not "put two pages in tabs". It is:

> **The Finder's sentence becomes how Insights is filtered, and the filter sheet disappears.**

### What it looks like

```
Insights

Showing  all markets  for  every player  at  every club ,  any day ,
biggest change  first.                                      More filters

── Team 4 v Team 11 · Thu 19:00 ────────────────────────
   card   card   card
```

Every underlined token opens its own chooser. The feed stays grouped by match. Finder's unique
clauses — "in 6 of the last 10 games", "N in a row" — become **additional tokens in the same
sentence**, so the historical query stops being a separate page and becomes a way of narrowing
the feed.

### Why this is right and not just tidy

1. The audit found the orientation line said how many and in what order but never **what they are
   about**. A sentence is exactly that, and it replaces a line that was already there doing less.
2. It removes a modal. Filter state becomes legible without opening anything.
3. It puts the product's best interaction on its most-visited page instead of its least.
4. It collapses two of the four "find a forecast" destinations, which is the navigation problem
   the earlier audit recorded and declined to fix.

### What has to be decided first, and it is not a design question

- **Entitlements.** The Finder is capped (three free searches a day); Insights is not. Merged,
  something has to decide when editing a token counts as a "search". The honest rule: it counts
  only when a clause the Finder uniquely offers is used — the historical ones. **This needs the
  owner's call, not a designer's.**
- **The route.** `/finder` is in the footer, in analytics and in readers' bookmarks. It should
  redirect to `/insights` carrying its query, not 404.

**Built in this pass:** the sentence, on Insights, replacing the filter bar for the main filters.
**Not built:** moving the historical clauses across, and the entitlement rule. Those are the two
parts that need a product decision first.

## 3. Explore — half of it should go

Explore is four things:

| Section | Verdict |
|---|---|
| A search box, "Find a league, team or player" | **Remove.** The header carries a global search on every page, with the same placeholder |
| "Your teams" | Keep. It is the only place the clubs you follow appear as a jumping-off point |
| The league grid, each tile saying what is next | **Keep — this is the page.** It is the only thing here that exists nowhere else |
| "Tools": Compare, Track record, Learn, Referees, Live, Plans | **Remove.** All six are in the footer of every page. Verified, not assumed |

So Explore is a league browser wearing a navigation menu. Strip the duplicated search and the
duplicated link list, and what is left is a good page that `/leagues` and `/teams` are also trying
to be.

**Decision: Explore is the league browser. `/leagues` and `/teams` point at it.** Three routes, one
screen, no reader ever wondering which of them they wanted.

## 4. The rest

| Page | Verdict | Why |
|---|---|---|
| **Today** | Keep | The only day-shaped view. It answers "what is on" |
| **Match** | Keep | The only fixture-shaped view |
| **Player** | Keep | Already consolidated this pass: two boxes of the same ten games became one |
| **Track record** | Keep | Answers "can I trust you". Nothing else does, and it is the page the subscription rests on |
| **Combos** | Keep, but it is a **saved-items** page, not a discovery one. It belongs beside "You", not among the four ways to find a forecast |
| **Following** | Keep | Same family as Combos: your stuff |
| **Compare** | **Weakest case.** Two clubs side by side, which the Team page nearly does. Not merged here because it needs a look at whether anyone uses it — a question for analytics, not for me |
| **Referees** | Keep | A real dimension of the data with nowhere else to live |
| **Learn** | Keep | Explains the method. Load-bearing for trust |
| **Live** | Keep, **unreviewed** | Still never rendered: the demo has no live fixture (docs/57 §7) |

## 5. What this does to the navigation

Before: Today, Insights, Finder, Combos, Explore, You — **four of six are ways to find a forecast.**

After: Today, Insights (with the Finder inside it), Explore (the league browser), Combos and
Following (your saved things), You. **Two ways to find a forecast, and they differ by a question a
reader can actually answer**: "what is on today" or "what is worth reading".
