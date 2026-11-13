"""routes_admin.py -- the admin panel API. Every route names the permission it needs.

Permissions (accounts.PERMS): owner = everything; admin = everything except keys, staff, purge, live refunds;
support = look up people, fix accounts, read the inbox; analyst = read-only numbers with personal data masked.

Every write: checks the permission, validates input, writes audit_log (who, what, target, when), and never
returns a secret. There is NO "sign in as this user" feature, on purpose.
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from typing import Optional

import httpx
from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, Field

import accounts as A
import admin_queries as AQ
import analytics as AN
import deps as D
import engine_bridge as B
import emailer as E
import integrations as INT
import jobs
import plans as P
import routes_billing as RB
import security
import settings_store as S
import stripe_billing as SB
import transports as T
from cached_fetch import PitchClient, PitchError

router = APIRouter(prefix="/api/admin")
perm = D.require_perm
# email.provider and email.smtp_* decide where the stored mail password and every reset link go (docs/36 C1)
OWNER_ONLY_SETTINGS = ("security.", "billing.", "auth.", "features.billing", "tracking.", "email.provider", "email.smtp_")


def utcnow():
    return datetime.now(timezone.utc)


def parse_dt(s: str | None):
    if not s:
        return None
    try:
        d = datetime.fromisoformat(s)
        return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    except ValueError:
        raise D.err(400, "BAD_DATE", "Use a date like 2026-10-25.")


def wrap_plan_error():
    class Ctx:
        def __enter__(self): return self
        def __exit__(self, t, e, tb):
            if isinstance(e, P.PlanError): raise D.err(400, e.code, e.message)
            if isinstance(e, SB.StripeError): raise D.err(502, "STRIPE_ERROR", f"Stripe said: {e.message or e.code}")
            if isinstance(e, SB.StripeConfigError): raise D.err(503, "STRIPE_CONFIG", str(e))
            if isinstance(e, ValueError) and not isinstance(e, A.AuthError): raise D.err(400, "BAD_REQUEST", str(e))
            return False
    return Ctx()


# ----------------------------------------------------------------------------- dashboard and analytics
@router.get("/dashboard")
def dashboard(user=Depends(perm("analytics.read")), db=Depends(D.get_db)):
    ov = AN.overview(db, 30)
    h = AQ.health(db) if A.can(user, "logs.read") else None
    return {"overview": ov, "health": h}


@router.get("/home")
def admin_home(user=Depends(perm("analytics.read")), db=Depends(D.get_db)):
    import admin_home as AH
    return AH.home(db, user)


@router.get("/feeds")
def admin_feeds(user=Depends(perm("logs.read")), db=Depends(D.get_db)):
    """Both football feeds side by side (docs/43)."""
    import admin_home as AH
    return AH.feeds(db)


@router.get("/analytics/overview")
def a_overview(days: int = Query(30, ge=1, le=400), user=Depends(perm("analytics.read")), db=Depends(D.get_db)):
    return AN.overview(db, days)


@router.get("/analytics/series")
def a_series(name: str, days: int = Query(30, ge=1, le=400), user=Depends(perm("analytics.read")), db=Depends(D.get_db)):
    if name not in AN.CLIENT_EVENTS | AN.SERVER_EVENTS:
        raise D.err(400, "BAD_EVENT")
    return {"name": name, "series": AN.series(db, name, days)}


@router.get("/analytics/funnel")
def a_funnel(days: int = Query(30, ge=1, le=400), user=Depends(perm("analytics.read")), db=Depends(D.get_db)):
    return {"steps": AN.funnel(db, days)}


@router.get("/analytics/traffic")
def a_traffic(days: int = Query(30, ge=1, le=400), user=Depends(perm("analytics.read")), db=Depends(D.get_db)):
    return {"pages": AN.top_pages(db, days), "referrers": AN.referrers(db, days), "devices": AN.devices(db, days)}


@router.get("/analytics/finder")
def a_finder(days: int = Query(30, ge=1, le=400), user=Depends(perm("analytics.read")), db=Depends(D.get_db)):
    return AN.finder_usage(db, days)


@router.get("/analytics/retention")
def a_retention(weeks: int = Query(8, ge=2, le=26), user=Depends(perm("analytics.read")), db=Depends(D.get_db)):
    return {"cohorts": AN.retention(db, weeks)}


@router.get("/analytics/revenue")
def a_revenue(days: int = Query(30, ge=1, le=400), user=Depends(perm("billing.read")), db=Depends(D.get_db)):
    return AN.revenue(db, days)


# ----------------------------------------------------------------------------- users
@router.get("/users")
def users(q: str = "", role: Optional[str] = None, plan: Optional[str] = None, verified: Optional[bool] = None, disabled: Optional[bool] = None,
          created_from: Optional[str] = None, created_to: Optional[str] = None, sort: str = "created_at", direction: int = -1,
          page: int = Query(1, ge=1), limit: int = Query(25, ge=1, le=100), user=Depends(perm("users.read")), db=Depends(D.get_db)):
    return AQ.list_users(db, user, q=q, role=role, plan=plan, verified=verified, disabled=disabled, created_from=parse_dt(created_from),
                         created_to=parse_dt(created_to), sort=sort, direction=direction, page=page, limit=limit)


@router.get("/users/{user_id}")
def user_detail(user_id: str, user=Depends(perm("users.read")), db=Depends(D.get_db)):
    d = AQ.user_detail(db, user, user_id)
    if not d:
        raise D.err(404, "NOT_FOUND", "No such user.")
    return d


class Reason(BaseModel):
    reason: str = Field(max_length=200)


@router.post("/users/{user_id}/disable")
def disable(user_id: str, body: Reason, user=Depends(perm("users.write")), db=Depends(D.get_db)):
    AQ.disable_user(db, user, user_id, True, body.reason)
    return {"ok": True}


@router.post("/users/{user_id}/enable")
def enable(user_id: str, body: Reason, user=Depends(perm("users.write")), db=Depends(D.get_db)):
    AQ.disable_user(db, user, user_id, False, body.reason)
    return {"ok": True}


class OptionalReason(BaseModel):
    reason: str = Field("", max_length=200)


@router.post("/users/{user_id}/logout")
def force_logout(user_id: str, body: OptionalReason = OptionalReason(), user=Depends(perm("users.write")), db=Depends(D.get_db)):
    return {"signed_out": AQ.force_logout(db, user, user_id, body.reason)}


@router.post("/users/{user_id}/resend-verification")
def resend_verification(user_id: str, user=Depends(perm("users.write")), db=Depends(D.get_db)):
    t = AQ.guard_target(db, user, user_id, allow_self=True)
    u, token = A.resend_verification(db, t["email"])
    if not u:
        raise D.err(409, "NOTHING_TO_DO", "This e-mail is already confirmed.")
    r = E.send_template(db, "verify_email", to=u["email"], user=u, vars={"link": f"{E.base_url()}/verify-email?token={token}", "hours": S.get(db, "auth.verify_token_hours")})
    AQ.audit(db, user, "user.resend_verification", user_id, {"email_status": r["status"]})
    return {"email_status": r["status"]}


@router.post("/users/{user_id}/send-reset")
def send_reset(user_id: str, user=Depends(perm("users.write")), db=Depends(D.get_db)):
    t = AQ.guard_target(db, user, user_id)
    u, token = A.request_reset(db, t["email"])
    r = E.send_template(db, "password_reset", to=t["email"], user=t, vars={"link": f"{E.base_url()}/reset-password?token={token}", "minutes": S.get(db, "auth.reset_token_minutes")})
    AQ.audit(db, user, "user.send_reset", user_id, {"email_status": r["status"]})
    return {"email_status": r["status"]}          # the link itself is never shown to staff


class Note(BaseModel):
    text: str = Field(max_length=1000)


@router.post("/users/{user_id}/notes")
def add_note(user_id: str, body: Note, user=Depends(perm("users.write")), db=Depends(D.get_db)):
    AQ.add_note(db, user_id, body.text, user)
    return {"ok": True}


class Comp(BaseModel):
    plan: str = Field(max_length=31)
    days: Optional[int] = Field(None, ge=1, le=3650)
    reason: str = Field(max_length=200)


@router.post("/users/{user_id}/comp")
def comp(user_id: str, body: Comp, user=Depends(perm("plans.write")), db=Depends(D.get_db)):
    AQ.guard_target(db, user, user_id, allow_self=True)
    with wrap_plan_error():
        P.grant_comp(db, user_id, body.plan, body.days, body.reason, user["email"])
    return {"ok": True}


@router.post("/users/{user_id}/comp/revoke")
def comp_revoke(user_id: str, user=Depends(perm("plans.write")), db=Depends(D.get_db)):
    P.revoke_comp(db, user_id, user["email"])
    return {"ok": True}


@router.delete("/users/{user_id}/purge")
def purge(user_id: str, user=Depends(perm("users.purge")), db=Depends(D.get_db)):
    info = AQ.purge_user(db, user, user_id)
    if info["subscription_ids"]:
        try:
            st = SB.Stripe(db)
            for sid in info["subscription_ids"]:
                SB.cancel_subscription(st, db, sid, at_period_end=False, actor=user["email"])
        except Exception:
            return {"ok": True, "warning": "Account removed, but we could not cancel billing. Cancel it in Stripe."}
    return {"ok": True}


# ----------------------------------------------------------------------------- staff
@router.get("/staff")
def staff(user=Depends(perm("security.read")), db=Depends(D.get_db)):
    return {"staff": AQ.list_staff(db), "roles": {r: sorted(p) for r, p in A.PERMS.items() if r != "user"}}


class Invite(BaseModel):
    email: str = Field(max_length=254)
    role: str = Field(max_length=10)


@router.post("/staff/invite")
def invite(body: Invite, user=Depends(perm("staff.manage")), db=Depends(D.get_db)):
    u, token = A.invite_staff(db, body.email, body.role, user["email"])
    link = f"{E.base_url()}/reset-password?token={token}"
    r = E.send_template(db, "staff_invite", to=u["email"], user=u, vars={"link": link, "role": body.role})
    AQ.audit(db, user, "staff.invite", u["id"], {"role": body.role, "email_status": r["status"]})
    return {"ok": True, "email_status": r["status"], **({"link": link} if r["status"] != "sent" else {})}


class RoleBody(BaseModel):
    role: str = Field(max_length=10)


@router.post("/users/{user_id}/role")
def set_role(user_id: str, body: RoleBody, user=Depends(perm("staff.manage")), db=Depends(D.get_db)):
    AQ.guard_target(db, user, user_id)
    A.set_role(db, user_id, body.role, user["email"])
    AQ.audit(db, user, "user.role", user_id, {"role": body.role})
    return {"ok": True}


@router.post("/users/{user_id}/reset-2fa")
def reset_2fa(user_id: str, user=Depends(perm("staff.manage")), db=Depends(D.get_db)):
    AQ.guard_target(db, user, user_id)
    db.users.update_one({"id": user_id}, {"$unset": {"totp": "", "recovery_codes": ""}})
    A.revoke_all(db, user_id)
    AQ.audit(db, user, "user.reset_2fa", user_id)
    return {"ok": True}


# ----------------------------------------------------------------------------- plans, subscriptions, payments, coupons
@router.get("/plans")
def plans_list(user=Depends(perm("plans.read")), db=Depends(D.get_db)):
    rows = list(db.plans.find({}, {"_id": 0}).sort("sort", 1))
    counts = {r["_id"]: r["n"] for r in db.subscriptions.aggregate([{"$match": {"status": {"$in": ["active", "trialing", "past_due"]}}}, {"$group": {"_id": "$plan_key", "n": {"$sum": 1}}}])}
    for r in rows:
        r["subscribers"] = counts.get(r["key"], 0)
    return {"plans": rows, "entitlements": {k: {"kind": v[0], "label": v[1]} for k, v in P.ENTITLEMENTS.items()}}


class PlanBody(BaseModel):
    key: Optional[str] = Field(None, max_length=31)
    name: Optional[str] = Field(None, max_length=40)
    tagline: Optional[str] = Field(None, max_length=140)
    bullets: Optional[list[str]] = None
    entitlements: Optional[dict] = None
    prices: Optional[list[dict]] = None
    visible: Optional[bool] = None
    highlight: Optional[bool] = None
    sort: Optional[int] = None
    trial_days: Optional[int] = Field(None, ge=0, le=365)
    archived: Optional[bool] = None


@router.post("/plans")
def plan_create(body: PlanBody, user=Depends(perm("plans.write")), db=Depends(D.get_db)):
    with wrap_plan_error():
        return P.create_plan(db, body.key, body.model_dump(exclude_none=True), user["email"])


@router.put("/plans/{key}")
def plan_update(key: str, body: PlanBody, user=Depends(perm("plans.write")), db=Depends(D.get_db)):
    with wrap_plan_error():
        return P.update_plan(db, key, body.model_dump(exclude_unset=True, exclude={"key"}), user["email"])


@router.post("/plans/{key}/sync")
def plan_sync(key: str, user=Depends(perm("billing.write")), db=Depends(D.get_db)):
    with wrap_plan_error():
        p = SB.sync_plan(db, SB.Stripe(db), key)
    AQ.audit(db, user, "plan.sync", key)
    return {"ok": True, "product": p.get("stripe_product_id"), "prices": [{"id": x["id"], "synced": bool(x.get("stripe_price_id"))} for x in p["prices"]]}


@router.get("/subscriptions")
def subscriptions(status: Optional[str] = None, plan: Optional[str] = None, page: int = Query(1, ge=1), limit: int = Query(25, ge=1, le=100),
                  user=Depends(perm("billing.read")), db=Depends(D.get_db)):
    return AQ.list_subscriptions(db, user, status=status, plan=plan, page=page, limit=limit)


@router.post("/subscriptions/{sub_id}/cancel")
def sub_cancel(sub_id: str, at_period_end: bool = True, user=Depends(perm("billing.write")), db=Depends(D.get_db)):
    if not db.subscriptions.find_one({"_id": sub_id}):
        raise D.err(404, "NOT_FOUND")
    with wrap_plan_error():
        SB.cancel_subscription(SB.Stripe(db), db, sub_id, at_period_end, user["email"])
    return {"ok": True, "note": "The status updates when Stripe confirms."}


@router.post("/subscriptions/{sub_id}/resume")
def sub_resume(sub_id: str, user=Depends(perm("billing.write")), db=Depends(D.get_db)):
    if not db.subscriptions.find_one({"_id": sub_id}):
        raise D.err(404, "NOT_FOUND")
    with wrap_plan_error():
        SB.resume_subscription(SB.Stripe(db), db, sub_id, user["email"])
    return {"ok": True}


@router.get("/payments")
def payments(status: Optional[str] = None, user_id: Optional[str] = None, date_from: Optional[str] = None, date_to: Optional[str] = None,
             page: int = Query(1, ge=1), limit: int = Query(25, ge=1, le=100), user=Depends(perm("billing.read")), db=Depends(D.get_db)):
    return AQ.list_payments(db, user, status=status, user_id=user_id, date_from=parse_dt(date_from), date_to=parse_dt(date_to), page=page, limit=limit)


class RefundBody(BaseModel):
    amount_cents: Optional[int] = Field(None, ge=1)
    reason: str = Field(max_length=200)


@router.post("/payments/{payment_id}/refund")
def refund(payment_id: str, body: RefundBody, user=Depends(perm("billing.write")), db=Depends(D.get_db)):
    if S.get(db, "billing.mode") == "live" and not A.can(user, "billing.live_refund"):
        raise D.err(403, "FORBIDDEN", "Only an owner can refund real money.")
    with wrap_plan_error():
        return SB.refund(SB.Stripe(db), db, payment_id, body.amount_cents, body.reason, user["email"])


@router.get("/coupons")
def coupons(user=Depends(perm("billing.read")), db=Depends(D.get_db)):
    return {"coupons": list(db.coupons.find({}, {"_id": 0}).sort("created_at", -1))}


class CouponBody(BaseModel):
    code: str = Field(max_length=30)
    name: str = Field("", max_length=40)
    percent_off: Optional[float] = None
    amount_off_cents: Optional[int] = None
    currency: Optional[str] = Field(None, max_length=3)
    duration: str = "once"
    months: Optional[int] = Field(None, ge=1, le=36)
    max_redemptions: Optional[int] = Field(None, ge=1)
    expires_at: Optional[str] = None


@router.post("/coupons")
def coupon_create(body: CouponBody, user=Depends(perm("billing.write")), db=Depends(D.get_db)):
    with wrap_plan_error():
        c = SB.create_coupon(db, SB.Stripe(db), code=body.code, name=body.name, percent_off=body.percent_off, amount_off_cents=body.amount_off_cents,
                             currency=body.currency, duration=body.duration, months=body.months, max_redemptions=body.max_redemptions,
                             expires_at=parse_dt(body.expires_at), actor=user["email"])
    return {k: v for k, v in c.items() if k != "_id"}


@router.post("/coupons/{code}/deactivate")
def coupon_off(code: str, user=Depends(perm("billing.write")), db=Depends(D.get_db)):
    with wrap_plan_error():
        SB.deactivate_coupon(SB.Stripe(db), db, code, user["email"])
    return {"ok": True}


# ----------------------------------------------------------------------------- e-mail
@router.get("/email/templates")
def templates(user=Depends(perm("email.read")), db=Depends(D.get_db)):
    return {"templates": [{k: v for k, v in E.get_template(db, key).items() if k in ("key", "category", "vars", "subject", "customised")} for key in E.DEFAULTS]}


@router.get("/email/templates/{key}")
def template_get(key: str, user=Depends(perm("email.read")), db=Depends(D.get_db)):
    if key not in E.DEFAULTS:
        raise D.err(404, "NOT_FOUND")
    return E.get_template(db, key)


class TemplateBody(BaseModel):
    subject: str = Field(max_length=150)
    html: str = Field(max_length=20000)
    text: str = Field(max_length=20000)


@router.put("/email/templates/{key}")
def template_save(key: str, body: TemplateBody, user=Depends(perm("email.write")), db=Depends(D.get_db)):
    if key not in E.DEFAULTS:
        raise D.err(404, "NOT_FOUND")
    with wrap_plan_error():
        return E.save_template(db, key, body.subject, body.html, body.text, user["email"])


@router.post("/email/templates/{key}/reset")
def template_reset(key: str, user=Depends(perm("email.write")), db=Depends(D.get_db)):
    E.reset_template(db, key, user["email"])
    return {"ok": True}


@router.get("/email/templates/{key}/preview")
def template_preview(key: str, user=Depends(perm("email.read")), db=Depends(D.get_db)):
    if key not in E.DEFAULTS:
        raise D.err(404, "NOT_FOUND")
    return E.preview(db, key)


@router.post("/email/templates/{key}/test")
def template_test(key: str, user=Depends(perm("email.write")), db=Depends(D.get_db)):
    """Sends the template, with sample values, to the signed-in staff member only."""
    if key not in E.DEFAULTS:
        raise D.err(404, "NOT_FOUND")
    pv = E.preview(db, key)
    r = E._deliver(db, to=user["email"], subject="[TEST] " + pv["subject"], html_body=pv["html"], text_body=pv["text"], category="transactional", template=key, user=user)
    return {"status": r["status"]}


@router.get("/email/suppressions")
def suppressions(page: int = Query(1, ge=1), user=Depends(perm("email.read")), db=Depends(D.get_db)):
    return AQ.paged(db, "email_suppressions", {}, [("at", -1)], page, 50, pii=A.can(user, "users.pii"))


@router.delete("/email/suppressions/{email}")
def unsuppress(email: str, user=Depends(perm("email.write")), db=Depends(D.get_db)):
    E.unsuppress(db, email, user["email"])
    return {"ok": True}


@router.get("/email/campaigns")
def campaigns(user=Depends(perm("email.read")), db=Depends(D.get_db)):
    return AQ.paged(db, "email_campaigns", {}, [("created_at", -1)], 1, 50, proj={"html": 0})


class CampaignBody(BaseModel):
    subject: str = Field(max_length=150)
    html: str = Field(max_length=50000)
    segment: str = Field("all", max_length=10)


@router.post("/email/campaigns")
def campaign_create(body: CampaignBody, user=Depends(perm("email.write")), db=Depends(D.get_db)):
    with wrap_plan_error():
        cid = E.create_campaign(db, body.subject, body.html, body.segment, user["email"])
    AQ.audit(db, user, "email.campaign.create", cid)
    return {"id": cid}


@router.post("/email/campaigns/{cid}/send")
def campaign_send(cid: str, user=Depends(perm("email.write")), db=Depends(D.get_db)):
    with wrap_plan_error():
        return E.send_campaign(db, cid, user["email"])


# ----------------------------------------------------------------------------- logs, health, security
@router.get("/logs/{kind}")
def logs(kind: str, request: Request, page: int = Query(1, ge=1), limit: int = Query(50, ge=1, le=100), since_hours: Optional[int] = Query(None, ge=1, le=24 * 90),
         user=Depends(perm("logs.read")), db=Depends(D.get_db)):
    since = utcnow() - timedelta(hours=since_hours) if since_hours else None
    flt = {k: v for k, v in request.query_params.items() if k not in ("page", "limit", "since_hours")}
    return AQ.list_logs(db, user, kind, flt, page, limit, since)


@router.get("/health")
def health(user=Depends(perm("logs.read")), db=Depends(D.get_db)):
    return AQ.health(db)


@router.get("/security")
def security_overview(user=Depends(perm("security.read")), db=Depends(D.get_db)):
    return AQ.security_overview(db)


# ----------------------------------------------------------------------------- keys
KEYS = {
    "pitchapi": {"label": "PitchAPI", "re": r"^pk_(live|test)_[A-Za-z0-9]{6,}$", "env": "PITCH_KEY", "hint": "starts with pk_live_ or pk_test_"},
    "apifootball": {"label": "API-Football key", "re": r"^[A-Za-z0-9]{20,64}$", "env": "APIFOOTBALL_KEY", "hint": "is the 32-character key from your API-Football dashboard"},
    "stripe_secret": {"label": "Stripe secret key", "re": SB.KEY_RE.pattern, "env": "STRIPE_SECRET_KEY", "hint": "starts with sk_test_ / sk_live_ (or a restricted rk_ key)"},
    "stripe_webhook": {"label": "Stripe webhook signing secret", "re": SB.WH_RE.pattern, "env": "STRIPE_WEBHOOK_SECRET", "hint": "starts with whsec_"},
    "resend": {"label": "Resend API key", "re": r"^re_[A-Za-z0-9_]{10,}$", "env": "RESEND_API_KEY", "hint": "starts with re_"},
    "resend_webhook": {"label": "Resend webhook signing secret", "re": r"^whsec_[A-Za-z0-9+/=]{10,}$", "env": "RESEND_WEBHOOK_SECRET", "hint": "starts with whsec_"},
    "postmark": {"label": "Postmark server token", "re": T.PROVIDERS["postmark"]["re"], "env": "POSTMARK_SERVER_TOKEN", "hint": T.PROVIDERS["postmark"]["hint"]},
    "sendgrid": {"label": "SendGrid API key", "re": T.PROVIDERS["sendgrid"]["re"], "env": "SENDGRID_API_KEY", "hint": T.PROVIDERS["sendgrid"]["hint"]},
    "brevo": {"label": "Brevo API key", "re": T.PROVIDERS["brevo"]["re"], "env": "BREVO_API_KEY", "hint": T.PROVIDERS["brevo"]["hint"]},
    "smtp_password": {"label": "SMTP password", "re": T.PROVIDERS["smtp"]["re"], "env": "SMTP_PASSWORD", "hint": T.PROVIDERS["smtp"]["hint"]},
    "mailchimp": {"label": "Mailchimp API key", "re": INT.AUDIENCE["mailchimp"]["re"], "env": "MAILCHIMP_API_KEY", "hint": INT.AUDIENCE["mailchimp"]["hint"]},
    "mailerlite": {"label": "MailerLite API token", "re": INT.AUDIENCE["mailerlite"]["re"], "env": "MAILERLITE_API_KEY", "hint": INT.AUDIENCE["mailerlite"]["hint"]},
    "sportapi": {"label": "SportAPI key", "re": r"^[A-Za-z0-9_\-]{16,128}$", "env": "SPORTAPI_KEY", "hint": "is the key from your SportAPI dashboard (16 to 128 letters, digits, - or _)"},
}


def key_view(db, provider):
    import os
    v = security.public_key_view(db, provider)
    env = bool(os.environ.get(KEYS[provider]["env"]))
    return {"provider": provider, "label": KEYS[provider]["label"], "hint": KEYS[provider]["hint"], **v,
            "source": "admin" if v["set"] else ("environment" if env else "none")}


@router.get("/keys")
def keys(user=Depends(perm("settings.read")), db=Depends(D.get_db)):
    return {"keys": [key_view(db, p) for p in KEYS]}


class KeyBody(BaseModel):
    key: str = Field(max_length=300)


@router.put("/keys/{provider}")
def key_save(provider: str, body: KeyBody, user=Depends(perm("keys.write")), db=Depends(D.get_db)):
    if provider not in KEYS:
        raise D.err(404, "NOT_FOUND")
    k = body.key.strip()
    if not re.fullmatch(KEYS[provider]["re"], k):
        raise D.err(400, "BAD_KEY", f"A {KEYS[provider]['label']} {KEYS[provider]['hint']}.")
    if provider == "stripe_secret" and k.startswith(("sk_live_", "rk_live_")) != (S.get(db, "billing.mode") == "live"):
        raise D.err(409, "MODE_MISMATCH", f"Billing mode is '{S.get(db, 'billing.mode')}'. Change the mode first, or use the matching key.")
    security.save_provider_key(db, provider, k)
    if provider == "pitchapi":
        S.reset(db, "ingest.paused_reason", actor=user["email"])
        # BOTH breakers. This cleared only PitchAPI's, so the one admin escape hatch for "the provider
    # cut us off" could not clear the breaker of the only provider in use (docs/89).
    db.job_locks.delete_many({"_id": {"$in": ["pitch_breaker", "af_breaker"]}})
    if provider == "apifootball":
        # A rejected key pauses ingest and trips the breaker (apifootball._unwrap). Saving a new
        # one is the owner saying "try again", so both have to clear or the new key never gets used.
        S.reset(db, "ingest.paused_reason", actor=user["email"])
        db.job_locks.delete_one({"_id": "af_breaker"})
    AQ.audit(db, user, "key.save", provider)                       # the key itself is never logged
    return key_view(db, provider)


@router.delete("/keys/{provider}")
def key_delete(provider: str, user=Depends(perm("keys.write")), db=Depends(D.get_db)):
    if provider not in KEYS:
        raise D.err(404, "NOT_FOUND")
    db.provider_keys.delete_one({"provider": provider})
    AQ.audit(db, user, "key.delete", provider)
    return key_view(db, provider)


@router.post("/keys/{provider}/test")
def key_test(provider: str, user=Depends(perm("settings.write")), db=Depends(D.get_db)):
    if provider not in KEYS:
        raise D.err(404, "NOT_FOUND")
    try:
        if provider == "pitchapi":
            PitchClient(db).fetch("/v1/leagues", ttl=timedelta(minutes=1), purpose="key_test", force=True)
            return {"ok": True}
        if provider == "apifootball":
            # /status is the right test and the only free one: it reports the plan and today's
            # usage without spending a call, so testing a key never costs the budget it reports on.
            import apifootball as AF
            st = AF.Client(db).status()
            sub, req = st.get("subscription") or {}, st.get("requests") or {}
            return {"ok": bool(sub.get("active", True)), "plan": sub.get("plan"), "ends": sub.get("end"),
                    "used_today": req.get("current"), "limit_day": req.get("limit_day")}
        if provider == "stripe_secret":
            b = SB.Stripe(db).req("GET", "/balance")
            return {"ok": True, "livemode": bool(b.get("livemode"))}
        if provider == "resend":
            key = security.get_provider_key(db, "resend", "RESEND_API_KEY")
            if not key:
                return {"ok": False, "code": "no_key"}
            with E._FACTORY() as c:
                r = c.get(f"{E.API}/domains", headers={"Authorization": f"Bearer {key}"})
            if r.status_code == 200:
                return {"ok": True, "domains": [{"name": d.get("name"), "status": d.get("status")} for d in r.json().get("data", [])]}
            if r.status_code == 401 and "restricted" in r.text.lower():
                return {"ok": True, "note": "This key can send e-mail but cannot list domains. That is fine."}
            return {"ok": False, "code": r.status_code}
        if provider in ("postmark", "sendgrid", "brevo", "smtp_password"):
            return T.test_key(db, {"smtp_password": "smtp"}.get(provider, provider))
        if provider in ("mailchimp", "mailerlite"):
            return INT.test_audience(db, provider)
        # webhook secrets cannot be tested without a real event: show when the last one arrived
        last = db.webhook_events.find_one({"provider": "stripe" if provider == "stripe_webhook" else "resend"}, sort=[("received_at", -1)])
        return {"ok": bool(security.get_provider_key(db, provider, KEYS[provider]["env"])), "last_event_at": last and last.get("received_at")}
    except PitchError as e:
        return {"ok": False, "code": e.code, "status": e.status}
    except (SB.StripeError, SB.StripeConfigError) as e:
        return {"ok": False, "code": getattr(e, "code", "config"), "message": str(e)[:120]}
    except httpx.HTTPError as e:
        return {"ok": False, "code": type(e).__name__}


# ----------------------------------------------------------------------------- settings, jobs
@router.get("/settings")
def settings_list(user=Depends(perm("settings.read")), db=Depends(D.get_db)):
    cur = {r["key"]: r for r in db.settings.find({}, {"_id": 0, "key": 1, "value": 1, "updated_by": 1, "updated_at": 1})}
    return [{**r, "value": cur[r["key"]]["value"] if r["key"] in cur else r["default"], "is_default": r["key"] not in cur,
             "updated_by": cur.get(r["key"], {}).get("updated_by"), "updated_at": cur.get(r["key"], {}).get("updated_at"),
             "owner_only": r["key"].startswith(OWNER_ONLY_SETTINGS)} for r in S.registry().values()]


class SetValue(BaseModel):
    value: object


@router.put("/settings/{key}")
def settings_put(key: str, body: SetValue, user=Depends(perm("settings.write")), db=Depends(D.get_db)):
    if key.startswith(OWNER_ONLY_SETTINGS) and not A.can(user, "keys.write"):
        raise D.err(403, "FORBIDDEN", "Only an owner can change this setting.")
    try:
        if key in ("email.smtp_host", "email.smtp_port"):
            if key not in S.registry():
                raise KeyError(key)
            if T.set_smtp_target(db, user["email"], **{key.split("_", 1)[1]: body.value}):
                AQ.audit(db, user, "key.delete", "smtp_password", detail="SMTP host changed")
        else:
            S.put(db, key, body.value, actor=user["email"])
    except KeyError:
        raise D.err(404, "NOT_FOUND", "Unknown setting.")
    except ValueError as e:
        raise D.err(409 if "locked" in str(e) else 400, "BAD_VALUE", str(e))
    import security_mw
    security_mw.clear_cache()
    return {"ok": True}


@router.delete("/settings/{key}")
def settings_reset(key: str, user=Depends(perm("settings.write")), db=Depends(D.get_db)):
    if key not in S.registry():
        raise D.err(404, "NOT_FOUND")
    if key.startswith(OWNER_ONLY_SETTINGS) and not A.can(user, "keys.write"):
        raise D.err(403, "FORBIDDEN", "Only an owner can change this setting.")
    S.reset(db, key, actor=user["email"])
    return {"ok": True}


@router.get("/settings/{key}/history")
def settings_history(key: str, user=Depends(perm("settings.read")), db=Depends(D.get_db)):
    return {"history": [{k: v for k, v in r.items() if k != "_id"} for r in db.settings_history.find({"key": key}).sort("at", -1).limit(30)]}


@router.post("/breaker/close")
def breaker_close(user=Depends(perm("jobs.run")), db=Depends(D.get_db)):
    db.job_locks.delete_one({"_id": "pitch_breaker"})
    AQ.audit(db, user, "breaker.close", "pitch_breaker")
    return {"ok": True}


@router.get("/brain")
def brain_layers(user=Depends(perm("logs.read")), db=Depends(D.get_db)):
    return AQ.brain_status(db)


@router.post("/calibration/rollback")
def calibration_rollback(user=Depends(perm("settings.write")), db=Depends(D.get_db)):
    import calibration as CAL
    out = CAL.rollback(db)
    AQ.audit(db, user, "calibration.rollback", None)
    return out


@router.get("/clubs")
def clubs(user=Depends(perm("logs.read")), db=Depends(D.get_db)):
    """Enabled leagues (with our internal number) and their clubs, for the Availability and SportAPI screens."""
    lgs = list(db.leagues.find({"enabled": True}, {"_id": 0, "iid": 1, "id": 1, "name": 1, "country": 1}).sort("name", 1))
    teams = {}
    for t in db.teams.find({"league_iid": {"$in": [l["iid"] for l in lgs]}}, {"_id": 0, "id": 1, "iid": 1, "name": 1, "league_iid": 1}).sort("name", 1):
        teams.setdefault(t["league_iid"], []).append({"id": t["id"], "iid": t["iid"], "name": t["name"]})
    return {"leagues": [{**l, "teams": teams.get(l["iid"], [])} for l in lgs]}


@router.get("/availability")
def availability_list(team: str, user=Depends(perm("logs.read")), db=Depends(D.get_db)):
    """One club's squad with who is out or doubtful (docs/22)."""
    import queries as Q
    tid = Q.iid_of(db, "teams", team)
    if not tid:
        raise D.err(404, "NOT_FOUND", "No such team.")
    rows = {r["player_iid"]: r for r in db.availability.find({"team_iid": tid}, {"_id": 0})}
    players = Q.attach_images(db, "players", list(db.players.find({"team_iid": tid}, {"_id": 0, "iid": 1, "id": 1, "name": 1, "pos": 1}).sort("name", 1)))
    return {"players": [{"id": p["id"], "name": p.get("name") or "Unnamed player", "pos": p.get("pos"), "image": p.get("image"),
                         **({k: rows[p["iid"]].get(k) for k in ("status", "source", "reason", "until", "updated_at", "by")} if p["iid"] in rows else {"status": "available"})}
                        for p in players]}


class AvailabilityBody(BaseModel):
    player_id: str = Field(max_length=64)
    status: str = Field(pattern=r"^(out|doubtful|available)$")
    reason: str = Field(default="", max_length=80)
    until: Optional[datetime] = None


@router.put("/availability")
def availability_set(body: AvailabilityBody, user=Depends(perm("jobs.run")), db=Depends(D.get_db)):
    import availability as AV
    import queries as Q
    pid = Q.iid_of(db, "players", body.player_id)
    if not pid:
        raise D.err(404, "NOT_FOUND", "No such player.")
    reason = body.reason.strip()
    import textguard
    if reason and textguard.scan(reason):
        raise D.err(400, "BAD_TEXT", "Please reword the reason: analysis only, no betting words.")
    until = body.until.astimezone(timezone.utc) if body.until and body.until.tzinfo else (body.until.replace(tzinfo=timezone.utc) if body.until else None)
    if until and until < datetime.now(timezone.utc):
        raise D.err(400, "BAD_DATE", "The end date is in the past.")
    row = AV.set_status(db, pid, body.status, source="admin", reason=reason, until=until, actor=user["email"])
    p = db.players.find_one({"iid": pid}, {"team_iid": 1})
    if p and p.get("team_iid"):                       # the club's next matches re-run on the next tick with the new status
        db.matches.update_many({"status": "scheduled", "$or": [{"home_iid": p["team_iid"]}, {"away_iid": p["team_iid"]}]},
                               {"$set": {"lineups_at": datetime.now(timezone.utc)}})
    AQ.audit(db, user, "availability.set", body.player_id, {"status": body.status})
    return {k: v for k, v in row.items() if k != "_id"}


class CalendarRow(BaseModel):
    team_iid: int
    kickoff: datetime
    comp: str = Field(pattern=r"^[a-z_]{2,24}$")
    stage: str = Field(default="", max_length=60)


@router.post("/calendar/import")
def calendar_import(rows: list[CalendarRow], user=Depends(perm("jobs.run")), db=Depends(D.get_db)):
    """Cups and European fixtures the league feed does not carry. Idempotent."""
    if len(rows) > 5000:
        raise D.err(400, "TOO_MANY", "At most 5000 rows per import.")
    known = set(S.get(db, "context.importance"))
    bad = sorted({r.comp for r in rows} - known - {"league"})
    if bad:
        raise D.err(400, "UNKNOWN_COMPETITION", "Unknown competition key: " + ", ".join(bad) + ". Add it to context.importance first.")
    clean = [{"team_iid": r.team_iid, "comp": r.comp, "stage": r.stage,
              "kickoff": r.kickoff.astimezone(timezone.utc).replace(tzinfo=None) if r.kickoff.tzinfo else r.kickoff} for r in rows]
    out = B.import_calendar(db, clean, source=user["email"])
    AQ.audit(db, user, "calendar.import", str(out["rows"]))
    return out


@router.post("/jobs/run")
def jobs_run(job: str, user=Depends(perm("jobs.run")), db=Depends(D.get_db)):
    if job not in jobs.MANUAL:
        raise D.err(400, "UNKNOWN_JOB", "Unknown job.")
    db.job_requests.insert_one({"job": job, "status": "pending", "requested_at": utcnow(), "requested_by": user["email"]})
    AQ.audit(db, user, "job.request", job)
    return {"queued": True}


# ----------------------------------------------------------------------------- announcements, inbox, content
@router.get("/announcements")
def ann_list(user=Depends(perm("content.write")), db=Depends(D.get_db)):
    return AQ.paged(db, "announcements", {}, [("created_at", -1)], 1, 50)


class AnnBody(BaseModel):
    text: str = Field(max_length=240)
    level: str = "info"
    audience: str = "all"
    starts_at: Optional[str] = None
    ends_at: Optional[str] = None
    active: bool = True


@router.post("/announcements")
def ann_create(body: AnnBody, user=Depends(perm("content.write")), db=Depends(D.get_db)):
    return {"id": AQ.save_announcement(db, user, None, body.text, body.level, body.audience, parse_dt(body.starts_at), parse_dt(body.ends_at), body.active)}


@router.put("/announcements/{aid}")
def ann_update(aid: str, body: AnnBody, user=Depends(perm("content.write")), db=Depends(D.get_db)):
    return {"id": AQ.save_announcement(db, user, aid, body.text, body.level, body.audience, parse_dt(body.starts_at), parse_dt(body.ends_at), body.active)}


@router.delete("/announcements/{aid}")
def ann_delete(aid: str, user=Depends(perm("content.write")), db=Depends(D.get_db)):
    from bson import ObjectId
    db.announcements.delete_one({"_id": ObjectId(aid)})
    AQ.audit(db, user, "announcement.delete", aid)
    return {"ok": True}


@router.get("/inbox")
def inbox(status: Optional[str] = None, page: int = Query(1, ge=1), user=Depends(perm("users.read")), db=Depends(D.get_db)):
    return AQ.paged(db, "contact_messages", {"status": status} if status else {}, [("at", -1)], page, 25, pii=A.can(user, "users.pii"))


class InboxBody(BaseModel):
    status: str = Field(max_length=10)
    note: Optional[str] = Field(None, max_length=500)


@router.put("/inbox/{mid}")
def inbox_update(mid: str, body: InboxBody, user=Depends(perm("inbox.write")), db=Depends(D.get_db)):
    AQ.update_contact(db, user, mid, body.status, body.note)
    return {"ok": True}


class PageBody(BaseModel):
    title: str = Field(max_length=120)
    body_md: str = Field(max_length=60000)


@router.get("/content")
def content_list(user=Depends(perm("content.write")), db=Depends(D.get_db)):
    return {"pages": list(db.content_pages.find({}, {"_id": 0, "slug": 1, "title": 1, "updated_at": 1, "starter": 1}))}


@router.put("/content/{slug}")
def content_put(slug: str, body: PageBody, user=Depends(perm("content.write")), db=Depends(D.get_db)):
    if not re.fullmatch(r"[a-z0-9-]{2,40}", slug):
        raise D.err(400, "BAD_SLUG")
    import textguard
    try:
        textguard.require_clean("Page", [body.title, body.body_md])
    except ValueError as e:
        raise D.err(400, "BANNED_WORDS", str(e))
    db.content_pages.update_one({"slug": slug}, {"$set": {"title": body.title, "body_md": body.body_md, "updated_at": utcnow(), "updated_by": user["email"]},
                                                 "$unset": {"starter": ""}}, upsert=True)      # saving = reviewed (docs/36 C2)
    AQ.audit(db, user, "content.save", slug)
    return {"ok": True}
