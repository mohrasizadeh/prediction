"""selftest_screens.py -- the page switches (docs/67).

Proves the thing that was actually broken: every `features.*` flag now REACHES the browser. They
existed in the registry from the start and were read nowhere but billing and maintenance, so the
owner could switch a page off and nothing would happen -- which is worse than having no switch,
because the nav looked the same and the page kept answering.
"""
import os, sys, base64
os.environ.setdefault("APP_ENCRYPTION_KEY", base64.b64encode(os.urandom(32)).decode())
HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
import mongomock
import admin_shell, mongo_init, settings_store as S, site_studio as SS


def check(c, m):
    if not c:
        print("  FAIL", m); sys.exit(1)
    print("  ok  ", m)


db = mongomock.MongoClient()["sc"]; mongo_init.ensure_indexes(db)

cfg = SS.public_config(db)
check("features" in cfg, "the public config carries a features block at all")
feats = cfg["features"]

# every switch in the registry must arrive, or the screen offers a control that governs nothing
reg = [k for k in S.registry() if k.startswith("features.")]
missing = [k for k in reg if k[len("features."):] not in feats]
check(not missing, f"all {len(reg)} features.* flags reach the browser (missing: {missing})")
check(all(isinstance(v, bool) for v in feats.values()), "and each arrives as a plain true/false")

# the four pages that had no switch before
for k in ("likely", "combos", "compare", "explore"):
    check(k in feats, f"'{k}' now has a switch -- it had none, so that page could not be hidden")

# flipping one is visible in the very next config read
check(feats["insights"] is True, "insights starts on")
S.put(db, "features.insights", False)
check(SS.public_config(db)["features"]["insights"] is False, "switching it off shows up in the config the browser reads")
S.put(db, "features.insights", True)
check(SS.public_config(db)["features"]["insights"] is True, "and back on again")

# the admin menu offers the screen, and does not collide with the CMS one. Asserted, not skipped:
# a check that quietly does nothing when it cannot find the menu is worse than no check.
ids = [row[0] for row in admin_shell.MODULES]
check(ids.count("screens") == 1, "the admin menu has exactly one Screens entry")
check(ids.count("pages") == 1 and "screens" in ids,
      "and it is separate from the CMS Pages entry, which kept its id -- two menu items with one "
      "name is a trap for whoever wants the other one")
labels = {row[0]: row[1] for row in admin_shell.MODULES}
check(labels["screens"] == "Screens" and labels["pages"] == "Pages", "the two are told apart by name too")
routes = {row[0]: row[4] for row in admin_shell.MODULES}
check(routes["screens"] == "/admin/screens" and routes["pages"] != routes["screens"], "and by route")

# ---------------------------------------------------------------- the waitlist signup (docs/68)
import newsletter as N
S.put(db, "newsletter.consent_text", "Yes, send me the match-day e-mail. I can unsubscribe from any of them.")
r = N.subscribe(db, "Reader@Example.test", source="waitlist", consent=True,
                consent_text=S.get(db, "newsletter.consent_text"), name="  Sam  ")
check(r in ("pending", "confirmed"), "a waitlist signup is accepted")
row = db.newsletter.find_one({"email": "reader@example.test"})
check(row and row["source"] == "waitlist", "and is recorded as coming from the waitlist, not the footer")
check(row.get("name") == "Sam", "the name is stored, trimmed")

# signing up without a name must not wipe a name given earlier
N.subscribe(db, "reader@example.test", source="waitlist", consent=True,
            consent_text=S.get(db, "newsletter.consent_text"))
check(db.newsletter.find_one({"email": "reader@example.test"}).get("name") == "Sam",
      "a later signup with no name leaves the one already there alone")

# consent is still required -- the waitlist does not get its own looser rule
try:
    N.subscribe(db, "no@example.test", source="waitlist", consent=False,
                consent_text=S.get(db, "newsletter.consent_text"), name="No")
    check(False, "consent must still be required")
except Exception as e:
    check("CONSENT" in str(getattr(e, "code", "")) or "tick" in str(e).lower(),
          "consent is still required on the waitlist form")

print("selftest_screens: all checks passed")
