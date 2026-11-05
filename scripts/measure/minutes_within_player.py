"""Does a player do MORE per minute when he plays less? (docs/58)

The question the simulated league cannot answer. It allocates player stats strictly in proportion
to minutes (`simulate.py`: w = base_w * skill * minutes/90), so within a player the per-90 rate is
flat BY CONSTRUCTION. Measuring the engine's linear-in-minutes assumption against data generated
under that same assumption is circular, and any difference between short and long appearances
there is player composition, not behaviour.

On real data the question is open and this answers it. For every player with enough of both, it
compares HIS OWN per-90 rate in short appearances against HIS OWN in long ones. Same player, so
composition cannot explain the result.

    # against production, read-only:
    MONGO_URL=... DB_NAME=... python scripts/measure/minutes_within_player.py

If short appearances show a materially higher per-90 rate, `engine.minutes_floor` is the lever and
its value is roughly the fixed part of that gap. If they do not, leave it at 0.
"""
import os, sys, math, collections, statistics as st

SHORT_MAX, LONG_MIN, MIN_EACH = 60, 75, 3
STATS = ("shots", "sot", "tackles")

url, dbname = os.environ.get("MONGO_URL"), os.environ.get("DB_NAME")
if url and dbname:
    from pymongo import MongoClient
    db = MongoClient(url)[dbname]
    print(f"source: production ({dbname})\n")
else:
    import base64
    os.environ.setdefault("APP_ENCRYPTION_KEY", base64.b64encode(os.urandom(32)).decode())
    HERE = "/home/user/prediction/backend"
    os.environ.setdefault("SOCCER_BRAIN_DIR", os.path.join(HERE, "soccer_brain"))
    sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(HERE, "tests")); sys.path.insert(0, os.environ["SOCCER_BRAIN_DIR"])
    import demo_server as DS
    db = DS.build()
    print("source: the SIMULATED league, where this is flat by construction -- expect no effect,\n"
          "        and do not read a null here as an answer about real football.\n")

rows = list(db.player_match_stats.find({"minutes": {"$gt": 0}}, {"_id": 0}))
by = collections.defaultdict(list)
for r in rows:
    by[r["player_iid"]].append(r)

print(f"Per-90 rate in short appearances (<{SHORT_MAX} min) against long ones (>={LONG_MIN} min),")
print(f"within the same player, for players with at least {MIN_EACH} of each.\n")
print(f"{'stat':<9}{'players':>9}{'short/90':>11}{'long/90':>10}{'ratio':>8}{'margin':>9}   verdict")
for stat in STATS:
    ratios = []
    for hs in by.values():
        sh = [h for h in hs if h["minutes"] < SHORT_MAX and h.get(stat) is not None]
        lo = [h for h in hs if h["minutes"] >= LONG_MIN and h.get(stat) is not None]
        if len(sh) < MIN_EACH or len(lo) < MIN_EACH:
            continue
        sm = sum(h["minutes"] for h in sh) / 90.0
        lm = sum(h["minutes"] for h in lo) / 90.0
        if sm <= 0 or lm <= 0:
            continue
        rs, rl = sum(h[stat] for h in sh) / sm, sum(h[stat] for h in lo) / lm
        if rl > 0:
            ratios.append(rs / rl)
    if len(ratios) < 8:
        print(f"{stat:<9}{len(ratios):>9}   too few players with enough of both to say anything")
        continue
    med = st.median(ratios)
    se = st.stdev(ratios) / math.sqrt(len(ratios))
    print(f"{stat:<9}{len(ratios):>9}{'':>11}{'':>10}{med:>8.2f}{1.96 * se:>9.2f}   "
          + ("flat (no effect)" if abs(med - 1) < 1.96 * se
             else ("MORE per minute when short" if med > 1 else "LESS per minute when short")))
print("\nratio = his short-appearance rate divided by his long-appearance rate. 1.00 means minutes")
print("scale cleanly, which is what the engine assumes today. Above 1 means short appearances are")
print("worth proportionally more, and engine.minutes_floor is the setting that credits that.")
