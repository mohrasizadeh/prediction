# 18. The brain: tactics, formations, competition importance and rotation

Written 2026-10-26. This document answers one question: **if the brain knows how a team plays and how much a match matters to it, are its forecasts better?** We tested it on real matches before building. The short answer is below, then the evidence, then what ships and how to switch things on.

## 1. The verdict

| Idea | Tested on | Result | What ships |
|---|---|---|---|
| Season-long tactical style (press, build-up, counter, long ball) as forecast inputs | 3 leagues, 1,588 team-matches, 6 metrics | **No gain.** Slightly worse (z -3.1 on the four core metrics). A team's own shots, corners and tackles already carry its style. | Layer built, **off** (`engine.tactic_layers`). Style words stay as *explanations* only. |
| Formation shape of the confirmed eleven (defenders, midfielders, forwards) | Same, with the real lineup handed to the model | **No gain** (z -0.2 to -0.8 on the four core metrics; goals no better). | Layer built, **off** (`engine.shape_layer`). |
| How first-choice the eleven is, number of changes | Same | **No gain** at team level (z -0.4). | Used only in the start model, see below. |
| Rotation: the calendar changes **who starts** | 34,763 squad rows, 3 leagues | **Real but small.** After a short rest regulars start less often (about 0.82 vs 0.87) and fringe players more. Held-out gain per row: +0.0004 to +0.0010 (z 0.9 to 2.1). | Built and **gated** (`context.start_model = auto`). It turns itself on only if it beats the plain start rate by 2 standard errors on your own data. |
| Rotation: it changes the **team's totals** | 14 Premier League seasons, goals | **No gain.** Rest days, European match behind or ahead: the effect is smaller than the noise (log-loss change +0.0003 +/- 0.0001, in the wrong direction). Squad depth absorbs it. | Not built as a rule. |
| "Nothing to play for" late in the season | 14 PL seasons | **Too few cases** (72 team-matches, +0.11 goal difference +/- 0.20). Cannot tell. | Not built. Revisit with more data. |
| Rotation **chip** on every forecast ("Champions League in 3 days, some regulars may rest") | Design | It is information, not a number. It costs nothing and is honest. | Ships **on**. |

In plain words: the brain does not get smarter by being told "this team presses high" or "they play a 4-3-3". It already learns that from the numbers. What the calendar does change is **who is on the pitch**, and that matters for **player** markets (shots, tackles) more than for team totals. We built that, we gate it, and we show the warning chip either way.

### One result we threw out
An early run showed lineup shape helping a lot (z about 7). It was false. Ligue 1 had 23 matches where the free event data was empty (all zeros) for two clubs, and the "shape" column had a zero in those rows, so the model learned "shape = 0 means zero shots". With those matches removed the gain vanished in every league. The loader now drops matches with an empty event feed (`validation/load_statsbomb.py`). **Take this as a rule for the real feed too:** a match with all-zero shots, tackles and corners for a side is a data hole, not football. `ingest.py` already stores a missing value as null, never zero. Keep it that way, and check `data_coverage` before trusting any layer.

### A finding about the old engine
On the same real matches the engine beats the plain league-average baseline on shots, shots on target and corners (z -6.7, -3.3 and -5.4 for the baseline). Good. But the **4x4 style-matchup terms** did not beat the same engine without them (pooled +0.0010 in favour of *without*, z 1.6; not significant). The shipped rule says a feature must beat its plain version. On this one season of three leagues it does not. **Decision for the owner:** run `backtest_real.py` on the PitchAPI history (section 8). If the matchup terms still do not win, set `engine.interactions` to off. We left the default as it was because one season from a different data provider is not enough to flip it.

## 2. How the brain thinks about any metric

Every metric (shots, shots on target, corners, tackles, fouls, yellow cards, goals, or one you add) goes through the same chain. A step stays in the chain only if it passed its gate.

1. **Baseline.** League average for this metric, times the team's own output, times what this opponent concedes. Time-weighted.
2. **Game script.** Dixon-Coles team strength says who is likely to lead. A side that trails shoots more; a side that leads defends more.
3. **Venue.** Home or away.
4. **Style match-up.** Eight numbers per team (shots, corners, tackles for and against, possession, shot accuracy), shrunk toward the league mean. Gated (see section 1).
5. **Context.** Rest, matches in the last 14 days, importance of this match and of the next one. Used only to move *who starts* (step 6), not the team total.
6. **Availability and minutes.** Each player has a mixture: starts (with minutes), comes on, does not play. A confirmed lineup collapses the mixture. With the start model on, the calendar re-weights the mixture before the lineup is out.
7. **Distribution.** A negative binomial around the expected count, with a dispersion fitted per metric. This gives the chance of every threshold, not just one.
8. **Reasons.** The factors with the largest push, written from fixed phrases.
9. **Gate and tier.** Strong / Solid / Watch, only if the interval and the track record support it.

**Adding a metric** takes one list entry and one column: add the name to `extra_stats`, store `<name>` and `<name>_against` per team-match, add thresholds to `engine.team_thresholds`. Fouls and yellow cards already run this way in the tests. Result so far: fouls and yellow cards are *noisy*; the engine edges the naive baseline (z -1.8 and -1.9 for the baseline) but do not promote them to Strong until your own backtest says so.

## 3. Competition importance and rotation

Clubs do not play every match the same way. A League Cup tie three days before a Champions League night is the classic case. The brain reads **every** competition a club plays in.

**Evidence that rotation is real in the lineup**
- Free Premier League, Serie A and Ligue 1 lineups, 2015/16: with a rest of 3.5 days or less a club makes **3.49** changes to its eleven, against **2.52** with more than 5.5 days. With a European match inside 4.5 days after, **3.21** against **2.68**.
- Cup ties, from published counts (not from our files): FA Cup fourth round about 6.1 changes on average; League Cup second round about 8.6; league games about 2.75.

**Evidence that it does not move team totals enough to model by hand**
- 14 Premier League seasons: adding "rest short", "European match behind", "European match ahead", "cup match ahead" to the goal model did not improve it on held-out seasons. Squad depth buffers the effect. Top clubs in the League Cup against lower-division clubs: goal difference +1.84 (171 ties), FA Cup +1.39 (208 ties). No sign that rotation makes them worse.

**What we built**
- `context.py`: `DEFAULT_IMPORTANCE` (league = 1.0, Champions League 0.95, knockout 1.15, Europa 0.75, FA Cup 0.55, League Cup 0.40, late rounds higher; editable in `context.importance`).
- `Calendar.context(team, kickoff, comp, stage)`: rest days, days to the next match, its importance and competition, matches in the last 14 days.
- `pressure_parts`: five plain numbers: `next_bigger`, `europe_soon`, `low_stakes`, `congestion`, `short`. Each is its own cause so the model can weigh them apart.
- `StartModel`: `P(start) = logistic(logit(usual start rate) + context terms)`, with each term also multiplied by how regular the player is. A regular is rested more, a fringe player plays more. The club's expected number of starters is kept, so it moves *who*, not *how many*.
- A **rotation chip**: low / medium / high with one sentence ("The club has a Champions League match in 3 days, so some regulars may rest."). Stored per club per match in `match_context`. Shown on the match page and as a small tag on forecasts. It never changes a number by itself.
- A confirmed lineup **always** wins over the model.

**The gate.** On each engine run the bridge fits the start model on older matches and scores it on the newest `context.holdout_share` (30%). If it does not beat the plain usual-start rate by `context.gate_z` standard errors (2.0), it stays off, and the result is stored in `engine_gates` with the reason. Modes: `off`, `auto` (default), `on` (forces it; use only to experiment).

**What the free data could and could not teach.** The 2015/16 files have no cup or Europa League calendar, and lineups exist only for that season. So `next_bigger` and `low_stakes` learned nothing (coefficient 0); `europe_soon` and `short x regular` did learn. The cup effect will only be learned from **your** data: PitchAPI lineups for cup matches, once ingested. Until enough rows exist (`context.min_rows`, default 3,000) the model stays off.

## 4. Tactics and formations

**What the guide (the attached PDF) gave us.** Four named systems with measurable signatures: high press (PPDA under 9, defensive actions high up the pitch, high turnovers), mid block (PPDA 10 to 13.5), low block (PPDA over 14, actions under 35 yards), positional play (5.5+ passes per sequence, slow direct speed, 60%+ possession and field tilt), direct counter (fast, under 3.5 passes, shot within 10 to 12 seconds), long ball (15 to 20%+ long passes, aerial duels). Three archetypes: Positional Control, Gegenpressing / Vertical, Compact Counter.

**What we did with it** (`tactics.py`).
- Turned each signature into an index that uses only fields a stats feed can give: PPDA, defensive-action height, passes per sequence, direct speed, field tilt, long-pass share, counter-shot rate. Teams are scored **against their own league and season** (z-score), not against the guide's fixed cut-offs, because PPDA is defined differently by each provider. The guide's absolute numbers stay in the docs as a reading aid.
- `named_systems(row)` and `archetype(row)` give a label when a team is one standard deviation above the league on a system.
- A `StyleTracker` builds these from past matches only, with shrinkage toward the league mean.
- Reliability: possession and directness are stable over a season (split-half correlation high); pressing is moderate; counter-attack and card counts are noisy. That is why the noisy ones do not help forecasts.

**What it is used for.** Explanations ("The opponent plays a low block, which lifts corners.") and the Team / Matchup pages. **Not** as forecast inputs, because the tests say it adds nothing beyond a team's own rates.

**Formation.** We carry `formation` and the shape of the eleven (`n_def`, `n_mid`, `n_fwd`) as `match_features` that can be plugged into the model once a lineup is confirmed. Off, for the reason in section 1. The hook is there so that a better data source (tracking data, real pressing events) can be tested with the same harness without touching the engine.

**Unverified with PitchAPI.** Whether it carries PPDA-like fields, pass-sequence data, long-pass counts or cup / European matches is **not confirmed** (doc 08). The engine switches the tactics layer on only if those columns exist **and** the gate passes.

## 5. What changed in the code

| Where | Change |
|---|---|
| `backend/soccer_brain/context.py` (new) | Competition weights, `Calendar`, `pressure_parts`, `rotation_pressure`, `StartModel`, `prior_and_regularity` |
| `backend/soccer_brain/tactics.py` (new) | Tier-B style indices, named systems, archetypes, `StyleTracker` |
| `backend/soccer_brain/backtest_real.py` (new) | Walk-forward harness for real data: scores the whole count distribution, paired z, `gate()` |
| `backend/soccer_brain/engine.py` | `extra_stats`, `match_features`, `tactics`, `shape` options (defaults reproduce the shipped report exactly); `set_start_model`; `predict_fixture(..., ctx=)`; `Forecast.rotation`, `rotation_why`, `p_play_usual` |
| `backend/engine_bridge.py` | `import_calendar`, `build_calendar`, `fit_start_model` (the gate), `context_for_match`; `run_league` stores `match_context` and `engine_gates` and passes the context |
| `backend/admin_queries.py`, `routes_admin.py` | `GET /api/admin/brain`, `POST /api/admin/calendar/import` |
| `backend/queries.py` | `match_detail` returns `rotation` per club |
| `backend/settings_registry.json` | 9 new settings (165 in all) |
| `backend/mongo_init.py` | Indexes for `club_calendar`, `match_context`, `engine_gates` |
| `backend/tests/selftest_brain.py` (new) | The tenth test suite |
| `validation/` (new) | The scripts that produced every number here (README inside) |

## 6. Data

New collections (doc 05 has the field lists):
- `club_calendar`: one row per club per match **outside** the tracked leagues' own fixtures (cups, Europe, super cups). League matches come from `matches`.
- `match_context`: rotation level and sentence per club per upcoming match.
- `engine_gates`: one row per engine run and layer: mode, passed, applied, n_train, n_test, gain, se, z, reason, coefficients.

**Filling the calendar.** Three ways, in order of effort: (1) admin **Brain layers** screen → paste or upload rows → `POST /api/admin/calendar/import`; (2) a monthly job that reads openfootball (public domain, CC0) cup and European fixture files from GitHub and maps club names to our ids (see `validation/load.py` for the parser and the name-matching rules; add an alias table in admin); (3) PitchAPI, if it lists cup and European matches for our clubs (**unverified**). Without a calendar the chip says nothing and the start model stays off; nothing breaks.

## 7. Admin and pages

- **Brain layers** (new, under Data → Engine): per league, the latest gate row for each layer (applied or not, gain, z, rows, the reason in words); the switches `context.start_model`, `engine.tactic_layers`, `engine.shape_layer`; the competition weights as a table; calendar coverage by competition and number of clubs covered; the calendar import box.
- **Match page**: a rotation chip for each club under the lineup block (low is hidden). Player forecasts show "usually starts 90%, today 70%" only when the start model is applied.
- **Forecast cards**: a small "Rotation watch" tag when the club's level is medium or high. No colour of its own; use the existing info style.
- Copy rules (doc 03) apply: the chip sentence is analysis, not advice. It is scanned by `textguard` like all other text.

## 8. How to re-run the proof on real data (do this before removing "Beta")

1. Export PitchAPI history for one league (at least two seasons) into the three frames `build_frames` makes.
2. `backtest_real.run_counts(ms, tg, pg, variants, stats=...)` with `variants = {"full": {}, "plain": {"interactions": False}, "tact": {"tactics": True}, "shape": {"match_features": (("n_def","shape"),("n_fwd","shape"))}}`.
3. `backtest_real.summarize_counts(res, ref="full")` prints the paired gain and z for each metric. `backtest_real.gate(res, "plain", "full")` is the yes / no.
4. Rule: a layer is on only if its pooled gain is positive and z is at least 2.0. **Cluster by team-match** (average the metrics for a team-match first), because the metrics inside one match are correlated and a plain pooled z overstates evidence by about a factor of 1.5 to 2.
5. **Look at the per-league and per-team numbers before believing a pooled one.** The false shape result above was visible in two lines of that table.
6. Check coverage: drop matches with an empty event feed before fitting.

## 9. Caveats, stated plainly

- All the real-data evidence is **free data**: one season (2015/16) of event data for three leagues, plus fixtures for 14 Premier League seasons. It is enough to reject big claims, not to prove small ones.
- Cups and the Europa League are missing from the 2015/16 calendar. That can hide an effect, never invent one.
- The "no stakes" sample is 72 team-matches. Unknown, not zero.
- PPDA and similar numbers differ by provider. Labels here are relative to the league, on purpose.
- Published rotation counts for cups come from news coverage, not our files.
- StatsBomb open data requires attribution: **"Data provided by StatsBomb."** Keep that line in `validation/README.md` and anywhere results derived from it are published. openfootball is CC0.
- Wording: this is analysis of football statistics. The product description still says "bettors" in the Project; the app copy must follow doc 03 (no odds, no betting terms, no promotion).
