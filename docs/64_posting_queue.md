# 64 — The posting queue

The ad builder makes twenty ads for tomorrow. This is what puts them out.

**The app owns the schedule; something else does the last hop.** That split is the whole design,
and it was the owner's idea: they already had a webhook endpoint screen in the admin.

## Why not post to Instagram directly

Publishing through Meta's own API needs an app that has passed App Review for
`instagram_business_content_publish`, and it needs this app to hold a long-lived Meta token and
refresh it forever. The first is weeks of waiting on someone else. The second puts a credential
that can post as the owner inside a repository that has already had credentials committed to its
history.

Routing the last hop through an automation tool the owner already uses removes both: **they** are
the reviewed app, and the token stays with them. `integrations.py` already sends signed, retried,
SSRF-checked webhooks with a delivery log and an admin UI, so the work was a queue and an event —
not a connector.

## What that costs, stated up front

| | |
|---|---|
| **Stories** | Not possible. Zapier's Instagram for Business app has *Publish Photo(s)* (single or carousel) and *Publish Video* (which posts as a Reel). There is no Stories action, and Meta's own support for Stories publishing is disputed between sources. |
| **TikTok** | No native posting action. Reaching it means a second tool inside the Zap, or TikTok's own Content Posting API — which keeps posts private until TikTok audits the app. |
| **The account** | Must still be an Instagram professional account with rights on a linked Facebook Page. That prerequisite is Meta's and no tool removes it. |
| **Reels** | The builder draws stills. A Reel is video, so it needs a canvas→frames→ffmpeg leg that does not exist yet. |

`KINDS` deliberately has no `"story"`. Putting one there without a publisher that can honour it
would be a control on the screen that silently never fires.

## The states, and why `sent` is not `posted`

    draft ──approve──▶ approved ──the job──▶ sent ──callback──▶ posted
      ▲                                        │
      └────────────────failed ◀────────────────┘

A post is marked **sent** the moment it is handed to the outbox, **not** when it is published —
the outbox may still be retrying on its 1m / 5m / 30m / 2h / 12h backoff. **posted** only ever
comes back from the callback. That distinction is the whole value of the screen when something has
gone wrong: "we asked" and "it is live" are different facts, and a queue that conflates them is a
queue you cannot trust at 19:45.

Every delivery carries a one-time `callback_token` that only that one delivery ever held, so the
tool can report the permalink or the error without this app trusting anything else about the
request. The callback lives under `/api/webhooks/`, which `security_mw` already exempts from the
browser-origin check and the write rate limiter — correct for a server-to-server POST with no
cookie, and better than widening those lists for a new prefix.

The callback parser is deliberately forgiving. The person wiring this is mapping fields by hand in
somebody else's UI: `ok` may arrive as a boolean or the string `"false"`, the permalink under any
of three names, and anything in `error` means failure whatever `ok` says. A callback rejected on a
technicality leaves the screen saying "sent" forever.

## Two rules enforced at the door

**Captions go through `textguard` before a post can be queued.** The builder writes captions from
templates and a planner, so nobody reads every one — this is the single place a generated caption
could carry a word this product does not publish all the way to the public.

**Media must be a public `https` URL.** Meta *fetches* the file; it is never uploaded through the
Zap. A relative path, a localhost address or a link that expires before the scheduled time all
fail at the far end, hours later, where nobody is watching. They fail at `queue()` instead.

## One thing that fails loudly on purpose

An approved post whose time has come with **nothing subscribed to `post.due`** is marked `failed`,
not left approved. Left approved it would fire the moment an endpoint was added — which could be
hours later, about a match that has already finished.

## Where the base URL comes from

`site_studio.base_url()` reads `PUBLIC_BASE_URL`, and `asset_abs_url` now goes through it too.
Everything that has to reach back in — an image in an e-mail, a file Instagram fetches, a callback
an automation tool posts to — has to agree about that address, and a second copy is a second thing
to get wrong on the day the domain changes.

## Still to build

* The admin screen: a calendar over the queue, and the step that renders tomorrow's batch in the
  browser and uploads the PNGs to the media library. `ad_plan` says it plainly — *"the planner
  decides what each ad says; the browser still draws it"* — and a scheduler firing at 09:00 has no
  browser, so the bytes have to exist before the schedule does.
* Video, if Reels are wanted.
* TikTok, if the audit is worth it.
