"""selftest_pitch_images.py -- league logos, club crests and player photos come from PitchAPI (doc 19 section 9).

    pip install mongomock httpx pymongo
    SOCCER_BRAIN_DIR=../engine python selftest_pitch_images.py

Proves: all three kinds are fetched from cdn.pitchapi.dev and stored as our own bytes; a league logo and a crest
already on the record cost no API call; a crest riding along with a match detail call is saved; nothing outside the
CDN is ever downloaded; a missing picture is recorded once and not asked for again; and the public payload then
serves our own address, not the provider's.
"""
from __future__ import annotations

import base64
import os
import sys

os.environ.setdefault("APP_ENCRYPTION_KEY", base64.b64encode(os.urandom(32)).decode())
HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("SOCCER_BRAIN_DIR", os.path.join(HERE, "soccer_brain"))
sys.path.insert(0, HERE); sys.path.insert(0, os.environ["SOCCER_BRAIN_DIR"])

import httpx
import mongomock

import mongo_init
import pitch_photos as PP
import queries as Q
import settings_store as S
from cached_fetch import PitchClient

ok = lambda m: print("  ok  ", m)


def check(c, m):
    if not c:
        print("  FAIL", m); sys.exit(1)
    ok(m)


PNG = b"\x89PNG\r\n\x1a\n" + b"\x01" * 64
api_log, cdn_log, other_log = [], [], []


def handler(r: httpx.Request):
    host = r.url.host
    if host == "api.pitchapi.dev":
        api_log.append(r.url.path)
        if r.url.path == "/v1/teams/t-ext-2":
            return httpx.Response(200, json={"data": {"id": "t-ext-2", "name": "Two", "image_url": "https://cdn.pitchapi.dev/t/2.png"}})
        if r.url.path == "/v1/players/p-ext-2":
            return httpx.Response(200, json={"data": {"id": "p-ext-2", "name": "Two", "image_url": ""}})          # no picture
        if r.url.path == "/v1/players/p-ext-3":
            return httpx.Response(200, json={"data": {"id": "p-ext-3", "name": "Three", "image_url": "https://evil.example.com/x.png"}})
        return httpx.Response(404, json={"error": {"code": "RESOURCE_NOT_FOUND", "message": "no"}})
    if host == PP.CDN:
        cdn_log.append(r.url.path)
        return httpx.Response(200, content=PNG)
    other_log.append(str(r.url))
    return httpx.Response(200, content=PNG)


def client_and_db():
    db = mongomock.MongoClient()["pi"]
    mongo_init.ensure_indexes(db)
    import security
    security.save_provider_key(db, "pitchapi", "pk_test_zzzz")
    S.put(db, "ingest.rps", 1000)
    db.leagues.insert_one({"iid": 1, "id": "lg-1", "ext_id": "l-ext-1", "name": "League",
                           "image_url": "https://cdn.pitchapi.dev/l.png", "enabled": True})
    db.teams.insert_one({"iid": 10, "id": "t-1", "ext_id": "t-ext-1", "name": "One", "league_iid": 1,
                         "image_url": "https://cdn.pitchapi.dev/t/1.png"})
    db.teams.insert_one({"iid": 11, "id": "t-2", "ext_id": "t-ext-2", "name": "Two", "league_iid": 1})   # no URL yet
    for i, ext in ((100, "p-ext-1"), (101, "p-ext-2"), (102, "p-ext-3")):
        db.players.insert_one({"iid": i, "id": f"p-{i}", "ext_id": ext, "name": f"P{i}", "pos": "FWD", "team_iid": 10,
                               "image_url": "https://cdn.pitchapi.dev/p/1.png" if i == 100 else None})
    http = httpx.Client(base_url="https://api.pitchapi.dev", transport=httpx.MockTransport(handler))
    return PitchClient(db, http=http, sleep=lambda s: None), db


def main():
    c, db = client_and_db()
    shared = httpx.Client(transport=httpx.MockTransport(handler))

    # --- a league logo already on the record: downloaded, no API call
    before = len(api_log)
    check(PP.fetch_image(c, "league", "l-ext-1", http=shared) == "stored", "league logo is stored")
    check(len(api_log) == before, "a league logo already on the record costs no API call")
    m = db.media.find_one({"kind": "league", "iid": 1})
    check(m and m["source"] == "pitchapi" and m["size"] == len(PNG), "the league logo is our own bytes, marked pitchapi")

    # --- a crest already on the record: downloaded, no API call
    before = len(api_log)
    check(PP.fetch_image(c, "team", "t-ext-1", http=shared) == "stored", "club crest is stored")
    check(len(api_log) == before, "a crest already on the record costs no API call")

    # --- a crest not on the record: one call to /v1/teams/{id}
    check(PP.fetch_image(c, "team", "t-ext-2", http=shared) == "stored", "a crest with no stored address is fetched")
    check("/v1/teams/t-ext-2" in api_log, "it asks PitchAPI for that club")
    check(db.teams.find_one({"iid": 11})["image_url"] == "https://cdn.pitchapi.dev/t/2.png", "and the address is remembered")

    # --- player photos
    check(PP.fetch_image(c, "player", "p-ext-1", http=shared) == "stored", "player photo is stored")
    check(PP.fetch_image(c, "player", "p-ext-2", http=shared) == "missing", "a player with no picture reports missing")
    check(db.players.find_one({"iid": 101})["photo_checked_at"] is not None, "and is marked checked, so it is not asked again")

    # --- nothing outside the CDN is ever downloaded
    check(PP.fetch_image(c, "player", "p-ext-3", http=shared) == "missing", "an address off the CDN is refused")
    check(not other_log, f"nothing outside cdn.pitchapi.dev was fetched (saw {other_log})")
    check(db.media.find_one({"kind": "player", "iid": 102}) is None, "and nothing was stored for it")

    # --- crests that ride along with a match detail call
    db.teams.insert_one({"iid": 12, "id": "t-3", "ext_id": "t-ext-3", "name": "Three", "league_iid": 1})
    n = PP.note_team_images(db, [{"id": "t-ext-3", "image_url": "https://cdn.pitchapi.dev/t/3.png"},
                                 {"id": "t-ext-3-bad", "image_url": "https://evil.example.com/t.png"}])
    check(n == 1, "a crest that came free with a match detail call is saved")
    check(db.teams.find_one({"iid": 12})["image_url"] == "https://cdn.pitchapi.dev/t/3.png", "the saved crest is the CDN one")

    # --- the queue plans all three kinds
    queued = PP.plan(db, force=True)
    tasks = set(db.ingest_queue.distinct("task", {"status": "pending"}))
    check(queued > 0, f"the daily plan queues work ({queued} items)")
    check("team_crest" in tasks and "player_photo" in tasks, f"it queues crests and photos ({sorted(tasks)})")

    # --- the public payload serves our address, not the provider's
    S.put(db, "images.enabled", True, actor="test")
    rows = Q.attach_images(db, "teams", [dict(db.teams.find_one({"iid": 10}))])
    check(rows[0]["image"].startswith("/api/media/team/"), f"a club payload carries our own address ({rows[0]['image']})")
    check("pitchapi.dev" not in str(rows[0]["image"]), "the provider's address is never sent to the browser")

    # --- status counts by source
    st = PP.status(db)
    check(st["from_pitchapi"] >= 4 and st["from_apifootball"] == 0, f"every stored picture came from PitchAPI ({st['from_pitchapi']})")

    print("\nALL PITCHAPI IMAGE CHECKS PASSED")


if __name__ == "__main__":
    main()
