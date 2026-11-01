"""Ingest queue survives errors (docs/36 H4): no task is ever left "running" for good. Provider failures retry with
back-off and stop the run; other errors retry and the run goes on; tasks cut off by a crash are released; a task
gives up after MAX_ATTEMPTS and raises an ingest issue. Retry-After is parsed safely and capped."""
import os, sys
from datetime import datetime, timedelta, timezone
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import mongomock
import ingest as I
from cached_fetch import PitchError, _retry_after


def check(c, m):
    if not c:
        print("  FAIL", m); sys.exit(1)
    print("  ok  ", m)


UTC = timezone.utc
db = mongomock.MongoClient()["q"]


class Client:
    def __init__(self): self.db = db


def task(key):
    return db.ingest_queue.find_one({"task": "match_ingest", "key": key})


def make(key, iid):
    db.matches.insert_one({"iid": iid, "ext_id": key, "id": f"m{iid}", "league_iid": 1, "ingested_at": None})
    I.enqueue(db, "match_ingest", key, priority=iid)


real = I.ingest_match

# 1. provider failure: retry later, stop the run
make("a", 1); make("b", 2)
def provider_down(client, m): raise PitchError("TRANSPORT", 0, "timeout")
I.ingest_match = provider_down
res = I.process_queue(Client())
check(task("a")["status"] == "pending" and task("a")["attempts"] == 1, "provider timeout: the task goes back to the queue (not stuck 'running')")
check(task("a")["next_run_at"].replace(tzinfo=UTC) > datetime.now(UTC) + timedelta(minutes=10), "...with a back-off before the next try")
check(res["stopped_by"] == "PitchError" and task("b")["status"] == "pending" and task("b")["attempts"] == 0, "...and the run stops, so an outage does not burn the budget on every task")
check("timeout" in task("a")["last_error"], "the last error is kept on the task")

# 2. a bug in one task: that task retries, the rest of the run goes on
db.ingest_queue.update_many({}, {"$set": {"next_run_at": datetime.now(UTC) - timedelta(minutes=1)}})
done = []
def flaky(client, m):
    if m["ext_id"] == "a": raise KeyError("shots")
    done.append(m["ext_id"]); db.matches.update_one({"_id": m["_id"]}, {"$set": {"ingested_at": datetime.now(UTC)}}); return True
I.ingest_match = flaky
res = I.process_queue(Client())
check(task("a")["status"] == "pending" and task("a")["attempts"] == 2 and "KeyError" in task("a")["last_error"], "unexpected error: the task retries later")
check(done == ["b"] and task("b")["status"] == "done", "...and the other tasks still run")

# 3. re-queueing by results_sync no longer meets a stuck task
I.ingest_match = real
db.ingest_queue.update_one({"key": "a"}, {"$set": {"status": "running", "started_at": datetime.now(UTC) - timedelta(minutes=20)}})
check(I.release_stuck(db) == 1 and task("a")["status"] == "pending" and task("a")["attempts"] == 3, "a task cut off by a crash is released after 15 minutes")
db.ingest_queue.update_one({"key": "a"}, {"$set": {"status": "running", "started_at": datetime.now(UTC) - timedelta(minutes=2)}})
check(I.release_stuck(db) == 0, "...but one that is really running is left alone")

# 4. give up after MAX_ATTEMPTS and tell the admin
db.ingest_queue.update_one({"key": "a"}, {"$set": {"status": "pending", "attempts": I.MAX_ATTEMPTS - 1, "next_run_at": datetime.now(UTC) - timedelta(minutes=1)}})
I.ingest_match = flaky
res = I.process_queue(Client())
check(task("a")["status"] == "failed" and res["failed"] == 1, f"after {I.MAX_ATTEMPTS} tries the task is marked failed")
check(db.ingest_issues.find_one({"kind": "task_failed"}) is not None, "...and an ingest issue shows on the admin home")
I.ingest_match = real

# 5. Retry-After
check(_retry_after("3", 2) == 3.0, "Retry-After in seconds")
check(_retry_after("3600", 2) == 10.0, "a huge Retry-After is capped at 10 s (the job lock is not held for an hour)")
check(_retry_after("Wed, 21 Oct 2015 07:28:00 GMT", 2) == 0.0, "Retry-After as an HTTP date works (no crash)")
check(_retry_after("soon", 4) == 4.0 and _retry_after(None, 2) == 2.0, "odd or missing values fall back to the default")

print("\nALL QUEUE CHECKS PASSED")
