"""routes_blog.py -- the blog: public HTML pages, and the admin screen behind them (docs/72).

  public  GET /api/blog                  the index, as HTML
          GET /api/blog/{slug}           one published post, as HTML
  admin   GET    /api/admin/blog         list drafts and published posts
          POST   /api/admin/blog/generate      prepare drafts for a day
          GET    /api/admin/blog/{slug}        one post, including a draft
          GET    /api/admin/blog/{slug}/preview   the rendered page for a DRAFT, never indexable
          PUT    /api/admin/blog/{slug}        edit title / description / intro
          POST   /api/admin/blog/{slug}/publish
          POST   /api/admin/blog/{slug}/unpublish
          DELETE /api/admin/blog/{slug}

The public routes return text/html, which no other route in this service does. They each set their
own Content-Security-Policy: the app-wide default is `default-src 'none'`, which would render the
page blank (see blog_render.CSP).
"""
from __future__ import annotations

import re
from typing import Optional

from fastapi import APIRouter, Depends, Query, Response
from pydantic import BaseModel, Field

import blog as B
import blog_render as BR
import deps as D
import settings_store as S
import textguard as TG

public = APIRouter(prefix="/api")
admin = APIRouter(prefix="/api/admin")
perm = D.require_perm

SLUG = re.compile(r"^[a-z0-9][a-z0-9-]{0,118}[a-z0-9]$")

# A post changes only when an admin republishes it, so it can be cached properly. Ten minutes at the
# browser, an hour at any shared cache: long enough to absorb a post doing well, short enough that
# fixing a typo does not need a cache purge.
_HTML = {"Cache-Control": "public, max-age=600, s-maxage=3600",
         "Content-Security-Policy": BR.CSP,
         "X-Content-Type-Options": "nosniff"}

# A draft preview must never be cached, and must never be indexed if the link escapes.
_DRAFT = {"Cache-Control": "no-store", "Content-Security-Policy": BR.CSP,
          "X-Robots-Tag": "noindex, nofollow", "X-Content-Type-Options": "nosniff"}


def _enabled(db) -> bool:
    return bool(S.get(db, "blog.enabled"))


def _404(db) -> Response:
    """A real 404, with a page rather than a JSON error: a visitor arrived here from a link.

    It carries X-Robots-Tag as well as the status, because a crawler that followed a stale link
    should drop it rather than keep the URL in a queue.
    """
    body = BR.render_index(db, [])
    return Response(body, status_code=404, media_type="text/html; charset=utf-8",
                    headers={**_DRAFT, "Cache-Control": "no-store"})


# ============================================================================= PUBLIC
@public.get("/blog", response_class=Response)
def blog_index(db=Depends(D.get_db)):
    if not _enabled(db):
        return _404(db)
    return Response(BR.render_index(db, B.published(db, limit=60)),
                    media_type="text/html; charset=utf-8", headers=_HTML)


@public.get("/blog/{slug}", response_class=Response)
def blog_post(slug: str, db=Depends(D.get_db)):
    if not _enabled(db) or not SLUG.match(slug or ""):
        return _404(db)
    post = B.get_public(db, slug)
    if not post:
        # Deliberately the same answer for "never existed", "still a draft" and "unpublished again".
        # Otherwise the status of unreleased posts is readable by guessing slugs, and the slugs are
        # guessable by design -- they are two club names and a date.
        return _404(db)
    return Response(BR.render_post(db, post), media_type="text/html; charset=utf-8", headers=_HTML)


# ============================================================================= ADMIN
class GenBody(BaseModel):
    day: Optional[str] = Field(None, max_length=10)
    limit: Optional[int] = Field(None, ge=1, le=40)


class EditBody(BaseModel):
    title: Optional[str] = Field(None, max_length=200)
    description: Optional[str] = Field(None, max_length=400)
    intro: Optional[str] = Field(None, max_length=2000)


@admin.get("/blog")
def blog_list(status: Optional[str] = Query(None), user=Depends(perm("content.write")), db=Depends(D.get_db)):
    return {"posts": B.listing(db, status), "enabled": _enabled(db),
            "auto": bool(S.get(db, "blog.auto_generate")), "base": BR.post_url("").rstrip("/")}


@admin.post("/blog/generate")
def blog_generate(body: GenBody, user=Depends(perm("content.write")), db=Depends(D.get_db)):
    counts = B.generate(db, body.day, limit=body.limit)
    return {"counts": counts, "posts": B.listing(db, None)}


@admin.get("/blog/{slug}")
def blog_get(slug: str, user=Depends(perm("content.write")), db=Depends(D.get_db)):
    p = db.blog_posts.find_one({"slug": slug}, {"_id": 0})
    if not p:
        raise D.err(404, "NO_POST", "That post does not exist.")
    return {"post": p, "url": BR.post_url(slug)}


@admin.get("/blog/{slug}/preview", response_class=Response)
def blog_preview(slug: str, user=Depends(perm("content.write")), db=Depends(D.get_db)):
    """The finished page for a post that is not published yet, so it is reviewed as a reader sees it."""
    p = db.blog_posts.find_one({"slug": slug}, {"_id": 0})
    if not p:
        raise D.err(404, "NO_POST", "That post does not exist.")
    return Response(BR.render_post(db, p), media_type="text/html; charset=utf-8", headers=_DRAFT)


@admin.put("/blog/{slug}")
def blog_edit(slug: str, body: EditBody, user=Depends(perm("content.write")), db=Depends(D.get_db)):
    if not db.blog_posts.find_one({"slug": slug}, {"_id": 1}):
        raise D.err(404, "NO_POST", "That post does not exist.")
    fields = {k: v for k, v in body.model_dump().items() if v is not None}
    try:
        return {"post": B.edit(db, slug, fields, user["email"])}
    except TG.BannedWords as e:
        raise D.err(400, "BANNED_WORDS", str(e))


@admin.post("/blog/{slug}/publish")
def blog_publish(slug: str, user=Depends(perm("content.write")), db=Depends(D.get_db)):
    if not db.blog_posts.find_one({"slug": slug}, {"_id": 1}):
        raise D.err(404, "NO_POST", "That post does not exist.")
    try:
        p = B.publish(db, slug, user["email"])
    except TG.BannedWords as e:
        raise D.err(400, "BANNED_WORDS", str(e))
    return {"post": p, "url": BR.post_url(slug)}


@admin.post("/blog/{slug}/unpublish")
def blog_unpublish(slug: str, user=Depends(perm("content.write")), db=Depends(D.get_db)):
    if not db.blog_posts.find_one({"slug": slug}, {"_id": 1}):
        raise D.err(404, "NO_POST", "That post does not exist.")
    return {"post": B.unpublish(db, slug, user["email"])}


@admin.delete("/blog/{slug}", status_code=204)
def blog_delete(slug: str, user=Depends(perm("content.write")), db=Depends(D.get_db)):
    db.blog_posts.delete_one({"slug": slug})
    return Response(status_code=204)
