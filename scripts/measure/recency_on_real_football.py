"""Does a player's recent form predict his next match better than his whole record? (docs/62)

The record anchor blends every player line toward his own clear rate over his last 40 appearances,
and until docs/62 those forty games counted EQUALLY. `engine.anchor_recency` fades them instead.
Neither the demo league nor engine_ab.py can say which is better -- simulate.py gives each player a
fixed skill that never drifts, and the A/B runner scores `expected` while the anchor moves `p`.

So this asks the question directly, on real football, with no engine in the loop:

    for a per-player per-match count, is a RECENCY-WEIGHTED history a better forecast of the next
    match than a FLAT one over the same window?

That is exactly what the anchor does and nothing else. Every estimate is strictly out of sample:
match t is predicted from matches before t only, walking forward through the season.

DATA. Five Premier League seasons of per-player per-gameweek records, from the openly published
Fantasy Premier League dataset (github.com/vaastav/Fantasy-Premier-League). It carries minutes,
starts, goals, assists, saves and cards per player per match.

WHAT IT CANNOT TEST. Shots and shots on target are not in this source, and they are the engine's
main markets. FBref has them and refuses automated requests; Understat serves an error page. So the
targets below are the real per-player counts that ARE available and that mirror engine lines --
goals, cards, saves, and the two questions behind the lineup badge. If recency wins across all of
them, in five independent seasons, that is evidence about the MECHANISM; it is not a measurement of
the shots market, and nothing here should be quoted as one.

SCORING. Log loss and Brier, lower better, against what actually happened. Paired by observation and
tested with a bootstrap clustered on PLAYER, because one player contributes many rows and treating
them as independent would overstate significance.

Run: python scripts/measure/recency_on_real_football.py [--window 40] [--min-prior 10]
"""
import argparse
import csv
import glob
import math
import os
import sys
from collections import defaultdict

import numpy as np

HERE = "/home/user/prediction/backend"
os.environ.setdefault("SOCCER_BRAIN_DIR", os.path.join(HERE, "soccer_brain"))
sys.path.insert(0, os.environ["SOCCER_BRAIN_DIR"])
from core import recency_weights  # noqa: E402

DATA = "/tmp/claude-0/-home-user-prediction/2bfe3db5-981d-538c-8ca7-af9e11a3f551/scratchpad/epl"

ap = argparse.ArgumentParser()
ap.add_argument("--window", type=int, default=40, help="appearances of history, as engine.py uses 40")
ap.add_argument("--min-prior", type=int, default=10, help="skip a row until the player has this many prior games")
ap.add_argument("--boot", type=int, default=1500)
ap.add_argument("--data", default=DATA)
args = ap.parse_args()

# (name, what it asks, how to read one row -> (counts?, value)) ; None means "this row does not count"
TARGETS = {
    "1+ goal":        lambda r: (float(r["goals_scored"]) >= 1) if _played(r) else None,
    "1+ card":        lambda r: (float(r["yellow_cards"]) + float(r["red_cards"]) >= 1) if _played(r) else None,
    "3+ saves (GK)":  lambda r: (float(r["saves"]) >= 3) if (_played(r) and r["position"] == "GK") else None,
    "60+ minutes":    lambda r: (float(r["minutes"]) >= 60),
    "starts":         lambda r: (float(r.get("starts") or 0) >= 1) if r.get("starts") not in (None, "") else None,
}


def _played(r):
    return float(r["minutes"]) > 0


def load(path):
    out = []
    with open(path, newline="", encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            try:
                out.append({"name": r["name"], "position": r.get("position", ""), "round": int(float(r["round"])),
                            "kickoff_time": r.get("kickoff_time", ""), "minutes": r["minutes"],
                            "goals_scored": r["goals_scored"], "yellow_cards": r["yellow_cards"],
                            "red_cards": r["red_cards"], "saves": r["saves"], "starts": r.get("starts", "")})
            except (KeyError, ValueError):
                continue
    out.sort(key=lambda r: (r["kickoff_time"] or "", r["round"]))
    return out


def ll(p, y):
    p = min(max(p, 1e-6), 1 - 1e-6)
    return -(math.log(p) if y else math.log(1 - p))


def run(rows, target, hls, window, min_prior):
    """Walk forward per player. Returns {label: [scores]} plus the player of each observation."""
    hist = defaultdict(list)              # player -> [0/1] oldest first
    res = {f"hl {h}" if h else "flat": [] for h in hls}
    brier = {k: [] for k in res}
    who = []
    read = TARGETS[target]
    for r in rows:
        y = read(r)
        if y is None:
            continue
        h = hist[r["name"]]
        if len(h) >= min_prior:
            past = np.array(h[-window:], float)
            for lab, hl in zip(res, hls):
                if hl:
                    w = recency_weights(len(past), float(hl))
                    sw = w.sum()
                    emp = float((w * past).sum() / sw)
                    neff = float(sw * sw / float((w * w).sum()))
                else:
                    emp, neff = float(past.mean()), float(len(past))
                p = (emp * neff + 1.0) / (neff + 2.0)          # the same smoothing the anchor uses
                res[lab].append(ll(p, y))
                brier[lab].append((p - (1.0 if y else 0.0)) ** 2)
            who.append(r["name"])
        h.append(1 if y else 0)
    return res, brier, who


def clustered_p(a, b, who, n_boot, seed=11):
    """Is `b` better than `a`? Bootstrap resampling PLAYERS, not rows."""
    a, b, who = np.array(a), np.array(b), np.array(who)
    by = defaultdict(list)
    for i, w in enumerate(who):
        by[w].append(i)
    keys = list(by)
    rng = np.random.default_rng(seed)
    diffs = []
    for _ in range(n_boot):
        idx = np.concatenate([by[keys[i]] for i in rng.integers(0, len(keys), len(keys))])
        diffs.append(a[idx].mean() - b[idx].mean())
    diffs = np.array(diffs)
    return float(np.percentile(diffs, 2.5)), float(np.percentile(diffs, 97.5)), float((diffs > 0).mean())


HLS = [None, 20, 12, 8, 5]
files = sorted(glob.glob(os.path.join(args.data, "merged_*.csv")))
print(f"\nseasons: {[os.path.basename(f).replace('merged_', '').replace('.csv', '') for f in files]}")
print(f"window {args.window} appearances, skipping a player until he has {args.min_prior} prior games\n")

grand = defaultdict(list)
grand_who = []
for target in TARGETS:
    all_res = {f"hl {h}" if h else "flat": [] for h in HLS}
    all_bri = {k: [] for k in all_res}
    all_who = []
    for f in files:
        rows = load(f)
        res, bri, who = run(rows, target, HLS, args.window, args.min_prior)
        for k in all_res:
            all_res[k].extend(res[k]); all_bri[k].extend(bri[k])
        all_who.extend(f"{os.path.basename(f)}:{w}" for w in who)
    n = len(all_who)
    if n < 500:
        print(f"{target}: only {n} observations, skipped")
        continue
    base = np.mean(all_res["flat"])
    print(f"--- {target}   ({n:,} out-of-sample predictions, {len(set(all_who)):,} player-seasons)")
    print(f"    {'history':<10}{'log loss':>10}{'vs flat':>10}{'Brier':>9}{'95% interval on the gain':>28}")
    for k in all_res:
        d = base - np.mean(all_res[k])
        if k == "flat":
            print(f"    {k:<10}{np.mean(all_res[k]):>10.4f}{'--':>10}{np.mean(all_bri[k]):>9.4f}")
        else:
            lo, hi, pw = clustered_p(all_res["flat"], all_res[k], all_who, args.boot)
            flag = "  better" if lo > 0 else ("  worse" if hi < 0 else "")
            print(f"    {k:<10}{np.mean(all_res[k]):>10.4f}{d:>+10.4f}{np.mean(all_bri[k]):>9.4f}"
                  f"{f'{lo:+.4f} to {hi:+.4f}':>28}{flag}")
    for k in all_res:
        grand[k].extend(all_res[k])
    grand_who.extend(all_who)
    print()

if grand.get("flat"):
    base = np.mean(grand["flat"])
    print(f"=== ALL TARGETS POOLED   ({len(grand['flat']):,} predictions)")
    print(f"    {'history':<10}{'log loss':>10}{'vs flat':>10}{'95% interval on the gain':>28}")
    for k in grand:
        if k == "flat":
            print(f"    {k:<10}{base:>10.4f}{'--':>10}")
        else:
            lo, hi, _ = clustered_p(grand["flat"], grand[k], grand_who, args.boot)
            flag = "  better" if lo > 0 else ("  worse" if hi < 0 else "")
            print(f"    {k:<10}{np.mean(grand[k]):>10.4f}{base - np.mean(grand[k]):>+10.4f}"
                  f"{f'{lo:+.4f} to {hi:+.4f}':>28}{flag}")
print("\n  A POSITIVE gain means the weighted history predicted the next match BETTER than the flat one.")
print("  The interval is a bootstrap clustered on player, so it does not treat one player's")
print("  many appearances as many independent facts.")
