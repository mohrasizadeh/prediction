"""integrations.py -- connect the app to the tools a marketer already uses.

  1. Audience sync   Confirmed newsletter sign-ups are copied to Mailchimp, Brevo or MailerLite (and removed when they unsubscribe).
  2. Outbound webhooks  Signed events to any URL (Zapier, Make, n8n, a Slack relay): sign-ups, subscriptions, payments, list joins.
  3. Tracking tags   GA4, Meta pixel, Google Ads ids. OFF by default, owner only, and the browser loads them only after consent.
  4. E-mail sending  The provider itself is chosen in settings (see transports.py); this file reports its status.

Everything is queued and retried by `tick()` (every 5 to 10 minutes), so a slow third party never slows a page and a down
third party never loses an event. Secrets are encrypted at rest and never returned after they are saved.

Not yet run against live accounts: the Mailchimp, Brevo and MailerLite request shapes are from their public docs.
"""
from __future__ import annotations

import hashlib
import hmac
import ipaddress
import json
import secrets
import socket
import time
from datetime import datetime, timedelta, timezone
from urllib.parse import quote, urlparse

import httpx

import security
import settings_store as S
import transports as T

EVENTS = ("user.signed_up", "user.verified", "subscription.started", "subscription.canceled", "payment.succeeded", "payment.failed",
          "newsletter.subscribed", "newsletter.unsubscribed", "popup.submitted", "contact.received")
BACKOFF = [timedelta(minutes=1), timedelta(minutes=5), timedelta(minutes=30), timedelta(hours=2), timedelta(hours=12)]
MAX_ENDPOINTS = 10
MAX_ATTEMPTS = 6

AUDIENCE = {
    "mailchimp": {"label": "Mailchimp", "key": "mailchimp", "env": "MAILCHIMP_API_KEY", "re": r"^[a-f0-9]{32}-[a-z]{2,4}\d{1,3}$", "hint": "looks like 32 letters and numbers, a dash, then us21"},
    "brevo": {"label": "Brevo", "key": "brevo", "env": "BREVO_API_KEY", "re": r"^xkeysib-[A-Za-z0-9\-]{20,}$", "hint": "starts with xkeysib-"},
    "mailerlite": {"label": "MailerLite", "key": "mailerlite", "env": "MAILERLITE_API_KEY", "re": r"^[A-Za-z0-9._\-]{30,2000}$", "hint": "is the API token from MailerLite > Integrations"},
}

_RESOLVE = socket.getaddrinfo        # tests replace this


def set_resolver(f):
    global _RESOLVE
    _RESOLVE = f
    T._RESOLVE = f                   # the SMTP host check uses the same resolver


def utcnow():
    return datetime.now(timezone.utc)


# ----------------------------------------------------------------------------- audience sync
def audience_provider(db) -> str:
    p = S.get(db, "integrations.audience_provider")
    return p if p in AUDIENCE else "none"


def queue_audience(db, action: str, email: str) -> bool:
    """action: 'upsert' or 'unsubscribe'. Returns False when no audience provider is chosen."""
    p = audience_provider(db)
    if p == "none" or action not in ("upsert", "unsubscribe"):
        return False
    email = email.strip().lower()
    if db.integration_jobs.find_one({"kind": "audience", "email": email, "action": action, "status": "pending"}):
        return True
    now = utcnow()
    db.integration_jobs.insert_one({"kind": "audience", "provider": p, "action": action, "email": email, "status": "pending", "attempts": 0,
                                    "next_at": now, "created_at": now, "expires_at": now + timedelta(days=30)})
    return True


def _key(db, p: str) -> str | None:
    spec = AUDIENCE[p]
    return security.get_provider_key(db, spec["key"], spec["env"])


def _call(method: str, url: str, headers: dict, body: dict | None = None, auth=None) -> httpx.Response:
    try:
        with T._FACTORY() as c:
            return c.request(method, url, headers=headers, json=body, auth=auth)
    except httpx.HTTPError as e:
        raise T.SendError(0, "network", type(e).__name__)


def _check(r: httpx.Response, ok=(200, 201, 202, 204)) -> None:
    if r.status_code in ok:
        return
    try:
        j = r.json()
        msg = j.get("detail") or j.get("message") or j.get("title") or ""
    except Exception:
        msg = ""
    raise T.SendError(r.status_code, "audience", str(msg)[:160])


def _apply(db, p: str, action: str, email: str) -> None:
    key, lst = _key(db, p), str(S.get(db, "integrations.audience_list_id") or "").strip()
    if not key:
        raise T.SendError(401, "no_key", "No API key saved for " + AUDIENCE[p]["label"])
    if not lst:
        raise T.SendError(400, "no_list", "No list or audience id is set")
    if p == "mailchimp":
        dc = key.rsplit("-", 1)[1]
        h = hashlib.md5(email.encode()).hexdigest()
        body = {"email_address": email, "status_if_new": "subscribed", "status": "subscribed" if action == "upsert" else "unsubscribed"}
        if action == "unsubscribe":
            body.pop("status_if_new")
        _check(_call("PUT", f"https://{dc}.api.mailchimp.com/3.0/lists/{lst}/members/{h}", {"Content-Type": "application/json"}, body, auth=("forecast", key)))
    elif p == "brevo":
        hd = {"api-key": key, "Accept": "application/json", "Content-Type": "application/json"}
        if action == "upsert":
            _check(_call("POST", "https://api.brevo.com/v3/contacts", hd, {"email": email, "listIds": [int(lst)], "updateEnabled": True}))
        else:
            _check(_call("PUT", f"https://api.brevo.com/v3/contacts/{quote(email, safe='')}", hd, {"emailBlacklisted": True}))
    else:
        hd = {"Authorization": f"Bearer {key}", "Accept": "application/json", "Content-Type": "application/json"}
        body = {"email": email, "groups": [lst]} if action == "upsert" else {"email": email, "status": "unsubscribed"}
        _check(_call("POST", "https://connect.mailerlite.com/api/subscribers", hd, body))


def test_audience(db, p: str | None = None) -> dict:
    p = p or audience_provider(db)
    if p not in AUDIENCE:
        return {"ok": False, "code": "none_selected"}
    key, lst = _key(db, p), str(S.get(db, "integrations.audience_list_id") or "").strip()
    if not key:
        return {"ok": False, "code": "no_key"}
    try:
        if p == "mailchimp":
            r = _call("GET", f"https://{key.rsplit('-', 1)[1]}.api.mailchimp.com/3.0/lists/{lst or 'x'}?fields=id,name", {}, auth=("forecast", key))
        elif p == "brevo":
            r = _call("GET", "https://api.brevo.com/v3/account", {"api-key": key, "Accept": "application/json"})
        else:
            r = _call("GET", "https://connect.mailerlite.com/api/groups?limit=1", {"Authorization": f"Bearer {key}", "Accept": "application/json"})
    except T.SendError as e:
        return {"ok": False, "code": e.name, "message": e.message}
    if r.status_code == 200:
        return {"ok": True, "list_set": bool(lst)}
    return {"ok": False, "code": r.status_code}


def backfill_audience(db) -> int:
    n = 0
    for r in db.newsletter.find({"status": "confirmed"}, {"email": 1}):
        n += 1 if queue_audience(db, "upsert", r["email"]) else 0
    return n


def process_audience(db, limit: int = 50, now=None) -> dict:
    now = now or utcnow()
    done = failed = dead = 0
    for j in db.integration_jobs.find({"kind": "audience", "status": "pending", "next_at": {"$lte": now}}).sort("next_at", 1).limit(limit):
        try:
            _apply(db, j["provider"], j["action"], j["email"])
            db.integration_jobs.update_one({"_id": j["_id"]}, {"$set": {"status": "done", "done_at": now}, "$inc": {"attempts": 1}})
            done += 1
        except T.SendError as e:
            n = j["attempts"] + 1
            permanent = e.status in (400, 401, 403, 404, 422) and e.name != "network"
            if permanent or n >= MAX_ATTEMPTS:
                db.integration_jobs.update_one({"_id": j["_id"]}, {"$set": {"status": "dead", "error": f"{e.status} {e.message}"[:200]}, "$inc": {"attempts": 1}})
                dead += 1
                alert(db, f"audience:{j['provider']}", f"{AUDIENCE[j['provider']]['label']} refused a contact: {e.status} {e.message}"[:200])
            else:
                db.integration_jobs.update_one({"_id": j["_id"]}, {"$set": {"next_at": now + BACKOFF[min(n - 1, len(BACKOFF) - 1)], "error": f"{e.status} {e.message}"[:200]}, "$inc": {"attempts": 1}})
                failed += 1
    return {"done": done, "retry": failed, "dead": dead}


def alert(db, key: str, text: str) -> None:
    """One open alert per key. Shown in Admin > Health; alerts.py e-mails the team."""
    db.admin_alerts.update_one({"key": key, "resolved": False}, {"$set": {"text": text, "at": utcnow()}, "$setOnInsert": {"notified": False, "created_at": utcnow()}}, upsert=True)


# ----------------------------------------------------------------------------- outbound webhooks
def check_url(url: str) -> str:
    """Only public https addresses. Blocks private, loopback, link-local and cloud-metadata ranges, so a webhook cannot be used to probe our own network."""
    u = urlparse(url)
    if u.scheme != "https" or not u.hostname or u.username or u.password:
        raise ValueError("The address must start with https:// and have no user name or password.")
    if u.port not in (None, 443, 8443):
        raise ValueError("Use the standard https port (443 or 8443).")
    if len(url) > 500:
        raise ValueError("The address is too long.")
    host = u.hostname
    try:
        literal = ipaddress.ip_address(host)                      # an address typed in directly: check it, never resolve it
    except ValueError:
        literal = None
    if literal is not None:
        addrs = [literal]
    else:
        try:
            infos = _RESOLVE(host, u.port or 443, proto=socket.IPPROTO_TCP)
        except OSError:
            raise ValueError("That host name does not resolve.")
        addrs = [ipaddress.ip_address(info[4][0]) for info in infos]
    for ip in addrs:
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast or ip.is_unspecified:
            raise ValueError("That address points to a private network. Use a public address.")
    return url


def sign(secret: str, body: str, ts: int | None = None) -> str:
    ts = ts or int(time.time())
    return f"t={ts},v1=" + hmac.new(secret.encode(), f"{ts}.{body}".encode(), hashlib.sha256).hexdigest()


def _view(ep: dict) -> dict:
    return {"id": ep["_id"], "url": ep["url"], "events": ep["events"], "active": ep["active"], "include_email": ep["include_email"], "note": ep.get("note", ""),
            "secret_last4": ep.get("secret_last4"), "fail_streak": ep.get("fail_streak", 0), "last_status": ep.get("last_status"),
            "last_at": ep.get("last_at"), "created_at": ep.get("created_at")}


def list_endpoints(db) -> list[dict]:
    return [_view(e) for e in db.webhook_endpoints.find({}).sort("created_at", -1)]


def _clean_events(events) -> list[str]:
    if not isinstance(events, list) or not events or any(e not in EVENTS for e in events):
        raise ValueError("Pick at least one event from the list.")
    return sorted(set(events))


def create_endpoint(db, actor: str, url: str, events: list[str], include_email: bool = False, note: str = "") -> dict:
    if db.webhook_endpoints.count_documents({}) >= MAX_ENDPOINTS:
        raise ValueError("You have 10 endpoints. Delete one first.")
    check_url(url)
    events = _clean_events(events)
    secret = "whsec_" + secrets.token_urlsafe(24)
    eid = "ep_" + secrets.token_hex(6)
    db.webhook_endpoints.insert_one({"_id": eid, "url": url, "events": events, "active": True, "include_email": bool(include_email), "note": (note or "")[:120],
                                     "secret": security.encrypt_secret(secret), "secret_last4": secret[-4:], "fail_streak": 0, "created_at": utcnow(), "created_by": actor})
    db.audit_log.insert_one({"actor": actor, "action": "webhook.create", "target": eid, "detail": {"url_host": urlparse(url).hostname, "events": events}, "at": utcnow()})
    return {**_view(db.webhook_endpoints.find_one({"_id": eid})), "secret": secret}          # the only time the secret is shown


def update_endpoint(db, actor: str, eid: str, *, url=None, events=None, active=None, include_email=None, note=None) -> dict:
    ep = db.webhook_endpoints.find_one({"_id": eid})
    if not ep:
        raise KeyError("No such endpoint.")
    upd = {}
    if url is not None: upd["url"] = check_url(url)
    if events is not None: upd["events"] = _clean_events(events)
    if active is not None:
        upd["active"] = bool(active)
        if active: upd["fail_streak"] = 0
    if include_email is not None: upd["include_email"] = bool(include_email)
    if note is not None: upd["note"] = note[:120]
    if upd:
        db.webhook_endpoints.update_one({"_id": eid}, {"$set": upd})
    db.audit_log.insert_one({"actor": actor, "action": "webhook.update", "target": eid, "detail": {k: v for k, v in upd.items() if k != "url"}, "at": utcnow()})
    return _view(db.webhook_endpoints.find_one({"_id": eid}))


def rotate_secret(db, actor: str, eid: str) -> dict:
    if not db.webhook_endpoints.find_one({"_id": eid}):
        raise KeyError("No such endpoint.")
    secret = "whsec_" + secrets.token_urlsafe(24)
    db.webhook_endpoints.update_one({"_id": eid}, {"$set": {"secret": security.encrypt_secret(secret), "secret_last4": secret[-4:]}})
    db.audit_log.insert_one({"actor": actor, "action": "webhook.rotate", "target": eid, "at": utcnow()})
    return {"id": eid, "secret": secret}


def delete_endpoint(db, actor: str, eid: str) -> None:
    db.webhook_endpoints.delete_one({"_id": eid})
    db.webhook_outbox.delete_many({"endpoint_id": eid, "status": "pending"})
    db.audit_log.insert_one({"actor": actor, "action": "webhook.delete", "target": eid, "at": utcnow()})


def emit(db, type_: str, data: dict | None = None, *, email: str | None = None, user_id: str | None = None) -> int:
    """Queue one event for every active endpoint that subscribed to it. Never raises into the caller's flow."""
    if type_ not in EVENTS or not S.get(db, "integrations.webhooks_enabled"):
        return 0
    n, evt = 0, "evt_" + secrets.token_hex(8)
    now = utcnow()
    for ep in db.webhook_endpoints.find({"active": True, "events": type_}):
        payload = {"id": evt, "type": type_, "created": now.isoformat(), "data": {**(data or {})}}
        if user_id:
            payload["data"]["user_id"] = user_id
        if email and ep.get("include_email"):
            payload["data"]["email"] = email
        db.webhook_outbox.insert_one({"_id": f"{evt}:{ep['_id']}", "endpoint_id": ep["_id"], "type": type_, "event_id": evt, "body": json.dumps(payload, separators=(",", ":"), default=str),
                                      "status": "pending", "attempts": 0, "next_at": now, "created_at": now, "expires_at": now + timedelta(days=14)})
        n += 1
    return n


def _deliver_one(db, row: dict, ep: dict, now) -> tuple[bool, int, str]:
    try:
        check_url(ep["url"])                                              # again at send time, in case DNS changed
        secret = security.decrypt_secret(ep["secret"])
        sig = sign(secret, row["body"])
        h = {"Content-Type": "application/json", "User-Agent": "forecast-webhooks/1.0", "X-Webhook-Id": row["event_id"], "X-Webhook-Event": row["type"], "X-Webhook-Signature": sig}
        t0 = time.monotonic()
        with T._FACTORY() as c:
            r = c.post(ep["url"], content=row["body"], headers=h, follow_redirects=False)
        ms = int((time.monotonic() - t0) * 1000)
        return 200 <= r.status_code < 300, r.status_code, f"{ms} ms"
    except ValueError as e:
        return False, 0, str(e)[:120]
    except httpx.HTTPError as e:
        return False, 0, type(e).__name__


def deliver_pending(db, limit: int = 50, now=None) -> dict:
    now = now or utcnow()
    ok_n = retry = dead = 0
    for row in db.webhook_outbox.find({"status": "pending", "next_at": {"$lte": now}}).sort("next_at", 1).limit(limit):
        ep = db.webhook_endpoints.find_one({"_id": row["endpoint_id"]})
        if not ep or not ep["active"]:
            db.webhook_outbox.update_one({"_id": row["_id"]}, {"$set": {"status": "dead", "error": "endpoint off or deleted"}})
            dead += 1
            continue
        ok, code, info = _deliver_one(db, row, ep, now)
        attempt = row["attempts"] + 1
        db.webhook_deliveries.insert_one({"endpoint_id": ep["_id"], "event_id": row["event_id"], "type": row["type"], "attempt": attempt, "ok": ok, "status": code,
                                          "info": info, "at": now, "expires_at": now + timedelta(days=30)})
        if ok:
            db.webhook_outbox.update_one({"_id": row["_id"]}, {"$set": {"status": "done", "done_at": now}, "$inc": {"attempts": 1}})
            db.webhook_endpoints.update_one({"_id": ep["_id"]}, {"$set": {"fail_streak": 0, "last_status": code, "last_at": now}})
            ok_n += 1
            continue
        streak = ep.get("fail_streak", 0) + 1
        upd = {"fail_streak": streak, "last_status": code, "last_at": now}
        if code == 410:
            upd["active"] = False
        if streak >= 20:
            upd["active"] = False
            alert(db, f"webhook:{ep['_id']}", f"Endpoint {urlparse(ep['url']).hostname} failed 20 times in a row and was switched off.")
        db.webhook_endpoints.update_one({"_id": ep["_id"]}, {"$set": upd})
        if code == 410 or attempt >= MAX_ATTEMPTS:
            db.webhook_outbox.update_one({"_id": row["_id"]}, {"$set": {"status": "dead", "error": f"{code} {info}"[:150]}, "$inc": {"attempts": 1}})
            dead += 1
        else:
            db.webhook_outbox.update_one({"_id": row["_id"]}, {"$set": {"next_at": now + BACKOFF[min(attempt - 1, len(BACKOFF) - 1)]}, "$inc": {"attempts": 1}})
            retry += 1
    return {"delivered": ok_n, "retry": retry, "dead": dead}


def send_test(db, actor: str, eid: str) -> dict:
    """Synchronous test delivery of a sample event, so the owner sees the answer straight away."""
    ep = db.webhook_endpoints.find_one({"_id": eid})
    if not ep:
        raise KeyError("No such endpoint.")
    now = utcnow()
    body = json.dumps({"id": "evt_test", "type": "webhook.test", "created": now.isoformat(), "data": {"hello": "from your app"}}, separators=(",", ":"))
    ok, code, info = _deliver_one(db, {"body": body, "event_id": "evt_test", "type": "webhook.test"}, ep, now)
    db.webhook_deliveries.insert_one({"endpoint_id": eid, "event_id": "evt_test", "type": "webhook.test", "attempt": 1, "ok": ok, "status": code, "info": info, "at": now, "expires_at": now + timedelta(days=30)})
    db.audit_log.insert_one({"actor": actor, "action": "webhook.test", "target": eid, "at": now})
    return {"ok": ok, "status": code, "info": info}


def deliveries(db, eid: str | None = None, limit: int = 50) -> list[dict]:
    q = {"endpoint_id": eid} if eid else {}
    return [{k: v for k, v in r.items() if k not in ("_id", "expires_at")} for r in db.webhook_deliveries.find(q).sort("at", -1).limit(limit)]


# ----------------------------------------------------------------------------- tracking tags
def csp_additions(db) -> dict:
    """Extra Content-Security-Policy sources the tracking tags need. Empty when tracking is off."""
    if not S.get(db, "tracking.enabled"):
        return {}
    add: dict[str, list[str]] = {"script-src": [], "connect-src": [], "img-src": []}
    if S.get(db, "tracking.ga4_id") or S.get(db, "tracking.google_ads_id"):
        add["script-src"] += ["https://www.googletagmanager.com"]
        add["connect-src"] += ["https://www.google-analytics.com", "https://*.google-analytics.com", "https://*.analytics.google.com", "https://www.googletagmanager.com"]
        add["img-src"] += ["https://www.google-analytics.com", "https://www.googletagmanager.com"]
    if S.get(db, "tracking.meta_pixel_id"):
        add["script-src"] += ["https://connect.facebook.net"]
        add["connect-src"] += ["https://www.facebook.com"]
        add["img-src"] += ["https://www.facebook.com"]
    return {k: sorted(set(v)) for k, v in add.items() if v}


# ----------------------------------------------------------------------------- the status page
def overview(db) -> dict:
    prov = T.get_provider(db)
    spec = T.PROVIDERS[prov]
    ap = audience_provider(db)
    jobs = {s: db.integration_jobs.count_documents({"kind": "audience", "status": s}) for s in ("pending", "done", "dead")}
    return {
        "email": {"provider": prov, "label": spec["label"], "key_set": bool(security.get_provider_key(db, spec["key"], spec["env"])),
                  "enabled": bool(S.get(db, "email.enabled")), "from_address": S.get(db, "email.from_address"), "bounces": spec["bounces"],
                  "providers": [{"id": k, "label": v["label"], "bounces": v["bounces"]} for k, v in T.PROVIDERS.items()]},
        "audience": {"provider": ap, "providers": [{"id": k, "label": v["label"]} for k, v in AUDIENCE.items()],
                     "key_set": bool(ap != "none" and _key(db, ap)), "list_id_set": bool(str(S.get(db, "integrations.audience_list_id") or "").strip()), "jobs": jobs},
        "webhooks": {"enabled": bool(S.get(db, "integrations.webhooks_enabled")), "endpoints": len(list_endpoints(db)),
                     "failing": db.webhook_endpoints.count_documents({"fail_streak": {"$gte": 3}}), "pending": db.webhook_outbox.count_documents({"status": "pending"}),
                     "dead": db.webhook_outbox.count_documents({"status": "dead"}), "events": list(EVENTS)},
        "tracking": {"enabled": bool(S.get(db, "tracking.enabled")), "ga4": bool(S.get(db, "tracking.ga4_id")), "meta": bool(S.get(db, "tracking.meta_pixel_id")),
                     "google_ads": bool(S.get(db, "tracking.google_ads_id")), "require_consent": bool(S.get(db, "tracking.require_consent")), "csp_additions": csp_additions(db)},
    }
