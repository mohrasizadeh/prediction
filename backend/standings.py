"""standings.py -- a competition's table as the competition actually runs it.

The League page drew ONE table from every finished match it could find: three points a win, sorted.
That is right for a league and wrong for nearly every cup:

  * UEFA NATIONS LEAGUE is four leagues (A to D) of several groups each. One table put Spain and San
    Marino in a single ranking of fifty-odd sides that never played each other.
  * A WORLD CUP, EURO or the old CHAMPIONS LEAGUE is groups first, then knockout rounds, and a
    knockout tie is not three points.
  * The FA CUP has no table at all. Every row the old table drew for it was invented.
  * The NEW CHAMPIONS LEAGUE is one 36-team league phase, then knockouts -- one table, but only of
    the league phase.

API-Football already knows each format. `/standings` answers with a LIST OF GROUPS -- one for a
league, eight for World Cup groups, one per group for each Nations League tier -- each row naming its
group, and answers empty for a competition that has no table. Every fixture carries its round name
("Group Stage - 2", "League A - 4", "Quarter-finals"). So nothing here guesses a format from a name:
the groups are the provider's, and the knockout rounds are the fixtures whose round is not a
group or league-phase matchday.

Tables are fetched by the tick, not by a page view (docs/82 §7: only for competitions with a fixture
in the last day or none stored yet), and stored in `league_standings`. A page view reads that row.
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

import settings_store as S

# A round that is one matchday of a table: "Regular Season - 12", "Group Stage - 2", "Group A - 3",
# "League A - 4", "League Stage - 8", "League Path - 1". Everything else is a knockout or play-off
# round ("Round of 16", "Quarter-finals", "Final", "1st Qualifying Round", "Play-offs").
TABLE_ROUND = re.compile(r"^(regular season|group stage|group [a-z0-9]+|league [a-d]\b|league stage|league path|league phase|apertura|clausura)", re.I)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def is_table_round(stage: str | None) -> bool:
    return bool(stage) and bool(TABLE_ROUND.match(stage.strip()))


def _row(r: dict) -> dict:
    a = r.get("all") or {}
    g = a.get("goals") or {}
    team = r.get("team") or {}
    return {"rank": r.get("rank"), "team_ext": str(team.get("id")) if team.get("id") is not None else None,
            "team_name": team.get("name"), "p": a.get("played"), "w": a.get("win"), "d": a.get("draw"),
            "l": a.get("lose"), "gf": g.get("for"), "ga": g.get("against"), "gd": r.get("goalsDiff"),
            "pts": r.get("points"), "form": (r.get("form") or "")[-5:], "description": r.get("description"),
            "group": r.get("group")}


def parse(response: list) -> list[dict]:
    """API-Football's `/standings` answer into [{name, rows}], in the provider's own order."""
    groups = []
    for item in response or []:
        for block in ((item.get("league") or {}).get("standings") or []):
            rows = [_row(r) for r in block or []]
            if not rows:
                continue
            groups.append({"name": rows[0].get("group") or "", "rows": rows})
    return groups


def sync(client, league: dict, season: int | str) -> int:
    """Fetch and store one competition-season's groups. Returns how many groups were stored."""
    import apifootball as AF
    db = client.db
    resp = AF.standings(client, int(league["ext_id"]), int(season))
    groups = parse(resp)
    db.league_standings.update_one({"league_iid": league["iid"], "season": str(season)},
                                   {"$set": {"league_iid": league["iid"], "season": str(season), "groups": groups,
                                             "at": utcnow()}}, upsert=True)
    return len(groups)


def due(db, league: dict, season: str, now: datetime) -> bool:
    """Only competitions that played in the last day, or have no table stored yet (docs/82 §7)."""
    row = db.league_standings.find_one({"league_iid": league["iid"], "season": str(season)}, {"at": 1})
    if not row:
        return True
    at = row.get("at")
    at = at if at is None or at.tzinfo else at.replace(tzinfo=timezone.utc)
    hours = float(S.get(db, "cache.ttl.standings_hours") or 1)
    if at and now - at < timedelta(hours=hours):
        return False
    since = (now - timedelta(hours=30)).replace(tzinfo=None)
    return db.matches.count_documents({"league_iid": league["iid"], "kickoff": {"$gte": since, "$lte": now.replace(tzinfo=None)}}, limit=1) > 0


def sync_due(client, leagues: list[dict], now: datetime | None = None, left=lambda: True) -> int:
    from ingest_af import _current_season
    now = now or utcnow()
    n = 0
    for lg in leagues:
        if not left():
            break
        season = _current_season(client.db, lg)
        if due(client.db, lg, str(season), now):
            n += sync(client, lg, season)
    return n


def _team_refs(db, exts: list[str]) -> dict:
    import queries as Q
    rows = list(db.teams.find({"ext_id": {"$in": [e for e in exts if e]}}, {"_id": 0, "iid": 1, "ext_id": 1}))
    named = Q._names(db, "teams", [r["iid"] for r in rows])
    return {r["ext_id"]: {k: v for k, v in named.get(r["iid"], {}).items() if k not in ("iid", "team_iid", "pos")} for r in rows}


def read(db, league: dict, season: str | None = None) -> dict:
    """What the League page's Table tab draws.

    {format, groups: [{name, rows}], rounds: [{name, matches}]}. `format` is "table" (one group),
    "groups" (several), "knockout" (no table, only rounds) or "none" (nothing from the provider:
    the page builds a table from results, which is right only for a plain league).
    """
    import queries as Q
    season = str(season or league.get("current_season") or "")
    row = db.league_standings.find_one({"league_iid": league["iid"], "season": season}, {"_id": 0}) or {}
    groups = row.get("groups") or []
    refs = _team_refs(db, [r.get("team_ext") for g in groups for r in g["rows"]])
    out_groups = []
    for g in groups:
        rows = []
        for r in g["rows"]:
            t = refs.get(r.get("team_ext")) or {"id": None, "name": r.get("team_name"), "image": None}
            rows.append({**{k: v for k, v in r.items() if k not in ("team_ext", "team_name", "group")}, "team": t})
        out_groups.append({"name": g.get("name") or "", "rows": rows})

    # Knockout rounds: every fixture whose round is not a table matchday, oldest round first.
    ms = list(db.matches.find({"league_iid": league["iid"], "season": season, "stage": {"$nin": [None, ""]}},
                              {"_id": 0, "iid": 1, "id": 1, "stage": 1, "kickoff": 1, "status": 1, "hg": 1, "ag": 1,
                               "home_iid": 1, "away_iid": 1, "pen_home": 1, "pen_away": 1}))
    ko = [m for m in ms if not is_table_round(m.get("stage"))]
    tm = Q._names(db, "teams", [t for m in ko for t in (m["home_iid"], m["away_iid"])])
    rounds: dict = {}
    for m in sorted(ko, key=lambda m: m.get("kickoff") or datetime.min):
        rounds.setdefault(m["stage"], []).append({
            "id": m.get("id"), "kickoff": m.get("kickoff"), "status": m.get("status"), "hg": m.get("hg"), "ag": m.get("ag"),
            "pen_home": m.get("pen_home"), "pen_away": m.get("pen_away"),
            "home": tm.get(m["home_iid"]), "away": tm.get(m["away_iid"])})
    out_rounds = [{"name": k, "matches": v} for k, v in rounds.items()]
    fmt = "groups" if len(out_groups) > 1 else "table" if out_groups else "knockout" if out_rounds else "none"
    return {"format": fmt, "season": season, "kind": league.get("kind"), "groups": out_groups, "rounds": out_rounds, "at": row.get("at")}
