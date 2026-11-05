"""Which baseline, for a team? (docs/54 section 3, continued to the team side)

Walk-forward, read-only measurement. Not a test: it answers a question, it does not assert.

    python scripts/measure/team_baseline.py
    # for production, replace demo_server.build() below with a read-only MongoClient.

Section 3 of docs/54 settled the player side. This is the same question for the metrics the
proposal asked about that belong to a club rather than a person: corners for and against, goals
for and against, fouls and cards. Every prediction uses earlier matches only; the score is the
negative-binomial log-likelihood of what actually happened, higher being better.

The dispersion r is fitted once per metric from the pooled data (method of moments) and then held
fixed across methods, so the comparison is between baselines and not between dispersions.
"""

import base64, os, sys, math, collections, statistics as st
os.environ.setdefault("APP_ENCRYPTION_KEY", base64.b64encode(os.urandom(32)).decode())
HERE = "/home/user/prediction/backend"
os.environ.setdefault("SOCCER_BRAIN_DIR", os.path.join(HERE, "soccer_brain"))
sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(HERE, "tests")); sys.path.insert(0, os.environ["SOCCER_BRAIN_DIR"])
from scipy.special import gammaln
import demo_server as DS
db = DS.build()

METRICS = ["shots", "sot", "corners", "corners_against", "shots_against", "sot_against",
           "tackles", "fouls", "yellow_cards", "goals", "goals_against"]


def nb_ll(y, mu, r):
    mu = max(float(mu), 1e-6); y = float(y)
    return float(gammaln(y + r) - gammaln(r) - gammaln(y + 1)
                 + r * math.log(r / (r + mu)) + y * math.log(mu / (r + mu)))


rows = [r for r in db.team_match_stats.find({}, {"_id": 0}) if r.get("shots") is not None]
rows.sort(key=lambda r: r["kickoff"])
by_team = collections.defaultdict(list)
for r in rows:
    by_team[r["team_iid"]].append(r)

LEAGUE, R = {}, {}
for s in METRICS:
    vals = [float(r.get(s) or 0) for r in rows]
    m = st.mean(vals); v = st.variance(vals)
    LEAGUE[s] = m
    # method of moments: v = m + m^2/r.  Overdispersion only; otherwise treat as near-Poisson.
    R[s] = (m * m / (v - m)) if v > m * 1.02 else 50.0
    R[s] = min(max(R[s], 0.5), 50.0)

# venue factor: how the league as a whole shifts at home vs away, from all rows
VEN = {}
for s in METRICS:
    h = [float(r.get(s) or 0) for r in rows if r.get("home")]
    a = [float(r.get(s) or 0) for r in rows if not r.get("home")]
    VEN[s] = (st.mean(h) / LEAGUE[s] if h and LEAGUE[s] else 1.0,
              st.mean(a) / LEAGUE[s] if a and LEAGUE[s] else 1.0)


def shrunk(hist, s, k=4.0, hl=None):
    n = len(hist)
    w = [0.5 ** ((n - 1 - i) / hl) for i in range(n)] if hl else [1.0] * n
    num = sum(wi * float(h.get(s) or 0) for wi, h in zip(w, hist))
    den = sum(w)
    return (LEAGUE[s] * k + num) / (k + den)


METHODS = {
    "A. last-10 mean (as proposed)": lambda h, s, nx: st.mean(float(x.get(s) or 0) for x in h[-10:]),
    "B. last-5 mean":                lambda h, s, nx: st.mean(float(x.get(s) or 0) for x in h[-5:]),
    "C. last-10 median":             lambda h, s, nx: st.median([float(x.get(s) or 0) for x in h[-10:]]),
    "D. all history, shrunk":        lambda h, s, nx: shrunk(h, s),
    "E. shrunk + half-life 12":      lambda h, s, nx: shrunk(h, s, hl=12.0),
    "F. shrunk x venue":             lambda h, s, nx: shrunk(h, s) * VEN[s][0 if nx.get("home") else 1],
}

MIN_HIST = 10
res = collections.defaultdict(lambda: collections.defaultdict(list))
for tid, hs in by_team.items():
    for i in range(MIN_HIST, len(hs)):
        hist, nxt = hs[:i], hs[i]
        for s in METRICS:
            y = float(nxt.get(s) or 0)
            for name, fn in METHODS.items():
                try:
                    mu = fn(hist, s, nxt)
                except Exception:
                    continue
                res[s][name].append(nb_ll(y, max(mu, 0.02), R[s]))


def paired_z(a, b):
    d = [x - y for x, y in zip(a, b)]
    if len(d) < 3:
        return float("nan")
    se = st.stdev(d) / math.sqrt(len(d))
    return (st.mean(d) / se) if se > 0 else float("nan")


print("Walk-forward log-likelihood per team-match (higher = better). Earlier matches only.\n")
hdr = f"{'metric':>16} " + " ".join(f"{n.split('.')[0]:>8}" for n in METHODS) + f"{'r':>7}{'n':>7}"
print(hdr); print("-" * len(hdr))
for s in METRICS:
    best = max(METHODS, key=lambda n: st.mean(res[s][n]) if res[s][n] else -9)
    line = f"{s:>16} "
    for n in METHODS:
        v = st.mean(res[s][n]) if res[s][n] else float("nan")
        line += f"{v:>8.3f}" + ("*" if n == best else " ")
    print(line + f"{R[s]:>6.1f}{len(res[s]['D. all history, shrunk']):>7}")
print("\n* = best for that metric")

print("\nPaired z against A (the proposed last-10 mean). Positive means better than the proposal;")
print("the project gate (docs/37) asks for 2 standard errors.\n")
hdr2 = f"{'metric':>16} " + " ".join(f"{n.split('.')[0]:>8}" for n in list(METHODS)[1:])
print(hdr2); print("-" * len(hdr2))
for s in METRICS:
    line = f"{s:>16} "
    for n in list(METHODS)[1:]:
        line += f"{paired_z(res[s][n], res[s]['A. last-10 mean (as proposed)']):>+8.2f} "
    print(line)
print("\nlegend:")
for n in METHODS:
    print("  ", n)
print("\nvenue factors used by F (home, away):")
for s in METRICS:
    print(f"   {s:>16}  {VEN[s][0]:.3f}  {VEN[s][1]:.3f}")
