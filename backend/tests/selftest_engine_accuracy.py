"""The engine review's fixes, each pinned (2026-11): who shares the team total, obvious lines, team
calibration, the record check, competitions in the rotation calendar, neutral grounds, referees."""
import os, sys, base64
os.environ.setdefault("APP_ENCRYPTION_KEY", base64.b64encode(os.urandom(32)).decode())
HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(HERE, "soccer_brain")); sys.path.insert(0, os.path.join(HERE, "tests"))
import numpy as np
import pandas as pd
import mongomock
import engine as E
import engine_bridge as B
import calibration as CAL
import queries as Q
import referees as RF
import tiering as TI
import simulate


def check(c, m):
    if not c:
        print("  FAIL", m); sys.exit(1)
    print("  ok  ", m)


ms, tg, pg = simulate.simulate_league(n_teams=12, seed=5)[:3]
AS_OF = int(ms["round"].max())


def shots(eng, lineups=None, team=0):
    f, _ = eng.predict_fixture(0, 1, lineups)
    return {x.player: x for x in f if x.scope == "player" and x.stat == "shots" and x.thr == 0.5 and x.team == team}


# ---------------------------------------------------------------- 1. departed players
base = shots(E.SoccerEngine(seed=0, n_draws=20).fit(ms, tg, pg, AS_OF))
g0 = sorted(tg[tg.team == 0].game_id.unique())
gone = pg[(pg.team == 0) & (pg.game_id.isin(g0[:8]))].copy()
gone["player"] += 100000                      # a whole squad that left after the eighth match
ghost = shots(E.SoccerEngine(seed=0, n_draws=20).fit(ms, tg, pd.concat([pg, gone]), AS_OF))
ratio = np.mean([ghost[k].expected / base[k].expected for k in base])
# The copy also duplicates those early matches for the positional averages, which is what is left.
check(abs(ratio - 1.0) < 0.05, f"players who left no longer take a share of the team's shots (current players x{ratio:.3f})")

# ---------------------------------------------------------------- 2. confirmed eleven adds up
eng = E.SoccerEngine(seed=0, n_draws=20).fit(ms, tg, pg, AS_OF)
last = pg[pg.team == 0].sort_values("round").game_id.iloc[-1]
xi = set(pg[(pg.game_id == last) & (pg.team == 0) & (pg.started == 1)].player)
f, _ = eng.predict_fixture(0, 1, {0: xi})
tot = sum(x.expected for x in f if x.scope == "player" and x.stat == "shots" and x.thr == 0.5 and x.team == 0)
team = [x.expected for x in f if x.scope == "team" and x.stat == "shots" and x.team == 0][0]
check(abs(tot / team - 1.0) < 0.05, f"with the eleven named, the players add up to the team's shots ({tot:.2f} v {team:.2f})")

# ---------------------------------------------------------------- 3. the likely range is exact
a = shots(E.SoccerEngine(seed=1, n_draws=60).fit(ms, tg, pg, AS_OF))
b = shots(E.SoccerEngine(seed=2, n_draws=60).fit(ms, tg, pg, AS_OF))
check(all(abs(a[k].lo - b[k].lo) < 1e-9 for k in a), "the low end of the range no longer moves with the random seed")

# ---------------------------------------------------------------- 4. neutral ground
eng_n = E.SoccerEngine(seed=0, n_draws=20).fit(ms, tg, pg, AS_OF)
_, p1 = eng_n.predict_fixture(0, 1, neutral=True)
_, p2 = eng_n.predict_fixture(1, 0, neutral=True)
check(abs(p1["p_home"] - p2["p_away"]) < 1e-6, "at a neutral ground the listed home side gets no advantage")
_, ph = eng_n.predict_fixture(0, 1)
check(ph["p_home"] > p1["p_home"], "...and a real home match still has one")

# ---------------------------------------------------------------- 5. obvious lines
yamal = lambda thr, p: {"scope": "player", "stat": "shots", "thr": thr, "p": p, "expected_usual": 3.9, "match_iid": 1,
                        "team_iid": 1, "player_iid": 7, "p_usual": p - 0.02, "edge": 0.02, "tier": "Solid", "pos": "FWD",
                        "lo": p - 0.05, "hi": p + 0.03, "fkey": f"k{thr}"}
check(Q.is_obvious(yamal(0.5, 0.97), 0.4) and not Q.is_obvious(yamal(1.5, 0.88), 0.4),
      "1+ shot is obvious for a player who averages 3.9; 2+ is a real question")
check(not Q.is_obvious({**yamal(0.5, 0.8), "expected_usual": 1.8}, 0.4), "...and 1+ is a real question for one who averages 1.8")
cards = Q.group_cards([yamal(0.5, 0.96), yamal(1.5, 0.88), yamal(2.5, 0.73)], 0.97, "player", None, "odds", 0.0, None,
                      "confident", obvious=0.4)
check(cards[0]["thr"] == 1.5, f"Yamal's card leads with 2+ shots, not 1+ (led with {cards[0]['market'] if 'market' in cards[0] else cards[0]['thr']})")
ladder = [dict(yamal(t, p), lo=p - 0.05, hi=p + 0.02) for t, p in ((0.5, 0.97), (1.5, 0.88), (2.5, 0.73), (3.5, 0.55), (4.5, 0.38))]
kept = B.select_lines(ladder, (0.5, 0.985), 3, obvious=0.4)
check(sorted(d["thr"] for d in kept) == [1.5, 2.5, 3.5], "the three lines a card carries are the real questions; 1+ stays on the ladder")
check("0.5" in kept[0]["ladder"], "...where the Finder and combos can still reach it")

# ---------------------------------------------------------------- 6. team calibration
m = CAL.default_map()
check(CAL.apply(m, 0.98, "pre", "team") > 0.95, "a near-certain team line is no longer capped at 92%")
check(abs(CAL.apply(m, 0.85, "pre", "team") - 0.80) < 0.01, "...while a stated 85% still reads 80%, the correction the audit asked for")

# ---------------------------------------------------------------- 7. the record check
db = mongomock.MongoClient().db
# A perfectly honest record: lines from 75% to 89%, each happening as often as it said.
rng = np.random.default_rng(3)
ps = np.repeat(np.linspace(0.75, 0.89, 15), 6)
db.forecast_outcomes.insert_many([{"scope": "player", "stat": "shots", "p": float(p), "player_played": True,
                                   "reached": bool(rng.random() < p)} for p in ps])
est, n = TI.Record(db, min_n=40).earned("player", "shots", 0.9)
check(n >= 40 and abs(est - 0.9) < 0.05, f"an honest record near 90% reads about 90%, not the hit rate of the 80% lines beside it ({est:.2f})")

# ---------------------------------------------------------------- 8. competitions and referees
check(B.comp_of({"catalog_key": "uefa.ucl"}) == "ucl" and B.comp_of({"name": "League Cup", "kind": "cup"}) == "league_cup"
      and B.comp_of({"name": "Friendlies", "kind": "international"}) == "friendly" and B.comp_of({"kind": "league"}) == "league",
      "a cup, a European night and a friendly are no longer all called a league match")
check(B.is_neutral({"catalog_key": "fifa.wc"}, {}) and not B.is_neutral({"kind": "league"}, {"stage": "Final"}),
      "World Cup matches are at neutral grounds; a league match is not")
check(RF.clean("Michael Oliver, England") == RF.clean("Michael Oliver") == "Michael Oliver",
      "one referee, one history, however the feed writes his name")
print("ALL OK")
