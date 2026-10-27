"""ingest.py -- turn PitchAPI responses into our collections. Every call goes through PitchClient.

Idempotent by design: every write is an upsert keyed by external id, and
`matches.ingested_at` is set last. A crash mid-match leaves the match
un-ingested, so the next run redoes it. No transaction is needed.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import normalize as N
import settings_store as S
from cached_fetch import (FOREVER, BreakerOpen, BudgetExhausted, NotFound, PitchClient, Unauthorized,
                          next_iid, utcnow)


# ------------------------------------------------------------------ helpers
def parse_dt(s):
    if not s:
        return None
    return datetime.fromisoformat(s.replace("Z", "+00:00")).astimezone(timezone.utc)


def upsert_entity(db, coll: str, ext_id: str, fields: dict, on_insert: dict | None = None) -> int:
    """Create or update by ext_id. Returns the integer iid."""
    doc = db[coll].find_one({"ext_id": ext_id}, {"iid": 1})
    now = utcnow()
    if doc:
        db[coll].update_one({"ext_id": ext_id}, {"$set": {**fields, "updated_at": now}})
        return doc["iid"]
    iid = next_iid(db, coll)
    db[coll].insert_one({"id": str(uuid.uuid4()), "iid": iid, "ext_id": ext_id, "created_at": now,
                         "updated_at": now, **fields, **(on_insert or {})})
    return iid


def issue(db, kind: str, detail: str = "", match_iid: int | None = None, league_iid: int | None = None):
    db.ingest_issues.insert_one({"at": utcnow(), "kind": kind, "detail": detail, "match_iid": match_iid,
                                 "league_iid": league_iid, "resolved": False})


def enqueue(db, task: str, key: str, priority: int = 5, payload: dict | None = None, run_at: datetime | None = None):
    db.ingest_queue.update_one({"task": task, "key": key},
                               {"$setOnInsert": {"status": "pending", "attempts": 0, "created_at": utcnow(),
                                                 "next_run_at": run_at or utcnow()},
                                "$set": {"priority": priority, "payload": payload or {}}},
                               upsert=True)


def days(n): return timedelta(days=n)
def hours(n): return timedelta(hours=n)


# ------------------------------------------------------- reference: leagues
def sync_leagues(client: PitchClient) -> int:
    db = client.db
    data = client.fetch("/v1/leagues", ttl=days(S.get(db, "cache.ttl.reference_days")), purpose="leagues")
    n = 0
    for lg in data.get("leagues", []):
        iid = upsert_entity(db, "leagues", lg["id"],
                            {"name": lg.get("name"), "country_code": lg.get("country_code"),
                             "image_url": lg.get("image_url"), "seasons": lg.get("seasons", []),
                             "current_season": max(lg.get("seasons", []) or [None], key=lambda x: x or "")},
                            on_insert={"enabled": False, "backfill_seasons": []})   # new leagues start OFF
        for label in lg.get("seasons", []):
            db.seasons.update_one({"league_iid": iid, "label": label}, {"$setOnInsert": {"backfilled": False}}, upsert=True)
        n += 1
    return n


# ---------------------------------------------------- matches of one season
def sync_league_matches(client: PitchClient, league: dict, season: str | None = None, status: str = "all", force: bool = False) -> int:
    db = client.db
    season = season or league.get("current_season")
    finished_season = season != league.get("current_season")
    on_match_day = db.matches.count_documents({"league_iid": league["iid"], "status": "scheduled",
                                               "kickoff": {"$gte": utcnow(), "$lte": utcnow() + hours(24)}}) > 0
    ttl = FOREVER if (finished_season and status == "all") else \
        (hours(S.get(db, "cache.ttl.fixtures_matchday_hours")) if on_match_day else hours(S.get(db, "cache.ttl.fixtures_future_hours")))
    params = {"status": status}
    if season:
        params["season"] = season
    data = client.fetch(f"/v1/leagues/{league['ext_id']}/matches", params, ttl=ttl, purpose="league_matches", force=force)
    n = 0
    for raw in data.get("matches", []):
        m = N.match_row(raw, league["ext_id"], season)
        if m["status"] == "other":
            issue(db, "unknown_status", f"{m['ext_id']}: {m['provider_status']}", league_iid=league["iid"])
        h = upsert_entity(db, "teams", m["home_ext"], {"name": m["home_name"], "league_iid": league["iid"]})
        a = upsert_entity(db, "teams", m["away_ext"], {"name": m["away_name"], "league_iid": league["iid"]})
        prev = db.matches.find_one({"ext_id": m["ext_id"]}, {"ingested_at": 1})
        iid = upsert_entity(db, "matches", m["ext_id"],
                            {"league_iid": league["iid"], "season": season, "kickoff": parse_dt(m["kickoff_iso"]),
                             "status": m["status"], "provider_status": m["provider_status"],
                             "home_iid": h, "away_iid": a, "hg": m["hg"], "ag": m["ag"]},
                            on_insert={"ingested_at": None, "lineups_confirmed": False, "lineup_fetches": 0, "round": None})
        if m["status"] == "final" and not (prev and prev.get("ingested_at")):
            enqueue(db, "match_ingest", m["ext_id"], priority=5 if not finished_season else 7, payload={"match_iid": iid})
        n += 1
    return n


def assign_rounds(db, league_iid: int) -> int:
    """round = dense rank of distinct UTC kickoff dates in this league (all seasons, oldest = 0)."""
    ms = list(db.matches.find({"league_iid": league_iid, "kickoff": {"$ne": None}}, {"iid": 1, "kickoff": 1}))
    dates = sorted({m["kickoff"].date() for m in ms})
    rank = {d: i for i, d in enumerate(dates)}
    for m in ms:
        db.matches.update_one({"iid": m["iid"]}, {"$set": {"round": rank[m["kickoff"].date()]}})
    return len(dates)


# ----------------------------------------------------- one finished match
def _settings_bundle(db) -> dict:
    return {"team_keys": S.get(db, "provider.pitchapi.team_keys"),
            "player_keys": S.get(db, "provider.pitchapi.player_keys"),
            "position_map": S.get(db, "provider.position_map")}


def ingest_match(client: PitchClient, match: dict) -> bool:
    db = client.db
    ttl = days(S.get(db, "cache.raw_retention_days"))   # raw JSON is short-lived; our tables are the long-term store
    ext = match["ext_id"]
    stats = client.fetch(f"/v1/matches/{ext}/stats", ttl=ttl, purpose="stats")
    plyr = client.fetch(f"/v1/matches/{ext}/players", ttl=ttl, purpose="players")
    lnup = client.fetch(f"/v1/matches/{ext}/lineups", ttl=ttl, purpose="lineups")

    home = db.teams.find_one({"iid": match["home_iid"]}); away = db.teams.find_one({"iid": match["away_iid"]})
    mm = {"home_ext": home["ext_id"], "away_ext": away["ext_id"]}
    try:
        out = N.normalize_match(mm, stats, plyr.get("data", plyr) if isinstance(plyr, dict) else plyr, lnup, _settings_bundle(db))
    except N.MissingField as e:
        issue(db, "missing_field", str(e), match_iid=match["iid"], league_iid=match["league_iid"])
        return False
    for i in out["issues"]:
        issue(db, i["kind"], i["detail"], match_iid=match["iid"], league_iid=match["league_iid"])

    ko = match["kickoff"]
    iid_of_team = {home["ext_id"]: home["iid"], away["ext_id"]: away["iid"]}
    sides = (("home", home["iid"], away["iid"], match["hg"], match["ag"]),
             ("away", away["iid"], home["iid"], match["ag"], match["hg"]))
    for side, tid, oid, gf, ga in sides:
        opp_side = "away" if side == "home" else "home"
        t, o = out["team"][side], out["team"][opp_side]
        row = {"match_iid": match["iid"], "team_iid": tid, "opp_iid": oid, "kickoff": ko, "home": side == "home",
               "goals": gf, "goals_against": ga, "league_iid": match["league_iid"]}
        for c in N.TEAM_COLS:
            row[c] = t[c]
            if c in ("shots", "sot", "corners", "tackles", "xg"):
                row[c + "_against"] = o[c]
        db.team_match_stats.update_one({"match_iid": match["iid"], "team_iid": tid}, {"$set": row}, upsert=True)

    for p in out["players"]:
        tid = iid_of_team.get(p["team_ext_id"])
        if tid is None:
            issue(db, "player_team_unknown", f"{p['ext_id']} team {p['team_ext_id']}", match_iid=match["iid"]); continue
        pid = upsert_entity(db, "players", p["ext_id"], {"name": p["name"], "team_iid": tid, "pos": p["pos"], "pos_raw": p["pos_raw"]})
        side = "home" if tid == home["iid"] else "away"
        row = {"match_iid": match["iid"], "player_iid": pid, "team_iid": tid, "home": side == "home",
               "opp_iid": away["iid"] if side == "home" else home["iid"], "kickoff": ko,
               "league_iid": match["league_iid"], "pos": p["pos"], "pos_raw": p["pos_raw"], "started": p["started"],
               **{c: p[c] for c in N.PLAYER_COLS},
               "team_shots": out["team_totals"][side]["shots"], "team_sot": out["team_totals"][side]["sot"],
               "team_tackles": out["team_totals"][side]["tackles"]}
        db.player_match_stats.update_one({"match_iid": match["iid"], "player_iid": pid}, {"$set": row}, upsert=True)

    save_lineups(db, match, out["lineups"], iid_of_team)
    db.matches.update_one({"iid": match["iid"]}, {"$set": {"ingested_at": utcnow(), "lineups_confirmed": True}})
    if S.get(db, "ingest.match_extra_detail") or S.get(db, "ingest.match_extra_events"):
        enqueue(db, "match_extras", ext, priority=6, payload={"match_iid": match["iid"]})
    return True


def save_lineups(db, match: dict, lu: dict, iid_of_team: dict | None = None) -> None:
    home = db.teams.find_one({"iid": match["home_iid"]}); away = db.teams.find_one({"iid": match["away_iid"]})
    for side, team in (("home", home), ("away", away)):
        d = lu[side]
        for x in d["players"]:
            pl = db.players.find_one({"ext_id": x["ext_id"]}, {"iid": 1})
            pid = pl["iid"] if pl else upsert_entity(db, "players", x["ext_id"], {"name": x.get("name"), "team_iid": team["iid"], "pos": None})
            db.lineups.update_one({"match_iid": match["iid"], "team_iid": team["iid"], "player_iid": pid},
                                  {"$set": {"started": x["started"], "confirmed": d["confirmed"], "formation": d["formation"],
                                            "lineup_type": d["lineup_type"], "shirt_number": x["shirt_number"],
                                            "position_id": x["position_id"], "pitch_x": x["pitch_x"], "pitch_y": x["pitch_y"],
                                            "is_captain": x["is_captain"], "fetched_at": utcnow()}}, upsert=True)


# ------------------------------------------------------------- lineup watch
def lineup_watch(client: PitchClient, now: datetime | None = None) -> int:
    """Fetch lineups for upcoming matches on the schedule from settings. Returns real calls made."""
    db = client.db
    now = now or utcnow()
    if not S.get(db, "ingest.lineups_watch_enabled"):
        return 0
    before = client.calls_made
    cur = db.matches.find({"status": "scheduled", "lineups_confirmed": False,
                           "kickoff": {"$gte": now - hours(1), "$lte": now + hours(48)}})
    for m in cur:
        near = m["kickoff"].replace(tzinfo=timezone.utc) - now <= hours(3)
        if near and m.get("lineup_fetches", 0) >= S.get(db, "cache.ttl.lineups_near_max_refresh"):
            continue
        ttl = timedelta(minutes=S.get(db, "cache.ttl.lineups_near_minutes")) if near else hours(S.get(db, "cache.ttl.lineups_far_hours"))
        n0 = client.calls_made
        data = client.fetch(f"/v1/matches/{m['ext_id']}/lineups", ttl=ttl, purpose="lineups_watch")
        lu = N.lineups(data)
        save_lineups(db, m, lu)
        both = lu["home"]["confirmed"] and lu["away"]["confirmed"]
        fetched = client.calls_made > n0
        db.matches.update_one({"iid": m["iid"]}, {"$set": {"lineups_confirmed": both, **({"lineups_at": utcnow()} if fetched else {})},
                                                  "$inc": {"lineup_fetches": 1 if fetched else 0}})
    return client.calls_made - before


# ------------------------------------------------------------------- queue
def process_queue(client: PitchClient, max_tasks: int = 1000) -> dict:
    db = client.db
    done = skipped = failed = 0
    stop = None
    ref_leagues = set()
    while done + skipped + failed < max_tasks:
        t = db.ingest_queue.find_one_and_update(
            {"status": "pending", "next_run_at": {"$lte": utcnow()}},
            {"$set": {"status": "running", "started_at": utcnow()}}, sort=[("priority", 1), ("next_run_at", 1)])
        if not t:
            break
        try:
            if t["task"] == "match_ingest":
                m = db.matches.find_one({"ext_id": t["key"]})
                ok = ingest_match(client, m) if m and not m.get("ingested_at") else True
                db.ingest_queue.update_one({"_id": t["_id"]}, {"$set": {"status": "done" if ok else "skipped", "finished_at": utcnow()}})
                done += ok; skipped += (not ok)
            elif t["task"] == "match_referee":
                import cards_model as CM
                m = db.matches.find_one({"ext_id": t["key"], "status": "scheduled"})
                ok = bool(m) and CM.check_referee(client, m)
                db.ingest_queue.update_one({"_id": t["_id"]}, {"$set": {"status": "done" if ok else "skipped", "finished_at": utcnow()}})
                done += ok; skipped += (not ok)
            elif t["task"] == "match_extras":
                import match_extras as MX
                m = db.matches.find_one({"ext_id": t["key"]})
                ok = bool(m) and MX.ingest_extras(client, m)
                db.ingest_queue.update_one({"_id": t["_id"]}, {"$set": {"status": "done" if ok else "skipped", "finished_at": utcnow()}})
                done += ok; skipped += (not ok)
                if m: ref_leagues.add(m["league_iid"])
            else:
                raise ValueError("unknown task " + t["task"])
        except (BudgetExhausted, BreakerOpen, Unauthorized) as e:
            db.ingest_queue.update_one({"_id": t["_id"]}, {"$set": {"status": "pending"}})   # put it back, try later
            stop = type(e).__name__
            break
        except NotFound:
            attempts = t.get("attempts", 0) + 1
            if attempts >= 3:
                db.ingest_queue.update_one({"_id": t["_id"]}, {"$set": {"status": "failed", "attempts": attempts}}); failed += 1
                issue(db, "not_found_gave_up", t["key"])
            else:   # retry in 24 hours
                db.ingest_queue.update_one({"_id": t["_id"]}, {"$set": {"status": "pending", "attempts": attempts,
                                                                        "next_run_at": utcnow() + hours(24)}})
                skipped += 1
    if ref_leagues:
        import match_extras as MX
        for lg in ref_leagues:
            MX.rebuild_referees(db, lg)
    return {"done": done, "skipped": skipped, "failed": failed, "stopped_by": stop}


# ----------------------------------------------------------------- coverage
COVERAGE_FIELDS = {"team_match_stats": ["shots", "sot", "corners", "tackles", "poss", "xg"],
                   "player_match_stats": ["minutes", "shots", "sot", "tackles", "pos"]}


def update_coverage(db, league_iid: int) -> dict:
    """Share of rows with a non-null value, per field. A market below engine.coverage_min is off."""
    out = {}
    for coll, fields in COVERAGE_FIELDS.items():
        total = db[coll].count_documents({"league_iid": league_iid})
        for f in fields:
            have = db[coll].count_documents({"league_iid": league_iid, f: {"$ne": None}})
            share = have / total if total else 0.0
            out[f"{coll}.{f}"] = share
            db.data_coverage.update_one({"league_iid": league_iid, "field": f"{coll}.{f}"},
                                        {"$set": {"share": share, "rows": total, "at": utcnow()}}, upsert=True)
    return out
