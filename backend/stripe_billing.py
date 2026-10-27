"""stripe_billing.py -- Stripe over plain HTTPS (httpx). No Stripe SDK, no card data on our server.

Money flow: the browser is sent to a Stripe-hosted Checkout page. Stripe takes the card. Stripe tells us
what happened by webhook. We only store status, ids and amounts. Card changes, invoices and cancel
happen in Stripe's hosted billing portal.

Safety rules in this file:
  * the secret key prefix must match billing.mode (test keys in test mode, live keys in live mode)
  * every POST that creates something carries an Idempotency-Key, so a double click makes one object
  * webhooks: HMAC-SHA256 signature check, 5-minute tolerance, constant-time compare, then event-id dedupe
  * out-of-order events are ignored by comparing event time to the last one applied
  * a webhook we cannot map (unknown price, unknown user) FAILS with 500, so Stripe retries and an admin sees it

NOT VERIFIED against a live Stripe account (check with Stripe test mode before launch):
  * newer API versions moved current_period_end onto the subscription ITEM, and the invoice's subscription
    id under invoice.parent.subscription_details. We read both places.
  * newer API versions changed promotion-code creation to promotion[type]=coupon. We try the new form,
    then the old one.
  * invoices may not carry payment_intent in the newest versions. Then refunds need the charge id.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import re
import time
from urllib.parse import urlencode
from datetime import datetime, timedelta, timezone

import httpx

import emailer
import plans as P
import security
import settings_store as S

API = "https://api.stripe.com/v1"
_FACTORY = lambda: httpx.Client(timeout=25)
_SLEEP = time.sleep
KEY_RE = re.compile(r"^(sk|rk)_(test|live)_[A-Za-z0-9]{10,}$")
WH_RE = re.compile(r"^whsec_[A-Za-z0-9]{10,}$")


def set_http_factory(f):
    global _FACTORY
    _FACTORY = f


def set_sleep(f):
    global _SLEEP
    _SLEEP = f


def utcnow():
    return datetime.now(timezone.utc)


def ts(n):
    return datetime.fromtimestamp(n, tz=timezone.utc) if n else None


class StripeError(Exception):
    def __init__(self, status, code="", message="", param=""):
        super().__init__(f"{status} {code} {message}")
        self.status, self.code, self.message, self.param = status, code, message, param


class StripeConfigError(Exception):
    pass


class WebhookError(Exception):
    pass


class WebhookProblem(Exception):
    """We understood the event but could not apply it. The route answers 500 so Stripe retries."""


def encode(params, prefix="") -> list[tuple[str, str]]:
    """Stripe wants form fields: a[b]=1, items[0][price]=x, flag=true."""
    out = []
    if isinstance(params, dict):
        for k, v in params.items():
            out += encode(v, f"{prefix}[{k}]" if prefix else str(k))
    elif isinstance(params, (list, tuple)):
        for i, v in enumerate(params):
            out += encode(v, f"{prefix}[{i}]")
    elif params is not None:
        out.append((prefix, "true" if params is True else "false" if params is False else str(params)))
    return out


class Stripe:
    def __init__(self, db):
        self.db = db
        self.key = security.get_provider_key(db, "stripe_secret", "STRIPE_SECRET_KEY")
        if not self.key:
            raise StripeConfigError("No Stripe secret key. Add it in Admin > Keys.")
        mode = S.get(db, "billing.mode")
        live = self.key.startswith(("sk_live_", "rk_live_"))
        if (mode == "live") != live:
            raise StripeConfigError(f"Billing mode is '{mode}' but the key is a {'live' if live else 'test'} key. Fix one of them.")
        self.version = S.get(db, "billing.stripe_api_version") or None

    def req(self, method: str, path: str, data: dict | None = None, idem: str | None = None, params: dict | None = None) -> dict:
        headers = {"Authorization": f"Bearer {self.key}", "User-Agent": "forecast-app/1.0"}
        if self.version:
            headers["Stripe-Version"] = self.version
        if idem:
            headers["Idempotency-Key"] = idem[:255]
        body = urlencode(encode(data)) if data else None
        if body:
            headers["Content-Type"] = "application/x-www-form-urlencoded"
        last = None
        for attempt in range(3):
            try:
                with _FACTORY() as c:
                    r = c.request(method, API + path, content=body, params=params, headers=headers)
            except httpx.HTTPError as e:
                last = StripeError(0, "network", type(e).__name__)
            else:
                if r.status_code < 300:
                    return r.json()
                try:
                    e = r.json().get("error", {})
                except Exception:
                    e = {}
                last = StripeError(r.status_code, e.get("code") or e.get("type", ""), e.get("message", ""), e.get("param", ""))
                if r.status_code not in (429, 500, 502, 503, 504):
                    raise last
            if method != "GET" and not idem:           # never retry a create without an idempotency key
                raise last
            _SLEEP(0.5 * (2 ** attempt))
        raise last


def abs_url(path: str) -> str:
    return path if path.startswith("https://") or path.startswith("http://") else emailer.base_url() + "/" + path.lstrip("/")


# ----------------------------------------------------------------------------- customers, checkout, portal
def ensure_customer(db, st: Stripe, user: dict) -> str:
    if user.get("stripe_customer_id"):
        return user["stripe_customer_id"]
    c = st.req("POST", "/customers", {"email": user["email"], "metadata": {"user_id": user["id"]}}, idem=f"cust-{user['id']}")
    db.users.update_one({"id": user["id"]}, {"$set": {"stripe_customer_id": c["id"]}})
    user["stripe_customer_id"] = c["id"]
    return c["id"]


def create_checkout(db, st: Stripe, user: dict, plan_key: str, price_id: str) -> dict:
    plan = P.get_plan(db, plan_key)
    if not plan or plan.get("archived") or plan.get("is_default"):
        raise P.PlanError("BAD_PLAN", "That plan is not for sale.")
    price = next((x for x in plan.get("prices", []) if x["id"] == price_id and x.get("active", True)), None)
    if not price:
        raise P.PlanError("BAD_PRICE", "That price is not available.")
    if P.live_subscription(db, user["id"]):
        raise P.PlanError("ALREADY_SUBSCRIBED", "You already have a plan. Use the billing portal to change it.")
    if not price.get("stripe_price_id") or plan.get("stripe_mode") not in (None, S.get(db, "billing.mode")):
        sync_plan(db, st, plan_key)
        plan = P.get_plan(db, plan_key)
        price = next(x for x in plan["prices"] if x["id"] == price_id)
    cust = ensure_customer(db, st, user)
    ok_url = abs_url(S.get(db, "billing.success_url"))
    ok_url += ("&" if "?" in ok_url else "?") + "session_id={CHECKOUT_SESSION_ID}"
    sub_data = {"metadata": {"user_id": user["id"], "plan_key": plan_key}}
    trial = plan.get("trial_days") if plan.get("trial_days") is not None else S.get(db, "plans.trial_days")
    if trial and int(trial) > 0 and not user.get("had_trial"):
        sub_data["trial_period_days"] = int(trial)
    data = {"mode": "subscription", "customer": cust, "client_reference_id": user["id"],
            "line_items": [{"price": price["stripe_price_id"], "quantity": 1}],
            "success_url": ok_url, "cancel_url": abs_url(S.get(db, "billing.cancel_url")),
            "allow_promotion_codes": bool(S.get(db, "billing.allow_promo_codes")), "subscription_data": sub_data,
            "metadata": {"user_id": user["id"], "plan_key": plan_key}}
    if S.get(db, "billing.automatic_tax"):
        data["automatic_tax"] = {"enabled": True}
        data["customer_update"] = {"address": "auto"}
    # one open checkout per person per price per minute: a double click returns the same session
    s = st.req("POST", "/checkout/sessions", data, idem=f"co-{user['id']}-{plan_key}-{price_id}-{int(time.time() // 60)}")
    return {"url": s["url"], "id": s["id"]}


def create_portal(db, st: Stripe, user: dict) -> dict:
    if not user.get("stripe_customer_id"):
        raise P.PlanError("NO_CUSTOMER", "You have no billing account yet.")
    s = st.req("POST", "/billing_portal/sessions", {"customer": user["stripe_customer_id"], "return_url": abs_url(S.get(db, "billing.portal_return_url"))})
    return {"url": s["url"]}


# ----------------------------------------------------------------------------- plan sync
def sync_plan(db, st: Stripe, plan_key: str) -> dict:
    """Make Stripe's product and prices match our plan. Stripe prices cannot be edited, so a price change
    makes a NEW price and retires the old one. People already subscribed keep the price they signed up at."""
    plan = P.get_plan(db, plan_key)
    if not plan or plan.get("is_default"):
        raise P.PlanError("BAD_PLAN", "Nothing to sync for this plan.")
    mode = S.get(db, "billing.mode")
    if plan.get("stripe_mode") not in (None, mode):
        # Test and live Stripe have separate products and prices. Ids from the other mode are useless here.
        plan = _forget_ids(db, plan)
    pid = plan.get("stripe_product_id")
    if not pid:
        pid = st.req("POST", "/products", {"name": plan["name"], "metadata": {"plan_key": plan_key}}, idem=f"prod-{plan_key}")["id"]
    elif plan.get("stripe_synced_name") != plan["name"]:
        st.req("POST", f"/products/{pid}", {"name": plan["name"]})
    prices = []
    for x in plan.get("prices", []):
        x = dict(x)
        old = x.pop("retired_stripe_price_id", None)
        if old:
            st.req("POST", f"/prices/{old}", {"active": False})
        if x.get("active", True) and not x.get("stripe_price_id"):
            idem = f"price-{plan_key}-{x['id']}-{x['amount_cents']}-{x['currency']}-{x['interval']}"
            x["stripe_price_id"] = st.req("POST", "/prices", {"product": pid, "unit_amount": x["amount_cents"], "currency": x["currency"],
                                                              "recurring": {"interval": x["interval"]}, "nickname": f"{plan['name']} {x['interval']}ly",
                                                              "metadata": {"plan_key": plan_key, "price_id": x["id"]}}, idem=idem)["id"]
        elif not x.get("active", True) and x.get("stripe_price_id"):
            st.req("POST", f"/prices/{x['stripe_price_id']}", {"active": False})
        prices.append(x)
    db.plans.update_one({"key": plan_key}, {"$set": {"stripe_product_id": pid, "stripe_synced_name": plan["name"], "stripe_mode": mode, "prices": prices, "synced_at": utcnow()}})
    return P.get_plan(db, plan_key)


def _forget_ids(db, plan):
    prices = [{k: v for k, v in x.items() if k not in ("stripe_price_id", "retired_stripe_price_id")} for x in plan.get("prices", [])]
    db.plans.update_one({"key": plan["key"]}, {"$set": {"prices": prices}, "$unset": {"stripe_product_id": "", "stripe_synced_name": ""}})
    return P.get_plan(db, plan["key"])


# ----------------------------------------------------------------------------- admin actions
def cancel_subscription(st: Stripe, db, sub_id: str, at_period_end: bool = True, actor: str = "system") -> None:
    if at_period_end:
        st.req("POST", f"/subscriptions/{sub_id}", {"cancel_at_period_end": True})
    else:
        st.req("DELETE", f"/subscriptions/{sub_id}", idem=f"cancel-{sub_id}")
    db.audit_log.insert_one({"actor": actor, "action": "subscription.cancel", "target": sub_id, "detail": {"at_period_end": at_period_end}, "at": utcnow()})


def resume_subscription(st: Stripe, db, sub_id: str, actor: str = "system") -> None:
    st.req("POST", f"/subscriptions/{sub_id}", {"cancel_at_period_end": False})
    db.audit_log.insert_one({"actor": actor, "action": "subscription.resume", "target": sub_id, "at": utcnow()})


def refund(st: Stripe, db, payment_id: str, amount_cents: int | None, reason: str, actor: str) -> dict:
    pay = db.payments.find_one({"_id": payment_id})
    if not pay:
        raise P.PlanError("NOT_FOUND", "No such payment.")
    ref = {"payment_intent": pay["payment_intent"]} if pay.get("payment_intent") else {"charge": pay["charge"]} if pay.get("charge") else None
    if not ref:
        raise P.PlanError("NO_REFERENCE", "This payment has no payment or charge id. Refund it in the Stripe dashboard.")
    left = pay.get("amount_paid", 0) - pay.get("refunded_cents", 0)
    if amount_cents is not None and not (0 < amount_cents <= left):
        raise P.PlanError("BAD_AMOUNT", f"You can refund up to {left} cents.")
    if not reason or len(reason.strip()) < 3:
        raise P.PlanError("REASON_REQUIRED", "Say why you are refunding.")
    data = {**ref, "metadata": {"by": actor, "reason": reason.strip()[:200]}}
    if amount_cents:
        data["amount"] = amount_cents
    r = st.req("POST", "/refunds", data, idem=f"refund-{payment_id}-{amount_cents or 'full'}-{pay.get('refunded_cents', 0)}")
    db.audit_log.insert_one({"actor": actor, "action": "payment.refund", "target": payment_id, "detail": {"amount": amount_cents or left, "reason": reason.strip()[:200]}, "at": utcnow()})
    return {"id": r["id"], "status": r.get("status")}


def create_coupon(db, st: Stripe, *, code: str, name: str, percent_off: float | None = None, amount_off_cents: int | None = None,
                  currency: str | None = None, duration: str = "once", months: int | None = None, max_redemptions: int | None = None,
                  expires_at: datetime | None = None, actor: str = "system") -> dict:
    code = (code or "").strip().upper()
    if not re.fullmatch(r"[A-Z0-9_-]{3,30}", code):
        raise P.PlanError("BAD_CODE", "Code: 3 to 30 letters, digits, - or _.")
    if (percent_off is None) == (amount_off_cents is None):
        raise P.PlanError("BAD_COUPON", "Give a percent off OR an amount off.")
    if percent_off is not None and not 0 < percent_off <= 100:
        raise P.PlanError("BAD_COUPON", "Percent off: above 0, up to 100.")
    if amount_off_cents is not None and (amount_off_cents < 1 or not currency):
        raise P.PlanError("BAD_COUPON", "Amount off needs cents and a currency.")
    if duration not in ("once", "repeating", "forever") or (duration == "repeating") != bool(months):
        raise P.PlanError("BAD_COUPON", "Duration: once, forever, or repeating with a number of months.")
    if db.coupons.find_one({"code": code}):
        raise P.PlanError("EXISTS", "That code already exists.")
    cdata = {"name": name[:40] or code, "duration": duration, "metadata": {"code": code}}
    if percent_off is not None: cdata["percent_off"] = percent_off
    else: cdata.update(amount_off=amount_off_cents, currency=currency.lower())
    if months: cdata["duration_in_months"] = months
    c = st.req("POST", "/coupons", cdata, idem=f"coupon-{code}")
    extra = {k: v for k, v in (("max_redemptions", max_redemptions), ("expires_at", int(expires_at.timestamp()) if expires_at else None)) if v}
    new_form = {"promotion": {"type": "coupon", "coupon": c["id"]}, "code": code, **extra}
    old_form = {"coupon": c["id"], "code": code, **extra}
    use_new = not st.version or st.version >= "2025-09-30"
    try:
        promo = st.req("POST", "/promotion_codes", new_form if use_new else old_form, idem=f"promo-{code}")
    except StripeError as e:
        if e.status == 400 and not st.version:             # account default is an older version: try the old form
            promo = st.req("POST", "/promotion_codes", old_form, idem=f"promo-{code}-old")
        else:
            raise
    row = {"code": code, "name": name, "percent_off": percent_off, "amount_off_cents": amount_off_cents, "currency": currency,
           "duration": duration, "months": months, "max_redemptions": max_redemptions, "expires_at": expires_at, "active": True,
           "stripe_coupon_id": c["id"], "stripe_promo_id": promo["id"], "created_by": actor, "created_at": utcnow()}
    db.coupons.insert_one(dict(row))
    db.audit_log.insert_one({"actor": actor, "action": "coupon.create", "target": code, "at": utcnow()})
    return row


def deactivate_coupon(st: Stripe, db, code: str, actor: str) -> None:
    c = db.coupons.find_one({"code": code})
    if not c:
        raise P.PlanError("NOT_FOUND", "No such code.")
    st.req("POST", f"/promotion_codes/{c['stripe_promo_id']}", {"active": False})
    db.coupons.update_one({"code": code}, {"$set": {"active": False}})
    db.audit_log.insert_one({"actor": actor, "action": "coupon.deactivate", "target": code, "at": utcnow()})


# ----------------------------------------------------------------------------- webhook
def verify_webhook(payload: bytes, sig_header: str, secret: str, tolerance: int = 300, now: float | None = None) -> dict:
    """Header looks like: t=1700000000,v1=<hex>,v1=<hex>. Signed text is '<t>.<payload>'."""
    try:
        parts = [p.split("=", 1) for p in (sig_header or "").split(",")]
        t = next(int(v) for k, v in parts if k == "t")
        sigs = [v for k, v in parts if k == "v1"]
    except (StopIteration, ValueError):
        raise WebhookError("bad signature header")
    if abs((now or time.time()) - t) > tolerance:
        raise WebhookError("timestamp outside tolerance")
    expected = hmac.new(secret.encode(), f"{t}.".encode() + payload, hashlib.sha256).hexdigest()
    if not any(hmac.compare_digest(expected, s) for s in sigs):
        raise WebhookError("signature mismatch")
    return json.loads(payload)


def _items(obj):
    return ((obj.get("items") or {}).get("data")) or []


def _period(obj):
    first = _items(obj)[0] if _items(obj) else {}
    return (obj.get("current_period_start") or first.get("current_period_start"),
            obj.get("current_period_end") or first.get("current_period_end"))


def _inv_sub_id(inv):
    return inv.get("subscription") or (((inv.get("parent") or {}).get("subscription_details") or {}).get("subscription"))


def _user_for(db, obj):
    uid = (obj.get("metadata") or {}).get("user_id")
    u = db.users.find_one({"id": uid}) if uid else None
    if not u and obj.get("customer"):
        u = db.users.find_one({"stripe_customer_id": obj["customer"]})
    return u


def _plan_for_price(db, price_id, meta):
    p = db.plans.find_one({"prices.stripe_price_id": price_id}) if price_id else None
    if p:
        pr = next(x for x in p["prices"] if x.get("stripe_price_id") == price_id)
        return p["key"], pr["id"]
    p = db.plans.find_one({"prices.retired_stripe_price_id": price_id}) if price_id else None
    if p:
        return p["key"], None
    if meta.get("plan_key") and db.plans.find_one({"key": meta["plan_key"]}):
        return meta["plan_key"], None
    return None, None


def upsert_subscription(db, obj: dict, event_created: int) -> dict:
    user = _user_for(db, obj)
    if not user:
        raise WebhookProblem(f"subscription {obj.get('id')}: no user for customer {obj.get('customer')}")
    prev = db.subscriptions.find_one({"_id": obj["id"]})
    if prev and event_created < prev.get("last_event_at", 0):
        return {"stale": True}
    items = _items(obj)
    price = (items[0].get("price") if items else None) or obj.get("plan") or {}
    plan_key, price_id = _plan_for_price(db, price.get("id"), obj.get("metadata") or {})
    if not plan_key and prev:
        plan_key, price_id = prev.get("plan_key"), prev.get("price_key")
    if not plan_key:
        raise WebhookProblem(f"subscription {obj['id']}: price {price.get('id')} matches no plan. Sync the plan in Admin > Plans.")
    start, end = _period(obj)
    status = obj.get("status")
    now = utcnow()
    since = None
    if status == "past_due":
        since = (prev or {}).get("past_due_since") or now
    rec = (price.get("recurring") or {})
    row = {"user_id": user["id"], "customer_id": obj.get("customer"), "status": status, "plan_key": plan_key, "price_key": price_id,
           "stripe_price_id": price.get("id"), "interval": rec.get("interval") or price.get("interval"),
           "amount_cents": price.get("unit_amount") or price.get("amount"), "currency": price.get("currency"),
           "current_period_start": ts(start), "current_period_end": ts(end), "cancel_at_period_end": bool(obj.get("cancel_at_period_end")),
           "canceled_at": ts(obj.get("canceled_at")), "ended_at": ts(obj.get("ended_at")), "trial_end": ts(obj.get("trial_end")),
           "past_due_since": since, "last_event_at": event_created, "updated_at": now}
    db.subscriptions.update_one({"_id": obj["id"]}, {"$set": row, "$setOnInsert": {"created_at": ts(obj.get("created")) or now}}, upsert=True)
    upd = {}
    if not user.get("stripe_customer_id") and obj.get("customer"):
        upd["stripe_customer_id"] = obj["customer"]
    if obj.get("trial_end") or status == "trialing":
        upd["had_trial"] = True
    if upd:
        db.users.update_one({"id": user["id"]}, {"$set": upd})
    return {"user": user, "plan_key": plan_key, "was_new": prev is None}


def upsert_invoice(db, inv: dict, status: str, event_created: int) -> dict:
    sub_id = _inv_sub_id(inv)
    sub = db.subscriptions.find_one({"_id": sub_id}) if sub_id else None
    user = _user_for(db, inv) or (db.users.find_one({"id": sub["user_id"]}) if sub and sub.get("user_id") else None)
    if not user:
        raise WebhookProblem(f"invoice {inv.get('id')}: no user for customer {inv.get('customer')}")
    prev = db.payments.find_one({"_id": inv["id"]})
    if prev and event_created < prev.get("last_event_at", 0):
        return {"stale": True, "user": user}
    if prev and prev.get("status") in ("refunded", "partially_refunded") and status == "paid":
        status = prev["status"]                                 # a refund we already saw is not undone by a late 'paid'
    line = ((inv.get("lines") or {}).get("data") or [{}])[0]
    row = {"user_id": user["id"], "customer_id": inv.get("customer"), "subscription_id": sub_id, "status": status,
           "amount_paid": inv.get("amount_paid", 0), "amount_due": inv.get("amount_due", 0), "currency": inv.get("currency"),
           "number": inv.get("number"), "invoice_url": inv.get("hosted_invoice_url"), "billing_reason": inv.get("billing_reason"),
           "period_end": ts((line.get("period") or {}).get("end")), "last_event_at": event_created,
           "created_at": ts(inv.get("created")) or utcnow(), "plan_key": sub and sub.get("plan_key")}
    for k in ("payment_intent", "charge"):
        if inv.get(k):
            row[k] = inv[k]
    db.payments.update_one({"_id": inv["id"]}, {"$set": row}, upsert=True)
    return {"user": user, "sub": sub, "payment": row}


def _emit(db, type_, user, data):
    """Outbound webhook (Zapier etc). Never lets a broken integration break billing."""
    try:
        import integrations as INT
        INT.emit(db, type_, data, email=user.get("email"), user_id=user.get("id"))
    except Exception:
        pass


def money(cents, cur) -> str:
    sym = {"cad": "CA$", "usd": "US$", "eur": "€", "gbp": "£"}.get((cur or "").lower(), (cur or "").upper() + " ")
    return f"{sym}{(cents or 0) / 100:,.2f}"


def handle_event(db, event: dict, notify=None) -> str:
    """Returns 'duplicate' or 'processed'. Raises WebhookProblem/Exception when it could not apply the event."""
    eid, typ = event["id"], event["type"]
    key = f"stripe:{eid}"
    prev = db.webhook_events.find_one({"_id": key})
    if prev and prev.get("status") == "processed":
        return "duplicate"
    db.webhook_events.update_one({"_id": key}, {"$set": {"provider": "stripe", "type": typ, "created": event.get("created"), "status": "processing",
                                                        "received_at": utcnow(), "livemode": event.get("livemode")}, "$inc": {"attempts": 1}}, upsert=True)
    try:
        _dispatch(db, event, notify or (lambda *a, **k: None))
    except Exception as e:
        db.webhook_events.update_one({"_id": key}, {"$set": {"status": "error", "error": str(e)[:300]}})
        raise
    db.webhook_events.update_one({"_id": key}, {"$set": {"status": "processed"}, "$unset": {"error": ""}})
    return "processed"


def _dispatch(db, event, notify):
    typ, obj, created = event["type"], event["data"]["object"], event.get("created", 0)
    if typ == "checkout.session.completed":
        uid = obj.get("client_reference_id") or (obj.get("metadata") or {}).get("user_id")
        if uid and obj.get("customer"):
            db.users.update_one({"id": uid, "stripe_customer_id": {"$exists": False}}, {"$set": {"stripe_customer_id": obj["customer"]}})
        db.events.insert_one({"name": "checkout_completed", "at": utcnow(), "day": utcnow().strftime("%Y-%m-%d"), "user_id": uid})
    elif typ in ("customer.subscription.created", "customer.subscription.updated", "customer.subscription.deleted"):
        if typ.endswith("deleted"):
            obj = {**obj, "status": "canceled"}
        r = upsert_subscription(db, obj, created)
        if r.get("stale"):
            return
        if typ.endswith("deleted"):
            notify("subscription_canceled", r["user"], {"plan": _plan_name(db, r["plan_key"]), "period_end": ""})
            _emit(db, "subscription.canceled", r["user"], {"plan": r["plan_key"]})
        elif r["was_new"]:
            db.events.insert_one({"name": "subscribed", "at": utcnow(), "day": utcnow().strftime("%Y-%m-%d"), "user_id": r["user"]["id"], "props": {"plan": r["plan_key"]}})
            _emit(db, "subscription.started", r["user"], {"plan": r["plan_key"]})
            if obj.get("status") in ("active", "trialing"):
                te = ts(obj.get("trial_end"))
                sub = db.subscriptions.find_one({"_id": obj["id"]}) or {}
                nxt = te or sub.get("current_period_end")
                notify("pro_welcome", r["user"], {"plan": _plan_name(db, r["plan_key"]), "date": nxt.strftime("%d %B %Y") if nxt else "shown in your account",
                                               "trial": f"Your free trial runs until {te.strftime('%d %B %Y')}. " if te else "", "sub": obj["id"]})
    elif typ in ("invoice.paid", "invoice.payment_succeeded"):
        r = upsert_invoice(db, obj, "paid", created)
        if r.get("stale"):
            return
        if r["sub"] and r["sub"].get("past_due_since"):
            db.subscriptions.update_one({"_id": r["sub"]["_id"]}, {"$set": {"past_due_since": None}})
        if obj.get("amount_paid", 0) > 0:
            pe = r["payment"]["period_end"]
            notify("receipt", r["user"], {"amount": money(obj.get("amount_paid"), obj.get("currency")), "plan": _plan_name(db, r["payment"].get("plan_key")),
                                         "period_end": pe.strftime("%Y-%m-%d") if pe else "", "invoice_url": obj.get("hosted_invoice_url") or ""})
            _emit(db, "payment.succeeded", r["user"], {"amount_cents": obj.get("amount_paid"), "currency": obj.get("currency"), "plan": r["payment"].get("plan_key")})
    elif typ == "invoice.payment_failed":
        r = upsert_invoice(db, obj, "failed", created)
        if r.get("stale"):
            return
        if r["sub"] and not r["sub"].get("past_due_since"):
            db.subscriptions.update_one({"_id": r["sub"]["_id"]}, {"$set": {"past_due_since": utcnow()}})
        notify("payment_failed", r["user"], {"plan": _plan_name(db, r["payment"].get("plan_key")), "days": str(S.get(db, "billing.past_due_grace_days"))})
        _emit(db, "payment.failed", r["user"], {"plan": r["payment"].get("plan_key")})
    elif typ == "charge.refunded":
        pay = (db.payments.find_one({"payment_intent": obj.get("payment_intent")}) if obj.get("payment_intent") else None) or db.payments.find_one({"charge": obj.get("id")})
        if pay:
            refunded = obj.get("amount_refunded", 0)
            db.payments.update_one({"_id": pay["_id"]}, {"$set": {"refunded_cents": refunded, "status": "refunded" if refunded >= pay.get("amount_paid", 0) else "partially_refunded", "charge": obj.get("id")}})
    elif typ == "customer.subscription.trial_will_end":
        u = _user_for(db, obj)
        if u:
            sub = db.subscriptions.find_one({"_id": obj["id"]})
            te = ts(obj.get("trial_end"))
            notify("trial_ending", u, {"plan": _plan_name(db, sub and sub.get("plan_key")), "date": te.strftime("%Y-%m-%d") if te else ""})
    # every other event type is accepted and ignored


def _plan_name(db, key):
    p = P.get_plan(db, key) if key else None
    return p["name"] if p else "your plan"
