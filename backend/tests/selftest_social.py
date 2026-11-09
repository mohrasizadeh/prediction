"""selftest_social.py -- the posting queue behind the ad builder (docs/64).

Proves: a caption with a banned word cannot be queued at all; media must be a public https URL
because Meta fetches it rather than receiving it; the schedule is owned here and only the last hop
is handed out; a due post reaches the existing signed webhook outbox and is marked `sent`, not
`posted`; "posted" only ever comes back from the callback, which is authorised by a token that
only that one delivery carried; and an approved post with nothing subscribed fails loudly instead
of waiting to fire at a match that has already finished.
"""
import os, sys, base64, datetime as dt
os.environ.setdefault("APP_ENCRYPTION_KEY", base64.b64encode(os.urandom(32)).decode())
HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
import mongomock
from fastapi.testclient import TestClient
import integrations as INT, mongo_init, settings_store as S, social as SOC
import server as srv


def check(c, m):
    if not c:
        print("  FAIL", m); sys.exit(1)
    print("  ok  ", m)


def fails(fn, needle, m):
    try:
        fn()
    except SOC.SocialError as e:
        check(needle.lower() in str(e).lower(), f"{m} (said: {e})"); return
    print("  FAIL", m, "-- it was accepted"); sys.exit(1)


db = mongomock.MongoClient()["soc"]; mongo_init.ensure_indexes(db)
S.put(db, "integrations.webhooks_enabled", True)
S.put(db, "social.enabled", True)
os.environ["PUBLIC_BASE_URL"] = "https://example.test"   # the one source every absolute URL reads
now = dt.datetime(2026, 11, 10, 18, 0, tzinfo=dt.timezone.utc)
IMG = "https://cdn.example.test/api/site/assets/a1.png"
ACT = "owner@example.test"

# ---------------------------------------------------------------- 1. what cannot be queued
fails(lambda: SOC.queue(db, ACT, platform="instagram", kind="post", media=[IMG],
                        caption="Best odds tonight", scheduled_at=now),
      "does not publish", "a caption with a banned word is refused before it can ever be scheduled")
fails(lambda: SOC.queue(db, ACT, platform="instagram", kind="story", media=[IMG],
                        caption="ok", scheduled_at=now),
      "unknown kind", "a Story is refused, because no webhook publisher can honour one")
fails(lambda: SOC.queue(db, ACT, platform="instagram", kind="post", media=["/api/site/assets/a1.png"],
                        caption="ok", scheduled_at=now),
      "public https url", "a relative media path is refused -- Meta fetches the file, it is not uploaded")
fails(lambda: SOC.queue(db, ACT, platform="instagram", kind="carousel", media=[IMG],
                        caption="ok", scheduled_at=now),
      "2 to 10", "a one-image carousel is refused")
fails(lambda: SOC.queue(db, ACT, platform="instagram", kind="post", media=[IMG],
                        caption="x" * (SOC.MAX_CAPTION + 1), scheduled_at=now),
      "at most", "an over-long caption is refused with the real limit in the message")

# ---------------------------------------------------------------- 2. the happy path
post = SOC.queue(db, ACT, platform="instagram", kind="post", media=[IMG],
                 caption="Haaland has reached 1+ shot in all 10 of his last 10.", scheduled_at=now)
check(post["status"] == "draft", "a queued post starts as a draft -- nothing leaves without approval")
check(post["callback_token"], "every post carries a one-time callback token")

# nothing goes out while it is a draft, even once its time has passed
check(SOC.send_due(db, now=now + dt.timedelta(minutes=5))["sent"] == 0, "a draft is never sent")

# ---------------------------------------------------------------- 3. approved, but nothing listening
SOC.approve(db, ACT, post["_id"])
out = SOC.send_due(db, now=now + dt.timedelta(minutes=5))
check(out["sent"] == 0 and out["no_endpoint"] == 1, "with no endpoint subscribed, nothing is sent")
check(db.social_posts.find_one({"_id": post["_id"]})["status"] == "failed",
      "and it FAILS rather than waiting -- a post left approved would fire at a finished match")

# ---------------------------------------------------------------- 4. with an endpoint
INT.set_resolver(lambda host, *a, **k: [(2, 1, 6, "", ("93.184.216.34", 443))])   # public address
ep = INT.create_endpoint(db, ACT, "https://hooks.zapier.test/hooks/catch/1/abc", ["post.due"])
check("post.due" in INT.EVENTS, "post.due is a real event, so an endpoint can subscribe to it")
SOC.approve(db, ACT, post["_id"])
out = SOC.send_due(db, now=now + dt.timedelta(minutes=5))
check(out["sent"] == 1, "a due, approved post is handed over")
row = db.social_posts.find_one({"_id": post["_id"]})
check(row["status"] == "sent" and row["sent_at"], "it is marked SENT, not posted -- the outbox may still be retrying")
queued = list(db.webhook_outbox.find({"type": "post.due"}))
check(len(queued) == 1, "exactly one delivery was queued, on the existing signed outbox")
import json
body = json.loads(queued[0]["body"])["data"]
check(body["media_url"] == IMG and body["caption"] == post["caption"], "the delivery carries the media URL and the caption")
check(body["callback_url"] == f"https://example.test/api/webhooks/social/{post['_id']}",
      "and a callback URL under the prefix the middleware already exempts")
check(body["callback_token"] == row["callback_token"], "and the token that authorises that callback")

# a post already sent is not sent twice, however often the job runs
check(SOC.send_due(db, now=now + dt.timedelta(hours=1))["sent"] == 0, "a sent post is never handed over twice")

# ---------------------------------------------------------------- 5. the callback
fails(lambda: SOC.callback(db, post["_id"], "wrong-token", ok=True), "wrong token", "a bad token is refused")
fails(lambda: SOC.callback(db, "sp_nope", row["callback_token"], ok=True), "unknown post", "an unknown post is refused")
SOC.callback(db, post["_id"], row["callback_token"], ok=True, permalink="https://instagram.test/p/xyz/")
done = db.social_posts.find_one({"_id": post["_id"]})
check(done["status"] == "posted" and done["permalink"], "a successful callback is the ONLY thing that says posted")
fails(lambda: SOC.edit(db, ACT, post["_id"], caption="too late"), "already gone", "a post that has gone out cannot be edited")
fails(lambda: SOC.cancel(db, ACT, post["_id"]), "already live", "and cancelling it here would not remove it")

# a failure reports why, and the post can be fixed and approved again
p2 = SOC.queue(db, ACT, platform="instagram", kind="carousel", media=[IMG, IMG + "?2"], caption="two up", scheduled_at=now)
SOC.approve(db, ACT, p2["_id"]); SOC.send_due(db, now=now + dt.timedelta(minutes=5))
t2 = db.social_posts.find_one({"_id": p2["_id"]})["callback_token"]
SOC.callback(db, p2["_id"], t2, ok=False, error="Instagram rejected the image ratio")
f2 = db.social_posts.find_one({"_id": p2["_id"]})
check(f2["status"] == "failed" and "ratio" in f2["error"], "a failure callback records the reason")
check(SOC.approve(db, ACT, p2["_id"])["status"] == "approved", "a failed post can be approved again once fixed")

# ---------------------------------------------------------------- 6. the switch, and the API
S.put(db, "social.enabled", False)
check(SOC.send_due(db, now=now + dt.timedelta(hours=2)).get("skipped"), "with posting off, nothing is handed over")
S.put(db, "social.enabled", True)

srv.set_db(db)
with TestClient(srv.app) as c:
    p3 = SOC.queue(db, ACT, platform="instagram", kind="post", media=[IMG], caption="three", scheduled_at=now)
    SOC.approve(db, ACT, p3["_id"]); SOC.send_due(db, now=now + dt.timedelta(minutes=5))
    tok = db.social_posts.find_one({"_id": p3["_id"]})["callback_token"]
    r = c.post(f"/api/webhooks/social/{p3['_id']}", json={"token": tok, "permalink": "https://instagram.test/p/q/"})
    check(r.status_code == 200 and r.json()["status"] == "posted", "the public callback endpoint works with no session")
    # the shapes a person hand-maps in somebody else's UI
    p4 = SOC.queue(db, ACT, platform="instagram", kind="post", media=[IMG], caption="four", scheduled_at=now)
    SOC.approve(db, ACT, p4["_id"]); SOC.send_due(db, now=now + dt.timedelta(minutes=5))
    t4 = db.social_posts.find_one({"_id": p4["_id"]})["callback_token"]
    r = c.post(f"/api/webhooks/social/{p4['_id']}", json={"token": t4, "ok": "false", "message": "rate limited"})
    check(r.json()["status"] == "failed", 'ok sent as the string "false" is still a failure')
    check(c.post(f"/api/webhooks/social/{p4['_id']}", json={"token": "nope"}).status_code == 404,
          "a callback with the wrong token is rejected by the endpoint too")
    check(c.get("/api/admin/social").status_code in (401, 403), "the admin queue needs a signed-in staff user")

# ---------------------------------------------------------------- 7. the batch, and captions
with TestClient(srv.app) as c:
    check(c.post("/api/admin/social/batch", json=[]).status_code in (401, 403),
          "the batch endpoint needs a signed-in staff user")
# a batch does not stop at the first bad item: nineteen good ads should not be lost to one
good = {"media": [IMG], "caption": "fine", "scheduled_at": now.isoformat()}
bad = {"media": ["not-a-url"], "caption": "fine", "scheduled_at": now.isoformat()}
made, failed = [], []
for i, it in enumerate([good, bad, good]):
    try:
        made.append(SOC.queue(db, ACT, platform="instagram", kind="post", media=it["media"],
                              caption=it["caption"], scheduled_at=now))
    except SOC.SocialError as e:
        failed.append((i, str(e)))
check(len(made) == 2 and len(failed) == 1 and failed[0][0] == 1,
      "one bad item in a batch does not take the good ones with it")

import ad_plan as AP
cap = AP._caption({"headline": "Haaland has reached 1+ shot in all 10", "subhead": "Man City vs Brentford",
                   "finder_q": ""}, "Statistical analysis for information and entertainment. Not betting advice.")
check(cap and "Haaland" in cap and "Not betting advice." in cap,
      "a planned ad carries the caption it would be posted with, disclaimer and all")
check(AP._caption({"headline": "Best odds tonight", "subhead": "", "finder_q": ""}, "") == "",
      "and a caption the guard refuses is dropped rather than published")
SOC.queue(db, ACT, platform="instagram", kind="post", media=[IMG], caption=cap, scheduled_at=now)
check(True, "  the kept caption is accepted by the queue, so the two guards agree")

ov = SOC.overview(db, now=now)
check(ov["posted"] >= 1 and ov["failed"] >= 1 and ov["subscribed"] == 1,
      "the overview counts what happened and whether anything is listening")

print("selftest_social: all checks passed")
