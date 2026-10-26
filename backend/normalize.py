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
               "interceptions", "clearances", "fouls_committed", "fouls_won"]
ZERO_WHEN_ABSENT = ("shots", "sot")


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
        # PitchAPI omits a count when it is 0 (0 never appears in real answers). Owner decision: for a player who
        # played, a missing shots / shots-on-target count is 0 when its key is mapped.
        for col in ZERO_WHEN_ABSENT:
            if row[col] is None and (player_keys.get(col) or {}).get("key"):
                row[col] = 0.0
        # Goalkeepers have no defence group: tackles is None, not 0.
        if row["pos"] == "GK":
            row["tackles"] = None
        elif row["tackles"] is not None and not has_group(p, (player_keys.get("tackles") or {}).get("group", "defense")):
            row["tackles"] = None
        rows.append(row)
    return rows


# ---------------------------------------------------------------- lineups
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
