# 19. Logos, crests and player photos

Written 2026-10-26. Goal: league logos, club crests and player photos on every screen, fetched **once** from API-Football (api-sports.io), kept in our own database and served from our own address.

## 1. The approach in one paragraph

We ask API-Football which image belongs to each of our leagues, clubs and players. We download each image **once**, check it, and store the bytes in MongoDB (`media`). The app then shows `/api/media/{kind}/{id}`, never a link to someone else's server. If an image is missing, the page draws initials (players) or a shield (clubs). A second run costs nothing. A new signing or a promoted club is picked up by a manual **Refresh** (about twice a year, at the transfer windows).

Why not link to the provider's images directly: slower pages, breaks if they change a path, throttling on their media server (they say it has per-second limits), no way to take one image down, and a looser security policy (`img-src https:`). Why not PitchAPI's own `image_url`: its hot-linking terms are not stated (doc 08), and it is a second set of images to keep consistent. We keep it as an optional fallback, off by default (`images.use_provider_urls`).

## 2. What you do (once)

1. Get an API-Football key at api-football.com (the free plan is enough to start: 100 calls a day). **Read their terms first** (section 8).
2. Run `backend/check_apifootball.py` once with your key (3 API calls). It prints `ok` or `CHECK` for each open question in section 3. Fix any `CHECK` before the first full run.
2b. Admin → Keys → **API-Football key** → paste, save.
3. Admin → Settings → `images.leagues`: map each of our leagues to its API-Football league id. Usual ids: Premier League 39, La Liga 140, Serie A 135, Bundesliga 78, Ligue 1 61. Check each one in your dashboard. The setting key is **our** league `iid` (the number the Leagues screen shows).
4. Admin → Engine → **Images** → **Run sync**. On the free plan it takes two days (it stops at the daily budget and says so). Press it again the next day.
5. Open the **Review** list. Approve or reject each pair. About one in ten will need a look.
6. Look at 20 pages. When happy, set `images.enabled = true`.

## 3. How a run works (`images.py`)

| Step | What happens | API calls |
|---|---|---|
| League | Our league's API-Football id comes from `images.leagues`. Its logo is downloaded. | 0 |
| Clubs | One call lists the league's clubs. We match ours by name **inside that league only**. The call tries this season, then the one before, then the one before that, because the free plan may not read the newest season. | 1 to 3 per league |
| Players | One call per matched club lists its squad. We match ours by surname, first initial and position. Clubs with no players of ours yet cost nothing. | 1 per club |
| Download | `media.api-sports.io/football/{leagues,teams,players}/{id}.png`, only from that host. Checked, then stored. | 0 (logos); photos are treated the same, see unverified below |

**Budget.** About 22 calls per league (1 to 3 for clubs, about 20 for squads). Five leagues is about 110 to 120 calls: two days on the free plan, one run on a paid plan. `images.daily_calls` (default 90) keeps headroom. The run stops cleanly at the budget or after 40 seconds and reports `done: false`. Run it again.

**Size.** An estimate, not a measurement: some tens of megabytes for five leagues. The Images screen shows the real number (`bytes_stored`). Free MongoDB tiers are small; check yours.

**Matching never guesses.** Each pair gets a score:
- Clubs: names are normalised (accents, "FC", "AFC", "and"/"&", a short alias table such as Man Utd and Spurs, plus your own in `images.team_aliases`). Equal after that = 1.0. A name that contains the other = 0.92. Otherwise a similarity ratio.
- Players: same surname and same first initial = 0.97. Same surname with no initial on one side = 0.8. Same surname, different initial = 0.55. Wrong position takes 0.12 off.
- A pair is used on its own only if the score is at least `images.min_confidence` (0.9) **and** the next-best candidate is at least 0.04 behind. 0.7 to that is **review**. Below 0.7 is **none**.
- If two of our players want the same photo, both go to review.

A wrong face on a player page is worse than initials. When in doubt the system shows initials.

### The calls we make, checked against the API-Football guide

**Read this first.** API-Football's own documentation page (`documentation-v3`) did not load for me (a client error on every try). I checked the calls against their public beginner's guide and independent tutorials instead. Where only those sources back a line, the table says so. `check_apifootball.py` tests the rest against your real key.

| Call | Parameters we send | Fields we read | Status |
|---|---|---|---|
| Header | `x-apisports-key: <key>` (direct API-Sports account; the `x-rapidapi-*` pair is for the RapidAPI marketplace only) | | Confirmed |
| `GET https://v3.football.api-sports.io/teams` | `league`, `season` (`league` needs `season`) | `response[].team.id`, `.name` | Confirmed |
| `GET /players/squads` | `team` | `response[0].players[].id`, `.name`, `.position` | Confirmed (also has `age`, `number`, `photo`; we ignore them) |
| Envelope | | `errors` (empty list on success, object when something is wrong), `results`, `paging`, `response` | Confirmed |
| Rate headers | | `x-ratelimit-requests-remaining` (daily), `x-ratelimit-remaining` (per minute); names are case-insensitive | Confirmed; the per-minute cap for each plan is not stated anywhere I could read |
| Wrong parameter or a season the plan cannot read | | HTTP 200 with empty `response`, sometimes with a `plan` error | Confirmed |
| 429 | | rate limit | Confirmed |
| 499 / 500 | | timeout / server error | Confirmed; their guide says retry |
| `GET /leagues?id=` | (`check_apifootball.py` only) | `seasons[].coverage` | Confirmed shape; not used by the sync |
| Image files | `https://media.api-sports.io/football/{leagues,teams,players}/{id}.png` | | **Not confirmed.** The script fetches one of each |
| Photos free of quota | | | **Not confirmed.** The script shows the counter before and after |
| Seasons on the free plan | | | **Not confirmed.** The script reports what comes back; the sync tries three seasons |
| Terms for storing and showing images | | | **Not read.** See section 8 |

**What the client does about it** (`AFClient.get`):
- Sends only `x-apisports-key`. Stops on 401 or 403 with a plain message.
- **Retries once** after 2 seconds on 499, 500, 502, 503, 504 or a dropped connection. Both attempts count against our budget. A second failure stops with a plain error.
- Reads `x-ratelimit-requests-remaining` after every answer and saves it for the day. If the provider says 0, the next call is not sent (their count wins over ours).
- If `x-ratelimit-remaining` (per minute) is 0, waits 5 seconds before the next call.
- Treats 429, and any `errors` text with "limit" or "request" in it, as "stop and resume later".
- Handles `errors` as a list or an object. Any other error is cached as an empty answer for 30 days, so a plan or season problem is not paid for twice.
- We do **not** call `/status` (not verified) and do **not** read `coverage` (it would cost one call per league for no change in what we do: a club with no squad simply returns nothing).

**Still unverified:** the four "Not confirmed" lines. Each fails safe: a missing image is remembered as `missing` and not retried; a photo that costs quota is counted by the daily budget.

## 4. What is stored

New collections (field lists in doc 05):
- `media`: the bytes. One row per `kind` (`league`, `team`, `player`) and our `iid`. PNG, JPEG or WebP only, size capped by `images.max_bytes`. SVG is refused, on purpose (SVG can carry scripts).
- `image_map`: the decision per record: API-Football id, scores, up to three candidates, `status` (`auto`, `approved`, `review`, `none`, `rejected`), `missing`.
- `image_api_cache`: API answers kept 30 days, so a re-run does not spend calls.
- `image_api_calls`: calls per day (the budget counter).
- `image_runs`: one row per run.

Nothing else from the provider is stored: no names, no stats.

## 5. How the app shows them

**Address.** `/api/media/team/{team public id}?v={first 8 of hash}`. The `v` changes when the image changes, so the browser can keep it for a year (`Cache-Control: public, max-age=31536000, immutable`, plus `ETag` and 304). The route answers 404 while `images.enabled` is off, for unknown ids, and for taken-down images.

**In API answers.** Every team, player and league object now carries `image`: our address or `null`. `image_url` (the provider link) is no longer returned. Fixtures carry `league` with its `image`. Search, match, team and player pages all use the same helper (`queries.attach_images`).

**Components** (add to doc 04 §7):

| Component | Sizes | Fallback | Notes |
|---|---|---|---|
| `Crest` | 20, 28, 40, 64 px | A shield outline in `text3` on `surface2` | Keep the aspect ratio (`object-fit: contain`), never crop a crest. Set `width` and `height` so the page does not jump. |
| `LeagueMark` | 20, 28, 40 px | The league's two-letter code on `surface2` | Same rules as `Crest`. |
| `PlayerAvatar` | 32, 48, 96 px | Initials (two letters) on a tint | Circle crop, `object-fit: cover; object-position: center top`. The tint is chosen from the player's id so it stays the same. Text plus tint, never colour alone. |

Rules for all three:
- `loading="lazy"` and `decoding="async"` except the first screenful. Fade in over 150 ms; no fade under `prefers-reduced-motion`.
- If the image fails to load, swap to the fallback (`onError`). Never show a broken-image icon.
- `alt=""` when the name is printed next to it (the image is decoration). Otherwise `alt="Arsenal crest"` / `alt="Bukayo Saka"`. No banned words (doc 03).
- Dark mode: many crests have dark art. Put each crest on a `surface` chip with 4 px padding and a 1 px `border` ring in dark mode only.
- Skeletons reserve the exact size.

**Where** (all screens in doc 01): fixture rows and the match header (both crests, league mark), forecast cards (player avatar or crest), the squad grid's first column, team and player headers, search results, leaderboards, league chips and filters, the Finder's league filter, the open-graph image (crests on the brand background; the server reads bytes from `media`).

**Footer.** `images.credit_text` (public setting) shows when images are on: "Club names, crests and player photos belong to their owners. We are not affiliated with any club or league."

**Security header.** With our own images only, tighten the public app's CSP to `img-src 'self' data:` (doc 15 had `https:`). Keep `https:` only while `images.use_provider_urls` is on. The admin Review cards show the provider's candidate picture by link, so the **admin** pages alone also allow `img-src https://media.api-sports.io`.

## 6. Admin → Engine → Images (new tab)

- Counts per kind: ours, stored, auto, approved, review, none, rejected. A bar for today's API calls against `images.daily_calls`. Bytes stored. Last run and whether it finished.
- Buttons: **Run sync**, **Refresh squads** (`?refresh=true`, 1 call per club; use after the transfer windows).
- **Review list**: one card per pair: our name and the candidates side by side with the provider's picture (the candidate's image is shown from `media.api-sports.io` in the admin only), the score, **Approve this one**, **Reject**, **Upload instead**.
- **Take down** on any record: removes the image at once; it is never fetched again. Use it when a rights holder asks, or when an image is wrong.
- **Upload**: PNG, JPEG or WebP, same checks. Use it for a club the provider lacks.

Routes (doc 06): `GET /images`, `GET /images/review`, `POST /images/sync`, `POST /images/{kind}/{iid}/approve`, `.../reject`, `PUT .../upload`, `DELETE /images/{kind}/{iid}`; public `GET /api/media/{kind}/{public_id}`. Writes need `jobs.run` (owner and admin); reading needs `logs.read`. Every write is in the audit log. The key is owner-only.

## 7. Settings (10 new; 175 in all)

| Key | Default | Meaning |
|---|---|---|
| `images.enabled` | false | Master switch. Off = initials and shields everywhere, media route closed. |
| `images.leagues` | `{}` | Our league `iid` → API-Football league id. |
| `images.daily_calls` | 90 | API calls the sync may use per day. |
| `images.min_confidence` | 0.9 | Score needed without review (0.7 to 1). |
| `images.players` | true | Off = logos and crests only. |
| `images.max_bytes` | 400000 | Largest file stored. |
| `images.season` | 0 | 0 = try this season and the two before. |
| `images.team_aliases` | `{}` | Extra club-name pairs for the matcher. |
| `images.use_provider_urls` | false | Fall back to PitchAPI's `image_url`. |
| `images.credit_text` | (sentence above) | Footer line. Public. |

## 8. Rights and risk, plainly

- A crest is a trademark. A photo belongs to its photographer or the club or the player's image-rights holder. API-Football supplies the files; that does **not** by itself tell us we may store and show them on a commercial site. **I could not read API-Football's terms** (their terms page did not load for me and their guide is silent on images). **You must read them and, if unclear, ask their support in writing**: may we store these images and serve them from our own domain, on which plan, and is attribution required? Keep the answer.
- Player photos carry more risk than crests and league logos. A safe first launch: crests and league logos on, `images.players` off. Turn photos on once you have the written answer.
- Built-in protections: one master switch, one switch for photos, take-down by record, no hot-linking, nothing stored but images and ids, the footer credit line.
- If we ever wrap the site as a native app, the app stores review club logos under their own rule (Apple's guideline 5.2.1 on third-party content); that is a separate check.

## 9. When things go wrong

| Symptom | Cause | What happens | Fix |
|---|---|---|---|
| "No API-Football key saved" | No key | Run stops, nothing called | Admin → Keys |
| 401 / 403 | Wrong or expired key | Run stops with a plain message | Re-enter key |
| 429 or "limit" message | Per-minute or daily limit | Run stops, resumes next time | Wait; lower `images.daily_calls` |
| 499 / 500 | Provider timeout or error | One retry after 2 s, then a plain error | Run again later |
| No clubs returned | Season not on your plan, or wrong league id | League reported as skipped | Set `images.season`, check `images.leagues` |
| Image 404 on the media host | No picture for that id | Marked `missing`, not retried | Upload one, or leave initials |
| Wrong club matched | Similar names | Appears in Review if close; if it passed as auto, take it down | Add an alias; raise `images.min_confidence` |
| Promoted club has no crest | Not in the clubs list yet | `none` | Next season, or upload |
| New signing has no photo | Squad was read before the transfer | Initials | **Refresh squads** |
| Player moved club | Photo belongs to the person | Photo stays | Nothing |

## 10. Code

| File | Job |
|---|---|
| `backend/images.py` | API client with cache and daily budget, name matching, download and checks, the run, approve / reject / remove |
| `backend/routes_images.py` | Public media route; admin routes |
| `backend/queries.py` | `attach_images` and `image` on every team, player and league object |
| `backend/jobs.py` | `images` is a manual job (never automatic) |
| `backend/tests/selftest_images.py` | The eleventh test suite (includes retry and rate-header checks) |
| `backend/check_apifootball.py` | One-off pre-flight: 3 API calls and 3 image downloads, prints `ok` / `CHECK` |

---

# 11. PitchAPI is now the source (2026-11-03)

Everything above still describes `images.py`, which still works. It is no longer the way pictures
arrive. **League logos, club crests and player photos all come from PitchAPI**, and API-Football is
not needed for anything.

## 11.1 Why this changed

Section 1 argued against PitchAPI's own `image_url` on two grounds. One of them no longer holds and
the other never applied to how we use it:

- *"Its hot-linking terms are not stated (doc 08 B2)."* True, and still unanswered — but it is only
  a hot-linking question if we hot-link. We do not. Each picture is downloaded **once** and the bytes
  are stored in `media`, exactly as API-Football's were, and the browser is only ever given
  `/api/media/{kind}/{id}`. `pitch_photos.py` has worked this way for player photos since it was
  written; this change extends the same treatment to logos and crests.
- *"It is a second set of images to keep consistent."* It was a second set while two providers were
  in play. Now there is one.

## 11.2 What it costs

| Picture | Where its address comes from | API calls |
|---|---|---|
| League logo | `leagues.image_url`, saved by `ingest.sync_leagues` from `GET /v1/leagues` (docs/08 row 2) | **0** |
| Club crest | `teams.image_url`, harvested from `GET /v1/matches/{id}` where `match_extras` already fetches it (docs/08 row 7); `GET /v1/teams/{id}` only for clubs no match detail has covered | **0 or 1 per club, once** |
| Player photo | `GET /v1/players/{id}` (docs/08 row 6) | 1 per player, once |

Downloads from `cdn.pitchapi.dev` are not API calls. Compare with section 3: API-Football wanted
about 22 calls per league and two days on its free plan, plus a key, plus a league-id map, plus a
review list for name matching. None of that is needed now, because PitchAPI tells us which picture
belongs to which entity — there is no matching to get wrong, so there is nothing to review.

## 11.3 How it runs

`pitch_photos.plan(db)` runs once a day from the tick and queues anything without a stored picture:
`league_logo`, `team_crest`, `player_photo`. Entities with current forecasts are queued first.
`ingest.process_queue` dispatches all three to `pitch_photos.fetch_image`.

Safety is unchanged from the player-photo path: only `https://cdn.pitchapi.dev` is ever downloaded
from, the bytes are sniffed (PNG, JPEG or WebP; SVG refused; size capped) by `images.store_media`,
and the record is marked checked so a missing picture is not asked for twice.

`images.enabled` still gates whether pictures are shown at all, and `images.use_provider_urls` still
links straight to the provider when you want that. Both behave as section 5 describes.

## 11.4 What happened to API-Football

Nothing was deleted. `images.py`, `check_apifootball.py`, the API-Football key, `images.leagues` and
the review list are all still there and still work, so an install that already synced from
API-Football keeps its pictures. They are now optional, and a fresh install never needs them.
`media.source` records which provider each stored picture came from; `pitch_photos.status(db)`
reports `from_pitchapi` and `from_apifootball`.

## 11.5 Code

| File | Job |
|---|---|
| `backend/pitch_photos.py` | All three kinds: plan, address lookup, download, store, status |
| `backend/ingest.py` | Dispatches `league_logo`, `team_crest` and `player_photo` |
| `backend/match_extras.py` | Saves the crests that arrive with the match-detail call |
| `backend/tests/selftest_pitch_images.py` | Proves all three come from the CDN, that nothing else is ever fetched, and that the browser gets our address |
