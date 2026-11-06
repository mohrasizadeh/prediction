"""accounts.py -- sign-up, sign-in, sessions, two-factor, tokens, roles. No web framework in here.

Routes (routes_accounts.py) call these functions. Every function takes `db` first and raises
AuthError(code, http_status, message) on a refusal. Nothing here sends e-mail: the functions
return the raw token and the route hands it to emailer.py. That keeps this module testable.

Rules this file enforces (see 14_security_and_privacy.md):
  * passwords: bcrypt (cost 12) over a sha256 prehash, so the 72-byte limit never truncates
  * one generic answer for "no such user" and "wrong password"; a dummy hash equalises timing
  * session tokens are random, stored only as a sha256 hash, revocable, with an absolute expiry
  * one-time tokens (verify, reset, e-mail change) are hashed, single-use, and expire
  * staff need two-factor; until they enrol, their session can only reach the enrolment routes
  * TOTP codes cannot be replayed; recovery codes are hashed and single-use
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import os
import re
import secrets
import unicodedata
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import bcrypt
import pyotp
from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError

import security
import settings_store as S

ROLES = ("owner", "admin", "support", "analyst", "user")
STAFF = ("owner", "admin", "support", "analyst")

# ----------------------------------------------------------------------------- permissions
_ADMIN = {
    "users.read", "users.write", "users.pii", "plans.read", "plans.write", "billing.read", "billing.write",
    "email.read", "email.write", "logs.read", "logs.pii", "analytics.read", "settings.read", "settings.write",
    "jobs.run", "content.write", "security.read", "inbox.write",
    "site.read", "site.write", "site.publish", "popups.read", "popups.write", "integrations.read", "integrations.write",
}
# owner only (they come with "*", and are NOT in _ADMIN): site.custom_css, tracking.write, keys.write, staff.manage, users.purge
PERMS = {
    "owner": {"*"},                                   # everything, including keys, staff and purge
    "admin": _ADMIN,
    "support": {"users.read", "users.write", "users.pii", "billing.read", "email.read", "logs.read",
                "inbox.write", "plans.read"},
    "analyst": {"analytics.read", "users.read", "billing.read", "logs.read", "plans.read", "email.read", "popups.read"},
    "user": set(),
}
OWNER_ONLY = ("keys.write", "staff.manage", "users.purge", "billing.live_refund", "site.custom_css", "tracking.write")


def can(user: dict | None, perm: str) -> bool:
    if not user:
        return False
    p = PERMS.get(user.get("role", "user"), set())
    return "*" in p or perm in p


class AuthError(Exception):
    def __init__(self, code: str, status: int = 400, message: str = ""):
        super().__init__(message or code)
        self.code, self.status, self.message = code, status, message or code


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _aware(dt):
    return dt.replace(tzinfo=timezone.utc) if dt is not None and dt.tzinfo is None else dt


def sha(s: str) -> str:
    return hashlib.sha256(s.encode()).hexdigest()


# ----------------------------------------------------------------------------- passwords
_ROUNDS = lambda: int(os.environ.get("BCRYPT_ROUNDS", "12"))
_COMMON = {"password", "password1", "password123", "1234567890", "qwertyuiop", "letmein123", "iloveyou12",
           "admin12345", "welcome123", "football123", "changeme123", "0123456789", "1q2w3e4r5t"}
_DUMMY = None


def _pre(pw: str) -> bytes:
    return base64.b64encode(hashlib.sha256(pw.encode()).digest())          # 44 bytes, never truncated


def hash_password(pw: str) -> str:
    return bcrypt.hashpw(_pre(pw), bcrypt.gensalt(_ROUNDS())).decode()


def verify_password(pw: str, hashed: str | None) -> bool:
    """Always does one bcrypt comparison, even when there is no user, so timing does not leak."""
    global _DUMMY
    if hashed is None:
        if _DUMMY is None:
            _DUMMY = hash_password("dummy-password-for-timing")
        bcrypt.checkpw(_pre(pw), _DUMMY.encode())
        return False
    try:
        return bcrypt.checkpw(_pre(pw), hashed.encode())
    except ValueError:
        return False


def check_password_policy(db, pw: str, email: str = "") -> None:
    n = int(S.get(db, "auth.password_min_length"))
    if not isinstance(pw, str) or len(pw) < n:
        raise AuthError("PASSWORD_TOO_SHORT", 400, f"Use at least {n} characters.")
    if len(pw) > 128:
        raise AuthError("PASSWORD_TOO_LONG", 400, "Use at most 128 characters.")
    if pw.lower() in _COMMON or len(set(pw)) < 4:
        raise AuthError("PASSWORD_TOO_COMMON", 400, "That password is too easy to guess.")
    if email and pw.lower() == email.split("@")[0].lower():
        raise AuthError("PASSWORD_TOO_COMMON", 400, "Do not use your e-mail name as your password.")


_EMAIL = re.compile(r"^[^@\s]{1,64}@[^@\s]{1,255}\.[^@\s.]{2,}$")


def norm_email(e: str) -> str:
    e = unicodedata.normalize("NFKC", (e or "").strip()).lower()
    if len(e) > 254 or not _EMAIL.match(e) or ".." in e:
        raise AuthError("BAD_EMAIL", 400, "Enter a valid e-mail address.")
    return e


# ----------------------------------------------------------------------------- logs
def log_auth(db, event: str, ok: bool, *, user_id=None, email=None, ip=None, ua=None, reason=None, by=None) -> None:
    db.auth_log.insert_one({"at": utcnow(), "event": event, "ok": ok, "user_id": user_id, "email": email,
                            "ip": ip, "ua": (ua or "")[:200], "reason": reason, "by": by})


# ----------------------------------------------------------------------------- tokens
def issue_token(db, user_id: str | None, kind: str, ttl: timedelta, data: dict | None = None) -> str:
    raw = secrets.token_urlsafe(32)
    db.auth_tokens.insert_one({"_id": sha(raw), "user_id": user_id, "kind": kind, "data": data or {},
                               "created_at": utcnow(), "expires_at": utcnow() + ttl, "used_at": None})
    return raw


def consume_token(db, raw: str, kind: str) -> dict | None:
    """Single use. The update is atomic, so two clicks cannot both succeed."""
    if not raw or len(raw) > 200:
        return None
    return db.auth_tokens.find_one_and_update(
        {"_id": sha(raw), "kind": kind, "used_at": None, "expires_at": {"$gt": utcnow()}},
        {"$set": {"used_at": utcnow()}}, return_document=ReturnDocument.BEFORE)


def peek_token(db, raw: str, kind: str) -> dict | None:
    return db.auth_tokens.find_one({"_id": sha(raw or ""), "kind": kind, "used_at": None, "expires_at": {"$gt": utcnow()}})


# ----------------------------------------------------------------------------- users
PUBLIC_FIELDS = {"_id": 0, "password_hash": 0, "totp": 0, "recovery_codes": 0, "failed_logins": 0}
THEMES = ("system", "dark", "light")


def public_user(u: dict) -> dict:
    """What the browser may see about the signed-in person."""
    return {"id": u["id"], "email": u["email"], "role": u["role"], "display_name": u.get("display_name") or "",
            "tz": u.get("tz", "UTC"), "theme": u.get("theme", "system"), "email_verified": bool(u.get("email_verified")),
            "two_factor": bool(u.get("_two_factor") or (u.get("totp") or {}).get("enabled")), "prefs": u.get("prefs", {}),
            "must_change_password": bool(u.get("must_change_password")), "created_at": u.get("created_at")}


def register(db, email: str, password: str, *, display_name: str = "", tz: str = "UTC", ip=None, ua=None, acq: dict | None = None):
    """Returns (user, verify_token) for a new account, or (None, None) when the e-mail is taken.
    The route answers 202 in both cases so nobody can probe which e-mails have accounts."""
    if not S.get(db, "auth.allow_signup"):
        raise AuthError("SIGNUP_CLOSED", 403, "Sign-up is closed right now.")
    email = norm_email(email)
    check_password_policy(db, password, email)
    pw_hash = hash_password(password)                      # done before the lookup: same timing both ways
    if db.users.find_one({"email": email}):
        log_auth(db, "register", False, email=email, ip=ip, ua=ua, reason="exists")
        return None, None
    verified = not S.get(db, "auth.require_email_verification")
    user = {"id": secrets.token_hex(8), "email": email, "role": "user", "password_hash": pw_hash,
            "display_name": (display_name or "").strip()[:60], "tz": _valid_tz(tz), "theme": "system",
            "email_verified": verified, "failed_logins": 0, "created_at": utcnow(), "had_trial": False,
            "prefs": {"product_emails": True, "marketing_emails": False, "alert_emails": True}}
    import analytics as _AN
    a = _AN.clean_utm(acq)
    if a or (isinstance(acq, dict) and acq.get("ref_host")):
        user["acq"] = {**(a or {}), "ref_host": str((acq or {}).get("ref_host") or "")[:80] or None}
    try:
        db.users.insert_one(dict(user))
    except DuplicateKeyError:
        return None, None
    log_auth(db, "register", True, user_id=user["id"], email=email, ip=ip, ua=ua)
    token = None
    if not verified:
        token = issue_token(db, user["id"], "verify_email", timedelta(hours=int(S.get(db, "auth.verify_token_hours"))))
    return user, token


def _valid_tz(tz: str) -> str:
    try:
        ZoneInfo(tz)
        return tz
    except Exception:
        return "UTC"


def resend_verification(db, email: str):
    u = db.users.find_one({"email": (email or "").strip().lower()})
    if not u or u.get("email_verified") or u.get("disabled"):
        return None, None
    return u, issue_token(db, u["id"], "verify_email", timedelta(hours=int(S.get(db, "auth.verify_token_hours"))))


def verify_email(db, raw: str) -> dict:
    t = consume_token(db, raw, "verify_email")
    if not t:
        raise AuthError("TOKEN_INVALID", 400, "This link is not valid any more. Ask for a new one.")
    db.users.update_one({"id": t["user_id"]}, {"$set": {"email_verified": True}})
    log_auth(db, "verify_email", True, user_id=t["user_id"])
    return db.users.find_one({"id": t["user_id"]})


# ----------------------------------------------------------------------------- sign in
# The lockout used to be read BEFORE the password was checked, and only a real address has a user
# record to read it from. So five wrong passwords against an address that exists turned the reply
# from 401 into 429, and an address that does not exist stayed on 401 forever -- six requests told
# an attacker whether anyone holds that e-mail. Everything else on this screen was already blind to
# it: `register` hashes before the lookup and answers the same either way, `request_reset` always
# answers 202, and `verify_password` runs one bcrypt comparison against a dummy hash when there is
# no user so the timing matches.
#
# The lock is now read AFTER the credentials, so a wrong password is 401 whatever the state of the
# account, and only someone who typed the right password is told the account is held. That keeps the
# lockout exactly as strong -- the right password still does not sign in while the lock stands --
# and keeps the message where it is useful, on the one person who can act on it.
def _locked(u, now) -> bool:
    lu = _aware(u.get("locked_until"))
    return bool(lu and lu > now)


def _fail(db, u, now):
    n = u.get("failed_logins", 0) + 1
    upd = {"failed_logins": n}
    if n >= int(S.get(db, "auth.max_failed_logins")):
        upd = {"failed_logins": 0, "locked_until": now + timedelta(minutes=int(S.get(db, "auth.lockout_minutes")))}
    db.users.update_one({"id": u["id"]}, {"$set": upd})


def login(db, email: str, password: str, *, ip=None, ua=None) -> dict:
    """Returns {"status": "ok", "token", "user", "scope"} or {"status": "needs_2fa", "challenge"}."""
    now = utcnow()
    e = (email or "").strip().lower()
    u = db.users.find_one({"email": e})
    good = verify_password(password or "", u.get("password_hash") if u else None)
    if not u or not good:
        # A failure while the account is already held does not extend the hold: _fail counts from
        # zero again and only re-locks once it reaches the limit, as it did before.
        if u:
            _fail(db, u, now)
        log_auth(db, "login", False, user_id=u and u["id"], email=e, ip=ip, ua=ua, reason="bad_credentials")
        raise AuthError("BAD_CREDENTIALS", 401, "Wrong e-mail or password.")
    if _locked(u, now):                              # right password, but the hold still stands
        log_auth(db, "login", False, user_id=u["id"], email=e, ip=ip, ua=ua, reason="locked")
        raise AuthError("LOCKED", 429, "Too many attempts. Try again later.")
    if u.get("disabled"):
        log_auth(db, "login", False, user_id=u["id"], email=e, ip=ip, ua=ua, reason="disabled")
        raise AuthError("ACCOUNT_DISABLED", 403, "This account is turned off. Contact support.")
    if not u.get("email_verified") and S.get(db, "auth.require_email_verification"):
        log_auth(db, "login", False, user_id=u["id"], email=e, ip=ip, ua=ua, reason="unverified")
        raise AuthError("EMAIL_NOT_VERIFIED", 403, "Check your inbox and confirm your e-mail first.")
    if (u.get("totp") or {}).get("enabled"):
        ch = issue_token(db, u["id"], "2fa_challenge", timedelta(minutes=5), {"tries": 0})
        return {"status": "needs_2fa", "challenge": ch}
    return _finish_login(db, u, ip, ua)


def _finish_login(db, u, ip, ua, method="password") -> dict:
    db.users.update_one({"id": u["id"]}, {"$set": {"failed_logins": 0, "last_login_at": utcnow(), "last_login_ip": ip}})
    scope = "full"
    if u["role"] in STAFF and S.get(db, "security.require_staff_2fa") and not (u.get("totp") or {}).get("enabled"):
        scope = "enroll_2fa"                          # can only reach the enrolment routes
    token = create_session(db, u, ip, ua, scope)
    log_auth(db, "login", True, user_id=u["id"], email=u["email"], ip=ip, ua=ua, reason=method)
    return {"status": "ok", "token": token, "scope": scope, "user": public_user(u)}


def login_2fa(db, challenge: str, code: str, *, ip=None, ua=None) -> dict:
    t = db.auth_tokens.find_one({"_id": sha(challenge or ""), "kind": "2fa_challenge", "used_at": None,
                                 "expires_at": {"$gt": utcnow()}})
    if not t:
        raise AuthError("CHALLENGE_EXPIRED", 401, "Sign in again.")
    if t["data"].get("tries", 0) >= 5:
        db.auth_tokens.delete_one({"_id": t["_id"]})
        raise AuthError("CHALLENGE_EXPIRED", 401, "Too many wrong codes. Sign in again.")
    u = db.users.find_one({"id": t["user_id"]})
    if not u or u.get("disabled") or not _check_second_factor(db, u, code):
        db.auth_tokens.update_one({"_id": t["_id"]}, {"$inc": {"data.tries": 1}})
        log_auth(db, "login_2fa", False, user_id=t["user_id"], ip=ip, ua=ua, reason="bad_code")
        raise AuthError("BAD_CODE", 401, "That code is not right.")
    db.auth_tokens.update_one({"_id": t["_id"]}, {"$set": {"used_at": utcnow()}})
    return _finish_login(db, u, ip, ua, method="password+2fa")


# ----------------------------------------------------------------------------- sessions
def create_session(db, u, ip=None, ua=None, scope="full") -> str:
    staff = u["role"] in STAFF
    now = utcnow()
    life = timedelta(minutes=int(S.get(db, "auth.staff_session_minutes"))) if staff else timedelta(days=int(S.get(db, "auth.session_days")))
    token = secrets.token_urlsafe(32)
    db.sessions.insert_one({"_id": sha(token), "sid": secrets.token_hex(6), "user_id": u["id"], "scope": scope,
                            "created_at": now, "last_seen": now, "expires_at": now + life, "staff": staff,
                            "ip": ip, "ua": (ua or "")[:200]})
    return token


def load_session(db, token: str | None):
    """Returns (user, session) or (None, None). Slides `last_seen` at most once a minute."""
    if not token or len(token) > 100:
        return None, None
    now = utcnow()
    s = db.sessions.find_one({"_id": sha(token)})
    if not s or _aware(s["expires_at"]) <= now:
        return None, None
    if s.get("staff"):
        idle = timedelta(minutes=int(S.get(db, "auth.staff_idle_minutes")))
        if now - _aware(s["last_seen"]) > idle:
            db.sessions.delete_one({"_id": s["_id"]})
            return None, None
    u = db.users.find_one({"id": s["user_id"]})
    if not u or u.get("disabled"):
        return None, None
    u["_two_factor"] = bool((u.get("totp") or {}).get("enabled"))
    for k in ("_id", "password_hash", "totp", "recovery_codes", "failed_logins"):
        u.pop(k, None)                                       # secrets never leave this function
    if now - _aware(s["last_seen"]) > timedelta(seconds=60):
        db.sessions.update_one({"_id": s["_id"]}, {"$set": {"last_seen": now}})
    return u, s


def end_session(db, token: str | None) -> None:
    if token:
        db.sessions.delete_one({"_id": sha(token)})


def revoke_all(db, user_id: str, keep_token: str | None = None) -> int:
    q = {"user_id": user_id}
    if keep_token:
        q["_id"] = {"$ne": sha(keep_token)}
    return db.sessions.delete_many(q).deleted_count


def list_sessions(db, user_id: str, current_token: str | None = None) -> list[dict]:
    cur = sha(current_token) if current_token else None
    return [{"sid": s["sid"], "created_at": s["created_at"], "last_seen": s["last_seen"], "ip": s.get("ip"),
             "ua": s.get("ua"), "current": s["_id"] == cur}
            for s in db.sessions.find({"user_id": user_id}).sort("last_seen", -1)]


def revoke_session(db, user_id: str, sid: str) -> bool:
    return db.sessions.delete_one({"user_id": user_id, "sid": sid}).deleted_count == 1


# ----------------------------------------------------------------------------- password changes
def request_reset(db, email: str):
    """Returns (user, token) or (None, None). The route always answers 202."""
    u = db.users.find_one({"email": (email or "").strip().lower()})
    if not u or u.get("disabled"):
        return None, None
    return u, issue_token(db, u["id"], "password_reset", timedelta(minutes=int(S.get(db, "auth.reset_token_minutes"))))


def confirm_reset(db, raw: str, new_password: str, *, ip=None, ua=None) -> dict:
    t = peek_token(db, raw, "password_reset")
    if not t:
        raise AuthError("TOKEN_INVALID", 400, "This link is not valid any more. Ask for a new one.")
    u = db.users.find_one({"id": t["user_id"]})
    check_password_policy(db, new_password, u["email"])
    if not consume_token(db, raw, "password_reset"):
        raise AuthError("TOKEN_INVALID", 400, "This link is not valid any more. Ask for a new one.")
    db.users.update_one({"id": u["id"]}, {"$set": {"password_hash": hash_password(new_password), "email_verified": True,
                                                  "failed_logins": 0, "must_change_password": False},
                                          "$unset": {"locked_until": ""}})
    revoke_all(db, u["id"])
    log_auth(db, "password_reset", True, user_id=u["id"], email=u["email"], ip=ip, ua=ua)
    return u


def change_password(db, user_id: str, current: str, new: str, keep_token: str | None = None, ip=None) -> None:
    u = db.users.find_one({"id": user_id})
    if not u or not verify_password(current or "", u.get("password_hash")):
        log_auth(db, "password_change", False, user_id=user_id, ip=ip, reason="bad_current")
        raise AuthError("BAD_CREDENTIALS", 403, "Your current password is not right.")
    check_password_policy(db, new, u["email"])
    db.users.update_one({"id": user_id}, {"$set": {"password_hash": hash_password(new), "must_change_password": False}})
    revoke_all(db, user_id, keep_token)                      # other devices are signed out
    log_auth(db, "password_change", True, user_id=user_id, ip=ip)


def request_email_change(db, user_id: str, new_email: str, password: str):
    u = db.users.find_one({"id": user_id})
    if not u or not verify_password(password or "", u.get("password_hash")):
        raise AuthError("BAD_CREDENTIALS", 403, "Your password is not right.")
    new_email = norm_email(new_email)
    if new_email == u["email"]:
        raise AuthError("SAME_EMAIL", 400, "That is already your e-mail.")
    if db.users.find_one({"email": new_email}):
        return u, None                                       # route answers 202 either way
    return u, issue_token(db, user_id, "email_change", timedelta(hours=int(S.get(db, "auth.verify_token_hours"))), {"new_email": new_email})


def confirm_email_change(db, raw: str):
    t = consume_token(db, raw, "email_change")
    if not t:
        raise AuthError("TOKEN_INVALID", 400, "This link is not valid any more.")
    u = db.users.find_one({"id": t["user_id"]})
    new = t["data"]["new_email"]
    try:
        db.users.update_one({"id": u["id"]}, {"$set": {"email": new, "email_verified": True}})
    except DuplicateKeyError:
        raise AuthError("EMAIL_TAKEN", 409, "That e-mail is already in use.")
    revoke_all(db, u["id"])
    log_auth(db, "email_change", True, user_id=u["id"], email=new)
    return u["email"], db.users.find_one({"id": u["id"]})


# ----------------------------------------------------------------------------- two-factor
def _totp_secret(u) -> str | None:
    t = u.get("totp") or {}
    enc = t.get("secret_enc")
    return security.decrypt_secret(enc) if enc else None


def twofa_begin(db, user_id: str) -> dict:
    u = db.users.find_one({"id": user_id})
    if (u.get("totp") or {}).get("enabled"):
        raise AuthError("ALREADY_ENABLED", 409, "Two-factor sign-in is already on.")
    secret = pyotp.random_base32()
    db.users.update_one({"id": user_id}, {"$set": {"totp.pending_enc": security.encrypt_secret(secret)}})
    import site_studio as _SS
    issuer = _SS.brand_name(db)
    return {"secret": secret, "otpauth_uri": pyotp.TOTP(secret).provisioning_uri(name=u["email"], issuer_name=issuer)}


def _match_counter(secret: str, code: str, last: int, now: datetime):
    """Returns the matching 30-second counter, or None. Accepts one step either side."""
    code = re.sub(r"\s", "", code or "")
    if not re.fullmatch(r"\d{6}", code):
        return None
    base = int(now.timestamp()) // 30
    t = pyotp.TOTP(secret)
    for off in (0, -1, 1):
        c = base + off
        if hmac.compare_digest(t.at(c * 30), code) and c > last:   # c <= last means the code was already used
            return c
    return None


def twofa_confirm(db, user_id: str, code: str) -> list[str]:
    u = db.users.find_one({"id": user_id})
    pend = (u.get("totp") or {}).get("pending_enc")
    if not pend:
        raise AuthError("NOT_STARTED", 400, "Start two-factor setup first.")
    c = _match_counter(security.decrypt_secret(pend), code, -1, utcnow())
    if c is None:
        raise AuthError("BAD_CODE", 400, "That code is not right.")
    codes = [secrets.token_hex(4) + "-" + secrets.token_hex(4) for _ in range(10)]
    db.users.update_one({"id": user_id}, {"$set": {"totp": {"enabled": True, "secret_enc": pend, "last_counter": c},
                                                 "recovery_codes": [sha(x) for x in codes]}})
    db.sessions.update_many({"user_id": user_id, "scope": "enroll_2fa"}, {"$set": {"scope": "full"}})
    log_auth(db, "2fa_enabled", True, user_id=user_id)
    return codes                                             # shown once


def _check_second_factor(db, u, code: str) -> bool:
    secret = _totp_secret(u)
    now = utcnow()
    if secret:
        last = (u.get("totp") or {}).get("last_counter", -1)
        c = _match_counter(secret, code, last, now)
        if c is not None:
            r = db.users.update_one({"id": u["id"], "totp.last_counter": {"$lt": c}}, {"$set": {"totp.last_counter": c}})
            if r.modified_count == 1:                        # a parallel request with the same code loses here
                return True
    h = sha(re.sub(r"\s", "", (code or "").lower()))
    r = db.users.update_one({"id": u["id"], "recovery_codes": h}, {"$pull": {"recovery_codes": h}})
    return r.modified_count == 1


def twofa_disable(db, user_id: str, password: str, code: str) -> None:
    u = db.users.find_one({"id": user_id})
    if u["role"] in STAFF and S.get(db, "security.require_staff_2fa"):
        raise AuthError("REQUIRED_FOR_STAFF", 403, "Staff accounts must keep two-factor sign-in on.")
    if not verify_password(password or "", u.get("password_hash")) or not _check_second_factor(db, u, code):
        raise AuthError("BAD_CREDENTIALS", 403, "Password or code is not right.")
    db.users.update_one({"id": user_id}, {"$unset": {"totp": "", "recovery_codes": ""}})
    log_auth(db, "2fa_disabled", True, user_id=user_id)


# ----------------------------------------------------------------------------- profile
def update_profile(db, user_id: str, fields: dict) -> dict:
    upd = {}
    if "display_name" in fields:
        upd["display_name"] = str(fields["display_name"] or "").strip()[:60]
    if "tz" in fields:
        try:
            ZoneInfo(fields["tz"])
        except Exception:
            raise AuthError("BAD_TZ", 400, "Unknown time zone.")
        upd["tz"] = fields["tz"]
    if "theme" in fields:
        if fields["theme"] not in THEMES:
            raise AuthError("BAD_THEME", 400, "Pick system, dark or light.")
        upd["theme"] = fields["theme"]
    if "prefs" in fields and isinstance(fields["prefs"], dict):
        for k in ("product_emails", "marketing_emails", "alert_emails", "alert_lineups", "alert_goals"):
            if k in fields["prefs"]:
                upd[f"prefs.{k}"] = bool(fields["prefs"][k])
        if "welcomed" in fields["prefs"]:
            upd["prefs.welcomed"] = bool(fields["prefs"]["welcomed"])
        if isinstance(fields["prefs"].get("leagues"), list):
            upd["prefs.leagues"] = [str(x)[:64] for x in fields["prefs"]["leagues"]][:20]
        me = db.users.find_one({"id": user_id}, {"role": 1})
        if me and me.get("role") in STAFF:                                   # staff-only switches
            for k in ("admin_digest", "admin_alerts"):
                if k in fields["prefs"]:
                    upd[f"prefs.{k}"] = bool(fields["prefs"][k])
    if upd:
        db.users.update_one({"id": user_id}, {"$set": upd})
    return public_user(db.users.find_one({"id": user_id}))


# ----------------------------------------------------------------------------- export and delete
USER_DATA = ("follows", "saved_forecasts", "notes", "alert_subscriptions", "follow_alerts", "combos")


def export_account(db, user_id: str) -> dict:
    u = db.users.find_one({"id": user_id}, PUBLIC_FIELDS)
    out = {"profile": u, "exported_at": utcnow()}
    for c in USER_DATA:
        out[c] = list(db[c].find({"user_id": user_id}, {"_id": 0}))
    out["subscriptions"] = list(db.subscriptions.find({"user_id": user_id}, {"_id": 0}))
    out["payments"] = list(db.payments.find({"user_id": user_id}, {"_id": 0}))
    out["emails_sent"] = list(db.email_log.find({"user_id": user_id}, {"_id": 0, "to": 0, "html": 0}))
    out["sign_in_history"] = list(db.auth_log.find({"user_id": user_id}, {"_id": 0}).sort("at", -1).limit(200))
    return out


def delete_account(db, user_id: str, password: str | None = None, *, by: str | None = None) -> dict:
    """Removes personal data. Payment rows stay (tax law) but lose the link to a name.
    Returns {"email", "stripe_customer_id", "subscription_ids"} so the caller can cancel billing."""
    u = db.users.find_one({"id": user_id})
    if not u:
        raise AuthError("NOT_FOUND", 404)
    if by is None and not verify_password(password or "", u.get("password_hash")):
        raise AuthError("BAD_CREDENTIALS", 403, "Your password is not right.")
    if u["role"] == "owner" and db.users.count_documents({"role": "owner", "disabled": {"$ne": True}}) <= 1:
        raise AuthError("LAST_OWNER", 409, "The last owner cannot be deleted.")
    info = {"email": u["email"], "stripe_customer_id": u.get("stripe_customer_id"),
            "subscription_ids": [s["_id"] for s in db.subscriptions.find({"user_id": user_id, "status": {"$in": ["active", "trialing", "past_due"]}})]}
    for c in USER_DATA:
        db[c].delete_many({"user_id": user_id})
    db.sessions.delete_many({"user_id": user_id})
    db.auth_tokens.delete_many({"user_id": user_id})
    db.admin_notes.delete_many({"user_id": user_id})
    db.email_log.update_many({"user_id": user_id}, {"$set": {"to": None, "to_hash": None}})
    db.events.update_many({"user_id": user_id}, {"$unset": {"user_id": ""}})
    db.subscriptions.update_many({"user_id": user_id}, {"$set": {"user_id": None, "deleted_user": user_id}})
    db.payments.update_many({"user_id": user_id}, {"$set": {"user_id": None, "deleted_user": user_id}})
    db.users.replace_one({"id": user_id}, {"id": user_id, "email": f"deleted+{user_id}@invalid", "role": "user",
                                           "disabled": True, "deleted_at": utcnow(), "email_verified": False})
    log_auth(db, "account_deleted", True, user_id=user_id, by=by)
    return info


# ----------------------------------------------------------------------------- staff
def bootstrap_owner(db) -> bool:
    """First start: create the owner from ADMIN_EMAIL + ADMIN_INITIAL_PASSWORD, only if no owner exists."""
    email, pw = os.environ.get("ADMIN_EMAIL"), os.environ.get("ADMIN_INITIAL_PASSWORD")
    if not (email and pw) or db.users.find_one({"role": "owner"}):
        return False
    db.users.insert_one({"id": secrets.token_hex(8), "email": email.strip().lower(), "role": "owner",
                         "password_hash": hash_password(pw), "must_change_password": True, "email_verified": True,
                         "failed_logins": 0, "created_at": utcnow(), "tz": "UTC", "theme": "system", "prefs": {}})
    return True


def invite_staff(db, email: str, role: str, by: str):
    """Owner only (the route checks staff.manage). Returns (user, token). The token sets the first password."""
    if role not in STAFF or role == "owner":
        raise AuthError("BAD_ROLE", 400, "Role must be admin, support or analyst.")
    email = norm_email(email)
    u = db.users.find_one({"email": email})
    if u and u["role"] in STAFF:
        raise AuthError("ALREADY_STAFF", 409, "That person is already on the team.")
    if u:
        db.users.update_one({"id": u["id"]}, {"$set": {"role": role}})
    else:
        u = {"id": secrets.token_hex(8), "email": email, "role": role, "password_hash": None, "email_verified": True,
             "must_change_password": True, "failed_logins": 0, "created_at": utcnow(), "tz": "UTC", "theme": "system", "prefs": {}}
        db.users.insert_one(dict(u))
    u["role"] = role
    log_auth(db, "staff_invited", True, user_id=u["id"], email=email, by=by, reason=role)
    return u, issue_token(db, u["id"], "password_reset", timedelta(days=3))


def set_role(db, user_id: str, role: str, by: str) -> None:
    if role not in ROLES:
        raise AuthError("BAD_ROLE", 400)
    u = db.users.find_one({"id": user_id})
    if not u:
        raise AuthError("NOT_FOUND", 404)
    if u["role"] == "owner" and role != "owner" and db.users.count_documents({"role": "owner", "disabled": {"$ne": True}}) <= 1:
        raise AuthError("LAST_OWNER", 409, "There must be at least one owner.")
    db.users.update_one({"id": user_id}, {"$set": {"role": role}})
    revoke_all(db, user_id)                                  # new rights, new sign-in
    log_auth(db, "role_changed", True, user_id=user_id, by=by, reason=f"{u['role']}->{role}")


def set_disabled(db, user_id: str, disabled: bool, by: str) -> None:
    u = db.users.find_one({"id": user_id})
    if not u:
        raise AuthError("NOT_FOUND", 404)
    if disabled and u["role"] == "owner" and db.users.count_documents({"role": "owner", "disabled": {"$ne": True}}) <= 1:
        raise AuthError("LAST_OWNER", 409, "The last owner cannot be turned off.")
    db.users.update_one({"id": user_id}, {"$set": {"disabled": disabled}})
    if disabled:
        revoke_all(db, user_id)
    log_auth(db, "disabled" if disabled else "enabled", True, user_id=user_id, by=by)
