# Iteration 12 helper: issue a newsletter confirm token and an unsubscribe token for a resend.dev test address
import os, sys, json
from datetime import timedelta
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))
from pymongo import MongoClient
import accounts, emailer

db = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
e = sys.argv[1]
log = db.email_log.find_one({"to": e}, sort=[("_id", -1)])
print("email_log", {k: (str(v)[:120]) for k, v in (log or {}).items() if k != "_id"})
print("newsletter row", db.newsletter.find_one({"email": e}, {"_id": 0, "token_hash": 0}))
tok = accounts.issue_token(db, None, "newsletter_confirm", timedelta(days=3), {"email": e})
json.dump({"confirm": tok, "unsub": emailer.sign_unsub(e)}, open("/tmp/t12_tokens.json", "w"))
print("tokens written")
