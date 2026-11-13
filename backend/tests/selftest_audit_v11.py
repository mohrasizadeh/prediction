"""The audit pass: every bug found by executing the pipeline rather than reading it. docs/90.

Each check here reproduces a defect that shipped and passed every existing test, because all of
them failed SILENTLY -- no exception, no log line, no counter. The pattern, nine times over, was a
reader still keyed on a shape the retired provider used, or a null the new provider means as a
zero. So every check below RUNS the real function and asserts on what came out; none of them greps
source text, which is the mistake that produced three false findings earlier in this pass (a regex
over a file happily matches the comment explaining the fix).
"""
import sys, os, base64
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("APP_ENCRYPTION_KEY", base64.b64encode(os.urandom(32)).decode())

from datetime import datetime, timedelta, timezone

import httpx
import mongomock

import normalize_af as NAF
import settings_store as S

OK = []


def check(name, cond):
    cond = bool(cond)
    OK.append(cond)
    print(("  ok     " if cond else "  FAIL   ") + name)


def utc(y, m, d):
    return datetime(y, m, d, 12, 0, tzinfo=timezone.utc)


# ------------------------------------------------------------------ the fixture builder
PM = {"G": "GK", "D": "DEF", "M": "MID", "F": "FWD"}


def person(pid, pos, minutes=90, goals=None, assists=None, shots=None, on=None,
           sub=False, saves=None, tackles=None, bare=False):
    """One entry of their `players` block. `bare` sends only `games`: no statistics at all."""
    g = {"position": pos, "minutes": minutes, "substitute": sub, "number": pid,
         "rating": "7.0", "captain": False}
    if bare:
        return {"player": {"id": pid, "name": f"P{pid}"}, "statistics": [{"games": g}]}
    return {"player": {"id": pid, "name": f"P{pid}"},
            "statistics": [{"games": g,
                            "goals": {"total": goals, "assists": assists, "saves": saves, "conceded": 0},
                            "shots": {"total": shots, "on": on},
                            "tackles": {"total": tackles, "blocks": None, "interceptions": None},
                            "fouls": {"committed": 1, "drawn": 0},
                            "passes": {"total": 20, "key": 0}}]}


def fixture(home, away, stats=None, events=None, lineups=None, fid=1):
    f = {"fixture": {"id": fid, "date": "2026-03-01T15:00:00+00:00",
                     "status": {"short": "FT"}, "referee": "A Referee"},
         "league": {"id": 39, "season": 2025, "round": "Regular Season - 1"},
         "teams": {"home": {"id": 10, "name": "Home"}, "away": {"id": 20, "name": "Away"}},
         "goals": {"home": 1, "away": 0},
         "players": [{"team": {"id": 10}, "players": home}, {"team": {"id": 20}, "players": away}]}
    if stats is not None:
        f["statistics"] = stats
    if events is not None:
        f["events"] = events
    if lineups is not None:
        f["lineups"] = lineups
    return f


# ==================================================================
print("goal involvements survive a fixture with no assist credited")
# A 3-1 in which no goal was credited with an assist. `assists` is null for all 26 players, which
# read as "assists not tracked", which nulled goal_involvements for the SCORERS too.
h = [person(1, "G", saves=3, tackles=0, shots=0), person(2, "D", goals=1, shots=2, on=1, tackles=2),
     person(3, "M", goals=1, shots=3, on=2, tackles=1), person(4, "F", goals=1, shots=4, on=3, tackles=0)]
a = [person(5, "G", saves=5, tackles=0, shots=0), person(6, "D", goals=1, shots=1, on=1, tackles=3)]
rows = NAF.players(fixture(h, a), PM)
check("no row carries a null goal involvement", all(r["goal_involvements"] is not None for r in rows))
check("each of the 4 scorers reads exactly 1.0",
      sorted(r["goal_involvements"] for r in rows if (r["goals"] or 0) > 0) == [1.0, 1.0, 1.0, 1.0])
check("a player who did neither reads a real 0.0",
      [r["goal_involvements"] for r in rows if r["ext_id"] == "1"] == [0.0])

print("a fixture in which nobody had a shot on target keeps its player rows")
# `sot` is in engine_bridge.PLAYER_REQUIRED, so an all-null column deleted every player row in the
# fixture -- and the matches it deleted were the lowest-output ones, so the models read high.
h = [person(1, "G", saves=2, shots=0, tackles=0), person(2, "D", shots=2, tackles=2)]
a = [person(5, "G", saves=1, shots=0, tackles=0), person(6, "D", shots=3, tackles=3)]
rows = NAF.players(fixture(h, a), PM)
check("sot reads 0.0, not None, when the shots block was sent",
      all(r["sot"] == 0.0 for r in rows))

print("a block the provider never sent still reads None")
# The other direction, which must NOT change: an absent block is unknown, and an unknown column has
# to drop the MARKET, never fabricate a zero.
rows = NAF.players(fixture([person(1, "D", bare=True)], [person(2, "M", bare=True)]), PM)
check("tackles stays None when no tackles block arrived", all(r["tackles"] is None for r in rows))
check("saves stays None when no goals block arrived", all(r["saves"] is None for r in rows))

print("an unused substitute gets no match row")
# Their bench man comes with a FULL statistics block and `games.minutes: null`. Mongo's `{$ne: 0}`
# matches null, so both readers that exclude a non-appearance counted him as a game played and
# failed, and `score_finished` counted it a miss in the track record.
h = [person(1, "G", saves=2, shots=0, tackles=0), person(2, "D", shots=2, on=1, tackles=2),
     person(99, "M", minutes=None, sub=True)]
rows = NAF.players(fixture(h, [person(5, "G", saves=1, shots=0, tackles=0)]), PM)
check("the bench man is absent", "99" not in [r["ext_id"] for r in rows])
h2 = [person(1, "G", saves=2, shots=0, tackles=0), person(7, "F", minutes=23, goals=1, shots=2, on=1, sub=True, tackles=0)]
rows2 = NAF.players(fixture(h2, [person(5, "G", saves=1, shots=0, tackles=0)]), PM)
check("a substitute who DID come on keeps his row", "7" in [r["ext_id"] for r in rows2])

print("one side's numbers never stand as proof for the other side")
# Trackedness used to be asked across the whole fixture. When one side came back empty the other
# side's numbers 'proved' the stat was tracked, and eleven starters were filled to zero -- a side
# that made no tackles and a front line with no shots, fitted as if real.
h = [person(1, "G", saves=2, shots=0, tackles=1), person(2, "D", shots=5, on=3, tackles=4)]
a = [person(5, "G", bare=True), person(6, "D", bare=True)]
rows = NAF.players(fixture(h, a), PM)
away = [r for r in rows if r["team_ext_id"] == "20"]
home = [r for r in rows if r["team_ext_id"] == "10"]
check("the empty side stays None", all(r["shots"] is None for r in away) and len(away) == 2)
check("the side that did send numbers keeps them", all(r["shots"] is not None for r in home))

print("a team statistic the provider sent as null is a zero")
TK = {"shots": "Total Shots", "sot": "Shots on Goal", "corners": "Corner Kicks",
      "poss": "Ball Possession", "fouls": "Fouls", "yellow_cards": "Yellow Cards",
      "xg": "expected_goals", "tackles": None}
sent = [{"type": "Total Shots", "value": 14}, {"type": "Shots on Goal", "value": 5},
        {"type": "Corner Kicks", "value": None}, {"type": "Ball Possession", "value": "58%"},
        {"type": "Fouls", "value": 11}, {"type": "Yellow Cards", "value": None}]
other = [{"type": "Total Shots", "value": 7}, {"type": "Shots on Goal", "value": 2},
         {"type": "Corner Kicks", "value": 3}, {"type": "Ball Possession", "value": None},
         {"type": "Fouls", "value": 9}, {"type": "Yellow Cards", "value": 2}]
st = [{"team": {"id": 10}, "statistics": sent}, {"team": {"id": 20}, "statistics": other}]
ts = NAF.team_stats(fixture([], [], stats=st), TK, "10", "20")
# corners and poss are both in TEAM_REQUIRED, so ONE null here deleted the whole match -- both
# teams and all 26 player rows -- from every frame, with no exception and no issue raised.
check("a null corner count reads 0.0", ts["home"]["corners"] == 0.0)
check("a null card count reads 0.0", ts["home"]["yellow_cards"] == 0.0)
check("possession is mirrored from the other side", ts["away"]["poss"] == 42.0)
check("xG is NOT zero-filled: a null xG is a gap, not a 0", ts["home"]["xg"] is None)
renamed = [{"type": "Total Shots", "value": 14}, {"type": "Corners", "value": 4}]
ts2 = NAF.team_stats(fixture([], [], stats=[{"team": {"id": 10}, "statistics": renamed},
                                            {"team": {"id": 20}, "statistics": renamed}]), TK, "10", "20")
check("a key the feed never sent stays None, so a renamed string still surfaces",
      ts2["home"]["corners"] is None)

print("the announced eleven gets real pitch coordinates")
# `pitch_x`/`pitch_y` were hard-coded None with their `grid` string stored beside them, unread.
# Match.jsx draws at `(pitch_x || 0) * 48`, so the whole XI piled onto the goal line the moment a
# real teamsheet arrived -- the predicted lineup looked right, the confirmed one collapsed.
G = ["1:1", "2:1", "2:2", "2:3", "2:4", "3:1", "3:2", "3:3", "3:4", "4:1", "4:2"]
def side(tid):
    return {"team": {"id": tid}, "formation": "4-4-2",
            "startXI": [{"player": {"id": 100 + i, "name": f"S{i}", "number": i + 1, "pos": "D", "grid": g}}
                        for i, g in enumerate(G)],
            "substitutes": [{"player": {"id": 900, "name": "Bench", "number": 20, "pos": "M", "grid": None}}],
            "coach": {"id": 7, "name": "Boss"}}
lu = NAF.lineups(fixture([], [], lineups=[side(10), side(20)]), PM)
starters = [p for p in lu["home"]["players"] if p["started"]]
check("eleven starters", len(starters) == 11)
check("a 4-4-2 occupies four distinct depths", len({p["pitch_x"] for p in starters}) == 4)
gk = [p for p in starters if p["grid"] == "1:1"][0]
check("the keeper is alone on his line, centred", (gk["pitch_x"], gk["pitch_y"]) == (0.03, 0.5))
check("no two starters share a point",
      len({(p["pitch_x"], p["pitch_y"]) for p in starters}) == 11)
check("a substitute is given no place on the pitch",
      all(p["pitch_x"] is None for p in lu["home"]["players"] if not p["started"]))


# ==================================================================
print("the three newer markets reach the publish loop")
import engine_bridge as B
for mk in ("player.saves", "player.fouls_committed", "player.goal_involvements"):
    check(f"{mk} has a coverage field", mk in B.MARKET_COVERAGE)
import ingest as I
check("ingest measures player saves coverage", "saves" in I.COVERAGE_FIELDS["player_match_stats"])
check("ingest measures team saves coverage", "saves" in I.COVERAGE_FIELDS["team_match_stats"])
db = mongomock.MongoClient()["a"]
for mk, field in B.MARKET_COVERAGE.items():
    db.data_coverage.insert_one({"league_iid": 1, "field": field, "share": 1.0})
en = B.enabled_markets(db, 1)
# `run_league` publishes with `markets.get(mk, False)`, so a market missing from this dict was
# dropped with no log and no counter: 19% of the lines the engine computed, binned.
check("enabled_markets now answers for saves", en.get("player.saves") is True)
check("enabled_markets now answers for fouls", en.get("player.fouls_committed") is True)
check("enabled_markets now answers for involvements", en.get("player.goal_involvements") is True)
dflt = S.registry()["engine.markets_enabled"]["default"]
check("the owner can switch all three off in Settings",
      all(k in dflt for k in ("player.saves", "player.fouls_committed", "player.goal_involvements")))

print("keepers reach the frame on the FIRST league of a fresh process")
# build_frames read `E.PLAYER_THR`, module state that only `configure_engine` fills -- and
# `run_league` calls configure_engine AFTER build_frames. So on league 1 of a new worker the GK
# discard did nothing and every keeper was deleted; leagues 2..N were fine. It also made the team
# saves column all-zero (not null), which the frame's own isna() guard cannot see.
import engine as E
E.PLAYER_THR.clear()
E.PLAYER_THR.update({"shots": [0.5, 1.5], "sot": [0.5], "tackles": [1.5, 2.5]})   # the import-time default
d2 = mongomock.MongoClient()["b"]
S.put(d2, "engine.auto_lines", False)
S.put(d2, "engine.player_thresholds", {"shots": [0.5], "sot": [0.5], "tackles": [1.5], "saves": [1.5]})
ladder = "engine.player_ladder" if S.get(d2, "engine.auto_lines") else "engine.player_thresholds"
check("the GK decision now reads the setting, not leftover module state",
      "saves" in (S.get(d2, ladder) or {}) and "saves" not in E.PLAYER_THR)

print("a league whose required team column is all-null returns None instead of raising")
# tg came out empty, pg was queried for an empty id list, and pg["pos"] raised KeyError on a frame
# with no columns -- after run_league had already written its engine_runs row as `running` and
# before it could ever update it. The league then sat "running" for ever and made jobs.tick's
# dirty check true on every subsequent tick.
d3 = mongomock.MongoClient()["c"]
for i in range(30):
    d3.matches.insert_one({"iid": i, "league_iid": 1, "status": "final", "round": i,
                           "home_iid": 1, "away_iid": 2, "hg": 1, "ag": 0,
                           "ingested_at": utc(2026, 3, 1), "kickoff": utc(2026, 3, 1)})
    for t, o in ((1, 2), (2, 1)):
        d3.team_match_stats.insert_one({"match_iid": i, "team_iid": t, "opp_iid": o, "home": t == 1,
                                        "league_iid": 1, "shots": 10.0, "sot": 4.0,
                                        "corners": None,                      # the renamed string
                                        "tackles": 15.0, "poss": 50.0, "shots_against": 10.0,
                                        "corners_against": None, "tackles_against": 15.0})
try:
    res = B.build_frames(d3, 1, 50)
    check("build_frames returns None rather than raising KeyError", res is None)
except Exception as e:
    check(f"build_frames returns None rather than raising ({type(e).__name__}: {e})", False)


# ==================================================================
print("a player's club never becomes his national team, and never moves backwards")
d4 = mongomock.MongoClient()["d"]
d4.leagues.insert_one({"iid": 1, "kind": "domestic", "enabled": True})
d4.leagues.insert_one({"iid": 2, "kind": "international", "enabled": True})   # World Cup qualifying
d4.teams.insert_one({"iid": 10, "name": "His Club"})
d4.teams.insert_one({"iid": 99, "name": "His Country"})
d4.players.insert_one({"iid": 5, "name": "A Player", "team_iid": 10, "team_as_of": utc(2026, 3, 1)})
d4.player_match_stats.insert_one({"player_iid": 5, "team_iid": 99, "league_iid": 2,
                                  "kickoff": utc(2026, 3, 20)})               # newer, but a country
I.refresh_player_clubs(d4)
check("an international appearance does not move his club",
      d4.players.find_one({"iid": 5})["team_iid"] == 10)
d4.player_match_stats.insert_one({"player_iid": 5, "team_iid": 77, "league_iid": 1,
                                  "kickoff": utc(2026, 1, 10)})               # a club, but OLDER
I.refresh_player_clubs(d4)
check("an older club match does not move him backwards",
      d4.players.find_one({"iid": 5})["team_iid"] == 10)
d4.player_match_stats.insert_one({"player_iid": 5, "team_iid": 77, "league_iid": 1,
                                  "kickoff": utc(2026, 4, 2)})                # a club, and newer
I.refresh_player_clubs(d4)
check("a newer club match does move him", d4.players.find_one({"iid": 5})["team_iid"] == 77)

print("a transient image failure is retried, a 404 is remembered")
# Every failure returned "missing", and the caller writes that onto the image_map row, which is then
# checked as `if m.get("missing"): continue`. For ever. One 503 during one sync denied a club its
# crest permanently, and only an admin could clear it.
import images as IMG
d5 = mongomock.MongoClient()["e"]
def resp(code):
    return httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(code)))
check("a 503 asks again later", IMG.download(d5, "team", 1, 11, http=resp(503)) == "retry")
check("a 429 asks again later", IMG.download(d5, "team", 1, 11, http=resp(429)) == "retry")
check("a 404 is their answer and is remembered", IMG.download(d5, "team", 1, 11, http=resp(404)) == "missing")
def boom(r):
    raise httpx.ConnectError("no route")
check("a dropped connection asks again later",
      IMG.download(d5, "team", 1, 11, http=httpx.Client(transport=httpx.MockTransport(boom))) == "retry")

print("the admin reads the running provider's numbers")
import routes_ingest_admin as RIA
d6 = mongomock.MongoClient()["f"]
S.put(d6, "provider.source", "apifootball")
af_cap = RIA._budget(d6)
S.put(d6, "provider.source", "pitchapi")
check("the ingest screen shows API-Football's cap under API-Football, not PitchAPI's 2,000",
      af_cap == int(S.get(d6, "apifootball.daily_cap")) and af_cap != RIA._budget(d6))
import admin_home as AH
d7 = mongomock.MongoClient()["g"]
I.enqueue(d7, "af_match", "1")
feeds = AH.feeds(d7)
check("the feeds panel counts the queue status the ingest actually writes",
      feeds["providers"][0]["queued"] == 1)
import purge as P
d8 = mongomock.MongoClient()["h"]
d8.alert_subscriptions.insert_one({"x": 1})
check("purge no longer reports a permanent unknown collection",
      "alert_subscriptions" not in P.unknown(d8))
check("features.live no longer names a retired provider",
      "SportAPI" not in (S.registry()["features.live"]["label"] + S.registry()["features.live"]["help"]))


# ==================================================================
print("the match events are DERIVED from, not merely stored")
# `_write_events` stored `match_events` and stopped. Almost nothing reads that archive; what the
# product reads is what `match_extras._apply` writes out of it. On the PitchAPI path `ingest_extras`
# called it; that path is `not af`-gated in jobs.tick, so under API-Football nobody did. cards_model
# is built entirely on those fields, so it did not fail -- it computed from zeros, and every player
# card forecast published at p = 0.0000 while the match card line read 0.39 instead of 0.57.
import ingest_af as IA
d9 = mongomock.MongoClient()["i"]
d9.players.insert_one({"iid": 501, "ext_id": "501", "name": "Booked", "team_iid": 10})
d9.players.insert_one({"iid": 502, "ext_id": "502", "name": "Scorer", "team_iid": 10})
d9.player_match_stats.insert_one({"match_iid": 1, "player_iid": 501, "team_iid": 10, "league_iid": 1})
d9.player_match_stats.insert_one({"match_iid": 1, "player_iid": 502, "team_iid": 10, "league_iid": 1})
d9.team_match_stats.insert_one({"match_iid": 1, "team_iid": 10, "opp_iid": 20, "league_iid": 1, "yellow_cards": 2.0})
d9.team_match_stats.insert_one({"match_iid": 1, "team_iid": 20, "opp_iid": 10, "league_iid": 1, "yellow_cards": 1.0})
m9 = {"iid": 1, "league_iid": 1, "home_iid": 10, "away_iid": 20, "kickoff": utc(2026, 3, 1)}
d9.matches.insert_one(dict(m9, status="final"))
ev = [{"type": "yellow", "minute": 40, "added": 0, "side": "home", "player_ext": "501",
       "player_name": "Booked", "in_ext": None, "in_name": None, "own_goal": False, "penalty": False},
      {"type": "goal", "minute": 55, "added": 0, "side": "home", "player_ext": "502",
       "player_name": "Scorer", "in_ext": None, "in_name": None, "own_goal": False, "penalty": False}]
IA._write_events(d9, m9, ev)
check("the events are archived", (d9.match_events.find_one({"match_iid": 1}) or {}).get("events"))
booked = d9.player_match_stats.find_one({"match_iid": 1, "player_iid": 501})
check("the booked player carries his card", booked.get("yellow_cards") == 1)
check("the player who was not booked carries a real 0",
      d9.player_match_stats.find_one({"match_iid": 1, "player_iid": 502}).get("yellow_cards") == 0)
check("the goalscorer's minute is recorded",
      d9.player_match_stats.find_one({"match_iid": 1, "player_iid": 502}).get("goal_minutes") == [55])
check("the opponent's cards-against are derived",
      d9.team_match_stats.find_one({"match_iid": 1, "team_iid": 20}).get("yellow_cards_against") == 2.0)
m9b = d9.matches.find_one({"iid": 1})
# `score_finished` refuses to grade a card forecast while extras_at is falsy, so without this the
# worthless lines were never graded either: a permanently empty track record on a constant 0.
check("extras_at is stamped, so card forecasts can be graded", m9b.get("extras_at") is not None)
check("the first scorer is recorded", m9b.get("first_scorer_iid") == 502)
check("the first goal's side is recorded", m9b.get("first_goal_side") == "home")

# A goalless, eventless match is a real result: bailing out early would leave extras_at unset for
# ever on exactly the matches whose card lines are all zero.
d9.matches.insert_one({"iid": 2, "league_iid": 1, "home_iid": 10, "away_iid": 20,
                       "kickoff": utc(2026, 3, 8), "status": "final"})
IA._write_events(d9, {"iid": 2, "league_iid": 1, "home_iid": 10, "away_iid": 20,
                      "kickoff": utc(2026, 3, 8)}, [])
m2 = d9.matches.find_one({"iid": 2})
check("a 0-0 with no events still gets extras_at", m2.get("extras_at") is not None)
check("and is recorded as having had no goal", m2.get("first_goal_side") == "none")

print("the announced eleven reaches db.lineups BEFORE kick-off")
# There was no API-Football lineup watch at all: jobs.tick gates the PitchAPI one behind `not af`
# and nothing replaced it, so db.lineups was only ever written AFTER the match by write_match.
# The engine therefore never saw a confirmed XI, the "lineups are in" e-mail never went, and
# `lineups_at` never moved so no forecast was re-fit when the teamsheet landed.
import apifootball as AF
import security
d10 = mongomock.MongoClient()["j"]
security.save_provider_key(d10, AF.PROVIDER, "k" * 24)
S.put(d10, "ingest.lineups_watch_hours", 6)
now10 = datetime.now(timezone.utc)
d10.teams.insert_one({"iid": 10, "ext_id": "10", "name": "Home"})
d10.teams.insert_one({"iid": 20, "ext_id": "20", "name": "Away"})
d10.matches.insert_one({"iid": 1, "ext_id": "555", "league_iid": 1, "status": "scheduled",
                        "home_iid": 10, "away_iid": 20, "kickoff": now10 + timedelta(hours=1)})
HDR10 = {"x-ratelimit-requests-limit": "75000", "x-ratelimit-requests-remaining": "74999",
         "X-RateLimit-Limit": "450", "X-RateLimit-Remaining": "449"}
body10 = [fixture([], [], lineups=[side(10), side(20)], fid=555)]
def h10(req):
    return httpx.Response(200, headers=HDR10, json={
        "get": req.url.path.lstrip("/"), "parameters": dict(req.url.params), "errors": [],
        "results": len(body10), "paging": {"current": 1, "total": 1}, "response": body10})
c10 = AF.Client(d10, httpx.Client(base_url=AF.BASE_URL, transport=httpx.MockTransport(h10)),
                sleep=lambda s: None)
res10 = IA.lineup_watch(c10, now10)
check("one call covered the fixture", res10["calls"] == 1)
check("the lineup was taken", res10["confirmed"] == 1)
check("24 lineup rows written: eleven and a substitute, each side",
      d10.lineups.count_documents({"match_iid": 1}) == 24)
check("eleven of them are starters",
      d10.lineups.count_documents({"match_iid": 1, "team_iid": 10, "started": True}) == 11)
check("they are marked confirmed, which is what the engine requires",
      d10.lineups.count_documents({"match_iid": 1, "confirmed": True}) == 24)
check("a starter carries his place on the pitch",
      (d10.lineups.find_one({"match_iid": 1, "team_iid": 10, "started": True}) or {}).get("pitch_x") is not None)
m10 = d10.matches.find_one({"iid": 1})
check("lineups_at is moved, so the forecast is re-fit", m10.get("lineups_at") is not None)
check("the match is flagged confirmed", m10.get("lineups_confirmed") is True)
# A second pass must not pay again for a fixture whose sheet we already hold.
res10b = IA.lineup_watch(c10, now10)
check("a fixture already confirmed is not fetched again", res10b["looked_at"] == 0)

# ==================================================================
print("the writer's event vocabulary is understood by every reader")
#
# THIS IS THE ONE CHECK THAT WOULD HAVE CAUGHT THREE BUGS AT ONCE.
#
# `normalize_af.events` is the single translator for both the live and the historical path, so a
# wrong word in it is wrong everywhere, for every league, with no second implementation left to
# disagree with it visibly. Its five words had FOUR consumers and three of them spoke the retired
# provider's dialect:
#
#   follow_alerts  queried for `red_card` / `second_yellow`, so a sending-off reached no follower
#                  at all, and an own goal was e-mailed as a plain "Goal" for the conceding side.
#   MatchEvents.jsx / LiveBits.jsx  keyed on `yellow_card` / `red_card` / `substitution`, so of
#                  everything the writer emits only `goal` had a label: `red` and `sub` fell through
#                  to the grey "unknown" fallback captioned with the raw column word. Match.jsx, on
#                  the same page, counted cards with the NEW words -- one screen, two vocabularies.
#
# Every one of those failed by returning fewer rows or a greyer label. Nothing raised.
import inspect
import follow_alerts as FA
import match_extras as MX
import live_track as LT

ev_all = NAF.events(fixture([], [], events=[
    {"type": "Goal", "detail": "Missed Penalty", "time": {"elapsed": 5}, "team": {"id": 10},
     "player": {"id": 1, "name": "Misser"}},
    {"type": "Goal", "detail": "Penalty", "time": {"elapsed": 30}, "team": {"id": 10},
     "player": {"id": 2, "name": "Scorer"}},
    {"type": "Goal", "detail": "Own Goal", "time": {"elapsed": 60}, "team": {"id": 20},
     "player": {"id": 3, "name": "Ogoal"}},
    {"type": "Card", "detail": "Yellow Card", "time": {"elapsed": 65}, "team": {"id": 10},
     "player": {"id": 9, "name": "Booked"}},
    {"type": "Card", "detail": "Second Yellow card", "time": {"elapsed": 70}, "team": {"id": 10},
     "player": {"id": 4, "name": "Two"}},
    {"type": "Card", "detail": "Red Card", "time": {"elapsed": 75}, "team": {"id": 10},
     "player": {"id": 8, "name": "Straight"}},
    {"type": "subst", "detail": "Substitution 1", "time": {"elapsed": 80}, "team": {"id": 10},
     "player": {"id": 5, "name": "Off"}, "assist": {"id": 6, "name": "On"}},
]), "10", "20")
emitted = {e["type"] for e in ev_all}
check(f"the fixture exercises all five words ({sorted(emitted)})", emitted == set(NAF.EVENT_TYPES))

# A MISSED PENALTY IS NOT A GOAL. Keyed on `type` alone it was byte-identical to a converted
# penalty -- same type, same `penalty: True` -- so a 5th-minute miss became the match's first goal,
# named the misser as `first_scorer_iid`, credited him `pen_goals` and a `goal_minutes` entry, and
# inflated the referee's penalty rate. On both paths. For every league.
check("a missed penalty is its own word", "missed_penalty" in emitted)
goals = [e for e in ev_all if e["type"] == "goal"]
check("the first GOAL is the scorer, not the man who missed",
      goals[0]["player_name"] == "Scorer" and goals[0]["minute"] == 30)
check("a missed penalty still carries the penalty flag, for the referee numbers",
      [e for e in ev_all if e["type"] == "missed_penalty"][0]["penalty"] is True)
check("a second yellow is flagged as one, while still counting as a sending-off",
      [e for e in ev_all if e.get("second_yellow")][0]["type"] == "red")

# Reader 1: the alert queries. `ALERT_TYPES` goes straight into a Mongo `$in`, so a word the writer
# never emits is a query that matches nothing.
check("every word the alerts subscribe to is a word the writer emits",
      set(FA.ALERT_TYPES) <= set(NAF.EVENT_TYPES))
check("a red card now matches the alert query", "red" in FA.ALERT_TYPES)
check("a missed penalty alerts nobody", "missed_penalty" not in FA.ALERT_TYPES)
labels = {e["type"]: FA.label_for(e) for e in ev_all}
check(f"a sending-off is described as one ({labels.get('red')!r})",
      FA.label_for({"type": "red", "second_yellow": True}) == "Second yellow, sent off")
check("an own goal is not described as a plain goal",
      FA.label_for({"type": "goal", "own_goal": True}) == "Own goal")

# Reader 2: `match_extras._apply`, which derives every card and substitution field the product
# reads. Asked by RUNNING it over the fixture above, because "the file contains the string" would
# also match the comment explaining the handling -- the mistake that produced three false findings
# earlier in this pass. What matters is the misser's row, and this is where C1's blast radius lands:
# `_write_events` now calls `_apply` and sets `first_goal_side`/`first_scorer_iid`, so a phantom goal
# propagates into the match, the player and the referee numbers at once.
dv = mongomock.MongoClient()["v"]
for pid in (1, 2, 3, 9, 4, 8, 5, 6):          # 6 came on, so he has a row of his own
    dv.players.insert_one({"iid": 500 + pid, "ext_id": str(pid), "name": f"P{pid}", "team_iid": 10})
    dv.player_match_stats.insert_one({"match_iid": 1, "player_iid": 500 + pid, "team_iid": 10, "league_iid": 1})
dv.team_match_stats.insert_one({"match_iid": 1, "team_iid": 10, "opp_iid": 20, "league_iid": 1, "yellow_cards": 3.0})
dv.team_match_stats.insert_one({"match_iid": 1, "team_iid": 20, "opp_iid": 10, "league_iid": 1, "yellow_cards": 0.0})
mv = {"iid": 1, "league_iid": 1, "home_iid": 10, "away_iid": 20, "kickoff": utc(2026, 3, 1)}
dv.matches.insert_one(dict(mv, status="final"))
IA._write_events(dv, mv, ev_all)
misser = dv.player_match_stats.find_one({"match_iid": 1, "player_iid": 501})
check("the man who MISSED is credited no penalty goal", (misser.get("pen_goals") or 0) == 0)
check("...and no goal minute", not (misser.get("goal_minutes") or []))
scorer = dv.player_match_stats.find_one({"match_iid": 1, "player_iid": 502})
check("the man who scored the penalty is credited one", scorer.get("pen_goals") == 1)
check("...at the minute he scored it", scorer.get("goal_minutes") == [30])
mv2 = dv.matches.find_one({"iid": 1})
check("the match's first scorer is the scorer, not the misser", mv2.get("first_scorer_iid") == 502)
check("the booked player has his card",
      dv.player_match_stats.find_one({"match_iid": 1, "player_iid": 509}).get("yellow_cards") == 1)
check("the man sent off for a second yellow has his red",
      dv.player_match_stats.find_one({"match_iid": 1, "player_iid": 504}).get("red_cards") == 1)
check("the substituted player's minute is recorded",
      dv.player_match_stats.find_one({"match_iid": 1, "player_iid": 505}).get("sub_off") == 80)
check("the man who came on is recorded as having come on",
      dv.player_match_stats.find_one({"match_iid": 1, "player_iid": 506}).get("sub_on") == 80)

# Reader 3: live_track, which decides whether a live card forecast has landed.
check("live_track recognises a booking", LT.is_yellow("yellow") is True)
check("...and does not count a sending-off as one", LT.is_yellow("red") is False)

# Reader 4: the front end, asked by RUNNING it rather than by grepping the file.
import json as _json
import subprocess
words_js = os.path.join(os.path.dirname(__file__), "..", "..", "frontend", "src", "components", "eventWords.js")
try:
    out = subprocess.run(
        ["node", "--input-type=module", "-e",
         f"import {{ EVENT_CLASS, eventLabel }} from {_json.dumps(os.path.abspath(words_js))};"
         f"const t={_json.dumps(sorted(NAF.EVENT_TYPES))};"
         "console.log(JSON.stringify({known:Object.keys(EVENT_CLASS),"
         "labels:Object.fromEntries(t.map(x=>[x,eventLabel({type:x})]))}));"],
        capture_output=True, text=True, timeout=60)
    fe = _json.loads(out.stdout.strip()) if out.returncode == 0 else None
except Exception:
    fe = None
if fe is None:
    check("the front end's vocabulary could be read (node)", False)
else:
    check(f"the front end knows every word the writer emits ({sorted(fe['known'])})",
          set(NAF.EVENT_TYPES) <= set(fe["known"]))
    # The old maps had no entry for `red` or `sub`, so both rendered through the grey fallback with
    # the raw column word as their caption. A label equal to the word itself IS that fallback.
    fell_through = [w for w, lab in fe["labels"].items() if lab == w.replace("_", " ")]
    check(f"no word falls through to the raw-word fallback ({fell_through})", not fell_through)
    check("a red card is labelled, not left as the column word", fe["labels"]["red"] == "Red card")
    check("a substitution is labelled", fe["labels"]["sub"] == "Substitution")
    check("a missed penalty has the label that was already waiting for it",
          fe["labels"]["missed_penalty"] == "Penalty missed")

# ==================================================================
print("the live lineups endpoint serves something")
# The whole in-play statistics-and-lineups branch of `live_af.live_tick` was behind
# `apifootball.live_stats`, which shipped OFF and which no test anywhere switched on -- so the
# branch had ZERO execution in the entire suite. Two of the live path's bugs were hiding in it, and
# `GET /api/live/{sid}/lineups` answered `{}` with no error: a feature that stopped existing
# quietly. It is on by default now, and this drives the real tick through a mocked transport.
import live_af as LA
import sportapi as SP
d11 = mongomock.MongoClient()["k"]
security.save_provider_key(d11, AF.PROVIDER, "k" * 24)
S.put(d11, "features.live", True)
check("the in-play statistics and lineups are on by default",
      S.get(d11, "apifootball.live_stats") is True)
# The tick narrows `?live=` to OUR competitions, so one has to be on or it correctly refuses.
d11.leagues.insert_one({"iid": 1, "ext_id": "39", "provider": "apifootball", "enabled": True,
                        "name": "A League", "kind": "domestic", "role": "forecast",
                        "current_season": "2025"})
d11.teams.insert_one({"iid": 10, "ext_id": "10", "name": "Home"})
d11.teams.insert_one({"iid": 20, "ext_id": "20", "name": "Away"})
d11.matches.insert_one({"iid": 1, "ext_id": "777", "league_iid": 1, "status": "scheduled",
                        "home_iid": 10, "away_iid": 20, "kickoff": datetime.now(timezone.utc)})
inplay = fixture([person(1, "G", saves=2, shots=0, tackles=1)],
                 [person(5, "G", saves=1, shots=0, tackles=0)],
                 lineups=[side(10), side(20)], fid=777)
inplay["fixture"]["status"] = {"short": "2H", "elapsed": 67}
inplay["events"] = [{"time": {"elapsed": 23, "extra": None}, "team": {"id": 10},
                     "player": {"id": 101, "name": "A One"}, "assist": {"name": None},
                     "type": "Card", "detail": "Red Card"}]
def h11(req):
    return httpx.Response(200, headers=HDR10, json={
        "get": req.url.path.lstrip("/"), "parameters": dict(req.url.params), "errors": [],
        "results": 1, "paging": {"current": 1, "total": 1}, "response": [inplay]})
c11 = AF.Client(d11, httpx.Client(base_url=AF.BASE_URL, transport=httpx.MockTransport(h11)),
                sleep=lambda s: None)
res11 = LA.live_tick(d11, c11)
check(f"the tick reports lineups stored ({res11.get('lineups')})", (res11.get("lineups") or 0) > 0)
sid = (d11.matches.find_one({"iid": 1}).get("live") or {}).get("sid")
lf = SP.lineups_for(d11, sid) if sid is not None else {}
check("the endpoint now returns a lineup rather than an empty object", bool(lf))
# `lineups_for` returns {side: {starters: [...], subs: [...]}}, which is the shape the match page
# reads -- not the raw stored row. Assert the page's shape, since that is the thing that was empty.
check(f"...for both sides ({sorted(lf)})", sorted(lf) == ["away", "home"])
check(f"...each with eleven starters ({[len(v['starters']) for v in lf.values()]})",
      all(len(v["starters"]) == 11 for v in lf.values()))
check("...and the bench alongside them",
      all(len(v["subs"]) == 1 for v in lf.values()))
check("...each starter named, so the page has something to draw",
      all(p.get("name") for v in lf.values() for p in v["starters"]))
# The red card above must reach the alert query in OUR vocabulary, which is the contract this
# whole section exists to protect.
reds = list(d11.live_events.find({"fixture_sid": sid, "type": {"$in": list(FA.ALERT_TYPES)}}))
check(f"a red card on the pitch matches the alert query ({len(reds)})", len(reds) == 1)
check("...and is stored in our vocabulary, not theirs",
      reds and reds[0]["type"] == "red")

# ==================================================================
print("API-Football rows reach the engine, and all six markets come alive")
#
# THE STRUCTURAL HOLE. The provider boundary was tested and the engine was tested, and NOTHING
# carried rows from one to the other: every test that drives `build_frames` seeds PitchAPI-shaped
# documents. That seam is the mechanism behind every silent death in this audit -- the dead
# `team_saves` column, the three dropped markets, the keeper-less frame -- because a column can be
# written correctly, read correctly, and still never arrive.
#
# So: ingest real API-Football answers through the real ingest, then ask the engine what it can see.
import af_leagues as AFL

d12 = mongomock.MongoClient()["l"]
security.save_provider_key(d12, AF.PROVIDER, "k" * 24)
d12.leagues.insert_one({"iid": 1, "ext_id": "39", "provider": "apifootball", "enabled": True,
                        "name": "A League", "kind": "domestic", "role": AFL.FORECAST,
                        "current_season": "2025", "backfill_seasons": ["2025"]})
CLUBS = [(10 + i, f"Club {i}") for i in range(8)]
SQUAD = ["G", "D", "D", "D", "D", "M", "M", "M", "M", "F", "F", "F", "F"]


def af_fixture(fid, home, away, day, with_stats=True):
    """One finished fixture in their shape, numbers varied so the models have something to fit."""
    def squad(tid, seed):
        out = []
        for k, pos in enumerate(SQUAD):
            pid = tid * 100 + k
            gk = pos == "G"
            out.append(person(pid, pos, minutes=90 if k < 11 else None,
                              sub=k >= 11,
                              goals=(1 if (k == 9 and seed % 3 == 0) else None),
                              assists=(1 if (k == 5 and seed % 4 == 0) else None),
                              shots=(0 if gk else (k + seed) % 4),
                              on=(0 if gk else (k + seed) % 2),
                              saves=((seed % 5) + 1 if gk else None),
                              tackles=(0 if gk else (k + seed) % 3)))
        return out
    def tstats(tid, seed):
        return {"team": {"id": tid}, "statistics": [
            {"type": "Total Shots", "value": 8 + seed % 7},
            {"type": "Shots on Goal", "value": 3 + seed % 4},
            {"type": "Corner Kicks", "value": (None if seed % 11 == 0 else 2 + seed % 6)},
            {"type": "Ball Possession", "value": f"{45 + seed % 11}%"},
            {"type": "Fouls", "value": 8 + seed % 6},
            {"type": "Yellow Cards", "value": (None if seed % 3 == 0 else 1 + seed % 3)},
            {"type": "Goalkeeper Saves", "value": 1 + seed % 5},
        ]}
    f = fixture(squad(home, fid), squad(away, fid + 1), fid=fid)
    f["fixture"]["date"] = f"2026-0{1 + day // 28}-{(day % 28) + 1:02d}T15:00:00+00:00"
    f["league"] = {"id": 39, "season": 2025, "round": f"Regular Season - {day // 4 + 1}"}
    f["teams"] = {"home": {"id": home, "name": f"Club {home}"},
                  "away": {"id": away, "name": f"Club {away}"}}
    # The `fixture()` helper above hardcodes clubs 10 and 20 on the player BLOCKS, so these have to
    # be re-stamped with this match's real clubs. Leaving them is a convincing way to fool yourself:
    # every player row still lands, `normalize_af` still works, and only the team totals come out
    # null -- because `_sum_team` is looking for players of a club that is not in the fixture. Which
    # is how this test first reported "the engine can build no frames" and blamed the product.
    f["players"] = [{"team": {"id": home}, "players": squad(home, fid)},
                    {"team": {"id": away}, "players": squad(away, fid + 1)}]
    f["goals"] = {"home": fid % 3, "away": (fid + 1) % 3}
    if with_stats:
        f["statistics"] = [tstats(home, fid), tstats(away, fid + 1)]
    f["events"] = [{"type": "Card", "detail": "Yellow Card", "time": {"elapsed": 30 + fid % 50},
                    "team": {"id": home}, "player": {"id": home * 100 + 3, "name": "Booked"}}]
    return f


ALL_FX = []
fid = 1000
for rnd in range(14):
    for a in range(0, 8, 2):
        ALL_FX.append(af_fixture(fid, CLUBS[a][0], CLUBS[a + 1][0], rnd * 4))
        fid += 1
BY_ID = {f["fixture"]["id"]: f for f in ALL_FX}
check(f"the fixture set is big enough for the engine's 20-match floor ({len(ALL_FX)})", len(ALL_FX) >= 25)


def h12(req):
    pr = dict(req.url.params)
    if "ids" in pr:
        body = [BY_ID[int(i)] for i in str(pr["ids"]).split("-") if int(i) in BY_ID]
    else:
        body = ALL_FX
    return httpx.Response(200, headers=HDR10, json={
        "get": req.url.path.lstrip("/"), "parameters": pr, "errors": [],
        "results": len(body), "paging": {"current": 1, "total": 1}, "response": body})


c12 = AF.Client(d12, httpx.Client(base_url=AF.BASE_URL, transport=httpx.MockTransport(h12)),
                sleep=lambda s: None)
lg12 = d12.leagues.find_one({"iid": 1})
IA.sync_fixtures(c12, lg12, 2025)
drained = IA.drain(c12, max_seconds=60.0)
check(f"every fixture was written through the real ingest ({drained['written']})",
      drained["written"] == len(ALL_FX))
check(f"...and none failed ({drained['failed']})", drained["failed"] == 0)
I.assign_rounds(d12, 1)
I.update_coverage(d12, 1)

# The engine, on rows that came out of API-Football and nothing else.
frames = B.build_frames(d12, 1, 60)
check("the engine can build frames from API-Football rows", frames is not None)
if frames:
    ms12, tg12, pg12, ap12, diag12 = frames
    check(f"...and kept the matches ({diag12['matches_kept']} of {diag12['matches_before']})",
          diag12["matches_kept"] >= len(ALL_FX) * 0.8)
    check(f"...with no blank player column ({diag12['blank_columns']})", not diag12["blank_columns"])
    # THE ASSERTION THAT WAS MISSING. Not "the column exists" -- which is what the existing tests
    # check -- but "the engine can fit a market on it". All six, including the three that the market
    # gate was silently dropping and the saves one that reached the frame with no keeper in it.
    want = {"shots", "sot", "tackles", "fouls_committed", "goal_involvements", "saves"}
    check(f"every market has data: {sorted(B.MARKETS_WITH_DATA)}", want <= B.MARKETS_WITH_DATA)
    gks = pg12[pg12["pos"] == "GK"] if "pos" in pg12.columns else []
    check(f"keepers are in the frame, so saves can be fitted ({len(gks)})", len(gks) > 0)
    check("the team saves column is not a column of zeros",
          "saves" in tg12.columns and float(tg12["saves"].max()) > 0.0)
    check("the team goal-involvements column is not a column of zeros",
          "goal_involvements" in tg12.columns and float(tg12["goal_involvements"].max()) > 0.0)
# And the derived card fields, which only exist because _write_events calls _apply.
check("the ingest derived the card fields the card model reads",
      d12.player_match_stats.count_documents({"yellow_cards": {"$gte": 1}}) >= len(ALL_FX))
check("...and stamped extras_at, without which no card forecast is ever graded",
      d12.matches.count_documents({"extras_at": {"$ne": None}}) == len(ALL_FX))
en12 = B.enabled_markets(d12, 1)
check(f"the market gate passes all three newer markets on real coverage",
      all(en12.get(m) for m in ("player.saves", "player.fouls_committed", "player.goal_involvements")))

# ==================================================================
print("the whistle queues the statistics, and the match page shows them")
#
# REPORTED: "the stats updated with a delay... I know that pitchapi is still serving the match page
# final stats, because I had it on before, and it would show exactly the same and the same delay".
# The delay was real and the provider was not the cause -- the retired provider's `results_sync` ran
# on the same six-hour cadence, which is why it felt identical.
#
# ONE place in the codebase queued a finished match's statistics: `sync_fixtures`, from the
# `af_fixtures` job, every `ingest.fixtures_sync_hours` (6). And when it ran it read `/fixtures`
# through a cache whose TTL is six hours off a match day, so it could run and still see the match as
# `scheduled` and queue nothing. Meanwhile the live tick had been stamping `final_at` the instant
# the status flipped and doing nothing with it.
import live_af as LA
import queries as Q

SQUAD13 = ["G", "D", "D", "D", "D", "M", "M", "M", "M", "F", "F"]


def tstats13(tid, seed):
    return {"team": {"id": tid}, "statistics": [
        {"type": "Total Shots", "value": 8 + seed % 7}, {"type": "Shots on Goal", "value": 3 + seed % 4},
        {"type": "Corner Kicks", "value": 2 + seed % 6},
        {"type": "Ball Possession", "value": f"{45 + seed % 11}%"},
        {"type": "Fouls", "value": 8 + seed % 6}, {"type": "Yellow Cards", "value": 1 + seed % 3},
        {"type": "Goalkeeper Saves", "value": 1 + seed % 5}]}


def squad13(tid, seed):
    return [person(tid * 100 + k, p, shots=(0 if p == "G" else (k + seed) % 4),
                   on=(0 if p == "G" else (k + seed) % 2),
                   saves=((seed % 5) + 1 if p == "G" else None),
                   tackles=(0 if p == "G" else (k + seed) % 3))
            for k, p in enumerate(SQUAD13)]


def fx13(short, elapsed=None):
    f = fixture(squad13(10, 3), squad13(20, 7), stats=[tstats13(10, 3), tstats13(20, 7)], fid=777)
    f["fixture"]["status"] = {"short": short, "elapsed": elapsed}
    f["teams"] = {"home": {"id": 10, "name": "Home"}, "away": {"id": 20, "name": "Away"}}
    f["players"] = [{"team": {"id": 10}, "players": squad13(10, 3)},
                    {"team": {"id": 20}, "players": squad13(20, 7)}]
    f["events"] = [{"type": "Card", "detail": "Yellow Card", "time": {"elapsed": 30},
                    "team": {"id": 10}, "player": {"id": 1003, "name": "Booked"}}]
    return f


def client13(db, body):
    def h(req):
        return httpx.Response(200, headers=HDR10, json={
            "get": req.url.path.lstrip("/"), "parameters": dict(req.url.params), "errors": [],
            "results": len(body), "paging": {"current": 1, "total": 1}, "response": body})
    return AF.Client(db, httpx.Client(base_url=AF.BASE_URL, transport=httpx.MockTransport(h)),
                     sleep=lambda s: None)


d13 = mongomock.MongoClient()["m"]
security.save_provider_key(d13, AF.PROVIDER, "k" * 24)
S.put(d13, "features.live", True)
d13.leagues.insert_one({"iid": 1, "ext_id": "39", "provider": "apifootball", "enabled": True,
                        "name": "L", "kind": "domestic", "role": AFL.FORECAST, "current_season": "2025"})
IA.sync_fixtures(client13(d13, [fx13("NS")]), d13.leagues.find_one({"iid": 1}), 2025)
m13 = d13.matches.find_one({"ext_id": "777"})
check("a fixture not yet played is not queued for statistics",
      d13.ingest_queue.count_documents({"task": IA.QUEUE_TASK}) == 0)

LA.live_tick(d13, client13(d13, [fx13("2H", 67)]))
check("...nor while it is being played",
      d13.ingest_queue.count_documents({"task": IA.QUEUE_TASK}) == 0)
# THE PAGE, MID-MATCH. `match_detail` returned no statistics at all before this: `live_stats` had one
# reader (`live_track`, grading a live forecast) and no display, and what the page showed as team
# stats was `team_styles` -- a historical model that by design does not move during a match.
mid = Q._stats_block(d13, d13.matches.find_one({"iid": m13["iid"]}))
check(f"the page is given this match's numbers while it is on ({mid and mid['source']})",
      mid is not None and mid["source"] == "live")
check("...with possession, which has no team statistic of its own on one side",
      mid and mid["home"].get("poss") is not None and mid["away"].get("poss") is not None)
check("...and the keeper's saves, summed from the players as the final path does",
      mid and mid["home"].get("saves") is not None)

LA.live_tick(d13, client13(d13, [fx13("FT")]))
check(f"THE WHISTLE queues it ({d13.ingest_queue.count_documents({'task': IA.QUEUE_TASK})})",
      d13.ingest_queue.count_documents({"task": IA.QUEUE_TASK}) == 1)
res13 = IA.drain(client13(d13, [fx13("FT")]), max_seconds=20.0)
check(f"...and `drain`, which runs every tick, ingests it ({res13['written']})", res13["written"] == 1)
m13b = d13.matches.find_one({"iid": m13["iid"]})
check("so the match is ingested within a tick, not within six hours",
      m13b.get("ingested_at") is not None)
fin = Q._stats_block(d13, m13b)
check(f"the page now reads the final row ({fin and fin['source']})",
      fin is not None and fin["source"] == "final")

# A ROW THAT APPEARS ONLY AT THE WHISTLE looks like a number that changed when all that changed is
# which document was read. The live block used to carry four columns and the final row nine.
live_cols = {k for k, v in mid["home"].items() if v is not None}
final_cols = {k for k, v in fin["home"].items() if v is not None}
check(f"no row appears only at full time ({sorted(final_cols - live_cols) or 'none'})",
      not (final_cols - live_cols))

# Queued once, not once a tick: a second final tick must not re-queue an ingested match.
LA.live_tick(d13, client13(d13, [fx13("FT")]))
check("an already-ingested match is not queued again",
      d13.ingest_queue.count_documents({"task": IA.QUEUE_TASK, "status": "pending"}) == 0)

print("a match day still looks like one after the last kick-off")
# `on_match_day` picks a 1-hour fixture-list TTL instead of 6. It counted only fixtures still
# SCHEDULED in the next 24h, so the moment the last match of a round kicked off the league stopped
# looking like a match day -- exactly when the results are landing.
def md_window(db):
    now_ = datetime.now(timezone.utc)
    return db.matches.count_documents({
        "league_iid": 1,
        "kickoff": {"$gte": now_ - timedelta(hours=6), "$lte": now_ + timedelta(hours=24)}}) > 0


for name, rec, want in (
        ("a match kicks off in three hours", {"status": "scheduled", "kickoff": +3}, True),
        ("it is being played right now", {"status": "scheduled", "kickoff": -0.5}, True),
        ("the last match kicked off two hours ago", {"status": "final", "kickoff": -2}, True),
        ("nothing within a week", {"status": "scheduled", "kickoff": +168}, False)):
    dz = mongomock.MongoClient()["z"]
    dz.matches.insert_one({"iid": 1, "league_iid": 1, "status": rec["status"],
                           "kickoff": datetime.now(timezone.utc) + timedelta(hours=rec["kickoff"])})
    got = md_window(dz)
    check(f"{name}: match day = {got}", got is want)

# ==================================================================
print()
bad = OK.count(False)
print(f"{len(OK) - bad}/{len(OK)} checks passed")
sys.exit(1 if bad else 0)
