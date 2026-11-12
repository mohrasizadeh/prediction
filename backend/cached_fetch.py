"""cached_fetch.py -- the ONLY place that talks to PitchAPI.

Rules (see 07_ingest_and_caching.md):
  1. Look in `api_cache` first. A fresh row costs zero calls.
  2. Respect the daily call budget, the request rate and the circuit breaker.
  3. Log every real call in `api_call_log`.
  4. Unwrap the {data | error} envelope here and nowhere else.
  5. Never use the vendor SDKs: they retry on their own and hide calls from the budget.
"""
from __future__ import annotations

import hashlib
import json
import zlib
import threading
import time
from datetime import datetime, timedelta, timezone

import httpx

import settings_store as S
from security import get_provider_key

BASE_URL = "https://api.pitchapi.dev"
FOREVER = None   # ttl value meaning "never expires" (finished matches, finished seasons)


def _retry_after(value, default: float, cap: float = 10.0) -> float:
    """Seconds to wait from a Retry-After header. Seconds or an HTTP date; anything odd falls back to the default.
    Capped, so one answer cannot hold the job lock for an hour (docs/36 H4)."""
    try:
        wait = float(value)
    except (TypeError, ValueError):
        try:
            from email.utils import parsedate_to_datetime
            wait = (parsedate_to_datetime(value) - datetime.now(timezone.utc)).total_seconds()
        except Exception:
            wait = default
    return max(0.0, min(wait, cap))


class PitchError(Exception):
    def __init__(self, code, status, message=""):
        super().__init__(f"{status} {code} {message}")
        self.code, self.status = code, status


class Unauthorized(PitchError): ...
class NotFound(PitchError): ...
class BudgetExhausted(Exception): ...
class BreakerOpen(Exception): ...


class Disabled(BreakerOpen):
    """PitchAPI is switched off in admin.

    A subclass of BreakerOpen on purpose: jobs.py already catches that, so switching the provider
    off stops it spending without a new exception to thread through every caller. The distinct type
    is so the admin can say "off" rather than "breaker open", which would read like a fault.
    """


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _aware(dt):
    """Mongo returns naive datetimes (UTC). Make them aware before comparing."""
    return dt if dt is None or dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def next_iid(db, name: str) -> int:
    """Integer ids for the engine (it needs ints). One counter per collection."""
    from pymongo import ReturnDocument
    doc = db.counters.find_one_and_update({"_id": name}, {"$inc": {"seq": 1}}, upsert=True,
                                          return_document=ReturnDocument.AFTER)
    return int(doc["seq"])


def _pack(data) -> bytes:
    """Compress the response. Keeps the 500 MB free database small and avoids
    Mongo field-name limits (PitchAPI uses display labels as object keys)."""
    return zlib.compress(json.dumps(data, separators=(",", ":")).encode(), 6)


def _unpack(blob) -> object:
    return json.loads(zlib.decompress(bytes(blob)).decode())


def cache_key(path: str, params: dict | None) -> str:
    q = json.dumps(sorted((params or {}).items()), separators=(",", ":"))
    return hashlib.sha256(f"GET {path}?{q}".encode()).hexdigest()


class PitchClient:
    def __init__(self, db, http: httpx.Client | None = None, sleep=time.sleep):
        self.db = db
        self.http = http or httpx.Client(base_url=BASE_URL, timeout=30.0)
        self._sleep = sleep
        self._last = 0.0
        self._lock = threading.Lock()
        self.calls_made = 0          # real calls in this object's lifetime (tests read this)

    # ---------------------------------------------------------------- guards
    def _calls_today(self) -> int:
        start = utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        return self.db.api_call_log.count_documents({"at": {"$gte": start}})

    def _check_guards(self) -> None:
        # The off switch. Checked before the breaker and the budget, because an off provider should
        # say so plainly rather than report whatever other state it happens to be in (docs/84).
        if not S.get(self.db, "pitchapi.enabled"):
            raise Disabled("PitchAPI is switched off in admin")
        br = self.db.job_locks.find_one({"_id": "pitch_breaker"})
        if br and _aware(br["expires_at"]) > utcnow():
            raise BreakerOpen(br.get("reason", "breaker open"))
        if self._calls_today() >= S.get(self.db, "ingest.daily_call_budget"):
            raise BudgetExhausted("daily call budget spent")

    def _trip_breaker(self, reason: str) -> None:
        mins = S.get(self.db, "ingest.breaker_minutes")
        self.db.job_locks.update_one({"_id": "pitch_breaker"},
                                     {"$set": {"reason": reason, "expires_at": utcnow() + timedelta(minutes=mins)}},
                                     upsert=True)

    def _pace(self) -> None:
        gap = 1.0 / max(S.get(self.db, "ingest.rps"), 0.1)
        with self._lock:
            wait = self._last + gap - time.monotonic()
            if wait > 0:
                self._sleep(wait)
            self._last = time.monotonic()

    # ----------------------------------------------------------------- calls
    def _real_call(self, path, params, purpose):
        key = get_provider_key(self.db, "pitchapi", "PITCH_KEY")
        if not key:
            raise Unauthorized("NO_KEY", 401, "no PitchAPI key set in admin")
        attempts_429 = 0
        attempts_5xx = 0
        while True:
            self._check_guards()
            self._pace()
            t0 = time.monotonic()
            try:
                r = self.http.get(path, params=params, headers={"X-API-KEY": key})
            except httpx.TransportError as e:
                self._log(path, 0, t0, purpose, "transport")
                attempts_5xx += 1
                if attempts_5xx > 3:
                    raise PitchError("TRANSPORT", 0, str(e))
                self._sleep(2 ** attempts_5xx)
                continue
            self.calls_made += 1
            code = None
            try:
                body = r.json()
            except Exception:
                body = {}
            if isinstance(body, dict) and "error" in body:
                code = (body["error"] or {}).get("code")
            self._log(path, r.status_code, t0, purpose, code)
            if r.status_code == 200 and "data" in body:
                return body["data"]
            if r.status_code == 401:
                self.db.settings.update_one({"key": "ingest.paused_reason"},
                                            {"$set": {"value": "PitchAPI key rejected (401)", "updated_at": utcnow()}},
                                            upsert=True)
                self._trip_breaker("401 unauthorized")
                raise Unauthorized(code or "UNAUTHORIZED", 401)
            if r.status_code == 429:
                attempts_429 += 1
                if attempts_429 > 3:
                    self._trip_breaker("429 rate limit")
                    raise BreakerOpen("429 rate limit")
                self._sleep(_retry_after(r.headers.get("Retry-After"), 2 ** attempts_429))
                continue
            if r.status_code == 404:
                raise NotFound(code or "RESOURCE_NOT_FOUND", 404)
            if r.status_code >= 500:
                attempts_5xx += 1
                if attempts_5xx > 3:
                    raise PitchError(code or "INTERNAL_SERVER_ERROR", r.status_code)
                self._sleep(2 ** attempts_5xx)
                continue
            raise PitchError(code or "UNKNOWN", r.status_code)   # 400 INVALID_PARAMETER etc: bug, no retry

    def _log(self, path, status, t0, purpose, code):
        self.db.api_call_log.insert_one({"at": utcnow(), "path": path, "status": status, "code": code,
                                         "ms": int((time.monotonic() - t0) * 1000), "purpose": purpose})

    def fetch(self, path: str, params: dict | None = None, ttl: timedelta | None = FOREVER,
              purpose: str = "", force: bool = False):
        """Return `data`. ttl=None means cache forever. Raises NotFound for a cached 404."""
        key = cache_key(path, params)
        now = utcnow()
        doc = self.db.api_cache.find_one({"_id": key})
        if doc and not force:
            exp = _aware(doc.get("expires_at"))
            if exp is None or exp > now:
                if doc.get("error_code"):
                    raise NotFound(doc["error_code"], 404)
                return _unpack(doc["data_z"])
        try:
            data = self._real_call(path, params, purpose)
        except NotFound as e:
            mins = S.get(self.db, "cache.ttl.error_minutes")
            self.db.api_cache.replace_one({"_id": key}, {"_id": key, "path": path, "params": params or {},
                                                         "error_code": e.code, "fetched_at": now,
                                                         "expires_at": now + timedelta(minutes=mins)}, upsert=True)
            raise
        except (BreakerOpen, BudgetExhausted, PitchError):
            if doc and "data_z" in doc and not doc.get("error_code"):
                self.db.ingest_issues.insert_one({"at": now, "kind": "stale_served", "path": path, "resolved": False})
                return _unpack(doc["data_z"])   # stale-if-error: better than a blank screen
            raise
        row = {"_id": key, "path": path, "params": params or {}, "data_z": _pack(data), "fetched_at": now}
        if ttl is not None:
            row["expires_at"] = now + ttl
        self.db.api_cache.replace_one({"_id": key}, row, upsert=True)
        return data
