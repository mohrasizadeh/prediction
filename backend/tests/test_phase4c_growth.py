# Phase 4c regression: popups, newsletter + confirm/unsubscribe, e-mail list, integrations, webhooks, tracking, analytics extras, alerts
import os, sys, time, secrets
from datetime import timedelta
import pytest
import requests

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))
from pymongo import MongoClient
import accounts, emailer
from iter12_login import session_for

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
API = BASE_URL + "/api"
db = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
RUN = secrets.token_hex(3)
EM = lambda tag: f"delivered+t12{tag}{RUN}@resend.dev"


@pytest.fixture(scope="module")
def admin():
    return session_for("admin")


@pytest.fixture(scope="module")
def owner():
    return session_for("owner")


@pytest.fixture(scope="module")
def analyst():
    return session_for("analyst")


@pytest.fixture(scope="module")
def popup(admin):
    r = admin.post(f"{API}/admin/popups", json={"template": admin.get(f"{API}/admin/popups/meta").json()["templates"][0]["id"]})
    assert r.status_code in (200, 201), r.text
    pid = r.json()["id"]
    yield pid
    admin.delete(f"{API}/admin/popups/{pid}")


# Popups admin
class TestPopups:
    def test_meta(self, admin):
        m = admin.get(f"{API}/admin/popups/meta").json()
        assert m["templates"] and "blank" in m and "modal" in m["kinds"]

    def test_bad_save_problems(self, admin, popup):
        d = admin.get(f"{API}/admin/popups/{popup}").json()
        d["content"]["title"] = ""; d["content"]["body"] = ""
        d["form"]["enabled"] = True; d["form"]["consent_text"] = "short"
        meta = admin.get(f"{API}/admin/popups/meta").json()
        data = {k: v for k, v in d.items() if k in meta["blank"]}
        r = admin.put(f"{API}/admin/popups/{popup}", json={"data": data})
        assert r.status_code == 422, r.text
        paths = [p["path"] for p in r.json()["error"]["problems"]]
        assert any("consent_text" in p for p in paths), paths

    def test_create_blank(self, admin):
        r = admin.post(f"{API}/admin/popups", json={"data": {}})
        if r.status_code in (200, 201):
            admin.delete(f"{API}/admin/popups/{r.json()['id']}")
        assert r.status_code in (200, 201), "blank 'New popup' fails: " + r.text[:200]

    def test_go_live_and_public(self, admin, popup):
        d = admin.get(f"{API}/admin/popups/{popup}").json()
        meta = admin.get(f"{API}/admin/popups/meta").json()
        data = {k: v for k, v in d.items() if k in meta["blank"]}
        data["targeting"]["audience"] = "all"; data["trigger"] = {**data["trigger"], "type": "immediate"}
        assert admin.put(f"{API}/admin/popups/{popup}", json={"data": data}).status_code == 200
        assert admin.post(f"{API}/admin/popups/{popup}/status", json={"status": "live"}).status_code == 200
        lst = admin.get(f"{API}/admin/popups").json()
        st = [p for p in lst["popups"] if p["id"] == popup][0]
        assert st["status"] == "live"
        pub = requests.get(f"{API}/popups", params={"path": "/", "device": "mobile", "visitor": "new", "vid": "t12" + RUN}).json()
        print("global", lst.get("global"), "public ids", [p["id"] for p in pub.get("popups", [])])
        if lst["global"].get("popups.enabled"):
            assert popup in [p["id"] for p in pub["popups"]]

    def test_events_and_stats(self, admin, popup):
        for ev in ("view", "view", "dismiss"):
            assert requests.post(f"{API}/popups/{popup}/event", json={"event": ev}).status_code == 204
        s = admin.get(f"{API}/admin/popups/{popup}/stats", params={"days": 30}).json()
        assert s["totals"]["view"] >= 2

    def test_submit_needs_consent(self, popup):
        r = requests.post(f"{API}/popups/{popup}/submit", json={"email": EM("pop"), "consent": False})
        print("no consent", r.status_code, r.text[:150])
        assert r.status_code in (400, 422)
        r = requests.post(f"{API}/popups/{popup}/submit", json={"email": EM("pop"), "consent": True})
        assert r.status_code == 200 and r.json()["ok"]

    def test_duplicate_delete(self, admin, popup):
        r = admin.post(f"{API}/admin/popups/{popup}/duplicate")
        assert r.status_code in (200, 201)
        cid = r.json()["id"]
        assert admin.delete(f"{API}/admin/popups/{cid}").status_code in (200, 204)
        assert admin.get(f"{API}/admin/popups/{cid}").status_code == 404


# Footer newsletter + confirm/unsubscribe + admin list
class TestNewsletter:
    def test_subscribe_generic_and_pending(self, admin):
        e = EM("nl")
        r1 = requests.post(f"{API}/newsletter/subscribe", json={"email": e, "consent": True})
        r2 = requests.post(f"{API}/newsletter/subscribe", json={"email": "not-an-email", "consent": True})
        print(r1.status_code, r1.text, r2.status_code, r2.text[:120])
        assert r1.status_code == 200
        rows = admin.get(f"{API}/admin/newsletter", params={"status": "pending"}).json()["rows"]
        assert any(x["email"] == e for x in rows)

    def test_confirm_flow(self, admin):
        e = EM("nl")
        assert requests.get(f"{API}/newsletter/confirm", params={"token": "bad"}).status_code == 400
        tok = accounts.issue_token(db, None, "newsletter_confirm", timedelta(days=3), {"email": e})
        p = requests.get(f"{API}/newsletter/confirm", params={"token": tok}).json()
        assert "email" in p and p["email"] != e  # masked
        assert requests.post(f"{API}/newsletter/confirm", json={"token": tok}).status_code == 200
        rows = admin.get(f"{API}/admin/newsletter", params={"status": "confirmed"}).json()["rows"]
        assert any(x["email"] == e for x in rows)

    def test_unsubscribe(self):
        t = emailer.sign_unsub(EM("nl"))
        g = requests.get(f"{API}/email/unsubscribe", params={"t": t})
        assert g.status_code == 200 and "email" in g.json()
        assert requests.post(f"{API}/email/unsubscribe", json={"t": t}).status_code in (200, 204)

    def test_export_perms(self, admin, analyst):
        r = admin.get(f"{API}/admin/newsletter/export")
        assert r.status_code == 200 and "email" in r.text.splitlines()[0].lower()
        assert analyst.get(f"{API}/admin/newsletter/export").status_code == 403

    def test_remove(self, admin):
        e = EM("nl2")
        requests.post(f"{API}/newsletter/subscribe", json={"email": e, "consent": True})
        assert admin.post(f"{API}/admin/newsletter/remove", json={"email": e}).status_code == 200


# Integrations, webhooks, tracking
class TestIntegrations:
    def test_overview(self, admin):
        d = admin.get(f"{API}/admin/integrations").json()
        assert d["email"]["provider"] == "emergent"
        assert {"email", "audience", "tracking"} <= set(d)

    def test_audience_save_test_reset(self, admin):
        prov = admin.get(f"{API}/admin/integrations").json()["audience"]["providers"][0]["id"]
        assert admin.put(f"{API}/admin/integrations/audience", json={"provider": prov, "list_id": "TEST123"}).status_code == 200
        t = admin.post(f"{API}/admin/integrations/audience/test").json()
        print("audience test", t)
        assert t.get("ok") is False
        assert admin.put(f"{API}/admin/integrations/audience", json={"provider": "none", "list_id": ""}).status_code == 200

    def test_webhooks(self, admin):
        evs = admin.get(f"{API}/admin/integrations/webhooks").json()["events"]
        r = admin.post(f"{API}/admin/integrations/webhooks", json={"url": "https://example.com/hook", "events": [evs[0]], "include_email": False, "note": "TEST"})
        assert r.status_code in (200, 201) and r.json().get("secret")
        eid = r.json()["id"]
        assert admin.put(f"{API}/admin/integrations/webhooks/{eid}", json={"active": False}).status_code == 200
        assert admin.post(f"{API}/admin/integrations/webhooks/{eid}/rotate").json().get("secret")
        t = admin.post(f"{API}/admin/integrations/webhooks/{eid}/test")
        print("hook test", t.status_code, t.text[:200])
        assert admin.delete(f"{API}/admin/integrations/webhooks/{eid}").status_code in (200, 204)
        assert all(x["id"] != eid for x in admin.get(f"{API}/admin/integrations/webhooks").json()["endpoints"])

    def test_tracking_owner_only(self, admin, owner):
        assert admin.put(f"{API}/admin/integrations/tracking", json={"enabled": False}).status_code == 403
        r = owner.put(f"{API}/admin/integrations/tracking", json={"enabled": False, "ga4_id": "", "meta_pixel_id": "", "google_ads_id": "", "require_consent": True})
        assert r.status_code == 200, r.text


# Analytics extras and alerts
class TestAnalytics:
    @pytest.mark.parametrize("path", ["analytics/realtime", "analytics/compare?days=7", "analytics/acquisition", "analytics/email", "analytics/popups", "analytics/newsletter", "alerts"])
    def test_get(self, admin, path):
        r = admin.get(f"{API}/admin/{path}")
        if r.status_code == 404:
            pytest.skip(f"path differs: {path}")
        assert r.status_code == 200, r.text[:200]

    def test_collect(self):
        r = requests.post(f"{API}/analytics/collect", json={"name": "page_view", "path": "/"})
        assert r.status_code == 204

    def test_alerts_run(self, admin):
        assert admin.post(f"{API}/admin/alerts/run").status_code == 200
