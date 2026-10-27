# Phase 4d gaps: Admin e-mail log, Admin images (site assets), public contact form, Finder usage counter
import base64
import os
import re
import sys
import time

import pytest
import requests
from dotenv import load_dotenv
from pymongo import MongoClient

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import admin_login_helper as H  # noqa: E402

load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))
BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
db = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/120 Safari/537.36"}
PNG = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==")


@pytest.fixture(scope="module")
def admin():
    return H.admin_session()


@pytest.fixture(scope="module")
def analyst():
    import json
    c = json.load(open("/tmp/t12_cookies.json"))["analyst"]
    s = requests.Session()
    for k, v in c.items():
        s.cookies.set(k, v, domain=BASE_URL.split("//")[1])
    return s


@pytest.fixture(scope="module")
def user():
    s = requests.Session()
    s.headers.update(UA)
    r = s.post(f"{BASE_URL}/api/auth/login", json={"email": "test_e1_user@example.com", "password": "Test-User-Pass-2026!q"})
    assert r.status_code == 200, r.text
    return s


# ---------------------------------------------------------------- e-mail log
class TestEmailLog:
    def test_admin_sees_rows_newest_first_unmasked(self, admin):
        r = admin.get(f"{BASE_URL}/api/admin/logs/email", params={"page": 1, "limit": 50})
        assert r.status_code == 200
        d = r.json()
        assert {"rows", "page", "limit", "total"} <= d.keys()
        ats = [x["at"] for x in d["rows"]]
        assert ats == sorted(ats, reverse=True)
        assert all("_id" not in x for x in d["rows"])
        if d["rows"]:
            assert "*" not in d["rows"][0]["to"]

    def test_analyst_sees_masked_to(self, analyst):
        r = analyst.get(f"{BASE_URL}/api/admin/logs/email")
        assert r.status_code == 200, r.text
        rows = r.json()["rows"]
        assert rows, "expected some email_log rows"
        assert all("*" in x["to"] or "…" in x["to"] for x in rows), rows[0]["to"]

    def test_status_filter(self, admin):
        st = db.email_log.distinct("status")[0]
        r = admin.get(f"{BASE_URL}/api/admin/logs/email", params={"status": st})
        assert r.status_code == 200
        assert r.json()["total"] == db.email_log.count_documents({"status": st})
        assert all(x["status"] == st for x in r.json()["rows"])

    def test_ui_status_options_match_real_statuses(self):
        # The UI dropdown offers LOG_TONE keys; real rows use emailer statuses
        ui = {"sent", "delivered", "failed", "bounced", "complained", "skipped", "queued"}
        real = set(db.email_log.distinct("status"))
        missing = real - ui
        assert not missing, f"statuses in email_log not selectable in UI filter: {missing}"

    def test_template_filter(self, admin):
        t = db.email_log.distinct("template")[0]
        r = admin.get(f"{BASE_URL}/api/admin/logs/email", params={"template": t})
        assert r.status_code == 200
        assert r.json()["total"] == db.email_log.count_documents({"template": t})
        assert all(x["template"] == t for x in r.json()["rows"])

    def test_anon_forbidden(self):
        assert requests.get(f"{BASE_URL}/api/admin/logs/email").status_code in (401, 403)


# ---------------------------------------------------------------- images
class TestImages:
    ids = []

    def test_upload_list_fetch_delete(self, admin):
        r = admin.post(f"{BASE_URL}/api/admin/site/assets", json={"name": "TEST_pixel.png", "data_b64": base64.b64encode(PNG).decode()})
        assert r.status_code == 200, r.text
        a = r.json()
        assert a["url"] == f"/api/site/assets/{a['id']}" and a["mime"] == "image/png"
        self.ids.append(a["id"])
        lst = admin.get(f"{BASE_URL}/api/admin/site/assets").json()
        assert lst["max_bytes"] == 512 * 1024
        assert lst["assets"][0]["id"] == a["id"]
        img = requests.get(BASE_URL + a["url"])
        assert img.status_code == 200 and img.content == PNG
        d = admin.delete(f"{BASE_URL}/api/admin/site/assets/{a['id']}")
        assert d.status_code == 200
        assert all(x["id"] != a["id"] for x in admin.get(f"{BASE_URL}/api/admin/site/assets").json()["assets"])
        assert requests.get(BASE_URL + a["url"]).status_code == 404

    def test_oversize_and_bad_type(self, admin):
        big = PNG + b"\0" * (520 * 1024)
        r = admin.post(f"{BASE_URL}/api/admin/site/assets", json={"name": "TEST_big.png", "data_b64": base64.b64encode(big).decode()})
        assert r.status_code in (400, 422)
        r = admin.post(f"{BASE_URL}/api/admin/site/assets", json={"name": "TEST_x.svg", "data_b64": base64.b64encode(b"<svg></svg>").decode()})
        assert r.status_code == 400

    def test_in_use_delete_blocked(self, admin):
        a = admin.post(f"{BASE_URL}/api/admin/site/assets", json={"name": "TEST_inuse.png", "data_b64": base64.b64encode(PNG).decode()}).json()
        self.ids.append(a["id"])
        pid = db.popups.insert_one({"name": "TEST inuse ref", "status": "draft", "content": {"image": a["url"]}}).inserted_id
        try:
            r = admin.delete(f"{BASE_URL}/api/admin/site/assets/{a['id']}")
            assert r.status_code == 409
            assert "used" in r.text
            assert any(x["id"] == a["id"] for x in admin.get(f"{BASE_URL}/api/admin/site/assets").json()["assets"])
        finally:
            db.popups.delete_one({"_id": pid})
        assert admin.delete(f"{BASE_URL}/api/admin/site/assets/{a['id']}").status_code == 200

    @classmethod
    def teardown_class(cls):
        db.site_assets.delete_many({"_id": {"$in": cls.ids}})


# ---------------------------------------------------------------- contact
class TestContact:
    @pytest.fixture(autouse=True)
    def _clear_rl(self):
        db.rate_limits.delete_many({"_id": re.compile("^contact:")})
        yield
        db.rate_limits.delete_many({"_id": re.compile("^contact:")})
        db.contact_messages.delete_many({"email": re.compile("^test_contact.*@example.com$")})

    def test_send_and_appears_in_inbox(self, admin):
        r = requests.post(f"{BASE_URL}/api/contact", json={"name": "TEST Contact", "email": "test_contact1@example.com", "message": "TEST hello there"}, headers=UA)
        assert r.status_code == 202 and r.json() == {"ok": True}
        doc = db.contact_messages.find_one({"email": "test_contact1@example.com"})
        assert doc and doc["message"] == "TEST hello there" and doc["status"] == "new"
        inbox = admin.get(f"{BASE_URL}/api/admin/inbox")
        assert inbox.status_code == 200, inbox.text
        assert "test_contact1@example.com" in inbox.text

    def test_short_message_rejected(self):
        r = requests.post(f"{BASE_URL}/api/contact", json={"email": "test_contact2@example.com", "message": "hey"}, headers=UA)
        assert r.status_code == 400

    def test_rate_limit_4th(self):
        codes = [requests.post(f"{BASE_URL}/api/contact", json={"email": f"test_contact_rl{i}@example.com", "message": "TEST rate limit"}, headers=UA).status_code for i in range(4)]
        assert codes[:3] == [202, 202, 202]
        assert codes[3] == 429


# ---------------------------------------------------------------- finder usage
class TestFinderUsage:
    @pytest.fixture(scope="class")
    def lg(self):
        return requests.get(f"{BASE_URL}/api/leagues").json()["countries"][0]["leagues"][0]["id"]

    @pytest.fixture(autouse=True)
    def _clean(self):
        u = db.users.find_one({"email": "test_e1_user@example.com"})
        db.finder_usage.delete_many({"subject": f"u:{u['id']}"})
        yield u
        db.finder_usage.delete_many({"subject": f"u:{u['id']}"})

    def test_anon_limit_in_me(self):
        me = requests.get(f"{BASE_URL}/api/auth/me").json()
        assert me["user"] is None
        assert isinstance(me["limits"]["anonymous_finder_searches_per_day"], int)

    def test_free_user_counter_increments(self, user, lg):
        me = user.get(f"{BASE_URL}/api/auth/me").json()
        assert me["entitlements"]["finder_searches_per_day"] == 10
        assert me["usage"]["finder_today"] == 0
        r = user.get(f"{BASE_URL}/api/finder", params={"stat": "shots", "threshold": 1.5, "leagues": lg})
        assert r.status_code == 200, r.text
        assert user.get(f"{BASE_URL}/api/auth/me").json()["usage"]["finder_today"] == 1

    def test_cap_reached(self, user, lg, _clean):
        db.finder_usage.update_one({"subject": f"u:{_clean['id']}", "day": time.strftime("%Y-%m-%d", time.gmtime()), "name": "finder"},
                                   {"$set": {"count": 10}}, upsert=True)
        r = user.get(f"{BASE_URL}/api/finder", params={"stat": "shots", "threshold": 1.5, "leagues": lg})
        assert r.status_code == 402
        assert user.get(f"{BASE_URL}/api/auth/me").json()["usage"]["finder_today"] == 10
