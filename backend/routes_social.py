"""routes_social.py -- the posting queue's admin API, and the one public callback (docs/64).

The admin half sits behind the same `site.read` / `site.write` permissions as the ad builder it
feeds. The public half is a single endpoint the automation tool calls back on, authorised by a
token that only the delivery for that one post ever carried -- so it needs no session, no key and
no allowance in the rate limiter's auth bucket.
"""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Body, Depends, Query
from pydantic import BaseModel, Field

import deps as D
import social as SOC

admin = APIRouter(prefix="/api/admin/social")
# /api/webhooks/ is already exempt from the browser-origin check and the write rate limiter
# (security_mw ORIGIN_EXEMPT / RATE_EXEMPT), which is exactly right for a server-to-server POST
# that carries no cookie. Putting this callback anywhere else would mean widening those lists.
public = APIRouter(prefix="/api/webhooks")
perm = D.require_perm


class NewPost(BaseModel):
    platform: str = Field("instagram")
    kind: str = Field("post")
    media: list[str] = Field(default_factory=list)
    caption: str = ""
    scheduled_at: datetime
    design_id: str | None = None
    note: str = ""


class EditPost(BaseModel):
    caption: str | None = None
    media: list[str] | None = None
    scheduled_at: datetime | None = None


def _bad(e: SOC.SocialError):
    # The message names what to fix, so it is shown rather than swallowed behind a generic code.
    return D.err(400, "BAD_POST", str(e))


@admin.get("")
def listing(frm: datetime | None = Query(None, alias="from"), to: datetime | None = None,
            user=Depends(perm("site.read")), db=Depends(D.get_db)):
    return {"overview": SOC.overview(db), "posts": SOC.listing(db, frm, to)}


@admin.post("")
def create(body: NewPost, user=Depends(perm("site.write")), db=Depends(D.get_db)):
    try:
        return SOC.queue(db, user["email"], platform=body.platform, kind=body.kind, media=body.media,
                         caption=body.caption, scheduled_at=body.scheduled_at,
                         design_id=body.design_id, note=body.note)
    except SOC.SocialError as e:
        raise _bad(e)


@admin.put("/{pid}")
def edit(pid: str, body: EditPost, user=Depends(perm("site.write")), db=Depends(D.get_db)):
    try:
        return SOC.edit(db, user["email"], pid, caption=body.caption, media=body.media,
                        scheduled_at=body.scheduled_at)
    except SOC.SocialError as e:
        raise _bad(e)


@admin.post("/{pid}/approve")
def approve(pid: str, user=Depends(perm("site.write")), db=Depends(D.get_db)):
    try:
        return SOC.approve(db, user["email"], pid)
    except SOC.SocialError as e:
        raise _bad(e)


@admin.post("/{pid}/unapprove")
def unapprove(pid: str, user=Depends(perm("site.write")), db=Depends(D.get_db)):
    try:
        return SOC.unapprove(db, user["email"], pid)
    except SOC.SocialError as e:
        raise _bad(e)


@admin.delete("/{pid}")
def cancel(pid: str, user=Depends(perm("site.write")), db=Depends(D.get_db)):
    try:
        return SOC.cancel(db, user["email"], pid)
    except SOC.SocialError as e:
        raise _bad(e)


@public.post("/social/{pid}")
def result(pid: str, body: dict = Body(default_factory=dict), db=Depends(D.get_db)):
    """What the automation tool reports after it tried to publish.

    Shape is deliberately forgiving, because the person wiring the Zap is mapping fields by hand in
    somebody else's UI: `ok` may arrive as a boolean or as a string, the permalink under any of the
    three names these tools use, and anything truthy in `error` means it failed whatever `ok` says.
    A callback that is rejected on a technicality leaves the screen saying "sent" forever.
    """
    raw = body.get("ok", body.get("success", True))
    ok = raw if isinstance(raw, bool) else str(raw).strip().lower() not in ("false", "0", "no", "")
    err = body.get("error") or body.get("message") or None
    if err:
        ok = False
    link = body.get("permalink") or body.get("url") or body.get("link")
    try:
        row = SOC.callback(db, pid, str(body.get("token") or ""), ok=ok, permalink=link, error=err)
    except SOC.SocialError as e:
        raise D.err(404, "NOT_FOUND", str(e))
    return {"ok": True, "status": row["status"]}
