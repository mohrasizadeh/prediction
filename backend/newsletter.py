"""newsletter.py -- e-mail list sign-ups (footer form, popups), with proof of consent.

Rules (Canada's CASL, and good practice anywhere):
  * Express consent: the person ticks or presses a button next to the exact consent text. We store that text, the time and the source.
  * Double opt-in by default (`newsletter.double_optin`): nothing is added to the list until the link in the confirmation e-mail is used.
  * One generic answer, whether the address is new, already on the list, or blocked. Nobody can probe the list.
  * Unsubscribe is one click and is synced to the audience provider.
  * Hard bounces and complaints (the suppression list) are never re-added.
"""
from __future__ import annotations

import re
import secrets
from datetime import datetime, timedelta, timezone

import accounts as A
import emailer as E
import settings_store as S


def utcnow():
    return datetime.now(timezone.utc)


def subscribe(db, email: str, *, source: str, consent_text: str, consent: bool, ip_hash: str | None = None,
              name: str | None = None, attrib: dict | None = None) -> str:
    """Returns 'pending', 'confirmed', 'already' or 'blocked'. The route shows the same message for all four."""
    if not consent:
        raise A.AuthError("CONSENT_REQUIRED", 400, "Please tick the box to say yes.")
    email = A.norm_email(email)
    if len(consent_text or "") < 10:
        raise A.AuthError("CONSENT_TEXT_MISSING", 400, "The sign-up form needs its consent sentence.")
    if E.is_suppressed(db, email, "marketing") in ("bounce", "complaint", "manual"):
        return "blocked"
    now = utcnow()
    row = db.newsletter.find_one({"email": email})
    if row and row.get("status") == "confirmed":
        return "already"
    double = bool(S.get(db, "newsletter.double_optin"))
    fields = {"status": "pending" if double else "confirmed", "source": source[:60], "consent_text": consent_text[:300], "consent_at": now,
              "ip_hash": ip_hash, "unsub_at": None, "confirmed_at": None if double else now}
    # docs/68: optional, and only ever used to address the e-mail. Kept out of `$setOnInsert` so a
    # reader who signs up again with their name filled in gets it recorded the second time.
    if (name or "").strip():
        fields["name"] = name.strip()[:80]
    # `attrib` is where the visit came from (analytics.attribution). On insert only: the FIRST
    # source that brought this person is the one that earned them, and a later visit from
    # somewhere else must not take the credit.
    ins = {"created_at": now, **({"attrib": attrib} if attrib else {})}
    db.newsletter.update_one({"email": email}, {"$set": fields, "$setOnInsert": ins}, upsert=True)
    # the e-mail address may also belong to an unsubscribed suppression; a fresh opt-in lifts only that kind
    sup = db.email_suppressions.find_one({"email": email})
    if sup and sup.get("reason") == "unsubscribe":
        db.email_suppressions.delete_one({"email": email})
    if double:
        raw = A.issue_token(db, None, "newsletter_confirm", timedelta(days=3), {"email": email})
        E.send_template(db, "newsletter_confirm", to=email, vars={"link": f"{E.base_url()}/newsletter/confirm?token={raw}"}, idem=f"nlc-{email}-{now:%Y%m%d%H%M}")
        return "pending"
    _confirmed_side_effects(db, email, source)
    return "confirmed"


def peek(db, token: str) -> dict | None:
    """Used by the confirm page so a mail scanner opening the link changes nothing."""
    t = A.peek_token(db, token, "newsletter_confirm")
    return {"email": E_mask(t["data"]["email"])} if t else None


def E_mask(e: str) -> str:
    n, d = e.split("@", 1)
    return n[:1] + "***@" + d


def confirm(db, token: str) -> bool:
    t = A.consume_token(db, token, "newsletter_confirm")
    if not t:
        return False
    email = t["data"]["email"]
    row = db.newsletter.find_one_and_update({"email": email, "status": "pending"}, {"$set": {"status": "confirmed", "confirmed_at": utcnow()}})
    if row:
        _confirmed_side_effects(db, email, row.get("source", ""))
    return True


def _confirmed_side_effects(db, email: str, source: str) -> None:
    try:
        import integrations as INT
        INT.queue_audience(db, "upsert", email)
        INT.emit(db, "newsletter.subscribed", {"source": source}, email=email)
    except Exception:                                       # a broken integration must never break a sign-up
        pass
    # docs/69: the waitlist page promises three forecasts every match day, so the first e-mail has
    # to say that back, now, rather than leaving the reader to wonder until the next fixture. It is
    # sent only for that source -- the footer form asked for something else -- and a failure here
    # is logged by the emailer, never raised: an e-mail that did not go out must not undo a
    # confirmed opt-in the reader has already seen succeed.
    if source == "waitlist":
        try:
            import waitlist_mail as WL
            row = db.newsletter.find_one({"email": email}, {"name": 1}) or {}
            WL.send_welcome(db, email, row.get("name") or "")
        except Exception:
            pass


def unsubscribed(db, email: str) -> None:
    """Called when someone unsubscribes by link (emailer.unsubscribe) or an admin removes them."""
    email = E.norm(email)
    r = db.newsletter.update_one({"email": email, "status": {"$ne": "unsubscribed"}}, {"$set": {"status": "unsubscribed", "unsub_at": utcnow()}})
    if r.modified_count:
        try:
            import integrations as INT
            INT.queue_audience(db, "unsubscribe", email)
            INT.emit(db, "newsletter.unsubscribed", {}, email=email)
        except Exception:
            pass


def counts(db) -> dict:
    return {s: db.newsletter.count_documents({"status": s}) for s in ("pending", "confirmed", "unsubscribed")}


def confirmed_emails(db):
    for r in db.newsletter.find({"status": "confirmed"}, {"email": 1}):
        yield r["email"]
