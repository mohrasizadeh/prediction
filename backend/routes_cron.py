"""routes_cron.py -- the platform's scheduled call (.emergent/crons.yml) for the ingest tick. Same work as
POST /api/jobs/tick, but the platform sends Authorization: Bearer $WEBHOOK_CRON_SECRET and waits only ~5 s,
so the tick runs in a background thread and the request returns 202 at once."""
from __future__ import annotations

import hmac
import os
import threading
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Header, Request
from pymongo.errors import DuplicateKeyError

import deps as D
import jobs

router = APIRouter(prefix="/api")


def _start(db):
    threading.Thread(target=jobs.tick, args=(db,), daemon=True).start()


@router.post("/cron/tick", status_code=202)
async def cron_tick(request: Request, authorization: str | None = Header(default=None),
                    x_webhook_id: str | None = Header(default=None), db=Depends(D.get_db)):
    # Cron endpoints must ack 2xx immediately; enqueue/background the actual work.
    secret = os.environ.get("WEBHOOK_CRON_SECRET", "")
    token = authorization[7:] if (authorization or "").startswith("Bearer ") else ""
    if not secret or not hmac.compare_digest(token, secret):
        raise D.err(401, "BAD_SECRET", "Bad secret.")
    try:
        body = await request.json()
    except ValueError:
        body = None
    if body is not None and not isinstance(body, dict):
        raise D.err(400, "BAD_BODY", "Expected a JSON object.")
    run_id = x_webhook_id or (body or {}).get("run_id") or ""
    if run_id:
        try:
            db.cron_runs.insert_one({"_id": str(run_id)[:100], "at": datetime.now(timezone.utc)})
        except DuplicateKeyError:
            return {"accepted": False, "duplicate": True}
    _start(db)
    return {"accepted": True}


@router.post("/cron/images/{mode}", status_code=202)
async def cron_images(mode: str, request: Request, authorization: str | None = Header(default=None),
                      x_webhook_id: str | None = Header(default=None), db=Depends(D.get_db)):
    # Cron endpoints must ack 2xx immediately; enqueue/background the actual work.
    # Twice-yearly image sync (1-5 Jan and Aug): mode "refresh" re-reads squads, "continue" carries on.
    secret = os.environ.get("WEBHOOK_CRON_SECRET", "")
    token = authorization[7:] if (authorization or "").startswith("Bearer ") else ""
    if not secret or not hmac.compare_digest(token, secret):
        raise D.err(401, "BAD_SECRET", "Bad secret.")
    try:
        body = await request.json()
    except ValueError:
        body = None
    if body is not None and not isinstance(body, dict):
        raise D.err(400, "BAD_BODY", "Expected a JSON object.")
    if mode not in ("refresh", "continue"):
        raise D.err(400, "BAD_MODE", "Mode is refresh or continue.")
    run_id = x_webhook_id or (body or {}).get("run_id") or ""
    if run_id:
        try:
            db.cron_runs.insert_one({"_id": "images:" + str(run_id)[:100], "at": datetime.now(timezone.utc)})
        except DuplicateKeyError:
            return {"accepted": False, "duplicate": True}
    refresh = mode == "refresh"
    db.job_requests.insert_one({"job": "images", "refresh": refresh, "status": "pending",
                                "requested_at": datetime.now(timezone.utc), "requested_by": "cron"})
    _start(db)
    return {"accepted": True, "refresh": refresh}
