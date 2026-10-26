"""routes_images.py -- serve stored images (public) and manage them (admin).

Public:  GET /api/media/{kind}/{public_id}      the image bytes, cached for a year (the URL carries ?v=hash)
Admin:   GET  /api/admin/images                 counts, budget, last run
         GET  /api/admin/images/review          pairs that need a person (best candidates shown)
         POST /api/admin/images/sync            queue the sync job (Run now)
         POST /api/admin/images/{kind}/{iid}/approve   body {af_id?}
         POST /api/admin/images/{kind}/{iid}/reject
         PUT  /api/admin/images/{kind}/{iid}/upload    raw PNG/JPEG/WebP bytes (fix a wrong or missing image)
         DELETE /api/admin/images/{kind}/{iid}         take an image down; it is never fetched again
Every write is permission-checked (`jobs.run`) and audited.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Query, Request, Response
from pydantic import BaseModel

import admin_queries as AQ
import deps as D
import images as IM
import queries as Q
import settings_store as S

public = APIRouter(prefix="/api")
admin = APIRouter(prefix="/api/admin/images")
perm = D.require_perm
COLL = {"league": "leagues", "team": "teams", "player": "players"}


@public.get("/media/{kind}/{public_id}")
def media(kind: str, public_id: str, request: Request, db=Depends(D.get_db)):
    nf = Response(status_code=404, headers={"Cache-Control": "public, max-age=300"})
    if kind not in COLL or not S.get(db, "images.enabled") or len(public_id) > 64:
        return nf
    iid = Q.iid_of(db, COLL[kind], public_id)
    d = db.media.find_one({"kind": kind, "iid": iid}) if iid is not None else None
    if not d:
        return nf
    etag = f'"{d["sha256"][:16]}"'
    h = {"ETag": etag, "Cache-Control": "public, max-age=31536000, immutable", "X-Content-Type-Options": "nosniff",
         "Content-Disposition": "inline"}
    if request.headers.get("if-none-match") == etag:
        return Response(status_code=304, headers=h)
    return Response(content=bytes(d["data"]), media_type=d["mime"], headers=h)


def _kind(kind: str):
    if kind not in COLL:
        raise D.err(400, "BAD_KIND", "Kind must be league, team or player.")


@admin.get("")
def overview(user=Depends(perm("logs.read")), db=Depends(D.get_db)):
    return IM.status(db)


@admin.get("/review")
def review(kind: Optional[str] = None, page: int = Query(1, ge=1), limit: int = Query(25, ge=1, le=100),
           user=Depends(perm("logs.read")), db=Depends(D.get_db)):
    q = {"status": "review"}
    if kind:
        _kind(kind); q["kind"] = kind
    total = db.image_map.count_documents(q)
    rows = list(db.image_map.find(q, {"_id": 0}).sort([("score", -1)]).skip((page - 1) * limit).limit(limit))
    return {"total": total, "rows": rows, "page": page}


@admin.post("/sync")
def sync(refresh: bool = False, user=Depends(perm("jobs.run")), db=Depends(D.get_db)):
    """Queue the sync. `refresh=true` also re-reads every squad (1 API call per club) to pick up new signings."""
    db.job_requests.insert_one({"job": "images", "refresh": bool(refresh), "status": "pending", "requested_at": datetime.now(timezone.utc), "requested_by": user["email"]})
    AQ.audit(db, user, "images.sync", "images")
    return {"queued": True}


class Pick(BaseModel):
    af_id: Optional[int] = None


@admin.post("/{kind}/{iid}/approve")
def approve(kind: str, iid: int, body: Pick, user=Depends(perm("jobs.run")), db=Depends(D.get_db)):
    _kind(kind)
    try:
        res = IM.approve(db, kind, iid, body.af_id)
    except IM.ImageError as e:
        raise D.err(400, "CANNOT_APPROVE", str(e))
    AQ.audit(db, user, "images.approve", f"{kind}:{iid}")
    return {"result": res}


@admin.post("/{kind}/{iid}/reject")
def reject(kind: str, iid: int, user=Depends(perm("jobs.run")), db=Depends(D.get_db)):
    _kind(kind)
    IM.reject(db, kind, iid)
    AQ.audit(db, user, "images.reject", f"{kind}:{iid}")
    return {"ok": True}


@admin.put("/{kind}/{iid}/upload")
async def upload(kind: str, iid: int, request: Request, user=Depends(perm("jobs.run")), db=Depends(D.get_db)):
    _kind(kind)
    if db[COLL[kind]].count_documents({"iid": iid}, limit=1) == 0:
        raise D.err(404, "NOT_FOUND", "No such record.")
    data = await request.body()
    try:
        out = IM.store_media(db, kind, iid, data, source="upload:" + user["email"])
    except IM.ImageError as e:
        raise D.err(400, "BAD_IMAGE", str(e))
    db.image_map.update_one({"kind": kind, "our_iid": iid}, {"$set": {"status": "approved", "source": "upload"}}, upsert=True)
    AQ.audit(db, user, "images.upload", f"{kind}:{iid}")
    return out


@admin.delete("/{kind}/{iid}")
def takedown(kind: str, iid: int, user=Depends(perm("jobs.run")), db=Depends(D.get_db)):
    _kind(kind)
    removed = IM.remove(db, kind, iid)
    AQ.audit(db, user, "images.remove", f"{kind}:{iid}")
    return {"removed": removed}
