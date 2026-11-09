"""engine_newmarket.py -- is a NEW player market worth publishing? (docs/70)

engine_ab.py answers a different question. It pairs two variants on the SAME forecasts and asks
which scores better, which only works when both variants forecast the same things. A market that
did not exist before has no counterpart to pair against, so the honest question is not "is this
variant better" but:

    1. Does the engine beat the obvious alternative?   The alternative to a model is the player's
       own average. If the engine cannot beat "use his historical rate", the market is an expensive
       way to restate a mean and should not ship.
    2. Is it calibrated?                               When the market says 70%, does it happen
       about 70% of the time? A market that is sharp but wrong is worse than no market, because
       this product's entire claim is that its numbers mean what they say.
    3. Can it clear the band at all?                   engine.line_band keeps a line only inside
       [0.5, 0.985]. A market whose lines all sit at 20% ships as nothing, however well modelled.

Walk-forward, the same rule as engine_ab: for every round the engine is refitted on EARLIER rounds
only, then forecasts that round, then the round is scored. Nothing from the round being scored is
used to make the forecast.

    python engine_newmarket.py --market fouls_committed
    python engine_newmarket.py --market goal_involvements --teams 14 --seed 5

Runs on a simulated league by default, because the live database is not reachable from a
development container. That is a real limitation and the report says so: simulated football tells
you whether the MACHINERY works and whether the market can clear a band, not what the market is
worth on the owner's actual leagues. Point it at a real database with --mongo to answer that.

Nothing is written anywhere and no setting is changed.
"""
from __future__ import annotations

import argparse
import math
import os
import sys
from collections import defaultdict

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "soccer_brain"))

import engine as E                     # noqa: E402
from simulate import simulate_league   # noqa: E402


def nb_ll(y, mu, r):
    """Log-likelihood of a count under the negative binomial the engine itself uses."""
    mu = max(float(mu), 1e-6)
    r = max(float(r), 1e-6)
    p = r / (r + mu)
    return float(math.lgamma(y + r) - math.lgamma(r) - math.lgamma(y + 1)
                 + r * math.log(p) + y * math.log(max(1 - p, 1e-12)))


def paired(a, b):
    """Mean gain of a over b on the keys they share, and its z. Paired, so the league's own
    difficulty and luck cancel -- the same observation is scored by both."""
    keys = set(a) & set(b)
    if len(keys) < 30:
        return 0.0, 0.0, 0.0, len(keys)
    d = np.array([a[k] - b[k] for k in keys], dtype=float)
    se = d.std(ddof=1) / math.sqrt(len(d))
    return float(d.mean()), float(se), float(d.mean() / se) if se > 0 else 0.0, len(d)


def run(market, n_teams, seed, refit_every, z_min, fit_r=False):
    ms, tg, pg, _ = simulate_league(n_teams=n_teams, seed=seed)
    own, team = market, "team_" + market
    if own not in pg.columns or team not in pg.columns:
        print(f"the simulated league has no {own}/{team}; nothing to measure")
        return 2

    # Fit and forecast this market ALONE, so the report is about it and not about the three that
    # already ship. Both lists matter: PLAYER_STATS decides what is fitted, PLAYER_THR decides what
    # lines are drawn -- a market in the first and not the second produces no forecasts at all,
    # silently, which is exactly the trap docs/70 describes for the settings.
    E.PLAYER_STATS[:] = [market]
    E.PLAYER_THR.clear()
    # A saves ladder starts higher: a keeper making NO save is the unusual match, so "1+ saves" is
    # near-certain and says nothing. The interesting lines are 2+ and above.
    E.PLAYER_THR[market] = [1.5, 2.5, 3.5, 4.5] if market == "saves" else [0.5, 1.5, 2.5]
    rounds = sorted(ms["round"].unique())
    start = max(6, len(rounds) // 3)      # enough history for a first fit
    play = [r for r in rounds if r >= start]

    pgi = {gid: g for gid, g in pg.groupby("game_id")}
    eng_ll, base_ll = {}, {}              # key -> log-likelihood
    buckets = defaultdict(lambda: [0, 0])  # predicted-decile -> [hit, n] for the 0.5 line
    eng = None

    for i, r in enumerate(play):
        if i % refit_every == 0 or eng is None:
            # extra_stats, so the TEAM layer forecasts this stat too -- without it the player
            # share has no mu_team to take a share of (docs/70).
            eng = E.SoccerEngine(seed=0, extra_stats=(market,), fit_player_r=fit_r).fit(ms, tg, pg, r)
            # The naive alternative, refit on exactly the same history: each player's own mean
            # rate per 90. Nothing clever -- that is the point of a baseline.
            past = pg[pg["round"] < r]
            past = past[past["minutes"] > 0]
            rate = (past.groupby("player")[own].sum() / (past.groupby("player")["minutes"].sum() / 90.0)).to_dict()
            league_rate = float(past[own].sum() / max(past["minutes"].sum() / 90.0, 1e-6))

        for m in ms[ms["round"] == r].itertuples():
            if m.home not in eng.tidx or m.away not in eng.tidx:
                continue
            rows = pgi.get(m.game_id)
            if rows is None:
                continue
            starters = {}
            for t in (m.home, m.away):
                st = rows[(rows["team"] == t) & (rows["started"] == 1)]
                if len(st) >= 7:
                    starters[t] = set(int(x) for x in st["player"])
            actual = {(int(x.team), int(x.player)): x for x in rows.itertuples()}
            try:
                fcs, _ = eng.predict_fixture(m.home, m.away, lineups=starters or None)
            except Exception:
                continue
            seen = set()
            for f in fcs:
                if f.scope != "player" or f.stat != market:
                    continue
                key = (m.game_id, int(f.player))
                if key in seen:
                    continue
                seen.add(key)
                a = actual.get((int(f.team), int(f.player)))
                if a is None or not getattr(a, "started", 0) or getattr(a, "minutes", 0) <= 0:
                    continue
                y = getattr(a, market, None)
                if y is None or y != y:
                    continue
                rr = eng.r_player.get(market, 6.0)
                eng_ll[key] = nb_ll(y, f.expected, rr)
                # the baseline's expectation for the same appearance, from his own rate
                mu_b = rate.get(int(f.player), league_rate) * (a.minutes / 90.0)
                base_ll[key] = nb_ll(y, mu_b, rr)
                # calibration of the 1+ line, which is the one a reader would see
                # The chance of clearing the ladder's FIRST rung -- 1+ for most markets, 2+ for
                # saves. Calibrating "1+ saves" would be measuring a near-certainty.
                #
                # `need` has to come from the SAME rung the forecast is about. It did not: the
                # forecast was P(Y >= need) while the outcome scored was `y >= 1`, which agree only
                # when need == 1. For saves, need is 2, so a forecast of "2+" was being graded
                # against "did he make any save at all" -- a near-certainty. That mismatch, not the
                # model, produced the 33-point miscalibration saves was first reported with.
                thr0 = E.PLAYER_THR[market][0]
                need = int(thr0) + 1
                p1 = 1.0 - sum(math.exp(nb_ll(k, f.expected, rr)) for k in range(need))
                b = min(int(p1 * 10), 9)
                buckets[b][0] += int(y >= need)
                buckets[b][1] += 1

    if not eng_ll:
        print(f"no {market} forecasts were produced -- the market never reached the forecast loop")
        return 2

    gain, se, z, n = paired(eng_ll, base_ll)
    me = float(np.mean(list(eng_ll.values())))
    mb = float(np.mean([base_ll[k] for k in eng_ll]))
    verdict = "PASSES" if (gain > 0 and z >= z_min) else "does not pass"

    print(f"\n{'=' * 74}\n{market} -- simulated league, {n_teams} teams, seed {seed}"
          f"{', dispersion fitted' if fit_r else ''}\n{'=' * 74}")
    print(f"{'':4}{'':26}{'n':>7}{'mean ll':>11}{'gain':>10}{'se':>8}{'z':>7}")
    print(f"{'':4}{'his own average':26}{n:>7}{mb:>11.4f}")
    print(f"{'':4}{'the engine':26}{n:>7}{me:>11.4f}{gain:>10.4f}{se:>8.4f}{z:>7.2f}   {verdict}")
    print(f"\n    gate: better than the baseline by at least {z_min} paired standard errors")

    need0 = int(E.PLAYER_THR[market][0]) + 1
    print(f"\n    calibration of the {need0}+ line -- said, against happened:")
    rows = [(b, h, t) for b, (h, t) in sorted(buckets.items()) if t >= 25]
    if not rows:
        print("      too few forecasts in any band to judge")
    else:
        worst = 0.0
        for b, h, t in rows:
            said, got = (b + 0.5) / 10, h / t
            worst = max(worst, abs(said - got))
            bar = "#" * int(got * 30)
            print(f"      said ~{said:4.0%}   happened {got:4.0%}   (n={t:5d})  {bar}")
        print(f"\n    worst gap between said and happened: {worst:.0%}")

    inband = [t for b, h, t in rows if (b + 0.5) / 10 >= 0.5]
    total = sum(t for _, _, t in rows)
    share = sum(inband) / total if total else 0.0
    print(f"\n    share of {need0}+ lines that clear the standard 0.5 floor: {share:.0%}"
          f"{'  -- needs engine.line_band_by_stat' if share < 0.25 else ''}")
    print("\n    SIMULATED football. This says whether the machinery works and whether the market")
    print("    can clear a band. What it is worth on the owner's real leagues needs the real data.")
    return 0 if verdict == "PASSES" else 1


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--market", required=True)
    ap.add_argument("--teams", type=int, default=14)
    ap.add_argument("--seed", type=int, default=3)
    ap.add_argument("--refit-every", type=int, default=3)
    ap.add_argument("--z", type=float, default=2.0)
    ap.add_argument("--fit-r", action="store_true", help="fit the dispersion from residuals (engine.fit_player_r)")
    a = ap.parse_args()
    sys.exit(run(a.market, a.teams, a.seed, a.refit_every, a.z, a.fit_r))
