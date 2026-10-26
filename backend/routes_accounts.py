"""routes_accounts.py -- sign-up, sign-in, account settings, privacy, contact, analytics beacon.

Every route here is thin: validate input, call accounts.py / emailer.py, return JSON.
Rules: same answer for "exists" and "does not exist" on sign-up, forgot-password and resend;
extra per-e-mail rate limits on top of the per-IP middleware; no secret ever returned except the
one-time values the person must see once (2FA secret, recovery codes).
"""
from __future__ import annotations

from datetime import timedelta
from typing import Optional

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

import accounts as A
import admin_queries as AQ
import analytics as AN
import deps as D
import emailer as E
import plans as P
import ratelimit as RL
import settings_store as S
import stripe_billing as SB

router = APIRouter(prefix="/api")


class Email(BaseModel):
    email: str = Field(max_length=254)


class Register(Email):
    password: str = Field(max_length=200)
    display_name: str = Field("", max_length=60)
    tz: str = Field("UTC", max_length=60)
    acq: Optional[dict] = None               # first-touch campaign tags the front end remembered: {source, medium, campaign, ref_host}


class Login(Email):
    password: str = Field(max_length=200)


class Challenge(BaseModel):
    challenge: str = Field(max_length=200)
    code: str = Field(max_length=40)


class TokenBody(BaseModel):
    token: str = Field(max_length=200)


class ResetBody(TokenBody):
    password: str = Field(max_length=200)


def _ctx(request: Request):
    return getattr(request.state, "ip", None), request.headers.get("user-agent", "")[:200]


def _emit(db, type_, user):
    try:
        import integrations as INT
        INT.emit(db, type_, {}, email=user.get("email"), user_id=user.get("id"))
    except Exception:
        pass


def _link(path: str, token: str) -> str:
    return f"{E.base_url()}{path}?token={token}"


def _send(db, key, user_or_none, to, vars=None, idem=None):
    try:
        return E.send_template(db, key, to=to, user=user_or_none, vars=vars or {}, idem=idem)
    except Exception:                       # e-mail trouble must never break sign-up or reset
        return {"status": "failed"}


def me_payload(db, user, request=None):
    if not user:
        ep = P.effective_plan(db, None)
        return {"user": None, "plan": {k: ep[k] for k in ("plan_key", "plan_name", "source")}, "entitlements": ep["entitlements"],
                "limits": {"anonymous_finder_searches_per_day": S.get(db, "plans.anonymous_finder_searches_per_day")}}
    ep = P.effective_plan(db, user)
    day_used = P.used_today(db, f"u:{user['id']}", "finder")
    return {"user": A.public_user(user), "plan": {k: v for k, v in ep.items() if k != "entitlements"}, "entitlements": ep["entitlements"],
            "usage": {"finder_today": day_used}, "billing_enabled": bool(S.get(db, "features.billing"))}


# ----------------------------------------------------------------------------- auth
@router.post("/auth/register", status_code=202)
def register(body: Register, request: Request, db=Depends(D.get_db)):
    ip, ua = _ctx(request)
    RL.check(db, f"register:{ip}", 5, 3600)
    user, token = A.register(db, body.email, body.password, display_name=body.display_name, tz=body.tz, ip=ip, ua=ua, acq=body.acq)
    if user:
        AN.track(db, "signup", user_id=user["id"], server=True, ip=ip, ua=ua, utm=body.acq)
        _emit(db, "user.signed_up", user)
        if token:
            _send(db, "verify_email", user, user["email"], {"link": _link("/verify-email", token), "hours": S.get(db, "auth.verify_token_hours")}, idem=f"verify-{user['id']}-{token[:8]}")
        else:
            _send(db, "welcome", user, user["email"], {"link": E.base_url()})
    return {"ok": True, "message": "If that address can be used, we sent a link to confirm it."}


@router.post("/auth/verify-email")
def verify_email(body: TokenBody, request: Request, db=Depends(D.get_db)):
    u = A.verify_email(db, body.token)
    AN.track(db, "verified", user_id=u["id"], server=True)
    _emit(db, "user.verified", u)
    _send(db, "welcome", u, u["email"], {"link": E.base_url()})
    return {"ok": True}


@router.post("/auth/resend-verification", status_code=202)
def resend_verification(body: Email, request: Request, db=Depends(D.get_db)):
    ip, _ = _ctx(request)
    RL.check(db, f"resendv:{ip}", 5, 3600)
    RL.check(db, f"resendv:{E.to_hash(body.email)}", 3, 3600)
    u, token = A.resend_verification(db, body.email)
    if u:
        _send(db, "verify_email", u, u["email"], {"link": _link("/verify-email", token), "hours": S.get(db, "auth.verify_token_hours")})
    return {"ok": True, "message": "If that address needs confirming, we sent a new link."}


@router.post("/auth/login")
def login(body: Login, request: Request, response: Response, db=Depends(D.get_db)):
    ip, ua = _ctx(request)
    RL.check(db, f"login:{E.to_hash(body.email)}", 10, 900)           # 10 tries per e-mail per 15 minutes, on top of lockout
    r = A.login(db, body.email, body.password, ip=ip, ua=ua)
    return _login_response(db, r, response)


def _login_response(db, r, response):
    if r["status"] == "needs_2fa":
        return {"needs_2fa": True, "challenge": r["challenge"]}
    staff = r["user"]["role"] in A.STAFF
    life = int(S.get(db, "auth.staff_session_minutes")) * 60 if staff else int(S.get(db, "auth.session_days")) * 86400
    D.set_session_cookie(response, r["token"], life)
    AN.track(db, "login", user_id=r["user"]["id"], server=True)
    full = db.users.find_one({"id": r["user"]["id"]})
    return {"scope": r["scope"], **me_payload(db, full)}


@router.post("/auth/login/2fa")
def login_2fa(body: Challenge, request: Request, response: Response, db=Depends(D.get_db)):
    ip, ua = _ctx(request)
    RL.check(db, f"2fa:{ip}", 10, 900)
    return _login_response(db, A.login_2fa(db, body.challenge, body.code, ip=ip, ua=ua), response)


@router.post("/auth/logout")
def logout(request: Request, response: Response, db=Depends(D.get_db)):
    A.end_session(db, D.session_token(request))
    D.clear_session_cookie(response)
    return {"ok": True}


@router.post("/auth/forgot-password", status_code=202)
def forgot_password(body: Email, request: Request, db=Depends(D.get_db)):
    ip, _ = _ctx(request)
    RL.check(db, f"forgot:{ip}", 5, 3600)
    RL.check(db, f"forgot:{E.to_hash(body.email)}", 3, 3600)
    u, token = A.request_reset(db, body.email)
    if u:
        _send(db, "password_reset", u, u["email"], {"link": _link("/reset-password", token), "minutes": S.get(db, "auth.reset_token_minutes")})
    return {"ok": True, "message": "If that address has an account, we sent a reset link."}


@router.post("/auth/reset-password")
def reset_password(body: ResetBody, request: Request, db=Depends(D.get_db)):
    ip, ua = _ctx(request)
    RL.check(db, f"reset:{ip}", 10, 3600)
    u = A.confirm_reset(db, body.token, body.password, ip=ip, ua=ua)
    _send(db, "password_changed", u, u["email"])
    return {"ok": True}


@router.get("/auth/me")
def me(user=Depends(D.optional_user), auth=Depends(D.current), db=Depends(D.get_db)):
    u, s = auth
    if u and s["scope"] != "full":                            # staff who still have to set up 2FA
        return {"user": A.public_user(u), "scope": s["scope"]}
    return me_payload(db, user)


# ----------------------------------------------------------------------------- account
class ProfileBody(BaseModel):
    display_name: Optional[str] = Field(None, max_length=60)
    tz: Optional[str] = Field(None, max_length=60)
    theme: Optional[str] = Field(None, max_length=10)
    prefs: Optional[dict] = None


@router.patch("/account/profile")
def update_profile(body: ProfileBody, user=Depends(D.require_user), db=Depends(D.get_db)):
    return {"user": A.update_profile(db, user["id"], body.model_dump(exclude_none=True))}


class PasswordBody(BaseModel):
    current: str = Field(max_length=200)
    new: str = Field(max_length=200)


@router.post("/account/password")
def change_password(body: PasswordBody, request: Request, user=Depends(D.require_user), db=Depends(D.get_db)):
    ip, _ = _ctx(request)
    RL.check(db, f"chpw:{user['id']}", 5, 900)
    A.change_password(db, user["id"], body.current, body.new, keep_token=D.session_token(request), ip=ip)
    _send(db, "password_changed", user, user["email"])
    return {"ok": True}


class EmailChange(BaseModel):
    new_email: str = Field(max_length=254)
    password: str = Field(max_length=200)


@router.post("/account/email", status_code=202)
def email_change(body: EmailChange, user=Depends(D.require_user), db=Depends(D.get_db)):
    RL.check(db, f"chem:{user['id']}", 5, 3600)
    u, token = A.request_email_change(db, user["id"], body.new_email, body.password)
    if token:
        _send(db, "email_change_confirm", u, A.norm_email(body.new_email), {"link": _link("/confirm-email", token), "new_email": A.norm_email(body.new_email)})
    return {"ok": True, "message": "If that address can be used, we sent a link to it."}


@router.post("/account/email/confirm")
def email_confirm(body: TokenBody, db=Depends(D.get_db)):
    old, new = A.confirm_email_change(db, body.token)
    _send(db, "email_changed", new, old, {"new_email": new["email"]})
    return {"ok": True}


class CodeBody(BaseModel):
    code: str = Field(max_length=40)


@router.post("/account/2fa/begin")
def twofa_begin(user=Depends(D.any_session_user), db=Depends(D.get_db)):
    return A.twofa_begin(db, user["id"])


@router.post("/account/2fa/confirm")
def twofa_confirm(body: CodeBody, user=Depends(D.any_session_user), db=Depends(D.get_db)):
    RL.check(db, f"2fac:{user['id']}", 10, 900)
    return {"recovery_codes": A.twofa_confirm(db, user["id"], body.code), "note": "Save these now. We show them once."}


class DisableBody(CodeBody):
    password: str = Field(max_length=200)


@router.post("/account/2fa/disable")
def twofa_disable(body: DisableBody, user=Depends(D.require_user), db=Depends(D.get_db)):
    RL.check(db, f"2fad:{user['id']}", 5, 900)
    A.twofa_disable(db, user["id"], body.password, body.code)
    return {"ok": True}


@router.get("/account/sessions")
def sessions(request: Request, user=Depends(D.require_user), db=Depends(D.get_db)):
    return {"sessions": A.list_sessions(db, user["id"], D.session_token(request))}


@router.delete("/account/sessions/{sid}")
def revoke_one(sid: str, user=Depends(D.require_user), db=Depends(D.get_db)):
    return {"ok": A.revoke_session(db, user["id"], sid)}


@router.post("/account/sessions/revoke-others")
def revoke_others(request: Request, user=Depends(D.require_user), db=Depends(D.get_db)):
    return {"revoked": A.revoke_all(db, user["id"], keep_token=D.session_token(request))}


@router.get("/account/export")
def export(user=Depends(D.require_user), db=Depends(D.get_db)):
    RL.check(db, f"export:{user['id']}", 3, 86400)
    return A.export_account(db, user["id"])


class DeleteBody(BaseModel):
    password: str = Field(max_length=200)


@router.delete("/account")
def delete_account(body: DeleteBody, response: Response, user=Depends(D.require_user), db=Depends(D.get_db)):
    RL.check(db, f"delacc:{user['id']}", 3, 3600)
    # stop billing first: if Stripe is down we refuse, so nobody is charged after deleting
    live = [s for s in db.subscriptions.find({"user_id": user["id"], "status": {"$in": ["active", "trialing", "past_due"]}})]
    if live:
        try:
            st = SB.Stripe(db)
            for s in live:
                SB.cancel_subscription(st, db, s["_id"], at_period_end=False, actor=user["email"])
        except Exception:
            raise D.err(503, "BILLING_UNAVAILABLE", "We could not cancel your subscription right now. Try again in a minute, or cancel it in the billing portal first.")
    email = user["email"]
    A.delete_account(db, user["id"], body.password)
    _send(db, "account_deleted", None, email)
    D.clear_session_cookie(response)
    return {"ok": True}


# ----------------------------------------------------------------------------- public helpers
class UnsubBody(BaseModel):
    t: str = Field(max_length=400)


@router.get("/email/unsubscribe")
def unsubscribe_preview(t: str, db=Depends(D.get_db)):
    """A GET never changes anything (mail scanners open links). It only shows who the link is for."""
    e = E.read_unsub(t)
    if not e:
        raise D.err(400, "TOKEN_INVALID", "This link is not valid.")
    return {"email": AQ.mask_email(e)}


@router.post("/email/unsubscribe")
def unsubscribe(request: Request, t: str | None = None, body: UnsubBody | None = None, db=Depends(D.get_db)):
    tok = t or (body.t if body else None)
    if not tok or not E.unsubscribe(db, tok):
        raise D.err(400, "TOKEN_INVALID", "This link is not valid.")
    return {"ok": True}


class ContactBody(BaseModel):
    name: str = Field("", max_length=80)
    email: str = Field(max_length=254)
    message: str = Field(max_length=4000)


@router.post("/contact", status_code=202)
def contact(body: ContactBody, request: Request, db=Depends(D.get_db)):
    ip, _ = _ctx(request)
    RL.check(db, f"contact:{ip}", 3, 3600)
    AQ.add_contact(db, body.name, body.email, body.message, ip=ip)
    AN.track(db, "contact", server=True, ip=ip)
    try:
        import integrations as INT
        INT.emit(db, "contact.received", {}, email=body.email)
    except Exception:
        pass
    # No auto-reply to the sender (strangers could use it to make us e-mail anyone). Staff read the inbox in the admin panel.
    return {"ok": True}


class Beacon(BaseModel):
    name: str = Field(max_length=30)
    path: str = Field("/", max_length=200)
    ref: Optional[str] = Field(None, max_length=300)
    props: Optional[dict] = None
    utm: Optional[dict] = None               # {source, medium, campaign} read from the landing URL (utm_source ...)


@router.post("/analytics/collect", status_code=204)
def collect(body: Beacon, request: Request, user=Depends(D.optional_user), db=Depends(D.get_db)):
    ip, ua = _ctx(request)
    dnt = request.headers.get("dnt") == "1" or request.headers.get("sec-gpc") == "1"
    AN.track(db, body.name, user_id=user and user["id"], ip=ip, ua=ua, path=body.path, ref=body.ref, props=body.props, dnt=dnt, utm=body.utm)
    return Response(status_code=204)


@router.get("/announcements")
def announcements(user=Depends(D.optional_user), db=Depends(D.get_db)):
    return {"items": AQ.active_announcements(db, user)}
