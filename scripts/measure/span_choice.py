"""How insensitive are the rungs we show? (docs/56)

Read-only measurement against the simulated league: runs the engine, then looks at the `span` every line
now carries -- how far its likelihood moves between the league's leakiest and meanest opponent for that
stat. Answers the only question that can set `engine.min_span` honestly: at each candidate threshold, how
many cards change their lead line, and what do they change from and to?

    python scripts/measure/span_choice.py
"""
import base64, os, sys, collections, statistics as st
os.environ.setdefault("APP_ENCRYPTION_KEY", base64.b64encode(os.urandom(32)).decode())
HERE = "/home/user/prediction/backend"
os.environ.setdefault("SOCCER_BRAIN_DIR", os.path.join(HERE, "soccer_brain"))
sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(HERE, "tests")); sys.path.insert(0, os.environ["SOCCER_BRAIN_DIR"])
import demo_server as DS
import engine_bridge as EB
import queries as Q
import settings_store as S

db = DS.build()
for lg in db.leagues.find({}, {"iid": 1}):
    EB.run_league(db, int(lg["iid"]))

fc = list(db.forecasts.find({"hidden": {"$ne": True}}, {"_id": 0, "contrib": 0}))
print(f"lines stored: {len(fc)}")
have = [f for f in fc if f.get("span") is not None]
print(f"with a span:  {len(have)}   unknown: {len(fc) - len(have)} (never gated)\n")
if not have:
    print("No spans. Re-run the engine after the change that adds them.")
    raise SystemExit(0)

sp = sorted(abs(float(f["span"])) for f in have)
qs = [0, 5, 10, 25, 50, 75, 90, 100]
print("span distribution, in likelihood points:")
for q in qs:
    v = sp[min(len(sp) - 1, int(q / 100 * (len(sp) - 1)))]
    print(f"   p{q:<3} {v * 100:6.2f}")

print("\nby scope and stat (median span, and share under 8 points):")
by = collections.defaultdict(list)
for f in have:
    by[(f["scope"], f["stat"])].append(abs(float(f["span"])))
for k in sorted(by):
    v = by[k]
    print(f"   {k[0]:<6} {k[1]:<8} n={len(v):<5} median {st.median(v)*100:6.2f}   under 8pts: {sum(1 for x in v if x < 0.08)/len(v)*100:5.1f}%")

print("\nthe dullest rungs the gate is meant to catch -- lowest span, highest likelihood:")
for f in sorted(have, key=lambda f: (abs(float(f["span"])), -float(f["p"])))[:12]:
    print(f"   span {abs(float(f['span']))*100:5.2f}pts  p {float(f['p'])*100:5.1f}%  {f['scope']:<6} {f.get('market') or f['stat']}")

print("\nwhat each threshold would do to the LEAD line of each card:")
base = {c["fkey"]: c for c in Q.group_cards(fc, 1.0, "player", S.get(db, "engine.market_weights"), "odds", 0.0)}
print(f"   {'min_span':>9} {'cards':>7} {'lead changed':>13} {'median lead p before':>21} {'after':>7}")
for thr in (0.0, 0.02, 0.04, 0.06, 0.08, 0.12, 0.20):
    cards = Q.group_cards(fc, 1.0, "player", S.get(db, "engine.market_weights"), "odds", thr)
    chg = sum(1 for c in cards if base.get(c["fkey"]) is None)
    med_b = st.median([float(c["p"]) for c in base.values()]) if base else 0
    med_a = st.median([float(c["p"]) for c in cards]) if cards else 0
    print(f"   {thr:>9.2f} {len(cards):>7} {chg:>13} {med_b*100:>20.1f}% {med_a*100:>6.1f}%")
print("\n'lead changed' counts cards whose leading line is not the one it led with at min_span=0.")
