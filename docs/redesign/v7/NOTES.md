# v7 — read against StatsHub, and what we did about it

Their three tools (Player Trends, Prop Screener, Prop Hunter) were studied from screenshots at
pixel level, and five agents audited our side in parallel. This file records the mechanism
difference, what we took, what we refused, and the two things I got wrong on the first pass.

---

## 1. How they choose the line, and how we do

They **mine the longest current streak**. The filters are "min games in streak" and "min hit rate",
so for every player they search across every market × every line × every window length and surface
the combination that produces the most impressive true statement. The evidence is in the cards:
one says `15/15`, another `12/12`, another `8/8` — and on the 8/8 card the strip draws **ten**
columns with the oldest two red and dimmed, showing where the streak broke. The record is not a
fixed window; it *is* the streak.

So the headline is always flattering, by construction. 609 of them existed on the day of the
screenshot.

We rank by `prominence = market_weight × lift × stake`, where `lift` is how far this fixture moves
the line from the entity's own normal game, and `is_trivial()` demotes any line whose `span` is
under `engine.min_span`. **Those two functions exist to kill exactly the lines a streak miner
promotes.** The code's own measurement: Kane's *1+ shot* rung moves about 4 likelihood points
across the entire league; his *5+* rung moves 32.

Their mechanism selects for lines that say nothing about tonight. Ours selects for lines that do.
That is the product's argument and it is now stated on the card rather than buried in a ranking
function: the streak appears, second, under the forecast, and never chooses the line.

## 2. What we took

**The per-game context.** Their strip carries five things per column: competition, home/away, the
count, minutes **and the position he played that day**. We carried three. `pos` is on every
`player_match_stats` row, has been since ingest was written, and was drawn nowhere in the product —
and it is the biggest confounder in a tackles or shots run. It is drawn now, but only when it
**changed** across the ten; a column of ten identical "MID"s is noise, so the caption says "all at
MID" once instead. Venue was in `run` all along and sighted readers never saw it, because the one
text slot held the minutes; away games now carry an `@`.

Competition per game was the one item we could not take. `league_iid` is on both stat rows, but
every row we hold comes from a tracked league — there is no cup/league distinction to draw, so a
badge would be ten identical marks. Recorded rather than built.

**The record, at two windows.** "9 cleared 1+" now carries "4 in a row" and "19 of his last 20".
Same question, three windows, one line.

**Named starts.** Their screener opens with eight questions, each printing its own parameters, so
you learn the tool by reading it. Ours opened with "Pick a league first" and a counter of searches
remaining. Eight starts now, chips derived from the query so a card cannot drift from the search it
runs. The eighth is "What we rate highest" — our forecast, not a run, because that is the
difference.

## 3. What we refused

The price pill, the bookmaker dropdown, "Save pick" and the ⚡ score. `docs/03 §8` — *"Do not add
seller links, price columns, or 'value' labels"* — and `docs/36` records it as the main payment and
ad-platform risk. Their footer carries GamStop and GambleAware; that is the cost of the price
column.

And the **mechanism**, not only the vocabulary. 609 streaks at 100%, found by searching every
market × line × window, is survivorship bias with a UI. Adopting streak-as-headline would throw
away the one thing they structurally cannot copy: we said something beforehand, so it can come true
in front of a reader, and it can be scored afterwards.

## 4. What we found on our own side

The feed card carries **67 fields and drew about twelve**. Their card is a counting tool at full
volume; ours was a forecasting engine on mute. Specifics fixed this round:

- **Live tracking existed on one screen.** The chip that says "Happened" / "2 of 3 so far" was
  wired only on the match page, because the only route that answered it took one match id and a
  feed spans many. `GET /api/live-forecasts` evaluates every match in play or just finished.
- **`match_id` was never written onto a forecast**, so the Insights "Match page" link fell back to
  the internal iid and went nowhere. The cause was worse than the symptom: `insights_feed` had
  `_decorate`'s body copied inline, so the feed was the one caller that never saw a new field.
- **"6 of the last 10" was a ratio, not a count**, compared against however many rows survived the
  filters. Two hits in three games satisfied it. And because `min_minutes` and `started` remove
  rows from the window, asking for 60+ minutes made the denominator smaller and the search
  **looser** — measured on the demo league, a stricter filter returned **86 rows where no filter
  returned 75**. It is a count now: 75 / 75 / 76.
- **`min_minutes` and `started` were unreachable from any browser** — not hidden, never sent. They
  are one control now ("games of 60+ minutes", "games he started"), worded to finish the window
  phrase, because the filter changes which games are counted and that has to be legible.
- **"Our forecast" offered markets that do not exist** — Goals, Assists and Minutes for a player,
  Tackles for a club. Picking one returned "Nothing meets that line", which reads as "nobody
  qualifies". Choosing a stat we only count and switching to forecast mode silently swapped it for
  shots. `GET /api/forecast-markets` reports what we actually hold, read from the forecasts
  themselves so it cannot drift from a settings list, and an unanswerable choice now says so and
  offers the counting mode instead.
- **Ties sorted arbitrarily**, so identical searches returned a different hundred each time.

## 5. Two things I had wrong

`rec_k`/`rec_n` is the **player's** record over his last 40 appearances, not our forecast record. I
described it as ours. The sheet also called it "this season", which in October it is not; both read
"in his last N" now.

The Finder's quota countdown is **not** a bug. The quota is keyed on the UTC day
(`plans.py:172`) and the display converts that to local time correctly — a reader in UTC−8 really
does get their searches back at 16:00 local.

## 6. Not done, and what it would cost

**Engine market breadth.** They forecast ten player markets; we forecast four (shots, shots on
target, tackles, yellow cards). The data for fouls committed, fouls won, passes, goals and assists
is already ingested, and `engine.market_weights` already contains weights for markets that do not
exist — someone planned this. But the player layer models a stat as a **share of the team's total
of that stat**, and only `team_shots`, `team_sot` and `team_tackles` are denormalised onto the
player row. A fouls market needs a new team-level dimension in the engine (`SUM_COLS` and
`TEAM_DIMS` have no fouls), that denormalised column, a backfill of every historical row, a ladder,
labels, coverage gating, and a walk-forward measurement before it is switched on — which is this
project's own convention (`engine.personal_lines` is still off pending `engine_ab.py`). Goals and
assists are worse: low-count events where a negative binomial on past goals is the wrong model, and
`match_goals` already uses Dixon-Coles for that reason.

The gap is also smaller than it looks. Readers can **screen** on all fifteen player stats today —
fouls, passes, goals and assists all work in the counting modes — and **forecast** four. Ten-to-four
was never the comparison.

**Merging Insights and Finder.** Still the owner's call: it deletes a route and moves entitlements
attached to Finder's query powers.

**Finder performance.** Every form/run search is a full collection scan plus roughly 200–300 serial
lookups, and `player_match_stats` has no `league_iid` index. No new filter should be added there
until that is done.
