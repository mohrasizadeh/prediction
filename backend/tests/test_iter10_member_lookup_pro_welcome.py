# Iteration 10: Member Lookup (admin Money lists + member detail), Pro welcome e-mail (pro_welcome), templates, campaign refusal
import os
import sys
import time
import json
import hmac
import hashlib

import pytest
import requests

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import admin_login_helper as ALH  # noqa: E402

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
ADMIN = {"email": "delivered+t10admin@resend.dev", "password": "Test-Admin-Pass-2026!q"}
MEMBER = {"email": "delivered+t10member@resend.dev", "password": "Test-User-Pass-2026!q"}
ALH.CREDS = ADMIN
ALH.STATE = "/tmp/t10_admin_totp.json"


def _db():
    from dotenv import load_dotenv
    from pymongo import MongoClient
    load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))
    return MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]


@pytest.fixture(scope="module")
def db():
    return _db()


@pytest.fixture(scope="module")
def admin():
    return ALH.admin_session()


@pytest.fixture(scope="module")
def member_id(db):
    u = db.users.find_one({"email": MEMBER["email"]})
    if not u:
        pytest.skip("TEST member missing")
    return u["id"]


# --- Member Lookup: lists carry e-mail
class TestMemberLookup:
    def test_subscriptions_have_email(self, admin, db):
        r = admin.get(f"{BASE_URL}/api/admin/subscriptions", params={"limit": 100})
        assert r.status_code == 200
        rows = r.json()["rows"]
        for x in rows:
            assert "email" in x and isinstance(x["email"], str)
            if not x.get("user_id"):
                assert x["email"] == "Deleted member"
            else:
                u = db.users.find_one({"id": x["user_id"]})
                assert x["email"] == (u["email"] if u else "Deleted member")

    def test_payments_have_email(self, admin, db):
        r = admin.get(f"{BASE_URL}/api/admin/payments", params={"limit": 100})
        assert r.status_code == 200
        for x in r.json()["rows"]:
            assert "email" in x
            if not x.get("user_id"):
                assert x["email"] == "Deleted member"

    def test_member_detail(self, admin, member_id):
        r = admin.get(f"{BASE_URL}/api/admin/users/{member_id}")
        assert r.status_code == 200
        d = r.json()
        assert d["profile"]["email"] == MEMBER["email"]
        assert isinstance(d["subscriptions"], list) and isinstance(d["payments"], list)
        assert "plan_name" in d["plan"]

    def test_member_detail_404(self, admin):
        r = admin.get(f"{BASE_URL}/api/admin/users/nope-not-a-user")
        assert r.status_code == 404


# --- E-mail templates and campaigns
class TestEmailAdmin:
    def test_templates_16(self, admin):
        r = admin.get(f"{BASE_URL}/api/admin/email/templates")
        assert r.status_code == 200
        keys = [t["key"] for t in r.json()["templates"]]
        assert len(keys) == 16 and "pro_welcome" in keys

    def test_pro_welcome_preview(self, admin):
        r = admin.get(f"{BASE_URL}/api/admin/email/templates/pro_welcome/preview")
        assert r.status_code == 200
        d = r.json()
        assert d["subject"] == "Welcome to Forecast Pro"
        assert "renewal" in d["html"] and "2026-12-01" in d["html"]

    def test_campaign_draft_and_send_refused(self, admin, db):
        r = admin.post(f"{BASE_URL}/api/admin/email/campaigns", json={"subject": "TEST_campaign t10", "html": "<p>Hello</p>", "segment": "all"})
        assert r.status_code == 200, r.text
        cid = r.json()["id"]
        try:
            lst = admin.get(f"{BASE_URL}/api/admin/email/campaigns").json()
            assert any(str(c.get("id") or c.get("_id")) == cid for c in lst["rows"]) or cid in json.dumps(lst)
            s = admin.post(f"{BASE_URL}/api/admin/email/campaigns/{cid}/send")
            print("send ->", s.status_code, s.text)
            assert s.status_code == 400
            assert "managed e-mail" in s.text or "Turn on" in s.text
            assert db.email_log.count_documents({"campaign_id": cid}) == 0
        finally:
            from bson import ObjectId
            db.email_campaigns.delete_one({"_id": ObjectId(cid)})


# --- Regression: public billing endpoints
class TestBillingRegression:
    def test_plans(self):
        r = requests.get(f"{BASE_URL}/api/plans")
        assert r.status_code == 200
        d = r.json()
        assert d["billing_enabled"] is True and any(p["key"] == "pro" for p in d["plans"])

    def test_member_billing_and_checkout(self):
        s = requests.Session()
        r = s.post(f"{BASE_URL}/api/auth/login", json=MEMBER)
        assert r.status_code == 200, r.text
        b = s.get(f"{BASE_URL}/api/account/billing")
        assert b.status_code == 200 and "plan" in b.json()


# --- Pro welcome after a real test-mode purchase (run with T10_E2E=1 after the browser checkout)
@pytest.mark.skipif(os.environ.get("T10_E2E") != "1", reason="needs completed checkout")
class TestProWelcome:
    def test_subscription_and_one_welcome(self, db, member_id):
        sub = db.subscriptions.find_one({"user_id": member_id})
        assert sub and sub["status"] in ("active", "trialing")
        logs = list(db.email_log.find({"user_id": member_id, "template": "pro_welcome"}))
        assert len(logs) == 1, logs
        assert logs[0]["status"] == "sent" and logs[0]["to"] == MEMBER["email"]
        assert logs[0]["subject"] == "Welcome to Forecast Pro"

    def test_body_mentions_dates(self, db, member_id):
        import emailer as E
        sub = db.subscriptions.find_one({"user_id": member_id})
        t = E.get_template(db, "pro_welcome")
        assert "{{trial}}" in t["html"] and "{{date}}" in t["html"]
        print("sub trial_end", sub.get("trial_end"), "period_end", sub.get("current_period_end"))

    def test_webhook_replay_no_second_email(self, db, member_id):
        import security
        import stripe_billing as SB
        sub = db.subscriptions.find_one({"user_id": member_id})
        ev = db.webhook_events.find_one({"provider": "stripe", "type": "customer.subscription.created"}, sort=[("received_at", -1)])
        secret = security.get_provider_key(db, "stripe_webhook", "STRIPE_WEBHOOK_SECRET")
        st = SB.Stripe(db)
        sobj = st.req("GET", f"/subscriptions/{sub['_id']}")
        for eid in [ev["_id"].split(":", 1)[1], "evt_TEST_t10_replay_" + str(int(time.time()))]:
            payload = json.dumps({"id": eid, "type": "customer.subscription.created", "created": int(time.time()), "livemode": False,
                                  "data": {"object": sobj}}).encode()
            t = int(time.time())
            sig = hmac.new(secret.encode(), f"{t}.".encode() + payload, hashlib.sha256).hexdigest()
            r = requests.post(f"{BASE_URL}/api/webhooks/stripe", data=payload, headers={"stripe-signature": f"t={t},v1={sig}", "Content-Type": "application/json"})
            print(eid, r.status_code, r.text)
            assert r.status_code == 200
        assert db.email_log.count_documents({"user_id": member_id, "template": "pro_welcome"}) == 1
        db.webhook_events.delete_many({"_id": {"$regex": "^stripe:evt_TEST_t10_replay_"}})
