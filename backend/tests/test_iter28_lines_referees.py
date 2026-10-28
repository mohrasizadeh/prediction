# Iteration 28: docs/25 fitted lines, normalised averages, referees (public endpoints)
import os
import re
import pytest
import requests

BASE = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/") or open("/app/frontend/.env").read().split("REACT_APP_BACKEND_URL=")[1].split()[0].rstrip("/")
MATCH = "2c690161-8aa0-4121-904b-0e435b461c53"
S = requests.Session()


def get(path, **params):
    r = S.get(f"{BASE}/api{path}", params=params, timeout=60)
    return r


# Insights feed: sorts, fields, markets
class TestInsights:
    def test_default_fields(self):
        r = get("/insights", limit=200)
        assert r.status_code == 200
        rows = r.json()
        assert len(rows) > 0
        for k in ("p_usual", "edge", "tier_basis", "tier_note"):
            assert all(k in f for f in rows), k
        assert all(f["tier"] in ("Strong", "Solid") for f in rows)
        assert all("_id" not in f for f in rows)

    def test_markets_varied(self):
        rows = get("/insights", limit=200).json()
        mk = {f["market"] for f in rows}
        print("markets sample:", sorted(mk)[:40])
        assert len(mk) >= 4
        thrs = {(f["stat"], f["thr"]) for f in rows}
        assert len({t for s, t in thrs}) >= 3

    def test_sort_edge_default_order(self):
        rows = get("/insights", limit=200, sort="edge").json()
        e = [f.get("edge") or 0 for f in rows]
        assert e == sorted(e, reverse=True)
        d = get("/insights", limit=200).json()
        assert [f["id"] for f in d] == [f["id"] for f in rows]

    def test_sort_likely(self):
        rows = get("/insights", limit=200, sort="likely").json()
        rank = {"Strong": 0, "Solid": 1}
        keys = [(rank[f["tier"]], -f["p"]) for f in rows]
        assert keys == sorted(keys)

    def test_sort_kickoff(self):
        rows = get("/insights", limit=200, sort="kickoff").json()
        k = [f["kickoff"] for f in rows]
        assert k == sorted(k)

    def test_sorts_differ(self):
        a = [f["id"] for f in get("/insights", limit=200, sort="edge").json()]
        b = [f["id"] for f in get("/insights", limit=200, sort="likely").json()]
        assert a != b

    def test_stat_scope_filter(self):
        rows = get("/insights", limit=200, stat="shots", scope="team").json()
        assert all(f["stat"] == "shots" and f["scope"] == "team" for f in rows)
        rows = get("/insights", limit=200, stat="corners").json()
        assert all(f["stat"] == "corners" for f in rows)

    def test_tiers_filter(self):
        rows = get("/insights", limit=200, tiers="Watch").json()
        assert all(f["tier"] == "Watch" for f in rows)
        print("watch rows", len(rows))

    def test_leagues_filter(self):
        rows = get("/insights", limit=200).json()
        lid = next((f["league_id"] for f in rows if f.get("league_id")), None)
        if not lid:
            pytest.skip("no league ids")
        f2 = get("/insights", limit=200, leagues=lid).json()
        assert f2 and all(f["league_id"] == lid for f in f2)

    def test_bad_sort_falls_back(self):
        r = get("/insights", sort="bogus")
        assert r.status_code == 200


# Match referee + league referees
class TestReferees:
    def test_match_referee(self):
        r = get(f"/matches/{MATCH}")
        assert r.status_code == 200
        ref = r.json().get("referee")
        print("referee:", ref)
        assert isinstance(ref, dict) and ref.get("sentence")

    def test_league_referees(self):
        lg = get("/leagues").json()
        ids = [l["id"] for c in lg.get("countries", []) for l in c["leagues"]]
        assert ids
        found = 0
        for lid in ids:
            r = get(f"/leagues/{lid}/referees")
            assert r.status_code == 200, (lid, r.text[:200])
            rows = r.json()
            assert isinstance(rows, list)
            for x in rows:
                assert "_id" not in x
                if x.get("cards_per_game_normalised") is not None:
                    found += 1
                    assert "factor" in x and 0.5 < x["factor"] < 1.6
        print("referee rows with normalised:", found)
        assert found > 0

    def test_league_referees_unknown(self):
        r = get("/leagues/does-not-exist/referees")
        print(r.status_code, r.text[:120])
        assert r.status_code in (200, 404)
