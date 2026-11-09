"""server.py -- the glue. Mounts the routers, the security layer, the public data routes and the tick.

Every route in docs/06 is mounted: the routers below plus the data routes in this file, routes_data.py and routes_me.py.
Only Telegram alerts (phase 2) and the admin data screens listed in docs/06 section 5 are left for the builder. Keep these patterns:
  * sync pymongo client, plain `def` routes (FastAPI runs them in a thread pool)
  * every /api/admin route uses deps.require_perm("<permission>")  -- checked on the server, every request
  * every admin write goes to audit_log
  * plan limits are read from plans.effective_plan(), never hard-coded
Run:  uvicorn server:app --reload
"""
from __future__ import annotations

import hmac
import os

from fastapi import Depends, FastAPI, Header, Query, Request
from pymongo import MongoClient

import accounts
import analytics as AN
import deps as D
import jobs
import legal_pages
import mongo_init
import plans as P
import queries as Q
import routes_accounts
import routes_admin
import routes_billing
import routes_social
import routes_teams
import routes_data
import routes_data_admin
import routes_ingest_admin
import routes_cron
import routes_images
import routes_live
import routes_me
import routes_ads
import routes_site
import security_mw
import settings_store as S

PROD = os.environ.get("ENV", "development") == "production"
app = FastAPI(title="Forecast API", docs_url=None if PROD else "/docs", redoc_url=None, openapi_url=None if PROD else "/openapi.json")
security_mw.install(app, D.get_db)
security_mw.add_cors(app, [o.strip() for o in os.environ.get("ALLOWED_ORIGINS", "").split(",") if o.strip()])
app.include_router(routes_accounts.router)
app.include_router(routes_billing.router)
app.include_router(routes_admin.router)
app.include_router(routes_site.public)
app.include_router(routes_site.admin)
app.include_router(routes_images.public)
app.include_router(routes_images.admin)
app.include_router(routes_live.public)
app.include_router(routes_live.admin)
app.include_router(routes_teams.router)
app.include_router(routes_social.admin)
app.include_router(routes_social.public)
app.include_router(routes_data.router)
app.include_router(routes_data_admin.router)
app.include_router(routes_ingest_admin.router)
app.include_router(routes_cron.router)
app.include_router(routes_me.router)
app.include_router(routes_ads.router)


def set_db(db) -> None:
    app.state.db = db


@app.on_event("startup")
def startup():
    if not hasattr(app.state, "db"):
        app.state.db = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
    db = app.state.db
    mongo_init.ensure_indexes(db)
    P.seed(db)
    legal_pages.seed(db)                    # starter Terms / Privacy / About when missing (docs/36 C2); never overwrites
    accounts.bootstrap_owner(db)            # first start only; the owner must change this password at first sign-in
    _start_live_loop(db)


def _start_live_loop(db):
    """SportAPI minute job in the server process (platform crons cannot run every minute). Off unless features.live."""
    import threading
    import time
    from datetime import datetime, timezone
    import sportapi as SP

    def loop():
        while True:
            try:
                if S.get(db, "features.live"):
                    SP.live_tick(db)
            except Exception as e:  # noqa: BLE001
                db.app_logs.insert_one({"at": datetime.now(timezone.utc), "level": "error", "source": "sportapi.live_loop", "message": str(e)[:500]})
            time.sleep(60)
    threading.Thread(target=loop, name="sportapi-live", daemon=True).start()


# ------------------------------------------------------------------- public
@app.get("/api/public/settings")
def public_settings(db=Depends(D.get_db)):
    return S.public(db)


@app.get("/api/content/{slug}")
def content(slug: str, db=Depends(D.get_db)):
    page = db.content_pages.find_one({"slug": slug}, {"_id": 0, "slug": 1, "title": 1, "body_md": 1, "updated_at": 1})
    if not page:
        raise D.err(404, "NOT_FOUND", "No such page.")
    return page          # body_md is Markdown. The front end must render it with a sanitizer. Never inject it as raw HTML.


@app.get("/api/fixtures")
def fixtures(date: str, tz: int = 0, leagues: str = "", db=Depends(D.get_db)):
    ids = [Q.iid_of(db, "leagues", x) for x in leagues.split(",") if x]
    return Q.fixtures_for_date(db, date, tz, [i for i in ids if i])


@app.get("/api/insights")
def insights(limit: int = 50, sort: str = "", stat: str = "", scope: str = "", leagues: str = "", tiers: str = "Strong,Solid",
             players: str = "", teams: str = "", min_p: float = 0.0, within_h: float = 0.0,
             user=Depends(D.optional_user), db=Depends(D.get_db)):
    """sort = edge (default: most different from usual) | likely | kickoff (docs/25).
    `players` and `teams` are comma-separated public ids and narrow the feed to them (docs/52)."""
    # `insights_per_day` is a daily quota ("Insight cards per day"), and nothing ever consumed it --
    # it was being spent as a per-response row limit instead. The page asks for 200 as a filtering
    # pool and then filters client-side on day, market, tier, position, venue, club and player, so a
    # free reader's 200 silently became 20 and every one of those filters ran on 20 rows. That is why
    # a player who is plainly in the data was missing from the feed. The cap belongs on what is
    # DISPLAYED, after the filters, and the page already applies it there: it reads the same
    # entitlement itself and renders the "your plan shows N a day" notice (Insights.jsx:109,207).
    ids = [i for i in (Q.iid_of(db, "leagues", x) for x in leagues.split(",") if x) if i] or ([-1] if leagues else None)
    pids = [i for i in (Q.iid_of(db, "players", x) for x in players.split(",") if x) if i] or ([-1] if players else None)
    tids = [i for i in (Q.iid_of(db, "teams", x) for x in teams.split(",") if x) if i] or ([-1] if teams else None)
    tl = tuple(t for t in tiers.split(",") if t in ("Strong", "Solid", "Watch")) or ("Strong", "Solid")
    return Q.insights_feed(db, limit=min(limit, 200), tiers=tl, league_iids=ids,
                           stat=stat or None, scope=scope if scope in ("player", "team") else None,
                           sort=sort if sort in Q.FEED_SORTS else None, player_iids=pids, team_iids=tids,
                           min_p=(min_p if 0 < min_p <= 1 else None),
                           within_h=(within_h if 0 < within_h <= 24 * 14 else None))


@app.get("/api/likely")
def likely(within_h: float = 4.0, limit: int = 60, leagues: str = "", stat: str = "", confirmed: bool = False,
           db=Depends(D.get_db)):
    """The "most likely" screen (docs/63): what is likeliest in the next few hours, likeliest first.

    This is not /api/insights with different arguments. That feed answers "what differs most from
    usual", leads on the edge, and defaults to Strong+Solid; this one answers "what is likeliest",
    leads on the number, and wants every tier -- a tier grades a different thing and a Watch line at
    88% belongs at the top of THIS list.

    The floor is `engine.watch_min` and it is RETURNED, not assumed. The screen says "nothing here
    reaches 60%" in its empty state and in its hint line, and a floor retyped in JavaScript is a
    sentence that goes quietly wrong the first time the setting moves.
    """
    floor = float(S.get(db, "engine.watch_min"))
    ids = [i for i in (Q.iid_of(db, "leagues", x) for x in leagues.split(",") if x) if i] or ([-1] if leagues else None)
    rows = Q.insights_feed(db, limit=min(limit, 200), tiers=("Strong", "Solid", "Watch"), league_iids=ids,
                           stat=stat or None, sort="likely", min_p=floor,
                           within_h=(within_h if 0 < within_h <= 24 * 14 else 4.0))
    if confirmed:
        rows = [r for r in rows if r.get("lineup_badge") == "confirmed" or r.get("scope") == "team"]
    # The feed's "likely" sort puts tier first; this screen is sorted by the number alone, because
    # the number is what it is named after.
    rows.sort(key=lambda r: -r["p"])
    return {"floor": floor, "within_h": within_h, "rows": rows,
            "confirmed_n": sum(1 for r in rows if r.get("lineup_badge") == "confirmed")}


@app.get("/api/search")
def search(q: str, db=Depends(D.get_db)):
    if len(q.strip()) < 2:
        raise D.err(400, "TOO_SHORT", "Type at least 2 characters.")
    return Q.search(db, q)


@app.get("/api/finder")
def finder(request: Request, mode: str = "likelihood", stat: str = "shots", threshold: float = 1.5, last_n: int = Query(10, ge=1, le=38),
           leagues: str = "", scope: str = "player", min_p: float = Query(0.0, ge=0, le=1), venue: str | None = None, started: bool = False,
           min_minutes: float = Query(0, ge=0, le=120), positions: str = "", min_reached: float = Query(0.0, ge=0, le=1),
           day: str | None = None, tz: int = Query(0, ge=-840, le=840), limit: int = Query(100, ge=1, le=200),
           user=Depends(D.optional_user), db=Depends(D.get_db)):
    """The Forecast Finder. Shows how a plan limit is enforced: search count per day and leagues per search."""
    ep = P.effective_plan(db, user)
    ent = ep["entitlements"]
    lg_ids = [i for i in (Q.iid_of(db, "leagues", x) for x in leagues.split(",") if x) if i]
    if ent["finder_leagues"] >= 0 and (not lg_ids or len(lg_ids) > ent["finder_leagues"]):
        raise D.err(403 if lg_ids else 400, "UPGRADE_REQUIRED" if lg_ids else "PICK_A_LEAGUE",
                    f"Your plan searches {ent['finder_leagues']} league(s) at a time." if lg_ids else "Pick a league to search.")
    if user:
        subject, cap = f"u:{user['id']}", ent["finder_searches_per_day"]
    else:
        subject, cap = D.anon_subject(request), int(S.get(db, "plans.anonymous_finder_searches_per_day"))
    ok, used = P.consume(db, subject, "finder", cap)
    if not ok:
        if not user:
            raise D.err(401, "SIGN_IN_REQUIRED", "Create a free account to keep searching.")
        raise D.err(402, "UPGRADE_REQUIRED", "You have used today's searches on your plan.")
    AN.track(db, "finder_search", user_id=user and user["id"], server=True, ip=getattr(request.state, "ip", ""), props={"stat": stat, "mode": mode})
    return Q.finder(db, mode, stat, threshold, last_n=last_n, league_iids=lg_ids or None, scope=scope, min_p=min_p, limit=limit, venue=venue,
                    started=started, min_minutes=min_minutes, positions=[p for p in positions.split(",") if p] or None, min_reached=min_reached,
                    day=day, tz_offset_min=tz)


# --------------------------------------------------------------------- tick
@app.post("/api/jobs/tick")
def tick(x_cron_secret: str | None = Header(default=None), db=Depends(D.get_db)):
    if not hmac.compare_digest(x_cron_secret or "", os.environ.get("CRON_SHARED_SECRET", "\0")):
        raise D.err(401, "BAD_SECRET", "Bad secret.")
    return jobs.tick(db)
