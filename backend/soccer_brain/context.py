"""context.py -- competition importance, rest, fixture congestion and rotation.

The idea: a club does not field the same eleven in every game. A League Cup tie three days before a
Champions League night, a fifth match in two weeks, a dead rubber: these change WHO plays and for HOW
LONG. This module turns the club's whole calendar (every competition) into a few numbers per
team and match, and learns from past lineups what those numbers do to the chance a player starts.

What it does NOT do (and the evidence says why):
  * It does not shift a team's expected goals by hand. On 14 Premier League seasons, rest days and a
    European game soon after moved goals by less than the noise (see 18_brain_tactics_and_context.md).
    A team-level effect is a gated option (`team_effect`), off until real lineups show it.
  * It does not guess who will rest. The rotation model is learned from the club's own history of
    changes, and a forecast says "rotation risk" instead of claiming to know the eleven.

Inputs
  schedule   one row per club per match, in EVERY competition the club plays:
             team, kickoff (datetime), comp (key), stage (text), venue ("H"/"A"/"N", optional)
  importance a dict {comp_key: weight}; league match = 1.0. Editable in settings (`context.importance`).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

DEFAULT_IMPORTANCE = {
    "league": 1.00,
    "ucl": 0.95, "ucl_late": 1.15,
    "uel": 0.75, "uel_late": 0.90,
    "uecl": 0.60, "uecl_late": 0.75,
    "fa_cup": 0.55, "fa_cup_late": 0.80,
    "league_cup": 0.40, "league_cup_late": 0.75,
    "domestic_cup": 0.55, "domestic_cup_late": 0.80,
    "super_cup": 0.50,
    "friendly": 0.20,
    "other": 0.70,
}
LATE_WORDS = ("quarter", "semi", "final", "round of 16", "last 16", "knockout", "playoff", "play-off", "round 5", "fifth round")
EUROPE = ("ucl", "uel", "uecl")

# prior shape of the rotation-pressure parts (the model learns the weights; these only define the parts)
GAP_FULL, GAP_ZERO = 2.5, 5.5          # next match within 2.5 days = full pressure, beyond 5.5 days = none
CONGESTION_FREE = 3                    # matches in the last 14 days before pressure starts
SHORT_REST = 3.5                       # days


def importance_of(comp: str, stage: str = "", table: dict | None = None) -> float:
    table = table or DEFAULT_IMPORTANCE
    st = (stage or "").lower()
    late = any(w in st for w in LATE_WORDS)
    if late and (comp + "_late") in table:
        return float(table[comp + "_late"])
    return float(table.get(comp, table.get("other", 0.7)))


class Calendar:
    """Every match of every club, in every competition. Built once per run from the schedule feed."""

    def __init__(self, schedule: pd.DataFrame, table: dict | None = None):
        s = schedule.copy()
        s["kickoff"] = pd.to_datetime(s["kickoff"])
        if "stage" not in s.columns:
            s["stage"] = ""
        s["imp"] = [importance_of(c, st, table) for c, st in zip(s["comp"], s["stage"])]
        s = s.sort_values(["team", "kickoff"]).reset_index(drop=True)
        self.s = s
        self.by_team = {t: g.reset_index(drop=True) for t, g in s.groupby("team")}

    def context(self, team, kickoff, this_comp: str | None = None, this_stage: str = "", table: dict | None = None) -> dict:
        """Numbers describing the club's calendar around one match. Uses only matches that are on the
        calendar BEFORE kickoff for the past and the fixture list for the future (that is public)."""
        g = self.by_team.get(team)
        kickoff = pd.Timestamp(kickoff)
        this_imp = importance_of(this_comp, this_stage, table) if this_comp else 1.0
        base = dict(rest_days=14.0, next_gap=14.0, prev_imp=1.0, next_imp=0.0, n14=0, n_next7=0,
                    this_imp=this_imp, prev_comp="", next_comp="")
        if g is None or g.empty:
            return base
        k = g["kickoff"].values
        i = int(np.searchsorted(k, np.datetime64(kickoff), side="left"))      # first row at or after kickoff
        prev = g.iloc[i - 1] if i > 0 else None
        j = i + 1 if (i < len(g) and abs((g["kickoff"].iloc[i] - kickoff).total_seconds()) < 3600) else i
        nxt = g.iloc[j] if j < len(g) else None
        if prev is not None:
            base["rest_days"] = float(min((kickoff - prev["kickoff"]).total_seconds() / 86400.0, 14.0))
            base["prev_imp"] = float(prev["imp"]); base["prev_comp"] = prev["comp"]
        if nxt is not None:
            base["next_gap"] = float(min((nxt["kickoff"] - kickoff).total_seconds() / 86400.0, 14.0))
            base["next_imp"] = float(nxt["imp"]); base["next_comp"] = nxt["comp"]
        lo = np.datetime64(kickoff - pd.Timedelta(days=14)); hi = np.datetime64(kickoff + pd.Timedelta(days=7))
        base["n14"] = int(((k >= lo) & (k < np.datetime64(kickoff))).sum())
        base["n_next7"] = int(((k > np.datetime64(kickoff)) & (k <= hi)).sum())
        return base


def pressure_parts(c: dict) -> dict:
    """Four plain numbers between 0 and about 1. Each one is its own cause, so the model can weigh them apart.

    next_bigger   a more important match is close behind this one
    europe_soon   a European match is close behind this one (even when the weights call it equal to a league match)
    low_stakes    this match is itself a lesser competition
    congestion    many matches in the last 14 days
    short         the last match was 3.5 days ago or less
    """
    gapw = float(np.clip((GAP_ZERO - c["next_gap"]) / (GAP_ZERO - GAP_FULL), 0.0, 1.0))
    bigger = max(c["next_imp"] - c["this_imp"], 0.0)
    europe = float(c.get("next_comp", "") in EUROPE)
    return dict(next_bigger=bigger * gapw,
                europe_soon=europe * gapw,
                low_stakes=max(1.0 - c["this_imp"], 0.0),
                congestion=float(np.clip((c["n14"] - CONGESTION_FREE) / 3.0, 0.0, 1.0)),
                short=float(c["rest_days"] < SHORT_REST))


PRESSURE_WEIGHTS = {"next_bigger": 1.0, "europe_soon": 0.5, "low_stakes": 0.6, "congestion": 0.4, "short": 0.4}


def rotation_pressure(c: dict, w: dict | None = None) -> float:
    """One summary number for display ("rotation watch" level). The learned model does not use it."""
    w = w or PRESSURE_WEIGHTS
    p = pressure_parts(c)
    return float(np.clip(sum(w[k] * p[k] for k in p), 0.0, 1.5))


def pressure_level(r: float) -> str:
    return "high" if r >= 0.7 else ("medium" if r >= 0.35 else "low")


def context_frame(matches: pd.DataFrame, cal: Calendar, comp_of=None, table: dict | None = None) -> pd.DataFrame:
    """Context rows for every (match, side). `matches` needs game_id, kickoff, home, away.
    comp_of(game_id) -> (comp_key, stage); default is 'league'."""
    rows = []
    for m in matches.itertuples():
        comp, stage = comp_of(m.game_id) if comp_of else ("league", "")
        for team, opp in ((m.home, m.away), (m.away, m.home)):
            c = cal.context(team, m.kickoff, comp, stage, table)
            c.update(pressure_parts(c))
            c["pressure"] = rotation_pressure(c)
            c.update(game_id=m.game_id, team=team, opp=opp)
            rows.append(c)
    return pd.DataFrame(rows)


# ================================================================== who starts
class StartModel:
    """P(start | in the squad) = logistic( logit(usual start rate) + context terms ).

    Terms (all learned, ridge-shrunk toward zero):
        next_bigger, low_stakes, congestion, short   how much each kind of pressure rests a player
        each of them x regularity                    a regular starter is rested more than a fringe player
    `regularity` is the player's share of his club's recent starts (0 to 1), from past games only.
    A fringe player (low regularity) is expected to start MORE under pressure, a regular LESS. The
    sum over a club's players is rescaled to 11 so the model cannot invent or lose starters.
    """

    PARTS = ["next_bigger", "europe_soon", "low_stakes", "congestion", "short"]

    def __init__(self, l2: float = 8.0):
        self.l2 = l2
        self.w = None
        self.names = None

    @staticmethod
    def _logit(p):
        p = np.clip(p, 0.02, 0.98)
        return np.log(p / (1 - p))

    def design(self, parts: pd.DataFrame, reg: np.ndarray) -> np.ndarray:
        cols = []; names = []
        c_reg = (reg - 0.5)
        for k in self.PARTS:
            v = parts[k].values.astype(float)
            cols += [v, v * c_reg]; names += [k, k + "*regular"]
        self.names = names
        return np.column_stack(cols)

    def fit(self, rows: pd.DataFrame):
        """rows: one row per player-match, columns: started (0/1), prior (usual start rate, past only),
        regular (0-1), next_bigger, low_stakes, congestion, short (0/1)."""
        from scipy.optimize import minimize
        X = self.design(rows, rows["regular"].values)
        y = rows["started"].values.astype(float)
        off = self._logit(rows["prior"].values.astype(float))

        def f(b):
            eta = off + X @ b
            p = 1.0 / (1.0 + np.exp(-eta))
            ll = np.sum(y * eta - np.logaddexp(0, eta))
            return -ll + 0.5 * self.l2 * np.sum(b ** 2), -(X.T @ (y - p)) + self.l2 * b

        res = minimize(f, np.zeros(X.shape[1]), jac=True, method="L-BFGS-B")
        self.w = res.x
        return self

    def predict(self, prior: np.ndarray, regular: np.ndarray, parts: dict) -> np.ndarray:
        """Adjusted start probabilities for one club's squad. Scaled so they sum to 11 when possible."""
        if self.w is None:
            return np.asarray(prior, float)
        df = pd.DataFrame({k: [parts[k]] * len(prior) for k in self.PARTS})
        X = self.design(df, np.asarray(regular, float))
        eta = self._logit(np.asarray(prior, float)) + X @ self.w
        p = 1.0 / (1.0 + np.exp(-eta))
        return p

    def coefficients(self) -> dict:
        return dict(zip(self.names, [float(x) for x in self.w])) if self.w is not None else {}


def prior_and_regularity(pg: pd.DataFrame, half_life: float = 8.0, prior0: float = 0.35) -> pd.DataFrame:
    """For every player-match row: usual start rate and regularity, from that club's PREVIOUS matches only.

    pg needs: round, team, player, started. One row per player in the matchday squad (unused substitutes
    included, with started = 0).
    prior    recency-weighted share of the player's earlier squad appearances that were starts
             (a new player gets `prior0`).
    regular  share of the club's last 10 matches in which he started (an absence counts as no).
    """
    pg = pg.sort_values(["team", "round"]).reset_index(drop=True)
    prior = np.full(len(pg), prior0); reg = np.zeros(len(pg))
    for team, g in pg.groupby("team", sort=False):
        hist, last_sets = {}, []
        for r in g["round"].unique():
            gr = g[g["round"] == r]
            recent = last_sets[-10:]
            for i, p in zip(gr.index, gr["player"]):
                h = hist.get(p)
                if h:
                    h = np.asarray(h, float)
                    w = 0.5 ** (np.arange(len(h))[::-1] / half_life)
                    prior[i] = (w @ h + prior0) / (w.sum() + 1.0)
                if recent:
                    reg[i] = sum(p in S for S in recent) / len(recent)
            for p, st in zip(gr["player"], gr["started"]):
                hist.setdefault(p, []).append(float(st))
            last_sets.append(set(gr.loc[gr["started"] == 1, "player"]))
    pg["prior"] = prior
    pg["regular"] = reg
    return pg
