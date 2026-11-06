"""Site Studio over HTTP: roles, validation, draft / preview / publish / rollback, images, CSS safety, mobile admin menu."""
from testkit import *
import base64 as b64
import site_studio as SS

PNG = b64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==")

with TestClient(srv.app) as owner:
    admin, support, analyst = boot(owner)
    anon = TestClient(srv.app)

    # ---------------- who can open it
    check(anon.get("/api/admin/site/draft").status_code in (401, 403), "signed-out visitors cannot open Site Studio")
    check(support.get("/api/admin/site/draft").status_code == 403 and analyst.get("/api/admin/site/draft").status_code == 403, "support and analyst have no Site Studio")
    r = admin.get("/api/admin/site/draft"); j = r.json()
    check(r.status_code == 200 and j["dirty"] is False and j["live_v"] == 0 and j["can_edit_css"] is False, "admin opens the studio; nothing is unsaved; css is owner only")
    check(owner.get("/api/admin/site/draft").json()["can_edit_css"] is True, "owner can edit custom CSS")
    m = j["meta"]
    # 10 presets: Forest is the default now, and Carbon is kept beside it the way Midnight, Apple
    # and Chalk were kept when each of them stopped being the default.
    check(len(m["fonts"]) >= 12 and "calendar" in m["icons"] and len(m["presets"]) == 10 and len(m["color_tokens"]) == 23, "editor options: fonts, icons, presets, 23 colour tokens")
    check(m["presets"][0]["id"] == "forest", "Forest leads the preset list, because it is the default")

    # ---------------- public config before anything is published
    r = anon.get("/api/site/config"); cfg = r.json()
    check(r.status_code == 200 and cfg["v"] == 0 and cfg["brand"]["name"] == "Forecast" and "--brand" in cfg["theme"]["css"], "visitors get working defaults before anything is published")
    check(all(k not in r.text for k in ("password", "secret", "stripe", "api_key")), "site config holds nothing secret")
    etag = r.headers["etag"]
    check(anon.get("/api/site/config", headers={"If-None-Match": etag}).status_code == 304, "unchanged config answers 304")
    check(cfg["disclaimer"].startswith("Statistical analysis") and cfg["popups_enabled"] is True and cfg["tracking"]["enabled"] is False, "disclaimer, popups switch and tracking state included")

    # ---------------- editing the draft: validation
    def put(client, section, data): return client.put(f"/api/admin/site/draft/{section}", json={"data": data})
    base_brand = dict(cfg["brand"])
    r = put(admin, "brand", {**base_brand, "name": ""})
    check(r.status_code == 422 and r.json()["error"]["code"] == "SITE_INVALID" and r.json()["error"]["problems"][0]["path"] == "brand.name", "empty brand name: field-level error")
    r = put(admin, "brand", {**base_brand, "tagline": "Best odds in town"})
    check(r.status_code == 422 and "odds" in r.text, "banned words refused in site text")
    r = put(admin, "brand", {**base_brand, "logo_light": "javascript:alert(1)"})
    check(r.status_code == 422, "javascript: image address refused")
    r = put(admin, "brand", {**base_brand, "nonsense": 1})
    check(r.status_code == 422 and "Unknown field" in r.text, "unknown fields refused (typos never silently do nothing)")
    r = put(admin, "brand", {**base_brand, "name": "Pitchside"})
    check(r.status_code == 200 and r.json()["sections_changed"] == ["brand"], "valid brand saved to the draft")
    check(anon.get("/api/site/config").json()["brand"]["name"] == "Forecast", "visitors still see the old name until Publish")
    d = admin.get("/api/admin/site/draft").json()
    check(d["dirty"] and d["updated_by"] == "admin@example.com" and d["draft"]["brand"]["name"] == "Pitchside", "draft shows who changed it")
    check(admin.get("/api/admin/site/diff").json()["changed"][0]["draft"]["name"] == "Pitchside", "diff shows live against draft")

    # ---------------- preview
    tok = admin.post("/api/admin/site/preview-token").json()
    check(tok["expires_in"] == 1800 and tok["url"].startswith("https://app.test/?preview="), "preview link made")
    pv = anon.get(f"/api/site/config?preview={tok['token']}")
    check(pv.status_code == 200 and pv.json()["brand"]["name"] == "Pitchside" and pv.json()["preview"] is True and pv.headers["cache-control"] == "no-store" and pv.headers["x-robots-tag"] == "noindex", "preview shows the draft, is never cached or indexed")
    check(anon.get("/api/site/config?preview=garbage").status_code == 403, "bad preview token refused")
    old = SS.preview_token(db.users.find_one({"email": "admin@example.com"})["id"], now=time.time() - 4000)
    check(anon.get(f"/api/site/config?preview={old}").status_code == 403, "expired preview token refused")
    check(analyst.post("/api/admin/site/preview-token").status_code == 403, "analyst cannot make preview links")

    # ---------------- publish
    check(analyst.post("/api/admin/site/publish", json={}).status_code == 403 and support.post("/api/admin/site/publish", json={}).status_code == 403, "only people with publish rights can publish")
    r = admin.post("/api/admin/site/publish", json={"note": "New name"})
    check(r.status_code == 200 and r.json()["v"] == 1, "published as version 1")
    c2 = anon.get("/api/site/config")
    check(c2.json()["brand"]["name"] == "Pitchside" and c2.json()["v"] == 1 and c2.headers["etag"] != etag, "visitors see it, with a new ETag")
    check(admin.post("/api/admin/site/publish", json={}).status_code == 422, "nothing to publish when there are no changes")
    check(admin.get("/api/admin/site/draft").json()["dirty"] is False, "the draft is clean after publishing")
    check(db.audit_log.find_one({"action": "site.publish", "actor": "admin@example.com"}) is not None, "publish is in the audit log")

    # ---------------- theme: colours, contrast, fonts, presets
    th = admin.get("/api/admin/site/draft").json()["draft"]["theme"]
    bad = json.loads(json.dumps(th)); bad["colors"]["dark"]["text"] = "#101820"
    r = put(admin, "theme", bad)
    check(r.status_code == 422 and "4.5:1" in r.text, "unreadable text colour blocked (contrast)")
    bad = json.loads(json.dumps(th)); bad["colors"]["light"]["brand"] = "red"
    check(put(admin, "theme", bad).status_code == 422, "colour must be #RRGGBB")
    bad = json.loads(json.dumps(th)); bad["font_body"] = "comic-sans"
    check(put(admin, "theme", bad).status_code == 422, "font must come from the list")
    bad = json.loads(json.dumps(th)); del bad["colors"]["dark"]["chart3"]
    check(put(admin, "theme", bad).status_code == 422, "every colour token is required")
    r = admin.post("/api/admin/site/draft/preset", json={"key": "pitch"})
    check(r.status_code == 200, "preset 'Pitch green' applied to the draft")
    ok = admin.get("/api/admin/site/draft").json()["draft"]["theme"]
    ok["font_body"] = "manrope"; ok["default_mode"] = "dark"
    check(put(admin, "theme", ok).status_code == 200, "font and default mode changed")
    check(admin.post("/api/admin/site/draft/preset", json={"key": "nope"}).status_code == 422, "unknown preset refused")
    for k in ("apple", "sunset", "ocean", "contrast", "daylight", "midnight", "pitch"):
        check(admin.post("/api/admin/site/draft/preset", json={"key": k}).status_code == 200, f"preset {k} passes the contrast rules")
    admin.post("/api/admin/site/draft/preset", json={"key": "pitch"})
    th = admin.get("/api/admin/site/draft").json()["draft"]["theme"]; th["font_body"] = "manrope"; th["font_heading"] = "playfair-display"; th["default_mode"] = "dark"
    put(admin, "theme", th)

    # ---------------- buttons
    bt = admin.get("/api/admin/site/draft").json()["draft"]["buttons"]
    x = json.loads(json.dumps(bt)); x["variants"]["primary"] = "ghost"
    check(put(admin, "buttons", x).status_code == 422, "the main button cannot be invisible")
    x = json.loads(json.dumps(bt)); x["height_px"]["md"] = 30
    check(put(admin, "buttons", x).status_code == 422, "buttons must be at least 40 px (touch size)")
    x = json.loads(json.dumps(bt)); x["focus_ring_px"] = 0
    check(put(admin, "buttons", x).status_code == 422, "keyboard focus ring cannot be removed")
    x = json.loads(json.dumps(bt)); x["variants"]["primary"] = "outline"; x["radius_px"] = 999; x["uppercase"] = True; x["hover"] = "darken"
    check(put(admin, "buttons", x).status_code == 200, "button style changed (outline, pill, caps, darken on hover)")

    # ---------------- navigation
    nav = admin.get("/api/admin/site/draft").json()["draft"]["nav"]
    x = json.loads(json.dumps(nav)); x["mobile_tabs"] = ["today", "finder", "insights", "teams", "learn"]
    check(put(admin, "nav", x).status_code == 422, "phone bar holds 4 items plus More, not 5")
    x = json.loads(json.dumps(nav)); x["mobile_tabs"] = ["today", "ghost"]
    check(put(admin, "nav", x).status_code == 422, "phone bar can only hold real menu items")
    x = json.loads(json.dumps(nav)); x["items"][0]["route"] = "javascript:alert(1)"
    check(put(admin, "nav", x).status_code == 422, "javascript: link refused")
    x = json.loads(json.dumps(nav)); x["items"][0]["route"] = "//evil.example.com"
    check(put(admin, "nav", x).status_code == 422, "protocol-relative link refused")
    x = json.loads(json.dumps(nav)); x["items"][1]["id"] = "today"
    check(put(admin, "nav", x).status_code == 422, "duplicate menu id refused")
    x = json.loads(json.dumps(nav)); x["items"][2]["label"] = "Sure bets"
    check(put(admin, "nav", x).status_code == 422, "banned word in a menu label refused")
    x = json.loads(json.dumps(nav)); x["items"][0]["icon"] = "skull"
    check(put(admin, "nav", x).status_code == 422, "icons come from the list")
    x = json.loads(json.dumps(nav)); x["items"].append({"id": "stats", "label": "Stats", "icon": "bar-chart", "route": "/stats", "enabled": True, "audience": "all", "badge": "New"}); x["mobile_tabs"] = ["today", "stats", "finder"]
    r = put(admin, "nav", x)
    check(r.status_code == 200, "new menu item added and placed in the phone bar")
    x["items"][0]["enabled"] = False
    check(put(admin, "nav", x).status_code == 422, "an item in the phone bar cannot be switched off")
    x["items"][0]["enabled"] = True

    # ---------------- footer, SEO, cookies, home
    ft = admin.get("/api/admin/site/draft").json()["draft"]["footer"]
    x = json.loads(json.dumps(ft)); x["social"] = [{"kind": "x", "url": "http://x.com/a"}]
    check(put(admin, "footer", x).status_code == 422, "social links must be https")
    x = json.loads(json.dumps(ft)); x["columns"] = [{"title": "Product", "links": [{"label": "Today", "route": "/"}]}]
    r = put(admin, "footer", x)
    check(r.status_code == 200 and any("/terms" in w["message"] for w in r.json()["warnings"]), "missing Terms link is a warning, not an error")
    put(admin, "footer", ft)
    seo = admin.get("/api/admin/site/draft").json()["draft"]["seo"]
    x = json.loads(json.dumps(seo)); x["redirects"] = [{"from": "/a", "to": "/b", "code": 301}, {"from": "/b", "to": "/a", "code": 301}]
    check(put(admin, "seo", x).status_code == 422, "redirect loop refused")
    x = json.loads(json.dumps(seo)); x["redirects"] = [{"from": "/admin/x", "to": "/", "code": 301}]
    check(put(admin, "seo", x).status_code == 422, "cannot redirect /admin")
    x = json.loads(json.dumps(seo)); x["title_template"] = "{name} {bogus}"
    check(put(admin, "seo", x).status_code == 422, "unknown placeholder refused")
    x = json.loads(json.dumps(seo)); x["redirects"] = [{"from": "/old-finder", "to": "/finder", "code": 301}]
    check(put(admin, "seo", x).status_code == 200, "redirect saved")
    ck = admin.get("/api/admin/site/draft").json()["draft"]["cookies"]
    x = dict(ck); x["reject_label"] = ""
    check(put(admin, "cookies", x).status_code == 422, "the cookie banner must offer a 'no' button")
    hm = admin.get("/api/admin/site/draft").json()["draft"]["home"]
    x = {"blocks": [{"id": b["id"], "enabled": False} for b in hm["blocks"]]}
    check(put(admin, "home", x).status_code == 422, "home page needs at least one block")

    # ---------------- custom CSS: owner only, filtered
    css_ok = ".card{border-radius:4px}"
    check(put(admin, "custom_css", {"css": css_ok}).status_code == 403, "admin cannot change custom CSS")
    check(admin.post("/api/admin/site/draft/custom_css/reset", json={"to": "default"}).status_code == 403, "admin cannot reset custom CSS either")
    for evil, why in (("@import url(https://evil.test/x.css);", "@import"), ("a{background:url(https://evil.test/p.png)}", "external url"), ("a{width:expression(alert(1))}", "expression"),
                      ("</style><script>alert(1)</script>", "html"), ("a{color:red", "unbalanced braces"), ("@font-face{font-family:x;src:url(/f.woff2)}", "font-face"), ("a{background:url(//evil.test/p.png)}", "protocol-relative url")):
        check(put(owner, "custom_css", {"css": evil}).status_code == 422, f"custom CSS blocks {why}")
    check(put(owner, "custom_css", {"css": ".x{background:url(/api/site/assets/abc)}" + css_ok}).status_code == 200, "owner saves safe CSS (local url allowed)")

    # ---------------- publish everything, check the compiled output
    r = admin.post("/api/admin/site/publish", json={"note": "Pitch green, new nav"})
    check(r.status_code == 200 and r.json()["v"] == 2, "version 2 published")
    c = anon.get("/api/site/config").json()
    css = c["theme"]["css"]
    check("--brand:#34D399" in css and '[data-theme="light"]' in css and "@layer custom{" in css and ".btn--primary{background:transparent;color:var(--brand);border-color:var(--brand)}" in css, "compiled CSS: tokens for both modes, outline primary button, custom layer")
    check("--btn-radius:999px" in css and "--btn-case:uppercase" in css and "@media (pointer:coarse)" in css and ".btn:focus-visible" in css, "button shape, case, 44px touch size and focus ring are in the CSS")
    check({f["slug"] for f in c["theme"]["fonts"]} == {"manrope", "playfair-display"} and c["theme"]["fonts"][0]["url"].startswith("/fonts/"), "only the fonts in use are listed, self-hosted")
    check(c["nav"]["mobile_tabs"] == ["today", "stats", "finder"] and any(i["id"] == "stats" and i["badge"] == "New" for i in c["nav"]["items"]), "new menu and phone bar are live")
    check(c["redirects"] == [{"from": "/old-finder", "to": "/finder", "code": 301}] and c["theme"]["default_mode"] == "dark", "redirects and default mode are live")
    check(all(k not in css for k in ("<", ">", "javascript:", "@import")), "no markup or script can reach the browser through the CSS")

    # ---------------- versions and rollback
    v = admin.get("/api/admin/site/versions").json()
    check(v["live_v"] == 2 and [x["v"] for x in v["versions"]] == [2, 1] and v["versions"][0]["changed"] and "data" not in v["versions"][0], "version list: newest first, with what changed")
    check(admin.get("/api/admin/site/versions/1").json()["data"]["brand"]["name"] == "Pitchside", "an old version can be opened")
    check(analyst.post("/api/admin/site/rollback/1").status_code == 403, "analyst cannot roll back")
    r = admin.post("/api/admin/site/rollback/1")
    check(r.status_code == 200 and r.json()["v"] == 3, "rollback publishes the old version as version 3 (history is never rewritten)")
    c = anon.get("/api/site/config").json()
    check(c["nav"]["mobile_tabs"] != ["today", "stats", "finder"] and f"--brand:{SS.DARK['brand']}" in c["theme"]["css"], "the site is back to version 1's look")
    check(admin.post("/api/admin/site/rollback/99").status_code == 422, "rollback to a missing version refused")
    # conflict: draft opened on an older live version
    put(admin, "brand", {**base_brand, "name": "Third Name"})
    db.site_state.update_one({"_id": "state"}, {"$set": {"draft_base_v": 1}})
    r = admin.post("/api/admin/site/publish", json={})
    check(r.status_code == 409 and r.json()["error"]["code"] == "PUBLISH_CONFLICT", "publishing over someone else's newer version is stopped")
    check(admin.post("/api/admin/site/publish", json={"force": True}).status_code == 200, "...unless you choose to override")
    check(admin.post("/api/admin/site/draft/discard").status_code == 200, "discard works on a clean draft")
    put(admin, "brand", {**base_brand, "name": "Scratch"}); admin.post("/api/admin/site/draft/discard")
    check(admin.get("/api/admin/site/draft").json()["draft"]["brand"]["name"] == "Third Name", "discard drops unsaved changes")
    admin.put("/api/admin/site/draft/brand", json={"data": {**base_brand, "name": "Scratch"}}); admin.post("/api/admin/site/draft/brand/reset", json={"to": "live"})
    check(admin.get("/api/admin/site/draft").json()["draft"]["brand"]["name"] == "Third Name", "reset one section to the live version")

    # ---------------- images
    def upload(client, name, raw): return client.post("/api/admin/site/assets", json={"name": name, "data_b64": b64.b64encode(raw).decode()})
    check(upload(analyst, "logo.png", PNG).status_code == 403, "analyst cannot upload")
    r = upload(admin, "logo.png", PNG)
    check(r.status_code == 200 and r.json()["mime"] == "image/png" and r.json()["url"].startswith("/api/site/assets/"), "PNG uploaded")
    asset = r.json()
    g = anon.get(asset["url"])
    check(g.status_code == 200 and g.headers["content-type"] == "image/png" and g.headers["x-content-type-options"] == "nosniff" and "sandbox" in g.headers["content-security-policy"] and "immutable" in g.headers["cache-control"], "image served safely: right type, nosniff, sandboxed, cached")
    check(upload(admin, "x.png", b"<svg xmlns='http://www.w3.org/2000/svg'><script>alert(1)</script></svg>").status_code == 400, "SVG refused (it can carry script)")
    check(upload(admin, "x.png", b"not an image at all").status_code == 400, "a file renamed .png but not an image is refused (checked by content)")
    check(upload(admin, "big.png", PNG + b"\0" * (600 * 1024)).status_code in (400, 413, 422), "over 512 KB refused")
    check(anon.get("/api/site/assets/" + "0" * 32).status_code == 404 and anon.get("/api/site/assets/../../etc/passwd").status_code in (404, 422), "unknown image id gives 404")
    check(len(admin.get("/api/admin/site/assets").json()["assets"]) == 1, "image library lists it")
    br = admin.get("/api/admin/site/draft").json()["draft"]["brand"]; br["logo_light"] = asset["url"]
    check(put(admin, "brand", br).status_code == 200, "logo set from the library")
    check(admin.delete(f"/api/admin/site/assets/{asset['id']}").status_code == 409, "an image in use cannot be deleted")
    admin.post("/api/admin/site/publish", json={"note": "logo"})
    br["logo_light"] = ""; put(admin, "brand", br)
    check(admin.delete(f"/api/admin/site/assets/{asset['id']}").status_code == 409, "...still protected while the live site uses it")
    admin.post("/api/admin/site/publish", json={"note": "no logo"})
    check(admin.delete(f"/api/admin/site/assets/{asset['id']}").status_code == 200 and anon.get(asset["url"]).status_code == 404, "unused image deleted")
    big = b64.b64encode(PNG + b"\0" * (300 * 1024)).decode()
    check(admin.post("/api/admin/site/assets", json={"name": "ok.png", "data_b64": big}).status_code == 200, "a 300 KB image gets through the body-size guard")
    check(admin.put("/api/admin/site/draft/brand", json={"data": {**base_brand, "tagline": "x" * 3_000_000}}).status_code == 413, "other routes keep the small body limit")

    # ---------------- the admin menu (desktop rail and phone bottom bar)
    sh = owner.get("/api/admin/shell").json()
    ids = {m["id"] for m in sh["modules"]}
    check({"studio", "popups", "integrations", "staff", "keys", "settings", "users", "analytics"} <= ids and sh["groups"][0] == "Overview"
          and {"Football data", "Marketing", "Website"} <= set(sh["groups"]), "owner menu: every module, in groups")
    check({"feeds", "pitchapi", "sportapi"} <= ids, "the owner's menu reaches both football providers (docs/43)")
    check(1 < len(sh["mobile_tabs"]) <= 4 and all(t in ids for t in sh["mobile_tabs"]), "phone bottom bar: up to 4 modules plus More")
    a_ids = {m["id"] for m in admin.get("/api/admin/shell").json()["modules"]}
    check("staff" not in a_ids and "studio" in a_ids and "keys" in a_ids, "admin menu: no Staff; Keys is viewable but owner-only to change")
    an_sh = analyst.get("/api/admin/shell").json(); an_ids = {m["id"] for m in an_sh["modules"]}
    check("studio" not in an_ids and "settings" not in an_ids and "analytics" in an_ids and "popups" in an_ids and "payments" in an_ids, "analyst menu: numbers only")
    su_ids = {m["id"] for m in support.get("/api/admin/shell").json()["modules"]}
    check("analytics" not in su_ids and "users" in su_ids and "inbox" in su_ids and "studio" not in su_ids, "support menu: people and inbox only")
    check(admin.put("/api/admin/shell/tabs", json={"ids": ["dashboard", "studio", "popups", "analytics"]}).status_code == 200 and admin.get("/api/admin/shell").json()["mobile_tabs"] == ["dashboard", "studio", "popups", "analytics"], "staff pick their own phone bar")
    check(admin.put("/api/admin/shell/tabs", json={"ids": ["dashboard", "staff"]}).status_code == 400, "cannot pin a module you may not use")
    check(admin.put("/api/admin/shell/tabs", json={"ids": ["dashboard"]}).status_code == 400 and admin.put("/api/admin/shell/tabs", json={"ids": ["dashboard", "users", "inbox", "logs", "health"]}).status_code in (400, 422), "2 to 4 tabs only")
    fan = TestClient(srv.app)
    fan.post("/api/auth/register", json={"email": "fan@example.com", "password": "fan-user-pass-1"}); fan.post("/api/auth/verify-email", json={"token": token_from("fan@example.com", "Confirm")})
    fan.post("/api/auth/login", json={"email": "fan@example.com", "password": "fan-user-pass-1"})
    check(fan.get("/api/admin/shell").status_code == 403 and fan.get("/api/admin/site/draft").status_code == 403 and fan.put("/api/admin/site/draft/brand", json={"data": {}}).status_code == 403, "a normal member gets 403 on every studio route")
    check(fan.get("/api/site/config").status_code == 200, "...but still gets the public site config")

    # ---------------- words everywhere
    texts = json.dumps(SS.defaults())
    import textguard
    check(textguard.find(SS.defaults()) == [] and not textguard.scan(texts.replace(textguard.DISCLAIMER, "")), "built-in site text contains no banned words")
    check(textguard.scan("Statistical analysis for information and entertainment. Not betting advice.") == [] and textguard.scan("great odds") == ["odds"], "only the exact disclaimer may contain a banned word")

print("\nALL STUDIO CHECKS PASSED")
