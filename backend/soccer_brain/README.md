# soccer_brain

Analysis engine for soccer statistics. Forecasts the probability that a team or
player reaches a threshold (shots, shots on target, corners, tackles), with an
uncertainty band, a tier, and plain-language reasons. No prices, no paid APIs.

## Run it

    pip install numpy scipy pandas
    python3 backtest.py        # about 2.5 minutes, prints the report

## Files

| File | Job |
| --- | --- |
| `core.py` | Shrinkage, recency weights, negative binomial probabilities, isotonic calibration, tiers, reasons, metrics |
| `nbglm.py` | Negative binomial regression with an offset and relative ridge penalties |
| `strength.py` | Dixon-Coles team strength with time decay: expected goals, win/draw/loss |
| `engine.py` | Style vectors, named tactics, team-total models, optional lineup-effects layer, player minutes and share layer, forecasts |
| `simulate.py` | Synthetic league with hidden tactical traits, to test the machinery |
| `backtest.py` | Walk-forward harness: refit on the past, forecast the next round, score |
| `context.py` | Competition importance, club calendar, rotation pressure, the start model (who starts) |
| `tactics.py` | Press, build-up, counter and long-ball indices from the tactical guide; named systems; off by default |
| `backtest_real.py` | Walk-forward harness for real data: whole-distribution score, paired z, gate |
| `schema.sql` | Sport-agnostic database tables |

## How a forecast is made

1. Team strength gives expected goals and expected margin (the game-state signal).
2. Each team gets a style vector from past games only: shots, corners, tackles,
   possession and shot accuracy, for and against, shrunk toward the league mean.
3. Team totals start from a simple baseline: league mean x team's output x
   opponent's concession. A regularised regression adds small corrections for
   venue, game state, style and style-by-style matchups.
4. Each player gets a shrunk share of the team total and a minutes mixture
   (starts, comes on, out). Confirmed lineups collapse the mixture.
5. Probabilities come from a negative binomial. A credible interval comes from
   re-drawing the uncertainty in the team total and the player's share.
6. Reasons are the factors that push the count up, written from fixed phrases.

## The opponent: tactic and personnel

- **Tactic.** Every forecast already uses the opponent's style vector: shots, corners
  and tackles they allow, and possession. The 4x4 matchup terms let an opponent's
  style change how our team's style plays out (a wide side against a low block,
  a pressing side against a possession side). Teams one standard deviation above
  the league on an index get a label (low block, high press, possession-based),
  carried on each forecast and used in the reasons ("The opponent plays a low
  block, which lifts corners.").
- **Personnel.** An optional layer (`SoccerEngine(lineup=True)`) fits how each
  player's presence in the starting XI moves the team's own output and the
  opponent's output (ridge regression), then applies it to the expected lineups
  of both sides. It is **off by default**: on simulated data it did not pass the
  gate (see below).

## Gates (a feature stays only if it passes)

- Beat the raw last-10 rate on log loss in every market.
- Beat the no-context player baseline.
- Matchup terms must beat the same engine without them.
- Each tier must hit at about its stated rate on forecasts it has never seen.

## What the simulated run showed

Simulated data, so it tests the machinery, not real soccer. The simulation now
rotates lineups and has hidden star defenders and attackers.

- Player forecasts: log loss 0.469 against 0.694 for the raw last-10 rate.
- Team context beat the no-context baseline on player markets (0.469 vs 0.478).
  On team markets the baseline was as good as the engine, so team markets are
  not proven yet.
- Matchup terms helped slightly on corners and tackles, neutral elsewhere.
- **Lineup layer: failed the gate.** It found the right direction (fitted
  opponent-defender effects correlate -0.11 with the true ones, own attackers
  +0.18) but too weakly. Team shots log loss 0.535 with it, 0.526 without; all team markets 0.602 vs 0.592.
  Learning each player's identity effect from about 70 games per team is not
  possible. We keep the layer off.
- Calibration: the engine was already close. Isotonic did not help (0.4686 vs 0.4673).
  Keep it as a monitor.
- Tiers: Strong stated 0.906, hit 0.880 (a little overconfident, so raise the Strong cutoff or calibrate it on real data). Solid stated 0.727, hit 0.734.

How personnel becomes learnable on real data: do not learn a coefficient per
player. Use observed player quality (defender tackles, interceptions, clearances
and aerial wins per 90; attacker xG and xA per 90) to build two or three team
"personnel indexes" for the expected lineup, then learn one coefficient per index.
That needs a provider with player-level tier B stats. Test it with the same gate.

## Known limits and next steps

1. Run on real data first. Everything above is simulated.
2. Style dimensions here are tier A (basic match stats). Add tier B (xG, passes,
   crosses, pressing) where a provider has them. The matchup terms should get stronger.
3. Add referee and fouls/cards markets.
4. Goalkeeper saves (opponent shots on target minus goals, keeper save rate).
5. Joint distributions (a Monte Carlo of the match) for combined thresholds.
6. Real lineup feed: the `lineups` table feeds `predict_fixture(..., lineups=)`.
7. Check each data provider's terms before charging users.
