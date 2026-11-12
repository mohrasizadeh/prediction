"""tiering.py -- earned tiers (docs/31). A tier is a promise about how often a line happens, so it is kept only where
our own scored results show it.

  Strong  90% or more AND similar lines in our track record happened that often
  Solid   80% or more AND the track record agrees
  Watch   60% or more, or anything the track record does not yet back

A Watch line always carries a note saying WHICH of those it is -- see _watch_says_why.

ONE RULE, ALWAYS (docs/76). There used to be a second: with `engine.personal_lines` on, every line
sits where the entity lands about half the time, so likelihood says the same thing about everybody,
and the badge graded the DEPARTURE from their usual game instead. That is defensible and it was
measured -- but it means "Strong" stops meaning "strong chance", and a reader who reads it that way
is right and the product is wrong. A 57% card reading Watch beside a 56% one reading Solid is what
that costs. The departure is still shown, in its own words, on its own line of the card; it is no
longer hidden inside a word that means something else.

THE TIER GRADES THE NUMBER ON THE CARD, AND NOTHING ELSE.

It used to grade `p x p_play` -- the chance he reaches the line times the chance he features -- while the card
showed `p`. Three things described one forecast and one of them measured something different, so a card could
read "94%" and "Watch" at the same time and be telling the truth twice. Worse, the lineup caps meant a player
under `likely_starter_p` could not be Strong or Solid WHATEVER his number was, and every feed admits Strong and
Solid only: measured 48 hours out, 206 visible player rows produced 3 Solid and 0 Strong, so the best players in
the league were absent from Today and Insights until about an hour before kick-off.

Whether he starts is a different question from how likely the line is if he plays, and the product already
answers it twice -- the lineup badge ("Confirmed starter", "Likely lineup", "Lineup not sure", "On the bench")
and the minutes row under the ten-game strip. Asking it a third time, inside the tier, only broke the tier.

This is also what the track record already measures: queries.track_record filters `player_played: True` and
reports the no-shows separately. So the number, the tier and the record now all describe the same thing -- the
chance the line is reached in a match he plays in. `p` itself already accounts for EXPECTED MINUTES, which is
why a substitute's ladder sits low without any help from the tier.

Whether he features at all is still a relevance question, and it is still answered: `engine.min_p_play` drops
the card of a player unlikely to feature, before any of this runs.

The track record is `forecast_outcomes`: for each scope and stat, how often lines with a similar chance happened
in matches the player played. It can only lower a tier, never raise one. Nothing here changes the percentage
shown, only the label.
"""
from __future__ import annotations

import numpy as np

import settings_store as S

RANK = {"Strong": 3, "Solid": 2, "Watch": 1, None: 0}


class Record:
    """Track record for one league run: sorted chances and cumulative hits per (scope, stat).

    Keyed on `p` over matches the player PLAYED, because that is what `p` claims and what the
    public track record reports (queries.track_record filters `player_played` and counts the
    no-shows separately). It used to key on `p x p_play` and score a no-show as a miss, which
    measured the unconditional chance -- a different quantity from the one on the card, and the
    reason a line could be demoted by a record that was never about it.
    """

    def __init__(self, db, window: float = 0.04, min_n: int = 40, k: float = 20.0):
        self.window, self.min_n, self.k = window, int(min_n), float(k)
        raw: dict = {}
        for o in db.forecast_outcomes.find({}, {"_id": 0, "scope": 1, "stat": 1, "p": 1, "player_played": 1, "reached": 1}):
            if o.get("p") is None or o.get("player_played") is False:
                continue
            raw.setdefault((o["scope"], o["stat"]), []).append((o["p"], 1 if o.get("reached") else 0))
        self.t = {}
        for key, rows in raw.items():
            rows.sort()
            self.t[key] = (np.array([r for r, _ in rows]), np.concatenate([[0], np.cumsum([y for _, y in rows])]))

    def earned(self, scope: str, stat: str, r: float):
        """(estimate, n) for lines with a chance near r, or (None, 0) when we hold nothing."""
        t = self.t.get((scope, stat))
        if t is None:
            return None, 0
        xs, cum = t
        w = self.window
        while w <= 0.16:
            lo, hi = np.searchsorted(xs, r - w, "left"), np.searchsorted(xs, r + w, "right")
            if hi - lo >= self.min_n:
                break
            w += 0.04
        n = int(hi - lo)
        if n == 0:
            return None, 0
        hits = float(cum[hi] - cum[lo])
        return (hits + self.k * r) / (n + self.k), n


def assign(db, rec: Record | None, f: dict) -> tuple[str | None, str | None]:
    """-> (tier, note). `f` carries p, lo, scope, stat, lineup_badge.

    Graded on `p`, the number the card shows. There is no lineup condition here any more: see the
    module docstring. `p_play` is still read elsewhere -- it decides whether the card exists at all
    (engine.min_p_play) and it sets the lineup badge -- but it no longer moves the label.
    """
    scope, badge = f["scope"], f.get("lineup_badge")
    p, lo = float(f["p"]), float(f["lo"])
    s_min, so_min = float(S.get(db, "engine.strong_min")), float(S.get(db, "engine.solid_min"))
    s_lo, so_lo = float(S.get(db, "engine.strong_lo_min")), float(S.get(db, "engine.solid_lo_min"))
    watch = float(S.get(db, "engine.watch_min"))
    t = "Strong" if (p >= s_min and lo >= s_lo) else "Solid" if (p >= so_min and lo >= so_lo) else "Watch" if p >= watch else None
    note = None
    if rec is not None and t in ("Strong", "Solid"):
        est, n = rec.earned(scope, f["stat"], p)
        if n < rec.min_n:
            if t == "Strong":
                # "finished matches" read as this player's matches, which are drawn on the card
                # right below the note -- ten of them. It never meant those: it means OUR OWN
                # settled forecasts, the sample the track record is measured on. Say that.
                t, note = "Solid", "Held at Solid until our record on these lines is measured"
        else:
            if t == "Strong" and est < s_min - 0.02:
                t, note = ("Solid" if est >= so_min - 0.02 else "Watch"), f"Similar lines happened {round(est * 100)}% of the time"
            if t == "Solid" and est < so_min - 0.02:
                t, note = "Watch", f"Similar lines happened {round(est * 100)}% of the time"
    return _watch_says_why(t, note, so_min)


# The words a reader sees, in one place (docs/75).
#
# They are the stored values today, and the map exists anyway: it is what makes a rename a one-line
# change instead of a hunt through three codebases. It was briefly used for one -- Well above usual
# / Above usual / Near usual, named for the axis the badge grades when `engine.personal_lines` is
# on -- and that was the wrong fix. "Strong" is a confidence word and a reader is RIGHT to read it
# as one; the answer is to grade the likelihood, which is what the engine does by default, not to
# rename the badge around a setting.
#
# Mirrored in the app by lib/copy.js and on the ad canvas by admin/ads/draw.js, which cannot import
# either. selftest_blog pins all three together so a rename cannot land in two of them.
TIER_LABEL = {"Strong": "Strong", "Solid": "Solid", "Watch": "Watch"}


def label(t: str | None) -> str:
    return TIER_LABEL.get(t or "", t or "")


def _watch_says_why(t: str | None, note: str | None, so_min: float) -> tuple[str | None, str | None]:
    """Watch is the one tier a reader cannot work out from the card.

    Strong and Solid are promises, and a card carrying one is self-explaining. Watch is the absence
    of a promise, and the number beside it does not say which absence: 73% with Watch reads as a
    contradiction unless the card says that 73 is under the 80 Solid asks for, or that the tier is
    held back by something other than the number -- the chance to play, the bench, our own record.
    Every one of those cases already produced a note. The plain one, which is most of them, produced
    nothing, so the commonest tier in the product was the only one that never explained itself.

    Reported by the owner, in those words: "I don't understand the concept of watch, why it has a
    high percentage but not solid".
    """
    if t == "Watch" and note is None:
        return t, f"Under {round(so_min * 100)}%, where Solid starts"
    return t, note



def _logit(x):
    x = min(max(x, 1e-4), 1 - 1e-4)
    return float(np.log(x / (1 - x)))


def _sig(z):
    return float(1 / (1 + np.exp(-z)))


def anchor_shift_rate(p, emp, n, K, w_max) -> float:
    """The log-odds shift toward a rate that is already computed, with `n` games of weight behind it.

    Split out so the record can be counted two ways and blended one way (docs/62): flat whole games,
    or the same games weighted by how recent they are, in which case `emp` is the weighted share and
    `n` is the EFFECTIVE sample size rather than a count of rows.
    """
    emp = min(max(float(emp), 1e-4), 1 - 1e-4)
    w = min(w_max, n / (n + K))
    return w * (_logit(emp) - _logit(p))


def anchor_shift(p, k, n, K, w_max) -> float:
    """The log-odds shift this player's own record implies for the model's chance `p`.

    Blend weight n/(n+K), never above w_max; the share is smoothed ((k+1)/(n+2)) so 40 of 40 is
    97.6%, not 100%.

    Returned on its own because the shift is a statement about the PLAYER, not about the fixture, so
    everything that describes the same player has to move by it together -- his chance tonight, the
    range around it, and the usual game it is compared against. Applying it to the first two and not
    the third is what made `edge` a mixture of a fixture effect and this correction (docs/61).
    """
    return anchor_shift_rate(p, (k + 1) / (n + 2), n, K, w_max)


def shift_one(v, d, cap):
    """One probability moved by a log-odds shift, held under `cap`."""
    return min(_sig(_logit(v) + d), cap)


def anchor(p, lo, hi, k, n, K, w_max, cap):
    """His own record counts. `p`, and the range around it, move by the shift above. Applies to
    "if he plays" player lines. The caller must move his usual game by the same shift."""
    d = anchor_shift(p, k, n, K, w_max)
    return shift_one(p, d, cap), shift_one(lo, d, cap), shift_one(hi, d, cap)
