"""Numbers users see are right (docs/36 H6-H9). Each check reproduces a bug the audit found, so it cannot come back:
H6 combos count a card line's chance to play once; H7 referee history survives a rebuild; H8 the player page only shows
lines for the next match; H9 a player's own record only adjusts lines for expected starters."""
import os, sys, base64
os.environ.setdefault("APP_ENCRYPTION_KEY", base64.b64encode(os.urandom(32)).decode())
HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(HERE, "soccer_brain")); sys.path.insert(0, os.path.join(HERE, "tests"))
import datetime as dt
import mongomock, mongo_init
import cards_model as CM, combo as CB, match_extras as MX, queries as Q, referees as RF


def check(c, m):
    if not c:
        print("  FAIL", m); sys.exit(1)
    print("  ok  ", m)


def newdb(name):
    db = mongomock.MongoClient()[name]; mongo_init.ensure_indexes(db); return db


UTC = dt.timezone.utc
now = dt.datetime.now(UTC)

# ---------------------------------------------------------------- H6: card lines in combos
db = newdb("h6")
m = {"iid": 1, "league_iid": 9, "home_iid": 11, "away_iid": 12, "kickoff": now + dt.timedelta(days=1), "status": "scheduled", "referee": None, "id": "m1", "ext_id": "m1"}
db.matches.insert_one(dict(m))
db.teams.insert_many([{"iid": 11, "name": "A", "id": "a", "ext_id": "a"}, {"iid": 12, "name": "B", "id": "b", "ext_id": "b"}])
db.players.insert_one({"iid": 5, "id": "p5", "ext_id": "p5", "name": "P", "team_iid": 11})
db.forecasts.insert_one({"id": "e1", "fkey": "x", "match_iid": 1, "is_current": True, "hidden": False, "scope": "player", "model": None, "player_iid": 5,
                         "team_iid": 11, "opp_iid": 12, "pos": "MID", "p_play": 0.6, "lineup_confirmed": False, "tier_basis": "pre", "stat": "shots",
                         "thr": 0.5, "p": 0.7, "lo": 0.6, "hi": 0.8, "kickoff": m["kickoff"]})
for i in range(10):
    db.player_match_stats.insert_one({"player_iid": 5, "match_iid": 100 + i, "minutes": 90, "yellow_cards": 1 if i % 3 == 0 else 0, "kickoff": now - dt.timedelta(days=7 * (i + 1))})
CM.run_match(db, m, "r", now, {"team": {}, "avg_team": 2.0, "ids": set(range(100, 110)), "pos90": {"MID": 0.2}, "ref_avg": 4.0})
card = db.forecasts.find_one({"stat": "yellow_cards"}, {"_id": 0})
shot = db.forecasts.find_one({"stat": "shots"}, {"_id": 0})
check(card["p_basis"] == "all" and CB.includes_play(card), "card lines are marked: their chance already counts the chance to play")
check(abs(CB.chance(card) - card["p"]) < 1e-9, f"combo uses a card line's chance as is ({card['p']:.3f}), not times p_play again")
check(abs(CB.chance(shot) - 0.7 * 0.6) < 1e-9, "other player lines are still 'if he plays' x chance to play")
old = dict(card); old.pop("p_basis")
check(abs(CB.chance(old) - card["p"]) < 1e-9, "card rows saved before the fix (no p_basis) are handled too")
rep = CB._report([dict(card, player=None, team=None, opp=None)], (1.0,))
check(rep["lines"][0]["includes_play"] is True, "the combo answer tells the page not to say 'if he plays' for card lines")

# ---------------------------------------------------------------- H7: referee history survives a rebuild
db = newdb("h7")
t0 = dt.datetime(2026, 1, 1)
for i in range(30):
    db.matches.insert_one({"iid": i + 1, "league_iid": 9, "status": "final", "referee": "Ref A", "home_iid": 1 + (i % 4), "away_iid": 5 + (i % 4), "hg": 1, "ag": 0,
                           "kickoff": t0 + dt.timedelta(days=i), "id": f"m{i}", "ext_id": f"m{i}"})
    db.team_match_stats.insert_many([{"match_iid": i + 1, "team_iid": 1 + (i % 4), "yellow_cards": 3}, {"match_iid": i + 1, "team_iid": 5 + (i % 4), "yellow_cards": 2}])
RF.refresh(db, 9)
before = RF.for_match(db, {"referee": "Ref A", "league_iid": 9})
MX.rebuild_referees(db, 9)                      # runs after every queue pass that handled match_extras
after = RF.for_match(db, {"referee": "Ref A", "league_iid": 9})
check("No history" not in after["sentence"] and after["factor"] == before["factor"], "the referee's history and card factor survive the rebuild")
check(db.referee_stats.find_one({"referee": "Ref A"})["home_win_pct"] == 1.0, "...and the rebuild still updates its own numbers")
check(db.referee_stats.count_documents({"referee": "Ref A", "league_iid": 9}) == 1, "...on the same row (no duplicates)")

# ---------------------------------------------------------------- H8: player page shows the next match only
db = newdb("h8")
db.teams.insert_many([{"iid": 11, "name": "A", "id": "a", "ext_id": "a"}, {"iid": 12, "name": "B", "id": "b", "ext_id": "b"}, {"iid": 13, "name": "C", "id": "c", "ext_id": "c"}])
db.players.insert_one({"iid": 5, "id": "p5", "ext_id": "p5", "name": "P", "team_iid": 11})
db.matches.insert_many([{"iid": 1, "id": "m1", "ext_id": "m1", "status": "final", "home_iid": 11, "away_iid": 12, "kickoff": now - dt.timedelta(days=2), "league_iid": 9},
                        {"iid": 2, "id": "m2", "ext_id": "m2", "status": "scheduled", "home_iid": 13, "away_iid": 11, "kickoff": now + dt.timedelta(days=5), "league_iid": 9}])
row = {"scope": "player", "player_iid": 5, "team_iid": 11, "stat": "shots", "thr": 0.5, "p": 0.8, "lo": 0.7, "hi": 0.9, "is_current": True, "hidden": False}
db.forecasts.insert_many([{**row, "id": "f1", "fkey": "1:p", "match_iid": 1, "opp_iid": 12, "kickoff": now - dt.timedelta(days=2)},
                          {**row, "id": "f2", "fkey": "2:p", "match_iid": 2, "opp_iid": 13, "p": 0.6, "kickoff": now + dt.timedelta(days=5)}])
d = Q.player_detail(db, 5)
check(d["next_match"]["iid"] == 2 and {c["match_iid"] for c in d["cards"]} == {2}, "player page: only the next match's lines, not last weekend's")

# ---------------------------------------------------------------- H9: own-record adjustment only for expected starters
import demo_server as DS
db = DS.build()
moved = [f for f in db.forecasts.find({"scope": "player", "lineup_badge": {"$in": ["bench", "unsure"]}}) if abs(f["p"] - f["p_pre_anchor"]) > 1e-9]
check(db.forecasts.count_documents({"lineup_badge": {"$in": ["bench", "unsure"]}}) > 0 and not moved,
      "bench and doubtful players keep the model's number (their record comes from starts)")
starters = [f for f in db.forecasts.find({"scope": "player", "lineup_badge": {"$in": ["confirmed", "likely"]}, "rec_n": {"$gte": 8}})]
check(any(abs(f["p"] - f["p_pre_anchor"]) > 1e-6 for f in starters), "expected starters still get their own record blended in (docs/32)")

print("\nALL NUMBER CHECKS PASSED")
