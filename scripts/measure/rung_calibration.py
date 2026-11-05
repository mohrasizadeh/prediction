"""Does the engine under-call the 1+ rung? (reported 2026-11-05)

Reported: a player with 1+ shot in 8 of his last 10 was shown 55%, with the suggestion that the
engine might be counting "exactly 1" rather than "1 or more".

Two separate questions, and only the second needs data:

  1. Is the threshold arithmetic cumulative? Checked directly below: nb_sf(1, mu, r) must equal
     1 - P(X = 0) exactly.
  2. Is the engine's P(X >= k) right in aggregate? That cannot be settled from one card, because a
     player's own last ten is a sample of ten. This walks forward over every player-match and
     compares what the model said against what happened, rung by rung.

Read-only. Run: python scripts/measure/rung_calibration.py
"""
import base64, os, sys, math, collections, statistics as st
os.environ.setdefault("APP_ENCRYPTION_KEY", base64.b64encode(os.urandom(32)).decode())
HERE = "/home/user/prediction/backend"
os.environ.setdefault("SOCCER_BRAIN_DIR", os.path.join(HERE, "soccer_brain"))
sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(HERE, "tests")); sys.path.insert(0, os.environ["SOCCER_BRAIN_DIR"])
import numpy as np
from scipy import stats as sps
from core import nb_sf

print("1. Is the threshold cumulative?")
bad = 0
for mu in (0.4, 0.85, 1.3, 2.0, 5.0):
    for r in (4.0, 5.0, 6.0, 10.0):
        p0 = sps.nbinom.pmf(0, r, r / (r + mu))        # P(exactly 0)
        got = float(nb_sf(1, mu, r))                    # what the engine uses for "1+"
        if abs(got - (1 - p0)) > 1e-12:
            bad += 1
            print(f"   MISMATCH mu={mu} r={r}: nb_sf(1)={got} vs 1-P(0)={1 - p0}")
        # and a game of 3 must count toward 1+, 2+ and 3+ alike
        for k in (1, 2, 3):
            if not (float(nb_sf(k, mu, r)) <= float(nb_sf(k - 1, mu, r)) + 1e-12):
                bad += 1
print(f"   {'FAIL' if bad else 'ok'}: nb_sf(1, mu, r) == 1 - P(X=0) for every case tried"
      f"{'' if not bad else f' ({bad} mismatches)'}")
print("   So 'a 3-shot game is not counted toward 1+' is not what the code does.\n")

print("2. Walk-forward: what the model said against what happened, by rung.")
import demo_server as DS
db = DS.build()
mi = {m["iid"]: m["kickoff"] for m in db.matches.find({}, {"iid": 1, "kickoff": 1})}
rows = [r for r in db.player_match_stats.find({"minutes": {"$gt": 0}}, {"_id": 0}) if r["match_iid"] in mi]
rows.sort(key=lambda r: mi[r["match_iid"]])
by = collections.defaultdict(list)
for r in rows:
    by[r["player_iid"]].append(r)

R = {"shots": 6.0, "sot": 5.0, "tackles": 10.0}
MIN_HIST = 10
res = collections.defaultdict(lambda: collections.defaultdict(lambda: [0.0, 0, 0]))   # stat,k -> [sum p, hits, n]
for hs in by.values():
    for i in range(MIN_HIST, len(hs)):
        hist, nxt = hs[:i], hs[i]
        m = nxt["minutes"]
        for stat in ("shots", "sot", "tackles"):
            tot = sum(float(h.get(stat) or 0) for h in hist)
            mins = sum(h["minutes"] for h in hist)
            if mins <= 0:
                continue
            mu = tot / (mins / 90.0) * (m / 90.0)       # his own rate, scaled to the minutes he played
            y = float(nxt.get(stat) or 0)
            for k in (1, 2, 3):
                p = float(nb_sf(k, max(mu, 1e-6), R[stat]))
                cell = res[stat][k]
                cell[0] += p; cell[1] += 1 if y >= k else 0; cell[2] += 1

print(f"   {'stat':<9}{'rung':>5}{'said':>9}{'happened':>10}{'gap':>8}{'margin':>9}{'n':>7}   verdict")
for stat in ("shots", "sot", "tackles"):
    for k in (1, 2, 3):
        s, hit, n = res[stat][k]
        if not n:
            continue
        said, act = s / n, hit / n
        se = math.sqrt(max(said * (1 - said), 1e-9) / n)
        gap = act - said
        print(f"   {stat:<9}{k:>4}+{said*100:>8.1f}%{act*100:>9.1f}%{gap*100:>+7.1f}p{1.96*se*100:>8.1f}p{n:>7}   "
              + ("within chance" if abs(gap) < 1.96 * se else ("UNDER-CALLS" if gap > 0 else "OVER-CALLS")))
print("\n   'said' is the model's own number given only earlier games; 'happened' is what followed.")
