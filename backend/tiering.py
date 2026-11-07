"""tiering.py -- earned tiers (docs/31). A tier is a promise about how often a line happens, so it is kept only where
our own scored results show it.

  Strong  the whole chance is 90% or more AND similar lines in our track record happened that often
  Solid   the whole chance is 80% or more AND the track record agrees
  Watch   60% or more, or anything the track record does not yet back

A Watch line always carries a note saying WHICH of those it is -- see _watch_says_why.

The whole chance of a player line is p x chance to play (a line "if he plays" is not a promise until he plays).
The track record is `forecast_outcomes`: for each scope and stat, how often lines with a similar whole chance happened
(a player who did not feature counts as a miss when we stored his chance to play). It can only lower a tier, never raise one.
Strong also needs a confirmed eleven for a player (setting). Nothing here changes the percentage shown, only the label.
"""
from __future__ import annotations

import numpy as np

import settings_store as S

RANK = {"Strong": 3, "Solid": 2, "Watch": 1, None: 0}


def whole(p: float, p_play: float | None, scope: str, badge: str | None) -> float:
    if scope != "player" or badge == "confirmed" or p_play is None:
        return p
    return p * float(p_play)


class Record:
    """Track record for one league run: sorted whole chances and cumulative hits per (scope, stat)."""

    def __init__(self, db, window: float = 0.04, min_n: int = 40, k: float = 20.0):
        self.window, self.min_n, self.k = window, int(min_n), float(k)
        raw: dict = {}
        for o in db.forecast_outcomes.find({}, {"_id": 0, "scope": 1, "stat": 1, "p": 1, "p_play": 1, "lineup_badge": 1, "player_played": 1, "reached": 1}):
            if o.get("p") is None:
                continue
            played = o.get("player_played") is not False
            if o.get("p_play") is not None and o.get("scope") == "player" and o.get("lineup_badge") != "confirmed":
                r, y = o["p"] * o["p_play"], 1 if (o.get("reached") and played) else 0       # whole chance: not playing is a miss
            elif played:
                r, y = o["p"], 1 if o.get("reached") else 0                                    # older rows: counted when he played
            else:
                continue
            raw.setdefault((o["scope"], o["stat"]), []).append((r, y))
        self.t = {}
        for key, rows in raw.items():
            rows.sort()
            self.t[key] = (np.array([r for r, _ in rows]), np.concatenate([[0], np.cumsum([y for _, y in rows])]))

    def earned(self, scope: str, stat: str, r: float):
        """(estimate, n) for lines with a whole chance near r, or (None, 0) when we hold nothing."""
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


def assign(db, rec: Record | None, f: dict, strong_needs_lineup: bool = True) -> tuple[str | None, str | None]:
    """-> (tier, note). `f` carries p, lo, scope, stat, p_play, lineup_badge."""
    scope, badge = f["scope"], f.get("lineup_badge")
    w = whole(f["p"], f.get("p_play"), scope, badge)
    lw = whole(f["lo"], f.get("p_play"), scope, badge)
    s_min, so_min = float(S.get(db, "engine.strong_min")), float(S.get(db, "engine.solid_min"))
    s_lo, so_lo = float(S.get(db, "engine.strong_lo_min")), float(S.get(db, "engine.solid_lo_min"))
    watch = float(S.get(db, "engine.watch_min"))
    if badge == "bench":
        return ("Watch" if w >= watch else None), "On the bench: Watch only"
    if f.get("is_personal") and f.get("p_usual") is not None:
        t, note = _departure_tier(db, f, w, lw)
        return _watch_says_why(*_lineup_caveat(t, note, scope, badge, strong_needs_lineup), so_min)
    t = "Strong" if (w >= s_min and lw >= s_lo) else "Solid" if (w >= so_min and lw >= so_lo) else "Watch" if w >= watch else None
    note = None
    if badge == "unsure" and t in ("Strong", "Solid"):
        t, note = "Watch", "Watch until lineups are out"
    if t == "Strong" and scope == "player" and badge != "confirmed" and strong_needs_lineup:
        t, note = "Solid", "Strong once the lineup is confirmed"
    # A player line is tiered on the WHOLE chance -- "if he plays" times the chance he plays -- so a 97% line on a
    # likely starter is judged as 97 x 84 = 81%. That is why it reads Solid while the card says 97%, and nothing
    # said so: the note below only fired when the line reached Strong and was held back for the lineup. Say it
    # whenever the chance to play is the only thing between this tier and a better one (docs/48).
    if note is None and scope == "player" and badge != "confirmed" and f.get("p_play") is not None:
        would = "Strong" if (f["p"] >= s_min and f["lo"] >= s_lo) else "Solid" if (f["p"] >= so_min and f["lo"] >= so_lo) else None
        if would and would != t and (would == "Strong" or t != "Strong"):
            note = f"{would} once the lineup is confirmed"

    if rec is not None and t in ("Strong", "Solid"):
        est, n = rec.earned(scope, f["stat"], w)
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



def _departure_tier(db, f: dict, w: float, lw: float) -> tuple[str | None, str | None]:
    """Tiering for a line that is the entity's OWN half-way count (docs/52).

    The ordinary tiers answer "how likely is this". Once the line is set where the entity lands about
    half the time, that question has the same answer for everybody and tells the reader nothing: on
    the measured feed 84 of 90 personal lines fell below even Watch.

    The question worth grading is the one the line was built to ask: **is this fixture unlike their
    normal game, and how sure are we?** So:

      Strong  the likely range sits wholly on one side of what they usually do, and the gap is big
      Solid   the gap is big enough to be worth saying, but the range still touches their usual
      Watch   there is a gap, but a small one
      none    this fixture looks like any other for them -- which is honest, and not worth a card

    A departure below is as real as one above: "well short of his normal game" is a forecast.
    """
    pu = float(f["p_usual"])
    d = abs(float(f["p"]) - pu)
    big, some = float(S.get(db, "engine.departure_strong")), float(S.get(db, "engine.departure_solid"))
    clear = (float(f["lo"]) > pu) or (float(f["hi"]) < pu)       # the range does not straddle the usual
    if d >= big and clear:
        return "Strong", None
    if d >= some:
        return "Solid", (None if clear else "The likely range still reaches their usual")
    if d >= some / 2:
        # Not "under 80%": a personal line is graded on the SIZE OF THE GAP, not on the chance, so
        # the plain note would name a bar this line is not measured against.
        return "Watch", "A small step from their usual game"
    return None, None


def _lineup_caveat(t, note, scope, badge, strong_needs_lineup):
    """The lineup rules apply whatever the tier was worked out from."""
    if badge == "unsure" and t in ("Strong", "Solid"):
        return "Watch", "Watch until lineups are out"
    if t == "Strong" and scope == "player" and badge != "confirmed" and strong_needs_lineup:
        return "Solid", "Strong once the lineup is confirmed"
    return t, note


def _logit(x):
    x = min(max(x, 1e-4), 1 - 1e-4)
    return float(np.log(x / (1 - x)))


def _sig(z):
    return float(1 / (1 + np.exp(-z)))


def anchor(p, lo, hi, k, n, K, w_max, cap):
    """His own record counts. The model's chance and his hit rate over his last n games are blended on the log-odds scale:
    weight n/(n+K), never above w_max. The hit rate is smoothed ((k+1)/(n+2)) so 40 of 40 is 97.6%, not 100%.
    The range moves by the same amount. The result never goes above `cap`. Applies to "if he plays" player lines."""
    emp = (k + 1) / (n + 2)
    w = min(w_max, n / (n + K))
    d = w * (_logit(emp) - _logit(p))
    return min(_sig(_logit(p) + d), cap), min(_sig(_logit(lo) + d), cap), min(_sig(_logit(hi) + d), cap)
