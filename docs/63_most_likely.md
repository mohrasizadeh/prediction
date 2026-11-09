# 63 — Most likely

The feed answers *"what differs most from usual"*. A reader an hour before kick-off is asking
something else: *"what is likeliest to happen?"* Answering the second question on a screen built
for the first is how the product came to show rows reading **"56% to take 2 shots"** — true,
careful, and of no use to anyone. This is the screen for the second question.

It is a new route, `/likely`, and it takes the second slot in the nav. Insights keeps its route
and moves to the footer links, so the two can be compared on real traffic before either is
retired. Nothing was deleted to make room.

## What decided the design

Three specialists worked on the mock-up in parallel — conversion/comprehension, visual and
information design, copy — and each rendered and looked at its own version rather than describing
one. Where they disagreed the call is recorded below. Two of them independently wrote **invented
calibration figures** into the design ("lines we published at 80–90% happened 86% of the time,
1,412 scored"). Those numbers are computable in principle and do not exist yet. They are the one
thing on this screen a reader could not check, so they are gated — see *The gated band* below.

## The row

| element | what it is | why |
|---|---|---|
| photo + club badge | `attach_images()` → `/api/media/players/{id}`, provider URL, or `null` | `null` is common until the media cache is warm, so **initials are a first-class state**, not an afterthought |
| position | a chip | three bare letters read as part of the name. The chip is deliberately colourless: colour here is spent on data, not taxonomy |
| line | `1+ shot`, with a **stepper** | see *The ladder* |
| likelihood | one figure, one bar, one caption | see *The number and its range* |
| last 10 | a two-tone strip | see *The line* |
| lineup | dot + word + weight | see *The lineup words* |
| Why | one tap down | the row answers in two seconds; this answers "why should I believe it" |

## The number and its range

The figure, the bar and the range are **one object**: figure, then bar, then the range as the
bar's own caption on the bar's right edge. It was first drawn with the range on the figure's
baseline with a gap between them — two numbers belonging to nothing, which is exactly how it read.

The bar is on a **fixed 50–100 scale on every row**, so `89–96` is a short mark hard right and
`62–82` is a mark three times as long left of centre. That difference is the product's honesty
about its own uncertainty, and it was previously carried by two grey digits nobody compares.

The caption carries the `%`. Under a row reading "2+ shots", a bare `71–86` reads as a count of
shots.

## The line

The dashed rule across the last-10 strip is the threshold. It went through three drawings:

1. **Over the bars.** With a line of 1 and a player who takes 1–3 shots a week it crossed every
   bar near its base and read as a strikethrough. The strip looked damaged.
2. **Behind the bars.** It stopped looking damaged by becoming invisible wherever a bar cleared
   it, which is to say it answered the question by hiding.
3. **The bar is split at it.** `--brand` up to the line, `--tier-strong` above it, with the dashed
   rule behind the bars so it still shows in the gaps and above a bar that fell short. The level
   is now a change of tone that lands at the same height across the strip, and **nothing is drawn
   over a bar at all.**

The split pays for itself: a solid dark bar is a game he got *exactly* what the line asks, a bar
with a bright cap is one he went past. "Does he clear it comfortably or scrape it" was not on the
screen before and costs nothing to show.

The 11th "tonight" column was **removed**. It was a full-height dashed box for a game that has not
been played, so the only thing its height could encode was a forecast of the maximum — which is
not what it meant. A placeholder that encodes a false value is worse than no placeholder.

## The ladder

`select_lines` already stored the whole ladder on every line (`ladder = {thr: p}`) so the Finder
could answer any threshold. The stepper is that ladder made tappable: move the line and the
number, the range, the bar, the dashed rule, the count and the group header all follow.

Two changes were needed.

- **`ladder_band = {thr: [lo, hi]}`.** A screen that lets a reader move the line has to move the
  range with it. Without this it could show a likelihood and would have to invent the spread,
  which is the one thing a page about uncertainty must not do. A rung contributes a band only if
  it has one: `select_lines` is a pure function and its other callers hand it the smallest dict
  that makes sense.
- **The rungs are capped by the data**, at one beyond his best in the last ten (max 6). A fixed
  1..6 on every row prints "6+ shots, 1%" down the page, which is dead ink and makes the control
  feel broken.

Stepping below the floor does not hide the row: it greys and says *"Below the 60% bar — not
listed by default"*, which teaches where the bar is instead of silently dropping things.

## The lineup words

Every word is about **him** and is a fact that can be checked.

| badge | word | |
|---|---|---|
| `confirmed` | Starting | he is in the announced eleven |
| `bench` | On the bench | the eleven is out and he is not in it |
| `likely` | Usually starts | docs/59 made this a record, so it says the record |
| `unsure` + `lineup_why: "record"` | Rotated | a thin start record |
| `unsure` + `lineup_why: "doubt"` | Doubtful | a stated doubt, or a run of missed club matches |
| `null` | No team news yet | an absence of a source, not a doubt about him |
| team line | Club line | corners rows have no lineup question |

`lineup_why` is new. `starter_badge` returned `"unsure"` for both a stated doubt and a thin start
record, so an injured player and a rotated one printed the same word — and the honest word for one
is a lie about the other. `starter_call` now returns `(badge, why)` and `starter_badge` is its
first element, so the rule lives in exactly one place.

A missing record still never reads as a doubt: an unmapped `minutes` key would otherwise badge a
whole league injured.

## The gated band

Rows are grouped by likelihood decade. Each header states what it can state today — how many
lines sit in it. The calibration clause (`· 412 scored · 94% happened`) appears **only** when
`/track-record` reports `ready` and has a bin for that decade, and it is read from
`forecast_outcomes`, never typed. Until then the footer carries the beta line and the count so
far.

This is the most valuable sentence the screen could carry and the one a competitor structurally
cannot write. It is worth nothing at all if it is written before it is true.

## Colour

Five jobs, each measured against its own surface in both modes (3:1 for a graphic, 4.5:1 for
text) before it was used:

| token | job |
|---|---|
| `--brand` | the forecast — the range bar, and the part of a run bar that reached the line |
| `--tier-strong` | the surplus — how far past the line a game went |
| `--accent` | the chosen line — the lit step. **1.20:1 on white**, so it is only ever a fill under `--on-accent` text, never a mark |
| `--down` | stop — a doubtful lineup dot, a match that has kicked off |
| `--lk-rule` | absence — the rail, missed games, blanks |

`--chart5` measures 2.19:1 and is unusable here for the same reason as `--accent`.
`--border-strong` is used for no mark at all: 2.25:1 light, 1.98:1 dark on `surface1`.

Colour is never the only signal. Lineup states differ by dot fill, word and weight; a run bar that
reached the line also differs in height and in where it changes tone.

## Where the filters live

`min_p` and `within_h` are on `insights_feed`, in the **query**. The screen asks for "the next few
hours"; filtering a fixed 200-row pool in the page would silently lose rows past it — the same bug
`/api/insights` already carries a comment about.

`/api/likely` **returns its floor** rather than letting the page retype `engine.watch_min`. The
screen says "nothing here reaches 60%" in its hint line and its empty state, and a floor retyped
in JavaScript is a sentence that goes quietly wrong the first time the setting moves.

At `watch_min` itself the filter is a guarantee, not the mechanism — tiering already refuses to
grade anything below it. `selftest_likely` asserts that explicitly, so it fails loudly if that ever
stops being true and the screen starts showing coin flips.

## Disagreements, and which way they went

- **Hatching the bar when the lineup is unsure** (conversion). Not taken. Every number already
  assumes he plays and the lineup column says how sure that is; folding lineup risk into the
  likelihood bar collapses the two questions the footer exists to keep apart. Its author flagged
  it as their least confident choice.
- **Position tags cut entirely** (conversion) vs **kept, unboxed** (design). Kept, as a chip: it
  costs one small object and the owner has asked for position on a player row before.
- **`89–96%` with the sign on the range** (copy) vs **one sign governing both** (design). Copy's,
  once the range became a standalone caption under the bar rather than a neighbour of the figure.

## What this screen still needs

- The calibration clause, as soon as 300 forecasts are scored.
- A five-second test on the phone render, one question: *"what is the single most likely thing
  tonight, and how sure are they?"* If the second half comes back wrong, the bar has failed and
  the range digits are carrying it alone.
