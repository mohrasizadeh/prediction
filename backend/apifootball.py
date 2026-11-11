"""apifootball.py -- the ONLY place that talks to API-Football (v3.football.api-sports.io). docs/81.

Replaces cached_fetch.py (PitchAPI) and sportapi.py (live). One provider for statistics, fixtures,
lineups, live, injuries and images.

Rules, the same five cached_fetch.py had, for the same reasons:
  1. Look in `api_cache` first. A fresh row costs zero calls.
  2. Respect the daily budget, the per-minute limit and the circuit breaker.
  3. Log every real call in `api_call_log`.
  4. Unwrap the {response | errors} envelope here and nowhere else.
  5. No vendor SDK: it would retry on its own and hide calls from the budget.

Three things about this provider that the code has to know and that nothing else should have to:

  * ERRORS COME BACK AS HTTP 200. A bad key, a plan that does not cover a season, a wrong
    parameter: all of them are `200 OK` with a populated `errors`, which is a LIST when empty and
    an OBJECT when not. `_unwrap` is the only place that knows this.

  * THEIR COUNT WINS OVER OURS. Every answer carries the remaining daily and per-minute quota in
    headers. We store both; if the provider says zero we stop, whatever our own counter thinks.
    docs/19 settled this for the image sync and it is the same rule here.

  * A SPIKE CAN GET US FIREWALLED, not throttled. Their rate-limit policy says abnormal traffic
    may be blocked "without prior notice", permanently. So pacing is not an optimisation here, and
    `_pace` honours the per-minute header rather than only our own requests-per-second setting.

`/status` does not count against the quota, which makes it the right call for the admin key test
and the health panel. It is the only call that bypasses the budget guard.
"""
from __future__ import annotations

import hashlib
import json
import threading
import time
import zlib
from datetime import datetime, timedelta, timezone

import httpx

import settings_store as S
from security import get_provider_key

BASE_URL = "https://v3.football.api-sports.io"
MEDIA_URL = "https://media.api-sports.io/football"
PROVIDER = "apifootball"
FOREVER = None          # ttl meaning "never expires": a finished match never changes


# ------------------------------------------------------------------ the match status vocabulary
# Their documented list, in full. Unlike SportAPI (docs/23) this vocabulary IS documented, so the
# three sets below are facts rather than guesses -- but the fallback stays: a word we have never
# seen counts as in play, because that is what keeps a forecast ticking through a period nobody
# told us about (docs/42).
FINAL = {"FT", "AET", "PEN"}                       # over, with a result
DEAD = {"PST", "CANC", "ABD", "AWD", "WO"}         # called off, or never played
NOT_YET = {"TBD", "NS"}                            # not started
IN_PLAY = {"1H", "HT", "2H", "ET", "BT", "P", "SUSP", "INT", "LIVE"}
NOT_PLAYING = FINAL | DEAD | NOT_YET


def in_play(status) -> bool:
    """Is this match being played right now? The one rule, for every screen (docs/42)."""
    return bool(status) and str(status).upper() not in NOT_PLAYING


def is_final(status) -> bool:
    return bool(status) and str(status).upper() in FINAL


def is_over(status) -> bool:
    """Finished, or called off and never coming back."""
    return bool(status) and str(status).upper() in (FINAL | DEAD)


def stale_not_started(status, kickoff, now=None, hours: float = 3.0) -> bool:
    """A match that says NS long after its kick-off.

    Their own documentation: a competition without livescore "remains in NS and will be updated in
    the minutes/hours following the match (this can take up to 48 hours)". So after kick-off NS
    does not mean scheduled, it means UNKNOWN -- and treating it as scheduled would park a played
    match in the upcoming list for two days and never ingest its statistics. Anything this returns
    True for is re-checked, not believed.
    """
    if str(status).upper() not in NOT_YET or kickoff is None:
        return False
    now = now or utcnow()
    ko = kickoff if kickoff.tzinfo else kickoff.replace(tzinfo=timezone.utc)
    return (now - ko) > timedelta(hours=hours)


# ------------------------------------------------------------------ plumbing
class APIFootballError(Exception):
    def __init__(self, kind: str, detail: str = ""):
        super().__init__(f"{kind}: {detail}" if detail else kind)
        self.kind, self.detail = kind, detail


class Unauthorized(APIFootballError): ...
class PlanLimited(APIFootballError): ...      # the key is fine; this league/season is not on the plan
class BudgetExhausted(Exception): ...
class BreakerOpen(Exception): ...


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _aware(dt):
    return dt if dt is None or dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _pack(data) -> bytes:
    return zlib.compress(json.dumps(data, separators=(",", ":")).encode(), 6)


def _unpack(blob):
    return json.loads(zlib.decompress(bytes(blob)).decode())


def cache_key(path: str, params: dict | None) -> str:
    q = json.dumps(sorted((params or {}).items()), separators=(",", ":"))
    return hashlib.sha256(f"GET {path}?{q}".encode()).hexdigest()


def _errors(body: dict) -> dict:
    """Their `errors` is `[]` when there are none and an object when there are. One shape out."""
    e = body.get("errors")
    if isinstance(e, dict):
        return {k: v for k, v in e.items() if v}
    if isinstance(e, list) and e:
        return {"error": "; ".join(str(x) for x in e)}
    return {}


class Client:
    def __init__(self, db, http: httpx.Client | None = None, sleep=time.sleep):
        self.db = db
        self.http = http or httpx.Client(base_url=BASE_URL, timeout=30.0)
        self._sleep = sleep
        self._last = 0.0
        self._lock = threading.Lock()
        self.calls_made = 0          # real calls in this object's lifetime (tests read this)
        self._paging = None          # `paging` of the last real call, for fetch_all

    # ------------------------------------------------------------- guards
    def _calls_today(self) -> int:
        start = utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        return self.db.api_call_log.count_documents({"at": {"$gte": start}})

    def quota(self) -> dict:
        """What the provider last told us about our quota. Their numbers, not ours."""
        return self.db.job_state.find_one({"_id": "apifootball_quota"}) or {}

    def _check_guards(self) -> None:
        br = self.db.job_locks.find_one({"_id": "af_breaker"})
        if br and _aware(br["expires_at"]) > utcnow():
            raise BreakerOpen(br.get("reason", "breaker open"))
        q = self.quota()
        # Their count wins over ours (docs/19). `day_remaining` is only trusted for today.
        if q.get("day") == utcnow().strftime("%Y-%m-%d") and q.get("day_remaining") is not None:
            if int(q["day_remaining"]) <= 0:
                raise BudgetExhausted("API-Football says the daily quota is spent")
        if self._calls_today() >= S.get(self.db, "ingest.daily_call_budget"):
            raise BudgetExhausted("our own daily call budget is spent")

    def _trip_breaker(self, reason: str) -> None:
        mins = S.get(self.db, "ingest.breaker_minutes")
        self.db.job_locks.update_one({"_id": "af_breaker"},
                                     {"$set": {"reason": reason, "expires_at": utcnow() + timedelta(minutes=mins)}},
                                     upsert=True)

    def _pace(self) -> None:
        """Our own requests-per-second floor, plus a full stop when the provider's per-minute
        allowance is gone. The second half matters more than the first: their firewall reacts to
        spikes, and a burst that empties the minute bucket is exactly a spike."""
        q = self.quota()
        if q.get("min_remaining") is not None and int(q["min_remaining"]) <= 0:
            self._sleep(float(S.get(self.db, "apifootball.minute_cooldown_s")))
        gap = 1.0 / max(S.get(self.db, "ingest.rps"), 0.1)
        with self._lock:
            wait = self._last + gap - time.monotonic()
            if wait > 0:
                self._sleep(wait)
            self._last = time.monotonic()

    def _note_quota(self, headers) -> None:
        def h(name):
            v = headers.get(name)
            try:
                return int(v)
            except (TypeError, ValueError):
                return None
        row = {"day": utcnow().strftime("%Y-%m-%d"), "at": utcnow(),
               "day_limit": h("x-ratelimit-requests-limit"),
               "day_remaining": h("x-ratelimit-requests-remaining"),
               "min_limit": h("X-RateLimit-Limit"),
               "min_remaining": h("X-RateLimit-Remaining")}
        self.db.job_state.update_one({"_id": "apifootball_quota"},
                                     {"$set": {k: v for k, v in row.items() if v is not None or k in ("day", "at")}},
                                     upsert=True)

    # -------------------------------------------------------------- calls
    def _unwrap(self, body: dict, path: str) -> list:
        """`response` out, or the right exception. The only place that knows an API-Football error
        arrives with HTTP 200."""
        errs = _errors(body)
        if errs:
            blob = "; ".join(f"{k}: {v}" for k, v in errs.items())
            if "token" in errs or "Bug" in blob:
                self.db.settings.update_one({"key": "ingest.paused_reason"},
                                            {"$set": {"value": f"API-Football rejected the key ({blob})",
                                                      "updated_at": utcnow()}}, upsert=True)
                self._trip_breaker("key rejected")
                raise Unauthorized("token", blob)
            if "plan" in errs or "subscription" in errs:
                raise PlanLimited("plan", blob)
            if "requests" in errs:
                self._trip_breaker("quota reached")
                raise BudgetExhausted(blob)
            raise APIFootballError("errors", f"{path}: {blob}")
        pg = body.get("paging") or {}
        self._paging = {"current": pg.get("current"), "total": pg.get("total")}
        return body.get("response") or []

    def _real_call(self, path: str, params: dict, purpose: str, free: bool = False) -> list:
        key = get_provider_key(self.db, PROVIDER, env_fallback="APIFOOTBALL_KEY")
        if not key:
            raise Unauthorized("no_key", "no API-Football key saved (Admin > Keys)")
        attempts = 0
        while True:
            if not free:
                self._check_guards()
            self._pace()
            t0 = time.monotonic()
            try:
                # ONLY x-apisports-key. Their documentation is explicit that an unexpected header
                # is answered with an error, so nothing else is added here.
                r = self.http.get(path, params=params, headers={"x-apisports-key": key})
            except httpx.TransportError as e:
                self._log(path, 0, t0, purpose, "transport")
                attempts += 1
                if attempts > 3:
                    raise APIFootballError("transport", str(e))
                self._sleep(2 ** attempts)
                continue
            self.calls_made += 1
            self._note_quota(r.headers)
            try:
                body = r.json()
            except Exception:
                body = {}
            self._log(path, r.status_code, t0, purpose, (list(_errors(body)) or [None])[0])
            if r.status_code == 429:
                attempts += 1
                if attempts > 3:
                    self._trip_breaker("429 rate limit")
                    raise BreakerOpen("429 rate limit")
                self._sleep(2 ** attempts)
                continue
            if r.status_code >= 500:
                attempts += 1
                if attempts > 3:
                    raise APIFootballError("server", f"{r.status_code} on {path}")
                self._sleep(2 ** attempts)
                continue
            if r.status_code == 204:
                return []
            if r.status_code != 200:
                raise APIFootballError("http", f"{r.status_code} on {path}")
            return self._unwrap(body, path)

    def _log(self, path, status, t0, purpose, code):
        self.db.api_call_log.insert_one({"at": utcnow(), "path": path, "status": status, "code": code,
                                         "ms": int((time.monotonic() - t0) * 1000), "purpose": purpose,
                                         "provider": PROVIDER})

    # ------------------------------------------------------------- public
    def fetch(self, path: str, params: dict | None = None, ttl: timedelta | None = FOREVER,
              purpose: str = "", force: bool = False) -> list:
        """One page of `response`, cached. ttl=None caches forever (a finished match)."""
        ck = cache_key(path, params)
        now = utcnow()
        doc = self.db.api_cache.find_one({"_id": ck})
        if doc and not force:
            exp = _aware(doc.get("expires_at"))
            if exp is None or exp > now:
                self._paging = doc.get("paging")       # a cached page still knows if another follows
                return _unpack(doc["data_z"])
        self._paging = None
        try:
            data = self._real_call(path, params or {}, purpose)
        except (BreakerOpen, BudgetExhausted, PlanLimited, APIFootballError):
            if doc and "data_z" in doc:
                self.db.ingest_issues.insert_one({"at": now, "kind": "stale_served", "path": path,
                                                  "detail": str(params or {}), "resolved": False})
                return _unpack(doc["data_z"])     # stale-if-error beats a blank screen
            raise
        row = {"_id": ck, "path": path, "params": params or {}, "data_z": _pack(data), "fetched_at": now,
               "paging": self._paging}
        if ttl is not None:
            row["expires_at"] = now + ttl
        self.db.api_cache.replace_one({"_id": ck}, row, upsert=True)
        return data

    def fetch_all(self, path: str, params: dict | None = None, ttl: timedelta | None = FOREVER,
                  purpose: str = "", max_pages: int = 50) -> list:
        """Every page of a paginated endpoint. Each page is one call against the quota, so this is
        used only where the endpoint really pages (`/players`, `/players/profiles`)."""
        params = dict(params or {})
        out, page = [], 1
        while page <= max_pages:
            params["page"] = page
            out.extend(self.fetch(path, params, ttl=ttl, purpose=purpose))
            total = (self._paging or {}).get("total")
            if not total or page >= int(total):
                break
            page += 1
        return out

    def status(self) -> dict:
        """Account, subscription and today's usage. Free: it does not count against the quota, so
        it is what the admin key test and the health panel call."""
        rows = self._real_call("/status", {}, "status", free=True)
        return rows[0] if isinstance(rows, list) and rows else (rows or {})


# ------------------------------------------------------------------ coverage
def coverage(client: Client, league_id: int, season: int) -> dict:
    """What this competition actually carries, in that season, on THIS plan.

    `/leagues?id=` returns a coverage block per season. Their own warning matters and is why this
    is read per league rather than assumed once: "The coverage of a competition can vary from
    season to season and values set to True do not guarantee 100% data availability."

    Returns a flat dict: fixtures_events, fixtures_lineups, fixtures_statistics,
    players_statistics, standings, players, injuries, plus `found`.
    """
    rows = client.fetch("/leagues", {"id": int(league_id)},
                        ttl=timedelta(days=S.get(client.db, "cache.ttl.reference_days")),
                        purpose="coverage")
    if not rows:
        return {"found": False}
    seasons = rows[0].get("seasons") or []
    row = next((s for s in seasons if str(s.get("year")) == str(season)), None)
    if row is None:
        return {"found": False, "seasons": [s.get("year") for s in seasons]}
    cov = row.get("coverage") or {}
    fx = cov.get("fixtures") or {}
    return {"found": True, "season": row.get("year"), "current": bool(row.get("current")),
            "start": row.get("start"), "end": row.get("end"),
            "fixtures_events": bool(fx.get("events")),
            "fixtures_lineups": bool(fx.get("lineups")),
            "fixtures_statistics": bool(fx.get("statistics_fixtures")),
            "players_statistics": bool(fx.get("statistics_players")),
            "standings": bool(cov.get("standings")), "players": bool(cov.get("players")),
            "injuries": bool(cov.get("injuries")), "top_scorers": bool(cov.get("top_scorers"))}


# ------------------------------------------------------------------ the one call that does it all
#
# `/fixtures?ids=a-b-c` takes up to TWENTY fixture ids and answers with events, lineups, statistics
# AND player statistics for every one of them, in a single request (changelog 3.9.2). That is the
# difference between 3 calls per match and 0.15, and it is what makes a three-season backfill a
# day's work instead of a fortnight's. Everything that ingests finished matches goes through here.
IDS_PER_CALL = 20


def fixtures_bundle(client: Client, fixture_ids: list[int], ttl=FOREVER, purpose="bundle") -> dict:
    """{fixture_id: fixture-with-everything} for up to 20 ids per call."""
    out = {}
    ids = [int(i) for i in fixture_ids]
    for i in range(0, len(ids), IDS_PER_CALL):
        chunk = ids[i:i + IDS_PER_CALL]
        rows = client.fetch("/fixtures", {"ids": "-".join(str(x) for x in chunk)}, ttl=ttl, purpose=purpose)
        for row in rows:
            fid = ((row.get("fixture") or {}).get("id"))
            if fid is not None:
                out[int(fid)] = row
    return out


def media_url(kind: str, ext_id) -> str:
    """Logos, crests, photos and flags. These do not count against the daily quota, but they ARE
    rate limited, and the licence note in their documentation is the reason docs/19 §8 is still
    open: they do not own these images and say so."""
    if kind == "flags":
        return f"https://media.api-sports.io/flags/{ext_id}.svg"
    return f"{MEDIA_URL}/{kind}/{ext_id}.png"
