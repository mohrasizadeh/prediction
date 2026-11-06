"""admin_queries.py -- everything the admin panel reads and the user-management actions.

Each reader takes `actor` (the signed-in staff user) and hides personal data the role may not see:
  users.pii  -> full e-mail, IP, user agent.   Without it: j***@gmail.com, 203.0.113.x, no user agent.
Pagination is always page + limit (limit capped at 100). Nothing here returns password hashes,
2FA secrets, recovery codes, session tokens or API keys.
"""
from __future__ import annotations

import re
import secrets
from datetime import datetime, timedelta, timezone

import accounts as A
import plans as P
import settings_store as S

LIVE = ["active", "trialing", "past_due"]


def utcnow():
    return datetime.now(timezone.utc)


# ----------------------------------------------------------------------------- masking
def mask_email(e: str | None) -> str | None:
    if not e or "@" not in e:
        return e
    name, dom = e.split("@", 1)
    return (name[:1] + "***@" + dom)


def mask_ip(ip: str | None) -> str | None:
    if not ip:
        return ip
    if ":" in ip:
        return ip.split(":")[0] + ":…"
    p = ip.split(".")
    return ".".join(p[:3] + ["x"]) if len(p) == 4 else ip


def mask_row(row: dict, pii: bool) -> dict:
    if pii:
        return row
    r = dict(row)
    for k in ("email", "to", "by_email"):
        if isinstance(r.get(k), str):
            r[k] = mask_email(r[k])
    if "ip" in r: r["ip"] = mask_ip(r["ip"])
    if "last_login_ip" in r: r["last_login_ip"] = mask_ip(r["last_login_ip"])
    for k in ("ua", "trace"):
        r.pop(k, None)
    return r


def page_args(page, limit):
    limit = max(1, min(int(limit or 25), 100))
    page = max(1, int(page or 1))
    return page, limit, (page - 1) * limit


def paged(db, coll, q, sort, page, limit, proj=None, pii=True, mask=True):
    page, limit, skip = page_args(page, limit)
    cur = db[coll].find(q, proj).sort(sort).skip(skip).limit(limit)
    rows = []
    for r in cur:
        _id = r.pop("_id", None)
        r.setdefault("id", str(_id) if _id is not None else None)
        rows.append(mask_row(r, pii) if mask else r)
    return {"rows": rows, "page": page, "limit": limit, "total": db[coll].count_documents(q)}


# ----------------------------------------------------------------------------- users
def _plan_ids(db):
    live = {s["user_id"] for s in db.subscriptions.find({"status": {"$in": LIVE}}, {"user_id": 1}) if s.get("user_id")}
    comp = {u["id"] for u in db.users.find({"comp": {"$exists": True}}, {"id": 1})}
    return live, comp


def list_users(db, actor, *, q="", role=None, plan=None, verified=None, disabled=None, created_from=None, created_to=None,
               sort="created_at", direction=-1, page=1, limit=25) -> dict:
    pii = A.can(actor, "users.pii")
    f: dict = {"deleted_at": {"$exists": False}}
    q = (q or "").strip()
    if q:
        if "@" in q:
            if not pii:
                return {"rows": [], "page": 1, "limit": limit, "total": 0, "note": "Your role cannot search by e-mail."}
            f["email"] = {"$regex": re.escape(q.lower())}
        else:
            f["$or"] = [{"id": q}, {"display_name": {"$regex": re.escape(q), "$options": "i"}}] + ([{"email": {"$regex": "^" + re.escape(q.lower())}}] if pii else [])
    if role in A.ROLES: f["role"] = role
    if verified is not None: f["email_verified"] = bool(verified)
    if disabled is not None: f["disabled"] = bool(disabled) if disabled else {"$ne": True}
    rng = {}
    if created_from: rng["$gte"] = created_from
    if created_to: rng["$lt"] = created_to
    if rng: f["created_at"] = rng
    if plan in ("free", "paid", "comp", "trial", "past_due"):
        live, comp = _plan_ids(db)
        if plan == "paid": f["id"] = {"$in": list({s["user_id"] for s in db.subscriptions.find({"status": "active"}) if s.get("user_id")})}
        elif plan == "trial": f["id"] = {"$in": list({s["user_id"] for s in db.subscriptions.find({"status": "trialing"}) if s.get("user_id")})}
        elif plan == "past_due": f["id"] = {"$in": list({s["user_id"] for s in db.subscriptions.find({"status": "past_due"}) if s.get("user_id")})}
        elif plan == "comp": f["id"] = {"$in": list(comp)}
        else: f["id"] = {"$nin": list(live | comp)}
    if sort not in ("created_at", "last_login_at", "email"):
        sort = "created_at"
    page, limit, skip = page_args(page, limit)
    total = db.users.count_documents(f)
    rows = []
    for u in db.users.find(f).sort(sort, 1 if direction == 1 else -1).skip(skip).limit(limit):
        ep = P.effective_plan(db, u)
        rows.append({"id": u["id"], "email": u["email"] if pii else mask_email(u["email"]), "display_name": u.get("display_name", ""),
                     "role": u["role"], "created_at": u.get("created_at"), "last_login_at": u.get("last_login_at"),
                     "email_verified": bool(u.get("email_verified")), "disabled": bool(u.get("disabled")),
                     "two_factor": bool((u.get("totp") or {}).get("enabled")), "plan": ep["plan_key"], "plan_source": ep["source"], "plan_status": ep.get("status"),
                     "has_stripe": bool(u.get("stripe_customer_id"))})
    return {"rows": rows, "page": page, "limit": limit, "total": total}


def user_detail(db, actor, user_id: str) -> dict | None:
    u = db.users.find_one({"id": user_id})
    if not u or u.get("deleted_at"):
        return None
    pii = A.can(actor, "users.pii")
    ep = P.effective_plan(db, u)
    prof = A.public_user(u) | {"last_login_at": u.get("last_login_at"), "last_login_ip": u.get("last_login_ip"), "disabled": bool(u.get("disabled")),
                               "stripe_customer_id": u.get("stripe_customer_id"), "comp": u.get("comp"), "had_trial": bool(u.get("had_trial"))}
    if not pii:
        prof["email"] = mask_email(prof["email"])
    prof = mask_row(prof, pii)
    ev = lambda coll, q, sort, n: [mask_row({k: v for k, v in r.items() if k != "_id"}, pii) for r in db[coll].find(q).sort(sort).limit(n)]
    sessions = [{"sid": s["sid"], "created_at": s["created_at"], "last_seen": s["last_seen"], "ip": s.get("ip"), "ua": s.get("ua")} for s in db.sessions.find({"user_id": user_id}).sort("last_seen", -1).limit(10)]
    return {"profile": prof, "plan": {k: v for k, v in ep.items() if k != "entitlements"}, "entitlements": ep["entitlements"],
            "subscriptions": [{**{k: v for k, v in s.items() if k != "_id"}, "id": s["_id"]} for s in db.subscriptions.find({"user_id": user_id}).sort("created_at", -1).limit(10)],
            "payments": [{**{k: v for k, v in p.items() if k != "_id"}, "id": p["_id"]} for p in db.payments.find({"user_id": user_id}).sort("created_at", -1).limit(20)],
            "sessions": [mask_row(s, pii) for s in sessions],
            "emails": ev("email_log", {"user_id": user_id}, [("at", -1)], 20),
            "sign_ins": ev("auth_log", {"user_id": user_id}, [("at", -1)], 20),
            "events": ev("events", {"user_id": user_id}, [("at", -1)], 20),
            "notes": ev("admin_notes", {"user_id": user_id}, [("at", -1)], 50),
            "counts": {"follows": db.follows.count_documents({"user_id": user_id}), "saved": db.saved_forecasts.count_documents({"user_id": user_id}),
                       "notes": db.notes.count_documents({"user_id": user_id})}}


def add_note(db, user_id: str, text: str, actor) -> None:
    if not db.users.find_one({"id": user_id}):
        raise A.AuthError("NOT_FOUND", 404)
    text = (text or "").strip()
    if not 1 <= len(text) <= 1000:
        raise A.AuthError("BAD_NOTE", 400, "A note is 1 to 1000 characters.")
    db.admin_notes.insert_one({"user_id": user_id, "text": text, "by": actor["email"], "at": utcnow()})
    audit(db, actor, "user.note", user_id)


def audit(db, actor, action, target, detail=None) -> None:
    db.audit_log.insert_one({"actor": actor["email"], "actor_role": actor.get("role"), "action": action, "target": target, "detail": detail, "at": utcnow()})


def guard_target(db, actor, target_id: str, allow_self=False):
    """Staff can act on normal users. Acting on other staff needs staff.manage (owner). Never on yourself for risky actions."""
    t = db.users.find_one({"id": target_id})
    if not t:
        raise A.AuthError("NOT_FOUND", 404, "No such user.")
    if t["id"] == actor["id"] and not allow_self:
        raise A.AuthError("SELF_ACTION", 409, "You cannot do this to your own account.")
    if t["role"] in A.STAFF and not A.can(actor, "staff.manage"):
        raise A.AuthError("FORBIDDEN", 403, "Only an owner can change a staff account.")
    return t


def disable_user(db, actor, user_id, disabled: bool, reason: str):
    guard_target(db, actor, user_id)
    if not (reason or "").strip():
        raise A.AuthError("REASON_REQUIRED", 400, "Say why.")
    A.set_disabled(db, user_id, disabled, actor["email"])
    audit(db, actor, "user.disable" if disabled else "user.enable", user_id, {"reason": reason.strip()[:200]})


def force_logout(db, actor, user_id, reason: str = ""):
    guard_target(db, actor, user_id, allow_self=True)
    n = A.revoke_all(db, user_id)
    # The screen now asks why before it cuts someone's sessions, so the answer is kept with the
    # row rather than dropped on the floor.
    audit(db, actor, "user.force_logout", user_id, {"sessions": n, "reason": (reason or "")[:200]})
    return n


def purge_user(db, actor, user_id):
    guard_target(db, actor, user_id)
    info = A.delete_account(db, user_id, by=actor["email"])
    audit(db, actor, "user.purge", user_id)
    return info


# ----------------------------------------------------------------------------- lists
def list_subscriptions(db, actor, *, status=None, plan=None, page=1, limit=25):
    q = {}
    if status: q["status"] = status
    if plan: q["plan_key"] = plan
    return _with_emails(db, actor, paged(db, "subscriptions", q, [("updated_at", -1)], page, limit))


def list_payments(db, actor, *, status=None, user_id=None, date_from=None, date_to=None, page=1, limit=25):
    q = {}
    if status: q["status"] = status
    if user_id: q["user_id"] = user_id
    rng = {}
    if date_from: rng["$gte"] = date_from
    if date_to: rng["$lt"] = date_to
    if rng: q["created_at"] = rng
    return _with_emails(db, actor, paged(db, "payments", q, [("created_at", -1)], page, limit))


def _with_emails(db, actor, r):
    pii = A.can(actor, "users.pii")
    ids = list({x["user_id"] for x in r["rows"] if x.get("user_id")})
    em = {u["id"]: (u["email"] if pii else mask_email(u["email"])) for u in db.users.find({"id": {"$in": ids}}, {"id": 1, "email": 1})}
    for x in r["rows"]:
        x.setdefault("email", em.get(x.get("user_id")) or "Deleted member")
    return r


def list_staff(db):
    return [{"id": u["id"], "email": u["email"], "role": u["role"], "two_factor": bool((u.get("totp") or {}).get("enabled")),
             "last_login_at": u.get("last_login_at"), "disabled": bool(u.get("disabled"))}
            for u in db.users.find({"role": {"$in": list(A.STAFF)}}).sort("created_at", 1)]


LOGS = {   # name -> (collection, perm for raw view, default sort, filterable fields)
    "audit": ("audit_log", "logs.read", [("at", -1)], ("actor", "action", "target")),
    "auth": ("auth_log", "logs.read", [("at", -1)], ("event", "ok", "user_id")),
    "app": ("app_logs", "logs.read", [("at", -1)], ("level", "status", "path")),
    "api": ("api_call_log", "logs.read", [("at", -1)], ("purpose", "status")),
    "webhooks": ("webhook_events", "logs.read", [("received_at", -1)], ("provider", "status", "type")),
    "jobs": ("job_runs", "logs.read", [("started_at", -1)], ("job", "status")),
    "issues": ("ingest_issues", "logs.read", [("at", -1)], ("resolved", "kind")),
    "email": ("email_log", "email.read", [("at", -1)], ("status", "template", "user_id")),
}


def list_logs(db, actor, kind: str, filters: dict | None = None, page=1, limit=50, since: datetime | None = None):
    if kind not in LOGS:
        raise A.AuthError("UNKNOWN_LOG", 404)
    coll, perm, sort, fields = LOGS[kind]
    if not A.can(actor, perm):
        raise A.AuthError("FORBIDDEN", 403)
    q = {}
    for k, v in (filters or {}).items():
        if k in fields and v not in (None, ""):
            q[k] = {"true": True, "false": False}.get(v, v) if isinstance(v, str) else v
    if since:
        q[sort[0][0]] = {"$gte": since}
    return paged(db, coll, q, sort, page, limit, pii=A.can(actor, "logs.pii"))


# ----------------------------------------------------------------------------- health and security
def health(db, now=None) -> dict:
    now = now or utcnow()
    day_ago = now - timedelta(hours=24)
    start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    last_run = db.job_runs.find_one({}, sort=[("started_at", -1)])
    breaker = db.job_locks.find_one({"_id": "pitch_breaker"})
    queue = {r["_id"]: r["n"] for r in db.ingest_queue.aggregate([{"$group": {"_id": "$status", "n": {"$sum": 1}}}])}
    calls_today = db.api_call_log.count_documents({"at": {"$gte": start}, "cached": {"$ne": True}})
    budget = S.get(db, "ingest.daily_call_budget")
    emailed = db.email_log.count_documents({"at": {"$gte": start}, "status": {"$in": ["sent", "delivered"]}})
    alerts = []
    def alert(level, msg): alerts.append({"level": level, "message": msg})
    if breaker: alert("red", f"PitchAPI breaker is open: {breaker.get('reason', '')}")
    if S.get(db, "ingest.paused_reason"): alert("red", S.get(db, "ingest.paused_reason"))
    if last_run is None or (now - A._aware(last_run["started_at"])) > timedelta(hours=3): alert("amber", "No background job has run in the last 3 hours. Check the scheduler ping.")
    if calls_today > 0.8 * budget: alert("amber", f"PitchAPI calls today: {calls_today} of {budget}.")
    we = db.webhook_events.count_documents({"status": "error", "received_at": {"$gte": day_ago}})
    if we: alert("red", f"{we} webhook event(s) failed in the last 24 hours. Billing may be out of date.")
    e5 = db.app_logs.count_documents({"level": "error", "at": {"$gte": day_ago}})
    if e5 > 5: alert("amber", f"{e5} server errors in the last 24 hours.")
    nofa = db.users.count_documents({"role": {"$in": list(A.STAFF)}, "totp.enabled": {"$ne": True}, "disabled": {"$ne": True}})
    if nofa: alert("amber", f"{nofa} staff account(s) have no two-factor sign-in.")
    if S.get(db, "features.billing") and not S.get(db, "email.enabled"): alert("amber", "Billing is on but e-mail is off. Receipts will not be sent.")
    if S.get(db, "features.billing") and S.get(db, "billing.mode") == "test": alert("amber", "Billing is on in TEST mode. No real money moves.")
    for al in db.admin_alerts.find({"resolved": False}):
        alert("red", al["text"])
    return {"alerts": alerts, "last_job_run": last_run and {"job": last_run.get("job"), "at": last_run.get("started_at"), "status": last_run.get("status")},
            "queue": queue, "breaker_open": bool(breaker), "api_calls_today": calls_today, "api_budget": budget,
            "emails_today": emailed, "email_cap": S.get(db, "email.daily_send_cap"), "webhook_errors_24h": we, "server_errors_24h": e5,
            "users": db.users.count_documents({}), "db_ok": True}


def security_overview(db, now=None) -> dict:
    now = now or utcnow()
    day_ago = now - timedelta(hours=24)
    hourly = {}
    for r in db.auth_log.find({"event": "login", "ok": False, "at": {"$gte": day_ago}}, {"at": 1}):
        h = A._aware(r["at"]).strftime("%H:00")
        hourly[h] = hourly.get(h, 0) + 1
    return {"failed_logins_24h": sum(hourly.values()), "failed_by_hour": hourly,
            "locked_accounts": db.users.count_documents({"locked_until": {"$gt": now}}),
            "rate_limited_24h": db.app_logs.count_documents({"status": 429, "at": {"$gte": day_ago}}),
            "bad_origin_24h": db.app_logs.count_documents({"status": 403, "at": {"$gte": day_ago}}),
            "staff": list_staff(db), "staff_without_2fa": db.users.count_documents({"role": {"$in": list(A.STAFF)}, "totp.enabled": {"$ne": True}, "disabled": {"$ne": True}}),
            "active_staff_sessions": db.sessions.count_documents({"staff": True, "expires_at": {"$gt": now}}),
            "recent_staff_actions": [{k: v for k, v in r.items() if k != "_id"} for r in db.audit_log.find({"actor_role": {"$in": list(A.STAFF)}}).sort("at", -1).limit(15)]}


# ----------------------------------------------------------------------------- announcements, contact
def save_announcement(db, actor, ann_id, text, level="info", audience="all", starts_at=None, ends_at=None, active=True):
    from bson import ObjectId
    if level not in ("info", "warn") or audience not in ("all", "free", "paid", "signed_out"):
        raise A.AuthError("BAD_ANNOUNCEMENT", 400)
    if not 1 <= len((text or "").strip()) <= 240:
        raise A.AuthError("BAD_ANNOUNCEMENT", 400, "Text: 1 to 240 characters.")
    import textguard
    textguard.require_clean("Announcement", text)
    doc = {"text": text.strip(), "level": level, "audience": audience, "starts_at": starts_at, "ends_at": ends_at, "active": bool(active), "updated_at": utcnow(), "by": actor["email"]}
    if ann_id:
        db.announcements.update_one({"_id": ObjectId(ann_id)}, {"$set": doc})
    else:
        ann_id = str(db.announcements.insert_one({**doc, "created_at": utcnow()}).inserted_id)
    audit(db, actor, "announcement.save", ann_id)
    return ann_id


def active_announcements(db, user, now=None) -> list[dict]:
    now = now or utcnow()
    src = P.effective_plan(db, user)["source"] if user else "anonymous"
    mine = {"all"} | ({"signed_out"} if not user else set()) | ({"paid"} if src in ("subscription", "comp") else {"free"} if user else set())
    out = []
    for a in db.announcements.find({"active": True, "audience": {"$in": list(mine)}}):
        if a.get("starts_at") and A._aware(a["starts_at"]) > now: continue
        if a.get("ends_at") and A._aware(a["ends_at"]) < now: continue
        out.append({"id": str(a["_id"]), "text": a["text"], "level": a["level"]})
    return out


def add_contact(db, name, email, message, ip=None):
    name, message = (name or "").strip()[:80], (message or "").strip()
    email = A.norm_email(email)
    if not 5 <= len(message) <= 4000:
        raise A.AuthError("BAD_MESSAGE", 400, "Write between 5 and 4000 characters.")
    return str(db.contact_messages.insert_one({"name": name, "email": email, "message": message, "status": "new", "at": utcnow(), "ip": ip}).inserted_id)


def update_contact(db, actor, msg_id, status, note=None):
    from bson import ObjectId
    if status not in ("new", "read", "replied", "spam", "closed"):
        raise A.AuthError("BAD_STATUS", 400)
    db.contact_messages.update_one({"_id": ObjectId(msg_id)}, {"$set": {"status": status, "handled_by": actor["email"], "handled_at": utcnow(), **({"note": note[:500]} if note else {})}})
    audit(db, actor, "contact.update", msg_id, {"status": status})


# ----------------------------------------------------------------------------- brain layers
def brain_status(db) -> dict:
    """What the brain is using right now: the latest gate result per league and layer, settings, and how much
    of each club's calendar we know. The admin screen 'Brain layers' reads this."""
    gates = {}
    for g in db.engine_gates.find({}, {"_id": 0}).sort("at", -1):
        gates.setdefault((g["league_iid"], g["layer"]), g)
    cal = db.club_calendar.aggregate([{"$group": {"_id": "$comp", "n": {"$sum": 1}}}])
    import calibration as CAL
    own = db.engine_calibration.find_one({"active": True}, {"_id": 0}, sort=[("created_at", -1)])
    pmap = CAL.current(db)
    calib = {"enabled": bool(S.get(db, "engine.calibration")), "auto": bool(S.get(db, "engine.calibration_auto")),
             "version": (pmap or {}).get("version"), "source": "own" if own else ("default" if pmap else "off"),
             "created_at": (own or {}).get("created_at"), "test_logloss": (own or {}).get("test_logloss"),
             "team_shrink": (pmap or {}).get("team_shrink"),
             "scored": db.forecast_outcomes.count_documents({"p_model": {"$ne": None}, "state": {"$in": ["pre", "lineup"]}}),
             "needed": int(S.get(db, "engine.calib_min_scored")),
             "last_refit": (db.job_runs.find_one({"job": "calibration"}, {"_id": 0, "result": 1, "started_at": 1}, sort=[("started_at", -1)]) or None)}
    return {"gates": list(gates.values()), "calibration": calib,
            "engine": {k: S.get(db, k) for k in ("engine.absence_model", "engine.match_context", "engine.strength_decay", "engine.history_rounds")},
            "settings": S.get_many(db, "context."),
            "tactic_layers": S.get(db, "engine.tactic_layers"), "shape_layer": S.get(db, "engine.shape_layer"),
            "calendar_rows_by_competition": {r["_id"]: r["n"] for r in cal},
            "clubs_with_calendar": len(db.club_calendar.distinct("team_iid"))}

