"""selftest_tiering.py -- earned tiers (docs/31): Strong and Solid are kept only where the NUMBER ON THE CARD and our
results back them.

Proves: the tier grades `p`, the number shown, and nothing else -- a likely starter, an unsure one and a confirmed one
with the same number get the same tier, because whether he starts is the lineup badge's question and asking it inside
the tier made a 94% line read "Watch"; Strong needs 90%, Solid 80%, Watch 60%; the track record can lower a tier (a
bucket that happened 60% of the time cannot stay Solid) and never raise one; too few results cap Strong at Solid; the
record is measured over matches the player PLAYED, which is what the public track record reports; classic mode keeps
the old rule.
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
t, n = TI.assign(db, rec, F(0.93, 0.88)); check(t == "Solid" and "our record" in n, "with no results behind it Strong drops to Solid")
t, _ = TI.assign(db, None, F(0.85, 0.75)); check(t == "Solid", "85% is Solid")
t, _ = TI.assign(db, None, F(0.78, 0.7)); check(t == "Watch", "78% is Watch: Solid is 80% now")
# THE LINEUP DOES NOT MOVE THE TIER. The same number gets the same label whoever is in the eleven;
# the lineup badge and the minutes row under the strip are where a reader learns about starting.
# Reported, twice: "being a starter has nothing to do with the forecasted number for any markets".
same = [TI.assign(db, None, F(0.96, 0.9, badge=b_, play=pp))[0]
        for b_, pp in (("confirmed", 1.0), ("likely", 0.85), ("unsure", 0.60), ("bench", 0.33))]
check(len(set(same)) == 1 and same[0] == "Strong",
      f"confirmed, likely, unsure and benched all read the same at 96%: {same}")
t, _ = TI.assign(db, None, F(0.96, 0.9, badge="likely", play=0.85)); check(t == "Strong", "a likely starter at 96% is Strong, not held back for the lineup")
t, _ = TI.assign(db, None, F(0.84, 0.72, badge="unsure", play=0.55)); check(t == "Solid", "an unsure lineup at 84% is Solid, not capped at Watch")
t, _ = TI.assign(db, None, F(0.93, 0.88, scope="team", badge=None, stat="corners")); check(t == "Strong", "a team line reads the same way")
# `p` already carries the expected minutes, so a substitute's own number is what lowers his tier.
t, _ = TI.assign(db, None, F(0.40, 0.30, badge="bench", play=0.33)); check(t is None, "a substitute's number is low on its own; no separate bench rule is needed")

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

# The record is measured where the claim applies: in matches he played. `p` says "if he plays", the
# public track record filters player_played, so the earned check reads the same rows. A no-show is
# not evidence that the line was wrong -- it is evidence about availability, which lives elsewhere.
for _ in range(100):
    db.forecast_outcomes.insert_one({"scope": "player", "stat": "tackles", "p": 0.92, "p_play": 0.8, "lineup_badge": "likely", "player_played": False, "reached": False})
for _ in range(100):
    db.forecast_outcomes.insert_one({"scope": "player", "stat": "tackles", "p": 0.92, "p_play": 0.8, "lineup_badge": "likely", "player_played": True, "reached": True})
rec = TI.Record(db)
est, n = rec.earned("player", "tackles", 0.92); check(n == 100 and est > 0.9, f"the record counts the matches he played, not the ones he missed ({est:.2f}, n={n})")

# the engine bridge reads the tier rule from settings
setting("engine.tier_mode", "classic"); check(B.S.get(db, "engine.tier_mode") == "classic", "classic mode can be chosen")
setting("engine.tier_mode", "earned")
# ---------------------------------------------------------------- docs/76: ONE rule, always
# The badge used to grade the DEPARTURE from a player's usual game whenever the line was that
# player's own half-way count. That is why a 57% card could read Watch beside a 56% one reading
# Solid, and it is why "Strong" stopped meaning "strong chance". There is one rule now, and these
# pin it: a personal line is graded on its NUMBER like everything else.
own = {**F(0.56, 0.48), "is_personal": True, "p_usual": 0.38}      # 18 points above usual, range clear
t, _ = TI.assign(db, None, own)
check(t is None, f"a personal line at 56% earns no badge, however far it sits from usual (got {t})")
t, _ = TI.assign(db, None, {**own, "p": 0.62, "lo": 0.55})
check(t == "Watch", "the same line at 62% is Watch, on the number")
t, _ = TI.assign(db, None, {**own, "p": 0.84, "lo": 0.75})
check(t == "Solid", "...and at 84% it is Solid")
t, _ = TI.assign(db, None, {**own, "p": 0.93, "lo": 0.88})
check(t == "Strong", "...and at 93% it is Strong")
# The two cards that started this: 57% and 56%, one of them a personal line. Same answer now.
a, _ = TI.assign(db, None, {**F(0.57, 0.50), "is_personal": True, "p_usual": 0.40})
b, _ = TI.assign(db, None, F(0.56, 0.49))
check(a == b, f"57% and 56% no longer disagree about their badge ({a} vs {b})")
check(not hasattr(TI, "_departure_tier"), "the departure grader is gone, not merely unreachable")
for k in ("engine.departure_strong", "engine.departure_solid"):
    check(k not in TI.S.registry(), f"{k} is gone from the registry rather than left reaching nothing")

# ---------------------------------------------------------------- the card no longer leads with it
# Grading on likelihood only helps if the card SHOWS a line whose likelihood is worth grading. The
# entity's own line sits at about a half by construction, so letting it lead would put an
# ungradeable number on the face of every card.
import queries as Q
grp = [{"id": "own", "fkey": "k1", "scope": "player", "stat": "shots", "thr": 2.5, "p": 0.51, "lo": 0.44,
        "hi": 0.58, "tier": None, "p_usual": 0.38, "edge": 0.13, "is_personal": True, "player_iid": 7,
        "match_iid": 1, "team_iid": 3, "span": 0.25, "pos": "FWD"},
       {"id": "low", "fkey": "k2", "scope": "player", "stat": "shots", "thr": 1.5, "p": 0.84, "lo": 0.76,
        "hi": 0.90, "tier": "Solid", "p_usual": 0.70, "edge": 0.14, "is_personal": False, "player_iid": 7,
        "match_iid": 1, "team_iid": 3, "span": 0.22, "pos": "FWD"}]
cards = Q.group_cards(grp, max_p=0.97, group="player", min_span=0.0)
check(len(cards) == 1, "one player, one card")
check(cards[0]["id"] == "low", f"the card leads with the line that has a real likelihood, not the half-way one (led with {cards[0]['id']})")
check(any(m["fkey"] == "k1" for m in cards[0]["more_lines"]), "...and the half-way line is still there, one tap away")

print("PASS selftest_tiering")
