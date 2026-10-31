"""selftest_radar.py -- the two-club radar is opponent-adjusted, never has an empty spoke, and handles missing expected goals (docs/35)."""
import datetime as dt
import numpy as np
import testkit as K
from testkit import check
import mongomock
import team_insights as TI

rng = np.random.default_rng(2)
db = mongomock.MongoClient().db
db.leagues.insert_one({"iid": 1, "current_season": "s"})
N = 8
att = np.linspace(0.45, -0.45, N)                     # team 0 is the best attack, 7 the worst
con = np.linspace(-0.3, 0.3, N)                       # team 0 concedes least
for t in range(N):
    db.teams.insert_one({"iid": t, "id": f"t{t}", "name": f"Team {t}", "league_iid": 1})
mid = 0
start = dt.datetime(2026, 1, 1)
for rd in range(10):
    for h in range(N):
        a = (h + 1 + rd) % N
        if a == h: continue
        mid += 1
        k = start + dt.timedelta(days=rd * 3)
        gh = rng.poisson(np.exp(0.3 + att[h] + con[a])); ga = rng.poisson(np.exp(0.1 + att[a] + con[h]))
        sh = rng.poisson(np.exp(2.5 + att[h] + con[a])); sa = rng.poisson(np.exp(2.5 + att[a] + con[h]))
        db.matches.insert_one({"iid": mid, "league_iid": 1, "season": "s", "status": "final", "kickoff": k})
        for team, opp, home, g, ga_, s_, sa_ in ((h, a, True, gh, ga, sh, sa), (a, h, False, ga, gh, sa, sh)):
            db.team_match_stats.insert_one({"match_iid": mid, "team_iid": team, "opp_iid": opp, "league_iid": 1, "kickoff": k, "home": home,
                "goals": int(g), "goals_against": int(ga_), "shots": int(s_), "shots_against": int(sa_), "sot": int(s_ * .35), "corners": int(s_ / 2.5),
                "poss": 50 + 10 * (att[team] - att[opp]), "xg": None})      # no expected goals from the feed
r = TI.league_radar(db, 1)
check(len(r) == N, "every club of the season is rated")
check(all(all(v is not None and 0 <= v <= 1 for v in x["axes"].values()) and len(x["axes"]) == 6 for x in r.values()), "six spokes, none empty, all between 0 and 1, even with no expected goals")
check(r[0]["axes"]["shots"] == 1.0 and r[7]["axes"]["shots"] == 0.0, "best shooting side sits at the top, worst at the bottom")
check(np.corrcoef([r[t]["axes"]["shots"] for t in range(N)], -np.arange(N))[0, 1] > .85, "shots spoke follows the true strength order")
check(r[0]["axes"]["poss"] > r[7]["axes"]["poss"] and r[0]["axes"]["corners"] > r[7]["axes"]["corners"], "possession and corners follow the club's strength")
db.teams.update_one({"iid": 0}, {"$set": {"image": None}})
c = TI.compare(db, "t0", "t7", as_fixture=True)
check(len(c["radar"]) == 6 and all(x["a"] is not None and x["b"] is not None and x["means"] for x in c["radar"]), "compare returns the new radar with its explanations")
check(c["radar_games"]["a"] > 0, "game counts are returned so the page can say when it is early in the season")
print("ok")
