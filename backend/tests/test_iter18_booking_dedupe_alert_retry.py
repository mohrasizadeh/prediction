# Iteration 18: booking_risk one row per player, notify_bookings records only sent/duplicate (retry otherwise),
# idem covers every player+match, referees regression, finder regression (TEST user). No PitchAPI / API-Football calls.
import os
import sys
import secrets
import datetime

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
NOW = lambda: datetime.datetime.now(datetime.timezone.utc)  # noqa: E731

LEAGUES = {"Bundesliga": "37140a56-00d6-4ed9-a7de-46f6d19a5e64", "LaLiga": "459108cf-0d2e-4281-bf44-d44d406d11f5",
           "Premier League": "4db3952b-e933-4076-be81-0d48989fb9a6", "Serie A": "1e2b1fe0-57a2-4084-9c33-095eb7ad7e49"}
SERIE_A_IID = 61
EMAIL = "delivered@resend.dev"
PW = "Test-Bk18-Pass-2026!q"


def _mk_user(email, alert=True):
    import accounts
    uid = "test_" + secrets.token_hex(6)
    DB.users.insert_one({"id": uid, "email": email, "role": "user", "password_hash": accounts.hash_password(PW),
                         "display_name": "TEST Booker18", "tz": "UTC", "theme": "light", "email_verified": True, "failed_logins": 0,
                         "created_at": NOW(), "had_trial": False, "disabled": False,
                         "prefs": {"product_emails": True, "marketing_emails": False, "alert_emails": alert}})
    return uid


def _cleanup(uid):
    DB.follows.delete_many({"user_id": uid})
    DB.sessions.delete_many({"user_id": uid})
    DB.booking_alerts.delete_many({"_id": {"$regex": f"^{uid}:"}})
    DB.email_log.delete_many({"user_id": uid})
    DB.users.delete_many({"id": uid})


# booking_risk: each player once (his next match)
class TestBookingRiskUnique:
    @pytest.mark.parametrize("name", list(LEAGUES))
    def test_unique_players(self, name):
        d = requests.get(f"{API}/leagues/{LEAGUES[name]}/booking-risk").json()
        rows = d["rows"]
        assert rows, f"{name} empty"
        pids = [r["player_iid"] for r in rows]
        assert len(pids) == len(set(pids)), f"{name} duplicates {pids}"
        ps = [r["p"] for r in rows]
        assert ps == sorted(ps, reverse=True)
        assert all(r["stat"] == "yellow_cards" for r in rows)

    def test_row_is_players_next_match(self):
        """Each row's kickoff is the earliest current yellow forecast for that player in the window."""
        d = requests.get(f"{API}/leagues/{LEAGUES['Serie A']}/booking-risk").json()
        now = datetime.datetime.utcnow()
        for r in d["rows"][:10]:
            first = DB.forecasts.find_one({"league_iid": SERIE_A_IID, "is_current": True, "stat": "yellow_cards", "scope": "player",
                                           "player_iid": r["player_iid"], "kickoff": {"$gte": now}}, sort=[("kickoff", 1)])
            assert first and first["match_iid"] == r["match_iid"], (r["player_iid"], r["match_iid"], first and first["match_iid"])


# /me/booking-risk unique with several follows
class TestMeBookingRisk:
    @pytest.fixture(scope="class")
    def env(self):
        DB.users.delete_many({"email": EMAIL, "id": {"$regex": "^test_"}})
        uid = _mk_user(EMAIL)
        tops = {}
        for name in ("Serie A", "Premier League"):
            tops[name] = requests.get(f"{API}/leagues/{LEAGUES[name]}/booking-risk").json()["rows"][:3]
            for r in tops[name]:
                DB.follows.insert_one({"user_id": uid, "kind": "player", "ref_iid": r["player_iid"], "created_at": NOW()})
        yield {"uid": uid, "tops": tops}
        _cleanup(uid)

    def test_me_unique(self, env):
        s = requests.Session()
        assert s.post(f"{API}/auth/login", json={"email": EMAIL, "password": PW}).status_code == 200
        d = s.get(f"{API}/me/booking-risk").json()
        pids = [x["player_iid"] for x in d["rows"]]
        assert len(pids) == 6, d
        assert len(set(pids)) == len(pids)
        assert all(1 <= x["rank"] <= 10 for x in d["rows"])


# notify_bookings: retry when blocked, idem covers all items
class TestNotifyRetry:
    @pytest.fixture(scope="class")
    def env(self):
        DB.users.delete_many({"email": EMAIL, "id": {"$regex": "^test_"}})
        prev_supp = DB.email_suppressions.find_one({"email": EMAIL})
        uid = _mk_user(EMAIL, alert=False)
        top = [r for r in requests.get(f"{API}/leagues/{LEAGUES['Serie A']}/booking-risk").json()["rows"][:10] if r["p"] >= 0.2]
        assert len(top) >= 3
        for r in top[:2]:
            DB.follows.insert_one({"user_id": uid, "kind": "player", "ref_iid": r["player_iid"], "created_at": NOW()})
        yield {"uid": uid, "top": top}
        DB.email_suppressions.delete_many({"email": EMAIL})
        if prev_supp:
            DB.email_suppressions.insert_one(prev_supp)
        _cleanup(uid)

    def _alerts(self, uid):
        return DB.booking_alerts.count_documents({"_id": {"$regex": f"^{uid}:"}})

    def _logs(self, uid, **q):
        return list(DB.email_log.find({"user_id": uid, "template": "booking_alert", **q}))

    def test_flow(self, env):
        import cards_model
        import emailer as E
        uid, top = env["uid"], env["top"]
        # 1. alert_emails false: skip before send, nothing recorded
        assert cards_model.notify_bookings(DB, SERIE_A_IID) == 0
        assert self._alerts(uid) == 0 and self._logs(uid) == []
        # 2. alerts on but address suppressed: skipped_suppressed, nothing recorded
        DB.users.update_one({"id": uid}, {"$set": {"prefs.alert_emails": True}})
        E.suppress(DB, EMAIL, "manual", "TEST_iter18")
        assert cards_model.notify_bookings(DB, SERIE_A_IID) == 0
        logs = self._logs(uid)
        assert logs and all(lg["status"] == "skipped_suppressed" for lg in logs), [lg["status"] for lg in logs]
        assert self._alerts(uid) == 0
        # 3. unsuppressed: sends, records both keys; idem includes both player:match
        DB.email_suppressions.delete_many({"email": EMAIL})
        assert cards_model.notify_bookings(DB, SERIE_A_IID) == 1
        sent = self._logs(uid, status="sent")
        assert len(sent) == 1
        idem = sent[0].get("idem", "")
        for r in top[:2]:
            assert f"{r['player_iid']}:{r['match_iid']}" in idem, idem
        assert self._alerts(uid) == 2
        for a in DB.booking_alerts.find({"_id": {"$regex": f"^{uid}:"}}):
            assert a["status"] == "sent"
        # 4. again: nothing new
        assert cards_model.notify_bookings(DB, SERIE_A_IID) == 0
        assert len(self._logs(uid, status="sent")) == 1
        # 5. follow a 3rd top player: new e-mail only for him, distinct idem
        DB.follows.insert_one({"user_id": uid, "kind": "player", "ref_iid": top[2]["player_iid"], "created_at": NOW()})
        assert cards_model.notify_bookings(DB, SERIE_A_IID) == 1
        sent = self._logs(uid, status="sent")
        assert len(sent) == 2
        new = [s for s in sent if s["idem"] != idem][0]["idem"]
        assert f"{top[2]['player_iid']}:{top[2]['match_iid']}" in new
        assert self._alerts(uid) == 3


# Referees regression
class TestReferees:
    def test_sort_and_filter(self):
        a = requests.get(f"{API}/referees", params={"min_matches": 1}).json()
        c = requests.get(f"{API}/referees", params={"min_matches": 5}).json()
        assert len(a) >= len(c) > 0
        assert all(x["matches"] >= 5 for x in c)
        ys = [x["yellow_pg"] for x in c]
        assert ys == sorted(ys, reverse=True)
        assert requests.get(f"{API}/referees", params={"min_matches": 0}).status_code == 422


# Finder regression (signed-in TEST user)
class TestFinder:
    @pytest.fixture(scope="class")
    def user(self):
        DB.users.delete_many({"email": "test_iter18_finder@example.com"})
        import accounts
        uid = "test_" + secrets.token_hex(6)
        DB.users.insert_one({"id": uid, "email": "test_iter18_finder@example.com", "role": "user", "password_hash": accounts.hash_password(PW),
                             "display_name": "TEST Finder", "tz": "UTC", "theme": "light", "email_verified": True, "failed_logins": 0,
                             "created_at": NOW(), "had_trial": False, "disabled": False,
                             "prefs": {"product_emails": True, "marketing_emails": False, "alert_emails": True}})
        s = requests.Session()
        assert s.post(f"{API}/auth/login", json={"email": "test_iter18_finder@example.com", "password": PW}).status_code == 200
        yield s
        for c in DB.list_collection_names():
            DB[c].delete_many({"user_id": uid})
        DB.users.delete_many({"id": uid})

    @pytest.mark.parametrize("name", ["Premier League", "LaLiga", "Bundesliga"])
    def test_finder(self, user, name):
        r = user.get(f"{API}/finder", params={"mode": "likelihood", "stat": "shots", "threshold": 2, "scope": "player", "leagues": LEAGUES[name]})
        assert r.status_code == 200, r.text
        rows = r.json()
        assert len(rows) > 0
        assert all(x["stat"] == "shots" for x in rows)
