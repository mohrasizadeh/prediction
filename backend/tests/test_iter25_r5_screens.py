# iter25 R5: visitor finder usage meter, /leagues next+today, /track-record stat, /me/notes, /me/saved outcome,
# following-feed results, profile prefs.welcomed/leagues. Live preview URL; uses TEST user test_r5_welcome.
import os, uuid, pytest, requests

BASE = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/") or open("/app/frontend/.env").read().split("REACT_APP_BACKEND_URL=")[1].split()[0].rstrip("/")
EMAIL, PW = "test_r5_welcome@example.com", "Test-User-Pass-2026!q"


@pytest.fixture(scope="module")
def user():
    s = requests.Session(); s.headers["User-Agent"] = "TEST_ua_iter25_user"
    r = s.post(f"{BASE}/api/auth/login", json={"email": EMAIL, "password": PW})
    if r.status_code != 200:
        pytest.skip(f"login failed {r.status_code} {r.text[:200]}")
    yield s
    s.patch(f"{BASE}/api/account/profile", json={"prefs": {"welcomed": False, "leagues": []}})


@pytest.fixture(scope="module")
def leagues():
    r = requests.get(f"{BASE}/api/leagues"); assert r.status_code == 200
    return [l for c in r.json()["countries"] for l in c["leagues"]]


# visitor finder usage
def test_visitor_usage_and_decrement(leagues):
    ua = f"TEST_ua_iter25_{uuid.uuid4().hex[:8]}"
    h = {"User-Agent": ua}
    me = requests.get(f"{BASE}/api/auth/me", headers=h).json()
    assert me["user"] is None and me["usage"]["finder_today"] == 0
    cap = me["limits"]["anonymous_finder_searches_per_day"]; assert cap == 3
    lg = leagues[0]["id"]
    for i in range(cap):
        r = requests.get(f"{BASE}/api/finder", params={"mode": "form", "stat": "shots", "threshold": 2, "leagues": lg}, headers=h)
        assert r.status_code == 200, r.text
        assert requests.get(f"{BASE}/api/auth/me", headers=h).json()["usage"]["finder_today"] == i + 1
    r = requests.get(f"{BASE}/api/finder", params={"mode": "form", "stat": "shots", "threshold": 2, "leagues": lg}, headers=h)
    assert r.status_code == 401 and "SIGN_IN_REQUIRED" in r.text
    assert requests.get(f"{BASE}/api/auth/me", headers=h).json()["usage"]["finder_today"] == cap


# leagues list next + today
def test_leagues_next_today(leagues):
    assert leagues
    for l in leagues:
        assert "today" in l and isinstance(l["today"], int)
        assert "next" in l
    assert any(l["next"] and l["next"].get("kickoff") for l in leagues)


# track record with stat/league
def test_track_record_params(leagues):
    a = requests.get(f"{BASE}/api/track-record").json()
    assert "ready" in a and "scored" in a
    b = requests.get(f"{BASE}/api/track-record", params={"stat": "shots"}).json()
    assert b["scored"] <= a["scored"]
    c = requests.get(f"{BASE}/api/track-record", params={"stat": "shots", "league": leagues[0]["id"]})
    assert c.status_code == 200
    assert requests.get(f"{BASE}/api/track-record", params={"stat": "goals_bad"}).status_code == 422
    if a["ready"]:
        assert "tiers" in a and "bins" in a and "since" in a


# notes list
def test_notes_list(user):
    r = requests.get(f"{BASE}/api/search", params={"q": "ya"}).json()
    pid = (r.get("players") or [])[0]["id"]
    assert user.put(f"{BASE}/api/me/notes/{pid}", json={"text": "TEST_ note iter25"}).status_code in (200, 201)
    lst = user.get(f"{BASE}/api/me/notes").json()
    items = lst.get("items", lst if isinstance(lst, list) else [])
    assert any(n.get("text") == "TEST_ note iter25" for n in items), lst
    n0 = [n for n in items if n.get("text") == "TEST_ note iter25"][0]
    assert "_id" not in n0 and ("player" in n0 or "player_iid" in n0)
    user.delete(f"{BASE}/api/me/notes/{pid}")
    lst = user.get(f"{BASE}/api/me/notes").json()
    items = lst.get("items", lst if isinstance(lst, list) else [])
    assert not any(n.get("text") == "TEST_ note iter25" for n in items)
    assert requests.get(f"{BASE}/api/me/notes").status_code == 401


# saved + outcome, feed results
def test_saved_and_feed(user, leagues):
    s = user.get(f"{BASE}/api/me/saved"); assert s.status_code == 200
    for it in s.json()["items"]:
        assert "outcome" in it
    f = user.get(f"{BASE}/api/me/following-feed").json()
    assert set(["matches", "forecasts", "results"]) <= set(f)


# profile prefs welcomed + leagues persist
def test_prefs_welcomed(user, leagues):
    ids = [l["id"] for l in leagues[:2]]
    r = user.patch(f"{BASE}/api/account/profile", json={"prefs": {"welcomed": True, "leagues": ids}})
    assert r.status_code == 200, r.text
    me = user.get(f"{BASE}/api/auth/me").json()
    assert me["user"]["prefs"]["welcomed"] is True and me["user"]["prefs"]["leagues"] == ids
    assert me["user"]["prefs"].get("product_emails") is True
