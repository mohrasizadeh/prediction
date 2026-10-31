"""selftest_combo.py -- the combined chance of several lines in one match, "build one for me", and my combos (docs/28).

Proves: lines multiply after lineups; before lineups the tested correction (1.11, 1.19, 1.25) applies; a player has
to play first (chance = p x chance to play); two lines on one player are not multiplied blindly; the rules (one
match, one line per stat and player, at most N lines) answer clearly; the three suggestion modes behave and never
suggest a player we are unsure will play; saved combos are private, limited by the plan, show today's estimate
before the match and what happened after it; no user-facing sentence contains a banned word.
"""
import datetime as dt
import testkit as K
from testkit import check, db, setting
import combo as CB, textguard
from fastapi.testclient import TestClient

c = TestClient(K.srv.app)
c.__enter__()
for k in ("security.rate_limit_read_per_minute", "security.rate_limit_write_per_minute", "security.rate_limit_auth_per_minute"):
    setting(k, 1000)
now = dt.datetime.now(dt.timezone.utc)
db.teams.insert_many([{"iid": 1, "id": "t1", "ext_id": 1, "name": "Como"}, {"iid": 2, "id": "t2", "ext_id": 2, "name": "Venezia"}])
db.players.insert_many([{"iid": i, "id": f"p{i}", "ext_id": i, "name": n, "team_iid": 1 if i < 5 else 2} for i, n in ((1, "A Striker"), (2, "B Winger"), (3, "C Mid"), (4, "D Back"), (5, "E Forward"), (6, "F Mid"))])
db.matches.insert_many([{"iid": 10, "id": "m10", "ext_id": 10, "home_iid": 1, "away_iid": 2, "kickoff": now + dt.timedelta(days=1), "status": "scheduled", "league_iid": 1},
                        {"iid": 11, "id": "m11", "ext_id": 11, "home_iid": 2, "away_iid": 1, "kickoff": now + dt.timedelta(days=8), "status": "scheduled", "league_iid": 1}])
_n = [0]


def F(match, scope, team, player, stat, thr, p, play=1.0, state="lineup", badge=None, tier="Solid", edge=0.1, lo=None, hi=None):
    _n[0] += 1
    d = {"id": f"f{_n[0]}", "fkey": f"{match}:{scope}:{team}:{player or 0}:{stat}:{thr:g}", "match_iid": match, "league_iid": 1, "scope": scope,
         "team_iid": team, "opp_iid": 3 - team, "player_iid": player, "stat": stat, "thr": thr, "market": f"{int(thr + 0.5)}+ {stat}", "p": p,
         "lo": lo if lo is not None else p - 0.07, "hi": hi if hi is not None else min(p + 0.07, 0.99), "p_play": play, "state": state,
         "lineup_badge": badge if badge is not None else (None if scope == "team" else ("confirmed" if state == "lineup" else "likely")),
         "tier": tier, "edge": edge, "kickoff": now + dt.timedelta(days=1), "is_current": True, "hidden": False}
    db.forecasts.insert_one(dict(d))
    return d


def est(*docs, key="id"):
    return CB.estimate(db, **{"ids" if key == "id" else "fkeys": [d[key] for d in docs]})


print("[after lineups: lines multiply]")
a = F(10, "player", 1, 1, "shots", 1.5, 0.80); b = F(10, "player", 1, 2, "sot", 0.5, 0.70); t = F(10, "team", 2, None, "corners", 4.5, 0.60)
e = est(a, b, t)
check(abs(e["combined"] - 0.80 * 0.70 * 0.60) < 1e-3 and e["state"] == "lineup" and e["factor"] == 1.0, f"3 lines: {e['combined']} = .80 x .70 x .60, no correction")
check(e["range"]["lo"] <= e["combined"] <= e["range"]["hi"] and e["weakest"] == t["id"], "range brackets the number; the weakest line is named")
check(e["plain"] == "About 1 in 3" and CB.plain(0.62) == "About 6 in 10" and CB.plain(0.2) == "About 1 in 5" and CB.plain(0.96) == "Very likely", "plain words for the number")
check(est(a, b, t, key="fkey")["combined"] == e["combined"], "stable keys give the same answer as ids")

print("[before lineups: the tested correction]")
p1 = F(10, "player", 1, 3, "shots", 0.5, 0.80, play=0.90, state="pre", badge="likely")
p2 = F(10, "player", 2, 5, "shots", 0.5, 0.75, play=0.90, state="pre", badge="likely")
p3 = F(10, "team", 1, None, "shots", 11.5, 0.70, state="pre")
p4 = F(10, "team", 2, None, "corners", 5.5, 0.65, state="pre")
raw2 = (0.80 * 0.90) * (0.75 * 0.90)
check(abs(est(p1, p2)["combined"] - raw2 * 1.11) < 1e-3 and est(p1, p2)["state"] == "pre", "2 lines: product x 1.11, and a player has to play first (p x chance to play)")
check(abs(est(p1, p2, p3)["combined"] - raw2 * 0.70 * 1.19) < 1e-3, "3 lines: x 1.19")
e4 = est(p1, p2, p3, p4)
check(abs(e4["combined"] - raw2 * 0.70 * 0.65 * 1.25) < 1e-3, "4 lines: x 1.25")
check(any("2 players not confirmed" in n for n in e4["notes"]), "the note says how many players are not confirmed")
check(est(p3)["factor"] == 1.0, "one line: no correction")

print("[two lines on one player]")
s1 = F(10, "player", 1, 4, "shots", 0.5, 0.90); s2 = F(10, "player", 1, 4, "sot", 0.5, 0.70)
es = est(s1, s2)
check(abs(es["combined"] - 0.70 * 0.90 ** 0.38) < 1e-3 and es["combined"] > 0.70 * 0.90, "joint = harder line x easier line^0.38, above the plain product")
check(any("usually happen together" in n for n in es["notes"]), "the screen is told why")

print("[the rules]")
def code(fn):
    try:
        fn(); return None
    except CB.ComboError as ex:
        return ex.code
other_match = F(11, "player", 2, 6, "shots", 0.5, 0.7)
same = F(10, "player", 1, 1, "shots", 2.5, 0.55)
check(code(lambda: est(a, other_match)) == "MIXED_MATCHES", "two matches: refused")
check(code(lambda: est(a, same)) == "SAME_STAT", "two lines on one stat for one player: refused (keep one)")
check(code(lambda: CB.estimate(db, ids=["nope"])) == "NOT_FOUND" and code(lambda: CB.estimate(db, ids=[])) == "EMPTY", "unknown line and empty combo")
many = [F(10, "player", 1 if i % 2 else 2, 20 + i, "shots", 0.5, 0.7) for i in range(7)]
check(code(lambda: est(*many)) == "TOO_MANY", "more than combo.max_lines: refused")
long5 = [a, b, t, p3, F(10, "player", 2, 6, "tackles", 1.5, 0.6)]
e5 = est(*long5)
check(any("tested combos of up to 4" in n for n in e5["notes"]), "5 players or teams: the screen is told it is beyond what we tested")

print("[build one for me]")
db.forecasts.delete_many({"match_iid": 10})
S_ = [F(10, "player", 1, 1, "shots", 0.5, 0.93, edge=0.02), F(10, "team", 1, None, "shots", 9.5, 0.88, edge=0.05),
      F(10, "player", 2, 5, "sot", 0.5, 0.84, edge=0.04), F(10, "team", 2, None, "corners", 3.5, 0.70, edge=0.15),
      F(10, "player", 1, 2, "shots", 1.5, 0.72, edge=0.20), F(10, "player", 2, 6, "shots", 0.5, 0.60, edge=0.25),
      F(10, "player", 1, 3, "shots", 2.5, 0.97, play=0.55, state="pre", badge="unsure", edge=0.5),
      F(10, "player", 2, 6, "tackles", 1.5, 0.66, edge=0.10)]
sf, bl, bo = CB.suggest(db, 10, "safer"), CB.suggest(db, 10, "balanced"), CB.suggest(db, 10, "bolder")
check(len(sf["lines"]) == 2 and all(l["chance"] >= 0.80 for l in sf["lines"]), "safer: 2 lines, each 80% or more")
check(len(bl["lines"]) == 3 and all(l["chance"] >= 0.65 for l in bl["lines"]), "balanced: 3 lines, each 65% or more")
check(len(bo["lines"]) == 4 and all(l["chance"] >= 0.55 for l in bo["lines"]), "bolder: 4 lines, each 55% or more")
check(sf["combined"] > bl["combined"] > bo["combined"], f"safer {sf['combined']} > balanced {bl['combined']} > bolder {bo['combined']}")
check(all(l["badge"] != "unsure" for r in (sf, bl, bo) for l in r["lines"]), "never a player we are unsure will play")
check(all(len({((l["player"] or l["team"])["name"] + str(l["scope"])) for l in r["lines"]}) == len(r["lines"]) for r in (sf, bl, bo)), "one line per player or team")
check(CB.suggest(db, 999, "safer")["lines"] == [] and code(lambda: CB.suggest(db, 10, "wild")) == "BAD_MODE", "no lines: says so; bad mode: refused")

print("[routes]")
r = c.post("/api/combo/estimate", json={"ids": [S_[0]["id"], S_[2]["id"]]})
check(r.status_code == 200 and abs(r.json()["combined"] - 0.93 * 0.84) < 1e-3 and r.headers["cache-control"] == "no-store", "POST /api/combo/estimate")
check(c.post("/api/combo/estimate", json={"ids": [S_[0]["id"], other_match["id"]]}).json()["error"]["code"] == "MIXED_MATCHES", "route: two matches -> MIXED_MATCHES (409)")
check(c.post("/api/combo/estimate", json={"ids": ["zz"]}).status_code == 404, "route: unknown line -> 404")
check(c.get("/api/matches/m10/combo-suggest?mode=safer").json()["mode"] == "safer" and c.get("/api/matches/m10/combo-suggest?mode=x").status_code == 400, "GET /api/matches/{id}/combo-suggest")
check(c.get("/api/me/combos").status_code == 401, "my combos: signed out is 401")


def user(email):
    cl = TestClient(K.srv.app)
    cl.post("/api/auth/register", json={"email": email, "password": "long-pass-word-1"})
    cl.post("/api/auth/verify-email", json={"token": K.token_from(email, "")})
    check(cl.post("/api/auth/login", json={"email": email, "password": "long-pass-word-1"}).status_code == 200, f"{email} signs in")
    return cl


setting("email.enabled", True); setting("email.from_address", "hello@mail.example.com")
import security; security.save_provider_key(db, "resend", "re_abcdefghijk12345")
ua, ub = user("combo-a@example.com"), user("combo-b@example.com")
r = ua.put("/api/me/combos", json={"ids": [S_[0]["id"], S_[2]["id"], S_[3]["id"]]})
check(r.status_code == 201 and r.json()["estimate"]["combined"] > 0, "A saves a combo")
lst = ua.get("/api/me/combos").json()["items"]
check(len(lst) == 1 and lst[0]["label"] == "Como v Venezia" and lst[0]["status"] == "upcoming" and lst[0]["now"]["combined"] == r.json()["estimate"]["combined"], "list: label, upcoming, today's estimate")
check(ub.get("/api/me/combos").json()["items"] == [] and ub.request("DELETE", f"/api/me/combos/{lst[0]['id']}").json()["removed"] == 0, "private: B sees nothing and cannot delete A's combo")
check(ua.put("/api/me/combos", json={"ids": [S_[0]["id"], other_match["id"]]}).status_code == 409, "saving lines from two matches: 409")
rk = ua.put("/api/me/combos", json={"fkeys": [S_[0]["fkey"], S_[2]["fkey"]]})
check(rk.status_code == 201 and rk.json()["estimate"]["label"] == "Como v Venezia" and rk.json()["estimate"]["match_id"] == "m10", "save by stable keys (what the screens send); the estimate names the match")
check([x for x in ua.get("/api/me/combos").json()["items"] if x["id"] == rk.json()["id"]][0]["match_id"] == "m10", "a saved combo links back to its match")
ua.request("DELETE", f"/api/me/combos/{rk.json()['id']}")
check(ua.put("/api/me/combos", json={}).status_code == 400, "saving nothing: 400")
setting("features.billing", True)
db.plans.update_one({"key": "free"}, {"$set": {"entitlements.saved_max": 1}})
check(ua.put("/api/me/combos", json={"ids": [S_[1]["id"], S_[4]["id"]]}).status_code == 409, "over the plan limit: 409 LIMIT_REACHED")
setting("features.billing", False)

print("[after the match]")
db.matches.update_one({"iid": 10}, {"$set": {"kickoff": now - dt.timedelta(hours=5), "status": "final"}})
db.combos.update_one({"id": lst[0]["id"]}, {"$set": {"kickoff": now - dt.timedelta(hours=5)}})
w = ua.get("/api/me/combos").json()["items"][0]
check(w["status"] == "waiting" and w["result"]["of"] == 3 and not w["result"]["all"], "no results yet: waiting")
fk = [l["fkey"] for l in w["lines"]]
for i, k in enumerate(fk):
    db.forecast_outcomes.insert_one({"fkey": k, "forecast_id": f"o{i}", "actual": 3.0 if i < 2 else 1.0, "reached": i < 2, "player_played": True})
w = ua.get("/api/me/combos").json()["items"][0]
check(w["status"] == "settled" and w["result"] == {"reached": 2, "of": 3, "all": False} and w["lines"][0]["reached"] is True and w["lines"][2]["actual"] == 1.0, "settled: 2 of 3 reached, with what each player or team had")
check(ua.request("DELETE", f"/api/me/combos/{lst[0]['id']}").json()["removed"] == 1, "A deletes the combo")

print("[wording]")
from itertools import chain
texts = list(chain.from_iterable(r_["notes"] for r_ in (e, e4, es, e5))) + [CB.plain(x) for x in (0.1, 0.4, 0.6, 0.97)] + [CB.ComboError("x", m).message for m in
        ("Add at least one line.", "A combo holds lines from one match.", "Keep one line per stat for each player or team.", "One of those lines is no longer available.")]
check(not textguard.find(texts), "no sentence a user can see contains a banned word")
print("\nALL COMBO CHECKS PASSED")
