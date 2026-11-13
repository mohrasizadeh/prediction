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

## 3. Twenty ads waiting for you (added 2026-11-08)

The owner posts the night before, so the builder opens on **Post tomorrow**: a batch built for the
next day's fixtures, because a post needs the evening and the morning to earn its reach.
`backend/ad_plan.py` decides what each ad says; the browser still draws it.

### The date, not "tonight"

Every kicker is the fixture's date — `SUN 9 NOV`. An ad posted the night before is read the next
morning, so "tonight" is already wrong by the time anyone sees it, and wrong again for every reader
in another time zone.

### Variety is the actual problem

Twenty ads pulled naively off the feed are twenty forwards with a shots line, because that is what
the feed ranks highest, and an account that posts that looks like one post twenty times. So the
plan spends slots rather than taking a top-twenty:

* no player twice; at most two ads per club
* leagues and markets round-robin, so on-target, tackles and corners each get their turn and a
  smaller league is not crowded out by the richest one
* templates and sizes rotate, light and dark alternate
* **the famous go first inside those constraints**, because a name a reader knows is what earns the
  click. Fame is measured, not listed: season goals, assists, shots and minutes for a player, season
  goals and shots for a club, normalised per league. A hand-kept list of big clubs goes stale the
  first time somebody is promoted.

The recipe is five cards, four runs, two tables, two fixtures, two club-stat ads, two record ads,
two questions and one ask, scaled to the number requested (`ads.daily_count`, default 20). A slot
that cannot be filled — no record yet, no club stats — is topped up with another forecast, because
nineteen with a gap is not an answer to "I want twenty".

### Square and vertical only

`SIZES` in the planner is square, portrait and story. A landscape ad is for a link preview, not a
feed. The manual builder still offers landscape and wide for exactly that.

### Instagram's interface is part of the canvas

A story and a reel are the same 1080×1920 file, and the reel is the harsher of the two: the profile
row takes the top, and the caption, audio strip and button column take far more of the bottom than a
story does. `SAFE` in `sizes.js` therefore insets story content by 260 at the top and 420 at the
bottom; `paint()` fills the **whole** frame with the background and then moves into that box, so the
image still bleeds edge to edge while nothing it has to say is covered. The preview can draw the
covered bands on top, as a guide; the download is always re-painted clean.

### Light mode had to be fixed before it could ship

Sprout `#A9FF9B` on Chalk `#F4F7F3` is about **1.3:1**. The first light-mode ads put the big
percentage in it, which was a pale smear. The fix is not to drop the brand colour but to pick, from
the brand's own colours, the one that passes on this background, and only then to darken it:

* `p.ink` — anything accent-coloured that is **words**, held to 4.5:1 (WCAG 1.4.3)
* `p.accent` — bars, buttons, the meter, held to 3:1 (WCAG 1.4.11, because the run bars carry
  meaning and are not decoration)
* `p.onAccent` — what sits on that fill, held to 4.5:1 against it

On the Forest palette this resolves to Sprout in dark mode and Forest `#034737` in light, which is
what a designer would have picked by hand — the difference is that it is now true for whatever
palette the owner switches to. Measured in the browser: fourteen pairs, both modes, all pass; light
ink went from 1.3:1 to **9.92:1**.

### What a record ad may claim

A record ad is refused unless its league-and-market slice has `ads.record_min_n` scored forecasts
behind it (default 150) **and** we were calibrated on it — the gap between what we said and what
happened must be within 12 points. A 97% from forty forecasts is luck, and an image is the worst
place to make that claim. What survives is phrased the way the track record page phrases it — "we
said 84%, it happened 86% of the time, over 1,840 forecasts" — never as a win rate, which is not
what this product measures and not a phrase its own word rules allow.

## 4. The match, before and after (added 2026-11-13)

Three templates the owner asked for, all under **Build one**. They read `backend/ad_sources.py`
instead of the public feed, because the feed answers a different question: it returns the sixty
lines that differ most from usual across every match, one card per player. These ads need one
match's two squads, or one scored match day.

| id | the claim | data |
|---|---|---|
| `faceoff` (Head to head) | Before kick-off: one player from each side, with his strongest lines. Or, with a market picked, both players on that same market, set large | `GET /api/admin/ads/matchups`, then `/matchup?match_id=&stat=` |
| `verdict` (We said, it happened) | One published forecast beside what he actually recorded, with a tick or a cross and the line it had to clear | `GET /api/admin/ads/settled?day=` |
| `results` (How the day went) | A match day's forecasts against what happened, with the **whole day's** count | the same |

**Head to head picks the strongest player per side, and the owner can change either.** A
player's lines are one per market, strongest first, at most three. The ranking stops at
`engine.feed_max_p` like the public feed does, so a 96% "1+ shot" never leads unless the player has
nothing under the ceiling. With a market picked, only that market counts, so both numbers answer the
same question.

**The after-the-whistle data includes the misses.** `/proof` returns only forecasts that came in,
which suits a landing-page strip but not an ad series: a builder that can only draw hits is a
builder for cherry-picking. `settled()` returns hits and misses for one day (the kickoff's UTC date,
default the most recent). It counts only published lines (Strong/Solid/Watch at 60% or more) where
the player played, the same population as `/track-record`. Rows are ordered the way the feed leads:
each player's strongest line under the ceiling first.

**The day's count cannot be edited away.** The results ad always prints "95 of 137 came in that
day", taken from the whole day rather than the rows the owner picked. It has no sub-head field, so
five hits picked out of a bad day still say it was a bad day. The verdict ad draws a miss exactly as
it draws a hit.

The line strip says "needed 3", not "the line: 2.5": a reader counts shots, and the half is the
engine's bookkeeping. Sentences name the player ("shots for J. Smith"), never "he".

A saved design stores `match_id`, `stat`, `players` (home first) and `day`. As with every other
template, it redraws from today's numbers, not the ones on screen when it was saved.

Also fixed in this pass: the Ad builder screen crashed on open ("This screen hit a problem").
`/api/leagues` answers `{countries: [{leagues: [...]}]}`, and the screen called `.map` on that
object.
