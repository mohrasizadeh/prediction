"""How much does the start-vs-sub blend cost, once the chance to play is already divided out?

Rebuilds exactly what engine._scenarios does, then compares three expectations of minutes:
    Em        the raw mixture              (chance to play folded in)
    Em_c      Em / p_play                  (what engine.condition_on_play gives today: "if he features")
    m_start   his minutes when he starts   (what "if he starts" would give)
"""
import base64, os, sys, collections, statistics as st
os.environ.setdefault("APP_ENCRYPTION_KEY", base64.b64encode(os.urandom(32)).decode())
HERE="/home/user/prediction/backend"
os.environ.setdefault("SOCCER_BRAIN_DIR", os.path.join(HERE,"soccer_brain"))
sys.path.insert(0,HERE); sys.path.insert(0,HERE+"/tests"); sys.path.insert(0,os.environ["SOCCER_BRAIN_DIR"])
import numpy as np
from core import recency_weights
import demo_server as DS
db = DS.build()

mi={m["iid"]: m["kickoff"] for m in db.matches.find({}, {"iid":1,"kickoff":1})}
rows=[r for r in db.player_match_stats.find({}, {"_id":0}) if r["match_iid"] in mi]
rows.sort(key=lambda r: mi[r["match_iid"]])
by=collections.defaultdict(list)
for r in rows: by[r["player_iid"]].append(r)

out=[]
for pid,hs in by.items():
    if len(hs) < 12: continue
    m=np.array([float(h.get("minutes") or 0) for h in hs])
    stt=np.array([1.0 if (h.get("started") or (h.get("minutes") or 0)>=60) else 0.0 for h in hs])
    w=recency_weights(len(hs), 12.0)
    ps=(np.sum(w*stt)+1.0)/(np.sum(w)+2.0)
    sel=stt==1
    if not sel.sum(): continue
    m_start=float(np.average(m[sel], weights=w[sel]))
    ns=~sel; sub=ns&(m>0)
    p_sub=(np.sum(w[sub])+0.5)/(np.sum(w[ns])+1.5) if ns.sum() else 0.0
    m_sub=float(np.average(m[sub], weights=w[sub])) if sub.sum() else 20.0
    pplay=ps+(1-ps)*p_sub
    Em=ps*m_start+(1-ps)*p_sub*m_sub
    out.append((ps, pplay, Em, Em/max(pplay,1e-3), m_start))

print(f"players with >=12 appearances: {len(out)}\n")
for lo,hi,lab in ((0.80,1.01,"settled starters  (start rate >= 0.80)"),
                  (0.50,0.80,"rotated           (0.50 - 0.80)"),
                  (0.00,0.50,"fringe            (< 0.50)")):
    g=[r for r in out if lo<=r[0]<hi]
    if not g: continue
    print(f"{lab}   n={len(g)}")
    print(f"   median start rate            {st.median(r[0] for r in g):.3f}")
    print(f"   median chance to feature     {st.median(r[1] for r in g):.3f}")
    print(f"   median Em  (all-in)          {st.median(r[2] for r in g):5.1f} min")
    print(f"   median Em_c ('if features')  {st.median(r[3] for r in g):5.1f} min   <- today")
    print(f"   median m_start ('if starts') {st.median(r[4] for r in g):5.1f} min   <- proposed")
    gap=[(1 - r[3]/r[4])*100 for r in g]
    print(f"   so 'if features' sits        {st.median(gap):4.1f}% below 'if starts' (median), "
          f"max {max(gap):.1f}%\n")
