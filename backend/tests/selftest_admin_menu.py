"""The admin menu, and where the football feed lives in it (docs/43, docs/88).

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
# ONE provider, not three. This asserted the three-entry menu while PitchAPI drove the jobs and
# SportAPI drove the live tick; both are gone and so are their screens (docs/88). The list is
# written out rather than filtered so that adding a provider back has to be a deliberate edit here.
check(feeds == ["feeds", "apifootball", "leagues", "jobs"],
      f"one group holds every football pull, and it is one provider: {feeds}")
check(not any(m in MODS for m in ("pitchapi", "sportapi")),
      "no menu entry survives for a provider we no longer call")
check(MODS["apifootball"][4] == "/admin/data/apifootball",
      "API-Football has a route of its own, so it can be linked and pinned")
# THE PIPELINE MOVED, so this is now the inverse of what it used to assert. It said the two old
# providers must KEEP their screens, because the jobs called PitchClient and the live tick called
# SportAPI and a control for a running feed should not be URL-only. Both halves of that are false
# now (docs/88), and a menu entry is the cheap half of the claim -- what matters is that the
# running code no longer reaches for either provider, so the screens are not merely hidden.
import re as _re, pathlib as _pl
_root = _pl.Path(__file__).resolve().parent.parent
_live = (_root / "routes_live.py").read_text()
_jobs = (_root / "jobs.py").read_text()
check("pitchapi" not in MODS and "sportapi" not in MODS,
      "the retired providers have no menu entry")
check("live_af" in _live and _re.search(r"return SP\.live_tick", _live) is None,
      "the live tick goes to API-Football, with no branch back to SportAPI")
# The CALL, not the word: the comment explaining why the step went is worth keeping, and a test
# that forbids naming a thing forbids explaining it.
check(_re.search(r"^\s*import pitch_photos", _jobs, _re.M) is None
      and "PP.plan" not in _jobs,
      "the job tick has no PitchAPI photo step: pictures come from one place")
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
# Both tiles open API-Football now, because that is what serves both. The original complaint these
# pin -- a tile opening the job list or Integrations instead of the feed behind it -- still holds;
# only the feed changed.
check(tiles["data"]["module"] == "apifootball", "the Data tile on Home opens its provider, not the job list")
check(tiles["live"]["module"] == "apifootball", "the Live tile opens the feed behind it, not Integrations")
check(tiles["data"]["provider"] == "API-Football" and tiles["live"]["provider"] == "API-Football",
      "each tile names the provider actually serving it")
for t in tiles.values():
    check(t["module"] in MODS, f"the {t['title']} tile points at a module that exists ({t['module']})")

# ---------------------------------------------------------------- both feeds described in one place
f = AH.feeds(db, now)
names = [p["name"] for p in f["providers"]]
# ONE ROW. This asserted two, named PitchAPI and SportAPI, each linking to its own screen. The
# panel exists to answer "which feed is at fault" in a live problem (docs/43); with one feed the
# honest answer is one row, and two rows pointing at the same screen would be theatre.
check(names == ["API-Football"], f"one feed, named: {names}")
for p in f["providers"]:
    check(p["feeds"] and all(isinstance(x, str) for x in p["feeds"]), f"{p['name']} says what it is for")
    check(p["route"].startswith(MODS[p["module"]][4]), f"{p['name']} links to its own screen")
    check(p["cap"] and p["tone"] in ("green", "amber", "red", "off"), f"{p['name']} carries its budget and a tone")
# The one row has to claim every job the old two did between them, or something is being served by
# a feed this panel does not mention -- which is the failure it was built to prevent.
only = f["providers"][0]["feeds"]
for job in ("backfill", "live scores", "events", "lineups", "crests"):
    check(any(job in x.lower() for x in only), f"the one row claims {job}")

print("\nALL ADMIN MENU CHECKS PASSED")
