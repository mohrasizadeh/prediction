# Competitor audit — football statistics and forecast products

**Date of research:** 2026-11-06. **Method:** direct page fetches where the site permitted it, web search where it did not. Every claim below is tagged with how it was verified. Where I could not verify something, it says so.

**Evidence tags used throughout:**
- `[fetched]` — I retrieved the page on 2026-11-06 and read its rendered text. Labels and copy are quoted verbatim.
- `[search]` — taken from search-surfaced excerpts of the page, not a direct read. Quotes are the search engine's extracts, so treat exact wording as approximate.
- `[unverified]` — flagged explicitly; do not build on it.

**Sites I could not read directly, and why:**
- **Sofascore** — `https://www.sofascore.com/player/...` returned HTTP 403 to a plain client. All Sofascore detail below is `[search]`, mostly from Sofascore's own news articles.
- **FBref** — returned HTTP 403. Its scouting-report explainer is quoted from `[search]` extracts of `https://fbref.com/en/about/scouting-reports-explained`.
- **FotMob** — the page fetched (HTTP 200) but is client-rendered, and the markup carries the notice: *"The use of automatic services (robots, crawler, indexing etc.) as well as other methods for systematic or regular use is not permitted."* I did not query its data endpoints. All FotMob detail is `[search]`.
- **playerstats.football, footymetrics.com, pickfinder.app, web.archive.org** — outside this session's allowed network hosts. `[search]` only.

**A note on vocabulary.** Our product may never use betting words. This document quotes competitors' betting vocabulary because that is the evidence. Section 10 maps each banned word to *the job it does* and a non-betting replacement.

---

## 1. What matters — ten actionable findings

1. **Steal the plain-English filter restatement.** StatsHub's Prop Hunter renders the whole filter state as one sentence — *"Shots over 0.5 in 5 of the last 10 games (50%)"* — above the results. It is the single best interaction in the category and nobody else does it. Our Finder should restate itself the same way, in our vocabulary: *"At least 1 shot, in 5 of the last 10 matches."*
2. **"Over 0.5" is jargon for "at least 1".** Every competitor writes thresholds as `Over 0.5 / Over 1.5 / Over 2.5`. Saying *at least 1 / at least 2 / at least 3* is plainer, is what the number actually means, and satisfies our vocabulary constraint for free. This is a win with no cost.
3. **Name the reference class and the event threshold, every time.** The US National Weather Service publishes an FAQ page whose entire purpose is to stop people misreading one number, and it defines the event exactly: *"the probability that the forecast grid/point in question will receive at least 0.01" of rain"* ([weather.gov/ffc/pop](https://www.weather.gov/ffc/pop)) `[fetched]`. Gigerenzer et al. (2005) showed that without a stated reference class the same percentage is read in mutually contradictory ways. Our equivalent: *"Chance of at least 1 shot on target, if he starts."* Never a bare percentage.
4. **Frequency framing, not bare percentages.** Opta's prose never says "28.5% probability"; it says *"Liverpool are the favourites to win the title, doing so in 28.5% of simulations"*, and *"19 of the 20 competing teams won the title at least once in our 10,000 season simulations"* `[fetched]`. Natural frequencies are the format with the strongest (if contested) support in the risk-communication literature. Pair every probability with a count: *"62% — about 6 matches in 10."*
5. **No football product publishes its own calibration. That is our moat.** StatsHub's "track record" is one affiliate's betting P&L. Opta's self-assessment is narrative. FiveThirtyEight's "Checking Our Work" page — the only real precedent — is **gone** (see §7). A reliability curve plus *"of the 412 forecasts we published at 60–70%, 64% happened"* is both unmatched and the one question a profit figure cannot answer.
6. **Hit-rate tools are small-sample machines; shrinkage is our structural advantage.** StatsHub's most-saved preset is *"a shot in at least 8 of their last 10"*; its "Hot Form" preset is *4 of the last 5*. A 10-trial binomial at 50% has a 95% interval of roughly 19–81%; at 5 trials it is near-useless. Nowhere in the category is a sample-size penalty or an interval shown — the only control is a hard "Minimum games played" cutoff. Put the interval on the card.
7. **Opponent strength is a filter everywhere, never an adjustment.** StatsHub's match page offers *"Difficulty: All Matches / Easier Matchups / Harder Matchups"*; Team Trends offers *"Min opponent hit rate"* `[fetched]`. Both throw data away rather than reweighting it. Show opponent effect as a signed number with a one-line plain explanation — Opta's sentence is the model to copy: *"beating Real Madrid will give you more points than beating Real Valladolid"* `[fetched]`.
8. **Use a dot/outcome display, not only a percentage.** Quantile dotplots with 50 outcomes produced measurably better and more consistent decisions than a no-uncertainty control, and both dotplots and CDFs beat textual uncertainty (Fernandes et al., CHI 2018). Opta already ships a **"Stacked bar / Dot plot"** toggle on its predictions page `[fetched]` — the pattern is already legitimate in this category.
9. **Do not multiply probabilities in the combination builder.** Same-match statistics are correlated; hourly rain probabilities famously fail to aggregate to the daily figure for exactly this reason. Either model the joint distribution or state on screen that the combined figure assumes independence and is therefore an upper bound on confidence. This is a credibility landmine.
10. **Every screener in the category opens empty, and you can beat them by landing on something.** Prop Hunter lands on *"Set up your search — Pick a day, a stat and your leagues in Filters, then press Find Players."* Team Trends lands on *"No Games Available."* A daily product should open on today's most informative forecasts with filters pre-set.

---

## 2. StatsHub (statshub.com) — the direct competitor

All of this section is `[fetched]` on 2026-11-06 unless marked. Positioning, from the About page: *"Football data for punters who demand more"* and *"level the playing field"* ([statshub.com/about](https://statshub.com/about)).

### Information architecture
Top nav: **Fixtures | Prop Hunter | Prop Screener | Player Trends | More**. Inside any of the three tools there is a second segmented control — **Trends | Screener | Hunter** — so the three tools are siblings you flip between, not separate destinations. Full route list, from the homepage markup: `/prophunter`, `/prop-screener`, `/player-trends`, `/team-trends`, `/team-screener`, `/referees`, `/player-stats`, `/team-stats`, `/stats-explained`, `/odds-converter`, `/odds-api`, `/free-bets`, `/free-tools`, `/features`, `/blog`, `/news`, `/league/{slug}/{id}`, `/leagues/{country}/{slug}/{id}`, `/player/{slug}/{id}`, `/fixture/{home}-vs-{away}-{hash}/{id}`.

Sitemap index at `https://statshub.com/sitemap.xml` splits into static, blog, teams, players, fixtures, leagues, referees — i.e. every entity type is an indexed page. There is a Spanish locale (`/es/...`).

### Homepage — the fixtures feed ([statshub.com](https://statshub.com/))
- H1: *"Today's Football Fixtures, Player Stats & Team Stats"*, then the date and a language switch.
- Subhead states coverage and metric set in one line: *"Live scores and fixtures from 120+ leagues, with the player and team stats behind every match: shots, tackles, fouls, cards and corners, side by side with the odds."*
- Date navigation: `Previous day / Fri, 06 Nov / Next day` plus a dropdown of `Yesterday, Today, Tomorrow` and then 14 named weekdays.
- Fixtures grouped **Popular Competitions** first (each with a match count), then **Competitions A–Z**, with a `Collapse all` control.
- An inline cross-promo card sits between competition groups: *"🎯 Find props worth backing — Screen every player line and see who is in form. Both tools are free."*
- A Telegram widget shows pick cards with engagement counts: *"Silva · Card @5.50"*, *"Haaland · O0.5 Goals @2.10"*, *"12:42 2.1K 🔥 84"*, and *"StatsHub Football 12.4K subscribers"*.
- A **Community Tweets** module: *"Tag @StatsHubCom for a chance to be featured. Only tweets for upcoming games in the next 24 hours will be shown."*

**Read:** the feed is a conventional scores-site index. Its forecast content is not on the feed — it is in the two tools and in Telegram. There is no per-fixture forecast card on the feed at all. That is an opening: our fixtures feed carries forecast cards, theirs does not.

### Prop Hunter ([statshub.com/prophunter](https://statshub.com/prophunter))
Tagline: *"Find players whose recent games clear a line, then check the price."* Tabs: **Players | Saved picks**. Side panels: **Filters | Presets | Saved**.

Filters, as labelled:

| Group | Controls |
|---|---|
| Date & leagues | `When`: Today / 24h / 2 days / 3 days / 7 days; `Leagues` |
| Filter by | `Stat`: Shots, Shots on target, Fouls committed, Fouls won, Tackles |
| | `Measure by`: **Hit rate \| Average** |
| | `Hit rate` 50%+; `Line` Over 0.5; `Games counted` Last 10 games |
| | `Bookmakers` — *"All bookmakers 15 of 15 active"* |
| Advanced (optional) | `Position` GK/DEF/MID/FWD; `Venue` Both/Home/Away; `Lineup` All/Predicted/Confirmed; `Min. minutes`; `Betting line`; `Min Odds` |
| Advanced, with help text | `Started the match` — *"Only games the player started, not ones they came on in."* |
| | `Super Sub` — *"Combine a substitute's stats with the player they replaced."* |
| | `Selected leagues only` — *"Stats come from every league the player played in."* |
| | `Minimum games played` — *"Skip players with too few recent games, up to the Last X Games window."* |
| | `Max games ago` — *"Only show players who last played for their team within the last X games."* |

**The best thing on the site.** Above the results, the filter state is restated as one sentence: **"Shots over 0.5 in 5 of the last 10 games (50%)"**. It updates live. It is the only place in the whole category where a user can read back what they just built.

**Presets** — described as *"Ready-made searches, each a different angle. Tap one to see its players straight away."* Eight of them, each with a human name, a one-line rationale, and its parameters shown as chips:

| Preset | Copy | Parameters |
|---|---|---|
| The Classic (*"Most saved"*) | *"The search people save most: a shot in at least 8 of their last 10."* | Shots over 0.5 · Last 10 · 80%+ |
| Value CB Shots | *"Defenders who had a shot in 10+ of their last 20, still priced 2.20 or bigger."* | Shots over 0.5 · Last 20 · 50%+ · DEF · 60'+ · Odds 2.20+ |
| Hot Form | *"Attackers with a shot on target in 4 of their last 5: who is in form right now."* | SOT over 0.5 · Last 5 · 80%+ · MID/FWD · 60'+ · Odds 1.80+ |
| Volume Strikers | *"Forwards with 2 or more shots in 11+ of their last 15, at 1.60 or bigger."* | Shots over 1.5 · Last 15 · 70%+ · FWD · Odds 1.60+ |
| Midfield Enforcers | *"Midfielders who committed a foul in 12+ of their last 15, at 1.50 or bigger."* | Fouls committed over 0.5 · Last 15 · 80%+ · MID · 60'+ |
| Foul Magnets | *"Players fouled twice or more in 6+ of their last 10, at 1.90 or bigger."* | Fouls won over 1.5 · Last 10 · 60%+ · MID/FWD |
| Tackle Machines | *"Defenders and midfielders with 2+ tackles in 9+ of their last 15, at 1.80 or bigger."* | Tackles over 1.5 · Last 15 · 60%+ · DEF/MID · 60'+ |
| Card Watch | *"Booked in 7+ of their last 20, priced 3.00 or bigger to be carded."* | Yellow cards over 0.5 · Last 20 · 35%+ · DEF/MID |

Note the pattern: the preset name is a **player archetype**, not a parameter set. "Midfield Enforcers" and "Foul Magnets" are how users actually think. Note also that each description states the count *and* the window in words ("a shot in at least 8 of their last 10") rather than only a percentage — the frequency framing arrives by accident, and it reads well.

**Empty state:** *"Set up your search — Pick a day, a stat and your leagues in Filters, then press Find Players."* Nothing is computed until you press the button.

### Prop Screener ([statshub.com/prop-screener](https://statshub.com/prop-screener))
Tagline: *"Player props by hit rate, odds and form."* A **Player | Team** toggle (Team marked `New`), and a **Saved picks** tab.

Results are a **table**, not cards:

| Player | Market | Odds | L5 | ▸ L10 | L15 | Matchup | Stats |
|---|---|---|---|---|---|---|---|

Three windows side by side (L5/L10/L15) with the sort marker on L10 — so the user eyeballs whether the three agree. That is a crude but real uncertainty cue, and the only one in the product.

Markets (12): Fouls committed, Fouls won, Tackles, Player shots created, Shots, Shots on target, Goals, Assists, Scored or assisted, Passes, Yellow cards, Saves.

Filters: `Over / Under` (Both/Over/Under); `Window` L5/L10/L15; `Hit rate L10` 0–100% range slider; `Hit rates from` **Same league | All competitions**; `Super Sub` — *"Count a substitute's minutes towards the player they replaced."*; `Lineup` All/Predicted/Confirmed; `Max games ago`; `Odds` 1.30–10.00+ slider; `Bookmakers` (15 named: 10bet, Altenar Group, Bet365, Betfair Exchange, Betfred, BetMGM UK, BetVictor, BoyleSports, Kambi, Ladbrokes, Paddy Power, Pinnacle, Skybet, Unibet, William Hill); `Fixture date` Any/Today/24h/2d/3d/7d; `Leagues`. One preset: *"L10 hit rate, highest"*.

### Player Trends ([statshub.com/player-trends](https://statshub.com/player-trends))
*"Best recent hit-rate streaks across all player props. **Shows the strongest window (3-40 games) for each prop.**"*

That sentence is the product's biggest statistical problem, stated as a feature — see §9.

Extra filters not in the other tools: `Min games in streak` (3 games); `Min hit rate` (60%); `Last game` Any/Played/Started with help *"Played includes coming off the bench."*; `Lineup` with help *"Predicted includes players already confirmed."*; **`Exclude injured & suspended`**. Markets add **Foul involvements** to the Screener's 12.

**"How to read a card" — a tappable card anatomy.** This is a genuinely good onboarding device and worth copying. Instruction: *"Tap any part of the example card, or step through them below it."* Nine numbered parts:

1. **Kick-off and fixture** — *"When the game starts and who is playing, with the player's side underlined. Tap the fixture on a real card for the match page."*
2. **Lineup and activity**
3. **Player and position**
4. **Best price**
5. **Market and line**
6. **Record and hit rate**
7. **Per 90 and average**
8. **Recent games**
9. **Season average and opponent**

(Descriptions for 2–9 load client-side and I could not read them; the headings are verbatim from the markup.) The *composition* is the finding: a forecast card in this category carries fixture, availability, identity, the number, the threshold, the recent record, a rate, a recent-games strip, and a season/opponent baseline — nine slots. Ours needs the same nine jobs covered, with the model's probability and interval replacing slots 4 and 6.

### Team Trends ([statshub.com/team-trends](https://statshub.com/team-trends))
*"Best recent hit-rate streaks across all team props. Shows the strongest window (3-8 games) for each prop."* and *"The strongest streaks on every team bet, with the best price."*

Team markets (7): Shots, Shots on target, **Corners**, Goals, Cards, Tackles, **Offsides**. Extra filters: **`Min opponent hit rate`** and **`Home / away form only`**. Card anatomy is 8 parts (same minus position).

### Referees ([statshub.com/referees](https://statshub.com/referees))
*"Card and penalty records for every referee, and who is taking the next games."* A rare and valuable page type.

Filters: `When`; **`Kick-off within`** Any/1h/3h/6h/12h; `Upcoming games only` — *"Hide referees with no game appointed yet"*; **`Strictness`** Any / Lenient / Average / Strict; `Card line` Over 3.5 / 4.5 / 5.5; hit rate Any/50%+/60%+/70%+/80%+; `Minimum games` Any/10+/25+/50+/100+; `This season only` — *"Only games in each competition's current season"*; `Beats the price` Off/Over/Under; `Has card odds`.

**Strictness as a three-way label (Lenient / Average / Strict) is the one place in the product where a continuous quantity is binned into words.** It works. It is also exactly what a model should produce as a *number* with an interval, because referee samples are small.

### Player page ([statshub.com/player/erling-haaland/16391](https://www.statshub.com/player/erling-haaland/16391))
- Header: initials avatar, name, club, then a single metadata line — *"Forward · #9 · 26y · 195cm · Left"*.
- Tabs: **Player Stats | Trends**.
- **Next match** card: competition, opponent, kick-off, and a `View match` action. This is the fixture→player→fixture loop closed in one control.
- **Game logs** with a **Table | Charts** toggle, plus `Super Sub` and `More Filters`.
- Quick metric chips above the log: Shots, SOT, Goals, Assists, G + A, Fouls, Fouls won, Tackles, Yellow cards.
- Full metric picker (`More stats`) adds: Fouls committed, Fouls won, Tackles, Player shots created, Foul involvements, Scored or assisted, Expected goals (xG), Expected assists (xA), xG + xA, Passes, Crosses, Offsides, and six **Beta** granular markets: *Shots outside the box, Shots on target outside the box, Headed shot, Headed shot on target, First half shots, First half shots on target*.
- **Positions Played** (empty for this player: *"No position data for this season yet."*).
- **Player Traits** — *"Stats compared to other forwards"* (a positional-percentile module, same idea as FBref and FotMob).
- **Season Performance** — `Minutes played / Matches` header, a **Total | Per 90** toggle, and a `Rank` column, grouped: **Shooting** (Goals, xG, Shots, Shots on target, Goal conversion, Big chances missed, Headed goals, Penalty goals) · **Passing** (Assists, xA, Accurate passes, Pass accuracy, Key passes, Big chances created, Accurate long balls, Long ball accuracy, Accurate crosses, Cross accuracy) · **Possession** (Successful dribbles, Successful dribbles %, Duels won, Duels won %, Aerial duels won, Aerial duels won %, Touches, Dispossessed) · **Defending** (Tackles, Interceptions, Clearances, Recoveries, Blocked shots) · **Discipline** (Fouls committed, Fouls drawn, Yellow cards, Red cards, Offsides).
- Auto-generated SEO prose at the foot: *"Erling Haaland player profile"*, a season summary, *"next match"*, *"previous match"*.

**A live data defect, worth noting as a warning.** On the page I fetched, every value in Season Performance rendered as `—`, and `Minutes played : — · Matches : —`, while the prose below described *"Erling Haaland's 24/25 season"* with concrete numbers alongside a November 2026 fixture. Mixed-season and empty states are visible in production. `[fetched]`

### Match / fixture page ([example](https://www.statshub.com/fixture/fc-twente-vs-pafos-fc-mw43n7/498343))
- Header: crests, score, `FT · Thu 05 Nov`, venue (*De Grolsch Veste*), and the **referee with a bare number** — *"Michal Očenáš 4.50"*, with no unit or label visible.
- Tabs: **Players | Teams | Lineups | Tables | Trends | Charts | Opponent Stats**.
- A home/away team toggle, then the same metric picker as the player page.
- Filters: `Last 20 Games`; `Home + Away / Home / Away`; `Competitions`; `Bookmakers`; **`Difficulty: All Matches / Easier Matchups / Harder Matchups`**; `Super Sub`; `H2H`.

**"Opponent Stats" as a tab and "Difficulty" as a filter are the two places StatsHub gestures at opponent adjustment — and both are manual.** The user has to remember to apply them, and applying them shrinks the sample.

### Stats Explained ([statshub.com/stats-explained](https://statshub.com/stats-explained))
A glossary, badged *"Official Opta Definitions"*, *"60+ Football Stats"*, *"Beginner to Advanced"*. Nine categories with counts: Goals & Shots (10), Passing & Assists (6), Sequences & Possession (2), Ball Control & Movement (5), Defending (5), Duels & Physical (2), Fouls & Discipline (5), Set Pieces (2), Miscellaneous (2). Each entry carries a **difficulty badge** (Basic / Intermediate / Advanced) and a category badge; there is a search box plus Category and Difficulty filters.

**The difficulty badge is a good idea we should copy for our own engine concepts** (shrinkage, opponent adjustment, calibration): it gives a reader permission to skip.

### Monetisation ([statshub.com/pricing](https://statshub.com/pricing))
The boundary is stated in one line and it is a **capability split, not a metering split**: *"Start free. Upgrade for the Model."* / *"150+ leagues scanned every day for mispriced player props. **The stats stay free; the Model finds the bets.**"*

| Tier | Price | Included |
|---|---|---|
| **StatsHub** | **£0** — *"Free forever · no card"* | Player & team stats, form, H2H · Trends tool · Prop Screener · PropHunter · Referee tool |
| **The Model – Matchday** | **£29.99**/mo, struck through from £49.99, *"Save 40%"*, *"£1.00 a day · billed monthly"* | all of the above, plus: Model fair odds on every prop · 10+ bookmakers scanned for +EV bets · Best odds across bookmakers · Private Sharps chat · **Kick-offs in the next 12 hours** |
| **The Model Platinum** | **£99.99**/mo, struck through from £149.99, *"Save 33%"*, *"£3.33 a day"* | plus: Full slate days ahead · All 3 independent models · Consensus picks · Extra filters & thresholds · Short, medium & long windows · Early access |

Mechanics of the boundary worth noting:
- The free tier is **an account, not a trial**: *"The free plan is an account, not a trial: the stats, trends, Prop Screener, PropHunter and referee tools stay free."*
- The paid gate on the cheap tier is a **time window**, not a feature — Matchday gives you the model only for *"games kicking off in the next 12 hours"*, and Platinum unlocks the full slate days ahead. Recency is the thing sold twice.
- Every tier card shows the full feature list with the locked items visible and a *"See what's included 5 / 10 / 15"* counter. The ladder is legible at a glance.
- Three named model personalities: *"Franko spots trends fast. Hugo keeps things steady on shots. Theo was built with actual bookmaker traders and only speaks when he's confident."* Plus *"Built with Real Traders — These weren't built in a lab. We worked with professional sports traders who actually set lines for a living."*
- Window choice is sold as a feature: *"Player just changed clubs? Short window catches that. Steady veteran? Long window smooths the noise. The models adapt — or on Pro, you pick the window yourself."*

### How StatsHub does "trust"
Four devices, in descending honesty:
1. **The free glossary with Opta attribution** (`/stats-explained`). Genuinely good.
2. **Per-row history**: *"See the Track Record First — Every pick shows how it would have hit over the last 10, 20, and 30 games. No black boxes — you see the evidence before you bet."* This is backtested hit rate per row, not model accuracy.
3. **An affiliate's betting P&L presented as the track record**: *"+213u Units profit, Dec 2025 – Mar 2026"*, *"1 unit = one standard stake"*, *"From @MaccasValueBets using the model. All publicly recorded."* A second block: *"2,500 bets from the Model"*, *"£6,860 profit"*, *"12.1% ROI"*, *"13.1% ROI on player props"*, *"1,886 settled"*, sourced as *"His own spreadsheet, shared with us."*
4. **An explicit admission of selection bias, presented as politeness**: *"We've crossed out and hidden the other tipsters in it who are showing a negative ROI, as we don't want to throw shade at anyone."*

That fourth line is the whole weakness in one sentence: the evidence is a filtered sample of other people's records. No calibration, no reliability curve, no count of forecasts issued, no baseline comparison.

---

## 3. FotMob `[search]`

FotMob is the best-designed mass-market football app and the closest reference for *scanning*. I could not read its pages directly (client-rendered; its markup forbids automated use), so the following is from search-surfaced page extracts.

- **Season shot map** with a summary strip of totals — e.g. *"On target: 34% · 44 Shots · 4 Goals · 4.74 xG"*. Individual shots are filterable and each carries its **xG and xGOT**.
- **Season performance** in grouped categories (Shooting / Passing / Discipline), with metrics including xG, **xGOT (expected goals on target)**, non-penalty xG, shots on target, expected assists, passes, duels, discipline. Example: *"Shooting · Goals 5 · Expected goals (xG) 5.08 · xG on target (xGOT) 3.89"*.
- **Per-match rating** shown inline beside each recent match, with minutes — e.g. *"45' 4.9"*. This is the form strip: result, minutes, rating, in one row.
- **Player traits** — percentile bars comparing the player to others in the same position.
- Nav includes a **Predictor** (user predictions, not a model) and a **Lineup Builder**.
- **Monetisation:** advertising plus a cheap subscription. App Store in-app purchases listed as *"Monthly subscription $1.99, 3 months membership $3.99, 1 year subscription $9.99"*; prices vary by region and the plan is unnamed in that listing. The US listing advertises *"detailed match stats, including xG and shot maps"* in the free app, so basic xG appears not to be gated. FotMob publishes an advertising media kit at `data.fotmob.com`. `[search]` — I could not confirm which specific features sit behind the paid tier in 2026.

**What to take:** the *minutes + rating + result* triple on every form row, and the shot map's summary strip (a chart that states its own totals so you never have to count marks).

**What they cannot do:** everything is retrospective. There is no forward-looking number for any player statistic.

---

## 4. Sofascore `[search]`

Direct fetch returned HTTP 403. All of the following is from Sofascore's own news articles, surfaced via search.

- **Sofascore Rating** exists at two time scales, explicitly labelled: *"Match Rating – Shows how a player and team performed in a single game"* and *"Season Rating – Averages performances across an entire competition or season."* Showing the same construct at two scales with different names is a good pattern.
- **Rating categories are documented but inconsistent across their own articles**: one breakdown lists Passing, Dribbling, Defending plus Goalkeeping; another says the categories are grouped into five including Shooting. The two articles conflict and I could not resolve which is current ([rating breakdown](https://www.sofascore.com/news/sofascore-rating-breakdown-what-goes-into-calculations/)). That inconsistency is itself the finding: a flagship composite whose own documentation disagrees with itself.
- **Attack Momentum** — a live in-match graph of *"which team is on the attack and when"*, built from *passes into dangerous areas, shots on and off target, set pieces, and counter-attacks*, and explicitly *"available to all Sofascore users"* ([article](https://www.sofascore.com/news/how-sofascores-attack-momentum-changed-sport-analysis)).
- **Maps**: heatmaps, plus newer **Passing, Dribbling and Defending Maps**, reached by opening a match and switching between maps on a player's stats page. The Defending Map covers *"contributions without the ball such as tackles, interceptions, and clearances"* ([article](https://www.sofascore.com/news/introducing-sofascores-new-maps-a-smarter-way-to-read-the-game)).
- An **"attribute overview"** of scores covering attacking, defending and creativity. I could **not verify** whether these are displayed as percentiles, nor the exact section names on a live player page.

**What to take:** Attack Momentum is the category's proof that users will read a continuous, derived, non-obvious quantity if it is drawn as a shape rather than printed as a number. A time-series of "forecast pressure" or a distribution shape is within audience tolerance.

---

## 5. Flashscore `[fetched] + [search]`

- The homepage fetched (HTTP 200) but its match content is client-rendered. What is server-rendered is a navigation shell: `Scores | News | Favorites`, a sport bar (Football, Tennis, Basketball, Hockey, Golf, Formula 1, Baseball, Snooker), `Pinned Leagues`, `My Teams`, `Rankings (FIFA, UEFA)`, and a long alphabetical country list from Albania to Vietnam, each expanding to that country's competitions. **Breadth is the product.** `[fetched]`
- The top of the page carries stacked gambling-harm disclaimers in four jurisdictions (French, German, Portuguese/Brazilian, Ukrainian) — e.g. *"18+. Verantwortungsbewusst wetten."*, *"18+ Ministério da Fazenda adverte: Aposta não é investimento."* `[fetched]` **Flashscore's monetisation is bookmaker advertising**, and the regulatory cost of that is visible above the fold on every page.
- Reviews describe Flashscore as broad-coverage with thinner per-player depth than Sofascore or FotMob, and note that stats depth varies by competition. These are low-authority listicles; treat as weak. `[search] [unverified]`

**What to take:** the country-A–Z plus pinned-leagues plus My Teams pattern is how a 120-league product stays navigable. Our fixtures feed needs pinning and a flat alphabetical escape hatch, not only "popular leagues".

**The opening:** a product whose chrome is dominated by gambling warnings cannot be the calm, analytical option. That position is vacant.

---

## 6. Understat, FBref / StatsBomb, Opta / Stats Perform

### Understat — **down at the time of this audit** `[fetched]`
`https://understat.com/league/EPL` returned HTTP 200 with a body consisting entirely of:

> Understat.com
> We will come back soon

I found **no** reports confirming an outage or explaining it; Similarweb still showed tracked traffic for Feb and Apr 2026. **Verified down on 2026-11-06; cause unknown.** Do not cite Understat's design from memory in the review — it may not exist by the time we ship. It is also the live demonstration of why free analytics sites are a fragile reference point.

### FBref `[search]` (direct fetch returned HTTP 403)
From its own explainer, [fbref.com/en/about/scouting-reports-explained](https://fbref.com/en/about/scouting-reports-explained):

- *"Scouting Reports compare a player's statistics to other players at their position over a specific amount of time. **Each statistic is ranked as a percentile** based on how it compares to other players."*
- Eligibility: *"any player who has reached a minimum amount of playing time in a competition **with Opta data** receives a scouting report."* So FBref's own depth is licensed, not proprietary — a platform dependency.
- Two forms: a **summary** on the player page and a **complete scouting report** with percentiles for all statistics.
- Two windows only: **Last 365 Days**, or an individual domestic league season.
- Per-90 values sit beside percentiles, with metric names spelled out including their definition — e.g. *"Shots Total"*, *"npxG: Non-Penalty xG"*.

**What to take:** the **per-90 value next to its percentile** is the most information-dense player row in the category. One number says *how much*, the other says *compared to whom*. Our player page should carry both, plus a third our competitors cannot: *what we expect next*.

**What they cannot do:** a percentile is relative and retrospective. A 99th-percentile tackler tells you nothing about tomorrow. And with only 365-day and full-season windows there is no recency weighting and no opponent view.

### Opta / Stats Perform — theanalyst.com `[fetched]`
This is the most sophisticated probability presentation in football, and the closest reference for our track-record and match pages.

**The predictions page** ([theanalyst.com/competition/premier-league/predictions](https://theanalyst.com/competition/premier-league/predictions)):

- Competition sub-nav: `Overview | Articles | Stats | Predictions | Power Rankings | Table | Fixtures`.
- A view toggle **`Positions | Outcomes`** and, crucially, a chart-type toggle **`Stacked bar | Dot plot`**.
- Column headers carry their own definition inline: *"Winners — Win the league"*, *"Likely finish — Chance of finishing in each zone or reaching each round, 0 to 100%"*, with an axis labelled `25% 50% 75% 100%`.
- Zone legend named explicitly: *"UEFA Champions League, UEFA Europa League, Relegation"*.
- A second table, *"Finishing position predictions"*, ranked by expected finishing position, with `p PTS — Predicted final points` and then **twenty columns**: *"1 Chance of finishing 1st"* through *"20 Chance of finishing 20th"*. Example row: Arsenal, 81.69 predicted points, then 70.15 / 19.65 / 6.57 / 2.22 / 0.63 / 0.34 / 0.28 / 0.05 / 0.05 / 0.04 / 0.02 / 0.00 …

**That 20-column matrix is the whole distribution, not a point estimate, shown as a table.** It is the most honest forecast display in football. Its flaw is overprecision: two decimal places, including `0.00`, on a simulation-derived figure.

**Methodology, published in plain words at the foot of every supercomputer article** under the heading *"How Does the Opta Supercomputer Model Work?"*:

> *"The model estimates the probability of each match outcome (win, draw or loss) by using betting market odds and Opta Power Rankings. The odds and rankings are based on historical and recent team performances. The model considers the strength of opponents by using these match outcome probabilities and simulates the remaining fixtures in the competition thousands of times. By analysing the outcome of each of these simulations, the model can see how often teams finished in each league position to create our final predictions."*

Two things to note. First, it is four sentences and a layperson can follow it. Second, **it discloses that the model consumes betting market prices** — so Opta's probabilities are partly a repackaging of the market, not an independent forecast. That disclosure is honest but it lives in article prose, not next to the table.

**Frequency framing is their house style** `[fetched]`, from [the 2025-26 projections article](https://theanalyst.com/articles/premier-league-predictions-2025-26):

- *"Liverpool are the favourites to win the title, doing so in **28.5% of simulations**."*
- *"19 of the 20 competing teams won the title **at least once in our 10,000 season simulations**."*
- *"every single team was relegated **at least seven times**, while 19 finished bottom in at least one sim."*
- *"**The one simulation out of 10,000** in which Arsenal finished 20th…"*
- *"City regain their crown in just 18.8% of sims."*
- *"After simulating every match of the 2025-26 Premier League season 10,000 times, we're able to average the points total of every club across those simulations…"*

**They also quote their own past forecasts against the outcome, inside the prose** — a lightweight accountability pattern:

- *"Arne Slot had just a **5.1% chance** of winning the Premier League in his first season at Anfield **last summer according to the supercomputer**…"*
- *"They were heavily backed by the supercomputer last season with an **82.2% likelihood** of winning the league, but that has understandably reduced…"*
- *"Bournemouth (10.1%) and Nottingham Forest (8.9%) … that is certainly a better chance than the supercomputer gave either of them last summer. The Cherries' chances back then were just 0.6%, while Forest's were less than 0.1%."*

**Opta Power Rankings** `[fetched]` — how to explain a derived rating and an opponent adjustment in two sentences:

> *"the Opta Power Rankings are a global team ranking system that assigns an ability score to over 13,000 men's domestic football teams and over 2,000 women's domestic football teams **on a scale between zero and 100, where zero is the worst-ranked team in the world and 100 is the best team in the world**. Scores are determined based on performances relative to others, so **beating Real Madrid will give you more points than beating Real Valladolid**, for example."*

Both anchors of the scale are named, and the opponent adjustment is explained by example rather than by formula. Copy this sentence shape.

**Do they publish accuracy?** Not properly. `[search]` Their 2023-24 season review compared pre-season projections to the final table narratively — *"the top three accurately reflected the pre-season picks"*, *"well over half the division placed within two positions"*, and a note that on the final day the model gave Manchester City an 84.3% title probability ([article](https://theanalyst.com/articles/opta-supercomputer-premier-league-2023-24-predictions/)). I found **no Brier score, no reliability diagram, no calibration bins, and no third-party evaluation**. A claim that Opta has not released enough inputs for outside reproduction appeared in a non-English secondary source and is `[unverified]`.

**What Opta cannot do:** it is team- and competition-level. There are no player-statistic forecasts anywhere in the public product. That is precisely our territory.

---

## 7. FiveThirtyEight — the best precedent, and it is gone

**Verified dead on 2026-11-06** `[fetched]`. All three relevant URLs now redirect to ABC News:

| URL | Result |
|---|---|
| `projects.fivethirtyeight.com/soccer-predictions/` | redirects to `abcnews.go.com/politics` |
| `projects.fivethirtyeight.com/checking-our-work/` | redirects to `abcnews.go.com/politics` |
| `fivethirtyeight.com/features/how-our-club-soccer-predictions-work/` | redirects to `abcnews.com/politics` |

The content is not merely unmaintained; it is unreachable at its canonical URLs. I could not reach the Wayback Machine from this session, so the following is from search-surfaced excerpts `[search]` and should be treated as approximate wording.

**"Checking Our Work"** was the only consumer-facing forecast-accuracy page of its kind. What it did:
- Defined calibration in one plain sentence — whether events forecast at 30 percent happen about 30 percent of the time.
- Drew a **calibration plot with binned forecasts against a 45-degree reference line**: *"If our forecast is well-calibrated, all the bins on the calibration plot will be close to the 45-degree line."*
- Reported a **skill score against a naive baseline** ("an estimate based on historical averages"), which is the part most people forget — calibration alone is satisfiable by always predicting the base rate.
- Was willing to publish an unflattering reading of its own work: for MLB, *"very well-calibrated, though we rarely went out on a limb"* — i.e. it reported low discrimination as a limitation.

**Methodology** was a revised **Soccer Power Index (SPI)**, described as their best estimate of overall team strength, derived from expected goals scored versus conceded.

**Why this matters to us.** The single most trust-building page ever built in this space has been taken offline, and nobody in football has replaced it. A track-record page that does what "Checking Our Work" did — bins, a 45-degree line, a skill score against a stated baseline, and an honest reading including the bad news — is available, unoccupied, and defensible.

---

## 8. Player-statistics screener tools (beyond StatsHub) `[search]`

I could not reach any of these hosts from this session. Everything here is from search extracts; treat specifics as approximate and re-verify before citing externally.

| Tool | What it does | Free/paid boundary |
|---|---|---|
| [playerstats.football/player-props-finder](https://playerstats.football/player-props-finder) | Hit rates and streaks for shots, tackles, fouls, cards. Changelog describes a streak feature — *"Find players with consecutive games of x+ football stats"* — and a *"Hit Rate Criteria"* filter added Jan 2025. | **Metered: 3 free searches per day**, then login. Features page lists **£6.99/mo** after trial. |
| [footymetrics.com/player-props-finder](https://www.footymetrics.com/player-props-finder) | Filter every player with an upcoming fixture by stat, threshold, hit rate, league, position, lineup status, odds range. Example searches given as natural language: *"defenders with 1+ shot at odds above 2.00"*, *"midfielders averaging 3+ tackles playing tomorrow"*. Also a **"Fixture Scout"** with up to 4 conditions, match predictions, referee analytics. | **Metered: 3 Props Finder + 2 Fixture Scout searches per day** free; premium removes caps. Price not found. |
| [pickfinder.app/leagues/soccer](https://www.pickfinder.app/leagues/soccer) | Player statistic hit rates against the exact threshold across ~20 competitions incl. PL, UCL, MLS, Liga MX, NWSL. | Not determined. |
| [dimers.com](https://www.dimers.com/best-props/swc) | Filtering largely behind "Dimers Pro". | Paid. |
| MatchMind | Advertises a **public track record with a Brier score and calibration error**, a post-match audit page, and reliability diagrams, *"including bad weeks"*. | Unknown. **`[unverified]` — these are self-reported marketing claims on third-party listing sites; I could not reach the product.** |

**Three findings from this group:**

1. **Two different free/paid boundaries exist in the category.** Metering searches (playerstats.football, FootyMetrics: 3/day) versus splitting capability (StatsHub: counting free, model paid). Metering is cheap to build and immediately annoying; it also prices the *act of looking*, which is the wrong thing to charge for in a daily-habit product. The capability split fits an engine-based product: the counting layer is a commodity, the forecast is not.
2. **Natural-language example searches are how these tools teach their own filters** — *"midfielders averaging 3+ tackles playing tomorrow"*. Combined with StatsHub's live filter restatement, the pattern is clear: the filter state should be a readable sentence in both directions.
3. **Someone is already claiming Brier scores and reliability diagrams as a marketing feature.** Even unverified, that tells us the "published calibration" position will not stay empty forever.

---

## 9. Consolidated metrics table

"Counting tool" means a product that aggregates recorded events — StatsHub, FotMob, Sofascore, FBref. "Engine" means a product with a fitted distribution, opponent adjustment and shrinkage.

### Player metrics

| Metric | Who shows it | Why it matters | Can a counting tool do it? |
|---|---|---|---|
| Minutes played, appearances | All | Denominator for everything; the biggest single driver of a per-match forecast | Yes |
| Goals, assists | All | Table stakes; low-frequency so weak for forecasting | Yes |
| Shots | StatsHub, FotMob, Sofascore, FBref | The core forecastable volume statistic; high frequency, stable rate | Yes (count) |
| Shots on target | StatsHub, FotMob, Sofascore, FBref | Second core market; needs a conversion rate on top of shot volume | Yes (count) |
| Tackles | StatsHub, FotMob, Sofascore, FBref | Core defensive market; strongly position- and possession-dependent | Yes (count) |
| Fouls committed | StatsHub, FotMob, Sofascore, FBref | Core discipline market; feeds cards | Yes (count) |
| **Fouls won / fouls drawn** | StatsHub (as *Fouls won*), FBref (*Fouls Drawn*); absent or buried elsewhere | **Rare and valuable.** A separate forecastable market with different drivers (dribbling volume, opponent aggression) | Yes, but almost nobody surfaces it |
| **Foul involvements** (committed + won) | **StatsHub only**, in Player Trends | A composite that smooths two sparse series into one less-sparse one | Yes |
| Yellow cards | StatsHub, FotMob, Sofascore, FBref | High-interest, low-frequency — the market most in need of shrinkage and a referee term | Count yes; forecast badly |
| Red cards | FotMob, Sofascore, FBref | Too rare to forecast per match; context only | Yes |
| Passes, pass accuracy | All | High-volume, very stable — good for demonstrating interval width honestly | Yes |
| Key passes / chances created | FotMob, Sofascore, FBref | Creative-output proxy | Yes |
| **Player shots created** | **StatsHub** | A distinct market (shots generated for others) that most products fold into "key passes" | Yes |
| Saves | **StatsHub** (as a market), FBref | **Rare as a forecastable market.** GK statistics are usually relegated to a separate page; StatsHub treats saves as a first-class market | Yes |
| xG, xA, npxG | FotMob, Sofascore, FBref, StatsHub | Already model output; the audience's on-ramp to accepting modelled numbers | No — requires a shot-quality model |
| **xGOT (expected goals on target)** | **FotMob** | Separates shot quality from placement quality | No |
| Per-90 rates | FBref, FotMob, StatsHub (Total/Per 90 toggle) | Makes players with different minutes comparable | Yes |
| Positional percentile / "traits" | FBref (*percentile*), FotMob (*Player traits*), StatsHub (*Player Traits — stats compared to other forwards*) | Answers "is this a lot?"; the single most useful context device in the category | Yes |
| Match rating (composite) | FotMob, Sofascore | A single scannable number per match; drives habit | Yes, but opaque — Sofascore's own docs disagree on its composition |
| Duels, aerial duels, dribbles, touches, dispossessed | StatsHub, FotMob, Sofascore, FBref | Explain *why* a rate is what it is | Yes |
| Interceptions, clearances, recoveries, blocked shots | StatsHub, Sofascore, FBref | Defensive context behind tackle rates | Yes |
| Offsides | StatsHub, FBref | Thin market; useful as a positioning signal | Yes |
| **Shots outside the box / headed shots / first-half shots** | **StatsHub (Beta)** | **Rare.** Sub-market granularity; each is a smaller sample, so each needs *more* shrinkage, not less | Count yes — but at these sample sizes a raw count is actively misleading |
| Shot map / heatmap / passing map | FotMob, Sofascore, StatsHub (claimed) | Spatial context; high perceived value, low decision value | Yes |
| Positions played | StatsHub, FBref | Position changes invalidate a rate — critical and almost always missing from screeners | Yes |
| Lineup status (predicted / confirmed) | **StatsHub** (filter and card slot) | **The highest-leverage non-statistic on the page.** A forecast for a player who does not start is worthless | Yes (data), but only StatsHub makes it a first-class filter |
| Injury / suspension status | **StatsHub** (*"Exclude injured & suspended"*) | Same reason | Yes |
| **Expected minutes** | **Nobody** | The multiplier on every per-90 rate; the difference between a 90-minute and a 60-minute projection is ~33% of the expectation | **No — requires a model** |
| **Forecast probability of a threshold, next match** | **Nobody at player level.** StatsHub paid tier offers "fair odds" with undisclosed method | The actual question the user has | **No** |
| **Uncertainty interval on that forecast** | **Nobody** | Distinguishes "we are confident it's 60%" from "it's somewhere between 35% and 80%" | **No** |
| **Shrunk player rate** | **Nobody** | A player with 3 appearances should not show 100%; shrinkage toward position/league mean is the fix | **No — this is the single clearest engine-only metric** |
| **Opponent adjustment, as a number** | Nobody. StatsHub has *Easier/Harder Matchups* as a filter and an *Opponent Stats* tab; Opta adjusts internally at team level | Turns "8 of 10" into "8 of 10, but against sides that concede 30% more shots than Saturday's opponent" | **No** |
| **Full probability ladder (≥1, ≥2, ≥3 …) from one distribution** | Nobody. StatsHub shows separate hit rates per threshold, which can be mutually inconsistent | Internal consistency is a visible trust signal: P(≥2) must be ≤ P(≥1) | **No** |
| **Referee effect on a player's card forecast** | Nobody. StatsHub has a referee page and a card market, unlinked | Referee is a large, measurable term in card expectation | **No** |
| **Decomposition ("why is this number what it is")** | Nobody | Base rate + opponent + minutes + venue + referee, as a waterfall | **No** |

### Team metrics

| Metric | Who shows it | Why it matters | Can a counting tool do it? |
|---|---|---|---|
| Goals for/against, form, H2H | All | Table stakes | Yes |
| Shots, shots on target | StatsHub (Team Trends), all | Team-level volume markets | Yes |
| **Corners** | **StatsHub (Team Trends)**, Flashscore/FotMob in match stats | A genuinely popular market most analytics products ignore entirely | Yes |
| Cards (team) | StatsHub | Pairs with the referee page | Yes |
| Tackles, offsides (team) | **StatsHub** | Rare at team level | Yes |
| Possession, xG for/against | FotMob, Sofascore, Understat (when up), FBref | Strength proxies | No (xG) |
| **Opponent-conceded rates** | **StatsHub** (*Opponent Stats* tab, match page) | The input to opponent adjustment. Rare as a surfaced page | Yes (data); no (as an adjustment) |
| **Power ranking / ability score 0–100** | **Opta** (13,000+ men's teams, 2,000+ women's) | One number for strength, with both scale anchors named | No |
| **Expected points, finishing-position distribution** | **Opta** (20-column matrix) | Shows a distribution rather than a point estimate | No |
| **Team-level forecast with interval** | Opta (team only, no interval shown) | — | No |
| **Referee card/penalty record + strictness band** | **StatsHub only** | Rare, cheap to build, directly useful | Yes |

**Summary of the three tiers:**
- **Table stakes (must have, cannot differentiate):** minutes, appearances, goals, assists, shots, shots on target, tackles, fouls, cards, passes, per-90 rates, positional percentile, a recent-form strip, xG/xA.
- **Rare but clearly valuable (cheap differentiators):** fouls won, foul involvements, player shots created, saves as a first-class market, corners, offsides, referee records with a strictness band, opponent-conceded rates, positions played, lineup status and injury status as first-class filters.
- **Engine-only (the actual product):** expected minutes, shrunk rates, a numeric opponent adjustment, a forecast probability for the next match, an interval on it, a self-consistent probability ladder, a referee term in the card forecast, a decomposition of the number, correlation-aware combinations, and published calibration.

---

## 10. Betting vocabulary → the job it does → our replacement

Where a competitor uses a banned word, this is what it is for and what we build instead.

| Their word | The job it actually does | Our replacement |
|---|---|---|
| `Over 0.5 / Over 1.5` | Names the threshold the statistic is compared against | **"At least 1" / "at least 2"** — plainer, exact, and what the number means |
| `Hit rate` | Summarises "how often lately", and acts as a credibility cue for the row | **"5 of the last 10 matches"** as a count, kept visually distinct from the forecast. Never show a raw rate from fewer than ~8 observations without an interval |
| `Odds` / `Best price` | Two jobs: (a) an outside numeric estimate of the same event; (b) a **sort key for "which of these 4,000 rows deserves attention"** | Job (a) is not ours. Job (b) is the real need — replace with a model-internal salience: **"Furthest from this player's own baseline"**, **"Largest opponent effect"**, **"Highest confidence"** |
| `+EV` / `mispriced` | "Our number disagrees with the outside number, look here first" | **"Notable"** — ranked by departure from the player's own shrunk baseline and by interval width, not by disagreement with anyone |
| `Pick` / `my picks` | A thing I selected and want to keep | **"Saved forecast"**, **"Watchlist"**, **"Shortlist"** |
| `Props` / `markets` | A per-player statistic with a threshold | **"Statistic"** + **"threshold"**; the row is a **"forecast"** |
| `Parlay` / `accumulator` | Several forecasts considered together | **"Combination"** — and state the correlation caveat on screen |
| `Stake` / `unit` / `ROI` / `profit` | The only proof on offer that the numbers are worth paying for | **Calibration bins, a reliability curve, and a skill score against a stated baseline.** Strictly more informative and the thing a P&L cannot answer |
| `Bookmaker` / `sportsbook` | The source of the outside estimate | Omit entirely |
| `Tipster` | A person with a published record | Omit entirely; our record is the model's |
| `Line movement` | Something changed and that is informative | **"Forecast updated"** — show what moved and why (lineup confirmed, opponent changed, minutes revised) |

---

## 11. Presenting a probability and its uncertainty — what the research says

### The problem is the reference class, not the number
Gigerenzer, Hertwig, van den Broek, Fasolo & Katsikopoulos, **"A 30% Chance of Rain Tomorrow: How Does the Public Understand Probabilistic Weather Forecasts?"**, *Risk Analysis* 25(3), 2005, 623–629 — [researchonline.lse.ac.uk/id/eprint/16975](https://researchonline.lse.ac.uk/id/eprint/16975) `[search]`

- The core argument: *"Because the forecast is expressed as a single-event probability, it does not specify the class of events it refers to. Therefore, even numerical probabilities can be interpreted by members of the public in multiple, mutually contradictory ways."*
- Empirically, in five cities, **only in New York did a majority give the standard meteorological reading** — that in 3 out of 10 similar cases there will be rain. In each European city that reading was judged **least** appropriate; the preferred readings were "it will rain 30% of the time" and "in 30% of the area".
- Earlier work (Murphy et al., 1980) found most of 79 residents of Eugene, Oregon misread a 30% forecast, and concluded the confusion was about *the event referred to*, not about probability.
- Recommendation: *"Experts need to specify the reference class, that is, the class of events to which a single-event probability refers."*

**Applied to us:** "Haaland 62% shots" is the exact failure mode this paper describes. Write **"62% chance of at least 1 shot on target, if he starts"** — the event (≥1 SOT), the subject, and the conditioning assumption (starts) all stated.

### The authoritative forecaster publishes a page just to prevent misreading
US National Weather Service, **"What is the Meaning of PoP"** — [weather.gov/ffc/pop](https://www.weather.gov/ffc/pop) `[fetched]`

The page poses the two wrong readings itself before answering: *"What does this '40 percent' mean? ...will it rain 40 percent of of the time? ...will it rain over 40 percent of the area?"* Then:

> *"The 'Probability of Precipitation' (PoP) simply describes the probability that the forecast grid/point in question will receive **at least 0.01" of rain**. So, in this example, there is a 40 percent probability for at least 0.01" of rain at the specific forecast point of interest!"*

Two lessons. First, **pin the threshold** ("at least 0.01 inch", not "rain"). Second, the way to teach a probability is to **name the plausible misreadings and refute them** — more effective than a definition alone. Our glossary entry for a forecast probability should be written exactly this way.

### Dot/outcome displays measurably improve decisions
- Kay, Kola, Hullman & Munson, **"When(ish) is My Bus? User-centered Visualizations of Uncertainty in Everyday, Mobile Predictive Systems"**, CHI 2016 — [idl.uw.edu/papers/when-ish-is-my-bus](https://idl.uw.edu/papers/when-ish-is-my-bus) `[search]`. Introduces the **quantile dotplot**: a distribution drawn as a countable number of discrete dots, designed for small screens. Reported to reduce the variance of people's probability estimates by roughly 1.15× versus a density plot, and to support more confident estimates.
- Fernandes, Walls, Munson, Hullman & Kay, **"Uncertainty Displays Using Quantile Dotplots or CDFs Improve Transit Decision-Making"**, CHI 2018 (best paper honourable mention) — [mucollective.northwestern.edu/project/uncertainty-bus](https://mucollective.northwestern.edu/project/uncertainty-bus) `[search]`. Participants were **paid according to decision quality**, not asked to read off numbers. **Quantile dotplots with 50 outcomes produced decisions that were better on average and more consistent than a no-uncertainty control; CDFs performed nearly as well; both outperformed textual uncertainty.**

This is the strongest evidence in the literature for how to draw an uncertain quantity in a consumer interface, and it is directly transferable: a player's shot count is a small integer-valued quantity, exactly the shape a quantile dotplot handles best. **Opta already ships a `Dot plot` toggle** `[fetched]`, so the idiom is not alien to this audience.

### Frequencies versus percentages — supported, but contested
- Spiegelhalter, Pearson & Short, **"Visualizing Uncertainty About the Future"**, *Science* 333, 2011 — [PDF](https://www.stat.berkeley.edu/~aldous/157/Papers/spiegelhalter_visualizing.pdf) `[search]`. Reports that *"natural frequencies appear to be superior to percentages in improving understanding of biomedical screening"*, while noting that *"the merits of using frequencies instead of percentages are contested"*.
- Spiegelhalter, **"Risk and Uncertainty Communication"**, 2017 — [PDF](https://regulation.org.uk/library/2017-Spiegelhalter-Risk_and_Uncertainty_Communication.pdf) `[search]`. Two concrete rules: **keep the denominator fixed** when comparing frequencies, and **present percentages or frequencies both with and without the outcome** to avoid framing bias.

**Applied to us:** show *both* framings and hold the denominator constant across a page: **"62% — about 6 matches in 10"**, and on the negative side **"no shot on target in about 4 matches in 10"**. Do not switch between "in 10" and "in 20" within one screen.

### Icon arrays: good, but not a silver bullet, and bad at imprecision
`[search]` A systematic review finds **icon arrays and bar graphs both improve accuracy and comprehension, with neither clearly superior**, and that arrays using three or more colours performed *worse* than other formats. A Cambridge randomised trial on communicating imprecision concludes that **the best approach for conveying imprecision within an icon array is unclear** and that research testing it is limited ([PMC9731905](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC9731905/) — I could not fetch this page; it is behind a bot check, so the finding is from search extracts).

**Applied to us:** a 10- or 20-icon array is fine for a single headline probability. Do **not** try to encode the interval inside the array — put the interval in a separate, explicitly labelled element.

### Bands and cones are read as boundaries and as magnitudes
`[search]` NOAA's literature review of the hurricane "cone of uncertainty" reports that people **confuse uncertainty about position with the size or intensity of the storm**, and that the most common error is **assuming the cone contains every possible track** ([NOAA review PDF](https://www.aoml.noaa.gov/general/lib/lib1/nhclib/Bibliographies/Cone%20of%20Uncertainty%20Literature%20Review_4_10_19%20%281%29%20%281%29.pdf)). Psychological work identifies a distinct *"size misconception"* and *"boundary misconception"*, and finds that **explaining the graphic's conventions changes what people believe it shows** ([APA summary](https://www.apa.org/pubs/highlights/spotlight/issue-155)). Joslyn & Savelli (2021) describe the **deterministic construal error** — people reading an uncertainty visual as showing a single definite quantity — and note that most studies prime participants that uncertainty is being shown, which may hide how often the error occurs ([Frontiers in Computer Science](https://doaj.org/article/cebd478f05b948179153ebeecab55cf7)). Separately, NHC analysis suggests the cone would need to be modestly wider and longer to enclose 90% of positions rather than 67% ([summary](https://www.preventionweb.net/quick/102528)).

**Applied to us, three hard rules for uncertainty bands:**
1. **State the coverage in the label**, not in a footnote: *"80% of outcomes fall in this range"*. An unlabelled band is read as "everything possible".
2. **Never let band width be confusable with magnitude.** If a wider band could be read as "more shots", change the encoding.
3. **Assume the deterministic construal error by default.** The band must be visibly the primary object, not a decoration around a number — otherwise users read the number and ignore it.

### Probabilities of related events do not combine naively
`[search]` In weather UIs, users notice that *"the percentage of rain for the day is often less than the percentage of rain indicated for a particular hour"*, and the explanation is that **hourly events are not independent, so they do not simply sum** ([Apple discussion thread](https://discussions.apple.com/thread/250534762)). Users also report confusion when **likelihood and amount are shown as if they were the same series** — Dark Sky showing 0 precipitation amount alongside 20–70% likelihood ([MacRumors thread](https://forums.macrumors.com/threads/weather-app-w-hourly-precipitation-probability.2381671)).

**Applied directly to our combination builder:** two forecasts from the same match are correlated (shared minutes, shared game state, shared opponent). Multiplying their probabilities overstates confidence. Either compute the joint distribution or label the figure as assuming independence and therefore an upper bound. And keep **probability** and **expected amount** as visually distinct series — never on the same axis.

### Calibration is not accuracy, and both need a baseline
`[search]` A Brier score is the standard grade for probabilistic forecasts, but **a perfectly calibrated coin-flip model still scores 0.25** — so a non-zero score is not evidence of a bad model. Calibration (do 60% forecasts happen 60% of the time?) is distinct from discrimination (does the model separate likely from unlikely?), and a model can be well-ranked but systematically miscalibrated. Calibration is a long-run property: one absurd-looking single forecast is not evidence of a broken model. FiveThirtyEight's page handled this correctly by reporting **both** a calibration plot **and** a skill score against a historical-average baseline, and by naming low discrimination as a flaw (*"very well-calibrated, though we rarely went out on a limb"*).

### One counterweight
`[search]` van der Bles et al., **"Communicating uncertainty about facts, numbers and science"**, *Royal Society Open Science* 6(5), 2019 — [royalsocietypublishing.org](https://royalsocietypublishing.org/rsos/article/6/5/181870/95102/Communicating-uncertainty-about-facts-numbers-and). Explicitly communicating uncertainty **can increase anxiety through ambiguity aversion**. So uncertainty must be shown as *competence*, not as hedging: a visible interval plus a published calibration record reads as rigour; a visible interval with no accuracy record reads as an excuse. The two features have to ship together.

---

## 12. Evidence and recent form — how the category does it

| Product | Form display | What is shown alongside |
|---|---|---|
| **StatsHub** `[fetched]` | Card slot 8 is **"Recent games"**; the player page offers a game log with a **Table \| Charts** toggle; the Screener shows **L5 / L10 / L15 as three parallel columns** | Card slots: kick-off and fixture, lineup and activity, position, threshold, record and hit rate, per-90 and average, **season average and opponent**. Filters add venue, minutes, started-vs-substitute, competition scope |
| **FotMob** `[search]` | Per-match rows with **minutes and a numeric rating** inline (*"45' 4.9"*) | Result, competition, rating, minutes |
| **Sofascore** `[search]` | Match rating per game, season rating as the average; heatmaps and passing/dribbling/defending maps per match | Rating categories, in-match Attack Momentum |
| **FBref** `[search]` | Season and 365-day **tables**, no sparkline; per-90 beside percentile | Position, minutes, competition, percentile vs positional peers |
| **Opta** `[fetched]` | No player form. Team-level: stacked bar or dot plot of outcome probabilities, 20-column position matrix | Predicted points, zone legend |

**What everyone attaches to a form strip, and so must we:** minutes, opponent, home/away, competition, started-or-substitute, and position in that match. StatsHub makes all six available but as *filters*, which means the default view mixes them silently.

**The gap.** Nobody shows the form strip **against the forecast**. The obvious design — per-match bars with the forecast interval drawn behind them, so the user sees how often the actual landed inside the band — is both the most natural evidence display and a per-player calibration check. It does not exist anywhere in this category.

**The second gap.** Every form strip weights the last match the same as the tenth. StatsHub's answer is to sell window choice as a feature (*"Short window catches that… Long window smooths the noise"* — and on the top tier, *"Short, medium & long windows"*). An engine should not make the user choose: weight by recency and show the effective sample size.

---

## 13. Navigation and information architecture — how you get from a fixture to a player

**StatsHub's actual paths** `[fetched]`:
1. Homepage → competition group → fixture → `Players` tab → player row → player page. Four taps.
2. Player page → **"Next match"** card → `View match` → fixture page. The loop closes.
3. Player Trends card → *"Tap the fixture on a real card for the match page"* (card slot 1) → fixture page. **A forecast card links to the fixture, not only to the player.** Good.
4. Tool-to-tool: the `Trends | Screener | Hunter` segmented control inside every tool.
5. Entity pages exist for league, team, player, fixture and referee, each with its own sitemap — every entity is addressable and indexed.

**Filter design patterns in the category, best first:**
1. **Live plain-English restatement of the filter state** (StatsHub Prop Hunter). The best pattern in the category.
2. **Natural-language example searches as documentation** (FootyMetrics: *"midfielders averaging 3+ tackles playing tomorrow"*) `[search]`.
3. **Named archetype presets with their parameters shown as chips** (StatsHub's eight). The name describes a *player type*; the chips keep it honest.
4. **Help text on every non-obvious control** (StatsHub: *"Only games the player started, not ones they came on in."*). Consistently done, and the reason the tool is usable at all.
5. **Accordion grouping** — Date & leagues / Filter by / Advanced (optional), with a `Defaults` reset.
6. **Three windows side by side** rather than one chosen window (StatsHub Screener L5/L10/L15) — a cheap disagreement cue.
7. **A sort-marker in the column header** (`▸ L10`) so the ranking basis is always visible.

**Saved state in the category:**
- StatsHub: a `Saved picks` tab and a `Saved` filter panel, plus `Presets` split into *"Popular searches"* and *"Build your own"*. So: system presets, user-saved searches, and saved rows are three separate things. That taxonomy is right.
- Flashscore: `Favorites`, `Pinned Leagues`, `My Teams` `[fetched]`.
- playerstats.football / FootyMetrics: no saved-search feature found; the free tier meters searches instead `[search]`.

**Weaknesses to exploit:**
- StatsHub has **no comparison page** and **no combination builder** in the free product. Comparing two players means two tabs.
- There is **no forecast content on the fixtures feed at all** — the feed is scores, the forecasts are in tools. A user with no plan has nowhere to land.
- `Prop Hunter`, `Prop Screener`, `Player Trends`, `Team Trends`, `Team Screener` are five tools whose jobs overlap heavily (all three player tools filter the same markets by the same hit rate over the same windows). The `Trends | Screener | Hunter` switcher exists because the distinction is not self-evident.

---

## 14. What they do badly — the openings

### StatsHub
1. **Hit rate is a point estimate from a tiny sample, with no uncertainty anywhere.** *"5 of the last 10 games (50%)"* has a 95% interval of roughly 19–81%. The "Hot Form" preset uses *4 of the last 5*. The only mitigation is a hard `Minimum games played` cutoff. **Opening:** shrinkage plus a visible interval on every row.
2. **Streak mining, stated as a feature.** Player Trends *"shows the strongest window (3-40 games) for each prop"* across 13 markets. Selecting the best of ~38 windows × 13 markets × thousands of players guarantees extreme hit rates with little predictive content, and nothing on the page warns the user. **Opening:** one honest window with recency weighting, and a stated effective sample size.
3. **Opponent strength is a filter, not an adjustment.** *"Difficulty: All Matches / Easier Matchups / Harder Matchups"* and *"Min opponent hit rate"* discard data instead of reweighting it, and the default view silently mixes strong and weak opponents. **Opening:** a signed opponent adjustment shown on the card.
4. **The track record is an affiliate's betting P&L, with admitted selection.** *"+213u"*, *"12.1% ROI"*, from one person's spreadsheet over four months — and *"We've crossed out and hidden the other tipsters in it who are showing a negative ROI."* It cannot answer whether a 60% forecast happens 60% of the time. **Opening:** the whole of §7.
5. **"No black boxes" alongside three unexplained model personalities.** The free side promises *"No black boxes — you see the evidence before you bet"*; the paid side ships *Franko / Hugo / Theo* with no stated method, inputs, or error bars, differentiated by temperament (*"only speaks when he's confident"*). **Opening:** publish the method in four sentences the way Opta does.
6. **Two vocabularies either side of the paywall.** Free speaks *hit rate / L10 / line*; paid speaks *fair odds / +EV / consensus picks*. A converting user has to learn a second language at the moment they pay.
7. **Nothing is computed until you press the button.** Prop Hunter lands on *"Set up your search"*; Team Trends lands on *"No Games Available"*. **Opening:** land on today's forecasts.
8. **Unlabelled and overprecise numbers.** The fixture header shows the referee as *"Michal Očenáš 4.50"* with no unit. Hit rates are printed to the percent from five observations.
9. **Visible data defects.** Haaland's Season Performance rendered entirely as `—` with `Minutes played : —`, beside prose describing his *"24/25 season"* and a November 2026 fixture.
10. **No comparison page, no combination view, no per-player forecast-vs-actual history.** Three screens we have and they do not.

### Opta / theanalyst `[fetched]`
1. **Overprecision:** probabilities to two decimal places, including `0.00`, from a 10,000-run simulation. `0.00` should be "<0.1%" or "about 1 in 10,000" — which their prose does well and their tables do not.
2. **Methodology is in article prose, not beside the table.** The predictions page itself carries no "how this works" link I could find.
3. **The model consumes betting market odds**, so its probabilities are partly a repackaging of market prices. Disclosed, but only inside article text.
4. **No calibration page.** Self-assessment is narrative — *"a good showing"*, *"well over half the division placed within two positions"* `[search]`.
5. **Team-level only.** No player-statistic forecasts anywhere in the public product.

### FotMob / Sofascore / Flashscore
1. **Entirely retrospective.** Not one forward-looking number for a player statistic.
2. **Composite ratings are opaque,** and in Sofascore's case its own articles disagree on the rating's composition `[search]`.
3. **Flashscore's chrome is gambling advertising,** with harm warnings in four jurisdictions above the fold `[fetched]`. The calm analytical position is vacant.
4. **FotMob's terms forbid automated access** `[fetched]`, so there is no integration or export story.

### FBref
1. **Percentiles are relative and retrospective** — rank among peers, not an expectation for Saturday.
2. **Only two windows** (365 days, or a season). No recency weighting, no next-opponent view.
3. **Table-first and desktop-first.** No fixtures feed, no scanning surface, no mobile-first card.
4. **Licensed data dependency** — its own explainer conditions eligibility on *"a competition with Opta data"* `[search]`.

### Understat
**Down at the time of this audit** `[fetched]`. Also the live demonstration that free analytics references disappear.

---

## 15. Recommendations

Each with the reason, and the screen it lands on.

### Vocabulary and labelling
1. **Write thresholds as "at least N", never "Over N−0.5".** *Reason:* it is what the number means, it is plainer than the convention, and it discharges the vocabulary constraint for free. *Screens:* everywhere.
2. **Every probability carries its event, its subject and its conditioning assumption in the label.** *"62% chance of at least 1 shot on target, if he starts."* *Reason:* Gigerenzer et al. (2005) — an unqualified single-event probability is read in mutually contradictory ways; the NWS publishes a whole page because of it. *Screens:* forecast cards, match page, Finder rows.
3. **Pair every percentage with a frequency, with a fixed denominator per screen.** *"62% — about 6 matches in 10."* *Reason:* natural frequencies have the better (if contested) evidence base; Spiegelhalter's rule is to hold the denominator fixed; and Opta's house style proves the audience reads it happily. *Screens:* forecast cards, Insights.
4. **Give both the positive and negative framing on the detail view.** *"About 6 matches in 10 he records one; about 4 in 10 he does not."* *Reason:* Spiegelhalter (2017) on framing bias. *Screens:* match page, player page.
5. **Ban false precision.** Probabilities to whole percents; anything under 1% as *"fewer than 1 in 100"*. *Reason:* Opta's `0.00` columns claim resolution no simulation has. *Screens:* everywhere.

### Showing uncertainty
6. **Make a dot/outcome display the primary encoding for a forecast distribution, with the percentage as a label on it.** ~20 dots for a probability, a quantile dotplot for a count. *Reason:* Fernandes et al. (CHI 2018) — quantile dotplots and CDFs produced measurably better and more consistent *decisions* than no-uncertainty controls and beat textual uncertainty; Kay et al. (CHI 2016) designed the idiom for small screens; Opta already ships a `Dot plot` toggle, so it is not alien here. *Screens:* match page, player page, comparison.
7. **Label every band with its coverage, inside the band's own label.** *"80% of outcomes fall in this range."* *Reason:* the cone-of-uncertainty literature shows unlabelled bands are read as containing everything possible, and that explaining the convention changes what people believe it shows. *Screens:* everywhere a band appears.
8. **Assume the deterministic construal error.** The distribution must be the visually dominant object, with the point estimate subordinate to it — not a number with decoration. *Reason:* Joslyn & Savelli (2021); users default to reading one definite quantity. *Screens:* forecast cards.
9. **Keep probability and expected amount as visually distinct series, never on one axis.** *Reason:* the Dark Sky complaint — users confronted with 0 expected amount and 70% likelihood concluded the app was broken. *Screens:* match page, player page.
10. **Show the effective sample size next to any rate, and show shrinkage happening.** *"Based on 7 matches — pulled toward the positional average."* *Reason:* the whole category shows 100%-from-3-games with no caveat; this is our clearest structural advantage and it has to be visible to count. *Screens:* player page, Finder rows.

### Trust
11. **Build the track-record page as FiveThirtyEight's "Checking Our Work", because the original is gone.** Calibration bins against a 45-degree line; counts per bin (*"of the 412 forecasts we published at 60–70%, 64% happened"*); a skill score against a **named** baseline; split by market and by lead time; and the bad news included. *Reason:* no football product publishes calibration; the one real precedent is offline; StatsHub's P&L cannot answer the question; and a competitor is already advertising Brier scores as a feature `[unverified]`, so the position will not stay empty.
12. **Ship uncertainty and the accuracy record together, never uncertainty alone.** *Reason:* van der Bles et al. (2019) — communicated uncertainty can raise anxiety via ambiguity aversion. An interval with a published record reads as rigour; an interval without one reads as an excuse.
13. **Publish the method in four plain sentences, linked from beside every forecast, not buried in a blog.** Opta's paragraph is the length and register to match. *Reason:* StatsHub promises "no black boxes" and ships three named personalities; Opta's methodology is good but lives in article prose. Being the only product where the method sits next to the number is cheap and distinctive.
14. **Explain opponent adjustment by example, in one sentence, in Opta's shape.** Their *"beating Real Madrid will give you more points than beating Real Valladolid"* is the model. Name both anchors of any scale we invent, as they do with 0–100. *Screens:* glossary, match page tooltip.
15. **Show the decomposition of each forecast: base rate → opponent → expected minutes → venue → referee.** *Reason:* nobody can do this, it is the most direct demonstration that an engine exists, and it converts "trust us" into "check our work". *Screens:* match page detail, player page.
16. **Draw the form strip against the forecast band.** Per-match bars with the interval behind them, so the user sees how often the actual landed inside. *Reason:* it is simultaneously the most natural evidence display and a per-player calibration check, and it exists nowhere in the category. *Screens:* player page, match page.
17. **Build a glossary with difficulty badges, in the shape of the NWS PoP page: state the plausible misreadings, then refute them.** *Reason:* StatsHub's Opta-attributed glossary with Basic/Intermediate/Advanced badges is one of its strongest trust devices; the NWS page shows that naming the wrong readings teaches better than a definition. *Screens:* glossary, inline tooltips.

### Navigation and the feed
18. **Put forecast cards on the fixtures feed itself.** *Reason:* StatsHub's feed is scores-only and its forecasts live in tools behind a "Find Players" button, so a user with no plan has nowhere to land. Our one-line advantage is that the feed *is* the product.
19. **Land every screener on results, with sensible defaults, and let filters narrow from there.** *Reason:* Prop Hunter opens on *"Set up your search"*, Team Trends on *"No Games Available"*. Opening on today's most informative forecasts is a visible difference on first run.
20. **Restate the Finder's filter state as a live sentence above the results, in our vocabulary.** *"At least 1 shot on target, in 5 of the last 10 matches, for midfielders who started."* *Reason:* it is the single best interaction in the category (StatsHub's *"Shots over 0.5 in 5 of the last 10 games (50%)"*) and it is the only mechanism that lets a user verify what they built.
21. **Name presets after player archetypes, show their parameters as chips, and keep system presets, saved searches and saved rows as three separate things.** *Reason:* StatsHub's eight archetype presets ("Midfield Enforcers", "Foul Magnets") match how users think, and its `Presets / Saved / Saved picks` taxonomy is correct. *Screens:* Finder.
22. **Make lineup status, expected minutes, injury/suspension and position-in-that-match first-class elements of every forecast row — not filters the user must remember.** *Reason:* a forecast for a player who does not start is worthless, and StatsHub's defaults silently mix starters with substitutes unless the user finds `Started the match`. *Screens:* all forecast rows.
23. **Teach the card with a tappable annotated example.** *Reason:* StatsHub's nine-part *"How to read a card"* is the best onboarding in the category and ours has more elements to explain, not fewer. *Screens:* first-run, and a persistent link from the card.
24. **Carry the per-90 value next to its positional percentile next to our forecast — all three.** *Reason:* FBref's per-90-plus-percentile row is the densest useful row in the category; adding the forecast makes a row no competitor can print. *Screens:* player page.
25. **Make the combination builder correlation-aware, and say so on screen.** Either compute the joint distribution or label the figure as assuming independence and therefore an upper bound on confidence. *Reason:* same-match statistics share minutes, game state and opponent; hourly rain probabilities fail to aggregate for exactly this reason. Getting this wrong is the fastest way to destroy the credibility the rest of the product earns.

### Metrics to add because they are rare and cheap
26. **Fouls won, foul involvements, player shots created, saves as a first-class market, corners, offsides.** *Reason:* each is a distinct forecastable series that most analytics products omit entirely; StatsHub has them and the mass-market apps do not.
27. **A referee page whose output feeds the card forecast as a numeric term, with a strictness band in words.** *Reason:* StatsHub has a referee page and a card market and never joins them. Joining them is an engine-only move, and the Lenient/Average/Strict banding is a proven way to present a small-sample quantity.
28. **Opponent-conceded rates as a surfaced page, not a hidden tab.** *Reason:* it is the input to our opponent adjustment, so showing it is showing our work; StatsHub buries it in an `Opponent Stats` tab on the fixture page.

### Monetisation
29. **Split on capability, not on metered searches, and keep one vocabulary either side of the line.** *Reason:* metering (playerstats.football and FootyMetrics at 3 searches/day) prices the act of looking, which is fatal in a daily-habit product. StatsHub's capability split is the right shape — counting free, engine paid — but it fails by switching vocabulary at the boundary. *Screens:* pricing, upgrade prompts.
30. **Do not sell recency as the cheap tier.** StatsHub's £29.99 tier gates the model to *"games kicking off in the next 12 hours"* and charges £99.99 for the full slate. *Reason:* a forecast product whose cheap tier arrives too late to be useful teaches users the forecast does not matter. Gate on depth — decomposition, comparison, combinations, saved searches, history — not on how soon you may see it.
31. **Make the free tier genuinely complete for one job.** *Reason:* StatsHub's *"The free plan is an account, not a trial"* is why its free tier builds habit rather than resentment, and it is the right principle to copy.

---

## Appendix — URLs cited

**StatsHub** `[fetched 2026-11-06]`: [home](https://statshub.com/) · [Prop Hunter](https://statshub.com/prophunter) · [Prop Screener](https://statshub.com/prop-screener) · [Player Trends](https://statshub.com/player-trends) · [Team Trends](https://statshub.com/team-trends) · [Referees](https://statshub.com/referees) · [Player page example](https://www.statshub.com/player/erling-haaland/16391) · [Fixture page example](https://www.statshub.com/fixture/fc-twente-vs-pafos-fc-mw43n7/498343) · [Pricing](https://statshub.com/pricing) · [Features](https://www.statshub.com/features) · [Free tools](https://statshub.com/free-tools) · [About](https://statshub.com/about) · [Stats Explained](https://statshub.com/stats-explained) · [sitemap](https://statshub.com/sitemap.xml)

**Opta / Stats Perform** `[fetched]`: [PL predictions](https://theanalyst.com/competition/premier-league/predictions) · [2025-26 supercomputer projections](https://theanalyst.com/articles/premier-league-predictions-2025-26) · [Power Rankings article](https://theanalyst.com/articles/opta-power-rankings) · [2023-24 retrospective](https://theanalyst.com/articles/opta-supercomputer-premier-league-2023-24-predictions/) `[search]`

**Understat** `[fetched — down]`: [understat.com/league/EPL](https://understat.com/league/EPL)

**Flashscore** `[fetched]`: [flashscore.com](https://www.flashscore.com/)

**FBref** `[search]`: [Scouting reports explained](https://fbref.com/en/about/scouting-reports-explained)

**Sofascore** `[search]`: [Attack Momentum](https://www.sofascore.com/news/how-sofascores-attack-momentum-changed-sport-analysis) · [Rating breakdown](https://www.sofascore.com/news/sofascore-rating-breakdown-what-goes-into-calculations/) · [New maps](https://www.sofascore.com/news/introducing-sofascores-new-maps-a-smarter-way-to-read-the-game)

**Screeners** `[search]`: [playerstats.football](https://playerstats.football/player-props-finder) · [playerstats.football changelog](https://playerstats.football/changelog) · [FootyMetrics](https://www.footymetrics.com/player-props-finder) · [PickFinder](https://www.pickfinder.app/leagues/soccer)

**FiveThirtyEight** `[verified dead]`: `projects.fivethirtyeight.com/soccer-predictions/`, `projects.fivethirtyeight.com/checking-our-work/`, `fivethirtyeight.com/features/how-our-club-soccer-predictions-work/` — all redirect to abcnews.go.com

**Probability communication**: [NWS PoP](https://www.weather.gov/ffc/pop) `[fetched]` · [Gigerenzer et al. 2005](https://researchonline.lse.ac.uk/id/eprint/16975) · [Kay et al. CHI 2016](https://idl.uw.edu/papers/when-ish-is-my-bus) · [Fernandes et al. CHI 2018](https://mucollective.northwestern.edu/project/uncertainty-bus) · [Spiegelhalter et al. 2011](https://www.stat.berkeley.edu/~aldous/157/Papers/spiegelhalter_visualizing.pdf) · [Spiegelhalter 2017](https://regulation.org.uk/library/2017-Spiegelhalter-Risk_and_Uncertainty_Communication.pdf) · [van der Bles et al. 2019](https://royalsocietypublishing.org/rsos/article/6/5/181870/95102/Communicating-uncertainty-about-facts-numbers-and) · [NOAA cone literature review](https://www.aoml.noaa.gov/general/lib/lib1/nhclib/Bibliographies/Cone%20of%20Uncertainty%20Literature%20Review_4_10_19%20%281%29%20%281%29.pdf) · [Joslyn & Savelli 2021](https://doaj.org/article/cebd478f05b948179153ebeecab55cf7) · [APA graphical conventions summary](https://www.apa.org/pubs/highlights/spotlight/issue-155) · [Icon array imprecision RCT](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC9731905/) `[search only — bot-checked]`
