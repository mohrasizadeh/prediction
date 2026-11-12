"""jobs.py -- one entry point, `tick()`, called every 5 to 10 minutes.

Emergent's scheduled-job support is not documented, so we do not depend on it.
Two ways to call tick():
  1. POST /api/jobs/tick with header X-CRON-SECRET (an external pinger: cron-job.org is free).
  2. A background thread started at app startup (see 07_ingest_and_caching.md, section 6).
A lock makes overlapping calls harmless. tick() stops by itself after `max_seconds`.
Everything it does is resumable.
"""
from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone

from pymongo.errors import DuplicateKeyError

import engine_bridge as B
import ingest as I
import settings_store as S
from cached_fetch import BreakerOpen, BudgetExhausted, PitchClient, Unauthorized, utcnow

LOCK_MINUTES = 5
# What "Run now" may ask for. The four PitchAPI steps are still here because a database that has
# not moved yet still needs them; `af_fixtures` and `af_backfill` are the API-Football pair, and the
# Jobs screen shows whichever set `provider.source` actually runs. Asking for a job the current
# provider skips used to queue a request that could never be taken: the card said "stopped", Run now
# did nothing, and nothing said why.
MANUAL = {"reference_sync", "fixtures_sync", "results_sync", "backfill",
          "af_fixtures", "af_backfill",
          "engine", "alerts", "digest", "images", "referees", "waitlist_mail"}


def _waitlist_due(db, now) -> bool:
    """waitlist_mail.due, imported lazily: the module pulls in queries and the emailer, and a tick
    on a day with the e-mail switched off should not pay for either."""
    if not S.get(db, "waitlist.email_enabled"):
        return False
    import waitlist_mail as WL
    return WL.due(db, now)


def _lock(db, now) -> bool:
    db.job_locks.delete_many({"_id": "tick", "expires_at": {"$lt": now}})
    try:
        db.job_locks.insert_one({"_id": "tick", "at": now, "expires_at": now + timedelta(minutes=LOCK_MINUTES)})
        return True
    except DuplicateKeyError:
        return False


def _last(db, job):
    return db.job_runs.find_one({"job": job, "status": "ok"}, sort=[("started_at", -1)])


def _due_every(db, job, delta: timedelta, now) -> bool:
    last = _last(db, job)
    return last is None or (now - last["started_at"].replace(tzinfo=timezone.utc)) >= delta


def _run(db, job, fn, now):
    row = {"job": job, "started_at": now, "status": "running"}
    rid = db.job_runs.insert_one(row).inserted_id
    try:
        result = fn()
        db.job_runs.update_one({"_id": rid}, {"$set": {"status": "ok", "finished_at": utcnow(), "result": result}})
        return result
    except (BudgetExhausted, BreakerOpen, Unauthorized) as e:
        db.job_runs.update_one({"_id": rid}, {"$set": {"status": "stopped", "finished_at": utcnow(), "result": type(e).__name__}})
        return None
    except Exception as e:                       # a bug must not kill the tick
        db.job_runs.update_one({"_id": rid}, {"$set": {"status": "error", "finished_at": utcnow(), "error": repr(e)[:500]}})
        db.ingest_issues.insert_one({"at": utcnow(), "kind": "job_error", "detail": f"{job}: {e!r}"[:500], "resolved": False})
        return None


def tick(db, client: PitchClient | None = None, max_seconds: float = 50.0, now: datetime | None = None) -> dict:
    now = now or utcnow()
    t0 = time.monotonic()
    out = {"ran": [], "skipped": None}
    if not _lock(db, now):
        out["skipped"] = "another tick is running"; return out
    try:
        client = client or PitchClient(db)
        pend = list(db.job_requests.find({"status": "pending"}))
        forced = {r["job"] for r in pend}
        img_refresh = any(r.get("refresh") for r in pend if r["job"] == "images")
        db.job_requests.update_many({"status": "pending"}, {"$set": {"status": "taken", "taken_at": now}})
        leagues = list(db.leagues.find({"enabled": True}))
        left = lambda: time.monotonic() - t0 < max_seconds

        # WHICH PROVIDER FEEDS THE TABLES. docs/88.
        #
        # One switch, read once, because the two paths must never both run: they key entities on
        # different ext_ids, so a league ingested by both is every club and player twice over
        # (docs/78 §5.1). `provider.source` is the only thing that decides, and the PitchAPI steps
        # below are skipped wholesale rather than individually -- a half-switched tick is the
        # failure mode worth designing out.
        af = S.get(db, "provider.source") == "apifootball"
        if af:
            import apifootball as AF
            import ingest_af as IA
            afc = AF.Client(db)
            af_leagues_on = [lg for lg in leagues if lg.get("provider") == "apifootball"]
            try:
                if af_leagues_on and ("af_fixtures" in forced or _due_every(
                        db, "af_fixtures", timedelta(hours=S.get(db, "ingest.fixtures_sync_hours")), now)):
                    def af_fx():
                        n = 0
                        for lg in af_leagues_on:
                            if not left():
                                break
                            n += IA.sync_fixtures(afc, lg, IA._current_season(db, lg))["fixtures"]
                            I.assign_rounds(db, lg["iid"])
                        return n
                    if _run(db, "af_fixtures", af_fx, now) is not None:
                        out["ran"].append("af_fixtures")

                # `left()` OR asked for. Run now has to mean now: a tick that has already spent its
                # seconds would otherwise take the request and do nothing with it.
                if left() or "af_backfill" in forced:
                    res = _run(db, "af_backfill",
                               lambda: IA.backfill_tick(afc, max_seconds=max(5.0, max_seconds - (time.monotonic() - t0) - 10)),
                               now)
                    if res and (res.get("written") or res.get("synced")):
                        out["ran"].append("af_backfill")
            except (AF.BudgetExhausted, AF.BreakerOpen, AF.Unauthorized, AF.PlanLimited) as e:
                # The account, not this tick. Recorded and left for the next one; the engine steps
                # below still run on the data already in the tables.
                out["provider_paused"] = f"{type(e).__name__}: {e}"

        if not af and ("reference_sync" in forced or _due_every(db, "reference_sync", timedelta(days=S.get(db, "ingest.reference_sync_days")), now)):
            if _run(db, "reference_sync", lambda: I.sync_leagues(client), now) is not None: out["ran"].append("reference_sync")

        if not af and ("fixtures_sync" in forced or _due_every(db, "fixtures_sync", timedelta(hours=S.get(db, "ingest.fixtures_sync_hours")), now)):
            def fx():
                for lg in leagues:
                    I.sync_league_matches(client, lg, lg.get("current_season"), "upcoming"); I.assign_rounds(db, lg["iid"])
                return len(leagues)
            if leagues and _run(db, "fixtures_sync", fx, now) is not None: out["ran"].append("fixtures_sync")

        if not af and ("results_sync" in forced or _due_every(db, "results_sync", timedelta(hours=S.get(db, "ingest.results_sync_hours")), now)):
            def rs():
                before = db.ingest_queue.count_documents({"task": "match_ingest"})
                for lg in leagues:        # force=True: one list call per league, always fresh, so new results are seen
                    I.sync_league_matches(client, lg, lg.get("current_season"), "all", force=True); I.assign_rounds(db, lg["iid"])
                return {"leagues": len(leagues), "new_matches_queued": db.ingest_queue.count_documents({"task": "match_ingest"}) - before}
            if leagues and _run(db, "results_sync", rs, now) is not None: out["ran"].append("results_sync")

        if not af and ("backfill" in forced or db.seasons.count_documents({"backfilled": False, "queued": True})):
            def bf():
                n = 0
                for lg in leagues:
                    for label in lg.get("backfill_seasons", []):
                        s = db.seasons.find_one({"league_iid": lg["iid"], "label": label})
                        if s and not s.get("backfilled"):
                            I.sync_league_matches(client, lg, label, "all"); I.assign_rounds(db, lg["iid"])
                            db.seasons.update_one({"_id": s["_id"]}, {"$set": {"backfilled": True}}); n += 1
                return n
            if leagues and _run(db, "backfill", bf, now): out["ran"].append("backfill")

        if not af and left() and S.get(db, "ingest.lineups_watch_enabled"):
            if _run(db, "lineup_watch", lambda: I.lineup_watch(client, now), now) is not None: out["ran"].append("lineup_watch")

        if left() and S.get(db, "ingest.match_extra_detail"):
            import cards_model as CM
            _run(db, "referee_watch", lambda: CM.plan_referees(db, now), now)
        # No photo_plan step. Pictures come from api-football.com and nowhere else: the logo is a
        # URL on the entity, so `images.py` below needs no provider call to find one, and
        # `pitch_photos` (cdn.pitchapi.dev, a call per player) was a SECOND source of truth for the
        # same crest. Two sources for one picture is how a club ends up wearing another's badge.
        if not af and left():
            res = _run(db, "queue", lambda: I.process_queue(client, max_tasks=200), now)
            if res and (res["done"] or res["skipped"]): out["ran"].append("queue")

        for lg in leagues:
            if not left(): break
            last = db.engine_runs.find_one({"league_iid": lg["iid"], "status": {"$in": ["done", "skipped"]}}, sort=[("started_at", -1)])
            since = last["started_at"] if last else datetime(1970, 1, 1)
            dirty = (last is None
                     or db.matches.count_documents({"league_iid": lg["iid"], "ingested_at": {"$gt": since}}) > 0
                     or db.matches.count_documents({"league_iid": lg["iid"], "lineups_at": {"$gt": since}}) > 0)
            I.update_coverage(db, lg["iid"])
            I.refresh_player_clubs(db, lg["iid"])     # a loan moves a player; the club follows his latest match (docs/41)
            if "engine" in forced or dirty:
                if _run(db, f"engine:{lg['iid']}", lambda: B.run_league(db, lg["iid"], now), now) is not None: out["ran"].append(f"engine:{lg['iid']}")
        if left():
            if _run(db, "score", lambda: B.score_finished(db), now) is not None: out["ran"].append("score")
        if left() and ("referees" in forced or _due_every(db, "referees", timedelta(hours=24), now)):
            import referees as RF                                        # daily: normalised referee card numbers (docs/25)
            def refs():
                return {"leagues": [RF.refresh(db, lg["iid"]) for lg in db.leagues.find({"enabled": True}, {"iid": 1})]}
            if _run(db, "referees", refs, now) is not None: out["ran"].append("referees")
        if left():                                                       # copy list members out, deliver webhooks (both retry on their own)
            import integrations as INT
            import social as SOC
            # docs/64: due posts are handed over BEFORE the outbox is drained, so a post that comes
            # due this tick goes out on this tick rather than waiting for the next one.
            res = _run(db, "integrations", lambda: {**SOC.send_due(db, now=now, limit=int(S.get(db, "social.send_limit") or 20)),
                                                    **INT.process_audience(db, now=now), **INT.deliver_pending(db, now=now)}, now)
            if res and any(res.values()): out["ran"].append("integrations")
        if left() and "images" in forced:
            import images as IMG
            if _run(db, "images", lambda: IMG.run_sync(db, max_seconds=max(5.0, min(40.0, max_seconds - (time.monotonic() - t0))), refresh=img_refresh), now) is not None: out["ran"].append("images")
        if left() and ("blog" in forced or _due_every(db, "blog", timedelta(hours=6), now)):
            # docs/72: prepare DRAFT posts for TOMORROW's matches -- the post has to exist before
            # the match to be found by anyone searching the fixture, and to give a reader a reason
            # to open the site that evening. Four times a day rather than once, because a forecast
            # is refit as lineups land and a draft prepared at 03:00 would be reviewed against
            # numbers that have since moved. Publishing is never automatic.
            #
            # A published post is then updated in place after the whistle by the refresh below, so
            # one URL covers both: the preview that earns the visit, and the record that earns the
            # link.
            if S.get(db, "blog.auto_generate"):
                import blog as BL
                def blog_job():
                    made = BL.generate(db)
                    made["settled"] = BL.refresh_settled(db, now=now)
                    made["purged"] = BL.purge_old_drafts(db, days=int(S.get(db, "blog.draft_keep_days") or 14), now=now)
                    return made
                if _run(db, "blog", blog_job, now) is not None: out["ran"].append("blog")

        if left() and ("follow_alerts" in forced or _due_every(db, "follow_alerts", timedelta(minutes=2), now)):
            import follow_alerts as FA
            if _run(db, "follow_alerts", lambda: FA.run(db, now), now) is not None: out["ran"].append("follow_alerts")
        if left() and ("waitlist_mail" in forced or _waitlist_due(db, now)):
            # docs/69: the three strongest forecasts, once on a day that has football. `due` owns
            # both conditions -- the local hour has come, and today has no completed send -- and
            # send_matchday marks the day itself in `waitlist_sends`, so a send started here and
            # one started from the admin screen count exactly the same.
            import waitlist_mail as WL
            if _run(db, "waitlist_mail", lambda: WL.send_matchday(db, now=now), now) is not None: out["ran"].append("waitlist_mail")
        if left() and ("alerts" in forced or _due_every(db, "alerts", timedelta(minutes=15), now)):
            import alerts as AL
            if _run(db, "alerts", lambda: AL.run(db, now), now) is not None: out["ran"].append("alerts")
        if left() and ("digest" in forced or (now.weekday() == 0 and now.hour >= 12 and _due_every(db, "digest", timedelta(days=6), now))):
            import alerts as AL
            if _run(db, "digest", lambda: AL.send_digest(db, now), now) is not None: out["ran"].append("digest")
        if left() and _due_every(db, "cleanup", timedelta(hours=24), now):
            if _run(db, "cleanup", lambda: B.cleanup(db, now), now) is not None: out["ran"].append("cleanup")
        if left() and (now.weekday() == 0 and _due_every(db, "calibration", timedelta(days=6), now)):    # weekly refit (docs/21)
            import calibration as CAL
            if _run(db, "calibration", lambda: CAL.refit(db, now), now) is not None: out["ran"].append("calibration")
        if left() and _due_every(db, "injuries", timedelta(hours=12), now):                              # twice daily (docs/22)
            import availability as AV
            def inj():
                return {"expired": AV.expire(db, now), **AV.sync_apifootball(db, now=now)}
            if _run(db, "injuries", inj, now) is not None: out["ran"].append("injuries")
        db.job_requests.update_many({"status": "taken"}, {"$set": {"status": "done"}})
    finally:
        db.job_locks.delete_one({"_id": "tick"})
    out["seconds"] = round(time.monotonic() - t0, 1)
    return out
