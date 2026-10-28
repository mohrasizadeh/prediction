# iter27: usual_p on forecasts, team history, squad-season, player ranks, match-days, search next, predicted XI,
# track-record scope, match follows, presets, notes, zones admin, alert prefs, follow_alerts unit test (separate DB, fake mailer).
import os, sys, pytest, requests
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
BASE = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/") or open("/app/frontend/.env").read().split("REACT_APP_BACKEND_URL=")[1].split()[0].rstrip("/")
os.environ["REACT_APP_BACKEND_URL"] = BASE
from admin_login_helper import admin_session  # noqa: E402

USER = {"email": "test_e1_user@example.com", "password": "Test-User-Pass-2026!q"}
LALIGA = "459108cf-0d2e-4281-bf44-d44d406d11f5"
LALIGA_IID = 30
MATCH = "36cf495e-6dfa-4a65-998f-2ec88f506ed2"   # LaLiga, scheduled, no lineups


@pytest.fixture(scope="module")
def user():
    s = requests.Session(); s.headers["User-Agent"] = "TEST_ua_iter27_user"
    r = s.post(f"{BASE}/api/auth/login", json=USER)
    if r.status_code != 200:
        pytest.skip(f"user login failed {r.status_code}")
    return s


@pytest.fixture(scope="module")
def admin():
    try:
        return admin_session()
    except Exception as e:
        pytest.skip(f"admin login failed: {e}")


@pytest.fixture(scope="module")
def match():
    r = requests.get(f"{BASE}/api/matches/{MATCH}"); assert r.status_code == 200, r.text
    return r.json()


# usual_p on match forecasts + insights
def test_match_usual(match):
    fc = match.get("forecasts") or []
    assert fc, "no forecasts on match"
    assert all("usual_p" in f and "usual_n" in f for f in fc)
    withp = [f for f in fc if f["usual_p"] is not None]
    assert withp and all(0 <= f["usual_p"] <= 1 and f["usual_n"] >= 5 for f in withp)


def test_insights_usual():
    r = requests.get(f"{BASE}/api/insights"); assert r.status_code == 200, r.text
    d = r.json()
    rows = d if isinstance(d, list) else (d.get("forecasts") or d.get("items") or d.get("rows") or [])
    assert rows, list(d)
    assert all("usual_p" in f for f in rows)


# predicted XI
def test_predicted_xi(match):
    pr = match.get("predicted") or []
    assert len(pr) == 22, len(pr)
    for side in {p["team_iid"] for p in pr}:
        s = [p for p in pr if p["team_iid"] == side]
        assert len(s) == 11 and sum(1 for p in s if p["pos"] == "GK") == 1


def test_team_history_and_squad(match):
    tid = (match.get("home") or {}).get("id") or match["match"]["home"]["id"] if "match" in match else match["home"]["id"]
    r = requests.get(f"{BASE}/api/teams/{tid}/history", params={"stat": "corners", "last": 10}); assert r.status_code == 200, r.text
    g = r.json()["games"]; assert 0 < len(g) <= 10 and all("corners" in x for x in g)
    assert requests.get(f"{BASE}/api/teams/{tid}/history", params={"stat": "bogus"}).status_code == 422
    r = requests.get(f"{BASE}/api/teams/{tid}/squad-season"); assert r.status_code == 200
    ps = r.json()["players"]; assert ps
    for k in ("apps", "starts", "minutes", "goals", "shots", "tackles", "yellow_cards", "player"):
        assert k in ps[0]
    assert "_id" not in str(r.json())


def test_player_ranks(match):
    pid = next(f["player"]["id"] for f in match["forecasts"] if f.get("scope") == "player" and f.get("player"))
    r = requests.get(f"{BASE}/api/players/{pid}/ranks"); assert r.status_code == 200
    d = r.json()
    for x in d["ranks"]:
        assert 1 <= x["rank"] <= x["of"]


def test_match_days():
    r = requests.get(f"{BASE}/api/match-days", params={"start": "2026-10-27", "days": 7, "tz_offset_min": -300}); assert r.status_code == 200
    days = r.json()["days"]; assert days and all(len(d) == 10 for d in days)
    assert requests.get(f"{BASE}/api/match-days", params={"start": "bad"}).status_code == 422


def test_search_next():
    r = requests.get(f"{BASE}/api/search", params={"q": "sa"}); assert r.status_code == 200
    pl = r.json().get("players") or []
    assert pl and all("next" in p for p in pl)
    nx = [p["next"] for p in pl if p["next"]]
    assert nx and all(0 <= n["p"] <= 1 for n in nx)


def test_track_record_scope():
    for sc in ("player", "team"):
        r = requests.get(f"{BASE}/api/track-record", params={"scope": sc, "stat": "shots"}); assert r.status_code == 200, r.text
    assert requests.get(f"{BASE}/api/track-record", params={"scope": "x"}).status_code == 422


# match follows + feed
def test_follow_match(user):
    r = user.put(f"{BASE}/api/me/follows", json={"kind": "match", "ref_id": MATCH}); assert r.status_code == 201, r.text
    items = user.get(f"{BASE}/api/me/follows").json()["items"]
    m = [i for i in items if i["kind"] == "match"]
    assert m and m[0]["id"] == MATCH and " v " in m[0]["name"]
    feed = user.get(f"{BASE}/api/me/following-feed").json()
    assert any(x["id"] == MATCH for x in feed["matches"]) and "lineups" in feed
    r = user.delete(f"{BASE}/api/me/follows", json={"kind": "match", "ref_id": MATCH}); assert r.json()["removed"] == 1


def test_presets_roundtrip(user):
    body = {"items": [{"name": "TEST_preset", "q": "stat=shots&min=0.6"}]}
    assert user.put(f"{BASE}/api/me/presets", json=body).status_code == 200
    s2 = requests.Session(); s2.post(f"{BASE}/api/auth/login", json=USER)
    assert s2.get(f"{BASE}/api/me/presets").json()["items"] == body["items"]
    assert user.put(f"{BASE}/api/me/presets", json={"items": [{"name": "x", "q": ""}] * 9}).status_code == 422
    assert user.put(f"{BASE}/api/me/presets", json={"items": []}).json()["items"] == []
    assert requests.get(f"{BASE}/api/me/presets").status_code == 401


def test_note_roundtrip(user, match):
    pid = next(f["player"]["id"] for f in match["forecasts"] if f.get("scope") == "player" and f.get("player"))
    assert user.put(f"{BASE}/api/me/notes/{pid}", json={"text": "TEST_note"}).status_code == 200
    assert user.get(f"{BASE}/api/me/notes/{pid}").json()["text"] == "TEST_note"
    assert user.delete(f"{BASE}/api/me/notes/{pid}").json()["removed"] == 1


def test_alert_prefs(user):
    r = user.patch(f"{BASE}/api/account/profile", json={"prefs": {"alert_lineups": False, "alert_goals": False}}); assert r.status_code == 200, r.text
    p = user.get(f"{BASE}/api/auth/me").json()
    prefs = (p.get("user") or p).get("prefs") or {}
    assert prefs.get("alert_lineups") is False and prefs.get("alert_goals") is False
    user.patch(f"{BASE}/api/account/profile", json={"prefs": {"alert_lineups": True, "alert_goals": True}})


def test_zones_admin(admin):
    z = [{"start": 18, "end": 20, "label": "Relegation", "tone": "bottom"}, {"start": 1, "end": 4, "label": "Champions League", "tone": "top"}]
    r = admin.put(f"{BASE}/api/admin/leagues/{LALIGA_IID}", json={"zones": z})
    if r.status_code == 422:
        pytest.fail(f"tone values? {r.text}")
    assert r.status_code == 200, r.text
    pub = requests.get(f"{BASE}/api/leagues/{LALIGA}").json()["zones"]
    assert [x["start"] for x in pub] == [1, 18]
    r = admin.put(f"{BASE}/api/admin/leagues/{LALIGA_IID}", json={"zones": []}); assert r.status_code == 200
    assert requests.get(f"{BASE}/api/leagues/{LALIGA}").json()["zones"] == []


# follow_alerts unit test: separate DB, fake mailer, example.com users
def test_follow_alerts_unit(monkeypatch):
    from dotenv import load_dotenv
    load_dotenv("/app/backend/.env")
    from pymongo import MongoClient
    import follow_alerts as FA, emailer as E
    import plans
    monkeypatch.setattr(plans, "ent", lambda db, u, k: True)   # alerts are a Pro entitlement
    cl = MongoClient(os.environ["MONGO_URL"]); name = os.environ["DB_NAME"] + "_test_fa27"
    db = cl[name]; cl.drop_database(name)
    sent = []
    monkeypatch.setattr(E, "send_template", lambda db, t, to, user=None, vars=None, idem=None, **k: sent.append((t, to, vars)) or {"status": "sent"})
    monkeypatch.setattr(E, "base_url", lambda: "https://x.example.com")
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    try:
        db.teams.insert_many([{"iid": 1, "id": "t1", "name": "TEST Home"}, {"iid": 2, "id": "t2", "name": "TEST Away"}])
        db.players.insert_one({"iid": 9, "id": "p9", "name": "TEST Striker", "team_iid": 1})
        db.matches.insert_one({"iid": 5, "id": "m5", "status": "scheduled", "kickoff": now + timedelta(hours=1), "home_iid": 1, "away_iid": 2,
                               "live": {"sid": 77, "at": now, "minute": "30'", "hs": 1, "as": 0}})
        db.lineups.insert_one({"match_iid": 5, "team_iid": 1, "player_iid": 9, "confirmed": True, "started": True})
        db.live_events.insert_many([{"fixture_sid": 77, "eid": "e1", "type": "goal", "minute": "28'", "minute_num": 28, "player_name": "TEST Striker"},
                                    {"fixture_sid": 77, "eid": "e2", "type": "red_card", "extra": "Red card", "minute": "29'", "minute_num": 29},
                                    {"fixture_sid": 77, "eid": "e3", "type": "yellow_card", "extra": "Yellow card", "minute": "29'", "minute_num": 29},
                                    {"fixture_sid": 77, "eid": "e0", "type": "goal", "minute": "5'", "minute_num": 5}])
        base = {"disabled": False, "email_verified": True}
        db.users.insert_many([{**base, "id": "u1", "email": "TEST_fa1@example.com", "prefs": {}},
                              {**base, "id": "u2", "email": "TEST_fa2@example.com", "prefs": {"alert_goals": False}},
                              {**base, "id": "u3", "email": "TEST_fa3@example.com", "prefs": {"alert_emails": False}}])
        db.follows.insert_many([{"user_id": "u1", "kind": "player", "ref_iid": 9}, {"user_id": "u1", "kind": "match", "ref_iid": 5},
                                {"user_id": "u2", "kind": "match", "ref_iid": 5}, {"user_id": "u3", "kind": "team", "ref_iid": 1}])
        r1 = FA.run(db, now)
        kinds = sorted((t, to) for t, to, _ in sent)
        assert r1["lineups"] == 2, (r1, kinds)                 # u1 + u2 (u3 has alerts off)
        assert r1["goals"] == 2, (r1, kinds)                   # u1: goal e1 + red e2 (old goal e0 + yellow skipped); u2 goals off
        lu = [v for t, to, v in sent if t == "lineup_alert" and to == "TEST_fa1@example.com"][0]
        assert "TEST Striker" in lu["players"] and lu["link"].endswith("/match/m5")
        assert not any(to == "TEST_fa3@example.com" for _, to, _ in sent)
        r2 = FA.run(db, now)
        assert r2 == {"lineups": 0, "goals": 0}, r2            # once per user/event
        assert db.follow_alerts.count_documents({}) == 4
    finally:
        cl.drop_database(name)


# follow_alerts: SportAPI event types (red_card / second_yellow / own_goal / penalty) as stored by sportapi.store_events
def test_follow_alerts_real_event_types(monkeypatch):
    from dotenv import load_dotenv
    load_dotenv("/app/backend/.env")
    from pymongo import MongoClient
    import follow_alerts as FA, emailer as E
    import plans
    monkeypatch.setattr(plans, "ent", lambda db, u, k: True)   # alerts are a Pro entitlement
    cl = MongoClient(os.environ["MONGO_URL"]); name = os.environ["DB_NAME"] + "_test_fa27b"
    db = cl[name]; cl.drop_database(name)
    sent = []
    monkeypatch.setattr(E, "send_template", lambda db, t, to, user=None, vars=None, idem=None, **k: sent.append((t, vars["what"])) or {"status": "sent"})
    monkeypatch.setattr(E, "base_url", lambda: "https://x.example.com")
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    try:
        db.teams.insert_many([{"iid": 1, "id": "t1", "name": "TEST Home"}, {"iid": 2, "id": "t2", "name": "TEST Away"}])
        db.matches.insert_one({"iid": 5, "id": "m5", "status": "scheduled", "kickoff": now - timedelta(minutes=40), "home_iid": 1, "away_iid": 2,
                               "live": {"sid": 78, "at": now, "minute": "40'", "hs": 1, "as": 1}})
        db.live_events.insert_many([{"fixture_sid": 78, "eid": 1, "type": "red_card", "extra": "TEST Player", "minute": "35'", "minute_num": 35},
                                    {"fixture_sid": 78, "eid": 2, "type": "own_goal", "extra": "Own goal", "minute": "36'", "minute_num": 36},
                                    {"fixture_sid": 78, "eid": 3, "type": "penalty", "extra": "Penalty", "minute": "37'", "minute_num": 37},
                                    {"fixture_sid": 78, "eid": 4, "type": "second_yellow", "extra": "TEST Player 2", "minute": "38'", "minute_num": 38}])
        db.users.insert_one({"id": "u1", "email": "TEST_fa1@example.com", "prefs": {}, "disabled": False, "email_verified": True})
        db.follows.insert_one({"user_id": "u1", "kind": "match", "ref_iid": 5})
        r = FA.run(db, now)
        assert r["goals"] == 4, f"only {r['goals']} of 4 alerts sent: {sent}"
    finally:
        cl.drop_database(name)
