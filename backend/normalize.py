"""normalize.py -- PitchAPI JSON in, plain dicts out. No database, no network.

Read everything by `key`, never by the display label. A value that is missing
stays None. It is never turned into zero.

The key names that are not yet verified live in the settings
`provider.pitchapi.team_keys` and `provider.pitchapi.player_keys`.
A key that is None means "not verified yet": that column is stored as None
and shows up in coverage, so the market switches off instead of lying.
"""
from __future__ import annotations


class MissingField(Exception):
    """A required value is absent. The match is skipped and an ingest issue is written."""


# ----------------------------------------------------------------- values
def parse_team_value(v):
    """'329 (82%)' -> 329.0 ; '2.92' -> 2.92 ; '' or None -> None."""
    if v is None or v == "":
        return None
    try:
        return float(str(v).split(" ")[0])
    except ValueError:
        return None


def _num(x):
    if x is None or isinstance(x, bool):
        return None
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


# ------------------------------------------------------------- team stats
def team_items(stats_data: dict) -> dict:
    """{key: {home, away, format_type, title, group}} for the 'All' period.
    Never rely on array position: find the period by name, items by key."""
    out = {}
    for per in stats_data.get("periods", []):
        if str(per.get("period", "")).lower() != "all":
            continue
        for grp in per.get("groups", []):
            for it in grp.get("items", []):
                if it.get("key"):
                    out[it["key"]] = {"home": parse_team_value(it.get("home")),
                                      "away": parse_team_value(it.get("away")),
                                      "format_type": it.get("format_type"),
                                      "title": it.get("title"), "group": grp.get("group_name")}
    return out


TEAM_COLS = ["shots", "sot", "corners", "tackles", "poss", "xg", "fouls", "yellow_cards"]


def team_stats(stats_data: dict, team_keys: dict) -> dict:
    """-> {'home': {col: value|None}, 'away': {...}}"""
    items = team_items(stats_data)
    out = {"home": {}, "away": {}}
    for col in TEAM_COLS:
        key = team_keys.get(col)
        it = items.get(key) if key else None
        out["home"][col] = it["home"] if it else None
        out["away"][col] = it["away"] if it else None
    return out


# ----------------------------------------------------------- player stats
def player_stat(p: dict, group: str, key: str, use: str = "value"):
    """Read one number from a player's stats by group key and stat key."""
    for g in p.get("stats", []):
        if g.get("key") != group:
            continue
        for entry in (g.get("stats") or {}).values():
            if entry.get("key") == key:
                st = entry.get("stat") or {}
                if st.get("type") == "boolean":
                    return None
                return _num(st.get(use, st.get("value")))
    return None


def has_group(p: dict, group: str) -> bool:
    return any(g.get("key") == group for g in p.get("stats", []))


PLAYER_COLS = ["minutes", "shots", "sot", "tackles", "goals", "assists", "xg", "saves",
               "interceptions", "clearances", "fouls_committed", "fouls_won", "passes"]
# A count the provider omits because it is 0. Goals and assists join shots and sot here, and the
# reason they were missing is the reason this mattered: with them null, any per-90 rate divides a
# player's goals by only the games he SCORED in, which puts every scorer in the league near 1.0 a
# game. Nothing downstream could have caught that -- it is a plausible number, not a broken one.
# `tackles` belongs here for the same reason the other four do, and leaving it out cost the product
# its best players. The provider omits a count when it is 0, so a forward who made no tackle was
# stored with `tackles: null`; `tackles` is in engine_bridge.PLAYER_REQUIRED, so `dropna` deleted
# that whole appearance from the engine's frame; and the engine works out how many of his club's
# recent games a player missed by comparing the club's fixtures against his SURVIVING rows -- so a
# deleted appearance is indistinguishable from an absence. Two of them in his club's last two games
# and `p_play` falls under `engine.min_p_play`, which drops every card he has, in every market, with
# no carrier and no log. It is position-correlated, because a forward is who records no tackle.
#
# Measured on the demo league once the fake provider was made to omit a zero the way the real one
# does: 568 stored player rows fell to 395, and the chance-to-play of the affected players roughly
# halved (0.59 -> 0.33 for the second-busiest forward in the league, which is under min_p_play).
ZERO_WHEN_ABSENT = ("shots", "sot", "goals", "assists", "tackles")
# Derived at ingest, not read from the provider: stored so it can be graded, filtered and drawn
# like any other column (score_finished reads `actual` by the stat's own name, the Finder's form
# mode matches on it, and the ten-game strip draws it).
DERIVED_PLAYER_COLS = ("goal_involvements",)


def players(players_data, player_keys: dict, position_map: dict) -> list[dict]:
    """One dict per player who featured. position 'pos' is None when the raw id is not mapped."""
    rows = []
    for p in players_data:
        if not p.get("stats"):          # listed but never on the pitch: no stats groups at all
            continue
        pl = p.get("player", {})
        raw = pl.get("position_id")
        row = {"ext_id": pl.get("id"), "name": pl.get("name"), "team_ext_id": p.get("team_id"),
               "pos_raw": raw, "pos": position_map.get(str(raw)) if raw is not None else None}
        for col in PLAYER_COLS:
            spec = player_keys.get(col) or {}
            if spec.get("key"):
                row[col] = player_stat(p, spec["group"], spec["key"], spec.get("use", "value"))
            else:
                row[col] = None
        # PitchAPI omits a count when it is 0 (0 never appears in real answers). Owner decision: for a player
        # who played, a missing count is 0 when its key is mapped.
        #
        # ...and when the GROUP that would have carried it is present on this player. That second
        # condition is the one tackles already applies below, and it is the difference between "the
        # provider said nothing because it was zero" and "the provider sent us nothing at all". A
        # missing group means no data, and filling a 0 there would invent a fact rather than restore
        # one. Previously only tackles checked it; now every zero-filled column does.
        for col in ZERO_WHEN_ABSENT:
            spec = player_keys.get(col) or {}
            if row[col] is None and spec.get("key") and has_group(p, spec.get("group", "top_stats")):
                row[col] = 0.0
        # Goalkeepers have no defence group: tackles is None, not 0.
        if row["pos"] == "GK":
            row["tackles"] = None
        elif row["tackles"] is not None and not has_group(p, (player_keys.get("tackles") or {}).get("group", "defense")):
            row["tackles"] = None
        # "scored or assisted" as its own column. None unless BOTH parts are known: a sum that
        # silently treats an unknown as a zero is the same error this whole block exists to stop.
        row["goal_involvements"] = (None if row["goals"] is None or row["assists"] is None
                                    else float(row["goals"]) + float(row["assists"]))
        rows.append(row)
    return rows


# ---------------------------------------------------------------- lineups
def lineup_pos(x: dict, position_map: dict):
    """Starters: position_id is a formation-grid slot, so the line comes from pitch_x (depth, 0 own goal to 1). Subs: position_map."""
    px = x.get("pitch_x")
    if x.get("started") and px:
        return "GK" if px < 0.2 else "DEF" if px < 0.45 else "MID" if px < 0.8 else "FWD"
    raw = x.get("position_id")
    return position_map.get(str(raw)) if raw is not None else None


def lineups(lineups_data: dict) -> dict:
    out = {}
    for side in ("home", "away"):
        d = lineups_data.get(side) or {}
        people = []
        for kind, started in (("starters", True), ("subs", False)):
            for x in d.get(kind, []) or []:
                people.append({"ext_id": x.get("player_id"), "started": started,
                               "shirt_number": x.get("shirt_number"), "position_id": x.get("position_id"),
                               "pitch_x": x.get("pitch_x"), "pitch_y": x.get("pitch_y"),
                               "is_captain": bool(x.get("is_captain", False)), "name": x.get("name")})
        out[side] = {"confirmed": bool(d.get("confirmed", False)), "formation": d.get("formation"),
                     "lineup_type": d.get("lineup_type"), "players": people}
    return out


# ------------------------------------------------------------------ match
REQUIRED_TEAM = ["shots"]
REQUIRED_PLAYER = ["minutes", "shots"]


def normalize_match(match: dict, stats_data, players_data, lineups_data, settings: dict) -> dict:
    """match: {'home_ext','away_ext',...}. settings: team_keys, player_keys, position_map.
    Returns rows by external id plus issues. Raises MissingField for a required gap."""
    ts = team_stats(stats_data, settings["team_keys"])
    pl = players(players_data, settings["player_keys"], settings["position_map"])
    lu = lineups(lineups_data)
    issues = []

    for side in ("home", "away"):
        for col in REQUIRED_TEAM:
            if ts[side][col] is None:
                # fall back to the sum of player values if the player key exists
                tot = _sum_team(pl, match[side + "_ext"], col)
                if tot is None:
                    raise MissingField(f"team {col} missing for {side}")
                ts[side][col] = tot
                issues.append({"kind": "team_stat_from_players", "detail": col})
    gaps = [p["ext_id"] for p in pl if p["minutes"] is None or p["shots"] is None]
    if gaps:   # PitchAPI leaves keys out (seen on real answers): keep None, record once per match, do not drop the match
        issues.append({"kind": "player_stat_missing", "detail": f"{len(gaps)} players without minutes or shots: " + ", ".join(gaps[:10])})

    # started flag comes from the lineups endpoint
    started = {x["ext_id"] for s in ("home", "away") for x in lu[s]["players"] if x["started"]}
    for p in pl:
        p["started"] = p["ext_id"] in started

    # /players sends no position_id on real answers: take the line from the lineup
    lpos = {x["ext_id"]: lineup_pos(x, settings["position_map"]) for s in ("home", "away") for x in lu[s]["players"]}
    for p in pl:
        if p["pos"] is None:
            p["pos"] = lpos.get(p["ext_id"])
            if p["pos"] == "GK":
                p["tackles"] = None

    # team totals for the engine = sum over that team's players, same keys
    totals = {}
    for side in ("home", "away"):
        ext = match[side + "_ext"]
        totals[side] = {c: _sum_team(pl, ext, c) for c in ("shots", "sot", "tackles")}
        if ts[side]["tackles"] is None:
            ts[side]["tackles"] = totals[side]["tackles"]
        if ts[side]["sot"] is None:
            ts[side]["sot"] = totals[side]["sot"]
        s_stats, s_sum = ts[side]["shots"], totals[side]["shots"]
        if s_sum is not None and s_stats is not None and abs(s_stats - s_sum) > 1:
            issues.append({"kind": "team_player_shots_gap", "detail": f"{side}: stats {s_stats} vs players {s_sum}"})
    return {"team": ts, "players": pl, "lineups": lu, "team_totals": totals, "issues": issues}


def _sum_team(pl, team_ext, col):
    vals = [p[col] for p in pl if p["team_ext_id"] == team_ext and p[col] is not None]
    return float(sum(vals)) if vals else None


# --------------------------------------------------------------- listings
def status_of(raw: str | None) -> str:
    """Our status. Anything other than the two known values is 'other' (skipped, logged)."""
    return {"finished": "final", "not_started": "scheduled"}.get(raw or "", "other")


def match_row(m: dict, league_ext: str | None = None, season: str | None = None) -> dict:
    """One element of matches[] from /v1/leagues/{id}/matches or /v1/date/{date}."""
    lg = m.get("league") or {}
    return {"ext_id": m["id"], "league_ext": lg.get("id") or league_ext, "season": season,
            "kickoff_iso": m.get("time_utc"), "provider_status": m.get("status"), "status": status_of(m.get("status")),
            "home_ext": m["home_team"]["id"], "home_name": m["home_team"]["name"],
            "away_ext": m["away_team"]["id"], "away_name": m["away_team"]["name"],
            "hg": m.get("score_home"), "ag": m.get("score_away")}
