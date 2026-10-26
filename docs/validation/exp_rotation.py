"""exp_rotation.py -- does the calendar change WHO starts? (StatsBomb 2015/16 lineups + league and Champions League calendar)

Caveat stated up front: cups and the Europa League for 2015/16 are not in the free schedule, so "rest"
is measured from league and Champions League matches only. That can only HIDE an effect (a cup tie
three days earlier looks like a week of rest), never invent one.
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "engine"))
import numpy as np, pandas as pd
import load as OF
import load_statsbomb as L
import context as C

HERE = os.path.dirname(os.path.abspath(__file__))
ALIAS = {"as roma": "roma", "olympique lyonnais": "lyon", "ssc napoli": "napoli", "fc internazionale milano": "internazionale",
         "ac milan": "milan", "ss lazio": "lazio", "fc juventus": "juventus", "manchester city": "man city"}


def nn(x):
    n = OF.norm(x)
    return ALIAS.get(n, n)


def calendar(lg, matches, tg, tid):
    inv = {v: k for k, v in tid.items()}
    rows = []
    mt = pd.read_pickle(os.path.join(HERE, "data", "sb", f"mt_{lg}.pkl"))
    for r in mt.itertuples():
        for team in (r.home, r.away):
            rows.append((tid[team], pd.Timestamp(r.date) + pd.Timedelta(hours=15), "league", ""))
    eu = OF.parse_file(os.path.join(HERE, "data", "openfootball_champions-league", "2015-16", "cl.txt"), "2015-16", "UCL")
    names = {nn(t): i for t, i in tid.items()}
    n_eu = 0
    for e in eu:
        for side in ("home", "away"):
            k = nn(e[side + "_raw"])
            k = ALIAS.get(k, k)
            if k in names:
                rows.append((names[k], pd.Timestamp(e["dt"]), "ucl", e["stage"])); n_eu += 1
    cal = C.Calendar(pd.DataFrame(rows, columns=["team", "kickoff", "comp", "stage"]))
    return cal, n_eu


def context_rows(lg):
    matches, tg, pg, tid = L.load(lg)
    cal, n_eu = calendar(lg, matches, tg, tid)
    mt = pd.read_pickle(os.path.join(HERE, "data", "sb", f"mt_{lg}.pkl")).rename(columns={"match_id": "game_id"})
    gdate = dict(zip(mt["game_id"], pd.to_datetime(mt["date"]) + pd.Timedelta(hours=15)))
    out = []
    for r in tg.itertuples():
        c = cal.context(r.team, gdate[r.game_id], "league", "")
        c.update(C.pressure_parts(c))
        c.update(game_id=r.game_id, team=r.team, changes=r.changes, xi_reg=r.xi_reg, round=r.round)
        out.append(c)
    return pd.DataFrame(out), pg, tg, n_eu


if __name__ == "__main__":
    allrows = []
    for lg in ("PL", "SA", "L1"):
        ctx, pg, tg, n_eu = context_rows(lg)
        ctx["league"] = lg
        allrows.append(ctx)
        print(lg, "context rows", len(ctx), "| European calendar rows used:", n_eu)
    ctx = pd.concat(allrows)
    ctx.to_pickle(os.path.join(HERE, "data", "ctx_rows.pkl"))
    c = ctx.dropna(subset=["changes"])
    print("\nTEAM LEVEL: changes to the starting eleven vs the previous match")
    print("  all matches: mean changes", round(c.changes.mean(), 2), "n", len(c))
    for lab, m in (("rest <= 3.5 days", c.rest_days <= 3.5), ("rest 3.5 to 5.5 days", (c.rest_days > 3.5) & (c.rest_days <= 5.5)), ("rest > 5.5 days", c.rest_days > 5.5)):
        g = c[m]; print(f"  {lab:24s} n={len(g):4d}  changes {g.changes.mean():.2f} +/- {g.changes.std(ddof=1)/np.sqrt(len(g)):.2f}")
    for lab, m in (("European match within 4.5 days AFTER", (c.next_gap <= 4.5) & (c.next_imp > 0.9) & (c.next_comp == "ucl")),
                   ("no European match soon", ~((c.next_gap <= 4.5) & (c.next_comp == "ucl")))):
        g = c[m]; print(f"  {lab:38s} n={len(g):4d}  changes {g.changes.mean():.2f} +/- {g.changes.std(ddof=1)/np.sqrt(max(len(g),1)):.2f}")
