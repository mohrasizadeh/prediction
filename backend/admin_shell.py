"""admin_shell.py -- the list of admin modules, and what each role sees.

One source of truth for the menu. The front end calls GET /api/admin/shell and draws:
  * desktop (>= 1024 px): a left rail with the groups below
  * phone and small tablet (< 1024 px): a bottom app bar with 4 icons + "More". "More" opens a full-screen sheet with every module the
    person may use, grouped, with a search box.
Hiding a module is a convenience only. Every route still checks its permission on the server.
"""
from __future__ import annotations

import accounts as A
import settings_store as S

# id, label, group, icon, route, permissions (any one is enough)
MODULES = [
    ("dashboard", "Home", "Overview", "home", "/admin", ("analytics.read",)),
    ("needs", "Needs you", "Overview", "bell", "/admin/needs", ("logs.read",)),
    ("stats", "Dashboard", "Overview", "bar-chart", "/admin/stats", ("analytics.read",)),
    ("analytics", "Analytics", "Overview", "bar-chart", "/admin/analytics", ("analytics.read",)),
    ("users", "Users", "People", "users", "/admin/users", ("users.read",)),
    ("staff", "Staff", "People", "shield", "/admin/staff", ("staff.manage",)),
    ("inbox", "Inbox", "People", "mail", "/admin/inbox", ("inbox.write", "users.read")),
    ("newsletter", "E-mail list", "People", "list", "/admin/newsletter", ("email.read",)),
    ("popups", "Popups", "Growth", "layers", "/admin/popups", ("popups.read",)),
    ("announcements", "Announcements", "Growth", "bell", "/admin/announcements", ("content.write",)),
    ("campaigns", "Campaigns", "Growth", "send", "/admin/campaigns", ("email.write",)),
    ("studio", "Site Studio", "Site", "palette", "/admin/studio", ("site.read",)),
    ("pages", "Pages", "Site", "file-text", "/admin/pages", ("content.write",)),
    ("media", "Images", "Site", "image", "/admin/media", ("site.read",)),
    ("plans", "Plans", "Money", "tag", "/admin/plans", ("plans.read",)),
    ("subscriptions", "Subscriptions", "Money", "credit-card", "/admin/subscriptions", ("billing.read",)),
    ("payments", "Payments", "Money", "receipt", "/admin/payments", ("billing.read",)),
    ("coupons", "Coupons", "Money", "gift", "/admin/coupons", ("billing.write",)),
    ("revenue", "Revenue", "Money", "trending-up", "/admin/revenue", ("billing.read",)),
    ("templates", "E-mail templates", "E-mail", "mail", "/admin/email/templates", ("email.read",)),
    ("email_log", "E-mail log", "E-mail", "list", "/admin/email/log", ("email.read",)),
    ("suppressions", "Blocked addresses", "E-mail", "shield", "/admin/email/suppressions", ("email.read",)),
    ("integrations", "Integrations", "Connect", "plug", "/admin/integrations", ("integrations.read",)),
    ("leagues", "Leagues", "Data", "trophy", "/admin/data/leagues", ("jobs.run",)),
    ("jobs", "Jobs", "Data", "clock", "/admin/data/jobs", ("jobs.run",)),
    ("quality", "Data quality", "Data", "activity", "/admin/data/quality", ("jobs.run",)),
    ("engine", "Engine", "Data", "target", "/admin/data/engine", ("jobs.run",)),
    ("explorer", "Endpoint explorer", "Data", "compass", "/admin/data/explorer", ("jobs.run",)),
    ("cache", "Cache and usage", "Data", "layers", "/admin/data/cache", ("jobs.run",)),
    ("settings", "Settings", "System", "settings", "/admin/settings", ("settings.read",)),
    ("keys", "Keys", "System", "key", "/admin/keys", ("settings.read",)),
    ("logs", "Logs", "System", "list", "/admin/logs", ("logs.read",)),
    ("security", "Security", "System", "shield", "/admin/security", ("security.read",)),
    ("health", "Health", "System", "activity", "/admin/health", ("logs.read",)),
]
GROUP_ORDER = ["Overview", "People", "Growth", "Site", "Money", "E-mail", "Connect", "Data", "System"]
# the phone bottom bar prefers these, in this order, from whatever the role may use
DEFAULT_TABS = ["dashboard", "needs", "jobs", "engine", "users", "analytics", "studio", "popups", "inbox", "subscriptions", "logs"]
MAX_TABS = 4


def allowed(user: dict) -> list[dict]:
    out = []
    for mid, label, group, icon, route, perms in MODULES:
        if any(A.can(user, p) for p in perms):
            out.append({"id": mid, "label": label, "group": group, "icon": icon, "route": route})
    return out


def tabs_for(user: dict, mods: list[dict]) -> list[str]:
    ids = {m["id"] for m in mods}
    mine = [t for t in (user.get("admin_tabs") or []) if t in ids][:MAX_TABS]
    if len(mine) >= 2:
        return mine
    return [t for t in DEFAULT_TABS if t in ids][:MAX_TABS]


def shell(db, user: dict) -> dict:
    mods = allowed(user)
    groups = [g for g in GROUP_ORDER if any(m["group"] == g for m in mods)]
    open_alerts = db.admin_alerts.count_documents({"resolved": False})
    return {"user": {"id": user["id"], "email": user["email"], "role": user["role"], "display_name": user.get("display_name", "")},
            "groups": groups, "modules": mods, "mobile_tabs": tabs_for(user, mods), "open_alerts": open_alerts,
            "billing_mode": S.get(db, "billing.mode")}


def set_tabs(db, user: dict, ids: list[str]) -> list[str]:
    mods = {m["id"] for m in allowed(user)}
    if not isinstance(ids, list) or not 2 <= len(ids) <= MAX_TABS or len(set(ids)) != len(ids) or any(i not in mods for i in ids):
        raise A.AuthError("BAD_TABS", 400, f"Pick 2 to {MAX_TABS} different modules you can use.")
    db.users.update_one({"id": user["id"]}, {"$set": {"admin_tabs": ids}})
    return ids
