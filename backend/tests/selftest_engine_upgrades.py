"""The four docs/37 engine upgrades: each is off by default, each changes what it should and nothing else, and the
walk-forward A/B runner that decides whether to switch one on works end to end on a real-shaped database."""
import os, sys, base64
os.environ.setdefault("APP_ENCRYPTION_KEY", base64.b64encode(os.urandom(32)).decode())
HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(HERE, "soccer_brain")); sys.path.insert(0, os.path.join(HERE, "tests"))
import numpy as np
import engine as E
import engine_ab as AB
import engine_bridge as B
import settings_store as S
import simulate


def check(c, m):
    if not c:
        print("  FAIL", m); sys.exit(1)
    print("  ok  ", m)


# ---------------------------------------------------------------- frames to fit on
ms, tg, pg = simulate.simulate_league(n_teams=12, seed=5)[:3]
rng = np.random.default_rng(7)
tg["xg"] = np.clip(tg["goals"] * 0.85 + rng.normal(0, 0.3, len(tg)), 0.05, None)
AS_OF = int(ms["round"].max())


def fit(**kw):
    return E.SoccerEngine(seed=0, n_draws=20, **kw).fit(ms, tg, pg, AS_OF)


def player_totals(eng, stat="shots", thr=0.5):
    f, probs = eng.predict_fixture(0, 1)
    rows = {x.player: x.expected for x in f if x.scope == "player" and x.stat == stat and x.thr == thr}
    return rows, probs


# ---------------------------------------------------------------- defaults are off
d = E.SoccerEngine()
check(d.script_v2 is False and d.fit_player_r is False and d.opp_pos_k == 0.0 and d.xg_blend == 0.0,
      "every upgrade is off in a plain engine")
reg = S.registry()
check(all(reg[k]["default"] in (False, 0) for k in ("engine.script_v2", "engine.fit_player_r", "engine.opp_pos_k", "engine.xg_blend")),
      "...and off in the settings registry, so production is unchanged until a gate passes")

base = fit()
b_rows, b_probs = player_totals(base)

# ---------------------------------------------------------------- 1. game state
sv = fit(script_v2=True)
check(sv.glm["shots"].beta.shape[0] == base.glm["shots"].beta.shape[0] + 2, "game state adds exactly two inputs")
check(list(sv._groups()[0]).count("game_script") == 3, "...and both are labelled game state, so reasons still read right")
snap = sv.snaps[AS_OF]
check(len(snap) == 3 and np.isfinite(snap[2]).all() and (snap[2] > 0).any(), "tempo is built from past rounds only")
sv_rows, _ = player_totals(sv)
check(abs(sum(sv_rows.values()) - sum(b_rows.values())) > 1e-9, "it changes the forecast")

# ---------------------------------------------------------------- 2. player spread fitted from results
fr = fit(fit_player_r=True)
check(fr.r_player != base.r_player, "the spread is fitted, not the fixed default")
check(all(0.5 <= v <= 100.0 for v in fr.r_player.values()), f"...and lands in a sane range: {fr.r_player}")
check(set(fr.mu_fit) == set(E.PLAYER_STATS) and len(fr.mu_fit["shots"]) > 100,
      "it scores against the team totals the model PREDICTED, not the ones that happened")
few = E.SoccerEngine(seed=0, fit_player_r=True)
few.r_player = {"shots": 6.0, "sot": 5.0, "tackles": 10.0}
few.mu_fit = {}
few.pl = {}
few._fit_player_dispersion()
check(few.r_player == {"shots": 6.0, "sot": 5.0, "tackles": 10.0}, "with no history to learn from, the current value stays")

# ---------------------------------------------------------------- 3. what the opponent allows each position
op = fit(opp_pos_k=20.0)
check(op.opp_pos and "shots" in op.opp_pos and len(op.opp_pos["shots"]) > 10, "a factor is learned per opponent and position")
vals = list(op.opp_pos["shots"].values())
check(all(0.5 <= v <= 2.0 for v in vals), "factors are capped, so one freak run cannot double a forecast")
check(abs(float(np.mean(vals)) - 1.0) < 0.25, f"...and sit around 1.0 on average (got {np.mean(vals):.3f})")
op_rows, _ = player_totals(op)
moved = sum(abs(op_rows[p] - b_rows[p]) for p in b_rows)
check(moved > 1e-6, "player forecasts move")
check(abs(sum(op_rows.values()) - sum(b_rows.values())) < 1e-6,
      "...but the team total is unchanged: it splits the count between players, it does not invent shots")
flat = fit(opp_pos_k=1e9)
flat_rows, _ = player_totals(flat)
check(max(abs(flat_rows[p] - b_rows[p]) for p in b_rows) < 1e-6, "a huge prior turns it back into no adjustment")

# ---------------------------------------------------------------- 4. expected goals in team strength
xg = fit(xg_blend=0.5)
check(xg.dc_xg is not None, "a second strength model is fitted on expected goals")
_, xg_probs = player_totals(xg)
check(abs(xg_probs["p_home"] - b_probs["p_home"]) > 1e-6, "match chances change")
check(abs(xg_probs["p_home"] + xg_probs["p_draw"] + xg_probs["p_away"] - 1.0) < 1e-6, "...and still add up to one")
check("xg_home" in xg_probs["context"], "the blend is recorded on the forecast, so it can be audited later")
no_xg = ms.copy()
bare = tg.drop(columns=["xg"])
check(E.SoccerEngine(seed=0, xg_blend=0.5).fit(no_xg, bare, pg, AS_OF).dc_xg is None,
      "no expected goals in the feed: the layer stays off instead of guessing")

# ---------------------------------------------------------------- all four together
allf = fit(script_v2=True, fit_player_r=True, opp_pos_k=20.0, xg_blend=0.5)
rows, probs = player_totals(allf)
check(all(np.isfinite(v) and v >= 0 for v in rows.values()) and 0 < probs["p_home"] < 1, "all four together produce sane numbers")

# ---------------------------------------------------------------- the A/B runner, end to end
import demo_server as DS
db = DS.build()
lg = db.leagues.find_one({})
names = ["base", "opp_pos", "xg_blend"]
out = AB.run_league(db, lg["iid"], names, rounds=6, refit_every=3, burn=0, z_min=2.0, verbose=False)
check(out is not None, "the A/B runner walks forward over the real database shape")
check(all(out["team"][n] for n in names) and all(out["result"][n] for n in names), "it scores team counts and the match result")
check(any(out["player"][n] for n in names), "it scores player counts against the real starting eleven")
b, v = out["team"]["base"]["shots"], out["team"]["opp_pos"]["shots"]
check(set(b) == set(v) and len(b) > 10, "both variants score the same fixtures, so the comparison is paired")
st = AB.paired({"base": out["result"]["base"], "x": out["result"]["xg_blend"]}, "base", "x", None)
check(st and st["n"] > 10 and "z" in st, "it reports a paired gain with its standard error")
check(all(out["team"]["base"][s] == out["team"]["base"][s] for s in out["team"]["base"]), "base is production's own settings")
check(AB.VARIANTS["opp_pos"][1] == "engine.opp_pos_k", "each variant names the setting to switch on if it passes")

print("\nALL ENGINE UPGRADE CHECKS PASSED")
