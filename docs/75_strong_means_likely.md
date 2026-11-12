# 75 — Strong means likely, and the titles carry the search

> **Superseded in part, 2026-11-12.** This document's FIRST half — that the badge grades the
> likelihood except when `engine.personal_lines` is on, where it grades the departure — was replaced
> by **docs/76, "Strong means likely: one rule, always"**: the badge grades the likelihood in every
> case, and the departure is written out in words on the card instead. Where the two disagree,
> docs/76 wins; `tiering.py`, `blog_render.py`, `Learn.jsx` and `lib/copy.js` all follow it.
>
> The SECOND half — the page titles carrying the search — is current and is what this branch was
> merged for.

Two changes, one branch. Neither adds a feature; both fix something that was quietly costing us.

---

## Part 1 — The badge says Strong, and Strong means likely

### The complaint

A 57% card reads **Watch** beside a 56% one reading **Solid**. A reader concludes the product is
broken.

### Two ways out, and why the second one won

The badge *can* grade two different things, and which one it uses depends on a setting:

| `engine.personal_lines` | What the badge grades | Thresholds |
|---|---|---|
| **off** (the shipped default) | the **likelihood** | Strong ≥ 90% (low end ≥ 84%), Solid ≥ 80% (≥ 70%), Watch ≥ 60% |
| **on** | the **departure** from that player's usual game | `engine.departure_strong` 0.12, `departure_solid` 0.06 |

With personal lines on, every line sits where the player lands about half the time, so likelihood
says the same thing about everybody and the badge grades the gap instead (docs/52). That is where
57%-Watch-beside-56%-Solid comes from. It is not a bug; it is the second rule, doing its job.

**First attempt:** rename the badge to its axis — *Well above usual / Above usual / Near usual*.
Built, measured and rejected.

**The owner's answer, which is better:** keep Strong / Solid / Watch and keep the grading those
words already describe. Don't move the label to match the rule — run the rule the label already
promises. A reader who sees "Strong" and thinks "very likely" should be right.

### What that means in practice

**No code change.** The likelihood grading is already the default and already wired. The badge means
what it says whenever `engine.personal_lines` is **off**.

This install has it **on** — visible in a match-page screenshot: Monza *Strong* at 66%, and the note
*"the likely range still reaches it"*, which only `_departure_tier` writes. So the one change that
makes the badge mean likelihood here is **turning that setting off**, in Admin → Settings → Engine.

### The cost of turning it off, stated

`engine.personal_lines`' own help says what it was for:

> Stops "PSG 9+ shots" and "1+ shot" — lines that are true for nearly everyone and so say nothing.

Turn it off and league-wide rungs come back, so some cards will lead with a line that is very likely
and uninteresting. **That risk is now covered better elsewhere than it was when personal lines were
added**: `is_trivial` / `engine.min_span` (docs/56) demotes any rung that answers the same against
every defence in the league, per rung, with a measured span. It targets the same failure more
precisely and it postdates personal lines.

So the recommendation is: **turn personal lines off, keep the triviality guard on, and watch the
feed for a week.** If uninteresting lines start leading cards, raise `engine.min_span` before
reaching for personal lines again.

### If you keep personal lines on

Then the badge cannot mean likelihood, and the honest options are to leave the words describing the
gap (where they mislead) or rename them (which was rejected). There is one measured number worth
knowing before choosing that path, from `_departure_tier`'s own docstring:

> on the measured feed **84 of 90** personal lines fell below even Watch

That is why the departure rule exists. Grading personal lines on likelihood would leave almost every
card unbadged, which would empty the Insights feed, the waitlist e-mail and the ad planner — all
three select on `Strong` and `Solid`.

### What this branch still does for the badge

- The blog's per-badge explanation now **follows the rule actually in force** (`_tier_help`): a
  likelihood sentence by default, the gap sentence when personal lines are on. Previously it printed
  the gap sentence either way, so the badge and its own explanation could disagree — the exact fault
  this exercise was about.
- The Learn article leads with the likelihood rule, because that is the default, and describes the
  departure rule as the exception it is.
- `tiering.TIER_LABEL`, `lib/copy.js` and the ad canvas still share one label map, pinned to each
  other by `selftest_blog`, so a future rename cannot land in two of the three.

## Part 2 — The titles carry the search

### What the copy rules actually forbid

Checked against the regex rather than from memory. Only the **transaction** words are banned:

| Allowed | Banned |
|---|---|
| prediction, predictions, forecast, tips, stats, captain, differential, returns, projection, analysis, preview, form, record | odds, picks, props, bet/betting, accumulator, parlay, tipster, units, hit rate, stakes, lock, banker, punt |

**`{team} vs {team} prediction` — the highest-volume query shape in football — is fully available.**
We had been avoiding a word nothing forbids.

### What changed

| Page | Before | After |
|---|---|---|
| Blog, pre-match | *Arsenal v Chelsea forecasts, 11 November 2026* | **Arsenal vs Chelsea prediction, stats and team news** |
| Blog, settled | *Arsenal 2–1 Chelsea: how our forecasts did* | **Arsenal 2–1 Chelsea: stats and how our predictions did** |
| Player | *Bukayo Saka* | **Bukayo Saka stats, shots per game and what we expect next** |
| Team | *Arsenal* | **Arsenal stats, shots and cards per game** |
| Referee | *Michael Oliver* | **Michael Oliver referee stats: cards per game** |
| Referees | *Referees* | **Referee stats: cards per game** |

"vs", not "v" — people type "vs". *Forecast* is our word for the thing; *prediction* is the word
someone uses to look for it, and **a title that doesn't contain the search is a page that doesn't
answer it.**

The player, team and referee pages were bare names. A page titled *"Bukayo Saka"* competes with
every page on the internet that mentions him and answers none of the questions people type. These
pages already hold per-game history and a forward-looking number — the titles now say so.

Referee pages are the cheapest win in the product: the data is there, the competition is nil.

### `_fit()` — titles that fit and still read

Rendering the long names found a real bug: a hard `title[:70]` produced

> *Brighton & Hove Albion 0–0 Wolverhampton Wanderers: how our prediction*

— cut mid-phrase, in a search result, on two of the longest club names in the league. Descriptions
had the same fault (*"…11 Novemb"*).

`_fit(limit, *candidates)` takes candidates longest to shortest, returns the first that fits, and
only ever trims at a word boundary as a last resort. The bare fixture is the floor, so both clubs
are always named.

---

## What is deliberately not in this branch

- **The FPL layer and the Captain Picker.** Those are builds, not tweaks, and they need data and
  product decisions this branch does not have. docs/74 §8 sequences them.
- **Social and paid-channel work.** Not code.
- **Any change to how a tier is computed.** The grading is unchanged. This branch argues about words.
