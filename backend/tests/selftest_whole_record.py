"""A player's record is his, not one competition's (engine.all_competitions, engine.pool_internationals).

The case that found it: Lamine Yamal, 2-6 shots in each of his last ten, read "1+ shot 80%" for
Spain. The Nations League frame held a handful of his internationals, so his share of Spain's shots
came mostly from the average midfielder, and the card drew a ten-game strip the number never saw.
"""
import os, sys, base64
from datetime import datetime, timedelta
os.environ.setdefault("APP_ENCRYPTION_KEY", base64.b64encode(os.urandom(32)).decode())
HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(HERE, "soccer_brain")); sys.path.insert(0, os.path.join(HERE, "tests"))
import numpy as np
import pandas as pd
import mongomock
import engine as E
import engine_bridge as B
import settings_store as S
import simulate


def check(c, m):
    if not c:
        print("  FAIL", m); sys.exit(1)
    print("  ok  ", m)


# ---------------------------------------------------------------- the engine
ms, tg, pg = simulate.simulate_league(n_teams=12, seed=5)[:3]
AS_OF = int(ms["round"].max())
# One midfielder with only three games in this frame: a country's player in one competition.
mids = pg[(pg["team"] == 0) & (pg["pos"] == "MID")]
pid = int(mids.groupby("player")["minutes"].sum().idxmax())
keep_games = sorted(pg[(pg["player"] == pid)]["game_id"].unique())[-3:]
pg2 = pg[(pg["player"] != pid) | (pg["game_id"].isin(keep_games))].copy()


def shots(eng):
    f, _ = eng.predict_fixture(0, 1)
    return {x.thr: x for x in f if x.scope == "player" and x.player == pid and x.stat == "shots"}


base = E.SoccerEngine(seed=0, n_draws=20).fit(ms, tg, pg2, AS_OF)
b = shots(base)
check(b and b[min(b)].rec_n <= 3, "without his other games the frame holds only a few of his")

# His club season: forty games, 2 to 6 shots in each, out of 15-ish team shots.
rng = np.random.default_rng(1)
club = pd.DataFrame({"minutes": [90.0] * 40, "shots": rng.integers(2, 7, 40).astype(float),
                     "team_shots": rng.integers(13, 19, 40).astype(float),
                     "sot": rng.integers(1, 3, 40).astype(float), "team_sot": rng.integers(4, 7, 40).astype(float),
                     "tackles": rng.integers(0, 3, 40).astype(float), "team_tackles": rng.integers(14, 20, 40).astype(float)})
whole = E.SoccerEngine(seed=0, n_draws=20).fit(ms, tg, pg2, AS_OF).set_player_history({pid: club})
w = shots(whole)
lo = min(w)
check(w[lo].rec_n == 40, "with them, the forty-game record is his whole record")
check(w[lo].expected > b[lo].expected * 1.3, f"his expected shots follow his record ({b[lo].expected:.2f} -> {w[lo].expected:.2f})")
check(w[lo].p > b[lo].p, f"and so does the chance of 1+ ({b[lo].p:.2f} -> {w[lo].p:.2f})")
check(abs(w[lo].p_raw - float((club['shots'].values[-10:] > lo).mean())) < 1e-9, "the ten-game strip is the one the card draws")

# A shorter outside record than the frame's never replaces it.
short = E.SoccerEngine(seed=0, n_draws=20).fit(ms, tg, pg2, AS_OF).set_player_history({pid: club.head(2)})
check(shots(short)[lo].rec_n == b[lo].rec_n, "a shorter record elsewhere does not replace the frame's")

# The opponent still moves it: the team total is this fixture's.
f_easy = {x.thr: x for x in whole.predict_fixture(0, 1)[0] if x.scope == "player" and x.player == pid and x.stat == "shots"}
f_hard = {x.thr: x for x in whole.predict_fixture(0, 2)[0] if x.scope == "player" and x.player == pid and x.stat == "shots"}
check(abs(f_easy[lo].expected - f_hard[lo].expected) > 1e-6, "a different opponent still gives a different number")

# The keeper case the owner found next: Mads Hermansen, a save in each of his last ten, read "1+ save
# 82%" for Denmark v Portugal. Same cause, same fix: the keeper IS his side's saves, so his record is
# his club's saves too.
E.PLAYER_THR.setdefault("saves", [0.5, 1.5, 2.5])
gk = int(pg[(pg["team"] == 0) & (pg["pos"] == "GK")].groupby("player")["minutes"].sum().idxmax())
gk_keep = sorted(pg[pg["player"] == gk]["game_id"].unique())[-3:]
pg3 = pg[(pg["player"] != gk) | (pg["game_id"].isin(gk_keep))].copy()


def saves(eng):
    f, _ = eng.predict_fixture(0, 1)
    return {x.thr: x for x in f if x.scope == "player" and x.player == gk and x.stat == "saves"}


g_base = saves(E.SoccerEngine(seed=0, n_draws=20, extra_stats=("saves",)).fit(ms, tg, pg3, AS_OF))
gk_club = pd.DataFrame({"minutes": [90.0] * 40, "saves": rng.integers(1, 6, 40).astype(float)})
gk_club["team_saves"] = gk_club["saves"]
g_whole = saves(E.SoccerEngine(seed=0, n_draws=20, extra_stats=("saves",)).fit(ms, tg, pg3, AS_OF).set_player_history({gk: gk_club}))
if g_base and g_whole:
    check(g_whole[min(g_whole)].rec_n == 40 and g_whole[min(g_whole)].rec_k == 40,
          "a keeper's forty-game record comes from every competition (40 of 40 with a save)")
else:
    print("  skip  saves market not fitted on the simulated league")

# ---------------------------------------------------------------- the bridge
db = mongomock.MongoClient().db
db.leagues.insert_many([{"iid": 1, "kind": "league"}, {"iid": 2, "kind": "international"},
                        {"iid": 3, "kind": "international"}, {"iid": 4, "kind": "continental"}])
check(B.frame_leagues(db, 1) == [1], "a domestic league is fitted on its own")
check(B.frame_leagues(db, 4) == [4], "so is a club competition")
check(B.frame_leagues(db, 2) == [2, 3], "a national-team competition is fitted with every other one")
S.put(db, "engine.pool_internationals", False)
check(B.frame_leagues(db, 2) == [2], "...unless switched off")

now = datetime(2026, 11, 14)
rows = []
for i in range(50):
    rows.append({"player_iid": 7, "match_iid": i, "league_iid": 1 if i % 3 else 2, "kickoff": now - timedelta(days=60 - i),
                 "minutes": 90 if i != 10 else 0, "shots": i % 5, "team_shots": 15, "sot": 1, "team_sot": 5,
                 "tackles": 1, "team_tackles": 15})
rows.append({"player_iid": 7, "match_iid": 99, "league_iid": 1, "kickoff": now + timedelta(days=1), "minutes": 90, "shots": 9,
             "team_shots": 15, "sot": 1, "team_sot": 5, "tackles": 1, "team_tackles": 15})
db.player_match_stats.insert_many(rows)
h = B.player_history(db, [7, 8], now)
check(set(h) == {7}, "a player with no games has no history")
check(len(h[7]) == 40, "the last forty appearances")
check((h[7]["minutes"] > 0).all(), "only games he played in")
check(h[7]["shots"].iloc[-1] == 49 % 5, "oldest first, ending with his latest before the match")
check(9 not in set(h[7]["shots"]), "nothing from after the forecast")

# ---------------------------------------------------------------- why no Strong
import tiering as TI
soon = now + timedelta(hours=20)
db.forecasts.insert_many([
    {"is_current": True, "kickoff": soon, "scope": "player", "stat": "shots", "p": 0.93, "lo": 0.88, "tier": "Solid",
     "tier_note": "Held at Solid until our record on these lines is measured", "player_iid": 7, "match_iid": 1},
    {"is_current": True, "kickoff": soon, "scope": "player", "stat": "shots", "p": 0.91, "lo": 0.80, "tier": "Solid", "player_iid": 7, "match_iid": 1},
    {"is_current": True, "kickoff": soon, "scope": "player", "stat": "sot", "p": 0.95, "lo": 0.9, "tier": "Strong", "player_iid": 7, "match_iid": 1},
    {"is_current": True, "kickoff": soon, "scope": "player", "stat": "sot", "p": 0.99, "lo": 0.9, "tier": None, "carrier": True, "player_iid": 7, "match_iid": 1},
    {"is_current": True, "kickoff": now + timedelta(days=5), "scope": "player", "stat": "sot", "p": 0.95, "lo": 0.9, "tier": "Strong", "player_iid": 7, "match_iid": 2},
])
fu = TI.funnel(db, 48, now)
check(fu["total"] == 3 and fu["tiers"]["Strong"] == 1 and fu["tiers"]["Solid"] == 2, "counts the next two days' published lines, carriers left out")
check(fu["held"]["record_thin"] == 1 and fu["held"]["range"] == 1, "and names what held each Strong number back")
check({(r["scope"], r["stat"]) for r in fu["record"]} == {("player", "shots"), ("player", "sot")}, "with the record behind each market")

# A thin market is judged by its scope's record instead of being held at Solid for weeks.
db2 = mongomock.MongoClient().db
db2.forecast_outcomes.insert_many([{"scope": "player", "stat": "shots", "p": 0.9, "player_played": True, "reached": i % 20 != 0} for i in range(60)]
                                  + [{"scope": "player", "stat": "sot", "p": 0.9, "player_played": True, "reached": True} for _ in range(5)])
rec = TI.Record(db2, min_n=40)
est, n = rec.earned("player", "sot", 0.9)
check(n == 65 and est > 0.9, "on-target with five settled lines borrows the player record (65 lines)")
check(rec.earned("player", "shots", 0.9)[1] == 60, "a market with enough of its own keeps its own")
check(rec.earned("team", "corners", 0.9) == (None, 0), "a scope with nothing stays unmeasured")
print("ALL OK")
