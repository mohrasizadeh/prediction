"""alerts.py -- tell the team when something looks wrong, and send the weekly summary.

Alerts (checked by tick() every ~15 minutes, switch: admin.alerts_enabled)
  signup_drop       sign-ups in the last 7 days fell by admin.alert_signup_drop_pct or more against the 7 days before
  error_spike       server errors in the last hour passed admin.alert_errors_per_hour
  failed_payments   failed payments today passed admin.alert_failed_payments
  plus any alert raised elsewhere through integrations.alert() (a webhook endpoint switched off, a list provider refusing contacts)
Each alert is one row in `admin_alerts` with a key, so the same problem is one open alert, not fifty.
It clears itself when the numbers recover. The team gets one e-mail per alert, and another only after admin.alert_cooldown_hours
if it is still open. Only owners and admins who have not switched `prefs.admin_alerts` off are e-mailed.

Weekly summary (Mondays, switch: admin.digest_enabled) goes only to staff who turned `prefs.admin_digest` on.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import analytics as AN
import emailer as E
import integrations as INT
import reports as R
import settings_store as S

COMPUTED = ("signup_drop", "error_spike", "failed_payments")


def utcnow():
    return datetime.now(timezone.utc)


def _aware(d):
    return d.replace(tzinfo=timezone.utc) if d is not None and d.tzinfo is None else d


def _clear(db, key):
    db.admin_alerts.update_many({"key": key, "resolved": False}, {"$set": {"resolved": True, "resolved_at": utcnow()}})


def evaluate(db, now=None) -> dict:
    now = now or utcnow()
    opened, cleared = [], []

    def rule(key, bad: bool, text: str):
        if bad:
            INT.alert(db, key, text)
            opened.append(key)
        else:
            had = db.admin_alerts.count_documents({"key": key, "resolved": False})
            _clear(db, key)
            if had: cleared.append(key)

    a = db.users.count_documents({"role": "user", "created_at": {"$gte": now - timedelta(days=7)}})
    b = db.users.count_documents({"role": "user", "created_at": {"$gte": now - timedelta(days=14), "$lt": now - timedelta(days=7)}})
    pct = int(S.get(db, "admin.alert_signup_drop_pct"))
    drop = b >= 10 and (b - a) * 100 >= pct * b
    rule("signup_drop", drop, f"Sign-ups fell from {b} to {a} over the last 7 days (down {round((b - a) * 100 / b) if b else 0}%)." if drop else "")
    e = db.app_logs.count_documents({"level": "error", "at": {"$gte": now - timedelta(hours=1)}})
    lim = int(S.get(db, "admin.alert_errors_per_hour"))
    rule("error_spike", e >= lim, f"{e} server errors in the last hour (limit {lim}). Open Logs > Application.")
    f = db.payments.count_documents({"status": {"$in": ["failed", "uncollectible"]}, "created_at": {"$gte": now.replace(hour=0, minute=0, second=0, microsecond=0)}})
    fl = int(S.get(db, "admin.alert_failed_payments"))
    rule("failed_payments", f >= fl, f"{f} failed payments today (limit {fl}). Open Payments.")
    import legal_pages
    todo = legal_pages.needs_review(db)
    rule("legal_pages", bool(todo), "Legal pages still need your review before launch: " + ", ".join(todo)
         + ". They are starter text, not legal advice. Open Pages, check each one (with a lawyer) and save it." if todo else "")
    return {"opened": opened, "cleared": cleared}


def _recipients(db, pref: str, roles=("owner", "admin"), default=True):
    for u in db.users.find({"role": {"$in": list(roles)}, "disabled": {"$ne": True}, "email_verified": True}):
        if (u.get("prefs") or {}).get(pref, default):
            yield u


def notify(db, now=None, client=None) -> int:
    """E-mail the team about open alerts that have not been mailed, or whose cooldown is over."""
    now = now or utcnow()
    cool = timedelta(hours=int(S.get(db, "admin.alert_cooldown_hours")))
    sent = 0
    for al in db.admin_alerts.find({"resolved": False}):
        last = _aware(al.get("notified_at"))
        if last and now - last < cool:
            continue
        for u in _recipients(db, "admin_alerts"):
            r = E.send_template(db, "admin_alert", to=u["email"], user=u, vars={"text": al["text"], "link": f"{E.base_url()}/admin/health"}, idem=f"alert-{al['_id']}-{now:%Y%m%d%H}", client=client)
            sent += 1 if r["status"] == "sent" else 0
        db.admin_alerts.update_one({"_id": al["_id"]}, {"$set": {"notified": True, "notified_at": now}})
    return sent


def run(db, now=None, client=None) -> dict:
    if not S.get(db, "admin.alerts_enabled"):
        return {"skipped": "alerts are off"}
    out = evaluate(db, now)
    out["emails"] = notify(db, now, client)
    return out


def open_alerts(db) -> list[dict]:
    return [{"id": str(a["_id"]), "key": a["key"], "text": a["text"], "at": a.get("at"), "notified_at": a.get("notified_at")}
            for a in db.admin_alerts.find({"resolved": False}).sort("created_at", -1)]


def resolve(db, actor: str, alert_id: str) -> None:
    from bson import ObjectId
    db.admin_alerts.update_one({"_id": ObjectId(alert_id)}, {"$set": {"resolved": True, "resolved_at": utcnow(), "resolved_by": actor}})
    db.audit_log.insert_one({"actor": actor, "action": "alert.resolve", "target": alert_id, "at": utcnow()})


# ----------------------------------------------------------------------------- weekly summary
def _money(cents: int, cur: str) -> str:
    sym = {"cad": "CA$", "usd": "US$", "eur": "EUR ", "gbp": "GBP "}.get(cur, cur.upper() + " ")
    return f"{sym}{cents / 100:,.2f}"


def _arrow(ch):
    return "no earlier data" if ch is None else ("up " if ch > 0 else "down " if ch < 0 else "flat ") + (f"{abs(round(ch * 100))}%" if ch else "")


def build_digest(db, now=None) -> str:
    now = now or utcnow()
    c = R.compare(db, 7, now)
    lines = ["Last 7 days against the 7 days before.", ""]
    names = {"visitors": "Visitors", "signups": "Sign-ups", "verified": "Verified e-mails", "checkouts_started": "Checkouts started", "subscribed": "New paying people",
             "finder_searches": "Finder searches", "newsletter_joins": "List joins"}
    for m in c["metrics"]:
        if m["metric"] in names:
            lines.append(f"{names[m['metric']]}: {m['now']} ({_arrow(m['change'])})")
    for r in c["revenue"]:
        lines.append(f"Money collected ({r['currency'].upper()}): {_money(r['now_cents'], r['currency'])} ({_arrow(r['change'])})")
    pages = AN.top_pages(db, 7, 3, now)
    if pages:
        lines += ["", "Top pages: " + ", ".join(f"{p['path']} ({p['views']})" for p in pages)]
    acq = R.acquisition(db, 7, now)["rows"][:3]
    if acq:
        lines.append("Top sources by sign-ups: " + ", ".join(f"{r['source']}/{r['medium']} ({r['signups']})" for r in acq if r["signups"]))
    pop = [r for r in R.popup_report(db)["rows"] if r["view"]][:3]
    if pop:
        lines.append("Popups: " + ", ".join(f"{r['name']} ({r['view']} views, {round((r['submit_rate'] or r['click_rate'] or 0) * 100, 1)}% acted)" for r in pop))
    op = open_alerts(db)
    lines += ["", f"Open alerts: {len(op)}" + ("" if not op else " - " + "; ".join(a['text'] for a in op[:3]))]
    return "\n".join(lines)


def send_digest(db, now=None, client=None) -> dict:
    if not S.get(db, "admin.digest_enabled"):
        return {"skipped": "digest is off"}
    body = build_digest(db, now)
    sent = 0
    for u in _recipients(db, "admin_digest", roles=("owner", "admin", "analyst"), default=False):
        r = E.send_template(db, "team_digest", to=u["email"], user=u, vars={"summary": body, "link": f"{E.base_url()}/admin"}, idem=f"digest-{u['id']}-{(now or utcnow()):%G%V}", client=client)
        sent += 1 if r["status"] == "sent" else 0
    return {"sent": sent}
