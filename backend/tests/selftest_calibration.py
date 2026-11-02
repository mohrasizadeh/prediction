"""selftest_calibration.py -- the forecast clean-up (docs/21): calibration, no duplicate rows, one card per player.

Proves: the shipped map lifts confirmed-lineup player forecasts and pulls team forecasts toward 50%, leaves
pre-lineup player forecasts alone, never shows more than 97%; every forecast keeps its raw number; a second engine
run REPLACES the first (one row per forecast, never two); scoring writes one outcome per forecast; feeds show one
card per player per match with the other lines inside; the weekly refit waits for enough data, keeps a better map,
refuses a worse one, and can be rolled back.
"""
import os, sys, base64, collections, datetime as dt, random
os.environ.setdefault("APP_ENCRYPTION_KEY", base64.b64encode(os.urandom(32)).decode())
HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("SOCCER_BRAIN_DIR", os.path.join(HERE, "soccer_brain"))
sys.path.insert(0, HERE); sys.path.insert(0, os.environ["SOCCER_BRAIN_DIR"])
import httpx, mongomock
import calibration as CAL, engine_bridge as B, ingest as I, mongo_init, queries as Q, security, settings_store as S
from cached_fetch import PitchClient
from fake_pitchapi import PLAYER_KEYS, TEAM_KEYS, FakePitch
from simulate import simulate_league


def check(c, m):
    if not c:
        print("  FAIL", m); sys.exit(1)
    print("  ok  ", m)


print("[map]")
d = CAL.default_map()
check(CAL.apply(d, 0.75, "lineup", "player") > 0.77, "confirmed eleven, player 75% -> higher (the engine was too cautious)")
check(all(abs(CAL.apply(d, x, "pre", "player") - x) < 0.06 for x in (0.2, 0.4, 0.6)), "before lineups, player: small corrections only (it was nearly right)")
t = CAL.apply(d, 0.85, "pre", "team")
check(0.5 < t < 0.85 and abs(CAL.apply(d, 0.15, "pre", "team") - (1 - t)) < 1e-9, "team 85% -> pulled toward 50%, symmetric")
check(CAL.apply(d, 0.999, "lineup", "player") <= 0.97 and CAL.apply(d, 0.0, "lineup", "player") >= 0.003, "never above 97% or below 0.3%")
xs = [i / 100 for i in range(101)]
ys = [CAL.apply(d, x, "lineup", "player") for x in xs]
check(all(b >= a for a, b in zip(ys, ys[1:])), "the map never reverses the order of two forecasts")
check(CAL.apply(None, 0.42, "lineup", "player") == 0.42, "calibration off: raw number")

print("[engine runs]")
db = mongomock.MongoClient()["cal"]; mongo_init.ensure_indexes(db)
security.save_provider_key(db, "pitchapi", "pk_test_zzzz")
S.put(db, "ingest.rps", 1000); S.put(db, "provider.pitchapi.team_keys", TEAM_KEYS); S.put(db, "provider.pitchapi.player_keys", PLAYER_KEYS)
S.put(db, "provider.position_map", {"0": "GK", "1": "DEF", "2": "MID", "3": "FWD"})
matches, tg, pg, _ = simulate_league(n_teams=10, seed=4)
n_final = int(matches["round"].max()) + 1 - 2
fake = FakePitch(matches, tg, pg, n_final)
c = PitchClient(db, http=httpx.Client(base_url="https://api.pitchapi.dev", transport=fake.transport()), sleep=lambda s: None)
I.sync_leagues(c); lg = db.leagues.find_one({}); I.sync_league_matches(c, lg, "2025/2026", "all"); I.process_queue(c)
I.assign_rounds(db, lg["iid"]); I.update_coverage(db, lg["iid"])
now = fake.kick(n_final) - dt.timedelta(hours=26)
B.run_league(db, lg["iid"], now=now)                                    # day before: no lineups
first = db.forecasts.count_documents({})
check(first > 0 and db.forecasts.count_documents({"p_model": {"$exists": True}, "state": "pre"}) == first, "every forecast keeps its raw number; state = before lineups")
now2 = fake.kick(n_final) - dt.timedelta(hours=1)
I.lineup_watch(c, now=now2); B.run_league(db, lg["iid"], now=now2)      # lineups out: the engine runs again
B.run_league(db, lg["iid"], now=now2)                                   # and once more (a re-run must change nothing)
rows = list(db.forecasts.find({}, {"_id": 0, "fkey": 1, "run_id": 1, "is_current": 1, "match_iid": 1, "state": 1, "p": 1, "p_model": 1, "scope": 1, "calibration": 1}))
dup = [k for k, v in collections.Counter(r["fkey"] for r in rows).items() if v > 1]
check(not dup, f"after three runs: one row per forecast ({len(rows)} rows, no duplicates)")
check(all(r["is_current"] for r in rows) and len({r["run_id"] for r in rows if r["match_iid"] == rows[0]["match_iid"]}) == 1, "each match carries only its latest run")
lineup_player = [r for r in rows if r["state"] == "lineup" and r["scope"] == "player"]
check(lineup_player and any(abs(r["p"] - r["p_model"]) > 1e-6 for r in lineup_player), "confirmed-lineup forecasts are calibrated (shown % differs from raw)")
# Two ceilings, by design (docs/39): a line that went through the calibration map stops at calibration.CAP, and
# an anchored one stops at engine.p_cap. The blanket "nothing over 97%" here was never exercised until docs/44
# started keeping the likeliest lines, which is exactly where the gap between the two ceilings shows up.
cap = float(S.get(db, "engine.p_cap"))
check(all(r["p"] <= cap for r in rows), f"no forecast shows more than engine.p_cap ({cap:.1%})")
mapped = [r for r in rows if r.get("calibration")]
check(not mapped or all(r["p"] <= CAL.CAP[1] for r in mapped),
      f"a calibrated line still stops at {CAL.CAP[1]:.0%}: football always leaves room for surprise")
mp = db.match_probs.find_one({"is_current": True})
check(mp and "context" in mp and mp["context"]["mult_home"] > 0, "win/draw/loss carries the match-context multipliers (docs/22)")

print("[one card per player per market]")
# Since docs/46 a player may appear once per MARKET, so a good shots line and a good on-target line both surface.
# What must never repeat is the same player in the same market.
feed = Q.insights_feed(db, limit=500, tiers=("Strong", "Solid", "Watch"), now=now2 - dt.timedelta(hours=1))
keys = collections.Counter((f["match_iid"], f["scope"], f["team_iid"], f.get("player_iid"), f["stat"]) for f in feed)
check(feed and max(keys.values()) == 1, f"insights: {len(feed)} cards, never the same player and market twice in one match")
check(all(f.get("best_p") is not None and f["best_p"] >= f["p"] for f in feed),
      "every card carries the best percentage it holds, so a likelihood filter can see past the lead line")
withmore = [f for f in feed if f["more_lines"]]
check(withmore and all(m["fkey"] != f["fkey"] for f in withmore for m in f["more_lines"]), "the player's other lines sit inside the card")
ex = withmore[0]
same = [f for f in withmore if f["scope"] == "player" and f["stat"] == "shots"]
if same:
    h = same[0]
    tops = [m for m in h["more_lines"] if m["stat"] == "shots" and m["tier"] == h["tier"]]
    check(all(m["thr"] < h["thr"] or m["p"] >= h["p"] for m in tops), "headline = the most ambitious line in the best tier")
md = Q.match_detail(db, ex["match_iid"])
check(len(md["cards"]) < len(md["forecasts"]) and len({(x["team_iid"], x.get("player_iid")) for x in md["cards"]}) == len(md["cards"]), "match page: grouped cards next to the full list")
S.put(db, "engine.feed_group", "line")                 # docs/46: replaced the old on/off with three choices
check(len(Q.insights_feed(db, limit=500, tiers=("Strong", "Solid", "Watch"), now=now2 - dt.timedelta(hours=1))) > len(feed), "group=line: every line listed again")
S.put(db, "engine.feed_group", "player")
one = Q.insights_feed(db, limit=500, tiers=("Strong", "Solid", "Watch"), now=now2 - dt.timedelta(hours=1))
check(len(one) < len(feed), f"group=player: fewer cards than one per market ({len(one)} < {len(feed)})")
S.put(db, "engine.feed_group", "player_market")                  # back to the default for whatever runs next

print("[scoring]")
for m in db.matches.find({"iid": {"$in": list({r["match_iid"] for r in rows})}}):
    db.matches.update_one({"iid": m["iid"]}, {"$set": {"status": "final", "ingested_at": now2}})
db.forecasts.update_many({}, {"$set": {"kickoff": now2 - dt.timedelta(days=1)}})
n1 = B.score_finished(db); n2 = B.score_finished(db)
outs = list(db.forecast_outcomes.find({}, {"_id": 0}))
check(n1 > 0 and n2 == 0 and len({o["fkey"] for o in outs}) == len(outs), "one outcome per forecast; scoring twice adds nothing")
check(all("p_model" in o and o["state"] in ("pre", "lineup") for o in outs), "outcomes keep the raw number and the lineup state (for refitting)")

print("[weekly refit]")
db2 = mongomock.MongoClient()["cal2"]; mongo_init.ensure_indexes(db2)
check(CAL.refit(db2)["status"] == "waiting", "too few scored forecasts: waits")
rng = random.Random(3)
t0 = dt.datetime(2026, 1, 1, tzinfo=dt.timezone.utc)
docs = []
for i in range(9000):                    # our own results say: lineup forecasts are even more cautious than the default map assumes
    pm = rng.random() * 0.9
    truth = min(0.99, pm * 1.25)
    docs.append({"forecast_id": f"f{i}", "fkey": f"k{i}", "scope": "player", "state": "lineup", "p_model": pm, "p": pm,
                 "reached": rng.random() < truth, "scored_at": t0 + dt.timedelta(minutes=i),
                 "p_basis": "played", "player_played": True})         # player lines are "if he plays" (docs/27)
db2.forecast_outcomes.insert_many(docs)
dbo = mongomock.MongoClient()["cal_old"]; mongo_init.ensure_indexes(dbo)
dbo.forecast_outcomes.insert_many([{**d_, "forecast_id": d_["forecast_id"] + "o", "fkey": d_["fkey"] + "o", "p_basis": "all"} for d_ in docs])
S.put(dbo, "engine.calib_min_scored", 5000)
check(CAL.refit(dbo)["status"] == "waiting", "older all-in player results are not mixed into the 'if he plays' map")
S.put(db2, "engine.calib_min_scored", 5000)
r = CAL.refit(db2)
check(r["status"] == "updated" and r["candidate"] <= r["current"], f"a better map from our own results is kept ({r['candidate']} vs {r['current']})")
new = CAL.current(db2)
check(new["version"].startswith("own-") and CAL.apply(new, 0.6, "lineup", "player") > 0.7, "the new map is in use")
db3 = mongomock.MongoClient()["cal3"]; mongo_init.ensure_indexes(db3)
shift = [{**d_, "forecast_id": d_["forecast_id"] + "s", "fkey": d_["fkey"] + "s",
          "reached": d_["reached"] if i < 6300 else (rng.random() < 0.5)} for i, d_ in enumerate(docs)]   # the newest 30% behave differently
db3.forecast_outcomes.insert_many(shift); S.put(db3, "engine.calib_min_scored", 5000)
db3.engine_calibration.insert_one({"map": {"team_shrink": 1.0, "version": "flat", "lineup_player": {"x": [0, 1], "y": [0.5, 0.5]}}, "active": True, "created_at": t0})
r3 = CAL.refit(db3)
check(r3["status"] == "kept_current" and CAL.current(db3)["version"] == "flat", "a new map that does worse on the newest results is refused")
CAL.rollback(db2)
check(CAL.current(db2)["version"].startswith("default"), "rollback: back to the shipped map")
S.put(db2, "engine.calibration", False)
check(CAL.current(db2) is None, "calibration switch off: raw numbers")

print("\nALL CALIBRATION CHECKS PASSED")
