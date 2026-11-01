# 42. One rule for "is this match being played"

Written 2026-11-01. The owner asked for every SportAPI call to be consistent, after two symptoms: **live events were
not all pulling**, and **forecasts did not turn green as they happened**. The split of duties is unchanged and is
worth restating, because everything below only concerns the second half of it:

- **PitchAPI** — backfill, history, depth analytics. Everything the forecast is built from.
- **SportAPI** — every live call: the score, the minute, the events that feed the cards, lineups, final scores.

## The cause

SportAPI's status vocabulary is not documented for us (docs/08, docs/23): we see the words it sends, we were never
given the list. The code nevertheless named them one by one, in five different places, each with its own idea of
which words meant "on":

```python
LIVE = "LIVE"
...
hot = [f for f in tracked_today if f["status"] == LIVE or ...]          # which matches to poll this minute
PHASE = {"Scheduled": "scheduled", LIVE: "live", "FT": "final", ...}    # phase_of, used by every screen
phase = PHASE.get(f.get("status"))                                      # "HT" -> None
if lf.get("status") in (None, "Scheduled", "Postponed", "Cancelled"):   # live_track.evaluate
```

So for the whole of **half time**, **extra time**, the **break before extra time** and **penalties being taken** —
and for any word we have never seen — the match was not "on":

- it was dropped from the hot list, so its **events stopped being refreshed**; a card shown in the 46th minute
  arrived late or not at all;
- `phase_of` returned `None`, so it **stopped looking live** on Today, the scoreboard and the match page;
- `live_track.evaluate` ran but treated it as active-and-not-final for *unknown* words and as inactive for the four
  it knew, so **no line could tick** at half time.

A single match sends several of these words in a normal 90 minutes, which is why the symptom looked intermittent.

## The rule

One vocabulary, in `sportapi.py`, grouped by what the word *means*:

| Set | Words |
|---|---|
| `FINAL` | FT, AET, PENS, PEN, AP, Full Time, After Extra Time, After Penalties, Match Finished |
| `DEAD` | Postponed, PST, Cancelled, Canceled, CANC, Abandoned, ABD, Awarded, AWD, WO, Walkover, Technical Loss |
| `NOT_YET` | Scheduled, NS, Not Started, TBD, TBA, Time to be defined, Delayed, Deferred |

and three functions every caller now shares:

```python
in_play(status)   # being played: anything that is in none of the three sets
is_final(status)  # over, with a result
is_over(status)   # finished, or called off and not coming back
```

**An unknown word counts as being played.** That is the deliberate half of the trade. A word we have never seen is
far more likely to be a period of football than a new way of saying "postponed", and the two mistakes are not
equally bad: treating a live match as not-live loses events and ticks for real users, while treating a dead match as
live costs a few polls and shows "Live" on a match nobody is watching. To keep that cost small, the three sets above
list every spelling we have seen or can expect, including the short codes, and **matching ignores case, spaces and
punctuation** — `FT`, `ft`, `Full Time` and `full_time` are one word.

What this cannot do is invent a phase for a word that is genuinely new. `Admin → SportAPI` records every status word
the provider actually sends (`status_seen`), so the list can be checked against reality rather than against a guess.

## The browser was doing it too, and that was the bigger half

Eight places in the front end tested the provider's word for themselves:

```jsx
if (m.live && m.live.status === "LIVE") return "live";               // MatchCentre.matchState
{ every: d.match.live?.status === "LIVE" ? 30000 : 0 }              // whether to ask what has happened
const live = all.filter((f) => f.status === "LIVE");                 // the Live sheet
const done = all.filter((f) => !["LIVE", "Scheduled"].includes(f.status));
```

So even with the server right, at half time the live dot went out, the score and minute stopped refreshing, the Live
sheet filed the match under **Finished**, and — the one the owner reported — the match page **stopped asking which
forecasts had happened**, because the 30-second poll of `live-forecasts` was switched off. Lines could not turn green
during the interval, in extra time, or while penalties were being taken.

The browser should never have held that vocabulary, because it is the provider's and it is not fixed. The server now
sends the answer and the browser reads it:

| Sent on | Field | Meaning |
|---|---|---|
| a fixture (`public_fixture`) | `state` | `live` · `later` · `done` |
| a fixture | `live` | being played |
| a match row (`overlay`) | `live.playing`, `live.state`, `phase` | the same answer for the match screens |

`frontend/src/lib/live.js` holds the four readers every screen now uses — `fxState`, `fxLive`, `fxStarted`, `mLive`
— each falling back to the old `=== "LIVE"` test only for a payload cached before those fields existed. `atHalfTime`
also stops the chip from reading "Live" with no minute when the provider puts half time in the status rather than
the minute.

## Where the pages get their words

`status_text()` turns a status into something to read. A word we know keeps its wording ("Full time", "Not started");
an in-play word we do not know reads **"Live"**, never the raw code; a not-playing word we do not know is shown as it
came. `phase_of()` is the same idea for layout: anything in play is `live`.

## Fixtures that reach no page

While checking the calls, a second and quieter failure showed up: a fixture SportAPI follows is only of any use once
it is tied to one of our own matches (`live_fixtures.match_iid`). An unlinked fixture is polled and paid for, but it
reaches no screen — no live score, no events, no ticking forecast. The clubs can all be matched and the fixture still
miss, when the kick-off moved or we never held that match at all.

Nothing surfaced this, so there was no way to answer the owner's question *"where do I check SportAPI calls matched
or not"*. `fixture_links()` now reports it for the week either side of now, and `Admin → Integrations → SportAPI`
shows it as its own card: followed, matched, unmatched, and **unmatched while being played** — the one that means
live data is being lost right now — with the unmatched fixtures listed and whether their clubs are known, which says
whether the fix is a club to match in Team review or a match we simply do not carry.

## Files

| File | Change |
|---|---|
| `backend/sportapi.py` | `FINAL`/`DEAD`/`NOT_YET` by meaning; `in_play`, `is_final`, `is_over` matching on a canonical spelling; `phase_of` and `status_text` fall back to live for an unknown in-play word; `scoreboard`, `status`, `overlay`, the hot list, the final sweep and the backfill's "complete" all go through them; `fixture_links`, also in `status()`. |
| `backend/live_track.py` | Shares `in_play`/`is_final` instead of naming four words, so a line ticks at half time and in extra time. |
| `frontend/src/lib/live.js` | New. The four readers every screen uses, so the provider's vocabulary lives on the server only. |
| `frontend/src/components/LiveStatus.jsx`, `LiveSheet.jsx`, `MatchCentre.jsx`, `ui/LiveBits.jsx`, `pages/Live.jsx`, `pages/Today.jsx`, `pages/Match.jsx` | All eight `=== "LIVE"` tests replaced, including the one that switched off the live-forecast poll. |
| `backend/queries.py` | The date strip excludes every spelling of a called-off fixture, not two of them. |
| `frontend/src/admin/SportAPI.jsx` | New "Fixtures matched to our matches" card: the four counts, the unmatched fixtures, and the status words the provider really sends. |
| `backend/tests/selftest_live_status.py` | New. Every in-play and not-playing word; spelling ignored; `phase_of`/`status_text` never leave a live match without a phase or print a raw code; scoreboard, admin count and `live_track` agree at half time and in extra time; the `state`/`live`/`playing` the browser is sent for each period; `fixture_links` counts and lists the right fixtures. |

## Open

- `sportapi.events_refresh_s` is still 600 s. At half time this fix makes the refresh happen at all; 300 s would
  halve how late a card appears, at twice the calls for the events kind. The owner's call.
- `status_seen` is worth a look after a full matchday: any word in it that is not in one of the three sets above is
  being treated as live. That is the intended default, but if it turns out to be a "not started" spelling, it belongs
  in `NOT_YET`.
