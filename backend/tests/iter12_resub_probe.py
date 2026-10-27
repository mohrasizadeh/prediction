# Iteration 12 probe: does re-subscribing a confirmed address downgrade it to pending?
import os, sys, secrets
from datetime import timedelta
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))
import requests
from pymongo import MongoClient
import accounts

API = os.environ["REACT_APP_BACKEND_URL"].rstrip("/") + "/api"
db = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
e = f"delivered+t12re{secrets.token_hex(2)}@resend.dev"
print(requests.post(f"{API}/newsletter/subscribe", json={"email": e, "consent": True}).status_code)
tok = accounts.issue_token(db, None, "newsletter_confirm", timedelta(days=3), {"email": e})
print("confirm", requests.post(f"{API}/newsletter/confirm", json={"token": tok}).status_code)
print("after confirm", db.newsletter.find_one({"email": e}, {"_id": 0, "status": 1, "confirmed_at": 1}))
print(requests.post(f"{API}/newsletter/subscribe", json={"email": e, "consent": True}).status_code)
print("after re-subscribe", db.newsletter.find_one({"email": e}, {"_id": 0, "status": 1, "confirmed_at": 1}))
print("confirm mails", db.email_log.count_documents({"to": e, "template": "newsletter_confirm"}))
