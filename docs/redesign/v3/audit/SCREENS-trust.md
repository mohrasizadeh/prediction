# Trust and conversion screens — audit

Screens P-16, P-17, P-19, P-20, P-21, P-22, P-23, P-24, P-27 (IDs from `docs/57_screen_inventory.md`).
Written 2026-11-06 by reading the components, the queries behind them, and renders at 390 px and
1440 px in both schemes.

---

## 0. First: the supplied render set is invalid, and I replaced it

`docs/redesign/v3/before/*.png` cannot be used. Every file in it — P-01, P-03, P-04, P-05, P-06,
P-07 — renders the same screen: **"Set up two-factor sign-in"**. The cause is in the harness, not
the app:

`scripts/shots3.js` creates **one** browser context per (viewport, scheme) and signs that context
in as `owner@example.com` before looping over *all* screens, public ones included. That account
hits `scope === "enroll_2fa"`, and `Gates()` in `frontend/src/App.js` redirects **every** route to
`/enroll-2fa`. So the whole public half of the v3 "before" set is a photograph of the 2FA page.

Fix for the harness (not applied — out of scope for this audit): give public jobs their own
signed-out context, and only sign in for the `auth: true` jobs.

I captured my nine screens myself from the running demo server at `127.0.0.1:8011`, signed out, at
390×844 and 1440×900, dark and light. **No horizontal scroll at 390 px on any of the nine, in
either scheme.** Constraint 4 passes today; nothing below is a 390 px overflow.

Two of my screens are empty in demo data and I had to render the populated state by intercepting
the API response client-side (no writes):

| Screen | What demo data actually renders | Populated via |
|---|---|---|
| P-17 Track record | `{"ready":false,"scored":0,"needed":300}` → "Collecting results. 0 so far." | mocked `/api/track-record` |
| P-21 Plans | `billing_enabled:false` → "Paid plans are not open yet" | mocked `/api/plans` |

**This belongs in `docs/57` §7 beside P-03 Live and O-06 popups.** The page the brief calls the most
important in the product has never been reviewed with data in it, and the plan cards have never
been reviewed at all. Every reviewer to date has looked at an empty card and a tag icon.

---

## Top 10 changes, ranked

Ranked by (credibility gained) × (cheapness). Items 1–5 are all P-17.

| # | Screen | Change | Reason |
|---|---|---|---|
| 1 | P-17 | Stop choosing the headline band by `n`. Lead with the whole record, then the band table. | The current rule selects the largest band, which in this product is always 0.9–1.0 (docs/50: median stated 0.873). The page's biggest sentence is therefore structurally the *least* informative claim available — the band where the base rate alone would look good (docs/51 §1.3). One flattering band chosen by a rule the reader cannot see is cherry-picking even when the rule is well-meant. |
| 2 | P-17 | Add **"Where we were wrong"**: the most recent settled forecasts that missed, named, dated, with the final count. | Nothing else on the page is checkable. A sceptic does not believe an aggregate; they believe a named forecast they can look up. `forecast_outcomes` already holds `p`, `reached` and `scored_at`, and `Following` already renders a Hit/Miss tag — the component and the data both exist. This is the single highest-return item in the audit and the one most aligned with "honesty is the product". |
| 3 | P-17 | Put `stated` on the tier tiles: "We said 92. It happened 90. From 1,180 forecasts." | `queries.track_record` returns `tiers[t]["stated"]` and `TrackRecord.jsx` throws it away. "90 of 100 came true" with no claim beside it is unfalsifiable — a big number with nothing to check it against. The fix is reading a field already in the payload. |
| 4 | P-17 | Fix the `.tr` class collision with `TeamRadar` (`justify-items: center`). | The page has **two left edges 280 px apart** on desktop and a centred h1 above a left-aligned headline on phone. Cause confirmed: `teams.css:33` sets `.tr { justify-items: center }` for the team radar; `TrackRecord.jsx:100` uses the same class. `v2.css` §17a patched `text-align: left`, which does not undo `justify-items`, so the symptom survived the last pass. |
| 5 | P-17 | Rebuild the empty state. Today it is a centred title, six filter chips, and "0 so far." | This is the state in the build **right now**, and the first state most visitors will ever see. It currently tells a new reader the product has never been checked, then offers nothing — no method, no backtest, no link to Learn. `calibration.py` documents a walk-forward audit over 351,098 forecasts on three leagues; that evidence exists and the page hides it. |
| 6 | Global | Get Track record out of the footer. One record line on Today and on the forecast **card**, not only inside the sheet. | `docs/24` §30.8 promises "the track record is one tap from every forecast" and `docs/26` #18 specified an "Our record" block on Today. Neither shipped. Today the only paths in are the site footer, one Explore tile and a line inside `ForecastSheet` — i.e. two taps minimum, from a surface most readers never open. The product's proof is three clicks from the product. |
| 7 | P-21 | Row 1 becomes "The full settled record, every forecast, hits and misses — free, always". Replace the volume rows with plain-English ones. State "then CA$9.99 a month" beside the trial. | The plan table currently sells internal nouns ("Insights a day", "Games in the squad grid") and never mentions the one thing that justifies paying anyone for a forecast. The 5-day trial converts automatically — that is in Terms and nowhere on the card where the decision is made. |
| 8 | P-22 | Teach before you configure. Redirect signed-out visitors. Drop the duplicate e-mail ask. | Step 1 of 3 is "Which leagues do you watch?" — a new member is asked to tune a feed for a product that has not been named or explained. The page also renders fully to a signed-out visitor, whose "Next" will fail on `PATCH /account/profile`. And the footer newsletter form asks for an e-mail on the same screen as step 3's "Weekly e-mail" switch. |
| 9 | P-19/P-20 | Teach with the real `ForecastCard`, annotated. Add two missing articles. Drop the four-way filter over four items. | An article called "How to read a forecast card" does not contain a forecast card — it contains a stylised 240 px mock (`PicCard`). And the two things readers most misread — what a percentage is *not*, and what "(66 to 81)" means — have no article, while "(66 to 81)" ships on cards via `lib/copy.range()`. |
| 10 | P-24 / P-27 | Render the legal effective date the API already sends. Give the 404 a way out. | `/api/public/pages/{slug}` returns `updated_at`; `Markdown.jsx` drops it, so Terms and Privacy carry no date — the one piece of metadata a legal page must have. The 404 is "404" plus one sentence, no links; the most prominent interactive thing on it is the newsletter form. |

---

## P-17 — Track record (`/track-record`)

**Purpose.** Show, in a way a non-statistician can check, whether this product's numbers mean what
they say — including where they do not.

### Inventory

| Element | Verdict | Reason |
|---|---|---|
| `h1` "Track record" | **keep** | Added in the last pass for good reason. But see hierarchy — it renders centred. |
| "Updated as matches finish." | **change** | Vague. It should carry the real freshness: "Last scored 2 hours ago · next update after tonight's matches." The shell already computes `data_updated_at`. |
| League chips, Market chips (`tr-filters`) | **move** | Below the headline and the band table. On a 390 px phone they occupy the first ~270 px — a title, a subtitle and up to four rows of chips before the sentence the page exists to say. With ten real leagues this is worse; the list is not sliced. |
| `tr-headline` | **change** | The claim is right in form and wrong in selection. See Faults 1. |
| `Reliability` sentence | **keep, reword** | Genuinely good and rare: it names `n`, the margin, and whether the gap is real. It is the best thing on the page. Two wording faults, below. |
| "Across all bands: 4,120 scored forecasts since August 2026." | **move up** | This is the sentence that establishes the sample. It is currently the third paragraph in `k-faint` grey. It should sit with the headline. |
| `tr-chart` (the reliability scatter) | **change** | Right instrument, wrong lead, and it shows point estimates with no uncertainty. See Faults 3–5. |
| Chart caption "Dots on the dashed line = honest numbers" | **keep** | Excellent plain-language caption. Do not touch it. |
| Tier tiles (`tr-tier`) | **change** | Show `actual` only; `stated` is in the payload and discarded. Colour is spent on the wrong thing. |
| "3,580 of the 4,120 scored forecasts had a tier…" | **keep, promote** | Real honesty about what the two panels do and do not share. Currently 12 px grey at the bottom. |
| "How we score this" link | **keep, move up** | A methodology link belongs beside the claim, not after it. |
| **Missing: any individual forecast** | **add** | The page is 100 % aggregate. See change #2. |
| **Missing: any skill claim** | **add (honestly)** | See Q1. |
| Newsletter block + 13-link footer | **change** | On a 390 px phone the capture block and footer are ~40 % of total page height on the product's proof page. `v2.css` §16a already de-emphasised it; it should not be on this page at all. |

### Hierarchy

Current DOM order: title → subtitle → **filters** → headline → margin sentence → sample size →
chart → tier tiles → caveat → method link.

Proposed: **claim** (whole record, with sample and date range) → **the band table** (said /
happened / n / margin, one row per band) → **where we were wrong** (named, dated) → chart →
tier tiles → filters → method link. Filters are a refinement; they cannot come before the thing
they refine.

### Faults visible in the render

1. **The headline is chosen by `n`, and in this product that always means the top band.** The
   render says "When we say 93%, it happens 92% of the time." That is a true sentence about the
   0.9–1.0 band, 1,791 of 4,120 forecasts. It is also the band in which being right proves the
   least — docs/51 §1.3 states this outright. The code comment at `TrackRecord.jsx:55` argues for
   "the band with the most evidence behind it"; the effect is a selection rule the reader cannot
   see that lands on the most flattering, least informative band. Lead with the whole record.
2. **The miss is reported in a euphemism.** "The gap is wider than that: these happen less often
   than we said, **which is the gap to watch**." That is the overstating case — the one the reader
   needs stated plainly — and it is softened, while the understating case gets an explicit
   positive gloss ("so we are promising less than we deliver"). Asymmetric framing of a miss and a
   beat is exactly the kind of small dishonesty that costs more than it buys. Say: "These happened
   less often than we said. We are overstating this band by 1 point."
   Also, a copy bug: "±**1 points**" — singular at 1.
3. **The chart has no uncertainty on it.** Five point estimates, size-coded by `n`, nothing else.
   In the populated render the 0.5–0.6 dot (n=41, 44 % against a stated 55 %) is drawn with the
   same confidence as the n=1,791 dot, and the connecting polyline makes it a dramatic dive. At
   n=41 that 11-point gap is inside the noise — the page's own `Reliability` component would say
   so, but it only ever runs on the headline band. **The chart currently overstates a problem,
   which is a dishonesty in the generous direction but a dishonesty.** Add a vertical margin bar
   per dot (`var(--text3)`), or drop the connecting polyline entirely — connecting five
   independent estimates implies a trend that is not being claimed.
4. **Most of the chart is empty, by construction.** Axes run 40–100 %; bins only exist from 0.5
   and the stated means cluster at 0.55/0.65/0.75/0.85/0.93, so the left third of the plot is
   permanently blank and the right three dots nearly touch at 390 px. The scatter devotes most of
   its ink to a region this product will never populate. Either clip the axes to 50–100, or —
   better — change the picture (Q1).
5. **The lowest dot is clipped by the axis.** `Y()` clamps at `LO = 0.4`, so a band whose actual
   lands at or below 44 % is drawn sitting on the baseline with its lower half outside the grid.
6. **Two left edges.** On desktop the hero text starts at x≈545 while the chart card starts at
   x≈265. `teams.css:33` `.tr { justify-items: center }` is shared with `TeamRadar` and shrink-wraps
   every direct child of `section.tr`, so each block centres at its own content width. On phone
   the same rule centres the `h1` and subtitle while the headline below is left-aligned.
   `teams.css` also applies `.tr svg { max-width: 380px }` to the calibration chart, capping it at
   380 px on a 1440 px screen.
7. **Tier tile colour rewards the number, not the accuracy.** "90 of 100" renders in
   `var(--tier-strong)` (lime), "64 of 100" in `var(--tier-watch)` (violet). A reader scanning the
   column reads lime-big-number as good and violet-smaller-number as bad. On the populated data the
   truth is the reverse: Strong said 92 and delivered 90 (overstating), Watch said 68 and delivered
   64 (overstating by about the same, on a sixth of the sample). Colour here is encoding tier
   identity, and at a glance it reads as a grade. `v2.css` §15 already argues this exact point for
   the headline ("colour means something specific everywhere else in this product … spending it
   here would make the page's most important sentence say something it does not mean"). The same
   argument applies one block lower and was not carried through.
8. **The empty state is the shipped state.** With demo data: centred title, six chips that filter
   nothing, "We show the record once 300 forecasts have been scored… 0 so far", and a progress bar
   at 0 % that is effectively invisible in dark (`--surface3` on `--surface1`). No method, no
   backtest, no onward link.

### Proposals, ranked

1. **Lead with the whole record, then the bands.** Headline: "Across 4,120 settled forecasts since
   August 2026, we said 86% on average. 85% happened." Then one row per band. No selected band.
2. **Add "Where we were wrong."** Six to ten real settled forecasts, newest first, each with the
   player or club, the line, the date, what we said, and the final count. Include a toggle for
   "biggest misses". Reuse the `y-tag--miss` tag. Ship it before any other change on this page.
3. **Replace the scatter as the lead picture with a band table** (see Q1). Keep the scatter below
   it, with margin bars and no connecting line, for readers who want the curve.
4. **Put the claim on every tier tile**: "Strong — we said 92, it happened 90, from 1,180
   forecasts." Drop the tier colour from the number; keep it on the badge where it means tier.
5. **Fix `.tr`.** Do not rename either class (constraint 3). Add `justify-items: stretch` to the
   `you.css` `.tr` rule, or add a second class `tr-page` to the section and scope the layout to it.
6. **Rebuild the empty state** as: what we will measure, how (link to `/learn/how-we-score`), the
   backtest we have (`calibration.py`: walk-forward on three leagues, 351,098 forecasts — labelled
   plainly as a backtest, not as live results), and the live counter. Never show a bare 0.
7. **Move the filters below the fold** and give the league chip list a sensible cap.
8. **Freshness in the subtitle**, from `data_updated_at`.
9. **Drop the newsletter block from this page.** It is the one page where asking for something
   undercuts the message.

---

## P-21 — Plans (`/pricing`)

**Purpose.** Tell a reader what a subscription costs and what it changes, with no pressure.

### Inventory

| Element | Verdict | Reason |
|---|---|---|
| `h1` "Plans", lead "Start free…" | **keep** | Plain and correct. |
| Monthly/Yearly `Segmented` | **keep** | Honest: yearly shows the per-month figure *and* the annual total. |
| Price block | **keep** | "CA$0 forever" is a good line. |
| Trial line "5-day free trial" | **change** | The trial converts automatically (Terms: "A free trial … turns into a paid plan at the end of the trial unless you cancel"). The card does not say so. **The one near-dark-pattern on the page.** Make it: "Free for 5 days, then CA$9.99 a month. Cancel any time before it ends." |
| Row 1 "Today, Live and match pages ✓" | **delete** | Identical on both plans. A row that cannot differ is noise. |
| Rows 2–8 (the seven numeric caps) | **change** | "Finder searches a day 10", "Insights a day 20", "Games in the squad grid 5", "Saved forecasts 20", "Player notes 20", "Follows 10". A visitor who has not used the product cannot price any of these. docs/51 §1.2 measured that 7 of 10 paid entitlements are "the same thing, more of it". |
| Rows 9–11 (alerts, matchup tab, export) | **keep** | The only three that describe a capability. |
| Green values (`--up`) on every non-dash cell | **change** | `you.css:102` colours the last cell `var(--up)` regardless of plan, so Free's "10" and "20" glow the same green as Pro's "Unlimited". Colour carries zero information and makes Free look as capable as Pro at a glance. |
| **Missing: the settled record** | **add** | See below. |
| Footnote (cancel, currency, Stripe) | **keep** | Clear, honest, correctly placed. |
| `LockSheet` / `ProLock` (O-04) | **keep** | Reviewed: no countdown, no scarcity, "Not now" is a real, equal-weight option, trial terms stated. This component is clean. |

### Hierarchy

On a 390 px phone the Free and Pro cards are ~1,100 px apart, both listing the same eleven labels.
Comparing one row across plans means scrolling a screen and a half while holding a number in your
head. Either collapse to a single comparison table on phone, or make the rows a two-column
comparison inside one card. Desktop (≥820 px, two columns) is fine.

### Proposals, ranked

1. **First row, both plans, ticked: "The full settled record — every forecast, hits and misses."**
   This is the product's moat and it is already free. docs/51 §2.2: "Hiding the record behind a
   plan is the single worst thing a forecast product can do, and the current model does not do it —
   keep it that way and **make it louder**." It is currently silent.
2. **Name the trial's conversion on the card.**
3. **Rewrite the rows in reader language**: "Search any league at once" rather than "Leagues in one
   Finder search 1 / Unlimited"; "Alerts when a club or player you follow is in a forecast" rather
   than "Alerts for teams and players ✓".
4. **Stop colouring Free's caps green.** Reserve `--up` for the capability ticks, or use
   `--text` for values and `--up` only for ✓.
5. **One comparison table on phone.**
6. **Remove the identical first row.**

### On the boundary itself — see Q2.

---

## P-16 — You / Following (`/following`)

**Purpose.** One feed for everything a reader follows, and the record of what they saved.

### Inventory — signed out

| Element | Verdict | Reason |
|---|---|---|
| `h1` "You" | **change** | A signed-out visitor has no "you". The nav label and the page title should not be the same word here. |
| `v2-say` paragraph | **keep, shorten** | Four lines of prose describing a feature instead of showing it. |
| League grid (`ex-grid`) | **keep** | The previous pass added it to stop the page being a sign-up wall. Right instinct. |
| "Create a free account" + "Sign in" | **keep** | Correct. |
| Footer newsletter form, immediately below | **change** | The code comment at `Following.jsx:182` says the page no longer stacks two asks. On a page this short the footer form lands ~200 px under the sign-up button, so the render still shows two e-mail asks stacked. The comment describes a fix the screen does not have. |

### Inventory — signed in (from code)

| Element | Verdict | Reason |
|---|---|---|
| Tabs: Feed / Saved / Notes / Follows | **keep** | Right division. |
| Avatar filter row (`y-filter`) | **keep** | Good: filter by the thing you follow, with its crest. |
| `BookingRisk` card | **keep** | Reads as forecasting, not as the banned register ("may be booked this round"). Fine on vocabulary. |
| Feed items (match / result / lineup / forecast / saved) | **keep** | Saved items show Hit / Miss / Did not play with the final count. This is the honesty mechanic working. |
| **Missing: the reader's own record** | **add** | Saved items each carry an outcome and nothing aggregates them. |
| Follows cap line "N of 10 on your plan." | **change** | See Q2. |

### Proposals, ranked

1. **Add "Your record" to the Saved tab**: "Of your 23 settled saved forecasts, 18 came true. We
   said 81% on average; 78% happened." Every input already exists in `/me/saved` →
   `r.outcome.reached` and `r.forecast.p`. docs/51 §2.3 calls this "the one that creates
   ownership … the thing that does not churn", and it links the trust page to the personal page
   without a single new query. Highest value item on this screen.
2. **Show a real feed signed out.** One worked example — a club's next fixture, two lines, and
   yesterday's result with Hit/Miss — demonstrates the feature. The league grid describes it.
3. **Retitle the signed-out page.**
4. **Suppress the footer newsletter block when a sign-up CTA is on screen.**
5. **Remove the follows cap** (Q2): capping follows at 10 trains people not to invest in the
   product, and follows are the retention mechanism.

---

## P-19 / P-20 — Learn (`/learn`, `/learn/:slug`)

**Purpose.** Teach a reader to read a forecast — which, for a product whose whole claim is "our
numbers mean what they say", is load-bearing, not marketing.

### Inventory — index

| Element | Verdict | Reason |
|---|---|---|
| `h1` "Learn", "Two-minute reads. One picture each." | **keep** | Good promise, kept. |
| Category chips (4 chips over 4 articles) | **delete, for now** | "Start here" filters to one item. Two rows of control over four tiles. Reinstate past ~12 articles. |
| Four tiles with 170 px pictures | **change** | Four articles cost ~1,900 px of scroll. Halve the picture height on the index; keep the big picture on the article. |
| `PicScore` (the calibration line) | **keep** | The only picture that teaches an idea rather than decorating. |
| `PicTiers` (three badges) | **change** | It is literally the component that appears on every card; as a "picture of the idea" it shows nothing new. |
| **Missing: "What a percentage does and does not mean"** | **add** | The single most misread thing in the product. It currently exists as paragraph 4 of article 1 and as a bullet in Terms. |
| **Missing: "What (66 to 81) means"** | **add** | `lib/copy.range()` ships this on cards and nothing explains it anywhere. |
| **Missing: "How to read the track record"** | **add** | The page it supports is the one that needs a reader most. |

### Inventory — article

| Element | Verdict | Reason |
|---|---|---|
| Back link, picture, meta, h1, 4 paragraphs | **keep** | The writing is good, plain and honest ("A forecast is a reading of the data, not a promise"). |
| "Read next" — 3 tiles with 120 px pictures | **change** | **The footer is longer than the article.** ~600 px of teaching, ~1,000 px of onward tiles. Cut to one text link row. |
| Picture = `PicCard`, a 240 px stylised mock | **change** | An article called "How to read a forecast card" does not contain a forecast card. |
| "See the track record" button (how-we-score only) | **keep, extend** | Every article should end in the thing it explains. |

### Faults

1. **The teaching never reaches the moment of confusion.** `docs/24` §16 specifies Learn is
   "linked from the '?' icon on every card and chart". Grep of the whole front end: the only
   in-product entry is one line inside `ForecastSheet` — i.e. the reader must already have opened
   the detail overlay. Cards, the track-record chart, the tier badges and the likely range all link
   nowhere.
2. **Two Learn systems.** `ARTICLES` is a hardcoded array in `Learn.jsx`; `LearnArticle` falls
   back to `MarkdownPage` for unknown slugs, and Admin → Pages (AD-26) advertises authoring Learn
   pages. Anything an owner authors is reachable by URL and invisible on `/learn`.

### Proposals, ranked

1. **Render the real `ForecastCard` inside "How to read a forecast card", annotated** — callouts on
   the big number, the tier badge, the usual-rate tick, the reason line. The component exists;
   this is a layout, not a build.
2. **Add the two missing articles** ("What 78% means — and what it does not", "What the range in
   brackets means").
3. **Link Learn from the point of confusion**: a `?` on the tier badge, on the range, and on the
   track-record chart.
4. **Cut "Read next" to a text row.**
5. **Drop the category chips until there are enough articles to need them.**
6. **Merge the two Learn systems**, or make the index read `content_pages` as well.

---

## P-22 — Welcome (`/welcome`)

**Purpose, as built:** collect three preferences. **Purpose, as needed:** tell a new member what
this product is for, then collect preferences.

### Inventory

| Element | Verdict | Reason |
|---|---|---|
| 3-dot progress bar, "Step 1 of 3" | **keep** | Clear, short, honest about length. |
| Step 1 "Which leagues do you watch?" | **keep, demote to step 2** | Fine question, wrong first thing. |
| Step 2 "Pick 3 teams to follow" | **keep** | Good: real crests, real follow calls, instant effect. |
| `.wl-teams` with `max-height: 420px; overflow-y: auto` | **change** | A nested scroll region inside a scrolling page on a 390 px phone. Let the list grow or paginate it. |
| Step 3 alerts switches + `ProLock` | **keep** | Honest: the locked switch is visibly disabled with "Part of Pro" rather than silently failing. |
| Step 3 "Weekly e-mail" switch | **keep** | Double opt-in, says so. |
| Footer newsletter form on the same screen | **delete here** | The same ask twice on one screen. |
| "Next" / "Skip" | **keep** | Every step skippable, as promised. |
| **Missing: what the product is** | **add** | See below. |
| **Missing: a signed-out guard** | **add** | The page renders in full to a signed-out visitor (confirmed in the render: header shows "Sign in"). "Next" on the last step calls `PATCH /account/profile` and will fail into a toast. |
| Full site chrome (header, bottom bar, footer, disclaimer) | **change** | A first-run flow should own the screen. |

### Faults

1. **It is a tour of settings, not an introduction.** The first words a new member reads are
   "Step 1 of 3 — Which leagues do you watch?" The product is never named, the forecast is never
   shown, the track record is never mentioned, the one thing that distinguishes this product from
   a screener — that every forecast is settled in public — is never said.
2. **No payoff is shown.** The flow ends with `nav("/following")`, and the reader arrives at a feed
   with no explanation of what was built.
3. **Two e-mail asks on one screen.**

### Proposals, ranked

1. **Add a step 0 that is a claim, not a form.** Three lines and one real forecast card: what a
   forecast is here, that it is explained, and that every one of them is settled in public — with
   the current record number and a link to P-17. One screen, one "Start" button. This is the only
   moment in the product where a reader is guaranteed to be paying attention.
2. **Guard the route.** Signed-out → `/sign-up?next=/welcome`.
3. **Strip the chrome** for the duration of the flow (no footer, no newsletter).
4. **End on the payoff**: "Your feed has 3 clubs and 14 players in it. Here is tomorrow."
5. **Un-nest the team list's scroll.**

---

## P-23 — Contact (`/contact`)

**Purpose.** Let someone reach a human about data, account or payment.

### Inventory

| Element | Verdict | Reason |
|---|---|---|
| `h1` + lead with the two-working-day promise | **keep** | A stated reply time is itself a trust signal. Make sure it is true. |
| Name (optional) / E-mail / Message / counter | **keep** | Correct, minimal, labelled. |
| Submit disabled under 5 characters | **keep** | `v2.css` §16b already made disabled buttons readable. |
| "Never send passwords or card numbers." | **keep** | Good. |
| Success state | **keep** | Confirms the address it will reply to. |
| **Missing: a topic** | **add** | Admin → Inbox (AD-12) receives an undifferentiated stream. One `select` — Data looks wrong / Account / Payment / Something else — sorts the owner's queue for free. |
| **Missing: deflection** | **add** | "Cancel a plan → Account → Plan" and "A number looks wrong → tell us the match and the line" answer most of what arrives and reduce the owner's load. |
| Footer newsletter form | **change** | Two e-mail inputs on a page whose purpose is one e-mail input. |

### Faults

1. `h1` sits directly on the lead with no separation (margins collapse) — the only typographic
   rhythm fault on this screen.
2. "Questions about the data, your account or a payment" implicitly refuses everything else; a
   reader with a different question does not know whether to write.

### Proposals, ranked

1. Add the topic select, and pass it to the inbox.
2. Add two deflection links above the form.
3. Suppress the footer newsletter block on this page.
4. Space the lead from the title.

---

## P-24 — Legal (`/legal/:slug`)

**Purpose.** Terms, Privacy and About — the pages a cautious reader checks before trusting a
forecast product, and About in particular is a credibility page, not a formality.

### Inventory

| Element | Verdict | Reason |
|---|---|---|
| `h1` from `page.title` | **keep** | |
| Markdown body, no raw HTML (`Markdown.jsx` comment, docs/15) | **keep** | Correct sanitising posture. Do not add `rehype-raw`. |
| The Terms copy itself | **keep** | Unusually good. "A forecast of 70% means we expect the line to be reached about 7 times in 10, not every time" is the clearest sentence in the product — and it is buried in Terms. |
| **Missing: effective date** | **add** | `/api/public/pages/{slug}` returns `updated_at`; `Markdown.jsx` drops it. A Terms page with no date is the one thing a Terms page may not be. |
| **Missing: contents** | **add** | ~2,000 px of continuous prose on a phone with nine h2s and no jump list. |
| Footer newsletter form | **change** | Odd on a legal page. |

### Faults

1. No date (above).
2. Headings are tight against the following paragraph; `.prose` needs more space above `h2` than
   below it.
3. **Release gate, not a design item:** `legal_pages.py` seeds starter Terms/Privacy/About marked
   `starter=True`, and its own docstring says the text is "a starting point … not legal advice:
   have it reviewed before launch." `alerts.evaluate()` keeps an admin alert open until each is
   saved. If the build ships with starter text live, visitors are accepting unreviewed terms. Worth
   naming here because it is a trust-surface risk, even though the fix is editorial.

### Proposals, ranked

1. Render `updated_at` under the `h1` — "Last updated 12 October 2026."
2. Add a contents list on pages over ~4 headings.
3. **Move the "70% means about 7 times in 10" sentence out of Terms** and onto the forecast card
   and the track-record hero, where the reader who needs it actually is.
4. Space the headings.
5. Drop the newsletter block.

---

## P-27 — Not found (`*`)

**Purpose.** Recover a lost reader.

### Inventory

| Element | Verdict | Reason |
|---|---|---|
| "404" at 5 rem, `opacity: .9` | **change** | The largest, least useful thing on the page. |
| "We could not find that page." | **keep** | |
| **Missing: every way out** | **add** | No search, no link home, no suggestions. The only navigation is the bottom tab bar, which is chrome, not an answer. |
| Newsletter form | **delete here** | On a page with no other interactive element, the e-mail capture becomes the primary action. On an error page, that is the one thing it must not be. |

### Faults

A dead end. A reader who mistypes a player URL — which is how most 404s on this product will
happen — is offered a mailing-list signup and nothing else.

### Proposals, ranked

1. Add a search field, focused, with the attempted path as a hint. The `SearchOverlay` already
   exists and already searches clubs, players, leagues and referees.
2. Add three links: Today, Explore, Track record.
3. Shrink "404" to a label; lead with the sentence.
4. Remove the newsletter block.

---

# The four questions

## Q1. Track record: legible, honest, and is a reliability curve the right picture?

**Legible to a non-statistician: partly, and it degrades as you go down the page.** The headline
sentence ("When we say 93%, it happens 92% of the time") and the tier tiles ("90 of 100 came true")
are genuinely readable by anyone — that part is a real achievement and should not be touched. The
`Reliability` paragraph is better than most professional forecasters publish: it names the count,
states the margin, and says whether the gap is real or noise. But the chart below it is an
unlabelled scatter with a dashed diagonal, and reading it requires already knowing what calibration
is. A reader who does not know that cannot tell whether a dot above the line is good or bad.

**Honest about being wrong: no, in three specific ways.**
1. The headline band is *selected* — by `n`, which in this product always lands on 0.9–1.0 — and
   the reader cannot see the rule. A selected band is a chosen band.
2. A miss and a beat are framed asymmetrically: overdelivery gets "so we are promising less than we
   deliver", overstatement gets "which is the gap to watch". The second should be as plain as the
   first.
3. Tier tiles publish `actual` without `stated`, so the biggest numbers on the page cannot be
   checked against any claim — and the tier colour makes the bigger number look like the better
   one when on the populated data it is not.

**Honest about a thin sample: yes for one band, no for the rest.** `n >= 30` gating, dot size by
`n`, and the `Reliability` margin sentence are all correct instincts. But the margin is computed
for the headline band only; the chart draws an n=41 band and an n=1,791 band with identical
confidence and joins them with a line. The reader is shown a dramatic dive at the low end that is
almost certainly noise.

**Is a reliability curve the right picture? No — not as the lead.** It is the right *diagnostic*
and the wrong *lead picture*, for three reasons: it requires knowing what the diagonal means; it
cannot carry `n` and the margin beside each point without becoming cluttered; and in this product
two thirds of its area is permanently empty because the model almost never says anything under
80 %.

**What to lead with instead: a band table, one row per band.**

```
We said        It happened    From            
75%            72%            604 forecasts   ±3   ■ inside the margin
85%            86%          1,588 forecasts   ±2   ■ inside the margin
93%            92%          1,791 forecasts   ±1   ▲ we overstated by 1
```

Every row carries the claim, the outcome, the sample and the margin on one line, in plain numbers,
with no axis to read. It fits a 390 px phone. It makes a thin band visibly thin instead of visually
dramatic. And it forces the honest verdict to appear next to every number rather than once. Keep
the scatter below it, with margin bars and **no connecting polyline** — five independent estimates
joined by a line imply a trend nobody is claiming.

**What would make a sceptic believe it in ten seconds?** Not an aggregate. Aggregates are what
every dishonest forecast site publishes. Three things, in order:

1. **A named, dated miss.** "22 October — we said Kane 83% for 2+ shots. He had 1. Miss." A
   sceptic's ten seconds are spent looking for the misses; if they find them unprompted, in the
   open, with names and dates, the aggregates above become credible by association. If they have
   to hunt and cannot find one, nothing else on the page counts. **This is the highest-value change
   in the whole audit and the page has nothing like it.**
2. **The sample and the date range in the first sentence**, not the third paragraph.
3. **Honesty about what the page cannot yet prove.** Say it on the page: being right when you said
   90 % proves very little, because the base rate alone would manage it; skill shows in the 50–70 %
   band, where the sample is currently thin. docs/51 §1.3 already contains this argument, written
   against this product. A page that volunteers its own weakest point is believed about its
   strongest. A page that reports "93 → 92" as a triumph invites the reader to work out that it
   isn't one, and to wonder what else they must work out for themselves.

A note on what is *not* available yet and should not be faked: the product has a real skill
measurement — `engine_audit.py` computes log loss and Brier against a base-rate baseline with a
skill score, and `calibration.py` documents a 351,098-forecast walk-forward audit. None of it is
exposed by an API, and `league_base`/`spread` per rung are not stored (docs/50 §9.4), so
"we beat the obvious" cannot be computed on live forecasts today. Do not approximate it. Publish
the backtest, labelled as a backtest, and say the live skill measurement starts when the lower
bands fill.

## Q2. The free/paid boundary — is the line in the right place?

**What is free today** (`backend/plans.py` `FREE`): everything, in rationed amounts. 10 Finder
searches a day, 1 league per search, 20 insight cards a day, 5 games in the grids, 10 follows, 20
saves, 20 notes. Alerts, the tactical matchup tab and CSV export are off.

**What is paid** (`PRO`, CA$9.99/mo or CA$79.99/yr): the same things, uncapped, plus those three
capabilities.

**Is the line in the right place? No, and the reason is specific to a trust product.** Seven of ten
paid entitlements are "more of the same" (docs/51 §1.2 measured this). A volume gate makes two
promises a trust product cannot keep. It says the free tier is a *sample* — a trimmed version of
the real thing — which invites the reader to assume the good forecasts are behind the wall. And it
caps follows and saves, which are the two behaviours that *build* the reader's own settled record —
the one asset that would make them trust the product and stay. Charging to let someone keep more
evidence about you is backwards.

**Where it is right:** the settled record is entirely free and ungated — `/track-record` needs no
account — and `LockSheet` is clean: no countdown, no scarcity, "Not now" weighted equally. Keep
both. docs/51 §2.2 is correct that hiding the record would be the worst possible move; the
remaining problem is that the page does not *say* the record is free, so the reader gets no credit
for it.

**Where it should be: timing, not volume.** Free gets the complete settled record and every
forecast after kick-off. Paid gets today's forecasts before kick-off, and alerts. A forecast is
perishable — its value is in arriving in time — which is a scarcity the reader already understands
and which needs no banned vocabulary to explain. Remove the caps on follows, saves and notes
entirely: they punish the behaviour the product wants.

**Where should a visitor first hit the boundary?** Not on a cap, and not on Plans. On **tomorrow's
forecast**, on Today, after they have read yesterday's settled result for the same club — a card
that shows the line and the reasons and says "the number is here at 18:00, or now on Pro." They
have, by that point, seen the product be right and be wrong in public and still be there. That is
the only moment at which a paywall in this product is persuasive rather than suspicious.

**One tactic already in place that costs credibility:** the 5-day trial converts to a paid plan
automatically, and the card says only "5-day free trial". The conversion is disclosed in Terms and
nowhere near the decision. That is small, fixable, and exactly the sort of thing a reader who came
for honesty will hold against everything else on the page.

## Q3. Welcome — does a new reader learn what this is FOR?

**No. It is a preferences wizard with a progress bar.** The first thing a new member reads is
"Step 1 of 3 — Which leagues do you watch?". Across all three steps the product is never named,
a forecast is never shown, the words "track record" never appear, and the one claim that
distinguishes this from a statistics screener — that every forecast is scored afterwards and the
record is public, including the misses — is never made.

It is not even a tour of features; it is a tour of *settings*. A tour of features would at least
show a forecast card. This shows league logos, club crests and three switches.

It is also reachable signed out, where it is a dead flow, and it asks for an e-mail address twice
on the same screen (step 3's weekly-e-mail switch, plus the footer newsletter form).

What it gets right: every step is skippable, the locked alert switch is visibly disabled rather
than silently broken, and step 2 performs real follows so the feed is genuinely populated on exit.
Keep all three.

The fix is one screen: a step 0 that states the proposition and shows one real forecast card with
the current record beside it. This is the only moment in the product with a guaranteed attentive
reader, and it currently spends it on league checkboxes.

## Q4. Learn — real work or filler?

**The writing is real work. The placement makes it close to filler.**

The four articles are honest, plain and short, and they say things the product needs said: "A
forecast is a reading of the data, not a promise. Football is noisy, and even a high number will
not happen every time." "How often each tier came true is not something we claim. It is counted
from finished matches." That is correct and well judged.

Three things stop it doing its job:

1. **It is not reachable from where readers get confused.** docs/24 §16 specifies Learn is "linked
   from the '?' icon on every card and chart". The only in-product link is a line inside
   `ForecastSheet` — the reader must have already opened the detail overlay. Cards, tier badges,
   the likely range and the track-record chart link nowhere. A reader who does not understand the
   number has no path from the number to the explanation.
2. **The article about reading a card does not contain a card.** It contains a 240 px stylised
   mock. The real component exists and could be rendered and annotated.
3. **Two of the most-misread things in the product have no article at all**: what a percentage
   does *not* mean (one paragraph inside article 1, and a better-written bullet inside Terms), and
   what the "(66 to 81)" range on every card means (explained nowhere, while `lib/copy.range()`
   ships it).

Add to that the proportions — the "Read next" block is longer than the article it follows, and
four category chips filter four articles — and the section reads as built-and-left rather than
maintained. It is close to being genuinely useful; the content is already there and the gap is
entry points and two missing pieces.

---

## Constraint check on everything proposed above

- **Reserved vocabulary:** nothing proposed uses a word in `textguard.BANNED`. "Settled record",
  "came true", "forecasts", "before kick-off", "the reasons" carry all of it. The one reserved
  word stays where it is already allowed: inside the exact footer disclaimer, unchanged.
- **Colour:** every colour change named above is a token swap (`--up`, `--text`, `--text3`,
  `--tier-*`). No literal hex is proposed in any component.
- **Class names and test ids:** nothing proposed renames or removes either. The `.tr` collision fix
  is additive — `justify-items: stretch` on the existing rule, or a second class on the section.
- **390 px:** all nine screens pass today and nothing proposed adds a wide element. The band table
  in Q1 is four short columns and was sized for 390 px.
- **Honesty:** three existing items are called out as credibility costs — the band-selected
  headline, the asymmetric miss wording, and the silently-converting trial. The one conversion
  surface reviewed and found clean is `LockSheet`.
