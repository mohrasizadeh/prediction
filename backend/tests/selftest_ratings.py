"""selftest_ratings.py -- team attack/defence ratings (docs/33)."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "soccer_brain"))
import numpy as np
import testkit as K
from testkit import check
from ratings import RatingsModel

rng = np.random.default_rng(4)
n = 12
att = rng.normal(0, .25, n); con = rng.normal(0, .25, n)
H, A = [], []
for _ in range(14):
    for h in range(n):
        for a in range(n):
            if h != a and rng.random() < .35:
                H.append(h); A.append(a)
H = np.array(H); A = np.array(A)
mh = np.exp(2.2 + .15 + att[H] + con[A]); ma = np.exp(2.2 + att[A] + con[H])
yh = rng.poisson(mh).astype(float); ya = rng.poisson(ma).astype(float)
age = np.arange(len(H))[::-1] / 8.0
m = RatingsModel(60, 8).fit(H, A, yh, ya, age, n)
check(m.ok, "fits")
check(abs(m.h - .15) < .08, "finds the home factor")
check(np.corrcoef(m.a, att)[0, 1] > .85 and np.corrcoef(m.d, con)[0, 1] > .85, "recovers attack and concession")
tm = RatingsModel(60, 8).fit(H[:20], A[:20], yh[:20], ya[:20], age[:20], n)
check(not tm.ok and tm.mu(0, 1, True) is None, "too few games: no rating, caller keeps the old number")
check(m.mu(0, 1, True) > m.mu(0, 1, False), "home mean is above away mean for the same pair")
# a strong attack vs a leaky defence gets a higher mean than the reverse
i, j = int(np.argmax(att)), int(np.argmin(att)); k = int(np.argmax(con))
check(m.mu(i, k, False) > m.mu(j, int(np.argmin(con)), False), "strong attack v leaky defence beats weak attack v tight defence")
print("ok")
