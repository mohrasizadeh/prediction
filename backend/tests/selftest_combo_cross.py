"""Combo builder: one line is left alone, and lines may come from several matches (docs/40).

Three things the owner reported:
  1. the builder changed the number for a single line;
  2. it refused lines from different matches;
  3. the combined number had to be right.

The maths rule: lines in the SAME match lean on each other (same team news, same game state, same referee), which
is what the measured same-player exponent and pre-lineup factors correct for. Lines in DIFFERENT matches share
none of that, so the matches multiply plainly.
"""
import os, sys, base64
os.environ.setdefault("APP_ENCRYPTION_KEY", base64.b64encode(os.urandom(32)).decode())
HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(HERE, "soccer_brain")); sys.path.insert(0, os.path.join(HERE, "tests"))
import combo as CB


def check(c, m):
    if not c:
        print("  FAIL", m); sys.exit(1)
    print("  ok  ", m)


def F(**k):
    return {"scope": "player", "player_iid": 1, "team_iid": 9, "stat": "shots", "p": 0.92, "p_play": 1.0,
            "state": "lineup", "match_iid": 1, "fkey": "k1", "kickoff": None, "id": k.get("fkey", "k1"),
            "thr": 0.5, "market": "1+ shot", "lo": 0.88, "hi": 0.95, **k}


FACT = (1.0, 1.11, 1.19, 1.25)

# ---------------------------------------------------------------- 1. one line is not a combination
check(abs(CB.combine([F()], "p", FACT) - 0.92) < 1e-9, "one line on a confirmed starter comes back exactly as it is")
check(abs(CB.combine([F(p=0.98)], "p", FACT) - 0.98) < 1e-9,
      "a 98% line is not clipped to the combo's 97% cap: one line is not a combination")
check(abs(CB.combine([F(scope="team", p=0.94)], "p", FACT) - 0.94) < 1e-9, "one team line comes back as it is")
one = CB.combine([F(p_play=0.70, state="pre")], "p", FACT)
check(abs(one - 0.92 * 0.70) < 1e-9,
      "for a player who may not play, the number is 'if he plays' times the chance he plays, and nothing else")
check(abs(CB.combine([F(p_play=0.70, state="pre")], "p", (9.9, 9.9, 9.9, 9.9)) - 0.644) < 1e-9,
      "...with no pre-lineup correction: there is nothing to correlate with")

# ---------------------------------------------------------------- 2. several matches
same = [F(state="pre"), F(player_iid=2, stat="tackles", p=0.80, state="pre", fkey="k2")]
cross = [F(state="pre"), F(player_iid=2, team_iid=5, stat="tackles", p=0.80, state="pre", match_iid=2, fkey="k2")]
check(abs(CB.combine(same, "p", FACT) - 0.92 * 0.80 * 1.11) < 1e-9, "two players in ONE match: the tested correction applies")
check(abs(CB.combine(cross, "p", FACT) - 0.92 * 0.80) < 1e-9, "two players in DIFFERENT matches: multiply plainly, no correction")
check(CB.combine(cross, "p", FACT) < CB.combine(same, "p", FACT),
      "...so a cross-match combo is never inflated by a dependence that is not there")
three = cross + [F(player_iid=3, team_iid=7, p=0.90, match_iid=3, state="pre", fkey="k3")]
check(abs(CB.combine(three, "p", FACT) - 0.92 * 0.80 * 0.90) < 1e-9, "three matches multiply plainly")

# a match with two players still gets its own correction inside a cross-match combo
mixed = [F(state="pre"), F(player_iid=2, stat="tackles", p=0.80, state="pre", fkey="k2"),
         F(player_iid=3, team_iid=5, p=0.90, match_iid=2, state="pre", fkey="k3")]
check(abs(CB.combine(mixed, "p", FACT) - (0.92 * 0.80 * 1.11) * 0.90) < 1e-9,
      "the correction is applied per match, not to the whole combo")

# ---------------------------------------------------------------- 3. dependence inside a match survives
dep = [F(state="lineup"), F(stat="sot", p=0.70, state="lineup", fkey="k2")]
d = CB.combine(dep, "p", FACT)
check(d > 0.92 * 0.70, f"two lines on the same player happen together more often than the product says: {d:.4f} > {0.92 * 0.70:.4f}")
check(d < 0.92, "...but never more likely than the easier of the two")

# a cap still applies to a real combination
many = [F(p=0.99, player_iid=i, team_iid=i, match_iid=i, fkey=f"k{i}") for i in range(1, 5)]
check(CB.combine(many, "p", FACT) <= CB.CAP, f"a real combination is still capped at {CB.CAP}")

# ---------------------------------------------------------------- the report describes every match
import mongomock, mongo_init
db = mongomock.MongoClient()["c"]; mongo_init.ensure_indexes(db)
db.teams.insert_many([{"iid": 9, "id": "t9", "ext_id": 9, "name": "Como"}, {"iid": 5, "id": "t5", "ext_id": 5, "name": "Venezia"},
                      {"iid": 7, "id": "t7", "ext_id": 7, "name": "Parma"}, {"iid": 8, "id": "t8", "ext_id": 8, "name": "Lecce"}])
import datetime as dt
now = dt.datetime.now(dt.timezone.utc)
db.matches.insert_many([{"iid": 1, "id": "m1", "ext_id": 1, "home_iid": 9, "away_iid": 5, "kickoff": now},
                        {"iid": 2, "id": "m2", "ext_id": 2, "home_iid": 7, "away_iid": 8, "kickoff": now + dt.timedelta(days=1)}])
docs = [F(state="pre"), F(player_iid=2, team_iid=7, stat="tackles", p=0.80, state="pre", match_iid=2, fkey="k2", kickoff=now + dt.timedelta(days=1))]
docs[0]["kickoff"] = now
rep = CB._with_match(db, CB._report(docs, list(FACT)))
check(len(rep["matches"]) == 2, "the report lists both matches")
check([m["label"] for m in rep["matches"]] == ["Como v Venezia", "Parma v Lecce"], f"...named and in kick-off order: {[m['label'] for m in rep['matches']]}")
check(all("combined" in m for m in rep["matches"]), "...each with its own joint chance")
check(all(l.get("match_iid") for l in rep["lines"]), "every line says which match it belongs to")
check(any("do not lean on each other" in n for n in rep["notes"]), f"...and the page is told why they multiply plainly: {rep['notes']}")
check(rep["match_iid"] == 1 and rep["label"] == "2 matches", "older screens still get a match_iid, and the label counts the matches")

print("\nALL COMBO CHECKS PASSED")
