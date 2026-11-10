"""seo.py -- the sitemap, and the one list of public paths (docs/71).

WHY THIS EXISTS. Nothing on this site could be found. There was no robots.txt and no sitemap
anywhere in the repository, every URL shared one `<title>Forecast</title>`, and `seo.title_template`,
`seo.description_template`, `seo.og_image`, `seo.robots_index` and `seo.sitemap` had been sitting in
Site Studio and in `public_config` since the start with nothing reading them -- the same shape of bug
as the `features.*` switches in docs/67: a screen that implies control it does not have.

WHAT A SITEMAP IS FOR, so the contents are not guessed at later. It is a list of the pages we WANT
indexed, with the last time each changed. It is a discovery aid, not a ranking input, and it is the
only way a crawler finds a page that is reachable solely by running JavaScript -- which, until the
public surface is rendered server-side, is every page here.

WHAT IS DELIBERATELY ABSENT:
  * Anything behind a session (/account, /combos, /following) or any sign-in, reset or confirm flow.
    A crawler cannot see them and should not try.
  * /search. Its output is someone else's content rearranged; a search page in an index is thin by
    construction.
  * /dev/kit. It is development-only and already carries its own noindex.

THE HONEST LIMIT. robots.txt has to sit at the document root to be read at all, and this backend
serves no HTML -- the static build is served by the platform, every route here lives under /api. So
robots.txt is a real file in frontend/public/ and it points its Sitemap: line here. That works (the
directive takes any URL), but it also means a STATIC robots.txt cannot honour `seo.robots_index`.
Turning indexing off therefore does two things that this module and the client split between them:
this sitemap goes empty, and every page writes `<meta name="robots" content="noindex,nofollow">`.
Google honours the meta tag once it renders the page. It is a real noindex, one crawl later than a
header would be. Closing that gap needs the public surface rendered somewhere we control.
"""
from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from xml.sax.saxutils import escape

import settings_store as S
import site_studio as SS

# The sitemap protocol's own ceiling is 50,000 URLs / 50 MB uncompressed per file. These caps keep
# one file well inside it and, more to the point, keep the sitemap to pages worth crawling: a player
# who has never been forecast is a page with nothing on it, and 40,000 of those teach a crawler that
# this site is mostly empty.
MAX_URLS = 50_000
CAP_PLAYERS = 20_000
CAP_TEAMS = 5_000
CAP_MATCHES = 10_000
CAP_POSTS = 5_000

# How far either side of today a match page is worth indexing. Forward: every fixture we hold.
# Back: a settled match still earns its page, because it carries what we said and what happened --
# but a five-year-old one carries no reason for anyone to arrive on it.
PAST_DAYS = 400
FUTURE_DAYS = 120

# The public paths that are not generated from data. "" is the front page.
#
# The Learn slugs are NOT here. They live in frontend/src/pages/Learn.jsx, hardcoded in the ARTICLES
# array, and a second copy in this file would drift the first time someone adds an article. The list
# is read from that file instead, and selftest_seo asserts the read still finds them -- so renaming
# the array or changing its shape fails a test rather than silently shortening the sitemap.
STATIC_PATHS = (
    "", "live", "likely", "insights", "finder", "explore", "compare",
    "leagues", "teams", "referees", "track-record", "learn", "pricing", "waitlist",
    "legal/terms", "legal/privacy", "legal/about",
)

# Never offered to a crawler, and spelled out in robots.txt as well. Kept here so the two agree.
PRIVATE_PREFIXES = (
    "admin", "account", "combos", "following", "search", "dev",
    "sign-in", "sign-up", "signup", "verify-email", "confirm-email", "enroll-2fa",
    "forgot-password", "reset-password", "change-password",
    "newsletter/confirm", "unsubscribe", "welcome",
)

_LEARN_JSX = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                          "frontend", "src", "pages", "Learn.jsx")


def learn_slugs(path: str | None = None) -> list[str]:
    """The Learn article slugs, read from the file that actually defines them.

    Deliberately crude: find the ARTICLES array, take every `slug: "..."` inside it. A parser would
    not be more correct here, and this fails loudly (empty list -> failing test) rather than quietly.
    """
    src_path = path or _LEARN_JSX
    try:
        with open(src_path, "r", encoding="utf-8") as fh:
            src = fh.read()
    except OSError:
        return []
    start = src.find("ARTICLES = [")
    if start < 0:
        return []
    # Stop at the line that closes the array at column 0, so a slug in later code is never picked up.
    end = src.find("\n];", start)
    body = src[start:end if end > 0 else len(src)]
    out, i = [], 0
    while True:
        i = body.find("slug:", i)
        if i < 0:
            break
        j = i + 5
        while j < len(body) and body[j] in ' \t':
            j += 1
        if j < len(body) and body[j] in "\"'":
            q = body[j]
            k = body.find(q, j + 1)
            if k > 0:
                slug = body[j + 1:k]
                if slug and slug not in out:
                    out.append(slug)
        i = j
    return out


def is_private(path: str) -> bool:
    p = path.strip("/")
    return any(p == pre or p.startswith(pre + "/") for pre in PRIVATE_PREFIXES)


def _iso(dt) -> str:
    if not isinstance(dt, datetime):
        return ""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).date().isoformat()


def _seo(db) -> dict:
    """The live `seo` section.

    get_live() returns a VERSION -- {v, data, css, note, by, at} -- not the config. Reading
    `live["seo"]` off it gives None every time, which silently reads as "every switch is at its
    default", so both switches below did nothing at all until a test asked them to.
    """
    return ((SS.get_live(db) or {}).get("data") or {}).get("seo") or {}


def _enabled_league_iids(db) -> list:
    return [d["iid"] for d in db.leagues.find({"enabled": True}, {"iid": 1})]


def urls(db, now: datetime | None = None) -> list[dict]:
    """Every URL we want indexed, as {loc, lastmod}. Relative paths; the route makes them absolute.

    Returns [] when the owner has turned indexing or the sitemap off in Site Studio. An empty
    urlset rather than a 404 is the right answer to "the sitemap is off": the file exists, we are
    simply not asking for anything to be crawled.
    """
    seo = _seo(db)
    if seo.get("robots_index") is False or seo.get("sitemap") is False:
        return []

    now = now or datetime.now(timezone.utc)
    today = now.date().isoformat()
    out: list[dict] = [{"loc": "/" + p, "lastmod": today} for p in STATIC_PATHS if not is_private(p)]
    out += [{"loc": f"/learn/{s}", "lastmod": today} for s in learn_slugs()]

    # The blog posts (docs/72). These are the only pages in the product that are served as real
    # HTML, so they are the only ones a crawler can read without executing JavaScript -- which makes
    # them the most valuable rows in this file, not an afterthought at the end of it. Drafts are
    # never listed: the public route refuses them, and offering one here would advertise a URL that
    # answers 404.
    if S.get(db, "blog.enabled"):
        for b in db.blog_posts.find({"status": "published"},
                                    {"slug": 1, "published_at": 1}).sort("published_at", -1).limit(CAP_POSTS):
            if b.get("slug"):
                out.append({"loc": f"/api/blog/{b['slug']}", "lastmod": _iso(b.get("published_at")) or today})
        out.append({"loc": "/api/blog", "lastmod": today})

    lg_iids = _enabled_league_iids(db)
    if not lg_iids:
        return out[:MAX_URLS]

    for d in db.leagues.find({"enabled": True}, {"id": 1}).limit(CAP_TEAMS):
        if d.get("id"):
            out.append({"loc": f"/league/{d['id']}", "lastmod": today})

    for d in db.teams.find({"league_iid": {"$in": lg_iids}}, {"id": 1}).limit(CAP_TEAMS):
        if d.get("id"):
            out.append({"loc": f"/team/{d['id']}", "lastmod": today})

    # Only players we have actually forecast. A squad list is cheap to generate and worthless to
    # crawl; a player with a forecast has a page with numbers and reasons on it.
    seen_pl = set()
    for iid in db.forecasts.distinct("player_iid", {"player_iid": {"$ne": None}}):
        if iid is not None:
            seen_pl.add(iid)
        if len(seen_pl) >= CAP_PLAYERS:
            break
    if seen_pl:
        for d in db.players.find({"iid": {"$in": list(seen_pl)}}, {"id": 1}).limit(CAP_PLAYERS):
            if d.get("id"):
                out.append({"loc": f"/player/{d['id']}", "lastmod": today})

    lo = now - timedelta(days=PAST_DAYS)
    hi = now + timedelta(days=FUTURE_DAYS)
    mq = {"league_iid": {"$in": lg_iids}, "kickoff": {"$gte": lo, "$lte": hi}}
    for d in db.matches.find(mq, {"id": 1, "kickoff": 1, "status": 1}).sort("kickoff", -1).limit(CAP_MATCHES):
        if not d.get("id"):
            continue
        # A settled match will not change again, so its kickoff day is its lastmod. One still to be
        # played changes every time the forecast is refit, so today is the honest answer.
        mod = _iso(d.get("kickoff")) if d.get("status") == "final" else today
        out.append({"loc": f"/match/{d['id']}", "lastmod": mod or today})

    # De-duplicate on loc, keep first, and hold the protocol's ceiling.
    seen, uniq = set(), []
    for u in out:
        if u["loc"] in seen:
            continue
        seen.add(u["loc"])
        uniq.append(u)
    return uniq[:MAX_URLS]


def sitemap_xml(db, now: datetime | None = None) -> str:
    base = SS.base_url()
    rows = urls(db, now=now)
    parts = ['<?xml version="1.0" encoding="UTF-8"?>',
             '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    for u in rows:
        loc = escape(base + u["loc"])
        mod = f"<lastmod>{escape(u['lastmod'])}</lastmod>" if u.get("lastmod") else ""
        parts.append(f"<url><loc>{loc}</loc>{mod}</url>")
    parts.append("</urlset>")
    return "\n".join(parts)


def robots_txt(db) -> str:
    """Served from /api/seo/robots.txt as well as the static file, so the two can be compared.

    The static copy in frontend/public/ is what crawlers actually read -- see the module docstring.
    This one reflects the live setting, and is what the static file should say.
    """
    seo = _seo(db)
    base = SS.base_url()
    if seo.get("robots_index") is False:
        return "User-agent: *\nDisallow: /\n"
    lines = ["User-agent: *"]
    lines += [f"Disallow: /{p}/" for p in PRIVATE_PREFIXES]
    lines += ["Disallow: /api/", "Allow: /api/seo/", "", f"Sitemap: {base}/api/seo/sitemap.xml", ""]
    return "\n".join(lines)
