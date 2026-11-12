"""selftest_purge.py -- the fresh start clears the football data and nothing else. docs/83.

The thing being protected is not the deletion, which is easy. It is the LIST: a collection in the
wrong group is a product re-setup on one side and poisoned data on the other, and neither announces
itself. So every group is checked by name, the keep list is checked for the things that would hurt
most, and `unknown()` is checked to fail loudly when a collection nobody classified turns up.

    python3 tests/selftest_purge.py
"""
import os, sys, base64
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
os.environ.setdefault("APP_ENCRYPTION_KEY", base64.b64encode(os.urandom(32)).decode())

import mongomock

import purge as P

OK = []
def check(name, cond):
    cond = bool(cond)
    OK.append(cond)
    print(("  ok     " if cond else "  FAIL   ") + name)


def seeded():
    """A database with something in every collection the module names, so a purge has work to do
    and the keep list has something to protect."""
    db = mongomock.MongoClient()["purge"]
    for name in P.FOOTBALL + P.DERIVED + P.MINE + P.KEPT:
        db[name].insert_one({"seeded": True})
    for name in P.COUNTERS:
        db.counters.update_one({"_id": name}, {"$set": {"seq": 42}}, upsert=True)
    for key in P.JOB_KEYS:
        db.job_locks.update_one({"_id": key}, {"$set": {"reason": "x"}}, upsert=True)
        db.job_state.update_one({"_id": key}, {"$set": {"v": 1}}, upsert=True)
    db.settings.update_one({"key": "ingest.paused_reason"}, {"$set": {"value": "key refused"}}, upsert=True)
    return db


# ---------------------------------------------------------------- the classification
def t_the_groups_are_sane():
    overlap = (set(P.FOOTBALL) & set(P.KEPT)) | (set(P.DERIVED) & set(P.KEPT)) | (set(P.MINE) & set(P.KEPT))
    check(f"nothing is both cleared and kept: {sorted(overlap)}", not overlap)
    check("the three cleared groups do not overlap each other",
          not (set(P.FOOTBALL) & set(P.DERIVED)) and not (set(P.FOOTBALL) & set(P.MINE))
          and not (set(P.DERIVED) & set(P.MINE)))
    for name in ("leagues", "teams", "players", "matches", "player_match_stats", "team_match_stats",
                 "api_cache", "api_call_log", "image_map", "live_fixtures", "sportapi_team_map"):
        check(f"{name} is football data and goes", name in P.FOOTBALL)
    for name in ("forecasts", "forecast_outcomes", "engine_calibration"):
        check(f"{name} was computed from it and goes with it", name in P.DERIVED)


def t_the_things_a_drop_would_have_cost():
    """Each of these is a reason not to let the host discard the database."""
    for name, why in (("users", "the owner's own sign-in"), ("settings", "300 tuned values"),
                      ("provider_keys", "the keys"), ("media", "images already downloaded (docs/79)"),
                      ("site_assets", "the Site Studio"), ("content_pages", "pages built by hand"),
                      ("subscriptions", "billing, tied to live Stripe objects"),
                      ("payments", "billing"), ("blog_posts", "the blog"),
                      ("email_templates", "the e-mail templates"), ("audit_log", "the audit trail")):
        check(f"{name} is kept -- {why}", name in P.KEPT and name not in P.FOOTBALL + P.DERIVED + P.MINE)


def t_user_data_is_opt_in():
    check("follows, notes, saved cards and combos are their own group",
          {"follows", "notes", "saved_forecasts", "combos"} <= set(P.MINE))
    db = seeded()
    without = P.plan(db, include_mine=False)
    withmine = P.plan(db, include_mine=True)
    names = {r["collection"] for r in without["clear"]}
    check("a default purge does not touch them", not (names & set(P.MINE)))
    check("...and asking for them adds exactly those collections",
          {r["collection"] for r in withmine["clear"]} - names == set(P.MINE))
    check("the plan says how many of them there are, so the number is seen before it is typed",
          withmine["mine_total"] == len(P.MINE))


def t_unknown_collection_is_surfaced():
    db = seeded()
    check("a tidy database has nothing unclassified", P.unknown(db) == [])
    db["a_new_collection_nobody_classified"].insert_one({"x": 1})
    check("a collection added later shows up rather than being silently kept or cleared",
          P.unknown(db) == ["a_new_collection_nobody_classified"])
    check("...and the plan carries it to the screen",
          P.plan(db)["unknown"] == ["a_new_collection_nobody_classified"])


# ---------------------------------------------------------------- the plan, then the deed
def t_plan_changes_nothing():
    db = seeded()
    before = {c: db[c].count_documents({}) for c in db.list_collection_names()}
    p = P.plan(db)
    after = {c: db[c].count_documents({}) for c in db.list_collection_names()}
    check("asking what a purge would do does not do any of it", before == after)
    check("every cleared collection is counted from the database, not estimated",
          all(r["documents"] == 1 for r in p["clear"]))
    check("the total is the sum", p["total"] == len(P.FOOTBALL) + len(P.DERIVED))
    check("the keep list is shown too, so it is obvious what survives", len(p["keep"]) > 20)


def t_confirmation_is_required():
    db = seeded()
    for bad in ("", "yes", "delete football data", "DELETE FOOTBALL DATA "):
        try:
            P.run(db, bad)
            check(f"{bad!r} is refused", False)
        except ValueError:
            check(f"{bad!r} is refused", True)
    check("nothing was deleted by a refused attempt", db.leagues.count_documents({}) == 1)


def t_run_clears_the_right_things():
    db = seeded()
    res = P.run(db, P.CONFIRM, actor="owner@example.com")
    for name in P.FOOTBALL + P.DERIVED:
        check(f"{name} is empty", db[name].count_documents({}) == 0)
    for name in P.MINE:
        check(f"{name} survives a default purge", db[name].count_documents({}) == 1)
    kept_ok = [n for n in P.KEPT if n not in ("settings", "admin_notes", "job_locks", "job_state", "counters")]
    check(f"all {len(kept_ok)} kept collections still have their rows",
          all(db[n].count_documents({}) == 1 for n in kept_ok))
    check("the counters are reset, so the first new league is id 1 again",
          all(db.counters.find_one({"_id": n}) is None for n in P.COUNTERS))
    check("the feed breakers and tick state are cleared",
          all(db.job_locks.find_one({"_id": k}) is None for k in P.JOB_KEYS))
    check("a fresh start starts unpaused",
          (db.settings.find_one({"key": "ingest.paused_reason"}) or {}).get("value") == "")
    check("the purge is recorded in a collection that survives it",
          db.admin_notes.count_documents({"kind": "purge"}) == 1)
    check("...with who did it and how much went",
          res["documents"] == len(P.FOOTBALL) + len(P.DERIVED) and res["actor"] == "owner@example.com")


def t_run_with_mine():
    db = seeded()
    P.run(db, P.CONFIRM, include_mine=True)
    check("asked for explicitly, follows and notes go too",
          all(db[n].count_documents({}) == 0 for n in P.MINE))
    check("and the kept list is still untouched", db.users.count_documents({}) == 1
          and db.media.count_documents({}) == 1 and db.provider_keys.count_documents({}) == 1)


def t_indexes_survive():
    """Documents are deleted, collections are not dropped, so the indexes mongo_init built stay and
    the app does not need a restart to work afterwards."""
    db = seeded()
    db.matches.create_index("iid")
    before = len(db.matches.index_information())
    P.run(db, P.CONFIRM)
    check(f"an index on a cleared collection survives ({before} indexes)",
          len(db.matches.index_information()) == before)
    check("...and the collection still exists, empty", "matches" in db.list_collection_names()
          and db.matches.count_documents({}) == 0)


for fn in (t_the_groups_are_sane, t_the_things_a_drop_would_have_cost, t_user_data_is_opt_in,
           t_unknown_collection_is_surfaced, t_plan_changes_nothing, t_confirmation_is_required,
           t_run_clears_the_right_things, t_run_with_mine, t_indexes_survive):
    print(fn.__name__)
    fn()

print()
print(f"{sum(OK)}/{len(OK)} passed")
sys.exit(0 if all(OK) else 1)
