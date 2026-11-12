"""selftest_normalize_af.py -- API-Football JSON into our dicts. docs/85.

Built around the one thing that has already cost this project real forecasts: a null that means
zero and a null that means untracked look identical, and guessing wrong deletes appearances, reads
a deleted appearance as an absence, halves p_play and drops a player's cards -- silently, and
correlated with position. So the guard gets the most tests, in both directions.

    python3 tests/selftest_normalize_af.py
"""
import os, sys, base64
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
os.environ.setdefault("APP_ENCRYPTION_KEY", base64.b64encode(os.urandom(32)).decode())

import normalize_af as N
from normalize import MissingField

OK = []
def check(name, cond):
    cond = bool(cond)
    OK.append(cond)
    print(("  ok     " if cond else "  FAIL   ") + name)


TEAM_KEYS = {"shots": "Total Shots", "sot": "Shots on Goal", "corners": "Corner Kicks",
             "poss": "Ball Possession", "fouls": "Fouls", "yellow_cards": "Yellow Cards",
             "tackles": None, "xg": "expected_goals"}
POS = {"G": "GK", "D": "DEF", "M": "MID", "F": "FWD"}
SETTINGS = {"team_keys": TEAM_KEYS, "position_map": POS, "exclude_extra_time": True}


def pstat(**kw):
    """One player's statistics block, with everything absent unless given."""
    return {
        "games": {"minutes": kw.get("minutes"), "number": kw.get("number"),
                  "position": kw.get("pos"), "rating": kw.get("rating"),
                  "captain": kw.get("captain", False), "substitute": kw.get("sub", False)},
        "shots": {"total": kw.get("shots"), "on": kw.get("sot")},
        "goals": {"total": kw.get("goals"), "conceded": kw.get("conceded"),
                  "assists": kw.get("assists"), "saves": kw.get("saves")},
        "passes": {"total": kw.get("passes"), "key": None, "accuracy": None},
        "tackles": {"total": kw.get("tackles"), "blocks": None, "interceptions": kw.get("inter")},
        "duels": {"total": None, "won": None},
        "dribbles": {"attempts": None, "success": None, "past": None},
        "fouls": {"drawn": kw.get("fouls_won"), "committed": kw.get("fouls_committed")},
        "cards": {"yellow": kw.get("yellow"), "red": kw.get("red")},
    }


def fixture(short="FT", home_stats=None, away_stats=None, home_players=None, away_players=None,
            lineups=True):
    hs = {"Total Shots": "14", "Shots on Goal": "6", "Corner Kicks": "7",
          "Ball Possession": "59%", "Fouls": "11", "Yellow Cards": "2"}
    hs.update(home_stats or {})
    as_ = {"Total Shots": "9", "Shots on Goal": "3", "Corner Kicks": "4",
           "Ball Possession": "41%", "Fouls": "13", "Yellow Cards": "3"}
    as_.update(away_stats or {})
    f = {
        "fixture": {"id": 1035037, "referee": "Michael Oliver", "date": "2026-03-07T15:00:00+00:00",
                    "venue": {"name": "Emirates Stadium"},
                    "status": {"long": "Match Finished", "short": short, "elapsed": 90}},
        "league": {"id": 39, "name": "Premier League", "season": 2025, "round": "Regular Season - 28"},
        "teams": {"home": {"id": 42, "name": "Arsenal"}, "away": {"id": 49, "name": "Chelsea"}},
        "goals": {"home": 2, "away": 1},
        "score": {"halftime": {"home": 1, "away": 0}, "fulltime": {"home": 2, "away": 1}},
        "statistics": [
            {"team": {"id": 42}, "statistics": [{"type": k, "value": v} for k, v in hs.items()]},
            {"team": {"id": 49}, "statistics": [{"type": k, "value": v} for k, v in as_.items()]},
        ],
        "players": [
            {"team": {"id": 42}, "players": home_players if home_players is not None else [
                {"player": {"id": 1, "name": "Keeper"}, "statistics": [pstat(minutes=90, pos="G", saves=4, passes=20, tackles=0)]},
                {"player": {"id": 2, "name": "Defender"}, "statistics": [pstat(minutes=90, pos="D", shots=1, sot=0, tackles=4, inter=2, passes=55, fouls_committed=2, fouls_won=1)]},
                {"player": {"id": 3, "name": "Forward"}, "statistics": [pstat(minutes=78, pos="F", shots=5, sot=3, goals=2, assists=0, tackles=0, passes=18, fouls_won=3)]},
            ]},
            {"team": {"id": 49}, "players": away_players if away_players is not None else [
                {"player": {"id": 11, "name": "Away keeper"}, "statistics": [pstat(minutes=90, pos="G", saves=4, passes=25, tackles=0)]},
                {"player": {"id": 12, "name": "Away mid"}, "statistics": [pstat(minutes=90, pos="M", shots=2, sot=1, tackles=3, inter=1, passes=44, fouls_committed=3)]},
            ]},
        ],
    }
    if lineups:
        f["lineups"] = [
            {"team": {"id": 42}, "formation": "4-3-3", "coach": {"id": 7, "name": "A Coach"},
             "startXI": [{"player": {"id": 1, "name": "Keeper", "number": 1, "pos": "G", "grid": "1:1"}},
                         {"player": {"id": 2, "name": "Defender", "number": 4, "pos": "D", "grid": "2:2"}},
                         {"player": {"id": 3, "name": "Forward", "number": 9, "pos": "F", "grid": "4:2"}}],
             "substitutes": [{"player": {"id": 4, "name": "Bench", "number": 20, "pos": "M", "grid": None}}]},
            {"team": {"id": 49}, "formation": "4-2-3-1", "coach": {"id": 8, "name": "B Coach"},
             "startXI": [{"player": {"id": 11, "name": "Away keeper", "number": 1, "pos": "G", "grid": "1:1"}},
                         {"player": {"id": 12, "name": "Away mid", "number": 8, "pos": "M", "grid": "3:2"}}],
             "substitutes": []},
        ]
    return f


# ---------------------------------------------------------------- the contract
def t_same_shape_as_pitchapi():
    r = N.normalize_match(fixture(), SETTINGS)
    check("the keys are the ones ingest already expects",
          {"team", "players", "lineups", "team_totals", "issues"} <= set(r))
    check("team is home and away, each with our column names",
          set(r["team"]) == {"home", "away"} and "shots" in r["team"]["home"])
    # SIX, not five. `saves` joined them because engine_bridge requires ("saves", "team_saves") and
    # nothing but simulate.py had ever written team_saves -- so the saves market was dropped in
    # every real league while the tests passed on synthetic rows. The set is written out rather
    # than derived so that adding a seventh has to be a deliberate edit here: this set IS the list
    # of markets that can exist, and a column that arrives late arrives empty.
    check("team_totals carries exactly the stats whose team total sits on the player row",
          set(r["team_totals"]["home"]) == {"shots", "sot", "tackles", "fouls_committed",
                                            "goal_involvements", "saves"})


def t_team_stats_read_by_name():
    r = N.normalize_match(fixture(), SETTINGS)
    h = r["team"]["home"]
    check("shots, on target and corners come through", (h["shots"], h["sot"], h["corners"]) == (14.0, 6.0, 7.0))
    check("possession's per-cent sign is stripped, not parsed as text", h["poss"] == 59.0)
    check("fouls and yellow cards come through", (h["fouls"], h["yellow_cards"]) == (11.0, 2.0))
    check("a column we map to nothing stays None, never 0", h["xg"] is None)


def t_team_tackles_from_players():
    """There is no team tackles statistic on this provider (docs/80 §2), so the team total is the
    sum of its players' -- the same fallback normalize.py has always used."""
    r = N.normalize_match(fixture(), SETTINGS)
    check("home team tackles = 0 + 4 + 0 from its three players", r["team"]["home"]["tackles"] == 4.0)
    check("away team tackles = 0 + 3", r["team"]["away"]["tackles"] == 3.0)
    check("...and it matches what team_totals summed", r["team_totals"]["home"]["tackles"] == 4.0)


# ---------------------------------------------------------------- the guard, both ways
def t_null_is_zero_when_the_match_tracked_it():
    """The forward has tackles: 0 explicitly. Give him null instead and the guard must still read
    0, because other players in the match have a tackle count."""
    hp = [
        {"player": {"id": 2, "name": "Defender"}, "statistics": [pstat(minutes=90, pos="D", shots=1, tackles=4)]},
        {"player": {"id": 3, "name": "Forward"}, "statistics": [pstat(minutes=78, pos="F", shots=5, tackles=None)]},
    ]
    r = N.normalize_match(fixture(home_players=hp), SETTINGS)
    fwd = next(p for p in r["players"] if p["ext_id"] == "3")
    check("a forward with no tackle count in a match that tracked tackles reads 0, not None",
          fwd["tackles"] == 0.0)
    check("...so his appearance is not deleted by dropna, which is how p_play got halved",
          fwd["minutes"] == 78.0 and fwd["shots"] == 5.0)


def t_null_stays_none_when_nobody_has_it():
    """Nobody in the match has a tackle count: the match did not track them, so inventing a 0
    would invent a fact rather than restore one."""
    hp = [{"player": {"id": 2, "name": "D"}, "statistics": [pstat(minutes=90, pos="D", shots=1)]},
          {"player": {"id": 3, "name": "F"}, "statistics": [pstat(minutes=78, pos="F", shots=5)]}]
    ap = [{"player": {"id": 12, "name": "M"}, "statistics": [pstat(minutes=90, pos="M", shots=2)]}]
    r = N.normalize_match(fixture(home_players=hp, away_players=ap), SETTINGS)
    check("an untracked column stays None for everyone",
          all(p["tackles"] is None for p in r["players"]))
    check("...and the team total stays None rather than becoming a confident 0",
          r["team"]["home"]["tackles"] is None)
    check("a column that WAS tracked is unaffected by the other being absent",
          all(p["shots"] is not None for p in r["players"]))


def t_the_guard_looks_across_the_whole_fixture():
    """One player on the OTHER team having the number is enough: it is a property of the match,
    not of the team."""
    hp = [{"player": {"id": 3, "name": "F"}, "statistics": [pstat(minutes=90, pos="F", shots=4, inter=None)]}]
    ap = [{"player": {"id": 12, "name": "M"}, "statistics": [pstat(minutes=90, pos="M", shots=2, inter=5)]}]
    r = N.normalize_match(fixture(home_players=hp, away_players=ap), SETTINGS)
    check("interceptions tracked for an away player makes a home null read 0",
          next(p for p in r["players"] if p["ext_id"] == "3")["interceptions"] == 0.0)


def t_keepers_keep_their_tackles():
    """normalize.py blanks a keeper's tackles because PitchAPI sent keepers no defence group.
    Here every player's tackles are in the same object, so a keeper's 0 is real -- and blanking it
    would put None in a PLAYER_REQUIRED column, which deletes keeper rows on dropna (docs/70)."""
    r = N.normalize_match(fixture(), SETTINGS)
    gk = next(p for p in r["players"] if p["ext_id"] == "1")
    check("a goalkeeper's tackles are 0, not None", gk["tackles"] == 0.0)
    check("...so his row survives the dropna that the saves market needs him for", gk["saves"] == 4.0)
    check("and he is still read as a goalkeeper", gk["pos"] == "GK")


def t_columns_the_provider_does_not_carry():
    r = N.normalize_match(fixture(), SETTINGS)
    check("xg is None everywhere: it needs an add-on nobody is on",
          all(p["xg"] is None for p in r["players"]))
    check("clearances likewise, and neither is used by any market",
          all(p["clearances"] is None for p in r["players"]))


# ---------------------------------------------------------------- derived and joined
def t_goal_involvements():
    r = N.normalize_match(fixture(), SETTINGS)
    fwd = next(p for p in r["players"] if p["ext_id"] == "3")
    check("scored or assisted is goals + assists", fwd["goal_involvements"] == 2.0)
    hp = [{"player": {"id": 3, "name": "F"}, "statistics": [pstat(minutes=90, pos="F", shots=1, goals=1)]}]
    ap = [{"player": {"id": 12, "name": "M"}, "statistics": [pstat(minutes=90, pos="M", shots=1, goals=0)]}]
    r2 = N.normalize_match(fixture(home_players=hp, away_players=ap), SETTINGS)
    f2 = next(p for p in r2["players"] if p["ext_id"] == "3")
    check("...and assists absent for the whole match leaves it None, never a half-sum",
          f2["assists"] is None and f2["goal_involvements"] is None)


def t_started_from_their_own_flag():
    r = N.normalize_match(fixture(), SETTINGS)
    check("a starter is read from games.substitute, with no lineup cross-reference needed",
          next(p for p in r["players"] if p["ext_id"] == "3")["started"] is True)
    hp = [{"player": {"id": 4, "name": "Bench"}, "statistics": [pstat(minutes=12, pos="M", shots=1, sub=True)]}]
    r2 = N.normalize_match(fixture(home_players=hp), SETTINGS)
    check("a substitute is not a starter", next(p for p in r2["players"] if p["ext_id"] == "4")["started"] is False)


def t_lineups():
    r = N.normalize_match(fixture(), SETTINGS)
    home = r["lineups"]["home"]
    check("the formation comes through", home["formation"] == "4-3-3")
    check("a lineup that is present IS confirmed: theirs are the official ones", home["confirmed"] is True)
    check("eleven and bench are one list with a started flag", len(home["players"]) == 4
          and sum(1 for p in home["players"] if p["started"]) == 3)
    check("the grid position is kept, which is their notation for where a player stood",
          next(p for p in home["players"] if p["ext_id"] == "3")["grid"] == "4:2")
    check("the coach comes free with it", home["coach"] == "A Coach")
    r2 = N.normalize_match(fixture(lineups=False), SETTINGS)
    check("no lineup yet is not a confirmed empty one", r2["lineups"]["home"]["confirmed"] is False)


# ---------------------------------------------------------------- extra time
def t_extra_time_is_flagged():
    for short in ("AET", "PEN"):
        r = N.normalize_match(fixture(short=short), SETTINGS)
        check(f"{short} is flagged as extra time", r["extra_time"] is True)
        check(f"...and says why it matters", any(i["kind"] == "extra_time" for i in r["issues"]))
    r = N.normalize_match(fixture(short="FT"), SETTINGS)
    check("a 90-minute match is not flagged", r["extra_time"] is False
          and not any(i["kind"] == "extra_time" for i in r["issues"]))
    check("the match row carries the flag, so the frame filter can use it",
          N.match_row(fixture(short="AET"))["extra_time"] is True)
    off = N.normalize_match(fixture(short="AET"), {**SETTINGS, "exclude_extra_time": False})
    check("with the setting off the issue says the models are being biased, rather than going quiet",
          any("INCLUDED" in i["detail"] for i in off["issues"] if i["kind"] == "extra_time"))


# ---------------------------------------------------------------- the match row
def t_match_row():
    m = N.match_row(fixture())
    check("ids and names", (m["ext_id"], m["home_ext"], m["away_ext"]) == ("1035037", "42", "49"))
    check("the league and season come off the fixture", (m["league_ext"], m["season"]) == ("39", "2025"))
    check("the round is kept, which build_frames requires non-null", m["round"] == "Regular Season - 28")
    check("the score", (m["hg"], m["ag"]) == (2, 1))
    check("the referee is free here, where PitchAPI needed a call per match", m["referee"] == "Michael Oliver")
    check("FT is final", m["status"] == "final")
    for short, want in (("NS", "scheduled"), ("TBD", "scheduled"), ("AET", "final"), ("PEN", "final"),
                        ("1H", "other"), ("PST", "other"), ("CANC", "other")):
        check(f"{short} -> {want}", N.status_of(short) == want)


def t_missing_required_raises():
    # Shots absent for EVERY player in the fixture, so the guard correctly declines to invent a 0
    # and there is nothing to sum. Note what this test originally got wrong: with shots present for
    # the away side, the guard reads the home nulls as a real 0 and the sum is a legitimate 0 --
    # which is the guard working, not a gap.
    hp = [{"player": {"id": 3, "name": "F"}, "statistics": [pstat(minutes=90, pos="F", tackles=1)]}]
    ap = [{"player": {"id": 12, "name": "M"}, "statistics": [pstat(minutes=90, pos="M", tackles=2)]}]
    f = fixture(home_stats={"Total Shots": None}, home_players=hp, away_players=ap)
    try:
        N.normalize_match(f, SETTINGS)
        check("a match with no shots anywhere, and none to sum, is refused", False)
    except MissingField:
        check("a match with no shots anywhere, and none to sum, is refused", True)
    # and the case the first version of this test actually described
    f_zero = fixture(home_stats={"Total Shots": None},
                     home_players=[{"player": {"id": 3, "name": "F"},
                                    "statistics": [pstat(minutes=90, pos="F")]}])
    r0 = N.normalize_match(f_zero, SETTINGS)
    check("a side whose players all read 0 shots in a match that DID track them sums to 0, legitimately",
          r0["team"]["home"]["shots"] == 0.0)
    f2 = fixture(home_stats={"Total Shots": None})
    r = N.normalize_match(f2, SETTINGS)
    check("...but one that CAN be summed from the players is kept, and says so",
          r["team"]["home"]["shots"] == 6.0
          and any(i["kind"] == "team_stat_from_players" for i in r["issues"]))


def t_shots_disagreement_is_reported():
    r = N.normalize_match(fixture(home_stats={"Total Shots": "40"}), SETTINGS)
    check("a team total far from the sum of its players is flagged, not silently preferred",
          any(i["kind"] == "team_player_shots_gap" for i in r["issues"]))


for fn in (t_same_shape_as_pitchapi, t_team_stats_read_by_name, t_team_tackles_from_players,
           t_null_is_zero_when_the_match_tracked_it, t_null_stays_none_when_nobody_has_it,
           t_the_guard_looks_across_the_whole_fixture, t_keepers_keep_their_tackles,
           t_columns_the_provider_does_not_carry, t_goal_involvements, t_started_from_their_own_flag,
           t_lineups, t_extra_time_is_flagged, t_match_row, t_missing_required_raises,
           t_shots_disagreement_is_reported):
    print(fn.__name__)
    fn()

print()
print(f"{sum(OK)}/{len(OK)} passed")
sys.exit(0 if all(OK) else 1)
