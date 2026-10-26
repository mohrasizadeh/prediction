"""End-to-end over HTTP: public routes, sign-up/in, account settings, 2FA, security layer."""
import os, sys, base64, json, re, time
os.environ.update({"APP_ENCRYPTION_KEY": base64.b64encode(os.urandom(32)).decode(), "MONGO_URL": "mongomock://x", "DB_NAME": "srv",
                   "ADMIN_EMAIL": "boss@example.com", "ADMIN_INITIAL_PASSWORD": "boss-pass-12345", "CRON_SHARED_SECRET": "s3cret",
                   "COOKIE_SECURE": "0", "BCRYPT_ROUNDS": "4", "PUBLIC_BASE_URL": "https://app.test"})
HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("SOCCER_BRAIN_DIR", os.path.join(HERE, "soccer_brain"))
sys.path.insert(0, HERE); sys.path.insert(0, os.environ["SOCCER_BRAIN_DIR"])
import httpx, mongomock, pyotp
from fastapi.testclient import TestClient
import server as srv, emailer as E, security, settings_store as S, security_mw, accounts as A

db = mongomock.MongoClient()["srv"]; srv.set_db(db)
def check(c, m):
    if not c: print("  FAIL", m); sys.exit(1)
    print("  ok  ", m)
sent = []
def resend_handler(req):
    sent.append(json.loads(req.content)); return httpx.Response(200, json={"id": f"em_{len(sent)}"})
E.set_http_factory(lambda: httpx.Client(transport=httpx.MockTransport(resend_handler))); E.set_sleep(lambda s: None)
def token_for(to, kind=None):
    for p in reversed(sent):
        if p["to"] == [to] and (kind is None or kind in p["subject"]):
            return re.search(r"token=([A-Za-z0-9_-]+)", p["text"]).group(1)
    return None
def setting(k, v): S.put(db, k, v); security_mw.clear_cache()

with TestClient(srv.app) as c:
    setting("security.rate_limit_auth_per_minute", 1000); setting("security.rate_limit_write_per_minute", 1000)
    setting("email.enabled", True); setting("email.from_address", "hello@mail.example.com"); security.save_provider_key(db, "resend", "re_abcdefghijk12345")
    # ---------------- public + headers
    r = c.get("/api/public/settings")
    check(r.status_code == 200 and r.json()["features.maintenance"] is False and "security.max_body_kb" not in r.json() and "billing.mode" not in r.json(), "public settings readable; private ones not exposed")
    h = r.headers
    check(h["x-content-type-options"] == "nosniff" and "frame-ancestors 'none'" in h["content-security-policy"] and h["x-request-id"] and h["referrer-policy"], "security headers on every response")
    check(c.get("/api/auth/me").headers["cache-control"] == "no-store", "auth responses are not cached")
    r = c.get("/api/nope"); check(r.status_code == 404 and r.json()["error"]["code"] == "HTTP_404", "errors use one JSON shape")
    r = c.post("/api/auth/register", json={"email": "x"})
    check(r.status_code == 422 and r.json()["error"]["code"] == "BAD_REQUEST" and r.json()["error"]["fields"], "validation errors list fields, not values")
    r = c.post("/api/contact", content=b"{" + b'"message":"' + b"a" * 300000 + b'"}', headers={"content-type": "application/json"})
    check(r.status_code == 413 and r.json()["error"]["code"] == "TOO_LARGE", "oversized body refused")
    check(c.get("/api/admin/settings").status_code == 401 and c.get("/api/admin/users").status_code == 401 and c.put("/api/admin/keys/resend", json={"key": "re_abcdefghijk1"}).status_code == 401, "admin routes: 401 when signed out")
    check(c.post("/api/jobs/tick").status_code == 401 and c.post("/api/jobs/tick", headers={"x-cron-secret": "s3cret"}).status_code == 200, "tick: refuses a bad secret, accepts the right one")

    # ---------------- CSRF / origin
    r = c.post("/api/auth/login", json={"email": "a@b.co", "password": "x"}, headers={"origin": "https://evil.test"})
    check(r.status_code == 403 and r.json()["error"]["code"] == "BAD_ORIGIN", "state-changing request from a foreign origin refused")
    r = c.post("/api/auth/login", json={"email": "a@b.co", "password": "x"}, headers={"origin": "http://testserver"})
    check(r.status_code == 401, "same-origin request passes the origin check")
    r = c.post("/api/auth/login", json={"email": "a@b.co", "password": "x"}, headers={"sec-fetch-site": "cross-site"})
    check(r.status_code == 403, "cross-site fetch metadata refused")
    setting("security.allowed_origins", ["https://app.test"])
    check(c.post("/api/auth/login", json={"email": "a@b.co", "password": "x"}, headers={"origin": "https://app.test"}).status_code == 401, "configured front-end origin accepted")
    setting("security.allowed_origins", [])

    # ---------------- sign up, verify, sign in
    reg = lambda e, p="correct-horse-1": c.post("/api/auth/register", json={"email": e, "password": p, "display_name": "Fan", "tz": "America/Toronto"})
    r1, r2 = reg("fan@example.com"), reg("fan@example.com")
    check(r1.status_code == r2.status_code == 202 and r1.json() == r2.json(), "sign-up answers the same for a new and a taken e-mail")
    check(len([p for p in sent if p["to"] == ["fan@example.com"]]) == 1, "only the real new account gets a verify e-mail")
    check(reg("short@example.com", "short").status_code == 400, "weak password refused")
    check(c.post("/api/auth/login", json={"email": "fan@example.com", "password": "correct-horse-1"}).json()["error"]["code"] == "EMAIL_NOT_VERIFIED", "cannot sign in before confirming e-mail")
    tok = token_for("fan@example.com")
    check(c.post("/api/auth/verify-email", json={"token": tok}).status_code == 200 and c.post("/api/auth/verify-email", json={"token": tok}).status_code == 400, "verify link works once")
    check(any("Welcome" in p["subject"] for p in sent), "welcome e-mail sent after verifying")
    r = c.post("/api/auth/login", json={"email": "fan@example.com", "password": "correct-horse-1"})
    sc = r.headers["set-cookie"].lower()
    check(r.status_code == 200 and "httponly" in sc and "samesite=lax" in sc and "path=/" in sc and "sid=" in sc, "session cookie: HttpOnly, SameSite=Lax, Path=/")
    check("password_hash" not in r.text and "totp" not in r.text and r.json()["user"]["email"] == "fan@example.com", "sign-in response has no secrets")
    me = c.get("/api/auth/me").json()
    check(me["user"]["tz"] == "America/Toronto" and me["plan"]["source"] == "billing_off" and me["entitlements"]["finder_searches_per_day"] == -1, "me: profile, plan and limits (billing off = full access)")
    fresh = TestClient(srv.app)
    check(fresh.get("/api/auth/me").json()["user"] is None and fresh.get("/api/auth/me").json()["plan"]["plan_key"] == "free", "signed-out me: free plan, no user")
    check(db.users.find_one({"email": "fan@example.com"})["password_hash"].startswith("$2"), "password stored hashed")

    # ---------------- account settings
    check(c.patch("/api/account/profile", json={"display_name": "Sam", "theme": "dark", "prefs": {"marketing_emails": True}}).json()["user"]["theme"] == "dark", "profile saved")
    check(c.patch("/api/account/profile", json={"theme": "neon"}).status_code == 400 and c.patch("/api/account/profile", json={"tz": "Mars/Base"}).status_code == 400, "bad theme or time zone refused")
    check(fresh.patch("/api/account/profile", json={"theme": "dark"}).status_code == 401, "account routes need sign-in")
    other = TestClient(srv.app); other.post("/api/auth/login", json={"email": "fan@example.com", "password": "correct-horse-1"})
    check(len(c.get("/api/account/sessions").json()["sessions"]) == 2, "two devices listed")
    check(c.post("/api/account/password", json={"current": "wrong", "new": "another-long-pass-2"}).status_code == 403, "password change needs the current password")
    check(c.post("/api/account/password", json={"current": "correct-horse-1", "new": "another-long-pass-2"}).status_code == 200, "password changed")
    check(other.get("/api/auth/me").json()["user"] is None and c.get("/api/auth/me").json()["user"], "other device signed out, this one stays")
    check(any("password was changed" in p["subject"] for p in sent), "security e-mail sent for the change")
    # e-mail change
    r = c.post("/api/account/email", json={"new_email": "sam@example.com", "password": "another-long-pass-2"})
    tk = token_for("sam@example.com")
    check(r.status_code == 202 and tk, "e-mail change: link goes to the NEW address")
    check(c.post("/api/account/email/confirm", json={"token": tk}).status_code == 200 and db.users.find_one({"email": "sam@example.com"}) and any(p["to"] == ["fan@example.com"] and "changed" in p["subject"] for p in sent), "e-mail changed; the old address is told")
    c.post("/api/auth/login", json={"email": "sam@example.com", "password": "another-long-pass-2"})
    # forgot / reset
    check(c.post("/api/auth/forgot-password", json={"email": "ghost@example.com"}).status_code == 202 and c.post("/api/auth/forgot-password", json={"email": "sam@example.com"}).status_code == 202, "forgot-password: 202 for known and unknown")
    rt = token_for("sam@example.com", "Reset")
    check(rt and c.post("/api/auth/reset-password", json={"token": rt, "password": "reset-pass-word-3"}).status_code == 200, "reset link works")
    check(c.get("/api/auth/me").json()["user"] is None, "reset signed out every device")
    check(c.post("/api/auth/reset-password", json={"token": rt, "password": "reset-pass-word-4"}).status_code == 400, "reset link works once")
    # 2FA over HTTP
    c.post("/api/auth/login", json={"email": "sam@example.com", "password": "reset-pass-word-3"})
    b = c.post("/api/account/2fa/begin").json()
    r = c.post("/api/account/2fa/confirm", json={"code": pyotp.TOTP(b["secret"]).now()})
    codes = r.json()["recovery_codes"]
    check(len(codes) == 10, "2FA enabled; recovery codes shown")
    c.post("/api/auth/logout"); check(c.get("/api/auth/me").json()["user"] is None, "logout ends the session")
    r = c.post("/api/auth/login", json={"email": "sam@example.com", "password": "reset-pass-word-3"}).json()
    check(r.get("needs_2fa") and "user" not in r and "set-cookie" not in c.post("/api/auth/login", json={"email": "sam@example.com", "password": "reset-pass-word-3"}).headers, "password alone gives no session when 2FA is on")
    r2 = c.post("/api/auth/login/2fa", json={"challenge": r["challenge"], "code": "000000"})
    check(r2.status_code == 401, "wrong code refused")
    r2 = c.post("/api/auth/login/2fa", json={"challenge": r["challenge"], "code": codes[0]})
    check(r2.status_code == 200 and c.get("/api/auth/me").json()["user"]["two_factor"], "recovery code completes sign-in")
    # export + delete
    ex = c.get("/api/account/export").json()
    check(ex["profile"]["email"] == "sam@example.com" and "password_hash" not in json.dumps(ex, default=str) and "secret_enc" not in json.dumps(ex, default=str), "export has the person's data, no secrets")
    check(c.request("DELETE", "/api/account", json={"password": "wrong"}).status_code == 403, "delete needs the password")
    check(c.request("DELETE", "/api/account", json={"password": "reset-pass-word-3"}).status_code == 200 and c.get("/api/auth/me").json()["user"] is None, "account deleted; signed out")
    check(c.post("/api/auth/login", json={"email": "sam@example.com", "password": "reset-pass-word-3"}).status_code == 401, "deleted account cannot sign in")

    # ---------------- unsubscribe
    tokn = E.sign_unsub("news@example.com")
    check(c.get(f"/api/email/unsubscribe?t={tokn}").json()["email"] == "n***@example.com" and not db.email_suppressions.find_one({"email": "news@example.com"}), "GET unsubscribe only previews (mail scanners open links)")
    check(c.post(f"/api/email/unsubscribe?t={tokn}").status_code == 200 and db.email_suppressions.find_one({"email": "news@example.com"}), "POST unsubscribe works (one-click)")
    check(c.post("/api/email/unsubscribe?t=garbage").status_code == 400, "bad unsubscribe link refused")

    # ---------------- analytics beacon
    ua = "Mozilla/5.0 (Windows NT 10.0) Chrome/120"
    def beacon(name="page_view", path="/", ua=ua, **h): return c.post("/api/analytics/collect", json={"name": name, "path": path, "ref": "https://www.google.com/search?q=x"}, headers={"user-agent": ua, **h})
    n0 = db.events.count_documents({})
    beacon(path="/finder?secret=1"); beacon(ua="Googlebot/2.1"); beacon(DNT="1"); beacon(name="subscribed"); beacon(name="made_up")
    check(db.events.count_documents({}) == n0 + 1, "bots, Do Not Track and unknown/server-only event names are not recorded")
    e = db.events.find_one({"path": "/finder"})
    check(e and e["actor"].startswith("a:") and "ip" not in e and e["ref_host"] == "www.google.com" and "secret" not in json.dumps(e, default=str), "event: no IP, no query string, referrer host only, anonymous daily hash")
    check(c.get("/api/announcements").json() == {"items": []}, "announcements public route works")

    # ---------------- finder quota for signed-out visitors
    db.leagues.insert_one({"id": "lg1", "iid": 1, "ext_id": "x", "name": "L"})
    check(c.get("/api/finder?stat=shots&threshold=1.5").json()["error"]["code"] == "PICK_A_LEAGUE", "free plan searches one league at a time")
    r = [c.get("/api/finder?stat=shots&threshold=1.5&leagues=lg1", headers={"x-forwarded-for": "9.9.9.9"}).status_code for _ in range(4)]
    check(r == [200, 200, 200, 401], "signed-out visitor: 3 searches a day, then sign-in prompt")
    check(c.get("/api/finder?stat=shots&threshold=1.5&leagues=lg1", headers={"x-forwarded-for": "8.8.8.8"}).status_code == 200, "another visitor has their own count")
    # a signed-in person on a billing-on free plan gets the plan's limit
    setting("features.billing", True); S.put(db, "plans.anonymous_finder_searches_per_day", 3)
    c.post("/api/auth/register", json={"email": "free@example.com", "password": "free-user-pass-1"}); c.post("/api/auth/verify-email", json={"token": token_for("free@example.com")})
    c.post("/api/auth/login", json={"email": "free@example.com", "password": "free-user-pass-1"})
    db.plans.update_one({"key": "free"}, {"$set": {"entitlements.finder_searches_per_day": 2}})
    r = [c.get("/api/finder?stat=shots&threshold=1.5&leagues=lg1").status_code for _ in range(3)]
    check(r == [200, 200, 402] and c.get("/api/finder?stat=shots&leagues=lg1").json()["error"]["code"] == "UPGRADE_REQUIRED", "free plan limit enforced for a signed-in person (402 upgrade)")
    setting("features.billing", False)
    check(c.get("/api/finder?stat=shots&threshold=1.5&leagues=lg1").status_code == 200, "billing off: everyone signed in has full access again")
    c.post("/api/auth/logout")

    # ---------------- rate limiting
    setting("security.rate_limit_auth_per_minute", 3)
    codes_ = [c.post("/api/auth/login", json={"email": "z@example.com", "password": "x"}, headers={"x-forwarded-for": "7.7.7.7"}) for _ in range(5)]
    check([x.status_code for x in codes_] == [401, 401, 401, 429, 429] and "retry-after" in codes_[3].headers, "auth rate limit: 429 with Retry-After")
    check(c.post("/api/auth/login", json={"email": "z@example.com", "password": "x"}, headers={"x-forwarded-for": "6.6.6.6"}).status_code == 401, "limit is per IP")
    # spoofing: client adds a fake address on the left; only the rightmost (trusted proxy) entry counts
    codes_ = [c.post("/api/auth/login", json={"email": "z@example.com", "password": "x"}, headers={"x-forwarded-for": f"1.2.3.{i}, 7.7.7.7"}).status_code for i in range(2)]
    check(codes_ == [429, 429], "a spoofed X-Forwarded-For does not dodge the limit")
    setting("security.rate_limit_auth_per_minute", 1000)
    # per-email brake (on top of the IP limit and the account lockout)
    for i in range(10): c.post("/api/auth/login", json={"email": "victim@example.com", "password": "x"}, headers={"x-forwarded-for": f"5.5.5.{i}"})
    check(c.post("/api/auth/login", json={"email": "victim@example.com", "password": "x"}, headers={"x-forwarded-for": "5.5.5.99"}).status_code == 429, "per-e-mail brake stops a spread-out guessing attack")

    # ---------------- crash handling
    @srv.app.get("/api/boom")
    def boom(): raise RuntimeError("secret database password is hunter2")
    srv.app.router.routes.insert(0, srv.app.router.routes.pop())
    r = TestClient(srv.app, raise_server_exceptions=False).get("/api/boom")
    check(r.status_code == 500 and "hunter2" not in r.text and r.json()["error"]["code"] == "SERVER_ERROR" and r.json()["error"]["request_id"], "a crash returns a generic error with a request id, no detail")
    row = db.app_logs.find_one({"status": 500})
    check(row and row["request_id"] == r.json()["error"]["request_id"] and "hunter2" in row["trace"], "the detail goes to the app log for admins")
    check(db.app_logs.find_one({"status": 429}) and db.app_logs.find_one({"status": 403}), "blocked requests are logged")
print("\nALL SERVER CHECKS PASSED")
