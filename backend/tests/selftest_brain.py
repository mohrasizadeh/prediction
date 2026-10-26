"""selftest_brain.py -- the calendar, rotation and layer-gate parts of the brain.

    pip install mongomock numpy scipy pandas
    SOCCER_BRAIN_DIR=../engine python selftest_brain.py

Proves: competition weights and the club calendar; the start model finds a planted rotation effect and
ignores noise (the gate says so); with the model off or the lineup confirmed, forecasts do not move;
the rotation chip and its sentence; calendar import is idempotent; the real-data harness gate; no banned words.
"""
from __future__ import annotations

import base64
import os
import sys
from datetime import datetime, timedelta, timezone

os.environ.setdefault("APP_ENCRYPTION_KEY", base64.b64encode(os.urandom(32)).decode())
HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("SOCCER_BRAIN_DIR", os.path.join(HERE, "soccer_brain"))
sys.path.insert(0, HERE); sys.path.insert(0, os.environ["SOCCER_BRAIN_DIR"])

import mongomock
import numpy as np
import pandas as pd

import context as CX
import engine as E
import engine_bridge as B
import mongo_init
import settings_store as S
import textguard
from simulate import simulate_league

ok = lambda m: print("  ok  ", m)


def check(cond, msg):
    if not cond:
        print("  FAIL", msg); sys.exit(1)
    ok(msg)


T0 = datetime(2026, 8, 15, 15, 0, tzinfo=timezone.utc).replace(tzinfo=None)


def ctx_row(**kw):
    c = dict(rest_days=7.0, next_gap=7.0, prev_imp=1.0, next_imp=1.0, n14=2, n_next7=1, this_imp=1.0, prev_comp="league", next_comp="league")
    c.update(kw)
    return c


# --------------------------------------------------------------------------- 1. weights and calendar
def test_calendar():
    check(CX.importance_of("league") == 1.0, "a league match weighs 1.0")
    check(CX.importance_of("league_cup") < CX.importance_of("fa_cup") < 1.0, "League Cup < FA Cup < league")
    check(CX.importance_of("league_cup", "Semi-final") > CX.importance_of("league_cup", "Round 3"), "late rounds weigh more")
    check(CX.importance_of("nonsense") == CX.DEFAULT_IMPORTANCE["other"], "unknown competition falls back to 'other'")
    check(CX.importance_of("league_cup", table={"league_cup": 0.9}) == 0.9, "weights are editable")

    rows = [(1, T0, "league", ""), (1, T0 + timedelta(days=3), "ucl", "group"), (1, T0 - timedelta(days=3), "league_cup", "Round 3"),
            (2, T0, "league", "")]
    cal = CX.Calendar(pd.DataFrame(rows, columns=["team", "kickoff", "comp", "stage"]))
    c = cal.context(1, T0, "league", "")
    check(abs(c["rest_days"] - 3.0) < 1e-9 and abs(c["next_gap"] - 3.0) < 1e-9, "rest 3 days, next match in 3 days")
    check(c["next_comp"] == "ucl" and c["prev_comp"] == "league_cup", "previous and next competition found")
    check(c["n14"] == 1, "matches in the last 14 days counted (the match itself is not)")
    c2 = cal.context(2, T0, "league", "")
    check(c2["rest_days"] == 14.0 and c2["next_gap"] == 14.0, "a club with no other matches: rest and gap capped at 14")
    check(cal.context(99, T0)["rest_days"] == 14.0, "unknown club gives neutral numbers")

    # the same match must not be its own 'next match'
    c3 = cal.context(1, T0 + timedelta(days=3), "ucl", "group")
    check(c3["next_gap"] == 14.0, "the match being forecast is never its own next match")

    p = CX.pressure_parts(ctx_row(next_gap=2.5, next_imp=0.95, this_imp=0.40, next_comp="ucl"))
    check(p["next_bigger"] > 0.5 and p["europe_soon"] == 1.0 and p["low_stakes"] == 0.6, "cup tie before Europe: bigger match, Europe soon, low stakes")
    q = CX.pressure_parts(ctx_row())
    check(all(v == 0 for v in q.values()), "a plain week has zero pressure")
    check(CX.pressure_level(CX.rotation_pressure(ctx_row())) == "low", "plain week = low rotation level")
    check(CX.pressure_level(CX.rotation_pressure(ctx_row(next_gap=2.5, next_imp=0.95, this_imp=0.40, next_comp="ucl"))) == "high", "cup tie before Europe = high")
    check(CX.pressure_parts(ctx_row(next_gap=6.0, next_imp=0.95, this_imp=0.4, next_comp="ucl"))["next_bigger"] == 0.0, "a big match 6 days away does not count")


# --------------------------------------------------------------------------- 2. the start model
def planted(seed, effect):
    """Eight clubs, 14 players, 30 rounds. Regulars (first 11) usually start. `effect`: chance a regular is rested when a
    European match is 3 days behind this one."""
    rng = np.random.default_rng(seed)
    teams = list(range(8))
    rows, kicks, euro = [], {}, set()
    gid = 0
    for rnd in range(30):
        order = rng.permutation(teams)
        for h, a in zip(order[:4], order[4:]):
            gid += 1
            kicks[gid] = T0 + timedelta(days=7 * rnd)
            for t in (h, a):
                eu = rng.random() < 0.25
                if eu:
                    euro.add((t, kicks[gid]))
                for p in range(14):
                    reg = p < 11
                    prob = 0.93 if reg else 0.12
                    if eu and reg:
                        prob = 0.93 - effect
                    if eu and not reg:
                        prob = 0.12 + effect * 0.6
                    rows.append((gid, rnd, t, t * 100 + p, int(rng.random() < prob)))
    pg = pd.DataFrame(rows, columns=["game_id", "round", "team", "player", "started"])
    return pg, kicks, euro


def make_db(pg, kicks, euro, league_iid=1):
    db = mongomock.MongoClient()["brain"]
    mongo_init.ensure_indexes(db)
    sched = pg.groupby("game_id")["team"].unique()
    for g, ts in sched.items():
        db.matches.insert_one({"iid": int(g), "ext_id": f"x{g}", "league_iid": league_iid, "kickoff": kicks[g], "home_iid": int(ts[0]), "away_iid": int(ts[1]), "status": "final"})
    B.import_calendar(db, [{"team_iid": t, "kickoff": k + timedelta(days=3), "comp": "ucl", "stage": "group"} for t, k in euro], source="test")
    return db


def test_start_model():
    pg, kicks, euro = planted(1, effect=0.45)
    db = make_db(pg, kicks, euro)
    S.put(db, "context.min_rows", 500, actor="test")
    ms = pg[["game_id", "round"]].drop_duplicates()
    cal = B.build_calendar(db, range(8))
    res = B.fit_start_model(db, 1, ms, pg, cal)
    check(res["passed"] and res["z"] >= 2.0 and res["gain"] > 0, f"planted rotation effect passes the gate (z={res['z']:.1f})")
    co = res["model"].coefficients()
    check(co["europe_soon*regular"] < -0.5, "a regular is rested before a European match (coefficient < 0)")
    check(co["europe_soon"] + 0.5 * co["europe_soon*regular"] < co["europe_soon"] - 0.5 * co["europe_soon*regular"], "regulars lose starts, fringe players gain them")

    pg2, k2, e2 = planted(2, effect=0.0)
    db2 = make_db(pg2, k2, e2)
    S.put(db2, "context.min_rows", 500, actor="test")
    res2 = B.fit_start_model(db2, 1, pg2[["game_id", "round"]].drop_duplicates(), pg2, B.build_calendar(db2, range(8)))
    check(not res2["passed"], f"no real effect: the gate says no (z={res2['z']:.1f})")

    S.put(db2, "context.start_model", "on", actor="test")
    res3 = B.fit_start_model(db2, 1, pg2[["game_id", "round"]].drop_duplicates(), pg2, B.build_calendar(db2, range(8)))
    check(res3["model"] is not None and res3["mode"] == "on", "mode 'on' forces the model even when the gate says no")
    S.put(db2, "context.start_model", "off", actor="test")
    res4 = B.fit_start_model(db2, 1, pg2[["game_id", "round"]].drop_duplicates(), pg2, B.build_calendar(db2, range(8)))
    check(res4["model"] is None and not res4["passed"], "mode 'off' trains nothing")

    S.put(db, "context.min_rows", 10 ** 6, actor="test")
    res5 = B.fit_start_model(db, 1, ms, pg, cal)
    check(not res5["passed"] and "rows" in res5["reason"], "too little data: stays off and says why")


# --------------------------------------------------------------------------- 3. calendar import
def test_import():
    db = mongomock.MongoClient()["imp"]
    mongo_init.ensure_indexes(db)
    rows = [{"team_iid": 5, "kickoff": T0, "comp": "fa_cup", "stage": "Round 4"}, {"team_iid": 5, "kickoff": T0 + timedelta(days=4), "comp": "uel"}]
    B.import_calendar(db, rows); B.import_calendar(db, rows)
    check(db.club_calendar.count_documents({}) == 2, "importing the same calendar twice adds nothing")
    db.matches.insert_one({"iid": 1, "ext_id": "x1", "league_iid": 1, "kickoff": T0 + timedelta(days=8), "home_iid": 5, "away_iid": 6})
    cal = B.build_calendar(db, [5, 6])
    c = cal.context(5, T0 + timedelta(days=8), "league", "")
    check(c["prev_comp"] == "uel" and abs(c["rest_days"] - 4.0) < 1e-9, "league matches and imported cups sit on one calendar")


# --------------------------------------------------------------------------- 4. engine integration
def test_engine():
    matches, tg, pg, _ = simulate_league(seed=11)
    eng = E.SoccerEngine(n_draws=20, seed=3)
    as_of = 26
    eng.fit(matches[matches["round"] < as_of], tg[tg["round"] < as_of], pg[pg["round"] < as_of], as_of)
    h, a = [int(x) for x in matches[matches["round"] == as_of].iloc[0][["home", "away"]]]

    def sig(fcs):
        return sorted((f.scope, f.team, f.player or 0, f.stat, f.thr, round(f.p, 9), round(f.p_play, 9)) for f in fcs)

    f0, _ = eng.predict_fixture(h, a)
    ctx_hi = {h: ctx_row(rest_days=2.5, next_gap=2.5, next_imp=0.95, this_imp=0.40, next_comp="ucl", n14=5, prev_comp="league_cup"), a: ctx_row()}
    f1, _ = eng.predict_fixture(h, a, ctx=ctx_hi)
    check(sig(f0) == sig(f1), "no start model attached: calendar context changes no probability")
    top = [f for f in f1 if f.team == h]
    check(all(f.rotation == "high" and "Champions League" in f.rotation_why for f in top), "home club: rotation 'high' with a plain sentence")
    check(all(f.rotation == "low" and f.rotation_why == "" for f in f1 if f.team == a), "away club with a plain week: 'low', no sentence")

    # a hand-set model: regulars rest, fringe players play
    m = CX.StartModel()
    m.design(pd.DataFrame({k: [0.0] for k in CX.StartModel.PARTS}), np.array([0.5]))
    m.w = np.zeros(2 * len(CX.StartModel.PARTS))
    i = CX.StartModel.PARTS.index("europe_soon") * 2
    m.w[i] = 0.0; m.w[i + 1] = -4.0
    eng.set_start_model(m, enabled=False)
    f2, _ = eng.predict_fixture(h, a, ctx=ctx_hi)
    check(sig(f0) == sig(f2), "model attached but gate closed: forecasts identical")
    eng.set_start_model(m, enabled=True)
    f3, _ = eng.predict_fixture(h, a, ctx=ctx_hi)
    pp0 = {f.player: f.p_play for f in f0 if f.scope == "player" and f.team == h and f.stat == "shots" and f.thr == 0.5}
    pp3 = {f.player: f.p_play for f in f3 if f.scope == "player" and f.team == h and f.stat == "shots" and f.thr == 0.5}
    use = {f.player: f.p_play_usual for f in f3 if f.scope == "player" and f.team == h and f.stat == "shots" and f.thr == 0.5}
    reg = [p for p in pp0 if use[p] and use[p] > 0.8]
    fringe = [p for p in pp0 if use[p] and use[p] < 0.3]
    check(len(reg) >= 3 and all(pp3[p] < pp0[p] for p in reg), "regular starters: chance to play falls under rotation pressure")
    check(len(fringe) == 0 or all(pp3[p] >= pp0[p] - 1e-9 for p in fringe), "fringe players: chance to play does not fall")
    adj, base = eng._rotated_starts(h, CX.pressure_parts(ctx_hi[h]))
    check(abs(sum(adj.values()) - sum(base.values())) < 0.5, "the club's expected number of starters is kept (it moves who, not how many)")
    check(sum(1 for p in adj if adj[p] != base[p]) > 0, "the start model did move some chances")
    away = {f.player: f.p for f in f3 if f.team == a and f.scope == "player"}
    away0 = {f.player: f.p for f in f0 if f.team == a and f.scope == "player"}
    check(all(abs(away[k] - away0[k]) < 1e-12 for k in away), "the club with no pressure is untouched")

    # a confirmed lineup beats the model
    xi = {p for p in eng.squads[h]}
    xi = set(list(xi)[:11])
    fc, _ = eng.predict_fixture(h, a, lineups={h: xi}, ctx=ctx_hi)
    eng.set_start_model(None)
    fc0, _ = eng.predict_fixture(h, a, lineups={h: xi}, ctx=ctx_hi)
    check(sig(fc) == sig(fc0), "confirmed lineup: the start model does nothing")

    # text safety
    sents = {f.rotation_why for f in f1}
    check(not textguard.find(sorted(sents)), "rotation sentences contain no banned words")


# --------------------------------------------------------------------------- 5. the harness gate
def test_gate():
    import backtest_real as BR
    rng = np.random.default_rng(0)
    n = 600
    full = rng.normal(-2.0, 0.5, n)
    frame = []
    for v, d in (("full", np.zeros(n)), ("good", 0.05 + rng.normal(0, 0.1, n)), ("flat", rng.normal(0, 0.1, n))):
        for i in range(n):
            frame.append((v, i, 1, 0, "shots", 0.0, 1.0, 1.0, full[i] + d[i]))
    res = pd.DataFrame(frame, columns=["variant", "game_id", "round", "team", "stat", "y", "mu", "r", "ll"])
    ok1, g1, _ = BR.gate(res, "good", "full")
    ok2, g2, _ = BR.gate(res, "flat", "full")
    check(ok1 and g1 > 0, "gate: a real gain passes")
    check(not ok2, "gate: noise does not pass")


def main():
    for name, fn in (("calendar", test_calendar), ("start model and gate", test_start_model), ("calendar import", test_import),
                     ("engine integration", test_engine), ("harness gate", test_gate)):
        print(f"[{name}]")
        fn()
    print("\nALL BRAIN CHECKS PASSED")


if __name__ == "__main__":
    main()
