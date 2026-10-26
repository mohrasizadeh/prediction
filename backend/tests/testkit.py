"""testkit.py -- shared set-up for the HTTP self-tests: an app on an in-memory MongoDB, mocked outside services,
an owner with two-factor on, and one staff member per role. Only used by tests."""
import base64, hashlib, json, os, re, sys, time
os.environ.update({"APP_ENCRYPTION_KEY": base64.b64encode(os.urandom(32)).decode(), "MONGO_URL": "mongomock://x", "DB_NAME": "kit",
                   "ADMIN_EMAIL": "boss@example.com", "ADMIN_INITIAL_PASSWORD": "boss-pass-12345", "CRON_SHARED_SECRET": "s3cret",
                   "COOKIE_SECURE": "0", "BCRYPT_ROUNDS": "4", "PUBLIC_BASE_URL": "https://app.test"})
HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("SOCCER_BRAIN_DIR", os.path.join(HERE, "soccer_brain"))
sys.path.insert(0, HERE); sys.path.insert(0, os.environ["SOCCER_BRAIN_DIR"])
import httpx, mongomock, pyotp
from fastapi.testclient import TestClient
import server as srv, emailer as E, security, settings_store as S, security_mw, accounts as A, integrations as INT, transports as T

db = mongomock.MongoClient()["kit"]; srv.set_db(db)
sent = []            # every e-mail payload sent through any provider, normalised to Resend's shape
calls = []           # every outgoing HTTP request: (method, url, headers, json-or-None)
web = {"status": 200}   # what outside webhook receivers answer


def check(c, m):
    if not c:
        print("  FAIL", m); sys.exit(1)
    print("  ok  ", m)


def handler(r: httpx.Request):
    body = None
    try:
        body = json.loads(r.content) if r.content and r.headers.get("content-type", "").startswith("application/json") else (r.content.decode() if r.content else None)
    except Exception:
        body = r.content.decode(errors="replace")
    calls.append((r.method, str(r.url), dict(r.headers), body))
    h = r.url.host
    if h == "api.resend.com":
        sent.append(body); return httpx.Response(200, json={"id": f"em_{len(sent)}"})
    if h == "api.postmarkapp.com":
        if r.url.path == "/server": return httpx.Response(200, json={"Name": "x"})
        sent.append({"to": [body["To"]], "subject": body["Subject"], "text": body["TextBody"], "html": body["HtmlBody"]}); return httpx.Response(200, json={"MessageID": f"pm_{len(sent)}", "ErrorCode": 0})
    if h == "api.sendgrid.com":
        if r.url.path == "/v3/scopes": return httpx.Response(200, json={"scopes": []})
        sent.append({"to": [body["personalizations"][0]["to"][0]["email"]], "subject": body["subject"], "text": body["content"][0]["value"], "html": body["content"][1]["value"]})
        return httpx.Response(202, headers={"X-Message-Id": f"sg_{len(sent)}"})
    if h == "api.brevo.com":
        if r.url.path == "/v3/smtp/email":
            sent.append({"to": [body["to"][0]["email"]], "subject": body["subject"], "text": body["textContent"], "html": body["htmlContent"]}); return httpx.Response(201, json={"messageId": f"<b{len(sent)}>"})
        if r.url.path == "/v3/account": return httpx.Response(200, json={"email": "x"})
        return httpx.Response(web.get("audience", 201), json={"id": 1} if web.get("audience", 201) < 300 else {"message": "denied"})
    if h.endswith("api.mailchimp.com"):
        return httpx.Response(web.get("audience", 200), json={"id": "m"} if web.get("audience", 200) < 300 else {"title": "denied", "detail": "bad key"})
    if h == "connect.mailerlite.com":
        return httpx.Response(web.get("audience", 200), json={"data": {}} if web.get("audience", 200) < 300 else {"message": "denied"})
    if h.startswith("hooks"):
        return httpx.Response(web["status"], text="ok")
    return httpx.Response(404)


E.set_http_factory(lambda: httpx.Client(transport=httpx.MockTransport(handler))); E.set_sleep(lambda s: None)
INT.set_resolver(lambda host, port, proto=0: [(2, 1, 6, "", ({"private.example.com": "10.0.0.5", "local.example.com": "127.0.0.1"}.get(host, "93.184.216.34"), port))])


def setting(k, v):
    S.put(db, k, v); security_mw.clear_cache()


def token_from(to, kind):
    for p in reversed(sent):
        if p and p.get("to") == [to] and kind in p["subject"]:
            return re.search(r"token=([A-Za-z0-9_-]+)", p["text"]).group(1)


def boot(owner):
    """Owner enrols 2FA and gets an admin, support and analyst colleague. Returns (admin, support, analyst, login_codes)."""
    setting("security.rate_limit_auth_per_minute", 1000); setting("security.rate_limit_write_per_minute", 1000); setting("security.rate_limit_read_per_minute", 1000)
    setting("email.enabled", True); setting("email.from_address", "hello@mail.example.com"); security.save_provider_key(db, "resend", "re_abcdefghijk12345")
    owner.post("/api/auth/login", json={"email": "boss@example.com", "password": "boss-pass-12345"})
    b = owner.post("/api/account/2fa/begin").json()
    owner.post("/api/account/2fa/confirm", json={"code": pyotp.TOTP(b["secret"]).now()})

    def make_staff(role):
        email = f"{role}@example.com"
        r = owner.post("/api/admin/staff/invite", json={"email": email, "role": role})
        check(r.status_code == 200, f"owner invites {role}")
        cl = TestClient(srv.app)
        cl.post("/api/auth/reset-password", json={"token": token_from(email, "team"), "password": f"{role}-first-pass-1"})
        cl.post("/api/auth/login", json={"email": email, "password": f"{role}-first-pass-1"})
        b = cl.post("/api/account/2fa/begin").json(); cl.post("/api/account/2fa/confirm", json={"code": pyotp.TOTP(b["secret"]).now()})
        return cl
    return make_staff("admin"), make_staff("support"), make_staff("analyst")
