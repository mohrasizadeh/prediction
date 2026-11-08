"""Does weighting a player's own record by recency change his number, and which way? (docs/62)

The record anchor blends every player line toward his own clear rate over his last 40 appearances,
at up to 40% of the final number. Those forty games counted EQUALLY: a game from a year ago weighed
as much as last week's. It was the one layer in the engine that did not decay, and it is most of
why a player's last ten games were worth only about a third of his number.

`engine.anchor_recency` fades them at the player half-life, like everything else.

What this script can and cannot tell you:

  * It CAN measure the mechanical effect -- how many numbers move, how far, and whether they move
    toward what the player has been doing lately. That is a fact about the change and it is here.
  * It CANNOT tell you whether the new numbers are BETTER. That needs settled results, and the
    simulated league cannot supply them: simulate.py:61 draws each player one fixed skill at league
    creation and allocates every match from it, so a simulated player's form never drifts and there
    is nothing for recency to catch. The same limitation killed the player half-life A/B (docs/37).
  * engine_ab.py cannot score it either, and deliberately has no variant for it: that runner scores
    `expected`, the mean, and the anchor moves `p` afterwards in engine_bridge.

The real answer needs your own scored forecasts. `rec_rate` and `rec_neff` are now stored on every
forecast whether or not the switch is on, so once a few hundred have settled, the two anchors can be
compared on the same lines. Run with --mongo once you have them.

Read-only. Run: python scripts/measure/anchor_recency.py [--mongo URI] [--db NAME]
"""
import argparse
import base64
import os
import sys

os.environ.setdefault("APP_ENCRYPTION_KEY", base64.b64encode(os.urandom(32)).decode())
os.environ.setdefault("ADMIN_EMAIL", "owner@example.com")
os.environ.setdefault("ADMIN_INITIAL_PASSWORD", "demo-owner-pass-1")
HERE = "/home/user/prediction/backend"
os.environ.setdefault("SOCCER_BRAIN_DIR", os.path.join(HERE, "soccer_brain"))
os.environ.setdefault("DEMO_PERSONAL_LINES", "1")
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "tests"))
sys.path.insert(0, os.environ["SOCCER_BRAIN_DIR"])

import numpy as np  # noqa: E402

import settings_store as S  # noqa: E402
import tiering as TI  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("--mongo", default="", help="your real database; omit for a simulated league")
ap.add_argument("--db", default="prediction")
args = ap.parse_args()

if args.mongo:
    from pymongo import MongoClient
    db = MongoClient(args.mongo)[args.db]
    src = f"your own forecasts ({args.db})"
else:
    from demo_server import build
    db = build()
    src = "a simulated league"

K = float(S.get(db, "engine.anchor_k") or 30.0)
WMAX = float(S.get(db, "engine.anchor_max_w") or 0.4)
CAP = float(S.get(db, "engine.p_cap") or 0.985)
MING = int(S.get(db, "engine.anchor_min_games") or 15)

rows = [f for f in db.forecasts.find(
    {"is_current": True, "scope": "player", "hidden": {"$ne": True}},
    {"_id": 0, "p": 1, "p_pre_anchor": 1, "rec_k": 1, "rec_n": 1, "rec_rate": 1, "rec_neff": 1})
    if f.get("p_pre_anchor") is not None and f.get("rec_n") and f["rec_n"] >= MING
    and f.get("rec_rate") is not None and f.get("rec_neff") is not None]

print(f"\nsource: {src}")
print(f"player lines with a record long enough to anchor: {len(rows):,}")
if len(rows) < 30:
    print("Not enough to say anything. Run the engine first, or point --mongo at the real database.")
    raise SystemExit

flat, wtd, base = [], [], []
for f in rows:
    pb = float(f["p_pre_anchor"])
    d_flat = TI.anchor_shift(pb, f["rec_k"], f["rec_n"], K, WMAX)
    emp = (f["rec_rate"] * f["rec_neff"] + 1.0) / (f["rec_neff"] + 2.0)
    d_wtd = TI.anchor_shift_rate(pb, emp, f["rec_neff"], K, WMAX)
    base.append(pb)
    flat.append(TI.shift_one(pb, d_flat, CAP))
    wtd.append(TI.shift_one(pb, d_wtd, CAP))

base, flat, wtd = np.array(base), np.array(flat), np.array(wtd)
mv = (wtd - flat) * 100
print(f"\nhow far the weighted anchor moves a number, against the flat one")
print(f"  mean absolute move : {np.abs(mv).mean():.2f} points")
print(f"  median absolute    : {np.median(np.abs(mv)):.2f} points")
print(f"  90th percentile    : {np.percentile(np.abs(mv), 90):.2f} points")
print(f"  largest            : {np.abs(mv).max():.2f} points")
print(f"  lines that move at all (>0.5 pt): {(np.abs(mv) > 0.5).mean():.0%}")
print(f"  up / down          : {(mv > 0).mean():.0%} / {(mv < 0).mean():.0%}")

# Does it move numbers toward recent form? The weighted share IS recent form; the flat share is the
# whole window. Where they disagree, the new number should follow the weighted one.
rr = np.array([f["rec_rate"] for f in rows])
fr = np.array([(f["rec_k"] + 1) / (f["rec_n"] + 2) for f in rows])
dis = np.abs(rr - fr) > 0.02
if dis.sum() > 10:
    toward = np.sign(wtd[dis] - flat[dis]) == np.sign(rr[dis] - fr[dis])
    print(f"\nwhere recent form disagrees with the whole window ({dis.sum():,} lines, {dis.mean():.0%}):")
    print(f"  the new number follows RECENT form: {toward.mean():.0%} of the time")
    print(f"  mean gap between the two records  : {np.abs(rr[dis] - fr[dis]).mean() * 100:.1f} points")

print(f"\neffective games behind the record: flat {np.mean([f['rec_n'] for f in rows]):.1f}"
      f"  ->  weighted {np.mean([f['rec_neff'] for f in rows]):.1f}")
print("\n--- what this does NOT say")
print("  Nothing here says the new numbers are better. That needs settled results on a league where")
print("  form actually moves. See the module docstring.")
