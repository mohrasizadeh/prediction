# Recreate test_e1_user / test_e1_admin docs (preview only)
import os, sys, secrets, datetime
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))
from pymongo import MongoClient
import accounts

db = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
now = datetime.datetime.now(datetime.timezone.utc)
for email, pw, role in [("test_e1_user@example.com", "Test-User-Pass-2026!q", "user"),
                        ("test_e1_admin@example.com", "Test-Admin-Pass-2026!q", "admin")]:
    if db.users.find_one({"email": email}):
        print("exists", email); continue
    db.users.insert_one({"id": secrets.token_hex(8), "email": email, "role": role,
                         "password_hash": accounts.hash_password(pw), "display_name": "", "tz": "UTC",
                         "theme": "light", "email_verified": True, "failed_logins": 0, "created_at": now,
                         "had_trial": False, "disabled": False,
                         "prefs": {"product_emails": True, "marketing_emails": False, "alert_emails": True}})
    print("created", email, role)
