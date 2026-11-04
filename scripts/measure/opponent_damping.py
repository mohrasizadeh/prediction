"""Does the opponent adjustment help, and how hard? (docs/54 section 4.1)

Walk-forward, read-only measurement. Not a test: it answers a question, it does not assert.

    python scripts/measure/opponent_damping.py            # against the simulated league
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
from scipy.special import gammaln
import demo_server as DS
db = DS.build()
def nb_ll(y, mu, r=4.0):
    mu=max(float(mu),1e-6); y=float(y)
    return float(gammaln(y+r)-gammaln(r)-gammaln(y+1)+r*math.log(r/(r+mu))+y*math.log(mu/(r+mu)))

mi={m["iid"]:m["kickoff"] for m in db.matches.find({},{"iid":1,"kickoff":1})}
pr=[r for r in db.player_match_stats.find({"minutes":{"$gt":0}},{"_id":0}) if r["match_iid"] in mi]
pr.sort(key=lambda r: mi[r["match_iid"]])
tr=[r for r in db.team_match_stats.find({},{"_id":0}) if r["match_iid"] in mi]
tr.sort(key=lambda r: mi[r["match_iid"]])

# per-player history, and per-opponent "allowed" history, both time ordered
by_player=collections.defaultdict(list)
for r in pr: by_player[r["player_iid"]].append(r)
by_team_def=collections.defaultdict(list)          # what this team ALLOWED, match by match
for r in tr: by_team_def[r["team_iid"]].append(r)

AG={"shots":"shots_against","sot":"sot_against","tackles":"tackles_against"}
LEAGUE={}; 
for s,a in AG.items():
    v=[r.get(a) for r in tr if r.get(a) is not None]
    LEAGUE[s]=st.mean(v) if v else 0.0
LRATE={}
for s in AG:
    tot=sum(r.get(s) or 0 for r in pr); mins=sum(r["minutes"] for r in pr); LRATE[s]=tot/(mins/90)

def shrunk(hist, stat, prior, k=4.0):
    num=sum((h.get(stat) or 0) for h in hist); den=sum(h["minutes"]/90 for h in hist)
    return (prior*k+num)/(k+den)

def opp_factor(opp_iid, stat, before_ko, cap):
    """what this opponent allows, per match, relative to the league -- earlier matches only"""
    a=AG[stat]
    hs=[r for r in by_team_def[opp_iid] if mi[r["match_iid"]]<before_ko and r.get(a) is not None]
    if len(hs)<4 or not LEAGUE[stat]: return 1.0, 0
    f=(st.mean(r[a] for r in hs))/LEAGUE[stat]
    return min(max(f,1/cap),cap), len(hs)

res=collections.defaultdict(lambda: collections.defaultdict(list))
for pid,hs in by_player.items():
    for i in range(10,len(hs)):
        hist,nxt=hs[:i],hs[i]; m=nxt["minutes"]; ko=mi[nxt["match_iid"]]
        for stat in AG:
            y=nxt.get(stat) or 0
            base=shrunk(hist,stat,LRATE[stat])*(m/90)
            res[stat]["1. baseline only"].append(nb_ll(y,max(base,0.02)))
            for cap,label in ((1.5,"2. x opponent allows (cap 1.5)"),(1.25,"3. x opponent allows (cap 1.25)")):
                f,_=opp_factor(nxt["opp_iid"],stat,ko,cap)
                res[stat][label].append(nb_ll(y,max(base*f,0.02)))
            # half-strength version: sqrt of the factor
            f,_=opp_factor(nxt["opp_iid"],stat,ko,1.5)
            res[stat]["4. x sqrt(opponent allows)"].append(nb_ll(y,max(base*math.sqrt(f),0.02)))

names=["1. baseline only","2. x opponent allows (cap 1.5)","3. x opponent allows (cap 1.25)","4. x sqrt(opponent allows)"]
print("Walk-forward log-likelihood per player-match (higher = better)\n")
print(f"{'metric':>9} " + " ".join(f"{n.split('.')[0]:>8}" for n in names))
print("-"*48)
for stat in AG:
    best=max(names,key=lambda n: st.mean(res[stat][n]))
    line=f"{stat:>9} "
    for n in names:
        line+=f"{st.mean(res[stat][n]):>8.3f}"+("*" if n==best else " ")
    print(line+f"  n={len(res[stat][names[0]])}")
print("\nlegend:"); [print("  ",n) for n in names]

print("\nPaired test against baseline (the project's gate: z >= 2.0):")
import statistics as _st
for stat in AG:
    b=res[stat]["1. baseline only"]
    for n in names[1:]:
        d=[x-y for x,y in zip(res[stat][n],b)]
        mean=_st.mean(d); se=_st.pstdev(d)/math.sqrt(len(d)) if len(d)>1 else 0
        z=mean/se if se else 0
        print(f"   {stat:>9} {n:<34} gain {mean:+.4f}  se {se:.4f}  z {z:+5.2f}  {'PASS' if z>=2 else 'no'}")
