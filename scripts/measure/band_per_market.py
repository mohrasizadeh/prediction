"""What does a per-market likelihood band change? (asked 2026-11-08)

`engine.line_band` is one band for every market, floor 0.50. The markets are not equally common,
so that single floor decides which markets can appear at all:

  a player taking 1.5 shots a game   P(1+ shot) 0.74   P(1+ on target) 0.43

His shots line is stored and his on-target line is not. Measured on this league, on-target clears
the floor on 12% of player stat-groups against 53% for shots, which is why most cards have only
ONE market available to lead and engine.position_weights -- which rates on-target above shots for
a forward -- never gets to act.

`engine.line_band_by_stat` overrides the floor per market. This runs the same league twice, the
second time with on-target floored at 0.40, and reports what reaches a card.

Read-only: builds its own simulated league and re-runs the engine on it in memory.
Run: python scripts/measure/band_per_market.py
"""
import base64
import collections
import os
import statistics as st
import sys

os.environ.setdefault("APP_ENCRYPTION_KEY", base64.b64encode(os.urandom(32)).decode())
os.environ.setdefault("ADMIN_EMAIL", "owner@example.com")
os.environ.setdefault("ADMIN_INITIAL_PASSWORD", "demo-owner-pass-1")
HERE = "/home/user/prediction/backend"
os.environ.setdefault("SOCCER_BRAIN_DIR", os.path.join(HERE, "soccer_brain"))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "tests"))
sys.path.insert(0, os.environ["SOCCER_BRAIN_DIR"])

import engine_bridge as B  # noqa: E402
import queries as Q  # noqa: E402
import settings_store as S  # noqa: E402
from demo_server import build  # noqa: E402

import datetime as dt  # noqa: E402

db = build()
lg = db.leagues.find_one({})
# Two ENGINE RUNS on the same fixtures, not build()'s output against a re-run. The first version of
# this script took `now` from the LATEST scheduled kickoff, which widened the window past the round
# build() had forecast: every count roughly doubled and the comparison measured the extra fixtures
# rather than the setting. The earliest scheduled kickoff, less two hours, is the round build()
# itself used.
now = min(m["kickoff"] for m in db.matches.find({"status": "scheduled"}, {"kickoff": 1})) - dt.timedelta(hours=2)


def snapshot(label):
    fc = list(db.forecasts.find({**Q.NOT_HIDDEN, "scope": "player"}, {"_id": 0, "contrib": 0}))
    cards = Q.group_cards(fc, float(S.get(db, "engine.feed_max_p")), "player",
                          S.get(db, "engine.market_weights"), S.get(db, "engine.lift_scale"),
                          float(S.get(db, "engine.min_span")), S.get(db, "engine.position_weights"))
    carriers = db.forecasts.count_documents({"is_current": True, "scope": "player", "carrier": True})
    own = collections.Counter()
    for f in fc:
        own[(f.get("pos"), f["stat"])] += 1
    lead = collections.Counter(c["stat"] for c in cards)
    by_pos = collections.defaultdict(collections.Counter)
    for c in cards:
        by_pos[c.get("pos")][c["stat"]] += 1
    print(f"\n--- {label}")
    print(f"    visible player rows {len(fc)}   carriers {carriers}   cards {len(cards)}"
          f"   median lead {st.median([c['p'] for c in cards]):.0%}")
    print("    lead market: " + "  ".join(f"{k} {v} ({v/max(len(cards),1):.0%})" for k, v in lead.most_common()))
    for pos in ("FWD", "MID", "DEF"):
        c = by_pos.get(pos)
        if c:
            n = sum(c.values())
            print(f"      {pos} {n:>3} cards: " + "  ".join(f"{k} {v}" for k, v in c.most_common()))
    print("    on-target lines owned, by position: " + "  ".join(
        f"{p} {own.get((p, 'sot'), 0)}" for p in ("FWD", "MID", "DEF")))
    return lead


print(f"band {S.get(db, 'engine.line_band')}   by-stat {S.get(db, 'engine.line_band_by_stat')}")
B.run_league(db, lg["iid"], now=now)                     # baseline through the same code path
before = snapshot("one band for every market (today)")
_n0 = len(before)

S.put(db, "engine.line_band_by_stat", {"player": {"sot": [0.40, 0.985]}})
B.run_league(db, lg["iid"], now=now)
after = snapshot("on-target floored at 0.40")

print("\n--- harness check")
print("    Both snapshots are engine runs over the same fixtures with the same `now`; only the")
print("    setting differs. If the shots and tackles counts move much, the window moved and the")
print("    comparison is not measuring the band.")

print("\n--- what it costs")
print("    A lower floor admits less likely lines, so the median leading percentage can fall.")
print("    That is the trade: a market that exists at 45% against a market that does not exist.")
