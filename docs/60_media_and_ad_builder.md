# 60. Media library and the ad builder

Written 2026-11-08. Two tools under **Marketing**: a place to put files that e-mails and pages can
point at, and a thing that draws finished social images out of the product's own data.

## 1. Media

### What was already there

`site_assets` held owner-uploaded **images** — 512 KB each, 100 of them, PNG/JPEG/GIF/WebP/ICO,
written by `POST /api/admin/site/assets` behind `site.write` and read by anyone at
`GET /api/site/assets/{id}` with a one-year immutable cache. The admin screen for it was called
"Images" and sat under **Website**, because its only reader was Site Studio and the popup editor.

Three things stopped it being the thing an e-mail can use.

**The address was relative.** "Copy address" put `/api/site/assets/ab12…` on the clipboard. Pasted
into e-mail HTML that resolves against nothing, so the image is broken in every client. An e-mail
needs the whole address, scheme and host included. The page now copies
`PUBLIC_BASE_URL + /api/site/assets/{id}`, and the API returns it as `abs_url` so the browser is not
guessing at the host.

**There was no video.** `sniff()` knew five image headers and refused everything else.

**512 KB and one BSON document.** Fine for a logo, useless for video, and a Mongo document cannot
exceed 16 MB whatever we decide.

### Decisions

**Video is stored in chunks, images stay inline.** A video goes to `site_asset_chunks` in 1 MB
pieces with the metadata on the asset row; an image keeps its bytes on the row exactly as before, so
nothing that already works moves. The cap is a setting (`media.max_video_mb`, default 25).

**Upload sends raw bytes, not base64.** The image route posts JSON with a base64 field, which costs
a third more body and made `security_mw.BIG_BODY` necessary. `PUT /api/admin/media/upload?name=…`
takes the file as the body, the way `routes_images.py` already takes a crest. The old JSON route
stays, because Site Studio and the tests use it.

**Serving a video answers Range requests.** Without `Accept-Ranges` a browser cannot seek, and
Safari will not play the file at all. The public route reads only the chunks a range touches.

**Video in e-mail is told the truth.** Gmail, Outlook and Yahoo all strip `<video>`. A video in an
e-mail is a poster image wrapped in a link, and the Media page hands over that snippet ready to
paste rather than letting the owner find out from a support ticket. The direct address is there too,
for a landing page, where it does work.

Uploading and deleting need `site.write`, so staff with that permission and the owner. Reading needs
nothing: that is the point of the address.

## 2. The ad builder

An owner picks a template, a size and what goes in it, and gets a PNG. No account is connected and
nothing is posted — the export is a download and, where the browser offers one, the share sheet.
That was the owner's instruction and it is also the only version worth building: posting needs
per-network tokens, review and a publishing queue, and buys nothing a download does not.

### Drawn in the browser, on a canvas

`ShareCard` in `components/Share.jsx` has drawn the match share image on a `<canvas>` since docs/19,
fetching crests from our own `/api/media` through `getBlob`. The ad builder is that, grown up, and it
is the right choice for three reasons that have nothing to do with taste:

* **There is no server rasteriser.** `requirements.txt` has no Pillow, no cairo, no headless
  browser. Adding one to draw pictures would be the largest new dependency in the project.
* **The fonts are already here.** `public/fonts/` holds the sixteen faces Site Studio offers,
  self-hosted because the CSP has no `font-src`. A canvas uses whatever the document has loaded, so
  `await document.fonts.load(...)` is the whole of the font pipeline.
* **The crests are already fetchable.** Same origin, through the same helper the share card uses, so
  the canvas is never tainted and `toBlob` works.

Export is at the platform's real pixel size — 1080×1080, not a 540 upscale — by laying the template
out in its own coordinates and scaling the context once.

### The templates are claims, not layouts

The temptation is eight arrangements of a logo and a photo. What the product actually has is a
**finding**: this player's number for this market departs from his usual by this much, and here are
the ten games behind it. docs/56 and docs/50 say that departure is the only quantity comparable down
a feed, and docs/redesign/v2 calls the run strip the signature graphic. So each template leads with
one claim the data can carry, and the ingredients the owner listed — badge, crest, photo, position,
last ten, the Finder sentence — attach to whichever claim needs them.

| id | the claim | reads as |
|---|---|---|
| `card` | One forecast, whole: photo, crest, position, market, likelihood, band, tier, usual → forecast, the ten games | The product's own object, blown up |
| `run` | Ten bars and tonight's dashed line, almost no words | A shape, recognised before it is read |
| `table` | The strongest five tonight, with crests | A leaderboard; the densest and most saved |
| `fixture` | Two crests, the league mark, kick-off, the top line underneath | The match-day post |
| `finder` | The Finder question as type, with the answer count and the first names | Nobody else's product *is* a sentence |
| `stat` | One enormous number, one line of context | The record claim |
| `quote` | A headline on the brand gradient | Messaging with no data in it |
| `cover` | Hook plus brand, built to be slide 1 | The start of a carousel |

A **carousel** is `cover` then up to eight `card`/`run`/`table` slides then a closing `quote`,
exported as numbered PNGs in one zip (store-mode, written in `lib/zip.js`, so no dependency).

### The palette and the type come from Site Studio, always

The existing share card hardcodes `#1E2350` and `#7C83FF` — the Midnight palette, replaced two
redesigns ago. It has been posting the wrong brand colours ever since, silently, because a hex
literal cannot go stale loudly. The ad builder therefore reads `theme.colors` off the Site Studio
payload, both modes, and the font from `theme.font_body`, so changing the palette changes the ads.
`Share.jsx` is fixed the same way in this pass.

### Every ad carries the disclaimer

docs/03 requires it on what visitors see, an ad is the most public thing the product makes, and the
share card already prints it. It is drawn on every template, at a size that survives a phone, and
the toggle that removes it does not exist.

### Headlines go through the word rules

The owner types the hook. `textguard.require_clean` scans a saved design the same way it scans a
popup or an e-mail template, and the builder refuses to save what the server would refuse. The words
are in docs/03 and the list is `backend/textguard.py`.
