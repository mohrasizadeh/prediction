"""emailer.py -- send e-mail through the chosen provider (Resend by default; see transports.py). Templates, log, suppression list, webhook, campaigns.

Rules:
  * we never store an e-mail body in the log (reset and verify e-mails carry secret links)
  * bounced and complained addresses are suppressed for everything; unsubscribed ones for non-essential mail
  * transactional mail (verify, reset, receipts, security notices) ignores opt-outs and the daily cap
  * a failed send never breaks the page the person is on: send_template returns a status, it does not raise
  * the Resend API key lives in provider_keys (admin > Keys), encrypted; env RESEND_API_KEY is the dev fallback

Resend facts used (from their public docs; check against your account before launch):
  POST https://api.resend.com/emails, header Authorization: Bearer <key>, optional Idempotency-Key.
  Webhooks are signed with Svix: headers svix-id, svix-timestamp, svix-signature.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import html as _html
import json
import os
import re
import time
from datetime import datetime, timedelta, timezone

import httpx
from pymongo.errors import DuplicateKeyError

import security
import settings_store as S
import site_studio as SS
import textguard
import transports as T

API = "https://api.resend.com"
_FACTORY = lambda: httpx.Client(timeout=15)
_SLEEP = time.sleep


def set_http_factory(f):          # tests inject httpx.MockTransport here
    global _FACTORY
    _FACTORY = f
    T.set_http_factory(f)


def set_sleep(f):
    global _SLEEP
    _SLEEP = f
    T.set_sleep(f)


def utcnow():
    return datetime.now(timezone.utc)


def base_url() -> str:
    return os.environ.get("PUBLIC_BASE_URL", "http://localhost:3000").rstrip("/")


ResendError = T.SendError               # one error type for every provider (kept under the old name)
Resend = T.Resend


def get_client(db):
    """The sender for the provider chosen in settings (email.provider), or None when its key is missing."""
    return T.get_client(db)


# ----------------------------------------------------------------------------- templates
# category: transactional (always sent) | product (respects the product_emails switch) | marketing (opt-in only)
DEFAULTS = {
    "verify_email": {"category": "transactional", "vars": ["name", "link", "hours"],
        "subject": "Confirm your e-mail for {{brand}}",
        "html": "<p>Hi {{name}},</p><p>Confirm your e-mail to finish setting up your account.</p><p><a href=\"{{link}}\" style=\"{{button}}\">Confirm e-mail</a></p><p>The link works for {{hours}} hours. If you did not sign up, ignore this e-mail.</p>",
        "text": "Hi {{name}},\n\nConfirm your e-mail to finish setting up your account:\n{{link}}\n\nThe link works for {{hours}} hours. If you did not sign up, ignore this e-mail."},
    "password_reset": {"category": "transactional", "vars": ["name", "link", "minutes"],
        "subject": "Reset your {{brand}} password",
        "html": "<p>Hi {{name}},</p><p>We got a request to reset your password.</p><p><a href=\"{{link}}\" style=\"{{button}}\">Choose a new password</a></p><p>The link works for {{minutes}} minutes and only once. If you did not ask for this, ignore this e-mail. Your password stays the same.</p>",
        "text": "Hi {{name}},\n\nWe got a request to reset your password:\n{{link}}\n\nThe link works for {{minutes}} minutes and only once. If you did not ask for this, ignore this e-mail."},
    "password_changed": {"category": "transactional", "vars": ["name"],
        "subject": "Your {{brand}} password was changed",
        "html": "<p>Hi {{name}},</p><p>Your password was just changed and we signed you out on your other devices.</p><p>If this was not you, reset your password now and contact {{support}}.</p>",
        "text": "Hi {{name}},\n\nYour password was just changed and we signed you out on your other devices.\nIf this was not you, reset your password now and contact {{support}}."},
    "email_change_confirm": {"category": "transactional", "vars": ["name", "link", "new_email"],
        "subject": "Confirm your new e-mail for {{brand}}",
        "html": "<p>Hi {{name}},</p><p>Confirm that {{new_email}} is your new e-mail.</p><p><a href=\"{{link}}\" style=\"{{button}}\">Confirm new e-mail</a></p>",
        "text": "Hi {{name}},\n\nConfirm that {{new_email}} is your new e-mail:\n{{link}}"},
    "email_changed": {"category": "transactional", "vars": ["name", "new_email"],
        "subject": "Your {{brand}} e-mail was changed",
        "html": "<p>Hi {{name}},</p><p>Your account e-mail was changed to {{new_email}}.</p><p>If this was not you, contact {{support}} right away.</p>",
        "text": "Hi {{name}},\n\nYour account e-mail was changed to {{new_email}}.\nIf this was not you, contact {{support}} right away."},
    "staff_invite": {"category": "transactional", "vars": ["name", "link", "role"],
        "subject": "You have been added to the {{brand}} team",
        "html": "<p>Hi,</p><p>You now have the {{role}} role on {{brand}}. Set your password to start. You will also set up two-factor sign-in.</p><p><a href=\"{{link}}\" style=\"{{button}}\">Set your password</a></p><p>The link works for 3 days.</p>",
        "text": "You now have the {{role}} role on {{brand}}. Set your password:\n{{link}}\nThe link works for 3 days."},
    "welcome": {"category": "product", "vars": ["name", "link"],
        "subject": "Welcome to {{brand}}",
        "html": "<p>Hi {{name}},</p><p>Your account is ready. Start with today's matches and the Finder.</p><p><a href=\"{{link}}\" style=\"{{button}}\">Open {{brand}}</a></p>",
        "text": "Hi {{name}},\n\nYour account is ready. Start with today's matches and the Finder:\n{{link}}"},
    "pro_welcome": {"category": "transactional", "vars": ["name", "plan", "date", "trial", "link"],
        "subject": "Welcome to {{brand}} {{plan}}",
        "html": "<p>Hi {{name}},</p><p>Your {{plan}} plan is active. {{trial}}Your first renewal date is <strong>{{date}}</strong>.</p><p>You now have unlimited Finder searches and every forecast detail.</p><p><a href=\"{{link}}\" style=\"{{button}}\">See your plan</a></p><p>You can change or cancel any time from your account.</p>",
        "text": "Hi {{name}},\n\nYour {{plan}} plan is active. {{trial}}Your first renewal date is {{date}}.\nYou now have unlimited Finder searches and every forecast detail.\nSee your plan: {{link}}\nYou can change or cancel any time from your account."},
    "receipt": {"category": "transactional", "vars": ["name", "amount", "plan", "period_end", "invoice_url"],
        "subject": "Your {{brand}} receipt: {{amount}}",
        "html": "<p>Hi {{name}},</p><p>Thanks. We received {{amount}} for {{plan}}. Your access runs to {{period_end}}.</p><p><a href=\"{{invoice_url}}\">View your invoice</a></p>",
        "text": "Hi {{name}},\n\nThanks. We received {{amount}} for {{plan}}. Your access runs to {{period_end}}.\nInvoice: {{invoice_url}}"},
    "payment_failed": {"category": "transactional", "vars": ["name", "plan", "link", "days"],
        "subject": "We could not take your payment",
        "html": "<p>Hi {{name}},</p><p>Your last payment for {{plan}} did not go through. You keep access for {{days}} more days while you fix it.</p><p><a href=\"{{link}}\" style=\"{{button}}\">Update payment method</a></p>",
        "text": "Hi {{name}},\n\nYour last payment for {{plan}} did not go through. You keep access for {{days}} more days.\nUpdate your payment method: {{link}}"},
    "subscription_canceled": {"category": "transactional", "vars": ["name", "plan", "period_end"],
        "subject": "Your {{brand}} subscription has ended",
        "html": "<p>Hi {{name}},</p><p>Your {{plan}} subscription has ended. You are back on the free plan. Your saved items are still here.</p>",
        "text": "Hi {{name}},\n\nYour {{plan}} subscription has ended. You are back on the free plan. Your saved items are still here."},
    "booking_alert": {"category": "product", "vars": ["name", "players", "link"],
        "subject": "Players you follow may be booked this round",
        "html": "<p>Hi {{name}},</p><p>These players you follow are among the most likely to get a yellow card in their next match:</p><p><strong>{{players}}</strong></p><p><a href=\"{{link}}\" style=\"{{button}}\">See the forecasts</a></p><p>These are statistical estimates, not certainties. You can turn alert e-mails off in your account.</p>",
        "text": "Hi {{name}},\n\nThese players you follow are among the most likely to get a yellow card in their next match:\n{{players}}\n\nSee the forecasts: {{link}}\nThese are statistical estimates, not certainties. You can turn alert e-mails off in your account."},
    "trial_ending": {"category": "transactional", "vars": ["name", "plan", "date", "link"],
        "subject": "Your free trial ends on {{date}}",
        "html": "<p>Hi {{name}},</p><p>Your free trial of {{plan}} ends on {{date}}. We will charge your card then unless you cancel.</p><p><a href=\"{{link}}\">Manage your plan</a></p>",
        "text": "Hi {{name}},\n\nYour free trial of {{plan}} ends on {{date}}. We will charge your card then unless you cancel.\nManage your plan: {{link}}"},
    "newsletter_confirm": {"category": "transactional", "vars": ["link"],
        "subject": "Confirm your sign-up for {{brand}}",
        "html": "<p>Hi,</p><p>Someone (we hope you) asked for the {{brand}} e-mail list. Press the button to say yes. If it was not you, do nothing and you will not hear from us.</p><p><a href=\"{{link}}\" style=\"{{button}}\">Yes, add me</a></p><p>The link works for 3 days.</p>",
        "text": "Someone (we hope you) asked for the {{brand}} e-mail list. To say yes, open:\n{{link}}\nIf it was not you, do nothing and you will not hear from us.\nThe link works for 3 days."},
    "admin_alert": {"category": "transactional", "vars": ["text", "link"],
        "subject": "Alert from {{brand}}: something needs a look",
        "html": "<p>{{text}}</p><p><a href=\"{{link}}\" style=\"{{button}}\">Open the admin</a></p><p>You get this because you are on the team. Change it under Account > Notifications.</p>",
        "text": "{{text}}\n\nOpen the admin: {{link}}\nYou get this because you are on the team. Change it under Account > Notifications."},
    "team_digest": {"category": "transactional", "vars": ["name", "summary", "link"],
        "subject": "{{brand}}: your weekly numbers",
        "html": "<p>Hi {{name}},</p><div style=\"white-space:pre-line\">{{summary}}</div><p><a href=\"{{link}}\" style=\"{{button}}\">Open the admin</a></p>",
        "text": "Hi {{name}},\n\n{{summary}}\n\nOpen the admin: {{link}}"},
    "account_deleted": {"category": "transactional", "vars": ["name"],
        "subject": "Your {{brand}} account was deleted",
        "html": "<p>Hi {{name}},</p><p>Your account and personal data were deleted. Payment records are kept as the law requires, without your name.</p>",
        "text": "Hi {{name}},\n\nYour account and personal data were deleted. Payment records are kept as the law requires, without your name."},
}
BUTTON = "display:inline-block;padding:10px 18px;background:#1f9d6b;color:#ffffff;text-decoration:none;border-radius:8px;font-weight:600"
_VAR = re.compile(r"\{\{\s*(\w+)\s*\}\}")
_BAD_HTML = re.compile(r"<\s*(script|iframe|object|embed|form)\b|\son\w+\s*=|javascript:", re.I)


def esc(v) -> str:
    return _html.escape(str(v if v is not None else ""), quote=True)


def render(tpl: str, vars: dict, escape: bool) -> str:
    return _VAR.sub(lambda m: (esc if escape else str)(vars.get(m.group(1), "")) if m.group(1) != "button" else BUTTON, tpl)


def get_template(db, key: str) -> dict:
    if key not in DEFAULTS:
        raise KeyError(f"unknown template: {key}")
    d = DEFAULTS[key]
    row = db.email_templates.find_one({"key": key}) or {}
    return {"key": key, "category": d["category"], "vars": d["vars"], "subject": row.get("subject", d["subject"]),
            "html": row.get("html", d["html"]), "text": row.get("text", d["text"]), "customised": bool(row)}


def save_template(db, key: str, subject: str, html: str, text: str, actor: str) -> dict:
    if key not in DEFAULTS:
        raise KeyError(key)
    if not (1 <= len(subject) <= 150) or "\n" in subject or "\r" in subject:
        raise ValueError("Subject: 1 to 150 characters, one line.")
    if len(html) > 20000 or len(text) > 20000:
        raise ValueError("Template is too long.")
    if _BAD_HTML.search(html):
        raise ValueError("Scripts, forms and event handlers are not allowed in e-mail.")
    textguard.require_clean("E-mail template", [subject, html, text])
    db.email_templates.update_one({"key": key}, {"$set": {"subject": subject, "html": html, "text": text, "updated_by": actor, "updated_at": utcnow()}}, upsert=True)
    db.audit_log.insert_one({"actor": actor, "action": "email.template.save", "target": key, "at": utcnow()})
    return get_template(db, key)


def reset_template(db, key: str, actor: str) -> None:
    db.email_templates.delete_one({"key": key})
    db.audit_log.insert_one({"actor": actor, "action": "email.template.reset", "target": key, "at": utcnow()})


def layout(db, body_html: str, category: str, unsub_url: str | None) -> str:
    brand = esc(SS.brand_name(db))
    foot = f"<p style=\"color:#6b7280;font-size:12px\">{brand}. Statistical analysis for information and entertainment. Not betting advice.</p>"
    if category != "transactional":
        addr = esc(S.get(db, "email.footer_address"))
        foot += f"<p style=\"color:#6b7280;font-size:12px\">{addr}</p>"
        if unsub_url:
            foot += f"<p style=\"color:#6b7280;font-size:12px\"><a href=\"{esc(unsub_url)}\">Unsubscribe</a></p>"
    return (f"<div style=\"font-family:Inter,Arial,sans-serif;max-width:560px;margin:0 auto;padding:24px;color:#111827\">"
            f"<p style=\"font-weight:700;font-size:18px\">{brand}</p>{body_html}<hr style=\"border:none;border-top:1px solid #e5e7eb\">{foot}</div>")


# ----------------------------------------------------------------------------- suppression and unsubscribe
def norm(e: str) -> str:
    return (e or "").strip().lower()


def to_hash(e: str) -> str:
    return hashlib.sha256(norm(e).encode()).hexdigest()[:24]


def suppress(db, email: str, reason: str, source: str = "") -> None:
    db.email_suppressions.update_one({"email": norm(email)}, {"$set": {"reason": reason, "source": source, "at": utcnow()}}, upsert=True)


def unsuppress(db, email: str, actor: str) -> None:
    db.email_suppressions.delete_one({"email": norm(email)})
    db.audit_log.insert_one({"actor": actor, "action": "email.unsuppress", "target": to_hash(email), "at": utcnow()})


def is_suppressed(db, email: str, category: str) -> str | None:
    row = db.email_suppressions.find_one({"email": norm(email)})
    if not row:
        return None
    if row["reason"] in ("bounce", "complaint", "manual"):
        return row["reason"]
    return row["reason"] if category != "transactional" else None      # unsubscribe only stops non-essential mail


def _unsub_key() -> bytes:
    return hashlib.sha256(base64.b64decode(os.environ["APP_ENCRYPTION_KEY"]) + b"|unsubscribe").digest()


def sign_unsub(email: str) -> str:
    p = base64.urlsafe_b64encode(norm(email).encode()).decode().rstrip("=")
    return p + "." + hmac.new(_unsub_key(), p.encode(), hashlib.sha256).hexdigest()[:32]


def read_unsub(token: str) -> str | None:
    try:
        p, sig = token.split(".", 1)
        if not hmac.compare_digest(sig, hmac.new(_unsub_key(), p.encode(), hashlib.sha256).hexdigest()[:32]):
            return None
        return base64.urlsafe_b64decode(p + "=" * (-len(p) % 4)).decode()
    except Exception:
        return None


def unsubscribe(db, token: str) -> bool:
    email = read_unsub(token)
    if not email:
        return False
    suppress(db, email, "unsubscribe", "link")
    db.users.update_one({"email": email}, {"$set": {"prefs.marketing_emails": False, "prefs.product_emails": False}})
    try:
        import newsletter
        newsletter.unsubscribed(db, email)
    except Exception:
        pass
    return True


# ----------------------------------------------------------------------------- sending
STATUS_RANK = {"queued": 0, "sent": 1, "delayed": 2, "delivered": 3, "failed": 4, "bounced": 5, "complained": 6}


def _sent_today(db) -> int:
    start = utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    return db.email_log.count_documents({"at": {"$gte": start}, "status": {"$in": ["sent", "delivered", "delayed"]}})


def _log(db, **kw) -> object:
    return db.email_log.insert_one({"at": utcnow(), "attempts": 0, **kw}).inserted_id


def _deliver(db, *, to, subject, html_body, text_body, category, template, user=None, campaign_id=None,
             idem=None, force=False, client=None) -> dict:
    to = norm(to)
    base = dict(template=template, category=category, to=to, to_hash=to_hash(to), user_id=user and user.get("id"),
                subject=subject[:200], campaign_id=campaign_id)

    def skip(status):
        return {"status": status, "id": str(_log(db, status=status, **base))}

    if not S.get(db, "email.enabled"):
        return skip("skipped_disabled")
    cl = client or get_client(db)
    from_addr = S.get(db, "email.from_address")
    if cl is None or (not from_addr and not isinstance(cl, T.Emergent)):
        return skip("skipped_unconfigured")
    if is_suppressed(db, to, category):
        return skip("skipped_suppressed")
    if not force and category != "transactional":
        prefs = (user or {}).get("prefs", {})
        if category == "marketing" and not prefs.get("marketing_emails", False):
            return skip("skipped_optout")
        if category == "product" and not prefs.get("product_emails", True):
            return skip("skipped_optout")
        if _sent_today(db) >= int(S.get(db, "email.daily_send_cap")):
            return skip("skipped_cap")
    unsub = f"{base_url()}/api/email/unsubscribe?t={sign_unsub(to)}" if category != "transactional" else None
    payload = {"from": f"{S.get(db, 'email.from_name')} <{from_addr or 'managed'}>", "to": [to], "subject": subject,
               "html": layout(db, html_body, category, unsub and f"{base_url()}/unsubscribe?t={sign_unsub(to)}"), "text": text_body,
               "tags": [{"name": "template", "value": re.sub(r"[^A-Za-z0-9_-]", "_", template)}]}
    if S.get(db, "email.reply_to"):
        payload["reply_to"] = S.get(db, "email.reply_to")
    if unsub:
        payload["headers"] = {"List-Unsubscribe": f"<{unsub}>", "List-Unsubscribe-Post": "List-Unsubscribe=One-Click"}
    if idem and db.email_log.find_one({"idem": idem, "status": {"$in": ["queued", "sent", "delayed", "delivered"]}}):
        return {"status": "duplicate"}                 # same message already sent: works for every provider, not only Resend
    log_id = _log(db, status="queued", **base, **({"idem": idem[:200]} if idem else {}))
    try:
        res = cl.send(payload, idem=idem)
        db.email_log.update_one({"_id": log_id}, {"$set": {"status": "sent", "provider_id": res.get("id")}, "$inc": {"attempts": 1}})
        return {"status": "sent", "id": str(log_id), "provider_id": res.get("id")}
    except ResendError as e:
        db.email_log.update_one({"_id": log_id}, {"$set": {"status": "failed", "error": f"{e.status} {e.name}: {e.message}"[:300]}, "$inc": {"attempts": 1}})
        return {"status": "failed", "id": str(log_id), "error": e.name or str(e.status)}
    except ValueError as e:
        db.email_log.update_one({"_id": log_id}, {"$set": {"status": "failed", "error": f"blocked: {e}"[:300]}, "$inc": {"attempts": 1}})
        return {"status": "failed", "id": str(log_id), "error": "blocked_by_safety_check"}


def send_template(db, key: str, *, to: str, user: dict | None = None, vars: dict | None = None,
                  idem: str | None = None, force: bool = False, client=None) -> dict:
    t = get_template(db, key)
    v = {"brand": SS.brand_name(db), "support": S.get(db, "site.support_email") or "support", "name": ((user or {}).get("display_name") or "there"), **(vars or {})}
    subject = render(t["subject"], v, escape=False).replace("\r", " ").replace("\n", " ").strip()
    return _deliver(db, to=to, subject=subject, html_body=render(t["html"], v, escape=True),
                    text_body=render(t["text"], v, escape=False), category=t["category"], template=key,
                    user=user, idem=idem, force=force, client=client)


def send_test(db, to: str, client=None) -> dict:
    """A plain test message through the chosen provider, so the owner sees it work (or the exact error). Logged like any other e-mail."""
    to = norm(to)
    brand = SS.brand_name(db)
    prov = T.PROVIDERS[T.get_provider(db)]["label"]
    return _deliver(db, to=to, subject=f"Test e-mail from {brand}", html_body=f"<p>This is a test from {esc(brand)}, sent through {esc(prov)}. If you can read it, sending works.</p>",
                    text_body=f"This is a test from {brand}, sent through {prov}. If you can read it, sending works.", category="transactional", template="test", force=True, client=client)


def preview(db, key: str, vars: dict | None = None) -> dict:
    t = get_template(db, key)
    sample = {"brand": SS.brand_name(db), "support": "support@example.com", "name": "Sam", "link": f"{base_url()}/example-link",
              "hours": "48", "minutes": "60", "new_email": "new@example.com", "role": "support", "amount": "CA$9.99", "plan": "Pro",
              "period_end": "2026-12-01", "invoice_url": f"{base_url()}/invoice", "days": "7", "date": "01 December 2026", "trial": "Your free trial runs until 01 December 2026. ", **(vars or {})}
    return {"subject": render(t["subject"], sample, False), "html": layout(db, render(t["html"], sample, True), t["category"], f"{base_url()}/unsubscribe-preview"),
            "text": render(t["text"], sample, False)}


# ----------------------------------------------------------------------------- Resend webhook
class WebhookError(Exception):
    pass


def verify_svix(payload: bytes, headers, secret: str, tolerance: int = 300, now: float | None = None) -> dict:
    try:
        mid, ts, sigs = headers["svix-id"], headers["svix-timestamp"], headers["svix-signature"]
        if abs((now or time.time()) - int(ts)) > tolerance:
            raise WebhookError("timestamp outside tolerance")
        key = base64.b64decode(secret.split("_", 1)[1] if secret.startswith("whsec_") else secret)
    except (KeyError, ValueError) as e:
        raise WebhookError("bad headers") from e
    expected = base64.b64encode(hmac.new(key, f"{mid}.{ts}.".encode() + payload, hashlib.sha256).digest()).decode()
    for part in sigs.split():
        ver, _, sig = part.partition(",")
        if ver == "v1" and hmac.compare_digest(sig, expected):
            return json.loads(payload)
    raise WebhookError("signature mismatch")


def handle_resend_event(db, event: dict, svix_id: str) -> str:
    """Idempotent. Returns 'duplicate', 'ignored' or 'processed'."""
    try:
        db.webhook_events.insert_one({"_id": f"resend:{svix_id}", "provider": "resend", "type": event.get("type"), "received_at": utcnow(), "status": "processing"})
    except DuplicateKeyError:
        return "duplicate"
    typ, data = event.get("type", ""), event.get("data", {}) or {}
    status = {"email.delivered": "delivered", "email.bounced": "bounced", "email.complained": "complained", "email.delivery_delayed": "delayed"}.get(typ)
    out = "ignored"
    if status:
        pid = data.get("email_id")
        row = db.email_log.find_one({"provider_id": pid}) if pid else None
        if row and STATUS_RANK.get(status, 0) > STATUS_RANK.get(row["status"], 0):
            db.email_log.update_one({"_id": row["_id"]}, {"$set": {"status": status}})
        if status in ("bounced", "complained"):
            kind = str((data.get("bounce") or {}).get("type", "")).lower()
            if status == "complained" or not any(w in kind for w in ("transient", "temporary", "soft")):
                for addr in data.get("to", []) or []:
                    suppress(db, addr, "bounce" if status == "bounced" else "complaint", "resend_webhook")
        out = "processed"
    db.webhook_events.update_one({"_id": f"resend:{svix_id}"}, {"$set": {"status": "processed", "result": out}})
    return out


# ----------------------------------------------------------------------------- campaigns
SEGMENTS = ("all", "free", "paid", "newsletter", "everyone")


def _list_member(email: str) -> dict:
    """A newsletter subscriber who has no account. They said yes on a sign-up form; the proof is in the newsletter collection."""
    return {"id": "nl-" + to_hash(email), "email": email, "display_name": "", "prefs": {"marketing_emails": True, "product_emails": False}}


def segment_users(db, segment: str):
    import plans
    seen = set()
    if segment in ("all", "free", "paid", "everyone"):
        q = {"email_verified": True, "disabled": {"$ne": True}, "prefs.marketing_emails": True, "role": {"$exists": True}}
        for u in db.users.find(q):
            if segment in ("all", "everyone"):
                seen.add(norm(u["email"]))
                yield u
            else:
                paid = plans.effective_plan(db, u)["source"] in ("subscription", "comp")
                if (segment == "paid") == paid:
                    yield u
    if segment in ("newsletter", "everyone"):
        for r in db.newsletter.find({"status": "confirmed"}, {"email": 1}):
            if r["email"] not in seen:
                yield _list_member(r["email"])


def create_campaign(db, subject: str, html: str, segment: str, actor: str) -> str:
    if segment not in SEGMENTS:
        raise ValueError("Segment: all, free, paid, newsletter or everyone.")
    if not (1 <= len(subject) <= 150) or _BAD_HTML.search(html) or len(html) > 50000:
        raise ValueError("Subject 1 to 150 characters; no scripts in the body.")
    textguard.require_clean("Campaign", [subject, html])
    cid = db.email_campaigns.insert_one({"subject": subject, "html": html, "segment": segment, "status": "draft", "created_by": actor,
                                         "created_at": utcnow(), "sent": 0, "skipped": 0, "failed": 0}).inserted_id
    return str(cid)


def send_campaign(db, campaign_id: str, actor: str, client=None) -> dict:
    from bson import ObjectId
    c = db.email_campaigns.find_one({"_id": ObjectId(campaign_id)})
    if not c:
        raise ValueError("No such campaign.")
    if T.get_provider(db) == "emergent":
        raise ValueError("Campaigns can't go through the managed e-mail service, which is for account and payment e-mails only. Connect your own e-mail provider under Integrations to send campaigns.")
    if not S.get(db, "email.enabled") or not S.get(db, "email.marketing_enabled"):
        raise ValueError("Turn on e-mail and marketing e-mail in settings first.")
    if not S.get(db, "email.footer_address").strip():
        raise ValueError("Marketing e-mail needs a postal address in the footer (settings > Email).")
    room = int(S.get(db, "email.daily_send_cap")) - _sent_today(db)
    done = {r["to_hash"] for r in db.email_log.find({"campaign_id": campaign_id}, {"to_hash": 1})}
    sent = failed = skipped = left = 0
    for u in segment_users(db, c["segment"]):
        if to_hash(u["email"]) in done:
            continue
        if room <= 0:
            left += 1
            continue
        v = {"brand": SS.brand_name(db), "name": u.get("display_name") or "there"}
        r = _deliver(db, to=u["email"], subject=render(c["subject"], v, False), html_body=render(c["html"], v, True),
                     text_body=re.sub(r"<[^>]+>", "", render(c["html"], v, False)), category="marketing", template="campaign",
                     user=u, campaign_id=campaign_id, idem=f"camp-{campaign_id}-{u['id']}", client=client)
        if r["status"] == "sent":
            sent += 1; room -= 1
        elif r["status"] == "failed":
            failed += 1
        else:
            skipped += 1
    status = "partial" if left else "sent"
    db.email_campaigns.update_one({"_id": c["_id"]}, {"$set": {"status": status, "last_sent_at": utcnow()}, "$inc": {"sent": sent, "failed": failed, "skipped": skipped}})
    db.audit_log.insert_one({"actor": actor, "action": "email.campaign.send", "target": campaign_id, "detail": {"sent": sent, "left": left}, "at": utcnow()})
    return {"sent": sent, "failed": failed, "skipped": skipped, "left_for_tomorrow": left, "status": status}
