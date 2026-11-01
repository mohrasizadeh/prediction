# 37. Engine upgrades: four candidates and how to decide on them

Written 2026-11-01. Four changes to the forecast engine are built and shipped **off**. Each one is switched on only
if it beats what you run today, on your own matches, by the project's usual margin. The script that decides is
`backend/engine_ab.py`. Nothing in this document changes a forecast until you switch a setting on.

Background: a proposed "interaction-based" engine design was compared with ours (summary in the audit thread of
docs/36). Most of it we already do, often in a stronger form: a negative binomial instead of a Poisson, Dixon-Coles
for the result, opponent concession in every team total, a player share with a minutes mixture, uncertainty ranges,
isotonic calibration and earned tiers. Several of its ideas we have already tested and rejected on real data
(tactical style layers, formation shape, rotation on team totals: docs/18). What it had that we did not is below.

## 1. The four candidates

| Setting | What it adds | Why it might help |
|---|---|---|
| `engine.script_v2` | Two more inputs to every team total: how one-sided the fixture looks, and how many goals the two clubs' matches usually carry. | Today the model sees the expected margin as a straight line. A side expected to lead sits deeper, and an open match has more of everything. Neither is a straight line in the margin. |
| `engine.fit_player_r` | Works out how much a player's count bounces around its average from your own results. | Today those numbers are fixed guesses (shots 6, on target 5, tackles 10) set before any real data existed. They set the width of every player percentage. |
| `engine.opp_pos_k` | What this opponent lets players in that position do, as a factor on each player's share. | The team total already knows the opponent. It does not know that this opponent is soft against wide players and hard against strikers. This is the cheap version of a full-back-versus-winger matchup. |
| `engine.xg_blend` | A second Dixon-Coles fitted on expected goals, blended into the match chances. | Goals are few and swingy. Expected goals say more about how good a side is with the same number of matches. Our feed carries team expected goals. |

### What each one does to the maths

**Game state (`engine.script_v2`).** The team-total regression gains two columns: `|expected margin|` and the
average goals in the two clubs' matches. Both come from the snapshot built before the round, so no result from the
round being forecast leaks in. They join the existing `game_script` group, so the reasons on a card still read the
same.

**Player spread (`engine.fit_player_r`).** For every past appearance the player's share is rebuilt **without** that
game (leave one out), and the expected count uses the team total the model would have **predicted**, not the total
that actually happened. Scoring against the real total would hide the team-total error a forecast carries and leave
the engine too confident. The fitted value is capped at 100, above which a negative binomial is a Poisson for our
purposes. With too little history the current value stays.

**Opponent by position (`engine.opp_pos_k`).** For each (opponent, position, stat), the factor is what that
position actually did against them divided by what the league's players in that position would be expected to do
for the same team total and minutes, shrunk toward 1.0 by `opp_pos_k` units of expected count and capped to
0.5–2.0. It multiplies the player's share, and the shares are then renormalised, so **the team total never
changes**: it moves the count between the players on the pitch rather than inventing shots. A new reason is
available on a card ("The opponent gives up more shots to players in his position"). `20` is the starting point;
higher trusts the opponent's record less.

**Expected goals (`engine.xg_blend`).** A second Dixon-Coles is fitted on team expected goals with the same time
decay, and its expected goals are blended with the goals model's in log space. `0.5` counts them equally. The blend
is stored on the match forecast (`context.xg_home`, `context.xg_away`) so any number can be traced back. If the feed
has no expected goals for both sides, or there are fewer than 60 matches, the layer stays off rather than guessing.

## 2. How to decide (run this)

```bash
cd backend
MONGO_URL=... DB_NAME=... python3 engine_ab.py --league 3
MONGO_URL=... DB_NAME=... python3 engine_ab.py                 # every league that is switched on
MONGO_URL=... DB_NAME=... python3 engine_ab.py --only xg_blend --rounds 80
```

It reads the database and writes nothing. For every round it refits each variant on **earlier rounds only**, then
forecasts that round, then scores it. Three scores, each the mean log-likelihood of what really happened:

* **team counts** — the whole count distribution for shots, shots on target, corners and tackles, not one line.
* **player counts** — the same per player, with the real starting eleven handed to every variant, scored on
  players who started.
* **match result** — home, draw, away.

Every comparison is paired: the same fixture scored by both variants, so league strength and luck cancel. The
printed verdict is the project's standing gate: **better, and by at least 2 paired standard errors.**

Useful options: `--rounds N` (how far back to score, default 40), `--refit-every N` (default 4; lower is slower and
more exact), `--only a,b`, `--z 2.0`, `--league` repeated for several leagues.

Expect it to take a while: it refits the whole engine many times. Start with one league and `--rounds 20`.

## 3. What to do with the answer

* **Passes.** Switch the setting on in Admin → Settings → Engine (`engine.script_v2` and `engine.fit_player_r` are
  on/off; `engine.opp_pos_k` takes 20; `engine.xg_blend` takes 0.5). It applies at the next engine run. Record the
  numbers in the table below.
* **Does not pass.** Leave it off and record that too, with the z. A change that does not earn its place is not
  neutral: it is one more thing to maintain and one more way to be wrong.
* Re-run after a season of new data. A layer that fails on 300 matches can pass on 3,000.

### Results on real data

| Date | League(s) | Matches | Variant | Team counts (z) | Player counts (z) | Match result (z) | Decision |
|---|---|---|---|---|---|---|---|
| | | | | | | | *not run yet: needs the production database* |

**Do not fill this in from the demo database.** That league is simulated. It has no position-specific defensive
behaviour, so `opp_pos` is noise there and the gate correctly throws it out; and its expected goals are derived
from its goals, so `xg_blend` looks good for a circular reason. Only your own matches decide.

## 4. What is still not covered

These remain open after this round of work, in the order they are worth doing:

1. **Nothing is proven on your data yet.** The engine's accuracy has been shown on simulated matches, on StatsBomb
   2015/16 for three leagues, and on public match tables (team counts, no players). Until `engine_ab.py` and
   `soccer_brain/backtest_real.py` run on PitchAPI history, no player market is proven. This matters more than
   anything below.
2. **Minutes.** Expected minutes multiply every player count, and they come from a start/sub mixture of past
   appearances. A proper model (position, rest, expected margin, the start model) would improve every player
   market at once.
3. **More markets**, once 1 is done: scores a goal (shots × a position goal rate, penalty takers handled), fouls
   committed and fouls drawn. Fouls also feed the yellow-card model.
4. **Scoring early and per market.** Calibration was fitted on 2015/16 data and only refits after 5,000 scored
   forecasts. Score live forecasts per market as soon as real results arrive: that is also the public track record
   the product is meant to stand on (docs/36 Part 2).

## 5. Files

| File | Change |
|---|---|
| `backend/soccer_brain/engine.py` | The four layers, each off by default. |
| `backend/soccer_brain/core.py` | One new reason line for the opponent-by-position factor. |
| `backend/engine_bridge.py` | Reads the four settings. |
| `backend/engine_ab.py` | **New.** The walk-forward A/B runner and the gate. |
| `backend/settings_registry.json`, `docs/11_settings_registry.json` | Four settings, all off. |
| `backend/tests/selftest_engine_upgrades.py` | **New.** Each layer is off by default, does what it should and nothing else (the team total stays put under the position factor), and the runner works end to end. |
