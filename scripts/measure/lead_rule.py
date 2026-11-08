"""What does each lead rule put on the face of a card? (asked 2026-11-08)

`engine.lead_rule` chooses which of a card's lines leads it:

  prominence  the line with the most to say -- market weight x position weight x lift x stake.
              A near-certainty that is also usual carries no information, so it is demoted
              however high it reads (docs/46).
  confident   the strongest number the card can stand behind -- market weight x position
              weight x p.

The second is not a return to ranking on p, which is what docs/44 did and what produced the
"mbappe one shot is not a great insight" complaint. Both rules sit behind the same two guards in
group_cards: a line above `engine.feed_max_p` cannot lead while another line can, and nor can a
rung that reads the same against every opponent in the league (`engine.min_span`). Those two
remove the near-certain truism before either score is consulted. What this script measures is
what is left to choose between.

Read-only: builds its own simulated league and changes nothing.
Run: python scripts/measure/lead_rule.py
"""
import base64
import collections
import os
import statistics as st
import sys

os.environ.setdefault("APP_ENCRYPTION_KEY", base64.b64encode(os.urandom(32)).decode())
os.environ.setdefault("ADMIN_EMAIL", "owner@example.com")
os.environ.setdefault("ADMIN_INITIAL_PASSWORD", "demo-owner-pass-1")
HERE = "/home/user/prediction/backend"
os.environ.setdefault("SOCCER_BRAIN_DIR", os.path.join(HERE, "soccer_brain"))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "tests"))
sys.path.insert(0, os.environ["SOCCER_BRAIN_DIR"])

import queries as Q  # noqa: E402
import settings_store as S  # noqa: E402
from demo_server import build  # noqa: E402

db = build()
W = S.get(db, "engine.market_weights")
PW = S.get(db, "engine.position_weights")
SCALE = S.get(db, "engine.lift_scale")
MAXP = float(S.get(db, "engine.feed_max_p"))
SPAN = float(S.get(db, "engine.min_span"))

fc = list(db.forecasts.find({**Q.NOT_HIDDEN, "scope": "player"}, {"_id": 0, "contrib": 0}))
print(f"player forecasts: {len(fc)}   feed_max_p {MAXP}   min_span {SPAN}\n")

cards = {r: Q.group_cards(fc, MAXP, "player", W, SCALE, SPAN, PW, r) for r in Q.LEAD_RULES}
for r, cs in cards.items():
    print(f"{r:<12} {len(cs)} cards")
print()

print("1. THE NUMBER ON THE FACE OF THE CARD")
print(f"   {'rule':<12}{'min':>7}{'Q1':>7}{'median':>8}{'Q3':>7}{'max':>7}{'mean':>7}")
for r, cs in cards.items():
    ps = sorted(c["p"] for c in cs)
    q = st.quantiles(ps, n=4)
    print(f"   {r:<12}{min(ps):>7.0%}{q[0]:>7.0%}{q[1]:>8.0%}{q[2]:>7.0%}{max(ps):>7.0%}{st.mean(ps):>7.0%}")
# the best number anywhere on the card is the same under both rules: only the LEAD moves
best = {r: sorted(c["best_p"] for c in cs) for r, cs in cards.items()}
print(f"   best_p median is {st.median(best['prominence']):.0%} under both"
      if abs(st.median(best["prominence"]) - st.median(best["confident"])) < 1e-9 else "   best_p differs!")
print()

print("2. HOW MANY CARDS ACTUALLY CHANGE THEIR LEAD")
by = {r: {(c["match_iid"], c.get("player_iid")): c for c in cs} for r, cs in cards.items()}
keys = set(by["prominence"]) & set(by["confident"])
moved = [k for k in keys if by["prominence"][k].get("fkey") != by["confident"][k].get("fkey")]
print(f"   {len(moved)} of {len(keys)} cards lead on a different line ({len(moved)/max(len(keys),1):.0%})")
same_stat = sum(1 for k in moved if by["prominence"][k]["stat"] == by["confident"][k]["stat"])
print(f"   of those, {same_stat} stay in the same market and move rung; {len(moved)-same_stat} change market")
ups = [by["confident"][k]["p"] - by["prominence"][k]["p"] for k in moved]
if ups:
    print(f"   the change in the leading percentage: median {st.median(ups):+.1%}, max {max(ups):+.1%}, min {min(ups):+.1%}")
print()

print("3. WHICH MARKET LEADS")
for r, cs in cards.items():
    c = collections.Counter(x["stat"] for x in cs)
    tot = sum(c.values())
    print(f"   {r:<12}" + "  ".join(f"{k} {v} ({v/tot:.0%})" for k, v in c.most_common()))
print()

print("4. DOES IT CROWN THE BOTTOM RUNG?  (the docs/44 failure mode)")
for r, cs in cards.items():
    low = sum(1 for x in cs if float(x["thr"]) <= 1.5)
    print(f"   {r:<12}{low} of {len(cs)} leads are the ladder's lowest rung ({low/max(len(cs),1):.0%})")
print()

print("5. DO THE GUARDS STILL HOLD UNDER 'confident'?")
for r, cs in cards.items():
    over = [x for x in cs if x["p"] > MAXP]
    triv = [x for x in cs if Q.is_trivial(x, SPAN)]
    print(f"   {r:<12}leads above feed_max_p: {len(over)}   leads that are trivial: {len(triv)}")
print("   (both should be 0 unless every line in a group was itself over the bar -- the `or` floors)")
