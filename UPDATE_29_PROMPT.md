# Prompt for Emergent: update 29 (what is worth showing), already built

Everything below is already in this repo (branch `main`). Pull it. Do not rebuild it.

Read in this order: `docs/50_what_is_worth_showing.md`, `docs/51_what_to_sell.md`,
`docs/52_a_line_for_each_player_and_team.md`, `docs/redesign/swiss/README.md`,
`docs/19_images_logos_photos.md` §11. Then paste the box below.

**The one thing to understand before you start.** The app was showing true statements nobody needed:
`PSG 9+ shots, 88%`. Every team clears that, so no engine is required and no reader learns anything.
Update 29 gives every player and every team **its own line** — the count it clears about half the
time — so the number on the card is a claim rather than a description. **It is off by default**
(`engine.personal_lines`), because it has not been judged on real data yet. Section 3 below is how
you look at it; section 6 is what has to happen before it goes on in public.

---

## 0. The whole change in one table

| Part | What the user gets | Backend | Frontend | Spec |
|---|---|---|---|---|
| A. A line for each player and team | Cards say "14+ shots, 63% — they usually manage 13.5" instead of "7+ shots, 89%". Forecasts of a **shortfall** appear for the first time | `soccer_brain/engine.py`, `engine_bridge.py`, `tiering.py`, `queries.py`, `server.py` | `ForecastCard.jsx` | docs/52 |
| B. Filter Insights by player and club | Two pickers on Insights, offering only what the feed holds | `queries.py`, `server.py` | `pages/Insights.jsx` | docs/52 §6 |
| C. PitchAPI provides every picture | League logos, club crests and player photos all from PitchAPI. API-Football no longer needed | `pitch_photos.py`, `ingest.py`, `match_extras.py` | `admin/Jobs.jsx` label | docs/19 §11 |
| D. Swiss design pass | Every screen reviewed; the forecast card's tier note readable; the win/draw/away bar passes contrast; the desktop rail's hanging border gone | — | `styles/swiss.css` (new, loaded last) | docs/redesign/swiss |
| E. Two bug fixes | The League page no longer crashes; the player insight sheet no longer hides three of its ten games | — | `pages/League.jsx`, `styles/swiss.css` | docs/redesign/swiss |
| F. Research | What to show, and what to sell | — | — | docs/50, docs/51 |

Tests: **42 self-test suites, all passing** (`cd backend && bash run_tests.sh`).
No class name was added, renamed or removed in part D, so Site Studio and the copy checker are
untouched.

---

> **Task: pull the latest `main` and check update 29. Do not rewrite or "simplify" any file listed below.**
>
> **Already built (read only):**
> - Engine: `backend/soccer_brain/engine.py` (`personal_k`, `personal_thrs`, the two new `Forecast`
>   fields), `backend/engine_bridge.py` (settings through to the engine, `is_personal`, the
>   personal rung leading `select_lines`), `backend/tiering.py` (`_departure_tier`,
>   `_lineup_caveat`), `backend/queries.py` (`lift` both ways, `prominence` stake term,
>   `group_cards` leading with the entity's own rung, the feed's player and club filters).
> - Pictures: `backend/pitch_photos.py`, the three task kinds in `backend/ingest.py`, the free
>   crests in `backend/match_extras.py`.
> - Screens: `frontend/src/pages/Insights.jsx` (the two pickers, the likelihood floor at 0),
>   `frontend/src/components/ui/ForecastCard.jsx` (the "usually manages" line),
>   `frontend/src/styles/swiss.css` (new, loaded last in `index.js`),
>   `frontend/src/pages/League.jsx` (the crash fix).
> - Tests: `backend/tests/selftest_personal_lines.py`, `backend/tests/selftest_pitch_images.py`.
>
> **Step 1.** Run `cd backend && bash run_tests.sh`. It must print **42 PASS lines**.
> Run `cd frontend && node scripts/check-copy.js`. It must pass. Show me both logs.
>
> **Step 2.** Admin → Football data → PitchAPI: map `minutes`, `tackles`, `fouls_committed`,
> `fouls_won` and `passes` under **Quality and mapping**. Then Admin → Jobs → run `images` once.
> Pictures now come from PitchAPI; the API-Football key is no longer needed by anything.
> Show me the Images panel with `from_pitchapi` above zero.
>
> **Step 3.** Leave `engine.personal_lines` **off**. Open Insights on a phone and on a computer and
> show me: the Player picker, the Club picker, a club chosen (the count must drop), and the full
> list again. Nothing else should look different from before.
>
> **Step 4.** On a **copy of the database, not production**, set `engine.personal_lines` to on and
> run `engine` for one league. Show me Insights again. Expect the median likelihood to fall by
> roughly half, no card at 85% or more, and most cards to read as a shortfall rather than a rise.
> Then set it back off. **Do not leave it on.** Section 6 of this prompt says why.
>
> **Step 5.** Tell me anything that does not match `docs/52` §3 and §9, or the before-and-after
> pictures in `docs/redesign/swiss/pairs/`. Fix only what I approve.
>
> **Rules:** never use a word from `docs/03` (`picks`, `hit rate`, `odds`, `stakes` and the rest);
> the only allowed use of "betting" is the footer sentence in `copy.disclaimer`; do not change the
> engine, the correction numbers, or any threshold in `settings_registry.json` without asking.

---

## 1. Settings added

All off or at their old behaviour, so pulling this changes nothing until someone turns it on.

| Key | Default | What it does |
|---|---|---|
| `engine.personal_lines` | **off** | the whole of part A |
| `engine.personal_spread` | 1 | neighbour lines kept either side, for the Finder |
| `engine.departure_strong` | 0.12 | gap from usual needed for Strong, when personal lines are on |
| `engine.departure_solid` | 0.06 | gap needed for Solid; half of it is the Watch floor |

## 2. What part A does to the numbers

Same league, same engine, the setting off and on:

| | off | on |
|---|---|---|
| Median likelihood of a shown card | 0.887 | **0.447** |
| Cards at 85% or more | 14 of 20 | **0 of 20** |
| Cards led by the entity's own line | — | **20 of 20** |
| Forecasts of a shortfall | 0 | **14 of 20** |

```
Team 4   14+ shots   63%   They usually manage 13.5 · this line lands 48% of the time
Team 7   13+ shots   24%   They usually manage 13.1 · this line lands 53% of the time
Player 704  3+ shots 64%   His usual game is 2.6 · this line lands 51% of the time
```

The second row is the point of it. A claim that a team will fall well short of its own normal game
is a forecast, and the old scheme had no way to make one.

## 3. What to look at, and what it should look like

Open `/insights` with the setting on. Each card should name a count that entity actually reaches,
not a count everybody reaches. If you see `9+ shots` or `1+ shot` leading a card, something is
wrong — those are the lines this update exists to stop, and they should now sit in "more lines".

`docs/redesign/swiss/sheet-routes.png` and `sheet-states.png` show every screen as it stands.
`docs/redesign/swiss/pairs/` has ten before-and-after pairs on phone and desktop.

## 4. Two bugs fixed on the way

`frontend/src/pages/League.jsx:79` crashed the whole League page with
`Cannot read properties of null (reading 'toFixed')`, in all four viewport-and-theme combinations.
It guarded on the league-average object existing and then read a field that is `null` until some
refereed games exist.

The player insight sheet held ten games in a strip 354px wide that scrolled to 494px, so **three
games were off the right edge** with no fade and no scrollbar, while the caption underneath read
"9 of 10 reached it". The strip now wraps.

## 5. What is not done

- **Live screens are unreviewed.** The demo has no live match — all twelve fixtures are scheduled
  and the rest final — so the Live tab and in-play card tracking were never rendered during this
  work. Wiring `tests/live_mock.py` into `tests/demo_server.py` would close it.
- **Visitor popups are unreviewed** for the same reason: they are admin-authored content that does
  not exist in demo data.
- **The passes and fouls markets still need the PitchAPI key mapping** in step 2 before they can be
  built (docs/47).

## 6. Before `engine.personal_lines` goes on in public

Two things have to be true, and neither is true yet.

**The departure thresholds are guesses.** 0.12 and 0.06 were chosen to give a sensible spread of
tiers on a simulated league. They have no backing. Set them from real results, so that a Strong line
is right about as often as a Strong line used to be.

**Calibration in the 40–70% band is now load-bearing and has never been tested.** Nearly every shown
line used to sit above 80%, so the lower bins of the track record were empty. They will fill the
moment this is switched on. If the engine turns out to be poorly calibrated there, this change
*exposes* that rather than causing it — but it does expose it, in public, on the page whose whole
job is to show whether the forecasts can be trusted.

So: switch it on for one league, let the record fill, read `track_record`'s 0.4–0.7 bins, and only
then decide. The walk-forward gate in docs/37 **cannot** settle this — accuracy does not change, the
same ladder is computed either way. What changes is which true statement gets said out loud.
