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
print("ok")
