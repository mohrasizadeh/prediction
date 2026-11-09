# 67 — Screens: switching pages on and off

## What was wrong

The `features.*` settings had been in the registry since the beginning. **Nothing read them.** A
search across the whole backend finds `features.billing`, `features.maintenance` and nothing else;
`public_config` never sent them to the browser, and no component asked.

So `features.insights = false` did nothing at all. The nav kept the item, the route kept answering,
and the owner — looking at a Settings screen that said the page was off — believed it was. **A
switch that hides nothing is worse than no switch**, because it converts a question into a wrong
answer.

## What it is now

`public_config` sends every `features.*` flag, prefix stripped. `lib/features.js` holds **one map**
from path to flag, and the navigation, the footer and the router all read it, so they cannot
disagree. Hiding a page from the menu while its URL still answers is not hiding it.

Four pages had no flag at all and so could not be hidden: **Most likely, Combos, Compare,
Explore**. They have one now.

Two deliberate choices in `pageOn`:

* **A page with no entry is always on.** Today, a match, a player, a club, pricing, the account and
  the legal pages are the product, not features of it.
* **Off only when explicitly off.** An unknown flag, a config that has not loaded, or a failed load
  all leave a page ON. A visitor seeing a page the owner meant to hide is a smaller failure than a
  blank site because one request did not land.

A switched-off page redirects to home rather than 404ing: someone following an old link should land
somewhere useful, not be told their address was wrong.

## The admin screen

**Screens**, under System — not *Pages*, which is already the CMS, and two menu items with one name
is a trap for whoever wants the other one. `selftest_screens` asserts they stay distinct by id,
label and route.

It is the same settings the Settings screen can edit, as a short list of switches with the page
each one governs named beside it. Settings is a search box over 270 keys; deciding what a visitor
sees should not require knowing what a key is called. Three groups: the main screens, secondary
screens, and parts-of-a-screen.

Flipping one reloads the public config immediately, so the effect is visible without a refresh.

## Not a security boundary

This hides pages from visitors. It does **not** close the API behind them: `/api/insights` still
answers when Insights is switched off. That is the right scope for a product decision — but if a
page is ever hidden for a reason that matters, it needs a guard on the endpoint too, and this file
is not that.

## For the MVP

Suggested off at launch: `insights` (Most likely replaces it — two ranked feeds is one more than
anyone wants), `referees`, `leaderboards`, `compare`. Already off: `live`, `alerts`, `billing`.

Keep but out of the main navigation: Finder and Combos. Both work; neither explains the product to
someone arriving from a social post.
