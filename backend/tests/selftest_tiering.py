"""selftest_tiering.py -- earned tiers (docs/31): Strong and Solid are kept only where the whole chance and our results back them.

Proves: a player line before the lineup is judged on chance x chance to play, so a likely starter does not get Strong;
Strong needs 90% whole chance, Solid 80%; Strong for a player needs a confirmed eleven; the track record can lower a
tier (a bucket that happened 60% of the time cannot stay Solid) and never raise one; too few results cap Strong at Solid;
a player who did not feature counts as a miss in the record; an unsure player is Watch at most; classic mode keeps the old rule.
"""
import datetime as dt
import random
import testkit as K
from testkit import check, db, setting
import tiering as TI, engine_bridge as B

random.seed(3)
F = lambda p, lo, badge="confirmed", play=1.0, scope="player", stat="shots": {"p": p, "lo": lo, "scope": scope, "stat": stat, "p_play": play, "lineup_badge": badge}

# no results yet: thresholds only, and Strong is capped at Solid because nothing backs it
rec = TI.Record(db)
t, _ = TI.assign(db, None, F(0.93, 0.88)); check(t == "Strong", "confirmed 93% with a wide low end is Strong when no record is used")
t, n = TI.assign(db, rec, F(0.93, 0.88)); check(t == "Solid" and "more finished matches" in n, "with no results behind it Strong drops to Solid")
t, _ = TI.assign(db, None, F(0.85, 0.75)); check(t == "Solid", "85% is Solid")
t, _ = TI.assign(db, None, F(0.78, 0.7)); check(t == "Watch", "78% is Watch: Solid is 80% now")
# before the lineup: whole chance
t, n = TI.assign(db, None, F(0.96, 0.9, badge="likely", play=0.85)); check(t == "Solid" and TI.whole(0.96, 0.85, "player", "likely") < 0.9, "likely starter at 96% if he plays x 85% to play is not Strong")
t, _ = TI.assign(db, None, F(0.99, 0.95, badge="likely", play=0.99)); check(t == "Solid", "even at 98% whole, Strong waits for a confirmed eleven")
t, _ = TI.assign(db, None, F(0.99, 0.95, badge="unsure", play=0.99)); check(t == "Watch", "unsure lineup is Watch at most")
t, n = TI.assign(db, None, F(0.9, 0.8, badge="bench", play=0.05)); check(t is None and "bench" in n.lower(), "bench: no tier when the whole chance is tiny")
t, _ = TI.assign(db, None, F(0.93, 0.88, scope="team", badge=None, stat="corners")); check(t == "Strong", "a team line has no lineup condition")

# a record: shots lines near 85% happened 60% of the time; team corners near 93% happened 94% of the time
for _ in range(120):
    db.forecast_outcomes.insert_one({"scope": "player", "stat": "shots", "p": 0.85, "p_play": 1.0, "lineup_badge": "confirmed", "player_played": True, "reached": random.random() < 0.60})
for _ in range(120):
    db.forecast_outcomes.insert_one({"scope": "team", "stat": "corners", "p": 0.93, "player_played": True, "reached": random.random() < 0.95})
rec = TI.Record(db)
est, n = rec.earned("player", "shots", 0.85); check(n >= 40 and est < 0.7, f"record: shots near 85% happened about 60% (read {est:.2f}, n={n})")
t, note = TI.assign(db, rec, F(0.85, 0.75)); check(t == "Watch" and "happened" in note, "Solid is lowered to Watch where the record says 60%")
t, _ = TI.assign(db, rec, F(0.93, 0.88, scope="team", badge=None, stat="corners")); check(t == "Strong", "a bucket that delivers keeps Strong")
t, _ = TI.assign(db, rec, F(0.70, 0.6, scope="team", badge=None, stat="corners")); check(t == "Watch", "the record never raises a tier")

# a player who did not play is a miss when his chance to play was stored
for _ in range(100):
    db.forecast_outcomes.insert_one({"scope": "player", "stat": "tackles", "p": 0.92, "p_play": 0.8, "lineup_badge": "likely", "player_played": False, "reached": False})
for _ in range(100):
    db.forecast_outcomes.insert_one({"scope": "player", "stat": "tackles", "p": 0.92, "p_play": 0.8, "lineup_badge": "likely", "player_played": True, "reached": True})
rec = TI.Record(db)
est, n = rec.earned("player", "tackles", 0.92 * 0.8); check(est < 0.6, f"did-not-play counts as a miss ({est:.2f})")

# the engine bridge reads the tier rule from settings
setting("engine.tier_mode", "classic"); check(B.S.get(db, "engine.tier_mode") == "classic", "classic mode can be chosen")
setting("engine.tier_mode", "earned")
print("PASS selftest_tiering")
