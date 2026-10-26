"""ratelimit.py -- fixed-window rate limiter kept in MongoDB, so every worker shares the count.

    ok, retry_after = hit(db, "login:ip:1.2.3.4", limit=10, window_s=60)

One document per key per window. `expires_at` has a TTL index, so old windows delete themselves.
Fixed windows let a caller send up to 2x the limit across a window edge. That is fine for
abuse control. For hard caps use a quota counter (plans.py), not this.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from pymongo import ReturnDocument


class RateLimited(Exception):
    def __init__(self, retry_after: int):
        super().__init__("rate limited")
        self.retry_after = retry_after


def hit(db, key: str, limit: int, window_s: int, now: datetime | None = None) -> tuple[bool, int]:
    """Count one request. Returns (allowed, seconds_until_the_window_resets)."""
    now = now or datetime.now(timezone.utc)
    ts = int(now.timestamp())
    bucket = ts // window_s
    reset_in = (bucket + 1) * window_s - ts
    doc = db.rate_limits.find_one_and_update(
        {"_id": f"{key}:{bucket}"},
        {"$inc": {"n": 1}, "$setOnInsert": {"expires_at": now + timedelta(seconds=window_s + 60)}},
        upsert=True, return_document=ReturnDocument.AFTER,
    )
    return doc["n"] <= limit, reset_in


def check(db, key: str, limit: int, window_s: int, now: datetime | None = None) -> None:
    ok, retry = hit(db, key, limit, window_s, now)
    if not ok:
        raise RateLimited(retry)


def peek(db, key: str, window_s: int, now: datetime | None = None) -> int:
    now = now or datetime.now(timezone.utc)
    doc = db.rate_limits.find_one({"_id": f"{key}:{int(now.timestamp()) // window_s}"})
    return doc["n"] if doc else 0
