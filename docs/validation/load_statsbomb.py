"""load_statsbomb.py -- build the engine's three frames from the tables sb_extract.py wrote."""
import os
import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
SB = os.path.join(HERE, "data", "sb")


def load(league: str):
    tg = pd.read_pickle(os.path.join(SB, f"tg_{league}.pkl")).copy()
    pg = pd.read_pickle(os.path.join(SB, f"pg_{league}.pkl")).copy()
    mt = pd.read_pickle(os.path.join(SB, f"mt_{league}.pkl")).copy()
    # matches whose event feed is empty (all-zero shots, tackles and corners for a side) are data holes, not football
    empty = tg[(tg["shots"] == 0) & (tg["tackles"] == 0) & (tg["corners"] == 0)]["match_id"].unique()
    tg = tg[~tg["match_id"].isin(empty)].copy(); pg = pg[~pg["match_id"].isin(empty)].copy(); mt = mt[~mt["match_id"].isin(empty)].copy()
    mt["date"] = pd.to_datetime(mt["date"])
    days = sorted(mt["date"].unique())
    rnd = {d: i for i, d in enumerate(days)}
    mt["round"] = mt["date"].map(rnd)
    tid = {t: i for i, t in enumerate(sorted(set(tg["team"])))}
    mt["home_i"] = mt["home"].map(tid); mt["away_i"] = mt["away"].map(tid)
    matches = mt.rename(columns={"match_id": "game_id", "home_i": "home_id", "away_i": "away_id"})
    matches = pd.DataFrame({"game_id": mt["match_id"], "round": mt["round"], "home": mt["home_i"], "away": mt["away_i"],
                            "hg": mt["hg"], "ag": mt["ag"]})
    # team_game
    tg = tg.rename(columns={"match_id": "game_id"})
    tg["round"] = tg["game_id"].map(dict(zip(mt["match_id"], mt["round"])))
    tg["team_name"] = tg["team"]; tg["team"] = tg["team"].map(tid); tg["opp"] = tg["opp"].map(tid)
    # fouls / yellow "against" = what the opponent committed
    o = tg.set_index(["game_id", "team"])
    for c in ("fouls", "yellow", "xg"):
        tg[c + "_against"] = [o.at[(g, t), c] for g, t in zip(tg["game_id"], tg["opp"])]
    tg["goals"] = tg["goals"].astype(float)
    # player_game
    pg = pg.rename(columns={"match_id": "game_id"})
    pg["round"] = pg["game_id"].map(dict(zip(mt["match_id"], mt["round"])))
    pg["team"] = pg["team"].map(tid)
    opp = dict(zip(zip(tg["game_id"], tg["team"]), tg["opp"]))
    pg["opp"] = [opp[(g, t)] for g, t in zip(pg["game_id"], pg["team"])]
    tot = tg.set_index(["game_id", "team"])[["shots", "sot", "tackles"]]
    for c in ("shots", "sot", "tackles"):
        pg["team_" + c] = [tot.at[(g, t), c] for g, t in zip(pg["game_id"], pg["team"])]
    # unused squad players have no position in the lineup file: use the position they play elsewhere
    known = pg[pg["pos"] != "UNK"].groupby("player")["pos"].agg(lambda x: x.mode().iloc[0])
    pg["pos"] = [p if p != "UNK" else known.get(pl, "UNK") for p, pl in zip(pg["pos"], pg["player"])]
    pg_full = pg[pg["pos"] != "UNK"].copy()                  # includes goalkeepers: the eleven is eleven
    tg = add_xi_features(tg, pg_full)
    pg = pg_full[pg_full["pos"] != "GK"].copy()               # goalkeepers are not in player markets
    return matches, tg, pg, tid


def add_xi_features(tg, pg):
    """Per team-game: how first-choice the eleven is (past 10 matches only) and how many changes vs the last match."""
    starters = {k: set(v) for k, v in pg[pg["started"] == 1].groupby(["game_id", "team"])["player"]}
    reg, chg = {}, {}
    for team, g in tg.sort_values("round").groupby("team"):
        hist, prev = [], None
        for gid in g["game_id"]:
            S = starters.get((gid, team), set())
            last = hist[-10:]
            reg[(gid, team)] = float(np.mean([sum(p in h for h in last) / len(last) for p in S])) if (len(last) >= 3 and S) else np.nan
            chg[(gid, team)] = float(len(S - prev)) if prev is not None and S else np.nan
            hist.append(S); prev = S
    tg = tg.copy()
    tg["xi_reg"] = [reg[(g, t)] for g, t in zip(tg["game_id"], tg["team"])]
    tg["changes"] = [chg[(g, t)] for g, t in zip(tg["game_id"], tg["team"])]
    return tg


if __name__ == "__main__":
    for lg in ("PL", "SA", "L1"):
        m, t, p, tid = load(lg)
        print(lg, len(m), len(t), len(p), "rounds", m["round"].nunique(), "teams", len(tid))
