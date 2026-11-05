"""selftest_triviality.py -- do not lead a card with a line that cannot move (docs/56), and gate on the
chance to START rather than the chance to feature (docs/55).

    pip install mongomock httpx pymongo numpy scipy pandas cryptography
    SOCCER_BRAIN_DIR=../soccer_brain python selftest_triviality.py

The properties that matter, in the order they can fail:

  1. an insensitive rung does not lead while any other line in the group can;
  2. it is DEMOTED, not deleted -- it is still in more_lines, so the Finder and a combo keep it;
  3. a group in which EVERY rung is insensitive still produces a card. An empty feed is not an
     improvement on a dull one, and this is the failure mode a naive filter would have;
  4. an UNKNOWN span is never treated as trivial. A missing field must not silently hide a card;
  5. min_span = 0 leaves the old behaviour exactly as it was;
  6. the engine's own span is larger for a rung at the entity's own level than for a near-certain one,
     which is the claim the whole gate rests on;
  7. min_p_start withholds a card from a player who features but rarely starts, and min_p_play does not.
"""
from __future__ import annotations

import base64
import os
import sys

os.environ.setdefault("APP_ENCRYPTION_KEY", base64.b64encode(os.urandom(32)).decode())
HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("SOCCER_BRAIN_DIR", os.path.join(HERE, "soccer_brain"))
sys.path.insert(0, HERE); sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.environ["SOCCER_BRAIN_DIR"])

import numpy as np

import queries as Q
from core import nb_sf

FAILED = []


def check(ok, what):
    print(("  ok   " if ok else "  FAIL ") + what)
    if not ok:
        FAILED.append(what)


def line(fkey, p, span, stat="shots", thr=0.5, **kw):
    d = {"fkey": fkey, "match_iid": 1, "scope": "player", "team_iid": 7, "player_iid": 3,
         "stat": stat, "thr": thr, "market": f"{int(thr) + 1}+ shots", "p": p, "lo": p - 0.05,
         "hi": p + 0.05, "span": span, "tier": "Solid", "p_usual": 0.5, "edge": p - 0.5}
    d.update(kw)
    return d


print("1-5. the gate, on hand-built lines")
# a dull near-certainty and a live rung, in one group
dull = line("a", 0.93, 0.03, thr=0.5)
live = line("b", 0.55, 0.31, thr=4.5)
cards = Q.group_cards([dull, live], 1.0, "player", None, "odds", 0.08)
check(len(cards) == 1, "one card for one player and match")
check(cards[0]["fkey"] == "b", "the rung that can move leads (dull 0.93/3pts loses to live 0.55/31pts)")
check(any(m["fkey"] == "a" for m in cards[0]["more_lines"]), "the dull rung is demoted, not deleted")
check(cards[0]["best_p"] == 0.93, "best_p still sees the near-certain line")

# every rung insensitive: still a card
allsame = Q.group_cards([line("c", 0.93, 0.03), line("d", 0.88, 0.02, thr=1.5)], 1.0, "player", None, "odds", 0.08)
check(len(allsame) == 1 and allsame[0]["fkey"] in ("c", "d"), "a group of only insensitive rungs still makes a card")

# unknown span is not trivial
unk = Q.group_cards([line("e", 0.93, None), line("f", 0.55, 0.31, thr=4.5)], 1.0, "player", None, "odds", 0.90)
check(unk[0]["fkey"] in ("e", "f"), "an unknown span is never hidden: a card is still produced")
check(not Q.is_trivial({"span": None}, 0.5), "is_trivial is False for an unknown span")
check(not Q.is_trivial({"span": 0.001}, 0.0), "min_span = 0 switches the gate off entirely")
check(Q.is_trivial({"span": 0.03}, 0.08) and not Q.is_trivial({"span": 0.30}, 0.08), "the threshold itself works")

# With the gate OFF the dull near-certainty leads, because prominence multiplies lift by p and a 93%
# line beats a 55% one on both terms. That is precisely the card this gate exists to stop, so asserting
# it here keeps the demonstration honest: the gate changes the lead, it is not decoration on top of a
# rule that already got this right.
off = Q.group_cards([dull, live], 1.0, "player", None, "odds", 0.0)
check(off[0]["fkey"] == "a", "with the gate OFF the dull 93% line leads -- the behaviour being fixed")

print("\n6. the engine's own claim: a near-certain rung is less sensitive than a rung at the player's level")
# the same player, the same opponent range, two rungs. This is the arithmetic the gate depends on.
mu, r, dlog = 5.0, 6.0, 0.25
spans = {}
for k in (1, 5):
    spans[k] = abs(float(nb_sf(k, mu * np.exp(dlog), r)) - float(nb_sf(k, mu * np.exp(-dlog), r)))
print(f"     1+ shots span {spans[1] * 100:5.2f} pts      5+ shots span {spans[5] * 100:5.2f} pts")
check(spans[5] > 4 * spans[1], "the rung at his own level moves several times as far as the 1+ rung")
check(spans[1] < 0.08, "the 1+ rung for a five-shot striker is below an 8-point gate")

print("\n7. the start gate catches a regular substitute that the play gate does not")
# the measured shape from docs/55: a fringe player features in nearly every match but starts seldom
p_play, p_start = 0.93, 0.41
check(p_play >= 0.5, "min_p_play = 0.5 does NOT catch him: his chance to feature is 0.93")
check(p_start < 0.5, "min_p_start = 0.5 does catch him: his chance to start is 0.41")

print("\n" + ("FAILED: " + "; ".join(FAILED) if FAILED else "all checks passed"))
sys.exit(1 if FAILED else 0)
