# 73 — After the whistle

Four places in shipped code point at this document (`queries.py`, `blog.py`, `ForecastRow.jsx`). It
covers one rule, applied in three places, each of which was reported as a bug before it was fixed.

## The rule

**A forecast about a match that has been played must say what happened.**

Not "stop showing the forecast" — the forecast is the valuable part. Say what we said, and then say
what followed. The data to do it has existed since `score_finished` first ran; what was missing was
anywhere that read it per row.

## Why it kept being a bug

The product was built front-to-back for matches in the future. Every surface took "a forecast" to
mean "a thing that has not happened yet", so each one printed a kick-off time, a likelihood, and
nothing else — and each one went on doing it after the whistle. It read as broken in three separate
places before anyone traced it to one assumption.

| Surface | What it did | What it does |
|---|---|---|
| Match page row | Showed the kick-off time and no result | **FT**, plus Happened / Did not happen with the number |
| Blog post | *"Arsenal meet Chelsea on 8 November"*, future tense, no score | Score in the title, results per card, the tally |
| Live tracking | `ForecastRow` took `track` as a prop and never rendered it | Draws the live count, then the settled result |

## What is shown

`forecast_outcomes` carries `reached` **and** `actual`. Both are used, because *"Did not happen"* and
*"Did not happen — 2, where 3 were needed"* are different amounts of information and we hold the
second. A near miss and a nowhere-near miss are not the same evidence about a forecast, and flattening
them is a small dishonesty that compounds across a page.

A player who did not appear reads **"he did not play, so this one was never scored"**. He is left out
of any tally rather than counted a miss — counting him would be a different claim from the true one,
and it is the claim that flatters us.

The result belongs to the rung it was scored on. Stepping the ladder from 2+ to 3+ clears it, for the
same reason the departure-from-usual line only shows on the rung it describes: the answer to one
question is not the answer to another.

## The tally is stated either way

A settled blog post leads its forecasts with *"2 of the 3 forecasts in this post came in."*

A forecasting site that publishes only its hits is not publishing a record. Credibility is the one
thing a stranger cannot check for themselves, and the only way to earn it is to be visibly willing to
lose. This is the same reason the Track Record page counts the ones that were not reached.

## Why it is worth the work

Every other forecast page on the internet becomes a dead wrong page the moment the whistle goes. Ours
becomes a record of what we said and what followed, at the same URL — which is the one thing in the
product that earns a link rather than a visit (docs/72).

## One number, one place

`need_of(thr) = floor(thr) + 1` — the same arithmetic as the card's `need()` and as the scoring rule
in `forecast_outcomes` (`reached = actual > thr`).

Getting this wrong by one is not a rounding nicety. The first build of the blog card read a 2.0
threshold as *"2+ shots"* while the evidence line beneath it said *"reached 3+ in 6 of the last 10"* —
the card contradicting its own reasons, which is the first thing a reader notices and the last thing
they forget.
