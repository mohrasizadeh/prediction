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
    check(r.status_code == 200 and len(a["catalogue"]["templates"]) == 8 and len(a["catalogue"]["sizes"]) == 5, "eight templates and five sizes")
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

print("\nALL MEDIA AND AD CHECKS PASSED")
