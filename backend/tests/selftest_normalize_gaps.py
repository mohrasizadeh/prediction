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
if fails:
    raise SystemExit(f"{fails} failed")
print("normalize gaps self-test passed")
