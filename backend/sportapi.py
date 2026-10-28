"""sportapi.py -- live scores, match events, lineups and historical results from SportAPI (sportapi.ai). docs/23.

What we use SportAPI for (and nothing else):
  * live scores and match clock          GET /api/fixtures/date/{date}        one call = every fixture of the day
  * match events (goals, cards, subs)    GET /api/fixtures/{id}/events        only for live matches we track, on change
  * final details (half-time score)      GET /api/fixtures/{id}               once, when a match finishes
  * lineups (starting XI and bench)      GET /api/fixtures/{id}/lineups       a few times before kick-off, then stop
  * historical results                   GET /api/fixtures/date/{date}        past dates, cached for good once all are final
  * league list for the admin mapping    GET /api/leagues                     cached 7 days
PitchAPI stays the source of the statistics the engine learns from. SportAPI adds speed (live) and lineups.

The plan allows 2,000 calls a day. We count every call ourselves (`sportapi_calls`, per UTC day), stop at
`sportapi.daily_calls` (default 1,800, keeping 200 spare), and slow everything down when less than a quarter is left.
Visitors never cause a call: pages read our database; only the job below calls SportAPI.

Run `live_tick(db)` every minute (POST /api/jobs/live, called by an external pinger). It decides by itself whether a
call is due, so calling it more often costs nothing.
"""
from __future__ import annotations

import hashlib
import re
from datetime import datetime, timedelta, timezone

import httpx

import security
import settings_store as S
from images import team_score, player_score            # the same careful name matching as the image sync (docs/19)

BASE = "https://sportapi.ai"
PROVIDER = "sportapi"
KEY_RE = r"^[A-Za-z0-9_\-]{16,128}$"
LIVE = "LIVE"
FINAL = {"FT", "AET", "PENS"}
DEAD = {"Postponed", "Cancelled"}
POS = {"goalkeeper": "GK", "defender": "DEF", "midfielder": "MID", "forward": "FWD", "attacker": "FWD", "attacking midfielder": "MID"}

_FACTORY = lambda: httpx.Client(timeout=15.0, follow_redirects=False)


def set_http_factory(f):
    global _FACTORY
    _FACTORY = f


def utcnow():
    return datetime.now(timezone.utc)


def _aware(d):
    return d if d is None or d.tzinfo else d.replace(tzinfo=timezone.utc)


class SportAPIError(Exception):
    pass


class BudgetExhausted(SportAPIError):
    pass


class NoKey(SportAPIError):
    pass


# ------------------------------------------------------------------ client with a hard daily budget
def calls_today(db, now=None) -> dict:
    d = db.sportapi_calls.find_one({"_id": (now or utcnow()).strftime("%Y-%m-%d")}) or {}
    return {"n": int(d.get("n", 0)), "by_kind": d.get("by_kind", {})}


class Client:
    def __init__(self, db, http: httpx.Client | None = None, now=None):
        self.db = db
        self.now = now or utcnow()
        self.http = http or _FACTORY()
        self.key = security.get_provider_key(db, PROVIDER, env_fallback="SPORTAPI_KEY")
        if not self.key:
            raise NoKey("No SportAPI key saved (Admin > Keys).")

    def used(self) -> int:
        return calls_today(self.db, self.now)["n"]

    def cap(self) -> int:
        return int(S.get(self.db, "sportapi.daily_calls"))

    def left(self) -> int:
        return self.cap() - self.used()

    def tight(self) -> bool:
        """Less than a quarter of today's budget left: everything polls half as often."""
        return self.left() < self.cap() * 0.25

    def get(self, path: str, kind: str, cache_days: float | None = None) -> dict:
        if cache_days:
            hit = self.db.sportapi_cache.find_one({"_id": path, "expires_at": {"$gt": self.now.replace(tzinfo=None)}})
            if hit:
                return hit["payload"]
        if self.left() <= 0:
            raise BudgetExhausted("Today's SportAPI budget is used.")
        try:
            r = self.http.get(BASE + path, headers={"X-Api-Key": self.key, "accept": "application/json"})
        except httpx.HTTPError as e:
            self._count(kind)
            raise SportAPIError(f"SportAPI could not be reached ({type(e).__name__}).")
        self._count(kind)
        if r.status_code in (401, 403):
            raise SportAPIError("SportAPI refused the key.")
        if r.status_code == 429:
            self.db.sportapi_calls.update_one({"_id": self.now.strftime("%Y-%m-%d")}, {"$set": {"n": self.cap()}}, upsert=True)
            raise BudgetExhausted("SportAPI says the daily limit is reached.")
        if r.status_code == 404:
            return {"success": False, "not_found": True}
        if r.status_code != 200:
            raise SportAPIError(f"SportAPI answered {r.status_code}.")
        data = r.json()
        if not isinstance(data, dict) or data.get("success") is False:
            raise SportAPIError("SportAPI answered without success.")
        if cache_days:
            self.db.sportapi_cache.update_one({"_id": path}, {"$set": {"payload": data, "expires_at": (self.now + timedelta(days=cache_days)).replace(tzinfo=None)}}, upsert=True)
        return data

    def _count(self, kind):
        self.db.sportapi_calls.update_one({"_id": self.now.strftime("%Y-%m-%d")},
                                          {"$inc": {"n": 1, f"by_kind.{kind}": 1}, "$set": {"at": self.now}}, upsert=True)


# ------------------------------------------------------------------ mapping SportAPI ids to ours
def tracked_leagues(db) -> dict:
    """{sportapi league id: our league iid} from `sportapi.leagues` ({our iid: sportapi id})."""
    return {int(v): int(k) for k, v in (S.get(db, "sportapi.leagues") or {}).items() if v}


def map_team(db, sid: int, name: str, league_iid: int | None) -> int | None:
    """Our team iid for a SportAPI team, matched by name inside the mapped league only. Never guesses."""
    m = db.sportapi_team_map.find_one({"sid": sid})
    if m and m.get("status") in ("auto", "approved"):
        return m.get("our_iid")
    if m and m.get("status") in ("rejected", "review"):
        return None
    if league_iid is None:
        return None
    aliases = S.get(db, "sportapi.team_aliases") or {}
    cands = sorted(((team_score(t["name"], name, aliases), t) for t in db.teams.find({"league_iid": league_iid}, {"_id": 0, "iid": 1, "name": 1})),
                   key=lambda x: -x[0])
    best = cands[0] if cands else (0.0, None)
    runner = cands[1][0] if len(cands) > 1 else 0.0
    conf = float(S.get(db, "sportapi.min_confidence"))
    status = "auto" if best[0] >= conf and best[0] - runner >= 0.04 else ("review" if best[0] >= 0.7 else "none")
    db.sportapi_team_map.update_one({"sid": sid}, {"$set": {"sid": sid, "name": name, "league_iid": league_iid, "status": status, "score": round(best[0], 3),
                                                            "our_iid": best[1]["iid"] if best[1] and status != "none" else None,
                                                            "candidates": [{"iid": t["iid"], "name": t["name"], "score": round(s, 3)} for s, t in cands[:3]],
                                                            "at": utcnow()}}, upsert=True)
    return best[1]["iid"] if status == "auto" else None


def link_match(db, league_iid, home_iid, away_iid, kickoff) -> int | None:
    if not (league_iid and home_iid and away_iid and kickoff):
        return None
    m = db.matches.find_one({"league_iid": league_iid, "home_iid": home_iid, "away_iid": away_iid,
                             "kickoff": {"$gte": kickoff - timedelta(hours=36), "$lte": kickoff + timedelta(hours=36)}}, {"iid": 1})
    return m["iid"] if m else None


def _kickoff(f) -> datetime | None:
    k = f.get("kickoff_utc")
    if not k:
        return None
    try:
        return datetime.fromisoformat(k.replace("Z", "+00:00"))
    except ValueError:
        return None


def _minute_num(label) -> float:
    """"55'" -> 55, "90+3'" -> 93, "HT" -> 45. Used to sort events."""
    if label is None:
        return 0.0
    s = str(label)
    if s.upper() == "HT":
        return 45.0
    m = re.match(r"(\d+)(?:\s*\+\s*(\d+))?", s)
    return float(int(m.group(1)) + (int(m.group(2)) if m.group(2) else 0)) if m else 0.0


# ------------------------------------------------------------------ storing what we read
def upsert_fixture(db, f: dict, leagues: dict, now) -> dict | None:
    """Store one fixture of a tracked league. Returns {"changed": bool, "doc": ...} or None if not tracked."""
    lsid = f.get("league_id")
    if lsid not in leagues:
        return None
    league_iid = leagues[lsid]
    sid = int(f["id"])
    old = db.live_fixtures.find_one({"sid": sid}) or {}
    ko = _kickoff(f)
    home_iid = old.get("home_iid") or map_team(db, f.get("home_id"), f.get("home_team") or "", league_iid)
    away_iid = old.get("away_iid") or map_team(db, f.get("away_id"), f.get("away_team") or "", league_iid)
    match_iid = old.get("match_iid") or link_match(db, league_iid, home_iid, away_iid, ko)
    doc = {"sid": sid, "league_sid": lsid, "league_iid": league_iid, "league_name": f.get("league_name"),
           "date": f.get("date"), "kickoff": ko, "status": f.get("status"), "minute": f.get("minute"),
           "hs": f.get("home_score"), "as": f.get("away_score"), "result": f.get("result"), "winner": f.get("winner"),
           "pen_home": f.get("penalty_home"), "pen_away": f.get("penalty_away"), "stage": f.get("stage"),
           "home_sid": f.get("home_id"), "away_sid": f.get("away_id"), "home_name": f.get("home_team"), "away_name": f.get("away_team"),
           "home_short": f.get("home_short"), "away_short": f.get("away_short"),
           "home_iid": home_iid, "away_iid": away_iid, "match_iid": match_iid,
           "provider_updated_at": f.get("updated_at"), "polled_at": now}
    for k in ("ht_home", "ht_away"):
        if k in f:
            doc[k] = f[k]
    changed = any(old.get(k) != doc[k] for k in ("status", "hs", "as", "minute")) if old else True
    if old.get("status") != doc["status"] and doc["status"] in FINAL:
        doc["final_at"] = now
    db.live_fixtures.update_one({"sid": sid}, {"$set": doc}, upsert=True)
    if match_iid:                                           # a light mirror on our match, for the Today and match pages
        db.matches.update_one({"iid": match_iid}, {"$set": {"live": {k: doc[k] for k in ("status", "minute", "hs", "as", "pen_home", "pen_away")} | {"sid": sid, "at": now}}})
    return {"changed": changed, "doc": doc, "score_changed": bool(old) and (old.get("hs"), old.get("as")) != (doc["hs"], doc["as"]),
            "status_changed": bool(old) and old.get("status") != doc["status"]}


def store_events(db, fixture_sid: int, events: list, now) -> int:
    """Replace the fixture's events with the provider's list (it is the full list each time)."""
    fx = db.live_fixtures.find_one({"sid": fixture_sid}, {"home_iid": 1, "away_iid": 1}) or {}
    rows = []
    for e in events or []:
        eid = e.get("id") or int(hashlib.sha1(f"{fixture_sid}|{e.get('event_type')}|{e.get('player_name')}|{e.get('minute')}".encode()).hexdigest()[:12], 16)
        side = e.get("team_side")
        rows.append({"fixture_sid": fixture_sid, "eid": int(eid), "type": e.get("event_type"), "side": side,
                     "player_name": e.get("player_name"), "minute": e.get("minute"), "minute_num": _minute_num(e.get("minute")),
                     "extra": e.get("extra_info"), "team_iid": fx.get("home_iid") if side == "home" else fx.get("away_iid") if side == "away" else None,
                     "at": now})
    db.live_events.delete_many({"fixture_sid": fixture_sid})
    if rows:
        db.live_events.insert_many(rows)
    db.live_fixtures.update_one({"sid": fixture_sid}, {"$set": {"events_at": now, "events_n": len(rows)}})
    return len(rows)


def store_lineups(db, fixture_sid: int, data: dict, now) -> dict:
    """Keep the lineups; match names to our players inside the mapped club. If enough starters match with confidence,
    write them as a confirmed eleven so the engine can use them (only when PitchAPI has none). docs/23 §5."""
    fx = db.live_fixtures.find_one({"sid": fixture_sid}) or {}
    conf = float(S.get(db, "sportapi.min_confidence"))
    out = {}
    for side in ("home", "away"):
        team_iid = fx.get(f"{side}_iid")
        squad = list(db.players.find({"team_iid": team_iid}, {"_id": 0, "iid": 1, "name": 1, "pos": 1})) if team_iid else []
        block = (data or {}).get(side) or {}
        rows, claimed = [], {}
        for started, lst in ((True, block.get("starters") or []), (False, block.get("subs") or [])):
            for p in lst:
                pos = POS.get(str(p.get("position") or "").lower())
                scored = sorted(((player_score(q["name"], q.get("pos"), p.get("name") or "", p.get("position")), q) for q in squad), key=lambda x: -x[0])
                best = scored[0] if scored else (0.0, None)
                runner = scored[1][0] if len(scored) > 1 else 0.0
                ok = best[1] is not None and best[0] >= conf and best[0] - runner >= 0.04
                row = {"name": p.get("name"), "position": p.get("position"), "pos": pos, "shirt": p.get("shirt"), "captain": bool(p.get("is_captain")),
                       "mins": p.get("mins_played"), "started": started, "player_iid": best[1]["iid"] if ok else None, "score": round(best[0], 3)}
                if ok:
                    claimed.setdefault(best[1]["iid"], []).append(row)
                rows.append(row)
        for iid, rs in claimed.items():                    # two names claiming one player: trust neither
            if len(rs) > 1:
                for r in rs:
                    r["player_iid"] = None
        matched = sum(1 for r in rows if r["started"] and r["player_iid"])
        n_start = sum(1 for r in rows if r["started"])
        db.live_lineups.update_one({"fixture_sid": fixture_sid, "side": side},
                                   {"$set": {"fixture_sid": fixture_sid, "side": side, "team_iid": team_iid, "players": rows,
                                             "starters": n_start, "matched_starters": matched, "fetched_at": now}}, upsert=True)
        out[side] = {"starters": n_start, "matched": matched}
        if (S.get(db, "sportapi.lineups_to_engine") and fx.get("match_iid") and team_iid and n_start == 11 and matched == 11
                and not db.lineups.find_one({"match_iid": fx["match_iid"], "team_iid": team_iid, "confirmed": True, "source": {"$ne": "sportapi"}})):
            db.lineups.delete_many({"match_iid": fx["match_iid"], "team_iid": team_iid, "source": "sportapi"})
            db.lineups.insert_many([{"match_iid": fx["match_iid"], "team_iid": team_iid, "player_iid": r["player_iid"], "started": r["started"],
                                     "confirmed": True, "source": "sportapi", "shirt_number": str(r["shirt"] or ""), "is_captain": r["captain"],
                                     "fetched_at": now} for r in rows if r["player_iid"]])
            db.matches.update_one({"iid": fx["match_iid"]}, {"$set": {"lineups_at": now, "lineups_confirmed": True}})   # the engine re-runs on this
            out[side]["to_engine"] = True
    db.live_fixtures.update_one({"sid": fixture_sid}, {"$set": {"lineups_at": now, "lineups_ok": bool(out.get("home", {}).get("starters"))}})
    return out


# ------------------------------------------------------------------ the minute job
def _due(last, seconds, now) -> bool:
    return last is None or (now - _aware(last)).total_seconds() >= seconds


def live_tick(db, client: Client | None = None, now=None) -> dict:
    """Call every minute. Spends calls only when something is due. Returns what it did."""
    now = now or utcnow()
    if not S.get(db, "sportapi.enabled"):
        return {"status": "off"}
    leagues = tracked_leagues(db)
    if not leagues:
        return {"status": "no_leagues", "note": "Map leagues in sportapi.leagues first."}
    try:
        client = client or Client(db, now=now)
    except NoKey as e:
        return {"status": "no_key", "note": str(e)}
    slow = 2 if client.tight() else 1
    st = db.sportapi_state.find_one({"_id": "live"}) or {}
    today = now.strftime("%Y-%m-%d")
    out = {"status": "ok", "calls": 0, "date_polls": [], "events": 0, "lineups": 0, "finals": 0}
    try:
        # 1) the scoreboard: one call per date. Fast while anything is live or about to start.
        window = timedelta(minutes=int(S.get(db, "sportapi.window_before_min")))
        tracked_today = list(db.live_fixtures.find({"league_iid": {"$in": list(leagues.values())},
                                                    "kickoff": {"$gte": now - timedelta(hours=30), "$lte": now + timedelta(hours=24)}},
                                                   {"_id": 0, "sid": 1, "status": 1, "kickoff": 1, "date": 1}))
        hot = [f for f in tracked_today if f["status"] == LIVE or (f["status"] not in FINAL | DEAD and f.get("kickoff")
               and _aware(f["kickoff"]) - window <= now <= _aware(f["kickoff"]) + timedelta(hours=3))]
        if hot:
            interval = int(S.get(db, "sportapi.live_interval_s")) * slow
        elif any(f.get("kickoff") and now <= _aware(f["kickoff"]) <= now + timedelta(hours=12) for f in tracked_today):
            interval = int(S.get(db, "sportapi.idle_interval_s")) * slow
        else:
            interval = int(S.get(db, "sportapi.quiet_interval_s")) * slow
        dates = {today} | {f["date"] for f in hot if f.get("date")}          # a match that started late yesterday stays followed
        changed = []
        for d in sorted(dates):
            if _due((st.get("date_polls") or {}).get(d), interval, now):
                data = client.get(f"/api/fixtures/date/{d}", "date")
                out["calls"] += 1; out["date_polls"].append(d)
                for f in data.get("data") or []:
                    r = upsert_fixture(db, f, leagues, now)
                    if r and (r["score_changed"] or r["status_changed"]):
                        changed.append(r["doc"])
                db.sportapi_state.update_one({"_id": "live"}, {"$set": {f"date_polls.{d}": now}}, upsert=True)

        # 2) events: on every score or status change, and every few minutes while live (cards, subs)
        refresh = int(S.get(db, "sportapi.events_refresh_s")) * slow
        live_now = list(db.live_fixtures.find({"league_iid": {"$in": list(leagues.values())}, "status": LIVE}, {"_id": 0, "sid": 1, "events_at": 1}))
        want = {f["sid"] for f in changed if f["status"] == LIVE} | {f["sid"] for f in live_now if _due(f.get("events_at"), refresh, now)}
        for sid in sorted(want):
            ev = client.get(f"/api/fixtures/{sid}/events", "events")
            out["calls"] += 1
            if ev.get("data") is not None:
                store_events(db, sid, ev["data"], now); out["events"] += 1

        # 3) a match just finished: one detail call (half-time score, final events), then never again
        for f in db.live_fixtures.find({"league_iid": {"$in": list(leagues.values())}, "status": {"$in": list(FINAL)}, "final_done": {"$ne": True},
                                        "kickoff": {"$gte": now - timedelta(days=2)}}, {"_id": 0, "sid": 1}):
            det = client.get(f"/api/fixtures/{f['sid']}", "final")
            out["calls"] += 1
            fx = det.get("fixture") or {}
            if fx:
                upsert_fixture(db, fx, leagues, now)
                store_events(db, f["sid"], fx.get("events") or [], now)
            db.live_fixtures.update_one({"sid": f["sid"]}, {"$set": {"final_done": True}})
            out["finals"] += 1

        # 4) lineups: at each of the configured minutes before kick-off, until the provider has them
        slots = sorted(int(x) for x in S.get(db, "sportapi.lineups_minutes"))
        for f in db.live_fixtures.find({"league_iid": {"$in": list(leagues.values())}, "status": "Scheduled", "lineups_ok": {"$ne": True},
                                        "kickoff": {"$gte": now, "$lte": now + timedelta(minutes=max(slots) if slots else 0)}},
                                       {"_id": 0, "sid": 1, "kickoff": 1, "lineup_slots": 1}):
            mins = (_aware(f["kickoff"]) - now).total_seconds() / 60
            slot = next((s for s in slots if mins <= s and s not in (f.get("lineup_slots") or [])), None)
            if slot is None:
                continue
            lu = client.get(f"/api/fixtures/{f['sid']}/lineups", "lineups")
            out["calls"] += 1
            db.live_fixtures.update_one({"sid": f["sid"]}, {"$addToSet": {"lineup_slots": slot}})
            if lu.get("available") and lu.get("data"):
                store_lineups(db, f["sid"], lu["data"], now); out["lineups"] += 1
    except BudgetExhausted as e:
        out["status"] = "budget"; out["note"] = str(e)
    except SportAPIError as e:
        out["status"] = "error"; out["note"] = str(e)
    db.sportapi_state.update_one({"_id": "live"}, {"$set": {"last_tick": now, "last_result": {k: v for k, v in out.items() if k != "date_polls"}}}, upsert=True)
    return out


# ------------------------------------------------------------------ historical results
def backfill(db, start: str, end: str, client: Client | None = None, now=None, max_seconds: float = 40.0) -> dict:
    """One call per date, oldest first. A date whose fixtures are all final is cached for good and never called again.
    Keeps `sportapi.reserve_for_live` calls spare for today's live scores. Resumable: call again to continue."""
    import time
    now = now or utcnow()
    client = client or Client(db, now=now)
    leagues = tracked_leagues(db)
    d0, d1 = datetime.fromisoformat(start).date(), datetime.fromisoformat(end).date()
    if d1 < d0:
        d0, d1 = d1, d0
    if (d1 - d0).days + 1 > int(S.get(db, "sportapi.backfill_max_days")):
        raise ValueError(f"At most {S.get(db, 'sportapi.backfill_max_days')} days per request.")
    reserve = int(S.get(db, "sportapi.reserve_for_live"))
    t0 = time.monotonic()
    done, stored, skipped = [], 0, []
    d = d0
    while d <= d1:
        ds = d.isoformat()
        if db.sportapi_dates.find_one({"_id": ds, "complete": True}):
            skipped.append(ds); d += timedelta(days=1); continue
        if client.left() <= reserve or time.monotonic() - t0 > max_seconds:
            return {"status": "paused", "done": done, "stored": stored, "next": ds, "calls_left": client.left(),
                    "note": "Budget reserve or time limit reached. Run again (tomorrow if the budget is the reason)."}
        data = client.get(f"/api/fixtures/date/{ds}", "backfill")
        n = 0
        rows = data.get("data") or []
        for f in rows:
            if upsert_fixture(db, f, leagues, now):
                n += 1
        complete = all((f.get("status") in FINAL | DEAD) for f in rows if f.get("league_id") in leagues)
        db.sportapi_dates.update_one({"_id": ds}, {"$set": {"complete": complete and d < now.date(), "tracked": n, "at": now}}, upsert=True)
        done.append(ds); stored += n
        d += timedelta(days=1)
    return {"status": "done", "done": done, "skipped": skipped, "stored": stored, "calls_left": client.left()}


def league_list(db, client: Client | None = None) -> list:
    """For the admin mapping screen. Cached 7 days (1 call a week)."""
    client = client or Client(db)
    data = client.get("/api/leagues", "leagues", cache_days=7)
    out = []
    for c in data.get("data") or []:
        for lg in c.get("leagues") or []:
            out.append({"id": lg.get("id"), "name": lg.get("name"), "country": c.get("country"), "fixtures": lg.get("fixtures_count"), "teams": lg.get("teams_count")})
    return out


# ------------------------------------------------------------------ reads for the pages (no external calls)
STATUS_WORDS = {"Scheduled": "Not started", "LIVE": "Live", "FT": "Full time", "AET": "After extra time", "PENS": "After penalties",
                "Postponed": "Postponed", "Cancelled": "Cancelled", "Suspended": "Suspended"}


def public_fixture(f: dict, names=None) -> dict:
    return {"sid": f["sid"], "match_id": (names or {}).get(("m", f.get("match_iid"))), "league_iid": f.get("league_iid"), "league_name": f.get("league_name"),
            "kickoff": f.get("kickoff"), "status": f.get("status"), "status_text": STATUS_WORDS.get(f.get("status"), f.get("status")),
            "minute": f.get("minute"), "home": {"name": f.get("home_name"), "short": f.get("home_short"), "team": (names or {}).get(("t", f.get("home_iid")))},
            "away": {"name": f.get("away_name"), "short": f.get("away_short"), "team": (names or {}).get(("t", f.get("away_iid")))},
            "score": {"home": f.get("hs"), "away": f.get("as"), "ht_home": f.get("ht_home"), "ht_away": f.get("ht_away"),
                      "pen_home": f.get("pen_home"), "pen_away": f.get("pen_away")}, "winner": f.get("winner"),
            "events_n": f.get("events_n", 0), "updated": f.get("polled_at")}


def _names(db, fixtures):
    import queries as Q
    t = Q._names(db, "teams", [x for f in fixtures for x in (f.get("home_iid"), f.get("away_iid")) if x])
    ms = {m["iid"]: m["id"] for m in db.matches.find({"iid": {"$in": [f["match_iid"] for f in fixtures if f.get("match_iid")]}}, {"_id": 0, "iid": 1, "id": 1})}
    out = {("t", k): v for k, v in t.items()}
    out.update({("m", k): v for k, v in ms.items()})
    return out


def scoreboard(db, day: str | None = None, tz_offset_min: int = 0, now=None) -> dict:
    """Tracked fixtures for the user's local day, grouped by league, live first."""
    now = now or utcnow()
    d = datetime.fromisoformat(day).replace(tzinfo=timezone.utc) if day else now.replace(hour=0, minute=0, second=0, microsecond=0)
    d0 = d - timedelta(minutes=tz_offset_min)
    rows = list(db.live_fixtures.find({"kickoff": {"$gte": d0, "$lt": d0 + timedelta(days=1)}}, {"_id": 0}).sort("kickoff", 1))
    names = _names(db, rows)
    order = {LIVE: 0, "Scheduled": 1}
    rows.sort(key=lambda f: (order.get(f.get("status"), 2), f.get("kickoff") or now))
    groups = {}
    for f in rows:
        groups.setdefault(f.get("league_name") or "Other", []).append(public_fixture(f, names))
    st = db.sportapi_state.find_one({"_id": "live"}) or {}
    return {"leagues": [{"league": k, "fixtures": v} for k, v in groups.items()], "live_count": sum(1 for f in rows if f.get("status") == LIVE),
            "updated": st.get("last_tick")}


def events_for(db, sid: int) -> list:
    return [{k: e.get(k) for k in ("type", "side", "player_name", "minute", "minute_num", "extra")}
            for e in db.live_events.find({"fixture_sid": sid}, {"_id": 0}).sort("minute_num", 1)]


def lineups_for(db, sid: int) -> dict:
    out = {}
    for l in db.live_lineups.find({"fixture_sid": sid}, {"_id": 0}):
        ids = {p["iid"]: p["id"] for p in db.players.find({"iid": {"$in": [r["player_iid"] for r in l["players"] if r.get("player_iid")]}}, {"_id": 0, "iid": 1, "id": 1})}
        out[l["side"]] = {"starters": [dict({k: r.get(k) for k in ("name", "position", "shirt", "captain", "mins")}, player_id=ids.get(r.get("player_iid"))) for r in l["players"] if r["started"]],
                          "subs": [dict({k: r.get(k) for k in ("name", "position", "shirt", "captain", "mins")}, player_id=ids.get(r.get("player_iid"))) for r in l["players"] if not r["started"]]}
    return out


def results(db, day: str) -> dict:
    """Finished fixtures of tracked leagues on a date (from live polling or backfill). No external call."""
    rows = list(db.live_fixtures.find({"date": day, "status": {"$in": list(FINAL)}}, {"_id": 0}).sort("kickoff", 1))
    names = _names(db, rows)
    loaded = bool(db.sportapi_dates.find_one({"_id": day})) or bool(rows)
    return {"date": day, "loaded": loaded, "results": [public_fixture(f, names) for f in rows]}


def status(db, now=None) -> dict:
    now = now or utcnow()
    c = calls_today(db, now)
    st = db.sportapi_state.find_one({"_id": "live"}) or {}
    return {"enabled": bool(S.get(db, "sportapi.enabled")), "key_saved": bool(security.get_provider_key(db, PROVIDER, env_fallback="SPORTAPI_KEY")),
            "calls_today": c["n"], "by_kind": c["by_kind"], "cap": int(S.get(db, "sportapi.daily_calls")), "plan_limit": 2000,
            "leagues": S.get(db, "sportapi.leagues"), "last_tick": st.get("last_tick"), "last_result": st.get("last_result"),
            "live_now": db.live_fixtures.count_documents({"status": LIVE}),
            "teams": {s: db.sportapi_team_map.count_documents({"status": s}) for s in ("auto", "approved", "review", "none", "rejected")},
            "review": list(db.sportapi_team_map.find({"status": "review"}, {"_id": 0}).limit(50)),
            "dates_backfilled": db.sportapi_dates.count_documents({"complete": True})}
