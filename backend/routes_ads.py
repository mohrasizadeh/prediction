"""routes_ads.py -- the ad builder's data (admin only).

  GET    /api/admin/ads             the catalogue, the brand kit and the saved designs: one call,
                                    because the screen needs all three before it can draw anything
  POST   /api/admin/ads             save a design
  PUT    /api/admin/ads/{id}        replace one
  DELETE /api/admin/ads/{id}        delete one

The brand kit is read from the LIVE site data, not the draft. An ad goes out to people who see the
published site, so it has to match the published site: a palette being tried out in Site Studio is
not the brand yet. The existing share card hardcoded its colours and has been drawing a palette that
was replaced two redesigns ago (docs/60); nothing here holds a colour of its own.
"""
from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

import admin_queries as AQ
import ads as AD
import deps as D
import site_studio as SS
import textguard

router = APIRouter(prefix="/api/admin/ads")
perm = D.require_perm


def brand_kit(db) -> dict:
    """Colours, type and marks, as the published site has them."""
    d = SS.get_live(db)["data"]
    t = d["theme"]
    body, head = SS.FONTS[t["font_body"]], SS.FONTS[t["font_heading"]]
    return {
        "name": d["brand"]["name"], "tagline": d["brand"]["tagline"],
        "logo_light": d["brand"]["logo_light"], "logo_dark": d["brand"]["logo_dark"],
        "colors": t["colors"],                       # both modes; the builder picks one
        "default_mode": t["default_mode"],
        # The canvas needs a family name it can put in ctx.font, and a file to load before it draws.
        "font": {"body_stack": body["stack"], "heading_stack": head["stack"],
                 "body_family": body["stack"].split(",")[0].strip("'\""),
                 "heading_family": head["stack"].split(",")[0].strip("'\""),
                 "faces": SS.font_faces(d)},
        "radius": SS.RADIUS[t["radius"]],
        "disclaimer": textguard.DISCLAIMER,
    }


class Design(BaseModel):
    template: str = Field(max_length=40)
    size: str = Field(default="square", max_length=40)
    mode: str = Field(default="dark", max_length=10)
    name: str = Field(default="", max_length=80)
    headline: str = Field(default="", max_length=120)
    subhead: str = Field(default="", max_length=200)
    kicker: str = Field(default="", max_length=40)
    cta: str = Field(default="", max_length=40)
    footnote: str = Field(default="", max_length=120)
    fkeys: list[str] = Field(default_factory=list)
    finder_q: str = Field(default="", max_length=300)
    stat_value: str = Field(default="", max_length=16)
    logo: str = Field(default="", max_length=300)
    accent: str = Field(default="", max_length=9)
    slides: list[dict[str, Any]] = Field(default_factory=list)


@router.get("")
def overview(user=Depends(perm("site.read")), db=Depends(D.get_db)):
    return {"catalogue": AD.catalogue(), "brand": brand_kit(db), "designs": AD.listing(db)}


@router.post("")
def create(body: Design, user=Depends(perm("site.write")), db=Depends(D.get_db)):
    try:
        out = AD.save(db, user["email"], body.model_dump())
    except AD.AdError as e:
        raise D.err(400, "BAD_AD", str(e))
    AQ.audit(db, user, "ads.save", out["id"])
    return out


@router.put("/{did}")
def replace(did: str, body: Design, user=Depends(perm("site.write")), db=Depends(D.get_db)):
    try:
        out = AD.save(db, user["email"], body.model_dump(), did=did)
    except AD.AdError as e:
        raise D.err(400, "BAD_AD", str(e))
    AQ.audit(db, user, "ads.save", did)
    return out


@router.delete("/{did}")
def delete(did: str, user=Depends(perm("site.write")), db=Depends(D.get_db)):
    if not AD.remove(db, user["email"], did):
        raise D.err(404, "NOT_FOUND", "That ad no longer exists.")
    AQ.audit(db, user, "ads.delete", did)
    return {"ok": True}
