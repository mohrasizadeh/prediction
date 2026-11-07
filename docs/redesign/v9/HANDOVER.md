# Handover — v8 / v9 round

Baseline: `7466057`. Everything after it is this round. All ten commits are on `main` and pushed.
48 files, +1743 / -228. Verified at every commit: **42/42 self-tests, `npm run build`,
`npm run check-copy`**.

## Deploy in this order

They are already in dependency order on `main`, so a normal deploy of `main` is correct. The list
is here so a reviewer can read them one at a time.

| # | Commit | What it is | Needs |
|---|---|---|---|
| 1 | `975b54d` | **Forest palette.** The owner's seven colours replace Carbon as the default, both modes, every pair contrast-measured. | — |
| 2 | `6275142` | **The sheet answers the line you tapped.** Live line/filter selection; new `frontend/src/lib/lines.js`. | — |
| 3 | `c581492` | **Market choice.** New setting `engine.position_weights`; direction-aware reasons; `match_goals` finally has reasons. | setting |
| 4 | `c041f7c` | **Day strip on one row.** 230px → 74px; first card y=382 → 226. | — |
| 5 | `64ae6cd` | **The reference pass.** Palette gains `accent` / `onAccent` (**23 → 25 colour tokens**), the `<Hl>` highlighter, tabs on a rule, fitted segments, cards sharing a height, the spacing rhythm. `v2.css` §31–32. | **token count** |
| 6 | `f73a8b7` | **The language reaches every screen**, and the **feed stops contradicting the card** (`FEED_SORTS["edge"]` now ranks by `prominence`). Also cuts the circular `rec_k/rec_n` chip. | — |
| 7 | `1ceb77f` | **The two disappearances.** Ladder *carriers* for empty Finder cells; the Insights cap moved off the filtering pool. | see note |
| 8 | `bf1d9ed` | **Goals/assists zero-fill.** `normalize.py`, a guarded backfill, and the simulator work that makes it testable. | **backfill** |
| 9 | `5f26652` | **The owner's reference, as drawn.** Forest band, the ten-game chart, the chosen-line treatment. | — |
| 10 | `51dd4e1` | **Track record leads on the high band**; one chip and one tab row everywhere. New setting `engine.record_high_p`. | setting |

## The one required operational step

`bf1d9ed` fixes the zero-fill **going forward**. History ingested before it still holds
`goals: null` on goalless appearances. Run the backfill once per environment:

```
POST /ingest/goals/backfill            # dry run by default, writes nothing
POST /ingest/goals/backfill?dry_run=false
```

**Read `ok` before trusting the counts.** It is `false` when the provider does not map `goals`
(every row is null, and filling zeros would record that nobody in the league has ever scored) or
when nothing in scope records a goal at all. Both refusals are deliberate; neither is a transient
error to retry past.

Until it has run, any per-90 goal rate divides a player's goals by *the games he scored in*.
Measured on the demo league: **0.10 goals per appearance, or 1.16 if the goalless rows are still
null** — an 11× overstatement that reads as a believable striker rather than a broken number.

## Settings a deploy introduces

Three, all with registry defaults, so a deploy needs no manual configuration:

- `engine.position_weights` — how relevant each market is to each position.
- `engine.record_high_p` — `0.80`, range-guarded `0.6–0.99`. Where the Track record's headline
  band starts.
- Palette: `accent` / `onAccent` join the theme tokens. **Any stored custom theme will fail
  validation until it carries all 25.** The ten shipped presets already do.

## Notes for whoever picks this up

**Ladder carriers (`1ceb77f`).** `select_lines` now leaves one row behind when a whole
player-market falls below `engine.line_band`, so the Finder can still answer lines the band
dropped. Carriers are not published forecasts: the exclusion lives in `queries.NOT_HIDDEN` — the
constant every display query spreads — and separately in `score_finished`, `live_track` and
`cards_model`. **If you write a new query against `forecasts`, spread `NOT_HIDDEN` or you will
show rows the engine chose not to publish.** `ANY_STORED` is the opt-in for ladder lookups.

**Track record (`51dd4e1`).** The page leads on the high band, not the mean, because a mean over
every band can be right while every band inside it is wrong. `selftest_queries.py` builds exactly
that case — 300 lines at 20% that happened 40%, 300 at 90% that happened 70% — and asserts the
aggregate reads "said 55%, happened 55%" while the band says "said 90%, happened 70%". Do not
"simplify" the page back to the aggregate.

**`.k-sec` is a caption class, not a heading class.** A section heading is `.k-sec v2-sec` inside
a `.v2-sec-head`. Putting a bare `.k-sec` on an `<h2>` renders it at 13px — that collision is why
fourteen of fifteen screens had no section head before `f73a8b7`.

**The accent is rationed.** Mint is a fill carrying dark ink, spent on at most two marks per
screen. It is deliberately not on the Solid tier, "Confirmed starter", or a departure under 8
points: those sit on most cards, and filling them made twenty mint pills on one Insights screen.

**The banned-word list is enforced in CI** (`frontend/scripts/check-copy.js`). No price or odds
data appears anywhere, deliberately — it is what keeps "statistical analysis, not betting advice"
true rather than claimed.

## Not done, deliberately

- **The goals / goal-or-assist market.** `bf1d9ed` is the data gate only; the model is not built.
  Order when you take it: measure coverage after the backfill → the rate and the eligibility gate
  (player-level, with hysteresis, not per fixture) → a per-stat likelihood band, because a 1+ goal
  line is 10–35% and `engine.line_band` discards anything under 50% before storage → walk-forward
  validation before it goes live.
- **Team and match pages still use the card grid**, not the row treatment. That is the
  5,871px → ~2,500px change, specced but not built.
- **A Follow button on every Finder row** needs the shared-follow cache `SaveButton` already has,
  or 100 rows fire 100 requests.
- **`cards_model` enumerates players from surviving forecasts**, so a player dropped from
  shots/sot/tackles gets no yellow-card line either — worst for the defensive midfielders whose
  best market *is* the card one. Noted in the code at the call site.
