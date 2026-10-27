"""End-to-end over HTTP: the admin panel API, roles, billing flow with Stripe/Resend webhooks."""
import os, sys, base64, json, re, time, hmac, hashlib
os.environ.update({"APP_ENCRYPTION_KEY": base64.b64encode(os.urandom(32)).decode(), "MONGO_URL": "mongomock://x", "DB_NAME": "adm",
                   "ADMIN_EMAIL": "boss@example.com", "ADMIN_INITIAL_PASSWORD": "boss-pass-12345", "CRON_SHARED_SECRET": "s3cret",
                   "COOKIE_SECURE": "0", "BCRYPT_ROUNDS": "4", "PUBLIC_BASE_URL": "https://app.test"})
HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("SOCCER_BRAIN_DIR", os.path.join(HERE, "soccer_brain"))
sys.path.insert(0, HERE); sys.path.insert(0, os.environ["SOCCER_BRAIN_DIR"])
from urllib.parse import parse_qsl
from datetime import timedelta
import httpx, mongomock, pyotp
from fastapi.testclient import TestClient
import server as srv, emailer as E, stripe_billing as SB, security, settings_store as S, security_mw, accounts as A

db = mongomock.MongoClient()["adm"]; srv.set_db(db)
def check(c, m):
    if not c: print("  FAIL", m); sys.exit(1)
    print("  ok  ", m)
sent = []
E.set_http_factory(lambda: httpx.Client(transport=httpx.MockTransport(lambda r: (sent.append(json.loads(r.content)), httpx.Response(200, json={"id": f"em_{len(sent)}"}))[1]))); E.set_sleep(lambda s: None)
stripe_calls = []
def stripe_handler(r):
    body = dict(parse_qsl(r.content.decode())) if r.content else {}; stripe_calls.append((r.method, r.url.path, body)); p = r.url.path
    if p == "/v1/products": return httpx.Response(200, json={"id": "prod_1"})
    if p == "/v1/prices": return httpx.Response(200, json={"id": f"price_{len(stripe_calls)}"})
    if p == "/v1/customers": return httpx.Response(200, json={"id": "cus_1"})
    if p == "/v1/checkout/sessions": return httpx.Response(200, json={"id": "cs_1", "url": "https://checkout.stripe.test/c/1"})
    if p == "/v1/balance": return httpx.Response(200, json={"livemode": False})
    if p == "/v1/refunds": return httpx.Response(200, json={"id": "re_1", "status": "succeeded"})
    return httpx.Response(200, json={"id": p.rsplit("/", 1)[-1]})
SB.set_http_factory(lambda: httpx.Client(transport=httpx.MockTransport(stripe_handler))); SB.set_sleep(lambda s: None)
def setting(k, v): S.put(db, k, v); security_mw.clear_cache()
def token_from(to, kind):
    for p in reversed(sent):
        if p["to"] == [to] and kind in p["subject"]:
            return re.search(r"token=([A-Za-z0-9_-]+)", p["text"]).group(1)

with TestClient(srv.app) as owner:
    setting("security.rate_limit_auth_per_minute", 1000); setting("security.rate_limit_write_per_minute", 1000); setting("security.rate_limit_read_per_minute", 1000)
    setting("email.enabled", True); setting("email.from_address", "hello@mail.example.com"); security.save_provider_key(db, "resend", "re_abcdefghijk12345")
    # ---------------- owner: forced 2FA enrolment
    r = owner.post("/api/auth/login", json={"email": "boss@example.com", "password": "boss-pass-12345"})
    check(r.json()["scope"] == "enroll_2fa", "owner's first session can only enrol in 2FA")
    check(owner.get("/api/admin/dashboard").json()["error"]["code"] == "ENROLL_2FA_REQUIRED", "admin routes closed until 2FA is on")
    check(owner.get("/api/auth/me").json()["scope"] == "enroll_2fa", "me tells the front end to show the enrolment screen")
    b = owner.post("/api/account/2fa/begin").json()
    rc = owner.post("/api/account/2fa/confirm", json={"code": pyotp.TOTP(b["secret"]).now()}).json()["recovery_codes"]
    check(owner.get("/api/admin/dashboard").status_code == 200, "after enrolling, the same session reaches the panel")
    rcodes = list(rc)
    def staff_login(client, email, pw):
        r = client.post("/api/auth/login", json={"email": email, "password": pw}).json()
        r2 = client.post("/api/auth/login/2fa", json={"challenge": r["challenge"], "code": rcodes.pop(0)}); return r2
    def make_staff(role):
        email = f"{role}@example.com"
        r = owner.post("/api/admin/staff/invite", json={"email": email, "role": role})
        check(r.status_code == 200 and r.json()["email_status"] == "sent" and "link" not in r.json(), f"owner invites {role}; link goes by e-mail only")
        cl = TestClient(srv.app)
        check(cl.post("/api/auth/reset-password", json={"token": token_from(email, "team"), "password": f"{role}-first-pass-1"}).status_code == 200, f"{role} sets a password from the invite")
        r = cl.post("/api/auth/login", json={"email": email, "password": f"{role}-first-pass-1"}).json()
        b = cl.post("/api/account/2fa/begin").json(); cl.post("/api/account/2fa/confirm", json={"code": pyotp.TOTP(b["secret"]).now()})
        return cl
    admin, support, analyst = make_staff("admin"), make_staff("support"), make_staff("analyst")
    check(admin.post("/api/admin/staff/invite", json={"email": "x@example.com", "role": "support"}).status_code == 403, "admin cannot invite staff (owner only)")

    # a normal user
    fan = TestClient(srv.app)
    fan.post("/api/auth/register", json={"email": "fan@example.com", "password": "fan-user-pass-1", "display_name": "Fan"}); fan.post("/api/auth/verify-email", json={"token": token_from("fan@example.com", "Confirm")})
    fan.post("/api/auth/login", json={"email": "fan@example.com", "password": "fan-user-pass-1"})
    fan_id = db.users.find_one({"email": "fan@example.com"})["id"]
    check(fan.get("/api/admin/users").status_code == 403 and fan.get("/api/admin/settings").status_code == 403 and fan.get("/api/admin/keys").status_code == 403, "normal user: 403 on every admin route")

    # ---------------- roles
    check(analyst.get("/api/admin/dashboard").status_code == 200 and admin.get("/api/admin/dashboard").status_code == 200, "analyst and admin open the dashboard")
    check(support.get("/api/admin/dashboard").status_code == 403, "support has no analytics")
    ul = analyst.get("/api/admin/users?q=fan").json()
    check(ul["total"] == 1 and ul["rows"][0]["email"] == "f***@example.com", "analyst can search by name")
    ul = analyst.get("/api/admin/users").json()
    fr = next(x for x in ul["rows"] if x["id"] == fan_id)
    check(fr["email"] == "f***@example.com", "analyst sees masked e-mails")
    check(next(x for x in support.get("/api/admin/users").json()["rows"] if x["id"] == fan_id)["email"] == "fan@example.com", "support sees full e-mails")
    check(analyst.get("/api/admin/users?q=fan@example.com").json()["total"] == 0, "analyst cannot search by e-mail")
    d = support.get(f"/api/admin/users/{fan_id}")
    txt = d.text
    check(d.status_code == 200 and all(w not in txt for w in ("password_hash", "secret_enc", "recovery_codes", "$2b$")), "user detail never contains hashes or secrets")
    check(admin.get("/api/admin/users?plan=free").json()["total"] >= 1 and admin.get("/api/admin/users?verified=false").json()["total"] >= 0, "filters work (plan, verified)")
    check(analyst.post(f"/api/admin/users/{fan_id}/disable", json={"reason": "x"}).status_code == 403, "analyst cannot change users")
    # support actions
    check(support.post(f"/api/admin/users/{fan_id}/notes", json={"text": "Asked about invoices"}).status_code == 200 and len(support.get(f"/api/admin/users/{fan_id}").json()["notes"]) == 1, "support adds a note")
    boss_id = db.users.find_one({"email": "boss@example.com"})["id"]
    check(support.post(f"/api/admin/users/{boss_id}/disable", json={"reason": "x"}).status_code == 403, "support cannot touch an owner")
    sup_id = db.users.find_one({"email": "support@example.com"})["id"]
    check(support.post(f"/api/admin/users/{sup_id}/disable", json={"reason": "x"}).status_code in (403, 409), "nobody disables their own account")
    check(support.post(f"/api/admin/users/{fan_id}/disable", json={"reason": ""}).status_code == 400, "disabling needs a reason")
    check(support.post(f"/api/admin/users/{fan_id}/disable", json={"reason": "chargeback abuse"}).status_code == 200 and fan.get("/api/auth/me").json()["user"] is None, "disable signs the person out at once")
    check(TestClient(srv.app).post("/api/auth/login", json={"email": "fan@example.com", "password": "fan-user-pass-1"}).json()["error"]["code"] == "ACCOUNT_DISABLED", "disabled person cannot sign in")
    support.post(f"/api/admin/users/{fan_id}/enable", json={"reason": "resolved"}); fan.post("/api/auth/login", json={"email": "fan@example.com", "password": "fan-user-pass-1"})
    a = db.audit_log.find_one({"action": "user.disable"})
    check(a and a["actor"] == "support@example.com" and a["target"] == fan_id and a["detail"]["reason"] == "chargeback abuse", "audit log: who, what, whom, why")
    check(support.post(f"/api/admin/users/{fan_id}/send-reset").json()["email_status"] == "sent" and "link" not in support.post(f"/api/admin/users/{fan_id}/send-reset").text, "support sends a reset e-mail; the link is never shown to staff")
    check(support.post(f"/api/admin/users/{fan_id}/comp", json={"plan": "pro", "days": 30, "reason": "partner"}).status_code == 403, "support cannot grant plans")
    check(admin.post(f"/api/admin/users/{fan_id}/comp", json={"plan": "pro", "days": 30, "reason": ""}).status_code == 400, "comp needs a reason")
    check(admin.post(f"/api/admin/users/{fan_id}/comp", json={"plan": "pro", "days": 30, "reason": "launch partner"}).status_code == 200, "admin grants a comp plan")
    setting("features.billing", True)
    check(fan.get("/api/auth/me").json()["plan"]["source"] == "comp" and fan.get("/api/auth/me").json()["entitlements"]["export"] is True, "comp shows up as the person's plan")
    check(admin.delete(f"/api/admin/users/{fan_id}/purge").status_code == 403, "admin cannot purge (owner only)")

    # ---------------- keys and settings
    check(admin.put("/api/admin/keys/stripe_secret", json={"key": "sk_test_abcdefghij123456"}).status_code == 403, "admin cannot save keys (owner only)")
    check(owner.put("/api/admin/keys/stripe_secret", json={"key": "nonsense"}).status_code == 400, "malformed key refused")
    check(owner.put("/api/admin/keys/stripe_secret", json={"key": "sk_live_abcdefghij123456"}).json()["error"]["code"] == "MODE_MISMATCH", "live key refused while billing mode is test")
    r = owner.put("/api/admin/keys/stripe_secret", json={"key": "sk_test_abcdefghij123456"})
    check(r.json()["masked"] == "•••• 3456" and "abcdefghij" not in r.text, "key saved; only the last 4 come back")
    owner.put("/api/admin/keys/stripe_webhook", json={"key": "whsec_testsecret1234567890"})
    check(all("abcdefghij" not in json.dumps(x, default=str) for x in db.audit_log.find({})) and all("abcdefghij" not in json.dumps(x, default=str) for x in db.app_logs.find({})), "keys appear in no log")
    ks = {k["provider"]: k for k in admin.get("/api/admin/keys").json()["keys"]}
    check(ks["stripe_secret"]["set"] and ks["stripe_secret"]["source"] == "admin" and ks["resend"]["set"] and not ks["pitchapi"]["set"], "key screen shows what is set, never the value")
    check(owner.post("/api/admin/keys/stripe_secret/test").json() == {"ok": True, "livemode": False}, "Stripe key test works")
    check(analyst.post("/api/admin/keys/stripe_secret/test").status_code == 403, "analyst cannot run key tests")
    check(admin.put("/api/admin/settings/billing.mode", json={"value": "live"}).status_code == 403 and admin.put("/api/admin/settings/features.billing", json={"value": False}).status_code == 403, "billing switches are owner-only")
    check(admin.put("/api/admin/settings/email.daily_send_cap", json={"value": 50}).status_code == 200 and S.get(db, "email.daily_send_cap") == 50, "admin changes an ordinary setting")
    check(admin.put("/api/admin/settings/email.daily_send_cap", json={"value": "lots"}).status_code == 400, "wrong type refused")
    check(admin.put("/api/admin/settings/engine.lineup_effects", json={"value": True}).status_code == 409, "locked setting refused")
    check(admin.put("/api/admin/settings/nope.nothing", json={"value": 1}).status_code == 404, "unknown setting refused")
    check(admin.get("/api/admin/settings/email.daily_send_cap/history").json()["history"][0]["new"] == 50, "setting history kept")
    check(analyst.put("/api/admin/settings/email.daily_send_cap", json={"value": 5}).status_code == 403 and analyst.get("/api/admin/settings").status_code == 403, "analyst cannot read or change settings")

    # ---------------- plans and the billing flow
    pl = admin.get("/api/admin/plans").json()
    check({p["key"] for p in pl["plans"]} == {"free", "pro"} and "finder_searches_per_day" in pl["entitlements"], "plans screen lists plans and the entitlement catalogue")
    check(admin.put("/api/admin/plans/pro", json={"entitlements": {"alerts": "yes"}}).status_code == 400, "bad entitlement refused")
    r = admin.put("/api/admin/plans/pro", json={"name": "Pro", "bullets": ["A", "B"], "prices": [{"id": "monthly", "interval": "month", "amount_cents": 1299, "currency": "cad"}, {"id": "yearly", "interval": "year", "amount_cents": 9999, "currency": "cad"}]})
    check(r.status_code == 200 and r.json()["prices"][0]["amount_cents"] == 1299, "admin sets the prices")
    check(support.put("/api/admin/plans/pro", json={"name": "X"}).status_code == 403 and analyst.get("/api/admin/plans").status_code == 200, "support cannot edit plans; analyst can look")
    r = admin.post("/api/admin/plans", json={"key": "team", "name": "Team", "entitlements": {"alerts": True}, "visible": True})
    check(r.status_code == 200 and "team" in [p["key"] for p in TestClient(srv.app).get("/api/plans").json()["plans"]], "new plan appears on the public pricing route once visible")
    check(admin.post("/api/admin/plans/pro/sync").json()["prices"] == [{"id": "monthly", "synced": True}, {"id": "yearly", "synced": True}], "plan synced to Stripe")
    pub = TestClient(srv.app).get("/api/plans").json()
    check("stripe" not in json.dumps(pub) and pub["billing_enabled"], "public pricing shows no Stripe ids")
    # checkout
    setting("features.billing", False)
    check(fan.post("/api/billing/checkout", json={"plan": "pro", "price": "monthly"}).json()["error"]["code"] == "BILLING_OFF", "checkout closed while billing is off")
    setting("features.billing", True)
    db.users.update_one({"id": fan_id}, {"$unset": {"comp": ""}})
    r = fan.post("/api/billing/checkout", json={"plan": "pro", "price": "monthly"})
    co = [c for c in stripe_calls if c[1] == "/v1/checkout/sessions"][-1][2]
    check(r.json()["url"].startswith("https://checkout.stripe.test") and co["client_reference_id"] == fan_id, "checkout returns the hosted page")
    check(TestClient(srv.app).post("/api/billing/checkout", json={"plan": "pro", "price": "monthly"}).status_code == 401, "checkout needs sign-in")
    # webhook
    WH = "whsec_testsecret1234567890"
    def sign(raw, t=None, sec=WH):
        t = t or int(time.time()); return f"t={t},v1=" + hmac.new(sec.encode(), f"{t}.".encode() + raw, hashlib.sha256).hexdigest()
    pro_price = [p for p in db.plans.find_one({"key": "pro"})["prices"] if p["id"] == "monthly"][0]["stripe_price_id"]
    end = int((time.time() + 30 * 86400))
    def evt(id, typ, obj): return json.dumps({"id": id, "type": typ, "created": int(time.time()), "livemode": False, "data": {"object": obj}}).encode()
    sub = {"id": "sub_1", "customer": "cus_1", "status": "active", "metadata": {"user_id": fan_id}, "created": int(time.time()),
           "items": {"data": [{"price": {"id": pro_price, "unit_amount": 1299, "currency": "cad", "recurring": {"interval": "month"}}, "current_period_end": end, "current_period_start": int(time.time())}]}}
    pub_c = TestClient(srv.app)
    raw = evt("evt_1", "customer.subscription.created", sub)
    check(pub_c.post("/api/webhooks/stripe", content=raw, headers={"stripe-signature": "t=1,v1=bad"}).status_code == 400, "stripe webhook: bad signature refused")
    check(pub_c.post("/api/webhooks/stripe", content=raw).status_code == 400, "stripe webhook: missing signature refused")
    r = pub_c.post("/api/webhooks/stripe", content=raw, headers={"stripe-signature": sign(raw)})
    check(r.status_code == 200 and r.json()["result"] == "processed", "stripe webhook: signed event applied")
    check(pub_c.post("/api/webhooks/stripe", content=raw, headers={"stripe-signature": sign(raw)}).json()["result"] == "duplicate", "stripe webhook: same event again is a no-op")
    inv = {"id": "in_1", "customer": "cus_1", "subscription": "sub_1", "amount_paid": 1299, "amount_due": 1299, "currency": "cad", "number": "A-1", "hosted_invoice_url": "https://invoice.test/1", "payment_intent": "pi_1", "created": int(time.time()), "lines": {"data": [{"period": {"end": end}}]}}
    raw = evt("evt_2", "invoice.paid", inv); pub_c.post("/api/webhooks/stripe", content=raw, headers={"stripe-signature": sign(raw)})
    me = fan.get("/api/auth/me").json()
    check(me["plan"]["source"] == "subscription" and me["plan"]["plan_key"] == "pro", "after the webhook the person is on Pro")
    bs = fan.get("/api/account/billing").json()
    check(bs["subscription"]["status"] == "active" and bs["payments"][0]["amount_cents"] == 1299 and bs["can_use_portal"], "billing page: subscription, invoice, portal available")
    check(any("receipt" in p["subject"].lower() for p in sent), "receipt e-mail sent")
    check(admin.get("/api/admin/subscriptions?status=active").json()["total"] == 1 and admin.get("/api/admin/payments").json()["rows"][0]["id"] == "in_1", "admin sees the subscription and payment")
    check(analyst.get("/api/admin/analytics/revenue").json()["by_currency"][0]["mrr_cents"] == 1299, "revenue report: MRR 12.99")
    ov = analyst.get("/api/admin/analytics/overview").json()
    check(ov["people"]["paid"] == 1 and ov["revenue"]["by_currency"][0]["currency"] == "cad", "overview counts paid people")
    check(support.post("/api/admin/payments/in_1/refund", json={"amount_cents": 100, "reason": "x"}).status_code == 403, "support cannot refund")
    r = admin.post("/api/admin/payments/in_1/refund", json={"amount_cents": 500, "reason": "goodwill"})
    check(r.status_code == 200 and [c for c in stripe_calls if c[1] == "/v1/refunds"][-1][2]["amount"] == "500", "admin refunds in test mode")
    check(admin.post("/api/admin/payments/in_1/refund", json={"amount_cents": 999999, "reason": "x"}).status_code == 400, "over-refund refused")
    setting("billing.mode", "live"); security.save_provider_key(db, "stripe_secret", "sk_live_abcdefghij123456")
    check(admin.post("/api/admin/payments/in_1/refund", json={"amount_cents": 100, "reason": "x"}).status_code == 403, "live-mode refunds are owner-only")
    setting("billing.mode", "test"); security.save_provider_key(db, "stripe_secret", "sk_test_abcdefghij123456")
    check(admin.post("/api/admin/subscriptions/sub_1/cancel").status_code == 200 and stripe_calls[-1][2]["cancel_at_period_end"] == "true", "admin schedules a cancel")
    bad = {**sub, "id": "sub_2", "items": {"data": [{"price": {"id": "price_nope"}, "current_period_end": end}]}}
    raw = evt("evt_3", "customer.subscription.created", bad)
    check(pub_c.post("/api/webhooks/stripe", content=raw, headers={"stripe-signature": sign(raw)}).status_code == 500, "unmappable event: 500 so Stripe retries")
    h = admin.get("/api/admin/health").json()
    check(any("webhook" in a["message"] for a in h["alerts"]) and h["webhook_errors_24h"] == 1, "health screen raises a red alert for the failed webhook")
    check(admin.get("/api/admin/logs/webhooks?status=error").json()["rows"][0]["error"], "webhook log shows the failure reason")
    # coupons
    r = admin.post("/api/admin/coupons", json={"code": "launch20", "name": "Launch", "percent_off": 20})
    check(r.status_code == 200 and admin.get("/api/admin/coupons").json()["coupons"][0]["code"] == "LAUNCH20", "coupon created and listed")
    check(admin.post("/api/admin/coupons", json={"code": "launch20", "percent_off": 20}).status_code == 400, "duplicate coupon refused")
    # resend webhook
    WS = "whsec_" + base64.b64encode(b"resend-secret-bytes!").decode(); security.save_provider_key(db, "resend_webhook", WS)
    def svix(raw, mid, t=None):
        t = str(t or int(time.time())); k = base64.b64decode(WS.split("_", 1)[1])
        return {"svix-id": mid, "svix-timestamp": t, "svix-signature": "v1," + base64.b64encode(hmac.new(k, f"{mid}.{t}.".encode() + raw, hashlib.sha256).digest()).decode()}
    raw = json.dumps({"type": "email.bounced", "data": {"email_id": "em_1", "to": ["gone@example.com"], "bounce": {"type": "Permanent"}}}).encode()
    check(pub_c.post("/api/webhooks/resend", content=raw, headers={**svix(raw, "m1"), "svix-signature": "v1,AAAA"}).status_code == 400, "resend webhook: bad signature refused")
    check(pub_c.post("/api/webhooks/resend", content=raw, headers=svix(raw, "m1")).json()["result"] == "processed" and db.email_suppressions.find_one({"email": "gone@example.com"}), "resend webhook: bounce suppresses the address")
    check(admin.get("/api/admin/email/suppressions").json()["total"] == 1 and admin.delete("/api/admin/email/suppressions/gone@example.com").status_code == 200, "admin sees and clears a suppression")

    # ---------------- e-mail admin
    check(len(analyst.get("/api/admin/email/templates").json()["templates"]) == 16, "16 e-mail templates listed")
    check(admin.put("/api/admin/email/templates/welcome", json={"subject": "Hi", "html": "<script>x</script>", "text": "t"}).status_code == 400, "script in a template refused")
    check(admin.put("/api/admin/email/templates/welcome", json={"subject": "Hello {{name}}", "html": "<p>Custom {{name}}</p>", "text": "Custom"}).status_code == 200 and "Custom" in admin.get("/api/admin/email/templates/welcome/preview").json()["html"], "template saved and previewed")
    n = len(sent); check(admin.post("/api/admin/email/templates/welcome/test").json()["status"] == "sent" and sent[-1]["to"] == ["admin@example.com"] and sent[-1]["subject"].startswith("[TEST]") and len(sent) == n + 1, "test send goes to the signed-in staff member only")
    cid = admin.post("/api/admin/email/campaigns", json={"subject": "News", "html": "<p>Hi</p>", "segment": "all"}).json()["id"]
    check(admin.post(f"/api/admin/email/campaigns/{cid}/send").status_code == 400, "campaign blocked until marketing e-mail and a postal address are set")
    check(support.post("/api/admin/email/campaigns", json={"subject": "x", "html": "<p>x</p>"}).status_code == 403, "support cannot create campaigns")

    # ---------------- logs, health, security
    au = admin.get("/api/admin/logs/audit?action=user.disable").json()
    check(au["total"] >= 1 and au["rows"][0]["actor"] == "support@example.com", "audit log filter by action")
    db.auth_log.insert_one({"at": A.utcnow(), "event": "login", "ok": False, "email": "victim@example.com", "ip": "203.0.113.45", "ua": "Mozilla/5.0 secret-agent", "reason": "bad_credentials"})
    al = analyst.get("/api/admin/logs/auth?event=login&ok=false").json()["rows"][0]
    sl = support.get("/api/admin/logs/auth").status_code
    check(al["ip"] == "203.0.113.x" and al["email"] == "v***@example.com" and "ua" not in al, "analyst sees sign-in logs with masked IP and e-mail, no user agent")
    owner_row = owner.get("/api/admin/logs/auth?event=login&ok=false").json()["rows"][0]
    check(owner_row["ip"] == "203.0.113.45" and owner_row["email"] == "victim@example.com", "owner sees the full row")
    check(analyst.get("/api/admin/logs/nope").status_code == 404 and TestClient(srv.app).get("/api/admin/logs/audit").status_code == 401, "unknown log 404; logs need sign-in")
    sec = admin.get("/api/admin/security").json()
    check(sec["staff_without_2fa"] == 0 and len(sec["staff"]) == 4 and "failed_logins_24h" in sec, "security centre: everyone on staff has 2FA")
    check(support.get("/api/admin/security").status_code == 403 and analyst.get("/api/admin/security").status_code == 403, "security centre: admin and owner only")

    # ---------------- roles, staff
    check(owner.post(f"/api/admin/users/{db.users.find_one({'email': 'support@example.com'})['id']}/role", json={"role": "analyst"}).status_code == 200 and support.get("/api/auth/me").json()["user"] is None, "changing a role signs that person out")
    check(owner.post(f"/api/admin/users/{boss_id}/role", json={"role": "admin"}).status_code in (409,), "an owner cannot demote themselves (last owner)")
    # ---------------- announcements, inbox, content
    aid = admin.post("/api/admin/announcements", json={"text": "Data refresh tonight", "level": "info", "audience": "all"}).json()["id"]
    check(TestClient(srv.app).get("/api/announcements").json()["items"][0]["text"] == "Data refresh tonight", "announcement shows to visitors")
    admin.put(f"/api/admin/announcements/{aid}", json={"text": "Data refresh tonight", "active": False}); check(TestClient(srv.app).get("/api/announcements").json()["items"] == [], "turned-off announcement disappears")
    check(admin.post("/api/admin/announcements", json={"text": "x" * 300}).status_code == 422, "announcement length limit")
    check(TestClient(srv.app).post("/api/contact", json={"name": "Pat", "email": "pat@example.com", "message": "Hello there team"}).status_code == 202, "contact form accepted")
    im = admin.get("/api/admin/inbox").json()["rows"][0]
    check(im["email"] == "pat@example.com" and admin.put(f"/api/admin/inbox/{im['id']}", json={"status": "replied"}).status_code == 200, "inbox shows it; staff mark it replied")
    check(admin.put("/api/admin/content/privacy", json={"title": "Privacy", "body_md": "# Privacy\nWe keep little."}).status_code == 200 and TestClient(srv.app).get("/api/content/privacy").json()["title"] == "Privacy", "content page saved and public")
    check(admin.put("/api/admin/content/BAD SLUG", json={"title": "x", "body_md": "x"}).status_code in (400, 404), "bad slug refused")
    # ---------------- jobs and purge
    check(admin.post("/api/admin/jobs/run?job=engine").json()["queued"] and admin.post("/api/admin/jobs/run?job=nope").status_code == 400, "run-now queued; unknown job refused")
    check(owner.delete(f"/api/admin/users/{fan_id}/purge").status_code == 200 and db.users.find_one({"id": fan_id})["email"].startswith("deleted+"), "owner purges a person (data removed)")
    check(db.payments.find_one({"_id": "in_1"})["user_id"] is None, "their payment record stays, unlinked")
    check(owner.delete(f"/api/admin/users/{boss_id}/purge").status_code in (409,), "an owner cannot purge themselves")
    # analytics series
    for _ in range(3): TestClient(srv.app).post("/api/analytics/collect", json={"name": "page_view", "path": "/pricing"}, headers={"user-agent": "Mozilla/5.0 Chrome"})
    tp = analyst.get("/api/admin/analytics/traffic").json()
    check(tp["pages"][0]["path"] == "/pricing" and analyst.get("/api/admin/analytics/funnel").json()["steps"][0]["step"] == "Visitors" and len(analyst.get("/api/admin/analytics/retention").json()["cohorts"]) == 8, "traffic, funnel and retention reports respond")
    check(analyst.get("/api/admin/analytics/series?name=nope").status_code == 400, "unknown event name refused")
    # ---------------- brain layers and calendar import
    rows = [{"team_iid": 7, "kickoff": "2026-09-23T19:45:00Z", "comp": "league_cup", "stage": "Round 3"}]
    check(admin.post("/api/admin/calendar/import", json=rows).json()["rows"] == 1 and admin.post("/api/admin/calendar/import", json=rows).status_code == 200
          and db.club_calendar.count_documents({}) == 1, "calendar import works and is idempotent")
    check(admin.post("/api/admin/calendar/import", json=[{**rows[0], "comp": "made_up"}]).status_code == 400, "unknown competition key refused")
    check(analyst.post("/api/admin/calendar/import", json=rows).status_code == 403, "an analyst (read-only) cannot import a calendar")
    bs = analyst.get("/api/admin/brain").json()
    check(bs["calendar_rows_by_competition"] == {"league_cup": 1} and bs["clubs_with_calendar"] == 1 and bs["shape_layer"] == "off", "brain screen shows calendar coverage and layer switches")
    check(TestClient(srv.app).get("/api/admin/brain").status_code in (401, 403), "signed-out visitor: no brain screen")
    setting("context.start_model", "auto")
    check(admin.put("/api/admin/settings/context.start_model", json={"value": "maybe"}).status_code == 400, "bad value for the start-model switch refused")
    # ---------------- images: admin routes
    import images as IMG
    db.leagues.insert_one({"iid": 901, "id": "lg-x", "ext_id": 901, "name": "Test League", "enabled": False})
    db.teams.insert_one({"iid": 902, "id": "tm-x", "ext_id": 902, "name": "Test FC", "league_iid": 901})
    PNG = b"\x89PNG\r\n\x1a\n" + b"\x01" * 40
    check(analyst.get("/api/admin/images").status_code == 200 and analyst.get("/api/admin/images").json()["kinds"]["team"]["stored"] == 0, "images overview opens for read-only staff")
    check(analyst.put("/api/admin/images/team/902/upload", content=PNG).status_code == 403, "read-only staff cannot upload an image")
    check(admin.put("/api/admin/images/team/902/upload", content=PNG).status_code == 200 and db.media.count_documents({"kind": "team", "iid": 902}) == 1, "admin uploads a crest")
    check(admin.put("/api/admin/images/team/902/upload", content=b"<svg/>").status_code == 400, "an SVG upload is refused")
    check(admin.put("/api/admin/images/team/999999/upload", content=PNG).status_code == 404, "upload for a record that does not exist: 404")
    check(admin.put("/api/admin/images/club/902/upload", content=PNG).status_code == 400, "unknown kind refused")
    setting("images.enabled", True)
    pub = TestClient(srv.app)
    check(pub.get("/api/media/team/tm-x").status_code == 200, "signed-out visitor can see a stored crest")
    check(admin.delete("/api/admin/images/team/902").json()["removed"] is True and pub.get("/api/media/team/tm-x").status_code == 404, "take-down removes it at once")
    check(admin.post("/api/admin/images/sync").json()["queued"] and db.job_requests.find_one({"job": "images", "status": "pending"}), "sync queued as a job")
    check(owner.put("/api/admin/keys/apifootball", json={"key": "a1b2" * 8}).status_code == 200 and "a1b2a1b2" not in str(db.provider_keys.find_one({"provider": "apifootball"})), "owner saves the API-Football key; it is stored encrypted")
    check(owner.put("/api/admin/keys/apifootball", json={"key": "short"}).status_code == 400, "a malformed API-Football key is refused")
    check(admin.put("/api/admin/keys/apifootball", json={"key": "a1b2" * 8}).status_code == 403, "only the owner can change provider keys")
print("\nALL ADMIN CHECKS PASSED")
