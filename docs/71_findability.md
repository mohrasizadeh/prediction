# 71 — Findability: robots, the sitemap, and the document head

## What was true before this

Nothing on the site could be found, and no single thing was to blame — six were:

| | Before |
|---|---|
| Rendering | Client-rendered CRA. The HTML a crawler receives is `<div id="root"></div>`. |
| `<title>` | One for the entire site, and stale: `<title>Forecast</title>`, two brands out of date. |
| `description` | Absent. |
| `og:` / `twitter:` | Absent, so every link shared anywhere previewed as a bare URL. |
| `canonical` | Absent. |
| `robots.txt`, `sitemap.xml` | Neither file existed anywhere in the repository. |

And the part that matters for how we work: `seo.title_template`, `seo.description_template`,
`seo.og_image`, `seo.robots_index` and `seo.sitemap` had been in Site Studio and in
`/api/site/config` since the beginning **with nothing reading them**. An owner could set a title
template, publish, and watch nothing happen. That is the same bug as the `features.*` switches in
docs/67, and it is worth naming as a class: *a setting that reaches nothing is worse than a missing
setting, because it answers the question "did I already do this?" with a yes.*

## What exists now

### `backend/seo.py` — the sitemap

`urls(db)` returns the pages we want indexed; `sitemap_xml(db)` renders them. Served at
`GET /api/seo/sitemap.xml`, public, cached for an hour.

Included: the static public pages, each Learn article, every enabled league, the teams in those
leagues, **players we have actually forecast**, and matches from 400 days back to 120 days forward.

Excluded on purpose:

- Anything behind a session (`/account`, `/combos`, `/following`) and every sign-in, reset or
  confirm step. A crawler cannot see them.
- `/search` — someone else's content rearranged, thin by construction and effectively infinite.
- `/dev/kit` — development only, and already carries its own noindex.
- A player with no forecast. A squad list is cheap to generate and worthless to crawl; 40,000 empty
  pages teach a crawler that this site is mostly empty.
- A match older than the window. It still has a page; it has no reason for anyone to arrive on it.

`lastmod` is the kickoff day for a settled match — it will not change again — and today for one
still to be played, because the forecast is refit on every tick. That is the honest answer, and
`lastmod` is the one field in the sitemap protocol Google actually uses.

### The Learn slugs are read, not copied

The articles are hardcoded in `frontend/src/pages/Learn.jsx`. A second list in the backend would
drift the first time someone added an article, so `learn_slugs()` reads that file, and
`selftest_seo.py` asserts the read still finds every `slug:` in it. Rename the array and a test
fails instead of the sitemap quietly shortening.

### `frontend/public/robots.txt`

A static file, because robots.txt must sit at the document root to be read at all and this backend
serves no HTML — every route it has is under `/api`, and the platform serves the static build. Its
`Sitemap:` line points at `/api/seo/sitemap.xml`, which is a valid directive: a sitemap may live at
any URL.

**Because it is static it cannot follow `seo.robots_index`.** That gap is covered, imperfectly and
deliberately: turning indexing off empties the sitemap *and* makes every page write
`<meta name="robots" content="noindex,nofollow">`, which Google honours once it renders the page —
one crawl later than a header would. `GET /api/seo/robots.txt` returns what the static file *should*
say for the current setting, so the two can be compared when they disagree. Closing the gap properly
needs the public surface rendered somewhere we control.

The one absolute URL in the static file is written in, since the file cannot read `PUBLIC_BASE_URL`.
`selftest_seo` pins it to `brand.site`, so changing the domain fails a test that points here.

### `frontend/src/lib/seo.js` + `useTitle`

`useTitle` used to set `document.title` and nothing else, and about twenty screens already called
it. It was widened in place rather than joined by a second hook, so all twenty gained a description,
a canonical URL and `og:`/`twitter:` tags without being touched — and so there is still exactly one
place that decides what the head says. Every existing one-argument call still works.

```jsx
useTitle("Insights")
useTitle(name, { description: "…", image: crest, type: "profile" })
useTitle(t, { vars: { team1: home.name, team2: away.name } })   // feeds seo.title_template
```

**Templates are used only when the page can fill every placeholder they name.** The shipped default
is `"{name}: {team1} vs {team2} forecasts"` — written for a match page — and running it on the
Finder would produce `"Forecast Zone:  vs  forecasts"`. `fill()` returns null instead, and the
caller falls back to `"{page} · {name}"`. So one setting serves the page it was written for without
damaging the other twenty.

Canonical URLs drop the query and the hash: `?tab=`, `?market=` and a preview token are all the same
page to a search engine, and keeping them would split one page's standing across a dozen
near-duplicates. A Site Studio preview is never offered for indexing — `/api/site/config` already
refuses to be cached or indexed when it serves a draft, and this is the page half of that rule.

### `frontend/public/index.html`

The brand-level fallbacks, and for one class of reader the only thing that exists: Slack, WhatsApp,
X and Facebook read the HTML they are served and never run JavaScript. The title there is the
**brand**, not a page — a stale page name is worse than a general one, because the preview for
`/match/123` would otherwise read like the front page. `og:image` is left out rather than pointed at
a placeholder: a card with a broken image renders worse than a card with none.

## The limit, stated once and plainly

This is a client-rendered app. Writing tags at runtime fixes the tab, the bookmark, and what Google
sees on its **second, rendering** pass. It does not fix the first pass, and it does not fix link
previews at all.

So the next decision is the rendering one, and it is the expensive one. CRA cannot server-render.
The options, in increasing order of cost:

1. **Prerender the public routes at build time.** Cheap, fragile with CRA 5, and no good for a page
   whose content did not exist at build time — which is every match page.
2. **A thin meta-injection layer in front of the static build.** Serves the same bundle with the
   head rewritten per path. Gets correct titles and real link previews without touching the app.
3. **Move the public surface to Next.js.** The correct long-term answer and genuinely weeks of work.

Recommended order: (2) now, (3) when there is traffic worth migrating for.

## The vocabulary constraint, which is a strategy constraint

`textguard.py` and `frontend/scripts/check-copy.js` ban *odds*, *picks*, *stakes*, *units*,
*hit rate* and the rest, CI-enforced, with one permitted exception for the exact disclaimer. Three
of the four highest-volume search terms in this category are on that list.

That is not a bug and should not be "fixed". It does mean the reachable terms are the ones built on
our own vocabulary — *"<team> v <team> forecast"*, *"how likely is <player> to score"*,
*"<player> shots on target stats"* — and the head terms are closed to us by our own compliance
rules. Worth knowing now rather than discovering in six months.

It also decides how any automated content must work: anything that writes public copy has to pass
through `textguard` on the way in. A pipeline that ingests outside football coverage will drag
banned words in constantly — failing the build, or worse, writing straight to Mongo and bypassing
the check entirely. Generate from our own data, where we control the words.
