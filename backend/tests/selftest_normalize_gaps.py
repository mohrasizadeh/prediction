"""normalize.py rules from real PitchAPI answers: unused players skipped; missing shots/sot = 0 for players who played;
missing minutes stays None and is logged once per match instead of dropping the match."""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import normalize as N

KEYS = {"minutes": {"group": "top_stats", "key": "minutes_played"}, "shots": {"group": "top_stats", "key": "total_shots"},
        "sot": {"group": "top_stats", "key": "ShotsOnTarget"}, "tackles": {"group": "defense", "key": None}}
fails = 0


def check(cond, what):
    global fails
    print(("  ok   " if cond else "  FAIL ") + what)
    fails += 0 if cond else 1


def stat(key, v):
    return {key: {"key": key, "stat": {"type": "integer", "value": v}}}


played = {"player": {"id": "a", "position_id": 2}, "team_id": "h", "stats": [{"key": "top_stats", "stats": stat("minutes_played", 90)}]}
shooter = {"player": {"id": "b", "position_id": 3}, "team_id": "h", "stats": [{"key": "top_stats", "stats": {**stat("minutes_played", 70), **stat("total_shots", 3), **stat("ShotsOnTarget", 1)}}]}
no_minutes = {"player": {"id": "c", "position_id": 2}, "team_id": "a", "stats": [{"key": "top_stats", "stats": stat("total_shots", 1)}]}
bench = {"player": {"id": "d", "position_id": 1}, "team_id": "a", "stats": []}

rows = N.players([played, shooter, no_minutes, bench], KEYS, {})
check([r["ext_id"] for r in rows] == ["a", "b", "c"], "a listed player with no stats is skipped")
check(rows[0]["shots"] == 0.0 and rows[0]["sot"] == 0.0, "missing shots and shots on target count as 0 for a player who played")
check(rows[1]["shots"] == 3 and rows[1]["sot"] == 1, "real values are kept")
check(rows[2]["minutes"] is None, "missing minutes stays None")
check(N.players([played], {**KEYS, "shots": {"group": "top_stats", "key": None}}, {})[0]["shots"] is None, "an unmapped key stays None, never 0")

stats = {"periods": [{"period": "ALL", "groups": [{"group_name": "g", "items": [
    {"key": k, "home": "5", "away": "4"} for k in ("total_shots", "ShotsOnTarget", "corners", "tackles", "BallPossesion")]}]}]}
tk = {"shots": "total_shots", "sot": "ShotsOnTarget", "corners": "corners", "tackles": "tackles", "poss": "BallPossesion"}
out = N.normalize_match({"home_ext": "h", "away_ext": "a"}, stats, [played, shooter, no_minutes, bench], {"home": {}, "away": {}},
                        {"team_keys": tk, "player_keys": KEYS, "position_map": {}})
gaps = [i for i in out["issues"] if i["kind"] == "player_stat_missing"]
check(len(out["players"]) == 3 and len(gaps) == 1 and gaps[0]["detail"].startswith("1 players"), "match is kept; one issue for the gap")

# --- v8: goals and assists are zero-filled too, under the same two conditions -------------------
# Until now only shots and sot were. With goals null for a goalless appearance, any per-90 rate
# divides a player's goals by the games he SCORED in, so every scorer comes out near 1.0 a game --
# a plausible number, not an obviously broken one, which is why nothing downstream caught it.
GK2 = {**KEYS, "goals": {"group": "top_stats", "key": "goals_k"}, "assists": {"group": "top_stats", "key": "assists_k"}}
scored = {"player": {"id": "s", "position_id": 3}, "team_id": "h",
          "stats": [{"key": "top_stats", "stats": {**stat("minutes_played", 90), **stat("goals_k", 2), **stat("assists_k", 1)}}]}
blank = {"player": {"id": "n", "position_id": 3}, "team_id": "h",
         "stats": [{"key": "top_stats", "stats": stat("minutes_played", 90)}]}
g = {r["ext_id"]: r for r in N.players([scored, blank], GK2, {})}
check(g["s"]["goals"] == 2.0 and g["s"]["assists"] == 1.0, "a scorer's goals and assists are read")
check(g["n"]["goals"] == 0.0 and g["n"]["assists"] == 0.0, "a goalless appearance stores 0, not None -- the rate bug")
check(g["s"]["goal_involvements"] == 3.0 and g["n"]["goal_involvements"] == 0.0, "goal_involvements is goals + assists")

# Unmapped stays None: a column the provider never sends must not be invented as a zero, or every
# player in the league records "never scored" at full coverage.
u = {r["ext_id"]: r for r in N.players([blank], KEYS, {})}
check(u["n"]["goals"] is None and u["n"]["assists"] is None and u["n"]["goal_involvements"] is None,
      "an unmapped column stays unknown rather than becoming a zero")

# Missing GROUP stays None as well -- the rule tackles already applied, now applied to every
# zero-filled column. No group means the provider sent nothing, not that the count was zero.
nogroup = {"player": {"id": "x", "position_id": 3}, "team_id": "h", "stats": [{"key": "defense", "stats": {}}]}
x = N.players([nogroup], GK2, {})[0]
check(x["goals"] is None and x["shots"] is None, "no top_stats group means no data, so nothing is zero-filled")

if fails:
    raise SystemExit(f"{fails} failed")
print("normalize gaps self-test passed")
