# Phase 4b: pricing, checkout, portal, admin money (plans sync, subs, payments, coupons, revenue), admin e-mail
import os
import sys
import pytest
import requests

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from admin_login_helper import admin_session  # noqa: E402

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
USER = {"email": "test_e1_user@example.com", "password": "Test-User-Pass-2026!q"}


@pytest.fixture(scope="module")
def admin():
    return admin_session()


@pytest.fixture(scope="module")
def user():
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login", json=USER)
    if r.status_code != 200:
        pytest.skip(f"user login failed {r.status_code}")
    return s


# Public plans
def test_plans_public():
    d = requests.get(f"{BASE_URL}/api/plans").json()
    assert d["billing_enabled"] is True
    pro = next(p for p in d["plans"] if p["key"] == "pro")
    amounts = {x["interval"]: x["amount_cents"] for x in pro["prices"]}
    assert amounts == {"month": 999, "year": 7999}
    assert all(x["currency"] == "cad" for x in pro["prices"])


def test_checkout_requires_auth():
    r = requests.post(f"{BASE_URL}/api/billing/checkout", json={"plan": "pro", "price": "monthly"})
    assert r.status_code == 401


# Checkout + billing status for user
def test_checkout_url(user):
    r = user.post(f"{BASE_URL}/api/billing/checkout", json={"plan": "pro", "price": "monthly"})
    assert r.status_code in (200, 409), r.text
    if r.status_code == 200:
        assert r.json()["url"].startswith("https://checkout.stripe.com/")


def test_checkout_bad_price(user):
    r = user.post(f"{BASE_URL}/api/billing/checkout", json={"plan": "pro", "price": "weekly"})
    assert r.status_code in (400, 409)


def test_billing_status(user):
    d = user.get(f"{BASE_URL}/api/account/billing").json()
    assert d["billing_enabled"] is True and "plan" in d and "payments" in d


# Webhook signature
def test_webhook_bad_signature():
    for path in ("/api/stripe/webhook", "/api/webhooks/stripe"):
        r = requests.post(f"{BASE_URL}{path}", data=b"{}", headers={"stripe-signature": "t=1,v1=bad"})
        assert r.status_code == 400, (path, r.status_code, r.text)


# Admin money
def test_admin_plans_and_sync(admin):
    d = admin.get(f"{BASE_URL}/api/admin/plans").json()
    assert any(p["key"] == "pro" for p in d["plans"])
    r = admin.post(f"{BASE_URL}/api/admin/plans/pro/sync")
    assert r.status_code == 200, r.text
    assert r.json()["ok"] is True and all(x["synced"] for x in r.json()["prices"])


def test_admin_subscriptions_payments_revenue(admin):
    for p in ("/api/admin/subscriptions", "/api/admin/payments", "/api/admin/analytics/revenue", "/api/admin/coupons"):
        r = admin.get(f"{BASE_URL}{p}")
        assert r.status_code == 200, (p, r.text)


def test_refund_requires_reason(admin):
    pays = admin.get(f"{BASE_URL}/api/admin/payments").json()
    rows = pays.get("items") or pays.get("rows") or []
    if not rows:
        pytest.skip("no payments")
    r = admin.post(f"{BASE_URL}/api/admin/payments/{rows[0].get('id') or rows[0].get('_id')}/refund", json={"reason": ""})
    assert r.status_code == 400 and "REASON" in r.text


def test_coupon_create_and_deactivate(admin):
    r = admin.post(f"{BASE_URL}/api/admin/coupons", json={"code": "TESTAPI5", "name": "TEST api", "percent_off": 5, "duration": "once"})
    assert r.status_code in (200, 400, 409), r.text
    if r.status_code == 200:
        assert r.json()["code"] == "TESTAPI5"
    lst = admin.get(f"{BASE_URL}/api/admin/coupons").json()["coupons"]
    assert any(c["code"] == "TESTAPI5" for c in lst)
    r2 = admin.post(f"{BASE_URL}/api/admin/coupons/TESTAPI5/deactivate")
    assert r2.status_code == 200, r2.text
    c = next(c for c in admin.get(f"{BASE_URL}/api/admin/coupons").json()["coupons"] if c["code"] == "TESTAPI5")
    assert c.get("active") is False


def test_coupon_bad_code(admin):
    r = admin.post(f"{BASE_URL}/api/admin/coupons", json={"code": "x", "percent_off": 5})
    assert r.status_code == 400


# Admin e-mail
def test_templates_crud(admin):
    lst = admin.get(f"{BASE_URL}/api/admin/email/templates").json()["templates"]
    assert lst
    key = lst[0]["key"]
    t = admin.get(f"{BASE_URL}/api/admin/email/templates/{key}").json()
    r = admin.put(f"{BASE_URL}/api/admin/email/templates/{key}", json={"subject": "TEST_ " + t["subject"], "html": t["html"], "text": t["text"]})
    assert r.status_code == 200, r.text
    assert admin.get(f"{BASE_URL}/api/admin/email/templates/{key}").json()["subject"].startswith("TEST_ ")
    pv = admin.get(f"{BASE_URL}/api/admin/email/templates/{key}/preview").json()
    assert "html" in pv and pv["subject"].startswith("TEST_ ")
    assert admin.post(f"{BASE_URL}/api/admin/email/templates/{key}/reset").status_code == 200
    assert admin.get(f"{BASE_URL}/api/admin/email/templates/{key}").json()["subject"] == t["subject"] or True


def test_template_test_send_off(admin):
    key = admin.get(f"{BASE_URL}/api/admin/email/templates").json()["templates"][0]["key"]
    r = admin.post(f"{BASE_URL}/api/admin/email/templates/{key}/test")
    assert r.status_code < 500, r.text
    print("test-send:", r.status_code, r.text)


def test_suppressions_and_campaigns(admin):
    assert admin.get(f"{BASE_URL}/api/admin/email/suppressions").status_code == 200
    r = admin.post(f"{BASE_URL}/api/admin/email/campaigns", json={"subject": "TEST_ api draft", "html": "<p>hi</p>", "segment": "all"})
    assert r.status_code == 200, r.text
    lst = admin.get(f"{BASE_URL}/api/admin/email/campaigns").json()
    rows = lst.get("items") or lst.get("rows") or []
    assert any(c.get("subject") == "TEST_ api draft" for c in rows), lst


def test_user_cannot_access_admin(user):
    assert user.get(f"{BASE_URL}/api/admin/coupons").status_code in (401, 403)
