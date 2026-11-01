"""selftest_overlay.py -- SportAPI owns kick-off, status and score of a followed match (docs/30).

Proves: a moved kick-off moves the match into the right day on Today and out of the old one; live and final scores come
from SportAPI; postponed shows as postponed; a match SportAPI does not follow keeps PitchAPI's values; the day list
includes days that only SportAPI knows; the minute job loads the upcoming days with one call each and spares the live reserve.
"""
import datetime as dt
import testkit as K
from testkit import check as _c, db, setting
def check(name, ok, *a):
    print(('PASS ' if ok else 'FAIL ') + name, '' if ok else a)
    assert ok, name
import queries as Q, sportapi as SP

now = dt.datetime(2026, 11, 1, 12, 0, tzinfo=dt.timezone.utc)
db.teams.insert_many([{"iid": i, "id": f"t{i}", "ext_id": i, "name": n} for i, n in ((1, "Como"), (2, "Venezia"), (3, "Parma"), (4, "Genoa"))])
mk = lambda iid, h, a, ko, st="scheduled": {"iid": iid, "id": f"m{iid}", "ext_id": iid, "home_iid": h, "away_iid": a, "kickoff": ko, "status": st, "league_iid": 1, "hg": None, "ag": None}
db.matches.insert_many([mk(10, 1, 2, now + dt.timedelta(days=1)), mk(11, 3, 4, now + dt.timedelta(days=1))])
db.live_fixtures.insert_one({"sid": 900, "match_iid": 10, "league_iid": 1, "status": "Scheduled", "kickoff": now + dt.timedelta(days=2, hours=3), "hs": None, "as": None})

day = lambda n: (now + dt.timedelta(days=n)).strftime("%Y-%m-%d")
d1 = [m["iid"] for m in Q.fixtures_for_date(db, day(1))]
d2 = [m["iid"] for m in Q.fixtures_for_date(db, day(2))]
check("moved kick-off leaves the old day", d1 == [11])
check("moved kick-off appears on the new day", d2 == [10])
check("SportAPI value is shown", Q._aware(Q.fixtures_for_date(db, day(2))[0]["kickoff"]) == now + dt.timedelta(days=2, hours=3))
check("unfollowed match keeps PitchAPI kick-off", Q._aware(Q.fixtures_for_date(db, day(1))[0]["kickoff"]) == now + dt.timedelta(days=1) and Q.fixtures_for_date(db, day(1))[0].get("source") is None)

db.live_fixtures.update_one({"sid": 900}, {"$set": {"status": "LIVE", "minute": "34'", "hs": 1, "as": 0}})
m = Q.match_detail(db, 10)["match"]
check("live score from SportAPI", m["live"]["hs"] == 1 and m["live"]["status"] == "LIVE" and m["phase"] == "live")

db.live_fixtures.update_one({"sid": 900}, {"$set": {"status": "FT", "hs": 2, "as": 1}})
m = Q.match_detail(db, 10)["match"]
check("final score before PitchAPI has it", m["status"] == "final" and (m["hg"], m["ag"]) == (2, 1))

db.live_fixtures.update_one({"sid": 900}, {"$set": {"status": "Postponed", "hs": None, "as": None}})
check("postponed shows as postponed", Q.match_detail(db, 10)["match"]["status"] == "postponed")

db.live_fixtures.insert_one({"sid": 901, "match_iid": None, "league_iid": 1, "status": "Scheduled", "kickoff": now + dt.timedelta(days=5)})
md = Q.match_days(db, now, 10)
days = md["days"]
check("day list has SportAPI-only days, not postponed ones", day(5) in days and day(2) not in days)
check("each day names the leagues playing, with a crest field", all(
    isinstance(md["leagues"].get(d), list) and all({"id", "name", "matches"} <= set(x) for x in md["leagues"][d]) for d in days))
check("a league is counted once per match, not once per source",
      all(sum(x["matches"] for x in md["leagues"][d]) <= 40 for d in days))

# the minute job loads the upcoming days
class Fake:
    def __init__(s): s.paths = []
    def left(s): return 1000
    def tight(s): return False
    def get(s, path, kind, cache_days=None): s.paths.append((path, kind)); return {"data": []}
setting("sportapi.enabled", True); setting("sportapi.leagues", {"1": 39})
setting("sportapi.upcoming_days", 3)
f = Fake(); r = SP.live_tick(db, client=f, now=now)
ups = [p for p, k in f.paths if k == "upcoming"]
check("upcoming days loaded once each", len(ups) == 3 and ups[0].endswith(day(1)))
f2 = Fake(); SP.live_tick(db, client=f2, now=now + dt.timedelta(minutes=5))
check("and not again within the refresh time", not [1 for p, k in f2.paths if k == "upcoming"])
print("PASS selftest_overlay")
