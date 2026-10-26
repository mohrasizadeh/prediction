import os, sys, base64, json, time, hmac, hashlib
os.environ.update({"APP_ENCRYPTION_KEY": base64.b64encode(os.urandom(32)).decode(), "BCRYPT_ROUNDS": "4", "PUBLIC_BASE_URL": "https://app.test"})
HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__))); sys.path.insert(0, HERE)
from datetime import timedelta
from urllib.parse import parse_qsl
import httpx, mongomock
import accounts as A, plans as P, stripe_billing as SB, emailer as E, security, settings_store as S, mongo_init

db = mongomock.MongoClient()["b"]; mongo_init.ensure_indexes(db)
def check(c, m):
    if not c: print("  FAIL", m); sys.exit(1)
    print("  ok  ", m)
def raises(exc, fn, *a, **k):
    try: fn(*a, **k)
    except exc as e: return str(getattr(e, "code", "") or e)
    return False
now = A.utcnow()
def mkuser(i, **kw):
    u = {"id": f"u{i}", "email": f"u{i}@example.com", "role": "user", "email_verified": True, "display_name": f"User{i}",
         "prefs": {"product_emails": True, "marketing_emails": False, "alert_emails": True}, "created_at": now, **kw}
    db.users.insert_one(dict(u)); return u

# =============================================================== PLANS
check(P.seed(db) == 2 and P.seed(db) == 0, "seed makes Free and Pro once")
check(raises(P.PlanError, P.clean_entitlements, {"nope": 1}) == "UNKNOWN_ENTITLEMENT", "unknown entitlement refused")
check(raises(P.PlanError, P.clean_entitlements, {"finder_searches_per_day": -2}) == "BAD_ENTITLEMENT", "limit below -1 refused")
check(raises(P.PlanError, P.clean_entitlements, {"alerts": 1}) == "BAD_ENTITLEMENT", "a number is not a switch")
check(P.clean_entitlements({})["alerts"] is False, "gaps are filled with the closed (free) value")
anon = P.effective_plan(db, None)
check(anon["plan_key"] == "free" and anon["source"] == "anonymous", "signed-out visitor: free plan")
u1 = mkuser(1)
check(P.effective_plan(db, u1)["source"] == "billing_off" and P.effective_plan(db, u1)["plan_key"] == "pro", "billing off: every signed-in user gets the top plan")
S.put(db, "features.billing", True)
check(P.effective_plan(db, u1)["plan_key"] == "free", "billing on, no subscription: free")
P.grant_comp(db, "u1", "pro", 30, "launch partner", "boss"); u1 = db.users.find_one({"id": "u1"})
check(P.effective_plan(db, u1)["source"] == "comp", "comp gives the plan")
check(P.effective_plan(db, u1, now + timedelta(days=31))["plan_key"] == "free", "comp ends on its date")
check(raises(P.PlanError, P.grant_comp, db, "u1", "pro", 5, " ", "boss") == "REASON_REQUIRED", "comp needs a reason")
check(raises(P.PlanError, P.grant_comp, db, "u1", "free", 5, "why", "boss") == "BAD_PLAN", "cannot comp the free plan")
P.revoke_comp(db, "u1", "boss"); u1 = db.users.find_one({"id": "u1"})
def sub(id, uid, status, end, **kw):
    db.subscriptions.update_one({"_id": id}, {"$set": {"user_id": uid, "status": status, "plan_key": "pro", "current_period_end": end, **kw}}, upsert=True)
sub("sub_a", "u1", "active", now + timedelta(days=10))
check(P.effective_plan(db, u1)["source"] == "subscription", "active subscription gives the plan")
sub("sub_a", "u1", "active", now - timedelta(days=5))
check(P.effective_plan(db, u1)["plan_key"] == "free", "period ended long ago (missed webhook): free")
sub("sub_a", "u1", "active", now - timedelta(days=1))
check(P.effective_plan(db, u1)["plan_key"] == "pro", "one day past the period end: still pro (late webhook slack)")
sub("sub_a", "u1", "past_due", now + timedelta(days=1), past_due_since=now - timedelta(days=3))
check(P.effective_plan(db, u1)["plan_key"] == "pro", "past due inside the grace days: still pro")
sub("sub_a", "u1", "past_due", now + timedelta(days=1), past_due_since=now - timedelta(days=9))
check(P.effective_plan(db, u1)["plan_key"] == "free", "past due beyond the grace days: free")
sub("sub_a", "u1", "canceled", now + timedelta(days=10))
check(P.effective_plan(db, u1)["plan_key"] == "free", "canceled: free")
db.subscriptions.delete_many({})

# quotas
res = [P.consume(db, "u:1", "finder", 3)[0] for _ in range(5)]
check(res == [True, True, True, False, False] and P.used_today(db, "u:1", "finder") == 3, "quota: 3 allowed, then refused, refusals are not counted")
check(P.consume(db, "u:2", "finder", 3)[0] and P.consume(db, "u:1", "other", 1)[0], "quotas are per person and per name")
check(all(P.consume(db, "u:9", "finder", -1)[0] for _ in range(20)), "-1 means no limit")
check(P.consume(db, "u:1", "finder", 3, now + timedelta(days=1))[0], "a new day starts a new count")

# plan admin
newp = P.create_plan(db, "plus", {"name": "Plus", "entitlements": {"alerts": True}, "prices": [{"id": "monthly", "interval": "month", "amount_cents": 499, "currency": "CAD"}]}, "boss")
check(newp["prices"][0]["currency"] == "cad" and newp["visible"] is False, "new plan: price cleaned, hidden until shown")
check(raises(P.PlanError, P.create_plan, db, "Bad Key!", {}, "boss") == "BAD_KEY", "bad plan key refused")
check(raises(P.PlanError, P.create_plan, db, "plus", {}, "boss") == "EXISTS", "duplicate plan key refused")
check(raises(P.PlanError, P.update_plan, db, "plus", {"prices": [{"id": "m", "interval": "week", "amount_cents": 500, "currency": "cad"}]}, "boss") == "BAD_PRICE", "bad interval refused")
check(raises(P.PlanError, P.update_plan, db, "plus", {"prices": [{"id": "m", "interval": "month", "amount_cents": 5, "currency": "cad"}]}, "boss") == "BAD_PRICE", "price below 50 cents refused")
db.plans.update_one({"key": "plus"}, {"$set": {"prices.0.stripe_price_id": "price_old"}})
p2 = P.update_plan(db, "plus", {"prices": [{"id": "monthly", "interval": "month", "amount_cents": 599, "currency": "cad"}]}, "boss")
check(p2["prices"][0].get("retired_stripe_price_id") == "price_old" and "stripe_price_id" not in p2["prices"][0], "price change retires the old Stripe price")
check(raises(P.PlanError, P.update_plan, db, "free", {"archived": True}, "boss") == "DEFAULT_PLAN", "default plan cannot be archived")
db.subscriptions.insert_one({"_id": "s_x", "user_id": "u1", "status": "active", "plan_key": "plus"})
check(raises(P.PlanError, P.update_plan, db, "plus", {"archived": True}, "boss") == "IN_USE", "plan with subscribers cannot be archived")
db.subscriptions.delete_many({})
check(P.update_plan(db, "plus", {"archived": True}, "boss")["archived"] and "plus" not in [x["key"] for x in P.public_plans(db)], "archived plan leaves the pricing page")
check(all("stripe" not in json.dumps(x) for x in P.public_plans(db)), "public plans show no Stripe ids")

# =============================================================== STRIPE
class FakeStripe:
    def __init__(self): self.calls = []; self.n = 0; self.reject_promo_new = False
    def __call__(self, request):
        body = dict(parse_qsl(request.content.decode())) if request.content else {}
        self.calls.append((request.method, request.url.path, body, dict(request.headers)))
        p = request.url.path; self.n += 1
        if p == "/v1/customers": return httpx.Response(200, json={"id": "cus_1"})
        if p == "/v1/products": return httpx.Response(200, json={"id": "prod_1"})
        if p == "/v1/prices": return httpx.Response(200, json={"id": f"price_{self.n}"})
        if p == "/v1/checkout/sessions": return httpx.Response(200, json={"id": "cs_1", "url": "https://checkout.stripe.test/c/1"})
        if p == "/v1/billing_portal/sessions": return httpx.Response(200, json={"id": "bps_1", "url": "https://billing.stripe.test/p/1"})
        if p == "/v1/refunds": return httpx.Response(200, json={"id": "re_1", "status": "succeeded"})
        if p == "/v1/coupons": return httpx.Response(200, json={"id": "co_1"})
        if p == "/v1/promotion_codes":
            if self.reject_promo_new and "promotion[type]" in body: return httpx.Response(400, json={"error": {"type": "invalid_request_error", "message": "Received unknown parameter: promotion", "param": "promotion"}})
            return httpx.Response(200, json={"id": "promo_1"})
        return httpx.Response(200, json={"id": p.rsplit("/", 1)[-1]})
    def of(self, path): return [c for c in self.calls if c[1] == path]
fs = FakeStripe(); SB.set_http_factory(lambda: httpx.Client(transport=httpx.MockTransport(fs))); SB.set_sleep(lambda s: None)
E.set_http_factory(lambda: httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200, json={"id": "em_x"})))); E.set_sleep(lambda s: None)

check(SB.encode({"a": {"b": [1, {"c": True}]}, "x": None, "y": "z"}) == [("a[b][0]", "1"), ("a[b][1][c]", "true"), ("y", "z")], "form encoding: nested, lists, booleans, no None")
check(raises(SB.StripeConfigError, SB.Stripe, db) is not False, "no key: clear config error")
security.save_provider_key(db, "stripe_secret", "sk_live_abcdefghij123456")
check("test" in (raises(SB.StripeConfigError, SB.Stripe, db) or "") or "live" in (raises(SB.StripeConfigError, SB.Stripe, db) or ""), "live key while mode is test: refused")
security.save_provider_key(db, "stripe_secret", "sk_test_abcdefghij123456")
st = SB.Stripe(db)
u2 = mkuser(2)
SB.ensure_customer(db, st, u2); SB.ensure_customer(db, st, u2)
c = fs.of("/v1/customers")
check(len(c) == 1 and c[0][2]["email"] == "u2@example.com" and c[0][2]["metadata[user_id]"] == "u2" and c[0][3]["idempotency-key"] == "cust-u2", "customer made once, with the idempotency key")
check(c[0][3]["authorization"] == "Bearer sk_test_abcdefghij123456", "secret key sent as Bearer")
before = len(fs.calls)
SB.sync_plan(db, st, "pro")
pro = P.get_plan(db, "pro")
check(pro["stripe_product_id"] == "prod_1" and all(x["stripe_price_id"].startswith("price_") for x in pro["prices"]), "sync: product and both prices created and saved")
pr = fs.of("/v1/prices")
check(pr[0][2]["recurring[interval]"] == "month" and pr[0][2]["unit_amount"] == "999" and pr[0][2]["currency"] == "cad", "price sent with amount, currency, interval")
n = len(fs.calls); SB.sync_plan(db, st, "pro")
check(len(fs.calls) == n, "sync again: nothing changes, no calls")
P.update_plan(db, "pro", {"prices": [{"id": "monthly", "interval": "month", "amount_cents": 1299, "currency": "cad"}, {"id": "yearly", "interval": "year", "amount_cents": 7999, "currency": "cad", "stripe_price_id": "ignored"}]}, "boss")
old_month = P.get_plan(db, "pro")  # price changed => retired id recorded
SB.sync_plan(db, st, "pro")
pro = P.get_plan(db, "pro")
deact = [c for c in fs.calls if c[1].startswith("/v1/prices/") and c[2].get("active") == "false"]
check(len(deact) == 1 and pro["prices"][0]["stripe_price_id"] and "retired_stripe_price_id" not in pro["prices"][0], "price change: new price made, old one switched off")
# test/live separation: ids made in one mode are not reused in the other
db.plans.update_one({"key": "pro"}, {"$set": {"stripe_mode": "live"}})
n_before = len(fs.of("/v1/prices"))
SB.sync_plan(db, st, "pro")
check(len(fs.of("/v1/prices")) == n_before + 2 and P.get_plan(db, "pro")["stripe_mode"] == "test", "plan synced in another mode: ids from that mode are dropped and rebuilt")
S.put(db, "plans.trial_days", 7)
chk = SB.create_checkout(db, st, u2, "pro", "monthly")
f = fs.of("/v1/checkout/sessions")[-1][2]
check(chk["url"].startswith("https://checkout.stripe.test") and f["mode"] == "subscription" and f["client_reference_id"] == "u2", "checkout: hosted page, subscription mode, our user id attached")
pro = P.get_plan(db, "pro")
check(f["line_items[0][price]"] == pro["prices"][0]["stripe_price_id"] and f["line_items[0][quantity]"] == "1", "checkout: right price")
check(f["success_url"].startswith("https://app.test/account/billing") and "{CHECKOUT_SESSION_ID}" in f["success_url"] and f["cancel_url"] == "https://app.test/pricing?status=cancelled", "checkout: absolute return urls")
check(f["subscription_data[trial_period_days]"] == "7" and f["subscription_data[metadata][user_id]"] == "u2", "checkout: trial on first subscription, user id on the subscription")
db.users.update_one({"id": "u2"}, {"$set": {"had_trial": True}}); u2 = db.users.find_one({"id": "u2"})
SB.create_checkout(db, st, u2, "pro", "yearly")
check("subscription_data[trial_period_days]" not in fs.of("/v1/checkout/sessions")[-1][2], "no second free trial")
check(raises(P.PlanError, SB.create_checkout, db, st, u2, "free", "x") == "BAD_PLAN", "cannot buy the free plan")
check(raises(P.PlanError, SB.create_checkout, db, st, u2, "pro", "nope") == "BAD_PRICE", "unknown price refused")
check(SB.create_portal(db, st, u2)["url"].startswith("https://billing.stripe.test") and fs.of("/v1/billing_portal/sessions")[-1][2]["customer"] == "cus_1", "portal link for the customer")

# webhook signature
SEC = "whsec_testsecret1234567890"
def sign(payload: bytes, t=None, secret=SEC):
    t = t or int(time.time()); return f"t={t},v1=" + hmac.new(secret.encode(), f"{t}.".encode() + payload, hashlib.sha256).hexdigest()
body = json.dumps({"id": "evt_1", "type": "x"}).encode()
check(SB.verify_webhook(body, sign(body), SEC)["id"] == "evt_1", "webhook: good signature accepted")
check(raises(SB.WebhookError, SB.verify_webhook, body + b" ", sign(body), SEC), "webhook: tampered body refused")
check(raises(SB.WebhookError, SB.verify_webhook, body, sign(body, secret="whsec_other1234567890"), SEC), "webhook: wrong secret refused")
check(raises(SB.WebhookError, SB.verify_webhook, body, sign(body, t=int(time.time()) - 4000), SEC), "webhook: old timestamp refused (replay)")
check(raises(SB.WebhookError, SB.verify_webhook, body, "garbage", SEC) and raises(SB.WebhookError, SB.verify_webhook, body, "", SEC), "webhook: missing or bad header refused")
two = sign(body).replace("v1=", "v1=deadbeef,v1=")
check(SB.verify_webhook(body, two, SEC), "webhook: several v1 signatures, one good, accepted")

# events
db.subscriptions.delete_many({}); db.payments.delete_many({}); db.events.delete_many({})
pmo = P.get_plan(db, "pro")["prices"][0]["stripe_price_id"]
end = int((now + timedelta(days=30)).timestamp())
def sub_obj(status="active", price=pmo, shape="new", uid="u2", **kw):
    o = {"id": "sub_1", "customer": "cus_1", "status": status, "metadata": {"user_id": uid}, "created": int(now.timestamp()),
         "items": {"data": [{"price": {"id": price, "unit_amount": 1299, "currency": "cad", "recurring": {"interval": "month"}}}]}, **kw}
    if shape == "new": o["items"]["data"][0].update(current_period_start=int(now.timestamp()), current_period_end=end)
    else: o.update(current_period_start=int(now.timestamp()), current_period_end=end)
    return o
def ev(id, typ, obj, created=None): return {"id": id, "type": typ, "created": created or int(time.time()), "livemode": False, "data": {"object": obj}}
notes = []
notify = lambda kind, user, ctx: notes.append((kind, user["id"], ctx))
t0 = int(time.time())
check(SB.handle_event(db, ev("evt_s1", "customer.subscription.created", sub_obj(), t0), notify) == "processed", "subscription.created processed")
s = db.subscriptions.find_one({"_id": "sub_1"})
check(s["plan_key"] == "pro" and s["price_key"] == "monthly" and s["status"] == "active" and s["user_id"] == "u2" and s["current_period_end"] is not None, "subscription stored with plan, price and period end (period on the item)")
check(SB.handle_event(db, ev("evt_s1", "customer.subscription.created", sub_obj(), t0), notify) == "duplicate", "same event id twice: second is a no-op")
SB.handle_event(db, ev("evt_s2", "customer.subscription.updated", sub_obj(shape="old", cancel_at_period_end=True), t0 + 10), notify)
s = db.subscriptions.find_one({"_id": "sub_1"})
check(s["cancel_at_period_end"] and s["current_period_end"] is not None, "period end also read from the subscription (older API shape)")
SB.handle_event(db, ev("evt_s0", "customer.subscription.updated", sub_obj(status="canceled"), t0 + 5), notify)
check(db.subscriptions.find_one({"_id": "sub_1"})["status"] == "active", "older event arriving late is ignored")
check(db.users.find_one({"id": "u2"})["had_trial"] is True and db.events.count_documents({"name": "subscribed"}) == 1, "subscribed event counted once")
bad = ev("evt_bad", "customer.subscription.updated", sub_obj(price="price_unknown", uid="u2") | {"id": "sub_9"}, t0)
check(raises(SB.WebhookProblem, SB.handle_event, db, bad, notify), "unknown price: event fails so Stripe retries")
check(db.webhook_events.find_one({"_id": "stripe:evt_bad"})["status"] == "error", "failure is recorded for the admin")
db.plans.update_one({"key": "plus"}, {"$set": {"prices.0.stripe_price_id": "price_unknown"}})
check(SB.handle_event(db, bad, notify) == "processed" and db.webhook_events.find_one({"_id": "stripe:evt_bad"})["status"] == "processed", "after the plan is fixed, the retry succeeds")
check(raises(SB.WebhookProblem, SB.handle_event, db, ev("evt_nouser", "customer.subscription.created", sub_obj(uid="ghost") | {"customer": "cus_ghost", "id": "sub_g"}, t0), notify), "no matching user: event fails")
db.subscriptions.delete_one({"_id": "sub_9"})

inv = {"id": "in_1", "customer": "cus_1", "subscription": "sub_1", "amount_paid": 1299, "amount_due": 1299, "currency": "cad", "number": "A-001",
       "hosted_invoice_url": "https://invoice.stripe.test/1", "payment_intent": "pi_1", "billing_reason": "subscription_create", "created": t0,
       "lines": {"data": [{"period": {"end": end}}]}}
SB.handle_event(db, ev("evt_i1", "invoice.paid", inv, t0 + 20), notify)
pay = db.payments.find_one({"_id": "in_1"})
check(pay["status"] == "paid" and pay["amount_paid"] == 1299 and pay["user_id"] == "u2" and pay["plan_key"] == "pro", "invoice.paid: payment stored")
check(notes[-1][0] == "receipt" and notes[-1][2]["amount"] == "CA$12.99" and notes[-1][2]["plan"] == "Pro", "receipt notification with amount and plan")
inv2 = {k: v for k, v in inv.items() if k != "subscription"} | {"id": "in_2", "parent": {"subscription_details": {"subscription": "sub_1"}}, "payment_intent": "pi_2"}
SB.handle_event(db, ev("evt_i2", "invoice.paid", inv2, t0 + 30), notify)
check(db.payments.find_one({"_id": "in_2"})["subscription_id"] == "sub_1", "invoice's subscription read from parent.subscription_details (newer API shape)")
SB.handle_event(db, ev("evt_f1", "invoice.payment_failed", inv | {"id": "in_3", "amount_paid": 0, "payment_intent": "pi_3"}, t0 + 40), notify)
check(db.payments.find_one({"_id": "in_3"})["status"] == "failed" and db.subscriptions.find_one({"_id": "sub_1"})["past_due_since"] is not None and notes[-1][0] == "payment_failed", "payment failed: marked, grace clock started, person told")
SB.handle_event(db, ev("evt_i4", "invoice.paid", inv | {"id": "in_3", "amount_paid": 1299, "payment_intent": "pi_3"}, t0 + 50), notify)
check(db.subscriptions.find_one({"_id": "sub_1"})["past_due_since"] is None and db.payments.find_one({"_id": "in_3"})["status"] == "paid", "retry paid: grace clock cleared")
SB.handle_event(db, ev("evt_r1", "charge.refunded", {"id": "ch_1", "payment_intent": "pi_1", "amount_refunded": 500}, t0 + 60), notify)
check(db.payments.find_one({"_id": "in_1"})["status"] == "partially_refunded" and db.payments.find_one({"_id": "in_1"})["refunded_cents"] == 500, "partial refund recorded")
SB.handle_event(db, ev("evt_r2", "charge.refunded", {"id": "ch_1", "payment_intent": "pi_1", "amount_refunded": 1299}, t0 + 70), notify)
check(db.payments.find_one({"_id": "in_1"})["status"] == "refunded", "full refund recorded")
SB.handle_event(db, ev("evt_t1", "customer.subscription.trial_will_end", sub_obj(trial_end=end), t0 + 80), notify)
check(notes[-1][0] == "trial_ending", "trial ending: person told")
S.put(db, "features.billing", True)
check(P.effective_plan(db, db.users.find_one({"id": "u2"}))["source"] == "subscription", "after events, the person is on Pro")
SB.handle_event(db, ev("evt_d1", "customer.subscription.deleted", sub_obj(), t0 + 90), notify)
check(db.subscriptions.find_one({"_id": "sub_1"})["status"] == "canceled" and notes[-1][0] == "subscription_canceled", "subscription deleted: canceled, person told")
check(P.effective_plan(db, db.users.find_one({"id": "u2"}))["plan_key"] == "free", "after cancel, back to Free")
check(SB.handle_event(db, ev("evt_other", "customer.created", {"id": "cus_x"}), notify) == "processed", "unknown event types are accepted and ignored")

# refunds, coupons, cancel
r = SB.refund(st, db, "in_3", 300, "duplicate charge", "boss")
rf = fs.of("/v1/refunds")[-1]
check(r["status"] == "succeeded" and rf[2]["payment_intent"] == "pi_3" and rf[2]["amount"] == "300" and rf[3]["idempotency-key"].startswith("refund-in_3-300"), "refund: right payment, amount, idempotency key")
check(raises(P.PlanError, SB.refund, st, db, "in_3", 99999, "too much", "boss") == "BAD_AMOUNT", "refund above what is left refused")
check(raises(P.PlanError, SB.refund, st, db, "in_3", 100, "", "boss") == "REASON_REQUIRED", "refund needs a reason")
db.payments.insert_one({"_id": "in_noref", "amount_paid": 100})
check(raises(P.PlanError, SB.refund, st, db, "in_noref", None, "why", "boss") == "NO_REFERENCE", "payment with no payment/charge id: clear message")
SB.cancel_subscription(st, db, "sub_1", True, "boss")
check(fs.calls[-1][1] == "/v1/subscriptions/sub_1" and fs.calls[-1][2]["cancel_at_period_end"] == "true", "cancel at period end")
cp = SB.create_coupon(db, st, code="launch20", name="Launch", percent_off=20, duration="once", max_redemptions=50, actor="boss")
pcs = fs.of("/v1/promotion_codes")[-1][2]
check(cp["code"] == "LAUNCH20" and pcs["promotion[type]"] == "coupon" and pcs["code"] == "LAUNCH20" and pcs["max_redemptions"] == "50", "coupon and promotion code created (new API form)")
fs.reject_promo_new = True; st2 = SB.Stripe(db); st2.version = None
SB.create_coupon(db, st2, code="OLDSTYLE", name="Old", amount_off_cents=500, currency="CAD", duration="repeating", months=3, actor="boss")
check("coupon" in fs.of("/v1/promotion_codes")[-1][2] and fs.of("/v1/coupons")[-1][2]["duration_in_months"] == "3", "older API: falls back to the old promotion-code form")
check(raises(P.PlanError, SB.create_coupon, db, st, code="x", name="n", percent_off=10, actor="b") == "BAD_CODE", "bad coupon code refused")
check(raises(P.PlanError, SB.create_coupon, db, st, code="BOTH10", name="n", percent_off=10, amount_off_cents=5, currency="cad", actor="b") == "BAD_COUPON", "percent and amount together refused")
check(raises(P.PlanError, SB.create_coupon, db, st, code="LAUNCH20", name="n", percent_off=10, actor="b") == "EXISTS", "duplicate code refused")
# errors and retries
class Flaky:
    def __init__(self): self.n = 0
    def __call__(self, r):
        self.n += 1
        return httpx.Response(429 if self.n < 3 else 200, json={"error": {"code": "rate_limit"}} if self.n < 3 else {"id": "ok"})
fl = Flaky(); SB.set_http_factory(lambda: httpx.Client(transport=httpx.MockTransport(fl)))
check(st.req("POST", "/customers", {"a": 1}, idem="k1") == {"id": "ok"} and fl.n == 3, "429 retried when an idempotency key is present")
fl.n = 0
check(raises(SB.StripeError, st.req, "POST", "/customers", {"a": 1}) is not False and fl.n == 1, "a create without an idempotency key is never retried")
SB.set_http_factory(lambda: httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(402, json={"error": {"type": "card_error", "code": "card_declined", "message": "declined"}}))))
check(raises(SB.StripeError, st.req, "POST", "/customers", {"a": 1}, "k") == "card_declined", "4xx surfaces the Stripe error code")
SB.set_http_factory(lambda: httpx.Client(transport=httpx.MockTransport(fs)))

# =============================================================== EMAIL
class FakeResend:
    def __init__(self): self.calls = []; self.mode = "ok"; self.n = 0
    def __call__(self, request):
        self.n += 1; self.calls.append((request.method, str(request.url), json.loads(request.content), dict(request.headers)))
        if self.mode == "429-then-ok" and self.n % 3 != 0: return httpx.Response(429, json={"name": "rate_limit_exceeded", "message": "slow"})
        if self.mode == "422": return httpx.Response(422, json={"name": "validation_error", "message": "bad to address"})
        if self.mode == "net": raise httpx.ConnectError("down")
        return httpx.Response(200, json={"id": f"em_{self.n}"})
fr = FakeResend(); E.set_http_factory(lambda: httpx.Client(transport=httpx.MockTransport(fr)))
u3 = mkuser(3, display_name="Sam <b>x</b>")
r = E.send_template(db, "verify_email", to="u3@example.com", user=u3, vars={"link": "https://app.test/verify?t=abc&x=1", "hours": 48})
check(r["status"] == "skipped_disabled" and not fr.calls, "e-mail off: logged as skipped, nothing sent")
S.put(db, "email.enabled", True)
check(E.send_template(db, "verify_email", to="u3@example.com", user=u3, vars={"link": "x"})["status"] == "skipped_unconfigured", "no from-address or key: skipped")
S.put(db, "email.from_address", "hello@mail.example.com"); security.save_provider_key(db, "resend", "re_abcdefghijk12345")
r = E.send_template(db, "verify_email", to="U3@Example.com", user=u3, vars={"link": "https://app.test/verify?t=abc&x=1", "hours": 48}, idem="verify-u3-1")
m, url, pl, hd = fr.calls[-1]
check(r["status"] == "sent" and url == "https://api.resend.com/emails" and hd["authorization"] == "Bearer re_abcdefghijk12345" and hd["idempotency-key"] == "verify-u3-1", "sent through Resend with bearer key and idempotency key")
check(pl["to"] == ["u3@example.com"] and pl["from"] == "Forecast <hello@mail.example.com>" and "headers" not in pl, "transactional: right addresses, no unsubscribe header")
check("&lt;b&gt;" in pl["html"] and "<b>x</b>" not in pl["html"] and "abc&amp;x=1" in pl["html"], "variables are HTML-escaped in the body")
check("\n" not in pl["subject"] and pl["text"].count("https://app.test/verify?t=abc&x=1") == 1, "subject is one line; text version keeps the raw link")
row = db.email_log.find_one({"provider_id": "em_1"})
check(row and row["status"] == "sent" and "html" not in row and "vars" not in row and "abc" not in json.dumps(row, default=str), "log row holds no body and no link")
check("Not betting advice" in pl["html"], "footer carries the standard disclaimer")
S.put(db, "email.footer_address", "1 Main St, Cambridge ON")
r = E.send_template(db, "welcome", to="u3@example.com", user=u3, vars={"link": "https://app.test"})
pl, hd = fr.calls[-1][2], fr.calls[-1][3]
check(r["status"] == "sent" and "List-Unsubscribe" in pl["headers"] and pl["headers"]["List-Unsubscribe-Post"] == "List-Unsubscribe=One-Click" and "1 Main St" in pl["html"], "product mail: unsubscribe headers, address, link")
token = pl["headers"]["List-Unsubscribe"].split("t=")[1].rstrip(">")
check(E.read_unsub(token) == "u3@example.com" and E.read_unsub(token + "x") is None and E.read_unsub("a.b") is None, "unsubscribe token verifies, tampering fails")
check(E.unsubscribe(db, token) and E.send_template(db, "welcome", to="u3@example.com", user=db.users.find_one({"id": "u3"}), vars={})["status"] == "skipped_suppressed", "after unsubscribe, product mail stops")
check(E.send_template(db, "password_reset", to="u3@example.com", user=u3, vars={"link": "l"})["status"] == "sent", "…but security mail still arrives")
E.suppress(db, "u3@example.com", "bounce", "test")
check(E.send_template(db, "password_reset", to="u3@example.com", user=u3, vars={"link": "l"})["status"] == "skipped_suppressed", "a bounced address gets nothing at all")
E.unsuppress(db, "u3@example.com", "boss")
u4 = mkuser(4, prefs={"product_emails": False, "marketing_emails": False})
check(E.send_template(db, "welcome", to="u4@example.com", user=u4, vars={})["status"] == "skipped_optout", "product mail respects the person's switch")
S.put(db, "email.daily_send_cap", 1)
check(E.send_template(db, "welcome", to="u3@example.com", user=db.users.find_one({"id": "u3"}) | {"prefs": {"product_emails": True}}, vars={})["status"] == "skipped_cap", "daily cap stops non-essential mail")
check(E.send_template(db, "password_reset", to="u3@example.com", user=u3, vars={"link": "l"})["status"] == "sent", "…but not security mail")
S.put(db, "email.daily_send_cap", 100)
fr.mode, fr.n = "429-then-ok", 0
check(E.send_template(db, "receipt", to="u3@example.com", user=u3, vars={"amount": "x", "plan": "p", "period_end": "d", "invoice_url": "u"})["status"] == "sent", "429 from Resend is retried")
fr.mode = "422"
r = E.send_template(db, "receipt", to="u3@example.com", user=u3, vars={})
check(r["status"] == "failed" and db.email_log.find_one({"status": "failed"})["error"].startswith("422"), "a rejected send is logged as failed, not raised")
fr.mode = "net"
check(E.send_template(db, "receipt", to="u3@example.com", user=u3, vars={})["status"] == "failed", "network failure is logged as failed, not raised")
fr.mode = "ok"

# templates
check(raises(ValueError, E.save_template, db, "welcome", "Hi", "<script>x</script>", "t", "boss") is not False, "script in a template refused")
check(raises(ValueError, E.save_template, db, "welcome", "Hi\nthere", "<p>x</p>", "t", "boss") is not False, "multi-line subject refused")
E.save_template(db, "welcome", "Hello {{name}}", "<p>Custom {{name}}</p>", "Custom {{name}}", "boss")
pv = E.preview(db, "welcome")
check(pv["subject"] == "Hello Sam" and "Custom Sam" in pv["html"] and E.get_template(db, "welcome")["customised"], "saved template is used; preview shows sample values")
E.reset_template(db, "welcome", "boss")
check(not E.get_template(db, "welcome")["customised"], "reset returns to the default")

# resend webhook
WS = "whsec_" + base64.b64encode(b"super-secret-key-bytes").decode()
def svix(payload: bytes, mid="msg_1", t=None, secret=WS):
    t = str(t or int(time.time())); key = base64.b64decode(secret.split("_", 1)[1])
    return {"svix-id": mid, "svix-timestamp": t, "svix-signature": "v1," + base64.b64encode(hmac.new(key, f"{mid}.{t}.".encode() + payload, hashlib.sha256).digest()).decode()}
pb = json.dumps({"type": "email.delivered", "data": {"email_id": "em_1", "to": ["u3@example.com"]}}).encode()
check(E.verify_svix(pb, svix(pb), WS)["type"] == "email.delivered", "resend webhook: good signature accepted")
check(raises(E.WebhookError, E.verify_svix, pb + b"x", svix(pb), WS) and raises(E.WebhookError, E.verify_svix, pb, svix(pb, t=int(time.time()) - 1000), WS) and raises(E.WebhookError, E.verify_svix, pb, {}, WS), "resend webhook: tampered, old, missing headers refused")
check(E.handle_resend_event(db, json.loads(pb), "msg_1") == "processed" and db.email_log.find_one({"provider_id": "em_1"})["status"] == "delivered", "delivered updates the log")
check(E.handle_resend_event(db, json.loads(pb), "msg_1") == "duplicate", "same webhook id twice: no-op")
hb = {"type": "email.bounced", "data": {"email_id": "em_1", "to": ["Bounce@Example.com"], "bounce": {"type": "Permanent"}}}
E.handle_resend_event(db, hb, "msg_2")
check(db.email_suppressions.find_one({"email": "bounce@example.com"})["reason"] == "bounce" and db.email_log.find_one({"provider_id": "em_1"})["status"] == "bounced", "hard bounce: log updated, address suppressed")
E.handle_resend_event(db, {"type": "email.bounced", "data": {"email_id": "em_2", "to": ["soft@example.com"], "bounce": {"type": "Transient"}}}, "msg_3")
check(db.email_suppressions.find_one({"email": "soft@example.com"}) is None, "soft bounce: not suppressed")
E.handle_resend_event(db, {"type": "email.complained", "data": {"email_id": "em_3", "to": ["angry@example.com"]}}, "msg_4")
check(db.email_suppressions.find_one({"email": "angry@example.com"})["reason"] == "complaint", "complaint: suppressed")
E.handle_resend_event(db, json.loads(pb), "msg_5")
check(db.email_log.find_one({"provider_id": "em_1"})["status"] == "bounced", "a late 'delivered' does not undo a bounce")
check(E.handle_resend_event(db, {"type": "email.opened", "data": {}}, "msg_6") == "ignored", "opens are ignored (we do not track opens)")

# campaigns
for i in (5, 6, 7):
    mkuser(i, prefs={"product_emails": True, "marketing_emails": i != 7})
db.users.update_one({"id": "u6"}, {"$set": {"email_verified": False}})
cid = E.create_campaign(db, "News for {{name}}", "<p>Hi {{name}}, new features.</p>", "all", "boss")
check(raises(ValueError, E.send_campaign, db, cid, "boss") is not False, "campaign blocked while marketing is off")
S.put(db, "email.marketing_enabled", True); S.put(db, "email.footer_address", "")
check("postal address" in (raises(ValueError, E.send_campaign, db, cid, "boss") or ""), "campaign blocked without a postal address")
S.put(db, "email.footer_address", "1 Main St")
check(raises(ValueError, E.create_campaign, db, "S", "<script>x</script>", "all", "boss") is not False, "script in campaign refused")
res = E.send_campaign(db, cid, "boss")
sent_to = {c[2]["to"][0] for c in fr.calls[-5:]}
check(res["sent"] == 1 and "u5@example.com" in sent_to and "u6@example.com" not in sent_to and "u7@example.com" not in sent_to, "campaign reaches only verified, opted-in people")
check(E.send_campaign(db, cid, "boss")["sent"] == 0, "running it again sends nothing twice")
db.users.update_one({"id": "u8"}, {"$set": {}}, upsert=False)
mkuser(8, prefs={"product_emails": True, "marketing_emails": True}); mkuser(9, prefs={"product_emails": True, "marketing_emails": True})
S.put(db, "email.daily_send_cap", E._sent_today(db) + 1)
res = E.send_campaign(db, cid, "boss")
check(res["sent"] == 1 and res["left_for_tomorrow"] == 1 and res["status"] == "partial", "campaign stops at the daily cap and says how many are left")
print("\nALL BILLING AND EMAIL CHECKS PASSED")
