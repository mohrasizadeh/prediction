"""plans.py -- plans, entitlements, who is on what, and daily quotas.

A plan is a row in `plans`. Its `entitlements` say what a member of that plan may do.
The admin edits plans; Stripe is only told about the name and the prices (stripe_billing.sync_plan).

effective_plan(db, user) answers "what may this person do right now?" in one place:
    1. billing switched off (features.billing = false)  -> everyone signed in gets the top plan
    2. a comp (free upgrade an admin granted)           -> that plan, until its end date
    3. a live subscription (active / trialing / past_due inside the grace days)
    4. otherwise the default (free) plan
Entitlement value -1 means "no limit". Booleans are on/off.
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

from pymongo import ReturnDocument

import settings_store as S

ENTITLEMENTS = {                    # key: (kind, label, free default)
    "finder_searches_per_day": ("int", "Finder searches per day", 10),
    "finder_leagues": ("int", "Leagues the Finder can search at once", 1),
    "grid_games": ("int", "Games shown in the squad and team grids", 5),
    "insights_per_day": ("int", "Insight cards per day", 20),
    "follows_max": ("int", "Followed teams and players", 10),
    "saved_max": ("int", "Saved forecasts", 20),
    "notes_max": ("int", "Player notes", 20),
    "alerts": ("bool", "Alerts", False),
    "matchup_tab": ("bool", "Tactical matchup tab", False),
    "export": ("bool", "Export to CSV", False),
}
PRO = {"finder_searches_per_day": -1, "finder_leagues": -1, "grid_games": 10, "insights_per_day": -1,
       "follows_max": -1, "saved_max": -1, "notes_max": -1, "alerts": True, "matchup_tab": True, "export": True}
FREE = {k: v[2] for k, v in ENTITLEMENTS.items()}
KEY_RE = re.compile(r"^[a-z][a-z0-9_]{1,30}$")
INTERVALS = ("month", "year")


class PlanError(Exception):
    def __init__(self, code, message=""):
        super().__init__(message or code)
        self.code, self.message = code, message or code


def utcnow():
    return datetime.now(timezone.utc)


def _aware(dt):
    return dt.replace(tzinfo=timezone.utc) if dt is not None and dt.tzinfo is None else dt


def seed(db) -> int:
    """Creates Free and Pro on first start. Prices are placeholders: the admin sets the real ones."""
    n = 0
    if not db.plans.find_one({"key": "free"}):
        db.plans.insert_one({"key": "free", "name": "Free", "tagline": "Everything you need to follow the games.",
                             "bullets": ["Daily insights", "Squad and team grids", "10 Finder searches a day"],
                             "entitlements": dict(FREE), "is_default": True, "visible": True, "archived": False,
                             "sort": 0, "prices": [], "trial_days": 0, "highlight": False, "created_at": utcnow()})
        n += 1
    if not db.plans.find_one({"key": "pro"}):
        db.plans.insert_one({"key": "pro", "name": "Pro", "tagline": "The full picture.",
                             "bullets": ["Unlimited Finder", "Tactical matchup tab", "Alerts and CSV export"],
                             "entitlements": dict(PRO), "is_default": False, "visible": True, "archived": False,
                             "sort": 10, "highlight": True, "trial_days": None, "created_at": utcnow(),
                             "prices": [{"id": "monthly", "interval": "month", "amount_cents": 999, "currency": "cad", "active": True},
                                        {"id": "yearly", "interval": "year", "amount_cents": 7999, "currency": "cad", "active": True}]})
        n += 1
    return n


# ----------------------------------------------------------------------------- reading
def clean_entitlements(ent: dict) -> dict:
    out = {}
    for k, v in (ent or {}).items():
        if k not in ENTITLEMENTS:
            raise PlanError("UNKNOWN_ENTITLEMENT", f"Unknown entitlement: {k}")
        kind = ENTITLEMENTS[k][0]
        if kind == "bool":
            if not isinstance(v, bool):
                raise PlanError("BAD_ENTITLEMENT", f"{k} must be true or false")
            out[k] = v
        else:
            if isinstance(v, bool) or not isinstance(v, int) or v < -1:
                raise PlanError("BAD_ENTITLEMENT", f"{k} must be a whole number, or -1 for no limit")
            out[k] = v
    for k, v in ENTITLEMENTS.items():                 # fill gaps with the free value (closed by default)
        out.setdefault(k, v[2])
    return out


def get_plan(db, key):
    return db.plans.find_one({"key": key}, {"_id": 0})


def default_plan(db):
    return db.plans.find_one({"is_default": True}, {"_id": 0}) or {"key": "free", "name": "Free", "entitlements": dict(FREE)}


def top_plan(db):
    p = list(db.plans.find({"is_default": {"$ne": True}, "archived": {"$ne": True}}, {"_id": 0}).sort("sort", -1).limit(1))
    return p[0] if p else default_plan(db)


def public_plans(db) -> list[dict]:
    """For the pricing page. No Stripe ids."""
    out = []
    for p in db.plans.find({"visible": True, "archived": {"$ne": True}}, {"_id": 0}).sort("sort", 1):
        out.append({"key": p["key"], "name": p["name"], "tagline": p.get("tagline", ""), "bullets": p.get("bullets", []),
                    "highlight": bool(p.get("highlight")), "is_default": bool(p.get("is_default")), "entitlements": p["entitlements"],
                    "trial_days": p.get("trial_days") if p.get("trial_days") is not None else S.get(db, "plans.trial_days"),
                    "prices": [{"id": x["id"], "interval": x["interval"], "amount_cents": x["amount_cents"], "currency": x["currency"]}
                               for x in p.get("prices", []) if x.get("active", True)]})
    return out


def live_subscription(db, user_id: str, now=None):
    now = now or utcnow()
    grace = timedelta(days=int(S.get(db, "billing.past_due_grace_days")))
    for s in db.subscriptions.find({"user_id": user_id, "status": {"$in": ["active", "trialing", "past_due"]}}).sort("current_period_end", -1):
        end = _aware(s.get("current_period_end"))
        if s["status"] == "past_due":
            since = _aware(s.get("past_due_since")) or now
            if now - since > grace:
                continue
        elif end and end + timedelta(days=2) < now:      # 2 days of slack for a late webhook
            continue
        return s
    return None


def effective_plan(db, user: dict | None, now=None) -> dict:
    """{plan_key, plan_name, entitlements, source, status, period_end, cancel_at_period_end}"""
    now = now or utcnow()
    if user is None:
        d = default_plan(db)
        return {"plan_key": d["key"], "plan_name": d["name"], "entitlements": clean_entitlements(d["entitlements"]),
                "source": "anonymous", "status": None}
    if not S.get(db, "features.billing"):
        t = top_plan(db)
        return {"plan_key": t["key"], "plan_name": t["name"], "entitlements": clean_entitlements(t["entitlements"]),
                "source": "billing_off", "status": None}
    comp = user.get("comp")
    if comp and (not comp.get("until") or _aware(comp["until"]) > now):
        p = get_plan(db, comp["plan_key"])
        if p:
            return {"plan_key": p["key"], "plan_name": p["name"], "entitlements": clean_entitlements(p["entitlements"]),
                    "source": "comp", "status": "comp", "period_end": comp.get("until")}
    s = live_subscription(db, user["id"], now)
    if s:
        p = get_plan(db, s["plan_key"])
        if p:
            return {"plan_key": p["key"], "plan_name": p["name"], "entitlements": clean_entitlements(p["entitlements"]),
                    "source": "subscription", "status": s["status"], "period_end": s.get("current_period_end"),
                    "cancel_at_period_end": bool(s.get("cancel_at_period_end")), "interval": s.get("interval")}
    d = default_plan(db)
    return {"plan_key": d["key"], "plan_name": d["name"], "entitlements": clean_entitlements(d["entitlements"]), "source": "free", "status": None}


def ent(db, user, key):
    return effective_plan(db, user)["entitlements"][key]


# ----------------------------------------------------------------------------- quotas
def consume(db, subject: str, name: str, limit: int, now=None) -> tuple[bool, int]:
    """Count one use of `name` today for `subject`. Returns (allowed, used_so_far). limit -1 = no limit.
    A refused call is not counted, so a person at the cap stays at the cap."""
    now = now or utcnow()
    day = now.strftime("%Y-%m-%d")
    if limit < 0:
        return True, 0
    exp = now + timedelta(days=3)
    try:
        doc = db.finder_usage.find_one_and_update(
            {"subject": subject, "day": day, "name": name, "count": {"$lt": limit}},
            {"$inc": {"count": 1}, "$setOnInsert": {"expires_at": exp}}, upsert=True, return_document=ReturnDocument.AFTER)
        return True, doc["count"]
    except Exception as e:                                     # upsert collided with the unique index = already at the cap
        from pymongo.errors import DuplicateKeyError
        if isinstance(e, DuplicateKeyError):
            return False, limit
        raise


def used_today(db, subject: str, name: str, now=None) -> int:
    now = now or utcnow()
    d = db.finder_usage.find_one({"subject": subject, "day": now.strftime("%Y-%m-%d"), "name": name})
    return d["count"] if d else 0


# ----------------------------------------------------------------------------- admin writes
def _clean_prices(prices, old=None):
    old = {p["id"]: p for p in (old or [])}
    out, seen = [], set()
    for p in prices or []:
        pid = str(p.get("id", "")).strip().lower()
        if not KEY_RE.match(pid) or pid in seen:
            raise PlanError("BAD_PRICE", "Each price needs a unique short id like monthly or yearly.")
        seen.add(pid)
        if p.get("interval") not in INTERVALS:
            raise PlanError("BAD_PRICE", "Interval must be month or year.")
        amt = p.get("amount_cents")
        if isinstance(amt, bool) or not isinstance(amt, int) or not (50 <= amt <= 10_000_000):
            raise PlanError("BAD_PRICE", "Amount must be in cents, between 50 and 10,000,000.")
        cur = str(p.get("currency") or "").lower()
        if not re.fullmatch(r"[a-z]{3}", cur):
            raise PlanError("BAD_PRICE", "Currency must be a 3-letter code.")
        prev = old.get(pid)
        row = {"id": pid, "interval": p["interval"], "amount_cents": amt, "currency": cur, "active": bool(p.get("active", True))}
        if prev:                                               # keep the Stripe link only when nothing that Stripe fixes has changed
            same = (prev["amount_cents"], prev["currency"], prev["interval"]) == (amt, cur, p["interval"])
            if same and prev.get("stripe_price_id"):
                row["stripe_price_id"] = prev["stripe_price_id"]
            elif prev.get("stripe_price_id"):
                row["retired_stripe_price_id"] = prev["stripe_price_id"]
        out.append(row)
    return out


def create_plan(db, key, fields: dict, actor: str) -> dict:
    key = (key or "").strip().lower()
    if not KEY_RE.match(key):
        raise PlanError("BAD_KEY", "Plan key: lower-case letters, digits and _, starting with a letter.")
    if db.plans.find_one({"key": key}):
        raise PlanError("EXISTS", "A plan with that key already exists.")
    doc = {"key": key, "name": str(fields.get("name") or key.title())[:40], "tagline": str(fields.get("tagline") or "")[:140],
           "bullets": [str(b)[:100] for b in (fields.get("bullets") or [])][:12], "entitlements": clean_entitlements(fields.get("entitlements") or {}),
           "is_default": False, "visible": bool(fields.get("visible", False)), "archived": False, "sort": int(fields.get("sort", 20)),
           "highlight": bool(fields.get("highlight", False)), "trial_days": fields.get("trial_days"), "created_at": utcnow(),
           "prices": _clean_prices(fields.get("prices"))}
    db.plans.insert_one(dict(doc))
    db.audit_log.insert_one({"actor": actor, "action": "plan.create", "target": key, "at": utcnow()})
    return get_plan(db, key)


def update_plan(db, key, fields: dict, actor: str) -> dict:
    p = db.plans.find_one({"key": key})
    if not p:
        raise PlanError("NOT_FOUND", "No such plan.")
    upd = {}
    if "name" in fields: upd["name"] = str(fields["name"])[:40]
    if "tagline" in fields: upd["tagline"] = str(fields["tagline"])[:140]
    if "bullets" in fields: upd["bullets"] = [str(b)[:100] for b in fields["bullets"]][:12]
    if "entitlements" in fields: upd["entitlements"] = clean_entitlements(fields["entitlements"])
    if "visible" in fields: upd["visible"] = bool(fields["visible"])
    if "highlight" in fields: upd["highlight"] = bool(fields["highlight"])
    if "sort" in fields: upd["sort"] = int(fields["sort"])
    if "trial_days" in fields:
        td = fields["trial_days"]
        if td is not None and (isinstance(td, bool) or not isinstance(td, int) or not 0 <= td <= 365):
            raise PlanError("BAD_TRIAL", "Trial days: 0 to 365, or blank for the default.")
        upd["trial_days"] = td
    if "prices" in fields:
        if p.get("is_default"):
            raise PlanError("DEFAULT_PLAN", "The default plan has no prices.")
        upd["prices"] = _clean_prices(fields["prices"], p.get("prices"))
    if "archived" in fields:
        if p.get("is_default"):
            raise PlanError("DEFAULT_PLAN", "The default plan cannot be archived.")
        if fields["archived"] and db.subscriptions.count_documents({"plan_key": key, "status": {"$in": ["active", "trialing", "past_due"]}}):
            raise PlanError("IN_USE", "People are still subscribed to this plan. Move them first.")
        upd["archived"] = bool(fields["archived"])
        if fields["archived"]:
            upd["visible"] = False
    upd["updated_at"] = utcnow()
    db.plans.update_one({"key": key}, {"$set": upd})
    db.audit_log.insert_one({"actor": actor, "action": "plan.update", "target": key, "detail": sorted(upd), "at": utcnow()})
    return get_plan(db, key)


def grant_comp(db, user_id: str, plan_key: str, days: int | None, reason: str, actor: str) -> None:
    if not reason or len(reason.strip()) < 3:
        raise PlanError("REASON_REQUIRED", "Say why you are giving this.")
    if not get_plan(db, plan_key) or get_plan(db, plan_key).get("is_default"):
        raise PlanError("BAD_PLAN", "Pick a paid plan.")
    until = utcnow() + timedelta(days=days) if days else None
    db.users.update_one({"id": user_id}, {"$set": {"comp": {"plan_key": plan_key, "until": until, "reason": reason.strip()[:200], "by": actor, "at": utcnow()}}})
    db.audit_log.insert_one({"actor": actor, "action": "comp.grant", "target": user_id, "detail": {"plan": plan_key, "days": days, "reason": reason.strip()[:200]}, "at": utcnow()})


def revoke_comp(db, user_id: str, actor: str) -> None:
    db.users.update_one({"id": user_id}, {"$unset": {"comp": ""}})
    db.audit_log.insert_one({"actor": actor, "action": "comp.revoke", "target": user_id, "at": utcnow()})
