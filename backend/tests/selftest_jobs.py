import os, sys, base64, datetime as dt
os.environ.setdefault("APP_ENCRYPTION_KEY", base64.b64encode(os.urandom(32)).decode())
HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("SOCCER_BRAIN_DIR", os.path.join(HERE, "soccer_brain"))
sys.path.insert(0, HERE); sys.path.insert(0, os.environ["SOCCER_BRAIN_DIR"])
import httpx, mongomock
import jobs, mongo_init, security, settings_store as S
from cached_fetch import PitchClient
from fake_pitchapi import PLAYER_KEYS, TEAM_KEYS, FakePitch
from simulate import simulate_league
ok = lambda m: print("  ok  ", m)
def check(c, m):
    if not c: print("  FAIL", m); sys.exit(1)
    ok(m)
db = mongomock.MongoClient()["j"]; mongo_init.ensure_indexes(db)
security.save_provider_key(db, "pitchapi", "pk_test_zzzz")
# `provider.source` SAID EXPLICITLY, because this file tests the PitchAPI path and the default is
# API-Football now. It used to be pitchapi, so this fixture got the path it wanted by accident; when
# the default moved, every step it asserts was skipped and the failure read "reference sync ran,
# league found" with no mention of a provider. A test of one provider should name it.
for k, v in {"ingest.rps": 1000, "provider.source": "pitchapi",
             "provider.pitchapi.team_keys": TEAM_KEYS, "provider.pitchapi.player_keys": PLAYER_KEYS,
             "provider.position_map": {"0": "GK", "1": "DEF", "2": "MID", "3": "FWD"}}.items(): S.put(db, k, v)
matches, tg, pg, _ = simulate_league(n_teams=12, seed=3)
n_final = int(matches["round"].max()) + 1 - 2
fake = FakePitch(matches, tg, pg, n_final)
c = PitchClient(db, http=httpx.Client(base_url="https://api.pitchapi.dev", transport=fake.transport()), sleep=lambda s: None)

NOW = fake.kick(n_final) - dt.timedelta(hours=2)   # pretend it is two hours before the next round
r = jobs.tick(db, c, now=NOW); check("reference_sync" in r["ran"], "tick 1: reference sync ran, league found")
check(db.matches.count_documents({}) == 0, "tick 1: nothing ingested while no league is enabled")
db.leagues.update_one({}, {"$set": {"enabled": True, "backfill_seasons": []}})
r = jobs.tick(db, c, now=NOW); check("fixtures_sync" in r["ran"] or "results_sync" in r["ran"], "tick 2: fixtures sync ran for the enabled league")
for _ in range(3): jobs.tick(db, c, now=NOW)     # queue drains
check(db.matches.count_documents({"status": "final", "ingested_at": None}) == 0, "queue drained over ticks")
check(db.engine_runs.count_documents({"status": "done"}) >= 1 and db.forecasts.count_documents({}) > 0, "engine ran by itself and wrote forecasts")
runs_before = db.engine_runs.count_documents({})
n = len(fake.log); r = jobs.tick(db, c, now=NOW)
check(db.engine_runs.count_documents({}) == runs_before, "idle tick does not re-run the engine")
check(len(fake.log) - n <= 6 and "reference_sync" not in r["ran"], "idle tick makes almost no calls")
db.job_locks.insert_one({"_id": "tick", "at": dt.datetime.now(dt.timezone.utc), "expires_at": dt.datetime.now(dt.timezone.utc) + dt.timedelta(minutes=5)})
check(jobs.tick(db, c, now=NOW)["skipped"] == "another tick is running", "a held lock blocks a second tick")
db.job_locks.delete_one({"_id": "tick"})
db.job_requests.insert_one({"job": "engine", "status": "pending", "requested_at": dt.datetime.now(dt.timezone.utc)})
check(any(x.startswith("engine") for x in jobs.tick(db, c, now=NOW)["ran"]), "admin 'Run now' request forces an engine run")
# --- the daily update: only NEW results are fetched; everything stored stays untouched
old_ids = {m["ext_id"] for m in db.matches.find({"ingested_at": {"$ne": None}}, {"ext_id": 1})}
old_rows = db.player_match_stats.count_documents({})
fake.n_final += 1                                    # one more round of results arrives (6 matches)
log0 = len(fake.log)
r = jobs.tick(db, c, now=NOW + dt.timedelta(hours=7))
new_paths = fake.log[log0:]
touched_old = [p for p in new_paths if any(i in p for i in old_ids) and "/lineups" not in p]
check("results_sync" in r["ran"], "7 hours later: results check runs (every ingest.results_sync_hours)")
check(touched_old == [], "no stored match is fetched again (zero calls for old results)")
check(sum(1 for p in new_paths if p.endswith("/stats")) == 6 and sum(1 for p in new_paths if p.endswith("/players")) == 6, "exactly the 6 new results were fetched: 6 stats + 6 players calls")
check(db.player_match_stats.count_documents({}) > old_rows and db.matches.count_documents({"status": "final", "ingested_at": None}) == 0, "new results stored; old rows kept")
cal = len(fake.log); jobs.tick(db, c, now=NOW + dt.timedelta(hours=7, minutes=10))
check(len(fake.log) == cal, "a tick 10 minutes later makes zero calls")
import datetime as _d
f0 = db.forecasts.find_one({})
db.forecasts.update_one({"id": f0["id"]}, {"$set": {"kickoff": _d.datetime(2020, 1, 1)}})
db.forecast_outcomes.update_one({"forecast_id": f0["id"]}, {"$set": {"forecast_id": f0["id"]}}, upsert=True)
import engine_bridge as _B
check(_B.cleanup(db, now=NOW)["forecasts_deleted"] == 1 and db.forecasts.count_documents({"id": f0["id"]}) == 0, "cleanup removes old scored forecasts only")
print("\nALL JOB CHECKS PASSED")
