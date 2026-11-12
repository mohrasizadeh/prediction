"""ingest_af.py -- API-Football into our tables. docs/88.

The piece that was missing. `apifootball.py` could talk to them and `normalize_af.py` could turn
their JSON into our shapes, and nothing joined the two: until this module existed, every fixture,
lineup and player row in the database still came from PitchAPI.

## The shape of it

Two different calls, for two different jobs, and the difference is the whole cost model:

    the schedule   GET /fixtures?league=&season=   one call per league-season, no statistics
    the detail     GET /fixtures?ids=a-b-c...      TWENTY fixtures a call, everything attached

`/fixtures?ids=` returns events, lineups, team statistics and player statistics inline, for up to
twenty fixtures at once (docs/82 §4). That is 0.05 calls a match where PitchAPI needed three, which
is the single reason a three-season backfill is affordable at all. So nothing here ever fetches one
match's detail on its own -- `ingest_bundle` is the only path, and it takes a list.

## What it does NOT do

It does not write our tables. `ingest.write_match` does, for both providers, because everything in
that function is about our schema and none of it is about a provider. A second copy would be sixty
lines of team totals and goal columns drifting quietly out of step with the first.

## The team-stamping rule

`teams.league_iid` is stamped by whichever competition ingested a club last, and `images.py` and the
engine both read clubs back by it. Ingest the Champions League after the Premier League and every
English club's `league_iid` points at the Champions League, which is how a club ends up in the wrong
frame and wearing the wrong crest.

So only a FORECAST competition stamps it (`af_leagues.is_forecast`). A cup or a calendar-only
competition upserts its clubs -- it needs them to write a fixture -- and leaves the stamp alone.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import af_leagues as AFL
import apifootball as AF
import ingest as I
import normalize_af as NAF
import settings_store as S

PROVIDER = AF.PROVIDER_KEY if hasattr(AF, "PROVIDER_KEY") else "apifootball"


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _settings(db) -> dict:
    """What `normalize_af.normalize_match` needs, read once per tick rather than per fixture."""
    return {
        "team_keys": S.get(db, "provider.apifootball.team_keys"),
        "position_map": S.get(db, "provider.apifootball.position_map"),
        "exclude_extra_time": S.get(db, "provider.apifootball.exclude_extra_time"),
    }


# ------------------------------------------------------------------ the schedule
def sync_fixtures(client, league: dict, season: int | str) -> dict:
    """One league-season's fixtures: teams and match rows, no statistics. One call.

    A finished season is cached for ever -- its fixtures cannot change -- and a current one for the
    usual fixture TTL, shorter on a match day.
    """
    db = client.db
    season = int(season)
    current = season >= _current_season(db, league)
    if current:
        on_match_day = db.matches.count_documents({
            "league_iid": league["iid"], "status": "scheduled",
            "kickoff": {"$gte": utcnow(), "$lte": utcnow() + timedelta(hours=24)}}) > 0
        hrs = S.get(db, "cache.ttl.fixtures_matchday_hours" if on_match_day else "cache.ttl.fixtures_future_hours")
        ttl = timedelta(hours=float(hrs))
    else:
        ttl = AF.FOREVER

    rows = client.fetch("/fixtures", {"league": int(league["ext_id"]), "season": season},
                        ttl=ttl, purpose="fixtures")
    stamp = AFL.is_forecast(db, league["iid"])
    n, queued = 0, 0
    for raw in rows:
        m = NAF.match_row(raw)
        if m["status"] == "other":
            I.issue(db, "unknown_status", f"{m['ext_id']}: {m['provider_status']}", league_iid=league["iid"])
        h = _team(db, m["home_ext"], m["home_name"], league["iid"], stamp)
        a = _team(db, m["away_ext"], m["away_name"], league["iid"], stamp)
        prev = db.matches.find_one({"ext_id": m["ext_id"]}, {"ingested_at": 1})
        iid = I.upsert_entity(db, "matches", m["ext_id"],
                              {"league_iid": league["iid"], "season": str(season),
                               "kickoff": I.parse_dt(m["kickoff_iso"]), "status": m["status"],
                               "provider_status": m["provider_status"], "home_iid": h, "away_iid": a,
                               "hg": m["hg"], "ag": m["ag"], "extra_time": m.get("extra_time", False),
                               "referee": m.get("referee"), "venue": m.get("venue")},
                              on_insert={"ingested_at": None, "lineups_confirmed": False,
                                         "lineup_fetches": 0, "round": None})
        if m["status"] == "final" and not (prev and prev.get("ingested_at")):
            I.enqueue(db, "af_match", m["ext_id"], priority=5 if current else 7, payload={"match_iid": iid})
            queued += 1
        n += 1
    return {"fixtures": n, "queued": queued, "season": season, "league_iid": league["iid"]}


def _team(db, ext_id: str, name: str | None, league_iid: int, stamp: bool) -> int:
    """Upsert a club. `league_iid` is written only by a forecast competition -- see the module note."""
    fields = {"name": name}
    if stamp:
        fields["league_iid"] = league_iid
    return I.upsert_entity(db, "teams", ext_id, fields, on_insert={"league_iid": league_iid})


def _current_season(db, league: dict) -> int:
    """The newest season the catalogue says this competition has, or this calendar year."""
    row = db.af_catalog.find_one({"_id": int(league["ext_id"])}, {"years": 1}) or {}
    years = [y for y in (row.get("years") or []) if y]
    return max(years) if years else utcnow().year


# ------------------------------------------------------------------ the detail
def ingest_bundle(client, matches: list[dict]) -> dict:
    """Statistics, lineups and player rows for a LIST of matches. Twenty a call.

    Taking a list rather than a match is the point: one at a time would be one call each, which is
    the cost model we moved away from. Callers that have a single match still pass `[match]` -- the
    saving is real only in bulk, but the interface should not tempt anyone to loop.
    """
    db = client.db
    if not matches:
        return {"asked": 0, "written": 0, "missing": 0, "failed": 0}
    settings = _settings(db)
    by_ext = {str(m["ext_id"]): m for m in matches}
    bundles = AF.fixtures_bundle(client, [int(e) for e in by_ext])
    written = failed = 0
    for ext, match in by_ext.items():
        fixture = bundles.get(int(ext))
        if fixture is None:
            I.issue(db, "fixture_missing", f"{ext} was not in the answer",
                    match_iid=match["iid"], league_iid=match["league_iid"])
            continue
        try:
            out = NAF.normalize_match(fixture, settings)
        except Exception as e:                      # a normalizer fault is about THIS fixture only
            I.issue(db, "normalize_failed", f"{ext}: {type(e).__name__}: {e}",
                    match_iid=match["iid"], league_iid=match["league_iid"])
            failed += 1
            continue
        for i in out["issues"]:
            I.issue(db, i["kind"], i["detail"], match_iid=match["iid"], league_iid=match["league_iid"])
        I.write_match(db, match, out)
        _write_events(db, match, out.get("events") or [])
        written += 1
    return {"asked": len(by_ext), "written": written,
            "missing": len(by_ext) - written - failed, "failed": failed}


def _write_events(db, match: dict, ev: list[dict]) -> None:
    """Goals, cards and substitutions, in the shape `queries.py` and `cards_model.py` already read.

    On PitchAPI these were a call per match behind `ingest.match_extra_detail` (`match_extras.py`),
    so the referee model went hungry whenever the budget was tight. Here they arrive attached to the
    bundle that was fetched for the statistics, so they cost nothing and there is nothing to switch
    on. The stored shape is `match_extras`'s, down to `dedupe` -- the same readers read both.
    """
    if not ev:
        return
    import match_extras as MX
    tid = {"home": match["home_iid"], "away": match["away_iid"]}
    rows = []
    for e in ev:
        e = dict(e)
        e["team_iid"] = tid[e["side"]]
        pl = db.players.find_one({"ext_id": e.pop("player_ext", None)}, {"iid": 1}) if e.get("player_ext") else None
        e["player_iid"] = (pl or {}).get("iid")
        ip = db.players.find_one({"ext_id": e.pop("in_ext", None)}, {"iid": 1}) if e.get("in_ext") else None
        e["in_iid"] = (ip or {}).get("iid")
        rows.append(e)
    rows = MX.dedupe(rows)       # a second yellow arrives as a yellow AND a red at the same minute
    db.match_events.update_one({"match_iid": match["iid"]},
                               {"$set": {"match_iid": match["iid"], "league_iid": match["league_iid"],
                                         "kickoff": match["kickoff"], "events": rows}}, upsert=True)


# ------------------------------------------------------------------ draining the queue
QUEUE_TASK = "af_match"


def drain(client, max_seconds: float = 40.0, batch: int = AF.IDS_PER_CALL) -> dict:
    """Work the queue in bundles of twenty until the time runs out or it empties."""
    db = client.db
    import time
    t0 = time.monotonic()
    done = {"batches": 0, "written": 0, "failed": 0, "missing": 0}
    while time.monotonic() - t0 < max_seconds:
        # `next_run_at`, which is what `ingest.enqueue` writes. Querying `run_at` matched nothing
        # and the drain reported an empty queue while the queue was full -- a silent no-op, not an
        # error, which is the kind of bug a test catches and a run does not.
        tasks = list(db.ingest_queue.find(
            {"task": QUEUE_TASK, "status": "pending", "next_run_at": {"$lte": utcnow()}}
        ).sort([("priority", 1), ("next_run_at", 1)]).limit(batch))
        if not tasks:
            break
        ids = [t["_id"] for t in tasks]
        db.ingest_queue.update_many({"_id": {"$in": ids}},
                                    {"$set": {"status": "running", "started_at": utcnow()}})
        matches = []
        for t in tasks:
            m = db.matches.find_one({"iid": (t.get("payload") or {}).get("match_iid")})
            if m:
                matches.append(m)
        try:
            res = ingest_bundle(client, matches)
        except (AF.BudgetExhausted, AF.BreakerOpen, AF.Unauthorized, AF.PlanLimited):
            # Put the batch back and stop: these are about the ACCOUNT, not these fixtures, and
            # retrying them in a tighter loop is what turns a throttle into a block.
            db.ingest_queue.update_many({"_id": {"$in": ids}}, {"$set": {"status": "pending"}})
            raise
        db.ingest_queue.update_many({"_id": {"$in": ids}},
                                    {"$set": {"status": "done", "finished_at": utcnow()}})
        done["batches"] += 1
        for k in ("written", "failed", "missing"):
            done[k] += res[k]
    return done


# ------------------------------------------------------------------ what a tick does
def backfill_tick(client, max_seconds: float = 40.0) -> dict:
    """Pick up where the backfill left off: sync any league-season still owed, then drain.

    A season is "owed" while it is listed in the league's `backfill_seasons` and has no record of
    having been synced. The record is per league-season so a half-finished backfill resumes instead
    of starting again -- the calls it already spent are not spent twice.
    """
    db = client.db
    out = {"synced": [], **{k: 0 for k in ("batches", "written", "failed", "missing")}}
    _drop_malformed_seasons(db)
    for lg in db.leagues.find({"enabled": True, "provider": PROVIDER}):
        for season in (lg.get("backfill_seasons") or []):
            # `label`, which is what this collection is keyed on. This wrote `season` instead, so
            # the upsert made a row with NO label at all -- and the unique index is
            # (league_iid, label), so the first season of a league created `label: null` and the
            # second one collided with it:
            #
            #   E11000 duplicate key ... dup key: { league_iid: 22, label: null }
            #
            # The backfill died on its second season of the first league, every time. `af_leagues`,
            # `ingest` and the leagues screen all use `label`; only this did not.
            key = {"league_iid": lg["iid"], "label": str(season)}
            if db.seasons.find_one({**key, "fixtures_synced_at": {"$ne": None}}):
                continue
            res = sync_fixtures(client, lg, season)
            db.seasons.update_one(key, {"$set": {**key, "fixtures_synced_at": utcnow(),
                                                 "fixtures": res["fixtures"], "queued": res["queued"]},
                                        "$setOnInsert": {"backfilled": False}},
                                  upsert=True)
            out["synced"].append(res)
    drained = drain(client, max_seconds=max_seconds)
    for k in ("batches", "written", "failed", "missing"):
        out[k] = drained[k]
    out["finished"] = _mark_finished_seasons(db)
    return out


def _drop_malformed_seasons(db) -> int:
    """Clear the `label: null` rows the bug above wrote, which block every later upsert.

    They carry nothing -- no label means no season -- and leaving one in place keeps the unique
    index occupied so the first real write for that league fails too. Cheap, and idempotent.
    """
    return db.seasons.delete_many({"$or": [{"label": None}, {"label": {"$exists": False}}]}).deleted_count


def _mark_finished_seasons(db) -> int:
    """A season is backfilled when its fixtures are synced and nothing of its is left in the queue.

    Without this the Competitions screen says "0 backfilled" for ever, however much has landed: the
    flag was only ever written by the PitchAPI path.
    """
    n = 0
    for s in db.seasons.find({"fixtures_synced_at": {"$ne": None}, "backfilled": {"$ne": True}},
                             {"league_iid": 1, "label": 1}):
        # `.get`, not `[...]`. A row with no label is exactly what the bug above wrote, and this
        # reads the collection it corrupted -- so the repair and the reader have to tolerate the
        # same malformed row. Written as `s["label"]` first, which turned a duplicate-key error
        # into a KeyError one line later.
        label = s.get("label")
        if not label or s.get("league_iid") is None:
            continue
        iids = [m["iid"] for m in db.matches.find(
            {"league_iid": s["league_iid"], "season": label, "status": "final"}, {"iid": 1})]
        if not iids:
            continue
        left = db.ingest_queue.count_documents(
            {"task": QUEUE_TASK, "status": {"$ne": "done"}, "payload.match_iid": {"$in": iids}})
        if left == 0:
            db.seasons.update_one({"_id": s["_id"]}, {"$set": {"backfilled": True}})
            n += 1
    return n
