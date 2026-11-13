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


# Their (type, detail) pairs in the vocabulary SportAPI rows already use, which every reader of
# `live_events` matches on: live_track counts "yellow" types per side, follow_alerts looks for goal and
# red types, and the match page draws icons from them. Stored raw ("Card" with the colour in `detail`,
# the club as an id), none of those readers could tell a yellow from a red or a home card from an away
# one, so a yellow-card forecast could never tick and a red card never raised an alert.
_AF_KIND = {("goal", "normal goal"): "goal", ("goal", "own goal"): "own_goal", ("goal", "penalty"): "penalty",
            ("goal", "missed penalty"): "missed_penalty", ("card", "yellow card"): "yellow_card",
            ("card", "second yellow card"): "second_yellow", ("card", "red card"): "red_card"}


def _af_kind(typ, detail) -> str | None:
    t, d = str(typ or "").strip().lower(), str(detail or "").strip().lower()
    if t == "subst":
        return "substitution"
    if t == "var":
        return "var"
    return _AF_KIND.get((t, d), t or None)


def _event_rows(fixture: dict, match: dict | None, db=None) -> list[dict]:
    """Their inline events, flattened into the shape SportAPI rows have, raw type and detail kept beside."""
    import sportapi as SP                                    # its careful name match ties an event to our player
    fid = str(((fixture.get("fixture") or {}).get("id")))
    teams = fixture.get("teams") or {}
    home_ext, away_ext = str((teams.get("home") or {}).get("id")), str((teams.get("away") or {}).get("id"))
    fx = {"home_iid": (match or {}).get("home_iid"), "away_iid": (match or {}).get("away_iid")}
    rows = []
    for e in (fixture.get("events") or []):
        t = e.get("time") or {}
        team_ext = str((e.get("team") or {}).get("id"))
        side = "home" if team_ext == home_ext else "away" if team_ext == away_ext else None
        kind = _af_kind(e.get("type"), e.get("detail"))
        base, add = t.get("elapsed"), t.get("extra") or 0
        player, assist = (e.get("player") or {}).get("name"), (e.get("assist") or {}).get("name")
        sub = kind == "substitution"
        # On a substitution their `player` is the one going off and `assist` the one coming on.
        name = assist if sub else player
        rows.append({
            "sid": int(fid), "fixture_sid": int(fid), "fixture_ext": str(fid),
            "match_iid": (match or {}).get("iid"),
            "type": kind, "side": side,
            "minute": (f"{base}+{add}'" if add else f"{base}'") if base is not None else None,
            "minute_num": float((base or 0) + add),
            "player_name": name, "in_name": assist if sub else None, "out_name": player if sub else None,
            "assist_name": None if sub else assist,
            "player_iid": SP._event_player(db, fx, side, name) if db is not None and kind != "var" else None,
            "team_iid": fx.get(f"{side}_iid") if side else None,
            "extra": e.get("detail") if kind == "var" else None,
            "team_ext": team_ext,
            "player_ext": str((e.get("player") or {}).get("id")) if (e.get("player") or {}).get("id") else None,
            "af_type": e.get("type"), "detail": e.get("detail"), "comments": e.get("comments"),
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

    rows = _event_rows(fixture, match, db)
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


def _store_stats(db, fixture: dict, now: datetime) -> dict:
    """One fixture's live statistics, into `live_stats`, in THE SHAPE ITS READER EXPECTS.

    `live_track.evaluate` finds the row by `fixture_sid` and reads `teams.home.shots` and
    `players[].player_iid`. This used to write their raw `statistics` list keyed by `ext_id`, so the
    reader found nothing and no shots, corners or tackles forecast ever ticked live -- with the tick
    reporting stats stored. (It also upserted with no `fixture_sid`, against the unique index on it.)

    Normalized with the same `team_keys` map and player paths a finished match goes through, so a
    live "6 shots" and a full-time "6 shots" are the same number read the same way. The raw list is
    kept beside it, so the admin can see what arrived when a name in the map is wrong.
    """
    fid = (fixture.get("fixture") or {}).get("id")
    if fid is None:
        return {}
    teams = fixture.get("teams") or {}
    home_ext = str((teams.get("home") or {}).get("id"))
    away_ext = str((teams.get("away") or {}).get("id"))
    ts = NAF.team_stats(fixture, S.get(db, "provider.apifootball.team_keys") or {}, home_ext, away_ext)
    pl = NAF.players(fixture, S.get(db, "provider.apifootball.position_map") or {})
    side_of = {home_ext: "home", away_ext: "away"}
    players = []
    for p in pl:
        side = side_of.get(str(p.get("team_ext_id")))
        if side is None:
            continue
        # The same join a finished match uses (ingest.upsert_player keys players by ext_id), as a
        # lookup only: a live tick does not create players.
        ours = db.players.find_one({"ext_id": p["ext_id"]}, {"iid": 1})
        players.append({"player_iid": (ours or {}).get("iid"), "ext_id": p["ext_id"], "name": p.get("name"),
                        "side": side, **{c: p.get(c) for c in ("minutes", "shots", "sot", "tackles", "goals",
                                                                "assists", "saves", "fouls_committed", "passes")}})
    # No team tackles statistic exists on API-Football, and shots on target can be missing: the team
    # total is the players' sum, the fallback normalize_af.normalize_match uses for finished matches.
    for side, ext in (("home", home_ext), ("away", away_ext)):
        for col in ("tackles", "sot", "shots"):
            if ts[side].get(col) is None:
                ts[side][col] = NAF._sum_team(pl, ext, col)
    has = any(v is not None for s in ts.values() for v in s.values())
    doc = {"fixture_sid": int(fid), "ext_id": str(fid), "provider": PROVIDER, "at": now,
           "teams": ts if has else {"home": {}, "away": {}}, "players": players,
           "statistics": fixture.get("statistics") or []}
    db.live_stats.update_one({"fixture_sid": int(fid)}, {"$set": doc}, upsert=True)
    return doc


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
            _store_stats(db, fixture, now)
            out["stats"] += 1
            out["lineups"] = out.get("lineups", 0) + _store_lineups(db, fixture, now)
    db.job_state.update_one({"_id": "live_tick"},
                            {"$set": {"at": now, "provider": PROVIDER, **out}}, upsert=True)
    return out
