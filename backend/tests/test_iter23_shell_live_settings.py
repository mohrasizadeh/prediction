# Iteration 23: Redesign R2 shell APIs (live, search, newsletter) + features.live setting mirrors sportapi.enabled
import os
import sys
import uuid
from datetime import datetime, timezone

import pytest
import requests
from pymongo import MongoClient

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
B = f"{BASE_URL}/api"
LALIGA = "459108cf-0d2e-4281-bf44-d44d406d11f5"


def _db():
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))
    return MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]


@pytest.fixture(scope="module")
def s():
    return requests.Session()


@pytest.fixture(scope="module")
def admin():
    from admin_login_helper import admin_session
    try:
        return admin_session()
    except Exception as e:  # noqa: BLE001
        pytest.skip(f"admin login failed: {e}")


# --- live (SportAPI-backed)
def test_live_today_has_fixtures(s):
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    r = s.get(f"{B}/live", params={"date": today, "tz": 0})
    assert r.status_code == 200
    d = r.json()
    assert isinstance(d["live_count"], int)
    assert len(d["leagues"]) >= 1
    fx = [f for g in d["leagues"] for f in g["fixtures"]]
    assert len(fx) >= 1
    live = sum(1 for f in fx if f.get("status") == "LIVE")
    assert d["live_count"] == live


# --- search incl. typo fallback used by overlay (q[:3])
def test_search_barcelona(s):
    r = s.get(f"{B}/search", params={"q": "barc"}).json()
    assert any("Barcelona" in t["name"] for t in r.get("teams", []))


def test_search_typo_prefix_fallback(s):
    exact = s.get(f"{B}/search", params={"q": "barcelno"}).json()
    pre = s.get(f"{B}/search", params={"q": "bar", "limit": 30}).json()
    assert any("Barcelona" in t["name"] for t in pre.get("teams", [])), "prefix fallback must include Barcelona"
    print("exact typo hits:", len(exact.get("players", [])), len(exact.get("teams", [])))


def test_leagues_q(s):
    r = s.get(f"{B}/leagues", params={"q": "liga"})
    assert r.status_code == 200


# --- public settings / newsletter consent
def test_public_settings_consent(s):
    d = s.get(f"{B}/public/settings").json()
    assert d.get("newsletter.consent_text")


def test_newsletter_bad_email(s):
    r = s.post(f"{B}/newsletter/subscribe", json={"email": "nope", "consent": True})
    assert r.status_code in (400, 422)


def test_newsletter_ok_and_cleanup(s):
    email = f"TEST_nl23_{uuid.uuid4().hex[:6]}@example.com"
    r = s.post(f"{B}/newsletter/subscribe", json={"email": email, "consent": True})
    assert r.status_code == 200 and r.json().get("message")
    _db().newsletter.delete_many({"email": {"$regex": "^test_nl23_", "$options": "i"}})


# --- team views quick re-check
def test_matrix_last5_home(s):
    d = s.get(f"{B}/leagues/{LALIGA}/team-matrix", params={"window": "last5", "venue": "home"}).json()
    assert len(d["stats"]) == 14 and d["teams"]
    t = d["teams"][0]
    assert {"values", "pct", "form", "games"} <= set(t)


def test_compare_fixture(s):
    d = s.get(f"{B}/leagues/{LALIGA}/team-matrix").json()
    a, b = d["teams"][0]["team"]["id"], d["teams"][1]["team"]["id"]
    c = s.get(f"{B}/teams/compare", params={"a": a, "b": b, "as_fixture": "true"}).json()
    assert len(c["radar"]) == 6 and len(c["stands_out"]) <= 4 and c["edges"]


def test_compare_same_team(s):
    d = s.get(f"{B}/leagues/{LALIGA}/team-matrix").json()
    a = d["teams"][0]["team"]["id"]
    r = s.get(f"{B}/teams/compare", params={"a": a, "b": a})
    print("same team compare status", r.status_code)
    assert r.status_code in (200, 400, 422)


# --- admin: features.live unlocked, mirrors sportapi.enabled; leave ON
def test_admin_features_live_not_locked(admin):
    rows = admin.get(f"{B}/admin/settings").json()
    row = next(r for r in rows if r["key"] == "features.live")
    print("features.live row:", {k: row.get(k) for k in ("value", "owner_only", "locked", "is_default")})
    assert not row.get("locked")


def test_admin_toggle_features_live(admin):
    r = admin.put(f"{B}/admin/settings/features.live", json={"value": False})
    if r.status_code == 403:
        pytest.skip("admin refused (owner-only): " + r.text)
    assert r.status_code == 200, r.text
    sa = admin.get(f"{B}/admin/sportapi").json()
    print("sportapi after OFF:", {k: sa.get(k) for k in ("enabled",)})
    assert sa.get("enabled") is False
    r = admin.put(f"{B}/admin/settings/features.live", json={"value": True})
    assert r.status_code == 200, r.text
    sa = admin.get(f"{B}/admin/sportapi").json()
    assert sa.get("enabled") is True
    rows = admin.get(f"{B}/admin/settings").json()
    assert next(r for r in rows if r["key"] == "features.live")["value"] is True
