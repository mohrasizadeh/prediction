"""af_leagues.py -- which competitions we carry, what each one is FOR, and how it maps to an
API-Football league id. docs/81.

The owner's list is about forty competitions across three tiers. Carrying them is free on this
provider -- every plan has every league -- but carrying them all the same way would break the
engine, in two ways that produce plausible output rather than errors.

  1. A TEAM WOULD CHANGE LEAGUE EVERY TIME A CUP IS INGESTED. `ingest.sync_league_matches` stamps
     `teams.league_iid` from whichever competition the match came from, and `images.py` and the
     live team mapping both look clubs up BY that field. Ingest the FA Cup and every English club
     belongs to the FA Cup; the crest sync then finds no clubs in the Premier League and the live
     mapper has nobody to match against.

  2. THE ENGINE FITS ONE FRAME PER `league_iid`. A Champions League "league" is 32 clubs playing
     eight games each, with no common baseline, while the same clubs' league frames silently lose
     those matches. And a Premier League club's shots against a League Two side are not Premier
     League shots: pooling them biases every team-total model that docs/18 says is already doing
     most of the work.

So a competition has a ROLE, and the role decides what is done with it:

    forecast   fit models, publish cards. Domestic leagues only: one division, a full season, a
               common pool of clubs. These and only these set `teams.league_iid`.
    calendar   fixtures, results and lineups, nothing else. Feeds context.py's rotation and
               congestion model -- which is the whole reason to carry cups at all, because the
               midweek tie is WHY a club rotates on Saturday (docs/18 §3) -- plus the club page
               and the "played Tuesday" line. No cards, no rows in the engine's frames.
    off        known, listed in admin, not ingested.

National-team tournaments are `calendar` at best. The engine has no national-team history: a
player's share of his CLUB's shots says little about his share of his country's, squads turn over
between tournaments, and a team plays three group games. They are a content and fixtures feature
here, not a forecasting one, and the admin screen says so rather than offering cards that would
be guesses.

No league id is written down in this file. Ids are resolved against `/leagues` and confirmed in
admin, because a hard-coded id that is quietly wrong maps a competition to another competition,
and nothing downstream could tell.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import settings_store as S
from apifootball import coverage

FORECAST, CALENDAR, OFF = "forecast", "calendar", "off"
PROVIDER_KEY = "apifootball"


def _e(key, name, country, kind, tier, role, note=""):
    return {"key": key, "name": name, "country": country, "kind": kind, "tier": tier,
            "role": role, "note": note}


# kind: "league" (a domestic division), "cup" (domestic knockout), "continental" (club, across
# countries), "international" (national teams). API-Football's own `type` is only league|cup, so
# ours is the finer one and is used to pick the default role.
CATALOG = [
    # ---- Tier 1: the baseline -------------------------------------------------------------
    _e("eng.pl", "Premier League", "England", "league", 1, FORECAST),
    _e("esp.laliga", "La Liga", "Spain", "league", 1, FORECAST),
    _e("ita.seriea", "Serie A", "Italy", "league", 1, FORECAST),
    _e("ger.bundesliga", "Bundesliga", "Germany", "league", 1, FORECAST),
    _e("fra.ligue1", "Ligue 1", "France", "league", 1, FORECAST),
    _e("uefa.ucl", "UEFA Champions League", "World", "continental", 1, CALENDAR,
       "Mixed-league field, 8 games a club. Carried for the calendar: a Tuesday here is why a club rotates on Saturday."),
    _e("uefa.uel", "UEFA Europa League", "World", "continental", 1, CALENDAR),
    _e("uefa.uecl", "UEFA Europa Conference League", "World", "continental", 1, CALENDAR),
    _e("fifa.wc", "World Cup", "World", "international", 1, CALENDAR, "National teams: no club history to fit."),
    _e("fifa.wcq", "World Cup Qualification", "World", "international", 1, CALENDAR,
       "Several confederations, each its own competition in the API. Resolve them one by one."),
    _e("uefa.euro", "Euro Championship", "World", "international", 1, CALENDAR),
    _e("conmebol.copaamerica", "Copa America", "World", "international", 1, CALENDAR),

    # ---- Tier 2: secondary leagues and the domestic cups ----------------------------------
    _e("eng.championship", "Championship", "England", "league", 2, FORECAST),
    _e("ned.eredivisie", "Eredivisie", "Netherlands", "league", 2, FORECAST),
    _e("por.primeira", "Primeira Liga", "Portugal", "league", 2, FORECAST),
    _e("sco.premiership", "Premiership", "Scotland", "league", 2, FORECAST),
    _e("tur.superlig", "Süper Lig", "Turkey", "league", 2, FORECAST),
    _e("eng.facup", "FA Cup", "England", "cup", 2, CALENDAR,
       "Divisions mix. docs/18 measured the effect on who starts, not on team totals."),
    _e("eng.efl", "League Cup", "England", "cup", 2, CALENDAR),
    _e("esp.copadelrey", "Copa del Rey", "Spain", "cup", 2, CALENDAR),
    _e("ger.pokal", "DFB Pokal", "Germany", "cup", 2, CALENDAR),
    _e("ita.coppa", "Coppa Italia", "Italy", "cup", 2, CALENDAR),
    _e("fra.coupe", "Coupe de France", "France", "cup", 2, CALENDAR),
    _e("usa.mls", "Major League Soccer", "USA", "league", 2, FORECAST),
    _e("concacaf.leaguescup", "Leagues Cup", "World", "continental", 2, CALENDAR),
    _e("bra.seriea", "Serie A", "Brazil", "league", 2, FORECAST),
    _e("arg.primera", "Liga Profesional Argentina", "Argentina", "league", 2, FORECAST),
    _e("conmebol.libertadores", "CONMEBOL Libertadores", "World", "continental", 2, CALENDAR),
    _e("conmebol.sudamericana", "CONMEBOL Sudamericana", "World", "continental", 2, CALENDAR),
    _e("mex.ligamx", "Liga MX", "Mexico", "league", 2, FORECAST),
    _e("ksa.proleague", "Pro League", "Saudi-Arabia", "league", 2, FORECAST),

    # ---- Tier 3: year-round coverage -------------------------------------------------------
    _e("afc.asiancup", "Asian Cup", "World", "international", 3, CALENDAR),
    _e("caf.afcon", "Africa Cup of Nations", "World", "international", 3, CALENDAR),
    _e("concacaf.goldcup", "CONCACAF Gold Cup", "World", "international", 3, CALENDAR),
    _e("uefa.nations", "UEFA Nations League", "World", "international", 3, CALENDAR),
    _e("concacaf.nations", "CONCACAF Nations League", "World", "international", 3, CALENDAR),
    _e("fifa.cwc", "FIFA Club World Cup", "World", "continental", 3, CALENDAR),
    _e("concacaf.champions", "CONCACAF Champions League", "World", "continental", 3, CALENDAR,
       "Listed by the owner as the Champions Cup; the API may still carry the former name. Confirm in admin."),
    _e("afc.champions", "AFC Champions League", "World", "continental", 3, CALENDAR,
       "The 'Elite' rebrand may appear as a separate competition. Confirm in admin."),
]

BY_KEY = {e["key"]: e for e in CATALOG}


def default_role(kind: str) -> str:
    """Why a competition gets the role it gets. One rule, stated once."""
    return FORECAST if kind == "league" else CALENDAR


# ------------------------------------------------------------------ resolving a name to an id
def _norm(s) -> str:
    return "".join(ch for ch in str(s or "").lower() if ch.isalnum())


def score_name(ours: str, theirs: str) -> float:
    """Cheap and strict. An exact normalised match wins; containment is a candidate, not an answer."""
    a, b = _norm(ours), _norm(theirs)
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    if a in b or b in a:
        return 0.8
    at, bt = set(_norm(w) for w in str(ours).split()), set(_norm(w) for w in str(theirs).split())
    inter = at & bt
    return 0.6 * len(inter) / max(len(at | bt), 1)


def candidates(client, entry: dict, limit: int = 5) -> list[dict]:
    """What `/leagues` offers for this catalogue row, best first. Never picks: admin confirms."""
    params = {"search": entry["name"]} if len(entry["name"]) >= 3 else {"name": entry["name"]}
    rows = client.fetch("/leagues", params,
                        ttl=timedelta(days=S.get(client.db, "cache.ttl.reference_days")),
                        purpose="league_search")
    out = []
    for r in rows:
        lg, ctry = r.get("league") or {}, r.get("country") or {}
        s = score_name(entry["name"], lg.get("name"))
        same_country = _norm(ctry.get("name")) == _norm(entry["country"])
        if same_country:
            s += 0.25
        elif entry["country"] == "World" and _norm(ctry.get("name")) == "world":
            s += 0.25
        else:
            s -= 0.15                       # a same-named league in another country is the classic wrong map
        out.append({"id": lg.get("id"), "name": lg.get("name"), "type": lg.get("type"),
                    "country": ctry.get("name"), "logo": lg.get("logo"),
                    "seasons": sorted([s_.get("year") for s_ in (r.get("seasons") or []) if s_.get("year")], reverse=True)[:6],
                    "score": round(min(s, 1.0), 3), "same_country": same_country})
    out.sort(key=lambda x: -x["score"])
    return out[:limit]


def auto_pick(cands: list[dict], min_score: float = 0.95, margin: float = 0.1):
    """The one candidate we would accept without a human. Deliberately hard to satisfy: an
    ambiguous map is the failure that is invisible afterwards."""
    if not cands:
        return None
    best = cands[0]
    runner = cands[1]["score"] if len(cands) > 1 else 0.0
    ok = best["score"] >= min_score and (best["score"] - runner) >= margin and best.get("id")
    return best if ok else None


# ------------------------------------------------------------------ the plan, for the admin screen
def plan_row(client, entry: dict, seasons: list[int]) -> dict:
    """One catalogue row, resolved and checked: the candidates, the pick if it is unambiguous, the
    coverage of each season, and whether the role it was given is actually supportable."""
    cands = candidates(client, entry)
    pick = auto_pick(cands)
    row = {**entry, "candidates": cands, "league_id": (pick or {}).get("id"),
           "matched_name": (pick or {}).get("name"), "status": "auto" if pick else ("review" if cands else "none"),
           "coverage": {}, "warnings": []}
    if not pick:
        return row
    for season in seasons:
        cov = coverage(client, pick["id"], season)
        row["coverage"][str(season)] = cov
        if not cov.get("found"):
            row["warnings"].append(f"{season}: not available on this plan")
            continue
        # A SEASON THAT HAS NOT KICKED OFF REPORTS EVERYTHING FALSE, and their documentation says so:
        # "a competition that hasn't started yet will have all the fields in FALSE, that's why you
        # have to call this endpoint at least once a week" (docs/82 §8). Reporting that as "no player
        # statistics" reads on the Competitions screen as "this league is thin" when it means "come
        # back in August", and the owner maps leagues off these warnings.
        if not _has_started(cov):
            row["warnings"].append(f"{season}: season has not started, so coverage reads empty until it does")
            continue
        if entry["role"] == FORECAST:
            if not cov.get("players_statistics"):
                row["warnings"].append(f"{season}: no player statistics -- player markets cannot run")
            if not cov.get("fixtures_statistics"):
                row["warnings"].append(f"{season}: no team statistics -- team markets cannot run")
        if not cov.get("fixtures_lineups"):
            row["warnings"].append(f"{season}: no lineups -- the start model and the confirmed eleven are blind")
    return row


def _has_started(cov: dict, today=None) -> bool:
    """Has this season begun? The coverage row carries `start`, so the two reasons a field reads
    false -- not tracked, and not started -- are told apart rather than guessed at. No start date
    means we cannot tell, and we assume it has, because that is the case that gets a real warning."""
    start = cov.get("start")
    if not start:
        return True
    today = today or datetime.now(timezone.utc).date()
    try:
        return datetime.strptime(str(start)[:10], "%Y-%m-%d").date() <= today
    except ValueError:
        return True


def supportable_role(row: dict, season: str | None = None) -> str:
    """The role the DATA supports, which may be lower than the one we asked for. A forecast league
    with no player statistics is a calendar competition whether we like it or not, and saying so
    here is better than publishing empty markets and calling it a quiet week."""
    if row.get("role") != FORECAST:
        return row.get("role", OFF)
    covs = row.get("coverage") or {}
    if season is not None:
        covs = {season: covs.get(season, {})}
    if not covs:
        return FORECAST
    if any(c.get("players_statistics") or c.get("fixtures_statistics") for c in covs.values()):
        return FORECAST
    return CALENDAR


# ------------------------------------------------------------------ what is confirmed, and where
#
# THE `leagues` COLLECTION IS THE SOURCE OF TRUTH, not a settings map. It already carries `enabled`
# and `backfill_seasons` and already drives the admin screen, so a parallel {id: role} setting
# would be a second place to look and a first place to drift. A confirmed competition is a league
# row whose `ext_id` is its API-Football id and whose `role` says what it is for.
def saved_map(db) -> dict:
    """{our league iid: api-football league id}, from the rows admin confirmed."""
    return {int(r["iid"]): int(r["ext_id"]) for r in
            db.leagues.find({"provider": PROVIDER_KEY, "ext_id": {"$ne": None}}, {"iid": 1, "ext_id": 1})
            if str(r.get("ext_id", "")).isdigit()}


def role_of(db, league_iid: int) -> str:
    """What this competition of ours is for. Unconfirmed is off, never forecast."""
    lg = db.leagues.find_one({"iid": int(league_iid)}, {"role": 1}) or {}
    return lg.get("role") or OFF


def is_forecast(db, league_iid: int) -> bool:
    """The gate. Only a forecast competition fits models, publishes cards, or stamps a club's
    league -- which is what stops the FA Cup moving every English club out of the Premier League."""
    return role_of(db, league_iid) == FORECAST


def forecast_leagues(db) -> list[int]:
    return [int(r["iid"]) for r in db.leagues.find({"role": FORECAST, "enabled": True}, {"iid": 1})]


def calendar_leagues(db) -> list[int]:
    return [int(r["iid"]) for r in db.leagues.find({"role": CALENDAR, "enabled": True}, {"iid": 1})]


def confirm(db, entry: dict, af_league: dict, seasons: list[int] | None = None) -> int:
    """Write a catalogue row into `leagues` as a real competition, with its seasons.

    Idempotent, and it never silently re-points an existing row at a different competition: the
    league is keyed on the API-Football id, so confirming the same id twice updates, and
    confirming a different id creates a new row that admin can see beside the old one.
    """
    from ingest import upsert_entity         # local: ingest imports settings, which imports us

    iid = upsert_entity(db, "leagues", str(af_league["id"]), {
        "name": af_league.get("name") or entry["name"], "provider": PROVIDER_KEY,
        "country": af_league.get("country") or entry["country"],
        "image_url": af_league.get("logo"), "catalog_key": entry["key"],
        "kind": entry["kind"], "tier": entry["tier"], "role": entry["role"],
        "af_type": af_league.get("type"),
    }, on_insert={"enabled": False, "backfill_seasons": []})     # a new competition starts OFF
    for year in sorted(seasons or af_league.get("seasons") or [], reverse=True):
        db.seasons.update_one({"league_iid": iid, "label": str(year)},
                              {"$setOnInsert": {"backfilled": False}}, upsert=True)
    db.leagues.update_one({"iid": iid}, {"$set": {"current_season": str(max(
        [int(y) for y in (seasons or af_league.get("seasons") or [0])]))}})
    return iid
