"""live_af.py -- the live tick on API-Football. docs/88 §live.

Replaces `sportapi.live_tick`, and most of this module is about what it no longer has to do.

## The mapping problem, and why it is gone

SportAPI was a SECOND provider sitting beside the data provider, so nothing it said could be joined
to anything we held without guessing. `sportapi.map_team` matched its club names against ours,
`link_match` then guessed which of our fixtures that was from the two club ids and a kick-off time,
`sportapi_team_map` cached the guesses, and the admin carried a review queue for the ones it could
not make. Every one of those exists because the two sides had different ids for the same club.

API-Football's live feed returns OUR fixtures, with the fixture id we already store as
`matches.ext_id`. So the join is a lookup, not a match:

    db.matches.find_one({"ext_id": str(fixture_id)})

No name matching, no cached guesses, no review queue, and no class of bug where a live score is
attached to the wrong match because two clubs in a league share a short name.

## One call for everything in play

`GET /fixtures?live=a-b-c` returns every in-play fixture in those leagues WITH ITS EVENTS INLINE
(docs/82 §4). One call a tick, whatever the number of matches, and goals and cards arrive with the
score rather than needing a second request each. SportAPI needed a call per fixture for events.

Statistics are the exception: they are not on the live payload, so a fixture actually producing them
is refreshed through `fixtures_bundle`, twenty at a time, and only when `needs_stats` says it is
worth it -- half time is live but barren, and a call spent then buys nothing.
"""
from __future__ import annotations

from datetime import datetime, timezone

import apifootball as AF
import normalize_af as NAF
import settings_store as S

PROVIDER = "apifootball"


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _settings(db) -> dict:
    """What the normalizer needs, read once a tick rather than once a fixture.

    The same three `ingest_af._settings` reads: the live path translates the same payload with the
    same map, so a statistic renamed in Settings changes both at once.
    """
    return {"team_keys": S.get(db, "provider.apifootball.team_keys"),
            "position_map": S.get(db, "provider.apifootball.position_map"),
            "exclude_extra_time": S.get(db, "provider.apifootball.exclude_extra_time")}


def _dt(iso):
    """Their ISO date into an aware datetime. `scoreboard` range-queries `kickoff`, so a string
    stored there matches nothing and the board comes back empty with no error raised anywhere."""
    if not iso:
        return None
    try:
        return datetime.fromisoformat(str(iso).replace("Z", "+00:00"))
    except Exception:
        return None


def _winner(teams: dict) -> str | None:
    for side in ("home", "away"):
        if (teams.get(side) or {}).get("winner") is True:
            return side
    return None


def _our_match(db, fixture_id) -> dict | None:
    """Their live fixture is our fixture. A lookup, not a guess -- see the module note."""
    return db.matches.find_one({"ext_id": str(fixture_id)})


def _event_rows(db, fixture: dict, match: dict | None) -> list[dict]:
    """Their inline events, in the shape `live_track` and `sportapi.events_for` actually read.

    THIS WROTE THE PROVIDER'S OWN WORDS. `type` was API-Football's raw "Card", with "Yellow Card" in
    `detail` -- and `live_track.is_yellow` tests `"yellow" in type`, so NO LIVE BOOKING WAS EVER
    COUNTED and live card tracking was dead. `side`, `player_iid` and `minute_num` were missing
    too, so `events_for` sorted on a field that did not exist and the match page's event list was
    empty.

    `normalize_af.events` already does this translation correctly for the finished-match path, and
    the live path did it again by hand and got it wrong. One translator, both paths.
    """
    fx = fixture.get("fixture") or {}
    fid = fx.get("id")
    teams = fixture.get("teams") or {}
    home_ext = str((teams.get("home") or {}).get("id"))
    away_ext = str((teams.get("away") or {}).get("id"))
    tid = {"home": (match or {}).get("home_iid"), "away": (match or {}).get("away_iid")}
    rows = []
    for e in NAF.events(fixture, home_ext, away_ext):
        pl = db.players.find_one({"ext_id": e.get("player_ext")}, {"iid": 1}) if e.get("player_ext") else None
        minute, extra = e.get("minute") or 0, e.get("added") or 0
        rows.append({
            "sid": int(fid), "fixture_sid": int(fid), "fixture_ext": str(fid),
            "match_iid": (match or {}).get("iid"),
            # `type` is OUR vocabulary -- goal / yellow / red / sub -- not theirs.
            "type": e["type"], "side": e["side"], "team_iid": tid.get(e["side"]),
            "minute": minute, "extra": extra,
            # what events_for sorts on; a plain minute cannot order 45+2 against 46.
            "minute_num": minute + (extra or 0) / 100.0,
            "player_iid": (pl or {}).get("iid"),
            "player_ext": e.get("player_ext"), "player_name": e.get("player_name"),
            "assist_name": e.get("in_name"),
            "own_goal": e.get("own_goal"), "penalty": e.get("penalty"), "second_yellow": e.get("second_yellow"),
        })
    return rows


def _store(db, fixture: dict, now: datetime) -> dict:
    fx = fixture.get("fixture") or {}
    fid = fx.get("id")
    if fid is None:
        return {"changed": False}
    teams, goals = fixture.get("teams") or {}, fixture.get("goals") or {}
    st = (fx.get("status") or {}).get("short")
    match = _our_match(db, fid)
    old = db.live_fixtures.find_one({"sid": int(fid)}) or {}

    # THE SHAPE THE READERS ALREADY EXPECT.
    #
    # `sportapi.public_fixture`, `scoreboard`, `results` and `queries.py` all read this collection
    # and were written against SportAPI's field names. The first version of this wrote `ext_id` and
    # an ISO-string `kickoff` and nothing else, which would have left the public scoreboard EMPTY
    # while the tick reported success: the data arriving, and no reader able to see it.
    #
    # `sid` is their fixture id as an int, so /api/live/{sid}/events keeps working. `kickoff` is a
    # datetime because `scoreboard` RANGE-QUERIES it, and a string there matches nothing. `date` is
    # the day string `results` looks up.
    #
    # The status words need no translation: `sportapi.FINAL`, `NOT_YET` and `DEAD` already list
    # API-Football's shorts, and `in_play` is "none of those three", so 1H, HT and ET read as live
    # with no table at all. docs/42 made that provider-agnostic on purpose, and it paid off here.
    lg = fixture.get("league") or {}
    score = fixture.get("score") or {}
    ko = _dt(fx.get("date"))
    doc = {
        "sid": int(fid), "ext_id": str(fid), "provider": PROVIDER,
        "league_sid": lg.get("id"), "league_ext": str(lg.get("id")), "league_name": lg.get("name"),
        "league_iid": (match or {}).get("league_iid"),
        "match_iid": (match or {}).get("iid"),
        "kickoff": ko, "date": ko.strftime("%Y-%m-%d") if ko else None,
        "status": st, "in_play": st in AF.IN_PLAY,
        "minute": (fx.get("status") or {}).get("elapsed"),
        "hs": goals.get("home"), "as": goals.get("away"),
        "ht_home": (score.get("halftime") or {}).get("home"),
        "ht_away": (score.get("halftime") or {}).get("away"),
        "pen_home": (score.get("penalty") or {}).get("home"),
        "pen_away": (score.get("penalty") or {}).get("away"),
        "winner": _winner(teams),
        "home_sid": (teams.get("home") or {}).get("id"), "away_sid": (teams.get("away") or {}).get("id"),
        "home_ext": str((teams.get("home") or {}).get("id")),
        "away_ext": str((teams.get("away") or {}).get("id")),
        "home_name": (teams.get("home") or {}).get("name"),
        "away_name": (teams.get("away") or {}).get("name"),
        "home_short": (teams.get("home") or {}).get("name"),
        "away_short": (teams.get("away") or {}).get("name"),
        "home_iid": (match or {}).get("home_iid"), "away_iid": (match or {}).get("away_iid"),
        "polled_at": now,
    }
    changed = (not old) or any(old.get(k) != doc[k] for k in ("status", "hs", "as", "minute"))
    went_final = old.get("status") != st and str(st or "").upper() in NAF.FINAL_SHORTS
    if went_final:
        doc["final_at"] = now
    db.live_fixtures.update_one({"sid": int(fid)}, {"$set": doc}, upsert=True)

    # THE WHISTLE IS THE SIGNAL TO FETCH THE STATISTICS, and nothing was acting on it.
    #
    # This line knew the match had just ended -- it has been stamping `final_at` all along -- and
    # then left it there. The only thing in the codebase that queues a finished match's statistics
    # is `ingest_af.sync_fixtures`, which runs from the `af_fixtures` job every
    # `ingest.fixtures_sync_hours`: SIX HOURS by default. Worse, when it does run it reads
    # `/fixtures` through a cache whose TTL is six hours off a match day, so it could run and still
    # see the match as `scheduled` and queue nothing at all.
    #
    # So a match that finished at five o'clock could have no shots, no possession and no player
    # numbers until nearly midnight, and the delay looked exactly like the one the retired provider
    # used to have -- because that provider's `results_sync` was on the same six-hour cadence. It
    # was never about which provider; it was about nobody asking until the next scheduled sweep.
    #
    # `drain` runs on every tick, so queueing here turns six hours into about a minute. It costs no
    # extra call: this bundle was going to be fetched regardless, just later.
    if went_final and match and not match.get("ingested_at"):
        import ingest as I
        import ingest_af as IA
        I.enqueue(db, IA.QUEUE_TASK, str(fid), priority=3,          # ahead of the backfill
                  payload={"match_iid": match["iid"]})

    rows = _event_rows(db, fixture, match)
    if rows:
        # Replace rather than append: their feed restates the whole list each poll, so appending
        # would write a goal again on every tick for the rest of the match.
        db.live_events.delete_many({"fixture_sid": int(fid)})
        db.live_events.insert_many(rows)
    db.live_fixtures.update_one({"sid": int(fid)},
                                {"$set": {"events_at": now, "events_n": len(rows)}})

    if match:                       # the light mirror the Today and match pages read
        # `sid`, which is what every reader of this mirror wants: `queries._live_events` does
        # `(m.get("live") or {}).get("sid")` and `follow_alerts.goals` queries `{"live.sid": ...}`.
        # Writing `ext_id` here left both permanently empty -- no event list on the match page, and
        # goal and red-card alert e-mails that never went out, with `return 0` reading as a quiet
        # night.
        db.matches.update_one({"iid": match["iid"]}, {"$set": {"live": {
            "status": st, "minute": doc["minute"], "hs": doc["hs"], "as": doc["as"],
            "sid": int(fid), "ext_id": str(fid), "at": now}}})
    return {"changed": changed, "match_iid": (match or {}).get("iid"), "events": len(rows),
            "orphan": match is None}


def _store_lineups(db, fixture: dict, now: datetime) -> int:
    """The announced eleven, into `live_lineups`, which otherwise has no writer at all.

    `GET /api/live/{sid}/lineups` reads this collection. After the move nothing wrote to it, so the
    endpoint answered with an empty object and no error -- a feature that stopped existing quietly
    (docs/89 section 2). The live payload carries no lineups, so they come from the fixture bundle,
    the same place the confirmed eleven comes from for a finished match.

    THE SHAPE IS THE READER'S, not a fresh one. `sportapi.lineups_for` wants one row a side with a
    `players` list, each carrying `started`, `player_iid`, `name`, `position` and `shirt`. Writing
    `starters`/`bench` instead would have left the endpoint returning nothing while the tick
    reported lineups stored -- exactly the mistake the scoreboard caught (docs/88).
    """
    fid = (fixture.get("fixture") or {}).get("id")
    if fid is None:
        return 0

    def rows(block, started):
        key = "startXI" if started else "substitutes"
        out = []
        for p in (block.get(key) or []):
            pl = p.get("player") or {}
            ours = db.players.find_one({"ext_id": str(pl.get("id"))}, {"iid": 1}) if pl.get("id") is not None else None
            out.append({"started": started, "player_iid": (ours or {}).get("iid"),
                        "name": pl.get("name"), "position": pl.get("pos"),
                        "shirt": pl.get("number"), "captain": False, "mins": None,
                        "grid": pl.get("grid"), "ext_id": str(pl.get("id")) if pl.get("id") is not None else None})
        return out

    n = 0
    for side_i, block in enumerate(fixture.get("lineups") or []):
        side = "home" if side_i == 0 else "away"
        players = rows(block, True) + rows(block, False)
        if not players:
            continue
        tid = (block.get("team") or {}).get("id")
        db.live_lineups.update_one(
            {"fixture_sid": int(fid), "side": side},
            {"$set": {"fixture_sid": int(fid), "sid": int(fid), "side": side,
                      "team_sid": tid, "team_ext": str(tid),
                      "formation": block.get("formation"), "players": players, "at": now}},
            upsert=True)
        n += 1
    return n

def live_tick(db, client=None, now: datetime | None = None) -> dict:
    """One call for every in-play fixture in our competitions, plus statistics where they exist."""
    now = now or utcnow()
    if not S.get(db, "features.live"):
        return {"skipped": "live is off", "fixtures": 0}
    client = client or AF.Client(db)

    leagues = [int(l["ext_id"]) for l in db.leagues.find(
        {"enabled": True, "provider": PROVIDER}, {"ext_id": 1}) if str(l.get("ext_id", "")).isdigit()]
    if not leagues:
        return {"skipped": "no API-Football competition is on", "fixtures": 0}

    try:
        fixtures = AF.live_fixtures(client, leagues)
    except (AF.BudgetExhausted, AF.BreakerOpen, AF.Unauthorized, AF.PlanLimited) as e:
        return {"skipped": f"{type(e).__name__}: {e}", "fixtures": 0}

    settings = _settings(db)
    out = {"fixtures": len(fixtures), "changed": 0, "events": 0, "orphans": 0, "stats": 0, "lineups": 0}
    for f in fixtures:
        r = _store(db, f, now)
        out["changed"] += bool(r.get("changed"))
        out["events"] += r.get("events", 0)
        out["orphans"] += bool(r.get("orphan"))

    # Statistics are not on the live payload. Only fixtures actually producing them are worth a
    # call -- half time is live and barren -- and they go twenty at a time like everything else.
    want = AF.needs_stats(fixtures)
    if want and S.get(db, "apifootball.live_stats"):
        bundles = AF.fixtures_bundle(client, want, ttl=None, purpose="live_stats")
        for fid, fixture in bundles.items():
            # THE SHAPE `live_track` READS, not the provider's raw array.
            #
            # This stored API-Football's `statistics` list verbatim, and `live_track.evaluate`
            # (line 67-70) wants `teams: {home|away: {shots, sot, corners, tackles}}` and
            # `players: [{player_iid, ...}]`. So every live stat line sat at "unknown" for the whole
            # match -- the four markets in STATS_STATS could never be tracked.
            #
            # `normalize_af` already turns their payload into our column names for the finished
            # match; using it here too means one translator, and the live numbers are the same
            # numbers the final row will carry.
            #
            # Keyed on `fixture_sid`: mongo_init indexes live_stats UNIQUE on that field and NOT
            # sparse, so keying on `ext_id` gave every document `fixture_sid: null` -- the first
            # fixture stored and the SECOND raised DuplicateKeyError, killing the statistics step
            # for the rest of the tick. Same shape as the seasons.label crash.
            teams_block, players_block = {}, []
            try:
                tms = fixture.get("teams") or {}
                hx, ax = str((tms.get("home") or {}).get("id")), str((tms.get("away") or {}).get("id"))
                ts = NAF.team_stats(fixture, settings["team_keys"], hx, ax)
                # EVERY column the finished-match row carries, not the four `live_track` happens to
                # need. The same numbers are now shown on the match page while the match is on, and
                # a live table that silently holds fewer rows than the final one makes the figures
                # appear to change at the whistle when all that changed is which document was read.
                teams_block = {side: {c: ts[side].get(c) for c in NAF.TEAM_COLS}
                               for side in ("home", "away")}
                pls = NAF.players(fixture, settings["position_map"])
                for pl in pls:
                    ours = db.players.find_one({"ext_id": pl["ext_id"]}, {"iid": 1})
                    players_block.append({"player_iid": (ours or {}).get("iid"),
                                          "ext_id": pl["ext_id"],
                                          **{c: pl.get(c) for c in ("shots", "sot", "tackles")}})
                # Team tackles, from the players. API-Football publishes no team Tackles statistic
                # at all, so without this the live tackles line reads "unknown" for ninety minutes
                # on a market the product actually sells. The finished-match path does exactly the
                # same (normalize_af, docs/80 section 2), so the live number and the final number
                # are computed the same way rather than disagreeing at the whistle.
                for side, ext in (("home", hx), ("away", ax)):
                    if teams_block[side].get("tackles") is None:
                        teams_block[side]["tackles"] = NAF._sum_team(pls, ext, "tackles")
                    # Saves the same way, and for the same reason the finished path does it: the
                    # keeper's saves are a player number with no team statistic behind them, and
                    # `saves` is a market we publish. Without this the match page would show a saves
                    # row that filled in only at the whistle.
                    teams_block[side]["saves"] = (teams_block[side].get("saves")
                                                  if teams_block[side].get("saves") is not None
                                                  else NAF._sum_team(pls, ext, "saves"))
            except Exception as e:      # one fixture's statistics, not the tick's
                db.ingest_issues.insert_one({"at": now, "kind": "live_stats_shape",
                                             "detail": f"{fid}: {type(e).__name__}: {e}"})
            db.live_stats.update_one({"fixture_sid": int(fid)},
                                     {"$set": {"fixture_sid": int(fid), "ext_id": str(fid), "at": now,
                                               "teams": teams_block, "players": players_block,
                                               "statistics": fixture.get("statistics") or []}},
                                     upsert=True)
            out["stats"] += 1
            out["lineups"] = out.get("lineups", 0) + _store_lineups(db, fixture, now)
    db.job_state.update_one({"_id": "live_tick"},
                            {"$set": {"at": now, "provider": PROVIDER, **out}}, upsert=True)
    return out
