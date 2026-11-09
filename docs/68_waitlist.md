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
