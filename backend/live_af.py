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


def _event_rows(fixture: dict, match: dict | None) -> list[dict]:
    """Their inline events, flattened. Goals and cards are what the feed is for."""
    fid = str(((fixture.get("fixture") or {}).get("id")))
    rows = []
    for e in (fixture.get("events") or []):
        t = e.get("time") or {}
        rows.append({
            "sid": int(fid), "fixture_sid": int(fid), "fixture_ext": str(fid),
            "match_iid": (match or {}).get("iid"),
            "minute": t.get("elapsed"), "extra": t.get("extra"),
            "team_ext": str((e.get("team") or {}).get("id")),
            "player_ext": str((e.get("player") or {}).get("id")) if (e.get("player") or {}).get("id") else None,
            "player_name": (e.get("player") or {}).get("name"),
            "assist_name": (e.get("assist") or {}).get("name"),
            "type": e.get("type"), "detail": e.get("detail"), "comments": e.get("comments"),
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
    if old.get("status") != st and str(st or "").upper() in NAF.FINAL_SHORTS:
        doc["final_at"] = now
    db.live_fixtures.update_one({"sid": int(fid)}, {"$set": doc}, upsert=True)

    rows = _event_rows(fixture, match)
    if rows:
        # Replace rather than append: their feed restates the whole list each poll, so appending
        # would write a goal again on every tick for the rest of the match.
        db.live_events.delete_many({"fixture_sid": int(fid)})
        db.live_events.insert_many(rows)
    db.live_fixtures.update_one({"sid": int(fid)},
                                {"$set": {"events_at": now, "events_n": len(rows)}})

    if match:                       # the light mirror the Today and match pages read
        db.matches.update_one({"iid": match["iid"]}, {"$set": {"live": {
            "status": st, "minute": doc["minute"], "hs": doc["hs"], "as": doc["as"],
            "ext_id": str(fid), "at": now}}})
    return {"changed": changed, "match_iid": (match or {}).get("iid"), "events": len(rows),
            "orphan": match is None}


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

    out = {"fixtures": len(fixtures), "changed": 0, "events": 0, "orphans": 0, "stats": 0}
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
            db.live_stats.update_one({"ext_id": str(fid)},
                                     {"$set": {"ext_id": str(fid), "at": now,
                                               "statistics": fixture.get("statistics") or []}},
                                     upsert=True)
            out["stats"] += 1
    db.job_state.update_one({"_id": "live_tick"},
                            {"$set": {"at": now, "provider": PROVIDER, **out}}, upsert=True)
    return out
