"""Countries are drawn as a round flag; clubs never are (flags.py, queries.attach_images)."""
import sys, os, base64
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("APP_ENCRYPTION_KEY", base64.b64encode(os.urandom(32)).decode())

import mongomock

import flags as FL
import queries as Q

OK = []


def check(name, cond):
    cond = bool(cond)
    OK.append(cond)
    print(("  ok     " if cond else "  FAIL   ") + name)


HERE = os.path.dirname(__file__)
FLAGS = os.path.join(HERE, "..", "..", "frontend", "public", "flags")

print("names map to flags we ship")
for name, code in [("England", "gb-eng"), ("Scotland", "gb-sct"), ("USA", "us"), ("Korea Republic", "kr"),
                   ("Côte d'Ivoire", "ci"), ("Ivory Coast", "ci"), ("Bosnia & Herzegovina", "ba"), ("Türkiye", "tr"),
                   ("Turkey", "tr"), ("China PR", "cn"), ("Congo DR", "cd"), ("Republic of Ireland", "ie"),
                   ("England W", "gb-eng"), ("Spain U21", "es"), ("Curaçao", "cw")]:
    check(f"{name} -> {code}", FL.code_for(name) == code)
check("a club name has no flag", FL.code_for("Arsenal") is None and FL.code_for(None) is None)
missing = sorted({c for c in FL._BY_KEY.values() if not os.path.exists(os.path.join(FLAGS, f"{c}.svg"))})
check(f"every mapped code has an SVG in public/flags (missing: {missing})", not missing)

print("only teams that played an international competition get one")
db = mongomock.MongoClient().db
db.leagues.insert_many([{"iid": 1, "kind": "league"}, {"iid": 2, "kind": "international"}])
db.teams.insert_many([{"iid": 10, "id": "a", "name": "England"}, {"iid": 11, "id": "b", "name": "France"},
                      {"iid": 12, "id": "c", "name": "Brazil"}, {"iid": 13, "id": "d", "name": "Arsenal"}])
db.matches.insert_many([{"iid": 100, "league_iid": 2, "home_iid": 10, "away_iid": 11},
                        {"iid": 101, "league_iid": 1, "home_iid": 12, "away_iid": 13}])   # a club named Brazil
FL.forget()
t = Q._names(db, "teams", [10, 11, 12, 13])
check("England and France are countries", t[10].get("flag") == "gb-eng" and t[11].get("flag") == "fr")
check("a club that happens to be called Brazil keeps its crest", "flag" not in t[12])
check("Arsenal keeps its crest", "flag" not in t[13])
FL.forget()

print(f"\n{sum(OK)}/{len(OK)} passed")
sys.exit(0 if all(OK) else 1)
