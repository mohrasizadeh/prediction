"""ads.py -- the ad builder's catalogue and its saved designs (docs/60).

The drawing happens in the browser on a canvas, because there is no server rasteriser in this
project and the fonts and crests are already in front of the browser (docs/60 section 2). So this
module holds the two things the server does own:

  * the CATALOGUE -- which templates exist, which sizes exist, and which fields each template reads.
    One list, so the admin screen cannot offer a template the saved-design validator rejects.
  * the DESIGNS -- an owner's saved ad, so a weekly post is re-rendered rather than rebuilt. Text an
    owner types ends up on a public image, so it goes through textguard exactly as a popup does.

Nothing here draws anything and nothing here is posted anywhere: the export is a download, which was
the owner's instruction and is also the only version that needs no per-network tokens.
"""
from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone

import textguard

MAX_DESIGNS = 60

# id -> (label, what it says, the fields it reads beyond the common ones)
# `needs` drives the screen: "cards" means pick forecasts, "none" means it is all type.
TEMPLATES = {
    "card":    {"label": "Forecast card", "needs": "card",
                "about": "One forecast, whole: the photo, the crest, the position, the market, the likelihood with its range, the tier, and the ten games behind it."},
    "run":     {"label": "The ten games", "needs": "card",
                "about": "The run strip as the hero, with almost no words. A shape a reader recognises before they have read it."},
    "table":   {"label": "Strongest tonight", "needs": "cards",
                "about": "A list of forecasts with crests, strongest first. The densest template and the one most often saved."},
    "fixture": {"label": "Match day", "needs": "card",
                "about": "Two crests, the league mark and the kick-off, with the leading forecast underneath."},
    "finder":  {"label": "Finder question", "needs": "finder",
                "about": "A Forecast Finder search set as type, with how many players answer it and the first few names."},
    "stat":    {"label": "One number", "needs": "none",
                "about": "A single enormous number with one line of context. For a record claim."},
    "quote":   {"label": "Headline", "needs": "none",
                "about": "A headline on the brand gradient with the mark. Messaging, with no data in it."},
    "cover":   {"label": "Carousel cover", "needs": "none",
                "about": "A hook and the brand, built to be the first slide of a carousel."},
}
CARD_TEMPLATES = ("card", "run", "table", "fixture")

# Real platform pixel sizes. Exported at these, never upscaled from a preview.
SIZES = {
    "square":    {"label": "Square 1080 x 1080", "w": 1080, "h": 1080, "about": "Instagram and Facebook feed, and every carousel slide."},
    "portrait":  {"label": "Portrait 1080 x 1350", "w": 1080, "h": 1350, "about": "The tallest a feed post may be, so it fills the most screen."},
    "story":     {"label": "Story 1080 x 1920", "w": 1080, "h": 1920, "about": "Stories and short-video covers, 9 by 16."},
    "landscape": {"label": "Landscape 1200 x 630", "w": 1200, "h": 630, "about": "X, a Facebook link, and the picture a shared link shows."},
    "wide":      {"label": "Wide 1600 x 900", "w": 1600, "h": 900, "about": "Display placements and a video thumbnail."},
}
MODES = ("dark", "light")
# A carousel is a cover, then slides, then a closing headline. Ten is Instagram's limit.
MAX_SLIDES = 10


def catalogue() -> dict:
    return {"templates": [{"id": k, **v} for k, v in TEMPLATES.items()],
            "sizes": [{"id": k, **v} for k, v in SIZES.items()],
            "modes": list(MODES), "max_slides": MAX_SLIDES, "max_designs": MAX_DESIGNS,
            "card_templates": list(CARD_TEMPLATES)}


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class AdError(ValueError):
    """A design the owner cannot save. The route turns it into a 400 with this message."""


def _clean_text(d: dict) -> None:
    """The words rules (docs/03). An ad is the most public thing the product makes, so the same scan
    that guards a popup guards this, and it runs on SAVE rather than on export -- the export happens
    in the browser, where the server cannot see it, so saving is the only honest place to refuse."""
    found = textguard.find({k: v for k, v in d.items() if k in ("name", "headline", "subhead", "kicker", "cta", "footnote")})
    if found:
        raise AdError("Those words are not allowed on anything a visitor sees: " + ", ".join(found)
                      + ". Say what the number is instead.")


def normalise(body: dict) -> dict:
    """Everything the browser needs to redraw this ad, and nothing else. Unknown keys are dropped
    rather than stored, so a design cannot carry a field no template reads."""
    t = str(body.get("template") or "")
    if t not in TEMPLATES:
        raise AdError("Pick one of the templates on the screen.")
    size = str(body.get("size") or "square")
    if size not in SIZES:
        raise AdError("Pick one of the sizes on the screen.")
    mode = str(body.get("mode") or "dark")
    if mode not in MODES:
        mode = "dark"
    out = {
        "template": t, "size": size, "mode": mode,
        "name": str(body.get("name") or "")[:80],
        "headline": str(body.get("headline") or "")[:120],
        "subhead": str(body.get("subhead") or "")[:200],
        "kicker": str(body.get("kicker") or "")[:40],
        "cta": str(body.get("cta") or "")[:40],
        "footnote": str(body.get("footnote") or "")[:120],
        # What the ad is about. `fkeys` are forecast keys, so a saved design redraws with today's
        # number rather than the one that was on screen when it was saved.
        "fkeys": [str(x)[:120] for x in (body.get("fkeys") or [])][:MAX_SLIDES],
        "finder_q": str(body.get("finder_q") or "")[:300],
        "stat_value": str(body.get("stat_value") or "")[:16],
        "logo": str(body.get("logo") or "")[:300],
        "accent": str(body.get("accent") or "")[:9] if re.fullmatch(r"#[0-9A-Fa-f]{6}", str(body.get("accent") or "")) else "",
        "slides": [s for s in (body.get("slides") or []) if isinstance(s, dict)][:MAX_SLIDES],
    }
    if not out["name"]:
        out["name"] = TEMPLATES[t]["label"]
    _clean_text(out)
    return out


def save(db, actor: str, body: dict, did: str | None = None) -> dict:
    d = normalise(body)
    if did:
        if not db.ad_designs.find_one({"_id": did}, {"_id": 1}):
            raise AdError("That ad no longer exists.")
        db.ad_designs.update_one({"_id": did}, {"$set": {**d, "at": utcnow(), "by": actor}})
    else:
        if db.ad_designs.count_documents({}) >= MAX_DESIGNS:
            raise AdError(f"You have {MAX_DESIGNS} saved ads, which is the limit. Delete one first.")
        did = uuid.uuid4().hex
        db.ad_designs.insert_one({"_id": did, **d, "at": utcnow(), "by": actor})
    db.audit_log.insert_one({"actor": actor, "action": "ads.save", "target": did, "at": utcnow()})
    return one(db, did)


def one(db, did: str) -> dict | None:
    r = db.ad_designs.find_one({"_id": did})
    return {**{k: v for k, v in r.items() if k != "_id"}, "id": r["_id"]} if r else None


def listing(db) -> list[dict]:
    return [{**{k: v for k, v in r.items() if k != "_id"}, "id": r["_id"]}
            for r in db.ad_designs.find({}).sort("at", -1).limit(MAX_DESIGNS)]


def remove(db, actor: str, did: str) -> bool:
    gone = db.ad_designs.delete_one({"_id": did}).deleted_count > 0
    if gone:
        db.audit_log.insert_one({"actor": actor, "action": "ads.delete", "target": did, "at": utcnow()})
    return gone
