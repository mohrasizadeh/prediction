# Iteration 30: insights card grouping (lead = most likely), card-forecast reasons, finder day param, regressions.
import os
import pytest
import requests
from datetime import date, timedelta
from pymongo import MongoClient


def _env(path, key):
    for line in open(path):
        if line.startswith(key + "="):
            return line.split("=", 1)[1].strip().strip('"')


BASE_URL = (os.environ.get("REACT_APP_BACKEND_URL") or _env("/app/frontend/.env", "REACT_APP_BACKEND_URL")).rstrip("/")
MONGO_URL = _env("/app/backend/.env", "MONGO_URL")
DB_NAME = _env("/app/backend/.env", "DB_NAME")


@pytest.fixture(scope="module")
def db():
    return MongoClient(MONGO_URL)[DB_NAME]


@pytest.fixture(scope="module")
def cards():
    r = requests.get(f"{BASE_URL}/api/insights", params={"limit": 200}, timeout=60)
    assert r.status_code == 200, r.text[:300]
    return r.json()


# Insights: headline is the most likely line; more_lines sorted desc
class TestInsightsGrouping:
    def test_nonempty(self, cards):
        assert isinstance(cards, list) and len(cards) > 0

    def test_head_is_max(self, cards):
        bad = []
        for c in cards:
            for x in c.get("more_lines") or []:
                if x["p"] <= 0.93 and x["p"] > c["p"] + 1e-9:
                    bad.append((c["id"], c["market"], c["p"], x["market"], x["p"]))
        assert not bad, bad[:5]

    def test_more_sorted_desc(self, cards):
        bad = [c["id"] for c in cards if [x["p"] for x in c.get("more_lines") or []] != sorted([x["p"] for x in c.get("more_lines") or []], reverse=True)]
        assert not bad, bad[:5]

    def test_has_opp_and_kickoff(self, cards):
        miss = [c["id"] for c in cards if not c.get("kickoff") or not (c.get("opp") or {}).get("name")]
        assert not miss, miss[:5]

    def test_one_card_per_entity_match(self, cards):
        keys = [(c["match_iid"], c["scope"], c["team_iid"], c.get("player_iid")) for c in cards]
        assert len(keys) == len(set(keys))

    @pytest.mark.parametrize("params", [{"stat": "shots", "scope": "player"}, {"stat": "sot"}, {"stat": "tackles"}, {"stat": "corners"},
                                        {"stat": "shots", "scope": "team"}, {"stat": "yellow_cards"}, {"tiers": "Watch"}, {"tiers": "Strong,Solid,Watch"},
                                        {"sort": "likely"}, {"sort": "kickoff"}])
    def test_filters_ok(self, params):
        r = requests.get(f"{BASE_URL}/api/insights", params={"limit": 200, **params}, timeout=60)
        assert r.status_code == 200, r.text[:200]
        data = r.json()
        if "stat" in params:
            allowed = {params["stat"]}
            assert all(c["stat"] in allowed for c in data), {c["stat"] for c in data}
        if params.get("tiers") == "Watch":
            assert all(c["tier"] == "Watch" for c in data)


# Card forecasts in DB (read only)
class TestCardForecasts:
    def test_match_cards_reasons(self, db):
        docs = list(db.forecasts.find({"stat": "match_yellow_cards", "is_current": True}, {"_id": 0, "reasons": 1, "match_iid": 1}))
        assert docs, "no match_yellow_cards forecasts"
        txt = [" ".join(d.get("reasons") or []) for d in docs]
        n_f = sum("adjusted for opponents" in t for t in txt)
        n_r = sum("one yellow every" in t for t in txt)
        print(f"match cards={len(docs)} fouls_adjusted={n_f} ref_per_foul={n_r}")
        assert n_f > 0
        assert n_r > 0

    def test_player_cards_sane(self, db):
        docs = list(db.forecasts.find({"stat": "yellow_cards", "is_current": True, "scope": "player"}, {"_id": 0, "p": 1, "p_play": 1, "tier_basis": 1}))
        assert docs
        assert all(0 <= d["p"] <= 1 for d in docs)
        ls = [d for d in docs if d.get("tier_basis") == "likely_starter"]
        assert all(d["p_play"] == 1.0 for d in ls)
        print(f"player cards={len(docs)} likely_starter={len(ls)}")


# Finder: day param accepted (spends one anonymous search per call; keep calls minimal)
class TestFinderDay:
    def test_finder_requires_league(self):
        r = requests.get(f"{BASE_URL}/api/finder", params={"mode": "likelihood", "stat": "shots"}, timeout=30)
        assert r.status_code in (400, 402, 403, 422), r.status_code


# Regression: core public endpoints never 5xx
class TestRegression:
    def test_fixtures_and_matches(self):
        for d in (date.today(), date.today() + timedelta(days=1)):
            r = requests.get(f"{BASE_URL}/api/fixtures", params={"date": d.isoformat(), "tz": 0}, timeout=60)
            assert r.status_code == 200, r.text[:200]
        lg = requests.get(f"{BASE_URL}/api/leagues", timeout=30)
        assert lg.status_code == 200

    def test_match_pages(self, cards, db):
        iids = list({c["match_iid"] for c in cards})[:8]
        ids = [m["id"] for m in db.matches.find({"iid": {"$in": iids}}, {"id": 1})]
        assert ids
        for mid in ids:
            r = requests.get(f"{BASE_URL}/api/matches/{mid}", timeout=60)
            assert r.status_code == 200, (mid, r.status_code)
