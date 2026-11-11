"""selftest_af_leagues.py -- the competition catalogue, resolver and roles. docs/81.

The thing being protected here is not the mapping, it is what happens when the mapping is WRONG
or the coverage is thin: a league quietly matched to a same-named league in another country, or a
forecast league with no player statistics that publishes nothing and looks like a quiet week.

    python3 tests/selftest_af_leagues.py
"""
import os, sys, base64
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
os.environ.setdefault("APP_ENCRYPTION_KEY", base64.b64encode(os.urandom(32)).decode())

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


def lg(lid, name, country, typ="League", seasons=None, cov=None):
    cov = cov or {}
    fx = {"events": cov.get("events", True), "lineups": cov.get("lineups", True),
          "statistics_fixtures": cov.get("stats", True), "statistics_players": cov.get("pstats", True)}
    return {"league": {"id": lid, "name": name, "type": typ, "logo": ""},
            "country": {"name": country},
            "seasons": [{"year": y, "current": y == max(seasons or [2024]),
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


# ---------------------------------------------------------------- the role gate
def t_roles_gate():
    db = mongomock.MongoClient()["af"]
    db.settings.insert_one({"key": "apifootball.roles", "value": {"39": "forecast", "45": "calendar"}})
    check("a forecast competition answers yes", L.is_forecast(db, 39))
    check("a calendar competition answers no -- this is what stops the FA Cup restamping every English club",
          not L.is_forecast(db, 45))
    check("a competition nobody confirmed answers no", not L.is_forecast(db, 999))


for fn in (t_catalogue, t_same_name_other_country, t_ambiguous_goes_to_review, t_no_match,
           t_thin_coverage_demotes, t_good_coverage_keeps_forecast, t_season_not_on_plan,
           t_missing_lineups_warns, t_roles_gate):
    print(fn.__name__)
    fn()

print()
print(f"{sum(OK)}/{len(OK)} passed")
sys.exit(0 if all(OK) else 1)
