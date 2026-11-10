# 74 — MVP audit, competitive position, audience and pricing

Audited 10 November 2026 against the repository at `181a3c8`. Everything below about the code was
read out of the code. Everything about the market is judgement, labelled as such.

---

## 1. How MVP-ready is it

One number hides the answer, because three different things are being asked.

| Dimension | Ready | Why |
|---|---|---|
| **Feature completeness** | **90%** | 26 public screens, 37 admin screens, 73 backend modules, 297 API routes, 52 test suites, all green. Accounts, 2FA, billing, audit log, CSP, rate limiting, Site Studio, media library, ad builder, posting queue, waitlist, newsletter, combos, Finder, blog. |
| **Launch readiness** | **60%** | Three hard blockers below, none of them code. |
| **Revenue readiness** | **35%** | Billing is switched off, and the accuracy claim is not yet evidenced end to end. |
| **Distribution readiness** | **20%** | Findability landed this week. Nothing has been published, indexed or shared yet. |

**Headline: ~65% MVP-ready.** The engineering is well past MVP. What is missing is almost entirely
non-engineering, which is the harder half to finish because none of it can be done by writing code.

### The honest shape of the problem

This codebase is **over-built for an MVP and under-evidenced for a paid product.** There is a media
library, a posting queue with HMAC-signed webhook delivery and retry backoff, a nine-template ad
builder, a combo builder, and a full design-system admin — on a product that has not yet shown a
stranger a single forecast. Meanwhile the one claim the whole thing rests on, *our numbers are
good*, is supported by a backtest whose own docstring says it runs on simulated data.

That is not a criticism of the work. It is a statement about where the next month should go.

---

## 2. The three launch blockers

### Blocker 1 — Credentials in git history ⛔

740 tracked files under `.emergent/`, `test_reports/` and `memory/`, carrying an owner e-mail,
`ADMIN_INITIAL_PASSWORD`, a post-setup password, a `__Host-sid` session cookie and a TOTP secret with
its recovery codes.

They are **in history**, so deleting them at the tip does nothing. The sequence is: rotate every
secret → reset 2FA → revoke sessions → `git rm -r --cached` → `.gitignore` → `git filter-repo` →
force-push → ask collaborators to re-clone.

This has been outstanding for the whole of this engagement. It is the single thing that should be
done before anything else, and it gets worse the longer the repository exists.

### Blocker 2 — `ENV=production` is unset ⛔

`/docs` and `/openapi.json` are public, and the production CSP is not applied. `server.py` gates both
on `PROD`. One environment variable.

### Blocker 3 — `PUBLIC_BASE_URL` is unset ⛔

Now load-bearing for four things: emailed links (**including password resets**), share images, the
sitemap, and every blog post URL. Until it is set they all say `localhost:3000`.

All three are Emergent environment settings, not deploys.

---

## 3. The credibility gate

`backend/soccer_brain/backtest.py`, its own docstring:

> *"Run on simulated data now; the same harness runs on real data later."*

So `backtest_report.txt` — the calibration table, the tier accuracy, the log-loss comparison — is the
engine recovering the generating process of a simulator **written by the same project**. That is a
genuinely useful engineering check: it catches implementation bugs and proves the maths is wired up.
It is not evidence of real-world accuracy, and it cannot support a subscription whose entire pitch is
accuracy.

**This is not as bad as it first looks.** `docs/validation/` holds substantial real-data research —
StatsBomb open data across three leagues, openfootball, walk-forward runners, `audit_real.py`,
`ratings_walkforward.py`. The *components* were tested against reality. What does not yet exist is an
**end-to-end record of this engine's own published forecasts scored against results**.

Two things in the simulated report deserve attention regardless:

- The full engine scores **0.469** against a simple no-context baseline at **0.478** — about **2%**.
  The tactical matchup terms tie the model without them (`plain` is also 0.469). The large win is
  over `raw`, a last-10 rate, at 0.694 — *"substantially better than what a basic stats site shows"*
  is defensible; *"our tactical model is the edge"* is not yet.
- On match outcome the engine **loses to league frequencies** (1.0820 vs 1.0743). Match outcome is
  not the product, but do not put a win/draw/loss bar anywhere that implies it is a strength.

**The fix is calendar time, not work.** `features.beta_tag` stays on and the Track Record page
accumulates until `track_record.min_scored` is met on live forecasts. The acceptance checklist
already encodes this as C7. Plan on a full season, or at minimum a few hundred scored forecasts per
market, before the Beta tag comes off or anyone is charged.

---

## 4. Competitive position

### The field

| Tier | Who | Price | What they have that you don't | What you have that they don't |
|---|---|---|---|---|
| Mass-market scores | Sofascore, FotMob, OneFootball, 365Scores | Free–$2/mo | Tens of millions of users, every league, live, apps | Per-player line probabilities with stated reasons |
| Open stats | FBref, Understat, WhoScored | Free | Depth, trust, SEO authority built over a decade | Any forward-looking number at all |
| Fantasy tools | Fantasy Football Hub, Fix, Scout | £3–8/mo | A named audience that already pays | A calibrated probability per line |
| Club / enterprise | Opta, StatsBomb, SciSports | €899–1,499/mo | Proprietary tracking data | Nothing — different market |
| Prop research tools | (betting-adjacent) | $20–80/mo | Willingness to pay | Compliance, and a public record |

### Where you actually rank

**Top of the field, alone, on two axes:**

1. **Reason transparency.** Every forecast carries the model's own feature contributions worded as
   sentences, plus a ten-game strip the reader can check. Nobody in the consumer tiers does this.
   Most "AI prediction" sites generate narrative *after* the number.
2. **Willingness to publish misses.** The Track Record page, the settled blog posts, the tier that is
   honest enough to say *"no badge — tonight looks like any other night."* This is rare because it is
   commercially uncomfortable, which is exactly why it is defensible.

**Bottom of the field on everything that drives acquisition:** coverage breadth, brand, app presence,
live experience, SEO authority, and audience. You are at zero users.

### The strategic bind, stated plainly

Your product's **function** sits in the $20–80/mo tier. Your product's **vocabulary** sits in the
$0–2/mo tier — by deliberate choice, enforced in CI by `textguard`.

That choice is right. It keeps you out of a regulated, platform-hostile, app-store-restricted
category, and it is the reason the compliance surface is clean. But it has a consequence that should
be faced rather than discovered: **three of the four highest-volume search terms in this space are on
your banned list.** You cannot compete for the traffic the adjacent category buys. You have to earn a
different audience on different terms.

Which makes the next section the most important one in this document.

---

## 5. Target audience

### The problem

The product does not currently name its user. It is built for *"someone who wants to know how likely a
player is to reach a stat line, and why"* — which describes a behaviour, not a person. Every screen is
excellent and no screen is addressed to anybody in particular.

### The candidates

| Audience | Size | Pays? | Fit | Verdict |
|---|---|---|---|---|
| Prop researchers | Large | **Yes, readily** | Perfect functional fit | **Excluded by your own rules.** Correctly. |
| **FPL managers** | ~11M players | **Yes, £3–8/mo** | Strong | **The beachhead** |
| DFS / fantasy (other) | Large, US-centric | Yes | Medium — wrong sport weighting | Later |
| Analytics hobbyists | Small | Rarely | High | Good for credibility, not revenue |
| Media & creators | Tiny | B2B rates | High | Opportunistic, not a plan |

### Recommendation: Fantasy Premier League managers

Pick one audience. Pick this one.

- **They already pay.** £3–8/mo for tools is an established norm in this niche. No education needed.
- **Their decision is literally your output.** *Will this player return?* is a probability question
  about goals, assists and minutes — which your engine already forecasts natively.
- **No vocabulary problem.** Nothing in FPL language touches your banned list. You can compete for
  *"best FPL captain gameweek 12"* without compromising a single compliance rule.
- **Seasonal urgency drives weekly return visits** — the hardest retention problem in a stats
  product, solved by the format itself.
- **English-language, UK-heavy, highly online, intensely communal.** Reddit, Discord and YouTube
  distribution is well-trodden.
- **Your differentiator is their complaint.** FPL tools give rankings and projected points with no
  reasoning. "Here is the number, here is why, and here is our public record" is exactly the gap.

**What it needs that you do not have:** FPL's own vocabulary. Price, points, ownership %, captaincy,
differentials, fixture difficulty, gameweek numbering, deadline times. That is a translation layer
over an engine that already computes the hard part — **weeks, not months.**

A Captain Picker that says *"Haaland, 71% to return, and here is why, and here is how we did on this
call the last ten weeks"* is a product with a named buyer. "A football forecast site" is not.

---

## 6. Pricing

### The prerequisite

**Do not charge before the Beta tag comes off.** The product's entire claim is accuracy. Charging for
accuracy you have not yet evidenced on live data is the one move that would damage the thing you have
spent this long building. Free until the record exists; then price it.

### Recommended structure

Assuming the FPL beachhead and a GBP-first market — note `plans.currency` currently defaults to
**CAD**, which is wrong for this audience.

| Tier | Price | Contents |
|---|---|---|
| **Free** | £0 | 3 Finder searches a day, 1 league, 20 insights a day, 10 follows, the blog, the full track record. Generous on purpose: it is the SEO surface and the proof. |
| **Pro** | **£3.99/mo** or **£29/yr** (39% off) | Unlimited Finder, all leagues, 10-game grids, alerts, matchup tab, CSV export, combos |
| **Season** | **£24** one-off, Aug–May | The format this audience actually thinks in |

Your `plans.py` entitlements already encode almost exactly this split. The structure is built; only
the numbers and the currency need setting.

### Why £3.99 and not £9.99

- It sits inside the established £3–8 band, at the friendly end, where an impulse decision is
  available to someone who has never heard of you.
- You cannot yet charge a premium for accuracy, because you cannot yet prove it. Price for adoption
  now; raise it when the record is public and good. Raising a price on a proven product is easy;
  rebuilding trust after over-charging an unproven one is not.
- Annual and seasonal plans matter more than the monthly rate here. Football is seasonal, churn in
  May is structural, and a season pass converts that from a loss into a renewal moment.

### Mechanics

- **Keep the 5-day trial** (`plans.trial_days`), and require a card. A trial without a card in a
  weekly-decision product gets used once and abandoned.
- `billing.allow_promo_codes` is already on — use it for the FPL communities you seed into.
- Do not discount below £2.99. Below that you are competing with free, and free wins.
- `features.billing` is **false** today, which means *every signed-in user is on the top plan*. That
  is the correct setting for right now and a revenue blocker the day you decide to charge. Flip it
  deliberately, with the record published, not quietly.

---

## 7. User experience

### What is genuinely good

Mobile-first discipline verified repeatedly at 390px. One shared forecast row across every surface
(docs/61). The reasons are real model contributions, not narrative. Empty, loading and error states
everywhere. WCAG work done rather than claimed. The tier system is intellectually honest in a way
almost nothing in this category is.

### The five risks, in order

**1. The tier system is the hardest idea in the product, and it is unexplained at the point of use.**

The badge grades *departure from a player's usual game*, not the percentage next to it. So a 57% card
reads Watch while a 56% one reads Solid. That is correct, defensible, and genuinely confusing. A new
reader's first encounter with it is a contradiction they have no way to resolve — the explanation
lives in Learn, which they have not visited.

*Fix:* one tappable line under the first badge a reader meets: *"Why is this Solid at 56% when that
one is Watch at 57%?"* The blog posts already do this well, with a sentence under each badge. Bring
that sentence into the app.

**2. "No badge" is the commonest state, and an un-badged feed reads as an empty one.**

This is honest and it is a presentation problem. Most nights look like any other night — true, and it
makes the product look like it has nothing to say.

*Fix:* lead surfaces with what *is* unusual, say plainly how many lines were considered, and treat "a
quiet night" as a finding rather than a blank.

**3. There is no first-run experience.** A stranger lands on Today and must infer the entire
conceptual model from a grid. Learn exists but is passive. Three screens on first visit — what a
forecast is, what a tier means, what the record shows — would carry more weight than any feature in
the backlog.

**4. `images.enabled` defaults to false** and gates every crest and avatar app-wide. This single
default produced three separate "missing feature" reports during this engagement. For a product whose
rows are *"player, club, opponent"*, a crestless build looks broken rather than minimal.

*Fix:* default it on, or surface it in first-run setup where it cannot be missed.

**5. Free gives everything.** With `features.billing` false, a signed-in user has Pro. Correct for
today; it means nobody has ever experienced a limit, so you have **no evidence about which limits
bite** — which is the data you need to price confidently.

### Smaller, worth doing

- The You page still renders differently from the agreed design.
- The retired `ForecastCard` survives only in `DevKit.jsx` — delete it, or it will get reused.
- The lead-line / ungraded-rung rule is still unexplained on screen.
- `emailer.base_url()` duplicates `site_studio.base_url()`, whose docstring claims to be the only
  reader of `PUBLIC_BASE_URL`. One-line fix; the invariant is right.

---

## 8. What to do next

### Weeks 1–2 — stop the bleeding, start the clock

1. **Rotate the credentials and purge the history.** Nothing else matters if this leaks.
2. Set `ENV=production` and `PUBLIC_BASE_URL`.
3. Enable the leagues you intend to cover; confirm each produces forecasts on the Engine screen.
4. **Start the live track record.** It is a calendar dependency — every week not counting is a week
   added to the date you can charge.
5. Publish the first blog posts and submit the sitemap. Distribution compounds; start it early even
   though it pays late.

### Weeks 3–6 — name the audience

6. Build the FPL layer: price, points, ownership, captaincy, fixture difficulty.
7. Ship a **Captain Picker** as the single hero feature. One screen, one question, your reasoning,
   your record.
8. Fix the tier explanation at point of use, and add a three-screen first run.
9. Default `images.enabled` on.

### Weeks 7–12 — earn the right to charge

10. Weekly *"what we got most wrong"* post. It earns links, and links are what make the fixture posts
    rank.
11. Seed the FPL communities. Lead with the record, never with a prediction.
12. When `track_record.min_scored` is met and the numbers hold: Beta tag off, `features.billing` on,
    £3.99.

### Explicitly not now

Combos, the ad builder, the posting queue, more markets, more leagues. All built, none of them the
constraint. The constraint is that nobody knows this exists and the accuracy claim is not yet proven.

---

## 9. The one-paragraph version

You have built, to a standard well above MVP, a football forecasting product that is more honest than
anything else in its category — and you have not yet shown it to anybody, cannot yet prove its central
claim on live data, have credentials sitting in a git history, and have not decided who it is for. The
engineering risk is behind you. Everything in front of you is distribution, evidence and positioning.
Pick FPL managers, start the record clock this week, purge the secrets today, and charge £3.99 the
month you can point at a public record and say *"this is how we did."*
