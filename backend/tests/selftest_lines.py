"""selftest_lines.py -- forecasts fitted to each player and team, normalised averages, referees (docs/25).

Proves: automatic lines differ by player and team (no single "12+ shots / 5+ corners" for everyone) and stay inside
the likelihood band; labels are built for any line; likely starters can be Solid or Strong before the lineup, others
say "Watch until lineups are out"; every forecast carries its usual number and the lift over it, total goals included; player lines are \"if he plays\" with a lineup badge, and that badge is read off how many of his club's last matches he
started rather than off a chance-to-play gate he could never reach (docs/59); the feed ranks by
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
# v8: when a band keeps nothing, one row still survives as a ladder CARRIER so the Finder can
# answer the lines the band dropped (engine_bridge.select_lines). It is not a published line --
# NOT_HIDDEN keeps it off every screen, score_finished out of the record, live_track off the
# ticker -- so what this has always guarded still holds: nothing READABLE is kept, and in
# particular the ambitious end is not resurrected.
none_kept = B.select_lines(kane, [0.99, 1.0], 3)
check([d for d in none_kept if not d.get("carrier")] == [],
      "a band nothing reaches publishes nothing, rather than falling back to the ambitious end")
check(len(none_kept) == 1 and none_kept[0].get("carrier") and none_kept[0].get("ladder")
      and none_kept[0]["thr"] == 0.5 and none_kept[0]["tier"] is None,
      "...but one unreadable carrier keeps the ladder, so the Finder still has an answer")
# equally likely lines: the more ambitious one is worth more
tie = [{"scope": "player", "team_iid": 1, "player_iid": 8, "stat": "sot", "thr": t, "p": 0.8} for t in (0.5, 1.5)]
check([d["thr"] for d in B.select_lines(tie, [0.5, 0.99], 1)] == [1.5], "of two equally likely lines, the more ambitious is kept")

# --- the band is per MARKET, because the markets are not equally common ------------------------
# A player taking 1.5 shots a game is 74% to have one and 43% to put one on target, so a single
# floor keeps his shots line and deletes his on-target line -- measured on the demo league,
# on-target survives the 0.5 floor on 12% of player stat-groups against 53% for shots, which is
# why most cards have only one market available to lead whatever engine.position_weights says.
# And a rare market cannot be offered at all: a striker's 1+ goal is 30-45%, every rung of a goals
# ladder falls below 0.5, and the whole market is stored as an invisible carrier.
_sot = [{"scope": "player", "team_iid": 1, "player_iid": 5, "stat": "sot", "thr": t, "p": p_}
        for t, p_ in ((0.5, 0.43), (1.5, 0.18), (2.5, 0.06))]
_sh = [{"scope": "player", "team_iid": 1, "player_iid": 5, "stat": "shots", "thr": t, "p": p_}
       for t, p_ in ((0.5, 0.74), (1.5, 0.45), (2.5, 0.20))]
_one = B.select_lines(_sot + _sh, [0.5, 0.985], 3)
check([d["stat"] for d in _one if not d.get("carrier")] == ["shots"],
      "one band for all: his on-target market is a carrier and only shots can lead")
_per = B.select_lines(_sot + _sh, [0.5, 0.985], 3, {"player": {"sot": [0.4, 0.985]}})
_vis = sorted(d["stat"] for d in _per if not d.get("carrier"))
check(_vis == ["shots", "sot"], f"a floor of 0.4 for on-target puts the market on the card ({_vis})")
check(all(d["p"] >= 0.5 for d in _per if not d.get("carrier") and d["stat"] == "shots"),
      "...and shots keeps its own band: the override is per market, not a global loosening")
check(B.band_for([0.5, 0.985], {"player": {"sot": [0.4, 1.0]}}, "team", "sot") == (0.5, 0.985),
      "scope is part of the key: a player override does not move the team market")
check(B.band_for([0.5, 0.985], {}, "player", "sot") == (0.5, 0.985)
      and B.band_for([0.5, 0.985], None, "player", "sot") == (0.5, 0.985),
      "an empty override is exactly today's behaviour")

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
# Carriers sit outside the band by definition -- that is why they exist -- and are never shown,
# so every assertion below about what the product publishes excludes them.
rows = list(db.forecasts.find({"carrier": {"$ne": True}}, {"_id": 0, "contrib": 0}))
carriers = db.forecasts.count_documents({"carrier": True})
check(all(not (float(band_chk[0]) <= c["p"] <= float(band_chk[1])) for band_chk in [S.get(db, "engine.line_band")]
          for c in db.forecasts.find({"carrier": True}, {"p": 1})),
      f"{carriers} ladder carriers, every one of them outside the band -- which is why it was dropped")
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
# The tier grades the NUMBER. It used to grade p x p_play, so a likely starter could not be Strong
# and an unsure one could not be Solid whatever his number was -- which, with every feed admitting
# Strong and Solid only, took the best players off Today and Insights until the lineup was out.
# Whether he starts is the lineup badge's question, and the minutes row under the strip answers it
# again. Asking it a third time inside the tier only broke the tier.
so_min, s_min = float(S.get(db, "engine.solid_min")), float(S.get(db, "engine.strong_min"))
wrong = [(r["p"], r["tier"], r["lineup_badge"]) for r in pre
         if r["tier"] in ("Strong", "Solid") and r["p"] < so_min - 1e-9]
check(not wrong, f"Strong and Solid are read off the number shown, not off a discounted one: {wrong[:3]}")
check(any(r["tier"] in ("Strong", "Solid") for r in plain) or not plain,
      "a player whose lineup is not settled can still reach Solid on his number alone")
# This used to look for BOTH badges among the Solid and Strong rows. Since docs/59 the badge is
# read off the player's record of starting, and almost every published regular is correctly
# "likely", so finding one badge there no longer means the tier is sorting on it -- the test could
# only fail for the right reason by accident. The guarantee itself is checked twice instead: the
# line above (a player the lineup gate does not pass still reaches Solid) and the docs/59 section
# below, which runs the league with the badge rule off and on and compares every tier.
# A whitelist of exact sentences needs editing every time a note is added, which is how it missed the one docs/48
# introduced ("Solid once the lineup is confirmed", on a line held back by the chance to play rather than by the
# lineup rule). Match the shapes instead.
import re as _re
OK_NOTE = (None, "Held at Solid until our record on these lines is measured",
           "A small step from their usual game", "The likely range still reaches their usual")
_SHAPES = (r"^Similar lines happened \d+% of the time$", r"^Under \d+%, where Solid starts$")
# The three lineup notes are gone with the lineup caps that produced them. A note that explains a
# demotion the product no longer makes would be a card apologising for nothing.
gone = [r["tier_note"] for r in pre if r["tier_note"] and ("lineup" in r["tier_note"] or "bench" in r["tier_note"].lower())]
check(not gone, f"no card still blames the lineup for its tier: {sorted(set(gone))[:3]}")
bad = [r["tier_note"] for r in pre
       if r["tier_note"] not in OK_NOTE and not any(_re.match(x, str(r["tier_note"])) for x in _SHAPES)]
check(not bad, f"every card can say why it is not a better tier: {sorted(set(bad))[:3]}")
# Watch is the absence of a promise, and the number beside it does not say which absence -- "73%,
# Watch" reads as the card contradicting itself. Strong and Solid may stay silent; Watch may not.
mute = [r["fkey"] for r in pre if r["tier"] == "Watch" and not r["tier_note"]]
check(not mute, f"every Watch line says why it is Watch ({len(mute)} silent)")
reasons = collections.Counter(r["reasons"][0] for r in pre if r["reasons"])
check(len(reasons) >= 2, f"player cards do not all share one sentence ({len(reasons)} different first reasons)")

# The opponent can only reach a player through his team's total (docs/54), so "how far above his
# usual" is a CLUB-level quantity: within one club and one stat, every player's departure is the
# same number. It was not, because `p` was his share of a normalised team total while `p_usual` was
# his raw per-90 rate, separately shrunk -- two estimators of one thing, so each player carried a
# fixed personal offset on top of the fixture. Measured before the fix, the share of departure
# variance that was genuinely the fixture ran 91% (shots), 95% (tackles) and 59% (sot).
# scripts/measure/departure_calibration.py is the standing check.
import numpy as _np
_dep = collections.defaultdict(list)
for r in rows:
    if r["scope"] == "player" and r.get("expected") and r.get("expected_usual"):
        _dep[(r["team_iid"], r["match_iid"], r["stat"])].append(
            float(_np.log(r["expected"] / r["expected_usual"])))
_spread = [float(_np.std(v)) for v in _dep.values() if len(v) > 1]
check(_spread and max(_spread) < 1e-9,
      f"one club, one market, one departure: within-club sd {max(_spread) if _spread else -1:.2e} over {len(_spread)} clubs")

print('[player lines are "if he plays", with a lineup badge (docs/27)]')
pl_rows = [r for r in rows if r["scope"] == "player"]
check(all(r["p_basis"] == "played" for r in pl_rows) and all(r["p_basis"] == "all" and r["lineup_badge"] is None for r in rows if r["scope"] == "team"),
      "player forecasts are marked 'if he plays'; team forecasts are not")
# docs/59: the badge is read off his record of starting. The share is a necessary condition for
# "Likely lineup" and a sufficient one for "Lineup not sure" -- a stated doubt or a run of missed
# club matches can only ever lower it, never raise it -- so both directions are checked here.
_share = float(S.get(db, "engine.starter_start_share"))
_rec = [r for r in pl_rows if r["lineup_badge"] in ("likely", "unsure")]
check(_rec and all(r.get("club_recent") for r in _rec),
      f"every pre-lineup player card carries the record its badge was read off ({len(_rec)} of them)")
check(all(r["starts_recent"] / r["club_recent"] >= _share for r in _rec if r["lineup_badge"] == "likely"),
      f"badge before lineups: Likely lineup only once he has started {_share:.0%} of his club's last matches")
check(all(r["lineup_badge"] == "unsure" for r in _rec if r["starts_recent"] / r["club_recent"] < _share),
      "...and a player who started fewer than that is always Lineup not sure")
check(all(r["p_play"] >= 0.5 for r in pl_rows), "a player unlikely to play gets no card")
check(all(r["lineup_badge"] in ("likely", "unsure", "confirmed", "bench") for r in pl_rows),
      "every player line carries a lineup badge, which is where the start question is answered")

print("[Likely lineup is read off his record of starting (docs/59)]")
# The badge used to be `p_play >= engine.likely_starter_p` (0.85), and that gate was unreachable.
# `p_play` comes from the absence model, whose input is a recency-weighted start rate with a
# Laplace prior: at half-life 12 sum(w) converges to 17.83, so ps <= 18.83/19.83 = 0.9496 even for
# a player who started EVERY game, and ABSENCE_START turns that into p_play <= 0.8812. The gate
# therefore sat at 96% of the achievable maximum and asked for about 97.6% of recent games started.
# Measured on this demo league 48 hours out: 43 of 85 player cards read "Lineup not sure", among
# them a player who had started NINE of his club's last ten and three who had started all ten.
#
# So the badge now asks what the owner asked for, and what the ten-game strip under it already
# shows: of his club's last N matches, what share did he start.
SB = B.starter_badge
def sb(k, n, missed=0, doubtful=False, enabled=True, fallback="unsure"):
    return SB(k, n, missed, doubtful, enabled=enabled, share=0.6, max_missed=1, fallback=fallback)
check(sb(6, 10) == "likely" and sb(8, 10) == "likely" and sb(10, 10) == "likely",
      "started 6 or more of his club's last 10: Likely lineup")
check(sb(5, 10, fallback="likely") == "unsure" and sb(2, 10, fallback="likely") == "unsure",
      "started 5 of 10 or fewer: Lineup not sure -- a rotation player, whatever the old gate said")
check(sb(10, 10, missed=1) == "likely" and sb(10, 10, missed=2, fallback="likely") == "unsure",
      "one missed club match is ordinary rotation; a run of two is how an unannounced absence looks")
check(sb(10, 10, doubtful=True, fallback="likely") == "unsure",
      "the feed or the admin says Doubtful: Lineup not sure, however good the record")
check(sb(2, 10, enabled=True, fallback="likely") == "unsure" and sb(2, 10, enabled=False, fallback="likely") == "likely",
      "setting off: the old chance-to-play rule comes back, untouched")
# A record we cannot READ is never an answer. It falls back to the old gate, both ways, because
# "no record" must not quietly mean "every player in this league is a doubt" -- which is the trap
# the unmapped `minutes` key has already sprung twice (see engine_bridge.build_frames).
for _k, _n in ((None, None), (None, 10), (0, 0), (3, 0), (3, None)):
    check(sb(_k, _n, fallback="likely") == "likely" and sb(_k, _n, fallback="unsure") == "unsure",
          f"no readable record ({_k} of {_n}): the badge falls back to the chance-to-play gate, both ways")

# ...and the engine is what decides whether the record is readable, from the DATA it holds.
_ms2, _tg2, _pg2, _ap2, _diag2 = B.build_frames(db, lg["iid"], int(S.get(db, "engine.history_rounds")))
_as_of2 = int(_ms2["round"].max()) + 1
def _record(pgx, apx=None):
    e = B.configure_engine(db)
    e.fit(_ms2, _tg2, pgx, _as_of2, appearances=_ap2 if apx is None else apx)
    return {int(pid): (i.get("starts_recent"), i.get("club_recent")) for pid, i in e.pl.items()}
_base = _record(_pg2)
check(_base and all(n and k is not None for k, n in _base.values()),
      f"the demo league has a readable start record for all {len(_base)} players")
# A signing has no record of the matches played before he arrived, so the window starts at his
# first appearance for the club. Without that, a player who joined four matches ago and started
# every one of them reads 4 of 10 and is called a doubt for his first two months.
_w10 = sorted(_ms2["round"].unique())[-10:]
_ever = next(pid for pid, (k, n) in sorted(_base.items()) if (k, n) == (10, 10))
_cut = (_pg2["player"] == _ever) & (_pg2["round"].isin(_w10[:4]))
_ncut = (_ap2["player"] == _ever) & (_ap2["round"].isin(_w10[:4]))
_signing = _record(_pg2[~_cut].copy(), _ap2[~_ncut].copy())
check(_signing[_ever] == (6, 6),
      f"a player first seen four matches into the window is judged on those six, not charged for the four before he arrived: {_signing[_ever]}")
check(all(_signing[pid] == _base[pid] for pid in _base if pid != _ever),
      "...and trimming changes nothing for everyone who was there all along, so absences still count against them")
# `provider.pitchapi.player_keys.minutes.key` ships as null. The badge is read off STARTS exactly
# so that an unmapped minutes column cannot reach it. Prove it: all-null and all-zero minutes.
_null = _pg2.copy(); _null["minutes"] = np.nan
_zero = _pg2.copy(); _zero["minutes"] = 0.0
check(_record(_null) == _base, "minutes all null (unmapped provider key): every start record unchanged, not blank")
check(_record(_zero) == _base, "minutes all zero (mapped but never sent): every start record unchanged, not blank")
# `started` is the column the badge DOES read, and it comes from the lineups endpoint, so a league
# without that coverage reports eleven substitutes a side. That has to read as "no record" -- the
# same shape of bug as the unmapped minutes key, one column over.
_nolu = _pg2.copy(); _nolu["started"] = 0
check(all(k is None and n is None for k, n in _record(_nolu).values()),
      "lineups not covered (started never set): no readable record, so the badge falls back rather than calling the whole league a doubt")
_gap = _pg2[~_pg2["round"].isin(sorted(_ms2["round"].unique())[-10:])].copy()
check(all(k is None and n is None for k, n in _record(_gap).values()),
      "a provider gap over the whole window: no readable record, again a fallback and not a league of doubts")
# And the outer guard that means the badge is never even asked: a league whose minutes column is
# empty is skipped before any forecast is written.
_saved = [(d["match_iid"], d["player_iid"], d.get("minutes"))
          for d in db.player_match_stats.find({}, {"match_iid": 1, "player_iid": 1, "minutes": 1})]
db.player_match_stats.update_many({}, {"$set": {"minutes": None}})
_blank = B.build_frames(db, lg["iid"], int(S.get(db, "engine.history_rounds")))
check(_blank[4]["blank_columns"] == ["minutes"] and len(_blank[2]) == 0,
      "a league with no minutes at all is caught upstream, by name, and writes no player forecast")
for _mi, _pi, _v in _saved:
    db.player_match_stats.update_one({"match_iid": _mi, "player_iid": _pi}, {"$set": {"minutes": _v}})

# The whole league, with the rule off and on. The badge is a DISPLAY signal: the tier grades the
# percentage alone (tiering.py), engine.min_p_play still decides on the chance to play whether a
# card exists at all, and neither may move when the badge does.
S.put(db, "engine.starter_from_record", False)
B.run_league(db, lg["iid"], now=now)
_off = {r["fkey"]: r for r in db.forecasts.find({"scope": "player"}, {"_id": 0, "contrib": 0})}
S.put(db, "engine.starter_from_record", True)
B.run_league(db, lg["iid"], now=now)
_on = {r["fkey"]: r for r in db.forecasts.find({"scope": "player"}, {"_id": 0, "contrib": 0})}
check(set(_off) == set(_on), f"the same cards exist either way: {len(_off)} off, {len(_on)} on")
check(all(_off[k]["tier"] == _on[k]["tier"] for k in _off), "...with the same tier on every one of them")
check(all(_off[k]["tier_basis"] == _on[k]["tier_basis"] and _off[k]["tier_note"] == _on[k]["tier_note"] for k in _off),
      "...the same tier basis and the same note")
check(all(abs(_off[k]["p"] - _on[k]["p"]) < 1e-12 and abs(_off[k]["p_play"] - _on[k]["p_play"]) < 1e-12 for k in _off),
      "...and the same percentage and chance to play: only the badge moved")
_pre = [k for k in _off if _off[k]["state"] == "pre"]
check(not [k for k in _pre if _off[k]["lineup_badge"] == "likely" and _on[k]["lineup_badge"] == "unsure"],
      "no player the old gate called a likely starter is demoted by his record")
_bar = float(S.get(db, "engine.starter_start_share"))
# docs/62: the badge is decided on the share the engine actually used, which is the RECENCY-WEIGHTED
# one when engine.starter_half_life is set and the flat pair otherwise. These two checks used to
# read the flat ratio, and that stopped being the rule the badge follows.
def _share(k):
    r = _on[k]
    return float(r["starts_share"]) if r.get("starts_share") is not None else r["starts_recent"] / r["club_recent"]
def _flat(k):
    return _on[k]["starts_recent"] / _on[k]["club_recent"]

_moved = [k for k in _pre if _off[k]["lineup_badge"] == "unsure" and _on[k]["lineup_badge"] == "likely"]
check(_moved and all(_share(k) >= _bar for k in _moved),
      f"{len(_moved)} lines move to Likely lineup, every one of them a player who starts for his club")
_still = [k for k in _pre if _on[k]["lineup_badge"] == "unsure"]
check(all(_share(k) < _bar for k in _still),
      f"{len(_still)} lines stay Lineup not sure, every one of them under the bar on the record the badge reads")

# And the point of weighting it: the two records disagree, and the disagreement is the finding.
# A player who has started 6 of his club's last 10 but not the RECENT ones is drifting out of the
# side, and the flat count cannot tell him from one who is drifting into it.
_drift = [k for k in _still if _flat(k) >= _bar]
check(all(_share(k) < _bar <= _flat(k) for k in _drift),
      f"{len(_drift)} lines are a doubt despite a flat record at or above the bar, because the recent matches were not starts")
if _drift:
    _k = _drift[0]
    check(_on[_k]["starts_share"] is not None and _on[_k]["starts_recent"] == 6 and _on[_k]["club_recent"] == 10,
          f"...e.g. started 6 of the club's last 10, but weighted that reads {_share(_k):.0%}, under the {_bar:.0%} bar")
check(all(_on[k].get("starts_share") is not None for k in _pre if _on[k].get("club_recent")),
      "every readable record carries the weighted share beside the countable pair")
check(len(_still) < len([k for k in _pre if _off[k]["lineup_badge"] == "unsure"]) / 2,
      "pre-lineup doubt is no longer the majority verdict: "
      f"{len([k for k in _pre if _off[k]['lineup_badge'] == 'unsure'])} of {len(_pre)} -> {len(_still)} of {len(_pre)}")

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
# DERIVED FROM THE SETTINGS, AND NON-EMPTY. Two faults, both of which this hit:
#
#   * `thr <= {...}` is True for the empty set, so this passed if `run_league` published NOTHING --
#     the exact failure it exists to catch. `thr and` fixes that.
#   * the set was written out by hand, so it broke the moment a market was added. It just did:
#     registering saves, fouls and goal involvements in `MARKET_COVERAGE` (docs/90) made this league
#     publish `player.goal_involvements` lines as well, which is the fix working. A test that has to
#     be edited every time the product gains a market is a test that gets edited carelessly.
#
# What the check actually means is "with auto lines off, every line sits on one of the thresholds
# the owner configured", so it reads them from the settings and says exactly that.
fixed = {("player", st, t) for st, ts in S.get(db, "engine.player_thresholds").items() for t in ts}
fixed |= {("team", st, t) for st, ts in S.get(db, "engine.team_thresholds").items() for t in ts}
check(bool(thr) and thr <= fixed, f"auto lines off: every line is on a configured threshold ({len(thr)} lines)")
check(("player", "goal_involvements", 0.5) in thr,
      "...and the goal involvements market now publishes, having been dropped by the market gate")
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
