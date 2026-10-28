"""Run after selftest.py logic: builds the same data and exercises every query."""
import os, sys, base64, datetime as dt
os.environ.setdefault("APP_ENCRYPTION_KEY", base64.b64encode(os.urandom(32)).decode())
HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("SOCCER_BRAIN_DIR", os.path.join(HERE, "soccer_brain"))
sys.path.insert(0, HERE); sys.path.insert(0, os.environ["SOCCER_BRAIN_DIR"])
import httpx, mongomock
import engine_bridge as B, ingest as I, mongo_init, queries as Q, security, settings_store as S
from cached_fetch import PitchClient
from fake_pitchapi import PLAYER_KEYS, TEAM_KEYS, FakePitch
from simulate import simulate_league

ok = lambda m: print("  ok  ", m)
def check(c, m):
    if not c: print("  FAIL", m); sys.exit(1)
    ok(m)

db = mongomock.MongoClient()["q"]; mongo_init.ensure_indexes(db)
security.save_provider_key(db, "pitchapi", "pk_test_zzzz")
S.put(db, "ingest.rps", 1000); S.put(db, "provider.pitchapi.team_keys", TEAM_KEYS); S.put(db, "provider.pitchapi.player_keys", PLAYER_KEYS)
S.put(db, "provider.position_map", {"0": "GK", "1": "DEF", "2": "MID", "3": "FWD"})
matches, tg, pg, _ = simulate_league(n_teams=12, seed=3)
n_final = int(matches["round"].max()) + 1 - 2
fake = FakePitch(matches, tg, pg, n_final)
c = PitchClient(db, http=httpx.Client(base_url="https://api.pitchapi.dev", transport=fake.transport()), sleep=lambda s: None)
I.sync_leagues(c); lg = db.leagues.find_one({}); I.sync_league_matches(c, lg, "2025/2026", "all"); I.process_queue(c)
I.assign_rounds(db, lg["iid"]); I.update_coverage(db, lg["iid"])
now = fake.kick(n_final) - dt.timedelta(hours=2)
I.lineup_watch(c, now=now); B.run_league(db, lg["iid"], now=now)

day = fake.kick(n_final).date().isoformat()
fx = Q.fixtures_for_date(db, day)
check(len(fx) == 6 and fx[0]["home"]["name"].startswith("Team") and fx[0]["probs"], "fixtures_for_date: 6 matches with names and win/draw/loss")
d = Q.match_detail(db, fx[0]["iid"])
check(d and d["forecasts"] and d["styles"] and d["h2h"] is not None, "match_detail: forecasts, styles, head-to-head")
check(all(not f.get("hidden") for f in d["forecasts"]), "match_detail hides hidden forecasts")
feed = Q.insights_feed(db, limit=20, tiers=("Strong", "Solid", "Watch"), now=now)
o = [(Q.CONFIDENT[f["tier"]], -(f.get("edge") or 0.0)) for f in feed]
check(len(feed) > 0 and o == sorted(o), "insights_feed: Strong and Solid together by the lift over usual, then Watch (docs/25)")
lk = Q.insights_feed(db, limit=20, tiers=("Strong", "Solid", "Watch"), now=now, sort="likely")
o2 = [(Q.TIER_RANK[f["tier"]], -f["p"]) for f in lk]
check(len(lk) > 0 and o2 == sorted(o2), "insights_feed sort=likely: ordered by tier then likelihood")
t = fx[0]["home_iid"]
g = Q.squad_grid(db, t, "shots", 5)
check(g and all(len(r["games"]) <= 5 for r in g), "squad_grid: at most 5 games per player")
check(len(Q.team_totals_grid(db, t, "corners", 5)) == 5, "team_totals_grid: 5 games with for/against")
for mode in ("likelihood", "form", "run"):
    r = Q.finder(db, mode, "shots", 2, last_n=10, now=now)
    check(len(r) > 0, f"finder mode={mode}: {len(r)} rows")
check(Q.finder(db, "form", "shots", 2, now=now)[0]["score"] >= Q.finder(db, "form", "shots", 2, now=now)[-1]["score"], "finder form sorted high to low")
lb = Q.leaderboard(db, lg["iid"], "shots", per90=True, min_minutes=300)
check(lb and lb[0]["per90"] >= lb[-1]["per90"], "leaderboard per 90 sorted")
a = Q.against_by_position(db, t, "shots", 10)
check(a["games"] == 10 and "FWD" in a["by_position"], "against_by_position: by position")
check(Q.track_record(db)["ready"] is False, "track_record: not shown until enough scored forecasts")
s = Q.search(db, "player 1")
check(s["players"] and Q.search(db, "(")["players"] == [], "search: partial match, regex characters are escaped")
check(Q.team_form(db, t, 5)[0]["result"] in "WDL", "team_form")
ph = Q.player_history(db, g[0]["player_iid"], 10)
check(len(ph["games"]) <= 10 and ph["reached"]["shots"]["1"] >= ph["reached"]["shots"]["2"], "player_history: reached counts fall as the line rises")
check(all(x["home"] for x in Q.player_history(db, g[0]["player_iid"], 20, venue="home")["games"]), "player_history: home filter")
check(all(x["started"] for x in Q.player_history(db, g[0]["player_iid"], 20, started=True)["games"]), "player_history: started filter")
pd_ = Q.player_detail(db, g[0]["player_iid"], now=now)
check(pd_ and pd_["next_match"] and pd_["forecasts"], "player_detail: next match and forecasts")
td = Q.team_detail(db, t, now=now)
check(td and td["style"] and len(td["form"]) == 5 and td["next"], "team_detail: style, form, next fixtures")
check(len(Q.league_matches(db, lg["iid"], "scheduled", now=now)) == 12 and len(Q.league_matches(db, lg["iid"], "final", now=now)) > 0, "league_matches: scheduled and results")
pid = db.players.find_one({}, {"id": 1, "iid": 1})
check(Q.iid_of(db, "players", pid["id"]) == pid["iid"], "iid_of maps public id to integer id")
fh = Q.finder(db, "form", "shots", 1, last_n=10, venue="home", started=True, min_minutes=45, positions=["FWD"], min_reached=0.5, now=now)
check(all(x["reached"] / x["games"] >= 0.5 for x in fh), "finder form: venue, started, minutes, position and min_reached filters")
fl = Q.finder(db, "likelihood", "shots", 1, positions=["DEF"], min_p=0.2, now=now)
check(all(x["pos"] == "DEF" and x["p"] >= 0.2 for x in fl), "finder likelihood: position and minimum filters")
# --- Finder: pick a day (the PlayerStats date selector)
day_rows = Q.finder(db, "form", "shots", 1, last_n=10, day=day, now=now)
teams_that_day = {x for m in fx for x in (m["home_iid"], m["away_iid"])}
check(day_rows and all(x["team_iid"] in teams_that_day for x in day_rows), "finder form with a date: only teams playing that day")
none_rows = Q.finder(db, "form", "shots", 1, last_n=10, day="2031-01-01", now=now)
check(none_rows == [], "finder with a day that has no matches returns nothing")
lk = Q.finder(db, "likelihood", "shots", 1, day=day, now=now)
check(lk and all(x["kickoff"].date().isoformat() == day for x in lk), "finder likelihood with a date: only that day")
print("\nALL QUERY CHECKS PASSED")
