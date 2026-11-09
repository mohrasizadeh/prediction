# 70 — Two new player markets: fouls, and goals-or-assists

The engine published three player markets — shots, shots on target, tackles. This adds two more,
and the interesting part is why neither was a settings change.

## What the owner asked for, and why the combined form is the right one

The ask was goals, assists and fouls. Goals and assists are better answered **together**, as one
market, and that is what shipped.

An elite forward is roughly **30%** for a goal and **15%** for an assist in a given match. Both sit
under `engine.line_band`'s 0.5 floor, so neither can exist on its own — every rung falls below the
band and the whole market ships as an invisible carrier. That is not an oversight; `band_for`'s
docstring says it in as many words.

Combined, they are about **40–45%**. But the combination has to be done as a **count**, not as a sum
of two probabilities: a player who scores often also assists, so adding the marginals double-counts
the overlap. `goal_involvements` has been a stored, backfilled column since
`normalize.DERIVED_PLAYER_COLS` — *goals + assists*, and `None` unless **both** parts are known, so
an unknown is never silently a zero. Being a count, the same negative-binomial machinery applies
with no new mathematics.

So the market is one event — *did he score or assist* — counted once.

## Why none of this was a setting

`PLAYER_STATS` was a hard-coded module constant. `configure_engine` overrode `PLAYER_THR` and
`TEAM_THR` from settings and never touched it, so **a market added to `engine.player_ladder` was
silently ignored**: no error, no forecasts, a setting that looked configured and did nothing. Five
things had to exist in code before the ladder could mean anything:

| | |
|---|---|
| the market is modelled | `engine.ALL_PLAYER_STATS` |
| its **team total** is on the player row | `ingest.py` — the model is a *share of a team total*, `E = pgp["team_"+s] * minutes/90` |
| it has a dispersion | `DEFAULT_R_PLAYER`; `self.r_player[s]` is a direct lookup, so a missing one is a `KeyError` mid-run |
| it has words | `engine_bridge.STAT_LABEL`, or a card prints the raw column name |
| history exists for it | a column added today starts empty, and the engine reads `engine.history_rounds` back |

## The dispersion

`var = mu + mu²/r`, so a **lower** r means more clustering. Involvements get **3.0** against shots'
6.0: a player either gets involved in a goal or he does not, where shots arrive steadily. These are
starting values, not claims — `engine.fit_player_r` replaces all of them from the data when it is on.

## Three failure modes, and where each is stopped

**A market the owner did not ask for must not publish.** **A market the engine cannot fit must be
dropped, not guessed at.** **A market with no data in this league must drop the market, never the
rows** — a `dropna` on an empty column would delete every appearance in the league and take the three
working markets down with it.

All three are settled in one place, computed from the canonical list on every run:

```python
E.PLAYER_STATS[:] = [s for s in E.ALL_PLAYER_STATS if s in E.PLAYER_THR and s in avail]
```

Computed **from `ALL_PLAYER_STATS`**, not by narrowing whatever the last league left behind.
`PLAYER_STATS` is module state and `run_league` is a per-league loop, so filtering in place meant a
market dropped for one league stayed dropped for every league after it and could never grow back.
The test caught that; it was not caught by reading.

And `fit()` itself narrows to what the frame carries. The guard belongs in the engine, not in its
callers: `selftest_brain` builds its own frame and failed with `KeyError: 'team_fouls_committed'`
the moment the markets were added. A caller that is studying shots has no reason to carry columns
for markets it is not studying, and the engine should fit what it is given.

## The wall: a player market needs a TEAM forecast

Found by `engine_newmarket.py`, not by reading, and it is the reason neither market ships yet.

A player market is *a share of a team total*, and `predict_fixture` takes that share of
**`mu_team[stat]`** — the team's **predicted** total. So the stat must be one the **team layer
forecasts**, and the team layer models exactly four: `STATS = ["shots", "sot", "corners",
"tackles"]`, plus anything passed as `extra_stats` — which `engine_bridge` never passes.

Fouls and goal involvements are in neither. The engine fitted both happily and then died at the
first fixture:

```
goal_involvements  ->  KeyError 'goal_involvements'
fouls_committed    ->  KeyError 'fouls_committed'
```

`selftest_new_markets` did not catch this, because the wiring it checks **is** right. It took a
walk-forward run that actually predicts a fixture. Had the settings been pasted in, the next engine
run would have raised mid-league.

So `fit()` now requires three things of a market, not two: its own column, its team total, **and
that the team layer forecasts it**. A market failing the third is simply not published — pasting it
into the ladder produces no forecasts rather than an exception, which is what makes the settings
safe to set.

**To unblock:** the team layer has to forecast the stat. `SoccerEngine` already takes an
`extra_stats` argument for exactly this and nothing passes it. Fouls would need
`fouls_committed` and `fouls_committed_against` on the team frame, then threading through.
Goal involvements would need a team involvement total — real, but a stranger quantity.

## Saves, and the market that passed the gate and still must not ship

Keepers are a third case. `engine.exclude_positions` is `["GK"]` and can only remove a player from
**every** market at once, so the engine gained a per-market position map: `MARKET_POSITIONS`, with
`saves: ("GK",)`. A keeper gets keeper markets and nobody else's; everyone else gets the rest and
never saves. `build_frames`' `dropna` had to become position-aware too — `normalize.players` sets a
keeper's tackles to `None` on purpose, and tackles is in `PLAYER_REQUIRED`, so a flat `dropna`
deleted every keeper in the league.

The share model turned out to be **right** for saves, not degenerate as first thought. A keeper is
his side's saves, so his share is ~1.0 — but the team layer forecasts the team total, and that is
where the work happens: it knows this side concedes shots. A near-1.0 share of a well-forecast team
total is a real forecast.

**And then it appeared to fail calibration** — 55% said against 88% happened, a 33-point gap. Two
things were wrong with that finding, and both were mine rather than the engine's.

**The gap was a bug in the validation harness.** `engine_newmarket.py` forecast the ladder's first
rung but scored the outcome at a fixed `y >= 1`:

```python
need = int(thr0) + 1                     # 2 for saves, 1 for every other market
p1 = 1.0 - sum(exp(nb_ll(k, mu, r)) for k in range(need))   # P(Y >= need)
buckets[b][0] += int(y >= 1)             # <-- graded against "any save at all"
```

The two agree only when `need == 1`. Fouls and involvements both start at 0.5, so `need` is 1 and
their numbers were sound. Saves starts at 1.5, so a forecast of **2+ saves** was being graded
against **did he make any save** — a near-certainty. That one mismatch was the whole 33 points.

**And the dispersion diagnosis was backwards.** I wrote that the counts were under-dispersed and so
outside what a negative binomial can represent. Measured:

```
keeper appearances 364    mean 2.68    var 9.17    var/mean 3.43
```

Heavily **over**-dispersed, not under — comfortably inside the family. The reasoning that produced
the opposite conclusion was built on the broken comparison above.

**What was actually wrong was one constant.** `var/mean = 1 + mu/r`, so a var/mean of 3.4 at mu 2.7
implies an `r` near 1. The market shipped with `r = 5.0`, guessed by analogy with shots, which made
every saves forecast too sharp. A sweep over three independent simulated leagues:

```
     r   mean z   worst calibration gap   lines in band
   0.8     4.64         20.3%                 50%
   1.2     4.63         14.7%                 65%
   1.8     4.61          9.3%                 74%
   2.5     4.59          8.0%                 78%     <-- shipped
   3.5     4.56         12.0%                 81%
   5.0     4.53         14.7%                 85%     <-- was shipped
   8.0     4.48         14.7%                 86%
```

A clean minimum at **2.5**: the gap halves, the likelihood gain is unchanged, and 78% of rungs still
clear the standard band. That is the value in `DEFAULT_R_PLAYER` and in the registry.

**The reason it validated and still did nothing live.** `engine_newmarket.py` builds a
`SoccerEngine` directly, so it kept the code default. Production goes through
`engine_bridge.configure_engine`, which read the dispersion straight out of the settings row:

```python
eng.r_player = dict(S.get(db, "engine.r_player"))     # replaced the dict wholesale
```

A settings row only holds the markets that existed when it was written. `saves` was added later and
was in neither the registry default nor any stored row, so `r_player` had no `saves` key and the
first saves line raised `KeyError('saves')` deep in the line-drawing loop. The market was
configured and fatal — the one state it should never be able to reach. It now merges over the code
defaults, so a row can override a market's dispersion but can never delete one, and
`selftest_new_markets` checks both the registry coverage and the stale-row case.

## The second guard: the team layer had none

Turning the markets on by default found a second way the chain could be configured-and-fatal, in
the same shape as the first and one layer up.

`extra_stats` appends a **(for, against) column pair** to `sum_cols` and records the offsets that
pair landed at in `team_dims`. `_snapshots` then indexes the whole team frame by `sum_cols`:

```python
X = g[self.sum_cols].values.astype(float)
# KeyError: "['fouls_committed', 'fouls_committed_against'] not in index"
```

So a team frame that does not carry a market's columns raised in `_snapshots` — before a single
forecast was attempted, and taking the three working markets down with it. The player list has had
a guard at the top of `fit()` since the first wall; the team list had none, and nothing noticed
because the markets shipped **off**, which left `extra_stats` empty on every run.

The guard now sits immediately above the player one, and has to run first, since the player check
tests `c in self.stats`:

```python
keep = [s for s in self.extra
        if s in STATS or (s in tg.columns and (s + "_against") in tg.columns)]
if list(keep) != list(self.extra):
    self._set_extra(keep)
```

`_set_extra` rebuilds `sum_cols` **and** `team_dims` together from the kept list. That matters: the
pairs are positional, so removing a market from one of them alone leaves every later market's
recorded offsets pointing at the wrong column — a silent wrong number rather than a crash, which is
the worse failure. `selftest_new_markets` now checks both that a frame missing one market's columns
loses only that market, and that every surviving offset still points inside `sum_cols`.

The rule both guards share: a market is **off**, or **published**. It is never configured and fatal,
and a league missing a source column loses the market rather than the run.

## Fouls is the weak one, and the number I first gave was too kind

Re-measured across two league sizes and three seeds each, after the keeper work landed:

```
                 n     gain      se      z
 14 teams  s=3  2772  0.0165  0.0064   2.59  PASSES
 14 teams  s=5  2772  0.0417  0.0173   2.41  PASSES
 14 teams  s=7  2772  0.0213  0.0079   2.69  PASSES
 20 teams  s=3  5720  0.0086  0.0071   1.20  does not pass
 20 teams  s=5  5720  0.0018  0.0034   0.54  does not pass
 20 teams  s=7  5720  0.0192  0.0062   3.07  PASSES
```

Four of six clear the gate. **I earlier reported fouls at gain 0.0814, z 2.87 — that figure is
superseded.** It was one run on one league before keepers existed in the simulator, and it was
roughly four times the gain any later run reproduces.

The honest reading is about size, not significance. Involvements gain **0.118** and saves **0.199**
per appearance; fouls gains **0.002 to 0.042**. Whether that scrapes past two standard errors
depends on the league. So the engine's foul forecast is *barely* better than restating the player's
own foul rate per 90 — which is the thing `engine_newmarket.py`'s first rule exists to catch:

> If the engine cannot beat "use his historical rate", the market is an expensive way to restate a
> mean and should not ship.

That is not surprising for this market. Fouling is mostly a stable trait of a player; there is
little match-to-match signal for a model to add beyond his own average, and most of what the engine
contributes is opponent and game-script. Fouls is also well calibrated (worst gap 13%) and 80% of
its rungs clear the standard band, so the lines it publishes are *true* — they are simply not
telling a reader much they could not get from the player's season average.

**Recommendation: leave fouls off until `engine_ab.py` has run on the real database.** It ships on
with the others because that is what was asked for, and it is one key to turn off:
`engine.player_ladder`, drop the `fouls_committed` entry. Real football may well give this market
more to work with than simulated football does.

## Switching them on

**Nothing to paste.** All three markets ship **on** as registry defaults, so a fresh install and any
key you have never saved picks them up on the next engine run:

```json
// engine.player_ladder
{ "shots": [0.5,1.5,2.5,3.5,4.5,5.5], "sot": [0.5,1.5,2.5,3.5],
  "tackles": [1.5,2.5,3.5,4.5,5.5], "fouls_committed": [0.5,1.5,2.5],
  "goal_involvements": [0.5], "saves": [1.5,2.5,3.5,4.5] }

// engine.line_band_by_stat   — required for involvements, not for fouls or saves
{ "goal_involvements": [0.25, 0.985] }

// engine.r_player
{ "shots": 6.0, "sot": 5.0, "tackles": 10.0,
  "fouls_committed": 6.0, "goal_involvements": 3.0, "saves": 2.5 }
```

A **saved row overrides the default**, so any of these keys already edited by hand keeps its stored
value. The admin settings screen marks each key `is_default`; `S.reset(db, key)` puts one back.

Saves starts at 2+ rather than 0.5 because a keeper making no save is the unusual match, so "1+
save" is a near-certainty that says nothing. Involvements need the 0.25 floor because even the best
forwards sit near 40% for a goal or an assist, and under the standard 0.5 floor every rung is
dropped and the market ships as nothing. That override is a **product** decision as much as an
engine one: a 42% line published beside a 94% line changes what "likely" means across the screens.

Team totals need no provider call — `build_frames` derives all three from rows the database already
holds (`fouls_committed` *is* the stored `fouls`; saves and involvements are sums over the side's
player rows). A market with no data is dropped for that league rather than guessed at.

**Still simulated football.** Every number above says the machinery works and the market can clear a
band. What these markets are worth on real leagues needs `engine_ab.py` on the real database, and
`engine.fit_player_r` is the right way to replace the three dispersions with fitted ones once it
clears — the docs/37 convention holds.
