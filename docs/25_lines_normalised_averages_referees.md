# 25. Forecasts fitted to each player and team, normalised averages, referees

Written 2026-10-28, after the owner asked three things:
1. Why every forecast is "12+ shots" or "5+ corners", and why player forecasts all look the same.
2. Why a likely starter at 73% is only "Watch" while a team at 67% is "Solid".
3. That one big game (22 shots, an 8-card match) should not drag an average: every average must be normalised, for teams, players and referees.

**Short answer:**
- The engine's numbers were real all along.
- The questions we asked it were fixed and the same for everyone.
- The feed sorted the obvious answers to the top.
- The team averages behind every forecast counted a game from three seasons ago as much as last week's.

We changed all four. Every change was tested on real matches before it went in.

---

## 1. What we changed, in one table

| Before | Now | Setting |
|---|---|---|
| 7 fixed lines for everyone: team 12+ shots, 5+ corners; player 1+/2+ shots, 1+ on target, 2+/3+ tackles | **Automatic lines.** The engine scores a ladder (player shots 1+ to 6+, tackles 2+ to 6+, team shots 7+ to 23+, corners 2+ to 11+, and so on). For each player or team we keep the lines between 50% and 95%, the 3 most ambitious. | `engine.auto_lines`, `engine.player_ladder`, `engine.team_ladder`, `engine.line_band`, `engine.max_lines_per_stat` |
| Feed sorted by "most likely": near-certain picks on top | **Sorted by lift over usual**: how much this match moves the player's or team's own normal number. "Most likely" and "kick-off" stay as options. | `engine.feed_sort`, route `?sort=` |
| A 96% "1+ shot" could lead a card | Lines above 93% never lead while another line can. They stay inside the card. | `engine.feed_max_p` |
| The card led with the best tier, so a Strong "1+ shot" beat a Solid "3+ shots" | The card leads with the **boldest line still Solid or better**, in the stat that moved most from usual. Strong and Solid rank together in the feed, by lift over usual. | none |
| Before lineups a player could never be Solid or Strong | A **likely starter** (85%+ chance to play) can be Solid or Strong before the lineup. Others say "Watch until lineups are out". | `engine.likely_starter_p` |
| Every player of a club had the same reason ("The team's own style produces more shots") | A player's card leads with a reason about him (his share of the team's shots, limited minutes, the opponent's lineup), then at most one team reason | none |
| Labels had to be typed for every line | Labels are built ("4+ shots", "7+ corners", "2+ shots on target"). An admin label still wins. | `copy.market_labels` (optional) |
| Team averages: all games of about 3 seasons count the same, judged as raw counts | **Normalised:** recent games count more (half-life 20 games); each game is judged against what that opponent usually allows; one game is capped at the league's 99th percentile | `engine.style_half_life`, `engine.style_opp_adjust`, `engine.style_cap_q` |
| Player tackle averages moved too much with one big game | Stronger prior for tackles (80 instead of 40). Shots and on target stay at 40 (best as they were). | `engine.player_prior` |
| Referees: nothing in the backend computed them; a plain average is what people usually show | **Normalised referee factor**: the referee's cards against what the two teams usually get, shrunk to average, older matches fading, one wild match capped. A daily job writes `referee_stats`. The match page gets a referee line. | `referees.prior_cards`, `referees.half_life`, `referees.cap_q` |

---

## 2. What "normalised" means here, in plain words

An average is normalised when one unusual game cannot drag it far. We use four guards, the same idea for every metric:

1. **Recent games count more.** A team's game 20 games ago counts half as much as its last game. Before, a game from two seasons ago counted the same as last weekend's.
2. **Each game is judged against the opponent.** 22 shots against the league's leakiest defence is less impressive than 22 against the tightest. We divide by how much that opponent usually allows (for shots, fouls, cards). Corners did not benefit, so they are not adjusted.
3. **Start from the league average.** A team, player or referee with few games sits close to the league average and moves away only as games add up. This was already in the engine for teams and players; referees now get it too.
4. **Cap the freak game.** A single game is capped at the league's 99th percentile before averaging. This is mostly a guard against feed errors. Real big games carry real information, and capping them harder made forecasts worse in our tests.

**Worked example, team shots.** A team takes 14 shots a game for 15 games against ordinary opponents. It then takes 22 against a side that concedes 40% more than the league average.

| Method | Before the game | After |
|---|---|---|
| Plain average | 14.0 | 14.5 |
| Normalised | 13.5 (pulled slightly toward the league's 12.5) | 13.7 |

**Worked example, referee cards.** A referee has 10 matches at 3.5 cards. Then comes an 8-card match.

| Method | Before | After |
|---|---|---|
| Plain average | 3.50 | 3.91 |
| Normalised | 3.48 | 3.63 |

The referee's number only moves far when it happens again and again.

---

## 3. The evidence

### 3a. Team averages: 27,135 matches, 5 leagues, 15 seasons

- **Data:** football-data match statistics, 2010/11 to 2024/25, Premier League, La Liga, Bundesliga, Serie A, Ligue 1.
- **Method:**
  - Walk-forward: every match is predicted from earlier matches only.
  - Prediction: league average x the team's attacking average x the opponent's defensive average.
  - Score: negative binomial log likelihood of the real count, per team-game.
  - **Gain** is the change in that score in thousandths (higher = better). **z** is the strength of evidence (above 3 is clear).

| Stat | Recency only | Opponent only | Cap only | Recency + opponent | + cap (shipped) |
|---|---|---|---|---|---|
| Shots | +25.1 (z 28) | +2.1 | +0.3 | **+26.4 (z 30)** | +26.0 |
| Shots on target | +15.4 (z 19) | +0.8 | +0.2 | **+16.2 (z 20)** | +15.9 |
| Corners | +6.1 (z 10) | -0.3 | +0.3 | +5.9 | **+6.0** |
| Fouls | +24.7 (z 29) | -2.0 | +1.0 | +25.4 | **+25.5 (z 32)** |
| Yellow cards | +5.3 (z 10) | -0.1 | +0.2 | +6.2 | **+6.3 (z 12)** |

**Every league improved, in every stat.**
- The baseline is today's method: a plain average over about three seasons, shrunk to the league.
- Recency is most of the gain.
- The opponent adjustment helps shots, on target, fouls and cards. Corners are not opponent-adjusted (setting `engine.style_opp_adjust`).

### 3b. Player averages: StatsBomb 2015/16, 25,166 player-games, 3 leagues

The player's share of his team's total, scored on his next game with the real team total and minutes, so only the averaging differs.

| Change | Shots | On target | Tackles |
|---|---|---|---|
| Weaker prior (20) | -3.3 (z -7.6) | -1.0 | -6.2 |
| Stronger prior (80) | -1.8 | -2.3 | **+2.4 (z +5.1, all 3 leagues)** |
| Cap each game at the 99th percentile | -0.3 | -0.2 | +0.3 |

The engine's player averages were already well normalised for shots and on target. Tackles needed a stronger prior, now 80.

### 3c. Referees: 5,295 Premier League matches, 2010/11 to 2024/25

Match yellow cards, predicted from the two teams, then with a referee factor.

| Referee method | Gain vs teams only |
|---|---|
| Plain average cards per game (what referee tables usually show) | **-19.9 (z -4.5): worse than ignoring the referee** |
| Raw ratio to the teams' expectation | -5.3 |
| Normalised (prior 80 cards, half-life 60 matches) | +4.0 (z +2.5) |
| **Normalised + cap at the 99th percentile (shipped)** | **+4.2 (z +2.7); better in 12 of 15 seasons** |

Referee factors run from about 0.88 to 1.12. A referee rarely changes a match's cards by more than 12%. Showing the plain average overstates that by a lot.

### 3d. The real engine, end to end

The full engine (styles, regression, player shares, calibration-free raw likelihoods), walk-forward on StatsBomb 2015/16, refitted every 4 match dates, both states (before lineups and with the confirmed eleven), on the new ladders. 675,000 forecasts per variant. Gain in log loss per forecast x1000 against today's engine (higher = better):

| Market | Recency only | Recency + opponent | + cap | **Shipped** (+ tackles prior 80) |
|---|---|---|---|---|
| Player shots | +0.14 (z 7.2) | +0.13 | +0.12 | **+0.12 (z 5.6)** |
| Player on target | -0.02 | +0.01 | +0.01 | **+0.01** |
| Player tackles | +0.07 | +0.08 | +0.08 | **+0.29 (z 3.9)** |
| Team shots | +2.13 (z 5.8) | +1.65 | +1.42 | **+1.42 (z 3.4)** |
| Team corners | +0.34 | +0.34 | +0.88 | **+0.88 (z 2.9)** |
| Team tackles | +1.19 | +1.27 | +1.27 | **+1.27 (z 2.8)** |

- Pooled over the three leagues, the shipped settings are better in every market.
- Of the 18 market-by-league cells, 14 are better and 4 are slightly worse. The worst is Serie A team tackles, at -1.07.
- The gains here are smaller than in §3a. This test covers one season, so team averages start from only about 12 games, and old seasons (where recency matters most) do not exist yet.
- On team shots, recency alone did slightly better in this one season. Over 15 seasons (§3a), adding the opponent adjustment was better. We follow the larger test.

### 3e. Likely starters before the lineup

StatsBomb 2015/16, pre-lineup forecasts, calibrated as shown in the app.

| Players with an 85%+ chance to play | Said | Came true |
|---|---|---|
| Strong (80%+, low end 70%+) | 85% on average | **83%** |
| Solid (65%+, low end 55%+) | 72% | **71%** |
| For comparison: Strong with the confirmed eleven | 89% | 89% |

So a likely starter's Strong or Solid means what it says, and we let them have it. Below 85% to play, a player stays at Watch until the lineup is confirmed.

---

## 4. New and changed fields

**Every forecast row (`forecasts`):**

| Field | Meaning |
|---|---|
| `p_usual` | The same line from the player's or team's own normalised average, before this opponent and match. Show it as "Usually 58%". |
| `edge` | `p - p_usual`: what this match changes. The feed ranks by it. |
| `tier_basis` | `team`, `lineup` (confirmed eleven), `likely_starter` (85%+ to play), or `pre` |
| `tier_note` | `"Watch until lineups are out"` when the lineup is what keeps it at Watch; otherwise empty |
| `market` | Built words for any line ("4+ shots") |

**Cards (`cards[].more_lines`)** now also carry `p_usual` and `edge`.

**Card headline rule (`queries.group_cards`):**
- Of the lines that are Strong or Solid, take the stat with the biggest lift over usual, then its most ambitious line.
- Only when no line is Strong or Solid does the best tier lead, as before.

**`GET /api/insights`** takes these parameters:
- `sort` = `edge` (default) | `likely` | `kickoff`;
- `stat`, `scope` (`player` | `team`);
- `leagues` (comma-separated league ids);
- `tiers` (comma-separated, default `Strong,Solid`).

**`GET /api/matches/{id}`** adds:
```json
"referee": {"referee": "M Oliver", "factor": 1.06, "matches": 41, "cards_per_game": 4.1,
            "cards_per_game_normalised": 3.8, "sentence": "M Oliver gives about 6% more cards than the teams would usually pick up."}
```
It is `null` when the match has no referee.

**`GET /api/leagues/{id}/referees`** now returns the normalised rows:
- `matches`, `cards_per_game` (plain);
- `cards_per_game_normalised`, `factor`, `league_cards_per_game`;
- `sentence`.

Show the normalised number first. The plain one goes in small type.

**Job `referees`:** daily, and on the manual job list.
- It needs `matches.referee` (the name) and each side's `yellow` in `team_match_stats`.
- With no such data it writes nothing and says so in its result.

**Settings (15 new, 214 in all):**
- `engine.auto_lines`, `engine.player_ladder`, `engine.team_ladder`, `engine.line_band`, `engine.max_lines_per_stat`;
- `engine.likely_starter_p`;
- `engine.style_half_life`, `engine.style_opp_adjust`, `engine.style_cap_q`, `engine.player_prior`;
- `engine.feed_sort`, `engine.feed_max_p`;
- `referees.prior_cards`, `referees.half_life`, `referees.cap_q`.

Old behaviour is one switch away:
- `engine.auto_lines` off, `engine.style_half_life` 0, `engine.style_opp_adjust` [], `engine.style_cap_q` 0;
- `engine.likely_starter_p` 1.0, `engine.feed_sort` "likely".

---

## 5. What the screens must change (frontend)

1. **The "vs usual" line.**
   - Show "Usually 58%", from `p_usual`.
   - Remove "−27 pts vs usual (100% in last 10)". The last-10 rate (`p_raw`) is the least reliable number we have (doc 21). It made good forecasts look bad.
2. **Tier note.** When `tier_note` is set, show it under the tier badge, in small text.
3. **Likely starter.** When `tier_basis` is `likely_starter`, the lineup chip reads "Likely starter", not "Lineup likely".
4. **Team cards** show the team's name (`team`) and crest, never the word "Team".
5. **Player names** show the full surname. Truncate the first name first ("R. Højlund").
6. **Insights** gets a sort control: "Different from usual" (default), "Most likely", "Kick-off". It passes `?sort=`.
7. **Match page:** show `referee.sentence` under the context chips when present.
8. **Referees table:** columns Referee, Matches, Cards per game (normalised), vs teams' usual (factor as +6% / −4%). The plain average goes in small grey text under the normalised one.
9. **Reasons:** show `reasons[0]` on the card and the rest in the detail sheet. Do not invent text.

---

## 6. Limits, plainly

- **Different data per test.**
  - The team test used match statistics (no tackles or possession in that data).
  - The player and likely-starter tests used one season of event data.
  - The end-to-end engine test used one season, three leagues. It is the shortest run, so its gains are the smallest and the least certain.
- **Referee data.** Referees are named only for the Premier League in our test data. Other leagues use the same method; we could not measure them.
- **Yellow-card forecasts are not a market yet.**
  - The referee factor is shown on the match page and in the table.
  - A cards market can be added with the engine's `extra_stats` once the feed's card data is verified.
- **More lines, more rows.** About 3 lines per player per stat instead of 1 or 2, but only lines between 50% and 95% are stored.

## 7. Files

| File | Change |
|---|---|
| `backend/soccer_brain/engine.py` | Normalised team averages (recency, opponent, cap); player prior per stat; `p_usual`; player-first reasons |
| `backend/engine_bridge.py` | Ladders and automatic line selection; likely-starter tiers; `tier_basis`, `tier_note`, `p_usual`, `edge`; built labels |
| `backend/queries.py` | Headline never near-certain; feed sorts; referee line on the match page |
| `backend/server.py` | `/api/insights` takes `sort`, `stat`, `scope`, `leagues`, `tiers` |
| `backend/referees.py` | New: normalised referee numbers and the daily refresh |
| `backend/jobs.py` | Daily `referees` job |
| `backend/settings_registry.json`, `backend/settings_store.py`, `docs/11_settings_registry.json` | 15 new settings with ranges |
| `backend/tests/selftest_lines.py` | New suite (the 18th) |
| `docs/validation/team_norm.py`, `ref_norm.py`, `player_norm.py`, `audit_norm.py`, `score_e2e.py` | The tests in section 3, rerunnable |
