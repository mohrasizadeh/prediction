"""reset_admin.py -- locked out of the owner account? Run this from the backend shell.

    python reset_admin.py

Sets the OWNER password to ADMIN_INITIAL_PASSWORD, unlocks the account, turns two-factor off (you must enrol again
at next sign-in), signs out every owner session, and forces a password change.
Needs MONGO_URL, DB_NAME, ADMIN_EMAIL, ADMIN_INITIAL_PASSWORD in the environment.
"""
import os
import sys
from datetime import datetime, timezone

from pymongo import MongoClient

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import accounts

db = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
email = os.environ["ADMIN_EMAIL"].strip().lower()
u = db.users.find_one({"email": email, "role": "owner"})
if not u:
    print("no owner with that e-mail")
    raise SystemExit(1)
db.users.update_one({"id": u["id"]}, {"$set": {"password_hash": accounts.hash_password(os.environ["ADMIN_INITIAL_PASSWORD"]), "must_change_password": True,
                                              "failed_logins": 0, "disabled": False, "email_verified": True},
                                     "$unset": {"locked_until": "", "totp": "", "recovery_codes": ""}})
accounts.revoke_all(db, u["id"])
db.audit_log.insert_one({"actor": "shell", "actor_role": "shell", "action": "owner.reset", "target": u["id"], "at": datetime.now(timezone.utc)})
print("owner reset: sign in with ADMIN_INITIAL_PASSWORD, change it, and set up two-factor again")
