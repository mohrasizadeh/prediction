# iter25: create / delete TEST users for R5 testing (preview only). usage: python iter25_users.py create|delete
import os, sys, secrets, datetime
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))
from pymongo import MongoClient
import accounts

db = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
now = datetime.datetime.now(datetime.timezone.utc)
USERS = [("test_e1_user@example.com", "Test-User-Pass-2026!q"), ("test_r5_welcome@example.com", "Test-User-Pass-2026!q")]
if sys.argv[1] == "create":
    for email, pw in USERS:
        if db.users.find_one({"email": email}):
            print("exists", email); continue
        db.users.insert_one({"id": secrets.token_hex(8), "email": email, "role": "user",
                             "password_hash": accounts.hash_password(pw), "display_name": "", "tz": "UTC",
                             "theme": "light", "email_verified": True, "failed_logins": 0, "created_at": now,
                             "had_trial": False, "disabled": False,
                             "prefs": {"product_emails": True, "marketing_emails": False, "alert_emails": True}})
        print("created", email)
else:
    for email, _ in USERS:
        u = db.users.find_one({"email": email})
        if not u: continue
        uid = u["id"]
        for c in db.list_collection_names():
            if c == "users": continue
            r = db[c].delete_many({"user_id": uid})
            if r.deleted_count: print("deleted", r.deleted_count, "from", c)
        db.users.delete_one({"id": uid}); print("deleted user", email)
