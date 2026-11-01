"""selftest_livetrack.py -- a forecast ticks green as it happens (docs/31).

Proves: yellow cards (match and player) count from live events; the line is "hit" the moment the count passes it and
stays hit; a line not yet reached is "live" while the match is on and "missed" at full time; a line with no count is
"unknown" (never a false tick); events are matched to our players inside the right club only; team and player
statistics are read from several answer shapes and from the setting's names; a bad statistics answer does not stop
the minute job; scheduled and postponed matches track nothing.
"""
import datetime as dt
import testkit as K
from testkit import check, db, setting, srv
import live_track as LT, settings_store as S, sportapi as SP
from fastapi.testclient import TestClient

now = dt.datetime.now(dt.timezone.utc)
db.teams.insert_many([{"iid": 1, "id": "t1", "ext_id": 1, "name": "Como"}, {"iid": 2, "id": "t2", "ext_id": 2, "name": "Venezia"}])
db.players.insert_many([{"iid": 11, "id": "p11", "ext_id": 11, "name": "Marco Rossi", "team_iid": 1, "pos": "MID"}, {"iid": 12, "id": "p12", "ext_id": 12, "name": "Luca Bianchi", "team_iid": 2, "pos": "DEF"}])
db.matches.insert_one({"iid": 5, "id": "m5", "ext_id": 5, "home_iid": 1, "away_iid": 2, "kickoff": now, "status": "scheduled", "league_iid": 1})
db.live_fixtures.insert_one({"sid": 77, "match_iid": 5, "league_iid": 1, "status": "LIVE", "minute": "40'", "home_iid": 1, "away_iid": 2, "kickoff": now, "polled_at": now})
F = lambda k, scope, stat, thr, **x: db.forecasts.insert_one({"fkey": k, "match_iid": 5, "is_current": True, "hidden": False, "scope": scope, "stat": stat, "thr": thr, "team_iid": x.get("team", 1), "player_iid": x.get("player")})
F("c4", "team", "match_yellow_cards", 3.5); F("c6", "team", "match_yellow_cards", 5.5)
F("py", "player", "yellow_cards", 0.5, player=11); F("py2", "player", "yellow_cards", 1.5, player=11)
F("sh", "player", "shots", 0.5, player=11); F("co", "team", "corners", 4.5, team=1)

db.live_events.insert_many([{"fixture_sid": 77, "eid": i, "type": "yellow_card", "side": s, "player_name": n, "player_iid": pi, "minute": f"{10 + i}'", "minute_num": 10 + i}
                            for i, (s, n, pi) in enumerate([("home", "Marco Rossi", 11), ("away", "Luca Bianchi", 12), ("away", "X", 12)])])
r = LT.evaluate(db, 5)["items"]
check(r["c4"] == {"state": "live", "current": 3, "needed": 4, "source": "events"}, "match cards counted: 3 of 4, still live")
db.live_events.insert_one({"fixture_sid": 77, "eid": 9, "type": "second_yellow", "side": "home", "player_name": "Marco Rossi", "player_iid": 11, "minute": "50'", "minute_num": 50})
r = LT.evaluate(db, 5)["items"]
check(r["c4"]["state"] == "hit" and r["c4"]["current"] == 4, "4th card turns the line green")
check(r["py"]["state"] == "hit" and r["py2"]["state"] == "hit", "player cards: 1+ and 2+ both reached")
check(r["c6"]["state"] == "live", "6+ cards not yet")
check(r["sh"]["state"] == "unknown" and r["co"]["state"] == "unknown", "no statistics yet: unknown, no false tick")
db.live_events.insert_one({"fixture_sid": 77, "eid": 10, "type": "yellow_card", "side": "home", "player_name": "Somebody Else", "player_iid": None, "minute": "55'", "minute_num": 55})
check(LT.evaluate(db, 5)["items"]["py2"]["state"] == "hit", "a hit stays a hit when another event is unmatched")

# statistics: three answer shapes and the setting's names
keys = {"shots": ["shots", "total_shots"], "sot": ["shots_on_target"], "corners": ["corners"], "tackles": ["tackles"]}
a = SP.parse_stats({"data": {"home": {"Total Shots": "12 (50%)", "corners": 5}, "away": {"corners": 2}}}, keys)
b = SP.parse_stats({"teams": [{"side": "home", "stats": {"shots": 9}}]}, keys)
c = SP.parse_stats([{"type": "Corners", "home": 6, "away": 3}, {"type": "Fouls", "home": 9, "away": 8}], keys)
check(a["teams"]["home"] == {"shots": 12.0, "corners": 5.0} and a["teams"]["away"] == {"corners": 2.0}, "shape 1: home and away blocks")
check(b["teams"]["home"] == {"shots": 9.0}, "shape 2: teams list")
check(c["teams"]["home"] == {"corners": 6.0} and c["teams"]["away"] == {"corners": 3.0}, "shape 3: rows; unknown names ignored")
p = SP.parse_stats({"players": [{"name": "Marco Rossi", "side": "home", "stats": {"shots": 2, "tackles": 1}}]}, keys)
check(p["players"][0]["shots"] == 2.0, "player statistics read")
SP.store_stats(db, 77, {"teams": a["teams"], "players": p["players"]}, now)
r = LT.evaluate(db, 5)["items"]
check(r["co"]["state"] == "hit" and r["co"]["current"] == 5, "team corners from statistics: 5 beats 4.5")
check(r["sh"]["state"] == "hit" and r["sh"]["current"] == 2, "player shots matched to our player inside the club")

db.live_fixtures.update_one({"sid": 77}, {"$set": {"status": "FT"}})
F("late", "team", "corners", 8.5, team=1)
r = LT.evaluate(db, 5)
check(r["items"]["late"]["state"] == "missed" and r["items"]["c6"]["state"] == "missed" and r["items"]["c4"]["state"] == "hit", "full time: hit stays, the rest are missed")
db.live_fixtures.update_one({"sid": 77}, {"$set": {"status": "Postponed"}})
check(LT.evaluate(db, 5) == {"active": False, "items": {}}, "postponed matches track nothing")

# the route
db.live_fixtures.update_one({"sid": 77}, {"$set": {"status": "LIVE"}})
cl = TestClient(srv.app); cl.__enter__()
setting("security.rate_limit_read_per_minute", 1000)
j = cl.get("/api/matches/m5/live-forecasts").json()
check(j["active"] and j["items"]["c4"]["state"] == "hit", "route answers")
check(cl.get("/api/matches/nope/live-forecasts").status_code == 404, "unknown match is 404")

# a bad statistics answer does not stop the minute job
class Bad:
    def left(s): return 1000
    def tight(s): return False
    def get(s, path, kind, cache_days=None):
        if kind == "stats": raise SP.SportAPIError("boom")
        return {"data": []}
setting("sportapi.enabled", True); setting("sportapi.leagues", {"1": 39}); setting("sportapi.live_stats", True); setting("sportapi.upcoming_days", 0)
out = SP.live_tick(db, client=Bad(), now=now + dt.timedelta(minutes=10))
check(out.get("stats_error") == "boom" and out["status"] == "ok", "a failing statistics call is reported and the rest of the job still runs")

# ---- docs/38: a match is "on" for every in-play word, not only the exact word LIVE.
# Before this, events stopped refreshing at half-time and in extra time, so a card shown then arrived late or never.
for word in ("LIVE", "HT", "1H", "2H", "ET", "BT", "P", "INT", "SUSP", "Live", "In Play", "45+"):
    check(SP.in_play(word), f"'{word}' counts as a match that is on")
for word in ("Scheduled", "TBD", "FT", "AET", "PENS", "Postponed", "Cancelled", "Abandoned", "WO", None, ""):
    check(not SP.in_play(word), f"'{word}' does not count as on")

class Counting:
    """Answers every call and remembers which fixtures were asked for events."""
    def __init__(s): s.events_for = []
    def left(s): return 10_000
    def tight(s): return False
    def get(s, path, kind, cache_days=None):
        if kind == "events":
            s.events_for.append(int(path.split("/")[3]))
            return {"data": []}
        return {"data": []}

setting("sportapi.live_stats", False)
db.live_fixtures.delete_many({"sid": {"$in": [91, 92, 93]}})
base = {"league_iid": 1, "home_iid": 1, "away_iid": 2, "kickoff": now, "polled_at": now, "match_iid": None}
db.live_fixtures.insert_many([{**base, "sid": 91, "status": "HT"}, {**base, "sid": 92, "status": "ET"},
                              {**base, "sid": 93, "status": "FT", "final_done": True}])
c = Counting()
SP.live_tick(db, client=c, now=now + dt.timedelta(hours=2))
check(91 in c.events_for and 92 in c.events_for, "events are refreshed at half-time and in extra time, not only while the word is LIVE")
check(93 not in c.events_for, "a finished match is not polled again")
check(db.live_fixtures.find_one({"sid": 91}).get("events_at") is not None, "...and the refresh time is recorded")

# the provider's own status words are remembered, so `in_play` can be checked against what it really sends
SP.upsert_fixture(db, {"id": 95, "league_id": 39, "date": now.strftime("%Y-%m-%d"), "status": "Second Half",
                       "home_id": 1, "away_id": 2, "home_team": "Como", "away_team": "Venezia"}, {39: 1}, now)
seen = (db.sportapi_state.find_one({"_id": "live"}) or {}).get("status_seen") or {}
check(seen.get("Second Half") == 1, f"the words this provider sends are counted, so the list can be checked: {sorted(seen)}")

# ---- docs/38: reading the provider's statistic names without a hand-kept list
check(SP._canon("Shots (Total)") == SP._canon("shots total") == "shotstotal", "a name is matched on letters and digits only")
a = SP.stat_alias({})
check(a.get("totalshots") == "shots" and a.get("shotsongoal") == "sot" and a.get("cornerkicks") == "corners" and a.get("tackleswon") == "tackles",
      "the built-in names work with no setting at all")
check(SP.stat_alias({"shots": ["Goal Attempts"]}).get("goalattempts") == "shots", "a name from the setting is added to the built-in ones")

K2 = {"shots": [], "sot": [], "corners": [], "tackles": []}
rows = SP.parse_stats([{"type": "Total Shots", "home": 14, "away": 8}, {"type": "Shots on Goal", "home": 5, "away": 2},
                       {"type": "Corner Kicks", "home": 7, "away": 3}, {"type": "Ball Possession", "home": "55%", "away": "45%"}], K2)
check(rows["teams"]["home"] == {"shots": 14.0, "sot": 5.0, "corners": 7.0}, f"a row-shaped answer is read: {rows['teams']['home']}")
blocks = SP.parse_stats({"home": {"stats": {"shots-total": 11, "Shots On Target": 4, "Tackles Won": 19}},
                         "away": {"stats": {"shots-total": 9, "Shots On Target": 3, "Tackles Won": 14}}}, K2)
check(blocks["teams"]["away"] == {"shots": 9.0, "sot": 3.0, "tackles": 14.0}, "a home/away answer is read")
check(rows["unmatched"] == ["Ball Possession"] and not blocks["unmatched"], "names we cannot place are reported, and only those")

# coverage is written on every fetch, so Admin shows it without spending a call
SP.store_stats(db, 77, SP.parse_stats([{"type": "Total Shots", "home": 3, "away": 1}, {"type": "Offsides", "home": 2, "away": 0}], K2), now)
cov = SP.stats_coverage(db)
check(cov["found"]["shots"] is True and cov["found"]["tackles"] is False, f"coverage says which counts were found: {cov['found']}")
check("Offsides" in cov["unmatched"], "...and which names were not placed")

# the admin panel's routes: see the state with no provider call, and teach a name
with TestClient(srv.app) as owner:
    admin = K.boot(owner)[0]
    r = admin.get("/api/admin/sportapi/live-stats")
    j = r.json()
    check(r.status_code == 200 and set(j["stats"]) == set(SP.BUILTIN_STAT_NAMES) and "coverage" in j,
          "Admin can read the live-statistics state without spending a call")
    check(j["coverage"]["found"]["shots"] is True and "Offsides" in j["coverage"]["unmatched"], "...and it carries the coverage just written")
    check(any(f["sid"] == 77 for f in j["fixtures"]), "...and lists fixtures that can be checked")
    check(admin.post("/api/admin/sportapi/stats-keys", json={"stat": "nope", "name": "x"}).status_code == 400, "an unknown count is refused")
    ok = admin.post("/api/admin/sportapi/stats-keys", json={"stat": "shots", "name": "Goal Attempts"})
    check(ok.status_code == 200 and "Goal Attempts" in ok.json()["stats_keys"]["shots"], "a provider name can be taught from the panel")
    check(SP.stat_alias(S.get(db, "sportapi.stats_keys")).get("goalattempts") == "shots", "...and it is used from then on")
    again = admin.post("/api/admin/sportapi/stats-keys", json={"stat": "shots", "name": "goal attempts"})
    check(again.json().get("note") == "already known", "the same name twice is not added twice")

print("PASS selftest_livetrack")
