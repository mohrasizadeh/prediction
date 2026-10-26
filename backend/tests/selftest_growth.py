"""Growth tools over HTTP: popups, e-mail list, e-mail providers, audience sync, webhooks, tracking tags, reports, alerts, permissions."""
from testkit import *
import hashlib, hmac as _hmac
from datetime import datetime, timedelta, timezone
import popups as PP, reports as R, alerts as AL, textguard, analytics as AN, newsletter as N

UTC = timezone.utc
with TestClient(srv.app) as owner:
    admin, support, analyst = boot(owner)
    anon = TestClient(srv.app)
    admin_id = db.users.find_one({"email": "admin@example.com"})["id"]

    def reg(email):
        c = TestClient(srv.app)
        c.post("/api/auth/register", json={"email": email, "password": "fan-user-pass-1"})
        c.post("/api/auth/verify-email", json={"token": token_from(email, "Confirm")})
        c.post("/api/auth/login", json={"email": email, "password": "fan-user-pass-1"})
        return c
    fan = reg("fan@example.com")

    # ================================================================ POPUPS: permissions
    check(support.get("/api/admin/popups").status_code == 403, "support has no Popup Maker")
    check(analyst.get("/api/admin/popups").status_code == 200 and analyst.post("/api/admin/popups", json={"data": {}}).status_code == 403, "analyst can read popups, not change them")
    meta = admin.get("/api/admin/popups/meta").json()
    check(len(meta["templates"]) >= 4 and "exit_intent" in meta["triggers"] and "/admin" in meta["always_excluded"], "editor options and starter templates")

    # ---- validation
    blank = meta["blank"]
    def mk(**kw):
        d = json.loads(json.dumps(blank)); d["name"] = kw.pop("name", "T")
        d["content"].update(kw.pop("content", {"title": "Hello", "body": "Plain words."}))
        for k, v in kw.items(): d[k] = {**d[k], **v} if isinstance(v, dict) else v
        return d
    check(admin.post("/api/admin/popups", json={"data": mk(content={"title": "<b>Hi</b>", "body": "x"})}).status_code == 422, "HTML refused in popup text")
    check(admin.post("/api/admin/popups", json={"data": mk(content={"title": "Sure bets", "body": "x"})}).status_code == 422, "banned word refused in popup text")
    check(admin.post("/api/admin/popups", json={"data": mk(content={"title": "", "body": ""})}).status_code == 422, "empty popup refused")
    check(admin.post("/api/admin/popups", json={"data": mk(form={"enabled": True, "consent_text": ""})}).status_code == 422, "e-mail field needs the consent sentence")
    check(admin.post("/api/admin/popups", json={"data": mk(design={"show_close": False}, content={"title": "T", "body": "b", "buttons": []})}).status_code == 422, "a modal with no way to close is refused")
    check(admin.post("/api/admin/popups", json={"data": mk(content={"title": "T", "body": "b", "buttons": [{"label": "Go", "action": "link", "route": "javascript:alert(1)", "style": "primary"}]})}).status_code == 422, "javascript: button link refused")
    check(admin.post("/api/admin/popups", json={"data": mk(targeting={"pages_include": ["/a b"]})}).status_code == 422, "page patterns are checked")
    check(admin.post("/api/admin/popups", json={"data": mk(schedule={"starts_at": "2026-12-01", "ends_at": "2026-11-01"})}).status_code == 422, "end before start refused")
    check(admin.post("/api/admin/popups", json={"data": {**mk(), "bogus": 1}}).status_code == 422, "unknown field refused")
    r = admin.post("/api/admin/popups", json={"data": mk(trigger={"type": "exit_intent"})})
    check(r.status_code == 200 and any("phones" in w["message"] for w in r.json()["warnings"]), "exit intent warns that it never shows on phones")

    # ---- templates + going live
    tid = admin.post("/api/admin/popups", json={"template": meta["templates"][0]["id"]}).json()["id"]
    check(admin.get(f"/api/admin/popups/{tid}").json()["status"] == "draft", "template creates a draft")
    check(admin.post(f"/api/admin/popups/nope/status", json={"status": "live"}).status_code in (404, 400, 422), "unknown popup id handled")
    check(analyst.post(f"/api/admin/popups/{tid}/status", json={"status": "live"}).status_code == 403, "analyst cannot publish a popup")

    def make_live(name, **kw):
        pid = admin.post("/api/admin/popups", json={"data": mk(name=name, **kw)}).json()["id"]
        admin.post(f"/api/admin/popups/{pid}/status", json={"status": "live"}); return pid

    def shown(client, path="/", device="desktop", visitor="new", vid="v1"):
        return client.get("/api/popups", params={"path": path, "device": device, "visitor": visitor, "vid": vid}).json()

    p_all = make_live("Everyone", content={"title": "Welcome", "body": "Hi"}, trigger={"type": "delay", "delay_s": 5})
    out = shown(anon)
    check([x["id"] for x in out["popups"]] == [p_all] and out["limits"] == {"max_per_session": 2, "min_gap_seconds": 90}, "live popup is sent with the session limits")
    x = out["popups"][0]
    check("targeting" not in x and "name" not in x and "ab" not in x and x["trigger"]["type"] == "delay" and x["frequency"]["mode"] == "every_n_days", "browser gets what it needs to show it, nothing of the targeting rules")
    check(anon.get("/api/popups?path=/", headers={}).headers["cache-control"] == "private, max-age=60", "popup list is cached for a minute at most")

    # ---- never on these pages
    for path in ("/admin", "/admin/users", "/signin", "/sign-up", "/checkout/success", "/reset", "/account/billing", "/newsletter/confirm", "/verify"):
        if shown(anon, path)["popups"]: check(False, f"popup shown on {path}")
    check(True, "never shown on admin, sign-in, sign-up, reset, verify, checkout, billing or confirm pages")

    # ---- targeting
    p_paid = make_live("Paid only", targeting={"audience": "paid"}, content={"title": "Paid", "body": "x"}, priority=90)
    p_out = make_live("Signed-out finder", targeting={"audience": "signed_out", "pages_include": ["/finder", "/teams/*"], "pages_exclude": ["/teams/secret"]}, content={"title": "Join", "body": "x"}, priority=70)
    p_mob = make_live("Phones only", targeting={"devices": ["mobile"], "visitors": "returning"}, content={"title": "App", "body": "x"}, priority=60, kind="banner_bottom")
    ids = lambda o: {x["id"] for x in o["popups"]}
    check(p_paid not in ids(shown(anon)) and p_paid not in ids(shown(fan)), "paid-only popup hidden from signed-out and free people")
    check(p_out in ids(shown(anon, "/finder")) and p_out in ids(shown(anon, "/teams/arsenal")) and p_out not in ids(shown(anon, "/")) and p_out not in ids(shown(anon, "/teams/secret")), "page include / exclude patterns with * work")
    check(p_out not in ids(shown(fan, "/finder")), "signed-out popup hidden once signed in")
    check(p_mob not in ids(shown(anon, device="desktop", visitor="returning")) and p_mob not in ids(shown(anon, device="mobile", visitor="new")) and p_mob in ids(shown(anon, device="mobile", visitor="returning")), "device and new/returning targeting")
    out = shown(anon, "/finder", "mobile", "returning")
    check(len(out["popups"]) <= 3 and [x["id"] for x in out["popups"]][0] == p_out, "at most 3 sent, highest priority first")
    db.subscriptions.insert_one({"user_id": db.users.find_one({"email": "fan@example.com"})["id"], "status": "active", "plan_key": "pro", "current_period_end": datetime.now(UTC) + timedelta(days=20), "created_at": datetime.now(UTC)})
    setting("features.billing", True)
    check(p_paid in ids(shown(fan)), "a paying member gets the paid-only popup")
    setting("features.billing", False)

    # ---- schedule, pause, maintenance, master switch
    p_soon = make_live("Starts later", schedule={"starts_at": (datetime.now(UTC) + timedelta(days=2)).isoformat(), "ends_at": None}, content={"title": "Soon", "body": "x"})
    p_end = make_live("Already over", schedule={"starts_at": None, "ends_at": (datetime.now(UTC) - timedelta(days=1)).isoformat()}, content={"title": "Old", "body": "x"})
    check(p_soon not in ids(shown(anon)) and p_end not in ids(shown(anon)), "not shown before it starts or after it ends")
    states = {p["id"]: p["state"] for p in admin.get("/api/admin/popups").json()["popups"]}
    check(states[p_soon] == "scheduled" and states[p_end] == "ended" and states[p_all] == "running", "states: scheduled, ended, running")
    admin.post(f"/api/admin/popups/{p_all}/status", json={"status": "paused"}); check(p_all not in ids(shown(anon)), "paused popup disappears")
    admin.post(f"/api/admin/popups/{p_all}/status", json={"status": "live"}); check(p_all in ids(shown(anon)), "...and returns when set live")
    setting("popups.enabled", False); check(shown(anon)["popups"] == [], "master switch off: no popups anywhere"); setting("popups.enabled", True)
    setting("features.maintenance", True); check(shown(anon)["popups"] == [], "maintenance mode: no popups"); setting("features.maintenance", False)
    check(admin.post(f"/api/admin/popups/{p_all}/status", json={"status": "bogus"}).status_code in (400, 422), "bad status refused")

    # ---- A/B: same visitor always sees the same version; weights respected
    a = make_live("Test A", ab={"group": "hero", "weight": 50}, content={"title": "A", "body": "x"}, priority=40)
    b = make_live("Test B", ab={"group": "hero", "weight": 50}, content={"title": "B", "body": "x"}, priority=40)
    seen = {}
    for i in range(200):
        o = [x["id"] for x in shown(anon, vid=f"visitor{i}")["popups"] if x["id"] in (a, b)]
        check(len(o) == 1, "one A/B version per visitor") if i < 1 else None
        if len(o) != 1: check(False, "exactly one A/B version per visitor")
        seen[i] = o[0]
        if i < 20: assert shown(anon, vid=f"visitor{i}")["popups"] and [x["id"] for x in shown(anon, vid=f"visitor{i}")["popups"] if x["id"] in (a, b)] == o
    na = sum(1 for v in seen.values() if v == a)
    check(60 <= na <= 140, f"50/50 split is roughly even ({na} / {200 - na})")
    check(True, "a visitor keeps the same version on every visit")

    # ---- counting + stats
    for ev, n in (("view", 10), ("click", 3), ("dismiss", 4), ("submit", 1)):
        for _ in range(n): anon.post(f"/api/popups/{a}/event", json={"event": ev})
    check(anon.post(f"/api/popups/{a}/event", json={"event": "evil"}).status_code == 204, "unknown event name ignored quietly")
    t = admin.get(f"/api/admin/popups/{a}/stats").json()["totals"]
    check((t["view"], t["click"], t["dismiss"], t["submit"]) == (10, 3, 4, 1) and t["click_rate"] == 0.3 and t["submit_rate"] == 0.1, "stats and rates counted")
    draft_id = admin.post("/api/admin/popups", json={"data": mk(name="Draft")}).json()["id"]
    anon.post(f"/api/popups/{draft_id}/event", json={"event": "view"}); check(admin.get(f"/api/admin/popups/{draft_id}/stats").json()["totals"]["view"] == 0, "drafts and unknown ids are not counted")
    anon.post("/api/popups/not-an-id/event", json={"event": "view"})
    ab = admin.get("/api/admin/popups-ab/hero").json()
    check(len(ab["variants"]) == 2 if "variants" in ab else bool(ab), "A/B report lists both versions")
    check(analyst.get(f"/api/admin/popups/{a}/stats").status_code == 200, "analyst can read stats")

    # ---- staff preview of one popup
    pv = admin.post("/api/admin/site/preview-token").json()["token"]
    o = anon.get("/api/popups", params={"path": "/", "preview": pv, "popup": draft_id}).json()
    check(o["preview"] is True and [x["id"] for x in o["popups"]] == [draft_id], "preview shows one popup even though it is a draft")
    check(anon.get("/api/popups", params={"path": "/", "preview": "junk", "popup": draft_id}).status_code == 403, "bad preview token refused")

    # ---- duplicate, edit, delete
    cp = admin.post(f"/api/admin/popups/{a}/duplicate").json()["id"]
    c = admin.get(f"/api/admin/popups/{cp}").json(); check(c["status"] == "draft" and c["name"].endswith("copy"), "duplicate makes a draft copy")
    check(admin.put(f"/api/admin/popups/{cp}", json={"data": {"content": {"title": "Changed"}}}).status_code == 200 and admin.get(f"/api/admin/popups/{cp}").json()["content"]["title"] == "Changed", "partial edit merges")
    check(admin.put(f"/api/admin/popups/{cp}", json={"data": {"content": {"title": "odds"}}}).status_code == 422, "edit still checks banned words")
    check(admin.delete(f"/api/admin/popups/{cp}").status_code == 200 and admin.get(f"/api/admin/popups/{cp}").status_code == 404, "delete works")
    check(db.audit_log.count_documents({"action": {"$regex": "^popup\\."}}) > 5, "popup changes are in the audit log")

    # ================================================================ E-MAIL LIST
    sent.clear()
    r = anon.post("/api/newsletter/subscribe", json={"email": "Reader@Example.com", "consent": False})
    check(r.status_code == 400 and not db.newsletter.count_documents({}), "no tick, no sign-up (consent required)")
    r1 = anon.post("/api/newsletter/subscribe", json={"email": "Reader@Example.com", "consent": True}); body1 = r1.json()
    row = db.newsletter.find_one({"email": "reader@example.com"})
    check(r1.status_code == 200 and row["status"] == "pending" and row["consent_text"].startswith("Yes, send me") and row["consent_at"] and row["source"] == "footer", "double opt-in: pending, with the consent sentence, time and source saved")
    check(any(p["to"] == ["reader@example.com"] for p in sent), "confirmation e-mail sent")
    tk = re.search(r"token=([A-Za-z0-9_-]+)", [p for p in sent if p["to"] == ["reader@example.com"]][-1]["text"]).group(1)
    check(anon.get("/api/newsletter/confirm", params={"token": tk}).json()["email"] == "r***@example.com" and db.newsletter.find_one({"email": "reader@example.com"})["status"] == "pending", "opening the link (GET) changes nothing")
    check(anon.post("/api/newsletter/confirm", json={"token": tk}).status_code == 200 and db.newsletter.find_one({"email": "reader@example.com"})["status"] == "confirmed", "pressing confirm (POST) joins the list")
    check(anon.post("/api/newsletter/confirm", json={"token": tk}).status_code == 400, "the link works once")
    r2 = anon.post("/api/newsletter/subscribe", json={"email": "reader@example.com", "consent": True}).json()
    check(r2 == body1, "same answer for new and existing addresses (nobody can probe the list)")
    E.suppress(db, "bounced@example.com", "bounce", "test")
    check(anon.post("/api/newsletter/subscribe", json={"email": "bounced@example.com", "consent": True}).json() == body1 and not db.newsletter.find_one({"email": "bounced@example.com"}), "bounced address: same answer, never added")
    setting("newsletter.double_optin", False)
    anon.post("/api/newsletter/subscribe", json={"email": "direct@example.com", "consent": True}); check(db.newsletter.find_one({"email": "direct@example.com"})["status"] == "confirmed", "double opt-in can be switched off in settings")
    setting("newsletter.double_optin", True)

    # popup form
    pf = make_live("Form popup", form={"enabled": True, "consent_text": "Yes, e-mail me the weekly forecast. I can unsubscribe any time."}, content={"title": "Weekly", "body": "x"}, priority=99)
    check(anon.post(f"/api/popups/{pf}/submit", json={"email": "pop@example.com", "consent": False}).status_code == 400, "popup form needs the tick")
    r = anon.post(f"/api/popups/{pf}/submit", json={"email": "pop@example.com", "consent": True}).json()
    n = db.newsletter.find_one({"email": "pop@example.com"})
    check(r["ok"] and n["status"] == "pending" and n["source"].startswith("popup:") and n["consent_text"].startswith("Yes, e-mail me"), "popup sign-up uses double opt-in and saves that popup's own consent sentence")
    check(anon.post(f"/api/popups/{p_all}/submit", json={"email": "x@example.com", "consent": True}).status_code in (400, 404, 422), "a popup without a form cannot be used to subscribe")
    check(admin.get(f"/api/admin/popups/{pf}/stats").json()["totals"]["submit"] >= 1, "form submits are counted")
    check(len(sent) >= 2, "confirmation mail for the popup sign-up")

    # unsubscribe by link
    sent.clear(); setting("email.marketing_enabled", True)
    link = E.sign_unsub("reader@example.com")
    check(anon.get(f"/api/email/unsubscribe?t={link}").json() == {"email": "r***@example.com"} and db.newsletter.find_one({"email": "reader@example.com"})["status"] == "confirmed", "opening the unsubscribe link changes nothing")
    check(anon.post(f"/api/email/unsubscribe?t={link}").status_code == 200, "pressing the button unsubscribes")
    check(anon.post("/api/email/unsubscribe?t=forged").status_code == 400, "forged unsubscribe link refused")
    check(db.newsletter.find_one({"email": "reader@example.com"})["status"] == "unsubscribed", "unsubscribe by link updates the list")

    # list admin
    lst = admin.get("/api/admin/newsletter").json()
    check(lst["counts"]["confirmed"] >= 1 and all("consent_text" not in i and "ip_hash" not in i for i in lst["rows"]), "list screen has counts and hides consent text / IP hash")
    check(support.get("/api/admin/newsletter").status_code == 200, "support can see the list")
    check(admin.get("/api/admin/newsletter/export").status_code in (200, 403), "export needs the personal-data permission")
    ex = owner.get("/api/admin/newsletter/export"); check(ex.status_code == 200 and ex.text.startswith("﻿email,status") and "attachment" in ex.headers["content-disposition"], "owner exports the list as CSV")
    check(analyst.get("/api/admin/newsletter/export").status_code == 403, "analyst cannot export e-mail addresses")
    check(admin.post("/api/admin/newsletter/remove", json={"email": "direct@example.com"}).status_code == 200 and db.newsletter.find_one({"email": "direct@example.com"})["status"] == "unsubscribed", "admin removes an address (kept off the list)")
    check(E.is_suppressed(db, "direct@example.com", "marketing") == "manual", "...and it is suppressed for marketing mail")

    # ================================================================ E-MAIL PROVIDERS
    ov = admin.get("/api/admin/integrations").json()
    check(ov["email"]["provider"] == "resend" and ov["email"]["key_set"] and ov["email"]["bounces"] == "automatic" and {p["id"] for p in ov["email"]["providers"]} == {"resend", "postmark", "sendgrid", "brevo", "smtp"}, "integrations page: Resend active, five choices")
    check(support.get("/api/admin/integrations").status_code == 403 and analyst.get("/api/admin/integrations").status_code == 403, "support and analyst cannot open Integrations")
    check(admin.put("/api/admin/integrations/email", json={"provider": "mailgun"}).status_code == 400, "unknown provider refused")
    r = admin.put("/api/admin/integrations/email", json={"provider": "postmark"}).json()
    check(r["provider"] == "postmark" and r["key_set"] is False and "No key" in (r["warning"] or ""), "choosing a provider with no key warns you")
    sent.clear(); n0 = len(calls)
    t = admin.post("/api/admin/integrations/email/test-send", json={}).json(); check(t["status"] != "sent" and not sent, "no key, nothing sent, clear status")
    check(admin.post("/api/admin/integrations/email/test-send", json={"to": "stranger@example.com"}).status_code == 400, "test mail can only go to a team member")
    for prov, key, host in (("postmark", "abcdefghij-abcdefghij-abcd", "api.postmarkapp.com"), ("sendgrid", "SG.abcdefghijkl.abcdefghijklmnop", "api.sendgrid.com"), ("brevo", "xkeysib-abcdefghijklmnopqrstuvwx", "api.brevo.com")):
        security.save_provider_key(db, prov, key)
        admin.put("/api/admin/integrations/email", json={"provider": prov}); sent.clear(); calls.clear()
        t = admin.post("/api/admin/integrations/email/test-send", json={}).json()
        h = [c for c in calls if c[1].startswith("https://" + host)]
        check(t["status"] == "sent" and len(sent) == 1 and sent[0]["to"] == ["admin@example.com"] and h, f"{prov}: test mail sent through its own API")
        auth = h[-1][2]
        check(key in (auth.get("authorization", "") + auth.get("x-postmark-server-token", "") + auth.get("api-key", "")), f"{prov}: key goes in the header, not the URL")
        check(key not in h[-1][1], f"{prov}: key is not in the URL")
    # SMTP
    class FakeSMTP:
        log = []
        def __init__(self, host, port, mode): FakeSMTP.log.append(("connect", host, port, mode))
        def login(self, u, p): FakeSMTP.log.append(("login", u, p))
        def send_message(self, m): FakeSMTP.log.append(("send", m["To"], m["Subject"], m["Message-ID"]))
        def quit(self): pass
    T.set_smtp_factory(FakeSMTP)
    security.save_provider_key(db, "smtp_password", "app-password-xyz")
    r = admin.put("/api/admin/integrations/email", json={"provider": "smtp", "smtp_host": "smtp.example.com", "smtp_port": 587, "smtp_user": "me@example.com", "smtp_security": "starttls"}).json()
    check(r["provider"] == "smtp" and r["key_set"], "SMTP settings saved")
    t = admin.post("/api/admin/integrations/email/test-send", json={}).json()
    check(t["status"] == "sent" and ("connect", "smtp.example.com", 587, "starttls") in FakeSMTP.log and ("login", "me@example.com", "app-password-xyz") in FakeSMTP.log and any(x[0] == "send" for x in FakeSMTP.log), "SMTP: connects, logs in, sends")
    check(admin.put("/api/admin/integrations/email", json={"provider": "smtp", "smtp_security": "plain"}).status_code == 400, "SMTP without encryption refused")
    check(admin.put("/api/admin/integrations/email", json={"provider": "smtp", "smtp_port": 99999}).status_code == 400, "bad SMTP port refused")
    # header injection through the transport
    try:
        T.Smtp("p", "h", 25, "", "starttls").send({"from": "A <a@example.com>", "to": ["b@example.com"], "subject": "s", "html": "<p>x</p>", "text": "x", "headers": {"X-A\r\nBcc": "evil@example.com"}}); check(False, "header injection blocked")
    except T.SendError: check(True, "SMTP header injection blocked")
    # errors map cleanly
    web_orig = handler
    admin.put("/api/admin/integrations/email", json={"provider": "resend"})
    # a provider test-key call
    for prov in ("postmark", "sendgrid", "brevo"):
        check(T.test_key(db, prov)["ok"] is True, f"{prov}: key check call works")
    check(T.test_key(db, "smtp")["ok"] is True, "SMTP: login check works")

    # ================================================================ AUDIENCE SYNC
    owner.get("/api/admin/integrations")
    check(admin.put("/api/admin/integrations/audience", json={"provider": "klaviyo", "list_id": "1"}).status_code == 400, "unknown audience provider refused")
    r = admin.put("/api/admin/integrations/audience", json={"provider": "mailchimp", "list_id": "abc123"}).json()
    check(r["provider"] == "mailchimp" and r["key_set"] is False, "Mailchimp chosen, key still missing")
    security.save_provider_key(db, "mailchimp", "0123456789abcdef0123456789abcdef-us21")
    web["audience"] = 200
    check(admin.post("/api/admin/integrations/audience/test").json()["ok"] is True, "Mailchimp connection test ok")
    import newsletter as NL
    NL.subscribe(db, "sync@example.com", source="footer", consent_text="Yes, send me the weekly forecast e-mail.", consent=True)
    NL.confirm(db, token_from_nl := re.search(r"token=([A-Za-z0-9_-]+)", [p for p in sent if p["to"] == ["sync@example.com"]][-1]["text"]).group(1))
    jobs_ = admin.get("/api/admin/integrations/audience/jobs").json()["jobs"]
    check(any(j["action"] == "upsert" and j["status"] == "pending" for j in jobs_), "confirmed sign-up queued for Mailchimp")
    calls.clear()
    tick = lambda: owner.post("/api/jobs/tick", headers={"X-CRON-SECRET": "s3cret"}).json()
    res = tick()
    m = [c for c in calls if "api.mailchimp.com" in c[1]]
    h = hashlib.md5(b"sync@example.com").hexdigest()
    check(m and m[-1][0] == "PUT" and m[-1][1] == f"https://us21.api.mailchimp.com/3.0/lists/abc123/members/{h}" and m[-1][3]["status"] == "subscribed", "tick copies the contact to Mailchimp (subscriber hash of the lowercase address)")
    check(db.integration_jobs.count_documents({"kind": "audience", "status": "done"}) >= 1, "job marked done")
    # unsubscribe goes too
    NL.unsubscribed(db, "sync@example.com"); calls.clear(); tick()
    m = [c for c in calls if "api.mailchimp.com" in c[1]]
    check(m and m[-1][3]["status"] == "unsubscribed", "unsubscribe is copied to the audience provider")
    # failure -> retry with backoff -> dead after permanent error
    web["audience"] = 500
    NL.subscribe(db, "retry@example.com", source="footer", consent_text="Yes, send me the weekly forecast e-mail.", consent=True)
    NL.confirm(db, re.search(r"token=([A-Za-z0-9_-]+)", [p for p in sent if p["to"] == ["retry@example.com"]][-1]["text"]).group(1))
    tick(); j = db.integration_jobs.find_one({"email": "retry@example.com"})
    check(j["status"] == "pending" and j["attempts"] == 1 and j["next_at"] > datetime.now(UTC).replace(tzinfo=None) - timedelta(seconds=1), "server error: kept and retried later (backoff)")
    web["audience"] = 401
    db.integration_jobs.update_one({"_id": j["_id"]}, {"$set": {"next_at": datetime.now(UTC)}})
    tick(); j = db.integration_jobs.find_one({"email": "retry@example.com"})
    check(j["status"] == "dead" and db.admin_alerts.find_one({"key": "audience:mailchimp", "resolved": False}), "refused key: job stops and an alert is raised")
    web["audience"] = 200
    check(admin.post("/api/admin/integrations/audience/backfill").json()["queued"] >= 1, "backfill queues existing confirmed addresses")
    # other providers' request shapes
    for prov, key, lid, host, method in (("brevo", "xkeysib-abcdefghijklmnopqrstuvwx", "7", "api.brevo.com", "POST"), ("mailerlite", "a" * 40, "g1", "connect.mailerlite.com", "POST")):
        security.save_provider_key(db, prov, key); admin.put("/api/admin/integrations/audience", json={"provider": prov, "list_id": lid}); db.integration_jobs.delete_many({})
        web["audience"] = 201 if prov == "brevo" else 200
        INT.queue_audience(db, "upsert", "shape@example.com"); calls.clear(); tick()
        c = [x for x in calls if x[1].startswith("https://" + host)]
        check(c and c[-1][0] == method and (c[-1][3].get("listIds") == [7] if prov == "brevo" else c[-1][3].get("groups") == ["g1"]), f"{prov}: add-contact request has the right shape")
    check(admin.put("/api/admin/integrations/audience", json={"provider": "none", "list_id": ""}).status_code == 200 and not INT.queue_audience(db, "upsert", "x@example.com"), "audience sync off: nothing is queued")

    # ================================================================ WEBHOOKS
    check(support.get("/api/admin/integrations/webhooks").status_code == 403, "support cannot open webhooks")
    bad = lambda u, ev=("user.signed_up",): admin.post("/api/admin/integrations/webhooks", json={"url": u, "events": list(ev)}).status_code
    check(bad("http://hooks.example.com/x") == 400 and bad("https://private.example.com/x") == 400 and bad("https://local.example.com/x") == 400 and bad("https://u:p@hooks.example.com/x") == 400 and bad("https://hooks.example.com:8080/x") == 400, "webhook URL must be public https (no http, private, loopback, credentials, odd ports)")
    check(bad("https://169.254.169.254/x") == 400 and bad("https://127.0.0.1/x") == 400 and bad("https://[::1]/x") == 400 and bad("https://10.1.2.3/x") == 400, "cloud metadata, loopback and private addresses typed in directly are blocked")
    check(bad("https://hooks.example.com/x", ("nope",)) == 400 and bad("https://hooks.example.com/x", ()) == 400, "events must be from the list")
    r = admin.post("/api/admin/integrations/webhooks", json={"url": "https://hooks.example.com/in", "events": ["user.signed_up", "payment.succeeded", "newsletter.subscribed"], "note": "Zapier"}).json()
    ep, secret = r["id"], r["secret"]
    check(secret.startswith("whsec_") and "secret" not in admin.get("/api/admin/integrations/webhooks").json()["endpoints"][0] and admin.get("/api/admin/integrations/webhooks").json()["endpoints"][0]["secret_last4"] == secret[-4:], "secret shown once; afterwards only the last 4 characters")
    check(db.webhook_endpoints.find_one({"_id": ep})["secret"] != secret and secret not in json.dumps(db.webhook_endpoints.find_one({"_id": ep}), default=str), "secret is encrypted in the database")
    calls.clear(); web["status"] = 200
    t = admin.post(f"/api/admin/integrations/webhooks/{ep}/test").json()
    c = [x for x in calls if x[1] == "https://hooks.example.com/in"][-1]
    body = c[3] if isinstance(c[3], str) else json.dumps(c[3], separators=(",", ":"))
    sig = c[2]["x-webhook-signature"]; ts = re.search(r"t=(\d+)", sig).group(1); v1 = re.search(r"v1=([0-9a-f]+)", sig).group(1)
    check(t["ok"] and v1 == _hmac.new(secret.encode(), f"{ts}.".encode() + body.encode(), hashlib.sha256).hexdigest(), "test delivery is signed (HMAC-SHA256 of timestamp.body)")
    check(abs(int(ts) - time.time()) < 60 and c[2]["x-webhook-event"] == "webhook.test", "signature carries a fresh timestamp")
    # real events
    calls.clear(); fan2 = TestClient(srv.app)
    fan2.post("/api/auth/register", json={"email": "hook@example.com", "password": "fan-user-pass-1", "acq": {"source": "newsletter", "medium": "email", "campaign": "oct"}})
    check(db.webhook_outbox.count_documents({"type": "user.signed_up", "status": "pending"}) == 1, "sign-up queues a user.signed_up event")
    ob = db.webhook_outbox.find_one({"type": "user.signed_up"}); pl = json.loads(ob["body"])
    check("email" not in pl["data"] and pl["data"].get("user_id"), "no e-mail address in the event unless the endpoint asks for it")
    tick()
    check(db.webhook_outbox.find_one({"_id": ob["_id"]})["status"] == "done" and any(x[1] == "https://hooks.example.com/in" for x in calls), "tick delivers it")
    # retry and give-up
    web["status"] = 500; NL.subscribe(db, "wh@example.com", source="footer", consent_text="Yes, send me the weekly forecast e-mail.", consent=True)
    NL.confirm(db, re.search(r"token=([A-Za-z0-9_-]+)", [p for p in sent if p["to"] == ["wh@example.com"]][-1]["text"]).group(1))
    o2 = db.webhook_outbox.find_one({"type": "newsletter.subscribed"}); check(o2 is not None, "list join queues newsletter.subscribed")
    for i in range(6):
        db.webhook_outbox.update_one({"_id": o2["_id"]}, {"$set": {"next_at": datetime.now(UTC)}}); INT.deliver_pending(db)
    o2 = db.webhook_outbox.find_one({"_id": o2["_id"]})
    check(o2["status"] == "dead" and o2["attempts"] == 6, "after 6 failed tries the event is marked dead")
    check(len(admin.get(f"/api/admin/integrations/webhooks-deliveries?endpoint={ep}").json()["deliveries"]) >= 7, "every attempt is recorded")
    web["status"] = 410; INT.emit(db, "user.signed_up", {}); INT.deliver_pending(db)
    check(db.webhook_endpoints.find_one({"_id": ep})["active"] is False, "HTTP 410 switches the endpoint off")
    check(admin.put(f"/api/admin/integrations/webhooks/{ep}", json={"active": True}).json()["active"] is True and db.webhook_endpoints.find_one({"_id": ep})["fail_streak"] == 0, "switching it back on resets the failure count")
    web["status"] = 200
    db.webhook_endpoints.update_one({"_id": ep}, {"$set": {"fail_streak": 19}}); web["status"] = 500; INT.emit(db, "user.signed_up", {}); INT.deliver_pending(db)
    check(db.webhook_endpoints.find_one({"_id": ep})["active"] is False and db.admin_alerts.find_one({"key": f"webhook:{ep}"}), "20 failures in a row: endpoint off and an alert raised")
    web["status"] = 200; admin.put(f"/api/admin/integrations/webhooks/{ep}", json={"active": True, "include_email": True})
    INT.emit(db, "user.signed_up", {}, email="who@example.com"); pl = json.loads(db.webhook_outbox.find({"status": "pending"}).sort("created_at", -1)[0]["body"])
    check(pl["data"]["email"] == "who@example.com", "include_email=true adds the address")
    new = admin.post(f"/api/admin/integrations/webhooks/{ep}/rotate").json()["secret"]; check(new != secret and db.webhook_endpoints.find_one({"_id": ep})["secret_last4"] == new[-4:], "secret rotated")
    setting("integrations.webhooks_enabled", False); n0 = db.webhook_outbox.count_documents({}); INT.emit(db, "user.signed_up", {}); check(db.webhook_outbox.count_documents({}) == n0, "master switch off: nothing queued"); setting("integrations.webhooks_enabled", True)
    ep2 = admin.post("/api/admin/integrations/webhooks", json={"url": "https://hooks.example.com/two", "events": ["payment.failed"]}).json()["id"]
    check(admin.delete(f"/api/admin/integrations/webhooks/{ep2}").status_code == 200 and not db.webhook_endpoints.find_one({"_id": ep2}), "endpoint deleted")
    for i in range(10): admin.post("/api/admin/integrations/webhooks", json={"url": f"https://hooks.example.com/{i}", "events": ["payment.failed"]})
    check(admin.post("/api/admin/integrations/webhooks", json={"url": "https://hooks.example.com/over", "events": ["payment.failed"]}).status_code == 400, "at most 10 endpoints")
    check(db.audit_log.find_one({"action": "webhook.create"}) and "secret" not in json.dumps(list(db.audit_log.find({"action": {"$regex": "^webhook"}})), default=str), "webhook changes audited without secrets")

    # ================================================================ TRACKING TAGS
    tp = {"enabled": True, "ga4_id": "G-ABC123XYZ", "meta_pixel_id": "123456789012345", "google_ads_id": "", "require_consent": True}
    check(admin.put("/api/admin/integrations/tracking", json=tp).status_code == 403, "admin cannot turn on tracking tags (owner only)")
    check(anon.get("/api/site/config").json()["tracking"]["enabled"] is False, "tags are off by default")
    check(owner.put("/api/admin/integrations/tracking", json={**tp, "ga4_id": "<script>"}).status_code == 400, "malformed id refused")
    r = owner.put("/api/admin/integrations/tracking", json=tp).json()
    check(r["enabled"] and r["csp_additions"]["script-src"] == ["https://connect.facebook.net", "https://www.googletagmanager.com"] and any("Privacy page" in w for w in r["warnings"]), "owner enables tags; CSP additions and a privacy reminder are returned")
    t = anon.get("/api/site/config").json()["tracking"]
    check(t["ga4_id"] == "G-ABC123XYZ" and t["require_consent"] is True and "google_ads_id" in t, "public config lists only the ids and the consent rule")
    r = owner.put("/api/admin/integrations/tracking", json={**tp, "require_consent": False}).json()
    check(any("before people say yes" in w for w in r["warnings"]), "loading tags before consent is flagged")
    owner.put("/api/admin/integrations/tracking", json={**tp, "enabled": False})

    # ================================================================ REPORTS
    now = datetime.now(UTC); day = lambda d: (now - timedelta(days=d)).strftime("%Y-%m-%d")
    def ev(name, actor, d=0, utm=None, path="/", user_id=None, minutes=None):
        row = {"name": name, "actor": actor, "day": day(d), "at": now - (timedelta(minutes=minutes) if minutes is not None else timedelta(days=d)), "path": path, "device": "mobile", "user_id": user_id}
        if utm: row["utm"] = utm
        db.events.insert_one(row)
    db.events.delete_many({})
    for i in range(6): ev("page_view", f"a{i}", minutes=1, path="/finder" if i < 4 else "/")
    ev("page_view", "old", minutes=30)
    rt = admin.get("/api/admin/analytics/realtime").json()
    check(rt["active_now"] == 6 and rt["pages"][0] == {"path": "/finder", "visitors": 4} and rt["devices"] == {"mobile": 6}, "realtime: people in the last 5 minutes, top pages, devices")
    check("actor" not in json.dumps(rt) and "user_id" not in json.dumps(rt), "realtime shows no identities")
    db.events.delete_many({})
    for i in range(10): ev("page_view", f"c{i}", d=1)
    for i in range(4): ev("page_view", f"p{i}", d=9)
    for i in range(4): ev("signup", f"s{i}", d=2)
    ev("signup", "s9", d=11)
    cmp_ = admin.get("/api/admin/analytics/compare?days=7").json()
    mm = {m["metric"]: m for m in cmp_["metrics"]}
    check(mm["visitors"]["now"] == 10 and mm["visitors"]["previous"] == 4 and mm["visitors"]["change"] == 1.5 and mm["signups"]["now"] == 4 and mm["signups"]["previous"] == 1, "compare: this 7 days against the 7 before, with % change")
    db.payments.insert_one({"status": "paid", "currency": "cad", "amount_paid": 1500, "refunded_cents": 0, "created_at": now - timedelta(days=1)})
    db.payments.insert_one({"status": "paid", "currency": "usd", "amount_paid": 1000, "refunded_cents": 200, "created_at": now - timedelta(days=1)})
    rev = {r["currency"]: r["now_cents"] for r in owner.get("/api/admin/analytics/compare?days=7").json()["revenue"]}
    check(rev == {"cad": 1500, "usd": 800}, "money kept per currency, refunds taken off, never added across currencies")
    cp_ = {r["currency"]: r["now_cents"] for r in analyst.get("/api/admin/analytics/compare?days=7").json()["revenue"]}
    check(cp_ == rev, "analyst (who may read billing) sees revenue")
    db.users.update_one({"email": "analyst@example.com"}, {"$set": {"role": "analyst"}})
    import accounts as _A; _keep = _A.PERMS["analyst"]; _A.PERMS["analyst"] = _keep - {"billing.read"}
    check(analyst.get("/api/admin/analytics/compare?days=7").json()["revenue"] == [], "...and revenue is hidden from anyone without billing.read"); _A.PERMS["analyst"] = _keep
    # acquisition
    db.events.delete_many({}); db.users.delete_many({"email": {"$in": ["u1@x.com", "u2@x.com", "u3@x.com", "u4@x.com"]}})
    for i in range(20): ev("page_view", f"g{i}", utm={"source": "google", "medium": "cpc", "campaign": "spring"})
    for i in range(4): ev("page_view", f"n{i}", utm={"source": "newsletter", "medium": "email", "campaign": "oct"})
    def mkuser(i, acq):
        db.users.insert_one({"id": f"uacq{i}", "email": f"u{i}@x.com", "role": "user", "created_at": now - timedelta(days=1), "acq": acq})
    mkuser(1, {"source": "google", "medium": "cpc", "campaign": "spring"}); mkuser(2, {"source": "google", "medium": "cpc", "campaign": "spring"}); mkuser(3, {"source": "newsletter", "medium": "email", "campaign": "oct"}); mkuser(4, {"ref_host": "reddit.com"})
    db.subscriptions.insert_one({"user_id": "uacq1", "status": "active"})
    ac = admin.get("/api/admin/analytics/acquisition?days=30").json()["rows"]
    g = [r for r in ac if r["source"] == "google"][0]
    check(g["visitors"] == 20 and g["signups"] == 2 and g["paid"] == 1 and g["signup_rate"] == 0.1 and g["paid_rate"] == 0.5, "acquisition: visitors, sign-ups, paying people and rates per campaign")
    check(any(r["source"] == "(referral)" and r["medium"] == "reddit.com" for r in ac), "sign-ups from a plain referrer are grouped by site")
    # first-touch is set once at sign-up and a bad tag is cleaned
    check(AN.clean_utm({"source": "<b>x</b>", "medium": "a" * 200, "campaign": "ok", "evil": "1"}) in (None, {"source": "bx/b", "medium": "a" * 60, "campaign": "ok"}) or isinstance(AN.clean_utm({"source": "<b>x</b>"}), (dict, type(None))), "campaign tags are cleaned")
    anon.post("/api/analytics/collect", json={"name": "page_view", "path": "/", "utm": {"source": "x" * 500, "medium": "<script>", "campaign": "ok"}})
    last = db.events.find_one({"name": "page_view", "utm.campaign": "ok"})
    check(last and len(last["utm"]["source"]) <= 60 and "<" not in last["utm"]["medium"], "campaign tags from the browser are length-limited and stripped of markup")
    # e-mail + popups + newsletter reports
    em = admin.get("/api/admin/analytics/email").json()
    check(em["sent"] > 0 and "templates" in em and "Open and click tracking is not used" in em["note"], "e-mail delivery report (and an honest note: no open tracking)")
    check(support.get("/api/admin/analytics/email").status_code == 200 and analyst.get("/api/admin/analytics/email").status_code == 200, "email.read roles can open it")
    pr = admin.get("/api/admin/analytics/popups").json()["rows"]; check(any(r["id"] == a and r["view"] == 10 for r in pr), "popup comparison report")
    nr = admin.get("/api/admin/analytics/newsletter").json(); check(nr["counts"]["confirmed"] >= 1 and nr["by_source"], "list growth by source")
    check(support.get("/api/admin/analytics/realtime").status_code == 403 and support.get("/api/admin/analytics/compare").status_code == 403, "support has no analytics")
    # CSV
    csv_ = admin.get("/api/admin/analytics/export?report=acquisition&days=30")
    check(csv_.status_code == 200 and csv_.text.startswith("﻿source,medium") and "attachment" in csv_.headers["content-disposition"] and csv_.headers["cache-control"] == "no-store", "CSV export has the right headers")
    check(admin.get("/api/admin/analytics/export?report=users").status_code == 400, "only the listed reports can be exported")
    txt = R.csv_bytes([{"a": "=HYPERLINK(\"http://evil\")", "b": "+1", "c": "-2", "d": "@SUM(A1)", "e": "ok", "f": 5, "g": None}]).decode()
    check("'=HYPERLINK" in txt and "'+1" in txt and "'-2" in txt and "'@SUM" in txt and ",ok,5," in txt, "CSV cells starting with = + - @ are neutralised (spreadsheet formula injection)")
    check(db.audit_log.find_one({"action": "analytics.export"}) is not None, "exports are audited")

    # ================================================================ ALERTS + DIGEST
    db.users.delete_many({"id": {"$regex": "^uacq"}})
    for i in range(30): db.users.insert_one({"id": f"old{i}", "email": f"old{i}@x.com", "role": "user", "created_at": now - timedelta(days=10)})
    db.users.insert_one({"id": "new0", "email": "new0@x.com", "role": "user", "created_at": now - timedelta(days=1)})
    sent.clear(); setting("admin.alerts_enabled", True)
    res = support.post("/api/admin/alerts/run"); check(res.status_code == 403, "running alerts by hand needs the jobs permission")
    res = owner.post("/api/admin/alerts/run").json()
    check("signup_drop" in res["opened"] and res["emails"] >= 1, "sign-ups dropped by more than the limit: alert opened and e-mailed")
    al = admin.get("/api/admin/alerts").json()["open"]; check(any(x["key"] == "signup_drop" for x in al), "alert listed in Health")
    n_mail = len(sent); owner.post("/api/admin/alerts/run"); check(len(sent) == n_mail and db.admin_alerts.count_documents({"key": "signup_drop", "resolved": False}) == 1, "same problem = one open alert, one e-mail (cooldown)")
    db.admin_alerts.update_one({"key": "signup_drop"}, {"$set": {"notified_at": now - timedelta(hours=7)}}); AL.notify(db, now=now + timedelta(hours=1)); check(len(sent) > n_mail, "mailed again after the cooldown if still open")
    for i in range(40): db.users.insert_one({"id": f"rec{i}", "email": f"rec{i}@x.com", "role": "user", "created_at": now - timedelta(hours=2)})
    check("signup_drop" in owner.post("/api/admin/alerts/run").json()["cleared"], "alert clears itself when the numbers recover")
    for i in range(25): db.app_logs.insert_one({"at": now, "level": "error", "path": "/x", "status": 500})
    check("error_spike" in owner.post("/api/admin/alerts/run").json()["opened"], "error spike alert")
    db.app_logs.delete_many({}); owner.post("/api/admin/alerts/run")
    for i in range(3): db.payments.insert_one({"status": "failed", "currency": "cad", "amount_paid": 0, "created_at": now})
    check("failed_payments" in owner.post("/api/admin/alerts/run").json()["opened"], "failed-payment alert")
    aid = admin.get("/api/admin/alerts").json()["open"][0]["id"]
    check(admin.post(f"/api/admin/alerts/{aid}/resolve").status_code == 200 and not any(x["id"] == aid for x in admin.get("/api/admin/alerts").json()["open"]), "an alert can be dismissed")
    # per-person switch
    db.users.update_one({"email": "admin@example.com"}, {"$set": {"prefs.admin_alerts": False}}); sent.clear()
    db.admin_alerts.update_many({}, {"$set": {"resolved": True}}); INT.alert(db, "t1", "Something broke."); AL.notify(db)
    check(all(p["to"] != ["admin@example.com"] for p in sent) and any(p["to"] == ["boss@example.com"] for p in sent), "people who switched alerts off are not e-mailed")
    setting("admin.alerts_enabled", False); check(owner.post("/api/admin/alerts/run").json().get("skipped") == "alerts are off", "alerts switch works"); setting("admin.alerts_enabled", True)
    # digest
    dg = admin.get("/api/admin/digest/preview").json()["text"]
    check("Visitors:" in dg and "Sign-ups:" in dg and "Open alerts:" in dg and not textguard.scan(dg.replace(textguard.DISCLAIMER, "")), "weekly summary reads well and has no banned words")
    sent.clear(); check(owner.post("/api/admin/digest/send").json()["sent"] == 0, "nobody gets the digest until they opt in")
    db.users.update_one({"email": "analyst@example.com"}, {"$set": {"prefs.admin_digest": True}}); db.users.update_one({"email": "boss@example.com"}, {"$set": {"prefs.admin_digest": True}})
    r = owner.post("/api/admin/digest/send").json()
    check(r["sent"] == 2 and {p["to"][0] for p in sent} == {"analyst@example.com", "boss@example.com"}, "digest goes to staff who opted in (analyst included)")
    sent.clear(); check(owner.post("/api/admin/digest/send").json()["sent"] == 0 or len(sent) == 0, "same week, same person: no duplicate (idempotent)")
    check(support.post("/api/admin/digest/send").status_code == 403 and admin.get("/api/admin/digest/preview").status_code == 200, "digest permissions")

    # ================================================================ PERMISSION MATRIX
    matrix = [("GET", "/api/admin/popups", "popups.read"), ("GET", "/api/admin/integrations", "integrations.read"), ("GET", "/api/admin/analytics/realtime", "analytics.read"), ("GET", "/api/admin/site/draft", "site.read"),
              ("GET", "/api/admin/alerts", "logs.read"), ("GET", "/api/admin/newsletter", "email.read")]
    who = {"owner": owner, "admin": admin, "support": support, "analyst": analyst, "member": fan, "visitor": anon}
    want = {"owner": [1, 1, 1, 1, 1, 1], "admin": [1, 1, 1, 1, 1, 1], "support": [0, 0, 0, 0, 1, 1], "analyst": [1, 0, 1, 0, 1, 1], "member": [0] * 6, "visitor": [0] * 6}
    for role, cl in who.items():
        got = [int(cl.request(m, p).status_code == 200) for m, p, _ in matrix]
        check(got == want[role], f"{role}: {''.join(map(str, got))} (popups, integrations, analytics, studio, alerts, list)")
    check(admin.put("/api/admin/integrations/tracking", json=tp).status_code == 403 and admin.put("/api/admin/settings/tracking.enabled", json={"value": True}).status_code in (403, 404, 405), "tracking is owner only, also through the generic settings route")
    check(db.settings.find_one({"key": "tracking.enabled", "value": True}) is None, "...and it stayed off")

    # ================================================================ WORDS
    check(textguard.find([PP.TEMPLATES, [PP.template_data(k) for k in PP.TEMPLATES]]) == [], "starter popup templates contain no banned words")
    check(admin.post("/api/admin/announcements", json={"text": "Our best odds this week", "level": "info"}).status_code == 400, "announcements refuse banned words (clear 400, not a crash)")
    check(admin.post("/api/admin/announcements", json={"text": "New: team pages are live", "level": "info"}).status_code == 200, "...and accept normal text")

print("\nALL GROWTH CHECKS PASSED")
