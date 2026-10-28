"""Admin home (docs/24 Admin): six health tiles, each green, amber, red or off, plus one 'Needs you' list
with the action on each item."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import accounts as A
import admin_queries as AQ
import alerts as AL
import calibration as CAL
import settings_store as S
import sportapi as SP


def _tone(used, cap):
    return "red" if cap and used >= cap else "amber" if cap and used >= 0.8 * cap else "green"


def tiles(db, now: datetime) -> list[dict]:
    day0 = now.replace(hour=0, minute=0, second=0, microsecond=0)
    reset = day0 + timedelta(days=1)
    h = AQ.health(db, now)
    sync = db.job_runs.find_one({"job": {"$in": ["fixtures_sync", "results_sync"]}, "status": "ok"}, {"_id": 0, "finished_at": 1, "started_at": 1}, sort=[("started_at", -1)])
    data = {"id": "data", "module": "jobs", "title": "Data", "tone": "red" if h["breaker_open"] else _tone(h["api_calls_today"], h["api_budget"]),
            "provider": "PitchAPI", "used": h["api_calls_today"], "cap": h["api_budget"], "reset_at": reset,
            "last_sync": (sync or {}).get("finished_at") or (sync or {}).get("started_at"), "breaker_open": h["breaker_open"]}
    sp = SP.status(db, now)
    live = {"id": "live", "module": "integrations", "title": "Live", "tone": _tone(sp["calls_today"], sp["cap"]) if sp["enabled"] else "off",
            "provider": "SportAPI", "enabled": sp["enabled"], "used": sp["calls_today"], "cap": sp["cap"], "by_kind": sp["by_kind"], "reset_at": reset,
            "live_now": sp["live_now"], "review": sp["teams"].get("review", 0)}
    run = db.job_runs.find_one({"job": {"$regex": "^engine"}}, {"_id": 0, "started_at": 1, "status": 1}, sort=[("started_at", -1)])
    bad = db.job_runs.count_documents({"job": {"$regex": "^engine"}, "status": "error", "started_at": {"$gte": now - timedelta(hours=24)}})
    own = db.engine_calibration.find_one({"active": True}, {"_id": 1})
    engine = {"id": "engine", "module": "engine", "title": "Engine", "tone": "red" if (run or {}).get("status") == "error" else "amber" if bad else "green",
              "last_run": (run or {}).get("started_at"), "forecasts": db.forecasts.count_documents({"is_current": True}),
              "map": "off" if CAL.current(db) is None else ("own" if own else "default"), "errors_24h": bad}
    review = db.image_map.count_documents({"status": "review"})
    images = {"id": "images", "module": "engine", "title": "Images", "tone": "amber" if review else "green", "review": review,
              "stored": db.media.count_documents({"kind": "player"})}
    signups = db.users.count_documents({"role": "user", "created_at": {"$gte": day0}})
    users = {"id": "users", "module": "users", "title": "Users", "tone": "green", "signups_today": signups, "total": db.users.count_documents({"role": "user"})}
    on = bool(S.get(db, "features.billing"))
    due = db.subscriptions.count_documents({"status": "past_due"}) if on else 0
    money = {"id": "money", "module": "subscriptions", "title": "Money", "tone": ("amber" if due or h["webhook_errors_24h"] else "green") if on else "off",
             "billing": on, "mode": S.get(db, "billing.mode"), "past_due": due, "webhook_errors_24h": h["webhook_errors_24h"]}
    return [data, live, engine, images, users, money]


def needs(db, user, now: datetime) -> list[dict]:
    out = []
    if A.can(user, "settings.write"):
        tid = {t["iid"]: t["id"] for t in db.teams.find({}, {"_id": 0, "iid": 1, "id": 1})}
        for r in db.sportapi_team_map.find({"status": "review"}, {"_id": 0}).limit(20):
            out.append({"kind": "match", "key": f"sp-{r['sid']}", "sid": r["sid"], "name": r.get("name"), "score": r.get("score"),
                        "candidates": [{**c, "id": tid.get(c["iid"])} for c in r.get("candidates", []) if tid.get(c["iid"])]})
    for r in db.image_map.find({"status": "review"}, {"_id": 0}).sort([("score", -1)]).limit(20):
        out.append({"kind": "image", "key": f"im-{r['kind']}-{r['our_iid']}", "image_kind": r["kind"], "our_iid": r["our_iid"],
                    "name": r.get("name") or r.get("our_name"), "score": r.get("score"), "candidates": r.get("candidates", [])})
    seen = set()
    for r in db.job_runs.find({"status": "error", "started_at": {"$gte": now - timedelta(hours=24)}}, {"_id": 0}).sort("started_at", -1):
        if r["job"] in seen:
            continue
        seen.add(r["job"])
        later = db.job_runs.find_one({"job": r["job"], "status": "ok", "started_at": {"$gt": r["started_at"]}}, {"_id": 1})
        if later:
            continue
        base = r["job"].split(":")[0]
        out.append({"kind": "job", "key": f"job-{r['job']}", "job": r["job"], "at": r["started_at"], "error": str(r.get("error") or r.get("result") or "")[:200],
                    "can_run": base in __import__("jobs").MANUAL, "run_as": base})
    for a in AL.open_alerts(db):
        out.append({"kind": "alert", "key": f"al-{a['id']}", "id": a["id"], "text": a["text"], "at": a.get("at")})
    groups: dict = {}
    for r in db.ingest_issues.find({"resolved": {"$ne": True}}, {"kind": 1, "detail": 1, "at": 1}).sort("at", -1).limit(500):
        g = groups.setdefault((r.get("kind"), r.get("detail")), {"ids": [], "at": r.get("at"), "kind": r.get("kind") or "issue", "detail": r.get("detail") or ""})
        g["ids"].append(str(r["_id"]))
    for g in list(groups.values())[:20]:
        n = len(g["ids"])
        out.append({"kind": "issue", "key": f"is-{g['ids'][0]}", "ids": g["ids"], "at": g["at"],
                    "text": f"{g['kind'].replace('_', ' ')}: {g['detail']}"[:240] + (f" ({n} times)" if n > 1 else "")})
    new = db.contact_messages.count_documents({"status": "new"})
    if new:
        out.append({"kind": "inbox", "key": "inbox", "count": new})
    return out


def home(db, user) -> dict:
    now = datetime.now(timezone.utc)
    return {"now": now, "name": (user.get("display_name") or user.get("name") or user.get("email", "").split("@")[0]).split(" ")[0],
            "tiles": tiles(db, now), "needs": needs(db, user, now) if A.can(user, "logs.read") else []}
