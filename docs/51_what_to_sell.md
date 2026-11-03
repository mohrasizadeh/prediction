# 51. What to sell

Written 2026-11-03, after docs/50. That document asked what is worth *showing*. This one asks what
is worth *paying for*, because they turn out to be the same question with the same answer.

**Nothing here is built.** It is a recommendation, and it says which parts are measured and which
are judgement.

---

## 1. The diagnosis in one sentence

The product currently sells **volume of the obvious**. It should sell **scarcity of the
verifiable**.

Three measurements say so.

### 1.1 Eight of twenty cards say nothing (measured, docs/50 §9.3)

Against each rung's own league baseline and spread: 8 of 20 headline cards are trivial, 9 say only
that the entity is unusual, 2 say only that today is unusual, and **1 says both** — which is the
sentence the engine exists to produce.

### 1.2 Everything gated is quantity, not quality (measured, `plans.ENTITLEMENTS`)

| Entitlement | Free | Pro | Kind |
|---|---|---|---|
| Finder searches a day | 10 | unlimited | quantity |
| Leagues searched at once | 1 | unlimited | quantity |
| Games in the grids | 5 | 10 | quantity |
| **Insight cards a day** | **20** | **unlimited** | **quantity** |
| Followed teams and players | 10 | unlimited | quantity |
| Saved forecasts | 20 | unlimited | quantity |
| Player notes | 20 | unlimited | quantity |
| Alerts | off | on | quality |
| Tactical matchup tab | off | on | quality |
| Export | off | on | quality |

Seven of ten paid entitlements are "the same thing, more of it". Put §1.1 next to that row four:
the free tier hands over twenty cards a day of which eight say nothing, and the paid tier offers
**unlimited more of the same**. More of something the reader does not value is worth nothing, at
any price.

### 1.3 The track record cannot prove skill (measured, `queries.track_record`)

The page is architecturally right: it bins forecasts by stated likelihood from 0.5 to 0.9+ and
reports stated against actual, with `n >= 30` required per bin. That is exactly how a forecaster
should be judged.

But the median shown likelihood is **0.873** and 14 of 20 cards sit at 85% or above (docs/50 §1),
so nearly all the mass lands in the top two bins and the 0.5–0.6 and 0.6–0.7 bins starve.

This is the part that matters most and is least obvious:

> **Being obviously right destroys the ability to prove you are good.**

A forecaster who says 90% and is right 90% of the time has demonstrated almost nothing — the base
rate alone would manage it. Skill is only visible in the 40–70% band, where a naive baseline cannot
follow you. The single asset that would justify a subscription is demonstrable skill, and the
current selection rule makes it unmeasurable by construction.

So the three findings are one finding. The app withholds the cards that would be worth paying for,
gives away unlimited copies of the cards that are not, and cannot prove it is any good because it
only ever says things that were going to happen anyway.

## 2. What to sell instead

### 2.1 The product

> **A small number of forecasts a day that the reader could not have made themselves, every one of
> them settled in public.**

Small is the feature, not a limitation. On the measured feed exactly one card in twenty cleared both
bars. On a real multi-league day that is perhaps five to fifteen — and five that matter beat twenty
that do not, because twenty forces the reader to do the filtering the engine was supposed to do.

Three properties, in order of importance:

1. **Surprising.** It clears the spread, who and when gates in docs/50 §9.4. If a league table
   could have told the reader, it does not ship.
2. **Settled.** Every forecast is scored afterwards and the record is public and permanent,
   including the ones that missed. `forecast_outcomes` already exists; the calibration report
   already exists.
3. **Explained.** The reasons are already on every card. This is the one thing the app already does
   that the hit-rate screeners structurally cannot (docs/50 §3), and it should be the loudest part
   of the identity.

### 2.2 Invert the gate: sell timing, not volume

Stop metering how *many* forecasts a reader sees. Meter **when** they see them and **whether the
app brings them to the reader**.

| | Free | Paid |
|---|---|---|
| The full settled record, every forecast ever made, hits and misses | **yes** | yes |
| Yesterday's forecasts, with outcomes | **yes** | yes |
| Today's forecasts | after kick-off | **before kick-off** |
| Alerts for a followed player or team | no | **yes** |
| Finder, grids, notes, saving | generous | generous |

Why this works and volume metering does not:

- **A forecast is perishable.** Its whole value is in arriving before the match. That is a real
  scarcity the reader already understands, and it needs no betting language to explain.
- **It makes the free tier the proof.** Anyone can audit the full record for nothing, which is the
  strongest possible answer to "why should I trust this". Hiding the record behind a plan is the
  single worst thing a forecast product can do, and the current model does not do it — keep it that
  way and make it louder.
- **It stops punishing the behaviour you want.** Capping follows at 10 and saves at 20 trains
  people not to invest in the product. Follows are the retention mechanism; they should be free and
  unlimited. Charge for the alert that the follow produces, not for the follow.

**Judgement, not measurement:** the free/paid line above is my recommendation, not a finding. The
measured part is that the current line is drawn on volume and that volume is not what the reader
values.

### 2.3 The habit loop

"Constantly brings value" means a reason to open it on a day when the reader was not planning to.
Three beats, and the app can already do all three:

- **Morning:** here are today's few, and why.
- **After the whistle:** here is how yesterday's few finished — including the misses, named as
  misses.
- **Any time:** here is your own record, for the players and teams you follow.

The third is the one that creates ownership. A reader who has followed eleven players and can see a
settled record for *their* eleven has something nobody else has, which is the thing that does not
churn.

## 3. The integrity guard

Making forecasts more interesting is one short step from making them worse, and that step is easy to
take by accident. Three guards, and the first is non-negotiable.

1. **Ship the selection change together with the per-band calibration report.** The moment the feed
   moves into the 40–70% band, the lower bins in `track_record` fill up and skill becomes
   measurable for the first time. That is the *point*. Publishing it is also what stops the feed
   drifting towards whatever is most dramatic: if the 50–60% band stops landing 50–60% of the time,
   the page says so in public.
2. **Never let selection touch the number.** The engine's job is the probability; selection's job
   is which true statement to say out loud. Those must stay separate pieces of code, or the
   calibration report becomes a measure of the selector rather than the model.
3. **Judge selection by reader behaviour, not accuracy** (docs/50 §7). Accuracy does not change —
   same numbers, same ladder. Cards opened, lines saved, players followed and return visits are the
   evidence. Run it as an A/B.

## 4. What I would do, in order

1. **Store `league_base` and `spread` per rung** (docs/50 §9.4). Everything else needs it and
   nothing can be filtered on data that is not recorded.
2. **Apply the three gates** — spread, who, when — and let the feed get smaller. Expect a large
   drop in card count. That is the change working.
3. **Publish the calibration report per band on the public record page**, before anyone asks.
4. **Redraw the plan line on timing**: free gets the settled record and yesterday; paid gets today
   before kick-off and alerts. Remove the caps on follows, saves and notes.
5. **Only then** return to engine features, aimed at the markets where spread shows there is
   variance to explain (docs/50 §9.5).

## 5. What would make me wrong

- If the A/B in §3.3 shows readers open and act on the near-certain feed *more* than the
  surprising one, §2 is wrong and the measurement should win.
- If the calibration report, once the lower bins fill, shows the engine is poorly calibrated at
  40–70%, then the current selection rule was accidentally protecting the product, and the right
  response is to fix calibration first and hold the feed where it is.
- The spread figures in docs/50 §9.1 come from the simulated demo league. The ordering should hold
  on real data; the absolute values may not. Step 1 above settles this in an afternoon.

A note on language: `textguard.BANNED` forbids *picks*, *hit rate*, *odds*, *stakes* and the rest
(docs/03). Nothing recommended here needs any of them. "Forecasts", "the record", "before kick-off"
and "the reasons" carry the whole proposition, which is a sign the proposition is sound rather than
a workaround.
