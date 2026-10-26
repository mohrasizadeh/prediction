"""reports.py -- the extra numbers a marketer asks for. Reads only; writes nothing.

  realtime       who is on the site right now (last 5 minutes), no identities
  compare        this period against the one before it, for the numbers that matter
  acquisition    where sign-ups and paying people came from (campaign tags + referrer)
  email_report   delivery health: sent, delivered, bounced, complaints, by template
  popup_report   every popup side by side
  newsletter_report  list size and growth by source
  csv_bytes      safe CSV export (cells that start with = + - @ are neutralised so a spreadsheet never runs them)
Money is never added across currencies.
"""
from __future__ import annotations

import csv
import io
from datetime import datetime, timedelta, timezone

import analytics as AN
import popups as PP

LIVE_SUB = ["active", "trialing", "past_due"]


def utcnow():
    return datetime.now(timezone.utc)


def _pct(now, prev):
    return None if not prev else round((now - prev) / prev, 3)


# ----------------------------------------------------------------------------- realtime
def realtime(db, minutes: int = 5, now=None) -> dict:
    now = now or utcnow()
    since = now - timedelta(minutes=minutes)
    rows = list(db.events.find({"at": {"$gte": since}}, {"actor": 1, "name": 1, "path": 1, "device": 1, "at": 1, "user_id": 1, "_id": 0}))
    actors = {r["actor"] for r in rows}
    pages: dict = {}
    for r in rows:
        if r["name"] == "page_view":
            pages.setdefault(r.get("path") or "/", set()).add(r["actor"])
    dev: dict = {}
    seen = set()
    for r in rows:
        if r["actor"] not in seen:
            seen.add(r["actor"])
            dev[r.get("device") or "unknown"] = dev.get(r.get("device") or "unknown", 0) + 1
    recent = sorted(rows, key=lambda r: r["at"], reverse=True)[:20]
    return {"window_minutes": minutes, "active_now": len(actors), "signed_in": len({r["user_id"] for r in rows if r.get("user_id")}),
            "pages": sorted(({"path": p, "visitors": len(a)} for p, a in pages.items()), key=lambda x: -x["visitors"])[:10], "devices": dev,
            "recent": [{"name": r["name"], "path": r.get("path"), "device": r.get("device"), "at": r["at"]} for r in recent]}


# ----------------------------------------------------------------------------- compare
def _window(db, start_day: str, end_day: str, start_dt, end_dt) -> dict:
    ev = lambda name: {"name": name, "day": {"$gte": start_day, "$lte": end_day}}
    pay = db.payments.find({"status": {"$in": ["paid", "partially_refunded"]}, "created_at": {"$gte": start_dt, "$lt": end_dt}})
    rev: dict = {}
    for p in pay:
        c = (p.get("currency") or "unknown").lower()
        rev[c] = rev.get(c, 0) + max(0, int(p.get("amount_paid", 0)) - int(p.get("refunded_cents", 0)))
    return {"visitors": len(db.events.distinct("actor", ev("page_view"))), "page_views": db.events.count_documents(ev("page_view")),
            "signups": db.events.count_documents(ev("signup")), "verified": db.events.count_documents(ev("verified")),
            "checkouts_started": db.events.count_documents(ev("checkout_started")), "subscribed": db.events.count_documents(ev("subscribed")),
            "finder_searches": db.events.count_documents(ev("finder_search")),
            "newsletter_joins": db.newsletter.count_documents({"confirmed_at": {"$gte": start_dt, "$lt": end_dt}}),
            "revenue_cents": rev}


def compare(db, days: int = 30, now=None) -> dict:
    now = now or utcnow()
    days = max(1, min(int(days), 200))
    end = now.replace(hour=23, minute=59, second=59, microsecond=0)
    s_now = (now - timedelta(days=days - 1)).replace(hour=0, minute=0, second=0, microsecond=0)
    s_prev = s_now - timedelta(days=days)
    cur = _window(db, AN.day_of(s_now), AN.day_of(now), s_now, end + timedelta(seconds=1))
    prev = _window(db, AN.day_of(s_prev), AN.day_of(s_now - timedelta(days=1)), s_prev, s_now)
    rows = []
    for k in ("visitors", "page_views", "signups", "verified", "checkouts_started", "subscribed", "finder_searches", "newsletter_joins"):
        rows.append({"metric": k, "now": cur[k], "previous": prev[k], "change": _pct(cur[k], prev[k])})
    money = []
    for c in sorted(set(cur["revenue_cents"]) | set(prev["revenue_cents"])):
        a, b = cur["revenue_cents"].get(c, 0), prev["revenue_cents"].get(c, 0)
        money.append({"currency": c, "now_cents": a, "previous_cents": b, "change": _pct(a, b)})
    return {"days": days, "from": AN.day_of(s_now), "previous_from": AN.day_of(s_prev), "metrics": rows, "revenue": money}


# ----------------------------------------------------------------------------- acquisition
def _key(u):
    u = u or {}
    return (u.get("source") or "(none)", u.get("medium") or "(none)", u.get("campaign") or "(none)")


def acquisition(db, days: int = 30, now=None) -> dict:
    """Visitors come from page_view events carrying campaign tags. Sign-ups and paying people come from users.acq (first touch)."""
    now = now or utcnow()
    start = now - timedelta(days=days)
    ds = AN.day_of(start)
    rows: dict = {}
    seen: dict = {}
    for r in db.events.find({"name": "page_view", "day": {"$gte": ds}, "utm": {"$exists": True}}, {"utm": 1, "actor": 1, "day": 1}):
        k = _key(r["utm"])
        seen.setdefault(k, set()).add((r["actor"], r["day"]))
    for k, a in seen.items():
        rows[k] = {"source": k[0], "medium": k[1], "campaign": k[2], "visitors": len(a), "signups": 0, "paid": 0}
    paid_ids = {s["user_id"] for s in db.subscriptions.find({"status": {"$in": LIVE_SUB}}, {"user_id": 1}) if s.get("user_id")}
    organic = {"source": "(none)", "medium": "(none)", "campaign": "(none)", "visitors": 0, "signups": 0, "paid": 0}
    for u in db.users.find({"role": "user", "created_at": {"$gte": start}}, {"acq": 1, "id": 1}):
        a = u.get("acq")
        if a and (a.get("source") or a.get("medium") or a.get("campaign")):
            k = _key(a)
            r = rows.setdefault(k, {"source": k[0], "medium": k[1], "campaign": k[2], "visitors": 0, "signups": 0, "paid": 0})
        else:
            host = (a or {}).get("ref_host")
            r = organic
            if host:
                r = rows.setdefault(("(referral)", host, "(none)"), {"source": "(referral)", "medium": host, "campaign": "(none)", "visitors": 0, "signups": 0, "paid": 0})
        r["signups"] += 1
        r["paid"] += 1 if u["id"] in paid_ids else 0
    out = list(rows.values())
    if organic["signups"]:
        out.append(organic)
    for r in out:
        r["signup_rate"] = round(r["signups"] / r["visitors"], 4) if r["visitors"] else None
        r["paid_rate"] = round(r["paid"] / r["signups"], 4) if r["signups"] else None
    out.sort(key=lambda r: (-r["signups"], -r["visitors"]))
    return {"days": days, "rows": out[:200], "note": "Visitors are counted per day per anonymous id, so a person who returns on two days counts twice. Sign-ups use the first campaign tag the person arrived with."}


# ----------------------------------------------------------------------------- e-mail, popups, newsletter
def email_report(db, days: int = 30, now=None) -> dict:
    now = now or utcnow()
    start = now - timedelta(days=days)
    by_status: dict = {}
    by_tpl: dict = {}
    for r in db.email_log.find({"at": {"$gte": start}}, {"status": 1, "template": 1, "category": 1}):
        by_status[r["status"]] = by_status.get(r["status"], 0) + 1
        t = by_tpl.setdefault(r.get("template") or "?", {"template": r.get("template") or "?", "category": r.get("category"), "sent": 0, "delivered": 0, "bounced": 0, "complained": 0, "failed": 0, "skipped": 0})
        st = r["status"]
        if st in ("sent", "delayed", "queued"): t["sent"] += 1
        elif st == "delivered": t["sent"] += 1; t["delivered"] += 1
        elif st == "bounced": t["sent"] += 1; t["bounced"] += 1
        elif st == "complained": t["sent"] += 1; t["complained"] += 1
        elif st == "failed": t["failed"] += 1
        else: t["skipped"] += 1
    sent = sum(t["sent"] for t in by_tpl.values())
    bounced, comp = sum(t["bounced"] for t in by_tpl.values()), sum(t["complained"] for t in by_tpl.values())
    return {"days": days, "by_status": by_status, "sent": sent, "bounce_rate": round(bounced / sent, 4) if sent else None,
            "complaint_rate": round(comp / sent, 4) if sent else None, "templates": sorted(by_tpl.values(), key=lambda x: -x["sent"]),
            "suppressed": db.email_suppressions.count_documents({}),
            "note": "Keep bounces under 2% and complaints under 0.1%. Open and click tracking is not used: it needs tracking pixels, which we do not add."}


def popup_report(db) -> dict:
    rows = []
    for p in PP.list_all(db):
        rows.append({"id": p["id"], "name": p["name"], "kind": p["kind"], "state": p["state"], "ab_group": p["ab"]["group"] or None, **p["stats"]})
    return {"rows": sorted(rows, key=lambda r: -r["view"])}


def newsletter_report(db, days: int = 30, now=None) -> dict:
    now = now or utcnow()
    start = now - timedelta(days=days)
    src: dict = {}
    for r in db.newsletter.find({"created_at": {"$gte": start}}, {"source": 1, "status": 1}):
        s = (r.get("source") or "?").split(":")[0] if not str(r.get("source", "")).startswith("popup:") else "popup"
        x = src.setdefault(s, {"source": s, "started": 0, "confirmed": 0})
        x["started"] += 1
        x["confirmed"] += 1 if r["status"] == "confirmed" else 0
    return {"days": days, "counts": {s: db.newsletter.count_documents({"status": s}) for s in ("pending", "confirmed", "unsubscribed")},
            "by_source": sorted(src.values(), key=lambda x: -x["started"]),
            "confirm_rate": None}


# ----------------------------------------------------------------------------- CSV
def _safe(v):
    if v is None:
        return ""
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        return str(v)
    if isinstance(v, (datetime,)):
        return v.isoformat()
    s = str(v)
    return "'" + s if s[:1] in ("=", "+", "-", "@", "\t", "\r") else s


def csv_bytes(rows: list[dict], columns: list[str] | None = None) -> bytes:
    cols = columns or (list(rows[0].keys()) if rows else [])
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(cols)
    for r in rows:
        w.writerow([_safe(r.get(c)) for c in cols])
    return ("﻿" + buf.getvalue()).encode("utf-8")           # BOM so Excel reads accents correctly
