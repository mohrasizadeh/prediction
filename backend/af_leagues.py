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

import re
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


# ==================================================================
# The whole provider catalogue, held locally
#
# The curated CATALOG above resolves thirty-nine competitions by name and asks for each to be
# confirmed. The owner wants the other thousand too: every competition API-Football carries, listed,
# with a switch. That is also what the provider recommends -- "It is recommended to save this
# information on your side so that you don't have to call the endpoint leagues again. Ideally, this
# data should be updated once a week" (docs/82 §6) -- so the list is SYNCED, not fetched per view.
#
# One call gets all of it, with each competition's seasons and the coverage of each season, so the
# screen can say what a competition actually carries before it is switched on. The thirty-nine stay
# as a recommendation flag on the rows they match, because knowing which of a thousand competitions
# matter is the part a list cannot tell you.
# ==================================================================
CATALOG_COLL = "af_catalog"


def _suggested_role(af_type: str, country: str) -> str:
    """The role a competition gets before anybody chooses.

    API-Football's own `type` is only League or Cup. A Cup mixes divisions and a competition whose
    country is "World" is continental or international, and docs/81 §2 is why neither can be a
    forecast competition: the engine fits one frame per competition, and pooling clubs of different
    standard — or national teams with no club history — biases it.
    """
    if str(country or "").strip().lower() == "world":
        return CALENDAR
    return FORECAST if str(af_type or "").strip().lower() == "league" else CALENDAR


def _kind(af_type: str, country: str) -> str:
    if str(country or "").strip().lower() == "world":
        return "continental"                     # or international; the screen does not need to split it
    return "league" if str(af_type or "").strip().lower() == "league" else "cup"


def sync_catalog(client, max_pages: int = 20) -> dict:
    """Fetch every competition the provider carries and store it. One call, in practice.

    Idempotent: a competition already stored is updated, and `enabled_iid` — the link to a `leagues`
    row, if the owner has switched it on — is preserved, because that is ours and not theirs.
    """
    from datetime import timedelta
    rows = client.fetch_all("/leagues", {},
                            ttl=timedelta(days=float(S.get(client.db, "cache.ttl.reference_days"))),
                            purpose="catalog_sync", max_pages=max_pages)
    db = client.db
    recommended = {}
    for e in CATALOG:                            # which of the thousand we have an opinion about
        recommended.setdefault(_norm(e["name"]) + "|" + _norm(e["country"]), e)
    seen, n_new = [], 0
    for r in rows:
        lg, ctry = r.get("league") or {}, r.get("country") or {}
        lid = lg.get("id")
        if lid is None:
            continue
        lid = int(lid)
        seasons = []
        for s in (r.get("seasons") or []):
            cov = s.get("coverage") or {}
            fx = cov.get("fixtures") or {}
            seasons.append({
                "year": s.get("year"), "start": s.get("start"), "end": s.get("end"),
                "current": bool(s.get("current")),
                "events": bool(fx.get("events")), "lineups": bool(fx.get("lineups")),
                "team_stats": bool(fx.get("statistics_fixtures")),
                "player_stats": bool(fx.get("statistics_players")),
                "standings": bool(cov.get("standings")), "injuries": bool(cov.get("injuries")),
            })
        seasons.sort(key=lambda s: -(s["year"] or 0))
        rec = recommended.get(_norm(lg.get("name")) + "|" + _norm(ctry.get("name")))
        doc = {
            "_id": lid, "name": lg.get("name"), "af_type": lg.get("type"), "logo": lg.get("logo"),
            "country": ctry.get("name"), "country_code": ctry.get("code"), "flag": ctry.get("flag"),
            "seasons": seasons,
            "years": [s["year"] for s in seasons if s["year"]],
            "kind": _kind(lg.get("type"), ctry.get("name")),
            "suggested_role": _suggested_role(lg.get("type"), ctry.get("name")),
            # does any season carry what a forecast competition needs? the screen sorts on this,
            # because "has player statistics somewhere" is the question that decides whether a
            # competition can carry cards at all (docs/81 §2)
            "has_player_stats": any(s["player_stats"] for s in seasons),
            "has_team_stats": any(s["team_stats"] for s in seasons),
            "has_lineups": any(s["lineups"] for s in seasons),
            "recommended": bool(rec), "catalog_key": (rec or {}).get("key"),
            "tier": (rec or {}).get("tier"),
            "synced_at": datetime.now(timezone.utc),
        }
        before = db[CATALOG_COLL].find_one({"_id": lid}, {"_id": 1})
        if not before:
            n_new += 1
        db[CATALOG_COLL].update_one({"_id": lid}, {"$set": doc}, upsert=True)
        seen.append(lid)
    return {"competitions": len(seen), "new": n_new, "calls": client.calls_made,
            "recommended": db[CATALOG_COLL].count_documents({"recommended": True})}


def catalog_page(db, q: str = "", country: str = "", kind: str = "", only: str = "",
                 page: int = 1, per_page: int = 50) -> dict:
    """One page of the stored catalogue, with the owner's on/off state joined on.

    A thousand competitions is too many to scroll, so the screen gets search, a country filter, a
    kind filter and `only`: recommended, on, off, or those that carry player statistics.
    """
    sel: dict = {}
    if q:
        sel["$or"] = [{"name": {"$regex": re.escape(q), "$options": "i"}},
                      {"country": {"$regex": re.escape(q), "$options": "i"}}]
    if country:
        sel["country"] = country
    if kind:
        sel["kind"] = kind
    if only == "recommended":
        sel["recommended"] = True
    elif only == "stats":
        sel["has_player_stats"] = True

    # which of them the owner has switched on, by API-Football id
    mine = {}
    for lg in db.leagues.find({"provider": PROVIDER_KEY}, {"_id": 0, "iid": 1, "ext_id": 1,
                                                           "enabled": 1, "role": 1, "backfill_seasons": 1}):
        if str(lg.get("ext_id", "")).isdigit():
            mine[int(lg["ext_id"])] = lg
    if only in ("on", "off"):
        ids = [i for i, l in mine.items() if bool(l.get("enabled")) == (only == "on")]
        if only == "on":
            sel["_id"] = {"$in": ids}
        else:
            sel["_id"] = {"$nin": [i for i, l in mine.items() if l.get("enabled")]}

    total = db[CATALOG_COLL].count_documents(sel)
    page = max(1, int(page))
    cur = (db[CATALOG_COLL].find(sel)
           .sort([("recommended", -1), ("tier", 1), ("has_player_stats", -1), ("name", 1)])
           .skip((page - 1) * per_page).limit(per_page))
    out = []
    for c in cur:
        m = mine.get(c["_id"]) or {}
        out.append({
            "league_id": c["_id"], "name": c.get("name"), "country": c.get("country"),
            "logo": c.get("logo"), "flag": c.get("flag"), "af_type": c.get("af_type"),
            "kind": c.get("kind"), "suggested_role": c.get("suggested_role"),
            "years": (c.get("years") or [])[:6],
            "has_player_stats": bool(c.get("has_player_stats")),
            "has_team_stats": bool(c.get("has_team_stats")),
            "has_lineups": bool(c.get("has_lineups")),
            "recommended": bool(c.get("recommended")), "tier": c.get("tier"),
            "iid": m.get("iid"), "on": bool(m.get("enabled")),
            "role": m.get("role") or c.get("suggested_role"),
            "backfill_seasons": m.get("backfill_seasons") or [],
        })
    return {"rows": out, "total": total, "page": page, "per_page": per_page,
            "pages": max(1, -(-total // per_page))}


def catalog_meta(db) -> dict:
    """What the filters offer, and when the list was last synced."""
    one = db[CATALOG_COLL].find_one({}, {"synced_at": 1}, sort=[("synced_at", -1)])
    return {"countries": sorted(c for c in db[CATALOG_COLL].distinct("country") if c),
            "kinds": sorted(k for k in db[CATALOG_COLL].distinct("kind") if k),
            "total": db[CATALOG_COLL].count_documents({}),
            "with_player_stats": db[CATALOG_COLL].count_documents({"has_player_stats": True}),
            "recommended": db[CATALOG_COLL].count_documents({"recommended": True}),
            "synced_at": (one or {}).get("synced_at")}


def switch(db, league_id: int, on: bool, seasons: list[int] | None = None, role: str | None = None) -> dict:
    """Turn a competition on or off.

    Turning one ON for the first time creates its `leagues` row from what the sync already stored,
    so no provider call is needed: the catalogue has the name, the seasons and the coverage.
    """
    c = db[CATALOG_COLL].find_one({"_id": int(league_id)})
    if not c:
        raise KeyError(f"competition {league_id} is not in the stored catalogue -- sync it first")
    entry = {"key": c.get("catalog_key") or f"af.{league_id}", "name": c.get("name"),
             "country": c.get("country"), "kind": c.get("kind"), "tier": c.get("tier") or 3,
             "role": role or c.get("suggested_role")}
    af = {"id": int(league_id), "name": c.get("name"), "type": c.get("af_type"),
          "logo": c.get("logo"), "country": c.get("country"), "seasons": c.get("years") or []}
    # EVERY season the catalogue knows, not three.
    #
    # `[:3]` was here, so a competition arrived with three season rows and the drawer could only
    # ever offer three -- for a league API-Football carries fifteen of. The number was never a
    # decision about the provider; it was a default for how many to QUEUE, applied to the wrong
    # thing. So: a row for every season, and only the most recent `backfill_default_seasons` ticked.
    years = sorted(c.get("years") or [], reverse=True)
    iid = confirm(db, entry, af, seasons or years)
    if seasons is None and years:
        n = max(1, int(S.get(db, "apifootball.backfill_default_seasons") or 3))
        db.leagues.update_one({"iid": iid}, {"$set": {"backfill_seasons": [str(y) for y in years[:n]]}})
        db.seasons.update_many({"league_iid": iid, "label": {"$in": [str(y) for y in years[:n]]}},
                               {"$set": {"queued": True}})
    db.leagues.update_one({"iid": iid}, {"$set": {"enabled": bool(on)}})
    db[CATALOG_COLL].update_one({"_id": int(league_id)}, {"$set": {"enabled_iid": iid}})
    return {"iid": iid, "league_id": int(league_id), "on": bool(on), "role": entry["role"]}
