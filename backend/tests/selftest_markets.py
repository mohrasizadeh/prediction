"""Near-certain lines reach the page, and the markets bettors ask for exist (docs/39).

Two gates used to hide them: engine.line_band threw away anything above 95% before it was stored, and
engine.feed_max_p stopped anything above 93% from leading a card. Both are now set at the display cap.
Also proves the two markets that need no statistics feed: team shots on target, and total goals in the match
read off the team-strength model's own scoreline matrix.
"""
import os, sys, base64
os.environ.setdefault("APP_ENCRYPTION_KEY", base64.b64encode(os.urandom(32)).decode())
HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(HERE, "soccer_brain")); sys.path.insert(0, os.path.join(HERE, "tests"))
import numpy as np
import engine_bridge as B
import queries as Q
import settings_store as S
from strength import DixonColes


def check(c, m):
    if not c:
        print("  FAIL", m); sys.exit(1)
    print("  ok  ", m)


# ---------------------------------------------------------------- total goals off the scoreline matrix
rng = np.random.default_rng(0)
n = 400
teams = [f"t{i}" for i in range(10)]
dc = DixonColes().fit([teams[i % 10] for i in range(n)], [teams[(i * 3 + 1) % 10] for i in range(n)],
                      rng.poisson(1.5, n), rng.poisson(1.1, n), np.arange(n)[::-1])
p = dc.outcome_probs("t0", "t3")
check(abs(p["p_home"] + p["p_draw"] + p["p_away"] - 1.0) < 1e-9, "the match result still adds up to one")
tot = p["totals"]
check(set(tot) >= {"0.5", "1.5", "2.5", "3.5"}, f"total-goal lines come off the same matrix: {sorted(tot)[:5]}")
check(all(0.0 <= v <= 1.0 for v in tot.values()), "...each one is a probability")
keys = sorted(tot, key=float)
check(all(tot[a] >= tot[b] for a, b in zip(keys, keys[1:])), "...and a higher line is never more likely than a lower one")
check(all(isinstance(k, str) for k in tot), "the lines are keyed by the line itself, so the answer stores as a document")

# ---------------------------------------------------------------- a real engine run
import demo_server as DS
db = DS.build()
band = S.get(db, "engine.line_band")
fmax = float(S.get(db, "engine.feed_max_p"))
cap = float(S.get(db, "engine.p_cap"))
check(float(band[1]) >= 0.98 and fmax >= 0.97, f"the band and the headline limit sit at the display cap: band {band}, feed_max_p {fmax}")

fc = list(db.forecasts.find({"is_current": True, "hidden": {"$ne": True}}, {"_id": 0}))
high = [f for f in fc if f["p"] >= 0.90]
check(len(high) >= 5, f"near-certain lines are stored, not thrown away: {len(high)} at 90% or more")
check(all(f["p"] <= cap for f in fc), f"...and none is shown above the cap of {cap}")

cards = Q.group_cards(fc, fmax)
lead_high = [c for c in cards if c["p"] >= 0.90]
check(len(lead_high) >= 5, f"and they lead their card instead of hiding behind 'more lines': {len(lead_high)}")

# ---------------------------------------------------------------- the new markets
mk = {f"{f['scope']}.{f['stat']}" for f in fc}
check("team.sot" in mk, f"team shots on target is a market: {sorted(mk)}")
goals = [f for f in fc if f["stat"] == "match_goals"]
check(goals, "total goals in the match is a market")
check(all(g["scope"] == "team" and g["player_iid"] is None for g in goals), "...stored as a match-level team line")
check(all("in the match" in g["market"] for g in goals), f"...and reads as a sentence: '{goals[0]['market']}'")
by_match = {}
for g in goals:
    by_match.setdefault(g["match_iid"], []).append(g)
one = sorted(next(iter(by_match.values())), key=lambda g: g["thr"])
check(all(a["p"] >= b["p"] for a, b in zip(one, one[1:])), "...higher goal lines are less likely, within one match")

# it needs no statistics feed: the market is on even where coverage is missing
db.data_coverage.delete_many({})
mkts = B.enabled_markets(db, db.leagues.find_one({})["iid"])
check(mkts.get("team.goals") is True and mkts.get("team.shots") is False,
      "total goals works in a league with no statistics coverage; shots correctly does not")

# ---------------------------------------------------------------- the track record can grade it
m = db.matches.find_one({"iid": goals[0]["match_iid"]})
db.matches.update_one({"iid": m["iid"]}, {"$set": {"status": "final", "hg": 2, "ag": 1,
                                                   "ingested_at": goals[0]["kickoff"], "kickoff": goals[0]["kickoff"]}})
db.forecasts.update_many({"match_iid": m["iid"], "stat": "match_goals"},
                         {"$set": {"kickoff": __import__("datetime").datetime(2020, 1, 1, tzinfo=__import__("datetime").timezone.utc)}})
db.forecast_outcomes.delete_many({})
B.score_finished(db)
rows = list(db.forecast_outcomes.find({"stat": "match_goals"}, {"_id": 0}))
check(rows, "a finished match grades its total-goals lines")
check(all(r["actual"] == 3.0 for r in rows), f"...with the real total (2 + 1 = 3): {sorted({r['actual'] for r in rows})}")
r15 = next((r for r in rows if r["thr"] == 1.5), None)
r35 = next((r for r in rows if r["thr"] == 3.5), None)
check(r15 and r15["reached"] is True, "2+ goals is marked reached")
check(r35 is None or r35["reached"] is False, "4+ goals is not")

print("\nALL MARKET CHECKS PASSED")
