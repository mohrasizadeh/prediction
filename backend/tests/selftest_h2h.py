"""queries.h2h: the meetings list, `summary` and `insights` (h2h_summary.py), on a synthetic history.

No network, no MongoDB: an in-memory database with two clubs, ten meetings, stats for seven of them
and goal events for the scoring ones, plus a league background so the baseline rates are the league's.
"""
import os, sys, base64, datetime as dt, re
os.environ.setdefault("APP_ENCRYPTION_KEY", base64.b64encode(os.urandom(32)).decode())
HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("SOCCER_BRAIN_DIR", os.path.join(HERE, "soccer_brain"))
sys.path.insert(0, HERE); sys.path.insert(0, os.environ["SOCCER_BRAIN_DIR"])
import mongomock
import h2h_summary as HS, queries as Q

ok = lambda m: print("  ok  ", m)
def check(c, m):
    if not c: print("  FAIL", m); sys.exit(1)
    ok(m)

db = mongomock.MongoClient()["h"]
A, B = 1, 2
db.teams.insert_many([{"iid": A, "id": "ta", "name": "Alpha"}, {"iid": B, "id": "tb", "name": "Beta"},
                      {"iid": 3, "id": "tc", "name": "Gamma"}, {"iid": 4, "id": "td", "name": "Delta"}])
db.leagues.insert_one({"iid": 9, "id": "lg", "name": "League"})
T0 = dt.datetime(2026, 8, 1, 19)
# Newest first. Alpha unbeaten in all ten; Beta never keeps Alpha out.
SC = [(A, B, 2, 1), (B, A, 1, 1), (A, B, 3, 0), (B, A, 0, 2), (A, B, 2, 2),
      (B, A, 1, 3), (A, B, 1, 0), (B, A, 2, 2), (A, B, 4, 1), (B, A, 0, 1)]
for i, (h, a, hg, ag) in enumerate(SC):
    iid = 100 + i
    db.matches.insert_one({"iid": iid, "id": f"m{i}", "league_iid": 9, "status": "final", "home_iid": h, "away_iid": a,
                           "hg": hg, "ag": ag, "kickoff": T0 - dt.timedelta(days=60 * i)})
    if i < 7:
        db.team_match_stats.insert_many([
            {"match_iid": iid, "team_iid": A, "shots": 15 + i % 3, "sot": 6, "corners": 7, "fouls": 10, "yellow_cards": 1},
            {"match_iid": iid, "team_iid": B, "shots": 8, "sot": 3, "corners": 3, "fouls": 12, "yellow_cards": 3}])
    if hg + ag:
        # Alpha scores first in every meeting it scored in; an own goal by Alpha in m1 counts for Beta.
        if i == 1:
            ev = [{"type": "goal", "side": "away" if h == B else "home", "minute": 5, "own_goal": True}]
        else:
            ev = [{"type": "goal", "side": "home" if h == A else "away", "minute": 9}]
        db.match_events.insert_one({"match_iid": iid, "events": ev})
# The current fixture (scheduled) and an unrelated league background of 40 ordinary matches.
db.matches.insert_one({"iid": 999, "id": "now", "league_iid": 9, "status": "scheduled", "home_iid": A, "away_iid": B, "kickoff": T0 + dt.timedelta(days=30)})
bg = [(2, 1), (1, 1), (0, 1), (2, 0), (1, 2), (0, 0), (3, 1), (1, 0)]
for i in range(40):
    hg, ag = bg[i % len(bg)]
    db.matches.insert_one({"iid": 2000 + i, "id": f"bg{i}", "league_iid": 9, "status": "final", "home_iid": 3, "away_iid": 4,
                           "hg": hg, "ag": ag, "kickoff": T0 - dt.timedelta(days=i)})

r = Q.h2h(db, A, B)
for k in ("a_wins", "b_wins", "draws", "matches", "summary", "insights"):
    check(k in r, f"h2h keeps / adds key `{k}`")
check(r["a_wins"] == 7 and r["draws"] == 3 and r["b_wins"] == 0 and len(r["matches"]) == 10, "counts: 7-3-0 over 10 meetings")
check(r["matches"][0]["id"] == "m0" and r["matches"][0]["league"] == {"id": "lg", "name": "League"}, "newest first, each with its league")
s = r["summary"]
check(s["meetings"] == 10 and s["first"] == T0 - dt.timedelta(days=540) and s["last"] == T0, "meetings and span")
check(s["a"]["wins"] == 7 and s["b"]["wins"] == 0 and s["draws"] == 3, "summary wins per club and draws")
check(s["a"]["goals"] == 21 and s["b"]["goals"] == 8 and s["goals"] == 29 and s["goals_pm"] == 2.9, "goals per club and per meeting")
check(s["a"]["biggest_win"]["match_id"] == "m8" and (s["a"]["biggest_win"]["gf"], s["a"]["biggest_win"]["ga"]) == (4, 1)
      and s["b"]["biggest_win"] is None, "biggest win: Alpha 4-1, Beta none")
check(s["both_scored"] == 6 and s["three_plus"] == 6 and s["goalless"] == 0, "both scored 6, 3+ goals 6, no 0-0")
check(s["a"]["clean_sheets"] == 4 and s["b"]["clean_sheets"] == 0, "clean sheets")
check(s["venue"] == {"home": "a", "played": 5, "a_wins": 4, "draws": 1, "b_wins": 0}, "this venue: Alpha at home 4-1-0")
check(s["first_goal"] == {"known": 10, "a": 9, "b": 1, "none": 0}, "who scored first, own goal flips the side")
check(s["stats_meetings"] == 7 and s["a"]["stats"]["corners"] == 7.0 and s["b"]["stats"]["yellow_cards"] == 3.0
      and s["a"]["stats"]["poss"] is None, "stat averages over the 7 meetings with stats; a column never stored is None")
check(s["streak"] == {"side": "a", "kind": "unbeaten", "n": 10}, "current run: Alpha unbeaten in 10")
check(s["last_meeting"]["match_id"] == "m0" and s["last_meeting"]["result"] == "a", "last meeting")

ins = r["insights"]
check(3 <= len(ins) <= HS.MAX_INSIGHTS, f"3-5 insights ({len(ins)})")
check([x["score"] for x in ins] == sorted((x["score"] for x in ins), reverse=True), "insights ranked by how unusual")
check(all(re.search(r"\d", x["text"]) for x in ins), "every insight carries its numbers")
check(ins[0]["text"] == "Alpha scored first in 9 of the last 10 meetings."
      and ins[1]["text"] == "Alpha have not lost in the last 10 meetings.", "the rarest first: scored first 9 of 10, then the unbeaten run")
check(sum(1 for x in ins if x["kind"] in ("wins", "streak")) == 1, "one sentence per family (wins and the run do not both appear)")
check(sum(1 for x in ins if x["kind"] in HS.STAT_WORDS) <= 2, "at most two stat comparisons")
banned = re.compile(r"\b(bet|bets|betting|odds|tips?|value|edge|stake|picks?|over 2\.5|btts|lock|banker)\b", re.I)
check(not any(banned.search(x["text"]) for x in ins), "no betting language in insights")

# The match page excludes the match being viewed, and the default list is 20 long.
d = Q.h2h(db, A, B, exclude=100)
check(len(d["matches"]) == 9 and d["summary"]["meetings"] == 9 and all(m["id"] != "m0" for m in d["matches"]), "exclude: the viewed match is not its own history")
for i in range(15):
    db.matches.insert_one({"iid": 3000 + i, "id": f"old{i}", "league_iid": 9, "status": "final", "home_iid": A, "away_iid": B,
                           "hg": 1, "ag": 1, "kickoff": T0 - dt.timedelta(days=900 + i)})
check(len(Q.h2h(db, A, B)["matches"]) == 20, "default limit 20")

# Never met: the old keys, an empty list, no summary, no insights.
e = Q.h2h(db, 3, A)
check(e == {"a_wins": 0, "b_wins": 0, "draws": 0, "matches": [], "summary": None, "insights": []}, "never met: null summary, no insights")

# One meeting: a summary, but no sentence leans on a sample of one.
one = mongomock.MongoClient()["o"]
one.teams.insert_many([{"iid": 1, "id": "x", "name": "X"}, {"iid": 2, "id": "y", "name": "Y"}])
one.matches.insert_one({"iid": 1, "id": "o1", "league_iid": 1, "status": "final", "home_iid": 1, "away_iid": 2, "hg": 0, "ag": 0, "kickoff": T0})
o = Q.h2h(one, 1, 2)
check(o["summary"]["meetings"] == 1 and o["summary"]["first_goal"] == {"known": 1, "a": 0, "b": 0, "none": 1}
      and o["summary"]["a"]["stats"] is None and o["insights"] == [], "one goalless meeting: summary only, stats None")

# The match page carries the same block.
md = Q.match_detail(db, 999)
check(md["h2h"]["summary"]["meetings"] == 20 and isinstance(md["h2h"]["insights"], list), "match_detail carries h2h summary and insights")
print("h2h selftest passed")
