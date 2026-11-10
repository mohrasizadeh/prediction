"""The blog (docs/72): tier selection, the draft boundary, the copy gate, and the page a crawler is served."""
from testkit import *
import re
from datetime import datetime, timedelta, timezone

import blog as B
import blog_render as BR
import textguard as TG
import seo as SEO
import settings_store as S

HERE_FE = os.path.join(os.path.dirname(HERE), "frontend")

now = datetime(2026, 11, 14, 12, 0, tzinfo=timezone.utc)
KO = datetime(2026, 11, 14, 17, 30, tzinfo=timezone.utc)


def fc(fid, **kw):
    """A forecast row shaped like the engine's output (engine_bridge), with the fields the blog reads."""
    d = {"id": fid, "fkey": "k" + fid, "run_id": "r1", "match_iid": 900, "is_current": True, "hidden": False,
         "scope": "player", "stat": "shots", "market": "player_shots", "thr": 2.0, "p": 0.7, "lo": 0.6, "hi": 0.8,
         "tier": None, "p_usual": 0.5, "edge": 0.2, "reasons": [], "player_iid": None, "team_iid": None,
         "span": 0.3, "is_personal": True, "pos": "FWD"}
    d.update(kw)
    return d


with TestClient(srv.app) as owner:
    admin, support, analyst = boot(owner)
    anon = TestClient(srv.app)

    # ---------------- slugs
    check(B.post_slug("Arsenal", "Chelsea", KO) == "arsenal-v-chelsea-2026-11-14", "the slug is both clubs and the date")
    check(B.post_slug("Bayern München", "Köln", KO).startswith("bayern-munchen-v-koln-"), "accents are folded, not dropped")
    # The two legs of a fixture must not collide: one would overwrite the other's post.
    check(B.post_slug("A", "B", KO) != B.post_slug("A", "B", KO + timedelta(days=120)), "the same clubs in a later month get their own slug")

    # ---------------- tier selection
    cards = [fc("s1", tier="Strong", p=0.82), fc("s2", tier="Strong", p=0.80), fc("o1", tier="Solid", p=0.66),
             fc("w1", tier="Watch", p=0.55), fc("n1", tier=None, p=0.52)]
    picked, missing = B.pick_three(cards)
    check([p["id"] for p in picked] == ["s1", "o1", "w1"], f"one Strong, one Solid, one lower, in that order (got {[p['id'] for p in picked]})")
    check(missing == [], "nothing missing when the day has all three")
    check(len({id(p) for p in picked}) == 3, "the same forecast is never used for two slots")

    # A day with no Strong is the ORDINARY case (docs/52), so it must degrade rather than promote.
    picked, missing = B.pick_three([fc("o1", tier="Solid"), fc("w1", tier="Watch")])
    check([p["id"] for p in picked] == ["o1", "w1"] and missing == ["Strong"], "no Strong: the slot is reported missing, not filled with a Solid")
    picked, missing = B.pick_three([fc("n1", tier=None), fc("n2", tier=None)])
    check([p["id"] for p in picked] == ["n1"] and missing == ["Strong", "Solid"], "ungraded rows fill only the lower slot, once")
    check(B.pick_three([])[0] == [], "no cards, no picks")

    # ---------------- line labels read like the product's own
    # floor(thr)+1, the same arithmetic as the card's need() and as forecast_outcomes' scoring rule
    # (reached = actual > thr). The first build read 2.0 as "2+ shots" under an evidence line saying
    # "reached 3+ in 6 of the last 10", so the card contradicted its own reasons.
    check(B.line_label(fc("x", thr=2.0)) == "3+ shots", "a 2.0 threshold is a 3+ line, because reached means MORE than 2")
    check(B.line_label(fc("x", thr=1.5)) == "2+ shots", "a 1.5 threshold is a 2+ line")
    check(B.line_label(fc("x", thr=3.5, stat="cards")) == "4+ cards", "a half rung is worded the same way the card words it")
    check(B.line_label(fc("x", stat="shots_on_target", thr=0.5)) == "1+ shots on target", "the stat name is unpicked from its id")
    check(B.need_of(2.0) == 3 and B.need_of(1.5) == 2 and B.need_of(None) is None, "need_of is the one place that arithmetic lives")

    # ---------------- a real post, end to end
    db.leagues.insert_one({"iid": 7, "ext_id": "L7", "id": "pl", "name": "Premier League", "enabled": True,
                           "current_season": "2026"})
    db.teams.insert_many([{"iid": 70, "ext_id": "T70", "id": "ars", "name": "Arsenal", "league_iid": 7},
                          {"iid": 71, "ext_id": "T71", "id": "che", "name": "Chelsea", "league_iid": 7}])
    db.players.insert_many([{"iid": 700, "ext_id": "P700", "id": "saka", "name": "Bukayo Saka", "team_iid": 70, "pos": "FWD"},
                            {"iid": 701, "ext_id": "P701", "id": "rice", "name": "Declan Rice", "team_iid": 70, "pos": "MID"},
                            {"iid": 702, "ext_id": "P702", "id": "palm", "name": "Cole Palmer", "team_iid": 71, "pos": "MID"}])
    db.matches.insert_one({"iid": 900, "ext_id": "M900", "id": "m900", "league_iid": 7, "status": "scheduled",
                           "kickoff": KO, "home_iid": 70, "away_iid": 71})
    db.forecasts.insert_many([
        fc("f1", player_iid=700, team_iid=70, tier="Strong", p=0.81, lo=0.72, hi=0.88, thr=2.0,
           reasons=["Arsenal are expected to hold the ball in Chelsea's half", "Chelsea concede shots to wide forwards"]),
        fc("f2", player_iid=701, team_iid=70, tier="Solid", p=0.64, thr=4.0, stat="tackles",
           reasons=["Chelsea build through the middle third"]),
        fc("f3", player_iid=702, team_iid=71, tier=None, p=0.52, thr=1.0, stat="shots_on_target", reasons=[]),
    ])

    p = B.build_post(db, 900, now=now)
    check(p is not None, "a fixture with three graded forecasts produces a post")
    check(p["status"] == "draft", "a post is born a DRAFT -- nothing is published by generating it")
    check(p["slug"] == "arsenal-v-chelsea-2026-11-14", "the post is slugged from the fixture")
    check(len(p["items"]) == 3, "three forecasts, no more")
    check([i["tier"] for i in p["items"]] == ["Strong", "Solid", "lower"], "one of each tier, strongest first")
    check(p["items"][0]["subject"] == "Bukayo Saka" and p["items"][0]["line"] == "3+ shots", "the lead item names the player and the line")
    check(p["items"][0]["pct"] == "81%", "the percentage is the engine's, rounded for reading")
    check(len(p["items"][0]["reasons"]) == 2, "the engine's own reasons travel with the item")
    check("Arsenal" in p["title"] and "Chelsea" in p["title"], "the title names both clubs")
    check(len(p["title"]) <= B.MAX_TITLE and len(p["description"]) <= B.MAX_DESC, "title and description stay inside what a result shows")
    check(p["match_id"] == "m900", "the post knows the match page to link to")

    # A fixture with one usable forecast is not worth a page.
    db.matches.insert_one({"iid": 901, "ext_id": "M901", "id": "m901", "league_iid": 7, "status": "scheduled",
                           "kickoff": KO, "home_iid": 71, "away_iid": 70})
    db.forecasts.insert_one(fc("g1", match_iid=901, player_iid=702, team_iid=71, tier="Solid", p=0.6))
    check(B.build_post(db, 901, now=now) is None, "one forecast is not a post")
    check(B.build_post(db, 404404, now=now) is None, "an unknown fixture is not a post")

    # ---------------- the copy gate
    # A banned word in a reason the ENGINE wrote must not reach a reader. The fixture is skipped
    # whole rather than having words stripped out of a sentence until it passes.
    db.forecasts.update_one({"id": "f2"}, {"$set": {"reasons": ["Their hit rate on tackles is high"]}})
    p2 = B.build_post(db, 900, now=now)
    check(all("hit rate" not in r.lower() for i in p2["items"] for r in i["reasons"]), "a reason carrying a banned word is dropped")
    db.forecasts.update_one({"id": "f2"}, {"$set": {"reasons": ["Chelsea build through the middle third"]}})

    # ---------------- generate, store, and leave published posts alone
    counts = B.generate(db, "2026-11-14", limit=10, now=now)
    check(counts["created"] == 1, f"the day's generation created the one post worth making ({counts})")
    stored = db.blog_posts.find_one({"slug": p["slug"]})
    check(stored and stored["status"] == "draft", "it was stored as a draft")

    counts = B.generate(db, "2026-11-14", limit=10, now=now)
    check(counts["replaced"] == 1 and counts["created"] == 0, "running it again refreshes the draft rather than duplicating it")

    pub = B.publish(db, p["slug"], "boss@example.com")
    check(pub["status"] == "published" and pub["published_at"] and pub["published_by"] == "boss@example.com", "publishing records who and when")
    counts = B.generate(db, "2026-11-14", limit=10, now=now)
    check(counts["kept"] == 1 and counts["replaced"] == 0, "a PUBLISHED post is never rewritten by generation: its URL is already out there")

    # ---------------- the public boundary
    r = anon.get(f"/api/blog/{p['slug']}")
    check(r.status_code == 200 and r.headers["content-type"].startswith("text/html"), "a visitor with no session gets the post as HTML")
    html = r.text
    check(html.startswith("<!doctype html>"), "it is a whole document, not a fragment")
    check("Bukayo Saka" in html and "81%" in html, "the forecast is IN THE HTML -- which is the entire point: a crawler never runs JavaScript")
    check("<script" not in html.replace('<script type="application/ld+json">', ""), "the page carries no JavaScript beyond the JSON-LD data block")
    check("script-src 'none'" in r.headers.get("content-security-policy", ""), "...and its CSP says so")
    for tag in ('property="og:title"', 'property="og:description"', 'property="og:url"', 'rel="canonical"', 'name="twitter:title"'):
        check(tag in html, f"the page carries {tag}")
    check('"@type":"NewsArticle"' in html, "and Article structured data")
    check("/sign-up?from=blog-mid" in html and "/sign-up?from=blog-end" in html, "both call-to-action boxes are there, and tell the analytics apart")
    check(html.count("sign-up?from=blog") >= 2, "...twice, after the forecasts and at the end")
    check("Not betting advice." in html, "the disclaimer travels with the post")
    check("/match/m900" in html, "a reader can open the full match in the app")
    check(html.count('class="box"') == 4, "four benefit boxes, as asked")
    check("track-record" in html, "and the track record is linked")

    # The same answer for a draft, a missing post and a bad slug: the slugs are guessable by design
    # (two club names and a date), so a different answer would leak what is coming.
    B.unpublish(db, p["slug"], "boss@example.com")
    r2 = anon.get(f"/api/blog/{p['slug']}")
    check(r2.status_code == 404, "an unpublished post is a 404 for visitors")
    check(anon.get("/api/blog/no-such-post-2026-01-01").status_code == 404, "...the same answer as one that never existed")
    check(anon.get("/api/blog/NOT_A_SLUG").status_code == 404, "...and as a slug that could not be ours")
    check("noindex" in r2.headers.get("x-robots-tag", ""), "a 404 asks crawlers to drop the URL")
    B.publish(db, p["slug"], "boss@example.com")

    # ---------------- who may work on it
    check(anon.get("/api/admin/blog").status_code in (401, 403), "signed-out visitors cannot open the blog screen")
    check(analyst.get("/api/admin/blog").status_code == 403, "an analyst has no content permission")
    r = admin.get("/api/admin/blog")
    check(r.status_code == 200 and len(r.json()["posts"]) >= 1, "an admin sees the list")
    check("items" not in (r.json()["posts"][0] or {}), "the list is a list: the forecasts are not shipped with every row")

    pv = admin.get(f"/api/admin/blog/{p['slug']}/preview")
    check(pv.status_code == 200 and "Bukayo Saka" in pv.text, "an admin previews the real page")
    check("noindex" in pv.headers.get("x-robots-tag", "") and pv.headers["cache-control"] == "no-store", "...and a preview is never indexed or cached")
    check(anon.get(f"/api/admin/blog/{p['slug']}/preview").status_code in (401, 403), "a visitor cannot reach the preview")

    # ---------------- editing: wording yes, numbers no
    r = admin.put(f"/api/admin/blog/{p['slug']}", json={"title": "Arsenal v Chelsea: what we expect"})
    check(r.status_code == 200 and r.json()["post"]["title"] == "Arsenal v Chelsea: what we expect", "an admin may rewrite the title")
    check(r.json()["post"]["items"][0]["pct"] == "81%", "...and the numbers are untouched by it")
    r = admin.put(f"/api/admin/blog/{p['slug']}", json={"intro": "Our best picks for the weekend."})
    check(r.status_code == 400 and r.json()["error"]["code"] == "BANNED_WORDS", "an edit carrying a banned word is refused")
    check(db.blog_posts.find_one({"slug": p["slug"]})["intro"] != "Our best picks for the weekend.", "...and nothing was saved")

    # Publishing re-checks, because an edit is where a banned word gets in.
    db.blog_posts.update_one({"slug": p["slug"]}, {"$set": {"status": "draft", "intro": "Tipsters love this one."}})
    r = admin.post(f"/api/admin/blog/{p['slug']}/publish", json={})
    check(r.status_code == 400 and r.json()["error"]["code"] == "BANNED_WORDS", "publishing re-checks the copy and refuses")
    check(db.blog_posts.find_one({"slug": p["slug"]})["status"] == "draft", "...and the post stays a draft")
    db.blog_posts.update_one({"slug": p["slug"]}, {"$set": {"intro": "A clean opening."}})
    check(admin.post(f"/api/admin/blog/{p['slug']}/publish", json={}).status_code == 200, "cleaned up, it publishes")

    # ---------------- the index, the switch, and the sitemap
    r = anon.get("/api/blog")
    check(r.status_code == 200 and "Arsenal" in r.text, "the index lists the published post")
    locs = [u["loc"] for u in SEO.urls(db, now=now)]
    check(f"/api/blog/{p['slug']}" in locs and "/api/blog" in locs, "a published post is in the sitemap")

    S.put(db, "blog.enabled", False, "boss@example.com")
    check(anon.get(f"/api/blog/{p['slug']}").status_code == 404 and anon.get("/api/blog").status_code == 404, "switching the blog off hides every post")
    check(not any(l.startswith("/api/blog") for l in [u["loc"] for u in SEO.urls(db, now=now)]), "...and takes them out of the sitemap")
    check(db.blog_posts.count_documents({}) >= 1, "...without deleting anything")
    S.put(db, "blog.enabled", True, "boss@example.com")

    # ---------------- a hostile name cannot end the document
    db.teams.update_one({"iid": 71}, {"$set": {"name": 'Chelsea</script><script>alert(1)</script>'}})
    db.blog_posts.delete_many({"slug": "arsenal-v-chelsea-2026-11-14"})
    bad = B.build_post(db, 900, now=now)
    B.upsert_draft(db, bad)
    B.publish(db, bad["slug"], "boss@example.com")
    html = anon.get(f"/api/blog/{bad['slug']}").text
    check("<script>alert(1)</script>" not in html, "a club name carrying markup is escaped, not injected")
    check("&lt;script&gt;" in html, "...and survives as text")

    # ---------------- old drafts are swept, published posts never
    db.blog_posts.insert_one({"slug": "stale-2020-01-01", "status": "draft", "kickoff": now - timedelta(days=60),
                              "title": "Old", "items": []})
    n = B.purge_old_drafts(db, days=14, now=now)
    check(n == 1 and db.blog_posts.find_one({"slug": "stale-2020-01-01"}) is None, "a draft for a match long gone is deleted")
    check(db.blog_posts.find_one({"slug": bad["slug"]}) is not None, "a published post is never swept")

    # ---------------- docs/73: a settled match says what happened
    # Reported from a real match page: every row on a game that had already been played still showed
    # its KICK-OFF time and said nothing about whether the forecast came in. The aggregate was in
    # `_recap` the whole time; what was missing was the per-row answer the screen needed.
    import queries as Q
    db.matches.update_one({"iid": 900}, {"$set": {"status": "final", "hg": 1, "ag": 2}})
    db.forecast_outcomes.insert_many([
        {"forecast_id": "f1", "fkey": "kf1", "tier": "Strong", "reached": True, "actual": 3.0, "player_played": True},
        {"forecast_id": "f2", "fkey": "kf2", "tier": "Solid", "reached": False, "actual": 2.0, "player_played": True},
        {"forecast_id": "f3", "fkey": "kf3", "tier": None, "reached": False, "actual": 0.0, "player_played": False},
    ])
    d = Q.match_detail(db, 900)
    by = {f["id"]: f for f in d["forecasts"]}
    check(all(f.get("status") == "final" for f in d["forecasts"]), "every forecast on a settled match carries the match status, so the row can say FT")
    check(by["f1"]["outcome"] == {"reached": True, "actual": 3.0, "played": True}, "a forecast that came in says so, with the number it reached")
    check(by["f2"]["outcome"]["reached"] is False and by["f2"]["outcome"]["actual"] == 2.0, "one that did not carries what actually happened, not just a no")
    check(by["f3"]["outcome"]["played"] is False, "a player who did not appear is marked as such rather than scored a miss")

    db.matches.update_one({"iid": 900}, {"$set": {"status": "scheduled"}})
    d = Q.match_detail(db, 900)
    check(all("outcome" not in f for f in d["forecasts"]), "a match still to be played carries no outcome at all")
    check(all(f["status"] == "scheduled" for f in d["forecasts"]), "...and says so")

    # ---------------- docs/73: a post for a match already played
    # Without this a post generated for a past fixture reads in the future tense with no score and
    # no results -- the same fault reported on the match page, in a second place. It is also the one
    # thing nobody else does: everyone's forecast page becomes a dead wrong page after the whistle.
    db.blog_posts.delete_many({})
    db.forecast_outcomes.delete_many({})
    db.teams.update_one({"iid": 71}, {"$set": {"name": "Chelsea"}})
    db.matches.update_one({"iid": 900}, {"$set": {"status": "final", "hg": 2, "ag": 1}})
    db.forecast_outcomes.insert_many([
        {"forecast_id": "f1", "fkey": "kf1", "tier": "Strong", "reached": True, "actual": 4.0, "player_played": True},
        {"forecast_id": "f2", "fkey": "kf2", "tier": "Solid", "reached": True, "actual": 5.0, "player_played": True},
        {"forecast_id": "f3", "fkey": "kf3", "tier": None, "reached": False, "actual": 0.0, "player_played": True},
    ])
    sp = B.build_post(db, 900, now=now)
    check(sp["final"] is True and sp["score"] == "2\u20131", "a settled post knows the match is over and what the score was")
    check("2\u20131" in sp["title"] and "predictions did" in sp["title"], f"the score is in the title: {sp['title']!r}")
    check("played" in sp["intro"] and "meet" not in sp["intro"], "the intro is in the past tense")
    check(sp["came_in"] == 2 and sp["scored_n"] == 3, "the tally counts what came in")
    check(sp["items"][0]["result"] == {"reached": True, "actual": 4.0, "played": True}, "each item carries its own result")
    check(sp["items"][2]["result"]["reached"] is False, "...including the one that did not come in")
    check(sp["items"][2]["needed"] == 2, "...and what was needed, so the miss can be quantified")

    B.upsert_draft(db, sp); B.publish(db, sp["slug"], "boss@example.com")
    html = anon.get(f"/api/blog/{sp['slug']}").text
    check("Happened \u2014 4" in html, "the page says it happened, and with what number")
    check("Did not happen \u2014 0, where 2 were needed" in html, "a miss is quantified, and the verb agrees with the number")
    check(">FT<" in html and "2\u20131" in html, "the fixture strip shows the score and FT, not a kick-off time")
    check("2 of the 3 forecasts in this post came in" in html, "the tally is on the page, stated plainly either way")
    check("What we said, and what happened" in html, "...under a heading that is honest about what the post is")

    # A player who did not appear was never scored, and saying "did not happen" about him would be a
    # different claim from the true one.
    db.forecast_outcomes.update_one({"forecast_id": "f3"}, {"$set": {"player_played": False}})
    db.blog_posts.delete_many({})
    sp2 = B.build_post(db, 900, now=now)
    check(sp2["scored_n"] == 2 and sp2["came_in"] == 2, "a player who did not play is left out of the tally")
    B.upsert_draft(db, sp2); B.publish(db, sp2["slug"], "boss@example.com")
    h2 = anon.get(f"/api/blog/{sp2['slug']}").text
    check("never scored" in h2 and "Did not happen \u2014 0" not in h2, "...and the page says he did not play rather than scoring him a miss")

    # ---------------- the share row
    check(h2.count('class="sh"') == 5, "five places to share it")
    for host in ("twitter.com/intent/tweet", "wa.me/?text=", "facebook.com/sharer", "reddit.com/submit", "mailto:?"):
        check(host in h2, f"...including {host.split('/')[0].split('?')[0]}")
    check(f"https://app.test/api/blog/{sp2['slug']}" in h2, "the address is printed for a reader to copy")
    check('rel="noopener noreferrer nofollow"' in h2, "share links carry noopener and nofollow")
    # The share row must not cost this page its one real property.
    check("<script" not in h2.replace('<script type="application/ld+json">', ""), "and it needed no JavaScript to do any of it")
    check("script-src 'none'" in anon.get(f"/api/blog/{sp2['slug']}").headers.get("content-security-policy", ""),
          "...so the CSP still forbids script outright")

    # A post for a match still to be played says none of this.
    db.matches.update_one({"iid": 900}, {"$set": {"status": "scheduled"}})
    db.blog_posts.delete_many({})
    up = B.build_post(db, 900, now=now)
    check(up["final"] is False and not up["score"], "an upcoming post is not marked final")
    check("meet" in up["intro"] and all(i["result"] is None for i in up["items"]), "...and carries no results at all")
    B.upsert_draft(db, up); B.publish(db, up["slug"], "boss@example.com")
    h3 = anon.get(f"/api/blog/{up['slug']}").text
    check(">FT<" not in h3 and "Three forecasts, and why" in h3, "...and reads as a preview, with no FT marker")
    check(h3.count('class="sh"') == 5, "an upcoming post can be shared too")

    # ---------------- the ten-game strip, and evidence before opinion
    db.blog_posts.delete_many({})
    db.forecast_outcomes.delete_many({})
    db.matches.update_one({"iid": 900}, {"$set": {"status": "scheduled"}})
    # Ten games on the shots line for Saka, oldest first, as queries._usual builds them.
    db.player_match_stats.delete_many({})
    db.player_match_stats.insert_many([
        {"player_iid": 700, "match_iid": 800 + i, "kickoff": KO - timedelta(days=70 - 7 * i),
         "minutes": 90, "opp_iid": 71, "home": i % 2 == 0, "pos": "FWD", "shots": v}
        for i, v in enumerate([1, 3, 2, 4, 0, 3, 3, 2, 5, 4])])
    ev = B.build_post(db, 900, now=now)
    it = ev["items"][0]
    check(len(it["run"]) == 10, f"the item carries the last ten games ({len(it['run'])})")
    check(it["played_n"] == 10 and it["cleared"] == 6, f"and the record on the line: {it['cleared']} of {it['played_n']}")
    check(it["needed"] == 3 and it["line"] == "3+ shots", "the line label and the needed count are the same number")
    check(any("reached 3+ in 6 of the last 10" in e for e in it["evidence"]), f"the record leads the why: {it['evidence'][:1]}")
    check(it["evidence"] and it["evidence"][0].startswith("He"), "a player is 'he', a club is 'they'")

    # Evidence is checkable; the engine's reasons are its read of the fixture. Order matters.
    B.upsert_draft(db, ev); B.publish(db, ev["slug"], "boss@example.com")
    h = anon.get(f"/api/blog/{ev['slug']}").text
    check('class="runwrap"' in h and h.count('class="run"') >= 1, "the strip is drawn on the page")
    check('<b>6</b> of 10' in h, "...with the count beside it")
    check(h.index("reached 3+ in 6 of the last 10") < h.index("Chelsea concede shots to wide forwards"),
          "the checkable record comes BEFORE the model's reasons")
    check("<script" not in h.replace('<script type="application/ld+json">', ""), "...and the strip needed no JavaScript")

    # Fewer than three games is not evidence of anything.
    db.player_match_stats.delete_many({"player_iid": 700})
    db.player_match_stats.insert_many([
        {"player_iid": 700, "match_iid": 860 + i, "kickoff": KO - timedelta(days=20 - i),
         "minutes": 90, "opp_iid": 71, "home": True, "pos": "FWD", "shots": 2} for i in range(2)])
    db.blog_posts.delete_many({})
    thin = B.build_post(db, 900, now=now)
    B.upsert_draft(db, thin); B.publish(db, thin["slug"], "boss@example.com")
    h2 = anon.get(f"/api/blog/{thin['slug']}").text
    check('class="runwrap"' not in h2, "two games draws no strip at all")

    # ---------------- availability is not a reason
    db.forecasts.update_one({"id": "f1"}, {"$set": {"reasons": [
        "He is in the announced eleven", "The opponent's style allows more shots"]}})
    db.blog_posts.delete_many({})
    av = B.build_post(db, 900, now=now)
    rs = av["items"][0]["reasons"]
    check("The opponent's style allows more shots" in rs, "a reason about the fixture is kept")
    check(not any("announced eleven" in r for r in rs), "a reason that only says he will be on the pitch is dropped")
    db.forecasts.update_one({"id": "f1"}, {"$set": {"reasons": [
        "Arsenal are expected to hold the ball in Chelsea's half", "Chelsea concede shots to wide forwards"]}})

    # ---------------- the day a batch is built for
    # A post has to exist BEFORE the match to be found by anyone searching the fixture.
    db.blog_posts.delete_many({})
    db.matches.update_one({"iid": 900}, {"$set": {"kickoff": now + timedelta(days=1)}})
    made = B.generate(db, now=now)
    check(made["created"] == 1, f"with no day given, the batch is built for TOMORROW's fixtures ({made})")
    db.blog_posts.delete_many({})
    check(B.generate(db, now.date().isoformat(), now=now)["created"] == 0, "...not today's")
    db.matches.update_one({"iid": 900}, {"$set": {"kickoff": KO}})

    # ---------------- a published post settles in place, same URL
    db.blog_posts.delete_many({})
    pre = B.build_post(db, 900, now=now)
    B.upsert_draft(db, pre); B.publish(db, pre["slug"], "boss@example.com")
    url_before = pre["slug"]
    check(B.refresh_settled(db, now=now) == 0, "a match still to be played settles nothing")
    db.matches.update_one({"iid": 900}, {"$set": {"status": "final", "hg": 2, "ag": 1}})
    check(B.refresh_settled(db, now=now + timedelta(days=1)) == 0,
          "final but nothing scored yet: left as a preview rather than claiming results it has not got")
    db.forecast_outcomes.insert_many([
        {"forecast_id": "f1", "fkey": "kf1", "tier": "Strong", "reached": True, "actual": 4.0, "player_played": True},
        {"forecast_id": "f2", "fkey": "kf2", "tier": "Solid", "reached": False, "actual": 2.0, "player_played": True},
    ])
    check(B.refresh_settled(db, now=now + timedelta(days=1)) == 1, "once scored, the post settles")
    done = db.blog_posts.find_one({"slug": url_before}, {"_id": 0})
    check(done["slug"] == url_before, "THE URL DOES NOT CHANGE: the link that was shared still works")
    check(done["status"] == "published" and done["final"] is True, "it is still published, and now marked final")
    check("predictions did" in done["title"] and "2\u20131" in done["title"], "the title turned over with it")
    check(done["came_in"] == 1 and done["scored_n"] == 2, "and the tally is the scored items only")
    check(done["items"][0]["result"]["reached"] is True, "results are attached by forecast id, item by item")
    check(B.refresh_settled(db, now=now + timedelta(days=1)) == 0, "settling is idempotent")

    # ---------------- docs/75: the tier words, and the one place they are decided
    import tiering as TI
    check(TI.TIER_LABEL == {"Strong": "Strong", "Solid": "Solid", "Watch": "Watch"},
          "the stored tiers map to the reader's words in one place")
    check(BR.TIER_WORD["Strong"] == TI.TIER_LABEL["Strong"], "the blog reads that map rather than keeping its own")
    check(BR.TIER_WORD["lower"] == "No badge", "...and names the no-badge case for a reader who has never seen a badge")

    # The ad canvas draws the same words. It cannot import the app (it runs on a canvas and is kept
    # free of app imports), so its copy of the map is pinned here instead -- an ad is the FIRST place
    # a stranger meets the badge, and it must not teach a vocabulary the app contradicts.
    draw = open(os.path.join(HERE_FE, "src", "admin", "ads", "draw.js"), encoding="utf-8").read()
    for stored, words in TI.TIER_LABEL.items():
        check(f'{stored}: "{words}"' in draw, f"the ad canvas draws {words!r} for {stored}")
    copy_js = open(os.path.join(HERE_FE, "src", "lib", "copy.js"), encoding="utf-8").read()
    for stored, words in TI.TIER_LABEL.items():
        check(f'label: "{words}"' in copy_js, f"the app's badge says {words!r} too")
    # The badge says Strong because the engine grades the LIKELIHOOD. The help sentence has to
    # describe the rule actually in force, or the badge and its own explanation disagree -- which is
    # the fault this whole exercise was about.
    check("90% or more" in BR._tier_help(db, "Strong"), "with likelihood grading, Strong explains itself as a likelihood")
    S.put(db, "engine.personal_lines", True, "boss@example.com")
    check("gap" in BR._tier_help(db, "Strong"), "...and with personal lines on, as a gap from usual")
    S.put(db, "engine.personal_lines", False, "boss@example.com")
    check("90% or more" in BR._tier_help(db, "Strong"), "...switching back switches the sentence back")

    # ---------------- docs/75: titles carry the search
    t, d, _ = B.words(final=False, hn="Arsenal", an="Chelsea", when="11 November 2026", score="",
                      scored_n=0, came_in=0, lead={"subject": "Saka", "line": "3+ shots", "pct": "81%"})
    check(t == "Arsenal vs Chelsea prediction, stats and team news", f"a preview title carries the search: {t!r}")
    check(" v " not in t, "...with 'vs', which is what people type")
    check(not TG.scan(t) and not TG.scan(d), "...and clears the copy rules")
    # Two of the longest names in the league: the title must still fit AND still be a sentence.
    for a, b in [("Brighton & Hove Albion", "Wolverhampton Wanderers"),
                 ("Borussia Monchengladbach", "Eintracht Frankfurt")]:
        for fin, sc in ((False, ""), (True, "0\u20130")):
            t, d, _ = B.words(final=fin, hn=a, an=b, when="11 November 2026", score=sc, scored_n=3,
                              came_in=2, lead={"subject": "X", "line": "1+ shots", "pct": "50%"})
            check(len(t) <= B.MAX_TITLE and len(d) <= B.MAX_DESC, f"{a} v {b}: inside the limits ({len(t)}/{len(d)})")
            check(not t.split()[-1].lower() in ("our", "and", "the", "how", "with", "of", "a"),
                  f"...and does not end on a dangling word: {t!r}")
            check(a in t and b in t, "...with both clubs still named")

print("PASS")
