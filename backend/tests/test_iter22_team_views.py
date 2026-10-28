# Iteration 22: Team Views Pack (team-matrix, teams/compare) + redesign shell public APIs
import os
import uuid
import pytest
import requests
from pymongo import MongoClient

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
B = f"{BASE_URL}/api"
LALIGA = "459108cf-0d2e-4281-bf44-d44d406d11f5"


@pytest.fixture(scope="module")
def s():
    return requests.Session()


@pytest.fixture(scope="module")
def two_teams(s):
    d = s.get(f"{B}/leagues/{LALIGA}/team-matrix").json()
    return d["teams"][0]["team"]["id"], d["teams"][1]["team"]["id"]


# --- team matrix
@pytest.mark.parametrize("window", ["season", "last10", "last5"])
@pytest.mark.parametrize("venue", ["all", "home", "away"])
def test_matrix_windows(s, window, venue):
    r = s.get(f"{B}/leagues/{LALIGA}/team-matrix", params={"window": window, "venue": venue})
    assert r.status_code == 200
    d = r.json()
    assert d["window"] == window and d["venue"] == venue
    assert len(d["stats"]) == 14
    assert len(d["teams"]) > 0
    cap = {"season": 999, "last10": 10, "last5": 5}[window]
    for t in d["teams"]:
        assert set(t) >= {"team", "games", "form", "values", "pct"}
        assert 0 < t["games"] <= cap
        assert len(t["form"]) <= 5 and all(f in "WDL" for f in t["form"])
        assert len(t["values"]) == 14
        for v in t["pct"].values():
            assert v is None or 0 <= v <= 1
    names = [t["team"]["name"] for t in d["teams"]]
    assert names == sorted(names)


def test_matrix_bad_window(s):
    assert s.get(f"{B}/leagues/{LALIGA}/team-matrix", params={"window": "last3"}).status_code == 422
    assert s.get(f"{B}/leagues/{LALIGA}/team-matrix", params={"venue": "neutral"}).status_code == 422


def test_matrix_unknown_league(s):
    assert s.get(f"{B}/leagues/{uuid.uuid4()}/team-matrix").status_code == 404


# --- compare
@pytest.mark.parametrize("fixture", [False, True])
@pytest.mark.parametrize("window", ["season", "last5"])
def test_compare(s, two_teams, fixture, window):
    a, b = two_teams
    r = s.get(f"{B}/teams/compare", params={"a": a, "b": b, "as_fixture": str(fixture).lower(), "window": window})
    assert r.status_code == 200
    d = r.json()
    assert d["a"]["team"]["id"] == a and d["b"]["team"]["id"] == b
    assert d["as_fixture"] is fixture
    assert (d["a"]["venue"], d["b"]["venue"]) == (("home", "away") if fixture else ("all", "all"))
    assert d["same_league"] is True
    assert len(d["radar"]) == 6
    for ax in d["radar"]:
        for k in ("a", "b"):
            assert ax[k] is None or 0 <= ax[k] <= 1
    assert len(d["edges"]) > 0
    for e in d["edges"]:
        assert e["lean"] in (None, "a", "b")
    assert len(d["stands_out"]) <= 4


def test_compare_lean_direction(s, two_teams):
    a, b = two_teams
    d = s.get(f"{B}/teams/compare", params={"a": a, "b": b}).json()
    for e in d["edges"]:
        if e["key"] == "goals" and e["a"] != e["b"]:
            assert e["lean"] == ("a" if e["a"] > e["b"] else "b")
        if e["key"] == "goals_against" and e["a"] != e["b"]:
            assert e["lean"] == ("a" if e["a"] < e["b"] else "b")
        if e["key"] in ("tackles", "fouls", "yellow_cards"):
            assert e["lean"] is None


def test_compare_unknown(s, two_teams):
    assert s.get(f"{B}/teams/compare", params={"a": two_teams[0], "b": str(uuid.uuid4())}).status_code == 404


def test_compare_missing_param(s):
    assert s.get(f"{B}/teams/compare", params={"a": "x"}).status_code == 422


def test_live_and_search(s):
    lv = s.get(f"{B}/live").json()
    assert lv["live_count"] == 0
    r = s.get(f"{B}/search", params={"q": "barc"}).json()
    assert any("Barcelona" in t["name"] for t in r.get("teams", []))


# --- newsletter
def test_newsletter_generic_and_cleanup(s):
    email = f"TEST_nl_{uuid.uuid4().hex[:8]}@example.com"
    r = s.post(f"{B}/newsletter/subscribe", json={"email": email, "consent": True})
    assert r.status_code == 200, r.text
    msg = r.json().get("message")
    assert msg
    r2 = s.post(f"{B}/newsletter/subscribe", json={"email": email, "consent": True})
    assert r2.json().get("message") == msg
    db = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
    res = db.newsletter.delete_many({"email": {"$regex": "^test_nl_", "$options": "i"}})
    assert res.deleted_count >= 1
