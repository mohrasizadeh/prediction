# METRICS — every number the reader can see

Full audit for the v3 design review. Written 2026-11-06 by reading the code, not from memory:
`backend/soccer_brain/engine.py` (the `Forecast` dataclass, lines 102–136, and `predict_fixture`,
lines 900–1040), `backend/engine_bridge.py` (the stored document, lines 180–420), `backend/queries.py`,
`backend/tiering.py`, `backend/combo.py`, `backend/calibration.py`, `backend/referees.py`,
`backend/match_extras.py`, `backend/team_insights.py`, `backend/cards_model.py`, and every
`frontend/src/pages/*.jsx` plus `frontend/src/components/**`.

Scope: **reader-facing screens only** — the public screens P-01…P-37, the account sections A-01…A-06
and the overlays O-01…O-06 from `docs/57_screen_inventory.md`. The 33 admin modules are staff-facing
and are out of scope; where an admin number is the *only* place a reader-facing quantity is visible,
it is called out.

Where this document says "default", it means the value in `backend/settings_registry.json`. Two
defaults change how most of this reads and are stated once here:

- **`engine.personal_lines` = `false`.** So today there is no `thr_personal`, `is_personal` is false
  on every line, and `tiering._departure_tier` never runs. Several fields exist only to serve a
  feature that is switched off.
- **`engine.condition_on_play` = `true`.** So every player `p` is "if he plays", and `p_basis` is
  `"played"` on every player line except the separate yellow-card model.

---

## 1. The ten highest-impact findings

| # | Finding | Where | Why it matters | Fix |
|---|---|---|---|---|
| 1 | **`p_usual` and `usual_p` are different numbers with the same name.** `p_usual` (engine) is a model probability from the entity's own fitted rate; `usual_p` (`queries._usual`) is the raw share of its last 10 games. Both ride on the same JSON object. One is drawn as "Usual 57%", the other is never drawn at all. | every card screen; `backend/queries.py:813`, `engine.py:123` | A reviewer, a test or a future developer reading `f.usual_p` gets a silently different quantity. The near-collision is a latent production bug, not a cosmetic one. | Rename the empirical one `last10_share`. Delete it if the strip already carries it (it does — see §3). |
| 2 | **`span` is computed on every line and shown nowhere.** It is the one quantity that answers the product's own thesis question — "could this have come out differently against another opponent?" — and it is used only as a hidden server-side gate (`queries.is_trivial`, `engine.min_span` 0.06). | engine → all cards; 0 frontend references | docs/56 argues span *is* the differentiator. The app computes it, acts on it silently, and never lets the reader see the argument it is making. | Draw it. See §4.1. |
| 3 | **`tier` means two incompatible things, under one badge.** With `personal_lines` off, Strong = "whole chance ≥ 90%". With it on, `_departure_tier` makes Strong = "the range sits clear of usual and the gap ≥ 12 points" — which can be a 35% line. Same word, same three dots, same colour. | `backend/tiering.py:70–145`; every card; P-17 | P-17 Track record reports "Our record on Strong forecasts" by pooling both populations. Turning `personal_lines` on would make the trust page's headline number meaningless without a single visible change. | Two badges, or gate the track record by `is_personal`. Do not ship personal lines until this is resolved. |
| 4 | **P-17 measures a different quantity from the badge it prints.** `queries.track_record` filters `player_played: True` — it scores the "if he plays" number. `tiering.Record` counts a non-appearance as a **miss** — it scores the whole chance. The page therefore validates a number the tier was not earned on. | `queries.py:752`, `tiering.py:33–45` | The one screen whose whole job is trust is answering the wrong question, flatteringly. | Report both: "when we say 80% and he plays" and "when we say 80%, counting the times he did not play". |
| 5 | **The `match_goals` band is a hard-coded constant.** `_goal_lines` sets `lo, hi = p ± 0.06` for every goals line, and these lines never pass through `calibration.apply`. | `engine_bridge.py:204`; M-03, P-01 chips | O-01 prints "That range is how sure we are: the wider it is, the less sure the forecast" directly under a width that is identical on every goals line in the app. The copy makes a promise the number cannot keep. | Take lo/hi from the scoreline matrix, or suppress the range on goals lines and say the band is not modelled. |
| 6 | **The Lineups pitch labels `p_play` as "chance to start".** `queries.predicted_xi` also *ranks* the predicted eleven by `p_play`. `p_start` exists precisely because `p_play` is ~0.93 for fringe players (docs/55). | M-04, `Match.jsx:36,65`; `queries.py:862` | A regular substitute at `p_play` 0.95 outranks a genuine starter at 0.90, and the number beside his head says he is 95% to start. Both the label and the ordering are wrong. | Rank and label on `p_start`. |
| 7 | **O-01 prints the same number twice, with two labels.** The header shows `pct(f.p)`; the "If he plays" tile shows `pct(f.p)` too, because the divide-by-`p_play` branch only fires when `p_basis === "all"`, which is false for every ordinary player line under the default config. | O-01, `ForecastSheet.jsx:104` | Two tiles that must differ, identical, next to "Chance he plays 84%" — it reads as a bug and teaches the reader to distrust the sheet. | Drop the tile; the header already is the "if he plays" number. Say so once, in the header. |
| 8 | **"Minimum likelihood" filters two different fields on two screens.** P-04 filters `max(f.p, f.best_p)`; M-03 filters `f.p`. Same control, same label, same step, different answer. | P-04 `Insights.jsx:76`, M-03 `MatchCentre.jsx:122` | The reader learns one meaning and it breaks on the next screen. | One helper, one field. `best_p` is the right field — a card's lead line is deliberately not its likeliest. |
| 9 | **"How many lines in this match" has three different answers.** `insight_count` = tier in (Strong, Solid); M-03 tab badge = cards with `p ≥ 0.5`; M-03 group headers = cards above the slider. All three can appear within two taps. | P-01, P-11, M-03 | Three counts of one thing, none labelled with its rule. | Keep one — Strong+Solid — and label it "worth reading", as P-04 already does. |
| 10 | **Referee "cards a game" is three different numbers at two precisions.** `yellow_pg` (events ÷ matches **with events**) on P-11, `per_game.yellow` (same, 2 dp) on P-15, and `cards_per_game` / `cards_per_game_normalised` (team_match_stats ÷ **all** his matches) on P-14. P-11 prints "Games 20" beside a figure whose denominator may be 6. | `match_extras.py:158`, `referees.py:94`, `League.jsx:113`, `Referees.jsx:30`, `Referee.jsx:7` | The same referee reads differently on three screens, and the headline denominator is wrong on one of them. 2 dp on a 6-game sample is fiction. | One field (`cards_per_game_normalised`), 1 dp, denominator printed. |

---

## 2. Full inventory

Columns: **Metric** (field · reader label) — **Where** (screen IDs) — **What it means** (from the
code) — **Right metric?** — **Presented well?** — **Better.**

### 2.1 The forecast line — the numbers on a card

These travel together on one object and appear on every screen that draws a `ForecastCard`:
**P-01** (Top 3), **P-04**, **P-05** (likelihood mode), **P-08** (signed-out sample), **P-13**,
**P-16**, **M-03**, **P-26**, and inside **O-01** / **O-02**.

| Metric | Where | What it actually means | Right metric? | Presented well? | Better alternative |
|---|---|---|---|---|---|
| `p` · the big "74%" | all card screens, O-01, P-18, P-11 bookings, P-16 | P(count > `thr`) for this fixture. For a player it is **conditional on him playing** (`cond_play` divides by `p_play`). Then put through `calibration.apply` (capped at 0.97), then optionally blended with his own last-40 record by `tiering.anchor` (capped at `engine.p_cap` 0.985). So it is a calibrated, record-anchored conditional probability — four transforms deep. | Yes for "will this happen", no as a ranking key: docs/50 measured median shown `p` at 0.873 and docs/48 showed why points-of-`p` cannot be compared across markets. The app knows this (the feed sorts on `lift`) but still gives `p` the largest glyph on the card. | Whole percent is right. Placement is the problem: it is the biggest number on a card that is deliberately *not* chosen for it. | Keep `p` at its current size only where the reader asked for likelihood (P-05 likelihood mode, O-01). On a ranked feed, give the departure (`edge`) the hero slot and `p` the supporting one — the card's own comment block already argues this and then does the opposite. |
| `lo` / `hi` · "(66 to 81)" | all card screens, O-01, O-02 | 10th and 90th percentile of `n_draws` = **60** Monte-Carlo draws over team and player dispersion, calibrated with the same map as `p`, and shifted by `tiering.anchor`. An 80% credible band, from 60 draws. | Yes. An uncertainty width is exactly what a counting tool cannot produce. | Two problems. (a) It is printed to the point ("66 to 81") when 60 draws give the 10th percentile a Monte-Carlo error of roughly ±2 points. (b) O-01 explains it as "how sure we are" without ever saying it is an 8-in-10 band. | Round to the nearest 5 and say the coverage once: "8 times in 10 between 65 and 80". Raise `n_draws` before printing finer. |
| `p_display` · "95%+" / "under 50%" | P-05 (ladder answers), suppresses range and run | Set only by `queries._from_ladder`, when the asked-for rung was outside `engine.line_band` and is read off the stored `ladder`. | Yes in principle — an honest refusal to be precise past the model's ceiling. | **Inconsistent with the rest of the app.** A stored line at 0.97 prints "97%"; the same rung resolved from the ladder prints "95%+". Three ceilings coexist: calibration `CAP` 0.97, `engine.p_cap` 0.985, this display cap 0.95. | One ceiling, applied in one place. "95%+" is the honest one; use it everywhere above 0.95 and delete the other two from the reader's view. |
| `tier` · Strong / Solid / Watch + 3 dots | all card screens, P-04 list + filter, P-17, P-16, O-01, Newsletter | Normally: `whole = p × p_play` against `engine.strong_min` 0.90 / `solid_min` 0.80 / `watch_min` 0.60, with `lo` floors, then **lowered** (never raised) by the measured record for that (scope, stat) in `tiering.Record`. Lineup caveats apply. With `personal_lines` on it is instead a **departure** grade with no relation to likelihood. | Yes — a reader wants one word, not a number. | The badge is honest about rank and silent about basis. A 97% line reading "Solid" is explained only by `tier_note`, which is optional and small. | Put the basis in the badge's own tooltip/aria text ("Solid: 97% if he plays, 84% to play"). And see finding 3: never let one badge carry two definitions. |
| `tier_note` · "Strong once the lineup is confirmed" | card, O-01 | One sentence from `tiering.assign` / `_departure_tier` explaining a demotion. Four shapes: lineup caveat, "Held at Solid until our record on these lines is measured", "Similar lines happened N% of the time", "The likely range still reaches their usual". | Yes — the best copy in the product. It turns a demotion into a reason. | Small grey text beside the badge, easy to miss, and null on most cards. | Keep. Consider always having one, even when nothing was demoted ("Strong: our record on these backs it"). |
| `p_usual` · "Usual 57%" | card `v2-cmp` row, O-01 ("A player like him…") | **For a team:** P(count > thr) under the team's own normalised average against an average opponent, no venue, no matchup (`mu_usual`, `engine.py:922`). **For a player: `p_usual = p_base`** (`engine.py:1035`) — his own per-90 shrunk rate (`rho90` prior, strength 4.0) carried through *this* match's minutes mixture, with no opponent adjustment. Not a season average: the minutes are this fixture's. | Yes, and it is the product's best idea. The pair (`p`, `p_usual`) is a claim; `p` alone is a description. | **The label in O-01 misdescribes it.** "A player like him in a fixture like this: usually 57%" is wrong twice: it is *him*, not a player like him, and it is an *average* opponent, not a fixture like this. The card's "Usual" is correct. Two labels for one field, one of them false. | Use one sentence everywhere: "His own normal game, before this opponent: 57%." |
| `edge` → `dep` · "+12" | card `v2-cmp` row | `p − p_usual`, stored on the document; the card recomputes it as `Math.round((p − p_usual) × 100)`. Also the feed's default sort key — except the sort does **not** use it: `FEED_SORTS["edge"]` sorts on `queries.lift`, which is the change in **log-odds** (`engine.lift_scale` = `"odds"`). | The quantity is right and docs/48 is right that points are the thing to *show* and log-odds the thing to *rank* by. | **A bare "+12" with no unit, no word and no sign convention explained**, sitting between a percentage and a count. And the feed's order visibly disagrees with it: a card showing +8 can sit above one showing +18 because the log-odds move was larger. The P-04 sort label says "biggest change", which is true of neither number as drawn. | Print it as a sentence fragment with a unit: "12 points above his usual". Either sort on the displayed number or show the ranked number ("twice as likely as usual") instead of the points. |
| `expected_usual` · "his average 2.4" | card `v2-cmp` row | **For a player:** `Σ probs·mus_b` — his expected count *in this match's minutes scenario*, from his own rate, against an average opponent, divided by `p_play` when `cond_play` is on. **For a team:** `mu_usual` — the normalised per-game average. | A count is the most legible thing on the card and worth keeping. | **"his average" is wrong.** It is not an average of anything he has done; it is a forecast of his count against an average opponent, in tonight's minutes. A reader will read it as a season average and compare it to the strip, which *is* a season average, and find they disagree. | Label it "normally about 2.4 in a game like this". |
| `expected` · — | **nowhere** (only the dead `Football.jsx` card, which no page imports) | `Σ probs·mus` — the expected count **for this fixture**, opponent and all. The direct counterpart of `expected_usual`. | Yes, badly needed. | Not presented at all. | **Show it.** The card currently says "normally 2.4" and never says "tonight 3.1". The one-line fix: `tonight 3.1 · normally 2.4`. See §4.2. |
| `p_play` · "Chance he plays 84%"; pitch "%" | O-01 tile, M-04 pitch, combo sheet, P-01 Top-3 ranking (invisibly) | P(he features at all), from the availability model (`ABSENCE_PLAY`) and the minutes scenario; `likely_play` overrides it to 1.0 for likely starters when `likely_starter_p` 0.85 is met. | Yes, and keeping it out of `p` (docs/27) is correct. | Three problems. (a) M-04 labels it "chance to start" — see finding 6. (b) P-01's `topRated` secretly ranks by `p × p_play`, a quantity shown nowhere on that screen. (c) In the combo it becomes `chance`, a fourth name for the same product. | One name for `p × p_play` — "chance it happens" — used in the combo, in P-01's ranking, and in the tier explanation, since all three already use it. |
| `p_start` · "he starts 41% of the time" | card, only when `p_basis === "played"`, not confirmed, and `p_start < 0.8` | P(he is in the starting eleven for **this** match) from `_rotated_starts` / the fitted `StartModel`, with calendar pressure. | Yes — docs/55 is right that this is the gate that catches a fringe player. | **"of the time" turns a forecast into a historical rate.** It is this match's chance, not a career frequency. And the gate `engine.min_start` defaults to 0.0, so the field's main purpose is switched off; it survives only as this one caption. | "41% to start tonight". Then use it where it belongs: rank the predicted eleven by it (finding 6) and consider a non-zero `min_start`. |
| `lineup_badge` · Confirmed starter / Likely lineup / Lineup not sure / On the bench | card footer, O-01 tile, combo notes | `confirmed` = in the announced eleven; `bench` = eleven out and he is not in it; `likely` = pre-lineup and `p_play ≥ 0.85`; `unsure` = anything else. | Yes. Four states, each actionable. | Good. The footer tag is well placed and the muted treatment for `unsure`/`bench` is right. | None. |
| `rec_k` / `rec_n` · "Reached this line in 27 of his last 40 games" | O-01 only, gated on `rec_n ≥ 8` | Count of his **last 40 appearances** (minutes > 0, `ap[s].values[-40:]`) where the figure exceeded `thr`. Also the input to `tiering.anchor`, which moves `p` itself. | The record matters, and docs/32 is right that it should feed the number. | **It contradicts the card above it.** The card's strip says "Last 10 · 6 cleared 3+"; the sheet one scroll down says "27 of his last 40". Two true counts of one thing at two windows, neither labelled as a window choice. 40 appearances can span two seasons and a club move. | Pick one window and use it in both places. 10 is what the strip can draw; 40 is what the anchor needs. Show 10, and if the anchor's 40 must be disclosed, say so where the anchor is explained, not as a second record. |
| `run[]` + derived `cleared` · the ten-column strip, "Last 10 · 6 cleared 3+" | card (`CardRun`), when ≥3 games have a figure | Built by `queries._usual`: his last 10 appearances with minutes > 0 **strictly before this kickoff**, oldest first, each carrying `{v, m (minutes), opp, home}`. `cleared` counts `v > thr` client-side. The eleventh, dashed column is tonight's rung with `p` under it. | Yes — the single best object in the product. It makes a truism visible as a rule lying under every column (docs/56 §1), without a number. | Very good. Minutes above and crest below answer "was it a quiet game or ten minutes off the bench". One trap: `CardRun` is passed `line = f.thr` (2.5) and tests `v > line`, while `GameStrip` is passed `line = floor(thr)+1` (3) and tests `v >= line`. Both are correct today, but the same prop name carries two different units in two components that must agree. | Keep. Give both the integer rung and one comparison, so a future caller cannot silently shift a count by one game. |
| `run[].m` · "72'" above each column | card, and `GameStrip` on P-13 / O-02 | Minutes played in that game. | Yes, essential — a shot in 28 minutes is evidence *for* the player and a bare count reads it as against. | Good; the `.low` class at < 70' is a nice touch. | Consider the per-90 figure on demand, which the comment in `_usual` says was the point of carrying minutes but which nothing computes. |
| `usual_p` / `usual_n` · — | **nowhere** | `usual_p` = share of the same last-10 window where `v > thr`, rounded to 4 dp, `None` when fewer than 5 games. `usual_n` = the count. Shipped on every card over the wire. | Redundant: the strip beside it already shows the same ten games and `cleared` already counts them. | Not presented. Pure payload and pure confusion risk against `p_usual` (finding 1). | Delete, or rename to `last10_share` and use it as the strip's caption instead of recomputing `cleared` in the component. |
| `more_lines` count · "+3 more lines" | card footer | Every other stored line for the same (match, scope, entity, stat) group, with `fkey, stat, thr, market, p, lo, hi, tier, p_usual, edge, ladder`. Max `engine.max_lines_per_stat` 3 per stat, so usually 2. | A count of lines is weak, but as a disclosure control it is fine. | Good, and the `topMore` affordance below is the best small decision on the card. | None. |
| `best_p` → "up to 92%" | card footer (`topMore`), P-04 min-likelihood filter | `max(p)` over every line in the card's group, including the lead. | Yes — it is the honest answer to "what is this player's best number", which the lead line deliberately is not. | The label "up to 92%" appears only when a hidden line beats the lead. The *filter* that uses it is labelled "At least N% likely" and silently matches on it. | Say what it is once: "his likeliest line here: 92%". Use the same field in M-03's slider (finding 8). |
| `ladder` · — (used, never drawn) | O-02 / P-13 read it for the rung picker and to resolve `p` for any line; P-05 answers from it | `{thr → p}` for every rung the engine generated for that entity and stat — 4 to 16 rungs (`engine.player_ladder`, `engine.team_ladder`), calibrated. Stored on **every** kept line. | Yes. docs/50 measured that 20 of 20 cards had a 35–65% rung on the ladder and 0 of 20 showed one. | **The ladder is never drawn.** Its only visible trace is which buttons the rung picker offers. The whole survival curve — the single richest object the engine produces — is invisible. | Draw it. See §4.3. |
| `span` · — | **nowhere**; gates `group_cards` via `is_trivial` | \|P(≥k \| leakiest defence) − P(≥k \| meanest defence)\| in likelihood points, over half the 10–90 range of the league's own concession strengths. `None` when the snapshot is too thin, and `None` is never treated as trivial. Measured median 9.5 points; a striker's 1+ rung moves 3.7, his 5+ rung 31.3. | **The single most valuable number in the engine** and the only one a counting tool cannot produce. | Not presented. | See §4.1. |
| `p_prev` / `p_prev_at` · "rose from 66% to 78%" | **P-16 only** | The last `p` for the same `fkey` that differed by ≥ 0.005, carried forward across runs. | Yes — movement is news, and it is the one number that says the engine is alive. | Buried on the one screen a reader visits least, as a sentence in a mixed feed. | Promote. A small delta chip on the card itself ("+12 since Tuesday") is cheap and is exactly what a reader checking back wants. |
| `p_model`, `p_pre_anchor`, `p_raw`, `p_base` · — | **nowhere** | `p_model` = the engine's number before calibration. `p_pre_anchor` = after calibration, before the record blend. `p_raw` = share of his last 10 appearances above `thr` (a *fifth* count of the same thing). `p_base` = for players, identical to `p_usual`; for teams, P(count) from the team offset alone. | Audit fields. Correctly invisible — except `p_base`, which duplicates `p_usual` for players and means something different for teams, which is a trap. | Not presented. | Keep `p_model` (calibration needs it). Drop `p_raw`. Make `p_base` team-only or rename it. |
| `rotation` / `rotation_why` · — | **nowhere** reader-facing (the dead card had "Rotation risk") | `low`/`medium`/`high` from `context.rotation_pressure`, plus one plain sentence. `match_detail` returns it as `d.rotation` with `level`, `why`, `rest_days`, `next_gap`. Nothing renders `d.rotation`. | Yes — "they have Europe on Wednesday" is exactly the kind of thing a reader cannot get from a counting tool. | Not presented. The sentence is already written and already plain English. | Show `rotation_why` in M-04's notes, beside team news, where it belongs. One line of JSX. |
| `p_play_usual` · — | **nowhere** | His chance to play with no calendar pressure, so the shift is visible. | Only as the second half of a pair with `p_play`. | Not presented. | Show only as "84% to play, usually 91% — they play again on Wednesday". Otherwise delete. |
| `reasons[]` · the "why" line / list | card (first only), O-01 (all), dead card | 1–3 sentences from `_reasons` / `_player_reasons`, naming the opponent's tactic and personnel when they matter, built from the grouped `contrib`. | Yes. | The card shows only `reasons[0]`; O-01 shows all. Good escalation. | None. |
| `contrib` · — | **nowhere** (projected out of most queries) | Per-feature log contributions to `mu`. | Developer-only. | Correctly hidden. | Keep hidden. Could seed a "what moved this" breakdown later, but only grouped. |
| `opp_tactics` / `own_tactics` / `opp_key_players` · — | `opp_tactics` only in the dead card; the others nowhere | Tactic labels for both sides, and `[(player, effect on this stat)]` for the opponent's most relevant players. | `opp_key_players` is a genuinely good, genuinely non-trivial finding — "their best tackler is out" — and it reaches the reader only when `_player_reasons` happens to fold it into a sentence. | Not presented. | Surface `opp_key_players` in O-01 as a named row. It is the clearest "we modelled the opponent" evidence the app owns. |
| `p_basis` · "Assumes he plays" | card, when `played`, not confirmed | `"played"` when `cond_play` is on and the line is a player line; `"all"` for the yellow-card model. | Yes — docs/55 is right that saying so stops a careful number reading as a wrong one. | Good. | Fold into the `p_play` sentence so the reader gets one statement, not two. |
| `thr` + `market` · "3+ shots" | everywhere | `market` is built by `engine_bridge.label_for` as `floor(thr)+1` plus the stat's word, or an admin override from `copy.market_labels`. | Yes. | Good. The half-integer `thr` never reaches the reader, which is right. | None. |
| `track` · "2 of 3 so far" / "Happened" / "Did not happen" | M-03 during a live match, card chip | `live_track`: `current` is the figure so far, `needed` is `floor(thr)+1`, `state` is hit/live/missed/unknown. | Yes — this is the app proving itself in real time. | Good. | Show it on **P-03**, which today shows no forecast number at all (§3). |

### 2.2 The combination (P-08, O-05 combo sheet, M-03 "Build one for me")

| Metric | Where | What it actually means | Right metric? | Presented well? | Better alternative |
|---|---|---|---|---|---|
| `chance` · "84%" per line | combo sheet, BuildForMe | `p × p_play` for a player (unless `includes_play`, i.e. the cards model), `p` for a team. Capped to [0,1]. | Yes, and it is the honest number for a combination. | Good — the sheet even explains the gap from the card ("The card says 97% *if he plays*; here we also count the 84% chance he plays"). The best explanatory copy in the app. | Give this quantity the same name everywhere it is computed: here, in `Today.topRated`, and in `tiering.whole`. |
| `combined` · the big combo number | combo sheet, P-08, BuildForMe | Lines grouped by entity: the easiest line times each harder one to the power **0.38** (measured, docs/28 §2); matches multiply plainly; before lineups, times `combo.pre_factors` by entity count (1.00/1.11/1.19/1.25); capped at 0.97. | Yes, and the measurement behind it (237,000 real combinations) is the strongest validation in the product. | Good, and the notes are honest about what is extrapolation. | None. |
| `range.lo` / `range.hi` · "Range 41 to 63%" | combo sheet | `combine(lo)` and `combine(hi)` — the product of the marginal 10th percentiles and the product of the marginal 90th percentiles. | **No.** Multiplying marginal bounds assumes the uncertainties are perfectly correlated, so the band is systematically too wide, and it widens with every line added. | Printed to the point, beside a track bar that draws it. | Either state the assumption ("widest case"), or draw the bands jointly. A band that grows with line count for the wrong reason undermines the one number it sits under. |
| `plain` · "About 7 in 10" / "About 1 in 4" | combo sheet, BuildForMe | `≥0.95` → "Very likely"; `≥0.5` → "About N in 10" with `N = round(c×10)`; else "About 1 in M". | Yes. Frequency framing is more honest than a percentage for a compound event, and it reads as a finding rather than a weak number. | Good. | None. |
| `factor` · — | **nowhere** | The pre-lineup correction actually applied (1.00–1.25). | Yes, for honesty. | Not presented; the sheet says only "a small, tested correction". | Name it: "we added 11% for the lineups not being out". It is the app showing its work. |
| `weakest` · the highlighted row | combo sheet | `min(chance)` line's id. | Yes — actionable. | Good. | None. |
| `matches[].combined` · per-fixture number | combo sheet, when >1 match | `_one_match` for that fixture alone. | Yes. | Good. | None. |
| `result.reached` / `of`, `actual` · "Reached 2 of 3", "Had 4" | P-08 finished tab | `forecast_outcomes.reached` = `actual > thr`; `actual` is the real figure. `played === false` → "Did not play". | Yes. Settling in public is the product's argument. | Good, and the `null` → dash (never a cross) rule is right. | None. |
| Summary `allHit`, `hit/lines`, `expected` · "From our chances we expected about 1.8 combos" | P-08 | Client-side over settled combos: `expected = Σ combined`. | Yes, and the small-sample caveat is well judged. | Good. | None. |

### 2.3 Match page (P-02 / M-01…M-05)

| Metric | Where | What it actually means | Right metric? | Presented well? | Better alternative |
|---|---|---|---|---|---|
| `probs.p_home` / `p_draw` / `p_away` · the W/D/L bar | P-01 rows, P-11 rows, M-hero, share image | Dixon-Coles outcome probabilities, times the match-context multipliers (`MATCH_CONTEXT_COEF`) and the xG blend. **Not** calibrated. | Yes. | Good: colour plus printed numbers, and `WdlBar` prints an aria label with all three. The draw percentage is drawn but only labelled in the aria text. | Print the draw number too; a reader comparing two fixtures needs all three. |
| `probs.xg_home` / `xg_away` · "Expected goals 1.7 – 1.2" | M-hero | The strength model's λ for each side, after context and xG-blend multipliers. | Yes, and it is the one place the app says what it thinks the *shape* of the match is. | 1 dp is right. But it sits in the footer as small grey text, below the referee, while the thing it explains (the W/D/L bar) is above it. | Pair it with the bar. "1.7 – 1.2 expected goals" is the sentence the bar is a picture of. |
| `probs.context.mult_home` / `mult_away` · — | **nowhere** | The multiplier results form and stakes applied to each side's goals. | Only as an explanation. | Not presented. | The `context.why` sentences already cover this in M-04. Leave the numbers out. |
| Score, `recap.ht` · "2 – 1", "Half-time 1 – 0" | M-hero | From `matches.hg/ag` once final, else the live feed; half-time from SportAPI or goal minutes ≤ 45. | Yes. | Good. | None. |
| `recap.hit` / `scored` / `by_tier` · "How our forecasts did: 9 of 12 … Strong 4/4 · Solid 5/8" | M-hero when final | Over this match's Strong+Solid lines with an outcome and `player_played != False`. | Yes. The single most persuasive thing on a finished match. | Good. | Say the stated figure too: "9 of 12 — we said about 10". That is the calibration claim, in situ. |
| `insight_count` · "14 lines" / the "With insights" chip | P-01, P-11 | Count of Strong+Solid lines for the match. | **No** as a chip — docs/redesign/v2 already found that every fixture has a similar number, which is why `best_line` replaced it. It survives as the fallback and as the filter. | It is now the *fallback* when `best_line` is missing, so it appears exactly where the app has least to say. In `Today.Group` a sum `n` of it is computed and never used — dead code. | Delete the chip fallback (show nothing). Keep the count only as the P-04 answer line, which labels it properly. Remove the dead `n`. |
| M-03 tab badge · "Forecasts 11" | M-03 | Cards with `p ≥ 0.5`. | No — a third count rule (finding 9). | Unlabelled. | Use `insight_count`. |
| `best_line` · "R. Højlund 3+ shots 72%" / "happened" | P-01 rows, P-11 rows | The match's highest-`prominence` Strong/Solid line, with `who`, `market`, `p`, and once final `reached`. | **Yes — the best recent change in the product.** It makes the fixture row say something instead of counting. | Good, including flipping to "happened" / "did not" after the whistle. | One mismatch: P-01's Top 3 above these rows is ranked by `tier` then `p × p_play`, not by `prominence`, so the row and the card above it can disagree about which line in a match is best. Rank both on `prominence`. |
| `live.minute`, `live_count` · "67'", "4 live now" | P-01, P-03, M-hero, live pill | SportAPI. | Yes. | Good. | None. |
| `h2h.a_wins` / `draws` / `b_wins` · "3 / 2 / 5" | M-05 | Over the last 10 meetings we hold, either venue. | Marginal. It is the purest counting-tool number in the app and the thesis says it is table stakes. | Clear. The window (10) is not stated. | Keep but demote, and state the window. Or make it earn its place: "we expect 1.7 – 1.2 tonight; in these meetings they have averaged 1.2 – 1.4". |
| Event counts · "Goals 2 / Cards 4 / Subs 6" | M-02 | Counted client-side from `events`. | Yes for a recap. | Good. | None. |
| `Momentum` · a two-segment bar | live card (O-05 / live sheet) | Count of events per half per side — goals, cards **and** substitutions pooled. | **No.** Substitution counts are not momentum. The label claims an analytical quantity and delivers an event tally. | No numbers at all, only an aria label. | Either compute something that is momentum (shots or the live `track` counts by half), or rename it "Events by half". |
| `edges[]` · "12.7 … Shots … 10.4" with a lean bar | M-05 Form, P-07 | `team_insights.matrix` → `_avg`, the **per-game mean over the season (or last 5)**, rounded to 2 dp, with `lean` to the better side. `as_fixture` splits it into home-only and away-only. | Yes for a preview. | **Three precisions for one field across the app**: M-05 renders it with `num1` (1 dp), P-07 renders `{e.a}` raw (the stored 2 dp), P-11's team matrix uses its own `fmt` (1 dp). | One formatter, 1 dp. A per-game average over 8 matches does not support 2 dp. |
| `radar[]` axes · a six-spoke shape | M-05, P-07 | Each axis is the club's **percentile within its own league** (0–1, 3 dp) of an opponent-adjusted `RatingsModel` rating, not a raw average. Defence is negated so outward is better. Missing → drawn at 0.5. | Yes, and the opponent adjustment is the right call (the comment explains why a raw average flatters a soft schedule). | Mostly good: the "What the spokes mean" disclosure and the thin-sample warning are both right. Two issues: the aria label says "67 out of 100" when the underlying granularity in a 20-club league is 1/19 ≈ 5 points; and a missing axis is drawn at mid-way, indistinguishable from a genuinely average club. | Say "11th of 20" rather than "out of 100". Draw a missing axis as a gap, not a value. |
| `styles.tactics[]` · tactic chips | M-05, P-12 | Tactic keys whose `tactic_z` ≥ 1.0. | Yes. | Good. | `tactic_z` itself is stored and never shown; a chip with "+1.8" would say how pronounced the style is. Low priority. |
| `context.situation` · "Relegation fight" chips | M-hero, M-04 | `stakes` booleans: `dead` / `rel` / `race`. | Yes — this is modelled (`MATCH_CONTEXT_COEF`) and shown, which is the right pairing. | Good. | None. |
| `context.form_vs_expected` (`form_fp`), `games_left` · — | **nowhere** | Points in the last 5 league games **minus the points the model expected** — a genuinely model-derived form number, not a W/D/L streak. `games_left` is matches remaining. | `form_fp` is excellent and is exactly the kind of number the thesis calls for. | Not presented at all, while `FormPills` (plain W/D/L) is shown on P-12. The app shows the counting version and hides the forecasting version. | **Show `form_fp`.** "Four points better than we expected over their last five" beside the W/D/L pills. See §4.4. |
| `rotation.rest_days` / `next_gap` / `next_comp` / `n14` · — | **nowhere** | Days since the last match, days to the next, the next competition, matches in 14 days. | Yes as the evidence behind `rotation_why`. | Not presented. | Show `rest_days` / `next_gap` as the fine print under `rotation_why`. |
| `availability[]` · "Out" / "Doubtful" + reason | M-04 | `availability.public_list` — feed or admin. | Yes. | Good. | None. |
| `predicted` XI `p_play` · "84%" by each head | M-04 | `queries.predicted_xi`: for each player the **max `p_play` across his lines**, keeper taken from the most-started GK in the last 10. | The eleven is right; the field is wrong (finding 6). | Label wrong, ordering wrong, and `pp < 0.7` greys the marker — a threshold that appears nowhere else. | Rank and label on `p_start`. Drop the 0.7 grey or align it with `likely_starter_p` 0.85. |
| `referee.sentence` · "X gives about 9% more cards than the teams would usually pick up" | M-hero, M-04 | `referees.sentence` from `factor`; below 5 matches it says so and treats him as average. | Yes, and the "few matches so far" branch is honest. | Good — the best-calibrated piece of copy in the product. | None. |

### 2.4 Team, league and player screens

| Metric | Where | What it actually means | Right metric? | Presented well? | Better alternative |
|---|---|---|---|---|---|
| `squad_grid` cell `v`, `avg` · the grid and its "Avg" column | P-12 Squad/Grid, M-05 Players | The stat in each of the **team's** last N games (not each player's), and the mean over non-null, non-hidden cells. | Yes. The "team's last N" choice is subtle and right — it makes the columns line up. | Good, and letting the reader exclude a game from the average is a genuinely thoughtful control. The exclusion is client-side and unlabelled in the average's header. | Note the exclusion in the column header ("Avg of 8"). |
| `team_totals` `for` / `against` · paired bars | P-12 Numbers | The raw per-match figure and the opponent's, last N, 1 dp. | Yes. | Good. | None. |
| `against_by_position` `per_game` / `per_player_game` · "3.2 per game · 0.8 per player" | P-12 | Opponents' players' totals for the stat against this club in its last N games, divided by games and by player-games. | Yes, and it is the closest reader-facing thing to the engine's own `opp_pos` factor. | Both numbers in one tile with no explanation of why there are two. `per_player_game` divides by player-games, which varies with squad rotation, so it is the less stable of the two. | Show `per_game` only. Keep `per_player_game` behind the tile. |
| `squad_season` apps / starts / minutes / goals / shots / tackles / yellow_cards | P-12 Squad/Cards | Season totals for this club, `Math.round`ed. | Yes as orientation. | Good, dense, legible. | None. |
| `leaderboard` `total` / `per90` | P-11 Leaders | Season totals, or total × 90 / minutes, over players with ≥ 450 minutes. | Yes. | 1 dp via `num1`. The 450-minute floor is stated in the empty state only. | State the floor in the table caption, not only when empty. |
| `player_ranks` · "3rd of 61 · shots · 2.41" | P-13 | Per-90 rank this season among players with ≥ `min_minutes` 270 (3 games), `per90` rounded to **2 dp**. | Yes — a rank is more legible than a rate. | **2 dp on a 3-game minimum is dishonest** (270 minutes of shots at 2 dp implies a precision of one shot per 37 games). The floor is printed, which is good. | 1 dp. And print the rank as a fraction of a stated population, which it already does well. |
| `player_history.reached[stat][t]` · — | **nowhere** | For the shown window, games with the stat ≥ t, for t in 1..5, plus `games`. | Redundant: O-02 recomputes `hits` itself from the rows. | Not presented. | Delete, or use it instead of the client-side recount so the two can never disagree. |
| `team_form` · W/D/L pills | P-12, P-02 | Last 5 results. | Table stakes. | Good as orientation. | Pair with `form_fp` (§4.4) so the pills gain a forecast meaning. |
| Standings P/W/D/L/GD/Pts | P-11 Table | Computed **in the browser** from up to 400 finished fixtures, 3-1-0. | Yes. | Good, with zone legends. Client-side computation means it can disagree with any official table over deductions and ongoing appeals. | Say where it comes from: "from the finished matches we hold". |
| team-matrix `values` + `pct` heat | P-11 Teams | `values` = per-game means (2 dp stored, 1 dp shown); `pct` = within-league percentile by value, 3 dp, ties split. | Yes. | Good. The heat scale carries `pct` and the cell carries `values`, which is the right pairing. | Unify the formatter with P-07 / M-05. |
| `first_goal` `scored_first` / `conceded_first` / `goalless`, `after_scoring` W-D-L, `scorers[].n` | P-12 Numbers, M-05 | Over the last 20 finished matches with a `first_goal_side`. | Yes, and "what happened next" is a good second-order question. | **One real bug:** the "Conceded first" percentage is computed as `100 − round(scored/played×100) − round(goalless/played×100)` — a residual of two rounded numbers, so it can be 1–2 points away from `conceded_first / played` and can disagree with the bar beside it. | `pc(d.conceded_first, d.played)`, like the row above it. |
| `search.next.p` · "Next 84%" | P-18 (and the search overlay) | The soonest upcoming player line's `p`, with `market` and `tier`, from an aggregation taking `$first` by kickoff then `p`. | A bare percentage with the line only in a `title` attribute is not a metric, it is a number. | **Badly.** "Next 84%" with no market visible is unreadable, and on touch there is no hover to reveal it. | Show the market, or show the tier badge alone. |

### 2.5 Referees (P-14, P-15, P-11 Leaders → Referees, M-hero)

| Metric | Where | What it actually means | Right metric? | Presented well? | Better alternative |
|---|---|---|---|---|---|
| `yellow_pg` / `red_pg` / `pens_pg` · "Yellows a game 3.47" | P-11, P-15 (`per_game.*`) | Events of that type across his matches, divided by **matches with event data** (`with_events`), from `match_extras.rebuild_referees`. | The raw average is the wrong metric and `referees.py` says so in its own docstring: on 5,295 matches it made card forecasts **worse** (z −4.5). | **Worst presentation in the product.** 2 dp. Denominator is `with_events`, but the adjacent "Games" column prints `matches`. P-15 prints `with_events` in the header sentence and then uses it silently as the divisor. | Show `cards_per_game_normalised` as the headline, 1 dp, with the plain figure and the real denominator as fine print — which is exactly what P-14 already does. |
| `cards_per_game` · "3.2 plain" | P-14 | Yellow cards of **both teams** from `team_match_stats`, divided by **all** his matches. | Shown correctly as the plain comparison. | Good — 1 dp, labelled "plain", subordinate to the normalised figure. | Make this the only plain figure in the app and delete `yellow_pg` from the reader's view. |
| `cards_per_game_normalised` · "3.4" | P-14 | `league_cards_per_game × factor`. | **Yes — this is the right metric** and it is the one the app hides on two of its three referee screens. | Good on P-14. | Use it on P-11 and P-15 too. |
| `factor` · "+9%" / "−6%" | P-14, and the M-hero sentence | `(cards he gave + 80) / (cards the teams were predicted to give + 80)`, his older games faded (half-life 60), one game capped at the league 99th percentile. Shrinks to 1.0 for a referee with few games. | Yes. It is the one referee number that controls for who he was given. | Good: a signed percentage with a colour, and a column header that explains it ("vs teams' usual"). | None. |
| `home_win_pct` · "48%" | P-11 | His matches the home side won, over **all** his matches. | **No.** A referee's home-win share is noise at any sample this app holds, and presenting it in a table of his tendencies invites a causal reading. | Whole percent, no sample caveat. | Remove. If kept, print it against the league's own home-win share so it reads as "the same as everyone else", which it will. |
| `matches` / `with_events` · "20 matches on record, 6 with card data" | P-15 header | Two denominators. | Yes, and P-15 states both. | P-15 is honest; P-11's table is not (above). | Carry P-15's sentence into P-11. |
| booking-risk `p` + `rank` · "84%" with a bar | P-11 Bookings, P-16 | The `yellow_cards` line from `cards_model`, highest first, each player's next match only. These lines have `p_basis: "all"` — `p` **already includes** the chance he plays. | Yes. | The bar is fine. But these cards have **no `p_usual`, no `edge`, no `span`**, so on P-04 they lose the entire comparison row, the run direction and the triviality gate. The reader sees a bare percentage where every other market gets a claim. | Give `cards_model` an `expected_usual` / `p_usual` pair and a span. Its `lo`/`hi` are also fabricated (λ×0.8 and λ×1.2 — a flat ±20% on the rate), so the printed range is not a credible interval. |

### 2.6 Track record (P-17) and the Finder (P-05)

| Metric | Where | What it actually means | Right metric? | Presented well? | Better alternative |
|---|---|---|---|---|---|
| `bins[].stated` / `actual` / `n` · the said-vs-happened chart | P-17 | Over `forecast_outcomes` with `player_played: True`, bucketed by `p` in 0.1 steps from 0.5 to 0.9, ≥ 30 per bin: `stated` = mean `p`, `actual` = share reached. | Yes. This chart is the product's licence to exist. | Good: diagonal, dot area by `n`, and an aria label with every pair. | Two gaps. The bins start at 0.5, so the sub-50% lines the P-04 slider now reaches (floor 0, deliberately, docs/52) can never be reported on. And `player_played: True` is the wrong filter (finding 4). |
| Headline · "When we say 82%, it happens 79% of the time" | P-17 | The bin with the largest `n`. | Yes, and choosing by `n` rather than by a fixed band is right. | Good. | None. |
| `Reliability` margin · "±7 points" | P-17 | `1.96 × sqrt(stated(1−stated)/n)`, then says whether the gap exceeds it, and names the direction. | **Yes — the best-reasoned number in the app.** It stops a reader assuming the worst from a gap that is sampling noise. | Very good, including "we are promising less than we deliver" for a favourable miss. | Minor: the SE treats the bin as one Bernoulli at `stated`, ignoring the spread of `p` inside the bin, so it is slightly optimistic. Negligible at these widths. |
| `tiers[t].actual` · "92 of 100 came true" | P-17 | Share reached among scored outcomes with that tier, rendered "of 100" at n ≥ 100 and "k of n" below. | Yes, and the of-100 framing is right. | **`tiers[t].stated` is computed by the backend and never shown.** So the tier cards say how often it happened and never what we claimed — the one comparison the page is about. | Print both: "Strong: we said about 91%, it happened 92 of 100." |
| `scored`, `needed`, `since` · "We show the record once 300 forecasts have been scored. 180 so far." | P-17 | Totals, with a progress bar. | Yes. Refusing to show a record until it means something is the right instinct. | Good. | None. |
| `reached` / `games` · "6/10" or the hit strip | P-05 form mode, P-04 history clause | Of the last `last_n` games with a figure, how many reached the threshold. **Requires only `min(last_n, 3)` games.** | Yes — the Finder is explicitly a history tool and should count. | **P-04's clause label lies about the window.** "in 6 of their last 10" sends `min_reached = 0.6` and matches anyone at 60% of *however many games exist*, which can be 2 of 3. | Either enforce the stated window or label it as a share ("in at least 60% of their last 10"). |
| `run` · "4 in a row" | P-05 run mode | The current unbroken streak at or above the threshold, newest first. | Yes. | Good. | None. |
| `HitStrip` squares · "7/10" | P-05, P-26 | Ten filled/empty squares plus the fraction. | Superseded. `Marks.jsx` says so itself: ten identical marks are "a picture of nothing". | It survives on P-05 while P-04's cards use `CardRun`. | Replace with `RunStrip`, which was written for exactly this and which **no screen imports** — the better component is dead and the worse one ships. |
| Finder usage meter · "3 of 5 searches left today" | P-05 | Entitlement counter. | Yes. | Good, including the reset time. | None. |

---

## 3. Metrics we compute but never show

Read from the `Forecast` dataclass, the stored `forecasts` document in `engine_bridge.run_league`,
and `match_detail`'s return value, cross-checked against a grep of the whole frontend.

| Field | What it is | Worth showing? | What it would be worth |
|---|---|---|---|
| **`span`** | Likelihood points this rung moves between the league's leakiest and meanest defence. Median 9.5; a striker's 1+ rung 3.7, his own level 31.3. | **Yes — the highest-value unshown number in the app.** | It is the product's thesis as a number. See §4.1. |
| **`ladder`** | The whole survival function, 4–16 rungs, calibrated, on every kept line. | **Yes.** docs/50: 20 of 20 cards had an interesting rung on the ladder, 0 of 20 showed one. | See §4.3. |
| **`expected`** | The expected count for *this* fixture. | **Yes.** | The card already prints `expected_usual` ("normally 2.4") with no counterpart. One number closes the sentence. See §4.2. |
| **`form_fp`** (match_context) | Points in the last 5 minus the points the model expected. A fitted quantity (`MATCH_CONTEXT_COEF`, 46,000 matches). | **Yes.** | The app shows plain W/D/L pills and hides the model's own form measure. See §4.4. |
| **`rotation`, `rotation_why`, `rest_days`, `next_gap`, `next_comp`, `n14`** | Calendar pressure, with a ready-written plain sentence. | **Yes, `rotation_why` at least.** | "They play in Europe on Wednesday, so regulars may be rested" is a reason no counting tool has. One line of JSX in M-04. |
| **`opp_key_players`** | `[(player, effect on this stat)]` — the opponent's players who most move this number. | **Yes.** | The clearest evidence that the opponent was modelled. Reaches the reader today only if `_player_reasons` happens to phrase it. |
| **`p_play_usual`** | Chance to play with no calendar pressure. | Only paired with `p_play`. | "84% to play, usually 91%" makes the rotation story numeric. |
| **`tiers[t].stated`** (P-17) | What we claimed, per tier. | **Yes.** | Without it the tier cards are half a calibration statement (§2.6). |
| **`tactic_z`** | How many SDs each tactic index is from the league mean. | Marginal. | Would let a chip say "a pronounced low block" rather than "a low block". |
| **`player_history.reached`** | Games at or above each of 1..5 in the window. | No — O-02 recomputes it. | Delete, or use it so the two cannot disagree. |
| `usual_p` / `usual_n` | Last-10 empirical share. | No — the strip shows it. | Delete; it is also a naming hazard (finding 1). |
| `p_raw` | A fifth count of the same last-10 share. | No. | Delete. |
| `p_base` | Team: offset-only probability. Player: **identical to `p_usual`**. | No. | Make team-only or rename. |
| `p_model`, `p_pre_anchor` | Pre-calibration and pre-anchor numbers. | No — audit fields. | Keep stored, keep hidden. |
| `contrib` | Per-feature log contributions. | No. | Keep hidden; it already feeds `reasons`. |
| `probs.context.mult_home/away`, `xg_mult` | The context and xG multipliers applied. | No — `context.why` says it in words. | Leave out. |
| `combo.factor` | The pre-lineup correction actually applied. | **Yes, in words.** | "We added 11% because the lineups are not out" is the app showing its work, and it already claims the correction exists without quantifying it. |
| `thr_personal`, `is_personal`, departure tiers | Only meaningful with `engine.personal_lines`, which is **off**. | Blocked on finding 3. | Do not ship until the tier ambiguity is resolved. |

**Also unshown, by screen:** **P-03 Live** draws no forecast number whatsoever, while
`live_track` already produces `current` / `needed` / `state` per line and M-03 draws it. A live
scores page that cannot say "he needs one more shot" is the app's best moment, missed. (docs/57 §7
notes P-03 has never been rendered in review; this is a second reason to fix that.)

---

## 4. Metrics we don't have and should

### 4.1 Show `span` — "this line can move"

Already computed on every line; no new modelling. Three forms, cheapest first:

1. **A sentence in O-01.** "Against the meanest defence in the league this is 58%; against the
   leakiest, 79%." Two numbers the engine already has (`p ± span/2` in effect, or recomputed
   exactly). This is the single clearest statement the app can make that a counting tool cannot.
2. **A mark on the card's bar.** The bar already draws the band and the usual tick; a faint
   whisker for the span turns it into "here is how much the opponent matters".
3. **A chip, only at the top end.** "Moves 31 points by opponent" on the lines where it is large.
   Never show it when small — that is the gate's job, silently.

Why: docs/56 argues that insensitivity, not likelihood, is what makes a line useless, and the app
acts on that belief behind the reader's back. Showing it converts a hidden ranking rule into the
product's visible argument.

### 4.2 Close the count sentence: `expected` beside `expected_usual`

The card says "his average 2.4" and never says what it expects tonight. One field, already stored,
already 1 dp. `tonight 3.1 · normally 2.4` is a complete, legible claim in nine characters, and it
is the same claim as `p` vs `p_usual` in units a reader thinks in.

### 4.3 Draw the ladder

The stored `ladder` is the full survival function and nothing renders it. Two cheap renderings:

- **A rung list in O-01**, every rung with its likelihood, the chosen one marked. This is a
  three-line component and it answers "what about 2+?" without a round trip. O-02 already resolves
  `p` from the ladder for its picker, so the data path exists.
- **A small curve on the card.** The ladder's shape *is* the player: a flat ladder is a metronome,
  a steep one is a boom-or-bust forward. No other screen says this.

### 4.4 Show `form_fp` — form against expectation

Stored per club per match, never drawn, while the plain W/D/L pills are on P-12 and M-05. "Six
points better than we expected over their last five" is a forecasting statement; "W W D L W" is a
counting one. This is the clearest case in the audit of the app showing the table-stakes version of
a number it already owns the differentiated version of.

### 4.5 Metrics the engine could produce cheaply and does not

| Proposal | Cost | Worth |
|---|---|---|
| **Ladder percentile of the shown rung.** "This is his 2nd-lowest rung of 6." | Free — `ladder` is stored. | Directly measures docs/50's complaint. It would also have caught the regression docs/50 found, on the card, visibly. |
| **Movement since the last run, on the card.** `p_prev` is stored and drawn only on P-16. | Free. | The only number that proves the forecast is live rather than a table. |
| **Stated-vs-happened for *this* line's bucket, on the card.** `tiering.Record.earned` already computes it and uses it to demote. | Free — it is in `tier_note` only when it demotes. | "We have said this about 140 times; it happened 83% of the time." Trust, at the point of reading, not on a separate page. |
| **Opponent rank for the relevant concession dimension.** "Their defence concedes the 3rd-most shots in the league." `snap[0][:, dag]` already holds it; the radar already turns such ratings into percentiles. | Small. | Makes the matchup claim concrete, and it is what a reader checks before trusting a departure. |
| **Per-90 on the run strip.** `_usual` already carries minutes "so the card can show the same ten games per 90 without asking anyone to do the arithmetic" — and nothing does. | Free. | Removes the one systematic misreading the strip invites. |
| **Combined "chance it happens" on the card, optional.** `p × p_play` is computed in three places and shown only in the combo. | Free. | It is the number the tier is earned on, so showing it would make every "Solid at 97%" self-explanatory. |
| **A calibrated band width as a word.** The band is printed and explained; its width is never characterised. | Free. | "Fairly sure" / "not sure" from `hi − lo` gives the band a meaning at a glance. |

---

## 5. Metrics we show but should not

| Metric | Where | Why it should go |
|---|---|---|
| **`insight_count` as a chip** ("14 lines") | P-01, P-11 fallback | Already found useless by the v2 critique, which is why `best_line` exists. It now appears only where `best_line` is absent, i.e. where there is least to say. Show nothing instead. Also delete the dead `n` sum in `Today.Group`. |
| **M-03's tab badge count** (`p ≥ 0.5`) | M-03 | A third counting rule for one thing, with no label. Use `insight_count` or nothing. |
| **`home_win_pct`** | P-11 referees | Noise at every sample this app holds, presented in a table of a referee's tendencies, inviting a causal reading. |
| **`yellow_pg` / `red_pg` / `pens_pg` at 2 dp** | P-11, P-15 | Wrong metric (the raw average is measured to make forecasts *worse*), wrong denominator beside the stated "Games", and two decimal places on single-digit samples. |
| **`per_player_game`** | P-12 Against | Second number in a tile with no explanation of why two exist; its denominator moves with rotation. |
| **`combo.range`** | combo sheet | The product of marginal bounds is not a joint interval and widens with every line for the wrong reason. Suppress or label as a worst case. |
| **`lo`/`hi` on `match_goals` lines** | M-03, P-01 chips | A hard-coded ±6 points, printed under copy that says the width means something. |
| **`lo`/`hi` on `cards_model` lines** | P-11 Bookings, P-04 | λ×0.8 / λ×1.2 — a flat ±20% on the rate, not a credible interval. |
| **`HitStrip`** | P-05, P-26 | Superseded by `RunStrip`, which `Marks.jsx` wrote to replace it and which **nothing imports** — `RunStrip` is dead code and `HitStrip` is still the one on screen. The component's own comment says ten identical marks are "a picture of nothing". |
| **The "If he plays" tile** | O-01 | Identical to the header number under the default config (finding 7). |
| **Second record statement** (`rec_k`/`rec_n` at 40 games) | O-01 | Contradicts the 10-game strip two inches above it (§2.1). Keep one window. |
| **`usual_p`, `usual_n`, `p_raw`** | shipped, not drawn | Payload and a naming hazard. The strip already says it. |

---

## 6. Precision: how many digits are honest

| Metric | Now | Honest | Why |
|---|---|---|---|
| `p` | whole % | whole %, capped at "95%+" | Calibration caps at 0.97, `p_cap` at 0.985, display at 0.95. Pick 0.95 and apply it once. |
| `lo` / `hi` | whole %, to the point | nearest 5, with the coverage stated | 10/90 percentiles from 60 draws carry ~±2 points of Monte-Carlo error. |
| `edge` / `dep` | whole points, no unit | whole points, with a unit word | The number is fine; the label is missing. |
| `expected`, `expected_usual` | 1 dp | 1 dp | Right. |
| `xg_home` / `xg_away` | 1 dp | 1 dp | Right. |
| `team_insights` per-game values | 2 dp stored; 1 dp on M-05 and P-11; **2 dp raw on P-07** | 1 dp everywhere | A mean over 8–30 matches does not support 2 dp, and three renderings of one field is worse than any of them. |
| `per90` (player ranks) | 2 dp | 1 dp | 270-minute minimum. |
| Referee per-game | 2 dp | 1 dp, with the real denominator | Samples of 5–20 games with event data. |
| `cards_per_game_normalised` | 1 dp | 1 dp | Right. |
| `factor` | whole % signed | whole % signed | Right, and shrunk toward 1.0, so it is safe. |
| Radar axes | drawn 0–1, aria "out of 100" | "11th of 20" | Percentile granularity in a 20-club league is ~5 points. |
| `combined`, `plain` | whole % + a frequency | both | Right. |
| Track-record `stated` / `actual` | whole % | whole %, with `n` and the margin | Already done, and done well. |
| FirstGoal "Conceded first" | residual of two rounded numbers | `pc(conceded_first, played)` | A straight arithmetic bug. |

---

## 7. Two numbers on one screen that answer one question differently

Collected, because this was the brief's specific ask.

| Screen | The two numbers | Why they differ |
|---|---|---|
| **O-01** | header `pct(p)` and the "If he plays" tile | Identical under the default config; the divide-by-`p_play` branch never fires (finding 7). |
| **O-01** | "6 cleared 3+ · Last 10" (strip, via the card) and "27 of his last 40" | Two windows, 10 vs 40 appearances, neither labelled as a choice. |
| **The card** | "Usual 57%" and "his average 2.4" | A probability and a count, from two different baselines (`p_base` vs `mu_usual_p`), side by side with no unit words. |
| **The card** | "Usual 57%" (correct label) vs O-01's "A player like him in a fixture like this: usually 57%" (wrong label) | One field, two descriptions, one false. |
| **P-01** | the Top-3 cards (ranked `tier`, then `p × p_play`) and the fixture rows' `best_line` (ranked `prominence`) | Two definitions of "the best line in this match", on one screen, three inches apart. |
| **P-04 vs M-03** | "Minimum likelihood" filtering `max(p, best_p)` vs `p` | Same control, same label, different field (finding 8). |
| **P-04** | the sort "biggest change" (log-odds `lift`) and the card's "+12" (points) | A feed whose order visibly contradicts the number it is ordered by. |
| **P-01 / P-11 / M-03** | `insight_count`, the M-03 badge, and the group headers | Three counting rules for "how many lines" (finding 9). |
| **P-11 / P-14 / P-15** | `yellow_pg`, `cards_per_game`, `cards_per_game_normalised` | Three numbers for "how many cards does this referee give", two precisions, two denominators (finding 10). |
| **P-07 / M-05 / P-11** | the same `edges` / `values` field at 2 dp, 1 dp and 1 dp | Three formatters for one field. |
| **P-12 FirstGoal** | the split bar and the "Conceded first" percentage | The percentage is a rounding residual and can disagree with the bar. |
| **P-05 vs P-04** | `p_display` "95%+" vs a stored line printing "97%" | Two display ceilings for the same quantity. |
| **P-17** | "Strong: 92 of 100 came true" and the Strong badge on a card | The page scores played-only "if he plays" numbers; the badge is earned on the whole chance including non-appearances (finding 4). |

---

## 8. Labels that misdescribe their number

| Label | Field | What it actually is |
|---|---|---|
| "A player like him in a fixture like this: usually 57%" (O-01) | `p_usual` | **Him**, against an **average** opponent. |
| "his average 2.4" (card) | `expected_usual` | A forecast of his count in tonight's minutes against an average opponent. |
| "he starts 41% of the time" (card) | `p_start` | His chance of starting **this** match. |
| "Predicted eleven, with each player's chance to start" (M-04) | `p_play` | His chance of **featuring**. `p_start` exists for exactly this distinction. |
| "biggest change" (P-04 sort) | `lift` on log-odds | Not the change the card prints. |
| "in 6 of their last 10" (P-04 history clause) | `min_reached` 0.6 | 60% of however many games exist, minimum 3. |
| "Momentum" (live card) | event counts per half | Goals, cards **and substitutions**, pooled. |
| "Games 20 · Yellows a game 3.47" (P-11) | `matches` and `yellow_pg` | The 3.47 is divided by `with_events`, not by 20. |
| "That range is how sure we are: the wider it is, the less sure the forecast" (O-01) | `lo`/`hi` | True for most markets; false for `match_goals` (constant ±6) and for `cards_model` lines (flat ±20% of λ). |
| "Forecasts 11" (M-03 badge) | cards with `p ≥ 0.5` | Not the same count as "11 insights" anywhere else. |

---

## 9. Copy compliance

Every wording proposed in this document was checked against `backend/textguard.BANNED`
(`bet`, `odds`, `wager`, `stake`, `parlay`, `picks`, `props`, `hit rate`, `units`, `locks`,
`bankers`, `tipsters`, `punters`, and their variants). None of the proposed strings contains a
banned term. Two existing items are worth flagging:

- **`team_insights.compare` emits "Clear edge to <club>"** into `stands_out`, which is reader-facing
  on P-07 and M-05. "Edge" is not in `BANNED`, so it passes, but it is the most betting-adjacent word
  in the product's own copy. "Clear advantage to <club>" costs nothing.
- **`tiering.anchor`'s docstring says "hit rate"**, and `tests/selftest_prominence.py` uses it too.
  Not reader-facing, so textguard never sees it, but the banned vocabulary is alive in the codebase
  and will leak into a label eventually. The reader-facing word for this quantity is "record".

**And a gap in the guard itself.** `frontend/src/pages/DevKit.jsx:45` renders a heading reading
`Hit-rate strip`. Both guards match the phrase `hit rate` with a space, so the hyphenated form
passes: `node frontend/scripts/check-copy.js` reports "copy check passed" today. P-26 is
developer-only and unlinked, so the exposure is small, but the hole is not: add `[- ]` to the
`hit rate` alternative in **both** `backend/textguard.py` and `frontend/scripts/check-copy.js`, or
the next hyphenated banned term reaches a live screen unchallenged.
