"""selftest_af_leagues.py -- the competition catalogue, resolver and roles. docs/81.

The thing being protected here is not the mapping, it is what happens when the mapping is WRONG
or the coverage is thin: a league quietly matched to a same-named league in another country, or a
forecast league with no player statistics that publishes nothing and looks like a quiet week.

    python3 tests/selftest_af_leagues.py
"""
import os, sys, base64
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
os.environ.setdefault("APP_ENCRYPTION_KEY", base64.b64encode(os.urandom(32)).decode())

import datetime as dt

import httpx
import mongomock

import af_leagues as L
import apifootball as AF
import security

OK = []
def check(name, cond):
    OK.append(cond)
    print(("  ok     " if cond else "  FAIL   ") + name)


def client(leagues):
    db = mongomock.MongoClient()["af"]
    security.save_provider_key(db, AF.PROVIDER, "k" * 24)
    def h(req):
        if req.url.path == "/leagues" and req.url.params.get("id"):
            lid = int(req.url.params["id"])
            row = next((r for r in leagues if (r["league"]["id"]) == lid), None)
            return httpx.Response(200, json=env([row] if row else []))
        return httpx.Response(200, json=env(leagues))
    return AF.Client(db, httpx.Client(base_url=AF.BASE_URL, transport=httpx.MockTransport(h)), sleep=lambda s: None)


def env(response):
    return {"errors": [], "results": len(response), "paging": {"current": 1, "total": 1}, "response": response}


def lg(lid, name, country, typ="League", seasons=None, cov=None, start="2024-08-01"):
    cov = cov or {}
    fx = {"events": cov.get("events", True), "lineups": cov.get("lineups", True),
          "statistics_fixtures": cov.get("stats", True), "statistics_players": cov.get("pstats", True)}
    return {"league": {"id": lid, "name": name, "type": typ, "logo": ""},
            "country": {"name": country},
            "seasons": [{"year": y, "current": y == max(seasons or [2024]), "start": start,
                         "coverage": {"fixtures": fx, "standings": True, "players": True,
                                      "injuries": cov.get("injuries", True), "top_scorers": True}}
                        for y in (seasons or [2024])]}


# ---------------------------------------------------------------- the catalogue itself
def t_catalogue():
    tiers = {1: 0, 2: 0, 3: 0}
    for e in L.CATALOG:
        tiers[e["tier"]] += 1
    check(f"the owner's three tiers are all present ({tiers})", all(v > 0 for v in tiers.values()))
    check("every domestic division is a forecast competition",
          all(e["role"] == L.FORECAST for e in L.CATALOG if e["kind"] == "league"))
    check("no cup, continental or national-team competition is a forecast competition",
          all(e["role"] == L.CALENDAR for e in L.CATALOG if e["kind"] != "league"))
    check("the default role follows only from the kind",
          all(L.default_role(e["kind"]) == e["role"] for e in L.CATALOG))
    check("no league id is hard-coded anywhere in the catalogue",
          not any("id" in e for e in L.CATALOG))
    names = [e["key"] for e in L.CATALOG]
    check("every catalogue key is unique", len(names) == len(set(names)))


# ---------------------------------------------------------------- resolving
def t_same_name_other_country():
    """Serie A exists in Italy and in Brazil; Premiership in Scotland and elsewhere. This is the
    wrong map that nothing downstream can detect."""
    c = client([lg(135, "Serie A", "Italy"), lg(71, "Serie A", "Brazil")])
    ita = L.plan_row(c, L.BY_KEY["ita.seriea"], [2024])
    bra = L.plan_row(c, L.BY_KEY["bra.seriea"], [2024])
    check("Italy's Serie A resolves to the Italian one", ita["league_id"] == 135)
    check("Brazil's Serie A resolves to the Brazilian one", bra["league_id"] == 71)


def t_ambiguous_goes_to_review():
    c = client([lg(1, "Premier League", "England"), lg(2, "Premier League", "England")])
    row = L.plan_row(c, L.BY_KEY["eng.pl"], [2024])
    check("two equally good candidates are sent to review, not picked",
          row["status"] == "review" and row["league_id"] is None)
    check("...and both are offered so a human can choose", len(row["candidates"]) == 2)


def t_no_match():
    c = client([lg(39, "Premier League", "England")])
    row = L.plan_row(c, L.BY_KEY["ksa.proleague"], [2024])
    check("a competition the provider does not offer is 'none', not a wrong guess",
          row["league_id"] is None and row["status"] in ("none", "review"))


# ---------------------------------------------------------------- coverage decides the role
def t_thin_coverage_demotes():
    c = client([lg(307, "Pro League", "Saudi-Arabia", seasons=[2024], cov={"pstats": False, "stats": False})])
    row = L.plan_row(c, L.BY_KEY["ksa.proleague"], [2024])
    check("a forecast league with no statistics is warned about, loudly",
          any("player statistics" in w for w in row["warnings"]))
    check("...and the role the DATA supports is calendar, whatever we asked for",
          L.supportable_role(row) == L.CALENDAR)


def t_good_coverage_keeps_forecast():
    c = client([lg(39, "Premier League", "England", seasons=[2024, 2023, 2022])])
    row = L.plan_row(c, L.BY_KEY["eng.pl"], [2024, 2023, 2022])
    check("a well-covered division stays a forecast league", L.supportable_role(row) == L.FORECAST)
    check("no warnings on a league with everything", row["warnings"] == [])
    check("coverage is recorded per season, not once per league", len(row["coverage"]) == 3)


def t_season_not_on_plan():
    c = client([lg(39, "Premier League", "England", seasons=[2024])])
    row = L.plan_row(c, L.BY_KEY["eng.pl"], [2024, 2019])
    check("a season the plan cannot read is named in the warnings",
          any("2019" in w and "plan" in w for w in row["warnings"]))
    check("...and the seasons it CAN read are still fine", row["coverage"]["2024"]["found"] is True)


def t_missing_lineups_warns():
    c = client([lg(2, "UEFA Champions League", "World", typ="Cup", cov={"lineups": False})])
    row = L.plan_row(c, L.BY_KEY["uefa.ucl"], [2024])
    check("no lineups is called out even for a calendar competition (the start model needs them)",
          any("lineups" in w for w in row["warnings"]))
    check("a continental competition stays calendar regardless of its coverage",
          L.supportable_role(row) == L.CALENDAR)


# ---------------------------------------------------------------- the whole provider catalogue
def full_client(leagues):
    """A client whose /leagues answers with the complete list, as it does with no parameters."""
    db = mongomock.MongoClient()["af"]
    security.save_provider_key(db, AF.PROVIDER, "k" * 24)
    def h(req):
        return httpx.Response(200, json=env(leagues))
    return AF.Client(db, httpx.Client(base_url=AF.BASE_URL, transport=httpx.MockTransport(h)),
                     sleep=lambda s: None)


def t_sync_stores_the_whole_list():
    c = full_client([
        lg(39, "Premier League", "England", seasons=[2024, 2023]),
        lg(45, "FA Cup", "England", typ="Cup", seasons=[2024]),
        lg(2, "UEFA Champions League", "World", typ="Cup", seasons=[2024]),
        lg(999, "Fourth Division", "Nowhere", seasons=[2024], cov={"pstats": False, "stats": False}),
    ])
    res = L.sync_catalog(c)
    db = c.db
    check(f"every competition is stored in one call ({res['calls']} call)",
          res["competitions"] == 4 and res["calls"] == 1)
    check("the thirty-nine we have an opinion about are flagged, the rest are not",
          db[L.CATALOG_COLL].count_documents({"recommended": True}) == 3
          and (db[L.CATALOG_COLL].find_one({"_id": 999}) or {}).get("recommended") is False)
    pl = db[L.CATALOG_COLL].find_one({"_id": 39})
    check("a division is suggested as a forecast competition", pl["suggested_role"] == L.FORECAST)
    fa = db[L.CATALOG_COLL].find_one({"_id": 45})
    check("a cup is suggested as calendar: it mixes divisions (docs/81 §2)", fa["suggested_role"] == L.CALENDAR)
    ucl = db[L.CATALOG_COLL].find_one({"_id": 2})
    check("a World competition is calendar whatever its type says", ucl["suggested_role"] == L.CALENDAR)
    check("coverage is stored per season, so the screen can say what a competition carries",
          pl["has_player_stats"] is True and len(pl["seasons"]) == 2)
    check("...including a competition that carries none",
          db[L.CATALOG_COLL].find_one({"_id": 999})["has_player_stats"] is False)
    again = L.sync_catalog(c)
    check("a re-sync updates rather than duplicating", again["new"] == 0
          and db[L.CATALOG_COLL].count_documents({}) == 4)


def t_catalog_page_filters():
    c = full_client([lg(39, "Premier League", "England", seasons=[2024]),
                     lg(45, "FA Cup", "England", typ="Cup", seasons=[2024]),
                     lg(140, "La Liga", "Spain", seasons=[2024]),
                     lg(999, "Fourth Division", "Nowhere", seasons=[2024],
                        cov={"pstats": False, "stats": False})])
    L.sync_catalog(c)
    db = c.db
    check("a thousand competitions are paged, not dumped", L.catalog_page(db, per_page=2)["pages"] == 2)
    check("search matches the name", [r["name"] for r in L.catalog_page(db, q="liga")["rows"]] == ["La Liga"])
    check("...and the country", len(L.catalog_page(db, q="england")["rows"]) == 2)
    check("a country filter narrows it", len(L.catalog_page(db, country="Spain")["rows"]) == 1)
    check("a kind filter separates cups from divisions",
          len(L.catalog_page(db, kind="cup")["rows"]) == 1)
    check("'recommended' shows the ones we have an opinion about",
          len(L.catalog_page(db, only="recommended")["rows"]) == 3)
    check("'stats' shows only what could carry player cards",
          len(L.catalog_page(db, only="stats")["rows"]) == 3)
    first = L.catalog_page(db)["rows"][0]
    check("the recommended ones sort first, so a thousand rows still open on what matters",
          first["recommended"] is True)
    meta = L.catalog_meta(db)
    check("the filters are offered from what was actually synced",
          meta["total"] == 4 and "Spain" in meta["countries"] and meta["recommended"] == 3)


def t_switch_on_and_off():
    c = full_client([lg(39, "Premier League", "England", seasons=[2024, 2023, 2022]),
                     lg(45, "FA Cup", "England", typ="Cup", seasons=[2024])])
    L.sync_catalog(c)
    db = c.db
    before = c.calls_made
    res = L.switch(db, 39, True)
    check("switching one on costs no provider call: the sync already stored what it needs",
          c.calls_made == before)
    check("it becomes a real league row, on, with its suggested role",
          db.leagues.find_one({"iid": res["iid"]})["enabled"] is True and res["role"] == L.FORECAST)
    check("...and three seasons are created for the backfill picker",
          db.seasons.count_documents({"league_iid": res["iid"]}) == 3)
    page = L.catalog_page(db)
    row = next(r for r in page["rows"] if r["league_id"] == 39)
    check("the list shows it as on", row["on"] is True and row["iid"] == res["iid"])
    check("'on' and 'off' filter against that", len(L.catalog_page(db, only="on")["rows"]) == 1
          and len(L.catalog_page(db, only="off")["rows"]) == 1)
    L.switch(db, 39, False)
    check("switching it off leaves the row and its seasons, so turning it back on loses nothing",
          db.leagues.find_one({"iid": res["iid"]})["enabled"] is False
          and db.seasons.count_documents({"league_iid": res["iid"]}) == 3)
    L.switch(db, 45, True, role=L.FORECAST)
    check("a role can be overridden when switching on", db.leagues.find_one(
        {"ext_id": "45"})["role"] == L.FORECAST)
    try:
        L.switch(db, 12345, True)
        check("a competition not in the stored list is refused rather than guessed", False)
    except KeyError:
        check("a competition not in the stored list is refused rather than guessed", True)


# ---------------------------------------------------------------- the role gate
def t_unstarted_season_is_not_a_thin_league():
    """docs/82 section 8: a competition that has not kicked off reports every coverage field false.
    Calling that "no player statistics" reads on the mapping screen as "this league is thin" when it
    means "come back in August" -- and the owner maps leagues off these warnings."""
    future = (dt.date.today() + dt.timedelta(days=60)).isoformat()
    c = client([lg(39, "Premier League", "England", seasons=[2026],
                   cov={"pstats": False, "stats": False, "lineups": False}, start=future)])
    row = L.plan_row(c, L.BY_KEY["eng.pl"], [2026])
    check("an unstarted season says so, in those words",
          any("has not started" in w for w in row["warnings"]))
    check("...and does not claim the league lacks player statistics",
          not any("no player statistics" in w for w in row["warnings"]))
    check("...nor that its lineups are missing", not any("no lineups" in w for w in row["warnings"]))
    # the same emptiness on a season that IS under way is a real finding and still reported
    past = (dt.date.today() - dt.timedelta(days=60)).isoformat()
    c2 = client([lg(307, "Pro League", "Saudi-Arabia", seasons=[2025],
                    cov={"pstats": False, "stats": False}, start=past)])
    row2 = L.plan_row(c2, L.BY_KEY["ksa.proleague"], [2025])
    check("a season under way with no statistics is still called out",
          any("no player statistics" in w for w in row2["warnings"]))
    check("...and is still demoted to calendar", L.supportable_role(row2) == L.CALENDAR)


def t_confirm_writes_a_league():
    c = client([lg(39, "Premier League", "England", seasons=[2024, 2023, 2022])])
    db = c.db
    af = {"id": 39, "name": "Premier League", "type": "League", "logo": "x", "country": "England",
          "seasons": [2024, 2023, 2022]}
    iid = L.confirm(db, L.BY_KEY["eng.pl"], af)
    row = db.leagues.find_one({"iid": iid})
    check("confirming writes a real league row keyed on the API-Football id", row["ext_id"] == "39")
    check("it carries the role, kind and tier so the screen can show them",
          row["role"] == L.FORECAST and row["kind"] == "league" and row["tier"] == 1)
    check("a newly confirmed competition starts switched OFF, with nothing queued",
          row["enabled"] is False and row["backfill_seasons"] == [])
    check("its seasons are created so the existing backfill picker works",
          db.seasons.count_documents({"league_iid": iid}) == 3)
    check("current_season is the newest", row["current_season"] == "2024")
    again = L.confirm(db, L.BY_KEY["eng.pl"], af)
    check("confirming the same competition twice updates rather than duplicating",
          again == iid and db.leagues.count_documents({}) == 1)


def t_roles_gate():
    c = client([])
    db = c.db
    pl = L.confirm(db, L.BY_KEY["eng.pl"], {"id": 39, "name": "Premier League", "seasons": [2024]})
    fa = L.confirm(db, L.BY_KEY["eng.facup"], {"id": 45, "name": "FA Cup", "seasons": [2024]})
    check("a forecast competition answers yes", L.is_forecast(db, pl))
    check("a calendar competition answers no -- this is what stops the FA Cup restamping every English club",
          not L.is_forecast(db, fa))
    check("a competition nobody confirmed answers no", not L.is_forecast(db, 999))
    db.leagues.update_many({}, {"$set": {"enabled": True}})
    check("the forecast list holds the division only", L.forecast_leagues(db) == [pl])
    check("the calendar list holds the cup only", L.calendar_leagues(db) == [fa])
    check("saved_map pairs our id with theirs", L.saved_map(db) == {pl: 39, fa: 45})


for fn in (t_catalogue, t_same_name_other_country, t_ambiguous_goes_to_review, t_no_match,
           t_thin_coverage_demotes, t_good_coverage_keeps_forecast, t_season_not_on_plan,
           t_missing_lineups_warns, t_unstarted_season_is_not_a_thin_league,
           t_confirm_writes_a_league, t_sync_stores_the_whole_list,
           t_catalog_page_filters, t_switch_on_and_off, t_roles_gate):
    print(fn.__name__)
    fn()

print()
print(f"{sum(OK)}/{len(OK)} passed")
sys.exit(0 if all(OK) else 1)
