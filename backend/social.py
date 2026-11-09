"""social.py -- the posting queue behind the ad builder (docs/64).

The app owns the schedule; something else does the last hop. That split is the whole design.

WHY NOT POST DIRECTLY TO INSTAGRAM. Publishing through Meta's own API needs an app that has been
through App Review for `instagram_business_content_publish`, and it needs this app to hold a
long-lived Meta token and refresh it forever. The first is weeks of waiting on someone else; the
second puts a credential that can post as the owner inside a repository that has already had
credentials committed to its history. Routing the last hop through an automation tool the owner
already has (Zapier, Make, n8n -- anything that can receive a webhook) removes both: THEY are the
reviewed app, and the token stays with them.

WHAT THAT COSTS, stated plainly rather than discovered later:
  * Instagram Stories cannot be published this way. Zapier's Instagram for Business app has
    Publish Photo(s) (single image or carousel) and Publish Video (which posts as a Reel). There
    is no Stories action, and Meta's own support for Stories publishing is disputed.
  * TikTok has no native posting action. Reaching it means a second tool inside the Zap, or
    TikTok's own Content Posting API -- which keeps posts private until TikTok audits the app.
  * The account must still be an Instagram professional account with rights on a linked Facebook
    Page. That prerequisite belongs to Meta and no tool removes it.

WHAT IT DOES NOT COST. The schedule, the queue, the approval, the retries and the record of what
happened all stay here. `integrations.emit` already signs each delivery, retries it on a backoff
of 1m / 5m / 30m / 2h / 12h for up to six attempts, refuses to resolve a private address, and logs
every attempt -- so a Zap that is down delays a post instead of losing it. Nothing in this module
re-implements any of that.

A post is NOT fire-and-forget. Every delivery carries a one-time callback URL, and the tool is
expected to call it back with the permalink or the error, so the screen can say what actually
happened rather than only what was sent.
"""
from __future__ import annotations

import re
import secrets
from datetime import datetime, timedelta, timezone

import integrations as INT
import settings_store as S
import site_studio as SS
import textguard as TG

# Kinds map onto the actions an automation tool actually offers. "story" is deliberately absent:
# see the module docstring. Adding it here without a publisher that can honour it would put a
# control on the screen that silently never fires.
KINDS = ("post", "carousel", "reel")
PLATFORMS = ("instagram",)
MAX_MEDIA = 10                 # Zapier's carousel action takes up to 10 image URLs
MAX_CAPTION = 2200             # Instagram's own cap
STATUSES = ("draft", "approved", "sent", "posted", "failed", "cancelled")
_URL = re.compile(r"^https://[^\s/$.?#].[^\s]*$", re.I)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class SocialError(ValueError):
    """A queue rule the caller broke. The message is shown to the admin, so it says what to fix."""


def _check_caption(caption: str) -> str:
    caption = (caption or "").strip()
    if len(caption) > MAX_CAPTION:
        raise SocialError(f"A caption can be at most {MAX_CAPTION} characters; this one is {len(caption)}.")
    # The one place a generated caption could reach the public with a word this product does not
    # use. The builder writes these from templates and a planner, so nobody reads every one.
    bad = TG.scan(caption)
    if bad:
        raise SocialError(f"The caption uses words this product does not publish: {', '.join(sorted(set(bad)))}.")
    return caption


def _check_media(kind: str, media: list[str]) -> list[str]:
    media = [m.strip() for m in (media or []) if m and m.strip()]
    if not media:
        raise SocialError("A post needs at least one image or video.")
    # Meta FETCHES the file from a URL -- it is never uploaded through the Zap. A relative path, a
    # localhost address or a signed link that expires before the scheduled time all fail at the far
    # end, hours later, where nobody is watching. They fail here instead.
    for m in media:
        if not _URL.match(m):
            raise SocialError(f"Media must be a public https URL that stays reachable until the post goes out; got {m!r}.")
    if kind in ("post", "reel") and len(media) != 1:
        raise SocialError(f"A {kind} takes exactly one file.")
    if kind == "carousel" and not (2 <= len(media) <= MAX_MEDIA):
        raise SocialError(f"A carousel takes 2 to {MAX_MEDIA} images.")
    return media


def queue(db, actor: str, *, platform: str, kind: str, media: list[str], caption: str,
          scheduled_at: datetime, design_id: str | None = None, note: str = "") -> dict:
    """Put one post in the queue as a draft. Nothing leaves the building until it is approved."""
    if platform not in PLATFORMS:
        raise SocialError(f"Unknown platform {platform!r}.")
    if kind not in KINDS:
        raise SocialError(f"Unknown kind {kind!r}. Stories cannot be published through a webhook; see docs/64.")
    if scheduled_at.tzinfo is None:
        scheduled_at = scheduled_at.replace(tzinfo=timezone.utc)
    doc = {"_id": "sp_" + secrets.token_hex(8), "platform": platform, "kind": kind,
           "media": _check_media(kind, media), "caption": _check_caption(caption),
           "scheduled_at": scheduled_at, "status": "draft", "design_id": design_id, "note": note,
           # one-time bearer for the callback: the tool proves which post it is reporting on
           # without this app having to trust anything else about the request.
           "callback_token": secrets.token_urlsafe(18),
           "event_id": None, "permalink": None, "error": None, "attempts": 0,
           "created_at": utcnow(), "created_by": actor,
           "approved_at": None, "approved_by": None, "sent_at": None, "posted_at": None}
    db.social_posts.insert_one(doc)
    db.audit_log.insert_one({"actor": actor, "action": "social.queue", "target": doc["_id"], "at": utcnow()})
    return doc


def _one(db, pid: str) -> dict:
    row = db.social_posts.find_one({"_id": pid})
    if not row:
        raise SocialError("That post is no longer in the queue.")
    return row


def approve(db, actor: str, pid: str) -> dict:
    row = _one(db, pid)
    if row["status"] not in ("draft", "failed"):
        raise SocialError(f"A post that is {row['status']} cannot be approved.")
    db.social_posts.update_one({"_id": pid}, {"$set": {"status": "approved", "approved_at": utcnow(),
                                                       "approved_by": actor, "error": None}})
    db.audit_log.insert_one({"actor": actor, "action": "social.approve", "target": pid, "at": utcnow()})
    return _one(db, pid)


def unapprove(db, actor: str, pid: str) -> dict:
    row = _one(db, pid)
    if row["status"] != "approved":
        raise SocialError("Only an approved post can be put back to a draft.")
    db.social_posts.update_one({"_id": pid}, {"$set": {"status": "draft", "approved_at": None, "approved_by": None}})
    db.audit_log.insert_one({"actor": actor, "action": "social.unapprove", "target": pid, "at": utcnow()})
    return _one(db, pid)


def edit(db, actor: str, pid: str, *, caption=None, scheduled_at=None, media=None) -> dict:
    """Change a post before it goes. A post that has been sent is history and cannot be edited:
    the tool may already have published it, and rewriting the row here would make this screen
    disagree with Instagram."""
    row = _one(db, pid)
    if row["status"] in ("sent", "posted"):
        raise SocialError("That post has already gone out.")
    set_ = {}
    if caption is not None:
        set_["caption"] = _check_caption(caption)
    if media is not None:
        set_["media"] = _check_media(row["kind"], media)
    if scheduled_at is not None:
        set_["scheduled_at"] = scheduled_at if scheduled_at.tzinfo else scheduled_at.replace(tzinfo=timezone.utc)
    if set_:
        db.social_posts.update_one({"_id": pid}, {"$set": set_})
        db.audit_log.insert_one({"actor": actor, "action": "social.edit", "target": pid, "at": utcnow()})
    return _one(db, pid)


def cancel(db, actor: str, pid: str) -> dict:
    row = _one(db, pid)
    if row["status"] == "posted":
        raise SocialError("That post is already live; cancelling it here would not remove it.")
    db.social_posts.update_one({"_id": pid}, {"$set": {"status": "cancelled"}})
    db.audit_log.insert_one({"actor": actor, "action": "social.cancel", "target": pid, "at": utcnow()})
    return _one(db, pid)


def send_due(db, now=None, limit: int = 20, base_url: str | None = None) -> dict:
    """Hand every approved post whose time has come to the webhook outbox. Called by jobs.tick.

    A post is marked `sent` the moment it is handed over, NOT when it is published: the outbox owns
    delivery from there and may still be retrying. `posted` only ever comes back from the callback,
    so the screen can distinguish "we asked" from "it is live" -- which is the distinction that
    matters when something has gone wrong.
    """
    now = now or utcnow()
    if not S.get(db, "social.enabled"):
        return {"sent": 0, "skipped": "social posting is off"}
    base = (base_url or SS.base_url()).rstrip("/")
    out = {"sent": 0, "no_endpoint": 0}
    q = {"status": "approved", "scheduled_at": {"$lte": now}}
    for row in list(db.social_posts.find(q).sort("scheduled_at", 1).limit(limit)):
        payload = {"post_id": row["_id"], "platform": row["platform"], "kind": row["kind"],
                   "caption": row["caption"], "media": row["media"],
                   "media_url": row["media"][0], "scheduled_at": row["scheduled_at"].isoformat(),
                   # the tool calls this back with the permalink, or with an error
                   "callback_url": f"{base}/api/webhooks/social/{row['_id']}" if base else None,
                   "callback_token": row["callback_token"]}
        n = INT.emit(db, "post.due", payload)
        if not n:
            # Nothing subscribed. Leaving it `approved` means it goes out the moment an endpoint is
            # added -- including, hours later, a post about a match that has already finished.
            out["no_endpoint"] += 1
            db.social_posts.update_one({"_id": row["_id"]}, {"$set": {
                "status": "failed", "error": "No webhook endpoint is subscribed to post.due."}})
            continue
        db.social_posts.update_one({"_id": row["_id"]}, {"$set": {"status": "sent", "sent_at": now},
                                                         "$inc": {"attempts": 1}})
        out["sent"] += 1
    return out


def callback(db, pid: str, token: str, *, ok: bool, permalink: str | None = None, error: str | None = None) -> dict:
    """What the tool reports back. Authorised by the per-post token, which only the delivery carried."""
    row = db.social_posts.find_one({"_id": pid})
    if not row or not token or not secrets.compare_digest(str(token), str(row.get("callback_token") or "")):
        raise SocialError("Unknown post or wrong token.")
    if ok:
        db.social_posts.update_one({"_id": pid}, {"$set": {"status": "posted", "posted_at": utcnow(),
                                                           "permalink": permalink, "error": None}})
    else:
        db.social_posts.update_one({"_id": pid}, {"$set": {"status": "failed", "error": (error or "")[:500]}})
    return db.social_posts.find_one({"_id": pid})


def listing(db, frm: datetime | None = None, to: datetime | None = None, limit: int = 200) -> list[dict]:
    q: dict = {}
    if frm or to:
        q["scheduled_at"] = {k: v for k, v in (("$gte", frm), ("$lte", to)) if v}
    rows = list(db.social_posts.find(q, {"callback_token": 0}).sort("scheduled_at", 1).limit(limit))
    return rows


def overview(db, now=None) -> dict:
    now = now or utcnow()
    c = db.social_posts.count_documents
    return {"enabled": bool(S.get(db, "social.enabled")),
            "subscribed": db.webhook_endpoints.count_documents({"active": True, "events": "post.due"}),
            "draft": c({"status": "draft"}), "approved": c({"status": "approved"}),
            "sent": c({"status": "sent"}), "posted": c({"status": "posted"}),
            "failed": c({"status": "failed"}),
            "due_next_24h": c({"status": "approved", "scheduled_at": {"$gte": now, "$lte": now + timedelta(hours=24)}}),
            "overdue": c({"status": "approved", "scheduled_at": {"$lt": now}})}
