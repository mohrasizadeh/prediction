"""waitlist_stats.py -- the numbers behind Admin > Waitlist (docs/68 "Measuring it").

Everything here is read from the same first-party `events` collection the rest of Analytics uses
(analytics.py), plus the e-mail list for confirmations. No third-party script is involved, Do Not
Track is honoured where the event is written, and bots are dropped there too.

WHAT "VISITOR" MEANS. An anonymous visitor's id is a hash that changes every day (analytics.anon_id),
by design: we can count people per day but cannot follow anyone across days. So "visitors" over a
window is the sum of each day's distinct visitors -- someone who comes back on three days counts
three times. The screen says so rather than calling it "unique people".

The page sends:
  page_view      one per load of /waitlist
  wl_scroll      props.depth 25 / 50 / 75 / 100, each at most once per load
  wl_section     props.section proof / engine / record / costs / close, once per load
  wl_form_start  the first time the form is focused
and the server writes `waitlist_signup` when the form is submitted, with the visit's source.
"""
from __future__ import annotations

from datetime import timedelta

import analytics as AN

PATH = "/waitlist"
DEPTHS = (25, 50, 75, 100)
SECTIONS = [("proof", "Scored cards"), ("engine", "Inside the engine"), ("record", "The record"),
            ("costs", "Three things we do"), ("close", "Closing ask")]


def _actors(db, name: str, since: str, extra: dict | None = None) -> set:
    """Distinct (day, actor) pairs: one per visitor per day, the unit every rate here is built on."""
    q = {"name": name, "day": {"$gte": since}, "path": PATH, **(extra or {})}
    return {(r["_id"]["d"], r["_id"]["a"]) for r in db.events.aggregate([{"$match": q}, {"$group": {"_id": {"d": "$day", "a": "$actor"}}}])}


def _rate(n, d):
    return round(n / d, 4) if d else None


def _window(db, since: str, until: str | None = None) -> dict:
    """Headline counts for days >= since (and < until, for the previous window)."""
    day = {"$gte": since, **({"$lt": until} if until else {})}
    views = db.events.count_documents({"name": "page_view", "path": PATH, "day": day})
    visitors = len({(r["_id"]["d"], r["_id"]["a"]) for r in db.events.aggregate([
        {"$match": {"name": "page_view", "path": PATH, "day": day}}, {"$group": {"_id": {"d": "$day", "a": "$actor"}}}])})
    signups = db.events.count_documents({"name": "waitlist_signup", "day": day})
    return {"views": views, "visitors": visitors, "signups": signups, "conversion": _rate(signups, visitors)}


def report(db, days: int = 30, now=None) -> dict:
    now, ds = AN._days(days, now)
    since = ds[0]
    prev_since = AN.day_of(now - timedelta(days=2 * len(ds) - 1))
    cur, prev = _window(db, since), _window(db, prev_since, since)

    # ---- by day: views, visitors, sign-ups
    pv = {r["_id"]: r["n"] for r in db.events.aggregate([{"$match": {"name": "page_view", "path": PATH, "day": {"$gte": since}}},
                                                         {"$group": {"_id": "$day", "n": {"$sum": 1}}}])}
    vis: dict = {}
    for d, _a in _actors(db, "page_view", since):
        vis[d] = vis.get(d, 0) + 1
    su = {r["_id"]: r["n"] for r in db.events.aggregate([{"$match": {"name": "waitlist_signup", "day": {"$gte": since}}},
                                                         {"$group": {"_id": "$day", "n": {"$sum": 1}}}])}
    by_day = [{"day": d, "views": pv.get(d, 0), "visitors": vis.get(d, 0), "signups": su.get(d, 0)} for d in ds]

    # ---- how far people read. Rates are over visitors, so "50%" means half of the people who
    # loaded the page scrolled at least that far -- not half of the scroll events.
    visitors = _actors(db, "page_view", since)
    nv = len(visitors) or 0
    scroll = []
    reached = {d: set() for d in DEPTHS}
    for r in db.events.find({"name": "wl_scroll", "path": PATH, "day": {"$gte": since}}, {"day": 1, "actor": 1, "props": 1, "_id": 0}):
        dep = (r.get("props") or {}).get("depth")
        for d in DEPTHS:
            if isinstance(dep, (int, float)) and dep >= d:
                reached[d].add((r["day"], r["actor"]))
    for d in DEPTHS:
        n = len(reached[d] & visitors) if visitors else len(reached[d])
        scroll.append({"depth": d, "visitors": n, "share": _rate(n, nv)})
    sections = []
    for sid, label in SECTIONS:
        n = len(_actors(db, "wl_section", since, {"props.section": sid}) & visitors) if visitors else 0
        sections.append({"section": sid, "label": label, "visitors": n, "share": _rate(n, nv)})

    # ---- the funnel, each step a subset of visitors by construction
    started = _actors(db, "wl_form_start", since)
    funnel = [{"step": "Visited", "count": nv},
              {"step": "Read half the page", "count": len(reached[50] & visitors)},
              {"step": "Started the form", "count": len(started & visitors) if visitors else len(started)},
              {"step": "Signed up", "count": cur["signups"]}]
    for i, f in enumerate(funnel):
        f["of_visitors"] = _rate(f["count"], nv)
        f["of_previous"] = _rate(f["count"], funnel[i - 1]["count"]) if i else None

    # ---- sources: visitors by where they came from, and the sign-ups each one brought.
    # A visitor's source is taken from their first page view of the day.
    first: dict = {}
    for r in db.events.find({"name": "page_view", "path": PATH, "day": {"$gte": since}},
                            {"day": 1, "actor": 1, "utm": 1, "ref_host": 1, "device": 1, "at": 1, "_id": 0}).sort("at", 1):
        first.setdefault((r["day"], r["actor"]), r)
    src: dict = {}
    camp: dict = {}
    dev: dict = {}
    for r in first.values():
        s = AN.source_of(r.get("utm"), r.get("ref_host"))
        row = src.setdefault(s, {"source": s, "visitors": 0, "signups": 0, "confirmed": 0})
        row["visitors"] += 1
        c = (r.get("utm") or {}).get("campaign")
        if c:
            k = (s, c)
            camp.setdefault(k, {"source": s, "campaign": c, "visitors": 0, "signups": 0})["visitors"] += 1
        dev[r.get("device") or "unknown"] = dev.get(r.get("device") or "unknown", 0) + 1
    for r in db.events.find({"name": "waitlist_signup", "day": {"$gte": since}}, {"utm": 1, "ref_host": 1, "_id": 0}):
        s = AN.source_of(r.get("utm"), r.get("ref_host"))
        src.setdefault(s, {"source": s, "visitors": 0, "signups": 0, "confirmed": 0})["signups"] += 1
        c = (r.get("utm") or {}).get("campaign")
        if c:
            camp.setdefault((s, c), {"source": s, "campaign": c, "visitors": 0, "signups": 0})["signups"] += 1

    # ---- the list itself: confirmed people, which is what the match-day e-mail actually reaches
    start_dt = now - timedelta(days=len(ds) - 1)
    start_dt = start_dt.replace(hour=0, minute=0, second=0, microsecond=0)
    confirmed = 0
    for r in db.newsletter.find({"source": "waitlist", "status": "confirmed", "confirmed_at": {"$gte": start_dt}}, {"attrib": 1, "_id": 0}):
        confirmed += 1
        s = (r.get("attrib") or {}).get("source")
        if s:
            src.setdefault(s, {"source": s, "visitors": 0, "signups": 0, "confirmed": 0})["confirmed"] += 1
    for row in src.values():
        row["rate"] = _rate(row["signups"], row["visitors"])
    for row in camp.values():
        row["rate"] = _rate(row["signups"], row["visitors"])

    members = db.newsletter.count_documents({"source": "waitlist", "status": "confirmed"})
    waiting = db.newsletter.count_documents({"source": "waitlist", "status": "pending"})
    recent = now - timedelta(minutes=30)
    live = len(set(db.events.distinct("actor", {"name": "page_view", "path": PATH, "at": {"$gte": recent}})))

    def change(a, b):
        return round((a - b) / b, 3) if b else None

    return {
        "window_days": len(ds), "since": since,
        "totals": {**cur, "confirmed": confirmed, "members": members, "waiting": waiting, "live": live},
        "previous": prev,
        "change": {k: change(cur[k], prev[k]) for k in ("views", "visitors", "signups")},
        "by_day": by_day, "scroll": scroll, "sections": sections, "funnel": funnel,
        "sources": sorted(src.values(), key=lambda r: (-r["visitors"], -r["signups"]))[:20],
        "campaigns": sorted(camp.values(), key=lambda r: (-r["visitors"], -r["signups"]))[:20],
        "devices": dev,
        "note": "Visitors are counted per day: someone who comes back on three days counts three times, "
                "because the anonymous id changes daily by design. Do Not Track visitors and bots are not counted.",
    }
