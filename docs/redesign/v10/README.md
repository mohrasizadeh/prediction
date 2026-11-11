# v10 — the card, locked

Two agreed designs, reached over about twenty rounds with the owner. **Open `desktop.html` at
1366px and `phone.html` at 390px**; both run from this folder with no build step.

> **This folder is the DESIGN, not the implementation.** `frontend/src/components/ui/ForecastRow.jsx`
> and `frontend/src/styles/likely.css` still render the previous card (docs/77). Building this is
> the next piece of work, and the prototypes here are its reference.

---

## 1. What both share

**The forecast is a sentence.** `Marcus Linday makes 2+ tackles`. The subject, the verb, the line
and the market, in that order, reading left to right. Everything else on the card serves it.

**The verb belongs to the market.** A player *takes* shots, *makes* tackles, *commits* fouls, *wins*
corners, *scores* goals — so changing the market must change the verb, or the sentence stops being
English the moment a reader explores. Two forms per market, because a club is plural in the
product's own voice (*"SC Heerenveen take"*). This belongs beside `STAT_LABEL` in
`engine_bridge.py:339`, which already holds the singular/plural **noun** pair per market and already
ships it to the card. See §6.

**The line reads `2+ tackles`, never "2 or more tackles"** — the same phrase the market label uses
in Finder, the blog and the ad builder, so one form of words travels the whole product.

**Three grades, three fills.** Strong and Solid were two greens a few points apart in value and read
as the same badge down a column. They now differ in **fill as well as hue**, which is what survives
a glance, a small screen and a colour-blind reader:

| | fill | text |
|---|---|---|
| **Strong** | `--accent` | `--on-accent` |
| **Solid** | `--brand` | `--on-brand` |
| **Watch** | `--surface1`, `--border-strong` outline | `--text3` |

**The result is a mark and a count in a muted shape** — green ✓ `got 3`, red ✗ `got 1`. Same height,
radius and padding as the grade badge so the two read as siblings, but a **tint** rather than a fill:
the grade is a judgement we are making and the thing the feed sorts by; the result is a fact that has
already settled. The mark carries the verdict, so colour never does that job alone.

**The ten games are word-sized.** Tufte's test for a sparkline is that it is about the height of the
text beside it. Importance comes from where it sits and how it contrasts, not from bulk — the round
where the bars went to 45×44px is the one the owner rejected outright.

**Bars are sized in percentages, not pixels.** One CSS height governs the strip at both widths. Sized
in pixels from JavaScript, raising the strip in CSS stretched an empty box and left the data where it
was.

---

## 2. Desktop — a table, 1366px

Nine column widths, one per kind of data, every cell naming **both** its row and its column:

```
Forecast 500 · Last 10 150 · Result 128 · Chance 74 · Grade 96 · Why 74 · Lineup 92 · Actions 84
```

- **Rows are 70px**: 22px strip, 20px of padding top and bottom, 24px left and right.
- **The sentence is ONE cell.** Splitting the name, verb, line and market into four columns aligned
  them and stopped them reading as a sentence, because the verb had to be flung to the right edge of
  its cell to make the alignment work. One cell, natural spacing; the six data columns after it keep
  their alignment regardless.
- **Headers and content are centred together** on each column's axis, so they line up by
  construction whatever ornament sits in front of the text. **Chance keeps its right edge** — it is a
  column of numbers, and numbers align right or they cannot be compared down a page.
- **Why sits after Grade**, because it explains the forecast. Save and combo stay at the far right,
  because they act on it.

## 3. Phone — a card, 390px

One card per forecast, 16px gutter, 4/8px rhythm, **350px** tall.

```
face 46 · name 19 · figure 42 ·· grade beneath the figure
the sentence, full width
┌ LAST 10 · DID HE REACH IT ───────────────┐
│  the ten games, 46px            6 of 10  │
└──────────────────────────────────────────┘
✓ got 3   ● Starting
──────────────────────────────────────────── hairline
Why                                   ☆  ＋
```

- **The two changeable words are set at the size and weight of the words around them**, marked by
  the brand colour and a dotted rule. They were 17px bold pills in 17px regular prose, which read as
  machinery dropped into a line of text. The 44px tap area is carried by a pseudo-element that costs
  no ink.
- **Every target is 44px with 8px between**, the project's own standard (docs/12 F1 and L18,
  docs/36 A11Y-6) — which `hig.css` and `hig-admin.css` already set under `pointer: coarse`.
- **The evidence is in a labelled panel**, so the proof is visibly a separate object from the claim,
  and the label says what the bars mean without opening Why. It says *did they reach it* on a club.
- **Each band closes on the right.** Anchoring everything left left a hard left edge and a ragged
  right one — dense on one side, empty on the other.

`p-variants.css` also holds the three variants this was chosen from: `p1` compact (258px), `p2`
framed evidence (339px), `p3` big answer (303px). The locked card is `p4`.

---

## 4. The measurements that settled arguments

| | |
|---|---|
| Desktop row | 70px, strip 22px |
| Phone card | 350px, strip 46px |
| Phone targets | 0 under 44px, minimum gap 8px |
| Horizontal overflow | 0px at both widths |
| Desktop columns | one x per column, verified by measurement |

## 5. Open, and deliberately not decided here

- **The strip's scale is per row** (`mx` = that subject's own ceiling), so bar heights are comparable
  *within* a row and meaningless *between* rows. Right for "did he clear his line", wrong for
  comparing two players, and a shared scale would flatten every low-volume player into a sliver.
  A decision about the statistic, not the layout.
- **A custom market label** (`copy.market_labels`) will not compose into a sentence. The card should
  fall back to the plain `2+ tackles` form when one is in play.
- **`match_goals`** has the match as its subject, so no verb in the table fits. It wants its own
  sentence form or the plain label.
- **The ad builder's card template** still draws the old layout.

## 6. What the backend needs

```python
# beside STAT_LABEL in engine_bridge.py
STAT_VERB = {"tackles": ("makes", "make"), "shots": ("takes", "take"),
             "sot": ("has", "have"), "fouls": ("commits", "commit"),
             "fouls_committed": ("commits", "commit"), "saves": ("makes", "make"),
             "corners": ("wins", "win"), "goals": ("scores", "score"),
             "goal_involvements": ("has", "have"), "yellow": ("picks up", "pick up")}
```

Shipped on each market exactly as `noun` already is (`queries.py:922`). A verb table in the frontend
would drift the first time a market is added to the engine and nobody updates the card.
