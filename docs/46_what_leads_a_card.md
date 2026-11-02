# 46. Showing the forecasts people actually care about

Written 2026-11-02. Reported: *"mbappe one shot or benfica 7 shots are not that much great insights those are
almost given … how can we show the forecats that users actually care. also putting players all forecatss under one
card may not be a good idea as they hide those from the filter."*

Both halves were the same bug.

## The cause

`group_cards` picked the line that leads a card by **raw likelihood**. Since docs/44 made `select_lines` keep the
likeliest lines, that is always the dullest line a player owns:

```
LEAD TODAY  : 1+ shot            95%   usually 93%   lift  +2%
BIGGEST LIFT: 2+ shots on target 49%   usually 28%   lift +21%   <- never seen
```

A card then **inherits the lead line's** `stat`, `tier`, `p` and `edge`. So:

- `engine.feed_sort` defaults to `edge` — *"most different from the player's or team's usual"* — and it was
  ranking this whole card by **+2%**. The feature that was supposed to surface news was being fed the one number
  guaranteed not to be news.
- Every filter judged the player by that line too, which is the second half of the report. A card is one object;
  if its identity is its least interesting line, the player is effectively hidden behind it.

`queries.py` already contained an unused `lead_stat()` that picked by lift, so this was always the intent.

## What leads a card now

A score, in `queries.prominence()`, of three things **multiplied**, so a line has to have all three:

```
score = importance(market) × lift over usual × likelihood
```

- **importance** — `engine.market_weights`, the owner's own order from docs/39 as numbers he can tune:
  for players on target 1.40, tackles 1.30, passes 1.25, fouls won 1.20, fouls 1.15 … shots 1.00;
  for teams goals 1.40, cards 1.30, corners 1.25, on target 1.20, shots 1.10. Anything unlisted counts as 1.0.
- **lift over usual** — `p − p_usual`, floored at zero. A line exactly as usual scores **nothing**, which is what
  retires "1+ shot, usually 93%" and "7+ shots, usually 96%" from the headline.
- **likelihood** — an unusual line nobody can act on is not an insight either, so a 20%-that-is-usually-5% does
  not outrank a 49%-that-is-usually-28%.

When **no** line in a card has any lift, the likeliest leads, exactly as before. The `feed_max_p` rule from
docs/25 is untouched: a line above it never leads while another line can.

| | before | after |
|---|---|---|
| Mbappé, shots | 1+ shot 95% (usually 93%) | **3+ shots 58%** (usually 38%) |
| Mbappé, on target | *hidden inside the card* | **2+ on target 49%** (usually 28%) |
| Benfica | 7+ shots 97% (usually 96%) | **13+ shots 44%** (usually 26%) |

## One card per market, and a pager

`engine.feed_group` replaces the old on/off `engine.feed_one_per_player` with three choices:

- **`player_market`** (new default) — one card per player or team **per market**, so a good shots line and a good
  on-target line both surface instead of competing for one slot.
- `player` — one card for everything that player has, the old behaviour.
- `line` — no grouping at all.

The match page and the player page stay on `player`: there you are looking at a squad, not a feed. They use the
same lead rule, so the line that leads is consistent everywhere.

**Filters can now see past the lead.** Every card carries `best_p`, the best percentage anywhere in it, and
*"at least N% likely"* asks about that. Otherwise a card led by a 49% insight would vanish under a 90% filter
while holding a 95% line — the exact complaint, moved rather than fixed.

**Pagination.** One card per market means more cards, so the Insights list is paged, with a per-page control
(10 / 25 / 50 / 100, remembered) and a count. It pages the rows the server already sent, which is the plan's
insight allowance — so this is paging within your allowance, not a way around it.

## Files

| File | Change |
|---|---|
| `backend/queries.py` | `prominence()`; `group_cards` takes a grouping and the weights and leads by score; `best_p` on every card; `insights_feed` reads `engine.feed_group`; the match and player pages use the same lead rule. |
| `backend/settings_registry.json` | `engine.market_weights`, `engine.feed_group`; `engine.feed_one_per_player` removed. |
| `frontend/src/pages/Insights.jsx` | The likelihood filter reads `best_p`; pager with a per-page control. |
| `frontend/src/styles/hig.css` | The pager. |
| `backend/tests/selftest_prominence.py` | New: both reported examples, the three terms, ties, the no-lift fallback, the three groupings, the `feed_max_p` rule. |
| `backend/tests/selftest_lines.py`, `selftest_calibration.py` | Two assertions encoded the old lead rule and the old on/off grouping; rewritten to the new ones. |

## Open

- **The weights are a first guess at the owner's stated order, not a measured one.** Nothing yet checks whether a
  market people actually open and follow matches its weight. Once there are enough follows and combo adds per
  market, they could be fitted instead of set by hand — the same walk-forward discipline docs/37 uses for the
  engine.
- `passes`, `fouls_won` and `fouls` carry weights but **no forecasts exist for them yet**: those provider keys are
  still unmapped (docs/08). The weights are ready for when they are.
- Paging stops at the plan's insight allowance, because that is what the server sends. Deeper paging would need
  the feed to page server-side, which also means deciding what a free plan may page through.
