"""pitch_photos.py -- every picture the site shows, from PitchAPI (docs/19 §9).

PitchAPI carries an `image_url` on `https://cdn.pitchapi.dev/...` for leagues, teams and players
(docs/08 rows 2, 5, 6 and 7). This module turns those three into stored pictures:

    league logo    leagues.image_url, already saved by ingest.sync_leagues   -> 0 extra calls
    club crest     harvested free from /v1/matches/{id} where match_extras
                   already fetches it, else GET /v1/teams/{id}               -> 0 or 1 call per club, once
    player photo   GET /v1/players/{id}                                      -> 1 call per player, once

Each picture is downloaded once and stored in `media` like every other image, so public pages never
link to the provider and the hot-linking question docs/08 B2 leaves open never arises. Anything that
already has a stored picture is skipped. Queued as ingest tasks "league_logo", "team_crest" and
"player_photo": entities with current forecasts first, then everyone else.

This replaces API-Football as the source of pictures. images.py still works and its key, league map
and review list are untouched, but nothing needs them any more.
"""
from __future__ import annotations

from datetime import timezone

from urllib.parse import urlparse

import httpx

import images as IM
from cached_fetch import FOREVER, PitchClient, utcnow

CDN = "cdn.pitchapi.dev"

# collection, ingest task and the id we queue by, per kind of picture
KINDS = {
    "league": {"coll": "leagues", "task": "league_logo"},
    "team": {"coll": "teams", "task": "team_crest"},
    "player": {"coll": "players", "task": "player_photo"},
}


def cdn_url(url) -> str:
    """The URL if it is an https address on PitchAPI's own CDN, else "". Nothing else is fetched."""
    u = urlparse(str(url or ""))
    return str(url) if u.scheme == "https" and u.hostname == CDN else ""


def note_team_images(db, teams: list[dict]) -> int:
    """Save crest URLs that came free with a payload we already fetched. `teams` are provider objects
    with `id` and `image_url` (docs/08 row 7: /v1/matches/{id} carries both clubs with their crests)."""
    n = 0
    for t in teams or []:
        url = cdn_url((t or {}).get("image_url"))
        if not url or not (t or {}).get("id"):
            continue
        n += db.teams.update_one({"ext_id": t["id"], "image_url": {"$ne": url}}, {"$set": {"image_url": url}}).modified_count
    return n


def _queue(db, kind: str, hot: set, limit: int | None = None) -> int:
    """Queue everything of this kind that has no stored picture yet."""
    from ingest import enqueue
    spec = KINDS[kind]
    have = set(db.media.distinct("iid", {"kind": kind}))
    n = 0
    for d in db[spec["coll"]].find({"ext_id": {"$ne": None}, "image_checked_at": None}, {"iid": 1, "ext_id": 1}):
        if d["iid"] in have:
            continue
        enqueue(db, spec["task"], d["ext_id"], priority=7 if d["iid"] in hot else 9, payload={})
        db.ingest_queue.update_one({"task": spec["task"], "key": d["ext_id"], "status": {"$in": ["done", "failed", "skipped"]}},
                                   {"$set": {"status": "pending", "attempts": 0, "next_run_at": utcnow()}})   # retry temporary failures
        n += 1
        if limit and n >= limit:
            break
    return n


def plan(db, force: bool = False) -> int:
    """Queue every league, club and player without a stored picture. Runs at most once a day from the tick."""
    st = db.job_state.find_one({"_id": "player_photo_plan"}) or {}
    at = st.get("at")
    if at is not None and at.tzinfo is None:
        at = at.replace(tzinfo=timezone.utc)
    if not force and at and (utcnow() - at).total_seconds() < 86400:
        return 0
    hot_players = set(db.forecasts.distinct("player_iid", {"is_current": True, "scope": "player"}))
    hot_teams = set(db.forecasts.distinct("team_iid", {"is_current": True}))
    n = _queue(db, "league", set())                 # a handful, and they cost no API call at all
    n += _queue(db, "team", hot_teams)
    n += _queue(db, "player", hot_players)
    db.job_state.update_one({"_id": "player_photo_plan"}, {"$set": {"at": utcnow(), "queued": n}}, upsert=True)
    return n


# players keep their old field name so an install that has already checked them does not check again
_CHECKED_FIELD = {"league": "image_checked_at", "team": "image_checked_at", "player": "photo_checked_at"}


def _image_url(client: PitchClient, kind: str, ext_id: str, stored) -> str | None:
    """The CDN address for this entity, or None when the provider could not be reached.
    A league's address arrived with /v1/leagues and a club's may have arrived with a match we
    already fetched, so neither costs a call when it is already on the record."""
    known = cdn_url(stored)
    if known:
        return known
    if kind == "league":
        d = client.fetch(f"/v1/leagues/{ext_id}", ttl=FOREVER, purpose="league_logo")
    elif kind == "team":
        d = client.fetch(f"/v1/teams/{ext_id}", ttl=FOREVER, purpose="team_crest")
    else:
        d = client.fetch(f"/v1/players/{ext_id}", ttl=FOREVER, purpose="player_photo")
    if d is None:
        return None
    return cdn_url(d.get("image_url"))


def fetch_image(client: PitchClient, kind: str, ext_id: str, http=None) -> str:
    """One picture: find its CDN address, download it once, store the bytes. Never raises."""
    db = client.db
    spec = KINDS[kind]
    d = db[spec["coll"]].find_one({"ext_id": ext_id}, {"iid": 1, "image_url": 1})
    if not d:
        return "skipped"
    checked = lambda: db[spec["coll"]].update_one({"iid": d["iid"]}, {"$set": {_CHECKED_FIELD[kind]: utcnow()}})
    url = _image_url(client, kind, ext_id, d.get("image_url"))
    if url is None:
        return "missing"                             # provider unreachable: retried at the next daily plan
    if not url:
        checked()                                    # it simply has no picture
        return "missing"
    db[spec["coll"]].update_one({"iid": d["iid"], "image_url": {"$ne": url}}, {"$set": {"image_url": url}})
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
        return "missing"                             # temporary: retried at the next daily plan
    checked()
    try:
        IM.store_media(db, kind, d["iid"], r.content, source="pitchapi")
    except IM.ImageError:
        return "bad"
    return "stored"


def fetch_photo(client: PitchClient, ext_id: str, http=None) -> str:
    """Kept so older callers and queued tasks keep working."""
    return fetch_image(client, "player", ext_id, http=http)


def status(db) -> dict:
    out = {}
    for kind, spec in KINDS.items():
        out[kind] = {
            "total": db[spec["coll"]].count_documents({}),
            "stored": len(db.media.distinct("iid", {"kind": kind})),
            "pending": db.ingest_queue.count_documents({"task": spec["task"], "status": "pending"}),
            "checked": db[spec["coll"]].count_documents({_CHECKED_FIELD[kind]: {"$ne": None}}),
        }
    # the shape the Images screen has always read, so it keeps working
    out.update({"players": out["player"]["total"], "with_photo": out["player"]["stored"],
                "pending": sum(k["pending"] for k in (out["league"], out["team"], out["player"])),
                "checked": out["player"]["checked"],
                "from_pitchapi": db.media.count_documents({"source": "pitchapi"}),
                "from_apifootball": db.media.count_documents({"source": "apifootball"})})
    return out
