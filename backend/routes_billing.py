"""routes_billing.py -- pricing, checkout, billing portal, and the two webhooks (Stripe, Resend).

Nothing here touches a card. Checkout and the portal are Stripe-hosted pages. The webhooks are the only
way our records of "who paid" change, and both are signature-checked before any work is done.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

import analytics as AN
import deps as D
import emailer as E
import plans as P
import ratelimit as RL
import security
import settings_store as S
import stripe_billing as SB

router = APIRouter(prefix="/api")
log = logging.getLogger("billing")


def make_notify(db):
    def notify(kind, user, ctx):
        v = dict(ctx)
        if kind in ("payment_failed", "trial_ending"):
            v["link"] = E.base_url() + "/account/billing"
        E.send_template(db, kind, to=user["email"], user=user, vars=v, idem=f"{kind}-{user['id']}-{ctx.get('invoice_url') or ctx.get('date') or ctx.get('plan') or ''}"[:200])
    return notify


@router.get("/plans")
def plans(db=Depends(D.get_db)):
    return {"billing_enabled": bool(S.get(db, "features.billing")), "currency": S.get(db, "plans.currency"), "plans": P.public_plans(db)}


@router.get("/account/billing")
def billing_status(user=Depends(D.require_user), db=Depends(D.get_db)):
    ep = P.effective_plan(db, user)
    sub = P.live_subscription(db, user["id"])
    pays = [{"id": p["_id"], "amount_cents": p.get("amount_paid"), "currency": p.get("currency"), "status": p.get("status"),
             "at": p.get("created_at"), "invoice_url": p.get("invoice_url"), "number": p.get("number")}
            for p in db.payments.find({"user_id": user["id"]}).sort("created_at", -1).limit(12)]
    return {"billing_enabled": bool(S.get(db, "features.billing")), "plan": {k: v for k, v in ep.items() if k != "entitlements"},
            "entitlements": ep["entitlements"], "can_use_portal": bool(user.get("stripe_customer_id")),
            "subscription": sub and {"status": sub["status"], "plan": sub["plan_key"], "interval": sub.get("interval"), "amount_cents": sub.get("amount_cents"),
                                     "currency": sub.get("currency"), "period_end": sub.get("current_period_end"), "cancel_at_period_end": bool(sub.get("cancel_at_period_end")),
                                     "trial_end": sub.get("trial_end")},
            "comp": user.get("comp") and {"plan": user["comp"]["plan_key"], "until": user["comp"].get("until")}, "payments": pays}


class CheckoutBody(BaseModel):
    plan: str = Field(max_length=31)
    price: str = Field(max_length=31)


def _stripe(db):
    try:
        return SB.Stripe(db)
    except SB.StripeConfigError as e:
        log.warning("stripe config: %s", e)
        raise D.err(503, "BILLING_UNAVAILABLE", "Payments are not available right now.")


def _guard_billing(db):
    if not S.get(db, "features.billing"):
        raise D.err(409, "BILLING_OFF", "Paid plans are not open yet.")


@router.post("/billing/checkout")
def checkout(body: CheckoutBody, user=Depends(D.require_user), db=Depends(D.get_db)):
    _guard_billing(db)
    RL.check(db, f"checkout:{user['id']}", 10, 3600)
    if not user.get("email_verified"):
        raise D.err(403, "EMAIL_NOT_VERIFIED", "Confirm your e-mail before you subscribe.")
    st = _stripe(db)
    try:
        out = SB.create_checkout(db, st, user, body.plan, body.price)
    except P.PlanError as e:
        raise D.err(409 if e.code == "ALREADY_SUBSCRIBED" else 400, e.code, e.message)
    except SB.StripeError as e:
        log.error("stripe checkout failed: %s %s", e.status, e.code)
        raise D.err(502, "BILLING_ERROR", "We could not start checkout. Try again in a minute.")
    AN.track(db, "checkout_started", user_id=user["id"], server=True, props={"plan": body.plan, "price": body.price})
    return {"url": out["url"]}


@router.post("/billing/portal")
def portal(user=Depends(D.require_user), db=Depends(D.get_db)):
    _guard_billing(db)
    RL.check(db, f"portal:{user['id']}", 20, 3600)
    st = _stripe(db)
    try:
        return SB.create_portal(db, st, user)
    except P.PlanError as e:
        raise D.err(400, e.code, e.message)
    except SB.StripeError as e:
        log.error("stripe portal failed: %s %s", e.status, e.code)
        raise D.err(502, "BILLING_ERROR", "We could not open the billing page. Try again in a minute.")


@router.post("/webhooks/stripe")
async def stripe_webhook(request: Request, db=Depends(D.get_db)):
    raw = await request.body()
    secret = await run_in_threadpool(security.get_provider_key, db, "stripe_webhook", "STRIPE_WEBHOOK_SECRET")
    if not secret:
        raise D.err(503, "NOT_CONFIGURED", "Webhook secret not set.")
    try:
        event = SB.verify_webhook(raw, request.headers.get("stripe-signature", ""), secret)
    except (SB.WebhookError, ValueError):
        raise D.err(400, "BAD_SIGNATURE", "Signature check failed.")
    try:
        result = await run_in_threadpool(SB.handle_event, db, event, make_notify(db))
    except Exception as e:                       # includes WebhookProblem: Stripe will retry, and the admin sees the failure
        log.error("stripe event %s failed: %s", event.get("id"), e)
        raise D.err(500, "EVENT_FAILED", "Could not apply the event.")
    return {"received": True, "result": result}


@router.post("/webhooks/resend")
async def resend_webhook(request: Request, db=Depends(D.get_db)):
    raw = await request.body()
    secret = await run_in_threadpool(security.get_provider_key, db, "resend_webhook", "RESEND_WEBHOOK_SECRET")
    if not secret:
        raise D.err(503, "NOT_CONFIGURED", "Webhook secret not set.")
    try:
        event = E.verify_svix(raw, request.headers, secret)
    except (E.WebhookError, ValueError):
        raise D.err(400, "BAD_SIGNATURE", "Signature check failed.")
    result = await run_in_threadpool(E.handle_resend_event, db, event, request.headers["svix-id"])
    return {"received": True, "result": result}
