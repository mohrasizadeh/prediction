# Iteration 12 cleanup: TEST popups' stats, resend.dev newsletter rows/e-mails, TEST webhooks + deliveries, rate limits, TEST staff users
import os, sys, re
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))
from pymongo import MongoClient

db = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
OWN = ["6ae01bc88f38f65403cf2974", "6ae01b996b81e54c91bf4ee2", "6ae01aabb9a354f428999af6"]
live_ids = [str(p["_id"]) for p in db.popups.find({}, {"_id": 1})]
print("popups left", live_ids)
ps = db.popup_stats.find_one({}) or {}
print("popup_stats sample keys", list(ps.keys())[:8])
for f in ("popup_id", "pid", "popup"):
    n = db.popup_stats.delete_many({f: {"$exists": True, "$nin": live_ids}}).deleted_count
    if n: print("popup_stats removed", f, n)
if "popup_events" in db.list_collection_names():
    print("popup_events removed", db.popup_events.delete_many({"popup_id": {"$nin": live_ids}}).deleted_count)
rx = re.compile(r"@resend\.dev$")
print("newsletter rows", db.newsletter.delete_many({"email": rx}).deleted_count)
print("suppressions", db.email_suppressions.delete_many({"email": rx}).deleted_count)
eps = [e["id"] for e in db.webhook_endpoints.find({"$or": [{"url": re.compile("example\\.com")}, {"note": "TEST"}]}, {"id": 1})]
print("test endpoints", db.webhook_endpoints.delete_many({"id": {"$in": eps}}).deleted_count)
live_eps = [e["id"] for e in db.webhook_endpoints.find({}, {"id": 1})]
print("orphan deliveries", db.webhook_deliveries.delete_many({"endpoint_id": {"$nin": live_eps}}).deleted_count)
print("orphan outbox", db.webhook_outbox.delete_many({"endpoint_id": {"$nin": live_eps}}).deleted_count)
print("rate limits", db.rate_limits.delete_many({"_id": re.compile("^(nlsub|popsub|popev)")}).deleted_count)
print("tokens", db.tokens.delete_many({"kind": "newsletter_confirm", "data.email": rx}).deleted_count if "tokens" in db.list_collection_names() else "n/a")
print("email_log", db.email_log.delete_many({"to": rx}).deleted_count)
