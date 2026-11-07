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

# --- v9: the page leads on the band a reader acts on, not on the mean of every band -------------
# The headline was "across N forecasts we said 29% on average, it happened 31%". Two faults, and
# the second is the one that matters: the mean is dominated by the mass of LOW lines, where being
# right is easy by being timid -- and a mean over every band can be right while every band inside
# it is wrong, because overconfidence at the top and underconfidence at the bottom cancel out.
# This builds exactly that: perfect in aggregate, badly wrong in both halves.
_tr = [{"league_iid": None, "stat": "shots", "scope": "player", "player_played": True,
        "tier": "Watch", "p": 0.20, "reached": i < 120, "scored_at": now,
        "fkey": f"trlo{i}", "forecast_id": f"trlo{i}"}                          # said 20, happened 40
       for i in range(300)]
_tr += [{"league_iid": None, "stat": "shots", "scope": "player", "player_played": True,
         "tier": "Strong", "p": 0.90, "reached": i < 210, "scored_at": now,
         "fkey": f"trhi{i}", "forecast_id": f"trhi{i}"}                         # said 90, happened 70
        for i in range(300)]
db.forecast_outcomes.insert_many([dict(x) for x in _tr])
tr = Q.track_record(db, min_n=100)
check(tr["ready"] and abs(tr["overall"]["stated"] - tr["overall"]["actual"]) < 0.02,
      f"the whole-record mean looks healthy: said {tr['overall']['stated']:.0%}, happened {tr['overall']['actual']:.0%}")
check(tr.get("high") and tr["high"]["n"] == 300 and abs(tr["high"]["stated"] - 0.90) < 0.01,
      "...but the high band is reported on its own")
check(tr["high"]["actual"] < tr["high"]["stated"] - 0.15,
      f"...and it says the thing the mean hid: said {tr['high']['stated']:.0%}, happened {tr['high']['actual']:.0%}")
check(tr["high"]["from"] == float(S.get(db, "engine.record_high_p")),
      "the band's floor is the setting, and travels with the answer so the page can name it")
db.forecast_outcomes.delete_many({"fkey": {"$regex": "^trlo|^trhi"}})
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

# --- v8: the ladder carrier -------------------------------------------------------------------
# Reported as "Idrissa Gueye has no percentage and no button". The ladder was stamped only on the
# lines that SURVIVED engine.line_band, so a player whose every rung fell below it left nothing
# behind at all and the Finder had no answer -- an empty cell where every other row carries a
# number, which reads as the player being missing.
carriers = list(db.forecasts.find({"carrier": True}, {"_id": 0, "stat": 1, "tier": 1, "ladder": 1, "player_iid": 1, "scope": 1}))
check(all(c["tier"] is None and c.get("ladder") for c in carriers),
      f"a ladder carrier holds a ladder and no tier ({len(carriers)} of them)")
# It must be invisible everywhere a reader looks. NOT_HIDDEN is the one guard, so test the queries.
feed_keys = {f.get("fkey") for f in Q.insights_feed(db, limit=500, tiers=("Strong", "Solid", "Watch"), now=now)}
carrier_keys = {c.get("fkey") for c in db.forecasts.find({"carrier": True}, {"fkey": 1})}
check(not (feed_keys & carrier_keys), "a carrier never reaches the feed")
for mid in {c["match_iid"] for c in db.forecasts.find({"carrier": True}, {"match_iid": 1})}:
    md = Q.match_detail(db, mid)
    check(not ({f.get("fkey") for f in md.get("forecasts", [])} & carrier_keys),
          "a carrier never reaches the match page, which filters on no tier at all")
    break
# And the thing it exists for: a line the band dropped can still be answered.
if carriers:
    c0 = db.forecasts.find_one({"carrier": True})
    thr = float(next(iter(c0["ladder"])))
    got = Q._from_ladder(db, c0["match_iid"], c0["scope"], c0["stat"], thr,
                         c0.get("player_iid") if c0["scope"] == "player" else c0.get("team_iid"))
    check(got is not None and got["p"] is not None and got["tier"] is None and got["addable"] is False,
          "a line the band dropped is answerable from the carrier, with no tier and nothing to save")

# A rung no ladder holds must stay unanswerable rather than borrow a neighbour's number.
# engine.player_ladder starts tackles at 1.5, so "1+ tackles" is a question with no rung.
lad = S.get(db, "engine.player_ladder") or {}
if lad.get("tackles") and 0.5 not in [float(t) for t in lad["tackles"]]:
    mid2 = db.forecasts.find_one({"scope": "player", "stat": "tackles"}, {"match_iid": 1, "player_iid": 1})
    if mid2:
        check(Q._from_ladder(db, mid2["match_iid"], "player", "tackles", 0.5, mid2["player_iid"]) is None,
              "1+ tackles is not on the ladder, so nothing may imply a number for it")

# The club's Quick view offers a Venue control, which was a lie until team_history could honour it.
t_iid = db.team_match_stats.find_one({"corners": {"$ne": None}})["team_iid"]
allg = Q.team_history(db, t_iid, "corners", 40)["games"]
home = Q.team_history(db, t_iid, "corners", 40, "home")["games"]
away = Q.team_history(db, t_iid, "corners", 40, "away")["games"]
check(len(allg) > 0 and len(home) + len(away) == len(allg), "team history: home plus away is the whole run")
check(all(g["home"] for g in home) and not any(g["home"] for g in away), "...and each half holds only its own venue")
check(Q.team_history(db, t_iid, "corners", 40, "elsewhere")["games"] == allg, "an unknown venue filters nothing rather than everything")
check(all(g.get("home") is not None for g in allg), "every row says where it was played, which is what the strip draws")

# --- v8: goals and assists are stored, and the backfill for history that predates that ---------
print("[goals zero-fill]")
played = list(db.player_match_stats.find({"minutes": {"$ne": None}}, {"goals": 1, "assists": 1, "goal_involvements": 1, "shots": 1}))
check(played and all(r.get("goals") is not None for r in played),
      f"every appearance records a goal count, 0 included ({len(played)} rows)")
check(all(r.get("goal_involvements") == (r["goals"] + r["assists"]) for r in played),
      "goal_involvements is stored, and is goals + assists on every row")
scored = [r for r in played if r["goals"] > 0]
check(0 < len(scored) < len(played), f"some appearances have a goal and most do not ({len(scored)} of {len(played)})")
# The bug this fixes, stated as the arithmetic: a rate over games-he-scored-in is near 1.0 a game.
# Over every appearance it is a believable per-match rate.
bad = sum(r["goals"] for r in scored) / len(scored)
good = sum(r["goals"] for r in played) / len(played)
check(bad > 0.9 and good < 0.5, f"goals per appearance {good:.2f}, but {bad:.2f} if the goalless rows were still null")

# Nothing left to do, because ingest now fills it -- and the "no goals at all" alarm stays quiet.
rep = I.fill_player_goal_cols(db, dry_run=True)
check(rep["ok"] and rep["goals"] == 0 and rep["assists"] == 0 and rep["rows_with_a_goal"] > 0,
      "the backfill is a no-op on data ingested since the fix")

# Legacy rows: null goals on appearances that were read (shots is not null). They fill, and the
# derived column is recomputed with them.
ids = [r["_id"] for r in db.player_match_stats.find({"minutes": {"$ne": None}}, {"_id": 1}).limit(5)]
db.player_match_stats.update_many({"_id": {"$in": ids}}, {"$set": {"goals": None, "goal_involvements": None}})
dry = I.fill_player_goal_cols(db, dry_run=True)
check(dry["goals"] == len(ids) and db.player_match_stats.count_documents({"_id": {"$in": ids}, "goals": None}) == len(ids),
      "a dry run counts what it would fill and writes nothing")
wet = I.fill_player_goal_cols(db, dry_run=False)
check(wet["ok"] and wet["goals"] == len(ids) and wet["involvements"] == len(ids),
      "the backfill fills the goals and recomputes goal_involvements")
check(all(r["goals"] == 0.0 and r["goal_involvements"] == r["assists"]
          for r in db.player_match_stats.find({"_id": {"$in": ids}}, {"goals": 1, "assists": 1, "goal_involvements": 1})),
      "...and the filled rows are consistent again")

# THE GATE. With the column unmapped every row is null, so a naive fill would record that nobody in
# the league has ever scored, at full coverage. It must refuse instead.
keys = S.get(db, "provider.pitchapi.player_keys")
S.put(db, "provider.pitchapi.player_keys", {**keys, "goals": {**keys["goals"], "key": None}}, "selftest")
ref = I.fill_player_goal_cols(db, dry_run=False)
check(not ref["ok"] and "does not map" in ref["reason"] and ref["goals"] == 0,
      "with the column unmapped the backfill refuses rather than writing zeros over the whole league")
S.put(db, "provider.pitchapi.player_keys", keys, "selftest")

print("\nALL QUERY CHECKS PASSED")
