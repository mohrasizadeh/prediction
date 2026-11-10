# 75 — The badge names its axis, and the titles carry the search

Two changes, one branch. Neither adds a feature; both fix something that was quietly costing us.

---

## Part 1 — The badge

### What was wrong

The badge read **Strong / Solid / Watch**. Those are confidence words, so a reader maps them to
*strong chance*. But the badge has never graded the chance — it grades the **departure from this
player's usual game** (docs/52, docs/58).

So a reader meets a 57% card reading *Watch* beside a 56% one reading *Solid*, and concludes the
product is broken. It isn't. **The concept was right and the label was arguing with it.**

This is the single hardest idea in the product, and the word on the badge was actively teaching the
wrong model before anyone got as far as the explanation.

### What changed

| Stored | Shown |
|---|---|
| `Strong` | **Well above usual** |
| `Solid` | **Above usual** |
| `Watch` | **Near usual** |
| *(none)* | nothing on a card; *Typical* where a filter needs a word |

Named for the axis, the contradiction evaporates without a word of explanation: *"56%, above usual"*
beside *"57%, near usual"* is obviously coherent. Nobody expects "above usual" to track the
percentage, because it doesn't claim to.

### What did NOT change

**Nothing below the display layer.** The stored values are still `Strong` / `Solid` / `Watch`:

- the engine writes them (`engine_bridge`, `tiering`)
- settings name them (`engine.tier_strong`, `engine.tier_solid`)
- `forecast_outcomes` keeps them, so the whole track record stays comparable
- every filter and query uses them
- the palette tokens stay `--tier-strong` / `--tier-solid` / `--tier-watch`
- `TierBadge`'s class and `data-testid` keep the stored value

**No migration. No data touched.** A rename at the display layer only.

### Where the words live

Three copies, by necessity, each pinned to the others by a test:

| Copy | Why it exists |
|---|---|
| `frontend/src/lib/copy.js` → `TIER` / `tierLabel()` | The app |
| `backend/tiering.py` → `TIER_LABEL` / `label()` | The server, which also writes tier *notes* |
| `frontend/src/admin/ads/draw.js` | The ad canvas, deliberately free of app imports |

`blog_render.py` imports the backend map rather than keeping a fourth. `selftest_blog` asserts all
three agree, and that none of the old confidence words survives anywhere a reader can see one.

An **ad is the first place most strangers meet the badge.** An ad saying *Strong* next to a card
saying *Well above usual* would teach two vocabularies for one thing — hence the test.

### Two notes reworded

`tiering.py` writes explanatory notes that named a tier. *"Held at Above usual until…"* is not a
sentence anyone would write, so they were reworded rather than substituted:

- *"Held at Solid until our record on these lines is measured"* → **"Held back until our record on
  these lines is measured"**
- *"Under 80%, where Solid starts"* → **"Under 80%, where the next grade up starts"**

### The cost, stated

"Well above usual" is three words where "Strong" was one. It is less punchy and less shareable, and
the filter chips are taller on a phone (`.k-chips` wraps, so they wrap rather than overflow).

That is the trade. A punchy word that teaches the wrong model is worth less than a plain phrase that
teaches the right one, on the one concept most likely to make a newcomer leave.

### One thing to decide later

For an FPL audience the question is *"will he return?"* — a **probability** question, not a departure
question. On any Captain Picker, lead with the probability and demote the badge to a secondary
*"and this is unusual for him"* signal. Don't make FPL users learn this axis to use the headline
feature.

---

## Part 2 — The titles carry the search

### What the copy rules actually forbid

Checked against the regex rather than from memory. Only the **transaction** words are banned:

| Allowed | Banned |
|---|---|
| prediction, predictions, forecast, tips, stats, captain, differential, returns, projection, analysis, preview, form, record | odds, picks, props, bet/betting, accumulator, parlay, tipster, units, hit rate, stakes, lock, banker, punt |

**`{team} vs {team} prediction` — the highest-volume query shape in football — is fully available.**
We had been avoiding a word nothing forbids.

### What changed

| Page | Before | After |
|---|---|---|
| Blog, pre-match | *Arsenal v Chelsea forecasts, 11 November 2026* | **Arsenal vs Chelsea prediction, stats and team news** |
| Blog, settled | *Arsenal 2–1 Chelsea: how our forecasts did* | **Arsenal 2–1 Chelsea: stats and how our predictions did** |
| Player | *Bukayo Saka* | **Bukayo Saka stats, shots per game and what we expect next** |
| Team | *Arsenal* | **Arsenal stats, shots and cards per game** |
| Referee | *Michael Oliver* | **Michael Oliver referee stats: cards per game** |
| Referees | *Referees* | **Referee stats: cards per game** |

"vs", not "v" — people type "vs". *Forecast* is our word for the thing; *prediction* is the word
someone uses to look for it, and **a title that doesn't contain the search is a page that doesn't
answer it.**

The player, team and referee pages were bare names. A page titled *"Bukayo Saka"* competes with
every page on the internet that mentions him and answers none of the questions people type. These
pages already hold per-game history and a forward-looking number — the titles now say so.

Referee pages are the cheapest win in the product: the data is there, the competition is nil.

### `_fit()` — titles that fit and still read

Rendering the long names found a real bug: a hard `title[:70]` produced

> *Brighton & Hove Albion 0–0 Wolverhampton Wanderers: how our prediction*

— cut mid-phrase, in a search result, on two of the longest club names in the league. Descriptions
had the same fault (*"…11 Novemb"*).

`_fit(limit, *candidates)` takes candidates longest to shortest, returns the first that fits, and
only ever trims at a word boundary as a last resort. The bare fixture is the floor, so both clubs
are always named.

---

## What is deliberately not in this branch

- **The FPL layer and the Captain Picker.** Those are builds, not tweaks, and they need data and
  product decisions this branch does not have. docs/74 §8 sequences them.
- **Social and paid-channel work.** Not code.
- **Any change to how a tier is computed.** The grading is unchanged. This branch argues about words.
