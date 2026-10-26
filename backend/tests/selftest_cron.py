"""Platform cron route: bearer secret, idempotent run id, 202 at once, tick started in the background."""
import sys, os
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE if os.path.basename(HERE) == "tests" else "/app/backend/tests")
sys.path.insert(0, HERE)
os.environ["WEBHOOK_CRON_SECRET"] = "cron-test-secret-0123456789abcdef"
from testkit import *
import routes_cron as RC

if not any(getattr(r, "path", "") == "/api/cron/tick" for r in srv.app.routes):
    srv.app.include_router(RC.router)

started = []
RC._start = lambda d: started.append(1)

with TestClient(srv.app) as c:
    good = {"Authorization": "Bearer cron-test-secret-0123456789abcdef"}
    env = {"event": "schedule.triggered", "schedule_id": "ingest-tick", "run_id": "r1", "data": None}
    check(c.post("/api/cron/tick", json=env).status_code == 401 and not started, "no auth: 401, nothing runs")
    check(c.post("/api/cron/tick", json=env, headers={"Authorization": "Bearer wrong"}).status_code == 401 and not started, "wrong secret: 401")
    r = c.post("/api/cron/tick", json=env, headers={**good, "X-Webhook-Id": "w1"})
    check(r.status_code == 202 and r.json()["accepted"] is True and len(started) == 1, "good call: 202 and the tick starts")
    r = c.post("/api/cron/tick", json=env, headers={**good, "X-Webhook-Id": "w1"})
    check(r.status_code == 202 and r.json().get("duplicate") is True and len(started) == 1, "same run id twice: acknowledged, runs once")
    check(c.post("/api/cron/tick", json=[1, 2], headers={**good, "X-Webhook-Id": "w2"}).status_code == 400, "bad body: 400")
    check(c.post("/api/cron/tick", headers=good).status_code == 202 and len(started) == 2, "no body still accepted")
    check(c.post("/api/cron/images/refresh").status_code == 401 and not db.job_requests.find_one({"job": "images"}), "images: no auth, nothing queued")
    check(c.post("/api/cron/images/other", headers=good).status_code == 400, "images: unknown mode is 400")
    r = c.post("/api/cron/images/refresh", json=env, headers={**good, "X-Webhook-Id": "i1"})
    q = db.job_requests.find_one({"job": "images", "requested_by": "cron"})
    check(r.status_code == 202 and q["refresh"] is True and q["status"] == "pending" and len(started) == 3, "images refresh: queued with squad re-read, tick starts")
    check(c.post("/api/cron/images/refresh", headers={**good, "X-Webhook-Id": "i1"}).json().get("duplicate") is True, "images: same run id runs once")
    c.post("/api/cron/images/continue", headers={**good, "X-Webhook-Id": "i2"})
    check(db.job_requests.count_documents({"job": "images", "refresh": False}) == 1, "images continue: queued without squad re-read")
print("cron self-test passed")
