"""selftest_routes.py -- the public data routes (routes_data.py) and the user's own data (routes_me.py) over HTTP.

Builds a simulated league through the fake PitchAPI, runs the engine, then calls every route.
Proves: every doc-06 data route answers; unknown ids are 404; bad input is 400; public answers are cacheable;
signed-out requests to /api/me are 401; user A cannot see user B's rows; plan limits give 409 LIMIT_REACHED;
the matchup tab is locked on the free plan.
"""
import datetime as dt
import testkit as K
from testkit import check, db, setting, token_from
import httpx
import engine_bridge as B, ingest as I, settings_store as S, security
from cached_fetch import PitchClient
from fake_pitchapi import PLAYER_KEYS, TEAM_KEYS, FakePitch
from simulate import simulate_league
from fastapi.testclient import TestClient

c = TestClient(K.srv.app)
c.__enter__()                                    # runs startup: indexes, plans, first owner

# ---------------------------------------------------------------- data
security.save_provider_key(db, "pitchapi", "pk_test_zzzz")
S.put(db, "ingest.rps", 1000); S.put(db, "provider.pitchapi.team_keys", TEAM_KEYS); S.put(db, "provider.pitchapi.player_keys", PLAYER_KEYS)
S.put(db, "provider.position_map", {"0": "GK", "1": "DEF", "2": "MID", "3": "FWD"})
matches, tg, pg, _ = simulate_league(n_teams=10, seed=5)
n_final = int(matches["round"].max()) + 1 - 2
fake = FakePitch(matches, tg, pg, n_final)
pc = PitchClient(db, http=httpx.Client(base_url="https://api.pitchapi.dev", transport=fake.transport()), sleep=lambda s: None)
I.sync_leagues(pc); lg = db.leagues.find_one({})
db.leagues.update_one({"iid": lg["iid"]}, {"$set": {"enabled": True, "country": "England"}})
I.sync_league_matches(pc, lg, "2025/2026", "all"); I.process_queue(pc)
I.assign_rounds(db, lg["iid"]); I.update_coverage(db, lg["iid"])
now = fake.kick(n_final) - dt.timedelta(hours=2)
I.lineup_watch(pc, now=now); B.run_league(db, lg["iid"], now=now)
for k in ("security.rate_limit_read_per_minute", "security.rate_limit_write_per_minute", "security.rate_limit_auth_per_minute"):
    setting(k, 1000)

team = db.teams.find_one({}); team2 = db.teams.find_one({"iid": {"$ne": team["iid"]}})
player = db.players.find_one({"team_iid": team["iid"]})
match = db.matches.find_one({"status": "final"})
fc = db.forecasts.find_one({"is_current": True, "hidden": {"$ne": True}})
check(team and player and match and fc, "simulated league, players, matches and forecasts are in place")

print("[public data routes]")
r = c.get("/api/leagues")
check(r.status_code == 200 and r.json()["countries"][0]["country"] == "England" and "iid" not in r.json()["countries"][0]["leagues"][0], "leagues grouped by country, no internal ids")
check("public" in r.headers["cache-control"], "public answers are cacheable")
check(c.get("/api/leagues?q=zzzz").json()["countries"] == [], "league search filters")
L = f"/api/leagues/{lg['id']}"
check(c.get(L).status_code == 200 and "next" in c.get(L).json(), "league page")
check(isinstance(c.get(L + "/fixtures?status=final").json(), list), "league fixtures (final)")
check(c.get(L + "/fixtures?status=bogus").status_code == 422, "league fixtures: bad status refused")
check(isinstance(c.get(L + "/leaderboard?stat=shots").json(), list), "leaderboard")
check(c.get(L + "/leaderboard?stat=sh%3Bots").status_code == 400, "leaderboard: odd stat name refused")
check(c.get(L + "/referees").status_code == 200, "referee table")
check(c.get("/api/leagues/nope").status_code == 404, "unknown league: 404")
r = c.get(f"/api/matches/{match['id']}")
check(r.status_code == 200 and r.json()["match"]["iid"] == match["iid"] and "h2h" in r.json(), "match page")
check(c.get("/api/matches/nope").status_code == 404, "unknown match: 404")
check(c.get(f"/api/h2h?a={team['id']}&b={team2['id']}").json().keys() >= {"a_wins", "b_wins", "draws"}, "head to head")
check(c.get(f"/api/teams/{team['id']}").json()["team"]["name"] == team["name"], "team page")
r = c.get(f"/api/teams/{team['id']}/squad-grid?stat=shots&last=10").json()
check(r["rows"] and r["last"] <= 10, "squad grid")
check(c.get(f"/api/teams/{team['id']}/squad-grid?venue=moon").status_code == 400, "squad grid: bad venue refused")
check(c.get(f"/api/teams/{team['id']}/totals?stat=shots").status_code == 200, "team totals")
check(c.get(f"/api/teams/{team['id']}/against?stat=shots").status_code == 200, "against by position")
check(c.get(f"/api/players/{player['id']}").json()["player"]["name"] == player["name"], "player page")
check(c.get(f"/api/players/{player['id']}/history?last=5").status_code == 200, "player history")
check(c.get("/api/players/nope").status_code == 404, "unknown player: 404")
check(c.get("/api/track-record").json().get("ready") is False, "track record not ready yet: says so")
check("data_updated_at" in c.get("/api/public/status").json(), "status answers")
db.content_pages.update_one({"slug": "about"}, {"$set": {"title": "About", "body_md": "Hi", "published": True}}, upsert=True)   # seeded at start (docs/36 C2)
db.content_pages.insert_one({"slug": "draft", "title": "Draft", "body_md": "x", "published": False})
check(c.get("/api/public/pages/about").json()["title"] == "About" and c.get("/api/public/pages/draft").status_code == 404, "published page shows, draft does not")

print("[plan gates on data]")
setting("features.billing", True)
r = c.get(f"/api/matches/{match['id']}").json()
check(r["matchup_locked"] is True and r["styles"] == {}, "free plan: matchup tab locked")
r = c.get(f"/api/teams/{team['id']}/squad-grid?stat=shots&last=10").json()
check(r["capped"] and r["last"] == 5, "free plan: grid capped at the plan's games")
setting("features.billing", False)

print("[user data routes]")
check(c.get("/api/me/follows").status_code == 401 and c.put("/api/me/follows", json={"kind": "team", "ref_id": team["id"]}).status_code == 401, "signed out: 401")


def user(email):
    cl = TestClient(K.srv.app)
    cl.post("/api/auth/register", json={"email": email, "password": "long-pass-word-1"})
    cl.post("/api/auth/verify-email", json={"token": token_from(email, "")})
    r = cl.post("/api/auth/login", json={"email": email, "password": "long-pass-word-1"})
    check(r.status_code == 200, f"{email} signs in")
    return cl


setting("email.enabled", True); setting("email.from_address", "hello@mail.example.com"); security.save_provider_key(db, "resend", "re_abcdefghijk12345")
a, b = user("a@example.com"), user("b@example.com")
check(a.put("/api/me/follows", json={"kind": "team", "ref_id": team["id"]}).status_code == 201, "A follows a team")
check(a.put("/api/me/follows", json={"kind": "team", "ref_id": team["id"]}).json().get("already"), "following twice is harmless")
check(a.put("/api/me/follows", json={"kind": "player", "ref_id": player["id"]}).status_code == 201, "A follows a player")
check(a.put("/api/me/follows", json={"kind": "team", "ref_id": "nope"}).status_code == 404, "unknown id: 404")
check(a.put("/api/me/follows", json={"kind": "coach", "ref_id": team["id"]}).status_code == 422, "unknown kind refused")
items = a.get("/api/me/follows").json()["items"]
check(len(items) == 2 and {i["kind"] for i in items} == {"team", "player"} and "no-store" in a.get("/api/me/follows").headers["cache-control"], "A sees two follows, private")
check(b.get("/api/me/follows").json()["items"] == [], "B cannot see A's follows")
check("matches" in a.get("/api/me/following-feed").json(), "following feed answers")
check(a.put("/api/me/saved", json={"fkey": fc["fkey"]}).status_code == 201, "A saves a forecast")
check(a.put("/api/me/saved", json={"fkey": "1:x:y:0:shots:1.5"}).status_code == 404, "unknown forecast: 404")
check(a.get("/api/me/saved").json()["items"][0]["forecast"]["fkey"] == fc["fkey"] and b.get("/api/me/saved").json()["items"] == [], "saved list is A's alone")
check(a.put(f"/api/me/notes/{player['id']}", json={"text": "Takes corners."}).json()["ok"], "A writes a note")
check(a.get(f"/api/me/notes/{player['id']}").json()["text"] == "Takes corners." and b.get(f"/api/me/notes/{player['id']}").json()["text"] is None, "notes are private to A")
check(a.put(f"/api/me/notes/{player['id']}", json={"text": "x" * 2001}).status_code == 422, "note over 2,000 characters refused")
check(b.request("DELETE", f"/api/me/notes/{player['id']}").json()["removed"] == 0 and a.get(f"/api/me/notes/{player['id']}").json()["text"], "B cannot delete A's note")

print("[limits]")
setting("features.billing", True)
db.plans.update_one({"key": "free"}, {"$set": {"entitlements.follows_max": 2, "entitlements.saved_max": 1}})
r = a.put("/api/me/follows", json={"kind": "team", "ref_id": team2["id"]})
check(r.status_code == 409 and r.json()["error"]["code"] == "LIMIT_REACHED", "follow over the plan limit: 409 LIMIT_REACHED")
fc2 = db.forecasts.find_one({"is_current": True, "fkey": {"$ne": fc["fkey"]}})
check(a.put("/api/me/saved", json={"fkey": fc2["fkey"]}).status_code == 409, "save over the plan limit: 409")
check(a.request("DELETE", "/api/me/follows", json={"kind": "team", "ref_id": team["id"]}).json()["removed"] == 1, "unfollow")
check(a.put("/api/me/follows", json={"kind": "team", "ref_id": team2["id"]}).status_code == 201, "room again after unfollow")
setting("features.billing", False)

print("\nALL ROUTE CHECKS PASSED")
