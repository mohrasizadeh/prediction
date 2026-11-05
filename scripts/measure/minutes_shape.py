"""Does "1+" scale with minutes the way the engine assumes? (reported 2026-11-05)

Reported: a player took 1+ shot in 8 of 10 games including a 17-minute appearance, while blanking
in two games of 90 and 45. The claim: how long he plays barely decides WHETHER he gets a shot
away, so scaling the expectation linearly with minutes under-calls short appearances.

The engine models a count: mu = rate_per_90 * minutes/90, then P(X >= k) from that. That is right
for the EXPECTED COUNT -- twice the time, twice the shots. It is not obviously right for the
extensive margin, "did he manage one at all", because a substitute comes on to attack and a
starter can have a quiet ninety.

This splits the walk-forward by how long the player actually played and compares what the model
said against what happened, at 1+, for every market. If the short buckets under-call and the long
buckets over-call, the linear-in-minutes shape is wrong and the report is right.

Read-only. Run: python scripts/measure/minutes_shape.py
"""
import base64, os, sys, math, collections
os.environ.setdefault("APP_ENCRYPTION_KEY", base64.b64encode(os.urandom(32)).decode())
HERE = "/home/user/prediction/backend"
os.environ.setdefault("SOCCER_BRAIN_DIR", os.path.join(HERE, "soccer_brain"))
sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(HERE, "tests")); sys.path.insert(0, os.environ["SOCCER_BRAIN_DIR"])
from core import nb_sf
import demo_server as DS

db = DS.build()
mi = {m["iid"]: m["kickoff"] for m in db.matches.find({}, {"iid": 1, "kickoff": 1})}
rows = [r for r in db.player_match_stats.find({"minutes": {"$gt": 0}}, {"_id": 0}) if r["match_iid"] in mi]
rows.sort(key=lambda r: mi[r["match_iid"]])
by = collections.defaultdict(list)
for r in rows:
    by[r["player_iid"]].append(r)

R = {"shots": 6.0, "sot": 5.0, "tackles": 10.0}
BUCKETS = [(1, 30, "1-30 min"), (30, 60, "30-60 min"), (60, 80, "60-80 min"), (80, 200, "80+ min")]
MIN_HIST = 10
res = collections.defaultdict(lambda: [0.0, 0, 0])      # (stat, bucket) -> [sum said, hits, n]
rate_obs = collections.defaultdict(lambda: [0.0, 0.0])  # (stat, bucket) -> [shots, per-90s]

for hs in by.values():
    for i in range(MIN_HIST, len(hs)):
        hist, nxt = hs[:i], hs[i]
        m = float(nxt["minutes"])
        b = next((lab for lo, hi, lab in BUCKETS if lo <= m < hi), None)
        if not b:
            continue
        for stat in ("shots", "sot", "tackles"):
            tot = sum(float(h.get(stat) or 0) for h in hist)
            mins = sum(h["minutes"] for h in hist)
            if mins <= 0:
                continue
            rate90 = tot / (mins / 90.0)
            mu = rate90 * (m / 90.0)                    # what the engine assumes: linear in minutes
            y = float(nxt.get(stat) or 0)
            cell = res[(stat, b)]
            cell[0] += float(nb_sf(1, max(mu, 1e-6), R[stat])); cell[1] += 1 if y >= 1 else 0; cell[2] += 1
            ro = rate_obs[(stat, b)]
            ro[0] += y; ro[1] += m / 90.0

print("P(1+) by how long the player actually played. 'said' assumes the count scales with minutes.\n")
print(f"{'stat':<9}{'minutes':<11}{'said':>8}{'happened':>10}{'gap':>8}{'margin':>8}{'n':>6}   verdict")
for stat in ("shots", "sot", "tackles"):
    for _, _, b in BUCKETS:
        s, hit, n = res[(stat, b)]
        if n < 25:
            continue
        said, act = s / n, hit / n
        se = math.sqrt(max(said * (1 - said), 1e-9) / n)
        gap = act - said
        v = "within chance" if abs(gap) < 1.96 * se else ("UNDER-CALLS" if gap > 0 else "OVER-CALLS")
        print(f"{stat:<9}{b:<11}{said*100:>7.1f}%{act*100:>9.1f}%{gap*100:>+7.1f}p{1.96*se*100:>7.1f}p{n:>6}   {v}")
    print()

print("And the assumption underneath: is the per-90 rate really flat across minutes played?")
print(f"{'stat':<9}{'minutes':<11}{'observed per 90':>17}")
for stat in ("shots", "sot", "tackles"):
    for _, _, b in BUCKETS:
        tot, n90 = rate_obs[(stat, b)]
        if n90 > 3:
            print(f"{stat:<9}{b:<11}{tot / n90:>17.2f}")
    print()
