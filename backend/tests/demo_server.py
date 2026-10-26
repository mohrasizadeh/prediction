"""demo_server.py -- the whole app on fake data, no keys and no MongoDB needed.

    pip install -r requirements.txt mongomock uvicorn
    python tests/demo_server.py            # API on http://localhost:8001 ; also serves ../frontend/build if it exists

Builds a simulated league through the fake PitchAPI (invented key names), runs the engine, and moves the next round
to today so the Today screen has matches. In-memory only: everything is gone when it stops. Never use in production.
"""
import base64, datetime as dt, os, sys
os.environ.setdefault("APP_ENCRYPTION_KEY", base64.b64encode(os.urandom(32)).decode())
os.environ.setdefault("ADMIN_EMAIL", "owner@example.com"); os.environ.setdefault("ADMIN_INITIAL_PASSWORD", "demo-owner-pass-1")
os.environ.setdefault("COOKIE_SECURE", "0"); os.environ.setdefault("PUBLIC_BASE_URL", "http://localhost:8001")
HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("SOCCER_BRAIN_DIR", os.path.join(HERE, "soccer_brain"))
sys.path.insert(0, HERE); sys.path.insert(0, os.path.dirname(os.path.abspath(__file__))); sys.path.insert(0, os.environ["SOCCER_BRAIN_DIR"])
import httpx, mongomock, uvicorn
import server as srv, engine_bridge as B, ingest as I, mongo_init, settings_store as S, security
from cached_fetch import PitchClient
from fake_pitchapi import PLAYER_KEYS, TEAM_KEYS, FakePitch
from simulate import simulate_league


def build():
    db = mongomock.MongoClient()["demo"]; mongo_init.ensure_indexes(db)
    security.save_provider_key(db, "pitchapi", "pk_demo_zzzz")
    S.put(db, "ingest.rps", 1000); S.put(db, "provider.pitchapi.team_keys", TEAM_KEYS); S.put(db, "provider.pitchapi.player_keys", PLAYER_KEYS)
    S.put(db, "provider.position_map", {"0": "GK", "1": "DEF", "2": "MID", "3": "FWD"})
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
    # move time so the next round kicks off today at 19:00 UTC
    target = dt.datetime.now(dt.timezone.utc).replace(hour=19, minute=0, second=0, microsecond=0)
    delta = target - fake.kick(n_final).replace(tzinfo=dt.timezone.utc) if fake.kick(n_final).tzinfo is None else target - fake.kick(n_final)
    for coll in ("matches", "forecasts", "player_match_stats", "team_match_stats"):
        for d in db[coll].find({"kickoff": {"$exists": True}}, {"_id": 1, "kickoff": 1}):
            k = d["kickoff"] if d["kickoff"].tzinfo else d["kickoff"].replace(tzinfo=dt.timezone.utc)
            db[coll].update_one({"_id": d["_id"]}, {"$set": {"kickoff": k + delta}})
    db.content_pages.insert_one({"slug": "learn", "title": "How to read a forecast", "published": True,
                                 "body_md": "A **forecast** is the chance a player or team reaches a stat line.\n\n- Strong: 3 dots\n- Solid: 2 dots\n- Watch: 1 dot"})
    return db


if __name__ == "__main__":
    db = build(); srv.set_db(db)
    build_dir = os.path.join(HERE, "..", "frontend", "build")
    if os.path.isdir(build_dir):
        from fastapi.responses import FileResponse
        from fastapi.staticfiles import StaticFiles
        srv.app.mount("/static", StaticFiles(directory=os.path.join(build_dir, "static")), name="static")   # JS and CSS keep the strict API headers; they are not documents

        @srv.app.get("/{path:path}", include_in_schema=False)
        def spa(path: str):
            if path.startswith("api/"):
                raise srv.D.err(404, "NOT_FOUND", "No such route.")
            # the page's own policy (docs/15); the API's default-src 'none' is for JSON answers only
            return FileResponse(os.path.join(build_dir, "index.html"), headers={"Content-Security-Policy":
                "default-src 'self'; img-src 'self' data:; style-src 'self'; script-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'"})
    print("Demo owner:", os.environ["ADMIN_EMAIL"], "/", os.environ["ADMIN_INITIAL_PASSWORD"])
    uvicorn.run(srv.app, host="0.0.0.0", port=int(os.environ.get("PORT", 8001)))
