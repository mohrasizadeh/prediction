"""What leads a card, and how cards are split (docs/46).

Reported: "mbappe one shot or benfica 7 shots are not that much great insights those are almost given ... how can
we show the forecasts that users actually care. also putting players all forecasts under one card may not be a
good idea as they hide those from the filter."

Both came from the same rule: the lead was picked on raw likelihood, which since docs/44 is always the dullest
line a player owns. The card then inherited that line's stat, tier and lift, so the feed's own "edge" sort ranked
every card by its least interesting line, and the filters judged the player by it too.
"""
import json, os, sys, base64
os.environ.setdefault("APP_ENCRYPTION_KEY", base64.b64encode(os.urandom(32)).decode())
HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(HERE, "soccer_brain")); sys.path.insert(0, os.path.join(HERE, "tests"))
import queries as Q

_REG = {r["key"]: r["default"] for r in json.load(open(os.path.join(HERE, "settings_registry.json")))}
W = _REG["engine.market_weights"]
PW = _REG["engine.position_weights"]


def check(c, m):
    if not c:
        print("  FAIL", m); sys.exit(1)
    print("  ok  ", m)


def L(stat, thr, p, usual, market, scope="player", pid=7):
    return {"match_iid": 1, "scope": scope, "team_iid": 9, "player_iid": pid if scope == "player" else None,
            "fkey": f"{scope}{pid}{stat}{thr}", "stat": stat, "thr": thr, "p": p, "p_usual": usual,
            "edge": p - usual, "market": market, "tier": "Solid", "lo": p - .05, "hi": p + .05, "kickoff": 1}


MBAPPE = [L("shots", 0.5, 0.95, 0.93, "1+ shot"), L("shots", 1.5, 0.85, 0.81, "2+ shots"),
          L("shots", 2.5, 0.58, 0.38, "3+ shots"), L("sot", 0.5, 0.78, 0.74, "1+ shot on target"),
          L("sot", 1.5, 0.49, 0.28, "2+ shots on target")]

# ---------------------------------------------------------------- the score itself
given = L("shots", 0.5, 0.95, 0.93, "1+ shot")
news = L("sot", 1.5, 0.49, 0.28, "2+ shots on target")
check(Q.prominence(news, W) > Q.prominence(given, W),
      f"a 49% line that is usually 28% beats a 95% line that is usually 93%: {Q.prominence(news, W):.4f} > {Q.prominence(given, W):.4f}")
check(Q.prominence(L("shots", 0.5, 0.95, 0.95, "1+ shot"), W) == 0.0, "a line exactly as usual scores nothing: it is not news")
check(Q.prominence(L("shots", 0.5, 0.95, 0.99, "1+ shot"), W) == 0.0, "...and neither is one BELOW usual; it never goes negative")
a = L("sot", 1.5, 0.50, 0.30, "2+ shots on target"); b = L("shots", 1.5, 0.50, 0.30, "2+ shots")
check(Q.prominence(a, W) > Q.prominence(b, W), "same lift, same likelihood: the more important market wins (on target over shots)")
hi = L("sot", 1.5, 0.60, 0.40, "x"); lo = L("sot", 1.5, 0.30, 0.10, "y")
check(Q.prominence(hi, W) > Q.prominence(lo, W), "same lift: the likelier line wins, so an unusual long shot does not lead")

# ---------------------------------------------------------------- what the market is worth to HIM
# Reported with a screenshot: a forward's card led with "1+ tackle" at 54% while his "1+ shot" at
# 69% sat collapsed underneath. Nothing in this function read `pos`, although every forecast
# carries it, so a tackle line and a shot line were worth the same to a striker and to a
# centre-back. Worse, market_weights rated tackles 1.3 against shots 1.0 -- numbers taken from the
# priority table in docs/39, which is a BUILD BACKLOG, and shots is missing from it only because
# it was already shipped.
fw_t = {**L("tackles", 1.5, 0.50, 0.30, "2+ tackles"), "pos": "FWD"}
fw_s = {**L("shots", 1.5, 0.50, 0.30, "2+ shots"), "pos": "FWD"}
check(Q.prominence(fw_t, W) > Q.prominence(fw_s, W), "without the table, a forward's tackle line outranks his shot line at equal lift -- the reported bug")
check(Q.prominence(fw_s, W, "odds", PW) > Q.prominence(fw_t, W, "odds", PW), "with it, the forward leads on shots")
df_t = {**L("tackles", 1.5, 0.50, 0.30, "2+ tackles"), "pos": "DEF"}
df_s = {**L("shots", 1.5, 0.50, 0.30, "2+ shots"), "pos": "DEF"}
check(Q.prominence(df_t, W, "odds", PW) > Q.prominence(df_s, W, "odds", PW), "and a defender still leads on tackles, by more than before")
check(Q.prominence(df_t, W, "odds", PW) > Q.prominence(df_t, W), "...the table reinforces a lead that was already right")
# A club line carries no position, so it must be untouched rather than defaulted oddly.
tm = L("corners", 4.5, 0.50, 0.30, "5+ corners", scope="team")
check(Q.prominence(tm, W, "odds", PW) == Q.prominence(tm, W), "a club line has no position and is unaffected")
check(Q.prominence(fw_s, W, "odds", {}) == Q.prominence(fw_s, W), "an empty table is the same as no table, so it can be switched off")
unknown = {**L("shots", 1.5, 0.50, 0.30, "2+ shots"), "pos": "WB"}
check(Q.prominence(unknown, W, "odds", PW) == Q.prominence(unknown, W), "a position we do not list counts as 1.0 rather than vanishing")
check(Q.prominence(L("passes", 9.5, 0.5, 0.3, "x"), {}) > 0, "an empty weight table still scores: anything unlisted counts as 1.0")

# ---------------------------------------------------------------- what leads a card
one = Q.group_cards(MBAPPE, 0.97, "player", W)
check(len(one) == 1, "group=player: one card for everything he has")
check(one[0]["market"] == "2+ shots on target", f"...led by what is worth saying, not '1+ shot': {one[0]['market']}")
check(one[0]["best_p"] == 0.95, "...and the card still carries his best percentage, so a filter can see it")
check(any(m["market"] == "1+ shot" for m in one[0]["more_lines"]), "...the near-certain line is kept, just not the headline")

two = sorted(Q.group_cards(MBAPPE, 0.97, "player_market", W), key=lambda c: c["stat"])
check(len(two) == 2, f"group=player_market: shots and on-target are separate cards, so both surface: {len(two)}")
check([c["market"] for c in two] == ["3+ shots", "2+ shots on target"], f"...each led by its own best line: {[c['market'] for c in two]}")
check(all(c["best_p"] >= c["p"] for c in two), "every card knows the best percentage it holds")
check(len(Q.group_cards(MBAPPE, 0.97, "line", W)) == len(MBAPPE), "group=line: no grouping at all")

# the owner's other example: a team line that is a given
BEN = [dict(L("shots", 6.5, 0.97, 0.96, "7+ shots", "team"), player_iid=None),
       dict(L("shots", 12.5, 0.44, 0.26, "13+ shots", "team"), player_iid=None)]
b = Q.group_cards(BEN, 0.97, "player_market", W)[0]
check(b["market"] == "13+ shots", f"a team's '7+ shots, usually 96%' does not lead either: {b['market']}")

# ---------------------------------------------------------------- when nothing is unusual
flat = [L("shots", 0.5, 0.95, 0.95, "1+ shot"), L("shots", 1.5, 0.60, 0.60, "2+ shots")]
f = Q.group_cards(flat, 0.97, "player", W)[0]
check(f["market"] == "1+ shot", "when no line in a card has any lift, the likeliest leads, as it used to")

# the max_p rule from docs/25 still holds
cap = [L("shots", 0.5, 0.99, 0.60, "1+ shot"), L("shots", 1.5, 0.70, 0.50, "2+ shots")]
c = Q.group_cards(cap, 0.97, "player", W)[0]
check(c["market"] == "2+ shots", "a line above feed_max_p still never leads while another line can")
check(Q.group_cards([cap[0]], 0.97, "player", W)[0]["market"] == "1+ shot", "...but it leads when it is all there is")

# ---------------------------------------------------------------- engine.lead_rule = "confident"
# Asked: "lead with better, higher percentages and better forecasts." Both answers are defensible
# and they answer different questions, so it is a setting. What makes "confident" safe -- and not a
# return to docs/44, whose ranking on raw p produced the complaint at the top of this file -- is
# that the two guards below do their work BEFORE either score is consulted.
C = dict(rule="confident")
m = Q.group_cards(MBAPPE, 0.97, "player", W, "odds", 0.0, PW, "confident")[0]
check(m["market"] == "1+ shot", "confident leads with the strongest number when nothing is gating it")
d = Q.group_cards(MBAPPE, 0.97, "player", W, "odds", 0.0, PW, "prominence")[0]
check(d["market"] != m["market"], f"...and prominence does not: it leads on {d['market']!r}")
check(m["best_p"] == d["best_p"], "the card holds the same lines either way; only the lead moves")
check(len(m["more_lines"]) == len(d["more_lines"]) == len(MBAPPE) - 1,
      "nothing is deleted by the choice of lead")

# Guard 1: a near-certainty above feed_max_p still cannot lead, whatever the rule says about it.
check(Q.group_cards(cap, 0.97, "player", W, "odds", 0.0, PW, "confident")[0]["market"] == "2+ shots",
      "confident still obeys feed_max_p: 99% does not lead while another line can")

# Guard 2: the triviality gate. This is the one that answers the Mbappe complaint under the new
# rule -- his 1+ shot barely moves across the league's defences, so it is demoted on insensitivity
# rather than on its percentage, and the confident rule never gets to see it.
_dull = L("shots", 0.5, 0.95, 0.93, "1+ shot"); _dull["span"] = 0.03
_live = L("shots", 2.5, 0.58, 0.38, "3+ shots"); _live["span"] = 0.31
t = Q.group_cards([_dull, _live], 0.97, "player", W, "odds", 0.08, PW, "confident")[0]
check(t["market"] == "3+ shots", "confident still obeys min_span: an insensitive rung cannot lead")
check(Q.group_cards([_dull], 0.97, "player", W, "odds", 0.08, PW, "confident")[0]["market"] == "1+ shot",
      "...but it leads when it is all the card has, so no card is ever hidden by the gate")

# The default is unchanged, which is the whole point of shipping it as a switch.
check(Q.group_cards(MBAPPE, 0.97, "player", W, "odds", 0.0, PW)[0]["fkey"] == d["fkey"],
      "the default lead rule is prominence: nothing moves until the setting is changed")

# ---------------------------------------------------------------- engine.lead_rule = "relevance"
# "for a player like mbappe, sot and goal come first, before shots. For a defender, tackles comes
# first. For a midfielder, tackles or shots." That is engine.position_weights, which already says
# exactly this -- FWD sot 1.5 > shots 1.4 >> tackles 0.5, DEF tackles 1.5 >> shots 0.6 -- and which
# today decides almost nothing, because it is a multiplier on a comparison it is usually absent
# from. Choosing the market first is the only way it can act.
FW = [L("shots", 2.5, 0.58, 0.38, "3+ shots"), L("sot", 0.5, 0.52, 0.50, "1+ shot on target")]
for f in FW:
    f["pos"] = "FWD"
r = Q.group_cards(FW, 0.97, "player", W, "odds", 0.0, PW, "relevance")[0]
check(r["stat"] == "sot", f"a forward leads on on-target, the market his position rates highest (got {r['stat']})")
p_ = Q.group_cards(FW, 0.97, "player", W, "odds", 0.0, PW, "prominence")[0]
check(p_["stat"] == "shots", "...where prominence leads on shots, because the 3+ rung has the lift")
check(r["best_p"] == p_["best_p"] and len(r["more_lines"]) == len(p_["more_lines"]),
      "the card holds the same lines; only which one is on its face moves")

DF = [L("shots", 0.5, 0.70, 0.55, "1+ shot"), L("tackles", 1.5, 0.55, 0.52, "2+ tackles")]
for f in DF:
    f["pos"] = "DEF"
check(Q.group_cards(DF, 0.97, "player", W, "odds", 0.0, PW, "relevance")[0]["stat"] == "tackles",
      "a defender leads on tackles even when his shots line is the likelier one")

# Within the chosen market, the line is still picked by prominence -- relevance chooses the market,
# not the rung.
MM = [L("sot", 0.5, 0.80, 0.79, "1+ shot on target"), L("sot", 1.5, 0.55, 0.35, "2+ shots on target")]
for f in MM:
    f["pos"] = "FWD"
check(Q.group_cards(MM, 0.97, "player", W, "odds", 0.0, PW, "relevance")[0]["market"] == "2+ shots on target",
      "inside the market, the line with the most to say still leads")

# The guards come first, so relevance cannot resurrect a line the product has already ruled out.
_hi = L("sot", 0.5, 0.99, 0.60, "1+ shot on target"); _hi["pos"] = "FWD"
_ok = L("shots", 1.5, 0.70, 0.50, "2+ shots"); _ok["pos"] = "FWD"
check(Q.group_cards([_hi, _ok], 0.97, "player", W, "odds", 0.0, PW, "relevance")[0]["stat"] == "shots",
      "a market whose only line is above feed_max_p does not win on relevance")
_dull = L("sot", 0.5, 0.80, 0.79, "1+ shot on target"); _dull["pos"] = "FWD"; _dull["span"] = 0.02
_live = L("shots", 2.5, 0.58, 0.38, "3+ shots"); _live["pos"] = "FWD"; _live["span"] = 0.31
check(Q.group_cards([_dull, _live], 0.97, "player", W, "odds", 0.08, PW, "relevance")[0]["stat"] == "shots",
      "...nor one whose only line reads the same against every opponent")

# One market on the card: nothing to choose, and no rule may drop it.
solo = [L("tackles", 1.5, 0.61, 0.60, "2+ tackles")]
solo[0]["pos"] = "FWD"                                   # tackles is this position's WORST market
check(Q.group_cards(solo, 0.97, "player", W, "odds", 0.0, PW, "relevance")[0]["stat"] == "tackles",
      "with one market available it leads, however little his position rates it")

print("\nALL PROMINENCE CHECKS PASSED")
