"""pitch_photos.py -- player photos from PitchAPI (GET /v1/players/{id} -> image_url on cdn.pitchapi.dev).

One call per player, cached forever; the picture is downloaded once and stored in `media` like every other image,
so public pages never link to the provider. Players who already have a stored photo are skipped.
Queued as ingest task "player_photo": players with current forecasts first, then everyone else.
"""
from __future__ import annotations

from urllib.parse import urlparse

import httpx

import images as IM
from cached_fetch import FOREVER, PitchClient, utcnow

CDN = "cdn.pitchapi.dev"


def plan(db, force: bool = False) -> int:
    """Queue every player without a stored photo. Runs at most once a day from the tick."""
    from ingest import enqueue
    st = db.job_state.find_one({"_id": "player_photo_plan"}) or {}
    if not force and st.get("at") and (utcnow() - st["at"]).total_seconds() < 86400:
        return 0
    have = set(db.media.distinct("iid", {"kind": "player"}))
    hot = set(db.forecasts.distinct("player_iid", {"is_current": True, "scope": "player"}))
    n = 0
    for p in db.players.find({"ext_id": {"$ne": None}, "photo_checked_at": None}, {"iid": 1, "ext_id": 1}):
        if p["iid"] in have:
            continue
        enqueue(db, "player_photo", p["ext_id"], priority=7 if p["iid"] in hot else 9, payload={})
        n += 1
    db.job_state.update_one({"_id": "player_photo_plan"}, {"$set": {"at": utcnow(), "queued": n}}, upsert=True)
    return n


def fetch_photo(client: PitchClient, ext_id: str, http=None) -> str:
    db = client.db
    p = db.players.find_one({"ext_id": ext_id}, {"iid": 1})
    if not p:
        return "skipped"
    d = client.fetch(f"/v1/players/{ext_id}", ttl=FOREVER, purpose="player_photo")
    url = (d or {}).get("image_url") or ""
    db.players.update_one({"iid": p["iid"]}, {"$set": {"photo_checked_at": utcnow()}})
    if urlparse(url).scheme != "https" or urlparse(url).hostname != CDN:
        return "missing"
    own = http is None
    http = http or httpx.Client(timeout=15, follow_redirects=False)
    try:
        r = http.get(url, headers={"accept": "image/*"})
    except httpx.HTTPError:
        return "missing"
    finally:
        if own:
            http.close()
    if r.status_code != 200:
        return "missing"
    try:
        IM.store_media(db, "player", p["iid"], r.content, source="pitchapi")
    except IM.ImageError:
        return "bad"
    return "stored"


def status(db) -> dict:
    return {"players": db.players.count_documents({}), "with_photo": len(db.media.distinct("iid", {"kind": "player"})),
            "pending": db.ingest_queue.count_documents({"task": "player_photo", "status": "pending"}),
            "checked": db.players.count_documents({"photo_checked_at": {"$ne": None}})}
