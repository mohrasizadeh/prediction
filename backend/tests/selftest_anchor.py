"""selftest_anchor.py -- a player's own record counts (docs/32)."""
import testkit as K
from testkit import check
import tiering as TI

a = lambda p, k, n, **kw: TI.anchor(p, p - .05, min(p + .04, .99), k, n, kw.get("K", 30), kw.get("w", .4), kw.get("cap", .985))
p, lo, hi = a(.93, 40, 40); check(p > .93 and p <= .985, "a star who cleared 40 of 40 moves up from 93%")
check(lo < p < hi or hi == p, "range stays ordered")
p, _, _ = a(.93, 20, 40); check(p < .93, "a player at 50% over 40 games moves down")
p, _, _ = a(.93, 40, 40, cap=.95); check(p <= .95, "cap holds")
p, _, _ = a(.5, 40, 40, w=0.0); check(abs(p - .5) < 1e-9, "zero weight leaves the model alone")
p1, _, _ = a(.8, 15, 15); p2, _, _ = a(.8, 40, 40); check(p2 > p1 > .8, "more games, more weight")
p, _, _ = a(.93, 40, 40); check(p < 0.976 + 1e-9, "smoothed rate: 40 of 40 is not treated as 100%")

# ---------------------------------------------------------------- the shift belongs to the PLAYER
# The anchor says "he clears this more often than the model thinks". That is just as true of an
# ordinary night as of this one, so his usual game has to move by the same amount. It used to move
# `p` and not `p_usual`, which put the whole anchor inside `edge = p - p_usual` -- the number the
# departure chip prints and the number `_departure_tier` grades (docs/61).
import math
d = TI.anchor_shift(0.50, 30, 40, 30, 0.4)
check(d > 0, "a player clearing 30 of 40 on a 50% line pulls his number up")
check(abs(TI.shift_one(0.50, d, 0.985) - TI.anchor(0.50, 0.4, 0.6, 30, 40, 30, 0.4, 0.985)[0]) < 1e-12,
      "the shift applied on its own matches what anchor() does to p")

# the test that would have caught it: a NEUTRAL fixture must report a zero departure
pu = 0.50                       # his usual, same line, opponent neutralised
pm = 0.50                       # the model's chance tonight: the fixture is average
d2 = TI.anchor_shift(pm, 30, 40, 30, 0.4)
p_new, pu_new = TI.shift_one(pm, d2, 0.985), TI.shift_one(pu, d2, 0.985)
check(abs(p_new - pu_new) < 1e-9,
      f"a neutral fixture reads as a zero departure once both move ({(p_new - pu_new) * 100:+.1f} pts)")
check(abs((p_new - pm) * 100) > 2,
      "...and that is not because the anchor did nothing: it moved the number by more than two points")
# the old behaviour, reproduced, so the regression is pinned rather than described
old_edge = p_new - pu           # p anchored, usual not
check(abs(old_edge * 100) > 2,
      f"the old way reported {old_edge * 100:+.1f} pts of 'departure' on a fixture with none")

# and it cancels exactly in log-odds, which is where the blend happens
lg = lambda x: math.log(x / (1 - x))
check(abs((lg(p_new) - lg(pu_new)) - (lg(pm) - lg(pu))) < 1e-9,
      "the fixture effect survives the anchor unchanged on the log-odds scale")
# a real fixture effect is kept, not flattened
pm2 = 0.62
p2 = TI.shift_one(pm2, TI.anchor_shift(pm2, 30, 40, 30, 0.4), 0.985)
pu2 = TI.shift_one(pu, TI.anchor_shift(pm2, 30, 40, 30, 0.4), 0.985)
check(p2 - pu2 > 0.05, f"a genuine fixture effect still shows ({(p2 - pu2) * 100:+.1f} pts)")

# ---------------------------------------------------------------- the record fades too (docs/62)
# His own record over 40 appearances is blended into every number at up to 40% of it, and those
# forty games used to count EQUALLY -- the one layer in the engine that did not decay. A game from
# a year ago weighed as much as last week's, which is most of why his last ten games were worth
# about a third of his number.
from core import recency_weights
import numpy as np

# a player who was poor and is now good: the same 40 games, two ways of counting them
old_half = [0] * 20
new_half = [1] * 20
games = np.array(old_half + new_half, float)          # oldest first, as the engine stores them
k, n = int(games.sum()), len(games)
w = recency_weights(n, 20.0)
rate_w = float((w * games).sum() / w.sum())
neff = float(w.sum() ** 2 / (w * w).sum())
check(abs(k / n - 0.5) < 1e-9, "flat: a player who was poor then good reads as exactly average")
check(rate_w > 0.62, f"weighted: the same forty games read as {rate_w:.0%}, because the good half is the recent half")
check(neff < n, f"and fewer games stand behind it ({neff:.0f} of {n}), so it is not also claiming more certainty")

d_flat = TI.anchor_shift(0.50, k, n, 30.0, 0.4)
emp_w = (rate_w * neff + 1.0) / (neff + 2.0)
d_wtd = TI.anchor_shift_rate(0.50, emp_w, neff, 30.0, 0.4)
check(abs(d_flat) < 1e-6, "flat: the record moves his number not at all -- it averaged his two halves away")
check(d_wtd > 0.15, f"weighted: it pulls him up, because that is what he has been doing lately (shift {d_wtd:+.2f})")
p_flat, p_wtd = TI.shift_one(0.50, d_flat, 0.985), TI.shift_one(0.50, d_wtd, 0.985)
check(p_wtd - p_flat > 0.03, f"worth {(p_wtd - p_flat) * 100:+.1f} points on the card")

# the reverse case must work too, or it is not a weighting, it is a thumb on the scale
rev = np.array(new_half + old_half, float)            # good then poor
rate_r = float((w * rev).sum() / w.sum())
d_rev = TI.anchor_shift_rate(0.50, (rate_r * neff + 1.0) / (neff + 2.0), neff, 30.0, 0.4)
check(d_rev < -0.15, f"a player who WAS good and now is not is pulled down by the same amount ({d_rev:+.2f})")

# and the two paths agree when every game is the same, which is the only case they must
flatline = np.ones(40)
rate_f = float((w * flatline).sum() / w.sum())
check(abs(rate_f - 1.0) < 1e-9, "a player who cleared it every time reads as 1.0 either way")

print("ok")
