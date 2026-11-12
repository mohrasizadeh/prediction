"""normalize_af.py -- API-Football JSON in, the same plain dicts normalize.py returns. docs/85.

The contract is deliberately identical to `normalize.normalize_match`, so `ingest.py` changes only
in which client it calls and which endpoint it reads. Everything downstream -- the frames, the
engine, the cards -- never learns that the provider changed.

Input is one element of `/fixtures?ids=` (docs/81 §1), which carries the fixture, its teams, its
score, its events, its lineups, its team statistics and its player statistics in one answer.

Three things in here are not transcription, and each one is a decision:

1. ABSENT-OR-ZERO, rebuilt. The provider omits a count that is zero, and says so: "absence alone
   does not tell you which of the two applies" (docs/82). That ambiguity is the bug that deleted
   appearances, read a deleted appearance as an absence, halved `p_play` and dropped every card of
   the players it hit -- position-correlated, because a forward is who records no tackle (568 stored
   rows fell to 395).

   PitchAPI's guard asked whether the stat's GROUP was present on that player. There are no groups
   here, and the replacement is a better test of the actual question: is this field non-null for any
   OTHER player in the same fixture? If fifteen other players have a tackle count, tackles were
   tracked in this match, so a null here is a real zero. If nobody has one, the match did not track
   them and it stays None. `_tracked_in_fixture` does that, once per fixture.

2. KEEPERS KEEP THEIR TACKLES. `normalize.players` blanks a goalkeeper's tackles, because PitchAPI
   sent keepers no defence group at all, so a 0 there would have been invented. API-Football puts
   every player's tackles in the same object, so a keeper's 0 is a real 0 -- and reproducing the old
   blanking would put `None` in a column that is in `engine_bridge.PLAYER_REQUIRED`, which is what
   deletes keeper rows on a flat dropna (docs/70). The old behaviour was a provider artefact, not a
   rule, and carrying it over would cost us the saves market.

3. EXTRA TIME IS FLAGGED, and by default excluded from the fitting frame. `statistics` is the whole
   match including extra time, with nothing to say so, so a 120-minute cup tie reports its shots,
   corners and tackles as one inflated number. Fitted beside 90-minute matches it drags every
   team-total model upward and makes cup fixtures look fast-paced. `provider.apifootball.exclude_extra_time`
   defaults on: the match is still ingested, still shown, still graded -- it is only kept out of the
   frames the engine fits. Keeping it costs one cup tie in ten; including it biases every model.

Two columns API-Football does not carry at all, and both are unused (docs/80 §1): `xg`, which needs
an add-on nobody is on, and `clearances`. They are stored as None, as a missing value always is.
"""
from __future__ import annotations

from normalize import MissingField, PLAYER_COLS, TEAM_COLS, _num

# Our column <- where it lives in a player's statistics block. (group, field) into the nested dicts
# the provider sends; None means the provider has no such number.
PLAYER_PATHS = {
    "minutes": ("games", "minutes"),
    "shots": ("shots", "total"),
    "sot": ("shots", "on"),
    "goals": ("goals", "total"),
    "assists": ("goals", "assists"),
    "saves": ("goals", "saves"),
    "tackles": ("tackles", "total"),
    "interceptions": ("tackles", "interceptions"),
    "fouls_committed": ("fouls", "committed"),
    "fouls_won": ("fouls", "drawn"),
    "passes": ("passes", "total"),
    "xg": None,              # Expected Goals add-on only, and engine.xg_blend is 0 (docs/80 §1)
    "clearances": None,      # not carried; unused by any market or required column
}

# A count the provider omits when it is zero. Same list as normalize.ZERO_WHEN_ABSENT, for the same
# reason, plus the two that only exist here.
ZERO_WHEN_ABSENT = ("shots", "sot", "goals", "assists", "tackles", "interceptions",
                    "fouls_committed", "fouls_won", "passes", "saves")

# Their fixture status shorts, to ours. normalize.status_of's vocabulary: final | scheduled | other.
FINAL_SHORTS = {"FT", "AET", "PEN"}
SCHEDULED_SHORTS = {"NS", "TBD"}
EXTRA_TIME_SHORTS = {"AET", "PEN"}       # reached extra time, so its totals cover more than 90'


def status_of(short: str | None) -> str:
    s = str(short or "").upper()
    return "final" if s in FINAL_SHORTS else "scheduled" if s in SCHEDULED_SHORTS else "other"


def went_to_extra_time(fixture: dict) -> bool:
    """Did this match run past 90 minutes? Read from the status, not from the clock, because the
    clock stops reporting once a match is over."""
    short = (((fixture or {}).get("fixture") or {}).get("status") or {}).get("short")
    return str(short or "").upper() in EXTRA_TIME_SHORTS


# ------------------------------------------------------------------ values
def parse_team_value(v):
    """'59%' -> 59.0 ; '295' -> 295.0 ; None or '' -> None.

    Possession and the pass percentage arrive with a per-cent sign; everything else is a bare
    number as a string or an int.
    """
    if v is None or v == "":
        return None
    s = str(v).strip().rstrip("%").strip()
    try:
        return float(s)
    except ValueError:
        return None


def team_items(fixture: dict) -> dict:
    """{team ext id: {statistic name: value}} for one fixture.

    Their `statistics` is a list per team of `{type, value}`, where `type` is a DISPLAY STRING and
    not a stable id -- which is why the map lives in settings and the admin screen checks it against
    a real answer (docs/81 §3).
    """
    out = {}
    for block in (fixture.get("statistics") or []):
        tid = ((block.get("team") or {}).get("id"))
        if tid is None:
            continue
        got = {}
        for st in (block.get("statistics") or []):
            if st.get("type"):
                got[str(st["type"])] = parse_team_value(st.get("value"))
        out[str(tid)] = got
    return out


def team_stats(fixture: dict, team_keys: dict, home_ext: str, away_ext: str) -> dict:
    items = team_items(fixture)
    out = {"home": {}, "away": {}}
    for side, ext in (("home", str(home_ext)), ("away", str(away_ext))):
        got = items.get(str(ext), {})
        for col in TEAM_COLS:
            name = team_keys.get(col)
            out[side][col] = got.get(name) if name else None
    return out


# ------------------------------------------------------------------ players
def _player_blocks(fixture: dict) -> list[tuple[str, dict, dict]]:
    """(team ext id, player, that player's one statistics block) for everyone who featured."""
    rows = []
    for block in (fixture.get("players") or []):
        tid = ((block.get("team") or {}).get("id"))
        for p in (block.get("players") or []):
            stats = (p.get("statistics") or [{}])
            rows.append((str(tid), p.get("player") or {}, stats[0] if stats else {}))
    return rows


def _raw(stat: dict, path):
    if not path:
        return None
    group, field = path
    return _num(((stat.get(group) or {}) or {}).get(field))


def _tracked_in_fixture(blocks) -> dict:
    """{column: was this number recorded for ANYONE in this match}.

    The replacement for PitchAPI's group check, and a direct test of the question rather than a
    proxy for it: if any player in the match has a tackle count, the match tracked tackles, so a
    null for another player is a real zero. If nobody does, it was not tracked and null stays None.
    """
    seen = {}
    for col, path in PLAYER_PATHS.items():
        if not path:
            seen[col] = False
            continue
        seen[col] = any(_raw(stat, path) is not None for _, _, stat in blocks)
    return seen


def players(fixture: dict, position_map: dict) -> list[dict]:
    blocks = _player_blocks(fixture)
    tracked = _tracked_in_fixture(blocks)
    rows = []
    for team_ext, p, stat in blocks:
        games = stat.get("games") or {}
        if not stat:                      # listed with no statistics block at all: never on the pitch
            continue
        raw_pos = games.get("position")
        row = {
            "ext_id": str(p.get("id")) if p.get("id") is not None else None,
            "name": p.get("name"), "team_ext_id": team_ext,
            "pos_raw": raw_pos,
            "pos": position_map.get(str(raw_pos)) if raw_pos is not None else None,
            # their own flag, so the started flag needs no lineups cross-reference the way
            # normalize.normalize_match had to build one
            "started": (games.get("substitute") is False) or None,
            "shirt": games.get("number"), "rating": _num(games.get("rating")),
            "captain": bool(games.get("captain")),
        }
        for col in PLAYER_COLS:
            row[col] = _raw(stat, PLAYER_PATHS.get(col))
        # the guard: a null is a zero only where the match recorded that number for somebody
        for col in ZERO_WHEN_ABSENT:
            if row.get(col) is None and tracked.get(col):
                row[col] = 0.0
        # A keeper's tackles are a real 0 here, unlike PitchAPI: see the header, point 2.
        row["goal_involvements"] = (None if row.get("goals") is None or row.get("assists") is None
                                    else float(row["goals"]) + float(row["assists"]))
        if row["ext_id"]:
            rows.append(row)
    return rows


# ------------------------------------------------------------------ lineups
def lineups(fixture: dict, position_map: dict) -> dict:
    """The official eleven and bench, per side.

    Theirs are the published lineups (20 to 40 minutes before kick-off), so a lineup that is here
    IS confirmed -- there is no predicted-versus-official distinction to carry, which is what
    PitchAPI's `lineup_type` existed for.
    """
    teams = fixture.get("teams") or {}
    want = {str((teams.get("home") or {}).get("id")): "home",
            str((teams.get("away") or {}).get("id")): "away"}
    out = {"home": {"confirmed": False, "formation": None, "lineup_type": None, "players": []},
           "away": {"confirmed": False, "formation": None, "lineup_type": None, "players": []}}
    for block in (fixture.get("lineups") or []):
        side = want.get(str(((block.get("team") or {}).get("id"))))
        if side is None:
            continue
        people = []
        for kind, started in (("startXI", True), ("substitutes", False)):
            for x in (block.get(kind) or []):
                pl = x.get("player") or {}
                people.append({
                    "ext_id": str(pl.get("id")) if pl.get("id") is not None else None,
                    "started": started, "shirt_number": pl.get("number"),
                    "position_id": pl.get("pos"),
                    "pos": position_map.get(str(pl.get("pos"))) if pl.get("pos") else None,
                    # "1:1", "2:4" -- row:column on the pitch grid, their own notation
                    "grid": pl.get("grid"), "pitch_x": None, "pitch_y": None,
                    "is_captain": False, "name": pl.get("name"),
                })
        out[side] = {"confirmed": bool(people), "formation": block.get("formation"),
                     "lineup_type": "official" if people else None,
                     "coach": ((block.get("coach") or {}).get("name")),
                     "coach_ext_id": ((block.get("coach") or {}).get("id")),
                     "players": people}
    return out


# ------------------------------------------------------------------ one match
REQUIRED_TEAM = ["shots"]


def _sum_team(pl, team_ext, col):
    vals = [p[col] for p in pl if p["team_ext_id"] == str(team_ext) and p.get(col) is not None]
    return float(sum(vals)) if vals else None


def normalize_match(fixture: dict, settings: dict) -> dict:
    """One bundled fixture -> the same shape `normalize.normalize_match` returns, plus `extra_time`.

    settings: team_keys, position_map, exclude_extra_time.
    """
    teams = fixture.get("teams") or {}
    home_ext = str((teams.get("home") or {}).get("id"))
    away_ext = str((teams.get("away") or {}).get("id"))
    issues = []

    ts = team_stats(fixture, settings["team_keys"], home_ext, away_ext)
    pl = players(fixture, settings["position_map"])
    lu = lineups(fixture, settings["position_map"])

    et = went_to_extra_time(fixture)
    if et:
        issues.append({"kind": "extra_time",
                       "detail": "totals cover more than 90 minutes; "
                                 + ("kept out of the engine's frames" if settings.get("exclude_extra_time", True)
                                    else "INCLUDED in the frames, which biases team totals upward")})

    for side, ext in (("home", home_ext), ("away", away_ext)):
        for col in REQUIRED_TEAM:
            if ts[side][col] is None:
                tot = _sum_team(pl, ext, col)
                if tot is None:
                    raise MissingField(f"team {col} missing for {side}")
                ts[side][col] = tot
                issues.append({"kind": "team_stat_from_players", "detail": col})

    gaps = [p["ext_id"] for p in pl if p.get("minutes") is None or p.get("shots") is None]
    if gaps:
        issues.append({"kind": "player_stat_missing",
                       "detail": f"{len(gaps)} players without minutes or shots: " + ", ".join(gaps[:10])})

    # A starter flag we could not read from `games.substitute` falls back to the lineup, as
    # normalize.normalize_match always did.
    started = {x["ext_id"] for s in ("home", "away") for x in lu[s]["players"] if x["started"]}
    for p in pl:
        if p.get("started") is None:
            p["started"] = p["ext_id"] in started

    # A position the player row did not carry comes from the lineup, which has one per player.
    lpos = {x["ext_id"]: x["pos"] for s in ("home", "away") for x in lu[s]["players"] if x.get("pos")}
    for p in pl:
        if p.get("pos") is None:
            p["pos"] = lpos.get(p["ext_id"])

    totals = {}
    for side, ext in (("home", home_ext), ("away", away_ext)):
        # Only the stats whose TEAM total sits on the player row, because the engine builds a
        # player's rate as his share of it (docs/70).
        totals[side] = {c: _sum_team(pl, ext, c)
                        for c in ("shots", "sot", "tackles", "fouls_committed", "goal_involvements")}
        # No team tackles statistic exists here, so the team total IS the sum of the players'
        # (docs/80 §2). The same fallback normalize.py has always used.
        for col in ("tackles", "sot"):
            if ts[side][col] is None:
                ts[side][col] = totals[side][col]
        s_stats, s_sum = ts[side]["shots"], totals[side]["shots"]
        if s_sum is not None and s_stats is not None and abs(s_stats - s_sum) > 1:
            issues.append({"kind": "team_player_shots_gap", "detail": f"{side}: stats {s_stats} vs players {s_sum}"})

    return {"team": ts, "players": pl, "lineups": lu, "team_totals": totals,
            "extra_time": et, "issues": issues}


# ------------------------------------------------------------------ the fixture listing
def match_row(fixture: dict) -> dict:
    """One fixture's own row, for `matches`. The shape `normalize.match_row` returns."""
    fx = fixture.get("fixture") or {}
    lg = fixture.get("league") or {}
    teams = fixture.get("teams") or {}
    goals = fixture.get("goals") or {}
    short = ((fx.get("status") or {}).get("short"))
    return {
        "ext_id": str(fx.get("id")),
        "league_ext": str(lg.get("id")) if lg.get("id") is not None else None,
        "season": str(lg.get("season")) if lg.get("season") is not None else None,
        "round": lg.get("round"),
        "kickoff_iso": fx.get("date"),
        "provider_status": short, "status": status_of(short),
        "extra_time": str(short or "").upper() in EXTRA_TIME_SHORTS,
        "home_ext": str((teams.get("home") or {}).get("id")),
        "home_name": (teams.get("home") or {}).get("name"),
        "away_ext": str((teams.get("away") or {}).get("id")),
        "away_name": (teams.get("away") or {}).get("name"),
        "hg": goals.get("home"), "ag": goals.get("away"),
        # Free here, where PitchAPI needed a per-match detail call for it (docs/80 §2), so
        # referees.py gets fed without ingest.match_extra_detail.
        "referee": fx.get("referee"),
        "venue": ((fx.get("venue") or {}).get("name")),
        "elapsed": ((fx.get("status") or {}).get("elapsed")),
    }
