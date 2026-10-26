# Phase 4: Insights, Finder, Search, Following (follows/saved/feed), Notes, Track record (iteration 7)
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
API = f"{BASE_URL}/api"
MATCH2 = "5ac44df1-d2ef-4e46-a354-1268be8828ba"
TEAM = "415eb552-d982-435a-8279-21d0a43aa315"
PLAYER = "20e4e25e-cc11-4566-afbf-caf8aa74e3f9"
SERIE_A = "1e2b1fe0-57a2-4084-9c33-095eb7ad7e49"
EMAIL, PW = "test_e1_user@example.com", "Test-User-Pass-2026!q"


@pytest.fixture(scope="module")
def anon():
    return requests.Session()


@pytest.fixture(scope="module")
def u():
    s = requests.Session()
    s.headers.update({"Origin": BASE_URL})
    r = s.post(f"{API}/auth/login", json={"email": EMAIL, "password": PW})
    if r.status_code != 200:
        pytest.skip(f"login failed {r.status_code} {r.text[:200]}")
    yield s
    # cleanup
    s.delete(f"{API}/me/follows", json={"kind": "team", "ref_id": TEAM})
    s.delete(f"{API}/me/follows", json={"kind": "player", "ref_id": PLAYER})
    s.delete(f"{API}/me/notes/{PLAYER}")
    for it in s.get(f"{API}/me/saved").json().get("items", []):
        s.delete(f"{API}/me/saved", json={"fkey": it["fkey"]})


# Insights
class TestInsights:
    def test_insights_list(self, anon):
        r = anon.get(f"{API}/insights", params={"limit": 200})
        assert r.status_code == 200
        d = r.json()
        assert isinstance(d, list) and d
        x = d[0]
        for k in ("id", "fkey", "stat", "scope", "tier", "p", "market"):
            assert k in x, k
        assert all(i["tier"] in ("Strong", "Solid") for i in d)
        assert "_id" not in x


# Track record
class TestTrackRecord:
    def test_not_ready(self, anon):
        r = anon.get(f"{API}/track-record")
        assert r.status_code == 200
        d = r.json()
        assert d["ready"] is False and d["needed"] == 300 and isinstance(d["scored"], int)


# Search
class TestSearch:
    def test_short_400(self, anon):
        assert anon.get(f"{API}/search", params={"q": "s"}).status_code == 400

    @pytest.mark.parametrize("q", ["sev", "inter"])
    def test_search(self, anon, q):
        r = anon.get(f"{API}/search", params={"q": q})
        assert r.status_code == 200
        d = r.json()
        assert d["teams"] or d["players"]
        for t in d["teams"]:
            assert q in t["name"].lower() and t["id"]

    def test_regex_safe(self, anon):
        assert anon.get(f"{API}/search", params={"q": ".*(["}).status_code == 200


# Finder (signed in to avoid anonymous cap)
class TestFinder:
    def test_no_league_400(self, u):
        if u.get(f"{API}/auth/me").json()["entitlements"]["finder_leagues"] < 0:
            pytest.skip("billing off: user is Pro, unlimited leagues")
        r = u.get(f"{API}/finder", params={"mode": "likelihood"})
        assert r.status_code == 400 and "PICK_A_LEAGUE" in r.text

    def test_two_leagues_403_free(self, u):
        if u.get(f"{API}/auth/me").json()["entitlements"]["finder_leagues"] < 0:
            pytest.skip("billing off: user is Pro, unlimited leagues")
        lg = u.get(f"{API}/leagues").json()
        ids = [l["id"] for c in lg["countries"] for l in c["leagues"]][:2]
        if len(ids) < 2:
            pytest.skip("one league only")
        r = u.get(f"{API}/finder", params={"leagues": ",".join(ids)})
        assert r.status_code == 403

    def test_likelihood(self, u):
        r = u.get(f"{API}/finder", params={"mode": "likelihood", "stat": "shots", "threshold": 1, "scope": "player", "leagues": SERIE_A})
        assert r.status_code == 200
        d = r.json()
        assert d and d[0]["player"]["name"] and d[0]["team"]["name"]
        assert [x["p"] for x in d] == sorted([x["p"] for x in d], reverse=True)

    def test_form(self, u):
        r = u.get(f"{API}/finder", params={"mode": "form", "stat": "shots", "threshold": 1, "scope": "player", "leagues": SERIE_A, "last_n": 10, "min_reached": 0.5})
        assert r.status_code == 200
        d = r.json()
        assert d
        x = d[0]
        assert x["reached"] / x["games"] >= 0.5 and x["player"]["name"] and x["team"]["name"]
        nx = next((y["next_match"] for y in d if y.get("next_match")), None)
        assert nx and nx["home"]["name"] and nx["away"]["name"]

    def test_run_team_positions_ignored(self, u):
        r = u.get(f"{API}/finder", params={"mode": "run", "stat": "corners", "threshold": 3, "scope": "team", "leagues": SERIE_A, "venue": "home"})
        assert r.status_code == 200
        for x in r.json():
            assert x["team"]["name"] and x["run"] >= 0

    def test_positions(self, u):
        r = u.get(f"{API}/finder", params={"mode": "likelihood", "stat": "shots", "threshold": 1, "scope": "player", "leagues": SERIE_A, "positions": "FWD"})
        assert r.status_code == 200
        assert all(x.get("pos") == "FWD" for x in r.json())


# Following: follows, feed, saved, notes
class TestFollowing:
    def test_anon_401(self, anon):
        assert anon.get(f"{API}/me/follows").status_code == 401

    def test_follow_team_player_and_feed(self, u):
        assert u.put(f"{API}/me/follows", json={"kind": "team", "ref_id": TEAM}).status_code == 201
        assert u.put(f"{API}/me/follows", json={"kind": "player", "ref_id": PLAYER}).status_code == 201
        again = u.put(f"{API}/me/follows", json={"kind": "team", "ref_id": TEAM})
        assert again.json().get("already") is True
        items = u.get(f"{API}/me/follows").json()["items"]
        ids = {i["id"] for i in items}
        assert TEAM in ids and PLAYER in ids
        feed = u.get(f"{API}/me/following-feed").json()
        assert isinstance(feed["matches"], list) and isinstance(feed["forecasts"], list)
        assert feed["matches"], "feed should show upcoming fixtures"
        assert feed["matches"][0]["home"]["name"]

    def test_feed_forecasts_decorated(self, u):
        feed = u.get(f"{API}/me/following-feed").json()
        for f in feed["forecasts"]:
            assert f.get("team") and f.get("opp"), "feed forecasts lack team/opp names (ForecastCard shows 'Team')"

    def test_unfollow(self, u):
        assert u.delete(f"{API}/me/follows", json={"kind": "team", "ref_id": TEAM}).json()["removed"] == 1
        ids = {i["id"] for i in u.get(f"{API}/me/follows").json()["items"]}
        assert TEAM not in ids

    def test_follow_bad_404(self, u):
        assert u.put(f"{API}/me/follows", json={"kind": "team", "ref_id": "nope"}).status_code == 404

    def test_saved_roundtrip(self, u):
        fk = u.get(f"{API}/insights").json()[0]["fkey"]
        assert u.put(f"{API}/me/saved", json={"fkey": fk}).status_code == 201
        items = u.get(f"{API}/me/saved").json()["items"]
        it = next(i for i in items if i["fkey"] == fk)
        assert it["forecast"] and it["forecast"]["fkey"] == fk
        assert u.delete(f"{API}/me/saved", json={"fkey": fk}).json()["removed"] == 1
        assert fk not in {i["fkey"] for i in u.get(f"{API}/me/saved").json()["items"]}

    def test_saved_decorated(self, u):
        fk = u.get(f"{API}/insights").json()[0]["fkey"]
        u.put(f"{API}/me/saved", json={"fkey": fk})
        it = next(i for i in u.get(f"{API}/me/saved").json()["items"] if i["fkey"] == fk)
        u.delete(f"{API}/me/saved", json={"fkey": fk})
        f = it["forecast"]
        assert f.get("team") and f.get("opp"), "saved forecasts lack team/opp names (ForecastCard renders 'Team')"

    def test_notes(self, u):
        assert u.put(f"{API}/me/notes/{PLAYER}", json={"text": "TEST_ note"}).status_code in (200, 201)
        assert "TEST_ note" in u.get(f"{API}/me/notes/{PLAYER}").text
        assert u.delete(f"{API}/me/notes/{PLAYER}").status_code in (200, 204)
        assert "TEST_ note" not in u.get(f"{API}/me/notes/{PLAYER}").text


# Fix 1 regression (iteration 8): /auth/me must not share the 10/min 'auth' bucket, or a few reloads sign the user out.
class TestAuthMeRateLimit:
    def test_auth_me_not_rate_limited_by_reloads(self, anon):
        codes = [anon.get(f"{API}/auth/me").status_code for _ in range(15)]
        assert 429 not in codes, f"/auth/me returned 429 after {codes.index(429)} calls: {codes}"
