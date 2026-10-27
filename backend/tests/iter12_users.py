# Create / delete TEST admin, owner (tracking), analyst for iteration 12 (Phase 4c). Recipients are resend.dev test inboxes only.
import os, sys, secrets, datetime
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))
from pymongo import MongoClient
import accounts

db = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
now = datetime.datetime.now(datetime.timezone.utc)
PW = "Test-Admin-Pass-2026!q"
USERS = [("delivered+t12admin@resend.dev", "admin"),
         ("delivered+t12owner@resend.dev", "owner"),
         ("delivered+t12analyst@resend.dev", "analyst")]


def create():
    for email, role in USERS:
        if db.users.find_one({"email": email}):
            print("exists", email); continue
        uid = "TEST" + secrets.token_hex(6)
        db.users.insert_one({"id": uid, "email": email, "role": role,
                             "password_hash": accounts.hash_password(PW), "display_name": "TEST " + role, "tz": "UTC",
                             "theme": "light", "email_verified": True, "failed_logins": 0, "created_at": now,
                             "had_trial": False, "disabled": False,
                             "prefs": {"product_emails": True, "marketing_emails": False, "alert_emails": True}})
        print("created", email, role, uid)


def delete():
    for email, _ in USERS:
        u = db.users.find_one({"email": email})
        if not u:
            continue
        uid = u["id"]
        for c in ("subscriptions", "payments", "sessions", "email_log", "events", "auth_log"):
            db[c].delete_many({"user_id": uid})
        db.email_log.delete_many({"to": email})
        db.users.delete_one({"id": uid})
        print("deleted", email)


if __name__ == "__main__":
    delete() if sys.argv[1:] == ["delete"] else create()
