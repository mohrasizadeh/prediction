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
# Ranked on the fair measure the sort actually uses, not raw percentage points: since docs/48 "different from
# usual" is a log-odds change, so that a line usually at 90% is not beaten automatically by one usually at 30%.
# v8: the order is the same measure that already decides which line LEADS a card (docs/46):
# market importance x position relevance x lift x stake. It used to be raw lift, which is
# market-blind and position-blind -- so a centre-back's tackles line with a big departure
# outranked a striker's shot line, and the feed contradicted the card sitting in it.
_W, _SC = S.get(db, "engine.market_weights"), S.get(db, "engine.lift_scale")
_PW = S.get(db, "engine.position_weights")
o = [(Q.CONFIDENT[f["tier"]], -Q.prominence(f, _W, _SC, _PW)) for f in feed]
check(len(feed) > 0 and o == sorted(o), "insights_feed: Strong and Solid together by what the line has to say, then Watch (docs/25, docs/46)")
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
# --- Finder: a line outside the kept band is answered from the stored ladder
dl = db.forecasts.find_one({"scope": "player", "stat": "shots", "ladder": {"$exists": True}})
if dl:
    dl_thr = sorted(float(k) for k in dl["ladder"])[0]
    db.forecasts.delete_many({"match_iid": dl["match_iid"], "player_iid": dl["player_iid"], "stat": "shots", "thr": dl_thr})
    lf = Q._from_ladder(db, dl["match_iid"], "player", "shots", dl_thr, dl["player_iid"])
    check(lf and lf["from_ladder"] and lf["tier"] is None and lf["id"] is None and lf["addable"] is False, "ladder fallback: no tier, no id, not addable")
    check(lf["p"] == dl["ladder"][f"{dl_thr:g}"] and (lf["p"] <= 0.95 or lf["p_display"] == "95%+"), "ladder fallback: p from the ladder, 95%+ label above the band")
# --- Finder: pick a day (the PlayerStats date selector)
day_rows = Q.finder(db, "form", "shots", 1, last_n=10, day=day, now=now)
teams_that_day = {x for m in fx for x in (m["home_iid"], m["away_iid"])}
check(day_rows and all(x["team_iid"] in teams_that_day for x in day_rows), "finder form with a date: only teams playing that day")
none_rows = Q.finder(db, "form", "shots", 1, last_n=10, day="2031-01-01", now=now)
check(none_rows == [], "finder with a day that has no matches returns nothing")
lk = Q.finder(db, "likelihood", "shots", 1, day=day, now=now)
check(lk and all(x["kickoff"].date().isoformat() == day for x in lk), "finder likelihood with a date: only that day")
# --- what a card can draw about the last ten games (v7 Tier 1)
pf = [f for f in feed if f.get("scope") == "player" and (f.get("run") or [])]
check(bool(pf), "the feed carries a run for player cards")
f0 = pf[0]
check(all("pos" in g for g in f0["run"]), "every run entry says which position he played that day")
check(any(g.get("pos") for g in f0["run"]), "...and at least one of them is filled, so the strip has something to draw")
check(all("home" in g and "m" in g and "v" in g for g in f0["run"]), "a run entry still carries venue, minutes and the count")
# The streak is the leading run of hits in the SAME walk that produces usual_p, newest first.
for f in pf:
    newest = [g["v"] for g in reversed(f["run"])]
    want = 0
    for v in newest:
        if v <= f["thr"]:
            break
        want += 1
    if f["streak"] != want:
        check(False, f"streak counts the leading run of hits ({f['streak']} != {want})")
check(True, "streak counts the leading run of hits, newest first, on every card")
check(all(f["streak"] <= f["usual_n"] for f in pf), "a streak can never be longer than the window it was counted in")
# match_id was never written onto a forecast, so the Insights "Match page" link resolved to the
# internal iid and went nowhere.
check(all(f.get("match_id") for f in feed), "every card carries the public match id, so the fixture can be linked")
mid = feed[0]["match_id"]
check(db.matches.find_one({"id": mid, "iid": feed[0]["match_iid"]}) is not None, "...and it is that match's own public id, not another's")

# --- "N of the last M" is a count, not a ratio (v7 Tier 2)
# It was compared against however many rows survived the filters, so a stricter filter could make
# the search looser: measured on this fixture, asking for 60+ minutes used to return MORE rows.
lgs = [l["iid"] for l in db.leagues.find({}, {"iid": 1})]
base = Q.finder(db, "form", "shots", 1, last_n=10, league_iids=lgs, min_reached=0.6, now=now)
mins = Q.finder(db, "form", "shots", 1, last_n=10, league_iids=lgs, min_reached=0.6, min_minutes=60, now=now)
strt = Q.finder(db, "form", "shots", 1, last_n=10, league_iids=lgs, min_reached=0.6, started=True, now=now)
# Minutes and started do not narrow the POPULATION, they change which games are counted: "his last
# ten games of 60+ minutes" reaches further back than "his last ten games", so players the plain
# search missed can appear. That is what the sentence asks for, and it is why the bar below has to
# be a count -- as a ratio over whatever survived, three games with two hits passed "6 of 10".
check(all(len(r["hits"]) <= 10 for r in mins), "a filtered window is still at most the window the reader named")
check(all(r["reached"] >= 6 for r in base), "every row in '6 of the last 10' actually reached it six times")
check(all(r["reached"] >= 6 for r in mins), "...and still does once short appearances are dropped")
few = Q.finder(db, "form", "shots", 1, last_n=10, league_iids=lgs, min_reached=1.0, now=now)
check(all(r["reached"] >= 10 for r in few), "'all 10 of the last 10' needs ten hits, not three out of three")
twice = Q.finder(db, "form", "shots", 1, last_n=10, league_iids=lgs, min_reached=0.6, now=now)
check([r["id"] for r in twice] == [r["id"] for r in base], "the same search twice returns the same order")

# Which questions "Our forecast" can answer at all, read from the forecasts rather than a flag.
with_srv = None
fmk = {}
for d in db.forecasts.aggregate([{"$match": {"is_current": True, "hidden": {"$ne": True}}},
                                 {"$group": {"_id": {"scope": "$scope", "stat": "$stat"}}}]):
    fmk.setdefault(d["_id"]["scope"], set()).add(d["_id"]["stat"])
check("player" in fmk and {"shots", "sot", "tackles"} <= fmk["player"], f"player markets exist for the stats the engine makes: {sorted(fmk.get('player', []))}")
check(not ({"goals", "assists", "minutes", "fouls_committed"} & fmk.get("player", set())),
      "and none for the stats it does not -- which is what the Finder must stop offering in forecast mode")

# The club's Quick view offers a Venue control, which was a lie until team_history could honour it.
t_iid = db.team_match_stats.find_one({"corners": {"$ne": None}})["team_iid"]
allg = Q.team_history(db, t_iid, "corners", 40)["games"]
home = Q.team_history(db, t_iid, "corners", 40, "home")["games"]
away = Q.team_history(db, t_iid, "corners", 40, "away")["games"]
check(len(allg) > 0 and len(home) + len(away) == len(allg), "team history: home plus away is the whole run")
check(all(g["home"] for g in home) and not any(g["home"] for g in away), "...and each half holds only its own venue")
check(Q.team_history(db, t_iid, "corners", 40, "elsewhere")["games"] == allg, "an unknown venue filters nothing rather than everything")
check(all(g.get("home") is not None for g in allg), "every row says where it was played, which is what the strip draws")

print("\nALL QUERY CHECKS PASSED")
