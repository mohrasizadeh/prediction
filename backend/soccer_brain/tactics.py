"""tactics.py -- tactical style indices, named systems and formation shape.

Everything here is built from PAST games only. Nothing is hand-tuned to a result:
the indices only describe how a team plays; the regression in engine.py learns what
those styles do to each metric, and a feature stays only if it passes the walk-forward gate.

Inputs (columns of `team_game`, all optional; the layer turns itself off if they are missing):
  ppda            passes the opponent made in its own 60% of the pitch, per our defensive action there
  ada             average distance of our defensive actions from our own goal line (yards, 0-120)
  field_tilt      our share (0-100) of final-third passes
  poss            possession share (0-100)
  passes_per_seq  mean passes per possession that included a pass
  direct_speed    metres per second the ball travels toward goal in open-play possessions
  long_ball_pct   share (0-100) of our passes that travel 35 yards or more
  high_turnovers  possessions won within 40 yards of the opponent's goal
  n_def, n_mid, n_fwd   starters by position group (formation shape)

Why relative scores and not the fixed cut-offs in the guide (PPDA under 9, and so on):
providers define PPDA differently (which actions count, which zone). Our own count on the same
matches had a league median of 15, not 10 to 13. So every label below is a position inside the
league (a z-score), and the guide's absolute numbers are kept only as a reference table.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

TB_COLS = ["ppda", "ada", "field_tilt", "poss", "passes_per_seq", "direct_speed", "long_ball_pct", "high_turnovers"]
SHAPE_COLS = ["n_def", "n_mid", "n_fwd"]
INDEX_NAMES = ["press", "control", "speed", "longball"]

# Reference only: the guide's absolute criteria (provider-specific; do not use as cut-offs).
GUIDE_REFERENCE = {
    "high_press": {"ppda": "< 9.0", "ada": "45+ yards", "note": "high turnovers within 40 yards of goal"},
    "mid_block": {"ppda": "10.0 to 13.5", "ada": "35 to 45 yards", "note": "interceptions in the middle third"},
    "low_block": {"ppda": "> 14.0", "ada": "< 35 yards", "note": "many clearances and blocks, low field tilt"},
    "positional_play": {"passes_per_seq": "5.5+", "direct_speed": "< 1.5 m/s", "field_tilt": "> 60%"},
    "vertical_counter": {"direct_speed": "2.5+ m/s", "passes_per_seq": "< 3.5", "note": "shot within 10 to 12 s of winning the ball"},
    "long_ball": {"long_ball_pct": "15 to 20%+", "note": "high share of launches, many aerial duels"},
}

SYSTEM_WORDS = {
    "high_press": "a high press",
    "low_block": "a low block",
    "positional_play": "a possession-based game",
    "vertical": "fast vertical attacks",
    "long_ball": "a long-ball approach",
}
ARCHETYPE_WORDS = {
    "positional_control": "Positional control",
    "gegenpress_vertical": "Gegenpressing and vertical attack",
    "compact_counter": "Compact low block and counter-attack",
}


def available(team_game: pd.DataFrame, min_cover: float = 0.9) -> bool:
    """True when every tier-B column exists and at least `min_cover` of rows have a value."""
    if team_game is None or team_game.empty:
        return False
    for c in TB_COLS:
        if c not in team_game.columns or team_game[c].notna().mean() < min_cover:
            return False
    return True


def shape_available(team_game: pd.DataFrame, min_cover: float = 0.9) -> bool:
    if team_game is None or team_game.empty:
        return False
    return all(c in team_game.columns and team_game[c].notna().mean() >= min_cover for c in SHAPE_COLS)


def _transform(df: pd.DataFrame) -> np.ndarray:
    """Columns in a fixed order, each on a scale where 'more' means more of the thing."""
    cols = [
        np.log(np.clip(df["ppda"].astype(float), 1.0, 80.0)),            # 0 log PPDA (low = pressing)
        df["ada"].astype(float),                                          # 1
        df["field_tilt"].astype(float) / 100.0,                           # 2
        df["poss"].astype(float) / 100.0,                                 # 3
        np.log(np.clip(df["passes_per_seq"].astype(float), 1.0, 20.0)),   # 4
        np.log(np.clip(df["direct_speed"].astype(float), 0.3, 6.0)),      # 5
        np.log(np.clip(df["long_ball_pct"].astype(float), 1.0, 60.0)),    # 6
        np.log1p(df["high_turnovers"].astype(float)),                     # 7
    ]
    return np.column_stack([np.asarray(c, float) for c in cols])


def _z(m: np.ndarray, have: np.ndarray) -> np.ndarray:
    """z-score of each column across teams that have data. Columns with no spread give 0."""
    out = np.zeros_like(m)
    if have.sum() < 3:
        return out
    mu = m[have].mean(0)
    sd = m[have].std(0)
    ok = sd > 1e-9
    out[:, ok] = (m[:, ok] - mu[ok]) / sd[ok]
    out[~have] = 0.0
    return out


def indices_from_means(m: np.ndarray, have: np.ndarray) -> np.ndarray:
    """m: (teams x 8) shrunk means of the transformed columns. Returns (teams x 4) z-scale indices."""
    z = _z(m, have)
    press = 0.4 * (-z[:, 0]) + 0.4 * z[:, 1] + 0.2 * z[:, 7]
    control = (z[:, 2] + z[:, 4] + z[:, 3]) / 3.0
    speed = z[:, 5]
    longball = z[:, 6]
    return np.column_stack([press, control, speed, longball])


class StyleTracker:
    """Past-only snapshots of every team's tactical indices and formation shape.

    snapshots(team_game, teams, tidx, as_of) -> {round: (idx[T,4], shape[T,3] or None, have[T])}
    The snapshot stored for round r uses games from rounds BEFORE r.
    """

    def __init__(self, k: float = 6.0, use_shape: bool = True):
        self.k = k
        self.use_shape = use_shape

    def snapshots(self, tg: pd.DataFrame, teams: list, tidx: dict, as_of) -> dict:
        T = len(teams)
        tb = _transform(tg)
        has_shape = self.use_shape and shape_available(tg)
        sh = tg[SHAPE_COLS].astype(float).values if has_shape else None
        S = np.zeros((T, tb.shape[1])); N = np.zeros((T, tb.shape[1]))
        SS = np.zeros((T, 3)); NS = np.zeros((T, 3))
        tix = tg["team"].map(tidx).values
        rounds = tg["round"].values
        order = np.argsort(rounds, kind="stable")
        out = {}

        def snap(r):
            tot_n = N.sum(0)
            league = np.where(tot_n > 0, S.sum(0) / np.maximum(tot_n, 1), 0.0)
            m = (S + self.k * league) / (N + self.k)
            have = N.max(1) > 0
            idx = indices_from_means(m, have)
            if has_shape:
                tn = NS.sum(0)
                lg = np.where(tn > 0, SS.sum(0) / np.maximum(tn, 1), 0.0)
                ms = (SS + self.k * lg) / (NS + self.k)
                shape = _z(ms, have)
            else:
                shape = None
            out[r] = (idx, shape, have)

        i = 0
        n = len(order)
        while i < n:
            r = rounds[order[i]]
            snap(r)
            j = i
            while j < n and rounds[order[j]] == r:
                row = order[j]
                t = tix[row]
                v = tb[row]
                ok = ~np.isnan(v)
                S[t, ok] += v[ok]; N[t, ok] += 1.0
                if has_shape:
                    s = sh[row]; ok2 = ~np.isnan(s)
                    SS[t, ok2] += s[ok2]; NS[t, ok2] += 1.0
                j += 1
            i = j
        snap(as_of)
        return out


# ------------------------------------------------------------------ names for people
def named_systems(idx_row, thr: float = 1.0) -> list:
    """Labels from the guide, as positions inside the league. A team can have several."""
    press, control, speed, longball = (float(x) for x in idx_row)
    out = []
    if press >= thr:
        out.append("high_press")
    elif press <= -thr:
        out.append("low_block")
    if control >= thr:
        out.append("positional_play")
    if speed >= thr and control <= 0.5:
        out.append("vertical")
    if longball >= thr:
        out.append("long_ball")
    return out


def archetype(idx_row, thr: float = 0.5):
    """Which of the guide's three synthesis archetypes fits best, or None when none clearly does.
    Returns (key, score). Score is the sum of how far the team sits past the threshold on the defining traits."""
    press, control, speed, longball = (float(x) for x in idx_row)
    cands = {
        "positional_control": control if (control >= thr and press >= -0.5) else 0.0,
        "gegenpress_vertical": (press + speed) / 2 if (press >= thr and speed >= 0.0) else 0.0,
        "compact_counter": ((-press) + speed) / 2 if (press <= -thr and speed >= 0.0) else 0.0,
    }
    key = max(cands, key=cands.get)
    return (key, round(float(cands[key]), 3)) if cands[key] > 0 else (None, 0.0)


def percentile_rank(values: np.ndarray, x: float) -> float:
    v = np.asarray(values, float)
    v = v[~np.isnan(v)]
    return float(100.0 * (v < x).mean() + 50.0 * (v == x).mean()) if len(v) else 50.0


def shape_label(n_def: float, n_mid: float, n_fwd: float) -> str:
    """A readable shape from average starters by line. Example: 4-4-2 or 3-5-2. Goalkeeper excluded."""
    d, m, f = int(round(n_def)), int(round(n_mid)), int(round(n_fwd))
    tot = d + m + f
    while tot > 10 and m > 0:
        m -= 1; tot -= 1
    while tot < 10:
        m += 1; tot += 1
    return f"{d}-{m}-{f}"
