"""Admin home (docs/24 Admin): six health tiles, each green, amber, red or off, plus one 'Needs you' list
with the action on each item."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import accounts as A
import admin_queries as AQ
import alerts as AL
import calibration as CAL
import security
import settings_store as S
import sportapi as SP


# admin_queries.health() already warns at 3 hours with no job of any kind. A feed is given longer
# because a quiet night is normal, and the engine longer again because it runs on a matchday rhythm.
STALE_SYNC = timedelta(hours=6)
STALE_ENGINE = timedelta(hours=26)


def _tone(used, cap):
    return "red" if cap and used >= cap else "amber" if cap and used >= 0.8 * cap else "green"


def _age_tone(last, limit, *, never="red"):
    """Red when it has never happened, red when it is older than `limit`, amber from four fifths.

    _tone above keys on budget use alone, and a pipeline that has stopped makes no calls at all, so
    a dead feed scored zero against its cap and came out the GREENEST thing on the dashboard -- at
    the same moment Health was saying no job had run in three hours. Time is the signal that
    matters for "is it running"; quota is only the signal for "is it about to stop".
    """
    if last is None:
        return never
    age = datetime.now(timezone.utc) - A._aware(last)
    return "red" if age > limit else "amber" if age > 0.8 * limit else "green"


def _worst(*tones):
    return "red" if "red" in tones else "amber" if "amber" in tones else "green"


def tiles(db, now: datetime) -> list[dict]:
    day0 = now.replace(hour=0, minute=0, second=0, microsecond=0)
    reset = day0 + timedelta(days=1)
    h = AQ.health(db, now)
    sync = db.job_runs.find_one({"job": {"$in": ["fixtures_sync", "results_sync"]}, "status": "ok"}, {"_id": 0, "finished_at": 1, "started_at": 1}, sort=[("started_at", -1)])
    last_sync = (sync or {}).get("finished_at") or (sync or {}).get("started_at")
    data = {"id": "data", "module": "pitchapi", "title": "Data",
            "tone": "red" if h["breaker_open"] else _worst(_tone(h["api_calls_today"], h["api_budget"]),
                                                           _age_tone(last_sync, STALE_SYNC)),
            "provider": "PitchAPI", "used": h["api_calls_today"], "cap": h["api_budget"], "reset_at": reset,
            "last_sync": last_sync, "breaker_open": h["breaker_open"]}
    sp = SP.status(db, now)
    live = {"id": "live", "module": "sportapi", "title": "Live", "tone": _tone(sp["calls_today"], sp["cap"]) if sp["enabled"] else "off",
            "provider": "SportAPI", "enabled": sp["enabled"], "used": sp["calls_today"], "cap": sp["cap"], "by_kind": sp["by_kind"], "reset_at": reset,
            "live_now": sp["live_now"], "review": sp["teams"].get("review", 0)}
    run = db.job_runs.find_one({"job": {"$regex": "^engine"}}, {"_id": 0, "started_at": 1, "status": 1}, sort=[("started_at", -1)])
    bad = db.job_runs.count_documents({"job": {"$regex": "^engine"}, "status": "error", "started_at": {"$gte": now - timedelta(hours=24)}})
    own = db.engine_calibration.find_one({"active": True}, {"_id": 1})
    engine = {"id": "engine", "module": "engine", "title": "Engine",
              "tone": "red" if (run or {}).get("status") == "error"
                      else _worst("amber" if bad else "green",
                                  _age_tone((run or {}).get("started_at"), STALE_ENGINE)),
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


def feeds(db, now: datetime | None = None) -> dict:
    """Both football feeds side by side: what each one is for, whether it is working, and what it costs today.

    The two providers do different jobs and their controls used to be in different parts of the menu, so the first
    question in any live problem -- which feed is at fault -- had no screen that answered it (docs/43). Nothing here
    calls a provider.
    """
    now = now or datetime.now(timezone.utc)
    reset = now.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
    h = AQ.health(db, now)
    sync = db.job_runs.find_one({"job": {"$in": ["fixtures_sync", "results_sync"]}, "status": "ok"},
                                {"_id": 0, "finished_at": 1, "started_at": 1}, sort=[("started_at", -1)])
    queued = db.ingest_queue.count_documents({"status": "queued"})
    pitch = {"id": "pitchapi", "name": "PitchAPI", "module": "pitchapi", "route": "/admin/data/pitchapi",
             "feeds": ["Match and player history", "Season backfill", "Depth analytics the forecasts are built from"],
             "enabled": not S.get(db, "ingest.paused_reason"), "key_saved": bool(security.get_provider_key(db, "pitchapi", env_fallback="PITCHAPI_KEY")),
             "used": h["api_calls_today"], "cap": h["api_budget"], "reset_at": reset, "breaker_open": h["breaker_open"],
             "paused_reason": S.get(db, "ingest.paused_reason") or None, "queued": queued,
             "last_at": (sync or {}).get("finished_at") or (sync or {}).get("started_at"),
             "tone": "red" if h["breaker_open"] else _tone(h["api_calls_today"], h["api_budget"])}
    sp = SP.status(db, now)
    fx = sp.get("fixtures") or {}
    live = {"id": "sportapi", "name": "SportAPI", "module": "sportapi", "route": "/admin/data/sportapi",
            "feeds": ["Live scores and the minute", "Match events that feed the cards", "Lineups", "Final scores"],
            "enabled": sp["enabled"], "key_saved": sp["key_saved"], "used": sp["calls_today"], "cap": sp["cap"],
            "reset_at": reset, "last_at": sp.get("last_tick"), "last_result": sp.get("last_result"),
            "live_now": sp["live_now"], "review": (sp.get("teams") or {}).get("review", 0),
            "unlinked": fx.get("unlinked", 0), "unlinked_live": fx.get("unlinked_live", 0),
            "tone": ("red" if fx.get("unlinked_live") else _tone(sp["calls_today"], sp["cap"])) if sp["enabled"] else "off"}
    return {"now": now, "providers": [pitch, live]}


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
