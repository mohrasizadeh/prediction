"""selftest_combo_build.py -- the combo builder (docs/65).

Proves: the builder searches every match in a window, not one; it solves for the chance of the
WHOLE combo rather than a floor under each line, and it solves against combine() itself, so the
target it reports is the correlation-aware number and not a product of percentages; it never
builds on a player we are unsure will play; it never puts the same player in twice; it prefers
lines from different matches, because independent legs are the honest kind; pinned lines survive
the search; alternates are ranked by quality rather than by what flatters the number; and when the
window cannot answer, it says which constraint emptied it instead of returning a shrug.
"""
import os, sys, base64, datetime as dt
os.environ.setdefault("APP_ENCRYPTION_KEY", base64.b64encode(os.urandom(32)).decode())
HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("SOCCER_BRAIN_DIR", os.path.join(HERE, "soccer_brain"))
sys.path.insert(0, HERE); sys.path.insert(0, os.environ["SOCCER_BRAIN_DIR"])
import mongomock
import combo as CB, mongo_init, settings_store as S


def check(c, m):
    if not c:
        print("  FAIL", m); sys.exit(1)
    print("  ok  ", m)


db = mongomock.MongoClient()["cb"]; mongo_init.ensure_indexes(db)
now = dt.datetime(2026, 11, 10, 12, 0, tzinfo=dt.timezone.utc)
FAC = list(S.get(db, "combo.pre_factors"))


def line(i, *, match, player=None, team=1, stat="shots", p=0.8, badge="confirmed", lg=10,
         state="lineup", tier="Solid", edge=0.05, thr=0.5):
    return {"id": f"f{i}", "fkey": f"k{i}", "run_id": "r", "match_iid": match, "league_iid": lg,
            "kickoff": now + dt.timedelta(hours=3), "scope": "player" if player else "team",
            "team_iid": team, "opp_iid": team + 100, "player_iid": player, "pos": "F",
            "stat": stat, "thr": thr, "market": f"{int(thr) + 1}+ {stat}", "p": p, "lo": max(0.01, p - .06),
            "hi": min(.99, p + .06), "p_play": 1.0, "lineup_badge": badge, "tier": tier, "edge": edge,
            "state": state, "is_current": True, "hidden": False, "p_basis": "played"}


# five matches, four players each, a spread of likelihoods
docs, i = [], 0
for m in range(1, 6):
    for pl in range(1, 5):
        i += 1
        docs.append(line(i, match=m, player=m * 10 + pl, team=m, p=round(0.55 + 0.07 * pl, 2), lg=10 + (m % 2)))
# Two sentinels for the ranking test, in a match of their own. One is the better LINE -- confirmed,
# a real departure from the player's usual game, graded Strong -- but slightly less likely than the
# other, which is a near-truism on an unconfirmed starter. Ranking by what flatters the combo would
# put the truism first.
i += 1; GOOD = f"k{i}"; docs.append(line(i, match=6, player=601, team=6, p=0.70, badge="confirmed", tier="Strong", edge=0.22))
i += 1; MEH = f"k{i}";  docs.append(line(i, match=6, player=602, team=6, p=0.76, badge="likely", tier="Watch", edge=0.0))
# one doubtful starter, and one bench player, both of which must never be chosen
i += 1; docs.append(line(i, match=1, player=999, p=0.95, badge="unsure"))
i += 1; docs.append(line(i, match=1, player=998, p=0.95, badge="bench"))
# a second line on a player who already has one, to prove the same-player rule
i += 1; docs.append(line(i, match=1, player=11, stat="sot", p=0.7))
db.forecasts.insert_many(docs)
BY = {d["fkey"]: d for d in docs}          # names come from collections this test does not need,
ent = lambda fkey: CB._entity(BY[fkey])    # so identity is read off the source rows

# ---------------------------------------------------------------- 1. the pool
pool, tally = CB.candidates(db, within_h=24, now=now)
check(tally["read"] == len(docs), "the search reads every line in the window")
check(tally["lineup"] == 2, "a doubtful starter and a bench player are both refused")
check(all(d.get("lineup_badge") in ("confirmed", "likely") for d in pool), "nothing unsure survives into the pool")
check(tally["matches"] == 6, "and it searched every match in the window, not one")
narrow = CB.candidates(db, within_h=24, min_leg=0.8, now=now)[1]
check(narrow["below_floor"] > 0 and narrow["kept"] < tally["kept"], "a floor under each line narrows the pool")
check(CB.candidates(db, within_h=1, now=now)[1]["read"] == 0, "the window is a real filter")

# ---------------------------------------------------------------- 2. a target for the WHOLE combo
for target in (0.25, 0.4, 0.55):
    rep = CB.build(db, 3, target=target, within_h=24, now=now)
    got = rep["combined"]
    check(abs(got - target) <= 0.06, f"a 3-line combo aimed at {int(target*100)}% came back at {int(got*100)}%")
    # the headline number IS what combine() says about those lines -- not a product of their chances
    held = [d for d in docs if d["fkey"] in {l["fkey"] for l in rep["lines"]}]
    check(round(CB.combine(held, "p", FAC), 4) == got, "  and the number is combine()'s own, not a re-derivation")
    naive = 1.0
    for d in held:
        naive *= CB.chance(d)
    check(abs(naive - got) > 1e-6, "  and it differs from the plain product, which is the whole point")

# ---------------------------------------------------------------- 3. the rules the builder keeps
rep = CB.build(db, 4, target=0.3, within_h=24, now=now)
ents = [ent(l["fkey"]) for l in rep["lines"]]
check(len(ents) == len(set(ents)), "no player appears twice in a built combo")
check(len({l["match_iid"] for l in rep["lines"]}) > 1, "and it spreads across matches rather than stacking one")
check(rep["range"]["lo"] <= rep["combined"] <= rep["range"]["hi"], "the combo carries a range, not just a number")
check(rep["searched"]["kept"] and rep["searched"]["matches"],
      "the report says what was searched, so the waiting screen can show real work")

# pinned lines survive
keep = [rep["lines"][0]["fkey"]]
again = CB.build(db, 4, target=0.3, within_h=24, keep_fkeys=keep, now=now)
check(keep[0] in {l["fkey"] for l in again["lines"]}, "a pinned line is never swapped out")
drop = rep["lines"][1]["fkey"]
without = CB.build(db, 4, target=0.3, within_h=24, exclude=[drop], now=now)
check(drop not in {l["fkey"] for l in without["lines"]}, "a dropped line never comes back")

# ---------------------------------------------------------------- 4. honest failure
empty = CB.build(db, 3, min_leg=0.99, within_h=24, now=now)
check(not empty["lines"] and "99%" in empty["reason"],
      f"an impossible floor names the constraint that emptied it: {empty['reason']!r}")
far = CB.build(db, 4, target=0.9, within_h=24, now=now)
check(any("closest we could get" in n for n in far["notes"]),
      "a target the window cannot reach is said out loud, not quietly missed")
try:
    CB.build(db, 1, now=now); check(False, "n must be at least 2")
except CB.ComboError as e:
    check(e.code == "BAD_N", "one line is not a combination")
try:
    CB.build(db, 3, target=1.5, now=now); check(False, "a target over 95% is refused")
except CB.ComboError as e:
    check(e.code == "BAD_TARGET", "an impossible target is refused with its own code")

# ---------------------------------------------------------------- 5. alternates
base = CB.build(db, 3, target=0.4, within_h=24, now=now)
keys = [l["fkey"] for l in base["lines"]]
alt = CB.alternates(db, keys, keys[1], within_h=24, now=now, limit=50)   # the whole ranking, not its head
check(alt["current"] == base["combined"], "alternates start from what the combo is worth now")
check(alt["options"], "and offer something")
check(all(o["fkey"] not in keys for o in alt["options"]), "never offering a line already in the combo")
opts = alt["options"]
rank = [o["fkey"] for o in opts]
check(GOOD in rank and MEH in rank, "both sentinels are offered")
check(rank.index(GOOD) < rank.index(MEH),
      "a better line outranks a likelier one -- the list is ranked by quality, not by what flatters the number")
g = next(o for o in opts if o["fkey"] == GOOD); m = next(o for o in opts if o["fkey"] == MEH)
check(m["combined_if_swapped"] > g["combined_if_swapped"],
      "  even though taking the likelier one would show a bigger number")
check(all(o["combined_if_swapped"] is not None and o["delta"] is not None for o in opts),
      "every option says what the combo becomes, and by how much it moves")
held_ents = {ent(k) for k in keys if k != keys[1]}
check(not [o for o in opts if ent(o["fkey"]) in held_ents],
      "and never a player already holding another slot")

print("selftest_combo_build: all checks passed")
