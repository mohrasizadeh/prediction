"""selftest_images.py -- the one-time image sync (doc 19) against a fake API-Football and an in-memory MongoDB.

    pip install mongomock httpx pymongo numpy scipy pandas cryptography
    SOCCER_BRAIN_DIR=../engine python selftest_images.py

Proves: matching (names, aliases, accents, initials); a wrong match is never used silently; the plan's season
limit is handled; the daily budget stops the run and the next run resumes; a second run costs nothing; bad files
(SVG, wrong bytes, too big) are refused; the image route is off until switched on and then cached for a year;
a take-down sticks; payloads carry our own image address or null.
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

import images as IM
import mongo_init
import queries as Q
import security
import settings_store as S

ok = lambda m: print("  ok  ", m)


def check(c, m):
    if not c:
        print("  FAIL", m); sys.exit(1)
    ok(m)


def png(tag: int) -> bytes:
    return b"\x89PNG\r\n\x1a\n" + bytes([tag % 256]) * 64


log = {"api": [], "media": []}
SQUAD = [{"id": 1100, "name": "B. Saka", "position": "Attacker"}, {"id": 1101, "name": "Gabriel Magalhães", "position": "Defender"},
         {"id": 1102, "name": "M. Ødegaard", "position": "Midfielder"}, {"id": 1103, "name": "John Smith", "position": "Defender"},
         {"id": 1104, "name": "James Smith", "position": "Defender"}, {"id": 1105, "name": "Kai Havertz", "position": "Attacker"},
         {"id": 1106, "name": "D. Rice", "position": "Midfielder"}]
TEAMS = [{"team": {"id": 42, "name": "Arsenal"}}, {"team": {"id": 33, "name": "Manchester United"}},
         {"team": {"id": 51, "name": "Brighton & Hove Albion"}}, {"team": {"id": 47, "name": "Tottenham"}},
         {"team": {"id": 40, "name": "Liverpool"}}, {"team": {"id": 50, "name": "Manchester City"}}]


def handler(r: httpx.Request):
    if r.url.host == "v3.football.api-sports.io":
        log["api"].append((r.url.path, dict(r.url.params)))
        assert r.headers["x-apisports-key"] == "k" * 32
        if r.url.path == "/teams":
            if r.url.params["season"] == "2025":
                return httpx.Response(200, json={"errors": {"plan": "Free plans do not have access to this season, try from 2021 to 2024."}, "response": []})
            return httpx.Response(200, json={"errors": [], "response": TEAMS})
        if r.url.path == "/players/squads":
            return httpx.Response(200, json={"errors": [], "response": [{"team": {"id": int(r.url.params["team"])}, "players": SQUAD if r.url.params["team"] == "42" else []}]})
        return httpx.Response(404)
    if r.url.host == IM.MEDIA_HOST:
        log["media"].append(r.url.path)
        pid = int(r.url.path.rsplit("/", 1)[1].split(".")[0])
        if pid == 1105:
            return httpx.Response(404)
        if pid == 1104:
            return httpx.Response(200, content=b"<svg onload='x'></svg>")
        return httpx.Response(200, content=png(pid))
    return httpx.Response(500)


def factory():
    return httpx.Client(transport=httpx.MockTransport(handler))


IM.set_http_factory(factory); IM.set_sleep(lambda s: None)


def make_db():
    db = mongomock.MongoClient()["img"]
    mongo_init.ensure_indexes(db)
    db.leagues.insert_one({"iid": 1, "id": "lg-1", "ext_id": 1, "name": "Premier League", "enabled": True, "current_season": "2025/2026", "image_url": "https://cdn.pitchapi.dev/l.png"})
    for i, n in enumerate(["Arsenal", "Man Utd", "Brighton", "Spurs", "Zzyzx FC"], start=10):
        db.teams.insert_one({"iid": i, "id": f"t-{i}", "ext_id": i, "name": n, "league_iid": 1, "image_url": "https://cdn.pitchapi.dev/t.png"})
    pl = [("Bukayo Saka", "FWD"), ("Gabriel Magalhaes", "DEF"), ("Martin Odegaard", "MID"), ("Smith", "DEF"), ("Kai Havertz", "FWD"), ("Nobody Known", "MID")]
    for i, (n, pos) in enumerate(pl, start=100):
        db.players.insert_one({"iid": i, "id": f"p-{i}", "ext_id": i, "name": n, "pos": pos, "team_iid": 10, "image_url": "https://cdn.pitchapi.dev/p.png"})
    security.save_provider_key(db, "apifootball", "k" * 32)
    S.put(db, "images.leagues", {"1": 39}, actor="test")
    return db


def test_matching():
    check(IM.team_score("Man Utd", "Manchester United") == 1.0, "alias: Man Utd = Manchester United")
    check(IM.team_score("Brighton", "Brighton & Hove Albion") == 1.0, "alias: Brighton = Brighton and Hove Albion")
    check(IM.team_score("Arsenal FC", "Arsenal") == 1.0, "club suffixes are ignored")
    check(IM.team_score("Manchester United", "Manchester City") < 0.9, "two Manchester clubs are not confused")
    check(IM.team_score("Inter", "Internazionale") == 1.0 and IM.team_score("Bayern", "Bayern München") == 1.0, "inter and bayern aliases, accents")
    check(IM.player_score("Bukayo Saka", "FWD", "B. Saka", "Attacker") >= 0.95, "full name matches 'B. Saka'")
    check(IM.player_score("Martin Odegaard", "MID", "M. Ødegaard", "Midfielder") >= 0.95, "Ø and ø fold to o")
    check(IM.player_score("Bukayo Saka", "FWD", "B. Saka", "Defender") < 0.9, "wrong position lowers the score")
    check(IM.player_score("Bukayo Saka", "FWD", "T. Saka", "Attacker") < 0.7, "same surname, different initial: not a match")
    check(IM.player_score("Smith", "DEF", "John Smith", "Defender") < 0.9, "surname only is never enough on its own")


def test_sync():
    db = make_db()
    out = IM.run_sync(db)
    check(out["done"], "first run finishes")
    m = {d["our_name"]: d for d in db.image_map.find({"kind": "team"})}
    check(m["Arsenal"]["status"] == "auto" and m["Man Utd"]["status"] == "auto" and m["Brighton"]["status"] == "auto" and m["Spurs"]["status"] == "auto",
          "four clubs matched without help (including aliases)")
    check(m["Zzyzx FC"]["status"] == "none" and m["Zzyzx FC"]["af_id"] is None, "a club with no counterpart gets no image and no guess")
    seasons = [p["season"] for path, p in log["api"] if path == "/teams"]
    check(seasons == ["2025", "2024"], "season the plan cannot read: falls back one season")
    check(len(log["api"]) == 3, "API calls: 2 for clubs (one refused season) + 1 squad = 3")
    check(db.media.count_documents({"kind": "team"}) == 4 and db.media.count_documents({"kind": "league"}) == 1, "4 crests and the league logo stored")
    pm = {d["our_name"]: d for d in db.image_map.find({"kind": "player"})}
    check(pm["Bukayo Saka"]["status"] == "auto" and pm["Martin Odegaard"]["status"] == "auto" and pm["Gabriel Magalhaes"]["status"] == "auto", "three players matched")
    check(pm["Smith"]["status"] == "review", "ambiguous 'Smith' goes to review (two candidates)")
    check(pm["Nobody Known"]["status"] == "none", "unknown player: none")
    check(db.media.count_documents({"kind": "player"}) == 3, "photos stored for the 3 matched players and Havertz's record is marked missing")
    hv = db.image_map.find_one({"kind": "player", "our_name": "Kai Havertz"})
    check(hv["status"] == "auto" and hv.get("missing") == "missing", "a photo the provider does not have is remembered, not retried")

    # second run: nothing to do
    n_api, n_media = len(log["api"]), len(log["media"])
    out2 = IM.run_sync(db)
    check(out2["done"] and len(log["api"]) == n_api and len(log["media"]) == n_media, "second run: zero API calls, zero downloads")

    # review
    rv = db.image_map.find_one({"kind": "player", "our_name": "Smith"})
    check({c["af_id"] for c in rv["candidates"]} == {1103, 1104}, "both candidates shown to the reviewer")
    try:
        IM.approve(db, "player", rv["our_iid"], 9999); check(False, "stranger id refused")
    except IM.ImageError:
        ok("an id that is not a candidate is refused")
    check(IM.approve(db, "player", rv["our_iid"], 1104) == "bad" and not db.media.find_one({"kind": "player", "iid": rv["our_iid"]}), "an SVG from the provider is refused")
    check(IM.approve(db, "player", rv["our_iid"], 1103) == "stored" and db.media.find_one({"kind": "player", "iid": rv["our_iid"]})["af_id"] == 1103, "approve fetches the chosen photo")
    IM.reject(db, "player", rv["our_iid"])
    check(not db.media.find_one({"kind": "player", "iid": rv["our_iid"]}) and db.image_map.find_one({"kind": "player", "our_iid": rv["our_iid"]})["status"] == "rejected", "reject removes it")

    # a new signing is found only by a refresh (one extra call), not by the normal run
    db.players.insert_one({"iid": 150, "id": "p-150", "ext_id": 150, "name": "Declan Rice", "pos": "MID", "team_iid": 10})
    n_api = len(log["api"])
    IM.run_sync(db)
    check(len(log["api"]) == n_api and not db.media.find_one({"kind": "player", "iid": 150}), "normal run does not re-read squads")
    IM.run_sync(db, refresh=True)
    check(len(log["api"]) == n_api + 1 and db.media.find_one({"kind": "player", "iid": 150}), "refresh: one call per matched club with players, new signing gets a photo")

    # take-down sticks
    saka = db.image_map.find_one({"kind": "player", "our_name": "Bukayo Saka"})["our_iid"]
    check(IM.remove(db, "player", saka), "take-down removes the image")
    n_media = len(log["media"])
    IM.run_sync(db)
    check(len(log["media"]) == n_media and not db.media.find_one({"kind": "player", "iid": saka}), "a taken-down image is never fetched again")
    return db


def test_budget_and_key():
    db = make_db()
    S.put(db, "images.daily_calls", 2, actor="test")
    log["api"].clear()
    out = IM.run_sync(db)
    check(out.get("stopped") == "budget" and not out["done"] and len(log["api"]) == 2, "budget of 2: run stops cleanly")
    S.put(db, "images.daily_calls", 90, actor="test")
    out = IM.run_sync(db)
    check(out["done"] and db.media.count_documents({"kind": "team"}) == 4, "next run resumes and finishes")
    S.put(db, "images.players", False, actor="test")
    db2 = make_db(); S.put(db2, "images.players", False, actor="test")
    IM.run_sync(db2)
    check(db2.media.count_documents({"kind": "player"}) == 0, "players switch off: logos only")
    db3 = mongomock.MongoClient()["nokey"]; mongo_init.ensure_indexes(db3)
    try:
        IM.run_sync(db3); check(False, "no key")
    except IM.NoKey:
        ok("no key saved: a plain error, no call made")
    db4 = make_db(); S.put(db4, "images.leagues", {}, actor="test")
    IM.run_sync(db4)
    check(db4.image_map.find_one({"kind": "league"})["status"] == "none" and db4.media.count_documents({}) == 0, "league id not set: nothing guessed")


def test_bytes():
    db = make_db()
    for bad, why in ((b"<svg xmlns='http://www.w3.org/2000/svg'/>", "SVG"), (b"GIF89a....", "GIF"), (b"just text", "text")):
        try:
            IM.store_media(db, "team", 10, bad, "test"); check(False, why)
        except IM.ImageError:
            ok(f"{why} refused")
    S.put(db, "images.max_bytes", 20000, actor="test")
    try:
        IM.store_media(db, "team", 10, png(1) + b"x" * 30000, "test"); check(False, "big")
    except IM.ImageError:
        ok("oversized file refused")
    r = IM.store_media(db, "team", 10, png(2), "upload")
    check(r["mime"] == "image/png" and db.media.count_documents({}) == 1, "a PNG is stored")
    IM.store_media(db, "team", 10, png(3), "upload")
    check(db.media.count_documents({}) == 1, "storing again replaces, never duplicates")


def test_serving(db):
    S.put(db, "images.enabled", False, actor="test")
    s0 = Q.search(db, "Arsenal")
    check(s0["teams"][0]["image"] is None and "image_url" not in s0["teams"][0], "images off: payload has image = null and no provider link")
    S.put(db, "images.enabled", True, actor="test")
    s1 = Q.search(db, "Arsenal")["teams"][0]
    check(s1["image"].startswith("/api/media/team/t-10?v="), "images on: payload carries our own address")
    check(Q.search(db, "Saka")["players"][0]["image"] is None, "a taken-down photo is null in the payload (the page draws initials)")
    check(Q.search(db, "Odegaard")["players"][0]["image"].startswith("/api/media/player/p-102?v="), "a player photo has our address")
    S.put(db, "images.use_provider_urls", True, actor="test")
    check(Q.search(db, "Zzyzx")["teams"][0]["image"] == "https://cdn.pitchapi.dev/t.png", "fallback to provider link only when switched on")

    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    import routes_images
    app = FastAPI(); app.state.db = db; app.include_router(routes_images.public)
    c = TestClient(app)
    S.put(db, "images.enabled", False, actor="test")
    check(c.get("/api/media/team/t-10").status_code == 404, "route is closed while images are off")
    S.put(db, "images.enabled", True, actor="test")
    r = c.get("/api/media/team/t-10")
    check(r.status_code == 200 and r.headers["content-type"] == "image/png" and r.content.startswith(b"\x89PNG"), "route serves the stored PNG")
    check("immutable" in r.headers["cache-control"] and "max-age=31536000" in r.headers["cache-control"] and r.headers["x-content-type-options"] == "nosniff", "cached for a year, no sniffing")
    check(c.get("/api/media/team/t-10", headers={"if-none-match": r.headers["etag"]}).status_code == 304, "ETag gives 304")
    check(c.get("/api/media/team/nope").status_code == 404 and c.get("/api/media/zzz/t-10").status_code == 404, "unknown id or kind: 404")
    check(c.get("/api/media/player/p-100").status_code == 404, "taken-down image: 404")


def test_client_hardening():
    """Retry once on 500, honour the provider's own counters, tolerate odd headers and error shapes."""
    def client_for(db, fn):
        return IM.AFClient(db, http=httpx.Client(transport=httpx.MockTransport(fn)))
    # 1. one 500, then success: retried once, both attempts counted
    db = make_db(); seen = []
    def h1(r):
        seen.append(1)
        return httpx.Response(500) if len(seen) == 1 else httpx.Response(200, json={"errors": [], "response": [{"team": {"id": 1, "name": "A"}}]})
    out = client_for(db, h1).get("/teams", {"league": 39, "season": 2024})
    check(len(seen) == 2 and out["response"] and IM.calls_today(db) == 2, "a 500 is retried once, then works (both calls counted)")
    # 2. two 500s in a row: a plain error, not a loop
    db = make_db(); seen.clear()
    def h2(r):
        seen.append(1); return httpx.Response(500)
    try:
        client_for(db, h2).get("/teams", {"league": 39, "season": 2024}); check(False, "two 500s")
    except IM.ImageError:
        check(len(seen) == 2, "two 500s: stops after one retry with a plain error")
    # 3. the provider says 0 requests remaining (header in any case): the next call is refused before it is sent
    db = make_db(); seen.clear()
    def h3(r):
        seen.append(1)
        return httpx.Response(200, headers={"X-RateLimit-Requests-Remaining": "0", "x-ratelimit-remaining": "9"}, json={"errors": [], "response": []})
    c = client_for(db, h3); c.get("/teams", {"league": 39, "season": 2024})
    try:
        c.get("/teams", {"league": 39, "season": 2023}); check(False, "remaining 0")
    except IM.BudgetExhausted:
        check(len(seen) == 1, "provider reports 0 left for today: next call is not sent")
    # 4. per-minute counter at 0 pauses briefly but still works; garbage header values are ignored
    db = make_db(); slept = []
    IM.set_sleep(lambda s: slept.append(s))
    def h4(r):
        return httpx.Response(200, headers={"x-ratelimit-remaining": "0", "x-ratelimit-requests-remaining": "abc"}, json={"errors": [], "response": []})
    client_for(db, h4).get("/teams", {"league": 39, "season": 2024})
    check(slept and (db.image_api_calls.find_one({}) or {}).get("remaining") is None, "per-minute window at 0: short pause; non-numeric header ignored")
    IM.set_sleep(lambda s: None)
    # 5. errors as a list, and a "rateLimit" error object, both handled
    db = make_db()
    def h5(r):
        return httpx.Response(200, json={"errors": {"rateLimit": "Too many requests. Your rate limit is 10 requests per minute."}, "response": []})
    try:
        client_for(db, h5).get("/teams", {"league": 39, "season": 2024}); check(False, "rateLimit error")
    except IM.BudgetExhausted:
        ok("a rate-limit message inside a 200 stops the run cleanly")
    db = make_db()
    def h6(r):
        return httpx.Response(200, json={"errors": ["Something odd"], "response": []})
    check(client_for(db, h6).get("/teams", {"league": 39, "season": 2024})["response"] == [], "errors as a list: treated as empty, no crash")


def main():
    for name, fn in (("matching", test_matching), ("sync", None), ("budget and key", test_budget_and_key), ("client hardening", test_client_hardening), ("bytes", test_bytes)):
        print(f"[{name}]")
        if fn is None:
            db = test_sync()
        else:
            fn()
    print("[serving]")
    test_serving(db)
    print("\nALL IMAGE CHECKS PASSED")


if __name__ == "__main__":
    main()
