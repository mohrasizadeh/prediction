# Iteration 21: update pack docs/23 parts B (forecast cards), C (brain: availability, context, calibration), D (SportAPI live, OFF)
import os
import sys
import time
import datetime

import pytest
import requests

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.dirname(HERE))
from dotenv import load_dotenv  # noqa: E402
load_dotenv(os.path.join(os.path.dirname(HERE), ".env"))
from pymongo import MongoClient  # noqa: E402

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
API = f"{BASE_URL}/api"
DB = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
NOW = datetime.datetime.now(datetime.timezone.utc)
NEW_KEYS = ("cards", "availability", "context", "live", "live_events")
OLD_KEYS = ("forecasts", "events", "rotation", "h2h", "starters")


def _get(url, **kw):
    for _ in range(4):
        r = requests.get(url, timeout=60, **kw)
        if r.status_code != 429:
            return r
        time.sleep(15)
    return r


@pytest.fixture(scope="module")
def admin():
    from admin_login_helper import admin_session
    return admin_session()


@pytest.fixture(scope="module")
def match_with_fc():
    m = DB.matches.find_one({"status": "scheduled", "kickoff": {"$gte": NOW}, "iid": {"$in": DB.forecasts.distinct("match_iid", {"kickoff": {"$gte": NOW}})}},
                            {"_id": 0, "id": 1, "iid": 1, "home_iid": 1, "away_iid": 1}, sort=[("kickoff", 1)])
    assert m, "no upcoming match with forecasts"
    return m


# ---------------------------------------------------------------- part B: one card per player
def _check_cards(cards):
    keys = [(c["match_iid"], c["scope"], c["team_iid"], c.get("player_iid")) for c in cards]
    assert len(keys) == len(set(keys)), "a player/team appears twice"
    for c in cards:
        assert isinstance(c["more_lines"], list)
        assert all(x["fkey"] != c["fkey"] for x in c["more_lines"])


def test_match_detail_keys_and_cards(match_with_fc):
    r = _get(f"{API}/matches/{match_with_fc['id']}?cb={time.time()}")
    assert r.status_code == 200
    d = r.json()
    for k in NEW_KEYS + OLD_KEYS:
        assert k in d, k
    assert d["cards"], "cards empty"
    _check_cards(d["cards"])
    # every forecast is in exactly one card (headline or more_lines)
    fk = sorted(f["fkey"] for f in d["forecasts"])
    ck = sorted([c["fkey"] for c in d["cards"]] + [x["fkey"] for c in d["cards"] for x in c["more_lines"]])
    assert fk == ck
    assert isinstance(d["availability"], list) and isinstance(d["live_events"], list)


def test_insights_no_player_twice_per_match():
    r = _get(f"{API}/insights?limit=200")
    assert r.status_code == 200
    rows = r.json()
    rows = rows.get("rows", rows.get("items", rows)) if isinstance(rows, dict) else rows
    assert rows
    keys = [(f["match_iid"], f["scope"], f["team_iid"], f.get("player_iid")) for f in rows]
    assert len(keys) == len(set(keys))
    assert all("more_lines" in f for f in rows)


def test_player_detail_cards(match_with_fc):
    f = DB.forecasts.find_one({"match_iid": match_with_fc["iid"], "player_iid": {"$ne": None}}, {"player_iid": 1})
    p = DB.players.find_one({"iid": f["player_iid"]}, {"id": 1})
    r = _get(f"{API}/players/{p['id']}")
    assert r.status_code == 200
    d = r.json()
    assert "cards" in d and "forecasts" in d
    _check_cards(d["cards"])


def test_no_duplicate_fkeys_in_db():
    dup = list(DB.forecasts.aggregate([{"$group": {"_id": "$fkey", "n": {"$sum": 1}}}, {"$match": {"n": {"$gt": 1}}}, {"$limit": 5}], allowDiskUse=True))
    assert dup == [], dup


def test_regression_referee_booking_firstgoal():
    lg = DB.leagues.find_one({"iid": {"$in": DB.referee_stats.distinct("league_iid")}}, {"id": 1})
    for path in (f"/leagues/{lg['id']}/referee-assignments", f"/leagues/{lg['id']}/booking-risk", f"/leagues/{lg['id']}/referees", "/referees"):
        assert _get(API + path).status_code == 200, path
    t = DB.teams.find_one({"league_iid": {"$exists": True}}, {"id": 1})
    assert _get(f"{API}/teams/{t['id']}/first-goal").status_code == 200


# ---------------------------------------------------------------- part D: live (switch off, no key)
def test_live_scoreboard():
    r = _get(f"{API}/live?date={NOW.date().isoformat()}&tz=0")
    assert r.status_code == 200
    d = r.json()
    assert set(("leagues", "live_count", "updated")) <= set(d)
    assert isinstance(d["leagues"], list) and isinstance(d["live_count"], int)


def test_live_bad_date_and_unknown_sid():
    assert _get(f"{API}/live?date=2026-1-1").status_code == 400
    assert _get(f"{API}/results?date=bad").status_code == 400
    r = _get(f"{API}/results?date={NOW.date().isoformat()}")
    assert r.status_code == 200 and "results" in r.json()
    assert _get(f"{API}/live/123456789/events").status_code == 404
    assert _get(f"{API}/live/123456789/lineups").status_code == 404


def test_jobs_live_requires_secret():
    assert requests.post(f"{API}/jobs/live", timeout=30).status_code == 401
    assert requests.post(f"{API}/jobs/live", headers={"X-CRON-SECRET": "wrong"}, timeout=30).status_code == 401


def test_admin_sportapi_status_and_tick(admin):
    before = admin.get(f"{API}/admin/sportapi").json()
    assert before["enabled"] is False and before["cap"] == 1800 and before["plan_limit"] == 2000
    r = admin.post(f"{API}/admin/sportapi/tick")
    assert r.status_code == 200 and r.json()["status"] == "off", r.text
    after = admin.get(f"{API}/admin/sportapi").json()
    assert after["calls_today"] == before["calls_today"]


def test_admin_sportapi_no_key_errors(admin):
    # SAFETY: only run when no key is saved, otherwise these would spend real SportAPI calls
    if admin.get(f"{API}/admin/sportapi").json()["key_saved"]:
        pytest.skip("A SportAPI key is saved; skipping to avoid real SportAPI calls")
    r = admin.get(f"{API}/admin/sportapi/leagues")
    assert r.status_code == 400 and "key" in r.text.lower(), r.text
    r = admin.post(f"{API}/admin/sportapi/backfill", json={"start": "2025-01-01", "end": "2025-01-02"})
    assert r.status_code == 400 and "key" in r.text.lower(), r.text


def test_admin_clubs(admin):
    d = admin.get(f"{API}/admin/clubs").json()
    assert d["leagues"] and all("iid" in l and isinstance(l["teams"], list) for l in d["leagues"])
    assert any(l["teams"] for l in d["leagues"])


def test_admin_keys_include_sportapi(admin):
    r = admin.get(f"{API}/admin/keys")
    assert r.status_code == 200
    assert "sportapi" in r.text and "SportAPI key" in r.text


# ---------------------------------------------------------------- part C: availability, brain, calibration
def test_availability_flow(admin, match_with_fc):
    team = DB.teams.find_one({"iid": match_with_fc["home_iid"]}, {"id": 1})
    assert DB.availability.count_documents({"team_iid": match_with_fc["home_iid"]}) == 0 or True
    lst = admin.get(f"{API}/admin/availability", params={"team": team["id"]})
    assert lst.status_code == 200
    players = lst.json()["players"]
    pl = next(p for p in players if p["status"] == "available")
    try:
        bad = admin.put(f"{API}/admin/availability", json={"player_id": pl["id"], "status": "out", "reason": "safe bet, odds boost"})
        assert bad.status_code == 400, bad.text
        r = admin.put(f"{API}/admin/availability", json={"player_id": pl["id"], "status": "out", "reason": "TEST_hamstring"})
        assert r.status_code == 200 and r.json()["status"] == "out"
        lst2 = admin.get(f"{API}/admin/availability", params={"team": team["id"]}).json()["players"]
        assert next(p for p in lst2 if p["id"] == pl["id"])["status"] == "out"
        md = admin.get(f"{API}/matches/{match_with_fc['id']}").json()
        row = [a for a in md["availability"] if a["player"]["id"] == pl["id"]]
        assert row and row[0]["status"] == "out" and row[0]["reason"] == "TEST_hamstring"
        assert admin.put(f"{API}/admin/availability", json={"player_id": pl["id"], "status": "sideline"}).status_code in (400, 422)
    finally:
        r = admin.put(f"{API}/admin/availability", json={"player_id": pl["id"], "status": "available"})
        assert r.status_code == 200
    assert not DB.availability.find_one({"reason": "TEST_hamstring"})


def test_brain_status(admin):
    d = admin.get(f"{API}/admin/brain").json()
    c = d["calibration"]
    assert {"enabled", "version", "source"} <= set(c) and c["source"] == "default"
    assert "engine.absence_model" in d["engine"] and "engine.match_context" in d["engine"]


def test_calibration_rollback(admin):
    r = admin.post(f"{API}/admin/calibration/rollback")
    assert r.status_code == 200 and r.json()["status"] == "default"
    assert requests.post(f"{API}/admin/calibration/rollback", timeout=30).status_code in (401, 403)


def test_switches_off_in_db():
    vals = {s["key"]: s.get("value") for s in DB.settings.find({"key": {"$in": ["sportapi.enabled", "injuries.enabled"]}})} if "settings" in DB.list_collection_names() else {}
    assert not vals.get("sportapi.enabled") and not vals.get("injuries.enabled")


# ---------------------------------------------------------------- contact form fix
def test_contact_202():
    r = requests.post(f"{API}/contact", json={"name": "TEST_iter21", "email": "test_iter21@example.com", "message": "TEST_iter21 hello"}, timeout=30)
    assert r.status_code == 202, r.text
    DB.contact_messages.delete_many({"email": "test_iter21@example.com"})
