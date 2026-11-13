"""Admin > Waitlist numbers, and the three match ads' data (docs/68 "Measuring it", docs/60 section 4).

Proves, for the waitlist:
  * /waitlist's events are accepted from a browser and a bot's are not;
  * a sign-up carries the visit's source, first touch only, and Do Not Track strips it;
  * the report counts visitors per day, reads scroll depth and sections as shares OF VISITORS, and
    gives each source its own visitors and sign-ups;
  * the dashboard route needs analytics.read.
And for the ads:
  * Head to head returns both squads for one match, one line per market per player, ranked under the
    feed ceiling; with a market picked, only that market;
  * the after-the-whistle data returns hits AND misses, and its count is the whole day's, not the
    rows returned;
  * a saved Head to head needs its match, and a malformed market or day is dropped, not stored.
"""
import datetime as dt
import os
import sys
import uuid

import testkit as K                                   # noqa: F401  (boots the app on an in-memory database)
from testkit import check, db, setting
from fastapi.testclient import TestClient
import server as srv
import analytics as AN
import waitlist_stats as WS
import ads as AD

UA = "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 Mobile/15E148 Safari/604.1"
DESK = "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_0) AppleWebKit/537.36 Chrome/124.0 Safari/537.36"
setting("analytics.first_party_enabled", True)
setting("security.rate_limit_write_per_minute", 1000); setting("security.rate_limit_read_per_minute", 1000)

# ---------------------------------------------------------------- where a visit came from
check(AN.source_of({"source": "instagram"}, "t.co") == "instagram", "a utm tag wins over the referrer")
check(AN.source_of(None, "l.instagram.com") == "instagram", "Instagram's link shim folds into 'instagram'")
check(AN.source_of(None, "t.co") == "x", "t.co is X")
check(AN.source_of(None, "www.google.co.uk") == "google", "any Google country domain is 'google'")
check(AN.source_of(None, "www.somefanblog.com") == "somefanblog.com", "an unknown site is named by its host, without www")
check(AN.source_of(None, None) == "direct", "no tag and no referrer is 'direct'")


def visitor(ip, ua=UA):
    c = TestClient(srv.app)
    c.headers.update({"user-agent": ua, "x-forwarded-for": ip})
    return c


def visit(c, ref=None, utm=None, depth=0, sections=(), form=False):
    body = {"name": "page_view", "path": "/waitlist", **({"ref": ref} if ref else {}), **({"utm": utm} if utm else {})}
    check(c.post("/api/analytics/collect", json=body).status_code == 204, "the page view is accepted")
    for d in (25, 50, 75, 100):
        if depth >= d:
            c.post("/api/analytics/collect", json={"name": "wl_scroll", "path": "/waitlist", "props": {"depth": d}})
    for s in sections:
        c.post("/api/analytics/collect", json={"name": "wl_section", "path": "/waitlist", "props": {"section": s}})
    if form:
        c.post("/api/analytics/collect", json={"name": "wl_form_start", "path": "/waitlist"})


# Five visitors: two from a tagged Instagram link (one signs up), one from X (signs up), one direct
# who leaves at once, and a bot that must not count at all.
a = visitor("10.0.0.1"); visit(a, utm={"source": "instagram", "campaign": "derby"}, depth=100, sections=("proof", "engine", "record", "costs", "close"), form=True)
b = visitor("10.0.0.2", DESK); visit(b, utm={"source": "instagram", "campaign": "derby"}, depth=50, sections=("proof",))
x = visitor("10.0.0.3"); visit(x, ref="https://t.co/abc", depth=75, sections=("proof", "engine"), form=True)
d = visitor("10.0.0.4"); visit(d)
bot = visitor("10.0.0.5", "Mozilla/5.0 (compatible; Googlebot/2.1)"); bot.post("/api/analytics/collect", json={"name": "page_view", "path": "/waitlist"})

r = a.post("/api/newsletter/subscribe", json={"email": "ig@example.com", "consent": True, "name": "Ana", "source": "waitlist",
                                               "utm": {"source": "instagram", "campaign": "derby"}, "ref": "https://l.instagram.com/"})
check(r.status_code == 200, "a waitlist sign-up with its source is accepted")
x.post("/api/newsletter/subscribe", json={"email": "x@example.com", "consent": True, "source": "waitlist", "ref": "https://t.co/abc"})
row = db.newsletter.find_one({"email": "ig@example.com"})
check(row["attrib"]["source"] == "instagram" and row["attrib"]["campaign"] == "derby", "the list row keeps where the sign-up came from")
# The same address again from somewhere else: the first source keeps the credit.
a.post("/api/newsletter/subscribe", json={"email": "ig@example.com", "consent": True, "source": "waitlist", "ref": "https://t.co/zzz"})
check(db.newsletter.find_one({"email": "ig@example.com"})["attrib"]["source"] == "instagram", "a second sign-up does not move the credit (first touch)")
# Do Not Track: the sign-up still counts, its source is not kept.
dn = visitor("10.0.0.6"); dn.headers.update({"dnt": "1"})
dn.post("/api/newsletter/subscribe", json={"email": "quiet@example.com", "consent": True, "source": "waitlist", "utm": {"source": "tiktok"}})
check("attrib" not in db.newsletter.find_one({"email": "quiet@example.com"}), "under Do Not Track no source is stored with the sign-up")
bare = [e for e in db.events.find({"name": "waitlist_signup"}) if not e.get("utm") and not e.get("ref_host")]
check(len(bare) == 1 and not db.events.find_one({"name": "waitlist_signup", "utm.source": "tiktok"}),
      "...and its sign-up event is counted but carries neither the tag nor the referrer")
# The footer form is not the waitlist and writes no waitlist event.
before = db.events.count_documents({"name": "waitlist_signup"})
d.post("/api/newsletter/subscribe", json={"email": "foot@example.com", "consent": True})
check(db.events.count_documents({"name": "waitlist_signup"}) == before, "a footer sign-up is not counted as a waitlist sign-up")

rep = WS.report(db, 30)
t = rep["totals"]
check(t["views"] == 4 and t["visitors"] == 4, f"four visits from four visitors; the bot is not one of them ({t['views']}, {t['visitors']})")
check(t["signups"] == 3, f"three people signed up; pressing the button twice is one sign-up ({t['signups']})")
check(abs(t["conversion"] - 0.75) < 1e-9, "the sign-up rate is sign-ups over visitors")
depth = {s["depth"]: s for s in rep["scroll"]}
check(depth[25]["visitors"] == 3 and abs(depth[50]["share"] - 0.75) < 1e-9 and depth[100]["visitors"] == 1,
      "scroll depth is the share of visitors who got at least that far")
sec = {s["section"]: s["visitors"] for s in rep["sections"]}
check(sec == {"proof": 3, "engine": 2, "record": 1, "costs": 1, "close": 1}, f"sections reached are counted per visitor: {sec}")
fun = [f["count"] for f in rep["funnel"]]
check(fun == [4, 3, 2, 3], f"the funnel reads visited, read half, started the form, signed up: {fun}")
src = {s["source"]: s for s in rep["sources"]}
check(src["instagram"]["visitors"] == 2 and src["instagram"]["signups"] == 1, "Instagram brought two visitors and one sign-up")
check(src["x"]["visitors"] == 1 and src["x"]["signups"] == 1, "X brought one visitor and one sign-up")
check(src["direct"]["visitors"] == 1, "the visit with no tag and no referrer is direct")
camp = {c["campaign"]: c for c in rep["campaigns"]}
check(camp["derby"]["visitors"] == 2 and camp["derby"]["signups"] == 1, "a campaign tag is reported on its own")
check(rep["devices"] == {"mobile": 3, "desktop": 1}, f"devices are split per visitor: {rep['devices']}")
check(t["live"] == 4, "everyone visited in the last half hour, so all four are 'right now'")
check(TestClient(srv.app).get("/api/admin/waitlist/analytics").status_code in (401, 403), "the dashboard is not open to the public")

# ---------------------------------------------------------------- the saved design
try:
    AD.normalise({"template": "faceoff"}); check(False, "a Head to head with no match is refused")
except AD.AdError:
    check(True, "a Head to head with no match is refused")
n = AD.normalise({"template": "faceoff", "match_id": "m1", "stat": "shots; drop", "players": ["p1", "p2", "p3"]})
check(n["stat"] == "" and n["players"] == ["p1", "p2"], "a malformed market is dropped and only two players are kept")
n = AD.normalise({"template": "results", "day": "13/11/2026"})
check(n["day"] == "", "a day that is not YYYY-MM-DD is dropped")
check({"faceoff", "verdict", "results"} <= {t["id"] for t in AD.catalogue()["templates"]}, "the three match ads are in the catalogue")

# ---------------------------------------------------------------- the ads' data, on the demo league
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import demo_server as DSV                               # noqa: E402
import ad_sources as AS                                 # noqa: E402
import settings_store as S                              # noqa: E402
ddb = DSV.build()
ms = AS.matchups(ddb)
check(len(ms) > 0 and all(m["home"] and m["away"] for m in ms), f"upcoming matches with lines on both sides are listed ({len(ms)})")
mu = AS.matchup(ddb, ms[0]["match_id"])
cap = float(S.get(ddb, "engine.feed_max_p"))
for side in ("home", "away"):
    cs = mu[side]["candidates"]
    check(len(cs) > 0, f"the {side} side has candidates")
    check(all((c["team_iid"] == mu["home_iid"]) == (side == "home") for c in cs), f"every {side} candidate plays for the {side} side")
    check(all(len({l["stat"] for l in c["lines"]}) == len(c["lines"]) <= 3 for c in cs), "at most three lines per player, one per market")
    check(all(c["lines"] == sorted(c["lines"], key=lambda l: -l["p"]) for c in cs), "a player's lines are strongest first")
    check(cs == sorted(cs, key=lambda c: -c["score"]), "players are ranked by their best line")
    check(all(l["p"] <= cap for c in cs for l in c["lines"]) or any(l["p"] > cap for c in cs for l in c["lines"][:1]),
          "lines over the feed ceiling only appear when a player has nothing under it")
st = mu["stats"][0]
one = AS.matchup(ddb, ms[0]["match_id"], st)
check(all(l["stat"] == st for s in ("home", "away") for c in one[s]["candidates"] for l in c["lines"]), "with a market picked, every line is that market")
check(AS.matchup(ddb, "no-such-match") is None, "an unknown match is None, which the route turns into a 404")

# Score one past round from the real simulated stats, as the morning job would.
now = dt.datetime.now(dt.timezone.utc)
utc = lambda k: k if k.tzinfo else k.replace(tzinfo=dt.timezone.utc)
last = {}
for m in sorted(ddb.matches.find({"status": "final"}), key=lambda m: utc(m["kickoff"]), reverse=True):
    for sd in ("home_iid", "away_iid"):
        last.setdefault(m[sd], m)
for f in list(ddb.forecasts.find({"is_current": True, "scope": "player", "tier": {"$in": list(AS.TIERS)}, "p": {"$gte": AS.FLOOR}})):
    m = last.get(f["team_iid"])
    r = ddb.player_match_stats.find_one({"match_iid": m["iid"], "player_iid": f["player_iid"]})
    fid = uuid.uuid4().hex
    ddb.forecasts.insert_one({**{k: v for k, v in f.items() if k != "_id"}, "id": fid, "fkey": f["fkey"] + ":past", "match_iid": m["iid"],
                              "opp_iid": m["away_iid"] if m["home_iid"] == f["team_iid"] else m["home_iid"], "kickoff": m["kickoff"], "is_current": False})
    act = float((r or {}).get(f["stat"]) or 0)
    ddb.forecast_outcomes.insert_one({"forecast_id": fid, "fkey": f["fkey"] + ":past", "league_iid": f["league_iid"], "stat": f["stat"], "scope": "player",
                                      "tier": f["tier"], "p": f["p"], "thr": f["thr"], "actual": act, "reached": act > f["thr"],
                                      "player_played": r is not None, "scored_at": now})
sd = AS.settled(ddb, limit=10)
check(sd["n"] > len(sd["rows"]) == 10, f"the day's count covers every scored line, not just the rows returned ({sd['n']} vs {len(sd['rows'])})")
eligible = {"player_played": True, "p": {"$gte": AS.FLOOR}, "tier": {"$in": list(AS.TIERS)}}
check(sd["n"] == ddb.forecast_outcomes.count_documents(eligible), "n is every published line scored that day where the player played")
check(sd["came_in"] == ddb.forecast_outcomes.count_documents({**eligible, "reached": True}), "came_in is the whole day's hits")
check(ddb.forecast_outcomes.count_documents({"player_played": False}) > 0, "...and the day did include lines on players who never came on, which n leaves out")
full = AS.settled(ddb, limit=500)
check(any(not r["reached"] for r in full["rows"]) and any(r["reached"] for r in full["rows"]), "hits and misses are both returned")
check(all("actual" in r and r["player"] for r in full["rows"]), "every row carries what happened and who it was about")
lead = []
for r_ in full["rows"]:
    if r_["player"]["id"] in lead:
        break
    lead.append(r_["player"]["id"])
check(len(lead) == len({r_["player"]["id"] for r_ in full["rows"]}), "each player's leading line comes before anyone's second line")
check(full["rows"][0]["p"] <= cap, "the day does not open on a line above the feed ceiling")
check(AS.settled(ddb, day="1999-01-01")["day"] == sd["day"], "an unknown day falls back to the latest one")
print("selftest_waitlist_ads: all checks passed")
