# Create / delete TEST admin, analyst, member for iteration 11 (recipients are resend.dev test inboxes only)
import os, sys, secrets, datetime
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))
from pymongo import MongoClient
import accounts

db = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
now = datetime.datetime.now(datetime.timezone.utc)
USERS = [("delivered+t11admin@resend.dev", "Test-Admin-Pass-2026!q", "admin"),
         ("delivered+t11analyst@resend.dev", "Test-Admin-Pass-2026!q", "analyst"),
         ("delivered+t11member@resend.dev", "Test-User-Pass-2026!q", "user")]


def create():
    for email, pw, role in USERS:
        if db.users.find_one({"email": email}):
            print("exists", email, db.users.find_one({"email": email})["id"]); continue
        uid = "TEST" + secrets.token_hex(6)
        db.users.insert_one({"id": uid, "email": email, "role": role,
                             "password_hash": accounts.hash_password(pw), "display_name": "TEST " + role, "tz": "UTC",
                             "theme": "light", "email_verified": True, "failed_logins": 0, "created_at": now,
                             "had_trial": False, "disabled": False,
                             "prefs": {"product_emails": True, "marketing_emails": False, "alert_emails": True}})
        print("created", email, role, uid)


def delete():
    for email, _, _ in USERS:
        u = db.users.find_one({"email": email})
        if not u:
            continue
        uid = u["id"]
        for c in ("subscriptions", "payments", "sessions", "email_log", "events", "auth_log"):
            print(c, db[c].delete_many({"user_id": uid}).deleted_count)
        print("email_log by to", db.email_log.delete_many({"to": email}).deleted_count)
        db.users.delete_one({"id": uid})
        print("deleted", email)
    print("synthetic subs", db.subscriptions.delete_many({"_id": {"$regex": "^sub_TEST_t11"}}).deleted_count)
    print("synthetic pays", db.payments.delete_many({"_id": {"$regex": "^in_TEST_t11"}}).deleted_count)
    print("webhook events", db.webhook_events.delete_many({"_id": {"$regex": "^stripe:evt_TEST_t11"}}).deleted_count)
    print("campaigns", db.email_campaigns.delete_many({"subject": {"$regex": "^TEST_t11"}}).deleted_count)


if __name__ == "__main__":
    delete() if sys.argv[1:] == ["delete"] else create()
