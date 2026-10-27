# Iteration 20 helper: create / delete the TEST UI user (never the owner). Usage: python iter20_users.py create|delete
import os, sys, secrets, datetime, requests
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))
load_dotenv("/app/frontend/.env")
from pymongo import MongoClient
DB = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
EMAIL, PW = "test_iter20_ui@example.com", "Test-It20-Pass-2026!q"
API = os.environ["REACT_APP_BACKEND_URL"].rstrip("/") + "/api"


def delete():
    for u in DB.users.find({"email": EMAIL}):
        for c in ("follows", "sessions", "email_log"):
            DB[c].delete_many({"user_id": u["id"]})
    DB.users.delete_many({"email": EMAIL})


if sys.argv[1] == "create":
    import accounts
    delete()
    DB.users.insert_one({"id": "test_" + secrets.token_hex(6), "email": EMAIL, "role": "user", "password_hash": accounts.hash_password(PW),
                         "display_name": "TEST UI20", "tz": "UTC", "theme": "light", "email_verified": True, "failed_logins": 0,
                         "created_at": datetime.datetime.now(datetime.timezone.utc), "had_trial": False, "disabled": False,
                         "prefs": {"product_emails": True, "marketing_emails": False, "alert_emails": False}})
    rows = requests.get(f"{API}/leagues/1e2b1fe0-57a2-4084-9c33-095eb7ad7e49/booking-risk").json()["rows"][:2]
    for r in rows:
        p = DB.players.find_one({"iid": r["player_iid"]}, {"id": 1, "name": 1})
        print("PLAYER", p["id"], p["name"])
else:
    delete()
    print("deleted")
