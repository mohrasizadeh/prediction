# First goal record (team/match) + yellow-card forecasts (cards model) + finder/track-record with new markets
import os
import sys

import pytest
import requests

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
API = f"{BASE_URL}/api"

SERIE_A = "1e2b1fe0-57a2-4084-9c33-095eb7ad7e49"
TEAM = "6b66a173-7dc8-4cad-82ce-edc68eab17e0"          # Lecce
MILAN_BOLOGNA = "4530cfaa-3977-4e68-a02f-c22c0e2ad100"  # upcoming Serie A


def _teams():
    d = requests.get(f"{API}/leagues/{SERIE_A}").json()
    ids = []
    for m in d.get("next", []) + d.get("recent", []):
        for k in ("home", "away"):
            t = m.get(k) or {}
            if t.get("id") and t["id"] not in ids:
                ids.append(t["id"])
    return ids


# First goal endpoint
class TestFirstGoal:
    def test_shape_and_sums(self):
        r = requests.get(f"{API}/teams/{TEAM}/first-goal")
        assert r.status_code == 200, r.text
        d = r.json()
        for k in ("played", "scored_first", "conceded_first", "goalless", "after_scoring", "after_conceding", "games", "scorers"):
            assert k in d
        assert d["played"] > 0
        assert d["scored_first"] + d["conceded_first"] + d["goalless"] == d["played"]
        assert sum(d["after_scoring"].values()) == d["scored_first"]
        assert sum(d["after_conceding"].values()) == d["conceded_first"]
        assert len(d["games"]) == d["played"]
        assert "'_id'" not in str(d)

    def test_games_consistent(self):
        d = requests.get(f"{API}/teams/{TEAM}/first-goal").json()
        for g in d["games"]:
            assert g["who"] in ("us", "them", "none")
            gf, ga = map(int, g["score"].split("-"))
            assert g["result"] == ("w" if gf > ga else "d" if gf == ga else "l")
            if g["who"] == "none":
                assert gf == 0 and ga == 0
                assert g["minute"] is None
            if g["who"] == "us":
                assert gf > 0
            if g["who"] == "them":
                assert ga > 0
            assert g["opp"] and g["opp"]["name"]
        # scorers counts never exceed scored_first and are sorted desc
        ns = [s["n"] for s in d["scorers"]]
        assert ns == sorted(ns, reverse=True)
        assert sum(ns) <= d["scored_first"]
        for s in d["scorers"]:
            assert s["player"]["id"] and s["player"]["name"]

    def test_scorer_counts_match_games(self):
        d = requests.get(f"{API}/teams/{TEAM}/first-goal").json()
        from collections import Counter
        c = Counter(g["scorer"]["id"] for g in d["games"] if g.get("scorer"))
        for s in d["scorers"]:
            assert c[s["player"]["id"]] == s["n"]

    def test_last_param(self):
        d = requests.get(f"{API}/teams/{TEAM}/first-goal", params={"last": 5}).json()
        assert d["played"] <= 5
        assert requests.get(f"{API}/teams/{TEAM}/first-goal", params={"last": 2}).status_code == 422

    def test_404(self):
        assert requests.get(f"{API}/teams/nope-team/first-goal").status_code == 404

    def test_all_serie_a_teams_sums(self):
        ids = _teams()
        if not ids:
            pytest.skip("league detail has no team table")
        for tid in ids:
            d = requests.get(f"{API}/teams/{tid}/first-goal").json()
            assert d["scored_first"] + d["conceded_first"] + d["goalless"] == d["played"], tid
            assert sum(d["after_scoring"].values()) == d["scored_first"], tid
            assert sum(d["after_conceding"].values()) == d["conceded_first"], tid


# Card forecasts on match detail
class TestCardForecasts:
    def _fc(self):
        d = requests.get(f"{API}/matches/{MILAN_BOLOGNA}").json()
        fc = d.get("forecasts")
        if isinstance(fc, dict):
            flat = []
            for v in fc.values():
                flat += v if isinstance(v, list) else []
            fc = flat
        return d, fc or []

    def test_match_has_card_forecasts(self):
        d, fc = self._fc()
        cards = [f for f in fc if f.get("model") == "cards"]
        assert cards, f"no cards forecasts, keys={list(d)}"
        py = [f for f in cards if f["stat"] == "yellow_cards"]
        mt = [f for f in cards if f["stat"] == "match_yellow_cards"]
        assert py and all(f["scope"] == "player" and f["thr"] == 0.5 and f["market"] == "Gets a yellow card" for f in py)
        assert sorted(f["thr"] for f in mt) == [3.5, 4.5]
        assert all(f["scope"] == "team" for f in mt)
        assert {f["market"] for f in mt} == {"4+ yellow cards in the match", "5+ yellow cards in the match"}
        for f in cards:
            assert 0 <= f["lo"] <= f["p"] <= f["hi"] <= 1
            assert f["reasons"] and any("referee" in r.lower() for r in f["reasons"])
        # 5+ must be less likely than 4+
        p = {f["thr"]: f["p"] for f in mt}
        assert p[4.5] < p[3.5]


# Finder with the new markets
class TestFinderCards:
    @pytest.fixture(scope="class")
    @staticmethod
    def s():
        from admin_login_helper import admin_session
        return admin_session()

    def test_likelihood_player_yellow(self, s):
        r = s.get(f"{API}/finder", params={"mode": "likelihood", "stat": "yellow_cards", "threshold": 1, "scope": "player", "leagues": SERIE_A})
        assert r.status_code == 200, r.text
        rows = r.json()
        assert rows and all(x["stat"] == "yellow_cards" and x["thr"] == 0.5 for x in rows)
        ps = [x["p"] for x in rows]
        assert ps == sorted(ps, reverse=True)

    def test_likelihood_match_yellow(self, s):
        r = s.get(f"{API}/finder", params={"mode": "likelihood", "stat": "match_yellow_cards", "threshold": 4, "scope": "team", "leagues": SERIE_A})
        assert r.status_code == 200, r.text
        rows = r.json()
        assert len(rows) >= 5 and all(x["stat"] == "match_yellow_cards" and x["thr"] == 3.5 for x in rows)

    @pytest.mark.parametrize("mode,scope,stat", [("form", "player", "yellow_cards"), ("run", "player", "yellow_cards"),
                                                 ("form", "team", "match_yellow_cards"), ("run", "team", "match_yellow_cards")])
    def test_form_run(self, s, mode, scope, stat):
        r = s.get(f"{API}/finder", params={"mode": mode, "stat": stat, "threshold": 1 if scope == "player" else 4, "scope": scope,
                                           "last_n": 10, "leagues": SERIE_A, **({"min_reached": 0.5} if mode == "form" else {})})
        assert r.status_code == 200, r.text
        assert isinstance(r.json(), list)


# Track record / insights still load
class TestTrackInsights:
    def test_track_record(self):
        assert requests.get(f"{API}/track-record").status_code == 200
        assert requests.get(f"{API}/track-record", params={"league": SERIE_A}).status_code == 200

    def test_insights(self):
        r = requests.get(f"{API}/insights")
        assert r.status_code == 200, r.text
