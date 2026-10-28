# Iteration 24 (Redesign R4): match recap, league fixtures/table data, finder hits, team compare, player history
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
API = f"{BASE_URL}/api"
LALIGA = "459108cf-0d2e-4281-bf44-d44d406d11f5"
FINAL = "5ac44df1-d2ef-4e46-a354-1268be8828ba"


@pytest.fixture(scope="module")
def s():
    return requests.Session()


# Match recap
class TestRecap:
    def test_final_match_recap(self, s):
        r = s.get(f"{API}/matches/{FINAL}")
        assert r.status_code == 200
        d = r.json()
        assert d["match"]["status"] == "final"
        rc = d["recap"]
        assert rc is not None
        assert isinstance(rc["ht"], list) and len(rc["ht"]) == 2
        assert rc["ht"][0] <= d["match"]["hg"] and rc["ht"][1] <= d["match"]["ag"]
        assert set(rc["by_tier"]) == {"Strong", "Solid"}
        assert rc["scored"] == sum(v[1] for v in rc["by_tier"].values())
        assert rc["hit"] == sum(v[0] for v in rc["by_tier"].values())
        assert 0 <= rc["hit"] <= rc["scored"]

    def test_scheduled_match_recap_null(self, s):
        lg = s.get(f"{API}/leagues/{LALIGA}").json()
        mid = lg["next"][0]["id"]
        d = s.get(f"{API}/matches/{mid}").json()
        assert d["match"]["status"] == "scheduled"
        assert d["recap"] is None


# League data used by the five tabs
class TestLeague:
    def test_league_detail(self, s):
        r = s.get(f"{API}/leagues/{LALIGA}")
        assert r.status_code == 200
        d = r.json()
        assert d["name"] == "LaLiga"
        assert isinstance(d["next"], list) and d["next"]

    def test_final_fixtures_limit_400(self, s):
        r = s.get(f"{API}/leagues/{LALIGA}/fixtures", params={"status": "final", "limit": 400})
        assert r.status_code == 200
        rows = r.json()
        assert rows and all(m["status"] == "final" and m["hg"] is not None for m in rows)
        assert all(m["home"] and m["away"] for m in rows)
        assert "_id" not in rows[0]

    def test_fixtures_limit_over_cap(self, s):
        r = s.get(f"{API}/leagues/{LALIGA}/fixtures", params={"status": "final", "limit": 401})
        assert r.status_code == 422

    def test_leaderboard(self, s):
        r = s.get(f"{API}/leagues/{LALIGA}/leaderboard", params={"stat": "shots", "limit": 30})
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    @pytest.mark.parametrize("path", ["referee-assignments", "referees", "booking-risk"])
    def test_league_subresources(self, s, path):
        r = s.get(f"{API}/leagues/{LALIGA}/{path}")
        assert r.status_code == 200, r.text


# Compare + player history
class TestCompareAndPlayer:
    def test_compare(self, s):
        rows = s.get(f"{API}/leagues/{LALIGA}/fixtures", params={"status": "final", "limit": 5}).json()
        a, b = rows[0]["home"]["id"], rows[0]["away"]["id"]
        r = s.get(f"{API}/teams/compare", params={"a": a, "b": b})
        assert r.status_code == 200, r.text
        d = r.json()
        assert "radar" in d and "edges" in d

    def test_player_history(self, s):
        lb = s.get(f"{API}/leagues/{LALIGA}/leaderboard", params={"stat": "shots", "limit": 1}).json()
        if not lb:
            pytest.skip("no leaderboard")
        pid = lb[0]["player"]["id"]
        r = s.get(f"{API}/players/{pid}/history", params={"last": 10})
        assert r.status_code == 200
        g = r.json()["games"]
        assert 0 < len(g) <= 10
        assert "shots" in g[0]


# Finder (anonymous cap: only one search)
class TestFinder:
    def test_finder_form_hits(self, s):
        r = s.get(f"{API}/finder", params={"mode": "form", "stat": "shots", "threshold": 2, "scope": "player",
                                           "last_n": 10, "leagues": LALIGA, "min_reached": 0.6})
        if r.status_code == 429:
            pytest.skip("anonymous finder cap reached")
        assert r.status_code == 200, r.text
        rows = r.json()
        assert rows
        for x in rows[:10]:
            assert len(x["hits"]) == x["games"] <= 10
            assert sum(x["hits"]) == x["reached"]
            assert x["reached"] / x["games"] >= 0.6
