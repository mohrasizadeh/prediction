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

## Switching them on

Run the backfill once — `POST /api/admin/ingest/team-totals/backfill?dry_run=false`. It calls the
provider **zero** times: both totals are sums over player rows the database already holds. A
team-match whose source column was never ingested is left empty rather than filled with a 0, because
a 0 there would claim nobody in the league ever committed a foul.

Then:

```json
// engine.player_ladder   (auto_lines is true by default, so this is the live one)
{ "shots": [0.5,1.5,2.5,3.5,4.5,5.5], "sot": [0.5,1.5,2.5,3.5],
  "tackles": [1.5,2.5,3.5,4.5,5.5], "fouls_committed": [0.5,1.5,2.5] }
```

```json
// engine.line_band_by_stat   — required for involvements, not for fouls
{ "goal_involvements": [0.30, 0.985] }
```

Fouls clear the standard band and need no override. Involvements do not, and the override is a
**product** decision as much as an engine one: a 42% line published beside a 94% line changes what
"likely" means across the screens, and the tiers and the record are calibrated around the current
floor. Both go through `engine_ab.py` before a default moves — the docs/37 convention holds.
