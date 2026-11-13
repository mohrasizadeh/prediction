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
        # A MATCH DAY IS NOT OVER WHEN THE LAST KICK-OFF HAS PASSED.
        #
        # This counted only fixtures still `scheduled` in the next 24 hours, so the moment the last
        # match of a round kicked off the league stopped looking like a match day and the fixture
        # list fell back to the six-hour TTL -- exactly when the results are landing and we most
        # want a fresh answer. A league could therefore be re-synced and still be handed a cached
        # list in which every match was `scheduled`, queueing nothing.
        #
        # Count the recent past as well: anything that kicked off in the last six hours is either
        # still being played or has just finished, and in both cases the answer is still moving.
        now_ = utcnow()
        on_match_day = db.matches.count_documents({
            "league_iid": league["iid"],
            "kickoff": {"$gte": now_ - timedelta(hours=6), "$lte": now_ + timedelta(hours=24)}}) > 0
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
                               "referee": m.get("referee"), "venue": m.get("venue"),
                               # The provider's round NAME ("Group Stage - 2", "Quarter-finals").
                               # `round` is our own matchday rank (assign_rounds); a cup's shape --
                               # groups, then knockout rounds -- needs theirs (standings.py).
                               "stage": m.get("round"),
                               "pen_home": ((raw.get("score") or {}).get("penalty") or {}).get("home"),
                               "pen_away": ((raw.get("score") or {}).get("penalty") or {}).get("away")},
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
    # FORCE A FRESH ANSWER. This shares `/fixtures?ids=...` with the live-statistics step, and the
    # whole point of this call is the FINAL numbers -- a cached answer here is, by construction,
    # one taken while the match was still being played. It costs no extra call, only a cache miss.
    bundles = AF.fixtures_bundle(client, [int(e) for e in by_ext], force=True)
    written = failed = 0
    for ext, match in by_ext.items():
        fixture = bundles.get(int(ext))
        if fixture is None:
            I.issue(db, "fixture_missing", f"{ext} was not in the answer",
                    match_iid=match["iid"], league_iid=match["league_iid"])
            continue
        # ONE FIXTURE'S FAULT IS ONE FIXTURE'S FAULT. The normalizer was guarded and the WRITE was
        # not, so anything raising inside write_match -- a DuplicateKeyError, a bad field -- escaped
        # drain entirely and the batch of twenty stayed `status: "running"` for ever: the
        # update_many that marks them done never ran, nothing on this path calls release_stuck, and
        # `_mark_finished_seasons` needs "done", so the season never completed either. The whole
        # write is inside the guard now.
        try:
            out = NAF.normalize_match(fixture, settings)
            for i in out["issues"]:
                I.issue(db, i["kind"], i["detail"], match_iid=match["iid"], league_iid=match["league_iid"])
            I.write_match(db, match, out)
            _write_events(db, match, out.get("events") or [])
            # THE MATCH IS OVER, SO SAY SO ON THE MATCH ROW.
            #
            # `sync_fixtures` used to be the only thing that queued a finished match, and it sets
            # `status` from the fixture list as it goes. The live tick now queues one the moment it
            # goes final (docs/90), and that path reached `write_match` without ever touching the
            # match row's own status -- so a match could have both sides' `team_match_stats`, all
            # 22 player rows and an `ingested_at`, while `matches.status` still read "scheduled".
            #
            # `queries._match_stats` returns (None, []) for anything that is not "final", so the
            # page showed NO statistics at all on a match whose numbers were sitting in the
            # database, until the next `af_fixtures` sweep corrected the status up to six hours
            # later. That is the delay this whole change set out to remove, one layer further up.
            #
            # The bundle is the same answer the fixture list would have given, so take the status
            # and the score from it rather than waiting to be told again.
            row = NAF.match_row(fixture)
            if row.get("status") == "final":
                db.matches.update_one({"iid": match["iid"]},
                                      {"$set": {"status": "final",
                                                "provider_status": row.get("provider_status"),
                                                "hg": row.get("hg"), "ag": row.get("ag"),
                                                "extra_time": row.get("extra_time", False)}})
        except Exception as e:
            I.issue(db, "normalize_failed", f"{ext}: {type(e).__name__}: {e}",
                    match_iid=match["iid"], league_iid=match["league_iid"])
            failed += 1
            continue
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
    # NO EARLY RETURN ON AN EMPTY LIST. A 0-0 with no card and no substitution is a real result, and
    # bailing out here would leave `extras_at` unset on it for ever -- which is exactly the flag
    # `score_finished` checks before grading a card forecast, so that match's card lines would never
    # be graded and the zeros below would never be written. `_apply` handles an empty list correctly:
    # its `update_many` reset is what stamps the honest zeros.
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

    # STORING THE EVENTS IS NOT THE JOB. Deriving from them is, and this stopped at the store.
    #
    # `match_events` is the archive; almost nothing reads it directly. What the product reads is what
    # `_apply` writes OUT of it: per-player `yellow_cards`, `red_cards`, `pen_goals`, `goal_minutes`,
    # `sub_on`/`sub_off`, and per-team `yellow_cards_against`, `red_cards`, `own_goals_for`. On the
    # PitchAPI path `ingest_extras` called it; that path is `not af`-gated in `jobs.tick`, so under
    # API-Football nobody called it and every one of those fields stayed at its default.
    #
    # `cards_model` is built entirely on them, so it did not fail -- it computed, confidently, from
    # zeros. `y = sum(r.get("yellow_cards") or 0)` was always 0, so the per-90 card rate was 0, so
    # lambda was 0, so EVERY player card forecast published at p = 0.0000 (47 lines a fixture). On
    # the team side `yellow_cards_against` was always 0, which collapsed the opponent share from 1.0
    # to K/(n+K) = 0.2 and multiplied the match line by sqrt(0.2): "4+ cards in the match" read
    # 0.390 where the same events with `_apply` run give 0.572.
    #
    # And `extras_at` is what `score_finished` checks before it will grade a card forecast, so those
    # worthless lines were never graded either -- a permanently empty track record on top of a
    # permanently wrong number.
    MX._apply(db, match, rows, tid)
    sets = {"extras_at": utcnow()}
    goals = [e for e in rows if e["type"] == "goal"]
    if goals:
        g = goals[0]
        sets["first_goal_side"] = ("away" if g["side"] == "home" else "home") if g["own_goal"] else g["side"]
        sets["first_scorer_iid"] = None if g["own_goal"] else g["player_iid"]
    else:
        sets["first_goal_side"], sets["first_scorer_iid"] = "none", None
    db.matches.update_one({"iid": match["iid"]}, {"$set": sets})


# ------------------------------------------------------------------ draining the queue
QUEUE_TASK = "af_match"


def drain(client, max_seconds: float = 40.0, batch: int = AF.IDS_PER_CALL) -> dict:
    """Work the queue in bundles of twenty until the time runs out or it empties."""
    db = client.db
    import time
    t0 = time.monotonic()
    done = {"batches": 0, "written": 0, "failed": 0, "missing": 0,
            # Tasks an earlier crash left mid-flight. `ingest.release_stuck` exists for exactly
            # this and its only caller is `process_queue`, which the API-Football tick never runs,
            # so nothing recovered them. Without this a single bad batch takes twenty matches out
            # of the backfill permanently and the season can never be marked backfilled.
            "released": I.release_stuck(db)}
    last_release = t0
    while time.monotonic() - t0 < max_seconds:
        # AND AGAIN AS WE GO. The release above runs once, at entry, and `release_stuck` only frees
        # a task older than its own threshold -- so a batch this very drain leaves mid-flight is not
        # recovered by it, whatever the commit message said. Re-checking periodically costs one
        # indexed update and means a long drain heals itself rather than waiting for the next tick.
        if time.monotonic() - last_release > 60:
            done["released"] += I.release_stuck(db)
            last_release = time.monotonic()
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


def lineup_watch(client, now: datetime | None = None, max_fixtures: int = 60) -> dict:
    """The announced eleven, BEFORE kick-off, into `db.lineups`.

    This had no API-Football equivalent at all. `jobs.py` gates the PitchAPI `lineup_watch` behind
    `not af`, and nothing replaced it, so under the new provider `db.lineups` was written only by
    `write_match` -- i.e. AFTER the match. Three things were therefore dead:

      * `engine_bridge` reads `db.lineups` for `started=True, confirmed=True` and needs eleven
        before it will pass a real XI into `predict_fixture`. It never got one, so every forecast
        ran on the engine's own `p_play` estimates even when the teamsheet was out.
      * `follow_alerts` never sent the "lineups are in" e-mail.
      * `jobs` never re-fit a forecast when the real eleven landed, because `lineups_at` never moved.

    One call covers twenty fixtures, and `apifootball.lineup_ttl` caches a lineup for ever once it
    is present, so a fixture is paid for once however often this runs.
    """
    db = client.db
    now = now or utcnow()
    window = float(S.get(db, "ingest.lineups_watch_hours") or 6)
    ms = list(db.matches.find({
        "status": "scheduled", "lineups_confirmed": {"$ne": True},
        "kickoff": {"$gte": now - timedelta(hours=1), "$lte": now + timedelta(hours=window)},
    }).limit(max_fixtures))
    if not ms:
        return {"looked_at": 0, "confirmed": 0, "calls": 0}

    settings = _settings(db)
    by_ext = {str(m["ext_id"]): m for m in ms}
    before = client.calls_made
    # NOT `FOREVER`, and not `AF.lineup_ttl` either: that is a per-fixture decision ("cache this
    # lineup for ever now I have it") and this fetch carries twenty fixtures at once, most of which
    # have no lineup yet. Cache the ANSWER briefly instead, so the next tick asks again and sees a
    # sheet that has since been announced. A fixture whose lineup HAS landed is excluded by the
    # query above, so we never pay for it twice.
    ttl = timedelta(minutes=float(S.get(db, "cache.ttl.lineups_near_minutes") or 10))
    bundles = AF.fixtures_bundle(client, [int(e) for e in by_ext], ttl=ttl, purpose="lineup_watch")
    n = 0
    for ext, match in by_ext.items():
        fixture = bundles.get(int(ext))
        if not fixture or not (fixture.get("lineups") or []):
            continue                                   # not announced yet; try again next tick
        try:
            lu = NAF.lineups(fixture, settings["position_map"])
            home = db.teams.find_one({"iid": match["home_iid"]}, {"ext_id": 1})
            away = db.teams.find_one({"iid": match["away_iid"]}, {"ext_id": 1})
            iid_of = {(home or {}).get("ext_id"): match["home_iid"],
                      (away or {}).get("ext_id"): match["away_iid"]}
            I.save_lineups(db, match, lu, iid_of)
            db.matches.update_one({"iid": match["iid"]},
                                  {"$set": {"lineups_at": now,
                                            "lineups_confirmed": bool(lu["home"]["confirmed"] and lu["away"]["confirmed"])},
                                   "$inc": {"lineup_fetches": 1}})
            n += 1
        except Exception as e:
            I.issue(db, "lineup_failed", f"{ext}: {type(e).__name__}: {e}",
                    match_iid=match["iid"], league_iid=match["league_iid"])
    return {"looked_at": len(by_ext), "confirmed": n, "calls": client.calls_made - before}


# ------------------------------------------------------------------ pulling it again
#
# Why this exists: a column added after a match was ingested is empty on that match for ever. The
# ingest only ever queues a match with no `ingested_at` (see `sync_fixtures`), so nothing re-reads
# one. Ratings, coaches and the derived card fields all arrived after rows had been written, and so
# did every normalizer fix in docs/90 -- a null the provider meant as a zero stays null on an old
# row no matter how correctly the code now reads it.
#
# It is cheap: the bundle carries twenty matches a call, so a whole league-season is about 19 calls.
def _reingest_scope(db, league_iid: int | None, season: str | None) -> dict:
    q = {"status": "final", "ingested_at": {"$ne": None}}
    if league_iid is not None:
        q["league_iid"] = int(league_iid)
    else:
        q["league_iid"] = {"$in": [l["iid"] for l in db.leagues.find(
            {"enabled": True, "provider": PROVIDER}, {"iid": 1})]}
    if season is not None:
        q["season"] = str(season)
    return q


def plan_reingest(db, league_iid: int | None = None, season: str | None = None) -> dict:
    """How many matches would be pulled again, and what that costs. CHANGES NOTHING.

    Always run this first. The answer is in calls, because that is the thing that can hurt.
    """
    q = _reingest_scope(db, league_iid, season)
    n = db.matches.count_documents(q)
    batch = int(S.get(db, "apifootball.reingest_batch") or 500)
    per_call = AF.IDS_PER_CALL
    return {"matches": n, "calls": -(-n // per_call), "batch": batch,
            "presses": -(-n // batch) if batch else 0,
            "cap": int(S.get(db, "apifootball.daily_cap") or 0),
            "leagues": sorted({m["league_iid"] for m in db.matches.find(q, {"league_iid": 1})})}


def reingest(db, league_iid: int | None = None, season: str | None = None,
             limit: int | None = None) -> dict:
    """Queue finished matches to be pulled again, NEWEST FIRST. Bounded, and safe to repeat.

    THE STATUS HAS TO BE SET EXPLICITLY. `ingest.enqueue` writes `status` under `$setOnInsert`, and
    a task that has already been drained is left at `status: "done"` -- so re-queueing a match that
    was ingested once is a silent no-op: the row exists, the status stays "done", and `drain` never
    looks at it again. A re-ingest built on `enqueue` would report every match queued and do nothing
    at all, which is the exact shape of failure docs/90 is about.

    `ingested_at` is deliberately NOT cleared. `write_match` upserts, so the rows are replaced in
    place; clearing it would make the match look un-ingested to every other reader in the meantime,
    and would lose that state for good if the re-pull never finished.

    Newest first because recent matches are the ones on the site's front page, and bounded so one
    press cannot queue twenty thousand matches at once. Priority 8: behind the live whistle (3),
    the current-season sweep (5) and the backfill (7).
    """
    q = _reingest_scope(db, league_iid, season)
    n = int(limit if limit is not None else (S.get(db, "apifootball.reingest_batch") or 500))
    now = utcnow()
    queued = 0
    for m in db.matches.find(q, {"iid": 1, "ext_id": 1}).sort("kickoff", -1).limit(n):
        db.ingest_queue.update_one(
            {"task": QUEUE_TASK, "key": str(m["ext_id"])},
            {"$set": {"task": QUEUE_TASK, "key": str(m["ext_id"]), "status": "pending",
                      "next_run_at": now, "priority": 8, "payload": {"match_iid": m["iid"]},
                      "requeued_at": now},
             "$setOnInsert": {"attempts": 0, "created_at": now}},
            upsert=True)
        queued += 1
    return {"queued": queued, "left": max(0, db.matches.count_documents(q) - queued)}


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
            # ROUNDS, before anything reads the league back.
            #
            # `sync_fixtures` writes `round: None` on insert and nothing in this function set it;
            # only the `af_fixtures` job called `assign_rounds`. But `build_frames` filters
            # `{"round": {"$ne": None}}`, so a league whose whole history had just been backfilled
            # had 96 of 96 matches invisible to the engine, `build_frames` returned None and
            # `run_league` recorded `status: skipped, note: "no data"` -- on a league that had just
            # been fully ingested. It healed itself at the next fixtures sync, up to six hours
            # later, and until then the recorded reason was simply untrue. Rounds are a pure
            # function of the kickoff dates we already hold; it costs no calls.
            I.assign_rounds(db, lg["iid"])
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
