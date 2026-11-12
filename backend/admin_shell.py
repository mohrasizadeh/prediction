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
#
# The order here is the order on screen. Groups answer "what am I here to do", and inside a group the most-used
# tool comes first. Everything that pulls football data sits in one group, named after the provider it talks to,
# because the two providers do different jobs and the first question is always which one is at fault (docs/43).
MODULES = [
    ("dashboard", "Home", "Overview", "home", "/admin", ("analytics.read",)),
    ("needs", "Needs you", "Overview", "bell", "/admin/needs", ("logs.read",)),
    ("analytics", "Analytics", "Overview", "bar-chart", "/admin/analytics", ("analytics.read",)),

    # Football data. THREE PROVIDER ENTRIES, ON PURPOSE AND NOT FOR LONG. API-Football is the one
    # we are moving to and the only one with a mapping and a quota screen, but the jobs still call
    # PitchClient and the live tick still calls SportAPI (docs/81 §4), so those two keep their
    # screens: the live tick's status and its team-mapping review queue are operational controls for
    # a feed that is running right now, and taking them out of the menu while they run would leave
    # them reachable only by typing a URL. They go when the pipeline goes, in that same change.
    ("feeds", "Feeds", "Football data", "plug", "/admin/data/feeds", ("logs.read", "jobs.run")),
    ("apifootball", "API-Football", "Football data", "activity", "/admin/data/apifootball", ("logs.read", "jobs.run")),
    ("pitchapi", "PitchAPI", "Football data", "book", "/admin/data/pitchapi", ("jobs.run",)),
    ("sportapi", "SportAPI", "Football data", "radio", "/admin/data/sportapi", ("logs.read", "jobs.run")),
    ("leagues", "Competitions", "Football data", "trophy", "/admin/data/leagues", ("jobs.run",)),
    ("jobs", "Jobs", "Football data", "clock", "/admin/data/jobs", ("jobs.run",)),

    ("engine", "Engine", "Forecasts", "target", "/admin/data/engine", ("jobs.run",)),

    ("users", "Users", "People", "users", "/admin/users", ("users.read",)),
    ("staff", "Staff", "People", "shield", "/admin/staff", ("staff.manage",)),
    ("inbox", "Inbox", "People", "mail", "/admin/inbox", ("inbox.write", "users.read")),

    ("popups", "Popups", "Marketing", "layers", "/admin/popups", ("popups.read",)),
    ("announcements", "Announcements", "Marketing", "flag", "/admin/announcements", ("content.write",)),
    ("blog", "Blog", "Marketing", "book", "/admin/blog", ("content.write",)),
    ("campaigns", "Campaigns", "Marketing", "send", "/admin/campaigns", ("email.write",)),
    ("newsletter", "E-mail list", "Marketing", "list", "/admin/newsletter", ("email.read",)),
    # Both new in docs/60. Media sat under Website as "Images" while its only reader was Site Studio;
    # an e-mail or an ad needs the same library, and that is marketing work, so it moved here and
    # took video with it. The route is unchanged, so an old bookmark still lands.
    ("ads", "Ad builder", "Marketing", "image", "/admin/ads", ("site.read",)),
    ("schedule", "Schedule", "Marketing", "calendar", "/admin/schedule", ("site.read",)),
    ("media", "Media", "Marketing", "film", "/admin/media", ("site.read",)),

    # The group already says E-mail, so the labels do not repeat it.
    ("templates", "Templates", "E-mail", "copy", "/admin/email/templates", ("email.read",)),
    ("email_log", "Log", "E-mail", "list", "/admin/email/log", ("email.read",)),
    ("suppressions", "Blocked addresses", "E-mail", "eye-off", "/admin/email/suppressions", ("email.read",)),

    ("plans", "Plans", "Money", "tag", "/admin/plans", ("plans.read",)),
    ("subscriptions", "Subscriptions", "Money", "credit-card", "/admin/subscriptions", ("billing.read",)),
    ("payments", "Payments", "Money", "receipt", "/admin/payments", ("billing.read",)),
    ("coupons", "Coupons", "Money", "gift", "/admin/coupons", ("billing.write",)),
    ("revenue", "Revenue", "Money", "trending-up", "/admin/revenue", ("billing.read",)),

    ("studio", "Site Studio", "Website", "palette", "/admin/studio", ("site.read",)),
    ("pages", "Pages", "Website", "file-text", "/admin/pages", ("content.write",)),

    ("screens", "Screens", "System", "layers", "/admin/screens", ("settings.read",)),
    ("settings", "Settings", "System", "settings", "/admin/settings", ("settings.read",)),
    ("keys", "Keys", "System", "key", "/admin/keys", ("settings.read",)),
    ("integrations", "Integrations", "System", "external", "/admin/integrations", ("integrations.read",)),
    ("logs", "Logs", "System", "list", "/admin/logs", ("logs.read",)),
    ("security", "Security", "System", "padlock", "/admin/security", ("security.read",)),
    ("health", "Health", "System", "monitor", "/admin/health", ("logs.read",)),
]
GROUP_ORDER = ["Overview", "Football data", "Forecasts", "People", "Marketing", "E-mail", "Money", "Website", "System"]

# Screens folded into another one, kept so an old bookmark or link still lands somewhere sensible. The front end
# redirects; nothing else needs to know.
MOVED = {"stats": "/admin/analytics", "cache": "/admin/data/pitchapi/usage",
         "quality": "/admin/data/pitchapi/quality", "explorer": "/admin/data/pitchapi/explorer"}

# the phone bottom bar prefers these, in this order, from whatever the role may use
DEFAULT_TABS = ["dashboard", "needs", "feeds", "sportapi", "jobs", "engine", "users", "analytics", "studio", "popups", "inbox", "subscriptions", "logs"]
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
