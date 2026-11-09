"""selftest_proof.py -- forecasts that were published, scored, and came in (docs/68).

Proves the rule that matters: a line on a player who never came on is NEVER proof. It was not
right about football, and showing it as a hit on a page whose whole argument is honesty would be
the one unforced error available there. Also: only lines that actually reached, only recent ones,
only above the floor, and one per player so the strip is not the same striker six times.
"""
import os, sys, base64, datetime as dt
os.environ.setdefault("APP_ENCRYPTION_KEY", base64.b64encode(os.urandom(32)).decode())
HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
import mongomock
import mongo_init, queries as Q


def check(c, m):
    if not c:
        print("  FAIL", m); sys.exit(1)
    print("  ok  ", m)


db = mongomock.MongoClient()["pf"]; mongo_init.ensure_indexes(db)
now = dt.datetime.now(dt.timezone.utc)

def add(i, *, p, reached=True, played=True, days=1, player=None, team=1, market="1+ shot", actual=3):
    fid = f"f{i}"
    db.forecasts.insert_one({"id": fid, "fkey": f"k{i}", "match_iid": 500 + i, "league_iid": 10,
                             "scope": "player" if player else "team", "team_iid": team, "opp_iid": team + 50,
                             "player_iid": player, "stat": "shots", "thr": 0.5, "market": market,
                             "p": p, "tier": "Solid", "kickoff": now - dt.timedelta(days=days),
                             "is_current": True, "hidden": False})
    db.forecast_outcomes.insert_one({"forecast_id": fid, "fkey": f"k{i}", "p": p, "thr": 0.5,
                                     "actual": actual, "reached": reached, "player_played": played,
                                     "scored_at": now - dt.timedelta(days=days), "stat": "shots",
                                     "scope": "player" if player else "team", "tier": "Solid"})

add(1, p=0.93, player=101)                              # a clean hit
add(2, p=0.88, player=102)                              # another
add(3, p=0.85, player=103, reached=False, actual=0)     # missed
add(4, p=0.91, player=104, played=False, actual=0)      # never came on
add(5, p=0.55, player=105)                              # under the floor
add(6, p=0.90, player=101, market="2+ shots")           # same player again
add(7, p=0.89, player=107, days=60)                     # too long ago

rows = Q.proof(db, limit=12, min_p=0.7, days=10)
keys = {r["fkey"] for r in rows}
check(rows, "it returns something")
check("k1" in keys and "k2" in keys, "forecasts that came in are included")
check("k3" not in keys, "a forecast that missed is not proof")
check("k4" not in keys,
      "a forecast on a player who never came on is NOT proof -- it was not right about football")
check("k5" not in keys, "a line under the floor is left out")
check("k7" not in keys, "and one from two months ago is not 'fresh'")
check("k6" not in keys, "one line per player, so the strip is not the same striker twice")
check(all(r["actual"] is not None and r["p"] for r in rows), "every row carries what we said and what happened")
check(all(r.get("market") for r in rows), "and the words for the line")
check(len(Q.proof(db, limit=1, min_p=0.7, days=10)) == 1, "the limit is honoured")
check(Q.proof(db, limit=12, min_p=0.99, days=10) == [], "an impossible floor returns nothing rather than something weaker")

# nothing scored at all is a normal state on a new install, not an error
empty = mongomock.MongoClient()["pf2"]; mongo_init.ensure_indexes(empty)
check(Q.proof(empty) == [], "an empty database returns an empty list, so the page can hide the section")

print("selftest_proof: all checks passed")
