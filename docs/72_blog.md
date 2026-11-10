# 72 — The blog: daily match posts

## What it is for

Organic arrivals and sign-ups. Every other surface in this product serves people who already found
us; this one is aimed at the stranger searching *"Arsenal v Chelsea forecast"* two days before
kick-off.

## The two decisions that shape everything else

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
- Each with its percentage, likely range, usual rate, and **the engine's own reasons** — the same
  list the match page shows. There is no prose generator inventing a rationale.
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
