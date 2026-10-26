"""sb_extract.py -- turn StatsBomb open-data events (CC BY-NC-style attribution required) into compact tables.

Used ONLY to validate the idea on real matches. Raw files are deleted after each match.
Output (data/sb/*.pkl): team_game, player_game, matches.
"""
import json, os, subprocess, sys, tempfile, math, collections
from multiprocessing import Pool
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "data", "sb")
B = "https://raw.githubusercontent.com/statsbomb/open-data/master/data"
LEAGUES = {"PL": (2, 27), "SA": (12, 27), "L1": (7, 27)}

DEF_ACTIONS = ("Interception", "Foul Committed")


def get(url, path):
    for _ in range(3):
        r = subprocess.run(["curl", "-sS", "-m", "120", "-f", "-o", path, url], capture_output=True)
        if r.returncode == 0:
            return True
    return False


def pos_group(name):
    n = name.lower()
    if "goalkeeper" in n: return "GK"
    if "back" in n: return "DEF"
    if "midfield" in n: return "MID"
    return "FWD"                       # wings, forwards, strikers


def mmss(s):
    if s is None: return None
    m, sec = s.split(":")[:2]
    return int(m) + int(sec) / 60.0


def ts(s):
    h, m, sec = s.split(":")
    return int(h) * 3600 + int(m) * 60 + float(sec)


def process(args):
    league, m = args
    mid = m["match_id"]
    tmp = tempfile.mkdtemp(prefix="sb_")
    ep, lp = os.path.join(tmp, "e.json"), os.path.join(tmp, "l.json")
    try:
        if not (get(f"{B}/events/{mid}.json", ep) and get(f"{B}/lineups/{mid}.json", lp)):
            return None
        ev = json.load(open(ep)); lu = json.load(open(lp))
    finally:
        for f in (ep, lp):
            if os.path.exists(f): os.remove(f)
        try: os.rmdir(tmp)
        except OSError: pass
    home, away = m["home_team"]["home_team_name"], m["away_team"]["away_team_name"]
    teams = [home, away]
    ev = [e for e in ev if e["period"] <= 2]            # no extra time / shoot-outs in league games anyway
    end_min = max((e["minute"] + e["second"] / 60.0 for e in ev), default=90.0)
    end_min = max(end_min, 90.0)

    T = {t: collections.defaultdict(float) for t in teams}
    P = collections.defaultdict(lambda: collections.defaultdict(float))        # (team, player_id) -> counts
    form = {}; start_pos = {t: [] for t in teams}
    final3_pass = {t: 0 for t in teams}; pass_n = {t: 0 for t in teams}
    seqs = collections.defaultdict(list)                                       # possession id -> events
    opp = {home: away, away: home}
    da_x = {t: [] for t in teams}                                              # defensive action x (own goal = 0)

    # pass 1: events
    for e in ev:
        t = e["type"]["name"]; tm = e["team"]["name"]
        if tm not in T: continue
        loc = e.get("location")
        if t == "Starting XI":
            form[tm] = e["tactics"]["formation"]
            start_pos[tm] = [(p["player"]["id"], pos_group(p["position"]["name"])) for p in e["tactics"]["lineup"]]
        seqs[e["possession"]].append(e)
        pid = e.get("player", {}).get("id")
        if t == "Pass":
            pa = e["pass"]; T[tm]["passes"] += 1
            if loc and loc[0] >= 80: T[tm]["final3_passes"] += 1
            if pa.get("length", 0) >= 35: T[tm]["long_balls"] += 1
            if pa.get("type", {}).get("name") == "Corner": T[tm]["corners"] += 1
            if pa.get("cross"): T[tm]["crosses"] += 1
            if loc and loc[0] <= 72: T[opp[tm]]["opp_passes_zone"] += 1          # passes allowed in the pressing zone
        elif t == "Shot":
            s = e["shot"]; xg = s.get("statsbomb_xg", 0.0)
            T[tm]["shots"] += 1; T[tm]["xg"] += xg
            on = s["outcome"]["name"] in ("Goal", "Saved", "Saved to Post")
            T[tm]["sot"] += 1 if on else 0
            if e["play_pattern"]["name"] == "From Counter":
                T[tm]["counter_shots"] += 1; T[tm]["counter_xg"] += xg
            if pid is not None:
                P[(tm, pid)]["shots"] += 1; P[(tm, pid)]["sot"] += 1 if on else 0
        elif t == "Duel" and e.get("duel", {}).get("type", {}).get("name") == "Tackle":
            T[tm]["tackles"] += 1
            if pid is not None: P[(tm, pid)]["tackles"] += 1
            if loc:
                da_x[tm].append(loc[0])
                if loc[0] >= 48: T[tm]["def_actions_zone"] += 1
                if loc[0] >= 80 and e["duel"].get("outcome", {}).get("name") in ("Won", "Success In Play", "Success Out"):
                    T[tm]["high_turnovers"] += 1
        elif t in DEF_ACTIONS:
            if t == "Foul Committed":
                T[tm]["fouls"] += 1
                c = e.get("foul_committed", {}).get("card", {}).get("name", "")
                if "Yellow" in c: T[tm]["yellow"] += 1
                if "Red" in c: T[tm]["red"] += 1
            if loc:
                da_x[tm].append(loc[0])
                if loc[0] >= 48: T[tm]["def_actions_zone"] += 1
                if t == "Interception" and loc[0] >= 80: T[tm]["high_turnovers"] += 1
        elif t == "Ball Recovery" and loc and loc[0] >= 80 and not e.get("ball_recovery", {}).get("recovery_failure"):
            T[tm]["high_turnovers"] += 1
        elif t == "Pressure":
            T[tm]["pressures"] += 1
            if loc and loc[0] >= 60: T[tm]["pressures_opp_half"] += 1
            if loc: da_x[tm].append(loc[0])
            if e.get("counterpress"): T[tm]["counterpress"] += 1

    # pass 2: possession sequences (open play)
    for pid_, es in seqs.items():
        tm = es[0]["possession_team"]["name"]
        if tm not in T: continue
        pp = es[0]["play_pattern"]["name"]
        mine = [e for e in es if e["team"]["name"] == tm and e.get("location")]
        passes = [e for e in mine if e["type"]["name"] == "Pass"]
        if not mine: continue
        T[tm]["seq_n"] += 1 if passes else 0
        T[tm]["seq_passes"] += len(passes)
        if pp in ("Regular Play", "From Counter", "From Keeper", "From Goal Kick", "From Throw In"):
            t0 = ts(es[0]["timestamp"]); t1 = ts(es[-1]["timestamp"]) + (es[-1].get("duration") or 0)
            dur = max(t1 - t0, 0.0)
            sx = mine[0]["location"][0]
            last = mine[-1]
            ex = (last.get("pass", {}).get("end_location") or last.get("carry", {}).get("end_location") or last["location"])[0]
            if dur >= 1.0 and es[0]["period"] == es[-1]["period"]:
                T[tm]["direct_m"] += max(ex - sx, 0.0) * 0.9144
                T[tm]["direct_s"] += dur
            shots = [e for e in mine if e["type"]["name"] == "Shot"]
            if shots and pp != "From Corner":
                if ts(shots[0]["timestamp"]) - t0 <= 12.0 and len(passes) <= 4:
                    T[tm]["quick_shots"] += 1

    # lineups -> player rows
    prow = []
    for tl in lu:
        tm = tl["team_name"]
        if tm not in T: continue
        for pl in tl["lineup"]:
            if not pl["positions"]:                      # in the matchday squad but never played
                prow.append(dict(match_id=mid, team=tm, player=pl["player_id"], name=pl["player_name"], pos="UNK",
                                 started=0, minutes=0.0, shots=0.0, sot=0.0, tackles=0.0))
                continue
            started = any(p["start_reason"] == "Starting XI" for p in pl["positions"])
            minutes = 0.0
            for p in pl["positions"]:
                a = mmss(p["from"]); b = mmss(p["to"]) if p["to"] else end_min
                minutes += max((b if b is not None else end_min) - (a or 0.0), 0.0)
            grp = pos_group(pl["positions"][0]["position"])
            c = P[(tm, pl["player_id"])]
            prow.append(dict(match_id=mid, team=tm, player=pl["player_id"], name=pl["player_name"], pos=grp,
                             started=int(started), minutes=min(minutes, end_min),
                             shots=c["shots"], sot=c["sot"], tackles=c["tackles"]))

    # team rows
    rows = []
    tot_pass = max(sum(T[t]["passes"] for t in teams), 1)
    for tm in teams:
        o = opp[tm]; a, b = T[tm], T[o]
        hg = m["home_score"]; ag = m["away_score"]
        goals, ga = (hg, ag) if tm == home else (ag, hg)
        n_def = sum(1 for _, g in start_pos[tm] if g == "DEF"); n_mid = sum(1 for _, g in start_pos[tm] if g == "MID")
        n_fwd = sum(1 for _, g in start_pos[tm] if g == "FWD")
        rows.append(dict(
            match_id=mid, league=league, date=m["match_date"], team=tm, opp=o, home=int(tm == home),
            goals=goals, goals_against=ga, formation=form.get(tm), formation_opp=form.get(o),
            n_def=n_def, n_mid=n_mid, n_fwd=n_fwd,
            shots=a["shots"], sot=a["sot"], corners=a["corners"], tackles=a["tackles"],
            xg=a["xg"], xg_against=b["xg"], shots_against=b["shots"], sot_against=b["sot"],
            corners_against=b["corners"], tackles_against=b["tackles"],
            poss=100.0 * a["passes"] / tot_pass,
            fouls=a["fouls"], yellow=a["yellow"], red=a["red"],
            passes=a["passes"], long_ball_pct=100.0 * a["long_balls"] / max(a["passes"], 1),
            field_tilt=100.0 * a["final3_passes"] / max(a["final3_passes"] + b["final3_passes"], 1),
            ppda=0.0,
            ppda_n=a["def_actions_zone"], opp_passes_zone=a["opp_passes_zone"],
            ada=(sum(da_x[tm]) / len(da_x[tm])) if da_x[tm] else None,
            passes_per_seq=a["seq_passes"] / max(a["seq_n"], 1),
            direct_speed=(a["direct_m"] / a["direct_s"]) if a["direct_s"] > 0 else None,
            high_turnovers=a["high_turnovers"], counter_shots=a["counter_shots"], counter_xg=a["counter_xg"],
            quick_shots=a["quick_shots"], pressures=a["pressures"], pressures_opp_half=a["pressures_opp_half"],
            counterpress=a["counterpress"], crosses=a["crosses"],
        ))
    # fix PPDA: opponent passes allowed (in the pressing zone) / our defensive actions in that zone
    for r in rows:
        r["ppda"] = r["opp_passes_zone"] / max(r["ppda_n"], 1)
    return rows, prow, dict(match_id=mid, league=league, date=m["match_date"], home=home, away=away,
                            hg=m["home_score"], ag=m["away_score"], end_min=end_min)


if __name__ == "__main__":
    os.makedirs(OUT, exist_ok=True)
    only = sys.argv[1:] or list(LEAGUES)
    for lg in only:
        cid, sid = LEAGUES[lg]
        mf = os.path.join(OUT, f"m_{lg}.json")
        if not os.path.exists(mf):
            get(f"{B}/matches/{cid}/{sid}.json", mf)
        ms = json.load(open(mf))
        print(lg, len(ms), "matches", flush=True)
        with Pool(3) as pool:
            res = [r for r in pool.imap_unordered(process, [(lg, m) for m in ms], chunksize=4) if r]
        tg = pd.DataFrame([r for rs, _, _ in res for r in rs])
        pg = pd.DataFrame([r for _, ps, _ in res for r in ps])
        mt = pd.DataFrame([x for _, _, x in res])
        tg.to_pickle(os.path.join(OUT, f"tg_{lg}.pkl")); pg.to_pickle(os.path.join(OUT, f"pg_{lg}.pkl")); mt.to_pickle(os.path.join(OUT, f"mt_{lg}.pkl"))
        print(lg, "done", len(tg), len(pg), flush=True)
