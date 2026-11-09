# 69 — The waitlist e-mail sequence

The landing page makes one promise, in one sentence: **our top three strong reads every match day
until we launch.** This is the machinery that keeps it, and the decisions are mostly about what it
refuses to do.

Two e-mails. Not a drip campaign, not a nurture sequence — two.

| | when | category |
|---|---|---|
| `waitlist_welcome` | once, the moment the address is confirmed | marketing |
| `waitlist_matchday` | once a day, on days that have football | marketing |

Both are `marketing`, which is not a formality: the only consent behind them is a sign-up form, so
they respect the opt-out, carry the postal address, carry the one-click `List-Unsubscribe`, and
count against `email.daily_send_cap` like anything else. Nothing here is smuggled through as
transactional to dodge those.

## "Every match day" is a promise about the days it does NOT send

A sequence that e-mails daily regardless is a sequence people unsubscribe from in week two, and an
e-mail saying *there is no football today* is worse than silence — it spends an open to deliver
nothing. So the trigger is the content itself: `send_matchday` finds the three strongest forecasts
above `engine.watch_min` kicking off **before local midnight**, and if it cannot find three it
sends nothing and says why. A thin Tuesday is a correct outcome, not a failure.

The window ended as a flat 30 hours in the first draft, and the first render showed why that was
wrong: an e-mail headed *Saturday 14 November* listed a 09:00 kick-off that was on the Sunday. A
time with the wrong day on it is worse than no time, and the reader has no way to spot it. The end
of the local day is both what "today" means and still far enough for a 09:00 send to name a 20:45
kick-off. A send configured for late evening has almost no window and may find nothing — which is
the honest answer, not a bug.

## Where the header graphic comes from

The ad builder already renders the day's cards in the browser, uploads each PNG to the media
library for a public URL, and queues it for Instagram (docs/64). That URL is an ordinary https
address on this install that stays reachable — exactly what an e-mail client needs. So this module
**draws nothing**. One render, two destinations.

It prefers the post whose forecast is one of the three the e-mail is naming, which is what the new
`fkeys` field on a queued post is for. Without it the best available answer would be "whatever was
queued first today", and "the related card" would be a claim rather than a fact. The reader sees
the same card twice, in two places, about the same player.

**A missing graphic is not an error.** The e-mail is three numbers and their reasons; it reads
perfectly as text. A day with no batch queued still goes out, without a picture.

The post's own **caption becomes the image's alt text**. That is not a nicety: most e-mail clients
block remote images until the reader asks for them, so for a good share of opens the alt text *is*
what is on the screen. An empty one would put a blank box at the top of every send. The caption was
written from the words already on the image (`ad_plan._caption`) and has been through textguard
twice, so it describes the picture and carries nothing this product does not publish.

## Raw HTML in a template, deliberately

`emailer.render` escapes every variable, which is right: a template is admin-editable and a name is
data. But the three forecasts are a *table* — escaped, they arrive as visible angle brackets. So
`render` now inserts a variable whose name ends in `_html` raw.

That is safe only because of where the value comes from. The one builder that uses it escapes every
field it reads out of the database first — club names and market labels come from the data feed,
which this app does not author — and nothing admin-typed is ever passed under an `_html` name.
`selftest_waitlist_mail` asserts both halves: the table is not escaped, and `Club "Two" & Co` is.

## E-mail HTML, not web HTML

Tables, inline styles, no class names, no flexbox, no CSS variables. Gmail strips a `<style>` block
on mobile and Outlook renders a `<div>` grid as one column, so the brand colours are written out as
hex in `waitlist_mail.C` and nowhere else. The image carries `width:100%;max-width:512px` and no
pixel width beyond that, because a fixed width is what makes an e-mail scroll sideways on a phone.

Kick-off times are 24-hour, as everywhere else in the product (docs/63).

## The record line, or no line at all

If `track_record` is not `ready`, the paragraph about how we have done **is not in the e-mail**. It
is never a win rate: *"when we said at least 60% likely, we said 88% on average and it happened 86%
of the time, over 1,204 scored forecasts."* Calibration is the honest shape of that answer
(docs/03, docs/68), and a page — or an e-mail — that framed it as a score would be inviting the
reader to read the number as a grade.

## Once a day, from anywhere

`db.waitlist_sends` holds one row per local day, **keyed by the day**, so "have we sent today" is a
primary-key lookup rather than a query over job history, and a send started from the admin screen
counts exactly as much as one started by the job.

Two separate guards, because they answer different questions:

* `due()` — should the job bother? The local hour has arrived and today has no completed send. It
  is what stops `jobs.tick` walking the whole list every five minutes to discover there is nothing
  to do.
* the per-address idempotency key (`wlm-<day>-<hash>`) — the actual guarantee. It is what makes
  **Send now** safe to press twice, and what lets a run that died half way through the list resume
  on the next tick instead of writing to everyone again.

A day whose run reached nobody — the cap was already spent, every address suppressed — is not
"done". `due()` returns true again, so it is retried rather than written off until tomorrow.

## The segment

`waitlist` is its own segment in `emailer.SEGMENTS`, resolving to `newsletter` rows with
`source: "waitlist"` and `status: "confirmed"`. It does **not** include the footer form's
subscribers: they asked for a different thing, and a campaign aimed at the waitlist should not
reach them. The name they gave on the form is used to address the e-mail, and nothing else
(docs/68).

## What the admin sees

The E-mail list screen renders the real body in a sandboxed iframe — today's actual three, today's
actual graphic, the actual subject line — because the one thing the owner needs before switching on
a daily send is to see what it will send. Describing it in prose and hoping is the wrong trade.
`Send now` sits on the top guard rung (a typed phrase), like every other bulk send, and it is only
offered when pressing it would do something — three forecasts found *and* somebody on the list. A
button whose only possible outcome is "nothing sent" is worse than no button.

## Settings

| key | default |
|---|---|
| `waitlist.email_enabled` | `false` |
| `waitlist.email_hour` | `9` |
| `waitlist.email_tz_offset_min` | `0` |

It also needs `email.enabled`, `email.marketing_enabled` and a postal address in
`email.footer_address`. Each missing one is reported by name in the `skipped` reason rather than as
a silent no-op.

## What this does not do

* It does not send Stories or anything to TikTok. That is the posting queue's problem, and docs/64
  says plainly what is and is not possible there.
* It does not hold a provider credential of its own. It goes through `emailer`, which goes through
  the provider chosen in settings, whose key lives encrypted in `provider_keys`.
* It does not invent a record, a sample size, or a fourth forecast to round out a thin day.
