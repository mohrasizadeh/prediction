"""The admin menu, and where the two football feeds live in it (docs/43).

Reported: "sportapi settings is under integration and pitchapi is somewhere else". SportAPI had no menu entry at
all -- it sat at the foot of Integrations, beside e-mail sending and ad tags -- while PitchAPI's controls were
spread over five entries in a group called Data. Nothing told the owner which provider did what.

Proves: the menu is well formed (no duplicate ids or routes, every group in the order list, no icon used twice
inside a group, no label repeating its own group's name); every football feed sits in one group, provider first;
each module has a screen; the home tiles point at the screen that now owns each provider; and GET /admin/feeds
describes both providers.
"""
import datetime as dt
import testkit as K                                   # noqa: F401  (boots the app on an in-memory database)
from testkit import check, db
import admin_shell as M, admin_home as AH

MODS = {m[0]: m for m in M.MODULES}
BY_GROUP = {}
for mid, label, group, icon, route, perms in M.MODULES:
    BY_GROUP.setdefault(group, []).append((mid, label, icon, route))

# ---------------------------------------------------------------- the menu is well formed
check(len(MODS) == len(M.MODULES), "no module id is used twice")
routes = [m[4] for m in M.MODULES]
check(len(set(routes)) == len(routes), "no two modules share a route")
check(all(r == "/admin" or r.startswith("/admin/") for r in routes), "every route is under /admin")
check(set(BY_GROUP) == set(M.GROUP_ORDER), f"every group is in the order list: {set(BY_GROUP) ^ set(M.GROUP_ORDER)}")
seen = [g for g in M.GROUP_ORDER if g in BY_GROUP]
check([m[2] for m in M.MODULES] == [g for g in seen for _ in BY_GROUP[g]],
      "the modules are listed grouped, in the group order: the rail draws them in this order")
for g, items in BY_GROUP.items():
    icons = [i for _, _, i, _ in items]
    check(len(set(icons)) == len(icons), f"no icon is used twice inside {g}: {icons}")
    for _, label, _, _ in items:
        check(g.lower() not in label.lower() or label == g, f"'{label}' does not repeat its group name ({g})")

# ---------------------------------------------------------------- the football feeds
feeds = [mid for mid, _, g, _, _ in [(m[0], m[1], m[2], m[3], m[4]) for m in M.MODULES] if g == "Football data"]
check(feeds == ["feeds", "apifootball", "pitchapi", "sportapi", "leagues", "jobs"],
      f"one group holds every football pull: {feeds}")
check(MODS["apifootball"][4] == "/admin/data/apifootball",
      "API-Football has a route of its own, so it can be linked and pinned")
# Three provider entries is the transitional state, not the end state. The jobs still call
# PitchClient and the live tick still calls SportAPI (docs/81 section 4), and the live tick's
# status and its team-mapping review queue are controls for a feed running right now. Dropping
# them from the menu before the pipeline moves would leave them URL-only.
check("pitchapi" in MODS and "sportapi" in MODS,
      "the providers the jobs actually use keep their screens until the pipeline moves")
check(MODS["leagues"][1] == "Competitions",
      "the leagues entry is called Competitions, because half of them are cups and tournaments")
check(MODS["engine"][2] == "Forecasts", "the engine is not a data feed and is not in that group")
check("Connect" not in M.GROUP_ORDER and MODS["integrations"][2] == "System",
      "the one-module 'Connect' group is gone; Integrations is plumbing, under System")
for gone in ("stats", "cache", "quality", "explorer"):
    check(gone not in MODS, f"'{gone}' is no longer its own menu entry")
    check(gone in M.MOVED, f"...and an old link to it still has somewhere to go: {M.MOVED.get(gone)}")

# ---------------------------------------------------------------- every module can be reached
import re, pathlib
app_js = pathlib.Path(__file__).parents[2].joinpath("frontend/src/admin/AdminApp.jsx").read_text()
screens = set(re.findall(r"(\w+):\s*\w+", app_js[app_js.index("const SCREENS"):app_js.index("const WITH_TABS")]))
missing = [m[0] for m in M.MODULES if m[0] not in screens]
check(not missing, f"every module in the menu has a screen behind it: missing {missing}")
for gone in ("stats", "cache", "quality", "explorer"):
    check(gone not in screens, f"'{gone}' is not wired as a top-level screen any more")

# ---------------------------------------------------------------- the home tiles point at the right screens
now = dt.datetime.now(dt.timezone.utc)
tiles = {t["id"]: t for t in AH.tiles(db, now)}
check(tiles["data"]["module"] == "pitchapi", "the Data tile on Home opens its provider, not the job list")
check(tiles["live"]["module"] == "sportapi", "the Live tile opens SportAPI, not Integrations: this was the complaint")
check(tiles["data"]["provider"] == "PitchAPI" and tiles["live"]["provider"] == "SportAPI",
      "each tile names the provider actually serving it, so the board does not claim a feed we have not moved")
for t in tiles.values():
    check(t["module"] in MODS, f"the {t['title']} tile points at a module that exists ({t['module']})")

# ---------------------------------------------------------------- both feeds described in one place
f = AH.feeds(db, now)
names = [p["name"] for p in f["providers"]]
# One provider does every pull now, but the two JOBS are still different -- the backfill spends a
# budget, the live tick watches a clock -- so the panel keeps two rows and both name the provider.
check(names == ["PitchAPI", "SportAPI"], f"both feeds, backfill first: {names}")
for p in f["providers"]:
    check(p["feeds"] and all(isinstance(x, str) for x in p["feeds"]), f"{p['name']} says what it is for")
    check(p["route"].startswith(MODS[p["module"]][4]), f"{p['name']} links to its own screen")
    check(p["cap"] and p["tone"] in ("green", "amber", "red", "off"), f"{p['name']} carries its budget and a tone")
check("Live scores and the minute" in f["providers"][1]["feeds"], "the second row is the live one")
check(any("backfill" in x.lower() for x in f["providers"][0]["feeds"]), "the first row is the backfill one")

print("\nALL ADMIN MENU CHECKS PASSED")
