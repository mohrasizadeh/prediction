# 68 — The waitlist page

`/waitlist`, outside the app shell. Someone arriving from a post should meet one page with one
thing to do, not a navigation bar inviting them elsewhere.

## What it leads with

The one claim nobody else in this space can make and this product can **check**: what it said,
against what happened, read live from `/track-record`.

> **We said 86%. It happened 87% of the time.** — across 486 scored forecasts

That is the headline because it is the product. Everything below it is an explanation of how that
number is arrived at.

**If the record is not ready the page says so and leads with the method instead.** It never prints
a figure it cannot stand behind — which would be a strange way to advertise a product whose entire
argument is that it does not do that.

## The record section

One row per likelihood band: what we said, what happened, how many were scored. Then the sentence
that stops a reader misreading it:

> The point is not that the second number is high. It is that the two are **close**. When we say
> 80%, we want it to happen about 80 times in 100 — not more, which would mean we were being timid,
> and not less, which would mean we were overclaiming.

Without that line, a reader takes "87% happened" as a win rate and the page becomes the thing it is
arguing against.

## The offer

Name and e-mail, for *"our three strongest forecasts on every match day, with the reasons and the
range, until we open"*.

The name is optional and is only ever used to address the e-mail. `newsletter.subscribe()` gained
it as an optional argument, kept out of `$setOnInsert` so a reader who signs up again with their
name filled in gets it recorded the second time — and `selftest_screens` pins that a later signup
**without** a name does not wipe one already there.

The waitlist sends `source: "waitlist"`, so the two audiences can be told apart later. Consent is
unchanged and still required: the waitlist does not get a looser rule than the footer form, and the
test asserts it.

## Three things we do that cost us

A section naming the product's own constraints — the range on every forecast, nothing shown under
60%, the misses published. They are real limitations, and stating them is the most persuasive thing
on the page precisely because nobody states limitations in an advert.

## Design

Same tokens, same type system, same rule that colour carries one meaning. No new colours, no
gradients, nothing the rest of the product does not already do. An advert that looks like a
different company is an advert for a different company.

Rendered before it was written, at 900px and at 390px, with no horizontal scroll and no page
errors.

## Measuring it (added 2026-11-13)

**Admin > Waitlist** (Marketing, `analytics.read`) answers whether the page is doing its one job. It
shows visitors, page views, sign-ups and the sign-up rate (each against the period before), how
many are on the list, and who is on the page right now. Below that: visitors and sign-ups per day;
the funnel (visited, read half the page, started the form, signed up); how far people scroll (25,
50, 75, 100%); which sections they reached; and sources and campaigns with visitors, sign-ups, rate
and confirmations. A link builder makes tagged links for each place the owner posts. Report:
`backend/waitlist_stats.py`, route `GET /api/admin/waitlist/analytics?days=`.

**Until this pass the page recorded no visits at all.** The page-view beacon lives in `<Layout>`,
and `/waitlist` sits outside it on purpose. The page now calls `usePageBeacon` itself.

The page sends three small events through the same first-party `/analytics/collect`: `wl_scroll`
(depth 25/50/75/100), `wl_section` (proof/engine/record/costs/close) and `wl_form_start`. Each is
sent at most once per page load and carries one small field and nothing about the person. The
server writes `waitlist_signup` when the form is submitted. That event carries the visit's UTM tags
and referrer, and it is written only for a **new** address: pressing the button twice, or signing up
while already on the list, is one sign-up. The list row keeps the source too (`attrib`, first touch
only), so confirmations can be credited to a source.

What it does not do: no cookies, no third-party script, no IP stored. Do Not Track and Global Privacy
Control drop the events and strip the source from a sign-up. Bots are dropped at collection. Because
the anonymous id changes daily by design, "visitors" over a period is the sum of each day's
visitors, and the screen says so.

**Sources.** A `utm_source` tag wins. Otherwise the referrer is folded into a name (t.co is `x`,
l.instagram.com is `instagram`, any Google domain is `google`), and with neither the visit is
`direct`. Instagram, TikTok and WhatsApp apps usually send no referrer, which is why the screen hands
over tagged links.
