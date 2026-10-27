# Iteration 19: PitchAPI player photos (fetch_photo mocked, no real PitchAPI), no cdn.pitchapi.dev hotlinks on public APIs,
# /me/booking-risk (header bell source), league referee assignments. No PitchAPI / API-Football calls.
import os
import sys
import secrets
import datetime
import time

import httpx
import pytest
import requests

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dotenv import load_dotenv  # noqa: E402
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))
from pymongo import MongoClient  # noqa: E402

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
API = f"{BASE_URL}/api"
DB = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
NOW = lambda: datetime.datetime.now(datetime.timezone.utc)  # noqa: E731
LEAGUES = {"Bundesliga": "37140a56-00d6-4ed9-a7de-46f6d19a5e64", "LaLiga": "459108cf-0d2e-4281-bf44-d44d406d11f5",
           "Premier League": "4db3952b-e933-4076-be81-0d48989fb9a6", "Serie A": "1e2b1fe0-57a2-4084-9c33-095eb7ad7e49"}
PW = "Test-It19-Pass-2026!q"
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
TEST_IID = -919001
TEST_EXT = "TEST_it19_ext"


class FakeClient:
    def __init__(self, data):
        self.db, self.data, self.calls = DB, data, []

    def fetch(self, path, params=None, ttl=None, purpose=None):
        self.calls.append((path, ttl, purpose))
        return self.data


class FakeResp:
    def __init__(self, code, content):
        self.status_code, self.content = code, content


class FakeHttp:
    def __init__(self, code=200, content=PNG, exc=None):
        self.code, self.content, self.exc, self.urls = code, content, exc, []

    def get(self, url, headers=None):
        self.urls.append(url)
        if self.exc:
            raise self.exc
        return FakeResp(self.code, self.content)

    def close(self):
        pass


# fetch_photo with mocked client/http only
class TestFetchPhoto:
    @pytest.fixture(autouse=True)
    def player(self):
        DB.players.delete_many({"iid": TEST_IID})
        DB.media.delete_many({"kind": "player", "iid": TEST_IID})
        DB.players.insert_one({"iid": TEST_IID, "id": "test-it19-" + secrets.token_hex(4), "ext_id": TEST_EXT, "name": "TEST Photo"})
        yield
        DB.players.delete_many({"iid": TEST_IID})
        DB.media.delete_many({"kind": "player", "iid": TEST_IID})

    def _run(self, url, http):
        import pitch_photos as PP
        c = FakeClient({"image_url": url} if url is not None else {})
        res = PP.fetch_photo(c, TEST_EXT, http=http)
        assert c.calls and c.calls[0][0] == f"/v1/players/{TEST_EXT}" and c.calls[0][1] is None
        return res

    def test_stored(self):
        h = FakeHttp()
        assert self._run("https://cdn.pitchapi.dev/p/1.png", h) == "stored"
        m = DB.media.find_one({"kind": "player", "iid": TEST_IID})
        assert m and m["source"] == "pitchapi" and m["mime"] == "image/png"
        assert DB.players.find_one({"iid": TEST_IID})["photo_checked_at"] is not None

    @pytest.mark.parametrize("url", ["http://cdn.pitchapi.dev/p/1.png", "https://evil.example.com/p.png",
                                     "https://cdn.pitchapi.dev.evil.com/p.png", "https://x.cdn.pitchapi.dev/p.png", "", None,
                                     "javascript:alert(1)"])
    def test_rejects_url(self, url):
        h = FakeHttp()
        assert self._run(url, h) == "missing"
        assert h.urls == []
        assert DB.media.find_one({"kind": "player", "iid": TEST_IID}) is None

    def test_non_200(self):
        assert self._run("https://cdn.pitchapi.dev/p/1.png", FakeHttp(code=404)) == "missing"
        assert DB.media.find_one({"kind": "player", "iid": TEST_IID}) is None

    def test_http_error(self):
        assert self._run("https://cdn.pitchapi.dev/p/1.png", FakeHttp(exc=httpx.ConnectError("x"))) == "missing"

    @pytest.mark.parametrize("content", [b"<svg xmlns='http://www.w3.org/2000/svg'/>", b"GIF89a....", b""])
    def test_bad_bytes(self, content):
        assert self._run("https://cdn.pitchapi.dev/p/1.png", FakeHttp(content=content)) == "bad"
        assert DB.media.find_one({"kind": "player", "iid": TEST_IID}) is None

    def test_unknown_player(self):
        import pitch_photos as PP
        c = FakeClient({"image_url": "https://cdn.pitchapi.dev/x.png"})
        assert PP.fetch_photo(c, "TEST_nope_ext", http=FakeHttp()) == "skipped"
        assert c.calls == []


# Public pages: stored photos served from /api/media, never cdn.pitchapi.dev
def _photo_player():
    ids = DB.media.distinct("iid", {"kind": "player", "source": "pitchapi"})
    hot = DB.forecasts.distinct("player_iid", {"is_current": True, "scope": "player", "player_iid": {"$in": ids}})
    assert hot, "no photo players"
    return DB.players.find_one({"iid": hot[0]}, {"_id": 0, "id": 1, "iid": 1, "team_iid": 1})


class TestPublicPhotos:
    def test_player_page(self):
        p = _photo_player()
        r = requests.get(f"{API}/players/{p['id']}")
        assert r.status_code == 200
        assert "cdn.pitchapi.dev" not in r.text
        assert f"/api/media/player/{p['id']}" in r.text

    def test_media_serves_image(self):
        p = _photo_player()
        r = requests.get(f"{API}/players/{p['id']}").json()
        img = r.get("image") or (r.get("player") or {}).get("image")
        assert img and img.startswith("/api/media/player/")
        m = requests.get(BASE_URL + img)
        assert m.status_code == 200 and m.headers["content-type"].startswith("image/") and len(m.content) > 100

    def test_team_squad(self):
        p = _photo_player()
        t = DB.teams.find_one({"iid": p["team_iid"]}, {"id": 1})
        r = requests.get(f"{API}/teams/{t['id']}/squad-grid")
        assert r.status_code == 200 and "cdn.pitchapi.dev" not in r.text
        assert "/api/media/player/" in r.text
        m = DB.matches.find_one({"$or": [{"home_iid": p["team_iid"]}, {"away_iid": p["team_iid"]}], "status": "final"}, sort=[("kickoff", -1)])
        r = requests.get(f"{API}/matches/{m['id']}")
        assert r.status_code == 200 and "cdn.pitchapi.dev" not in r.text and "/api/media/player/" in r.text

    @pytest.mark.parametrize("name", list(LEAGUES))
    def test_booking_and_leaderboard(self, name):
        for path in ("booking-risk", "leaderboard"):
            r = requests.get(f"{API}/leagues/{LEAGUES[name]}/{path}")
            assert r.status_code == 200 and "cdn.pitchapi.dev" not in r.text


# Header bell data source
class TestMeBookingRisk:
    @pytest.fixture(scope="class")
    def sess(self):
        import accounts
        email = "test_iter19_bell@example.com"
        DB.users.delete_many({"email": email})
        uid = "test_" + secrets.token_hex(6)
        DB.users.insert_one({"id": uid, "email": email, "role": "user", "password_hash": accounts.hash_password(PW),
                             "display_name": "TEST Bell19", "tz": "UTC", "theme": "light", "email_verified": True, "failed_logins": 0,
                             "created_at": NOW(), "had_trial": False, "disabled": False,
                             "prefs": {"product_emails": True, "marketing_emails": False, "alert_emails": False}})
        s = requests.Session()
        assert s.post(f"{API}/auth/login", json={"email": email, "password": PW}).status_code == 200
        yield s, uid
        for c in ("follows", "sessions", "email_log"):
            DB[c].delete_many({"user_id": uid})
        DB.users.delete_many({"id": uid})

    def test_signed_out_401(self):
        assert requests.get(f"{API}/me/booking-risk").status_code == 401

    def test_zero_then_two(self, sess):
        s, uid = sess
        assert s.get(f"{API}/me/booking-risk").json()["rows"] == []
        top = requests.get(f"{API}/leagues/{LEAGUES['Serie A']}/booking-risk").json()["rows"][:2]
        for r in top:
            DB.follows.insert_one({"user_id": uid, "kind": "player", "ref_iid": r["player_iid"], "created_at": NOW()})
        t = time.time()
        d = s.get(f"{API}/me/booking-risk").json()
        print("me/booking-risk seconds", round(time.time() - t, 2))
        assert len(d["rows"]) == 2
        assert "cdn.pitchapi.dev" not in str(d)


# Referee assignments
class TestAssignments:
    @pytest.mark.parametrize("name", list(LEAGUES))
    def test_shape(self, name):
        d = requests.get(f"{API}/leagues/{LEAGUES[name]}/referee-assignments").json()
        assert {"rows", "from", "league_avg"} <= set(d)
        assert d["rows"]
        ks = [r["kickoff"] for r in d["rows"]]
        assert ks == sorted(ks) and ks[0] == d["from"]
        for r in d["rows"]:
            assert r["home"]["name"] and r["away"]["name"]
            if r["referee"] and r["stats"]:
                assert r["stats"]["referee"] == r["referee"]

    def test_serie_a_named(self):
        d = requests.get(f"{API}/leagues/{LEAGUES['Serie A']}/referee-assignments").json()
        named = [r for r in d["rows"] if r["referee"]]
        assert len(named) >= 3
        assert all(r["stats"] and r["stats"]["yellow_pg"] is not None for r in named)

    @pytest.mark.parametrize("name", list(LEAGUES))
    def test_one_round_each_team_once(self, name):
        """'Next round' should list each club at most once."""
        d = requests.get(f"{API}/leagues/{LEAGUES[name]}/referee-assignments").json()
        teams = [t for r in d["rows"] for t in (r["home"]["id"], r["away"]["id"])]
        dup = {t for t in teams if teams.count(t) > 1}
        assert not dup, f"{name}: {len(d['rows'])} fixtures, {len(dup)} clubs appear twice"

    def test_unknown_league(self):
        assert requests.get(f"{API}/leagues/nope/referee-assignments").status_code == 404


# Regression
class TestRegression:
    def test_referees(self):
        c = requests.get(f"{API}/referees", params={"min_matches": 5}).json()
        assert c and all(x["matches"] >= 5 for x in c)
