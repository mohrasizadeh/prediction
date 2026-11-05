# v2 — every screen, questioned

A pass over the whole product with the frontend-design skill and Apple's HIG foundations applied
together, and with the tension between them stated rather than hidden (§0).

**How to read the verdicts.** "Verified" means I looked at the rendered screenshot at that width
and scheme. "Inferred" means I read the markup but did not review the render. The distinction is
kept because an inventory that hides it invites the reader to trust all of it equally.

---

## 0. The tension between the two sets of guidance, stated up front

Apple's HIG and the frontend-design brief pull in opposite directions on one axis, and pretending
otherwise would produce incoherent work.

| | HIG says | The design brief says |
|---|---|---|
| Colour | prefer system semantic colours | do not ship the palette every product in the category ships |
| Type | SF Pro, the platform font | a default stack is an invisible choice |
| Form | match platform conventions | be unmistakable for anyone else |

**The resolution used throughout: HIG's *principles* are binding; HIG's *appearance* is not.**

Binding, and applied everywhere: content over chrome, 44px targets, measured contrast in both
modes, semantic tokens rather than hard-coded values, reduced-motion honoured, every interactive
element labelled, motion that explains a change. These are correctness, not taste.

Not binding: iOS blue, SF Pro, capsule buttons, Apple's greys. This product is a web app read by
people who are not inside Apple's ecosystem while they use it, and looking like a stock iOS app is
the thing the brief exists to prevent. The previous pass over this product *did* adopt the Apple
appearance, which is exactly why it had no identity of its own.

## 1. Findings, by screen

### Insights — **verified** (both schemes, both widths)
Done earlier this pass: first forecast moved from 913px to 476px, filters collapsed into one
sentence, feed grouped by fixture. Remaining, not done: the day scroller is 8 chips tall on a phone
before the sentence; it could collapse to "Today" with a date picker.

### Today — **verified**
Carousel replaced by rows. Remaining: `insight_count` chips still say "14 insights", a count rather
than a value. Every fixture has a similar count, so it never helps a reader choose. **Suggestion:
say the best line in that match, or drop the chip.** Not done: needs an API field the row does not
currently carry.

### Match — **verified**
Hero given weight, group headings outrank their cards. Remaining: the likelihood slider is the
second copy of a control whose twin on Insights was already removed from the main surface.

### Player — **verified**
Two boxes of the same ten games merged into one; the strip became the run graph. Good.

### Track record — **verified**
Now has a visible title and display-size headline. **Caveat: the headline has never been seen with
data** — the demo has 0 scored forecasts, so the bold treatment is unproven against real text.

### League — **verified, and two faults fixed here**
1. **"Next round referees" rendered six cards each reading "Referee not named yet"** — roughly
   600px of page to say one thing six times. Now one sentence until a referee is actually named.
2. **"Overview" and "Fixtures" were the same fixtures.** Overview was next-up plus referees;
   Fixtures was the same list with a next/past switch. Overview is gone and Fixtures absorbs the
   referees, which belong to a round. Five tabs became four.

Still open: the league's fixture rows are bare — time, two clubs, "v" — while the *same fixture* on
Today carries a win/draw/away bar and a forecast chip. **The same object is rendered two ways in
two places and the weaker one is here.** Fixing it means sharing one row component; not done in
this pass because `MatchRow` and Today's `Row` take different shapes.

### Compare — **verified, and fixed here**
It opened as two empty search boxes, a toggle, and an empty state whose advice was *to go to a
different page*. A tool that demands two decisions before showing anything breaks "answer first"
harder than anywhere else in the product. **It now seeds both sides from the next fixture**, so it
opens with a real comparison — radar, what stands out, per-game bars — that a reader can change.

Still true: Compare is also reachable as "Compare with…" from a club page, which is where the
action makes most sense. If usage shows the destination is unused, the page should become that
action only. **That is a question for analytics, not for me.**

### Team — **verified**
Six tabs became three.

### Explore — **verified**
"Tools" removed (all six links are in the footer), search honestly relabelled. What remains is the
league browser.

### Combos and You (Following) — **verified, signed out**
Both show a sign-up wall and nothing else. **Two of the six primary destinations are dead ends for
a signed-out reader**, which is most first-time traffic, and the e-mail block sits underneath, so
the page is two conversion asks stacked. **Suggestion: for signed-out readers, show what the
feature produces** — a sample combo, a sample followed club — rather than only asking. Not done:
needs content decisions and sample data.

### Finder — **verified**
The query sentence is the best interaction in the product. Its clauses should move into the
Insights sentence (CONSOLIDATION §2); blocked on the entitlement rule.

### Referees, Learn, Live, Welcome, sign-in, sign-up, legal, search, 404 — **inferred only**
The system (ground, type, controls, tables, empty states) reaches them through the shared
stylesheet, and the sweep captured them without error, but I have not reviewed each render. **Live
has never been rendered at all** in any pass, because the demo data contains no live fixture
(docs/57 §7). I am not going to claim these are finished.

### Overlays and admin — **not reviewed this pass**
The forecast sheet, quick view, filter sheet, lock sheet and visitor popups are not routes, so the
sweep does not reach them. The admin's 33 modules are untouched by v2 beyond the shared tokens.

## 2. The three patterns behind most of the faults

Worth naming, because they predict where the next fault will be.

1. **A control asking before the page answers.** Insights' filter panel, Compare's two empty
   boxes, Quick view's five stacked rows, the match page's slider. Every one of them put a
   decision in front of the content.
2. **One thing said several ways.** "Usually 79%" with "Hit in 19 of his last 20" with the bar;
   two boxes of the same ten games; Overview and Fixtures; Squad and Squad grid; Explore's Tools
   and the footer.
3. **A count standing in for a value.** "14 insights", "Referee not named yet" six times, "20
   forecasts". A number that is similar on every row never helps anyone choose.

## 3. On "pixel perfect"

Not claimed. The product has 37 public screen routes, 6 account sections, 5 match tabs, 6 overlays
and 33 admin modules, in two colour schemes at two widths. This pass has reviewed and reworked the
screens that carry the product's argument and has applied one system to the rest. The honest state
is: **the spine is designed; the long tail is consistent but unexamined**, and §1 says exactly
which is which.
