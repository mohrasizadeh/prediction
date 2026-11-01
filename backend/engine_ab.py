"""engine_ab.py -- does a change to the engine actually forecast better? Run it on the real database (read only).

    MONGO_URL=... DB_NAME=... python engine_ab.py --league 3
    MONGO_URL=... DB_NAME=... python engine_ab.py --league 3 --only script_v2,opp_pos

Walk-forward, the same rule the rest of the engine lives by: for every round, each variant is refitted on earlier
rounds ONLY, then forecasts that round, then the round is scored. Nothing from the round being scored is used to
make the forecast, so the numbers are what you would have seen on the day.

Three scores, each the mean log-likelihood of what really happened (higher is better, they are negative):
  * team counts    the whole count distribution for shots, shots on target, corners, tackles.
  * player counts  the same for each player's shots, shots on target and tackles, with the real starting eleven
                   handed to every variant, scored on players who started.
  * match result   home / draw / away.

The verdict is paired: the same fixture scored by both variants, so league strength and luck cancel. A change
PASSES when it is better AND the gain is at least `--z` paired standard errors (2.0 = the project's gate).

Nothing is written to the database and no setting is changed. If a variant passes, switch its setting on in
Admin -> Settings; the names are printed with the result. See docs/37.
"""
from __future__ import annotations

import argparse
import math
import os
import sys
import time
from collections import defaultdict

import numpy as np

import engine_bridge as B
import settings_store as S

# variant -> (engine attributes to set, the setting an owner switches on if it passes)
VARIANTS = {
    "base": ({}, "(production settings, unchanged)"),
    "script_v2": ({"script_v2": True}, "engine.script_v2"),
    "fit_player_r": ({"fit_player_r": True}, "engine.fit_player_r"),
    "opp_pos": ({"opp_pos_k": 20.0}, "engine.opp_pos_k"),
    "xg_blend": ({"xg_blend": 0.5}, "engine.xg_blend"),
    "all": ({"script_v2": True, "fit_player_r": True, "opp_pos_k": 20.0, "xg_blend": 0.5}, "(all four)"),
}
PLAYER_STATS = ("shots", "sot", "tackles")


def nb_ll(y, mu, r):
    """log P(count = y) for a negative binomial with mean mu and dispersion r."""
    from scipy.special import gammaln
    mu = max(float(mu), 1e-9); r = max(float(r), 1e-6); y = float(y)
    return float(gammaln(y + r) - gammaln(r) - gammaln(y + 1)
                 + r * math.log(r / (r + mu)) + y * math.log(mu / (r + mu)))


def build_engine(db, overrides: dict):
    """Production settings first, so 'base' is exactly what the app runs today, then the variant on top."""
    eng = B.configure_engine(db)
    for k, v in overrides.items():
        setattr(eng, k, v)
    return eng


def paired(scores: dict, ref: str, name: str, key):
    """Gain of `name` over `ref` on the rows both scored, with the paired standard error."""
    a, b = scores[name], scores[ref]
    common = [k for k in a if k in b]
    if len(common) < 30:
        return None
    d = np.array([a[k] - b[k] for k in common], float)
    se = float(d.std(ddof=1) / math.sqrt(len(d))) if len(d) > 2 else float("nan")
    return {"n": len(d), "mean": float(np.mean([a[k] for k in common])), "gain": float(d.mean()),
            "se": se, "z": float(d.mean() / se) if se and se > 0 else 0.0}


def run_league(db, league_iid, names, rounds, refit_every, burn, z_min, verbose=True):
    hist = int(S.get(db, "engine.history_rounds"))
    frames = B.build_frames(db, league_iid, hist)
    if not frames:
        print(f"  league {league_iid}: no finished matches with stats"); return None
    ms, tg, pg = frames
    all_rounds = sorted(ms["round"].unique())
    if rounds:
        all_rounds = all_rounds[-rounds:]
    start = all_rounds[0] if len(all_rounds) > burn else None
    play = [r for r in all_rounds if r >= (all_rounds[0] + burn if not rounds else all_rounds[0])]
    if len(play) < 3:
        print(f"  league {league_iid}: not enough rounds to walk forward ({len(all_rounds)})"); return None
    if verbose:
        print(f"  league {league_iid}: {len(ms)} matches, {len(tg)} team-games, {len(pg)} player-games, "
              f"scoring rounds {play[0]}..{play[-1]}")

    tgi = tg.set_index(["game_id", "team"])
    pgi = {gid: g for gid, g in pg.groupby("game_id")}
    team_s = {n: defaultdict(dict) for n in names}      # variant -> stat -> key -> ll
    play_s = {n: defaultdict(dict) for n in names}
    res_s = {n: {} for n in names}
    engines, t0 = {}, time.time()

    for i, r in enumerate(play):
        if i % refit_every == 0 or not engines:
            for n in names:
                engines[n] = build_engine(db, VARIANTS[n][0]).fit(ms, tg, pg, r)
            if verbose:
                print(f"    refit at round {r} ({time.time() - t0:.0f}s)", flush=True)
        for m in ms[ms["round"] == r].itertuples():
            ref_eng = engines[names[0]]
            if m.home not in ref_eng.tidx or m.away not in ref_eng.tidx:
                continue
            rows = pgi.get(m.game_id)
            starters = {}
            if rows is not None:
                for t in (m.home, m.away):
                    st = rows[(rows["team"] == t) & (rows["started"] == 1)]
                    if len(st) >= 7:
                        starters[t] = set(int(x) for x in st["player"])
            actual = {(int(x.team), int(x.player)): x for x in rows.itertuples()} if rows is not None else {}

            for n in names:
                eng = engines[n]
                try:
                    fcs, probs = eng.predict_fixture(m.home, m.away, lineups=starters or None)
                except Exception as e:                       # one odd fixture must not kill the run
                    if verbose:
                        print(f"    skipped game {m.game_id} for {n}: {type(e).__name__}", file=sys.stderr)
                    continue
                means = eng.team_means(m.home, m.away)
                for team in (m.home, m.away):
                    if (m.game_id, team) not in tgi.index:
                        continue
                    row = tgi.loc[(m.game_id, team)]
                    for s in eng.stats:
                        if s not in row or row[s] != row[s]:
                            continue
                        mu, rr, _ = means[team][s]
                        team_s[n][s][(m.game_id, team)] = nb_ll(row[s], mu, rr)
                seen = set()
                for f in fcs:
                    if f.scope != "player" or f.stat not in PLAYER_STATS:
                        continue
                    key = (m.game_id, int(f.player), f.stat)
                    if key in seen:
                        continue
                    seen.add(key)
                    a = actual.get((int(f.team), int(f.player)))
                    if a is None or not getattr(a, "started", 0) or getattr(a, "minutes", 0) <= 0:
                        continue
                    y = getattr(a, f.stat, None)
                    if y is None or y != y:
                        continue
                    play_s[n][f.stat][key] = nb_ll(y, f.expected, eng.r_player[f.stat])
                y_res = 0 if m.hg > m.ag else 1 if m.hg == m.ag else 2
                p = (probs["p_home"], probs["p_draw"], probs["p_away"])
                res_s[n][m.game_id] = math.log(max(p[y_res], 1e-4))
    return {"team": team_s, "player": play_s, "result": res_s}


def report(out, names, z_min):
    ref = names[0]
    print(f"\n{'':14}{'variant':14}{'n':>7}{'mean ll':>10}{'gain':>10}{'se':>8}{'z':>7}  verdict")
    verdicts = {}
    for kind in ("team", "player", "result"):
        buckets = {}
        if kind == "result":
            buckets["match result"] = {n: out[kind][n] for n in names}
        else:
            stats = sorted({s for n in names for s in out[kind][n]})
            for s in stats:
                buckets[f"{kind} {s}"] = {n: out[kind][n][s] for n in names}
            if stats:
                buckets[f"{kind} ALL"] = {n: {(s, k): v for s in stats for k, v in out[kind][n][s].items()} for n in names}
        for label, scores in buckets.items():
            for n in names[1:]:
                st = paired(scores, ref, n, None)
                if not st:
                    continue
                ok = st["gain"] > 0 and st["z"] >= z_min
                if label.endswith("ALL") or label == "match result":
                    verdicts.setdefault(n, []).append((label, ok, st["z"]))
                print(f"{label:28}{n:14}{st['n']:>7}{st['mean']:>10.4f}{st['gain']:>+10.4f}{st['se']:>8.4f}{st['z']:>+7.2f}  "
                      f"{'PASS' if ok else 'no'}")
            print()
    print("=" * 78)
    print("VERDICT (the gate: better, by at least %.1f paired standard errors)" % z_min)
    for n in names[1:]:
        rows = verdicts.get(n, [])
        won = [l for l, ok, _ in rows if ok]
        setting = VARIANTS[n][1]
        if won:
            print(f"  {n:14} PASSES on: {', '.join(won)}   -> switch on {setting}")
        else:
            best = max((z for _, _, z in rows), default=0.0)
            print(f"  {n:14} does not pass (best z {best:+.2f})   -> leave {setting} off")
    print("\nNothing was changed. Put the result in docs/37 either way, so the next person knows it was tested.")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--league", type=int, action="append", help="league iid; repeat for more, default every league with data")
    ap.add_argument("--rounds", type=int, default=40, help="score the last N rounds (default 40)")
    ap.add_argument("--refit-every", type=int, default=4, help="refit every N rounds (default 4)")
    ap.add_argument("--burn", type=int, default=0, help="skip this many rounds before scoring")
    ap.add_argument("--z", type=float, default=2.0, help="standard errors needed to pass (default 2.0)")
    ap.add_argument("--only", help="comma-separated variants: " + ", ".join(n for n in VARIANTS if n != "base"))
    a = ap.parse_args()

    choices = [n for n in VARIANTS if n != "base"]
    names = ["base"] + (a.only.split(",") if a.only else choices)
    bad = [n for n in names[1:] if n not in VARIANTS]
    if bad:
        sys.exit("unknown variant(s): " + ", ".join(bad) + "\nchoose from: " + ", ".join(choices))

    from pymongo import MongoClient
    db = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
    leagues = a.league or [l["iid"] for l in db.leagues.find({"enabled": True}, {"iid": 1})]
    if not leagues:
        sys.exit("no leagues are switched on; pass --league <iid>")
    print(f"Walk-forward A/B on {len(leagues)} league(s), variants: {', '.join(names[1:])}")

    merged = {"team": {n: defaultdict(dict) for n in names}, "player": {n: defaultdict(dict) for n in names},
              "result": {n: {} for n in names}}
    for lg in leagues:
        out = run_league(db, lg, names, a.rounds, a.refit_every, a.burn, a.z)
        if not out:
            continue
        for kind in ("team", "player"):
            for n in names:
                for s, d in out[kind][n].items():
                    merged[kind][n][s].update({(lg,) + k: v for k, v in d.items()})
        for n in names:
            merged["result"][n].update({(lg, k): v for k, v in out["result"][n].items()})
    report(merged, names, a.z)


if __name__ == "__main__":
    main()
