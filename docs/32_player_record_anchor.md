# 32 · Player record anchor — the engine reads a star's own history

**Why.** A player like Mbappé or Yamal clears 1+ shot in about 98% of his games. The model reaches a player line from team shots × his share of them, spread with a fixed variance. That spread is wider than a consistent star's real record, so these lines came out a few points low (about 93% where the record says 97%), and it never looked at "he did this 39 times in 40".

**What changed.**
- `soccer_brain/engine.py`: every player forecast now carries `rec_k` and `rec_n`: in how many of his last (up to 40) games played he beat this line.
- `tiering.anchor()` blends the model's chance with his own smoothed hit rate `(k+1)/(n+2)` on the log-odds scale. Weight = `n/(n+K)`, never above `anchor_max_w`. The range moves by the same amount. Nothing goes above `engine.p_cap`.
- `engine_bridge.py` applies it to player lines after calibration, before tiers. `p_pre_anchor` is stored beside `p_model` so the audit can compare all three.
- Cards show "Hit in X of his last N games"; the detail sheet says the same.

**Examples** (model 93%, K 30, max weight 0.4): 40 of 40 → 95.4%; 39 of 40 → 94.0%; 30 of 40 → 87.7%; 20 of 40 → 82.5%. The anchor also pulls down players who looked good in the model but do not deliver.

**Settings** (Engine group, take effect on the next engine run): `engine.player_anchor` (on), `anchor_min_games` 15, `anchor_k` 30, `anchor_max_w` 0.4, `p_cap` 0.985.

**What it does not do.** It cannot make a line 98% when the model says 80% and the record says 70%. It also does not know about a changed role (new club, new position); the weight cap and the "last 40" window limit that. Whether it helps must be measured: run `python engine_audit.py --days 14` and compare Brier / hit rates of `p_pre_anchor` vs `p` once a few hundred player outcomes are stored.
