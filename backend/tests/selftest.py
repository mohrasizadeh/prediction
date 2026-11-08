"""selftest.py -- end-to-end check on an in-memory Mongo and a fake PitchAPI.

    pip install mongomock httpx pymongo numpy scipy pandas cryptography
    SOCCER_BRAIN_DIR=../engine python selftest.py

Proves: caching (second run = 0 calls), budget stop, 429 retry, idempotent upserts,
no zeros for missing data, forecasts written, no forbidden words in stored text.
"""
from __future__ import annotations

import base64
import os
import sys
import time

os.environ.setdefault("APP_ENCRYPTION_KEY", base64.b64encode(os.urandom(32)).decode())
HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("SOCCER_BRAIN_DIR", os.path.join(HERE, "soccer_brain"))
sys.path.insert(0, HERE); sys.path.insert(0, os.environ["SOCCER_BRAIN_DIR"])

import httpx
import mongomock
import numpy as np

import engine_bridge as B
import ingest as I
import mongo_init
import normalize as N
import security
import settings_store as S
from cached_fetch import BudgetExhausted, PitchClient, cache_key
from fake_pitchapi import PLAYER_KEYS, TEAM_KEYS, FakePitch
from simulate import simulate_league

ok = lambda m: print("  ok  ", m)


def check(cond, msg):
    if not cond:
        print("  FAIL", msg); sys.exit(1)
    ok(msg)


def main():
    t0 = time.time()
    db = mongomock.MongoClient()["selftest"]
    mongo_init.ensure_indexes(db)
    ok("indexes created")

    # --- security
    security.save_provider_key(db, "pitchapi", "pk_test_abcdef123456")
    check(security.get_provider_key(db, "pitchapi") == "pk_test_abcdef123456", "key round-trips through AES-GCM")
    check("pk_test" not in str(db.provider_keys.find_one()), "key is not stored in clear text")
    check(security.public_key_view(db, "pitchapi")["masked"] == "•••• 3456", "masked view shows last 4 only")

    # --- settings
    check(S.get(db, "ingest.rps") == 3, "default setting read")
    S.put(db, "ingest.rps", 1000, actor="test")                  # no sleeping in the test
    check(S.get(db, "ingest.rps") == 1000 and db.settings_history.count_documents({}) == 1, "setting override + history")
    try:
        S.put(db, "engine.lineup_effects", True); check(False, "locked setting must refuse")
    except ValueError:
        ok("locked setting refuses True")
    S.put(db, "provider.pitchapi.team_keys", TEAM_KEYS, "test")
    S.put(db, "provider.pitchapi.player_keys", PLAYER_KEYS, "test")
    S.put(db, "provider.position_map", {"0": "GK", "1": "DEF", "2": "MID", "3": "FWD"}, "test")
    S.put(db, "cache.ttl.lineups_far_hours", 6, "test")

    # --- fake league: 12 teams, last 2 rounds upcoming
    matches, tg, pg, _ = simulate_league(n_teams=12, seed=3)
    n_rounds = int(matches["round"].max()) + 1
    n_final = n_rounds - 2
    fake = FakePitch(matches, tg, pg, n_final)
    client = PitchClient(db, http=httpx.Client(base_url="https://api.pitchapi.dev", transport=fake.transport()), sleep=lambda s: None)

    check(I.sync_leagues(client) == 1, "leagues synced")
    lg = db.leagues.find_one({}); check(lg["enabled"] is False, "new league starts OFF")
    db.leagues.update_one({"iid": lg["iid"]}, {"$set": {"enabled": True}}); lg = db.leagues.find_one({})
    check(lg["current_season"] == "2025/2026", "current season picked")

    n = I.sync_league_matches(client, lg, "2025/2026", "all")
    check(n == len(matches), f"{n} matches upserted")
    check(db.ingest_queue.count_documents({"task": "match_ingest"}) == int((matches['round'] < n_final).sum()), "one queue task per finished match")
    calls_list = client.calls_made
    I.sync_league_matches(client, lg, "2025/2026", "all")
    check(client.calls_made == calls_list, "second list call is served from cache (0 calls)")

    # --- budget: stop after 20 calls
    S.put(db, "ingest.daily_call_budget", db.api_call_log.count_documents({}) + 20, "test")
    res = I.process_queue(client)
    check(res["stopped_by"] == "BudgetExhausted", "queue stops when the daily budget is spent")
    check(db.matches.count_documents({"ingested_at": {"$ne": None}}) == 6, "6 matches (18 calls) ingested before the stop")
    S.put(db, "ingest.daily_call_budget", 100000, "test")
    # --- 429 then success
    fake.fail_next = [429, 429]
    res = I.process_queue(client)
    check(res["done"] > 0 and res["stopped_by"] is None, "queue finishes after retrying through two 429s")
    check(db.matches.count_documents({"status": "final", "ingested_at": None}) == 0, "every finished match ingested")
    before = len(fake.log)
    I.process_queue(client); I.sync_league_matches(client, lg, "2025/2026", "all")
    check(len(fake.log) == before, "second pass makes ZERO new API calls")

    # --- data quality
    check(db.team_match_stats.count_documents({}) == 2 * n_final * 6, "two team rows per finished match")
    check(db.player_match_stats.count_documents({"pos": "GK"}) == 0 or db.player_match_stats.count_documents({"pos": "GK", "tackles": {"$ne": None}}) == 0, "goalkeeper tackles are null, not zero")
    check(db.player_match_stats.count_documents({"minutes": 0}) == 0, "players who did not feature are absent, not stored as zero")
    cov = I.update_coverage(db, lg["iid"])
    check(cov["team_match_stats.corners"] == 1.0 and cov["player_match_stats.tackles"] > 0.7, "coverage computed")
    # A 0 tackle count is OMITTED by the provider, the way goals and assists are, so a forward who
    # made no tackle used to be stored with `tackles: null`. `tackles` is in PLAYER_REQUIRED, so
    # `build_frames`' dropna deleted that whole appearance -- and the engine counts a missing
    # appearance as a match the player MISSED, which collapses his chance to play and drops every
    # card he has. It cost the product its forwards, because a forward is who records no tackle.
    # The old assertion above tolerated 30% of rows being null without asking what the nulls did.
    out = db.player_match_stats.count_documents({"pos": {"$ne": "GK"}, "minutes": {"$gt": 0}})
    nul = db.player_match_stats.count_documents({"pos": {"$ne": "GK"}, "minutes": {"$gt": 0}, "tackles": None})
    check(nul == 0, f"an outfield appearance always carries a tackle count, 0 included ({nul} of {out} null)")
    check(db.player_match_stats.count_documents({"tackles": 0}) > 0, "...and 0 is stored as 0, so the case is actually exercised")
    # The engine builds a player's rate as his SHARE OF A TEAM TOTAL, so a market can only exist
    # for a stat whose team total is on the player row. shots, on target and tackles have had one
    # since the start; goals never did, and it is the market the product wants next.
    _pg = db.player_match_stats.count_documents({"minutes": {"$gt": 0}})
    _ng = db.player_match_stats.count_documents({"minutes": {"$gt": 0}, "team_goals": None})
    check(_ng == 0, f"every player row carries his club's goals for that match ({_ng} of {_pg} missing)")
    _one = db.player_match_stats.find_one({"minutes": {"$gt": 0}})
    _tm = db.team_match_stats.find_one({"match_iid": _one["match_iid"], "team_iid": _one["team_iid"]})
    check(_one["team_goals"] == _tm["goals"], "...and it is the club's own score, not the opponent's")
    # The backfill is idempotent and refuses when there is nothing to do.
    _bf = I.fill_team_goals(db, dry_run=True)
    check(_bf["ok"] is False and "already" in _bf["reason"], "the team-goals backfill has nothing to do on fresh data")
    check(db.team_match_stats.find_one({"poss": {"$lt": 0}}) is None, "no negative values")
    check(I.assign_rounds(db, lg["iid"]) == n_rounds, "rounds = distinct kickoff dates")

    # --- goalkeeper rule: no defence group => tackles None
    gk = {"player": {"id": "p_x", "name": "GK", "position_id": 0}, "team_id": "t_x",
          "stats": [{"key": "top_stats", "stats": {"M": {"key": "minutes_played_fake", "stat": {"type": "integer", "value": 90}},
                                                   "S": {"key": "total_shots", "stat": {"type": "integer", "value": 0}}}}]}
    rows = N.players([gk], PLAYER_KEYS, {"0": "GK"})
    check(rows[0]["pos"] == "GK" and rows[0]["tackles"] is None and rows[0]["minutes"] == 90, "goalkeeper: tackles None, minutes read")
    try:
        N.normalize_match({"home_ext": "a", "away_ext": "b"}, {"periods": []}, [], {"home": {}, "away": {}},
                          {"team_keys": TEAM_KEYS, "player_keys": PLAYER_KEYS, "position_map": {}}); check(False, "must raise")
    except N.MissingField:
        ok("a required gap raises MissingField (match skipped, nothing written as zero)")

    # --- unverified key => null + market off
    k = dict(TEAM_KEYS); k["corners"] = None
    raw = fake._stats(next(fake.m.itertuples()))
    t = N.team_stats(raw, k)
    check(t["home"]["corners"] is None and t["home"]["shots"] is not None, "unmapped key stays None (never zero)")
    check(N.parse_team_value("329 (82%)") == 329.0 and N.parse_team_value("") is None and N.parse_team_value(None) is None, "team value parser")

    # --- lineup watch for upcoming matches
    now = fake.kick(n_final) - __import__("datetime").timedelta(hours=2)
    nlog = len(fake.log)
    I.lineup_watch(client, now=now)
    check(len(fake.log) > nlog, "lineup watch made calls for upcoming matches")
    check(db.matches.count_documents({"status": "scheduled", "lineups_confirmed": True}) == 6, "both-confirmed lineups flip the flag")
    nlog = len(fake.log); I.lineup_watch(client, now=now)
    check(len(fake.log) == nlog, "lineup watch twice in a row: second pass is served from cache (0 calls)")

    # --- engine
    from datetime import datetime, timezone
    t1 = time.time()
    out = B.run_league(db, lg["iid"], now=fake.kick(n_final) - __import__("datetime").timedelta(hours=2))
    check(out["status"] == "done" and out["forecasts"] > 100, f"engine run produced {out['forecasts']} forecasts in {time.time() - t1:.0f}s")
    f = db.forecasts.find_one({"scope": "player", "is_current": True, "tier": {"$ne": None}}) or db.forecasts.find_one({"scope": "player"})
    check(f and 0 < f["p"] < 1 and f["lo"] <= f["p"] <= f["hi"], "probabilities and bands are sane")
    check(db.forecasts.count_documents({"is_current": True}) == db.forecasts.count_documents({"run_id": out["run_id"]}), "only the latest run is current")
    check(db.match_probs.count_documents({"is_current": True}) == 6, "win/draw/loss stored for each upcoming match")
    check(db.team_styles.count_documents({}) == 12, "team style rows stored")
    check(db.match_context.count_documents({}) == 12, "rotation level stored for both clubs of each upcoming match")
    g = db.engine_gates.find_one({"layer": "start_model"})
    check(g and g["applied"] is False and g["reason"], "start-model gate recorded, and closed on thin data")
    f0 = db.forecasts.find_one({"scope": "team", "is_current": True})
    check(f0 and f0["rotation"] in ("low", "medium", "high"), "forecasts carry a rotation level")
    out2 = B.run_league(db, lg["iid"], now=fake.kick(n_final) - __import__("datetime").timedelta(hours=2))
    check(db.forecasts.count_documents({"is_current": True}) == out2["forecasts"], "a re-run replaces current forecasts, never doubles them")

    # --- scoring: store what happened next to the forecast
    f = db.forecasts.find_one({"scope": "player", "is_current": True, "stat": "shots", "thr": 0.5})
    db.matches.update_one({"iid": f["match_iid"]}, {"$set": {"status": "final", "ingested_at": f["created_at"]}})
    db.forecasts.update_one({"id": f["id"]}, {"$set": {"kickoff": f["created_at"] - __import__("datetime").timedelta(days=1)}})
    db.player_match_stats.insert_one({"match_iid": f["match_iid"], "player_iid": f["player_iid"], "shots": 2.0})
    check(B.score_finished(db) >= 1, "finished forecasts are scored")
    oc = db.forecast_outcomes.find_one({"forecast_id": f["id"]})
    check(oc and oc["reached"] is True and oc["actual"] == 2.0, "outcome stored: 2 shots reached 1+")

    # --- forbidden words in anything we stored for display
    import re
    bad = re.compile(r"\b(bet|bets|betting|bettor|bookie|bookmaker|sportsbook|odds|wager|parlay|accumulator|stake|punt|tipster|lock|banker|units|hit rate|picks|props)\b", re.I)
    texts = []
    for f in db.forecasts.find({}, {"reasons": 1, "market": 1}): texts += f["reasons"] + [f["market"]]
    for r in S.registry().values():
        if r["public"] and isinstance(r["default"], (str, dict, list)) and r["key"] != "copy.disclaimer":
            texts.append(str(r["default"]))
    hits = [t for t in texts if bad.search(t)]
    check(not hits, "no forbidden words in stored or public text")
    print(f"\nALL CHECKS PASSED in {time.time() - t0:.0f}s")


if __name__ == "__main__":
    main()
