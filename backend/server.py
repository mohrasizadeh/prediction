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

import hashlib
import hmac
import os

from fastapi import Depends, FastAPI, Header, Query, Request
from pymongo import MongoClient

import accounts
import analytics as AN
import deps as D
import jobs
import mongo_init
import plans as P
import queries as Q
import routes_accounts
import routes_admin
import routes_billing
import routes_data
import routes_data_admin
import routes_ingest_admin
import routes_cron
import routes_images
import routes_live
import routes_me
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
app.include_router(routes_data.router)
app.include_router(routes_data_admin.router)
app.include_router(routes_ingest_admin.router)
app.include_router(routes_cron.router)
app.include_router(routes_me.router)


def set_db(db) -> None:
    app.state.db = db


@app.on_event("startup")
def startup():
    if not hasattr(app.state, "db"):
        app.state.db = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
    db = app.state.db
    mongo_init.ensure_indexes(db)
    P.seed(db)
    accounts.bootstrap_owner(db)            # first start only; the owner must change this password at first sign-in


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
def insights(limit: int = 50, user=Depends(D.optional_user), db=Depends(D.get_db)):
    cap = P.effective_plan(db, user)["entitlements"]["insights_per_day"]
    return Q.insights_feed(db, limit=min(limit, 200, cap if cap >= 0 else 200))


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
        ip = getattr(request.state, "ip", "") or ""
        subject, cap = "ip:" + hashlib.sha256((ip + request.headers.get("user-agent", "")).encode()).hexdigest()[:16], int(S.get(db, "plans.anonymous_finder_searches_per_day"))
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
