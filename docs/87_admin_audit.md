# 87 — Admin panel audit

Fifty-one menu entries, thirty-seven screens, six sub-components. Every menu entry resolves to a
real screen (the `Soon` "Coming in the next phase" fallback is unreachable — dead code).

---

## 0. The blocker, before anything else

**There is no API-Football ingest. Nothing calls it, because it does not exist.**

```
who calls fixtures_bundle()  outside apifootball.py  ->  NOBODY
who calls normalize_af                               ->  NOBODY
```

`normalize_af.py` (their JSON into our dicts) and `apifootball.fixtures_bundle()` (20 fixtures a
call, events + lineups + statistics + players) are both written and both tested. Neither is wired to
anything. The job tick runs on `PitchClient`; the live tick runs on SportAPI.

So **the entire football data pipeline is still PitchAPI and SportAPI.** Removing them today does
not migrate the app to API-Football — it leaves the app with no way to fetch a fixture, a lineup or
a player statistic ever again. The Competitions screen would still list every competition and let
you switch them on, and nothing would follow.

58 files reference `pitchapi`/`PitchClient`/`sportapi`.

**The order has to be:**

1. Build the API-Football ingest — backfill, daily, live — on `fixtures_bundle` → `normalize_af`
2. Cut the jobs over to it, keeping the old path switchable
3. Watch real data land: fixtures, lineups, player rows, images
4. **Then** delete PitchAPI and SportAPI, in one change, with their screens, settings and tests

Done in that order, step 4 is mechanical. Done now, step 4 is an outage.

---

## 1. The five items flagged by the owner

| # | Item | Verdict |
|---|---|---|
| 1 | API-Football dashboard opens on Usage | **Do now.** One-line tab reorder plus the fallback. |
| 2 | Remove PitchAPI | **Blocked** by §0. Mechanical once the ingest exists. |
| 3 | Remove SportAPI | **Blocked** by §0. Same change. |
| 4 | Competitions UI/UX | **Do now.** Independent of the ingest. |
| 5 | Jobs pull images from PitchAPI | **Half already done — see below.** |

### On item 5, the images

This is further along than it looks. `images.py` **already** pulls from API-Football:
`media.api-sports.io/football/{leagues,teams,players}/{id}.png`, and on API-Football the logo is a
URL on the entity itself, so finding one costs no API call at all (on PitchAPI it cost about 22 a
league).

What you are seeing is that **both** image modules run from the job tick: `images.py` (API-Football)
at one step and `pitch_photos.py` (PitchAPI, `cdn.pitchapi.dev`) at another.

It cannot simply be cut, because `images.py` resolves entities by their API-Football id. While the
entities in the database came from PitchAPI, those ids are absent. So this one is ordered too:
after a purge and a fresh API-Football ingest, `images.py` stands alone and `pitch_photos.py` goes
with the rest of PitchAPI. Deleting it before then removes crests without replacing them.

---

## 2. Findings from the audit itself — all six withdrawn

**I raised six defects in the admin panel. Every one of them was wrong. The panel is in good
shape; the methods I used to audit it were not.**

Recording them is worth more than hiding them, because they failed in one way, repeatedly:

| claimed | actually | why the check lied |
|---|---|---|
| admin keeps a shadow palette `--p-*` | the Site Studio **preview** namespace, injected at runtime by `Studio.jsx:110` so the preview shows the SITE's theme, not the admin's | a grep cannot see a property set from JavaScript |
| `--c-brand` defined three times | defined once in `tokens.css`; the other two files only **use** it | "file contains the string" read as "file defines the token" |
| `--on-accent`, `--tint` undefined | `--on-accent` is emitted at runtime by `compile_css()` from the site config (`lib/theme.js` says so in its first paragraph); `--tint` is set per element in `Media.jsx:64` — the colour on a player's initials circle | static analysis of a stylesheet cannot see a theme the server compiles and the browser injects |
| 21 form controls with no accessible name | **zero**. `Settings.jsx:60` carries `aria-label`; `Leagues.jsx:77` is wrapped in a `<label>` | `<select[^>]*>` stops at the first `>`, which in JSX is the `=>` of the onChange handler — the tag was truncated before its label |
| 8 screens with no empty state | `Home.jsx:105` says "Nothing needs you right now"; `Keys` lists a fixed set of providers and can never be empty | grepped for the component name `Empty`, missed inline states and screens that cannot be empty |
| raw hex in the ad builder | `Ads.jsx:376` is a **fallback** after `design.accent` and the site's own accent; the hex in `ads/sizes.js` are **inside a comment** explaining a contrast ratio. `draw.js` takes its colours from Studio and says why | grep hit comments and fallbacks and reported them as literals |

The measurement that should have been first, not fourth:

```
admin.css uses but nothing defines   ->  none
tokens the admin shares with the app ->  17
tokens only the admin uses           ->  3
unnamed form controls (JSX-aware)    ->  0
```

**The admin does not drift from the app, and it is accessible.** The "UI/UX must match the app"
brief has no outstanding work in it that I can evidence.

### What the pattern was

Every false finding came from a regex over source text standing in for a test of behaviour. Each
one pointed at a tidy, structural-sounding problem; four of the six would have taken real work to
"fix", and the first would have broken the Site Studio preview on the way. The things that settled
them were small and specific: a JSX-aware tag walker, a set difference between token definitions
and uses, and reading four files.

If this audit is repeated, the order is: measure, read the file, then claim.

### 2.5 Dead on arrival with PitchAPI (stands)

`Cache.jsx` and `Quality.jsx` are imported by `PitchAPI.jsx` and nothing else — verified against the
import graph. They are not dead today; they become dead the moment §0 step 4 happens and should go
in that same change rather than linger.

### 2.6 The menu already says this (stands)

`admin_shell.py` carries a comment admitting the three provider entries are transitional and that
"They go when the pipeline goes, in that same change." That is the same conclusion as §0. It was
written before the ingest work stalled, so it has been true for longer than intended.

---

## 3. What is good, and should not be "improved"

* Every menu entry resolves to a screen; no orphan files; no unreachable routes. The `Soon`
  "Coming in the next phase" fallback is unreachable — the only dead code found.
* `MOVED` keeps old bookmarks working after screens were folded into tabs.
* Permissions are declared per menu entry and enforced server-side, not merely hidden in the UI.
* Raw `<button>` with `btn btn--*` is the convention in **both** the app (152) and the admin (175),
  with no shared component either side. Consistent, so not a defect.
* The Logs screen prints every field of a row, which is what made this week's 502 diagnosable.
* The ad builder reads the palette from Site Studio, with a comment explaining that the share card
  which hardcoded it "has been drawing a palette that was replaced two redesigns ago".

---

## 4. Order of work

1. **Done now, and it is small:** Usage leads the API-Football screen and is its fallback tab
   (§1.1). Competitions UX (§1.4) is open and independent of everything else.
2. **The real work, and the thing actually blocking you:** the API-Football ingest — backfill,
   daily, live — on `fixtures_bundle` → `normalize_af` → the collections (§0 steps 1–3).
3. **Then mechanical:** delete PitchAPI and SportAPI with their screens, settings, tests,
   `pitch_photos.py`, `Cache.jsx` and `Quality.jsx` (§0 step 4, §1.5, §2.5).

The headline is that **the admin panel is not the problem.** Four of the five items raised are
either done, trivial, or blocked by one missing piece, and the six defects I found in the panel
itself were all my own measurement errors. The one thing standing between this app and API-Football
is the ingest, and it has not been started.
