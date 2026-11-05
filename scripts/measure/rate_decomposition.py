"""Model the rate, not the count (docs/54 section 6), tested

Walk-forward, read-only measurement. Not a test: it answers a question, it does not assert.

    python scripts/measure/rate_decomposition.py

docs/54 section 6 argued that the best part of the baseline-and-opponent proposal is the
goalkeeper: saves are not a keeper property, they are the opponent's shots on target multiplied by
the keeper's save percentage, and averaging saves over ten games mixes the two. The simulated
league has no goalkeeper and no saves rows, so that market cannot be measured here. Two other
markets have exactly the same shape and do have data, so the principle is testable on them:

    player shots on target  =  his shots        x  his accuracy
    team yellow cards       =  the team's fouls x  its foul-to-card conversion

Each is scored three ways:

    direct       the count's own shrunk rate, which is what the engine does today
    decomposed   expected volume x shrunk conversion, both from earlier matches only
    oracle       the ACTUAL volume x shrunk conversion -- not a forecast, a ceiling. It says how
                 much of the error is the volume and how much is the rate, which is the whole
                 claim of section 6.

The oracle is scored as a BINOMIAL over the known volume, not as a negative binomial. Once the
volume is known the count cannot exceed it and the right distribution says so; scoring it with the
same negative binomial as the other two rows charges it for variance it does not have, and the
first run of this script did exactly that and made the ceiling look worse than the forecast. The
three rows are each a proper predictive distribution over the same observed count, so their
log-likelihoods are comparable, which is all the comparison needs.
"""

import base64, os, sys, math, collections, statistics as st
os.environ.setdefault("APP_ENCRYPTION_KEY", base64.b64encode(os.urandom(32)).decode())
HERE = "/home/user/prediction/backend"
os.environ.setdefault("SOCCER_BRAIN_DIR", os.path.join(HERE, "soccer_brain"))
sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(HERE, "tests")); sys.path.insert(0, os.environ["SOCCER_BRAIN_DIR"])
from scipy.special import gammaln
import demo_server as DS
db = DS.build()


def nb_ll(y, mu, r):
    mu = max(float(mu), 1e-6); y = float(y)
    return float(gammaln(y + r) - gammaln(r) - gammaln(y + 1)
                 + r * math.log(r / (r + mu)) + y * math.log(mu / (r + mu)))


def binom_ll(y, n, p):
    """exact when the volume is known: y of n at probability p"""
    y = int(round(y)); n = int(round(n))
    if n <= 0:
        return nb_ll(y, 0.02, 5.0)       # no volume, no binomial; fall back so the row stays scoreable
    y = min(y, n)
    p = min(max(float(p), 1e-6), 1 - 1e-6)
    return float(gammaln(n + 1) - gammaln(y + 1) - gammaln(n - y + 1)
                 + y * math.log(p) + (n - y) * math.log(1 - p))


def paired_z(a, b):
    d = [x - y for x, y in zip(a, b)]
    if len(d) < 3:
        return float("nan")
    se = st.stdev(d) / math.sqrt(len(d))
    return (st.mean(d) / se) if se > 0 else float("nan")


def report(title, rows, vol, cnt, exposure, r, prior_vol, prior_conv_k, min_hist=10):
    """rows: chronological per-entity histories. vol: volume key. cnt: the count modelled."""
    tot_c = sum(float(x.get(cnt) or 0) for h in rows.values() for x in h)
    tot_v = sum(float(x.get(vol) or 0) for h in rows.values() for x in h)
    tot_e = sum(exposure(x) for h in rows.values() for x in h)
    L_conv = tot_c / tot_v if tot_v else 0.0
    L_cnt = tot_c / tot_e if tot_e else 0.0
    L_vol = tot_v / tot_e if tot_e else 0.0

    out = collections.defaultdict(list)
    for h in rows.values():
        for i in range(min_hist, len(h)):
            hist, nxt = h[:i], h[i]
            e = exposure(nxt)
            if e <= 0:
                continue
            y = float(nxt.get(cnt) or 0)
            hc = sum(float(x.get(cnt) or 0) for x in hist)
            hv = sum(float(x.get(vol) or 0) for x in hist)
            he = sum(exposure(x) for x in hist)
            # direct: the count's own shrunk rate
            mu_direct = (L_cnt * prior_vol + hc) / (prior_vol + he) * e
            # decomposed: shrunk volume rate x shrunk conversion
            mu_vol = (L_vol * prior_vol + hv) / (prior_vol + he) * e
            conv = (L_conv * prior_conv_k + hc) / (prior_conv_k + hv) if (prior_conv_k + hv) > 0 else L_conv
            out["direct"].append(nb_ll(y, max(mu_direct, 0.02), r))
            out["decomposed"].append(nb_ll(y, max(mu_vol * conv, 0.02), r))
            out["oracle volume"].append(binom_ll(y, float(nxt.get(vol) or 0), conv))

    print(f"\n=== {title}   ({cnt} = {vol} x conversion)")
    print(f"    league conversion {L_conv:.3f}   n = {len(out['direct'])}   r = {r}")
    if not out["direct"] or tot_v <= 0 or tot_c <= 0:
        print(f"    NOT MEASURABLE on this data: {cnt} total = {tot_c:g}, {vol} total = {tot_v:g}.")
        print("    A row of equal numbers would read as a tie; it is an absence. Nothing is reported.")
        return out
    for k in ("direct", "decomposed", "oracle volume"):
        print(f"    {k:<16} {st.mean(out[k]):>8.4f}")
    print(f"    paired z, decomposed vs direct : {paired_z(out['decomposed'], out['direct']):+.2f}")
    print(f"    paired z, oracle     vs direct : {paired_z(out['oracle volume'], out['direct']):+.2f}"
          "   <- ceiling, binomial over the known volume")
    return out


# ---- player shots on target = his shots x his accuracy
mi = {m["iid"]: m["kickoff"] for m in db.matches.find({}, {"iid": 1, "kickoff": 1})}
prs = [r for r in db.player_match_stats.find({"minutes": {"$gt": 0}}, {"_id": 0}) if r["match_iid"] in mi]
prs.sort(key=lambda r: mi[r["match_iid"]])
by_player = collections.defaultdict(list)
for r in prs:
    by_player[r["player_iid"]].append(r)

report("Player shots on target", by_player, "shots", "sot",
       lambda x: x["minutes"] / 90.0, r=5.0, prior_vol=4.0, prior_conv_k=10.0)

# ---- team yellow cards = team fouls x conversion
trs = [r for r in db.team_match_stats.find({}, {"_id": 0}) if r.get("fouls") is not None]
trs.sort(key=lambda r: r["kickoff"])
by_team = collections.defaultdict(list)
for r in trs:
    by_team[r["team_iid"]].append(r)

report("Team yellow cards", by_team, "fouls", "yellow_cards",
       lambda x: 1.0, r=4.0, prior_vol=4.0, prior_conv_k=40.0)

# ---- goalkeeper saves: the market the proposal is actually about
n_saves = db.player_match_stats.count_documents({"saves": {"$gt": 0}})
print(f"\n=== Goalkeeper saves\n    rows with saves > 0 in this data: {n_saves}")
if not n_saves:
    print("    Not measurable here: the simulator has no goalkeeper and records no saves.")
    print("    The two tests above are the same decomposition on the data that does exist.")


# ---------------------------------------------------------------- diagnostic
# The first corrected run put the oracle BELOW the forecast it is supposed to bound (z -4.44).
# A ceiling that loses to the thing it bounds is a fault in the model, not a result, so these
# three checks ask which part is wrong: the spread of the conversion, the shrinkage applied to it,
# or the binomial's tightness.
print("\n\n=== Diagnostic: why the oracle loses")

acc = []
for h in by_player.values():
    sh = sum(float(x.get("shots") or 0) for x in h)
    so = sum(float(x.get("sot") or 0) for x in h)
    if sh >= 20:
        acc.append(so / sh)
if acc:
    print(f"    per-player accuracy over >=20 shots: n={len(acc)}  mean {st.mean(acc):.3f} "
          f"sd {st.stdev(acc) if len(acc) > 1 else 0:.3f}  min {min(acc):.3f}  max {max(acc):.3f}")
    print("    If the sd is near zero, every player converts at the league rate and there is no")
    print("    player-specific rate to recover: the decomposition has nothing to add and the")
    print("    binomial is merely a tighter distribution than the truth.")

tot_s = sum(float(x.get("shots") or 0) for h in by_player.values() for x in h)
tot_t = sum(float(x.get("sot") or 0) for h in by_player.values() for x in h)
L = tot_t / tot_s


def oracle_variants(min_hist=10):
    out = collections.defaultdict(list)
    for h in by_player.values():
        for i in range(min_hist, len(h)):
            hist, nxt = h[:i], h[i]
            n = float(nxt.get("shots") or 0)
            y = float(nxt.get("sot") or 0)
            if nxt["minutes"] <= 0:
                continue
            hs = sum(float(x.get("shots") or 0) for x in hist)
            ht = sum(float(x.get("sot") or 0) for x in hist)
            p_shrunk = (L * 10.0 + ht) / (10.0 + hs) if (10.0 + hs) > 0 else L
            p_raw = (ht / hs) if hs > 0 else L
            out["binomial, shrunk p"].append(binom_ll(y, n, p_shrunk))
            out["binomial, unshrunk p"].append(binom_ll(y, n, p_raw))
            out["binomial, league p"].append(binom_ll(y, n, L))
            # beta-binomial: the same mean, with the conversion itself uncertain
            for conc in (4.0, 12.0):
                a = p_shrunk * conc; b = (1 - p_shrunk) * conc
                yy = int(min(round(y), max(round(n), 0))); nn = int(round(n))
                if nn <= 0:
                    out[f"beta-binomial, conc {conc:g}"].append(nb_ll(y, 0.02, 5.0)); continue
                v = (gammaln(nn + 1) - gammaln(yy + 1) - gammaln(nn - yy + 1)
                     + gammaln(yy + a) + gammaln(nn - yy + b) - gammaln(nn + a + b)
                     + gammaln(a + b) - gammaln(a) - gammaln(b))
                out[f"beta-binomial, conc {conc:g}"].append(float(v))
    return out


ov = oracle_variants()
print(f"\n    Scored on the SAME rows, all with the actual shots known (n={len(ov['binomial, shrunk p'])}):")
for k in ("binomial, league p", "binomial, shrunk p", "binomial, unshrunk p",
          "beta-binomial, conc 4", "beta-binomial, conc 12"):
    if ov[k]:
        print(f"      {k:<26} {st.mean(ov[k]):>8.4f}")
print("\n    Read it this way: if the league-p binomial scores about the same as the shrunk-p one,")
print("    the data carries no per-player conversion worth estimating. If a beta-binomial beats")
print("    every plain binomial, the volume is known but the conversion is not, and a binomial")
print("    over a point estimate of p is overconfident -- which would make the 'ceiling' a worse")
print("    distribution than the negative binomial, and the earlier row a modelling artefact")
print("    rather than evidence against the decomposition.")
