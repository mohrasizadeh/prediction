"""engine.py -- the soccer brain.

Pipeline for one fixture, using only data from before kickoff:

  1. Team strength (Dixon-Coles) -> expected goals, win/draw/loss.
  2. Style vectors per team, rebuilt from past games only. Named tactics
     (low block, high press, possession-based) are read from the vectors.
  3. Team-total models (negative binomial regression) for shots, shots on
     target, corners, tackles. Starts from a simple baseline, then adds
     small corrections: venue, game state, style, style-by-style matchups.
  4. Lineup layer: how much each player's presence in the starting XI moves
     the team's own output and the opponent's output (ridge regression, a
     "regularised adjusted plus-minus"). Applied to the EXPECTED lineups
     of both teams, so a missing star defender or a rotated attack shows up.
  5. Player layer: each player's shrunk share of the team total, times a
     minutes scenario mixture, normalised to the team total.
  6. Probabilities with credible intervals, and reasons that name the
     opponent's tactic and personnel when they matter.

Optional layers (each OFF by default; each must pass the walk-forward gate before it is switched on):
  * tactics   tactical style indices from tier-B data (press, control, speed, long ball) and their
              matchups. See tactics.py.
  * shape     formation shape (starters by line) of both sides.
  * extra_stats  more team metrics (fouls, yellow cards, ...). Same machinery, no new code per metric.
  * context   competition importance, rest and rotation. See context.py.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import numpy as np
import pandas as pd

from core import (recency_weights, shrunk_rate, nb_sf, top_reasons, STAT_WORDS)
from nbglm import NBGLM
from strength import DixonColes
import tactics as TX
import context as CX

STATS = ["shots", "sot", "corners", "tackles"]
PLAYER_STATS = ["shots", "sot", "tackles"]
PLAYER_THR = {"shots": [0.5, 1.5], "sot": [0.5], "tackles": [1.5, 2.5]}
TEAM_THR = {"corners": [4.5], "shots": [11.5]}

SUM_COLS = ["shots", "shots_against", "corners", "corners_against",
            "tackles", "tackles_against", "poss", "sot"]       # the core 8; extra metrics are appended after these
OWN_I = [0, 2, 6, 4]   # shots_for, corners_for, poss, tackles_for
OPP_I = [1, 3, 6, 5]   # shots_against, corners_against, poss, tackles_against
TEAM_DIMS = {"shots": (0, 1), "corners": (2, 3), "tackles": (4, 5)}

DEFAULT_R_PLAYER = {"shots": 6.0, "sot": 5.0, "tackles": 10.0}
# Prior strength of a player's share of his team's total, in team-stat units (docs/25: tackles 80 beat 40, z +5.1;
# shots and on target are best at 40).
DEFAULT_PLAYER_PRIOR = {"shots": 40.0, "sot": 40.0, "tackles": 40.0}

# Thresholds offered for extra team metrics (editable in settings like the others).
EXTRA_THR = {"fouls": [11.5], "yellow": [1.5]}

TACTIC_WORDS = {"low_block": "a low block",
                "high_press": "a high press",
                "possession": "a possession-based game",
                "positional_play": "a possession-based game",
                "vertical": "fast vertical attacks",
                "long_ball": "a long-ball approach"}


@dataclass
class Forecast:
    scope: str                 # "player" or "team"
    team: int
    opp: int
    stat: str
    thr: float
    expected: float
    p: float
    lo: float
    hi: float
    player: int | None = None
    pos: str | None = None
    p_play: float = 1.0
    confirmed: bool = False
    contrib: dict = field(default_factory=dict)
    reasons: list = field(default_factory=list)
    opp_tactics: list = field(default_factory=list)
    own_tactics: list = field(default_factory=list)
    opp_key_players: list = field(default_factory=list)   # [(player, effect on stat)]
    p_raw: float | None = None
    p_base: float | None = None
    rotation: str = "low"          # "low" | "medium" | "high": how likely the club rests regulars (calendar)
    rotation_why: str = ""         # one plain sentence, empty when low
    p_play_usual: float | None = None   # chance he plays with no calendar pressure (shows the shift)
    p_usual: float | None = None        # the same line from his/the team's own normalised average, before this opponent
                                        # and match (docs/25). The feed ranks by p - p_usual.


# Availability (docs/22). A player who has not featured in his club's last matches is often injured, suspended or
# dropped. Fitted on StatsBomb 2015/16 (Premier League, Serie A, Ligue 1), history = games he featured in, exactly
# what the live feed gives: logit P = c0 + c1 * logit(usual start rate) + c2*[missed >= 1] + c3*[>= 2] + c4*[>= 3] + c5*[>= 4].
# Held-out gain in log loss per player-game: starts +0.138 (z +38), plays +0.165 (z +41), every league.
ABSENCE_START = (-0.107, 0.719, -1.238, -0.791, -0.356, -1.065)
ABSENCE_PLAY = (1.043, 0.288, -1.219, -0.642, -0.363, -1.036)


# Match context on expected goals (docs/22). Poisson coefficients on top of team strength, fitted walk-forward on
# 46,000 English league matches (Premier League, Championship, League One, League Two, 2008-09 to 2024-25).
#   fp:   points in the last 5 league games minus the points the model expected (results form)
#   dead: late in the season with nothing left to play for; rel: in a relegation fight; race: in the title/top race
# "own" = the scoring side, "opp" = the other side. Held-out gain: score z +3.5, result z +3.9 (pooled);
# three leagues better, the Premier League neutral.
MATCH_CONTEXT_COEF = {"fp_own": 0.0221, "fp_opp": -0.0266, "dead_own": 0.0335, "dead_opp": 0.0996,
                      "rel_own": 0.0093, "rel_opp": -0.0292, "race_own": 0.0289, "race_opp": -0.0339}


def context_multipliers(ch: dict, ca: dict, coef=MATCH_CONTEXT_COEF):
    """(mult_home_goals, mult_away_goals) from the two clubs' context dicts {fp, dead, rel, race}."""
    def eta(own, opp):
        return sum(coef[f"{k}_own"] * float(own.get(k, 0) or 0) + coef[f"{k}_opp"] * float(opp.get(k, 0) or 0) for k in ("fp", "dead", "rel", "race"))
    return float(np.exp(eta(ch or {}, ca or {}))), float(np.exp(eta(ca or {}, ch or {})))


def _logit(p):
    p = min(max(p, 1e-4), 1 - 1e-4)
    return float(np.log(p / (1 - p)))


def _avail(coef, ps, missed):
    z = coef[0] + coef[1] * _logit(ps) + sum(c for c, k in zip(coef[2:], (1, 2, 3, 4)) if missed >= k)
    return float(1.0 / (1.0 + np.exp(-z)))


class SoccerEngine:
    def __init__(self, interactions=True, lineup=False, half_life_rounds=20.0,
                 style_k=6.0, min_round=3, n_draws=60, sigma_team=0.07,
                 lineup_l2=10.0, seed=0, tactics=False, tactic_interactions=True, shape=False,
                 extra_stats=(), match_features=(), strength_decay=0.02,
                 style_half_life=None, style_opp_adjust=(), style_cap_q=None, player_prior=None):
        self.interactions = interactions
        # Normalised team averages (docs/25). None / () = the old plain running sums.
        self.style_half = style_half_life            # a team's game this many games ago counts half
        self.style_opp = tuple(style_opp_adjust)     # stats judged against what each opponent usually allows / makes
        self.style_cap_q = style_cap_q               # each game's count capped at this league quantile before averaging
        self.player_prior = dict(DEFAULT_PLAYER_PRIOR, **(player_prior or {}))   # prior games for a player's share
        self.strength_decay = strength_decay           # Dixon-Coles time decay per match date (docs/22: how much recent form counts)
        self.lineup = lineup
        self.tactics_req = tactics                  # requested; becomes active only if tier-B columns exist
        self.tactic_interactions = tactic_interactions
        self.shape_req = shape
        self.tx_on = False
        self.shape_on = False
        self.mf = tuple(match_features)             # ((column, group), ...) known at lineup time; see _feat
        self.extra = tuple(extra_stats)
        self.stats = list(STATS) + [s for s in self.extra if s not in STATS]
        self.sum_cols = list(SUM_COLS)
        self.team_dims = dict(TEAM_DIMS)
        for j, st_ in enumerate(s for s in self.extra if s not in STATS):
            self.sum_cols += [st_, st_ + "_against"]
            self.team_dims[st_] = (8 + 2 * j, 9 + 2 * j)
            TEAM_THR.setdefault(st_, list(EXTRA_THR.get(st_, [])))
        self.lineup_l2 = lineup_l2
        self.hl = half_life_rounds
        self.k = style_k
        self.min_round = min_round
        self.n_draws = n_draws
        self.sigma_team = sigma_team
        self.rng = np.random.default_rng(seed)
        self.r_player = dict(DEFAULT_R_PLAYER)
        self.absence = True                         # availability model (missed recent matches); docs/22
        self.match_context = True                   # results form and stakes on expected goals; docs/22
        self.start_model = None                     # context.StartModel, set by set_start_model()
        self.start_on = False                       # applied only when its walk-forward gate passed

    def set_start_model(self, model, enabled: bool = True):
        """Attach a fitted context.StartModel. `enabled` is the stored gate result: when False the
        model is kept (so the page can still show the rotation chip) but start odds are not changed."""
        self.start_model = model
        self.start_on = bool(enabled and model is not None and model.w is not None)
        return self

    # ------------------------------------------------------------ styles
    def _snap(self, S, n, gd):
        T = len(n)
        if n.sum() == 0:
            return np.zeros((T, S.shape[1])), np.zeros(T)
        league = S.sum(0) / n.sum()
        m = (S + self.k * league) / (n[:, None] + self.k)
        st = np.log(np.maximum(m, 1e-9) / np.maximum(league, 1e-9))
        sot_rate = m[:, 7] / np.maximum(m[:, 0], 1e-9)
        st[:, 7] = np.log(np.maximum(sot_rate, 1e-9) / (league[7] / max(league[0], 1e-9)))
        return st, gd / (n + 6.0)

    def _opp_pairs(self):
        """column -> the opponent's style column it is judged against (docs/25). A team's shots are divided by how
        many shots its opponent usually concedes; its shots conceded by how many its opponent usually takes."""
        pairs = {}
        for s_, (i_for, i_ag) in self.team_dims.items():
            if s_ in self.style_opp:
                pairs[i_for] = i_ag
                pairs[i_ag] = i_for
        return pairs

    def _snapshots(self, tg, as_of):
        """Style snapshot before every round. Normalised (docs/25) when set:
        * recency: before a team's new game is added, its earlier games are discounted (half-life in games);
        * opponent: each game is judged against what that opponent usually allows (or makes), from the snapshot
          before the game, so 22 shots against the league's leakiest defence count for less;
        * cap: each count is capped at a high league quantile, a guard against freak games and feed errors.
        The league mean stays the plain average of all games, as before."""
        T = len(self.teams)
        D = len(self.sum_cols)
        S = np.zeros((T, D)); n = np.zeros(T); gd = np.zeros(T)
        S0 = np.zeros(D); n0 = 0.0                       # plain league totals
        g_dec = 0.5 ** (1.0 / self.style_half) if self.style_half else 1.0
        pairs = self._opp_pairs()
        seen = []
        caps = None
        poss_i = self.sum_cols.index("poss") if "poss" in self.sum_cols else -1
        snaps = {}
        for r, g in tg.groupby("round"):
            snaps[r] = self._snap(S, n, gd)
            ti = g["team"].map(self.tidx).values
            oi = g["opp"].map(self.tidx).values
            X = g[self.sum_cols].values.astype(float)
            S0 += X.sum(0); n0 += len(X)
            Xa = X.copy()
            if self.style_cap_q:
                seen.append(X)
                if caps is None or len(seen) % 10 == 0:
                    allx = np.concatenate(seen[-200:])
                    caps = np.quantile(allx, self.style_cap_q, axis=0) if len(allx) >= 100 else None
                if caps is not None:
                    c = caps.copy()
                    if poss_i >= 0:
                        c[poss_i] = np.inf
                    Xa = np.minimum(Xa, c)
            if pairs:
                st = snaps[r][0]
                for j, pj in pairs.items():
                    rel = np.exp(np.clip(st[oi, pj], -0.7, 0.7))          # opponent at most 2x / 0.5x the league
                    Xa[:, j] = Xa[:, j] / rel
                    if j == 0 and len(self.sum_cols) > 7:
                        Xa[:, 7] = Xa[:, 7] / rel                         # shots on target move with shots (keeps the rate)
            if g_dec < 1.0:
                u = np.unique(ti)
                S[u] *= g_dec; n[u] *= g_dec; gd[u] *= g_dec
            np.add.at(S, ti, Xa)
            np.add.at(n, ti, 1.0)
            np.add.at(gd, ti, (g["goals"] - g["goals_against"]).values.astype(float))
        snaps[as_of] = self._snap(S, n, gd)
        self.league_mean = {s: float(S0[i] / max(n0, 1)) for s, i in
                            (("shots", 0), ("corners", 2), ("tackles", 4), ("sot", 7))}
        for s_, (i_, _) in self.team_dims.items():
            if s_ not in self.league_mean:
                self.league_mean[s_] = float(S0[i_] / max(n0, 1))
        return snaps

    def _offset(self, stat, X, Y, snap):
        """Simple baseline in log space: league mean x team's output x
        opponent's concession. The regression only learns corrections."""
        st = snap[0]
        dfor, dag = self.team_dims.get(stat, (0, 1))
        off = np.log(max(self.league_mean[stat], 1e-6)) + st[X, dfor] + st[Y, dag]
        if stat == "sot":
            off += st[X, 7]
        return float(off)

    def _offset_groups(self, stat, X, Y, snap):
        st = snap[0]
        dfor, dag = self.team_dims.get(stat, (0, 1))
        own = float(st[X, dfor] + (st[X, 7] if stat == "sot" else 0.0))
        return {"own_style": own, "opponent": float(st[Y, dag])}

    # ------------------------------------------------------------ tactics
    def tactic_labels(self, snap):
        """Named tactics from the style vectors. A team gets a label when it
        sits at least one standard deviation above the league on that index."""
        st = snap[0]
        idx = {"low_block": -st[:, 1] + 0.5 * st[:, 3] - 0.5 * st[:, 6],
               "high_press": st[:, 4],
               "possession": st[:, 6]}
        out = {}
        for name, v in idx.items():
            sd = v.std()
            z = (v - v.mean()) / sd if sd > 1e-9 else np.zeros_like(v)
            out[name] = z
        return out

    def _team_tactics(self, snap, X, tx=None):
        if tx is not None:                                   # tier-B: positions inside the league
            return TX.named_systems(tx[0][X])
        z = self.tactic_labels(snap)
        return [name for name, arr in z.items() if arr[X] >= 1.0]

    # ----------------------------------------------------------- features
    def _feat(self, X, Y, home, snap, tx=None, xf=None):
        st, rt = snap[0], snap[1]
        sx, sy = st[X], st[Y]
        parts = [sx, sy]
        if self.interactions:
            parts.append(np.outer(sx[OWN_I], sy[OPP_I]).ravel())
        parts.append([float(home), rt[X] - rt[Y]])
        if tx is not None:
            ix, iy = tx[0][X], tx[0][Y]
            parts.append(ix); parts.append(iy)
            if self.tactic_interactions:
                parts.append(np.outer(ix, iy).ravel())
            if self.shape_on and tx[1] is not None:
                parts.append(tx[1][X][[0, 2]]); parts.append(tx[1][Y][[0, 2]])   # defenders, forwards
        if self.mf:
            parts.append(xf[0]); parts.append(xf[1])
        return np.concatenate(parts)

    def _groups(self):
        D = len(self.sum_cols)
        g = ["own_style"] * D + ["opponent"] * D
        l2 = [3.0] * (2 * D)       # relative ridge strengths (see nbglm.py)
        if self.interactions:
            g += ["style"] * 16
            l2 += [10.0] * 16
        g += ["venue", "game_script"]
        l2 += [0.2, 1.0]
        if self.tx_on:
            k = len(TX.INDEX_NAMES)
            g += ["own_tactic"] * k + ["opp_tactic"] * k
            l2 += [3.0] * (2 * k)
            if self.tactic_interactions:
                g += ["tactic_matchup"] * (k * k)
                l2 += [10.0] * (k * k)
            if self.shape_on:
                g += ["own_shape"] * 2 + ["opp_shape"] * 2
                l2 += [5.0] * 4
        if self.mf:
            g += ["own_" + grp for _, grp in self.mf] + ["opp_" + grp for _, grp in self.mf]
            l2 += [3.0] * (2 * len(self.mf))
        return np.array(g), np.array(l2)

    # --------------------------------------------------------------- fit
    def fit(self, matches, tg, pg, as_of):
        self.as_of = as_of
        matches = matches[matches["round"] < as_of]
        tg = tg[tg["round"] < as_of].copy().reset_index(drop=True)
        pg = pg[pg["round"] < as_of].copy()
        self.teams = sorted(set(tg["team"]) | set(tg["opp"]))
        self.tidx = {t: i for i, t in enumerate(self.teams)}
        self.snaps = self._snapshots(tg, as_of)
        self.tx_snaps = None
        self.tx_on = bool(self.tactics_req and TX.available(tg))
        self.shape_on = bool(self.tx_on and self.shape_req and TX.shape_available(tg))
        if self.tx_on:
            self.tx_snaps = TX.StyleTracker(self.k, use_shape=self.shape_on).snapshots(tg, self.teams, self.tidx, as_of)
        self.groups, l2 = self._groups()
        self._fit_match_features(tg)

        # team-total models
        rows = tg[tg["round"] >= self.min_round]
        Xs = np.array([self._feat(self.tidx[r.team], self.tidx[r.opp], r.home, self.snaps[r.round],
                                  self.tx_snaps[r.round] if self.tx_on else None,
                                  self._xf_row(r.game_id, r.team, r.opp))
                       for r in rows.itertuples()])
        w = 0.5 ** ((as_of - 1 - rows["round"].values) / self.hl)
        self.glm = {}
        offs = {}
        for s in self.stats:
            offs[s] = np.array([self._offset(s, self.tidx[r.team], self.tidx[r.opp], self.snaps[r.round])
                                for r in rows.itertuples()])
            self.glm[s] = NBGLM(l2=l2).fit(Xs, rows[s].values.astype(float), w, offset=offs[s])

        # team strength
        self.dc = DixonColes(xi=self.strength_decay).fit(matches["home"], matches["away"], matches["hg"],
                                   matches["ag"], as_of - 1 - matches["round"].values)

        # team histories for baselines
        self.tg_hist = {t: g.sort_values("round") for t, g in tg.groupby("team")}

        # player layer
        pgp = pg[pg["minutes"] > 0]
        self.rho = {}
        self.rho90 = {}
        for s in PLAYER_STATS:
            E = pgp["team_" + s] * pgp["minutes"] / 90.0
            self.rho[s] = (pgp.groupby("pos")[s].sum() / E.groupby(pgp["pos"]).sum()).to_dict()
            self.rho90[s] = (pgp.groupby("pos")[s].sum()
                             / (pgp["minutes"] / 90.0).groupby(pgp["pos"]).sum()).to_dict()
        self.pl = {}
        for pid, g in pg.groupby("player"):
            g = g.sort_values("round")
            self.pl[pid] = dict(team=int(g["team"].iloc[-1]), pos=g["pos"].iloc[-1], g=g, pid=pid)
        # club matches in order, and for each player how many of his club's latest matches he has missed
        team_games = {t: list(g.sort_values("round")["game_id"]) for t, g in tg.groupby("team")}
        for pid, info in self.pl.items():
            tgl = team_games.get(info["team"], [])
            mine = set(info["g"].loc[info["g"]["team"] == info["team"], "game_id"])
            missed = 0
            for gid in reversed(tgl):
                if gid in mine:
                    break
                missed += 1
            info["missed"] = missed
        self.squads = {}
        for pid, info in self.pl.items():
            self.squads.setdefault(info["team"], {})[pid] = info

        if self.lineup:
            self._fit_lineup(rows, pg, w, offs, Xs)
        return self

    # ------------------------------------------------- match-specific features
    def _fit_match_features(self, tg):
        """Columns of team_game that are known once the lineup is out (formation shape, how first-choice
        the eleven is, rotation pressure from the calendar). Each team's recent average is the default
        used before the lineup is known."""
        self._mf_tab, self.mf_default, self.mf_mean = {}, {}, np.zeros(len(self.mf))
        if not self.mf:
            return
        cols = [c for c, _ in self.mf]
        v = tg[cols].astype(float)
        self.mf_mean = np.nan_to_num(v.mean().values, nan=0.0)
        vv = np.where(np.isnan(v.values), self.mf_mean, v.values)
        for gid, team, row in zip(tg["game_id"].values, tg["team"].values, vv):
            self._mf_tab[(gid, team)] = row
        for t, g in tg.sort_values("round").groupby("team"):
            idx = g.index
            last = vv[tg.index.get_indexer(idx)][-10:]
            self.mf_default[t] = last.mean(0)

    def _xf_row(self, gid, team, opp):
        if not self.mf:
            return None
        return self._mf_tab[(gid, team)], self._mf_tab[(gid, opp)]

    def _xf_pair(self, team, opp, xf):
        """Vectors for one fixture side. `xf` = {team: {column: value}} overrides the defaults."""
        if not self.mf:
            return None
        out = []
        for t in (team, opp):
            vec = np.array(self.mf_default.get(t, self.mf_mean), float).copy()
            for k, (c, _) in enumerate(self.mf):
                if xf and t in xf and c in xf[t] and xf[t][c] is not None and not np.isnan(float(xf[t][c])):
                    vec[k] = float(xf[t][c])
            out.append(vec)
        return out[0], out[1]

    # ----------------------------------------------------- lineup effects
    def _fit_lineup(self, rows, pg, w, offs, Xs):
        """Ridge regression of each team-game's residual on WHO started, for
        both teams. The residual is what the style baseline and regression
        could not explain. Columns: own starters, then opponent starters.
        Each column is centred within the team's own games, so coefficients
        measure presence versus the usual lineup."""
        pids = sorted(self.pl)
        self.pidx = {p: i for i, p in enumerate(pids)}
        P = len(pids)
        starters = pg[pg["started"] == 1].groupby(["game_id", "team"])["player"].apply(list).to_dict()
        team_of = {p: self.pl[p]["team"] for p in pids}
        N = len(rows)
        A = np.zeros((N, 2 * P))
        rt = rows["team"].values; ro = rows["opp"].values
        for n, r in enumerate(rows.itertuples()):
            for p in starters.get((r.game_id, r.team), []):
                A[n, self.pidx[p]] = 1.0
            for p in starters.get((r.game_id, r.opp), []):
                A[n, P + self.pidx[p]] = 1.0
        Ac = np.zeros_like(A)
        self.start_rate = {}
        for p in pids:
            i = self.pidx[p]; t = team_of[p]
            m_own = rt == t
            if m_own.any():
                mu_own = np.average(A[m_own, i], weights=w[m_own])
                Ac[m_own, i] = A[m_own, i] - mu_own
                self.start_rate[p] = float(mu_own)
            else:
                self.start_rate[p] = 0.5
            m_opp = ro == t
            if m_opp.any():
                Ac[m_opp, P + i] = A[m_opp, P + i] - np.average(A[m_opp, P + i], weights=w[m_opp])
        self.lu = {}
        M0 = Ac.T @ (w[:, None] * Ac) + self.lineup_l2 * np.eye(2 * P)
        for s in self.stats:
            y = rows[s].values.astype(float)
            mu = self.glm[s].predict_mu(Xs, offs[s])
            z = np.log((y + 1.0) / (mu + 1.0))
            z = z - np.average(z, weights=w)
            coef = np.linalg.solve(M0, Ac.T @ (w * z))
            self.lu[s] = (coef[:P], coef[P:])

    def _lineup_adj(self, s, team, opp, scen):
        """Effect (log scale) of the expected lineups on team's `s`.
        own: team's attackers. opp: opponent's defenders."""
        if not self.lineup or s not in self.lu:
            return 0.0, 0.0, []
        own = 0.0
        for pid in self.squads.get(team, {}):
            own += self.lu[s][0][self.pidx[pid]] * (scen[pid][3] - self.start_rate[pid])
        oth = 0.0
        key = []
        for pid in self.squads.get(opp, {}):
            c = self.lu[s][1][self.pidx[pid]]
            oth += c * (scen[pid][3] - self.start_rate[pid])
            if scen[pid][3] >= 0.5:
                key.append((int(pid), float(c)))
        key.sort(key=lambda kv: kv[1])          # most negative = best suppressor
        return float(np.clip(own, -0.25, 0.25)), float(np.clip(oth, -0.25, 0.25)), key[:2]

    # ----------------------------------------------------------- minutes
    def _scenarios(self, info, confirmed_set, ps_override=None):
        g = info["g"]
        m = g["minutes"].values; st = g["started"].values.astype(float)
        w = recency_weights(len(g), 12.0)
        ps = (np.sum(w * st) + 1.0) / (np.sum(w) + 2.0)
        sel = st == 1
        m_start = np.average(m[sel], weights=w[sel]) if sel.sum() else 75.0
        ns = ~sel
        sub_flag = ns & (m > 0)
        p_sub = (np.sum(w[sub_flag]) + 0.5) / (np.sum(w[ns]) + 1.5)
        m_sub = np.average(m[sub_flag], weights=w[sub_flag]) if sub_flag.sum() else 20.0
        p_play = None
        if confirmed_set is None and self.absence:
            base = ps
            ps_a = _avail(ABSENCE_START, base, info.get("missed", 0))
            p_play = max(ps_a, _avail(ABSENCE_PLAY, base, info.get("missed", 0)))
            if ps_override is not None:                    # calendar start model moves the usual rate; keep its relative change
                new = min(0.98, ps_a * float(ps_override) / max(base, 1e-3))
                p_play = min(1.0, max(new, p_play - ps_a + new))      # fewer starts -> fewer appearances; the bench chance stays
                ps_a = new
            ps = ps_a
            p_sub = min(1.0, max(0.0, (p_play - ps) / (1 - ps))) if ps < 1 else 0.0
        if confirmed_set is not None:
            ps = 1.0 if info["pid"] in confirmed_set else 0.0
        elif ps_override is not None and p_play is None:
            ps = float(ps_override)
        if info.get("unavailable") and confirmed_set is None:   # injured or suspended (feed or admin); a confirmed eleven wins
            return [], 0.0, 0.0, 0.0
        if info.get("doubtful") and confirmed_set is None:
            ps *= 0.5; p_sub *= 0.5
        scen = []
        if ps > 0:
            scen.append((ps, float(m_start)))
        if ps < 1:
            scen.append(((1 - ps) * p_sub, float(m_sub)))
        Em = sum(p * mm for p, mm in scen)
        return scen, Em, sum(p for p, _ in scen), float(ps)

    def usual_start_rate(self, info):
        g = info["g"]
        st = g["started"].values.astype(float)
        w = recency_weights(len(g), 12.0)
        return float((np.sum(w * st) + 1.0) / (np.sum(w) + 2.0))

    def _rotated_starts(self, team, parts):
        """Start chance for each squad player under the calendar pressure in `parts`, from the fitted
        StartModel. The club's total expected starters is kept as it was, so the model moves WHO plays,
        not how many."""
        squad = self.squads.get(team, {})
        pids = list(squad)
        base = np.array([self.usual_start_rate(squad[p]) for p in pids])
        if not (self.start_on and parts and len(pids)):
            return dict(zip(pids, base)), dict(zip(pids, base))
        adj = self.start_model.predict(base, base, parts)
        tot0, tot1 = base.sum(), adj.sum()
        if tot1 > 0:
            adj = np.clip(adj * tot0 / tot1, 0.02, 0.98)
        return dict(zip(pids, adj)), dict(zip(pids, base))

    # ------------------------------------------------------------ predict
    def _group_contrib(self, c):
        out = {}
        for gname, v in zip(self.groups, c):
            out[gname] = out.get(gname, 0.0) + float(v)
        return out

    def _draws(self, sigma):
        return np.exp(self.rng.normal(0.0, sigma, self.n_draws) - 0.5 * sigma ** 2)

    def _reasons(self, contrib, stat, opp_tactics):
        c = dict(contrib)
        lead = []
        if opp_tactics:
            keys = ("opponent", "style", "opp_tactic", "tactic_matchup")
            net = sum(c.get(k, 0.0) for k in keys)
            if net >= 0.04:
                for k in keys:
                    c.pop(k, None)
                lead.append(f"The opponent plays {TACTIC_WORDS.get(opp_tactics[0], opp_tactics[0])}, which lifts "
                            f"{STAT_WORDS.get(stat, stat)}.")
        return (lead + top_reasons(c, stat, n=2))[:3]

    def _player_reasons(self, contrib, team_contrib, stat, opp_tactics):
        """A player's card leads with what is about HIM (his share of the team's output, his minutes, the opponent's
        lineup), then at most one reason about the team. Before, every player of a club got the same team sentence."""
        own = {k: v for k, v in contrib.items() if k in ("role", "opp_lineup", "own_lineup")}
        if contrib.get("minutes", 0.0) < 0:                      # "minutes are high" is true of every starter; only a drag informs
            own["minutes"] = contrib["minutes"]
        lead = top_reasons(own, stat, n=1)
        team = self._reasons(team_contrib, stat, opp_tactics)[:1]
        out = lead + [t for t in team if t not in lead]
        return out[:2] if out else self._reasons(contrib, stat, opp_tactics)[:2]

    def team_means(self, home, away, xf=None):
        """Expected count and dispersion for every team metric, both sides. Used to score the
        whole count distribution (not only one threshold) and to show 'expected' on the page.
        Returns {team: {stat: (mu, r, mu_base)}} where mu_base is the plain
        league x team output x opponent concession baseline, with no regression."""
        snap = self.snaps[self.as_of]
        tx = self.tx_snaps[self.as_of] if self.tx_on else None
        out = {}
        for team, opp, is_home in ((home, away, 1), (away, home, 0)):
            X, Y = self.tidx[team], self.tidx[opp]
            feats = self._feat(X, Y, is_home, snap, tx, self._xf_pair(team, opp, xf))
            out[team] = {}
            for s in self.stats:
                off = self._offset(s, X, Y, snap)
                out[team][s] = (float(self.glm[s].predict_mu(feats, off)[0]), float(self.glm[s].r), float(np.exp(off)))
        return out

    def predict_fixture(self, home, away, lineups=None, xf=None, ctx=None, availability=None, match_ctx=None):
        """`ctx` = {team: context.Calendar.context(...) dict} for the two clubs (optional). With it, the
        forecast carries a rotation level and, when the StartModel is on, shifts who is expected to start.
        `availability` = {player: "out" | "doubtful"} from an injury feed or the admin (optional). An "out" player
        gets no forecast and his share of the team's shots and tackles goes to the others.
        A confirmed lineup always wins over the model."""
        lineups = lineups or {}
        availability = availability or {}
        for team in (home, away):
            for pid, info in self.squads.get(team, {}).items():
                st = availability.get(pid)
                info["unavailable"] = st == "out"
                info["doubtful"] = st == "doubtful"
        ctx = ctx or {}
        snap = self.snaps[self.as_of]
        # minutes scenarios for both squads first: lineups of BOTH teams matter
        scen_all, usual_ps, rot = {}, {}, {}
        for team in (home, away):
            conf = lineups.get(team)
            c = ctx.get(team)
            parts = CX.pressure_parts(c) if c else None
            rot[team] = ((CX.pressure_level(CX.rotation_pressure(c)), self._rotation_sentence(c, parts)) if c else ("low", ""))
            ps_adj, ps_base = self._rotated_starts(team, parts) if conf is None else ({}, {})
            for pid, info in self.squads.get(team, {}).items():
                scen_all[pid] = self._scenarios(info, conf, ps_adj.get(pid))
                usual_ps[pid] = ps_base.get(pid)

        tx = self.tx_snaps[self.as_of] if self.tx_on else None
        out = []
        for team, opp, is_home in ((home, away, 1), (away, home, 0)):
            X, Y = self.tidx[team], self.tidx[opp]
            feats = self._feat(X, Y, is_home, snap, tx, self._xf_pair(team, opp, xf))
            opp_tac = self._team_tactics(snap, Y, tx)
            own_tac = self._team_tactics(snap, X, tx)
            mu_team, grp, offs, keys = {}, {}, {}, {}
            for s in self.stats:
                offs[s] = self._offset(s, X, Y, snap)
                own_l, opp_l, key = self._lineup_adj(s, team, opp, scen_all)
                keys[s] = key
                mu_team[s] = float(self.glm[s].predict_mu(feats, offs[s] + own_l + opp_l)[0])
                grp[s] = self._group_contrib(self.glm[s].contributions(feats))
                for gname, v in self._offset_groups(s, X, Y, snap).items():
                    grp[s][gname] = grp[s].get(gname, 0.0) + v
                grp[s]["own_lineup"] = own_l
                grp[s]["opp_lineup"] = opp_l

            # the team's own normalised average against an average opponent (no venue, no matchup): "usual"
            mu_usual = {}
            for s in self.stats:
                dfor, _ = self.team_dims.get(s, (0, 1))
                lu_ = np.log(max(self.league_mean[s], 1e-6)) + snap[0][X, dfor] + (snap[0][X, 7] if s == "sot" else 0.0)
                mu_usual[s] = float(np.exp(lu_))

            # ---- team markets
            for s, thrs in TEAM_THR.items():
                if s not in self.stats:
                    continue
                u = self._draws(self.sigma_team)
                for thr in thrs:
                    k = int(np.floor(thr)) + 1
                    p = float(nb_sf(k, mu_team[s], self.glm[s].r))
                    pd_ = nb_sf(k, mu_team[s] * u, self.glm[s].r)
                    lo, hi = np.percentile(pd_, [10, 90])
                    hist = self.tg_hist.get(team)
                    p_raw = float((hist[s].values[-10:] > thr).mean()) if hist is not None and len(hist) else 0.5
                    p_base = float(nb_sf(k, np.exp(offs[s]), self.glm[s].r))
                    p_usual = float(nb_sf(k, mu_usual[s], self.glm[s].r))
                    out.append(Forecast("team", team, opp, s, thr, mu_team[s], p, float(lo), float(hi),
                                        contrib=grp[s], reasons=self._reasons(grp[s], s, opp_tac),
                                        opp_tactics=opp_tac, own_tactics=own_tac,
                                        opp_key_players=keys[s], p_raw=p_raw, p_base=p_base,
                                        rotation=rot[team][0], rotation_why=rot[team][1], p_usual=p_usual))

            # ---- player markets
            squad = self.squads.get(team, {})
            for s in PLAYER_STATS:
                post = {}
                for pid, info in squad.items():
                    g = info["g"]; ap = g[g["minutes"] > 0]
                    E = (ap["team_" + s] * ap["minutes"] / 90.0).values
                    post[pid] = shrunk_rate(ap[s].values, E, self.rho[s][info["pos"]], self.player_prior.get(s, 40.0), self.hl)
                Z = sum(post[pid].mean * scen_all[pid][1] / 90.0 for pid in squad)
                if Z <= 0:
                    continue
                for pid, info in squad.items():
                    sc, Em, pplay, _ = scen_all[pid]
                    if pplay < 0.15:
                        continue
                    sigma = float(np.sqrt(self.sigma_team ** 2 + post[pid].cv ** 2))
                    u = self._draws(sigma)
                    mus = np.array([mu_team[s] * post[pid].mean * m / 90.0 / Z for _, m in sc])
                    probs = np.array([pr for pr, _ in sc])
                    expected = float(np.sum(probs * mus))
                    contrib = dict(grp[s])
                    contrib["minutes"] = float(np.log(max(Em, 1.0) / 70.0))
                    contrib["role"] = float(np.log(max(post[pid].mean, 1e-6) / self.rho[s][info["pos"]]))
                    g = info["g"]; ap = g[g["minutes"] > 0]
                    pb = shrunk_rate(ap[s].values, (ap["minutes"] / 90.0).values,
                                     self.rho90[s][info["pos"]], 4.0, self.hl)
                    mus_b = np.array([pb.mean * m / 90.0 for _, m in sc])
                    reasons = self._player_reasons(contrib, grp[s], s, opp_tac)
                    for thr in PLAYER_THR[s]:
                        k = int(np.floor(thr)) + 1
                        pdraw = np.sum(probs[:, None] * nb_sf(k, mus[:, None] * u[None, :], self.r_player[s]), axis=0)
                        p = float(np.sum(probs * nb_sf(k, mus, self.r_player[s])))
                        lo, hi = np.percentile(pdraw, [10, 90])
                        last = ap[s].values[-10:]
                        p_raw = float((last > thr).mean()) if len(last) else 0.5
                        p_base = float(np.sum(probs * nb_sf(k, mus_b, self.r_player[s])))
                        out.append(Forecast("player", team, opp, s, thr, expected, p, float(lo), float(hi),
                                            player=int(pid), pos=info["pos"], p_play=float(pplay),
                                            confirmed=lineups.get(team) is not None, contrib=contrib,
                                            reasons=reasons, opp_tactics=opp_tac, own_tactics=own_tac,
                                            opp_key_players=keys[s], p_raw=p_raw, p_base=p_base,
                                            rotation=rot[team][0], rotation_why=rot[team][1],
                                            p_play_usual=usual_ps.get(pid), p_usual=p_base))
        mh, ma = (1.0, 1.0)
        if self.match_context and match_ctx:
            mh, ma = context_multipliers(match_ctx.get(home) or {}, match_ctx.get(away) or {})
        probs = self.dc.outcome_probs(home, away, mult_h=mh, mult_a=ma)
        probs["context"] = {"mult_home": round(mh, 4), "mult_away": round(ma, 4)}
        return out, probs

    @staticmethod
    def _rotation_sentence(c, parts):
        """One plain sentence for the page. Empty when pressure is low."""
        if not c or CX.pressure_level(CX.rotation_pressure(c)) == "low":
            return ""
        if parts["next_bigger"] >= 0.3:
            comp = {"ucl": "a Champions League match", "uel": "a Europa League match", "uecl": "a Conference League match"}.get(
                c.get("next_comp", ""), "a bigger match")
            return f"The club has {comp} in {c['next_gap']:.0f} days, so some regulars may rest."
        if parts["low_stakes"] >= 0.4:
            return "This is a lesser competition, so the club may rotate."
        if parts["short"] >= 1 or parts["congestion"] >= 0.5:
            return "The club has played often in the last two weeks, so some regulars may rest."
        return "The club may rotate here."
