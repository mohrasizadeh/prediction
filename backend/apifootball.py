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

# The ball is actually moving. A DIFFERENT question from `in_play`, and the difference costs calls:
# their guidance is to refresh statistics "only if the fixture is in progress, it's not necessary to
# update them when the fixture status is at half time" (docs/82 §4). `in_play` holds HT, BT, SUSP and
# INT because a forecast must keep ticking through a break -- that was the whole point of docs/42 --
# but none of those periods produces a new shot or tackle, so polling through them buys nothing.
PLAYING = {"1H", "2H", "ET", "LIVE"}


def in_play(status) -> bool:
    """Is this match being played right now? The one rule, for every screen (docs/42)."""
    return bool(status) and str(status).upper() not in NOT_PLAYING


def is_final(status) -> bool:
    return bool(status) and str(status).upper() in FINAL


def is_over(status) -> bool:
    """Finished, or called off and never coming back."""
    return bool(status) and str(status).upper() in (FINAL | DEAD)


def worth_refreshing_stats(status) -> bool:
    """Would calling for this fixture's statistics return anything new? Half time would not."""
    return bool(status) and str(status).upper() in PLAYING


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
class RateLimited(APIFootballError): ...      # too fast. Arrives as HTTP 200, see _unwrap (docs/82 §1)
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


def _retry_after(value, default: float, cap: float = 60.0) -> float:
    """Seconds to wait from a Retry-After header: seconds, or an HTTP date. Anything odd falls back
    to the default, and the whole thing is capped so one answer cannot hold a job lock for an hour
    (the same rule as cached_fetch, docs/36 H4)."""
    try:
        wait = float(value)
    except (TypeError, ValueError):
        try:
            from email.utils import parsedate_to_datetime
            wait = (parsedate_to_datetime(value) - utcnow()).total_seconds()
        except Exception:
            wait = default
    return max(0.0, min(wait, cap))


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

    def day_budget(self) -> int:
        """How many calls we will make today, leaving a reserve.

        The PLAN's number, not a number we typed: `x-ratelimit-requests-limit` says 75,000 on Ultra
        and something else on another plan, and reading it means the budget follows the subscription
        instead of going stale the day it changes. `apifootball.daily_cap` is only the fallback for
        before the first answer of the day has taught us the real one.

        This is deliberately NOT `ingest.daily_call_budget`: that one is 2,000, PitchAPI's figure,
        and sharing it would cap an Ultra plan at under 3% of what it allows.
        """
        q = self.quota()
        limit = q.get("day_limit") if q.get("day") == utcnow().strftime("%Y-%m-%d") else None
        if not limit:
            limit = int(S.get(self.db, "apifootball.daily_cap"))
        return max(0, int(limit) - int(S.get(self.db, "apifootball.daily_reserve")))

    def _check_guards(self) -> None:
        br = self.db.job_locks.find_one({"_id": "af_breaker"})
        # `fetch` guards this value and this did not: a breaker row without `expires_at`, or with a
        # null one, raised KeyError or compared None with a datetime. Neither is an APIFootballError,
        # so the route could not translate it and it surfaced as a bare 500 with no reason -- the
        # exact failure this module exists to make legible. A row we cannot read an expiry from is
        # treated as expired, because the breaker's job is to open on evidence, not on a damaged row.
        exp = _aware((br or {}).get("expires_at"))
        if br and exp is not None and exp > utcnow():
            raise BreakerOpen(br.get("reason", "breaker open"))
        q = self.quota()
        reserve = int(S.get(self.db, "apifootball.daily_reserve"))
        # Their count wins over ours (docs/19), and we stop at the reserve rather than at zero, so
        # a live tick or a key test still has calls left when a backfill has eaten the day.
        if q.get("day") == utcnow().strftime("%Y-%m-%d") and q.get("day_remaining") is not None:
            if int(q["day_remaining"]) <= reserve:
                raise BudgetExhausted(
                    f"API-Football says {q['day_remaining']} calls are left, at or under the {reserve} reserve")
        if self._calls_today() >= self.day_budget():
            raise BudgetExhausted(f"our own count reached today's budget of {self.day_budget()}")

    def _trip_breaker(self, reason: str) -> None:
        mins = S.get(self.db, "ingest.breaker_minutes")
        self.db.job_locks.update_one({"_id": "af_breaker"},
                                     {"$set": {"reason": reason, "expires_at": utcnow() + timedelta(minutes=mins)}},
                                     upsert=True)

    def _gap(self) -> float:
        """Seconds to leave between calls, from the provider's OWN per-minute allowance.

        `X-RateLimit-Limit` is the calls-per-minute ceiling for the plan. Spreading requests at
        that rate times a safety factor means the minute bucket is never emptied, which matters
        here more than politeness: their rate-limit policy blocks a key for "abnormal traffic
        spikes" rather than throttling it, and a burst that drains the bucket is exactly that.

        `ingest.rps` is deliberately NOT consulted. It is 3, PitchAPI's figure, and letting it
        govern here would cap an Ultra plan at 180 calls a minute out of the 450 it allows — a
        backfill two and a half times slower than it needs to be, for a limit that belongs to
        another provider. Until the first answer teaches us the real ceiling we use
        `apifootball.rps_unknown`, which is conservative on purpose.

        As the bucket empties the gap stretches in proportion: sprinting to zero and then stalling
        for a cooldown is the same burst with a pause after it.
        """
        unknown = 1.0 / max(float(S.get(self.db, "apifootball.rps_unknown")), 0.05)
        q = self.quota()
        lim, left = q.get("min_limit"), q.get("min_remaining")
        if not lim:
            return unknown                                # nothing learned yet: go slowly
        safety = max(0.05, min(1.0, float(S.get(self.db, "apifootball.minute_safety"))))
        gap = 60.0 / (float(lim) * safety)
        if left is not None and float(lim) > 0:
            share = max(0.0, float(left)) / float(lim)
            headroom = max(0.01, min(1.0, float(S.get(self.db, "apifootball.minute_headroom"))))
            if share < headroom:                          # the last of the bucket is spent slowest
                gap *= headroom / max(share, 0.02)
        return max(gap, self.min_gap())

    def per_second_limit(self) -> float | None:
        """The plan's calls-a-SECOND ceiling, which no header reports (docs/82 §2).

        Their plan table gives it beside the per-minute figure, and across every plan it is exactly
        the per-minute limit divided by sixty: Pro 300/5, Ultra 450/7.5, Mega 900/15, Custom
        1200/20. So it needs no plan-name lookup and no number typed in here — it is derived, and it
        stays right if they add a plan.
        """
        lim = self.quota().get("min_limit")
        return (float(lim) / 60.0) if lim else None

    def min_gap(self) -> float:
        """The shortest gap the plan permits. Even pacing is what makes the per-second ceiling hold:
        the average could be legal while two calls 10ms apart were not, so the ceiling is enforced
        between CONSECUTIVE calls rather than over a window."""
        per_s = self.per_second_limit()
        return (1.0 / per_s) if per_s else 0.0

    def _pace(self) -> None:
        q = self.quota()
        if q.get("min_remaining") is not None and int(q["min_remaining"]) <= 0:
            # Nothing left this minute. Their window is not published, so wait out a whole one.
            self._sleep(float(S.get(self.db, "apifootball.minute_cooldown_s")))
        gap = self._gap()
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
            if "rateLimit" in errs or "ratelimit" in {k.lower() for k in errs}:
                # THE PER-MINUTE LIMIT ARRIVES AS HTTP 200 (docs/82 §1). Before this case existed it
                # fell through to the generic error below: no backoff, no retry, and the job carried
                # on at the same pace -- which is how their documentation says a key, and the IP
                # behind it, gets firewalled. The caller retries after a cooldown.
                #
                # The answer usually carries X-RateLimit-Remaining: 0 and _note_quota has already
                # stored it, so _pace slows down on its own. Where it does not, say so ourselves.
                self.db.job_state.update_one({"_id": "apifootball_quota"},
                                             {"$set": {"min_remaining": 0, "at": utcnow()}}, upsert=True)
                raise RateLimited("rateLimit", blob)
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
                # If they say how long to wait, wait that long: guessing shorter is what turns a
                # throttle into a block. Capped so one answer cannot hold the job lock for an hour.
                self._sleep(_retry_after(r.headers.get("Retry-After"), default=2 ** attempts))
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
            try:
                return self._unwrap(body, path)
            except RateLimited as e:
                # Same handling as a 429, because it IS one: it just arrived with a 200.
                attempts += 1
                if attempts > 3:
                    self._trip_breaker("per-minute rate limit")
                    raise BreakerOpen(f"per-minute rate limit: {e.detail}")
                self._sleep(float(S.get(self.db, "apifootball.minute_cooldown_s")))
                continue

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
        used only where the endpoint really pages (`/players`, `/players/profiles`).

        `page` IS NOT SENT FOR THE FIRST PAGE. Page 1 is the default on every paginated endpoint, so
        sending it says nothing -- and the endpoints that do not page REFUSE the field rather than
        ignore it:

            errors: /leagues: page: The Page field do not exist.

        That arrives as HTTP 200 with an `errors` object, which is a refusal, not a page of data. It
        is how the Competitions screen came up empty with the provider blamed: `sync_catalog` asks
        for every competition in one call, and the one call could never succeed. Omitting the field
        until it is actually wanted works for both kinds of endpoint, so this needs no list of which
        is which -- a list that would have to be right about an API we do not control.
        """
        params = dict(params or {})
        out, page = [], 1
        while page <= max_pages:
            if page > 1:
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


# ------------------------------------------------------------------ live, in one call
#
# "To update fixtures and events, a single call to the fixtures/live endpoint is enough as it returns
# all current fixtures AND THEIR EVENTS, this avoids calling the endpoint events for each fixtures"
# (docs/82 §3). On a Saturday with twenty live matches that is one call where a fixture list plus a
# per-match events call would be twenty-one. Never cached: the whole point is freshness.
def live_fixtures(client: Client, league_ids: list[int] | None = None) -> list[dict]:
    """Every in-play fixture, with its events inline. `league_ids` narrows it to ours."""
    param = "-".join(str(int(i)) for i in league_ids) if league_ids else "all"
    return client.fetch("/fixtures", {"live": param}, ttl=timedelta(seconds=0), purpose="live", force=True)


def needs_stats(fixtures: list[dict]) -> list[int]:
    """Of those live fixtures, the ones actually producing statistics right now (§4)."""
    out = []
    for f in fixtures:
        st = ((f.get("fixture") or {}).get("status") or {}).get("short")
        fid = (f.get("fixture") or {}).get("id")
        if fid is not None and worth_refreshing_stats(st):
            out.append(int(fid))
    return out


# ------------------------------------------------------------------ lineups: fetch until present
def lineup_ttl(client: Client, fixture: dict):
    """How long a fixture's lineup answer may be cached.

    "As the lineups are updated only once and do not change during the fixture, once you have
    retrieved the data it is no longer necessary to update them" (docs/82 §5). So a lineup we have
    is cached FOR EVER, and only an absent one is polled again — they appear 20 to 40 minutes before
    kick-off, and in some competitions only after the match.
    """
    if (fixture.get("lineups") or []):
        return FOREVER
    mins = float(S.get(client.db, "cache.ttl.lineups_near_minutes"))
    return timedelta(minutes=mins)


# ------------------------------------------------------------------ standings: today's leagues only
def leagues_playing_on(client: Client, date: str) -> list[int]:
    """The distinct leagues with a fixture on `date` (YYYY-MM-DD), from one call.

    Their standings pattern (docs/82 §7): read the day's fixtures once, collect the league ids, and
    ask for those tables only. Twelve leagues on a Saturday, two on a Tuesday, rather than every
    league we carry every hour.
    """
    rows = client.fetch("/fixtures", {"date": date},
                        ttl=timedelta(hours=float(S.get(client.db, "cache.ttl.fixtures_matchday_hours"))),
                        purpose="day_fixtures")
    seen = []
    for r in rows:
        lid = (r.get("league") or {}).get("id")
        if lid is not None and int(lid) not in seen:
            seen.append(int(lid))
    return seen


def standings(client: Client, league_id: int, season: int, skip_uncovered: bool = True) -> list:
    """One league's table, skipped entirely where the competition does not carry standings — an
    uncovered league answers empty, and a call that was always going to answer empty is the kind
    their guidance exists to stop us making."""
    if skip_uncovered and not coverage(client, league_id, season).get("standings", True):
        return []
    return client.fetch("/standings", {"league": int(league_id), "season": int(season)},
                        ttl=timedelta(hours=float(S.get(client.db, "cache.ttl.standings_hours"))),
                        purpose="standings")


def media_url(kind: str, ext_id) -> str:
    """Logos, crests, photos and flags. These do not count against the daily quota, but they ARE
    rate limited, and the licence note in their documentation is the reason docs/19 §8 is still
    open: they do not own these images and say so."""
    if kind == "flags":
        return f"https://media.api-sports.io/flags/{ext_id}.svg"
    return f"{MEDIA_URL}/{kind}/{ext_id}.png"
