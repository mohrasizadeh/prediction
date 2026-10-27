# Iteration 15 cleanup: remove TEST users and their sessions / 2FA / audit-free side data
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))
from pymongo import MongoClient
db = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
emails = ["test_e1_user@example.com", "test_e1_admin@example.com"]
ids = [u["id"] for u in db.users.find({"email": {"$in": emails}}, {"id": 1})]
for c in db.list_collection_names():
    for f in ("user_id", "uid"):
        n = db[c].delete_many({f: {"$in": ids}}).deleted_count if ids else 0
        if n: print(c, f, n)
print("users", db.users.delete_many({"email": {"$in": emails}}).deleted_count)
