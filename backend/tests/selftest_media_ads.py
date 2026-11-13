"""Media library (images and video, public addresses, Range) and the ad builder (docs/60)."""
from testkit import *
import base64 as b64
import site_studio as SS
import ads as AD

PNG = b64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==")
# A real MP4 header: four bytes of box length, then "ftyp", then the brand. Padded past one chunk so
# the chunked path and a Range read across a chunk boundary are both exercised.
MP4 = b"\x00\x00\x00\x20ftypisom" + b"\x00" * (SS.CHUNK_BYTES + 5000)
WEBM = b"\x1a\x45\xdf\xa3" + b"\x00" * 2048

with TestClient(srv.app) as owner:
    admin, support, analyst = boot(owner)
    anon = TestClient(srv.app)

    # ---------------- sniffing, before any HTTP is involved
    check(SS.sniff(PNG) == "image/png" and SS.sniff(MP4) == "video/mp4" and SS.sniff(WEBM) == "video/webm", "PNG, MP4 and WebM are recognised")
    check(SS.sniff(b"<svg xmlns='x'></svg>") is None and SS.sniff(b"MZ\x90\x00") is None, "SVG and anything unknown are refused")
    check(SS.kind_of("video/mp4") == "video" and SS.kind_of("image/png") == "image", "kind follows the mime")

    # ---------------- who may upload
    def up(client, name, raw): return client.put(f"/api/admin/media/upload?name={name}", content=raw)
    check(anon.put("/api/admin/media/upload?name=x.png", content=PNG).status_code in (401, 403), "a signed-out visitor cannot upload")
    check(up(support, "x.png", PNG).status_code == 403 and up(analyst, "x.png", PNG).status_code == 403, "support and analyst have no upload")

    # ---------------- an image: raw bytes in, an absolute address out
    r = up(admin, "logo.png", PNG); j = r.json()
    check(r.status_code == 200 and j["kind"] == "image" and j["mime"] == "image/png", "an image uploads as raw bytes")
    check(j["url"] == f"/api/site/assets/{j['id']}" and j["abs_url"].endswith(j["url"]) and j["abs_url"].startswith("http"),
          "the address comes back absolute, which is the only kind that works in an e-mail")
    img = j
    g = anon.get(img["url"])
    check(g.status_code == 200 and g.content == PNG and g.headers["cache-control"].startswith("public") and g.headers["accept-ranges"] == "bytes",
          "anyone can read it, cached for a year, ranges advertised")
    check(anon.get(img["url"], headers={"If-None-Match": g.headers["etag"]}).status_code == 304, "an unchanged file answers 304")

    # ---------------- a video: chunked, and seekable
    r = up(admin, "clip.mp4", MP4); vid = r.json()
    check(r.status_code == 200 and vid["kind"] == "video" and vid["bytes"] == len(MP4), "a video uploads whole")
    row = db.site_assets.find_one({"_id": vid["id"]})
    check("data" not in row and row["chunks"] == 2 and db.site_asset_chunks.count_documents({"aid": vid["id"]}) == 2,
          "the bytes are in chunks, not on the row")
    g = anon.get(vid["url"])
    check(g.status_code == 200 and g.content == MP4, "the whole file is reassembled in order")
    # a range that crosses the chunk boundary is the one that catches an off-by-one in the maths
    lo, hi = SS.CHUNK_BYTES - 10, SS.CHUNK_BYTES + 9
    g = anon.get(vid["url"], headers={"Range": f"bytes={lo}-{hi}"})
    check(g.status_code == 206 and g.content == MP4[lo:hi + 1] and g.headers["content-range"] == f"bytes {lo}-{hi}/{len(MP4)}",
          "a range across the chunk boundary returns exactly those bytes")
    g = anon.get(vid["url"], headers={"Range": "bytes=-100"})
    check(g.status_code == 206 and g.content == MP4[-100:], "a suffix range returns the tail")
    check(anon.get(vid["url"], headers={"Range": f"bytes={len(MP4) + 5}-"}).status_code == 416, "a range past the end is 416")

    # ---------------- limits
    setting("media.max_image_kb", 1)
    check(up(admin, "big.png", PNG + b"\x00" * 4000).status_code == 400, "an image over the limit is refused")
    setting("media.max_image_kb", 512)
    setting("media.max_video_mb", 1)
    check(up(admin, "big.mp4", MP4).status_code == 400, "a video over the limit is refused")
    setting("media.max_video_mb", 25)
    lim = admin.get("/api/admin/site/assets").json()
    check(lim["max_image_bytes"] == 512 * 1024 and lim["max_video_bytes"] == 25 * 1024 * 1024 and lim["max_bytes"] == 512 * 1024,
          "the screen is told both limits, and max_bytes keeps its old meaning")
    check({a["kind"] for a in lim["assets"]} == {"image", "video"}, "the library lists both kinds")

    # ---------------- in use, and deleting
    tpl = db.email_templates.find_one({}) or {}
    if tpl:
        db.email_templates.update_one({"_id": tpl["_id"]}, {"$set": {"html": f"<img src='{img['abs_url']}'>"}})
        check(admin.delete(f"/api/admin/site/assets/{img['id']}").status_code == 409, "a file used by an e-mail template cannot be deleted")
        db.email_templates.update_one({"_id": tpl["_id"]}, {"$set": {"html": "<p>none</p>"}})
    check(admin.delete(f"/api/admin/site/assets/{vid['id']}").status_code == 200, "a video deletes")
    check(db.site_asset_chunks.count_documents({"aid": vid["id"]}) == 0, "...and takes its chunks with it, leaving nothing behind")
    check(anon.get(vid["url"]).status_code == 404, "...and the address stops answering")

    # ---------------- the ad builder
    check(anon.get("/api/admin/ads").status_code in (401, 403), "a signed-out visitor cannot open the ad builder")
    r = admin.get("/api/admin/ads"); a = r.json()
    # Eight from docs/60 section 2, and the match before and after from section 4.
    ids = [t["id"] for t in a["catalogue"]["templates"]]
    check(r.status_code == 200 and len(ids) == 11 and {"faceoff", "verdict", "results"} <= set(ids) and len(a["catalogue"]["sizes"]) == 5,
          "eleven templates (the three match ads among them) and five sizes")
    sq = next(s for s in a["catalogue"]["sizes"] if s["id"] == "square")
    check(sq["w"] == 1080 and sq["h"] == 1080, "a square exports at the real 1080, not an upscale")
    b = a["brand"]
    check(b["colors"]["dark"]["bg"].startswith("#") and b["colors"]["light"]["bg"].startswith("#"),
          "the palette comes from Site Studio, both modes, so an ad cannot hold a stale hex")
    check(b["font"]["body_family"] and b["font"]["faces"] and b["font"]["faces"][0]["url"].startswith("/fonts/"),
          "the typeface is named and its file is self-hosted, so the canvas can load it")
    check(b["disclaimer"].startswith("Statistical analysis"), "the disclaimer travels with the brand kit")

    # saving
    good = {"template": "card", "size": "portrait", "mode": "dark", "name": "Tonight", "kicker": "Forecast",
            "subhead": "His last ten and this match", "fkeys": ["a", "b"]}
    check(support.post("/api/admin/ads", json=good).status_code == 403, "support cannot save an ad")
    r = admin.post("/api/admin/ads", json=good); d = r.json()
    check(r.status_code == 200 and d["name"] == "Tonight" and d["size"] == "portrait" and d["fkeys"] == ["a", "b"], "an ad saves")
    r = admin.post("/api/admin/ads", json={**good, "headline": "Best odds tonight"})
    check(r.status_code == 400 and "odds" in r.text, "a headline with a banned word is refused, as a popup's would be")
    r = admin.post("/api/admin/ads", json={**good, "template": "nope"})
    check(r.status_code == 400, "an unknown template is refused")
    r = admin.put(f"/api/admin/ads/{d['id']}", json={**good, "name": "Renamed"})
    check(r.status_code == 200 and r.json()["name"] == "Renamed" and len(admin.get("/api/admin/ads").json()["designs"]) == 1, "editing replaces rather than adds")
    check(AD.normalise({**good, "accent": "red"})["accent"] == "" and AD.normalise({**good, "accent": "#A9FF9B"})["accent"] == "#A9FF9B",
          "only a plain hex is kept as an accent")
    check(len(AD.normalise({**good, "fkeys": [str(i) for i in range(40)]})["fkeys"]) == AD.MAX_SLIDES, "the slide count is capped")
    check(admin.delete(f"/api/admin/ads/{d['id']}").status_code == 200 and admin.delete(f"/api/admin/ads/{d['id']}").status_code == 404, "an ad deletes once")

    # ---------------- the menu
    sh = admin.get("/api/admin/shell").json()
    mk = {m["id"]: m for m in sh["modules"]}
    check(mk["ads"]["group"] == "Marketing" and mk["media"]["group"] == "Marketing" and mk["media"]["label"] == "Media",
          "both tools sit under Marketing")
    check(mk["media"]["route"] == "/admin/media", "the Images route is unchanged, so an old bookmark still lands")

    # ------------------------------------------------------------ the batch for tomorrow
    import ad_plan as AP
    import datetime as _dt

# ---------------------------------------------------------------- the batch for tomorrow
    tomorrow = (_dt.datetime.now(_dt.timezone.utc) + _dt.timedelta(days=1))
    day = tomorrow.date().isoformat()
    ko = tomorrow.replace(hour=19, minute=0, second=0, microsecond=0)

    # three leagues, four clubs each, with enough players and markets for the planner to vary
    LGS = [(9001, "Premier League"), (9002, "La Liga"), (9003, "Serie A")]
    STATS = ["shots", "sot", "tackles"]
    for lid, lname in LGS:
        db.leagues.update_one({"iid": lid}, {"$set": {"iid": lid, "id": f"l{lid}", "ext_id": f"x-l{lid}", "name": lname}}, upsert=True)
    pid = tid = mid = 9000
    for lid, _ in LGS:
        for t in range(4):
            tid += 1
            db.teams.update_one({"iid": tid}, {"$set": {"iid": tid, "id": f"t{tid}", "ext_id": f"x-t{tid}", "name": f"Club {tid}", "league_iid": lid}}, upsert=True)
        for m in range(2):
            mid += 1
            home, away = tid - 3 + m * 2, tid - 2 + m * 2
            db.matches.update_one({"iid": mid}, {"$set": {"iid": mid, "id": f"m{mid}", "ext_id": f"x-m{mid}", "league_iid": lid, "home_iid": home, "away_iid": away,
                                   "kickoff": ko, "status": "scheduled"}}, upsert=True)
            for k in range(6):
                pid += 1
                team = home if k < 3 else away
                db.players.update_one({"iid": pid}, {"$set": {"iid": pid, "id": f"p{pid}", "ext_id": f"x-p{pid}", "name": f"Player {pid}", "team_iid": team, "pos": "FWD"}}, upsert=True)
                # season volume, which is how the planner knows who is famous
                for g in range(8):
                    db.player_match_stats.insert_one({"player_iid": pid, "team_iid": team, "league_iid": lid,
                                                      "match_iid": 900 + g, "kickoff": ko - _dt.timedelta(days=7 * (g + 1)),
                                                      "minutes": 90, "goals": pid % 5, "assists": 1,
                                                      "shots": 3, "sot": 1, "tackles": 2})
                for si, st in enumerate(STATS):
                    db.forecasts.insert_one({
                        "id": f"f{pid}{si}", "fkey": f"k{pid}-{st}", "is_current": True, "hidden": False, "carrier": False,
                        "scope": "player", "stat": st, "thr": 1.5, "p": 0.6 + (pid % 7) * 0.04, "lo": 0.55, "hi": 0.9,
                        "tier": "Strong" if si == 0 else "Solid", "market": f"2+ {st}", "kickoff": ko,
                        "league_iid": lid, "match_iid": mid, "team_iid": team, "opp_iid": away if team == home else home,
                        "player_iid": pid, "pos": "FWD", "run": [{"v": 2, "m": 90}] * 10})
            db.team_match_stats.insert_many([
                {"team_iid": home, "league_iid": lid, "match_iid": 900 + g, "kickoff": ko, "opp_iid": away, "home": True,
                 "goals": 2, "shots": 14, "shots_against": 9, "sot": 5, "sot_against": 3,
                 "corners": 6, "corners_against": 4, "tackles": 15, "tackles_against": 16} for g in range(8)])

    plan = AP.plan(db, day, 0, 20)
    ads = plan["ads"]
    check(len(ads) == 20, f"the batch is the twenty that were asked for (got {len(ads)})")
    check(plan["kicker"] == ko.strftime("%a %-d %b").upper() and "TONIGHT" not in plan["kicker"],
          f"every ad is kicked by the DATE, not 'tonight' ({plan['kicker']})")
    check(all(a["size"] in ("square", "portrait", "story") for a in ads), "square and vertical only; no landscape in the batch")
    check({a["mode"] for a in ads} == {"dark", "light"}, "both light and dark are in the batch")
    check(len({a["template"] for a in ads}) >= 4, "at least four kinds of ad, not twenty of one")
    keys = [k for a in ads for k in a["fkeys"] if a["template"] in ("card", "run")]
    players = [k.split("-")[0] for k in keys]
    check(len(players) == len(set(players)), "no player carries two ads of his own")
    stats = {k.split("-", 1)[1] for k in keys if "-" in k}
    check(len(stats) >= 2, f"the batch spreads across markets, not just shots ({sorted(stats)})")
    lgs = {db.forecasts.find_one({"fkey": k})["league_iid"] for k in keys}
    check(len(lgs) >= 2, f"the batch spreads across leagues ({sorted(lgs)})")
    check(all(a["kicker"] == plan["kicker"] for a in ads), "the date is on every ad in the batch")

    # The honesty guard on a record ad. Three slices, three outcomes: too small, well calibrated,
    # and a slice we were simply wrong about. Only the middle one may become an image.
    def outcome(tag, i, league, stat, p_, hit):
        db.forecast_outcomes.insert_one({"forecast_id": f"o-{tag}{i}", "fkey": f"o-{tag}{i}", "league_iid": league,
                                         "stat": stat, "scope": "player", "tier": "Strong", "p": p_,
                                         "reached": hit, "player_played": True})
    for i in range(60):
        outcome("small", i, 9001, "shots", 0.8, True)
    for i in range(200):
        outcome("good", i, 9002, "sot", 0.85, i % 7 != 0)          # said 85, happened 86
    for i in range(200):
        outcome("bad", i, 9003, "tackles", 0.9, i % 3 != 0)        # said 90, happened 67
    sl = AP.record_slices(db, 150)
    got = {(x["league_iid"], x["stat"]) for x in sl}
    check((9001, "shots") not in got, "a slice with sixty forecasts behind it is too small to put on an ad")
    check((9003, "tackles") not in got, "a slice we were wrong about is never an ad, however high the percentage")
    good = next((x for x in sl if (x["league_iid"], x["stat"]) == (9002, "sot")), None)
    check(good and good["n"] == 200 and 0.84 <= good["actual"] <= 0.88,
          "a well-calibrated slice is offered, with its sample size, so the ad can print it")

    # over HTTP, with the default date being tomorrow
    r = admin.get("/api/admin/ads/day", params={"tz": 0, "count": 12})
    j = r.json()
    check(r.status_code == 200 and j["day"] == day and len(j["ads"]) == 12, "the day route defaults to tomorrow and honours the count")
    check(len(j["cards"]) > 0 and all("image" in (c.get("player") or {}) or c.get("player") is None for c in j["cards"][:3]),
          "the cards travel with the batch, so the browser draws without a second call")
    check(analyst.get("/api/admin/ads/day").status_code == 403, "an analyst cannot open the batch")
    check(admin.get("/api/admin/ads/day", params={"date": "not-a-date"}).status_code == 400, "a bad date is refused")


print("\nALL MEDIA AND AD CHECKS PASSED")
