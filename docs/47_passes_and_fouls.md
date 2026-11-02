# 47. Passes and fouls: PitchAPI already has them

Written 2026-11-02. Context: docs/46 gave `passes`, `fouls_won` and `fouls` weights in the market importance
table, and I noted they produce nothing because the provider keys are unmapped. The owner first offered SportAPI's
`/api/players/stats`, then PitchAPI's own player-stats documentation.

**The second one settles it, and the first proposal was wrong.** PitchAPI's stat line carries everything needed:

| Group | Appears on | Holds (abridged) |
|---|---|---|
| `top_stats` | everyone who featured | rating, **minutes**, goals, assists, xG, xA |
| `attack` | outfielders | touches, dribbles, crosses, **passes**, non-penalty xG |
| `defense` | outfielders | clearances, interceptions, recoveries, **tackles**, blocks |
| `duels` | outfielders | aerial and ground duels, **fouls committed**, **fouls won** |

So there was never a missing data source. There was a **missing mapping**: `provider.pitchapi.player_keys` ships
with `minutes`, `tackles`, `fouls_committed` and `fouls_won` all set to `key: null`, and `passes` absent entirely.

## Why not SportAPI

I had proposed `/api/players/stats` and costed it. It was the wrong answer on four counts, recorded so nobody
re-proposes it:

- It carries **no fouls won, no fouls committed, no shots on target and no cards** — it would have unblocked one
  of the three markets, not all of them.
- It is keyed by **player name plus team id**, with no stable identifier, so every row would depend on name
  matching. PitchAPI rows carry `player.id`.
- It costs **one call per player** — roughly 70 a day per league against an 1800 cap — where PitchAPI's player
  stats arrive inside match answers we already fetch **and cache**. The real cost is zero extra calls.
- It would have broken the split the owner set in docs/42: PitchAPI backfills, SportAPI is live.

## What changed here

Small, and deliberately short of the market itself:

- **`passes` is now a column** in `normalize.PLAYER_COLS`, so it flows into `player_match_stats` like any other,
  and a registry entry (`group: attack`, `key: null`, `use: value`) gives the mapping screen somewhere to put it.
  `use` picks which half of a made/attempted pair: `value` = completed, `total` = attempted.
- **Coverage reports `passes`, `fouls_won` and `fouls_committed`**, so `PitchAPI → Quality and mapping` shows them
  filling up rather than staying invisible. Nothing is gated on them: markets gate on `MARKET_COVERAGE`, which
  these are not in.
- **The fake provider emits `attack` and `duels` groups** in the documented shapes — a `fractionWithPercentage`
  pair for passes, plain counts for fouls — so the pipeline is exercised. Those numbers are invented from minutes
  and position; they are there to test shapes, not to be realistic football.

Verified end to end on the fake: 2021 player rows, `passes` present on 100% of them in the range 4–71, both fouls
columns likewise.

## What the owner has to do, and what is still missing

**This ships no new market.** It makes the data reachable; the markets need history that does not exist yet.

1. **Map the keys.** `Admin → Football data → PitchAPI → Quality and mapping` reads a real saved answer and lists
   every key it finds, by group. `minutes`, `tackles`, `fouls_committed`, `fouls_won` and `passes` are waiting
   there. This is the step nothing else can do for you: only a real answer shows the exact key strings, and the
   documentation is explicit that the display label is not stable.
2. **Backfill**, so the columns have history rather than only new matches.
3. **Then the markets.** `passes` and `fouls` are not in the engine: `PLAYER_STATS` is still `shots, sot,
   tackles`. Each needs its own ladder (passes sit at 20.5/30.5/40.5, not 0.5/1.5/2.5), its own negative-binomial
   dispersion and prior — the shots constants are meaningless at 30–60 a match — a team total for the share
   model, and the docs/37 walk-forward gate before it ships. That work is pointless before step 2 produces
   something to fit on.

## Files

| File | Change |
|---|---|
| `backend/normalize.py` | `passes` in `PLAYER_COLS`. |
| `backend/settings_registry.json` | `passes` in the player key map; the help says where the keys live and what `use` does. |
| `backend/ingest.py` | Coverage reports passes and both fouls columns. |
| `backend/tests/fake_pitchapi.py` | Emits `attack` and `duels` in the documented shapes. |
