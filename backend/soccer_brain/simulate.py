"""simulate.py -- synthetic soccer league with hidden tactical traits and star players.

Purpose: test the machinery. Teams have hidden traits (attack, defence,
possession, width, press, low block). Each squad also has two star
defenders and two star attackers whose presence in the starting XI moves
team shots. The engine never sees any of this, only box scores and
lineups, like real data.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def _sigmoid(x):
    return 1.0 / (1.0 + np.exp(-x))


def _schedule(n_teams):
    teams = list(range(n_teams))
    rounds = []
    t = teams[:]
    for _ in range(n_teams - 1):
        pairs = [(t[i], t[n_teams - 1 - i]) for i in range(n_teams // 2)]
        rounds.append(pairs)
        t = [t[0]] + [t[-1]] + t[1:-1]
    first = [[(h, a) if (i + k) % 2 == 0 else (a, h) for k, (h, a) in enumerate(p)]
             for i, p in enumerate(rounds)]
    second = [[(a, h) for (h, a) in p] for p in first]
    return first + second


def simulate_league(n_teams=20, seed=11, wide_block=0.20, press_poss=0.12,
                    star_def=0.07, star_att=0.05):
    rng = np.random.default_rng(seed)
    # Fouls draw from their OWN stream, created here so it is available while the squads are built.
    # Taking them from `rng` shifted every later draw and produced a different league for the same
    # seed -- which broke selftest_lines, a test that asserts something about the shape of the
    # league and nothing about fouls. A fixture other tests depend on must stay bit-identical when
    # a column is added to it.
    rng_f = np.random.default_rng(seed * 7919 + 13)
    T = n_teams
    att = rng.normal(0, 0.22, T); dfn = rng.normal(0, 0.22, T)
    poss = rng.normal(0, 1, T); wide = rng.normal(0, 1, T)
    press = rng.normal(0, 1, T); block = rng.normal(0, 1, T)

    # ---- squads: 14 players, two defensive stars and two attacking stars each
    pos_list = ["FWD"] * 3 + ["MID"] * 4 + ["DEF"] * 4 + ["FWD", "MID", "DEF"]

    # GK weights are 0.0 throughout: a keeper takes no shots, makes no tackles and scores no goals,
    # so he must receive none of a team's allocation of them. His one market is saves, which is
    # assigned directly rather than shared out.
    base_w = {"shots": {"FWD": 3.0, "MID": 1.2, "DEF": 0.4, "GK": 0.0},
              "tackles": {"FWD": 0.7, "MID": 1.5, "DEF": 1.6, "GK": 0.0},
              # Goals go mostly to forwards; assists are flatter and tilt to midfield. Shaped so a
              # squad contains both players who score often enough for a goal market to mean
              # something and players who do not -- which is the thing the eligibility gate has to
              # be able to tell apart.
              "goals": {"FWD": 4.0, "MID": 1.1, "DEF": 0.25, "GK": 0.0},
              "assists": {"FWD": 1.6, "MID": 2.2, "DEF": 0.5, "GK": 0.0},
              # Fouls tilt to the middle and the back, and they are far more EVEN across a squad
              # than goals are -- nearly everyone commits one sometimes, where most players never
              # score. That evenness is the point: it is what lets a fouls line clear the ordinary
              # likelihood band where a goals line cannot (docs/70).
              "fouls_committed": {"FWD": 1.0, "MID": 1.5, "DEF": 1.3, "GK": 0.1}}
    players = []
    for t in range(T):
        def_idx = [k for k, p in enumerate(pos_list) if p == "DEF"]
        fwd_idx = [k for k, p in enumerate(pos_list) if p == "FWD"]
        def_stars = set(rng.choice(def_idx, 2, replace=False))
        att_stars = set(rng.choice(fwd_idx, 2, replace=False))
        for k, pos in enumerate(pos_list):
            starter_core = k < 11
            ps = rng.choice([0.9, 0.55]) if starter_core else 0.35
            players.append(dict(
                player=t * 100 + k, team=t, pos=pos, p_start=ps,
                skill_shots=np.exp(rng.normal(0, 0.35)),
                skill_tackles=np.exp(rng.normal(0, 0.3)),
                # Wider spread than shots: whether a player scores often enough to be worth a goal
                # market is the thing the eligibility gate has to decide, so the squad has to
                # contain a real range rather than eleven similar players.
                skill_goals=np.exp(rng.normal(0, 0.55)),
                skill_assists=np.exp(rng.normal(0, 0.45)),
                # A narrow spread, deliberately: a squad has no "foul specialists" the way it has
                # goal specialists, so the market's value has to come from the opponent and the
                # game rather than from one player being ten times likelier than another.
                skill_fouls_committed=float(np.exp(rng_f.normal(0, 0.25))),
                # How much of what reaches him a keeper keeps out. A narrow spread: the difference
                # between keepers is real but small next to the difference between the defences in
                # front of them, which is the team layer's job to know.

                # A narrow spread, deliberately: a squad has no "foul specialists" the way it has
                # goal specialists, so the market's value has to come from the opponent and the
                # game rather than from one player being ten times likelier than another.

                q_def=1.0 if k in def_stars else rng.normal(0, 0.2),
                q_att=1.0 if k in att_stars else rng.normal(0, 0.2)))
    squads = {t: [p for p in players if p["team"] == t] for t in range(T)}
    # The keeper is held OUTSIDE `squads`, and every number about him comes off rng_f. The lineup
    # loop draws once per squad member, so a fifteenth player would shift every later draw and
    # change the league for a seed that has to keep producing the same one. He plays the full
    # ninety, as a first-choice keeper does, so he needs no share of the lineup model at all.
    #
    # The narrow skill spread is the honest shape: the difference between keepers is real but
    # small beside the difference between the defences in front of them -- which is the team
    # layer's job to know, and the reason a saves market is worth modelling at all.
    keepers = {t: dict(player=t * 100 + 90, team=t, pos="GK",
                       skill_saves=float(np.exp(rng_f.normal(0, 0.18)))) for t in range(T)}

    matches, tgs, pgs = [], [], []
    gid = 0
    sched = _schedule(T)
    for rnd, pairs in enumerate(sched):
        for (h, a) in pairs:
            lam_h = np.exp(0.33 + att[h] - dfn[a])
            lam_a = np.exp(0.05 + att[a] - dfn[h])
            hg, ag = rng.poisson(lam_h), rng.poisson(lam_a)
            matches.append(dict(game_id=gid, round=rnd, home=h, away=a, hg=hg, ag=ag))

            # ---- lineups first: team stats depend on who plays
            lineup = {}
            for X in (h, a):
                squad = squads[X]
                score = np.array([p["p_start"] + rng.uniform(0, 0.5) for p in squad])
                starters = set(np.argsort(-score)[:11])
                bench = [i for i in range(len(squad)) if i not in starters]
                subs = set(i for i in bench if rng.random() < 0.55)
                minutes = np.zeros(len(squad))
                for i in range(len(squad)):
                    if i in starters:
                        minutes[i] = float(np.clip(rng.normal(80, 14), 30, 90))
                    elif i in subs:
                        minutes[i] = rng.uniform(10, 35)
                att_score = sum(squad[i]["q_att"] for i in starters if squad[i]["pos"] in ("FWD", "MID"))
                def_score = sum(squad[i]["q_def"] for i in starters if squad[i]["pos"] in ("DEF", "MID"))
                lineup[X] = dict(starters=starters, minutes=minutes, att=att_score, dfn=def_score)

            side = {}
            for X, Y, is_home, lamX, lamY in ((h, a, 1, lam_h, lam_a), (a, h, 0, lam_a, lam_h)):
                d = lamY - lamX
                share = _sigmoid(0.35 * (poss[X] - poss[Y]) + 0.8 * ((att[X] - dfn[Y]) - (att[Y] - dfn[X])) + 0.1 * is_home)
                poss_obs = 100 * share + rng.normal(0, 3)
                log_shots = (np.log(12) + 1.0 * (att[X] - dfn[Y]) + 0.10 * poss[X]
                             - 0.10 * block[Y] + 0.07 * is_home + 0.05 * d
                             + star_att * lineup[X]["att"] - star_def * lineup[Y]["dfn"])
                shots = rng.negative_binomial(30, 30 / (30 + np.exp(log_shots)))
                acc = _sigmoid(-0.85 + 0.9 * (att[X] - dfn[Y]))
                sot = rng.binomial(shots, acc)
                log_corn = (np.log(5) + 0.18 * wide[X] + 0.12 * block[Y]
                            + wide_block * wide[X] * block[Y]
                            + 0.35 * (log_shots - np.log(12)) + 0.04 * d)
                corners = rng.negative_binomial(40, 40 / (40 + np.exp(log_corn)))
                log_tck = (np.log(17) + 0.12 * press[X] - 0.15 * poss[X] + 0.15 * poss[Y]
                           + press_poss * press[X] * poss[Y])
                tackles = rng.negative_binomial(60, 60 / (60 + np.exp(log_tck)))
                side[X] = dict(game_id=gid, round=rnd, team=X, opp=Y, home=is_home,
                               goals=hg if X == h else ag, goals_against=ag if X == h else hg,
                               shots=shots, sot=sot, corners=corners, tackles=tackles, poss=poss_obs)

            for X, Y in ((h, a), (a, h)):
                side[X]["shots_against"] = side[Y]["shots"]
                side[X]["sot_against"] = side[Y]["sot"]
                side[X]["corners_against"] = side[Y]["corners"]
                side[X]["tackles_against"] = side[Y]["tackles"]
                tgs.append(side[X])

                squad = squads[X]
                minutes = lineup[X]["minutes"]; starters = lineup[X]["starters"]
                alloc = {}
                # Not every goal is assisted, and an assist cannot come from the scorer, so the
                # count is drawn from the goals rather than equal to them.
                g_tot = int(side[X]["goals"])
                a_tot = int(rng.binomial(g_tot, 0.7)) if g_tot else 0
                # A team's fouls in a match: around eleven, overdispersed, and not a function of
                # how well the side is playing -- which is what makes it a different signal from
                # shots rather than a restatement of one.
                #
                # Drawn from a SEPARATE generator. Taking these from `rng` shifted every later draw
                # and silently produced a different league for the same seed, which broke
                # selftest_lines -- a test that asserts something about the shape of the league,
                # not about fouls. A fixture other tests depend on must stay bit-identical when a
                # column is added to it.
                f_tot = int(rng_f.negative_binomial(8, 8 / (8 + 11.0)))
                # The team layer has to forecast a stat before the player layer can take a share of
                # it (docs/70), so the team row carries both markets. `side[X]` is the same dict
                # already appended to tgs, so setting it here fills the row that was stored.
                side[X]["fouls_committed"] = f_tot
                side[X]["goal_involvements"] = g_tot + a_tot
                # Saves are what the opponent put on target and did not score. That is the real
                # relationship, and it is why the market is worth modelling: it is a forecast about
                # the DEFENCE in front of the keeper as much as about the keeper.
                faced = int(side[Y]["sot"])
                conceded = int(side[X]["goals_against"])
                s_tot = max(faced - conceded, 0)
                # A better keeper keeps out a shade more of what reaches him.
                s_tot = int(round(s_tot * keepers[X]["skill_saves"]))
                side[X]["saves"] = s_tot
                for stat, tot, key in (("shots", side[X]["shots"], "shots"),
                                       ("sot", side[X]["sot"], "shots"),
                                       ("tackles", side[X]["tackles"], "tackles"),
                                       ("goals", g_tot, "goals"),
                                       ("assists", a_tot, "assists")):
                    w = np.array([base_w[key][p["pos"]] * p["skill_" + key] * minutes[i] / 90.0
                                  for i, p in enumerate(squad)])
                    if stat == "sot":
                        w = w * np.exp(rng.normal(0, 0.1, len(w)))
                    alloc[stat] = rng.multinomial(tot, w / w.sum()) if w.sum() > 0 else np.zeros(len(w), int)
                # ...and the foul allocation likewise, off the shared stream.
                wf = np.array([base_w["fouls_committed"][p["pos"]] * p["skill_fouls_committed"] * minutes[i] / 90.0
                               for i, p in enumerate(squad)])
                alloc["fouls_committed"] = (rng_f.multinomial(f_tot, wf / wf.sum()) if wf.sum() > 0
                                            else np.zeros(len(wf), int))
                gk = keepers[X]
                pgs.append(dict(game_id=gid, round=rnd, team=X, opp=Y, player=gk["player"],
                                pos="GK", started=1, minutes=90.0,
                                shots=0, sot=0, tackles=0, goals=0, assists=0,
                                fouls_committed=0, goal_involvements=0,
                                saves=s_tot, team_saves=s_tot,
                                team_shots=side[X]["shots"], team_sot=side[X]["sot"],
                                team_tackles=side[X]["tackles"],
                                team_fouls_committed=f_tot, team_goal_involvements=g_tot + a_tot))
                for i, p in enumerate(squad):
                    pgs.append(dict(game_id=gid, round=rnd, team=X, opp=Y, player=p["player"],
                                    pos=p["pos"], started=int(i in starters), minutes=minutes[i],
                                    shots=int(alloc["shots"][i]), sot=int(alloc["sot"][i]),
                                    tackles=int(alloc["tackles"][i]),
                                    goals=int(alloc["goals"][i]), assists=int(alloc["assists"][i]),
                                    fouls_committed=int(alloc["fouls_committed"][i]),
                                    saves=0, team_saves=s_tot,
                                    # goals + assists, counted ONCE -- the same derivation
                                    # normalize.players does at ingest (docs/70).
                                    goal_involvements=int(alloc["goals"][i]) + int(alloc["assists"][i]),
                                    team_shots=side[X]["shots"], team_sot=side[X]["sot"],
                                    team_tackles=side[X]["tackles"],
                                    team_fouls_committed=f_tot, team_goal_involvements=g_tot + a_tot))
            # The mirrors, after both sides have their totals -- they cannot be set in the loop
            # above because the second side's numbers do not exist while the first is being built.
            for X, Y in ((h, a), (a, h)):
                for col in ("fouls_committed", "goal_involvements", "saves"):
                    side[X][col + "_against"] = side[Y][col]
            gid += 1

    truth = dict(att=att, dfn=dfn, poss=poss, wide=wide, press=press, block=block,
                 q_def={p["player"]: p["q_def"] for p in players},
                 q_att={p["player"]: p["q_att"] for p in players})
    return (pd.DataFrame(matches), pd.DataFrame(tgs), pd.DataFrame(pgs), truth)
