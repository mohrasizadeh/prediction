# 58 — The tier grades the number on the card

Supersedes the tier rules in `31_live_tracking_and_earned_tiers.md` §"The rule now", the note
machinery in `48_tier_note_lift_scale_quickview.md`, and the lineup rows in
`25_lines_normalised_averages_referees.md` and `27_if_he_plays_and_lineup_badge.md`. The lineup
BADGE in docs/27 is unchanged and is now the only place the start question is answered.

## What was wrong

The card showed `p` — the chance he reaches the line, assuming he plays. The tier was computed on
`p × p_play`, the chance he reaches it *and* features. Two different quantities, presented as one
judgement about one forecast. So a card could read **94% and "Watch"** and be telling the truth
twice over, which is not a thing a reader can be expected to hold in their head.

On top of that were three hard caps, all keyed to the lineup:

- a player under `engine.likely_starter_p` (0.85) was badged `unsure` and could not be Strong or
  Solid **whatever his number was**;
- a Strong line for any player without a confirmed eleven was knocked to Solid
  (`engine.strong_needs_lineup`);
- a benched player could reach Watch at best.

And every feed admits Strong and Solid only (`queries.py:70, 97, 417, 1172`;
`Today.jsx` `RANK`). Measured on the demo league 48 hours before kick-off: **206 visible player
rows produced 3 Solid and 0 Strong.** Strong was not merely rare, it was arithmetically impossible
— `p` is capped at 0.97 by calibration and `p_play` at 0.8812 by the absence model, so the whole
chance could not reach the 0.90 Strong asks for. The best players in the league were absent from
Today and Insights until about an hour before kick-off, every week.

docs/48 met this exact case — it names Mbappé — and answered it by adding an explanatory *note*
rather than asking whether the model was right. That is why it came back.

## The rule now

**The tier is the bar the number cleared, and nothing else.**

- **Strong:** `p` ≥ `engine.strong_min` (0.90) and the low end ≥ `engine.strong_lo_min` (0.84).
- **Solid:** ≥ `engine.solid_min` (0.80), low end ≥ `engine.solid_lo_min` (0.70).
- **Watch:** ≥ `engine.watch_min` (0.60). Below that, no tier.
- **The track record can lower a tier and never raise one**, unchanged — except that it is now
  measured on `p` over matches the player PLAYED, which is what `queries.track_record` has always
  reported to readers. It used to be keyed on the whole chance with a no-show scored as a miss,
  so a line could be demoted by a record that was not about it.
- No lineup condition anywhere. `engine.strong_needs_lineup` is deleted.

`p_play` still does two jobs, both of them honest: `engine.min_p_play` (0.5) drops the card of a
player unlikely to feature at all, and it sets the lineup badge.

## Why this is not a softening

`p` already carries expected minutes. A substitute's ladder collapses on its own — measured, a
confirmed bench player's 1+ shot rung sits around 0.40 — so he fails Watch on his number without
any separate bench rule. Nothing is being waved through.

The start question is answered twice on the card already, which is the owner's point and the
reason this is a double-count rather than a trade-off:

- the **lineup badge** — "Confirmed starter", "Likely lineup", "Lineup not sure", "On the bench";
- the **minutes row** under each of the last ten games, which is how you see a regular starter.

And `p_basis = "played"` puts "Assumes he plays" on the face of the card.

## What a reader sees change

A rotated star with a 94% shots line now reads **94%, Strong, "Lineup not sure"** instead of
**94%, Watch**. The uncertainty did not disappear; it moved to the badge that exists to carry it.
