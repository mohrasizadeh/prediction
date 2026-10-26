import sys,os
HERE=os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0,HERE)
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "engine"))
import numpy as np, pandas as pd
import pool
pd.set_option("display.width",200)
for prefix in ("tactics","oracle","shapeoracle"):
    t=pool.pooled(prefix)
    print("\n== pooled",prefix)
    print(t[t.stat.isin(["ALL 4 core","goals"])].round(4).to_string(index=False))
for prefix in ("tactics","oracle","shapeoracle"):
    R=pd.concat([pd.read_pickle(f"{HERE}/data/res_{prefix}_{lg}.pkl").assign(league=lg) for lg in ("PL","SA","L1")])
    R=R[R.stat.isin(["shots","sot","corners","tackles"])]
    ix=["league","game_id","team","stat"]
    full=R[R.variant=="full"].set_index(ix)["ll"]
    for v in sorted(set(R.variant)-{"full","base"}):
        a=R[R.variant==v].set_index(ix)["ll"]
        d=(a-full.loc[a.index]).groupby(level=[0,1,2]).mean()
        print(prefix,v,"clustered n",len(d),"gain",round(d.mean(),4),"z",round(d.mean()/(d.std()/len(d)**.5),2),
              "| by league:",{lg:round(g.mean(),4) for lg,g in d.groupby(level=0)})
