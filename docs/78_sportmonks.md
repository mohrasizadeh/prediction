# 78. Moving to SportMonks

**Question asked:** replace PitchAPI and SportAPI with SportMonks. Will it break anything — the
engine, and the way the data is shown?

**Answer:** every number this product needs exists in SportMonks, and the engine and the display
layer are not the parts at risk. The part at risk is **identity** — which row is which player — and
it is at risk in a way that would quietly destroy the track record and every saved card rather than
throw an error. That is the whole job. Done in the order below it is a safe migration; done as a
re-ingest it is a silent data loss.

Researched 2026-11-11 against the live v3 documentation.

---

## 1. What we actually consume today

Worth stating first, because the surface is much smaller than it feels.

**PitchAPI — the statistics the engine learns from.** Five endpoints, all through
`cached_fetch.PitchClient`, all normalised in one file (`normalize.py`, 258 lines):

| | |
|---|---|
| `/v1/leagues` | the league list |
| `/v1/leagues/{id}/matches` | fixtures and results |
| `/v1/matches/{id}/stats` | team numbers |
| `/v1/matches/{id}/players` | player numbers |
| `/v1/matches/{id}/lineups` | starters, bench, formation |

Plus, optional: `/v1/matches/{id}` (referee, stadium), `/v1/matches/{id}/events`, and
`/v1/{leagues,teams,players}/{id}` for images.

**SportAPI — speed.** Live scores, clock, events, lineups, historical results, league list
(`sportapi.py`, 818 lines).

**API-Football — a third provider nobody counted.** League logos, club crests, player photos
(`images.py`, 493 lines) and the optional injury feed (`availability.py`). SportMonks replaces this
one too, which is the part of the case that is easy to miss.

The columns the product needs are exactly these, and nothing else:

```
team    shots sot corners tackles poss xg fouls yellow_cards
player  minutes shots sot tackles goals assists xg saves
        interceptions clearances fouls_committed fouls_won passes
derived goal_involvements, shots_against, corners_against, tackles_against
```

## 2. Does SportMonks have them

All of them, with one asterisk.

**Team, per match** — `include=statistics` on a fixture. Type IDs: shots 42, shots on target 86,
corners 34, tackles 78, possession 45, fouls 56, yellow cards 84.

**Player, per match** — `include=lineups.details`. Type IDs: minutes 119, shots 42, shots on target
86, tackles 78, goals 52, assists 79, saves 57, interceptions 100, clearances 101, fouls 56, fouls
drawn 96, passes 80 (and accurate passes 116).

**The asterisk is xG.** It is not in either table. It needs the Expected Goals add-on —
`xGFixture` for teams, `lineups.xGLineup` for players — and the docs say plainly it is "not
available on any base plan without that add-on".

That costs us nothing today: `engine.xg_blend` is **0**, so xG is already switched off in the
engine, and `_fit_xg` returns early when the column is absent rather than failing. **Check the live
setting before deciding** — if production has it above zero, the add-on moves from optional to
required.

**Better than what we have, in three places:**

- **Stat identity is a number, not a label.** `type_id: 42` is shots. Our current mapping is a
  settings table of provider key *strings* (`provider.pitchapi.team_keys`), half of which are still
  `null`, and `MODULES.md` admits the test suite proves nothing about the real ones because
  `fake_pitchapi.py` invents them. A numeric type ID cannot be renamed under us.
- **Positions are real.** Players carry `position_id` (24 GK, 25 DEF, 26 MID, 27 ATT) and
  `detailed_position_id`. Today `/players` sends no position at all and `normalize.lineup_pos`
  infers the line from `pitch_x` depth — a guess we have been carrying.
- **Images are a URL on the entity.** `image_path` on teams, players and leagues. No separate call,
  no per-league squad listing, no name matching. That is `images.py` and most of `pitch_photos.py`
  gone.

**One call replaces thirty-one.** A finished matchday of ten matches costs us 1 listing + 10×3 =
31 PitchAPI calls. SportMonks:

```
GET /v3/football/fixtures/date/{date}
    ?include=participants;state;scores;statistics;lineups.details;events;referees
    &per_page=50
```

One call per 50 fixtures. `lineups.details` is within the three-level nesting limit. Do **not** add
`.type` in production — cache the type table once from `/core/types` instead.

## 3. The call budget stops being a constraint

| | now | SportMonks |
|---|---|---|
| PitchAPI | 2,000 / UTC day, counted by us | — |
| SportAPI | 1,800 / UTC day, counted by us | — |
| Starter | | 2,000 / **hour** / **entity** |
| Growth | | 2,500 / hour / entity |
| Pro | | 3,000 / hour / entity |

Limits are per *entity* (Fixture, Team, Player, League…), on a rolling hour from the first request
to that entity, and every successful response carries `rate_limit: {remaining, resets_in_seconds,
requested_entity}`. Livescores sit in the Fixture bucket.

Two consequences:

1. **Our two budget systems are now the wrong shape.** `ingest.daily_call_budget` and
   `sportapi.daily_calls` both count one global number per UTC day, and `Client.tight()` halves
   polling when a quarter is left. Against a per-entity hourly limit that logic would throttle us
   for no reason and leave most of the quota unused. The replacement is simpler than what we have:
   stop counting, read `remaining` off the response.
2. **Live polling becomes free.** 2,000/hour on the Fixture bucket is a call every two seconds. We
   poll once a minute.

## 4. Plans, and what to buy

€29/mo Starter (5 leagues), €99 Growth (30), €249 Pro (120), Enterprise custom (all, history
included). Extra leagues around €4. Historical data is a one-time purchase on Starter/Growth/Pro.
*Confirm every figure in MySportmonks — these came off the public pricing page.*

**Base plans include the three most recent seasons per subscribed league.** `engine.history_rounds`
is 320, so three seasons is comfortably more than the engine fits on. **The Historical Data add-on
is not needed.**

Included in every plan: schedules and results, livescores and events, fixture / season / team /
player / lineup / coach / referee statistics, standings, transfers.

Add-ons we would want: **Expected Goals, only if `engine.xg_blend` is non-zero in production.**
Add-ons we must leave off: the price-feed and tipping ones (Odds, Premium Odds, Predictions, value
selections). They are forbidden by docs/03 and would put banned vocabulary in our data, never mind
our copy. Expected Lineups (Growth+) is tempting for the lineup watcher but is not needed.

**Pick the plan by league count, not by data.** Every statistic we use is in Starter.

## 5. What breaks — the real list

### 5.1 Identity. This is the one that matters

`ingest.upsert_entity` is keyed on `ext_id` and **mints a new `iid` for an unseen one**. Ingesting
SportMonks into the current database therefore does not update our teams and players — it creates a
second copy of every one of them, with new iids.

Everything the product has learned and everything users own is keyed on those iids:

```
forecasts, forecast_outcomes   the track record
saved_forecasts, combos        what users saved
follows, follow_alerts, notes  what users follow and wrote
lineups, player_match_stats, team_match_stats, match_context,
referee_stats, team_styles, image_map, availability
```

A re-ingest leaves all of it pointing at orphaned rows. Nothing errors. The site comes up, the cards
are there, and the record is empty and every follow is dead. **This is the failure mode to design
against, and it is the reason this is a crosswalk and not an import.**

So: **keep every `iid`; rewrite `ext_id` in place.** Build a PitchAPI→SportMonks map first, by name,
inside the mapped league only, with a confidence gate and an admin review queue — and we do not have
to invent any of that, because `sportapi.map_team` already does exactly this for teams
(`sportapi_team_map`, statuses auto / review / rejected / none, margin-over-runner-up test, admin
screen), and `images.player_score` does it for players by surname and first initial. The migration
is that mechanism pointed at a new provider, with one addition: **nothing goes live until the
unmatched count is zero or explicitly accepted.**

Public URLs are safe either way — they use the row's `id` uuid, not the iid, so keeping rows keeps
every indexed URL.

### 5.2 Absent-or-zero. The trap we have already fallen into once

SportMonks: *"The API does not record `0` values in most cases, so absence alone does not tell you
which of the two applies"* — not tracked, or genuinely zero. Identical to PitchAPI, and this is the
bug that cost us our best players: `tackles: null` on a forward who made none → `dropna` deleted the
whole appearance → the engine read a deleted appearance as an absence → `p_play` halved → every card
dropped, position-correlated, silently. 568 stored rows fell to 395.

`normalize.ZERO_WHEN_ABSENT` guards it by asking whether the *group* that would carry the stat is
present on that player. SportMonks has no groups — `details` is a flat array — so the guard needs a
new form. **The new form is strictly better:** ask whether the type appears for *any other player in
the same fixture*. If tackles are recorded for fifteen other players, tackles were tracked in that
match, so absence here is a true zero. That is a direct test of the actual question, where the group
check was a proxy.

Card period statistics are the documented exception: a `0` there is a confirmed zero.

### 5.3 Status vocabulary

`sportapi.in_play/is_final/is_over` match normalised status *words* against three hand-built sets,
and the comment says the provider's vocabulary "is not verified". SportMonks has 25 documented
numeric states. In-play is `{2,3,4,6,9,21,22,23,25}`, final `{5,7,8}`, dead `{10,11,12,14,15,17,20}`,
not-yet `{1,13,16,26}`. This gets *more* reliable, but the three sets must be rewritten against ids
and the "anything unknown counts as in-play" fallback kept — that fallback is why forecasts tick
through half time (docs/42).

### 5.4 The two budget systems

Section 3. Both need replacing, not tuning.

### 5.5 What does **not** break

- **The engine.** It reads our collections, never the provider. `soccer_brain/` does not change.
  One line of `engine_bridge` touches xG and already degrades to neutral.
- **The display.** Every public screen reads our own `/api`. `lib/live.js` says in its header that
  the browser must not test the provider's status word — the server computes `m.phase`. The v10 card
  we just shipped reads `markets`, `noun`, `verb`, `chance`, `tier` — all ours.
- **The admin screens** need work, but it is renaming and rewiring panels, not redesign.

## 6. The order to do it in

**0. Probe, before any product code.** A standalone script in the shape of `check_apifootball.py` —
three or four calls, writes nothing. For each league we carry: which of the 20 types actually
populate, how many seasons are reachable, what `state_id`s appear, whether `minutes-played` is on
`lineups.details`, and whether `statistics` and the sum over players agree on shots. **The answer to
"will it break anything" is partly empirical and this is the measurement.** Coverage Finder shows
global coverage, not our entitlement, so this runs against our own key.

**1. The crosswalk.** `sportmonks_map` for teams and players, built by the existing scorers,
reviewed in admin, `ext_id` rewritten in place, iids untouched. Reversible: keep the old ext_id in a
sibling field.

**2. The adapter.** `sportmonks.py` (client, `rate_limit`-aware) and the type-id mapping as
settings, mirroring `provider.pitchapi.*`. A `provider.source` setting so both providers can be
installed at once and PitchAPI stays authoritative until step 3 passes.

**3. Parity.** Ingest the same matchdays from both into parallel collections and diff every team and
player column per match. Shots, tackles, minutes agreeing match-for-match is the gate. Anything that
disagrees is either a mapping error or a provider difference, and both need a name before we switch.
This is the step that makes the migration provable rather than hopeful.

**4. Live and lineups** replace `sportapi.py`. **5. Images and injuries** replace API-Football.
**6. Retire** the old clients, keys and settings.

Steps 0–3 are where the risk lives. 4–6 are mechanical.

## 7. Verdict

Technically this is a clear improvement: one provider instead of three, numeric stat ids instead of
unverified label strings, real positions instead of a depth guess, images without a sync, one call
where we make thirty-one, and an hourly per-entity budget that ends call-rationing as a design
constraint. Nothing the product shows today gets worse, and the engine does not change.

The migration is safe **if and only if** identity is migrated as a reviewed crosswalk that preserves
every `iid`, and if the absent-or-zero rule is rebuilt before the first real ingest. Those two are
not optional and they are not quick. Everything else is ordinary work.

Open before starting: the value of `engine.xg_blend` in production, and the league list, which
decides the plan.
