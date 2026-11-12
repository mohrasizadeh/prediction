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
from cached_fetch import (FOREVER, BreakerOpen, BudgetExhausted, NotFound, PitchClient, PitchError, Unauthorized,
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


def upsert_player(db, p: dict, team_iid: int, kickoff) -> int:
    """Create or update a player, and set his club from his LATEST match only.

    The queue does not run in date order (it sorts by priority, and a failed task is retried later), so taking the
    club from whichever match happened to be processed last put a loaned player back at the club he left: an old
    match ingested after a recent one overwrote it. `team_as_of` records the kick-off the club came from, and an
    older match never moves it (docs/41)."""
    cur = db.players.find_one({"ext_id": p["ext_id"]}, {"_id": 0, "iid": 1, "team_as_of": 1})
    fields = {"name": p["name"], "pos": p["pos"], "pos_raw": p["pos_raw"]}
    as_of = cur.get("team_as_of") if cur else None
    if as_of is not None and as_of.tzinfo is None:
        as_of = as_of.replace(tzinfo=timezone.utc)
    ko = kickoff.replace(tzinfo=timezone.utc) if kickoff is not None and kickoff.tzinfo is None else kickoff
    if cur is None or as_of is None or (ko is not None and ko >= as_of):
        fields["team_iid"] = team_iid
        fields["team_as_of"] = ko
    return upsert_entity(db, "players", p["ext_id"], fields)


def refresh_player_clubs(db, league_iid: int | None = None) -> int:
    """Put every player at the club he last played for. Repairs rows written before `team_as_of` existed, and
    anything a provider correction leaves behind. One pass over the stats, newest first."""
    q = {"league_iid": league_iid} if league_iid else {}
    latest: dict = {}
    for r in db.player_match_stats.find(q, {"_id": 0, "player_iid": 1, "team_iid": 1, "kickoff": 1}).sort("kickoff", -1):
        if r["player_iid"] not in latest:
            latest[r["player_iid"]] = r
    n = 0
    for pid, r in latest.items():
        ko = r["kickoff"].replace(tzinfo=timezone.utc) if r.get("kickoff") is not None and r["kickoff"].tzinfo is None else r.get("kickoff")
        res = db.players.update_one({"iid": pid, "$or": [{"team_iid": {"$ne": r["team_iid"]}},
                                                          {"team_as_of": {"$exists": False}}, {"team_as_of": None}]},
                                    {"$set": {"team_iid": r["team_iid"], "team_as_of": ko}})
        n += res.modified_count
    return n


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

    write_match(db, match, out)
    if S.get(db, "ingest.match_extra_detail") or S.get(db, "ingest.match_extra_events"):
        enqueue(db, "match_extras", ext, priority=6, payload={"match_iid": match["iid"]})
    return True


def write_match(db, match: dict, out: dict) -> None:
    """Normalized output -> our tables. THE ONE WRITER, for every provider.

    `out` is whatever a normalizer returns -- `normalize.normalize_match` for PitchAPI,
    `normalize_af.normalize_match` for API-Football -- and the two return the same shape on purpose
    (docs/85). Everything below this line is about OUR schema and none of it is about a provider, so
    a second provider that copied it would be sixty lines of team totals and goal columns drifting
    quietly out of step with these. The fetching differs; the writing must not.
    """
    home = db.teams.find_one({"iid": match["home_iid"]}); away = db.teams.find_one({"iid": match["away_iid"]})
    iid_of_team = {home["ext_id"]: home["iid"], away["ext_id"]: away["iid"]}
    ko = match["kickoff"]
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

    # His club's goals in this match, for the player rows below. The engine builds a player's rate
    # as his SHARE OF A TEAM TOTAL -- `shrunk_rate(ap[s], E=ap["team_"+s] * minutes/90)` -- so a
    # market can only exist for a stat whose team total is on the player row. shots, on target and
    # tackles have been there since the start; goals never was, which is one of the things standing
    # between the provider's `goals` column (mapped, ingested, zero-filled) and a goals market.
    # Written now rather than with the rest of that work because history has to ACCUMULATE: the
    # engine reads engine.history_rounds back, and a column added later starts empty.
    goals_of = {"home": match["hg"], "away": match["ag"]}
    for p in out["players"]:
        tid = iid_of_team.get(p["team_ext_id"])
        if tid is None:
            issue(db, "player_team_unknown", f"{p['ext_id']} team {p['team_ext_id']}", match_iid=match["iid"]); continue
        pid = upsert_player(db, p, tid, ko)
        side = "home" if tid == home["iid"] else "away"
        row = {"match_iid": match["iid"], "player_iid": pid, "team_iid": tid, "home": side == "home",
               "opp_iid": away["iid"] if side == "home" else home["iid"], "kickoff": ko,
               "league_iid": match["league_iid"], "pos": p["pos"], "pos_raw": p["pos_raw"], "started": p["started"],
               **{c: p[c] for c in (*N.PLAYER_COLS, *N.DERIVED_PLAYER_COLS)},
               "team_shots": out["team_totals"][side]["shots"], "team_sot": out["team_totals"][side]["sot"],
               "team_tackles": out["team_totals"][side]["tackles"], "team_goals": goals_of[side],
               # docs/70. Two more team totals, for the same reason team_goals was written: a market
               # cannot exist for a stat whose team total is missing from the player row, and a
               # column added later starts EMPTY -- the engine reads engine.history_rounds back, so
               # these have to accumulate before either market can be switched on.
               "team_fouls_committed": out["team_totals"][side]["fouls_committed"],
               "team_goal_involvements": out["team_totals"][side]["goal_involvements"]}
        db.player_match_stats.update_one({"match_iid": match["iid"], "player_iid": pid}, {"$set": row}, upsert=True)

    save_lineups(db, match, out["lineups"], iid_of_team)
    db.matches.update_one({"iid": match["iid"]}, {"$set": {"ingested_at": utcnow(), "lineups_confirmed": True}})


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
STUCK_AFTER = timedelta(minutes=15)     # a task "running" longer than this was cut off (crash, restart, timeout)
MAX_ATTEMPTS = 5


def _retry_later(db, t, err: str) -> bool:
    """Back-off retry for a task that raised. Returns True when it gave up. (docs/36 H4)"""
    attempts = t.get("attempts", 0) + 1
    if attempts >= MAX_ATTEMPTS:
        db.ingest_queue.update_one({"_id": t["_id"]}, {"$set": {"status": "failed", "attempts": attempts, "last_error": err, "finished_at": utcnow()}})
        issue(db, "task_failed", f"{t['task']} {t['key']}: {err}")
        return True
    wait = min(timedelta(minutes=15) * (2 ** (attempts - 1)), hours(24))     # 15 min, 30, 60, 120
    db.ingest_queue.update_one({"_id": t["_id"]}, {"$set": {"status": "pending", "attempts": attempts, "last_error": err,
                                                            "next_run_at": utcnow() + wait}})
    return False


def release_stuck(db, now: datetime | None = None) -> int:
    """Tasks left "running" by a crash or restart go back to the queue (they count as one attempt)."""
    now = now or utcnow()
    n = 0
    for t in db.ingest_queue.find({"status": "running", "started_at": {"$lt": now - STUCK_AFTER}}):
        _retry_later(db, t, "interrupted while running")
        n += 1
    return n


def process_queue(client: PitchClient, max_tasks: int = 1000) -> dict:
    db = client.db
    done = skipped = failed = 0
    stop = None
    ref_leagues = set()
    release_stuck(db)
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
            elif t["task"] in ("player_photo", "league_logo", "team_crest"):
                import pitch_photos as PP
                kind = {"player_photo": "player", "league_logo": "league", "team_crest": "team"}[t["task"]]
                res = PP.fetch_image(client, kind, t["key"])
                db.ingest_queue.update_one({"_id": t["_id"]}, {"$set": {"status": "done", "result": res, "finished_at": utcnow()}})
                done += 1
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
        except PitchError as e:
            # the provider failed after its own retries (timeout, 5xx): retry this task later and stop the run,
            # so an outage does not burn the budget on every other task
            failed += _retry_later(db, t, f"{type(e).__name__}: {e}"[:300])
            stop = "PitchError"
            break
        except Exception as e:           # bad payload, bug: never leave the task "running" (docs/36 H4)
            if _retry_later(db, t, f"{type(e).__name__}: {e}"[:300]):
                failed += 1
            else:
                skipped += 1
    if ref_leagues:
        import match_extras as MX
        for lg in ref_leagues:
            MX.rebuild_referees(db, lg)
    return {"done": done, "skipped": skipped, "failed": failed, "stopped_by": stop}


# ----------------------------------------------------------------- coverage
def fill_team_goals(db, league_iid: int | None = None, dry_run: bool = True) -> dict:
    """Backfill `team_goals` on player rows stored before the column existed.

    The engine builds a player's rate as his share of a team total, so a market needs that total on
    his row. Goals is the one the product most wants next and the only one of the four whose total
    was never written. This copies it from `team_match_stats.goals`, which is the match score and
    has always been stored, so nothing is inferred and nothing can be invented.

    Guards, lighter than the other two backfills because the source is a fact rather than an
    absence: the match must have a stored team row with a goals figure, and a row that already has
    the column is left alone, so it is idempotent. `dry_run` by default.
    """
    q = {"team_goals": None}
    if league_iid is not None:
        q["league_iid"] = league_iid
    todo = db.player_match_stats.count_documents(q)
    out = {"ok": True, "dry_run": dry_run, "league_iid": league_iid, "candidates": todo, "filled": 0}
    if not todo:
        out.update({"ok": False, "reason": "every player row already carries its club's goals"})
        return out
    goals = {(t["match_iid"], t["team_iid"]): t.get("goals")
             for t in db.team_match_stats.find({} if league_iid is None else {"league_iid": league_iid},
                                               {"_id": 0, "match_iid": 1, "team_iid": 1, "goals": 1})}
    n = 0
    for r in db.player_match_stats.find(q, {"_id": 1, "match_iid": 1, "team_iid": 1}):
        g = goals.get((r["match_iid"], r["team_iid"]))
        if g is None:
            continue
        n += 1
        if not dry_run:
            db.player_match_stats.update_one({"_id": r["_id"]}, {"$set": {"team_goals": float(g)}})
    out["filled"] = n
    out["no_team_row"] = todo - n
    return out


def fill_player_tackles(db, league_iid: int | None = None, dry_run: bool = True) -> dict:
    """Backfill `tackles` on history ingested while a 0 tackle count was stored as null.

    The provider omits a count when it is 0. `tackles` was not in ZERO_WHEN_ABSENT, so a forward
    who made no tackle stored `tackles: None` -- and because `tackles` is in
    engine_bridge.PLAYER_REQUIRED, `dropna` deleted that whole appearance from the engine's frame.
    The engine then reads a missing appearance as a match the player MISSED, which collapses his
    chance to play, which at `engine.min_p_play` drops every card he has in every market. It is
    position-correlated: a forward is who records no tackle. New ingests are correct; this repairs
    what is already stored.

    Guards, in the same spirit as fill_player_goal_cols, because writing a 0 where the truth is
    "we were never told" is worse than the null it replaces:

    * THE MAPPING GATE. If `provider.pitchapi.player_keys.tackles.key` is unset the column was
      never read, so every row is null and filling them would record that nobody in the league
      ever made a tackle.
    * NOT A GOALKEEPER. A keeper has no defence group at all; his tackles are null by rule
      (normalize.py), and that null is correct.
    * A REAL APPEARANCE, AND PROOF THE ROW WAS PARSED. `minutes` must be set and `shots` non-null.
    * THE SHARE GATE, which the goals backfill did not need. There is no stored evidence that the
      DEFENCE group was present on an old row -- `shots` only proves `top_stats` was. So the share
      of qualifying rows that are null is used as the evidence instead: a genuine omitted-zero
      pattern leaves a minority of appearances null, while a league whose defence group was never
      parsed leaves nearly all of them null. Above `max_null_share` the function refuses, because
      at that point a fill would be inventing a league of players who never tackle.

    Idempotent, and `dry_run` by default.
    """
    keys = S.get(db, "provider.pitchapi.player_keys") or {}
    max_null_share = 0.8
    if not (keys.get("tackles") or {}).get("key"):
        return {"ok": False, "reason": "provider does not map tackles -- every row is null, so filling "
                                       "zeros would record that nobody ever made a tackle",
                "tackles": 0, "candidates": 0, "null_share": None, "dry_run": dry_run, "league_iid": league_iid}
    q = {"pos": {"$ne": "GK"}, "minutes": {"$gt": 0}, "shots": {"$ne": None}}
    if league_iid is not None:
        q["league_iid"] = league_iid
    total = db.player_match_stats.count_documents(q)
    nulls = db.player_match_stats.count_documents({**q, "tackles": None})
    share = (nulls / total) if total else 0.0
    out = {"ok": True, "dry_run": dry_run, "league_iid": league_iid, "candidates": total,
           "tackles": nulls, "null_share": round(share, 4)}
    if not total:
        out.update({"ok": False, "reason": "no appearances in scope"})
        return out
    if share > max_null_share:
        out.update({"ok": False, "tackles": 0,
                    "reason": f"{round(share * 100)}% of appearances have no tackle count, which reads as a "
                              f"defence group that was never parsed rather than as omitted zeros; "
                              f"check provider.pitchapi.player_keys.tackles and re-ingest instead"})
        return out
    if not dry_run and nulls:
        db.player_match_stats.update_many({**q, "tackles": None}, {"$set": {"tackles": 0.0}})
    return out


def fill_player_team_totals(db, league_iid: int | None = None, dry_run: bool = True) -> dict:
    """Backfill team_fouls_committed and team_goal_involvements on history (docs/70).

    The engine builds a player's rate as his SHARE OF A TEAM TOTAL, so a market cannot exist for a
    stat whose team total is missing from the player row. Those two columns began being written
    with this change, which means every row ingested before it has them empty -- and the engine
    reads `engine.history_rounds` back, so both markets would be dropped as having no data until a
    season's worth of new matches had accumulated.

    Nothing here calls the provider. Both totals are sums over player rows the database already
    holds, so this is a read and a write over existing history and costs no quota.
    """
    q = {}
    if league_iid is not None:
        q["league_iid"] = league_iid
    out = {"ok": True, "dry_run": dry_run, "league_iid": league_iid, "matches": 0, "rows": 0, "skipped_no_source": 0}
    for key in db.player_match_stats.aggregate([{"$match": q}, {"$group": {"_id": {"m": "$match_iid", "t": "$team_iid"}}}]):
        mid, tid = key["_id"]["m"], key["_id"]["t"]
        rows = list(db.player_match_stats.find({"match_iid": mid, "team_iid": tid},
                                               {"_id": 1, "fouls_committed": 1, "goal_involvements": 1}))
        out["matches"] += 1
        set_ = {}
        for col, dest in (("fouls_committed", "team_fouls_committed"), ("goal_involvements", "team_goal_involvements")):
            vals = [r[col] for r in rows if r.get(col) is not None]
            # No source values at all means the market was never ingested for this league. Writing a
            # 0 would be inventing a fact -- the same error normalize.players exists to avoid -- so
            # the column is left empty and the market is dropped for that league instead.
            if vals:
                set_[dest] = float(sum(vals))
        if not set_:
            out["skipped_no_source"] += 1
            continue
        if not dry_run:
            db.player_match_stats.update_many({"match_iid": mid, "team_iid": tid}, {"$set": set_})
        out["rows"] += len(rows)
    return out


def fill_player_goal_cols(db, league_iid: int | None = None, dry_run: bool = True) -> dict:
    """Backfill goals / assists / goal_involvements on history ingested before they were zero-filled.

    Until now only `shots` and `sot` were filled, so a player who did not score stored goals=None.
    Any per-90 rate built on that divides his goals by the games he SCORED in: every scorer in the
    league comes out near 1.0 a game, which is a plausible number rather than an obviously broken
    one, so nothing downstream would have caught it.

    Three guards, because writing a 0 where the truth is "we were never told" is worse than the
    null it replaces:

    * THE MAPPING GATE. If `provider.pitchapi.player_keys.goals.key` is unset, the column was never
      read, so EVERY row is null -- and filling them would record that nobody in the league has
      ever scored, at 100% coverage. The function refuses and says so. This is the gate that makes
      the rest safe, and it is the one a careless backfill would skip.
    * PROOF THE ROW WAS READ. Only rows whose `shots` is non-null are touched. `shots` is itself
      zero-filled at ingest and only when its group was present, so a non-null `shots` is evidence
      that this player's stats group really was parsed. A row the provider never gave us keeps its
      nulls.
    * A REAL APPEARANCE. `minutes` must be set. Someone who did not play has no 0 to record.

    Idempotent, and `dry_run` by default: it reports what it would do and writes nothing.
    """
    keys = S.get(db, "provider.pitchapi.player_keys") or {}
    unmapped = [c for c in ("goals", "assists") if not (keys.get(c) or {}).get("key")]
    if unmapped:
        # Same shape as the success path, so a caller never has to branch on which keys exist.
        return {"ok": False, "reason": f"provider does not map {', '.join(unmapped)} -- every row is null, "
                                       f"so filling zeros would record that nobody ever scored",
                "goals": 0, "assists": 0, "involvements": 0, "rows_with_a_goal": 0,
                "dry_run": dry_run, "league_iid": league_iid}
    q = {"minutes": {"$ne": None}, "shots": {"$ne": None}}
    if league_iid is not None:
        q["league_iid"] = league_iid
    out = {"ok": True, "dry_run": dry_run, "league_iid": league_iid}
    for col in ("goals", "assists"):
        out[col] = db.player_match_stats.count_documents({**q, col: None})
        if not dry_run and out[col]:
            db.player_match_stats.update_many({**q, col: None}, {"$set": {col: 0.0}})
    # Now that both parts are known on those rows, the derived column follows.
    inv_q = {**q, "goals": {"$ne": None}, "assists": {"$ne": None}, "goal_involvements": None}
    out["involvements"] = db.player_match_stats.count_documents(inv_q) if dry_run else 0
    if not dry_run:
        n = 0
        for r in db.player_match_stats.find(inv_q, {"_id": 1, "goals": 1, "assists": 1}):
            db.player_match_stats.update_one({"_id": r["_id"]},
                                             {"$set": {"goal_involvements": float(r["goals"]) + float(r["assists"])}})
            n += 1
        out["involvements"] = n
    # A league in which nobody has scored is not a league. Report it rather than return a clean zero:
    # it means the mapping gate passed but the column still holds nothing real.
    scored = db.player_match_stats.count_documents({**q, "goals": {"$gt": 0}})
    out["rows_with_a_goal"] = scored
    if not scored:
        out["ok"] = False
        out["reason"] = "no row in scope records a goal -- the column is mapped but carries nothing, so do not trust a fill here"
    return out


COVERAGE_FIELDS = {"team_match_stats": ["shots", "sot", "corners", "tackles", "poss", "xg"],
                   "player_match_stats": ["minutes", "shots", "sot", "tackles", "pos", "passes", "fouls_won", "fouls_committed",
                                          "goals", "assists", "goal_involvements", "xg"]}


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
