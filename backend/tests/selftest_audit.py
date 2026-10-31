"""selftest_audit.py -- engine_audit.py runs on stored outcomes and says where accuracy is lost (docs/30)."""
import datetime as dt, io, contextlib
import testkit as K
from testkit import check, db
import engine_audit as A

now = dt.datetime.now(dt.timezone.utc)
for i in range(60):
    db.forecast_outcomes.insert_one({"forecast_id": f"f{i}", "fkey": f"k{i}", "league_iid": 1, "stat": "shots", "scope": "player", "tier": "Solid",
                                     "p": 0.7, "reached": i % 4 != 0, "state": "pre", "player_played": i % 10 != 0, "p_basis": "all", "p_play": 0.9,
                                     "lineup_badge": "likely", "kickoff": now - dt.timedelta(days=1 if i < 30 else 40)})
for i in range(40):
    db.matches.insert_one({"iid": 100 + i, "status": "final", "hg": i % 3, "ag": 1, "kickoff": now - dt.timedelta(days=2), "league_iid": 1})
    db.match_probs.insert_one({"match_iid": 100 + i, "at": now, "is_current": True, "p_home": 0.4, "p_draw": 0.3, "p_away": 0.3})
s = A.match_skill(db, now - dt.timedelta(days=14), now + dt.timedelta(days=1))
check(s and s["n"] == 40 and "skill_ll" in s, "match skill is worked out")
buf = io.StringIO()
with contextlib.redirect_stdout(buf):
    A.report([r for r in db.forecast_outcomes.find({}, {"_id": 0})], "all")
out = buf.getvalue()
check("did not play: 6" in out and "chance to play: stated 0.900  actual 0.900" in out, "the cost of did-he-play is shown")
check("by lineup badge" in out and "likely" in out, "groups by lineup badge")
print("PASS selftest_audit")
