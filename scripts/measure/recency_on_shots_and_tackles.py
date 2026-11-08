"""The same recency question, on the engine's own markets: shots, on target, tackles (docs/62).

`recency_on_real_football.py` could only reach goals, cards, saves, minutes and starts, and found a
split answer -- recency helps availability and hurts output. The obvious objection was that the
engine's markets are shots, shots on target and tackles, and none of those were tested.

They are here. Per-player per-match records scraped from FBref and published for reuse by
github.com/JaseZiv/worldfootballR_data (release `fb_advanced_match_stats`), Premier League:

  tackles          2017-08 to 2025-09   83,515 player-matches   2,936 matches
  shots, on target 2024-08 to 2025-09    8,464 player-matches     279 matches

Both tables carry `Min`, so a player who appeared and did nothing is a zero rather than a missing
row -- which matters, because every engine line is "if he plays".

Method is identical to the sibling script: walk forward per player, predict each appearance from
that player's earlier appearances only, flat window against recency-weighted, scored on log loss,
with a bootstrap clustered on PLAYER.

Run: python scripts/measure/recency_on_shots_and_tackles.py
"""
import argparse
import math
import os
import sys
from collections import defaultdict

import numpy as np
import pandas as pd
import pyreadr

HERE = "/home/user/prediction/backend"
os.environ.setdefault("SOCCER_BRAIN_DIR", os.path.join(HERE, "soccer_brain"))
sys.path.insert(0, os.environ["SOCCER_BRAIN_DIR"])
from core import recency_weights  # noqa: E402

DATA = "/tmp/claude-0/-home-user-prediction/2bfe3db5-981d-538c-8ca7-af9e11a3f551/scratchpad/epl"
ap = argparse.ArgumentParser()
ap.add_argument("--window", type=int, default=40)
ap.add_argument("--min-prior", type=int, default=10)
ap.add_argument("--boot", type=int, default=1500)
ap.add_argument("--data", default=DATA)
args = ap.parse_args()

HLS = [None, 20, 12, 8, 5]
LINES = {
    "Sh":          [("1+ shot", 1), ("2+ shots", 2), ("3+ shots", 3)],
    "SoT":         [("1+ on target", 1), ("2+ on target", 2)],
    "Tkl_Tackles": [("1+ tackle", 1), ("2+ tackles", 2), ("3+ tackles", 3)],
}
FILES = {"Sh": "ENG_M_1st_summary_player_advanced_match_stats.rds",
         "SoT": "ENG_M_1st_summary_player_advanced_match_stats.rds",
         "Tkl_Tackles": "ENG_M_1st_defense_player_advanced_match_stats.rds"}


def load(col):
    d = list(pyreadr.read_r(os.path.join(args.data, FILES[col])).values())[0]
    d = d[["Match_Date", "Player", "Min", col]].copy()
    d["Match_Date"] = pd.to_datetime(d["Match_Date"], errors="coerce")
    d["Min"] = pd.to_numeric(d["Min"], errors="coerce")
    d[col] = pd.to_numeric(d[col], errors="coerce")
    d = d.dropna(subset=["Match_Date", "Player", col])
    d = d[d["Min"].fillna(0) > 0]                 # he appeared: the question every line asks
    return d.sort_values("Match_Date")


def ll(p, y):
    p = min(max(p, 1e-6), 1 - 1e-6)
    return -(math.log(p) if y else math.log(1 - p))


def walk(d, col, need):
    hist = defaultdict(list)
    res = {f"hl {h}" if h else "flat": [] for h in HLS}
    who = []
    for pl, dt, v in zip(d["Player"].values, d["Match_Date"].values, d[col].values):
        y = 1 if v >= need else 0
        h = hist[pl]
        if len(h) >= args.min_prior:
            past = np.array(h[-args.window:], float)
            for lab, hl in zip(res, HLS):
                if hl:
                    w = recency_weights(len(past), float(hl))
                    sw = w.sum()
                    emp, neff = float((w * past).sum() / sw), float(sw * sw / float((w * w).sum()))
                else:
                    emp, neff = float(past.mean()), float(len(past))
                p = (emp * neff + 1.0) / (neff + 2.0)
                res[lab].append(ll(p, y))
            who.append(pl)
        h.append(y)
    return res, who


def ci(a, b, who, n_boot, seed=11):
    a, b, who = np.array(a), np.array(b), np.array(who)
    by = defaultdict(list)
    for i, w in enumerate(who):
        by[w].append(i)
    keys = list(by)
    rng = np.random.default_rng(seed)
    out = []
    for _ in range(n_boot):
        idx = np.concatenate([by[keys[i]] for i in rng.integers(0, len(keys), len(keys))])
        out.append(a[idx].mean() - b[idx].mean())
    return float(np.percentile(out, 2.5)), float(np.percentile(out, 97.5))


print(f"\nwindow {args.window} appearances, a player enters once he has {args.min_prior} prior games")
pooled, pooled_who = defaultdict(list), []
for col, lines in LINES.items():
    d = load(col)
    print(f"\n######## {col}   {len(d):,} appearances, {d['Player'].nunique():,} players, "
          f"{str(d['Match_Date'].min())[:10]} to {str(d['Match_Date'].max())[:10]}")
    for label, need in lines:
        res, who = walk(d, col, need)
        n = len(who)
        if n < 400:
            print(f"  {label}: only {n} predictions, skipped")
            continue
        base = np.mean(res["flat"])
        rate = None
        print(f"\n  --- {label}   ({n:,} out-of-sample predictions, {len(set(who)):,} players)")
        print(f"      {'history':<9}{'log loss':>10}{'vs flat':>10}{'95% interval on the gain':>28}")
        for k in res:
            if k == "flat":
                print(f"      {k:<9}{base:>10.4f}{'--':>10}")
            else:
                lo, hi = ci(res["flat"], res[k], who, args.boot)
                flag = "  better" if lo > 0 else ("  worse" if hi < 0 else "")
                print(f"      {k:<9}{np.mean(res[k]):>10.4f}{base - np.mean(res[k]):>+10.4f}"
                      f"{f'{lo:+.4f} to {hi:+.4f}':>28}{flag}")
        for k in res:
            pooled[k].extend(res[k])
        pooled_who.extend(f"{col}:{w}" for w in who)

if pooled.get("flat"):
    base = np.mean(pooled["flat"])
    print(f"\n======== ALL THREE MARKETS POOLED   ({len(pooled['flat']):,} predictions)")
    print(f"      {'history':<9}{'log loss':>10}{'vs flat':>10}{'95% interval on the gain':>28}")
    for k in pooled:
        if k == "flat":
            print(f"      {k:<9}{base:>10.4f}{'--':>10}")
        else:
            lo, hi = ci(pooled["flat"], pooled[k], pooled_who, args.boot)
            flag = "  better" if lo > 0 else ("  worse" if hi < 0 else "")
            print(f"      {k:<9}{np.mean(pooled[k]):>10.4f}{base - np.mean(pooled[k]):>+10.4f}"
                  f"{f'{lo:+.4f} to {hi:+.4f}':>28}{flag}")
print("\n  A POSITIVE gain means the recency-weighted history beat the flat one on the next match.")
