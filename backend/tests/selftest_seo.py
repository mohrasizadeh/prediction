"""robots and the sitemap (docs/71): what is offered to a crawler, what is withheld, and the switch that turns it off."""
from testkit import *
import os
import re
from datetime import datetime, timedelta, timezone

import seo as SEO
import site_studio as SS

HERE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ROBOTS = os.path.join(HERE, "frontend", "public", "robots.txt")
LEARN = os.path.join(HERE, "frontend", "src", "pages", "Learn.jsx")

now = datetime(2026, 11, 10, 12, 0, tzinfo=timezone.utc)

with TestClient(srv.app) as owner:
    admin, support, analyst = boot(owner)
    anon = TestClient(srv.app)

    # ---------------- the Learn slugs are read, not copied
    # The articles are hardcoded in Learn.jsx. A second list here would drift the first time someone
    # added an article, so the file is read. If that read ever returns nothing -- the array renamed,
    # its shape changed -- the sitemap silently loses every Learn page, so it is asserted directly.
    slugs = SEO.learn_slugs()
    check(len(slugs) >= 2, f"the Learn slugs are read out of Learn.jsx ({len(slugs)} found)")
    jsx = open(LEARN, encoding="utf-8").read()
    in_file = re.findall(r'slug:\s*"([a-z0-9-]+)"', jsx)
    check(sorted(set(slugs)) == sorted(set(in_file)), "...every one of them, and nothing that is not one")
    check("forecast-card" in slugs, "...including the article the footer links to")

    # ---------------- nothing private is ever offered
    for p in ("admin", "account", "account/billing", "combos", "following", "search", "dev/kit",
              "sign-in", "sign-up", "reset-password", "newsletter/confirm", "unsubscribe", "welcome"):
        check(SEO.is_private(p), f"private: /{p}")
    for p in ("", "live", "likely", "finder", "learn", "learn/tiers", "match/x", "team/y", "legal/terms"):
        check(not SEO.is_private(p), f"public: /{p}")
    check(not any(SEO.is_private(p) for p in SEO.STATIC_PATHS), "no static path in the sitemap is a private one")

    # ---------------- the sitemap on an empty database
    rows = SEO.urls(db, now=now)
    locs = [r["loc"] for r in rows]
    check(len(locs) == len(set(locs)), "no URL appears twice")
    check("/" in locs and "/finder" in locs and "/legal/privacy" in locs, "the static pages are listed")
    check("/learn/forecast-card" in locs, "each Learn article has its own URL")
    check(not any(SEO.is_private(l.lstrip("/")) for l in locs), "nothing private reached the list")
    check(all(r["lastmod"] for r in rows), "every URL carries a lastmod")

    # ---------------- the sitemap with real rows in it
    # Each of these collections carries a UNIQUE index on ext_id, so every row needs its own.
    db.leagues.insert_many([
        {"iid": 1, "ext_id": "L1", "id": "pl", "name": "Premier League", "enabled": True},
        {"iid": 2, "ext_id": "L2", "id": "ll", "name": "La Liga", "enabled": False},
    ])
    db.teams.insert_many([
        {"iid": 10, "ext_id": "T10", "id": "ars", "name": "Arsenal", "league_iid": 1},
        {"iid": 11, "ext_id": "T11", "id": "che", "name": "Chelsea", "league_iid": 1},
        {"iid": 12, "ext_id": "T12", "id": "rma", "name": "Real Madrid", "league_iid": 2},
    ])
    db.players.insert_many([
        {"iid": 100, "ext_id": "P100", "id": "saka", "name": "Saka", "team_iid": 10},
        {"iid": 101, "ext_id": "P101", "id": "nobody", "name": "Never Forecast", "team_iid": 10},
    ])
    db.forecasts.insert_one({"id": "f1", "fkey": "k1", "run_id": "r1", "match_iid": 500,
                             "player_iid": 100, "stat": "shots", "p": 0.7})
    db.matches.insert_many([
        {"iid": 500, "ext_id": "M500", "id": "m-soon", "league_iid": 1, "status": "scheduled",
         "kickoff": now + timedelta(days=2), "home_iid": 10, "away_iid": 11},
        {"iid": 501, "ext_id": "M501", "id": "m-done", "league_iid": 1, "status": "final",
         "kickoff": now - timedelta(days=5), "home_iid": 11, "away_iid": 10},
        {"iid": 502, "ext_id": "M502", "id": "m-ancient", "league_iid": 1, "status": "final",
         "kickoff": now - timedelta(days=2000), "home_iid": 10, "away_iid": 11},
        {"iid": 503, "ext_id": "M503", "id": "m-offleague", "league_iid": 2, "status": "scheduled",
         "kickoff": now + timedelta(days=2), "home_iid": 12, "away_iid": 12},
    ])
    rows = SEO.urls(db, now=now)
    locs = [r["loc"] for r in rows]
    mod = {r["loc"]: r["lastmod"] for r in rows}
    check("/league/pl" in locs and "/league/ll" not in locs, "only an enabled league gets a page")
    check("/team/ars" in locs and "/team/che" in locs and "/team/rma" not in locs, "teams follow their league")
    check("/player/saka" in locs, "a player we have forecast gets a page")
    check("/player/nobody" not in locs, "...and one we never have does not: that page has nothing on it")
    check("/match/m-soon" in locs and "/match/m-done" in locs, "fixtures either side of today are listed")
    check("/match/m-ancient" not in locs, "a match from five years ago is not worth a crawl")
    check("/match/m-offleague" not in locs, "a fixture in a disabled league is not listed")
    # A settled match will not change again; one still to be played is refit every tick.
    check(mod["/match/m-done"] == (now - timedelta(days=5)).date().isoformat(), "a final match's lastmod is its kickoff day")
    check(mod["/match/m-soon"] == now.date().isoformat(), "a scheduled match's lastmod is today, because the forecast moves")

    # ---------------- the XML itself
    xml = SEO.sitemap_xml(db, now=now)
    check(xml.startswith('<?xml version="1.0" encoding="UTF-8"?>'), "the sitemap is XML, declared as such")
    check('xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"' in xml, "...in the sitemap namespace")
    check(xml.count("<url>") == len(rows) and xml.rstrip().endswith("</urlset>"), "one <url> per row, and the document closes")
    check("<loc>https://app.test/finder</loc>" in xml, "every loc is absolute, from PUBLIC_BASE_URL")
    check("app.test//" not in xml, "...and never doubles the slash")

    r = anon.get("/api/seo/sitemap.xml")
    check(r.status_code == 200 and r.headers["content-type"].startswith("application/xml"), "a crawler with no session gets the sitemap")
    check("max-age=3600" in r.headers.get("cache-control", ""), "...cached for an hour, not recomputed per request")
    check("<loc>https://app.test/</loc>" in r.text, "...with the front page in it")

    r = anon.get("/api/seo/robots.txt")
    check(r.status_code == 200 and r.headers["content-type"].startswith("text/plain"), "robots.txt answers as text")
    check("Sitemap: https://app.test/api/seo/sitemap.xml" in r.text, "...and points at the sitemap, absolutely")
    check("Disallow: /admin/" in r.text and "Disallow: /account/" in r.text, "...and keeps crawlers out of the private areas")

    # ---------------- XML injection through a public id
    # Ids come from a provider. A '&' or a '<' in one would break the document for every crawler.
    db.teams.insert_one({"iid": 13, "ext_id": "T13", "id": 'a&b"<c>', "name": "Nasty", "league_iid": 1})
    xml = SEO.sitemap_xml(db, now=now)
    check("a&amp;b" in xml and "<c>" not in xml.split("<urlset")[1].replace("&lt;c&gt;", ""), "a hostile id is escaped, not injected")

    # ---------------- the switches
    SS.put_section(db, "boss@example.com", "seo", {**SS.get_draft(db)["data"]["seo"], "sitemap": False})
    SS.publish(db, "boss@example.com", note="sitemap off")
    check(SEO.urls(db, now=now) == [], "turning the sitemap off empties it")
    check("<urlset" in SEO.sitemap_xml(db, now=now), "...but the file still exists and parses")

    SS.put_section(db, "boss@example.com", "seo", {**SS.get_draft(db)["data"]["seo"], "sitemap": True, "robots_index": False})
    SS.publish(db, "boss@example.com", note="noindex")
    check(SEO.urls(db, now=now) == [], "asking not to be indexed empties it too, even with the sitemap on")
    check(SEO.robots_txt(db).strip() == "User-agent: *\nDisallow: /", "...and robots.txt served from the API says keep out")

    SS.put_section(db, "boss@example.com", "seo", {**SS.get_draft(db)["data"]["seo"], "robots_index": True})
    SS.publish(db, "boss@example.com", note="back on")
    check(len(SEO.urls(db, now=now)) > 10, "switching indexing back on restores the list")

    # ---------------- the static file crawlers actually read
    # It cannot read PUBLIC_BASE_URL, so its one absolute URL is written in. If the domain changes,
    # brand.site changes with it and this test is what says the file was missed.
    txt = open(ROBOTS, encoding="utf-8").read()
    host = SS.defaults()["brand"]["site"]
    check(f"Sitemap: https://{host}/api/seo/sitemap.xml" in txt, f"the static robots.txt points at {host}, the brand's own domain")
    check("User-agent: *" in txt, "...and addresses every crawler")
    for p in SEO.PRIVATE_PREFIXES:
        check(f"Disallow: /{p}/" in txt, f"the static robots.txt withholds /{p}/")
    check("Allow: /api/seo/" in txt and "Disallow: /api/" in txt, "...and lets the two SEO files through while holding the API back")

print("PASS")
