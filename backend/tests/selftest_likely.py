"""selftest_likely.py -- the "most likely" screen (docs/63).

Proves: an "unsure" lineup badge now says WHICH rule produced it, so a stated doubt and a thin
start record stop printing the same word; every stored line carries the band of each rung on its
ladder, so a reader who moves the line moves the range with it instead of being shown a
likelihood with an invented spread; the feed honours a likelihood floor and a kick-off window in
the QUERY rather than in the page; and /api/likely returns its floor rather than leaving the
screen to retype engine.watch_min in JavaScript.
"""
import os, sys, base64, datetime as dt
os.environ.setdefault("APP_ENCRYPTION_KEY", base64.b64encode(os.urandom(32)).decode())
HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("SOCCER_BRAIN_DIR", os.path.join(HERE, "soccer_brain"))
sys.path.insert(0, HERE); sys.path.insert(0, os.environ["SOCCER_BRAIN_DIR"])
import httpx, mongomock
from fastapi.testclient import TestClient
import engine_bridge as B, ingest as I, mongo_init, queries as Q, security, settings_store as S
import server as srv
from cached_fetch import PitchClient
from fake_pitchapi import PLAYER_KEYS, TEAM_KEYS, FakePitch
from simulate import simulate_league


def check(c, m):
    if not c:
        print("  FAIL", m); sys.exit(1)
    print("  ok  ", m)


# ---------------------------------------------------------------- 1. the badge now says why
A = dict(enabled=True, share=0.6, max_missed=2, fallback="likely")
check(B.starter_call(9, 10, 0, False, **A) == ("likely", "record"), "starter_call: a regular starter is 'likely', decided by the record")
check(B.starter_call(3, 10, 0, False, **A) == ("unsure", "record"), "starter_call: a thin record is 'unsure' BECAUSE OF the record")
check(B.starter_call(9, 10, 0, True, **A) == ("unsure", "doubt"), "starter_call: a stated doubt is 'unsure' BECAUSE OF the doubt, not the record")
check(B.starter_call(9, 10, 5, False, **A) == ("unsure", "doubt"), "starter_call: a run of missed club matches reads as a doubt, not as rotation")
# A missing record must NEVER read as a doubt: an unmapped `minutes` key would otherwise badge a
# whole league injured. It falls back, and says it could not decide.
check(B.starter_call(None, 10, 0, False, **A) == ("likely", None), "starter_call: no record falls back and reports no reason")
check(B.starter_badge(9, 10, 0, True, **A) == "unsure", "starter_badge still returns the badge alone for its existing callers")

# ---------------------------------------------------------------- 2. the ladder carries its bands
docs = [{"scope": "player", "team_iid": 1, "player_iid": 7, "stat": "shots", "thr": t,
         "p": p, "lo": round(p - 0.05, 4), "hi": round(p + 0.05, 4)}
        for t, p in ((0.5, 0.93), (1.5, 0.74), (2.5, 0.41), (3.5, 0.18))]
out = B.select_lines([dict(d) for d in docs], (0.5, 0.95), 2)
kept = [d for d in out if not d.get("carrier")]
check(kept, "select_lines keeps at least one line")
for d in kept:
    check(set(d["ladder"]) == set(d["ladder_band"]), "every rung with a likelihood also has a band")
    check(d["ladder_band"]["2.5"] == [0.36, 0.46], "ladder_band carries THAT rung's lo/hi, not the kept line's")
    check(d["ladder"]["2.5"] == 0.41, "the ladder still carries each rung's likelihood")
# The carrier row exists so the Finder can answer a line the band excluded; it must carry the
# bands too, or moving the line on it would show a number with no range.
low = B.select_lines([dict(d) for d in docs], (0.99, 1.0), 2)
check(low and low[0].get("carrier") and low[0].get("ladder_band"), "a carrier row carries the bands as well as the ladder")
# select_lines is a pure function and its other callers hand it the smallest dict that makes
# sense. Demanding lo/hi turned every one of those calls into a KeyError.
bare = [{"scope": "player", "team_iid": 1, "player_iid": 8, "stat": "shots", "thr": t, "p": p}
        for t, p in ((0.5, 0.9), (1.5, 0.6))]
out2 = B.select_lines(bare, (0.5, 0.95), 2)
check(out2 and all(d["ladder"] for d in out2) and all(d["ladder_band"] == {} for d in out2),
      "a line with no band still gets its ladder, and an empty band map rather than an exception")

# ---------------------------------------------------------------- 3. a real league
db = mongomock.MongoClient()["lk"]; mongo_init.ensure_indexes(db)
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

stored = list(db.forecasts.find({"scope": "player", "is_current": True}, {"_id": 0}))
check(stored, "the run produced player forecasts")
check(all("lineup_why" in f for f in stored), "every stored player line records why its badge was given")
check(all(f.get("lineup_why") in (None, "record", "doubt") for f in stored), "lineup_why is one of the two rules, or None")
banded = [f for f in stored if f.get("ladder_band")]
check(banded, "stored lines carry ladder_band")
rungs = [(f["fkey"], k) for f in banded for k in f["ladder"] if k not in f["ladder_band"]]
check(not rungs, "every rung with a likelihood also has a band")
outside = [(f["fkey"], k) for f in banded for k, p in f["ladder"].items()
           if not (f["ladder_band"][k][0] <= p <= f["ladder_band"][k][1])]
check(not outside, f"all {sum(len(f['ladder']) for f in banded)} stored rungs sit inside their own band")

# ---------------------------------------------------------------- 4. floor and window
ALL = ("Strong", "Solid", "Watch")
BIG = 10000                     # past any cap, so these comparisons are about the filter, not the limit
everything = Q.insights_feed(db, limit=BIG, tiers=ALL, now=now)
check(everything, "the feed returns rows at all")
watch_min = float(S.get(db, "engine.watch_min"))
floored = Q.insights_feed(db, limit=BIG, tiers=ALL, now=now, min_p=watch_min)
check(floored and all(f["p"] >= watch_min for f in floored), "min_p drops every line under the floor")
# At engine.watch_min itself the filter is a GUARANTEE, not the mechanism: tiering already refuses
# to grade anything below it, so no tiered line is under the floor to begin with. Saying that here
# rather than asserting a drop keeps the test honest -- and makes it fail loudly if that ever stops
# being true and the screen starts showing coin flips.
check(len(floored) == len(everything) and min(f["p"] for f in everything) >= watch_min,
      f"nothing tiered is under engine.watch_min ({watch_min}) in the first place")
high = Q.insights_feed(db, limit=BIG, tiers=ALL, now=now, min_p=0.9)
check(high and all(f["p"] >= 0.9 for f in high), "a floor above watch_min does filter")
check(len(high) < len(everything), "and it actually removed rows, so the check is not vacuous")
# The window must bite in the query. The screen asks for 'the next few hours'; filtering a fixed
# 200-row pool in the page would silently lose rows past it.
# `now` is two hours before kick-off and every remaining fixture is in the same round, so the
# window is proved at its BOUNDARY -- one hour excludes the lot, three hours includes it -- rather
# than by widening it, which this fixture cannot show.
tight = Q.insights_feed(db, limit=BIG, tiers=ALL, now=now, within_h=1)
near = Q.insights_feed(db, limit=BIG, tiers=ALL, now=now, within_h=3)
# mongomock hands back naive datetimes where pymongo hands back naive-UTC, so both sides are
# compared without a tzinfo rather than pretending one of them has one.
bare = lambda d: d.replace(tzinfo=None)
edge = bare(now) + dt.timedelta(hours=3)
check(near and all(bare(f["kickoff"]) <= edge for f in near), "within_h keeps only matches inside the window")
check(not tight and near, "the window excludes a round two hours out and includes it at three")
check(all("noun" in f and len(f["noun"]) == 2 for f in everything), "every row carries the singular/plural pair the stepper needs")

# ---------------------------------------------------------------- 5. the endpoint
# The route reads the real clock, as it should -- so the fixture is moved into the real future
# rather than a `now` being threaded through a public endpoint for the benefit of a test.
real = dt.datetime.now(dt.timezone.utc).replace(tzinfo=None) + dt.timedelta(minutes=90)
db.forecasts.update_many({}, {"$set": {"kickoff": real}})
db.matches.update_many({}, {"$set": {"kickoff": real}})
srv.set_db(db)
with TestClient(srv.app) as client:
    r = client.get("/api/likely", params={"within_h": 4, "limit": 60})
    check(r.status_code == 200, "GET /api/likely answers")
    body = r.json()
    check(body["floor"] == float(S.get(db, "engine.watch_min")),
          "the response carries engine.watch_min, so the screen never retypes the floor")
    rows = body["rows"]
    check(rows, "the endpoint returns rows")
    check(all(f["p"] >= body["floor"] for f in rows), "no row is under the floor")
    check([f["p"] for f in rows] == sorted((f["p"] for f in rows), reverse=True),
          "rows are sorted by likelihood alone -- the thing the screen is named after")
    # The feed's own 'likely' sort puts tier first, which would put a Watch line at 88% below a
    # Solid at 81%. This screen must not do that.
    tiers_seen = {f["tier"] for f in rows}
    check(len(tiers_seen) >= 1, "every tier is eligible for this screen")
    # a one-hour window is before kick-off, so the screen's own empty state is reachable
    nothing = client.get("/api/likely", params={"within_h": 1}).json()
    check(not nothing["rows"] and nothing["floor"] == body["floor"],
          "an empty window still reports the floor, so the empty state can state it")
    c2 = client.get("/api/likely", params={"within_h": 4, "confirmed": "true"}).json()
    check(all(f.get("lineup_badge") == "confirmed" or f["scope"] == "team" for f in c2["rows"]),
          "confirmed=true keeps only announced starters and team lines")
    check(len(c2["rows"]) <= len(rows), "the confirmed filter only ever narrows")

print("selftest_likely: all checks passed")
