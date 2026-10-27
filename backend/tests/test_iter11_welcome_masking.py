# Iteration 11: pro_welcome on first move into active/trialing (synthetic Stripe events), e-mail masking per role, campaign refusal order, preview sample
import os
import sys
import time
import datetime

import pytest
import requests

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.dirname(HERE))
from dotenv import load_dotenv  # noqa: E402
load_dotenv(os.path.join(os.path.dirname(HERE), ".env"))
import admin_login_helper as ALH  # noqa: E402

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
ADMIN = {"email": "delivered+t11admin@resend.dev", "password": "Test-Admin-Pass-2026!q"}
ANALYST = {"email": "delivered+t11analyst@resend.dev", "password": "Test-Admin-Pass-2026!q"}
MEMBER_EMAIL = "delivered+t11member@resend.dev"
PRICE = "price_1UUxVBGfBF8i81YjXwMt8g0X"


def _db():
    from pymongo import MongoClient
    return MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]


def _session(creds, state):
    ALH.CREDS, ALH.STATE = creds, state
    return ALH.admin_session()


@pytest.fixture(scope="module")
def db():
    return _db()


@pytest.fixture(scope="module")
def member(db):
    u = db.users.find_one({"email": MEMBER_EMAIL})
    if not u:
        pytest.skip("TEST member missing; run iter11_users.py")
    return u


@pytest.fixture(scope="module")
def admin():
    return _session(ADMIN, "/tmp/t11_admin_totp.json")


@pytest.fixture(scope="module")
def analyst():
    return _session(ANALYST, "/tmp/t11_analyst_totp.json")


def _sub(sid, uid, status, trial_end=None):
    now = int(time.time())
    return {"id": sid, "object": "subscription", "customer": "cus_TEST_t11", "status": status, "metadata": {"user_id": uid},
            "created": now, "cancel_at_period_end": False, "trial_end": trial_end,
            "items": {"data": [{"price": {"id": PRICE, "unit_amount": 999, "currency": "cad", "recurring": {"interval": "month"}},
                                "current_period_start": now, "current_period_end": now + 30 * 86400}]}}


_n = [0]


def _event(typ, obj):
    _n[0] += 1
    return {"id": f"evt_TEST_t11_{int(time.time())}_{_n[0]}", "type": typ, "created": int(time.time()) + _n[0], "livemode": False, "data": {"object": obj}}


@pytest.fixture(scope="module")
def notify(db):
    import routes_billing as RB
    real = RB.make_notify(db)
    calls = []

    def n(kind, user, ctx):
        calls.append((kind, ctx))
        real(kind, user, ctx)
    n.calls = calls
    return n


def _welcomes(db, uid):
    return list(db.email_log.find({"user_id": uid, "template": "pro_welcome"}))


# --- pro_welcome: incomplete -> active sends once
class TestWelcomeTransitions:
    def test_incomplete_then_active_once(self, db, member, notify):
        import stripe_billing as SB
        sid = "sub_TEST_t11_inc"
        assert SB.handle_event(db, _event("customer.subscription.created", _sub(sid, member["id"], "incomplete")), notify) == "processed"
        assert len(_welcomes(db, member["id"])) == 0
        assert not any(k == "pro_welcome" for k, _ in notify.calls)
        SB.handle_event(db, _event("customer.subscription.updated", _sub(sid, member["id"], "active")), notify)
        w = _welcomes(db, member["id"])
        assert len(w) == 1, w
        assert w[0]["status"] == "sent" and w[0]["to"] == MEMBER_EMAIL and w[0]["subject"] == "Welcome to Forecast Pro"
        ctx = [c for k, c in notify.calls if k == "pro_welcome"][-1]
        assert ctx["trial"] == "" and ctx["sub"] == sid
        datetime.datetime.strptime(ctx["date"], "%d %B %Y")
        # further updates: active again, past_due -> active: no second welcome
        SB.handle_event(db, _event("customer.subscription.updated", _sub(sid, member["id"], "active")), notify)
        SB.handle_event(db, _event("customer.subscription.updated", _sub(sid, member["id"], "past_due")), notify)
        SB.handle_event(db, _event("customer.subscription.updated", _sub(sid, member["id"], "active")), notify)
        assert len(_welcomes(db, member["id"])) == 1
        assert sum(1 for k, _ in notify.calls if k == "pro_welcome") == 1

    def test_replay_same_event_duplicate(self, db, member, notify):
        import stripe_billing as SB
        ev = _event("customer.subscription.updated", _sub("sub_TEST_t11_inc", member["id"], "active"))
        SB.handle_event(db, ev, notify)
        assert SB.handle_event(db, ev, notify) == "duplicate"
        assert len(_welcomes(db, member["id"])) == 1

    def test_unpaid_to_active_idem_blocks_second(self, db, member, notify):
        # prev_status 'unpaid' is not in the guard list, so notify is called again; idem key must stop the second e-mail
        import stripe_billing as SB
        sid = "sub_TEST_t11_inc"
        SB.handle_event(db, _event("customer.subscription.updated", _sub(sid, member["id"], "unpaid")), notify)
        SB.handle_event(db, _event("customer.subscription.updated", _sub(sid, member["id"], "active")), notify)
        print("notify pro_welcome calls", sum(1 for k, _ in notify.calls if k == "pro_welcome"))
        assert len([w for w in _welcomes(db, member["id"]) if w["status"] == "sent"]) == 1

    def test_trialing_created_has_trial_sentence(self, db, member, notify):
        import stripe_billing as SB
        sid = "sub_TEST_t11_trial"
        te = int(time.time()) + 14 * 86400
        SB.handle_event(db, _event("customer.subscription.created", _sub(sid, member["id"], "trialing", te)), notify)
        ctx = [c for k, c in notify.calls if k == "pro_welcome" and c["sub"] == sid]
        assert len(ctx) == 1
        d = datetime.datetime.fromtimestamp(te, datetime.timezone.utc).strftime("%d %B %Y")
        assert ctx[0]["trial"] == f"Your free trial runs until {d}. " and ctx[0]["date"] == d
        assert db.email_log.count_documents({"user_id": member["id"], "template": "pro_welcome", "idem": {"$regex": sid}, "status": "sent"}) == 1
        # trialing -> active must not send again
        SB.handle_event(db, _event("customer.subscription.updated", _sub(sid, member["id"], "active", te)), notify)
        assert len([c for k, c in notify.calls if k == "pro_welcome" and c["sub"] == sid]) == 1


# --- PII masking on Money lists
class TestMasking:
    @pytest.fixture(scope="class", autouse=True)
    def payment(self, db, member):
        db.payments.update_one({"_id": "in_TEST_t11_1"}, {"$set": {"user_id": member["id"], "status": "paid", "amount_paid": 999, "currency": "cad",
                                                                   "created_at": datetime.datetime.now(datetime.timezone.utc), "subscription_id": "sub_TEST_t11_inc"}}, upsert=True)

    def _row(self, s, path, key):
        r = s.get(f"{BASE_URL}/api/admin/{path}", params={"limit": 100})
        assert r.status_code == 200, r.text
        rows = [x for x in r.json()["rows"] if (x.get("id") or x.get("_id")) == key]
        assert rows, f"{key} not in {path}"
        return rows[0]

    def test_admin_sees_full(self, admin):
        assert self._row(admin, "subscriptions", "sub_TEST_t11_inc")["email"] == MEMBER_EMAIL
        assert self._row(admin, "payments", "in_TEST_t11_1")["email"] == MEMBER_EMAIL

    def test_analyst_masked(self, analyst):
        for path, key in (("subscriptions", "sub_TEST_t11_inc"), ("payments", "in_TEST_t11_1")):
            e = self._row(analyst, path, key)["email"]
            assert e == "d***@resend.dev", e

    def test_analyst_no_full_email_anywhere(self, analyst):
        for path in ("subscriptions", "payments"):
            txt = analyst.get(f"{BASE_URL}/api/admin/{path}", params={"limit": 100}).text
            assert MEMBER_EMAIL not in txt


# --- Campaign refusal (managed provider) even with marketing off; preview sample
class TestEmailAdmin:
    def test_campaign_refused_managed_first(self, admin, db):
        import settings_store as S
        assert S.get(db, "email.marketing_enabled") is False
        r = admin.post(f"{BASE_URL}/api/admin/email/campaigns", json={"subject": "TEST_t11 campaign", "html": "<p>Hi</p>", "segment": "all"})
        assert r.status_code == 200, r.text
        cid = r.json()["id"]
        s = admin.post(f"{BASE_URL}/api/admin/email/campaigns/{cid}/send")
        print(s.status_code, s.text)
        assert s.status_code == 400
        assert "managed e-mail service" in s.text and "Turn on" not in s.text
        assert db.email_log.count_documents({"campaign_id": cid}) == 0

    def test_preview_trial_and_date(self, admin):
        r = admin.get(f"{BASE_URL}/api/admin/email/templates/pro_welcome/preview")
        assert r.status_code == 200
        d = r.json()
        assert "Your free trial runs until 01 December 2026." in d["html"]
        assert "01 December 2026" in d["text"] and "2026-12-01" not in d["html"]
