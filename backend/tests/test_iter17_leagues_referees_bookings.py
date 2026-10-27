# Iteration 17: 7-day forecast window for all leagues, referee leaderboard, booking-risk + booking alert e-mails, AF client account errors
import os
import sys
import secrets
import datetime

import httpx
import pytest
import requests

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dotenv import load_dotenv  # noqa: E402
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))
from pymongo import MongoClient  # noqa: E402

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
API = f"{BASE_URL}/api"
DB = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]

LEAGUES = {"Bundesliga": "37140a56-00d6-4ed9-a7de-46f6d19a5e64", "LaLiga": "459108cf-0d2e-4281-bf44-d44d406d11f5",
           "Premier League": "4db3952b-e933-4076-be81-0d48989fb9a6", "Serie A": "1e2b1fe0-57a2-4084-9c33-095eb7ad7e49"}
EMPTY = {"Champions League": "76cb942e-fb46-4545-b826-b9d4b94d797e", "Europa League": "8f2b5dbf-3c35-4d3f-8699-7a9fbaf456a4"}
SERIE_A_IID = 61


@pytest.fixture(scope="module")
def admin():
    from admin_login_helper import admin_session
    return admin_session()


# Finder per league (7-day window)
class TestFinderLeagues:
    @pytest.mark.parametrize("name", list(LEAGUES))
    def test_shots_line2_per_league(self, admin, name):
        r = admin.get(f"{API}/finder", params={"mode": "likelihood", "stat": "shots", "threshold": 2, "scope": "player", "leagues": LEAGUES[name]})
        assert r.status_code == 200, r.text
        rows = r.json()
        assert len(rows) > 0, f"{name} has no shots forecasts"
        assert all(x["stat"] == "shots" for x in rows)
        assert {x["league"]["name"] if isinstance(x.get("league"), dict) else name for x in rows} == {name}

    @pytest.mark.parametrize("name", list(EMPTY))
    def test_cl_el_empty(self, admin, name):
        r = admin.get(f"{API}/finder", params={"mode": "likelihood", "stat": "shots", "threshold": 2, "scope": "player", "leagues": EMPTY[name]})
        assert r.status_code == 200, r.text
        assert r.json() == []


# Match pages have forecasts
class TestMatchForecasts:
    @pytest.mark.parametrize("name", ["Bundesliga", "LaLiga", "Premier League"])
    def test_next_match_has_forecasts(self, name):
        d = requests.get(f"{API}/leagues/{LEAGUES[name]}").json()
        nxt = [m for m in d.get("next", []) if m.get("status", "scheduled") == "scheduled"]
        assert nxt, f"{name} no next matches"
        m = requests.get(f"{API}/matches/{nxt[0]['id']}").json()
        fc = m.get("forecasts")
        n = sum(len(v) for v in fc.values() if isinstance(v, list)) if isinstance(fc, dict) else len(fc or [])
        assert n > 0, f"{name} match {nxt[0]['id']} has no forecasts"


# Referee leaderboard
class TestReferees:
    def test_default_and_shape(self):
        r = requests.get(f"{API}/referees")
        assert r.status_code == 200
        rows = r.json()
        assert rows
        for x in rows:
            assert x["matches"] >= 3
            for k in ("name", "yellow_pg", "red_pg", "pens_pg", "home_win_pct", "leagues"):
                assert k in x
            assert 0 <= x["home_win_pct"] <= 1
            assert x["leagues"] and all(l["name"] and l["id"] for l in x["leagues"])
        ys = [x["yellow_pg"] for x in rows]
        assert ys == sorted(ys, reverse=True)
        assert "_id" not in str(rows)

    def test_min_matches_filter(self):
        a = requests.get(f"{API}/referees", params={"min_matches": 1}).json()
        b = requests.get(f"{API}/referees", params={"min_matches": 3}).json()
        c = requests.get(f"{API}/referees", params={"min_matches": 5}).json()
        assert len(a) >= len(b) >= len(c)
        assert all(x["matches"] >= 5 for x in c)

    def test_validation(self):
        assert requests.get(f"{API}/referees", params={"min_matches": 0}).status_code == 422
        assert requests.get(f"{API}/referees", params={"min_matches": 21}).status_code == 422

    def test_multi_league_aggregation_matches_db(self):
        rows = requests.get(f"{API}/referees", params={"min_matches": 1}).json()
        x = max(rows, key=lambda r: len(r["leagues"]))
        docs = list(DB.referee_stats.find({"referee": x["name"]}))
        assert sum(d["matches"] for d in docs if d["league_iid"] in {l["iid"] for l in DB.leagues.find({"enabled": True})}) == x["matches"]

    def test_detail_link_works(self):
        rows = requests.get(f"{API}/referees").json()
        r = requests.get(f"{API}/referees/{rows[0]['name']}")
        assert r.status_code == 200 and r.json()["name"] == rows[0]["name"]


# Booking risk APIs
class TestBookingRisk:
    def test_me_requires_auth(self):
        assert requests.get(f"{API}/me/booking-risk").status_code == 401

    def test_league_booking_risk(self):
        d = requests.get(f"{API}/leagues/{LEAGUES['Serie A']}/booking-risk").json()
        assert d["rows"]
        ps = [r["p"] for r in d["rows"]]
        assert ps == sorted(ps, reverse=True)
        assert all(r["stat"] == "yellow_cards" and r["player"] for r in d["rows"])

    def test_league_booking_risk_unique_players(self):
        """Top-10 should be 10 distinct players for 'this round' (report-only check)."""
        d = requests.get(f"{API}/leagues/{LEAGUES['Serie A']}/booking-risk").json()
        top = [r["player_iid"] for r in d["rows"][:10]]
        assert len(set(top)) == len(top), f"duplicate players in top 10: {top}"


def _mk_user(email, alert=True):
    import accounts
    uid = "test_" + secrets.token_hex(6)
    DB.users.insert_one({"id": uid, "email": email, "role": "user", "password_hash": accounts.hash_password("Test-Bk-Pass-2026!q"),
                         "display_name": "TEST Booker", "tz": "UTC", "theme": "light", "email_verified": True, "failed_logins": 0,
                         "created_at": datetime.datetime.now(datetime.timezone.utc), "had_trial": False, "disabled": False,
                         "prefs": {"product_emails": True, "marketing_emails": False, "alert_emails": alert}})
    return uid


# Booking alert e-mails + /me/booking-risk with a follow
class TestBookingAlerts:
    @pytest.fixture(scope="class")
    def env(self):
        top = requests.get(f"{API}/leagues/{LEAGUES['Serie A']}/booking-risk").json()["rows"][:10]
        pick = next(r for r in top if r["p"] >= 0.2)
        DB.users.delete_many({"email": {"$in": ["delivered@resend.dev", "test_bk_optout@example.com"]}, "id": {"$regex": "^test_"}})
        u1 = _mk_user("delivered@resend.dev")
        u2 = _mk_user("test_bk_optout@example.com", alert=False)
        for u in (u1, u2):
            DB.follows.insert_one({"user_id": u, "kind": "player", "ref_iid": pick["player_iid"], "created_at": datetime.datetime.now(datetime.timezone.utc)})
        yield {"u1": u1, "u2": u2, "pick": pick}
        for u in (u1, u2):
            DB.follows.delete_many({"user_id": u})
            DB.sessions.delete_many({"user_id": u})
            DB.booking_alerts.delete_many({"_id": {"$regex": f"^{u}:"}})
            DB.email_log.delete_many({"user_id": u})
            DB.users.delete_many({"id": u})

    def test_me_booking_risk(self, env):
        s = requests.Session()
        r = s.post(f"{API}/auth/login", json={"email": "delivered@resend.dev", "password": "Test-Bk-Pass-2026!q"})
        assert r.status_code == 200, r.text
        d = s.get(f"{API}/me/booking-risk").json()
        assert d["rows"], d
        assert all(x["player_iid"] == env["pick"]["player_iid"] for x in d["rows"])
        assert all(1 <= x["rank"] <= 10 for x in d["rows"])
        assert "no-store" in s.get(f"{API}/me/booking-risk").headers.get("cache-control", "")

    def test_notify_once(self, env):
        import cards_model
        n1 = cards_model.notify_bookings(DB, SERIE_A_IID)
        logs = list(DB.email_log.find({"user_id": env["u1"], "template": "booking_alert"}))
        assert n1 >= 1, n1
        assert len(logs) == 1 and logs[0]["status"] == "sent", logs
        assert DB.booking_alerts.count_documents({"_id": {"$regex": f"^{env['u1']}:{env['pick']['player_iid']}:"}}) >= 1
        n2 = cards_model.notify_bookings(DB, SERIE_A_IID)
        assert n2 == 0
        assert DB.email_log.count_documents({"user_id": env["u1"], "template": "booking_alert"}) == 1

    def test_optout_gets_nothing(self, env):
        assert DB.email_log.count_documents({"user_id": env["u2"], "template": "booking_alert"}) == 0


# AF client: account errors are raised, not cached (mock transport, no real call)
class TestAFAccountErrors:
    def test_suspended_not_cached(self):
        import images as IM
        import security
        calls = []

        def fn(req):
            calls.append(str(req.url))
            return httpx.Response(200, json={"errors": {"access": "Your account is suspended"}, "response": []})
        orig = security.get_provider_key
        security.get_provider_key = lambda *a, **k: "dummy-key"
        try:
            c = IM.AFClient(DB, http=httpx.Client(transport=httpx.MockTransport(fn)))
            path = "/players/squads"
            params = {"team": 999999991}
            with pytest.raises(IM.ImageError) as e:
                c.get(path, params)
            assert "account" in str(e.value).lower()
            assert DB.image_api_cache.count_documents({"_id": {"$regex": "team=999999991"}}) == 0
            with pytest.raises(IM.ImageError):
                c.get(path, params)
            assert len(calls) == 2
        finally:
            security.get_provider_key = orig
            today = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")
            DB.image_api_calls.update_one({"_id": today}, {"$inc": {"n": -len(calls)}})
