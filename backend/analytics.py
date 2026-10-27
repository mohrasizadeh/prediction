"""analytics.py -- our own, privacy-friendly numbers. No cookies, no third-party scripts, no ad tech.

Collecting
  track() writes one row per event to `events`. Anonymous visitors get a hash that changes every day
  (sha256 of secret + day + ip + user agent), so we can count unique visitors per day but cannot follow
  a person across days. Signed-in people are counted by user id. We honour Do Not Track and Global
  Privacy Control when analytics.respect_dnt is on. We never store IP addresses in events.

Reading
  Every report takes `days` and returns plain dicts the admin panel can chart.
  Money is NEVER added across currencies: revenue is returned per currency.
"""
from __future__ import annotations

import hashlib
import os
import re
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse

import settings_store as S

CLIENT_EVENTS = {"page_view", "pricing_view", "paywall_view", "insight_view"}       # the browser may send these
SERVER_EVENTS = {"signup", "verified", "login", "finder_search", "checkout_started", "checkout_completed", "subscribed",
                 "follow", "save", "contact"}
_BOT = re.compile(r"bot|crawl|spider|slurp|headless|lighthouse|preview|monitor|curl|python-requests|wget", re.I)


def utcnow():
    return datetime.now(timezone.utc)


def day_of(dt) -> str:
    return dt.strftime("%Y-%m-%d")


def _salt() -> bytes:
    return (os.environ.get("APP_ENCRYPTION_KEY", "dev") + "|analytics").encode()


def anon_id(ip: str, ua: str, day: str) -> str:
    return "a:" + hashlib.sha256(_salt() + day.encode() + (ip or "").encode() + (ua or "").encode()).hexdigest()[:16]


def clean_path(p: str | None) -> str:
    p = (p or "/").split("?")[0].split("#")[0][:120]
    p = re.sub(r"/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}(?=/|$)", "/:id", p, flags=re.I)
    p = re.sub(r"/[0-9a-f-]{12,}(?=/|$)", "/:id", p, flags=re.I)  # long ids -> :id
    p = re.sub(r"/\d{3,}", "/:id", p)
    return p if p.startswith("/") else "/" + p


def clean_utm(utm) -> dict | None:
    """Campaign tags from the landing URL. Lower-case, short, letters/numbers/dash/underscore/dot only. Nothing else is kept."""
    if not isinstance(utm, dict):
        return None
    out = {}
    for k in ("source", "medium", "campaign"):
        v = utm.get(k)
        if isinstance(v, str):
            v = re.sub(r"[^a-z0-9_.\-]", "", v.strip().lower())[:40]
            if v:
                out[k] = v
    return out or None


def device_of(ua: str) -> str:
    return "mobile" if re.search(r"Mobi|Android|iPhone", ua or "") else "desktop"


def track(db, name: str, *, user_id: str | None = None, ip: str = "", ua: str = "", path: str | None = None,
          ref: str | None = None, props: dict | None = None, dnt: bool = False, server: bool = False, now=None, utm: dict | None = None) -> bool:
    """Returns True if a row was written."""
    if name not in (SERVER_EVENTS | CLIENT_EVENTS) or (not server and name not in CLIENT_EVENTS):
        return False
    if not S.get(db, "analytics.first_party_enabled"):
        return False
    if not server:
        if _BOT.search(ua or "") or (dnt and S.get(db, "analytics.respect_dnt")):
            return False
    now = now or utcnow()
    day = day_of(now)
    row = {"name": name, "at": now, "day": day, "actor": f"u:{user_id}" if user_id else anon_id(ip, ua, day),
           "path": clean_path(path) if path else None, "device": device_of(ua)}
    if user_id:
        row["user_id"] = user_id
    if ref:
        host = urlparse(ref).hostname or ""
        row["ref_host"] = host[:80] if host else None
    u = clean_utm(utm)
    if u:
        row["utm"] = u
    if props:
        row["props"] = {str(k)[:30]: (str(v)[:60] if not isinstance(v, (int, float, bool)) else v) for k, v in list(props.items())[:8]}
    db.events.insert_one(row)
    return True


# ----------------------------------------------------------------------------- reading
def _days(days: int, now=None):
    now = now or utcnow()
    days = max(1, min(int(days), 400))
    return now, [day_of(now - timedelta(days=i)) for i in range(days - 1, -1, -1)]


def series(db, name: str, days: int = 30, now=None) -> list[dict]:
    """[{day, count, uniques}] for every day in range, zero-filled."""
    now, ds = _days(days, now)
    cnt = {r["_id"]: r["n"] for r in db.events.aggregate([{"$match": {"name": name, "day": {"$gte": ds[0]}}}, {"$group": {"_id": "$day", "n": {"$sum": 1}}}])}
    uq = {}
    for r in db.events.aggregate([{"$match": {"name": name, "day": {"$gte": ds[0]}}}, {"$group": {"_id": {"d": "$day", "a": "$actor"}}}]):
        uq[r["_id"]["d"]] = uq.get(r["_id"]["d"], 0) + 1
    return [{"day": d, "count": cnt.get(d, 0), "uniques": uq.get(d, 0)} for d in ds]


def active_users(db, now=None) -> dict:
    """Signed-in people with any event in the window."""
    now = now or utcnow()
    f = lambda n: len([u for u in db.events.distinct("user_id", {"day": {"$gte": day_of(now - timedelta(days=n - 1))}}) if u])
    return {"dau": f(1), "wau": f(7), "mau": f(30)}


def top_pages(db, days: int = 30, limit: int = 15, now=None) -> list[dict]:
    now, ds = _days(days, now)
    views = {}
    uniq = {}
    for r in db.events.aggregate([{"$match": {"name": "page_view", "day": {"$gte": ds[0]}}}, {"$group": {"_id": {"p": "$path", "a": "$actor", "d": "$day"}, "n": {"$sum": 1}}}]):
        p = r["_id"]["p"] or "/"
        views[p] = views.get(p, 0) + r["n"]
        uniq[p] = uniq.get(p, 0) + 1
    return sorted(({"path": p, "views": v, "visitors": uniq[p]} for p, v in views.items()), key=lambda x: -x["views"])[:limit]


def referrers(db, days: int = 30, limit: int = 10, now=None) -> list[dict]:
    now, ds = _days(days, now)
    agg = db.events.aggregate([{"$match": {"name": "page_view", "day": {"$gte": ds[0]}, "ref_host": {"$nin": [None, ""]}}},
                               {"$group": {"_id": "$ref_host", "n": {"$sum": 1}}}])
    return sorted(({"host": r["_id"], "views": r["n"]} for r in agg), key=lambda x: -x["views"])[:limit]


def devices(db, days: int = 30, now=None) -> dict:
    now, ds = _days(days, now)
    return {r["_id"] or "unknown": r["n"] for r in db.events.aggregate([{"$match": {"name": "page_view", "day": {"$gte": ds[0]}}}, {"$group": {"_id": "$device", "n": {"$sum": 1}}}])}


def funnel(db, days: int = 30, now=None) -> list[dict]:
    """Counts, not a strict cohort: visitors who viewed, then sign-ups, verified, checkouts, paid in the same window."""
    now, ds = _days(days, now)
    q = lambda name: {"name": name, "day": {"$gte": ds[0]}}
    visitors = len(db.events.distinct("actor", q("page_view")))
    steps = [("Visitors", visitors), ("Signed up", db.events.count_documents(q("signup"))), ("Verified e-mail", db.events.count_documents(q("verified"))),
             ("Started checkout", db.events.count_documents(q("checkout_started"))), ("Paid", db.events.count_documents(q("subscribed")))]
    out, prev = [], None
    for label, n in steps:
        out.append({"step": label, "count": n, "of_previous": round(n / prev, 3) if prev else None})
        prev = n if n else None
    return out


def finder_usage(db, days: int = 30, now=None) -> dict:
    now, ds = _days(days, now)
    rows = list(db.events.find({"name": "finder_search", "day": {"$gte": ds[0]}}, {"props": 1, "user_id": 1, "_id": 0}))
    stats, modes = {}, {}
    for r in rows:
        p = r.get("props") or {}
        stats[p.get("stat", "?")] = stats.get(p.get("stat", "?"), 0) + 1
        modes[p.get("mode", "?")] = modes.get(p.get("mode", "?"), 0) + 1
    return {"total": len(rows), "signed_in": sum(1 for r in rows if r.get("user_id")), "by_day": series(db, "finder_search", days, now),
            "top_stats": sorted(({"stat": k, "n": v} for k, v in stats.items()), key=lambda x: -x["n"])[:10],
            "modes": modes, "searches_per_user": round(len(rows) / max(1, len({r.get("user_id") for r in rows if r.get("user_id")})), 2)}


def retention(db, weeks: int = 8, now=None) -> list[dict]:
    """Weekly sign-up cohorts. Cell [w] = share of the cohort with any signed-in event w weeks after sign-up."""
    now = now or utcnow()
    out = []
    for k in range(weeks - 1, -1, -1):
        start, end = now - timedelta(weeks=k + 1), now - timedelta(weeks=k)
        ids = [u["id"] for u in db.users.find({"created_at": {"$gte": start, "$lt": end}, "role": "user"}, {"id": 1, "_id": 0})]
        cells = []
        for w in range(0, k + 1):
            a, b = end + timedelta(weeks=w - 1), end + timedelta(weeks=w)
            if not ids:
                cells.append(None); continue
            act = db.events.distinct("user_id", {"user_id": {"$in": ids}, "at": {"$gte": a, "$lt": b}})
            cells.append(round(len(act) / len(ids), 3))
        out.append({"cohort_start": day_of(start), "size": len(ids), "weeks": cells})
    return out


# ----------------------------------------------------------------------------- money and people
LIVE = ["active", "trialing", "past_due"]


def _monthly(sub) -> float:
    amt = sub.get("amount_cents") or 0
    return amt / 12 if sub.get("interval") == "year" else amt


def revenue(db, days: int = 30, now=None) -> dict:
    """Per currency: MRR, ARR, ARPU, collected, refunded, churn. Trials do not count towards MRR."""
    now = now or utcnow()
    start = now - timedelta(days=days)
    cur: dict = {}
    def c(x): return cur.setdefault((x or "unknown").lower(), {"currency": (x or "unknown").lower(), "mrr_cents": 0, "paying": 0, "collected_cents": 0, "refunded_cents": 0, "failed_payments": 0})
    for s in db.subscriptions.find({"status": {"$in": ["active", "past_due"]}}):
        row = c(s.get("currency")); row["mrr_cents"] += int(_monthly(s)); row["paying"] += 1
    for p in db.payments.find({"created_at": {"$gte": start}}):
        row = c(p.get("currency"))
        if p.get("status") in ("paid", "partially_refunded", "refunded"):
            row["collected_cents"] += p.get("amount_paid", 0); row["refunded_cents"] += p.get("refunded_cents", 0)
        elif p.get("status") == "failed":
            row["failed_payments"] += 1
    for row in cur.values():
        row["arr_cents"] = row["mrr_cents"] * 12
        row["arpu_cents"] = int(row["mrr_cents"] / row["paying"]) if row["paying"] else 0
        row["net_collected_cents"] = row["collected_cents"] - row["refunded_cents"]
    base = db.subscriptions.count_documents({"created_at": {"$lt": start}, "$or": [{"ended_at": None}, {"ended_at": {"$gte": start}}]})
    lost = db.subscriptions.count_documents({"created_at": {"$lt": start}, "status": "canceled", "ended_at": {"$gte": start}})
    return {"by_currency": sorted(cur.values(), key=lambda r: -r["mrr_cents"]),
            "trialing": db.subscriptions.count_documents({"status": "trialing"}),
            "past_due": db.subscriptions.count_documents({"status": "past_due"}),
            "scheduled_to_cancel": db.subscriptions.count_documents({"status": {"$in": LIVE}, "cancel_at_period_end": True}),
            "churn": {"window_days": days, "start_base": base, "lost": lost, "rate": round(lost / base, 3) if base else None}}


def people(db, now=None) -> dict:
    """Free vs paid vs comp vs trial. Counts people, not subscriptions."""
    now = now or utcnow()
    total = db.users.count_documents({"role": "user", "disabled": {"$ne": True}})
    paid_ids = {s["user_id"] for s in db.subscriptions.find({"status": {"$in": ["active", "past_due"]}}, {"user_id": 1}) if s.get("user_id")}
    trial_ids = {s["user_id"] for s in db.subscriptions.find({"status": "trialing"}, {"user_id": 1}) if s.get("user_id")} - paid_ids
    comp_ids = {u["id"] for u in db.users.find({"comp": {"$exists": True}}, {"id": 1, "comp": 1}) if not u["comp"].get("until") or (u["comp"]["until"].replace(tzinfo=timezone.utc) > now)} - paid_ids - trial_ids
    paying = len(paid_ids)
    return {"total": total, "paid": paying, "trial": len(trial_ids), "comp": len(comp_ids), "free": max(0, total - paying - len(trial_ids) - len(comp_ids)),
            "verified": db.users.count_documents({"role": "user", "email_verified": True}), "unverified": db.users.count_documents({"role": "user", "email_verified": False}),
            "disabled": db.users.count_documents({"disabled": True}), "two_factor": db.users.count_documents({"totp.enabled": True})}


def plan_breakdown(db) -> list[dict]:
    out = {}
    for s in db.subscriptions.find({"status": {"$in": LIVE}}):
        r = out.setdefault(s["plan_key"], {"plan": s["plan_key"], "subscribers": 0, "trialing": 0})
        r["subscribers"] += 1; r["trialing"] += 1 if s["status"] == "trialing" else 0
    return sorted(out.values(), key=lambda r: -r["subscribers"])


def overview(db, days: int = 30, now=None) -> dict:
    now = now or utcnow()
    start, prev = now - timedelta(days=days), now - timedelta(days=2 * days)
    new = db.users.count_documents({"role": "user", "created_at": {"$gte": start}})
    before = db.users.count_documents({"role": "user", "created_at": {"$gte": prev, "$lt": start}})
    return {"window_days": days, "people": people(db, now), "active": active_users(db, now),
            "signups": {"now": new, "previous": before, "change": round((new - before) / before, 3) if before else None},
            "page_views": sum(r["count"] for r in series(db, "page_view", days, now)),
            "revenue": revenue(db, days, now), "plans": plan_breakdown(db),
            "signups_by_day": series(db, "signup", days, now), "visitors_by_day": series(db, "page_view", days, now)}
