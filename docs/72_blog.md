# 72 — The blog: daily match posts

## What it is for

Organic arrivals and sign-ups. Every other surface in this product serves people who already found
us; this one is aimed at the stranger searching *"Arsenal v Chelsea forecast"* two days before
kick-off.

## The two decisions that shape everything else

### 0. Published the evening BEFORE the match

`plan_day` builds for **tomorrow's** fixtures when no day is given, so a post is prepared today,
reviewed today and published tonight.

Search interest in a fixture peaks in the day or two before kick-off. A post published on the
morning of the match is too late to be crawled and too late to bring anyone in; one published
afterwards has missed the point entirely. The same reasoning, and the same choice, as the ad planner
(`ad_plan.py`: *"the owner posts the night before"*).

A post then **updates in place after the whistle** rather than being replaced — `refresh_settled`,
run on the tick. Same slug, same URL, now carrying what happened. One address covers both jobs: the
preview that earns the visit, and the record that earns the link.

### 1. One post per fixture, not one post per day

A daily round-up called *"Forecasts for 14 November"* holding twelve matches cannot rank for any of
them. The page that answers *"Arsenal v Chelsea forecast"* is a page **about Arsenal v Chelsea** —
one match, one URL, one title. The day is how often posts are generated; the fixture is the unit.

### 2. The post is server-rendered HTML

This is the only page in the product rendered on the server, and the reason is narrow. The app is
client-rendered: a crawler receives `<div id="root"></div>`, and Slack, WhatsApp, X and Facebook
never run JavaScript (docs/71). A page whose entire job is being found by a search engine and
surviving being pasted into a chat cannot be part of that app.

So `blog_render.py` assembles a finished page. It carries **no JavaScript** — not "very little",
none. That makes it fast on a phone, impossible to get wrong in a crawler, and it ends the
Content-Security-Policy argument a scripted page would start: the route ships
`default-src 'none'; script-src 'none'; img-src 'self' https: data:; style-src 'unsafe-inline'`.
(The one `<script type="application/ld+json">` is a *data* block — browsers never execute a script
of a non-JavaScript type — so the rule holds and the structured data still reaches Google.)

The palette comes from Site Studio's compiled theme, the same string the app loads at runtime, so a
post follows the brand without being regenerated. The card markup mirrors the agreed row (docs/61);
the one page a stranger sees first does not get its own visual language.

## Where a post lives, and the ugly part

```
https://forecast.zone/api/blog/arsenal-v-chelsea-2026-11-14
```

Under `/api` because **only `/api` reaches this service** — the platform serves the static app at
every other path, and this page has to come from the server to be worth anything. It works: Google
indexes whatever returns 200 with content, and `/api/` in a path carries no ranking penalty.

It is, however, not a pretty URL for a human to see in a chat. **One rewrite rule from `/blog/*` to
`/api/blog/*` fixes it**, and `blog_render.post_url()` is the single place that would change. Until
then this is the address that works, and it is the only one: it is what goes in `og:url`, in
`rel=canonical` and in the sitemap, so there is never a second URL competing for the same post.

## What a post contains

- The fixture, with crests.
- **Three forecasts: one Strong, one Solid, one lower rung** — enough to be worth reading, not
  enough to replace the product, and it quietly teaches what the tiers mean.
- Each with its percentage, likely range, usual rate, **the last ten games on that line as a bar
  strip** — the same ten numbers and the same drawing rules as the card (`ForecastRow`'s `Run`),
  in CSS rather than JSX because this page runs no script — and then the reasons.

### Evidence before opinion

The "why" under each card is in two parts, in this order:

1. **What a reader can check**, from the strip beside it: *"He reached 3+ in 6 of the last 10
   games"*, the streak if there is one, and how far the line swings between opponents (docs/56) —
   *"this line swings about 24 points depending on the opponent, so the fixture is doing real work
   here"*, or the opposite, *"this line barely moves whoever the opponent is"*. That last one matters:
   a rung that answers the same against every defence in the league is a fact about the player, not
   about this match, and saying so is the difference between a forecast and a table of averages.
2. **The engine's own reasons**, from `core.top_reasons`, which reads the model's feature
   contributions and words them from a fixed vocabulary — *"The opponent gives up more shots to
   players in his position"*, *"The expected game state lifts shots"*. These are the actual drivers,
   not a narrative written around the number afterwards.

Nothing in this module invents a sentence. And reasons that are only about **availability** are
dropped: *"he is in the announced eleven"* answers a different question from the one a post titled
*"why we think this"* is asking, and a reader notices. *"Expected minutes are limited"* stays — that
is a real cause of a lower count.

### One place for the arithmetic

`need_of(thr)` is `floor(thr) + 1` — the same arithmetic as the card's `need()` and as the scoring
rule in `forecast_outcomes` (`reached = actual > thr`). The first build read a 2.0 threshold as
*"2+ shots"* while the evidence line under it said *"reached 3+ in 6 of the last 10"*, so the card
contradicted its own reasons. A reader notices that before they notice anything else on the page.
- A call to action after the forecasts and again at the end, linking to sign-up with
  `?from=blog-mid` / `?from=blog-end` so analytics can tell the two apart.
- Four boxes on what an account gives, and a link to the track record.
- The disclaimer, and a link into the full match in the app.

### A tier is not a quota

Most days have **no Strong forecast at all** — docs/52: the badge grades the *departure* from a
player's usual game, and "no badge" is the commonest honest answer. So `pick_three` fills what it
can and reports what it could not, and the post **says so on the page** rather than hiding it. A
reader who is told learns what the badge means; a reader who is not assumes we had nothing.

A fixture with fewer than two usable forecasts produces **no post**. Generating 380 near-identical
pages is exactly how a site of its own data gets treated as scaled content abuse (docs/71).

## Nothing reaches a reader unreviewed

- Every figure is read off a stored forecast. The module invents no numbers.
- Every published string passes `textguard`. The banned list is CI-enforced for anything an admin
  types (docs/03); copy a machine assembles clears the same bar and is the likelier offender —
  *units*, *picks* and *hit rate* are ordinary football-writing words. A reason carrying one is
  dropped; a whole fixture that cannot be cleaned is skipped.
- A post is born a **draft**. Publishing is a separate admin action, and the copy is re-checked at
  that moment, because an edit is exactly where a banned word gets in.
- The public route answers **404 identically** for a draft, an unpublished post and one that never
  existed. The slugs are guessable by design — two club names and a date — so any other answer would
  leak what is coming.

## Admin → Marketing → Blog

Pick a day, press **Prepare drafts**. Review a post in an iframe of the *real* page (never a
reimplementation in JSX — that is a second renderer waiting to disagree with the published one),
then Publish.

A reviewer may edit the **title, search description and opening paragraph**. Not the numbers. If a
figure is wrong the fix belongs in the engine and the post should be regenerated — an admin editing
a percentage would publish a forecast the product never made.

Re-running generation **replaces a draft** (forecasts are refit every tick) and **never touches a
published post**, whose URL may already be shared and indexed.

The tick prepares drafts every six hours when `blog.auto_generate` is on, and deletes unreviewed
drafts for matches already played after `blog.draft_keep_days`. Published posts are never swept.

## After the whistle

A post for a match already played **says what happened**, because the first build did not and read
in the future tense with no score and no results — the same fault reported on the match page, in a
second place (docs/73).

| | Upcoming | Played |
|---|---|---|
| Title | *Arsenal v Chelsea forecasts, 8 November 2026* | *Arsenal 2–1 Chelsea: how our forecasts did* |
| Fixture strip | `v` | the score, and FT |
| Heading | Three forecasts, and why | What we said, and what happened |
| Each card | the forecast | plus *Happened — 4* or *Did not happen — 0, where 2 were needed* |
| Above the cards | — | *2 of the 3 forecasts in this post came in.* |

The tally is stated plainly whichever way it went. A forecasting site that publishes only its hits
is not publishing a record, and credibility is the one thing a stranger cannot check for themselves.
A player who did not appear reads *"he did not play, so this one was never scored"* — he is left out
of the tally rather than counted a miss, which would be a different claim from the true one.

This is also the differentiator worth naming: everyone else's prediction page becomes a dead wrong
page the moment the whistle goes. These become a record of what we said and what followed, and keep
earning.

## Sharing

A share row sits after the forecasts: X, WhatsApp, Facebook, Reddit, email, and the address printed
as selectable text.

**It uses no JavaScript.** The obvious build is a button calling `navigator.share`, and it would cost
this page the one property that makes it worth having — a script tag means a CSP that allows script,
on the only page in the product a stranger meets first. Plain links to each network's share endpoint
need no script, open the native app on a phone, and work with JS switched off, which is also the
state every crawler reads this page in. `Copy` is the one control here that genuinely cannot work
without script, so the URL is printed instead.

If a native share sheet is wanted later it is one small inline script and a CSP hash — worth doing
deliberately, not by accident.

## Settings

`blog.enabled`, `blog.auto_generate`, `blog.max_per_day`, `blog.cta_title`, `blog.cta_body`,
`blog.cta_button`, `blog.draft_keep_days` — all under **Marketing**.

Turning `blog.enabled` off hides every post from visitors and removes them from the sitemap, without
deleting anything.

## What is deliberately not here

- **A per-match og:image.** The ad builder draws on a canvas *in the browser*, so there is no
  server-side image pipeline to reuse. Posts fall back to the Site Studio `seo.og_image`. A real
  per-match card would need that pipeline moved server-side.
- **Comments, authors, categories, tags.** This is not a CMS. It is a generator with a review step.
- **Editing the forecasts.** See above.
