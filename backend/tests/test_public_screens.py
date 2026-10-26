# Public Match / Team / Player / League screens + image cron auth (iteration 6)
import os
import re
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
API = f"{BASE_URL}/api"
MATCH = "0e531123-1643-4e68-a9f0-23559b01701d"
MATCH2 = "5ac44df1-d2ef-4e46-a354-1268be8828ba"
TEAM = "415eb552-d982-435a-8279-21d0a43aa315"
PLAYER = "20e4e25e-cc11-4566-afbf-caf8aa74e3f9"
LEAGUE = "1e2b1fe0-57a2-4084-9c33-095eb7ad7e49"
MEDIA_RX = re.compile(r"^/api/media/(team|player|league)/[0-9a-f-]+\?v=[0-9a-f]{8}$")


@pytest.fixture(scope="module")
def s():
    return requests.Session()


def _img_ok(x):
    assert x is None or x.get("image") is None or MEDIA_RX.match(x["image"]), x.get("image")


# Cron image endpoints: auth + mode validation (never call with real secret)
class TestCronImages:
    def test_refresh_no_auth_401(self, s):
        r = s.post(f"{API}/cron/images/refresh")
        assert r.status_code == 401

    def test_continue_bad_token_401(self, s):
        r = s.post(f"{API}/cron/images/continue", headers={"Authorization": "Bearer nope"})
        assert r.status_code == 401

    def test_bad_mode_with_auth_400(self, s):
        secret = os.environ.get("WEBHOOK_CRON_SECRET")
        if not secret:
            # read backend .env without spending provider calls (mode is invalid => no job started)
            for line in open("/app/backend/.env"):
                if line.startswith("WEBHOOK_CRON_SECRET="):
                    secret = line.split("=", 1)[1].strip().strip('"')
        if not secret:
            pytest.skip("no secret")
        r = s.post(f"{API}/cron/images/foo", headers={"Authorization": f"Bearer {secret}"})
        assert r.status_code == 400
        assert "BAD_MODE" in r.text or "refresh or continue" in r.text


# Match detail
class TestMatch:
    def test_match_detail(self, s):
        r = s.get(f"{API}/matches/{MATCH}")
        assert r.status_code == 200
        d = r.json()
        assert d["home"]["name"] and d["away"]["name"]
        _img_ok(d["home"]); _img_ok(d["away"])
        assert isinstance(d["forecasts"], list)
        assert d["starters"], "expected starters"
        for x in d["starters"]:
            assert x["player"] and x["player"]["name"]
            _img_ok(x["player"])
        assert "\"_id\"" not in r.text

    def test_match2_lineup(self, s):
        d = s.get(f"{API}/matches/{MATCH2}").json()
        assert {d["home"]["name"], d["away"]["name"]} == {"Sevilla", "Osasuna"}
        assert d["starters"] and all(x.get("player") for x in d["starters"])
        for m in d["h2h"]["matches"]:
            assert m["home"]["name"] and m["away"]["name"]

    def test_unknown_match_404(self, s):
        assert s.get(f"{API}/matches/00000000-0000-0000-0000-000000000000").status_code == 404


# Team detail, totals, grid, against
class TestTeam:
    def test_team_detail(self, s):
        d = s.get(f"{API}/teams/{TEAM}").json()
        assert d["team"]["name"] == "Sevilla"
        assert d["league"] and d["league"]["name"]
        _img_ok(d["team"]); _img_ok(d["league"])
        for m in d["next"]:
            assert m["home"]["name"] and m["away"]["name"]
        for f in d["form"]:
            assert f["opp"] and f["opp"]["name"]

    def test_totals_opp(self, s):
        d = s.get(f"{API}/teams/{TEAM}/totals", params={"stat": "shots", "last": 10}).json()
        assert d["rows"]
        assert all(r["opp"] and r["opp"]["name"] for r in d["rows"])

    def test_squad_grid_opp(self, s):
        d = s.get(f"{API}/teams/{TEAM}/squad-grid", params={"stat": "shots", "last": 5}).json()
        assert d["rows"]
        for r in d["rows"]:
            assert r["player"]["name"]
            assert len(r["games"]) <= 5
            assert all(g["opp"] and g["opp"]["name"] for g in r["games"])

    def test_against(self, s):
        d = s.get(f"{API}/teams/{TEAM}/against", params={"stat": "shots"}).json()
        assert "by_position" in d and d["games"] >= 0

    def test_unknown_team_404(self, s):
        assert s.get(f"{API}/teams/nope").status_code == 404
        assert s.get(f"{API}/teams/nope/squad-grid").status_code == 404


# Player detail + history
class TestPlayer:
    def test_player_detail(self, s):
        d = s.get(f"{API}/players/{PLAYER}").json()
        assert d["player"]["name"]
        nx = d["next_match"]
        if nx:
            assert nx["home"]["name"] and nx["away"]["name"]
            # forecasts should belong to the next match
            assert all(f["match_iid"] == nx["iid"] for f in d["forecasts"]), "forecasts include other matches"

    def test_history_filters(self, s):
        a = s.get(f"{API}/players/{PLAYER}/history", params={"last": 20}).json()
        h = s.get(f"{API}/players/{PLAYER}/history", params={"last": 20, "venue": "home"}).json()
        st = s.get(f"{API}/players/{PLAYER}/history", params={"last": 20, "started": "true"}).json()
        assert a["games"]
        assert all(g["home"] for g in h["games"])
        assert all(g["started"] for g in st["games"])
        assert all(g["opp"] and g["opp"]["name"] for g in a["games"])


# Leagues
class TestLeague:
    def test_leagues_search(self, s):
        allc = s.get(f"{API}/leagues").json()["countries"]
        it = s.get(f"{API}/leagues", params={"q": "serie"}).json()["countries"]
        names = [l["name"] for c in it for l in c["leagues"]]
        assert any("Serie A" in n for n in names)
        assert sum(len(c["leagues"]) for c in it) < sum(len(c["leagues"]) for c in allc)

    def test_league_detail_and_tabs(self, s):
        d = s.get(f"{API}/leagues/{LEAGUE}").json()
        assert d["name"] == "Serie A"
        f = s.get(f"{API}/leagues/{LEAGUE}/fixtures", params={"status": "final", "limit": 60}).json()
        assert all(m["home"]["name"] for m in f)
        lb = s.get(f"{API}/leagues/{LEAGUE}/leaderboard", params={"stat": "shots", "per90": "true", "limit": 30}).json()
        assert isinstance(lb, list)
        if len(lb) > 1:
            assert lb[0]["per90"] >= lb[1]["per90"]
            assert lb[0]["player"]["name"]

    def test_media_serves(self, s):
        d = s.get(f"{API}/teams/{TEAM}").json()
        img = d["team"].get("image")
        if not img:
            pytest.skip("no crest")
        r = s.get(BASE_URL + img)
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("image/")
