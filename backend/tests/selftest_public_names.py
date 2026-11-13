"""Public answers carry names and images for opponents, H2H rows, team next matches and match starters (our database only)."""
import sys, os
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE if os.path.basename(HERE) == "tests" else "/app/backend/tests")
sys.path.insert(0, HERE)
from testkit import *
import queries as Q
from datetime import datetime, timedelta, timezone

now = datetime.now(timezone.utc)
db.leagues.insert_one({"iid": 1, "id": "lg1", "name": "L"})
db.teams.insert_many([{"iid": 1, "id": "t1", "name": "Alpha", "league_iid": 1}, {"iid": 2, "id": "t2", "name": "Beta", "league_iid": 1}])
db.players.insert_one({"iid": 5, "id": "p5", "name": "Pat Doe", "team_iid": 1, "pos": "MID"})
db.matches.insert_many([{"iid": 10, "id": "m10", "league_iid": 1, "home_iid": 1, "away_iid": 2, "status": "final", "hg": 2, "ag": 1, "kickoff": now - timedelta(days=3)},
                        {"iid": 11, "id": "m11", "league_iid": 1, "home_iid": 2, "away_iid": 1, "status": "scheduled", "kickoff": now + timedelta(days=3)}])
db.team_match_stats.insert_one({"match_iid": 10, "team_iid": 1, "opp_iid": 2, "home": True, "kickoff": now - timedelta(days=3), "shots": 9, "shots_against": 4})
db.player_match_stats.insert_one({"match_iid": 10, "player_iid": 5, "team_iid": 1, "opp_iid": 2, "kickoff": now - timedelta(days=3), "shots": 2, "minutes": 90, "started": True})
db.lineups.insert_one({"match_iid": 11, "team_iid": 1, "player_iid": 5, "started": True})

t = Q.team_detail(db, 1)
check(t["next"][0]["home"]["name"] == "Beta" and t["form"][0]["opp"]["name"] == "Beta" and t["league"]["id"] == "lg1", "team page: next opponents, form opponent, league")
check(Q.team_totals_grid(db, 1, "shots")[0]["opp"]["name"] == "Beta", "team totals: opponent name")
check(Q.squad_grid(db, 1, "shots")[0]["games"][0]["opp"]["name"] == "Beta", "squad grid: opponent per game")
m = Q.match_detail(db, 11)
check(m["starters"][0]["player"]["name"] == "Pat Doe" and m["h2h"]["matches"][0]["home"]["name"] == "Alpha", "match: starter names and H2H teams")
check(Q.player_detail(db, 5, now)["next_match"]["away"]["name"] == "Alpha", "player: next match teams")
# The match page's Stats tab (team_stats / player_stats / coach). A PitchAPI-shaped match: no rating
# and no coach were ever stored, so both must come back as None -- the page hides them on None.
f = Q.match_detail(db, 10)
check(f["team_stats"]["home"]["shots"] == 9 and f["team_stats"]["away"] is None and f["team_stats"]["home"]["xg"] is None,
      "finished match: team_stats per side, an unstored value stays None (never 0)")
ps = f["player_stats"]
check(len(ps) == 1 and ps[0]["player"]["name"] == "Pat Doe" and ps[0]["side"] == "home" and ps[0]["shots"] == 2,
      "finished match: player_stats rows carry the player and his side")
check(ps[0]["rating"] is None and f["coach"] == {"home": None, "away": None},
      "no rating and no coach stored: both are None, not invented")
check(m["team_stats"] is None and m["player_stats"] == [], "an unplayed match has no stats")
print("public names self-test passed")
