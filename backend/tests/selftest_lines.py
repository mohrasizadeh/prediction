"""selftest_lines.py -- forecasts fitted to each player and team, normalised averages, referees (docs/25).

Proves: automatic lines differ by player and team (no single "12+ shots / 5+ corners" for everyone) and stay inside
the likelihood band; labels are built for any line; likely starters can be Solid or Strong before the lineup, others
say "Watch until lineups are out"; every forecast carries its usual number and the lift over it, total goals included; player lines are \"if he plays\" with a lineup badge; the feed ranks by
that lift, never leads with a near-certain line, and the old order is one setting away; team averages are recency-
weighted, opponent-judged and capped; one wild match moves a referee's normalised number far less than his plain
average; the match page carries the referee line; the daily job writes referee_stats.
"""
import os, sys, base64, collections, datetime as dt
os.environ.setdefault("APP_ENCRYPTION_KEY", base64.b64encode(os.urandom(32)).decode())
HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("SOCCER_BRAIN_DIR", os.path.join(HERE, "soccer_brain"))
sys.path.insert(0, HERE); sys.path.insert(0, os.environ["SOCCER_BRAIN_DIR"])
import httpx, mongomock
import numpy as np, pandas as pd
import engine_bridge as B, ingest as I, mongo_init, queries as Q, referees as RF, security, settings_store as S
import engine as E
from cached_fetch import PitchClient
from fake_pitchapi import PLAYER_KEYS, TEAM_KEYS, FakePitch
from simulate import simulate_league


def check(c, m):
    if not c:
        print("  FAIL", m); sys.exit(1)
    print("  ok  ", m)


print("[labels and line selection]")
check(B.label_for(None, "player", "shots", 0.5, {}) == "1+ shot" and B.label_for(None, "player", "shots", 3.5, {}) == "4+ shots",
      "labels are built: 1+ shot, 4+ shots")
check(B.label_for(None, "team", "corners", 6.5, {}) == "7+ corners" and B.label_for(None, "player", "sot", 1.5, {}) == "2+ shots on target",
      "team corners and shots on target read naturally")
check(B.label_for(None, "team", "shots", 11.5, {"team_shots:11.5": "12+ team shots"}) == "12+ team shots", "an admin label still wins")
docs = [{"scope": "player", "team_iid": 1, "player_iid": 7, "stat": "shots", "thr": t, "p": p}
        for t, p in ((0.5, 0.97), (1.5, 0.88), (2.5, 0.71), (3.5, 0.55), (4.5, 0.38))]
kept = B.select_lines(docs, [0.5, 0.95], 3)
check(sorted(d["thr"] for d in kept) == [1.5, 2.5, 3.5], "exactly three sit inside this band, so all three are kept")
check(all(d["ladder"] == {"0.5": 0.97, "1.5": 0.88, "2.5": 0.71, "3.5": 0.55, "4.5": 0.38} for d in kept), "every kept line carries the whole ladder")

# When the band leaves more lines than we may keep, the LIKELIEST win -- not the most ambitious (docs/44).
# Reported: a striker's card read "4+ shots 52%, 5+ 40%, 6+ 26%" and his 1+ and 2+ lines were nowhere in the app.
kane = [{"scope": "player", "team_iid": 1, "player_iid": 9, "stat": "shots", "thr": t, "p": p}
        for t, p in ((0.5, 0.95), (1.5, 0.85), (2.5, 0.70), (3.5, 0.52), (4.5, 0.40), (5.5, 0.26))]
k = B.select_lines(kane, [0.05, 0.99], 3)
check(sorted(d["thr"] for d in k) == [0.5, 1.5, 2.5],
      f"the three most likely are kept (1+, 2+, 3+), not the three most ambitious: got {sorted(d['thr'] for d in k)}")
check(max(k, key=lambda d: d["p"])["thr"] == 0.5, "...so the near-certain 1+ shot leads the card, instead of being thrown away")
check(all(d["p"] >= 0.70 for d in k), "nothing below the three best survives when the band is wide open")
# the band, not the slice, is what decides how ambitious we get
tight = B.select_lines(kane, [0.5, 0.99], 3)
check(sorted(d["thr"] for d in tight) == [0.5, 1.5, 2.5], "raising the band floor does not change which three: it only removes long shots")
one = B.select_lines(kane, [0.9, 0.99], 3)
check([d["thr"] for d in one] == [0.5], "a floor above the rest of the ladder leaves just the one near-certain line")
check(B.select_lines(kane, [0.99, 1.0], 3) == [], "a band nothing reaches keeps nothing, rather than falling back to the ambitious end")
# equally likely lines: the more ambitious one is worth more
tie = [{"scope": "player", "team_iid": 1, "player_iid": 8, "stat": "sot", "thr": t, "p": 0.8} for t in (0.5, 1.5)]
check([d["thr"] for d in B.select_lines(tie, [0.5, 0.99], 1)] == [1.5], "of two equally likely lines, the more ambitious is kept")

print("[tiers]")
from core import tier
check(tier(0.82, 0.72, False) == "Watch" and tier(0.82, 0.72, True) == "Strong", "the tier rule itself is unchanged")

print("[engine run with automatic lines]")
db = mongomock.MongoClient()["lines"]; mongo_init.ensure_indexes(db)
security.save_provider_key(db, "pitchapi", "pk_test_zzzz")
S.put(db, "ingest.rps", 1000); S.put(db, "provider.pitchapi.team_keys", TEAM_KEYS); S.put(db, "provider.pitchapi.player_keys", PLAYER_KEYS)
S.put(db, "provider.position_map", {"0": "GK", "1": "DEF", "2": "MID", "3": "FWD"})
matches, tg, pg, _ = simulate_league(n_teams=10, seed=4)
n_final = int(matches["round"].max()) + 1 - 2
fake = FakePitch(matches, tg, pg, n_final)
c = PitchClient(db, http=httpx.Client(base_url="https://api.pitchapi.dev", transport=fake.transport()), sleep=lambda s: None)
I.sync_leagues(c); lg = db.leagues.find_one({}); I.sync_league_matches(c, lg, "2025/2026", "all"); I.process_queue(c)
I.assign_rounds(db, lg["iid"]); I.update_coverage(db, lg["iid"])
now = fake.kick(n_final) - dt.timedelta(hours=26)
B.run_league(db, lg["iid"], now=now)
rows = list(db.forecasts.find({}, {"_id": 0, "contrib": 0}))
band = S.get(db, "engine.line_band")          # read the setting: the upper end moved to the display cap (docs/39)
check(rows and all(float(band[0]) <= r["p"] <= float(band[1]) for r in rows),
      f"{len(rows)} forecasts, all inside the {band[0]:.0%}-{band[1]:.1%} band")
check(any(r["p"] > 0.95 for r in rows), "near-certain lines are kept, not discarded before they are stored (docs/39)")
# Since docs/44 the likeliest in-band lines are kept, so every team lands on the same low rungs of the ladder and
# it is the PERCENTAGE that tells them apart, not the threshold. That is the trade for never hiding a near-certain
# line; it is also how the statistics sites this app is measured against present a market.
team_shots = {r["thr"] for r in rows if r["scope"] == "team" and r["stat"] == "shots"}
check(len(team_shots) <= int(S.get(db, "engine.max_lines_per_stat")),
      f"team shot lines are a consistent market across teams: {sorted(team_shots)}")
tp = [r["p"] for r in rows if r["scope"] == "team" and r["stat"] == "shots" and r["thr"] == min(team_shots)]
check(len(set(round(p, 3) for p in tp)) > 1, f"...and the same line reads differently per team: {min(tp):.0%}-{max(tp):.0%}")
pl_shots = {r["thr"] for r in rows if r["scope"] == "player" and r["stat"] == "shots"}
check(len(pl_shots) >= 3, f"player shot lines differ by player: {sorted(pl_shots)}")
per = collections.Counter((r["scope"], r["team_iid"], r.get("player_iid"), r["stat"], r["match_iid"]) for r in rows)
check(max(per.values()) <= 3, "at most 3 lines per player (or team), stat and match")
check(all(r.get("p_usual") is not None and abs(r["edge"] - (r["p"] - r["p_usual"])) < 1e-9 for r in rows), "every forecast carries its usual number and the lift over it")
check(all(not r["market"].startswith(("0", "1.5")) and "+" in r["market"] for r in rows), "every line has readable words")
pre = [r for r in rows if r["scope"] == "player"]
likely = [r for r in pre if r["tier_basis"] == "likely_starter"]
plain = [r for r in pre if r["tier_basis"] == "pre"]
check(all(r["p_play"] >= 0.85 for r in likely) and all(r["p_play"] < 0.85 for r in plain), "likely starter = chance to play 85%+ before lineups")
check(all(r["tier"] != "Strong" for r in likely) and all(r["p"] * r["p_play"] >= 0.8 - 1e-9 for r in likely if r["tier"] == "Solid"), "likely starters are never Strong before lineups; Solid needs 80% whole chance (docs/31)")
check(all(r["tier"] in ("Watch", None) for r in plain), "other players stay at most Watch before lineups")
# A whitelist of exact sentences needs editing every time a note is added, which is how it missed the one docs/48
# introduced ("Solid once the lineup is confirmed", on a line held back by the chance to play rather than by the
# lineup rule). Match the shapes instead.
import re as _re
OK_NOTE = (None, "Watch until lineups are out", "On the bench: Watch only", "Held at Solid until our record on these lines is measured")
_SHAPES = (r"^(Strong|Solid) once the lineup is confirmed$", r"^Similar lines happened \d+% of the time$")
bad = [r["tier_note"] for r in pre
       if r["tier_note"] not in OK_NOTE and not any(_re.match(x, str(r["tier_note"])) for x in _SHAPES)]
check(not bad, f"every card can say why it is not a better tier: {sorted(set(bad))[:3]}")
check(any(str(r["tier_note"]).endswith("once the lineup is confirmed") for r in pre),
      "...and a line held back only by the chance to play says so, instead of leaving the reader to multiply (docs/48)")
reasons = collections.Counter(r["reasons"][0] for r in pre if r["reasons"])
check(len(reasons) >= 2, f"player cards do not all share one sentence ({len(reasons)} different first reasons)")

print('[player lines are "if he plays", with a lineup badge (docs/27)]')
pl_rows = [r for r in rows if r["scope"] == "player"]
check(all(r["p_basis"] == "played" for r in pl_rows) and all(r["p_basis"] == "all" and r["lineup_badge"] is None for r in rows if r["scope"] == "team"),
      "player forecasts are marked 'if he plays'; team forecasts are not")
check(all(r["lineup_badge"] == ("likely" if r["p_play"] >= 0.85 else "unsure") for r in pl_rows), "badge before lineups: Likely lineup at 85%+ chance to play, else Not sure")
check(all(r["p_play"] >= 0.5 for r in pl_rows), "a player unlikely to play gets no card")
check(all(r["tier"] in ("Watch", None) for r in pl_rows if r["lineup_badge"] == "unsure"), "Not sure players stay at most Watch")
S.put(db, "engine.condition_on_play", False)
B.run_league(db, lg["iid"], now=now)
old_rows = {r["fkey"]: r for r in db.forecasts.find({"scope": "player"}, {"_id": 0, "contrib": 0})}
S.put(db, "engine.condition_on_play", True)
B.run_league(db, lg["iid"], now=now)
new_rows = {r["fkey"]: r for r in db.forecasts.find({"scope": "player"}, {"_id": 0, "contrib": 0})}
both = [k for k in old_rows if k in new_rows]
check(both and all(old_rows[k]["p_basis"] == "all" for k in both), "switch off: the old all-in number comes back")
down = [k for k in both if new_rows[k]["p_model"] + 1e-9 < old_rows[k]["p_model"]]
check(not down, f"'if he plays' is never below the old number (chance to play only ever lowered it), {len(both)} lines compared")
lift = [new_rows[k]["p_model"] / max(old_rows[k]["p_model"], 1e-9) for k in both if old_rows[k]["p_play"] < 0.85]
check(not lift or float(np.median(lift)) > 1.05, "players with a real chance of missing the match rise the most")
rows = list(db.forecasts.find({}, {"_id": 0, "contrib": 0}))

print("[feed order]")
feed = Q.insights_feed(db, limit=500, tiers=("Strong", "Solid", "Watch"), now=now - dt.timedelta(hours=1))
fmax = float(S.get(db, "engine.feed_max_p"))     # the owner moved this to the display cap (docs/39)
check(all(f["p"] <= fmax or all(m["p"] > fmax for m in f["more_lines"]) for f in feed),
      f"a line above {fmax:.0%} only leads when no other line could")
check(any(f["p"] >= 0.90 for f in feed), "near-certain lines reach the feed and lead their card (docs/39)")
# v8: the order is the same measure that already decides which line LEADS a card (docs/46):
# market importance x position relevance x lift x stake. It used to be raw lift, which is
# market-blind and position-blind -- so a centre-back's tackles line with a big departure
# outranked a striker's shot line, and the feed contradicted the card sitting in it.
_W, _SC = S.get(db, "engine.market_weights"), S.get(db, "engine.lift_scale")
_PW = S.get(db, "engine.position_weights")
order = [(Q.CONFIDENT[f["tier"]], -Q.prominence(f, _W, _SC, _PW)) for f in feed]   # log-odds since docs/48
check(order == sorted(order), "default order: Strong and Solid together by what the line has to say, then Watch")
# The feed order and the card's lead line now answer to one measure. A forward's tackles line
# cannot out-rank his own shots line in the feed while losing to it inside the card.
fwd = [f for f in feed if f.get("pos") == "FWD" and f.get("stat") == "tackles"]
check(all(Q.prominence(f, _W, _SC, _PW) <= max([Q.prominence(m, _W, _SC, _PW) for m in f.get("more_lines") or []] or [0]) or not f.get("more_lines")
          for f in fwd) or not fwd, "a forward's tackles line does not lead the feed over a line that beats it on the card")
# the measure the ORDER uses must not be the one that favours whichever market sits mid-table (docs/48)
pts = [(Q.CONFIDENT[f["tier"]], -Q.lift(f, "points")) for f in feed]
check(pts != sorted(pts) or len(feed) < 3, "...and that is a different order from ranking on plain percentage points")
heads = [f for f in feed if f["tier"] in ("Strong", "Solid")]
# Since docs/46 the line that leads is the one with the most to say -- market importance x lift over usual x
# likelihood -- not simply the likeliest. "Mbappe 1+ shot" and "Benfica 7+ shots" are near certainties that are
# also entirely usual, and they were heading cards and dragging the feed's own lift sort down with them.
W = S.get(db, "engine.market_weights")
check(all(Q.prominence(f, W) >= max([Q.prominence({**m, "scope": f["scope"]}, W) for m in f["more_lines"]] or [0])
          for f in heads if f["p"] <= fmax),
      "headline: the line with the most to say leads the card, not the likeliest (docs/46)")
dull = [f for f in heads if (f.get("edge") or 0) <= 0.01 and any((m.get("edge") or 0) > 0.05 for m in f["more_lines"])]
check(not dull, f"no card is headed by a line that is exactly as usual while it holds one that is not: {len(dull)}")
check(all([m["p"] for m in f["more_lines"]] == sorted([m["p"] for m in f["more_lines"]], reverse=True) for f in feed),
      "other lines are listed most likely first")
lk = Q.insights_feed(db, limit=500, tiers=("Strong", "Solid", "Watch"), now=now - dt.timedelta(hours=1), sort="likely")
o2 = [(Q.TIER_RANK[f["tier"]], -f["p"]) for f in lk]
check(o2 == sorted(o2), "sort=likely gives the old order")

print("[old behaviour is one switch away]")
S.put(db, "engine.auto_lines", False)
B.run_league(db, lg["iid"], now=now)
thr = {(r["scope"], r["stat"], r["thr"]) for r in db.forecasts.find({}, {"_id": 0})}
check(thr <= {("team", "shots", 11.5), ("team", "corners", 4.5), ("player", "shots", 0.5), ("player", "shots", 1.5),
              ("player", "sot", 0.5), ("player", "tackles", 1.5), ("player", "tackles", 2.5)}, "auto lines off: the fixed thresholds again")
S.put(db, "engine.auto_lines", True)

print("[normalised team averages]")
ms, tgs, pgs, _ = simulate_league(n_teams=10, seed=4)
def style_shots(**kw):
    e = E.SoccerEngine(**kw)
    tg2 = tgs.copy()
    last = int(tg2["round"].max())
    i = tg2[(tg2["round"] == last)].index[0]
    tg2.loc[i, "shots"] = 60                                            # one wild game (or a feed error)
    e.fit(ms, tg2, pgs, last + 1)
    return float(e.snaps[last + 1][0][e.tidx[int(tg2.loc[i, "team"])], 0])
plain_v = style_shots(); capped = style_shots(style_cap_q=0.99)
check(capped < plain_v, f"a 60-shot game moves the team's average less when capped ({capped:.3f} vs {plain_v:.3f}, log scale)")
e1 = E.SoccerEngine(style_half_life=20, style_opp_adjust=("shots",), style_cap_q=0.99).fit(ms, tgs, pgs, int(ms["round"].max()) + 1)
check(np.isfinite(e1.snaps[int(ms["round"].max()) + 1][0]).all(), "recency + opponent + cap: a valid style for every team")

print("[referees]")
rows = []
t0 = dt.datetime(2025, 8, 1, tzinfo=dt.timezone.utc)
teams = list(range(10))
rng = np.random.default_rng(1)
k = 0
for wk in range(30):
    for j in range(5):
        h, a = teams[(j + wk) % 10], teams[(9 - j + wk) % 10]
        ref = f"Ref {j}"
        hy, ay = float(rng.poisson(1.8)), float(rng.poisson(2.0))
        rows.append({"referee": ref, "home": h, "away": a, "hy": hy, "ay": ay, "kickoff": t0 + dt.timedelta(days=7 * wk, minutes=j)})
rows.append({"referee": "New Ref", "home": 0, "away": 1, "hy": 5.0, "ay": 4.0, "kickoff": t0 + dt.timedelta(days=400)})
st, _ = RF.compute(rows)
nr = st["New Ref"]
check(nr["cards_per_game"] == 9.0 and nr["factor"] < 1.12, f"one 9-card match: plain average 9.0, normalised factor only {nr['factor']:.2f}")
check(all(0.7 < v["factor"] < 1.3 for v in st.values()), "every referee factor stays in a sane range")
check("treat this referee as average" in RF.sentence("New Ref", nr["factor"], nr["matches"]), "few matches: the sentence says we treat the referee as average")

dbr = mongomock.MongoClient()["refs"]; mongo_init.ensure_indexes(dbr)
dbr.leagues.insert_one({"iid": 1, "enabled": True})
for n, r in enumerate(rows):
    dbr.matches.insert_one({"iid": n, "id": f"m{n}", "ext_id": n, "league_iid": 1, "status": "final", "referee": r["referee"], "home_iid": r["home"], "away_iid": r["away"], "kickoff": r["kickoff"]})
    dbr.team_match_stats.insert_one({"match_iid": n, "team_iid": r["home"], "yellow": r["hy"]})
    dbr.team_match_stats.insert_one({"match_iid": n, "team_iid": r["away"], "yellow": r["ay"]})
res = RF.refresh(dbr, 1)
check(res["referees"] == 6 and dbr.referee_stats.count_documents({}) == 6, "referee_stats written for every referee")
line = RF.for_match(dbr, {"referee": "Ref 2", "league_iid": 1})
check(line and "sentence" in line and 0.7 < line["factor"] < 1.3, f"match page line: {line['sentence']}")
check(Q.referee_table(dbr, 1)[0]["matches"] >= 30, "the referees table reads the normalised rows")
print("ALL PASSED")
