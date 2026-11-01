# 38. Live events, forecasts ticking green, and three screen changes

Written 2026-11-01. Answers two questions about live data and records three design changes.

## 1. Why the match page was missing live events

Three causes, in the order they bite.

**a) Only the exact word `LIVE` counted as a match being on.** `sportapi.py` had `LIVE = "LIVE"` and refreshed events
only for fixtures whose status matched it exactly. Every other in-play state — half-time, extra time, a break,
penalties, "1H"/"2H"/"Second Half", or any word we have not seen — fell outside it. So events stopped refreshing at
half-time and through extra time, and a card shown in those periods arrived late or not at all. The provider's exact
words are **not verified** (docs/08, docs/23), so a single hard-coded word was always a guess.

**Fixed.** A match is now "on" for anything that is not scheduled, finished or called off:

```python
NOT_PLAYING = {"Scheduled", "TBD", "Abandoned", "Awarded", "WO", "Walkover", None, ""} | FINAL | DEAD
def in_play(status) -> bool: return status not in NOT_PLAYING
```

Unknown words count as on, which is the safe direction: at worst one extra call, never a missing card. The same rule
now decides the fast scoreboard window.

**b) Events refreshed only every 10 minutes.** `sportapi.events_refresh_s` defaults to 600, doubled to 20 minutes
when the daily call budget is tight. A card in the 20th minute could first appear in the 30th. Events are also
fetched at once on any goal or status change, which is why goals feel quicker than cards.

**Not changed by this work.** Lowering it costs calls: one live match for two hours is 12 calls at 600 s and 24 at
300 s. With `sportapi.daily_calls` at 1800 and a handful of simultaneous matches, 300 is affordable. **Owner
decision**: set `sportapi.events_refresh_s` to 300 if cards arriving within five minutes matters more than the
budget headroom.

**c) We mirror the provider's list exactly.** `store_events` deletes the fixture's events and re-inserts whatever
the provider returned, because that answer is meant to be the complete list each time. If the provider's in-play
list is partial, ours is partial too. Nothing we can fix from here; it shows up as events appearing late and then
filling in.

### How to tell which of these is biting you

Every status word the provider actually sends is now counted in `sportapi_state` under `status_seen`. After a
match day:

```
db.sportapi_state.findOne({_id: "live"}).status_seen
```

If words appear there that are really in-play but sit in `NOT_PLAYING` (an abandoned-then-resumed match, say), move
them. If the only words are `Scheduled`, `LIVE` and `FT`, cause (a) never applied to you and the lag is cause (b).

Also useful: `live_fixtures.events_at` is when each fixture's events were last pulled, and `events_n` how many were
stored.

## 2. Forecasts ticking green as they happen

Most of this already existed (docs/31): `live_track.evaluate` compares the live count with each line and returns
`hit`, `live`, `missed` or `unknown`, the match page reads it from `GET /api/matches/{id}/live-forecasts`, and the
card shows a "Happened" chip. What was missing:

- **The tick was easy to miss.** The first HIG pass removed card borders, and the hit state had been carried by a
  green border. A card whose line has happened now gets a **green outline and a green bar**, with the check in the
  chip. (`frontend/src/styles/hig.css`)
- **Only yellow cards can tick today.** Cards come from match events, which we always fetch. Shots, shots on
  target, tackles and corners come from the provider's **statistics** endpoint, and that is off:
  `sportapi.live_stats` defaults to false because its field names are unverified (`sportapi.stats_keys`).

**So, to get shot and tackle lines ticking green you need to:**

1. Turn on `sportapi.live_stats`.
2. Check `sportapi.stats_keys` against a real answer: the engine looks for its own names (`shots`, `sot`,
   `corners`, `tackles`) among the provider's. A wrong map means the count stays `unknown`, and the page shows **no
   tick rather than a false one**, which is the intended behaviour.
3. Watch the budget: statistics add one call per live match per `sportapi.stats_refresh_s` (180 s).

Until then, a shot line simply shows no tick while the match is on. That is honest, not broken.

## 3. Three screen changes

| Screen | Change |
|---|---|
| **Today and Insights** — the date strip | Each day now shows the crests of the leagues playing that day, up to three, then `+N`. `GET /api/match-days` returns `leagues` per day (name, crest, how many matches), counted once per match even when both our own row and a SportAPI row exist. The day's accessible name starts with the visible text and then lists the leagues, which also fixes the label-in-name problem from docs/36 A11Y-4. |
| **Player page** — the game strip | The plain bars are gone. Each game is now a column: **minutes played on top**, the count in the middle, and **the opponent's crest below**, so "4 shots" reads as "4 shots, 65 minutes, against them". A column is filled when the line was reached and outlined when there is no figure, so a missing number never looks like a zero (docs/03 §4.6). Screen readers get the full sentence per game. |
| **Live cards** | The green outline and bar described above. |

## 4. Files

| File | Change |
|---|---|
| `backend/sportapi.py` | `in_play()` and `NOT_PLAYING`; events, the hot window and the scoreboard interval all use it; every status word the provider sends is counted in `sportapi_state.status_seen`. |
| `backend/queries.py` | `match_days` returns the leagues playing each day as well as the days. |
| `backend/routes_data.py` | Passes that through. |
| `frontend/src/lib/prefs.js` | `useDayLeagues`. |
| `frontend/src/components/ui/DateScroller.jsx` | League crests under each day; a better accessible name. |
| `frontend/src/pages/Today.jsx`, `pages/Insights.jsx` | Pass the leagues in. |
| `frontend/src/pages/Player.jsx` | The new game strip. |
| `frontend/src/styles/hig.css` | Styles for the strip, the day crests and the live hit state. |
| `backend/tests/selftest_livetrack.py` | Every in-play word counts as on; events refresh at half-time and in extra time; a finished match is not polled again; the provider's words are counted. |
| `backend/tests/selftest_overlay.py` | `match_days` names the leagues and counts each match once. |

## 5. Still open

- `sportapi.events_refresh_s` is still 600. Lower it to 300 if you want cards within five minutes (section 1b).
- `sportapi.live_stats` is still off, so only card lines tick green (section 2).
- Neither the provider's status words nor its statistics field names have been verified against a real answer. The
  `status_seen` counter now gives you the first; `sportapi.stats_keys` still needs the second.
