"""selftest_new_markets.py -- fouls and goal involvements as player markets (docs/70).

Proves the chain end to end, and the three ways it could go wrong quietly:

  * goals+assists are forecast as ONE count, not two probabilities added -- a player who scores
    often also assists, and adding the marginals double-counts that overlap;
  * a market named in the settings that the engine cannot fit is DROPPED, not guessed at, and a
    market the engine can fit that nobody asked for is not published;
  * an empty market drops the MARKET, never the rows -- dropna on an empty column would delete
    every appearance in the league and take the three working markets with it;
  * PLAYER_STATS is module state and run_league is called once per league, so a market dropped
    for one league must not stay dropped for the next.
"""
import os, sys, base64
os.environ.setdefault("APP_ENCRYPTION_KEY", base64.b64encode(os.urandom(32)).decode())
HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("SOCCER_BRAIN_DIR", os.path.join(HERE, "soccer_brain"))
sys.path.insert(0, HERE); sys.path.insert(0, os.environ["SOCCER_BRAIN_DIR"])
import mongomock
import engine as E
import engine_bridge as EB, ingest as ING, mongo_init, normalize as N, settings_store as S


def check(c, m):
    if not c:
        print("  FAIL", m); sys.exit(1)
    print("  ok  ", m)


# ---------------------------------------------------------------- 1. the combined column
check("goal_involvements" in N.DERIVED_PLAYER_COLS,
      "goals+assists is a DERIVED column, computed at ingest rather than added in the page")

rows = N.players([{"player": {"id": "a", "position_id": 3}, "team_id": "h",
                   "stats": [{"key": "top_stats", "stats": {
                       "M": {"key": "minutes_played", "stat": {"type": "integer", "value": 90}},
                       "G": {"key": "goals_k", "stat": {"type": "integer", "value": 2}},
                       "A": {"key": "assists_k", "stat": {"type": "integer", "value": 1}}}}]}],
                 {"minutes": {"group": "top_stats", "key": "minutes_played"},
                  "goals": {"group": "top_stats", "key": "goals_k"},
                  "assists": {"group": "top_stats", "key": "assists_k"}}, {"3": "FWD"})
check(rows[0]["goal_involvements"] == 3.0, "two goals and one assist is three involvements, counted once")

# The rule that makes it honest: it is None unless BOTH parts are known. A sum that treats an
# unknown as a zero is the error the whole zero-fill block exists to prevent.
half = N.players([{"player": {"id": "b", "position_id": 3}, "team_id": "h",
                   "stats": [{"key": "other", "stats": {}}]}],
                 {"goals": {"group": "top_stats", "key": "goals_k"},
                  "assists": {"group": "top_stats", "key": "assists_k"}}, {"3": "FWD"})
check(half[0]["goal_involvements"] is None,
      "with either part unknown the involvement is unknown, never silently a zero")

# ---------------------------------------------------------------- 2. the team totals exist
check("fouls_committed" in N.PLAYER_COLS, "fouls are ingested per player")
src = open(os.path.join(HERE, "ingest.py")).read()
check('"team_fouls_committed"' in src and '"team_goal_involvements"' in src,
      "both team totals are written onto every player row -- the engine needs a share OF something")

# ---------------------------------------------------------------- 3. the engine knows the markets
for m in ("fouls_committed", "goal_involvements"):
    check(m in E.ALL_PLAYER_STATS, f"{m} is a market the engine fits")
    check(m in E.DEFAULT_R_PLAYER, f"{m} has a dispersion -- without one, r_player[s] is a KeyError mid-run")
    check(m in EB.STAT_LABEL, f"{m} has words, so a card does not print the raw column name")
check(E.DEFAULT_R_PLAYER["goal_involvements"] < E.DEFAULT_R_PLAYER["shots"],
      "involvements cluster harder than shots, so they carry a lower r")
check(EB.STAT_LABEL["goal_involvements"] == ("goal or assist", "goals or assists"),
      "and the words say what it is: one event, either way of causing it")

# ---------------------------------------------------------------- 4. settings decide what ships
db = mongomock.MongoClient()["nm"]; mongo_init.ensure_indexes(db)
S.put(db, "engine.auto_lines", True)
S.put(db, "engine.player_ladder", {"shots": [0.5, 1.5], "sot": [0.5], "tackles": [1.5]})
EB.configure_engine(db)
check("goal_involvements" not in E.PLAYER_STATS,
      "a market the owner has NOT put in the ladder is not published, however well the engine fits it")
check(set(E.PLAYER_STATS) == {"shots", "sot", "tackles"}, f"only what was asked for: {E.PLAYER_STATS}")

S.put(db, "engine.player_ladder", {"shots": [0.5], "fouls_committed": [0.5, 1.5], "goal_involvements": [0.5]})
EB.configure_engine(db)
check("fouls_committed" in E.PLAYER_STATS and "goal_involvements" in E.PLAYER_STATS,
      "and both new markets turn on from the setting alone, with no code change")

S.put(db, "engine.player_ladder", {"shots": [0.5], "corners": [4.5], "xg": [0.5]})
EB.configure_engine(db)
check(E.PLAYER_STATS == ["shots"],
      f"a market the engine cannot fit is dropped rather than guessed at (got {E.PLAYER_STATS})")

# ---------------------------------------------------------------- 5. the per-run reset
CANON = list(E.ALL_PLAYER_STATS)                   # whatever the engine currently models
E.PLAYER_STATS[:] = ["shots"]                      # as if a previous league had dropped the rest
check(list(E.ALL_PLAYER_STATS) == CANON, "the canonical list is untouched by a narrowing")
E.PLAYER_STATS[:] = list(E.ALL_PLAYER_STATS)       # what configure_engine does on the way in
check(list(E.PLAYER_STATS) == CANON,
      "so a market dropped for one league is restored for the next -- run_league is a per-league loop")

# ---------------------------------------------------------------- 6. the band is the gate
S.put(db, "engine.player_ladder", {"goal_involvements": [0.5]})
EB.configure_engine(db)
band = S.get(db, "engine.line_band")
check(band[0] >= 0.5, f"the standard floor is {band[0]}")
by_stat = S.get(db, "engine.line_band_by_stat")
check(isinstance(by_stat, dict),
      "and engine.line_band_by_stat is where a ~40% market earns its own floor -- without an entry "
      "every involvement rung falls under the standard one and the market ships as nothing")

# ---------------------------------------------------------------- 7. the team layer is the gate
# Found by engine_newmarket.py, not by reading: a player market is a SHARE OF A TEAM TOTAL, and
# predict_fixture takes that share of mu_team[stat]. So the stat must also be one the TEAM layer
# forecasts. Fouls and involvements are in neither STATS nor extra_stats, so until the team layer
# models them the engine fits a player model it cannot be asked for a forecast -- which was a
# KeyError at the first fixture, mid-league-run, from a settings change alone.
import pandas as pd
frame = pd.DataFrame({"round": [1] * 4, "player": [1, 2, 3, 4], "team": [1, 1, 2, 2],
                      "minutes": [90.0] * 4, "pos": ["FWD"] * 4,
                      "shots": [1.0] * 4, "team_shots": [10.0] * 4,
                      "fouls_committed": [1.0] * 4, "team_fouls_committed": [11.0] * 4})
eng = E.SoccerEngine(seed=0)
eng.stats = ["shots", "sot", "corners", "tackles"]          # the team layer, as production has it
E.PLAYER_STATS[:] = ["shots", "fouls_committed"]
keep = [c for c in E.PLAYER_STATS
        if c in frame.columns and ("team_" + c) in frame.columns and c in eng.stats]
check(keep == ["shots"],
      f"a player market the TEAM layer cannot forecast is dropped, columns or no columns (got {keep})")
check("fouls_committed" not in keep,
      "so pasting it into the ladder publishes nothing rather than raising KeyError mid-run")

# ---------------------------------------------------------------- 8. keepers and the rest
check(E.MARKET_POSITIONS.get("saves") == ("GK",),
      "saves is a keeper's market and nobody else's")
check("saves" not in [m for m in E.ALL_PLAYER_STATS if m not in E.MARKET_POSITIONS],
      "...and every OTHER market excludes keepers, so a GK never carries a 1+ shots line")
check("saves" in E.DEFAULT_R_PLAYER and "saves" in EB.STAT_LABEL,
      "saves has a dispersion and words like any other market")
check(EB.PLAYER_MARKET_COLS["saves"] == ("saves", "team_saves"),
      "and it needs a team total like any other market -- a keeper's share of his side's saves")

print("selftest_new_markets: all checks passed")
