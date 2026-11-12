"""purge.py -- clear the football data and nothing else, for a fresh start on a new provider. docs/83.

## Why not just drop the database

Asking the host to discard the database and start over would take the football data with it, which
is what is wanted — and also every one of these, which is not:

  * `users`, `sessions`, `auth_tokens` — the owner's own sign-in, the staff, anyone who has signed up
  * `settings`, `settings_history` — every tuned engine threshold, every copy change, 300 values
  * `provider_keys` — the keys themselves, so the first thing after the drop would be re-entering them
  * `site_assets`, `site_asset_chunks` — the owner's own uploads, used by the Site Studio, the ad
    builder and the blog. Not to be confused with `media`, which holds only provider crests, logos
    and player photos (see below)
  * `site_assets`, `site_versions`, `content_pages` — the whole Site Studio, built by hand
  * `plans`, `subscriptions`, `payments`, `coupons` — billing, which is tied to live Stripe objects.
    Dropping our side does not drop theirs, so the two would disagree
  * `blog_posts`, `popups`, `announcements`, the e-mail templates and the waitlist

A drop therefore costs a re-setup of the product to clear data that lives in about thirty known
collections. So this does the targeted thing instead, and names every collection it will touch.

## The three groups

`FOOTBALL`  what a provider gave us: leagues down to player-match rows, plus the caches, the call
            log and the id maps. All of it is re-fetchable, and all of it is keyed on provider ids
            that change with the provider (docs/78 §5.1), so it cannot be kept.

`DERIVED`   what the engine computed FROM that: forecasts, their outcomes, run and gate records, the
            fitted calibration map. Keeping these beside new football data would leave rows pointing
            at ids that no longer exist, and a calibration map fitted on forecasts that are gone.

`MINE`      what a person created and pointed AT the football data: follows, notes, saved cards,
            combos, alerts. Cleared only when asked for explicitly, because it is the one group
            nobody can re-fetch.

Everything else is left alone, and `unknown()` lists any collection this module has never heard of
so a new one cannot be silently missed in either direction.

## Why the images go too, reversing docs/79 §1

docs/79 §1 said to keep them: pixels are provider-neutral and re-downloading is pure cost. That was
right about the BYTES and wrong about the KEY. `media` rows are keyed `{kind, iid}` where `iid` is
OUR integer id (`images.py` line 247, read back in `routes_images.py` line 39). Clear the entities
and re-ingest, and a new club takes an id an old club used to hold — so it inherits that club's
crest. A real badge on the wrong team, which is worse than no badge, because nothing looks broken.

The owner found exactly this and reported wrong league badges.

The cost that justified keeping them has also gone. On PitchAPI each image needed an API call to
find (about 22 a league, docs/19). On API-Football the logo is a URL on the entity itself and image
requests do not count against the daily quota at all (docs/82 §9), so re-downloading is close to
free.

`site_assets` is a different collection and is kept: those are the owner's own uploads.
"""
from __future__ import annotations

from datetime import datetime, timezone

# ------------------------------------------------------------------ the groups
FOOTBALL = [
    # the entities, and the counters that issue their integer ids
    "leagues", "seasons", "teams", "players", "matches",
    # what each match produced
    "player_match_stats", "team_match_stats", "lineups", "match_events",
    "match_context", "match_probs",
    # per-league and per-club models built from matches
    "referee_stats", "team_styles", "club_calendar", "data_coverage", "availability",
    # the live mirror
    "live_fixtures", "live_events", "live_lineups", "live_stats",
    # provider plumbing: responses, the call log, the id maps
    "api_cache", "api_call_log", "image_api_cache", "image_api_calls", "image_map", "image_runs",
    # THE IMAGES THEMSELVES. See "Why the images go too" below -- this reverses docs/79 §1.
    "media",
    "sportapi_cache", "sportapi_calls", "sportapi_dates", "sportapi_state", "sportapi_team_map",
    # the ingest's own queue and complaints
    "ingest_queue", "ingest_issues",
]

DERIVED = ["forecasts", "forecast_outcomes", "engine_runs", "engine_gates", "engine_calibration"]

MINE = ["follows", "follow_alerts", "notes", "saved_forecasts", "combos", "booking_alerts"]

# NOT reset, and the reason is the bug that made the owner ask for this.
#
# Resetting them would make the first new league iid 1 again, which is tidy and wrong. Our integer
# ids are the key for things that survive a purge, and a REUSED id does not break a lookup -- it
# silently resolves to a different entity. That is how a crest ends up on the wrong club: a real
# badge, confidently wrong, which is worse than a missing one.
#
# Leaving them to climb costs nothing. A surviving row that points at a cleared entity becomes a
# dangling id, which resolves to nothing and shows as missing. Dangling is recoverable; reused is
# not, because nothing downstream can tell it happened.
#
# This also protects the collections a purge deliberately keeps (`MINE`: follows, notes, saved
# cards) when it is run without them, and any collection added later that keys on an iid.
MONOTONIC_IDS = ["leagues", "seasons", "teams", "players", "matches"]

# Breaker and tick state for the feeds. Not the whole of `job_locks`/`job_state`, which also hold
# locks for e-mail and billing jobs that have nothing to do with football.
JOB_KEYS = ["pitch_breaker", "af_breaker", "apifootball_quota", "sportapi_tick", "live_tick"]

# Named so that `unknown()` can tell "deliberately kept" from "never heard of". Keeping this list
# honest is the point of the whole module.
KEPT = [
    "users", "sessions", "auth_tokens", "auth_log", "settings", "settings_history", "provider_keys",
    "site_assets", "site_asset_chunks", "site_versions", "site_state", "site_counter",
    "content_pages", "blog_posts", "popups", "popup_stats", "announcements", "social_posts",
    "ad_designs", "plans", "subscriptions", "payments", "coupons", "newsletter", "waitlist_sends",
    "email_campaigns", "email_log", "email_suppressions", "email_templates", "contact_messages",
    "admin_alerts", "admin_notes", "audit_log", "app_logs", "events", "finder_usage", "rate_limits",
    "integration_jobs", "webhook_deliveries", "webhook_endpoints", "webhook_events", "webhook_outbox",
    "cron_runs", "job_runs", "job_requests", "job_locks", "job_state", "counters",
]


def groups(include_mine: bool = False) -> list[str]:
    return FOOTBALL + DERIVED + (MINE if include_mine else [])


def unknown(db) -> list[str]:
    """Collections this module has never been told about.

    A collection added later is the failure case in both directions: left out of FOOTBALL it
    survives a fresh start and poisons the new data with old ids; left out of KEPT it gets cleared
    when it should not. So neither list is allowed to go stale quietly — the admin screen shows
    whatever turns up here and refuses to guess which group it belongs in.
    """
    known = set(FOOTBALL) | set(DERIVED) | set(MINE) | set(KEPT)
    return sorted(c for c in db.list_collection_names() if c not in known)


# ------------------------------------------------------------------ the plan
def plan(db, include_mine: bool = False) -> dict:
    """What a purge would do, counted, without doing any of it.

    This is what the screen shows before the owner types the confirmation, so every number here is
    read from the database rather than estimated.
    """
    rows, total = [], 0
    for name in groups(include_mine):
        n = db[name].count_documents({}) if name in db.list_collection_names() else 0
        group = "football" if name in FOOTBALL else "derived" if name in DERIVED else "mine"
        rows.append({"collection": name, "documents": n, "group": group})
        total += n
    kept = []
    for name in KEPT:
        if name in db.list_collection_names():
            n = db[name].count_documents({})
            if n:
                kept.append({"collection": name, "documents": n})
    return {
        "clear": rows, "total": total,
        "keep": sorted(kept, key=lambda r: -r["documents"]),
        "monotonic_ids": MONOTONIC_IDS, "job_keys": JOB_KEYS,
        "unknown": unknown(db),
        "include_mine": include_mine,
        "mine_total": sum(r["documents"] for r in rows if r["group"] == "mine"),
    }


# ------------------------------------------------------------------ doing it
CONFIRM = "DELETE FOOTBALL DATA"


def run(db, confirm: str, include_mine: bool = False, actor: str = "") -> dict:
    """Clear the groups. `confirm` must be CONFIRM exactly.

    Deletes documents rather than dropping collections, so indexes built by `mongo_init` survive and
    the app does not need a restart to work afterwards.
    """
    if confirm != CONFIRM:
        raise ValueError(f"Type {CONFIRM!r} to confirm.")
    before = plan(db, include_mine)
    deleted = {}
    for name in groups(include_mine):
        if name in db.list_collection_names():
            deleted[name] = db[name].delete_many({}).deleted_count
    # The counters are deliberately left alone: see MONOTONIC_IDS.
    for key in JOB_KEYS:
        db.job_locks.delete_one({"_id": key})
        db.job_state.delete_one({"_id": key})
    # The pause a refused key or a spent budget may have left behind: a fresh start starts unpaused.
    db.settings.update_one({"key": "ingest.paused_reason"},
                           {"$set": {"value": "", "updated_at": datetime.now(timezone.utc)}}, upsert=True)
    row = {"at": datetime.now(timezone.utc), "actor": actor, "include_mine": include_mine,
           "documents": sum(deleted.values()), "by_collection": deleted,
           "expected": before["total"]}
    db.admin_notes.insert_one({"kind": "purge", **row})      # a record of it, in a collection we keep
    return row
