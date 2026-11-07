"""selftest_personal_lines.py -- a line for each player and team (docs/52).

    pip install mongomock httpx pymongo numpy scipy pandas cryptography
    SOCCER_BRAIN_DIR=../soccer_brain python selftest_personal_lines.py

Proves the three properties the method rests on, then that the feed uses it:

  1. the chosen line is the entity's OWN half-way count, so it moves with the entity;
  2. it is read off the fitted distribution, not an empirical median, so a small integer count and a
     short history do not break it;
  3. with it on, the shown likelihood stops hugging the top of the band -- which is the whole point;
  and the player and team filters narrow the feed.
"""
from __future__ import annotations

import base64
import os
import sys

os.environ.setdefault("APP_ENCRYPTION_KEY", base64.b64encode(os.urandom(32)).decode())
HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("SOCCER_BRAIN_DIR", os.path.join(HERE, "soccer_brain"))
sys.path.insert(0, HERE); sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.environ["SOCCER_BRAIN_DIR"])

import datetime as dt
import statistics as st

import httpx
import mongomock

import engine_bridge as B
import ingest as I
import mongo_init
import queries as Q
import security
import settings_store as S
from cached_fetch import PitchClient
from core import nb_sf
from engine import personal_k, personal_thrs
from fake_pitchapi import PLAYER_KEYS, TEAM_KEYS, FakePitch
from simulate import simulate_league

ok = lambda m: print("  ok  ", m)


def check(c, m):
    if not c:
        print("  FAIL", m); sys.exit(1)
    ok(m)


# ---------------------------------------------------------------- 1. the chooser itself
def test_chooser():
    # the line follows the entity, which is the whole idea
    seen = {}
    for mu in (0.4, 0.9, 2.1, 3.4, 5.3, 13.8):
        k = personal_k(lambda kk: nb_sf(kk, mu, 4.0))
        seen[mu] = k
        p = float(nb_sf(k, mu, 4.0))
        check(0.30 <= p <= 0.70, f"a mean of {mu} picks {k - 0.5:g}+ and lands at {p:.2f}, inside 30-70%")
    check(list(seen.values()) == sorted(seen.values()), "a bigger usual count always gives a line at least as high")
    check(len(set(seen.values())) >= 4, f"six different entities get four or more different lines {sorted(set(seen.values()))}")

    # it is read off the distribution, so a count of 2 does not have to mean "2+"
    mu = 2.1
    k = personal_k(lambda kk: nb_sf(kk, mu, 4.0))
    p_at, p_above = float(nb_sf(k, mu, 4.0)), float(nb_sf(k + 1, mu, 4.0))
    check(abs(p_at - 0.5) <= abs(p_above - 0.5),
          f"of the two rungs either side of a half it takes the nearer one ({p_at:.2f} over {p_above:.2f})")

    # a very quiet entity cannot be pushed below the lowest real line
    k = personal_k(lambda kk: nb_sf(kk, 0.05, 4.0))
    check(k >= 1, "an entity that almost never records the stat still gets a line of 0.5+, never lower")

    # the neighbours exist for the Finder, and never go below 0.5
    check(personal_thrs(1) == [0.5, 1.5], f"the lowest line keeps only the rungs that exist {personal_thrs(1)}")
    check(personal_thrs(5) == [3.5, 4.5, 5.5], f"a middling line keeps one either side {personal_thrs(5)}")


# ---------------------------------------------------------------- the league, run both ways
def build(personal: bool):
    db = mongomock.MongoClient()["pl"]; mongo_init.ensure_indexes(db)
    security.save_provider_key(db, "pitchapi", "pk_demo_zzzz")
    S.put(db, "ingest.rps", 1000)
    S.put(db, "provider.pitchapi.team_keys", TEAM_KEYS); S.put(db, "provider.pitchapi.player_keys", PLAYER_KEYS)
    S.put(db, "provider.position_map", {"0": "GK", "1": "DEF", "2": "MID", "3": "FWD"})
    S.put(db, "engine.personal_lines", personal)
    matches, tg, pg, _ = simulate_league(n_teams=12, seed=7)
    n_final = int(matches["round"].max()) + 1 - 2
    fake = FakePitch(matches, tg, pg, n_final)
    pc = PitchClient(db, http=httpx.Client(base_url="https://api.pitchapi.dev", transport=fake.transport()), sleep=lambda s: None)
    I.sync_leagues(pc); lg = db.leagues.find_one({})
    db.leagues.update_one({"iid": lg["iid"]}, {"$set": {"enabled": True, "country": "Demo"}})
    I.sync_league_matches(pc, lg, "2025/2026", "all"); I.process_queue(pc)
    I.assign_rounds(db, lg["iid"]); I.update_coverage(db, lg["iid"])
    now = fake.kick(n_final) - dt.timedelta(hours=2)
    I.lineup_watch(pc, now=now); B.run_league(db, lg["iid"], now=now)
    return db, now


def main():
    test_chooser()

    db_off, _ = build(False)
    db_on, now = build(True)
    # Carriers are excluded: they are rows that exist only to hold a ladder for the Finder and are
    # never shown to anyone, so counting them here would measure a distribution no reader sees.
    q = {"is_current": True, "carrier": {"$ne": True}}
    off = [f["p"] for f in db_off.forecasts.find(q, {"_id": 0, "p": 1})]
    on = [f["p"] for f in db_on.forecasts.find(q, {"_id": 0, "p": 1})]
    hi_off, hi_on = sum(p >= .85 for p in off) / len(off), sum(p >= .85 for p in on) / len(on)
    check(st.median(on) < st.median(off),
          f"the shown likelihood stops hugging the top: median {st.median(off):.2f} -> {st.median(on):.2f}")
    check(hi_on < hi_off / 2,
          f"near-certain lines more than halve: {hi_off:.0%} -> {hi_on:.0%} of lines at 85% or more")

    rows = list(db_on.forecasts.find({"is_current": True}, {"_id": 0}))
    per = [r for r in rows if r.get("is_personal")]
    check(per, "the entity's own rung is marked on the record")
    check(all(r.get("thr_personal") is not None for r in per), "every personal rung carries the line it was chosen at")
    own = [r for r in rows if r["stat"] != "match_goals"]      # a match total belongs to the fixture, not an entity
    check(own and all(r.get("expected_usual") is not None for r in own),
          "every line of an entity's own stat carries the count it manages in its usual game")
    check(all(r.get("expected_usual") is None and r.get("is_personal") is False
              for r in rows if r["stat"] == "match_goals"),
          "and a match total says so by carrying neither, rather than by missing the keys")

    # one line per entity+stat, and it is the personal one
    import collections
    g = collections.defaultdict(list)
    for r in rows:
        g[(r["scope"], r["team_iid"], r.get("player_iid"), r["stat"])].append(r)
    lead = [sorted(v, key=lambda d: (not d.get("is_personal")))[0] for v in g.values()]
    share = sum(1 for r in lead if r.get("is_personal")) / len(lead)
    check(share > 0.95, f"the entity's own rung leads {share:.0%} of groups")

    # teams stop being asked questions with obvious answers
    tsh = [r for r in lead if r["scope"] == "team" and r["stat"] == "shots"]
    if tsh:
        check(st.median(r["thr"] for r in tsh) >= 9,
              f"team shot lines move up the ladder (median line {st.median(r['thr'] for r in tsh):g}+)")
        check(all(r["expected_usual"] > r["thr"] - 3 for r in tsh),
              "and each one sits near what that team actually manages, not at the bottom of the ladder")

    # ---- the filters
    feed = Q.insights_feed(db_on, limit=200, tiers=("Strong", "Solid", "Watch"), now=now)
    check(feed, f"the feed returns cards ({len(feed)})")
    pid = next((f["player_iid"] for f in feed if f.get("player_iid")), None)
    if pid:
        one = Q.insights_feed(db_on, limit=200, tiers=("Strong", "Solid", "Watch"), now=now, player_iids=[pid])
        check(one and all(f["player_iid"] == pid for f in one), f"a player filter returns only that player ({len(one)})")
        check(len(one) < len(feed), "and it is narrower than the whole feed")
    tid = feed[0]["team_iid"]
    one = Q.insights_feed(db_on, limit=200, tiers=("Strong", "Solid", "Watch"), now=now, team_iids=[tid])
    check(one and all(f["team_iid"] == tid for f in one), f"a club filter returns only that club ({len(one)})")
    check(Q.insights_feed(db_on, limit=200, tiers=("Strong", "Solid", "Watch"), now=now, player_iids=[-1]) == [],
          "an unknown player returns nothing rather than everything")

    print("\nALL PERSONAL LINE CHECKS PASSED")


if __name__ == "__main__":
    main()
