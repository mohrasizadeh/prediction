"""Which baseline? (docs/54 section 3)

Walk-forward, read-only measurement. Not a test: it answers a question, it does not assert.

    python scripts/measure/baseline_choice.py            # against the simulated league
    # for production, replace demo_server.build() below with a read-only MongoClient:
    #   from pymongo import MongoClient
    #   db = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]

Every prediction uses earlier matches only. The score is the negative-binomial log-likelihood of
what actually happened, higher being better. See docs/54 for the numbers this produced and what
they mean.
"""

import base64, os, sys, math, collections, statistics as st
os.environ.setdefault("APP_ENCRYPTION_KEY", base64.b64encode(os.urandom(32)).decode())
HERE="/home/user/prediction/backend"
os.environ.setdefault("SOCCER_BRAIN_DIR", os.path.join(HERE,"soccer_brain"))
sys.path.insert(0,HERE); sys.path.insert(0,os.path.join(HERE,"tests")); sys.path.insert(0,os.environ["SOCCER_BRAIN_DIR"])
import numpy as np
from scipy.special import gammaln
import demo_server as DS
db = DS.build()

def nb_ll(y, mu, r=4.0):
    mu=max(float(mu),1e-6); y=float(y)
    return float(gammaln(y+r)-gammaln(r)-gammaln(y+1)+r*math.log(r/(r+mu))+y*math.log(mu/(r+mu)))

# order matches by kickoff
mi={m["iid"]: m["kickoff"] for m in db.matches.find({}, {"iid":1,"kickoff":1})}
rows=[r for r in db.player_match_stats.find({"minutes":{"$gt":0}},{"_id":0}) if r["match_iid"] in mi]
rows.sort(key=lambda r: mi[r["match_iid"]])
by_player=collections.defaultdict(list)
for r in rows: by_player[r["player_iid"]].append(r)

LEAGUE={}
for stat in ("shots","sot","tackles","fouls_committed","fouls_won"):
    tot=sum(r.get(stat) or 0 for r in rows); mins=sum(r["minutes"] for r in rows)
    LEAGUE[stat]=tot/(mins/90) if mins else 0.0

def shrunk(hist, stat, prior_rate, k=4.0, hl=None):
    """per-90 rate shrunk to the league, optional half-life decay"""
    n=len(hist)
    w=[0.5**((n-1-i)/hl) for i in range(n)] if hl else [1.0]*n
    num=sum(wi*(h.get(stat) or 0) for wi,h in zip(w,hist))
    den=sum(wi*(h["minutes"]/90) for wi,h in zip(w,hist))
    return (prior_rate*k+num)/(k+den)

METHODS={}
METHODS["A. last-10 mean per GAME (as proposed)"]      = lambda h,s,L,m: (st.mean((x.get(s) or 0) for x in h[-10:]))
METHODS["B. last-10 mean per 90 x minutes"]            = lambda h,s,L,m: (sum((x.get(s) or 0) for x in h[-10:])/max(1e-9,sum(x["minutes"]/90 for x in h[-10:])))*(m/90)
METHODS["C. last-10 MEDIAN per 90 x minutes"]          = lambda h,s,L,m: (st.median([(x.get(s) or 0)/max(x["minutes"]/90,0.2) for x in h[-10:]]))*(m/90)
METHODS["D. all history, shrunk to league"]            = lambda h,s,L,m: shrunk(h,s,L)*(m/90)
METHODS["E. all history, shrunk + half-life 12"]       = lambda h,s,L,m: shrunk(h,s,L,hl=12.0)*(m/90)

MIN_HIST=10
res=collections.defaultdict(lambda: collections.defaultdict(list))
for pid, hs in by_player.items():
    for i in range(MIN_HIST, len(hs)):
        hist, nxt = hs[:i], hs[i]
        m=nxt["minutes"]
        for stat in ("shots","sot","tackles","fouls_committed","fouls_won"):
            y=nxt.get(stat) or 0
            for name,fn in METHODS.items():
                try: mu=fn(hist,stat,LEAGUE[stat],m)
                except Exception: continue
                res[stat][name].append(nb_ll(y, max(mu,0.02)))

print(f"Walk-forward log-likelihood per player-match (higher = better). Predictions use earlier matches only.\n")
hdr=f"{'metric':>17} " + " ".join(f"{n.split('.')[0]:>7}" for n in METHODS)
print(hdr); print("-"*len(hdr))
for stat in ("shots","sot","tackles","fouls_committed","fouls_won"):
    best=max(METHODS, key=lambda n: st.mean(res[stat][n]) if res[stat][n] else -9)
    line=f"{stat:>17} "
    for n in METHODS:
        v=st.mean(res[stat][n]) if res[stat][n] else float('nan')
        line += f"{v:>7.3f}" + ("*" if n==best else " ")
    print(line + f"   n={len(res[stat][list(METHODS)[0]])}")
print("\n* = best for that metric")
print("\nlegend:")
for n in METHODS: print("  ", n)
