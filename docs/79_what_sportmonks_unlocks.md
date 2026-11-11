# 79. What SportMonks unlocks

Follows docs/78, which answered "can we move". This answers "what do we get", decided after the
owner chose a fresh start and the Growth plan.

**The headline is not that we can add features. It is that the engine already contains layers built
for data we have never had, and they are switched off because the feed is empty.** Turning those on
is the cheapest accuracy work available to us, because the code, the tests and the walk-forward gate
already exist.

---

## 1. The three decisions

### Start fresh: yes, and it removes the one serious risk

docs/78 §5.1 said identity was the thing that would break silently. In the testing phase there is no
track record to preserve and no user's saved card to orphan, so **the crosswalk stops being
load-bearing**. Build the database from SportMonks ids and the problem is gone, not mitigated.

### Reuse: keep the pictures, re-pull the statistics

Two different answers, for a reason.

**Images: keep them.** `images.py` already downloads each file once into our own `media` collection
and serves it from our own address — pixels, not a provider's data model. The only link to the old
provider is the `image_map` row joining our iid to an API-Football id, and once the new database
exists we rebuild that join by name with the scorers we already have. A crest is a crest, and a
re-download is pure cost for an identical file.

**Statistics: do not reuse the PitchAPI backfill.** This is the one place I would overrule the
instinct, and the reason is not effort, it is bias.

Two providers do not define a statistic the same way. "Tackles" may or may not require winning the
ball; "shots" may or may not include blocked attempts; "fouls" may count the award or the offence.
The engine fits a negative-binomial regression over a single frame of past matches and reads a
player's share of his club's total out of it. Stitching PitchAPI seasons to SportMonks seasons puts
a **definition seam inside that frame**, and the model cannot see a seam — it reads the step change
as a trend. Every club looks like it suddenly started tackling more, recency weighting
(`half_life_rounds = 20`) makes the newest side of the seam dominate, and the forecast is confidently
wrong in a way no test would catch.

And we do not need it: **the Growth plan carries the three most recent seasons per league**, where
`engine.history_rounds` is 320 rounds. The history we would be splicing is history we can simply
fetch, from one provider, with one set of definitions. One call per fifty fixtures makes the backfill
cheap — a full season of a 20-team league is eight calls.

Keep the old `player_match_stats` in a dormant collection if you want it for comparison. Do not feed
it to the engine.

### Growth, and how to spend the thirty leagues

€99/mo, 30 leagues, 2,500 calls per entity per hour. Right call — the data is identical on every
base plan, so the plan buys league count and nothing else.

**Spend some of those slots on cups and continental competitions, not only on top divisions.** This
is the non-obvious part. `context.py` exists to model rotation and congestion, and its input is "one
row per club per match, in **every** competition the club plays". A club's Champions League Tuesday
and its League Cup Wednesday are *the* reason it rotates on Saturday. If those competitions are not
in the subscription they are not in `/schedules/teams/{id}`, and the congestion model is blind to
exactly the fixtures that cause the effect it is trying to measure.

A workable split for ten domestic leagues: the ten leagues, plus UCL / UEL / UECL, plus the main
domestic cup of the four or five leagues that matter most. `context.importance` already has weights
keyed `ucl`, `uel`, `uecl`, `fa_cup`, `league_cup`, `domestic_cup`, `super_cup` waiting for them.

**Add-ons: buy none at the start.**

| Add-on | Verdict |
|---|---|
| Expected Goals | **Wait.** `engine.xg_blend` is 0, so nothing currently uses it. Revisit when the A/B runner says the blend earns its place — then it is a measured purchase, not a hopeful one. |
| Expected Lineups | **No, at €199/mo** — twice the base plan. The free `predictedLineups` include and official lineups ~1h before kickoff come with every plan, and we already have our own likely-starter model. |
| Pressure Index | **No — build it.** The docs list its inputs: shots on target, possession, attacking-third entries, dangerous attacks, defensive actions. Every one of those is in `statistics`, free. Paying €9–29 for a weighted sum of columns we already hold is paying for arithmetic. |
| Historical Data | **No.** Three seasons exceeds what the engine fits on. |
| Match Facts, News, Transfer Rumours | **No.** Pre-chewed insight is the thing this product is supposed to produce. |
| Price feeds and tipping selections | **Never.** Forbidden by docs/03, and they would put banned vocabulary inside our own database. |

So: €99/mo total, replacing three providers.

---

## 2. Eight layers already built, currently dark

This is where the real gain is, and it needs no new modelling.

| Setting | Now | Why it is off | What SportMonks gives it |
|---|---|---|---|
| `engine.tactic_layers` | `"off"` | `tactics.py` needs eight tier-B columns; the feed has none | a native style basis (§3.1) |
| `context.stakes_places` | `{}` | nobody filled it per league | real standings, per round |
| `context.enabled` → congestion | on but half-fed | PitchAPI gives league matches only | full multi-competition schedule |
| `engine.lineup_effects` | `false`, "LOCKED" | needs real lineups at volume | lineups on every fixture, three seasons |
| `engine.shape_layer` | `"off"` | needs starters by line | real `position_id` per lineup row |
| `engine.script_v2` | `false` | needs in-match state | `trends` time series, free |
| `engine.player_half_life` | `0` | player form never trusted | dense per-match player rows |
| `engine.xg_blend` | `0` | no xG | the add-on, when measured |

Every one of these has a walk-forward gate in front of it (`context.gate_z = 2.0`,
`holdout_share = 0.3`) and `engine_ab.py` to run it. **So the honest claim is not "accuracy will
improve by X%". It is: eight candidate layers go from untestable to testable, and the gate decides.**
That is the right way to buy accuracy, and it is the first time the product has been able to shop.

---

## 3. New engine inputs, ranked by what I would bet on

### 3.1 A style basis that actually populates — *high confidence*

`tactics.py` asks for `ppda`, `ada`, `field_tilt`, `passes_per_seq`, `direct_speed`,
`long_ball_pct`, `high_turnovers`, `poss`. SportMonks will not give the spatial ones — PPDA and
field tilt need event coordinates at scale, and `ballCoordinates` is live-only.

**It does not matter, and the module says why in its own header:** every label is a z-score inside
the league, not an absolute cut-off, *because providers define these differently*. The layer wants a
style *vector*, not those eight names. SportMonks has a good one, all included:

| index | from |
|---|---|
| control | possession 45, successful-passes-% 82, ball-safe 46 |
| directness | long-passes 62 / passes 80, total-crosses 98, successful-long-passes-% 27265 |
| threat rate | dangerous-attacks 44 / attacks 43, goal-attempts 54, big-chances-created 580 |
| disruption | interceptions 100, successful-interceptions 66, challenges 77, fouls 56, tackles-won 27267 |
| transition | counter-attacks 1527 |

Five indices from columns that arrive with the statistics we are already fetching — no extra call.
The style-by-style interaction terms (`engine.interactions`, already `true`) then have something to
interact. **This is the single largest unlock: a whole gated layer goes from impossible to merely
unproven.**

### 3.2 Referee data as data, not inference — *high confidence, small scope*

`referees.py` currently *derives* a referee's card tendency from our own stored matches with a
shrinkage prior, and cold-starts at "we treat this referee as average".

SportMonks gives it directly per season: fouls, yellows, reds, second yellows, penalties, matches
officiated, **split home / away and by on-pitch / bench / coach** — plus **VAR moments per match**,
which nothing in our model has ever had. The home/away split is the interesting one: a referee who
cards the away side disproportionately is a real asymmetry our single factor cannot express.

Keep the shrinkage model — it is sound — and feed it real counts plus a prior from the referee's own
season. The cold-start disclaimer mostly disappears.

### 3.3 Suspensions are certainties, not guesses — *high confidence*

`sidelined` is free and carries start date, end date, **games missed** and the type, distinguishing
injury from suspension.

A suspension is *deterministic*: the player cannot play, and the end date says exactly when he
returns. Today `engine.absence_model` infers absence from "has not featured recently", which cannot
tell a suspended player from a rested one from a mis-ingested appearance — the failure mode that
halved `p_play` (docs/78 §5.2). Replacing inference with a known fact on the cases where a fact
exists is strictly better, and it removes forecasts for players who certainly will not play, which
is a *visible* quality win on the feed, not only a statistical one.

### 3.4 Coach substitution rate → the minutes layer — *medium confidence, genuinely new*

Coach statistics include **substitutions per match**. Step 5 of the engine multiplies a player's
share by a "minutes scenario mixture", and that mixture is currently club-generic.

A coach who makes five changes by the 60th minute produces a different minutes distribution from one
who makes two late — and it is the *coach's* habit, which persists when he changes club and changes
when a club changes coach. That is a clean, cheap feature on exactly the quantity the player layer is
most sensitive to. I would not promise it survives the gate, but it is the most interesting idea in
this list that nobody else is likely to be using.

### 3.5 Full calendar → rotation, properly — *medium, conditional on the league allocation*

§1 covers it. `context.py` is written and tested; it has simply never been shown a midweek European
tie. Conditional on buying the cups.

### 3.6 Stakes, filled automatically — *medium*

`context.stakes_places` is `{}`. Standings per round, live standings and topscorers are all included,
so the places that matter — title race, European spots, relegation — can be *derived* per league
rather than hand-entered, and the "nothing left to play for" effect (worth about 10% on goals, per
docs/18) finally has an input.

### 3.7 Weather and pitch — *low to medium, cheap to test*

Weather condition and pitch state arrive on the fixture. Rain and a slow pitch plausibly move
corners, fouls and pass accuracy. One column each, straight into the existing team-total regression;
the gate will say. Worth it because the cost is near zero.

### 3.8 Rivals → the derby flag — *low to medium*

`/rivals/teams/{id}` gives named rivalries. A derby is a genuine behavioural regime for cards and
fouls, and it is one boolean. Our cards market is the one most likely to feel it.

### 3.9 Period splits — *low for accuracy, high for product (see §4)*

`periods.statistics` breaks every stat into first half, second half, extra time.

---

## 4. Markets and features we could not build before

**First-half markets.** `periods.statistics` makes first-half corners, shots and cards fittable with
the machinery we already have — `engine_newmarket.py` adds a market without new code. This roughly
doubles the card inventory per match without touching the engine's shape.

**Goalkeeper saves, properly.** Saves 57 and **saves-inside-box 104** both come per player per match.
The saves market exists (docs/70) but is thin; a keeper's share of shots faced *inside* the box is
the right denominator and we have never had it.

**A live momentum strip, free.** §1 said do not buy the Pressure Index. Build it from `trends` —
minute-by-minute team series, included — and we get a momentum chart on the live page plus an in-play
state feature for `script_v2`. One data source, one display feature, one engine feature.

**The honest availability panel.** `sidelined` with dates and games-missed turns "rotation risk" into
"suspended, back on the 22nd" where that is a fact. That is the kind of specificity that makes a
forecast product feel trustworthy, and it is free.

**Form against this opponent.** Head-to-head is its own endpoint. Today the player card's strip is
the last ten games; "and three of his last four against *them*" is a different and more persuasive
sentence, and it is a filter on data we already store.

**Team of the Week.** A weekly, automatically generated eleven. Our blog planner (docs/72) currently
has to invent its own angle each day; a TOTW round-up is a free recurring post with a built-in
reason to exist, and it costs one call a week.

**The club's whole season at a glance.** Standings, schedule and rankings together make a club page
that is a destination rather than a list of fixtures — the thing docs/35 said we lacked against
StatsHub.

---

## 5. Three gotchas that would bias the engine silently

Each of these produces plausible numbers, which is why they belong in writing.

**1. The flat `statistics` include sums extra time into the match total.** A cup tie that went to 120
minutes reports its shots, corners and tackles as one inflated number with no marker. Fitted
alongside 90-minute matches it drags every team-total model upward and makes cup fixtures look like
high-tempo ones. Use `periods.statistics` and sum regular time, or exclude matches that reached
state 7 or 8 from the fitting frame. **Decide this before the first backfill**, because it is baked
into every row afterwards.

**2. Absent still means zero-or-untracked.** docs/78 §5.2. The new guard — is this type present for
any *other* player in this fixture — must exist before the first real ingest, not after.

**3. Type ids are stable, coverage is not.** A statistic that populates in the Premier League may be
absent in the twenty-eighth league of a Growth plan. `engine.coverage_min` (0.9) already switches a
market off below coverage; it must be measured **per league**, not globally, or one well-covered
league will carry a market that is empty in nine others.

---

## 6. Order

1. **Probe** (docs/78 §6 step 0) — now also measuring, per league: which of the five style indices
   populate, whether coach substitution counts are present, `sidelined` density, and the extra-time
   question. The probe decides §3's order, so it earns its place twice.
2. **Fresh ingest**, SportMonks ids, extra-time rule decided, new absent-or-zero guard, three
   seasons.
3. **Rebuild `image_map`** by name; keep every downloaded file.
4. **Then, one at a time, through the gate:** style basis → suspensions → referee counts → stakes →
   calendar (if cups bought) → coach substitutions → weather → derby.
5. **Product, in parallel** (no gate needed): availability panel, momentum strip, first-half markets,
   head-to-head line, TOTW post.

Step 4 is deliberately serial. Eight layers through one gate, one at a time, is how we find out which
two actually matter — and `engine_ab.py` exists for exactly this.

## 7. The honest summary

The data is a clear step up, and most of the step is not new capability — it is that eight layers
already written and tested have never had an input. I would bet real money on the style basis,
suspensions and referee counts. I would bet a little on coach substitution rate and think it is the
most original idea here. I would not promise a number for any of them, and the reason the product has
a walk-forward gate is so that nobody has to.

The two things to get right before the first ingest are the extra-time rule and the absent-or-zero
guard. Both are cheap now and expensive later.
