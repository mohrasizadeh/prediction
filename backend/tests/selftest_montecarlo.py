"""selftest_montecarlo.py -- the simulator, used as a check on the engine (docs/66).

Proves: each forecast's stored `p` really is the sum of the mixture it claims to be (no sampling
involved, so a failure here is the engine and not the dice); drawing from that same mixture
reproduces `p` to within Monte Carlo error; and -- the question that decides whether a simulator
is worth showing anyone -- whether drawing entities independently recovers the correlation that
combo.py currently corrects for with factors measured on 237,000 real combinations.
"""
import os, sys, base64, datetime as dt
os.environ.setdefault("APP_ENCRYPTION_KEY", base64.b64encode(os.urandom(32)).decode())
HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("SOCCER_BRAIN_DIR", os.path.join(HERE, "soccer_brain"))
sys.path.insert(0, HERE); sys.path.insert(0, os.environ["SOCCER_BRAIN_DIR"])
import httpx, mongomock
import engine_bridge as B, ingest as I, mongo_init, security, settings_store as S
import montecarlo as MC
from cached_fetch import PitchClient
from fake_pitchapi import PLAYER_KEYS, TEAM_KEYS, FakePitch
from simulate import simulate_league


def check(c, m):
    if not c:
        print("  FAIL", m); sys.exit(1)
    print("  ok  ", m)


db = mongomock.MongoClient()["mc"]; mongo_init.ensure_indexes(db)
security.save_provider_key(db, "pitchapi", "pk_test_zzzz")
S.put(db, "ingest.rps", 1000); S.put(db, "provider.pitchapi.team_keys", TEAM_KEYS)
S.put(db, "provider.pitchapi.player_keys", PLAYER_KEYS)
S.put(db, "provider.position_map", {"0": "GK", "1": "DEF", "2": "MID", "3": "FWD"})
matches, tg, pg, _ = simulate_league(n_teams=12, seed=5)
n_final = int(matches["round"].max()) + 1 - 2
fake = FakePitch(matches, tg, pg, n_final)
c = PitchClient(db, http=httpx.Client(base_url="https://api.pitchapi.dev", transport=fake.transport()), sleep=lambda s: None)
I.sync_leagues(c); lg = db.leagues.find_one({}); I.sync_league_matches(c, lg, "2025/2026", "all"); I.process_queue(c)
I.assign_rounds(db, lg["iid"]); I.update_coverage(db, lg["iid"])
now = fake.kick(n_final) - dt.timedelta(hours=2)
I.lineup_watch(c, now=now)

# Fit the engine exactly as a run does, then ask it to keep the mixtures.
ms, tg_f, pg_f, ap, _diag = B.build_frames(db, lg["iid"], int(S.get(db, "engine.history_rounds")))
eng = B.configure_engine(db)
eng.fit(ms, tg_f, pg_f, int(ms["round"].max()) + 1, appearances=ap)
eng.keep_mixture = True

ups = list(db.matches.find({"league_iid": lg["iid"], "status": {"$ne": "final"}}, {"_id": 0}).limit(4))
check(ups, "there are fixtures to simulate")
per_match = []
for m in ups:
    fcs, _probs = eng.predict_fixture(int(m["home_iid"]), int(m["away_iid"]))
    per_match.append(fcs)
allf = [f for fcs in per_match for f in fcs]
check(allf, "the engine produced forecasts")
check(all(f.mix for f in allf), "and every one carries the mixture its p was summed from")

# ---------------------------------------------------------------- 1. no dice: is p the mixture?
a = MC.analytic_check(allf)
check(a["checked"] == len(allf), f"rebuilt every one of {a['checked']} forecasts from its own mixture")
check(a["max_diff"] < 1e-9,
      f"and the stored p IS that sum, to {a['max_diff']:.2e} -- so p and the mixture are one object")

# ---------------------------------------------------------------- 2. with dice: does drawing agree?
r = MC.check_marginals(allf[:120], n=40_000)
check(r["max_sigmas"] < 5.0,
      f"drawing from the same mixture reproduces p: worst line is {r['max_sigmas']:.1f} standard "
      f"errors out ({r['max_sigmas_diff']*100:.2f} points), largest gap anywhere "
      f"{r['max_diff']*100:.2f} points, over {r['checked']} lines at n=40,000")
# and the noise is real: far fewer draws must be visibly worse, which is why 100 runs is not a plan
few = MC.check_marginals(allf[:120], n=200, seed=3)
check(few["max_diff"] > r["max_diff"],
      f"at n=200 the worst gap grows to {few['max_diff']*100:.1f} points -- simulation adds noise, not information")

# ---------------------------------------------------------------- 3. the question that decides it
pf = MC.pair_factor(per_match, n=20_000, pairs_per_match=25, min_expected=100)
check(pf["pairs"] > 0, "sampled real pairs from these fixtures")
print(f"\n  pair factor over {pf['pairs']} pairs: {pf['factor']:.3f} "
      f"(sd {pf['sd']:.3f}, 10th-90th {pf['p10']:.3f}-{pf['p90']:.3f}); "
      f"{pf['skipped_too_rare']} pairs skipped as too rare to estimate")
print(f"  combo.py's measured factor for two entities before lineups: {pf['measured_pre_2']}")
print(f"  verdict: {pf['verdict']}")
check(abs(pf["factor"] - 1.0) < 0.03,
      "independent draws reproduce the plain product (factor about 1.00), as they must -- so a "
      "simulator WITHOUT shared game state cannot replace the measured factors")

print("\nselftest_montecarlo: all checks passed")
