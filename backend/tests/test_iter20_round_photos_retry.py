# Iteration 20: retest of iteration_19 fixes.
# - referee-assignments: one round only (no club twice) for all 6 referee leagues
# - pitch_photos.fetch_photo: photo_checked_at only for real outcomes (mocked client/http only, no PitchAPI)
# - plan()/enqueue retry path for temporary failures (run on a scratch DB so the live queue is never touched)
import os
import sys
import secrets
import datetime

import httpx
import pytest
import requests

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dotenv import load_dotenv  # noqa: E402
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))
from pymongo import MongoClient  # noqa: E402

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
API = f"{BASE_URL}/api"
MC = MongoClient(os.environ["MONGO_URL"])
DB = MC[os.environ["DB_NAME"]]
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
TEST_IID = -920001
TEST_EXT = "TEST_it20_ext"
CDN_URL = "https://cdn.pitchapi.dev/p/1.png"
REF_LEAGUES = sorted(DB.referee_stats.distinct("league_iid"))


class FakeClient:
    def __init__(self, data, db=DB):
        self.db, self.data, self.calls = db, data, []

    def fetch(self, path, params=None, ttl=None, purpose=None):
        self.calls.append(path)
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


# ---------------------------------------------------------------- referee assignments: one round
def _league(iid):
    return DB.leagues.find_one({"iid": iid}, {"_id": 0, "id": 1, "name": 1})


def test_six_ref_leagues():
    assert len(REF_LEAGUES) == 6, REF_LEAGUES


@pytest.mark.parametrize("liid", REF_LEAGUES)
def test_one_round_no_club_twice(liid):
    L = _league(liid)
    d = requests.get(f"{API}/leagues/{L['id']}/referee-assignments").json()
    rows = d["rows"]
    assert rows, L["name"]
    teams = [t for r in rows for t in (r["home"]["id"], r["away"]["id"])]
    assert len(teams) == len(set(teams)), f"{L['name']} has a club twice"
    ks = [r["kickoff"] for r in rows]
    assert ks == sorted(ks) and ks[0] == d["from"]
    # stops exactly at the first repeat: the next scheduled match (if any) has a club already listed
    last = DB.matches.find_one({"id": rows[-1]["match_id"]}, {"kickoff": 1})
    ids = {r["match_id"] for r in rows}
    nxt = [m for m in DB.matches.find({"league_iid": liid, "status": "scheduled", "kickoff": {"$gte": last["kickoff"]}},
                                     {"_id": 0, "id": 1, "home_iid": 1, "away_iid": 1}).sort("kickoff", 1) if m["id"] not in ids]
    if nxt:
        seen = set()
        for r in rows:
            m = DB.matches.find_one({"id": r["match_id"]}, {"home_iid": 1, "away_iid": 1})
            seen |= {m["home_iid"], m["away_iid"]}
        assert nxt[0]["home_iid"] in seen or nxt[0]["away_iid"] in seen, f"{L['name']} stopped early"
    print(L["name"], len(rows), "fixtures")


def test_unknown_league_404():
    assert requests.get(f"{API}/leagues/nope/referee-assignments").status_code == 404


# ---------------------------------------------------------------- fetch_photo photo_checked_at
class TestCheckedAt:
    @pytest.fixture(autouse=True)
    def player(self):
        DB.players.delete_many({"iid": TEST_IID})
        DB.media.delete_many({"kind": "player", "iid": TEST_IID})
        DB.players.insert_one({"iid": TEST_IID, "id": "test-it20-" + secrets.token_hex(4), "ext_id": TEST_EXT, "name": "TEST Photo20"})
        yield
        DB.players.delete_many({"iid": TEST_IID})
        DB.media.delete_many({"kind": "player", "iid": TEST_IID})

    def _run(self, data, http):
        import pitch_photos as PP
        res = PP.fetch_photo(FakeClient(data), TEST_EXT, http=http)
        return res, DB.players.find_one({"iid": TEST_IID}).get("photo_checked_at")

    def test_stored_sets(self):
        res, at = self._run({"image_url": CDN_URL}, FakeHttp())
        assert res == "stored" and at is not None

    @pytest.mark.parametrize("content", [b"<svg xmlns='http://www.w3.org/2000/svg'/>", b"GIF89a....", b""])
    def test_bad_sets(self, content):
        res, at = self._run({"image_url": CDN_URL}, FakeHttp(content=content))
        assert res == "bad" and at is not None

    @pytest.mark.parametrize("url", ["", None, "http://cdn.pitchapi.dev/p.png", "https://evil.example.com/p.png", "javascript:x"])
    def test_no_or_invalid_url_sets(self, url):
        h = FakeHttp()
        res, at = self._run({"name": "x", "image_url": url}, h)
        assert res == "missing" and at is not None and h.urls == []

    def test_empty_response_unset(self):
        res, at = self._run(None, FakeHttp())
        assert res == "missing" and at is None

    @pytest.mark.parametrize("code", [404, 500, 503, 302])
    def test_non_200_unset(self, code):
        res, at = self._run({"image_url": CDN_URL}, FakeHttp(code=code))
        assert res == "missing" and at is None

    @pytest.mark.parametrize("exc", [httpx.ConnectError("x"), httpx.ReadTimeout("x")])
    def test_httpx_error_unset(self, exc):
        res, at = self._run({"image_url": CDN_URL}, FakeHttp(exc=exc))
        assert res == "missing" and at is None


# ---------------------------------------------------------------- plan() re-queues (scratch DB only)
class TestPlanRetry:
    @pytest.fixture
    def sdb(self):
        name = "test_iter20_scratch_" + secrets.token_hex(3)
        s = MC[name]
        s.ingest_queue.create_index([("task", 1), ("key", 1)], unique=True)
        s.players.insert_one({"iid": TEST_IID, "ext_id": TEST_EXT, "name": "TEST", "photo_checked_at": None})
        yield s
        MC.drop_database(name)

    def test_plan_selects_unchecked(self, sdb):
        import pitch_photos as PP
        assert PP.plan(sdb, force=True) == 1
        q = sdb.ingest_queue.find_one({"task": "player_photo", "key": TEST_EXT})
        assert q and q["status"] == "pending"

    def test_temporary_failure_is_retried(self, sdb):
        """Simulate the worker: plan -> fetch_photo (503) -> task marked done -> next plan should make it pending again."""
        import pitch_photos as PP
        PP.plan(sdb, force=True)
        res = PP.fetch_photo(FakeClient({"image_url": CDN_URL}, db=sdb), TEST_EXT, http=FakeHttp(code=503))
        assert res == "missing"
        assert sdb.players.find_one({"iid": TEST_IID})["photo_checked_at"] is None
        sdb.ingest_queue.update_one({"task": "player_photo", "key": TEST_EXT}, {"$set": {"status": "done", "result": res}})  # as ingest.process_queue does
        assert PP.plan(sdb, force=True) == 1
        q = sdb.ingest_queue.find_one({"task": "player_photo", "key": TEST_EXT})
        assert q["status"] == "pending", f"plan() counted the player but the queue task stays '{q['status']}' (enqueue only $setOnInsert status)"
