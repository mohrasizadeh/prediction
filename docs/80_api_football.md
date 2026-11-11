# 80. API-Football, measured against what the engine actually eats

Follows docs/78 and docs/79. The owner found SportMonks expensive and asked whether API-Football
can do the job, suspecting it lacks granular metrics.

**It does lack metrics SportMonks has. It does not lack a single metric this engine consumes.**
Those are different statements and the difference is the whole decision.

One caveat on sourcing: **api-football.com and api-sports.io are behind a bot check** and would not
serve this session, and I did not spoof a browser to get in. Field shapes below come from a
third-party Go client's typed structs (exact JSON tags, derived from real responses) cross-checked
against the vendor's own guides; prices come from secondary listings. Everything marked *confirm*
is settled by five calls with the key we already hold — see §7.

---

## 1. Player, per match — the part that matters

`GET /fixtures/players?fixture={id}` returns, per player:

```
games   { minutes, number, position, rating, captain, substitute }
shots   { total, on }
goals   { total, conceded, assists, saves }
passes  { total, key, accuracy }
tackles { total, blocks, interceptions }
duels   { total, won }
dribbles{ attempts, success, past }
fouls   { drawn, committed }
cards   { yellow, red }
penalty { won, committed, scored, missed, saved }
offsides
```

Against `normalize.PLAYER_COLS`:

| our column | API-Football | |
|---|---|---|
| minutes | `games.minutes` | ✔ |
| shots | `shots.total` | ✔ |
| sot | `shots.on` | ✔ |
| tackles | `tackles.total` | ✔ |
| goals | `goals.total` | ✔ |
| assists | `goals.assists` | ✔ |
| saves | `goals.saves` | ✔ |
| interceptions | `tackles.interceptions` | ✔ |
| fouls_committed | `fouls.committed` | ✔ |
| fouls_won | `fouls.drawn` | ✔ |
| passes | `passes.total` | ✔ |
| **xg** | — | ✘ |
| **clearances** | — | ✘ |

Eleven of thirteen. **Now the part worth being precise about: neither missing column is used.**

- `PLAYER_REQUIRED` is `minutes, shots, sot, tackles, team_shots, team_sot, team_tackles`. Neither
  is in it.
- `ALL_PLAYER_STATS` — the markets the player layer fits — is `shots, sot, tackles,
  fouls_committed, goal_involvements, saves`. Neither is in it.
- `engine.xg_blend` is `0`.

So xG and clearances are columns we store and have never read. **On the engine as it stands,
API-Football's player feed is a complete substitute, not a reduced one.**

It also brings five columns PitchAPI never gave us: `duels total/won`, `dribbles
attempts/success/past` (**`past` is "times this defender was dribbled past"** — a defensive
vulnerability measure we have never had), `passes.key`, `passes.accuracy`, and a per-match
`rating`. `substitute` and `games.number` come free, which is the started-flag and the shirt number
without the separate lineups call.

## 2. Team, per match

`GET /fixtures/statistics?fixture={id}` → `[{type, value}]`, with the usual types: Total Shots,
Shots on Goal, Shots off Goal, Blocked Shots, Shots insidebox, Shots outsidebox, Corner Kicks,
Fouls, Offsides, Ball Possession, Yellow Cards, Red Cards, Goalkeeper Saves, Total passes, Passes
accurate, Passes %.

| our column | | |
|---|---|---|
| shots | Total Shots | ✔ |
| sot | Shots on Goal | ✔ |
| corners | Corner Kicks | ✔ |
| poss | Ball Possession | ✔ |
| fouls | Fouls | ✔ |
| yellow_cards | Yellow Cards | ✔ |
| **tackles** | not a team type | **already handled** |
| xg | `expected_goals` where covered | ~ |

Team tackles is a non-issue: `normalize.normalize_match` already sums the team's player tackles when
the team stat is absent (`if ts[side]["tackles"] is None: ts[side]["tackles"] = totals[side][...]`).
That fallback was written for PitchAPI and it covers this exactly.

**On xG there is a surprise in API-Football's favour.** `expected_goals` and `goals_prevented` do
appear in `/fixtures/statistics` for at least some leagues — one developer's sample found them on
12 of 12 Brasileirão 2024 fixtures. Where covered it is **free**, against SportMonks charging for the
add-on. Coverage will be patchy; `/leagues` says per league and season. *Confirm in §7.*

Two structural wins over PitchAPI, both free: `Shots insidebox` / `outsidebox` is a real
shot-quality split we have never had, and `/fixtures` carries **`referee` on the fixture itself** —
so `referees.py` gets fed without `ingest.match_extra_detail`'s extra call per match.

## 3. Everything else the product needs

| | |
|---|---|
| Fixtures and results | `/fixtures?league=&season=` ✔ |
| Lineups | `/fixtures/lineups?fixture=` ✔ (30–60 min before kick-off; `ingest.lineups_watch_enabled` already works this way) |
| Live | `/fixtures?live=all` ✔, `/fixtures/events` ✔ |
| Injuries | `/injuries` ✔ — **already wired**, `availability.py` |
| Images | `media.api-sports.io/.../{id}.png` ✔ — **already wired**, `images.py` |
| Referee | on the fixture ✔ |
| Full calendar, all competitions | `/fixtures?team=&season=` ✔ |

**Three of our six integration points already exist and run against this provider.** That is not a
small thing: images, injuries and a probe script (`check_apifootball.py`) are built, and docs/19
records the rate-header behaviour, the error shapes and the matching rules.

## 4. Cost, and the one place API-Football wins outright

Secondary listings, consistently: **Free 100 req/day · Pro ~$19/mo 7,500/day · Ultra ~$29/mo
75,000/day · Mega ~$39/mo 150,000/day**, and the tiers differ by **request quota, not by endpoint or
by league**. *Confirm — their pricing page would not load for me.*

**Every plan carries every league.** Against SportMonks Growth at €99 for thirty, that is the
decisive commercial difference, and it has an engine consequence docs/79 §1 warned about:

> `context.py` models rotation from "every competition the club plays", and the Tuesday European tie
> is the reason a club rotates on Saturday.

On SportMonks Growth we would have had to **spend league slots on cups and continental competitions**
to make the congestion layer work. On API-Football there is no league budget, so `/fixtures?team=`
returns the whole calendar by construction. **The rotation layer is better fed on the cheaper
provider.**

Call volume is the trade: API-Football has no batching, so a finished match costs 3 calls
(statistics, players, lineups) where SportMonks costs one per fifty fixtures. It does not matter,
because the quota is enormous:

| | SportMonks Growth | API-Football Ultra |
|---|---|---|
| 3-season backfill, 30 leagues | ~700 calls | ~100,000 calls |
| days to backfill | 1 | ~2 at 75,000/day |
| a 50-match matchday | 1 call | ~150 calls of 75,000 |

Thirty times chattier, and still using a fifth of a day's quota on the heaviest day of the season.

## 5. What you actually give up

Not the current product. The docs/79 **upside**, and only part of it.

| docs/79 item | On API-Football |
|---|---|
| §3.1 style basis | **Partly.** Control (possession, pass %) ✔, shot location (inside/outside box) ✔, disruption (tackles, interceptions, duels, fouls) ✔. **Lost: transition and directness** — no attacks, dangerous attacks, counter-attacks or long passes. Three indices instead of five. |
| §3.2 referee statistics | **Lost.** No referee statistics endpoint — the fixture gives a name. `referees.py` keeps deriving from our own matches, as today. |
| §3.3 suspensions | **Mostly kept.** `/injuries` is already wired. Whether it separates suspension from injury and carries a return date: *confirm*. |
| §3.4 coach substitution rate | **Lost.** No coach statistics. This was my favourite idea; it dies with this provider. |
| §3.5 full calendar → rotation | **Better** (§4). |
| §3.6 stakes from standings | **Kept.** `/standings` ✔. |
| §3.7 weather and pitch | **Lost.** |
| §3.8 derby flag | **Lost.** No rivals endpoint. |
| §4 first-half markets | **Lost.** `/fixtures/statistics` is full-match only; half-time *scores* exist, half-time corners and shots do not. |
| §4 momentum strip | **Weaker.** No minute-by-minute trends series; events and live statistics only. |
| §4 keeper saves inside the box | **Lost.** `goals.saves` only. |
| §4 Team of the Week | **Lost.** |

Of the three I said I would bet real money on: the style basis **partly survives**, suspensions
**survive**, referee counts **are lost**.

## 6. Two risks, one of them familiar

**Statistic types are display strings, not stable ids.** `"Total Shots"`, `"Ball Possession"`. This
is precisely the fragility that left half of `provider.pitchapi.team_keys` as `null` and made
`MODULES.md` admit the tests prove nothing about the real key names. SportMonks' numeric type ids
cannot be renamed under us; these can. **Mitigation:** keep the mapping in settings exactly as
`provider.pitchapi.team_keys` does, and have the probe print the live type list so a rename is
visible rather than silent.

**Absent still means zero.** docs/78 §5.2, unchanged. `/fixtures/players` omits a count that is
zero, which is the bug that halved `p_play`. The new guard — is this field present for any *other*
player in this fixture — is needed here just as it was for SportMonks. API-Football's nested shape
helps: `tackles` is an object, so `tackles: {total: null, ...}` present-but-null is distinguishable
from the object being absent.

And one open item carried from docs/19 §8, still unresolved: **nobody has read API-Football's terms
on storing and serving their images.** We are already doing it. If we are standardising on this
provider, get the written answer.

## 7. The probe, which settles all of it for five calls

`check_apifootball.py` already exists and already handles the key, the rate headers and the
coverage object. Extend it:

1. `/fixtures?league=X&season=Y&status=FT` → take one finished fixture id.
2. `/fixtures/statistics?fixture=ID` → **print every `type` string verbatim**, and say whether
   `expected_goals` is among them.
3. `/fixtures/players?fixture=ID` → confirm the eleven columns, and **check whether a player who
   certainly took no shot has `shots.total: 0` or `null`** — that is the absent-or-zero question,
   answered directly.
4. `/injuries?league=X&season=Y` → does `type` separate suspension from injury, is there an end date.
5. `/leagues?id=X` → the `coverage` flags per season, and **how many seasons the plan can read**.

Five calls on the free tier's hundred. It costs nothing and it converts every *confirm* in this
document into a fact.

## 8. Recommendation

**Go with API-Football, on Ultra (~$29/mo), and do the probe first.**

The reasoning, plainly:

- It covers **100% of what the engine consumes today.** The two columns it lacks are columns we
  store and have never read. "Lacks granular metrics" is true of the catalogue and false of our
  frame.
- It is **a third of the price with no league cap**, and the missing league cap makes the rotation
  layer *better* fed than Growth would have been.
- **Half the integration already exists** — images, injuries, a probe script and a documented set of
  gotchas.
- What we give up is mostly the speculative half of docs/79. Losing coach substitution rate and
  referee statistics is a real loss, and it is a €70-a-month loss, not a product-defining one.

The honest counter-argument, so it is on the record: SportMonks is the better *data product* —
numeric ids, batched calls, five style indices instead of three, half-time splits, referee and coach
statistics, minute-by-minute trends. If this app reaches the point where the engine is good and the
remaining gains are in features nobody else has, that is when the €99 earns itself. **Today the app
is in testing and the engine has eight dark layers to light up; three indices are enough to start
testing the style layer, and the money is better spent on being alive.**

Revisit when the A/B runner says the style layer earns its place and starts asking for the two
indices this provider cannot give.

---

## 9. The accuracy verdict

Asked directly: what does this do to forecast accuracy. The answer is **nothing, by itself** — and
the reason is more useful than the answer.

### The switch is accuracy-neutral by construction

Same columns in, same engine. `soccer_brain` reads our collections and cannot tell which provider
filled them. Where both providers supply a column, the forecast is identical. There is no version of
this decision where the model gets better because the invoice changed.

### The upside I sketched in docs/79 has already been measured, and it is zero

This is the part that matters, and it is in this repo, not in a vendor's catalogue.
`docs/validation/` holds a real-data walk-forward harness over StatsBomb events — three leagues,
1,588 team-matches, z clustered by team-match — plus 14 Premier League seasons for goals and 34,763
squad rows for the start model. doc 18 §1 records the verdicts:

| Layer | Gain | z | |
|---|---|---|---|
| Tactical style indices | −0.0016 | **−3.1** | worse |
| Style indices + shape | −0.0018 | **−2.9** | worse |
| Real lineup shape handed to the model | −0.0002 | −0.4 | nothing |
| Real first-choice score handed to the model | −0.0001 | −0.4 | nothing |
| Real number of changes handed to the model | −0.0001 | −0.3 | nothing |
| Rotation → team totals (14 PL seasons) | — | — | "smaller than the noise" |
| Rotation → **who starts** | +0.0004 to +0.0010 | +0.9 to +2.1 | **real but small** |

**The three oracle rows settle the question.** They hand the model the *true* shape, the *true*
first-choice score and the *true* number of changes — perfect information, the ceiling no feed can
exceed — and the gain is zero. A better provider cannot beat an oracle. So richer tactical and
rotation data has a measured upper bound of nothing at team level, and doc 18 explains why in one
line: *a team's own shots, corners and tackles already carry its style.*

So the honest expectation from either provider is **no measurable accuracy change**, and the
difference between SportMonks and API-Football on this axis is the difference between two numbers
that are both zero.

### Where accuracy actually comes from here

The repo's own history says it twice, and both times it was data quality, not modelling:

- **The missingness bug.** `tackles: null` on a forward who made none → `dropna` deleted the
  appearance → the engine read a deleted appearance as an absence → `p_play` 0.59 → 0.33, under
  `min_p_play`, so every card vanished, **position-correlated**. 568 stored rows fell to 395. That
  is the largest quantified accuracy event in this project.
- **The thrown-out result.** An early run showed shape helping at z ≈ 7. It was false: 23 Ligue 1
  matches had empty event feeds, the shape column held 0, and the model learned "shape 0 means zero
  shots". doc 18 §1 turns it into a rule — *all-zero shots, tackles and corners for a side is a data
  hole, not football* — and that rule must be carried to the new feed.

Both are missing-data defects. Neither is fixed by a provider; both are made easier or harder by
one. API-Football's nested objects (`tackles: {total: null}`) distinguish present-but-null from
absent, which is a better footing for the guard than PitchAPI's group heuristic.

### The three things that would move accuracy, in order

1. **Rebuild the absent-or-zero guard and carry the data-hole filter.** Removes a known
   position-correlated bias. Costs days, not euros, and is required before the first backfill either
   way.
2. **Settle `engine.interactions`.** It is `true` today and it **failed its own test**: the
   style-matchup terms did not beat the same engine without them, and the measured direction
   favoured *without* by +0.0010 (z 1.6). doc 18 §22 explicitly leaves the decision to the owner
   pending a run on real history. Turning a losing feature off is a free accuracy gain that needs no
   provider at all.
3. **Buy volume for calibration, not features.** The reliability table in
   `soccer_brain/backtest_report.txt` shows the top band overstated: Strong **stated 0.906 vs actual
   0.880**, and the 0.9–1.0 band stated 0.948 vs actual 0.933. `engine.calibration_auto` refits from
   our own results but waits for `engine.calib_min_scored` = 5,000 scored forecasts. **Thirty leagues
   reach that roughly six times faster than five.** This is the most user-visible accuracy work
   available: it makes "Strong" mean what it says.

Point 3 is the one place the provider choice does touch accuracy, and it points at API-Football:
accuracy here is bought with **league count and time**, not with granularity, and API-Football gives
every league on every plan.

Point 3 also subsumes the only surviving layer. The start model is the one thing with a positive
signal, it lives on the critical path for player cards (the most common Strong reason in the sample
output is "Expected minutes are high"), and its test was run on a calendar with **no cups and no
Europa League** (README, "Known limits"). An all-leagues plan is exactly what that gate needs to be
re-run honestly.

### Verdict

**API-Football, Ultra.** Not because it is more accurate — nothing here is — but because accuracy is
not currently provider-limited, and on the one axis where data does buy accuracy (volume for
calibration, and a complete calendar for the start model) the cheaper provider is the better one.

Spend the €70 a month saved on nothing. Spend the time on the guard, the `interactions` decision and
getting 5,000 scored forecasts on the board.
