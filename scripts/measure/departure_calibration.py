"""Is "how far above his usual" an honest number? (reported 2026-11-07)

`edge = p - p_usual` is the most load-bearing derived quantity in the product. It ranks the whole
feed (`queries.FEED_SORTS["edge"]` through `lift` and `prominence`), it is the "USUAL 58% / -6 pts"
chip on every card, and with `engine.personal_lines` on it is what the tier itself is graded on.

It is a DIFFERENCE between two numbers, so it is only as good as the two being built the same way.
They were not. In `soccer_brain/engine.py` the player's forecast is his share of a TEAM TOTAL:

    mus   = mu_team * rate[pid] * minutes_share(m) / Z        <- normalised by Z
    mus_b = pb.mean * minutes_share(m)                         <- not normalised at all

`Z` is the squad's shares summed over expected minutes; it averages about 0.88, so `p` carries a
x1.13 lift that `p_usual` never gets. On top of that `rate[pid]` and `pb.mean` are two DIFFERENT
shrinkage estimators of the same quantity -- one a share of the team total with the prior in team-
stat units, one a per-90 rate with a flat prior of 4 -- so each player also carries a fixed personal
offset that never changes between fixtures.

This script measures both, and then the thing that actually matters: whether a stated departure of
d points comes true as d points.

  1. THE STRUCTURAL TEST, which needs no results at all. Over a full round, every club plays one
     fixture, so the average fixture is by construction an average one: the mean of
     delta = log(expected / expected_usual) across a round should sit at ZERO. Anything else is an
     offset applied to every card in the product. This is the test that would have caught it.
  2. THE RUNG-FREENESS TEST. delta should be identical at every rung of a player's ladder, because
     the rung is a property of the question asked, not of the fixture. The within-(player, stat)
     spread of delta should be 0.
  3. THE CALIBRATION REGRESSION, which needs settled results: regress (outcome - p_usual) on
     d = p - p_usual. An honest departure has slope 1.0 and intercept 0.0. A positive intercept is
     exactly the offset from (1) carried into what readers were told.

Read-only: builds its own simulated league and touches no stored data.
Run: python scripts/measure/departure_calibration.py
"""
import base64
import collections
import os
import sys

os.environ.setdefault("APP_ENCRYPTION_KEY", base64.b64encode(os.urandom(32)).decode())
os.environ.setdefault("ADMIN_EMAIL", "owner@example.com")
os.environ.setdefault("ADMIN_INITIAL_PASSWORD", "demo-owner-pass-1")
HERE = "/home/user/prediction/backend"
os.environ.setdefault("SOCCER_BRAIN_DIR", os.path.join(HERE, "soccer_brain"))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "tests"))
sys.path.insert(0, os.environ["SOCCER_BRAIN_DIR"])

import numpy as np  # noqa: E402

from demo_server import build  # noqa: E402

db = build()

rows = [r for r in db.forecasts.find({"is_current": True, "scope": "player"}, {"_id": 0})
        if r.get("expected") and r.get("expected_usual")]
print(f"player forecasts with both a forecast and a usual: {len(rows)}\n")


def delta(r):
    """log(what we expect tonight / what he usually does), in the engine's own units."""
    return float(np.log(max(r["expected"], 1e-9) / max(r["expected_usual"], 1e-9)))


# ---------------------------------------------------------------- 1. the structural test
print("1. MEAN DEPARTURE OVER A WHOLE ROUND  (should be 0: the average fixture is average)")
print(f"   {'stat':<9}{'n':>6}{'mean delta':>12}{'sd':>8}{'median':>9}{'mean as points':>16}")
off = {}
for stat in ("shots", "sot", "tackles"):
    g = [r for r in rows if r["stat"] == stat]
    if not g:
        continue
    d = np.array([delta(r) for r in g])
    # what that offset is worth in probability points at each row's own rung, using the engine's
    # own sensitivity dP(X>=k)/dlog(mu) = k * P(X = k)
    pts = np.mean([abs(r["p"] - r["p_usual"]) for r in g if r.get("p_usual") is not None])
    off[stat] = float(d.mean())
    print(f"   {stat:<9}{len(g):>6}{d.mean():>12.4f}{d.std():>8.4f}{np.median(d):>9.4f}"
          f"{pts * 100:>15.1f}p")
print("   Measured on this league the mean sits near zero either way, so a CONSTANT inflation is")
print("   not the fault here -- test 1b is the one that localises it.\n")

# ---------------------------------------------------------------- 1b. the decisive test
# The opponent can only reach a player through the team total (docs/54 §5), so WITHIN one club and
# one stat every player's departure must be the SAME number. Any spread is the two baselines
# disagreeing about the player himself -- `p` uses his share of the team total, `p_usual` used his
# per-90 rate, two different shrinkage estimators of one quantity -- and that is a fixed personal
# offset, not an offset the product could calibrate away. Compare it against the league's whole
# spread of opponent strength, which is what the departure is supposed to be measuring.
print("1b. WITHIN ONE CLUB AND ONE STAT, IS THE DEPARTURE ONE NUMBER?  (the opponent is shared)")
print(f"   {'stat':<9}{'clubs':>7}{'within-club sd':>17}{'overall sd':>13}{'share that is club':>20}")
for stat in ("shots", "sot", "tackles"):
    g = [r for r in rows if r["stat"] == stat]
    if not g:
        continue
    byc = collections.defaultdict(list)
    for r in g:
        byc[(r["team_iid"], r["match_iid"])].append(delta(r))
    within = [float(np.std(v)) for v in byc.values() if len(v) > 1]
    allv = np.array([delta(r) for r in g])
    # how much of the variance is between clubs (the fixture) rather than inside them (the mismatch)
    club_means = np.array([np.mean(v) for v in byc.values() if len(v) > 1])
    share = (club_means.var() / allv.var()) if allv.var() > 0 else float("nan")
    print(f"   {stat:<9}{len(within):>7}{np.mean(within):>17.4f}{allv.std():>13.4f}{share:>19.0%}")
print("   A within-club sd near 0 means the two baselines agree about the player and only the")
print("   fixture moves the departure. A within-club sd comparable to the overall sd means most")
print("   of what the card calls 'above his usual' is an artefact of two different estimators.\n")

# ---------------------------------------------------------------- 2. rung-freeness
print("2. IS THE DEPARTURE THE SAME AT EVERY RUNG?  (it must be: the rung is not the fixture)")
grp = collections.defaultdict(list)
for r in rows:
    grp[(r["player_iid"], r["match_iid"], r["stat"])].append(r)
multi = {k: v for k, v in grp.items() if len(v) > 1}
spread = [float(np.std([delta(r) for r in v])) for v in multi.values()]
print(f"   groups with more than one rung: {len(multi)}")
if spread:
    print(f"   within-group sd of delta: max {max(spread):.6f}, mean {np.mean(spread):.6f}")
    print("   " + ("PASS - the departure is a property of the fixture, not of the rung"
                   if max(spread) < 1e-6 else "FAIL - the departure moves with the rung"))
print()

# ---------------------------------------------------------------- 3. the calibration regression
print("3. DOES A STATED DEPARTURE COME TRUE?  regress (outcome - p_usual) on (p - p_usual)")
print("   honest: slope 1.0, intercept 0.0.  a positive intercept is test 1 reaching the reader.")
outs = list(db.forecast_outcomes.find({"scope": "player"}, {"_id": 0}))
by_key = {r.get("fkey"): r for r in db.forecasts.find({"scope": "player"}, {"_id": 0})}
pairs = []
for o in outs:
    f = by_key.get(o.get("fkey"))
    if not f or f.get("p_usual") is None or o.get("player_played") is False:
        continue
    pairs.append((float(f["p"]) - float(f["p_usual"]), (1.0 if o.get("reached") else 0.0) - float(f["p_usual"])))
print(f"   settled player lines with a usual to compare against: {len(pairs)}")
if len(pairs) >= 30:
    x = np.array([a for a, _ in pairs])
    y = np.array([b for _, b in pairs])
    slope, intercept = np.polyfit(x, y, 1)
    print(f"   slope {slope:+.3f}   intercept {intercept * 100:+.2f} points   (n={len(pairs)})")
else:
    print("   not enough settled lines in a single simulated round to regress; the structural")
    print("   test above needs no outcomes and is the one that localises the bug.")
print()
print("NOTE: forecast_outcomes does not store p_usual, so on a production database this")
print("      regression can only reach back as far as engine.keep_days. score_finished now")
print("      stores p_usual and edge on the outcome so the history accumulates from here.")
