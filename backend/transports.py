"""transports.py -- the e-mail providers the owner can switch between in Admin > Integrations.

Every provider gets the same neutral message (the shape Resend uses):
  {"from": "Name <addr>", "to": [addr], "subject", "html", "text", "reply_to"?, "headers"?, "tags"?: [{"name","value"}]}
and returns {"id": "<provider message id>"}. Errors are raised as SendError(status, name, message).

Providers: resend (default; bounce webhooks handled), postmark, sendgrid, brevo, smtp.
Honest limits: bounces and complaints are handled automatically for Resend only. For the others, add bad
addresses by hand in Admin > E-mail > Suppressions, or use that provider's own dashboard. Postmark, SendGrid and
Brevo request shapes are written from their public docs and have NOT been run against live accounts.
"""
from __future__ import annotations

import re
import smtplib
import ssl
import time
import uuid
from email.message import EmailMessage
from email.utils import formataddr, parseaddr

import httpx

import security
import settings_store as S

_FACTORY = lambda: httpx.Client(timeout=15)
_SLEEP = time.sleep
_SMTP = None            # tests inject a fake: callable(host, port, security) -> connection with login/send_message/quit


def set_http_factory(f):
    global _FACTORY
    _FACTORY = f


def set_sleep(f):
    global _SLEEP
    _SLEEP = f


def set_smtp_factory(f):
    global _SMTP
    _SMTP = f


class SendError(Exception):
    def __init__(self, status, name="", message=""):
        super().__init__(f"{status} {name} {message}")
        self.status, self.name, self.message = status, name, message


PROVIDERS = {
    "resend": {"label": "Resend", "key": "resend", "env": "RESEND_API_KEY", "re": r"^re_[A-Za-z0-9_]{10,}$", "hint": "starts with re_", "bounces": "automatic"},
    "postmark": {"label": "Postmark", "key": "postmark", "env": "POSTMARK_SERVER_TOKEN", "re": r"^[A-Za-z0-9-]{20,60}$", "hint": "is the Server API token (letters, numbers, dashes)", "bounces": "manual"},
    "sendgrid": {"label": "SendGrid", "key": "sendgrid", "env": "SENDGRID_API_KEY", "re": r"^SG\.[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}$", "hint": "starts with SG.", "bounces": "manual"},
    "brevo": {"label": "Brevo", "key": "brevo", "env": "BREVO_API_KEY", "re": r"^xkeysib-[A-Za-z0-9\-]{20,}$", "hint": "starts with xkeysib-", "bounces": "manual"},
    "smtp": {"label": "SMTP server", "key": "smtp_password", "env": "SMTP_PASSWORD", "re": r"^.{1,200}$", "hint": "is the SMTP password or app password", "bounces": "manual"},
}


def _split(addr: str) -> tuple[str, str]:
    name, email = parseaddr(addr)
    return name, email


def _post(url: str, headers: dict, body: dict, ok=(200, 201, 202), retries: int = 3) -> httpx.Response:
    last = None
    for attempt in range(retries):
        try:
            with _FACTORY() as c:
                r = c.post(url, json=body, headers=headers)
        except httpx.HTTPError as e:
            last = SendError(0, "network", type(e).__name__)
        else:
            if r.status_code in ok:
                return r
            try:
                j = r.json()
            except Exception:
                j = {}
            msg = j.get("Message") or j.get("message") or (j.get("errors") or [{}])[0].get("message", "") if isinstance(j, dict) else ""
            last = SendError(r.status_code, str(j.get("name") or j.get("code") or j.get("ErrorCode") or "")[:40] if isinstance(j, dict) else "", str(msg)[:200])
            if r.status_code not in (429, 500, 502, 503, 504):
                raise last
        _SLEEP(0.5 * (2 ** attempt))
    raise last


class Resend:
    API = "https://api.resend.com"

    def __init__(self, key):
        self.key = key

    def send(self, payload: dict, idem: str | None = None) -> dict:
        h = {"Authorization": f"Bearer {self.key}", "Content-Type": "application/json", "User-Agent": "forecast-app/1.0"}
        if idem:
            h["Idempotency-Key"] = idem[:256]
        return _post(f"{self.API}/emails", h, payload, ok=(200, 201)).json()


class Postmark:
    def __init__(self, key):
        self.key = key

    def send(self, payload: dict, idem: str | None = None) -> dict:
        body = {"From": payload["from"], "To": ", ".join(payload["to"]), "Subject": payload["subject"], "HtmlBody": payload["html"], "TextBody": payload["text"],
                "MessageStream": "outbound"}
        if payload.get("reply_to"): body["ReplyTo"] = payload["reply_to"]
        if payload.get("headers"): body["Headers"] = [{"Name": k, "Value": v} for k, v in payload["headers"].items()]
        if payload.get("tags"): body["Tag"] = payload["tags"][0]["value"][:1000]
        r = _post("https://api.postmarkapp.com/email", {"X-Postmark-Server-Token": self.key, "Accept": "application/json", "Content-Type": "application/json"}, body, ok=(200,))
        j = r.json()
        if j.get("ErrorCode", 0) != 0:
            raise SendError(422, str(j.get("ErrorCode")), j.get("Message", ""))
        return {"id": j.get("MessageID")}


class SendGrid:
    def __init__(self, key):
        self.key = key

    def send(self, payload: dict, idem: str | None = None) -> dict:
        name, addr = _split(payload["from"])
        body = {"personalizations": [{"to": [{"email": t} for t in payload["to"]]}], "from": {"email": addr, **({"name": name} if name else {})},
                "subject": payload["subject"], "content": [{"type": "text/plain", "value": payload["text"]}, {"type": "text/html", "value": payload["html"]}]}
        if payload.get("reply_to"): body["reply_to"] = {"email": payload["reply_to"]}
        if payload.get("headers"): body["headers"] = payload["headers"]
        r = _post("https://api.sendgrid.com/v3/mail/send", {"Authorization": f"Bearer {self.key}", "Content-Type": "application/json"}, body, ok=(200, 202))
        return {"id": r.headers.get("X-Message-Id")}


class Brevo:
    def __init__(self, key):
        self.key = key

    def send(self, payload: dict, idem: str | None = None) -> dict:
        name, addr = _split(payload["from"])
        body = {"sender": {"email": addr, **({"name": name} if name else {})}, "to": [{"email": t} for t in payload["to"]], "subject": payload["subject"],
                "htmlContent": payload["html"], "textContent": payload["text"]}
        if payload.get("reply_to"): body["replyTo"] = {"email": payload["reply_to"]}
        if payload.get("headers"): body["headers"] = payload["headers"]
        if payload.get("tags"): body["tags"] = [payload["tags"][0]["value"]]
        r = _post("https://api.brevo.com/v3/smtp/email", {"api-key": self.key, "Accept": "application/json", "Content-Type": "application/json"}, body, ok=(200, 201))
        return {"id": r.json().get("messageId")}


class Smtp:
    """Any SMTP server (a hosting mailbox, Microsoft 365, Gmail with an app password). Slow and limited compared with an API; fine for a start."""
    def __init__(self, password, host, port, user, mode):
        self.pw, self.host, self.port, self.user, self.mode = password, host, int(port), user, mode

    def send(self, payload: dict, idem: str | None = None) -> dict:
        name, addr = _split(payload["from"])
        m = EmailMessage()
        m["From"] = formataddr((name, addr))
        m["To"] = ", ".join(payload["to"])
        m["Subject"] = payload["subject"]
        mid = f"<{uuid.uuid4().hex}@{addr.split('@')[-1]}>"
        m["Message-ID"] = mid
        if payload.get("reply_to"): m["Reply-To"] = payload["reply_to"]
        for k, v in (payload.get("headers") or {}).items():
            if not re.fullmatch(r"[A-Za-z0-9-]{1,40}", k) or "\n" in v or "\r" in v:
                raise SendError(400, "bad_header", k)
            m[k] = v
        m.set_content(payload["text"])
        m.add_alternative(payload["html"], subtype="html")
        try:
            if _SMTP:
                c = _SMTP(self.host, self.port, self.mode)
            elif self.mode == "ssl":
                c = smtplib.SMTP_SSL(self.host, self.port, timeout=15, context=ssl.create_default_context())
            else:
                c = smtplib.SMTP(self.host, self.port, timeout=15)
                c.starttls(context=ssl.create_default_context())
            try:
                if self.user:
                    c.login(self.user, self.pw)
                c.send_message(m)
            finally:
                try: c.quit()
                except Exception: pass
        except smtplib.SMTPResponseException as e:
            raise SendError(int(e.smtp_code), "smtp", str(e.smtp_error)[:150])
        except (OSError, smtplib.SMTPException) as e:
            raise SendError(0, "smtp", type(e).__name__)
        return {"id": mid}


def get_provider(db) -> str:
    p = S.get(db, "email.provider")
    return p if p in PROVIDERS else "resend"


def get_client(db):
    """The sender for the provider chosen in settings, or None when its key is missing."""
    p = get_provider(db)
    spec = PROVIDERS[p]
    key = security.get_provider_key(db, spec["key"], spec["env"])
    if not key:
        return None
    if p == "resend": return Resend(key)
    if p == "postmark": return Postmark(key)
    if p == "sendgrid": return SendGrid(key)
    if p == "brevo": return Brevo(key)
    host, user = S.get(db, "email.smtp_host"), S.get(db, "email.smtp_user")
    mode = S.get(db, "email.smtp_security")
    if not host or mode not in ("starttls", "ssl"):
        return None
    return Smtp(key, host, S.get(db, "email.smtp_port"), user, mode)


def test_key(db, pid: str) -> dict:
    """A harmless read-only call that proves the key works. For SMTP it opens a connection and logs in (nothing is sent)."""
    spec = PROVIDERS[pid]
    key = security.get_provider_key(db, spec["key"], spec["env"])
    if not key:
        return {"ok": False, "code": "no_key"}
    try:
        if pid == "smtp":
            host, mode, user = S.get(db, "email.smtp_host"), S.get(db, "email.smtp_security"), S.get(db, "email.smtp_user")
            if not host:
                return {"ok": False, "code": "no_host"}
            if _SMTP:
                c = _SMTP(host, int(S.get(db, "email.smtp_port")), mode)
            elif mode == "ssl":
                c = smtplib.SMTP_SSL(host, int(S.get(db, "email.smtp_port")), timeout=15, context=ssl.create_default_context())
            else:
                c = smtplib.SMTP(host, int(S.get(db, "email.smtp_port")), timeout=15)
                c.starttls(context=ssl.create_default_context())
            try:
                if user:
                    c.login(user, key)
            finally:
                try: c.quit()
                except Exception: pass
            return {"ok": True}
        if pid == "postmark":
            url, h = "https://api.postmarkapp.com/server", {"X-Postmark-Server-Token": key, "Accept": "application/json"}
        elif pid == "sendgrid":
            url, h = "https://api.sendgrid.com/v3/scopes", {"Authorization": f"Bearer {key}"}
        elif pid == "brevo":
            url, h = "https://api.brevo.com/v3/account", {"api-key": key, "Accept": "application/json"}
        else:
            return {"ok": False, "code": "unsupported"}
        with _FACTORY() as c:
            r = c.get(url, headers=h)
        return {"ok": r.status_code == 200, "code": None if r.status_code == 200 else r.status_code}
    except smtplib.SMTPAuthenticationError:
        return {"ok": False, "code": "smtp_login_refused"}
    except (OSError, smtplib.SMTPException, httpx.HTTPError) as e:
        return {"ok": False, "code": type(e).__name__}
