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

## A data bug worth knowing about (`ebf...`, the Finder club fix)

A Finder row took the player's club from `$first` over his MATCH ROWS -- the club he played those
games for. For anyone who has transferred that is the old club, and because the next fixture and
the forecast were both looked up from it, the row showed the wrong badge AND no percentage, because
he is not in that squad any more. One bug wearing two faces.

`players.team_iid` is the current club and was already maintained carefully (`upsert_player` guards
it with `team_as_of` so an older match ingested later cannot move it back, docs/41). That fix was
made for the player record in docs/41 and never reached the Finder. **If you add another surface
that needs a player's club, read it from `players`, not from his match rows.**

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

## The loose-ends sweep — what it fixed

Four things it found were dead or duplicated, and all four are gone from the tree:

- **`isLiveNow` was the canonical "is this match on right now?" test and nothing imported it.**
  `pages/Today.jsx` and `pages/Match.jsx` each hand-rolled `mLive(m) && status !== "final"`, which
  is two thirds of it: both counted a **postponed or cancelled** match as live, so it kept the live
  dot, and on the match page it also re-fetched every 30 seconds forever. Both now import the real
  one. If you add a third screen that asks the question, import it; do not retype it.
- **`components/Football.jsx` carried its own earlier `TierBadge`, `LikelihoodBar`, `ForecastCard`
  and `ProbBar`** long after every screen moved to `components/ui/`. No importers, different
  output from the kit versions, so a reader comparing the two could not tell which one ships. Gone.
  `TacticChip`, `MatchRow`, `FormPills`, the stat vocabularies and the small hooks stay — those are
  live.
- **`RunStrip`** was a third run graphic beside `CardRun` (feed size) and `GameStrip` (reading
  size), exported from the kit barrel and used by nothing. Gone. Its `.v2-run*` rules are still in
  `styles/v2.css` §13, deliberately: they are woven into three shared selectors and cost nothing,
  and they are where to start if the standalone strip is ever wanted back.
- **`components/Spec.jsx`** was the "to build" placeholder from the Emergent scaffold. Every screen
  it stood in for is built, so it and its two CSS rules are gone. `EMERGENT.md` still mentions it;
  read that as history.
- **`images.credit_text` held a crest-and-photo attribution notice that reached no screen.** The
  product was showing other people's crests and player photos with no notice at all. It now travels
  in the site config and renders in the footer meta (`footer-image-credit`); emptying the setting
  removes it.

## Settings an owner can change that change nothing

Measured, not guessed: of the 254 keys in `backend/settings_registry.json`, **47 are read by no
backend code and no frontend code**. They are in the admin Settings panel with labels and defaults,
and moving them does nothing. That is the single largest "half-built" surface left. In four groups,
with what I would do:

1. **~21 `features.*` flags** — `insights`, `finder`, `squad_grid`, `team_totals`, `against`,
   `referees`, `leaderboards`, `learn`, `favourites`, `alerts`, `newsletter`, `track_record`,
   `following`, `saved`, `search`, `beta_tag`, `show_xg`, `show_lineups`, `show_tactics`,
   `show_match_probs`, `require_signin_to_follow`. Turning off "Insights feed" leaves the Insights
   feed running. **This duplicates Site Studio**, which already turns screens off through
   `nav`/`footer` and is the mechanism that works. `features.billing`, `features.maintenance` and
   `features.live` are the three that are genuinely wired — do not remove those.
   *Do:* delete the dead flags from the registry and point the Features help text at Site Studio.
   Building a second gating layer to match them is the wrong direction.
2. **11 layout and default knobs the frontend hardcodes instead** — `home.sections`,
   `home.top_insights_count`, `home.date_back_days`, `home.date_forward_days`, `finder.max_leagues`,
   `finder.last_options`, `finder.default_last`, `finder.thresholds`, `finder.stats`,
   `grid.max_games`, `grid.default_games`. The live values are literals: `Finder.jsx:17` holds
   `last_n: "10"` and its slider is `min={5} max={20}`; the grid window is capped by the plan
   entitlement `grid_games`, not by `grid.max_games`. *Do:* these are the ones worth **wiring**, via
   `/api/public/settings` (which exists and today only `Newsletter.jsx` reads). Until then a reader
   of the registry is being told the wrong numbers.
3. **4 copy overrides never consulted** — `copy.strings`, `copy.tier_names`,
   `copy.tactic_explanations`, `copy.reason_overrides`. `lib/copy.js:4` hardcodes the tier names.
   *Do:* wire `copy.tier_names` (an owner renaming a tier is a real request) and delete the other
   three unless you build the override layer.
4. **11 owner-facing settings that are frozen at their defaults** — `security.log_retention_days`,
   `security.auth_log_retention_days`, `analytics.retention_days`, `ingest.concurrency`,
   `ingest.fixture_window_days`, `ingest.recheck_final_hours`, `engine.min_team_games`,
   `auth.google_enabled`, `auth.optional_2fa_for_users`, `alerts.telegram_enabled`,
   `alerts.telegram_bot_username`. The three retention ones are the sharp case: the real values are
   **hardcoded TTL indexes** in `backend/mongo_init.py` (`app_logs` 30 days, `auth_log` 90,
   `events` 400) that happen to equal the registry defaults exactly, so the setting looks live and
   is inert. *Do:* build those indexes from the settings and re-create them when they change. This
   one I deliberately did not do: it changes how long data is kept, which is the owner's call.

## The owner's four (v10)

1. **A missed game was invisible.** The run strip drew a game that did not clear the line in
   `--surface3`, which on the match page is one step from the card it sits on — **1.09:1**. Half of
   every run was a blank space, so "1, 0, 1, 2, 0" looked like "1, 1, 2" and a reader counting bars
   counted a better player than the data describes. There is now one token, `--v2-miss`, used by
   both run graphics (`CardRun` on cards, `GameStrip` on the player page and in the sheet), measured
   at **3.29:1 light / 3.34:1 dark** — the 3:1 WCAG 1.4.11 asks of a graphic you have to read. A
   game with no figure at all is hatched now, so "no data" and "did not clear it" are not a shade
   apart.
2. **A tier filter beside the slider, and Watch now says why it is Watch.** The chips are the same
   multi-select `ChipsRow` Insights uses, with counts taken after the slider. On the second half:
   Watch was the only tier that never explained itself. Strong and Solid are promises and
   self-explaining; Watch is the *absence* of one, and the number beside it does not say which
   absence — which is why "73%, Watch" reads as a card contradicting itself. `tiering.assign` now
   fills a note in the two cases that produced none: the plain one ("Under 80%, where Solid
   starts") and the personal-line one ("A small step from their usual game"). `selftest_lines`
   asserts no Watch line is silent. The Learn page's tier entry was rewritten around the same
   question.
3. **The card shows the club crest, the position, and can be followed.** The club was *named* on
   every player card and drawn on none — the one identifier a reader recognises before reading a
   word. The position matters because "2+ tackles" means something different for a full-back and a
   striker, and the card assumed one without saying so. `SaveButton` now sits in the foot: every
   rung under "+N more lines" could be kept and the headline line could not.
4. **The page scrolled sideways, and it was the header.** Measured on a 390px phone: the header row
   needs 412px and has 358, so the document took a 429px scroll width and the browser parked the
   view at the right — which is why a screenshot of Today showed the brand mark cut off the left
   edge of a page whose content all fits. Nothing in that row is optional, so the saving came from
   the wordmark beside a logo that is its own mark, and the size of the Beta pill: 338 of 358 now,
   and `scrollWidth === clientWidth` on every screen. The day strip was a second, smaller case of
   the same thing — three 14px league crests are ~48px of unshrinkable content inside a 44px tile —
   and those crests are gone, replaced by the dot that was already there for days without them. The
   league names stay in the tile's accessible name, where they cost no width. The tiles got a
   hairline, because transparent tiles on a transparent strip gave the dates nothing to stand on.
