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

from core import (recency_weights, shrunk_rate, nb_sf, fit_dispersion, top_reasons, STAT_WORDS)
from nbglm import NBGLM
from strength import DixonColes
import tactics as TX
import context as CX
from ratings import RatingsModel, HALF as R_HALF, LAM as R_LAM

STATS = ["shots", "sot", "corners", "tackles"]
# The markets the player layer fits and forecasts. It is a LIST and not derived from PLAYER_THR's
# keys because a stat can only be fitted when its column and its team total are both in the frame;
# engine_bridge.configure_engine narrows this to what the data actually carries, so a market named
# in the settings but missing from the feed is dropped rather than raising mid-run (docs/70).
ALL_PLAYER_STATS = ["shots", "sot", "tackles", "fouls_committed", "goal_involvements"]
PLAYER_STATS = list(ALL_PLAYER_STATS)   # narrowed per run; restored from ALL_ at the start of each
PLAYER_THR = {"shots": [0.5, 1.5], "sot": [0.5], "tackles": [1.5, 2.5]}
TEAM_THR = {"corners": [4.5], "shots": [11.5]}

SUM_COLS = ["shots", "shots_against", "corners", "corners_against",
            "tackles", "tackles_against", "poss", "sot", "sot_against"]   # the core 9; extras appended after these
OWN_I = [0, 2, 6, 4]   # shots_for, corners_for, poss, tackles_for
OPP_I = [1, 3, 6, 5]   # shots_against, corners_against, poss, tackles_against
TEAM_DIMS = {"shots": (0, 1), "corners": (2, 3), "tackles": (4, 5)}

# Negative-binomial dispersion per market: var = mu + mu^2/r, so a LOWER r means more clustering.
# A rare, bursty event clusters harder than a routine one -- a player either gets involved in a
# goal or he does not, where shots arrive steadily -- hence 3.0 for involvements against 6.0 for
# shots. `fit_player_r` replaces all of these from the data when it is on, which is the point of
# these being a starting value rather than a claim.
DEFAULT_R_PLAYER = {"shots": 6.0, "sot": 5.0, "tackles": 10.0,
                    "fouls_committed": 6.0, "goal_involvements": 3.0}
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


def personal_k(sf_at, hi: int = 40, target: float = 0.5) -> int:
    """The count where an entity's OWN distribution crosses `target` (docs/52).

    `sf_at(k)` is P(N >= k) under that entity's usual rate -- its own shrunk per-90 rate carried
    through this match's minutes, before any opponent adjustment. It falls as k rises, so there is
    exactly one crossing and we take the integer nearest it.

    Why not the median of its last N games: a count is a small integer, so the empirical median is
    degenerate (a median of 2 leaves P(>=2)=.65 and P(>=3)=.35, neither near a half) and a handful
    of appearances moves it by a whole unit. Inverting the fitted distribution has neither problem,
    and the rate behind it is already shrunk toward the positional mean and already mixed over this
    match's minutes, so a substitute's cameos do not drag his line down.
    """
    best, best_d = 1, abs(float(sf_at(1)) - target)
    for k in range(2, hi + 1):
        v = float(sf_at(k))
        d = abs(v - target)
        if d < best_d:
            best, best_d = k, d
        if v < target * 0.4:            # well past the crossing; it only falls from here
            break
    return best


def personal_thrs(k: int, spread: int = 1, lo_k: int = 1) -> list[float]:
    """The headline rung plus a neighbour either side, so the Finder keeps a range to answer from.
    Returned low to high; the caller marks which one is the personal line."""
    ks = sorted({max(lo_k, k + d) for d in range(-spread, spread + 1)})
    return [float(x) - 0.5 for x in ks]


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
    rec_k: int | None = None            # games (of his last rec_n played) in which he beat this line
    rec_n: int | None = None
    # The same record, weighted by how recent each game was (docs/62). `rec_k`/`rec_n` stay the flat
    # whole-game pair the card prints; these two are what the anchor should blend toward.
    rec_rate: float | None = None       # recency-weighted share of those games that beat the line
    rec_neff: float | None = None       # effective games behind that share (Kish)
    thr_personal: float | None = None   # this entity's OWN 50% line for this stat (docs/52): the count it clears
                                        # about half the time in its usual game. The headline rung.
    expected_usual: float | None = None # the count it manages in its usual game, against an average opponent
                                        # and match (docs/25). The feed ranks by p - p_usual.
    span: float | None = None           # docs/56: how much this rung's likelihood moves across the league's range of
                                        # opponents, in likelihood points. Small means the rung cannot carry news
                                        # about THIS fixture -- every opponent gives nearly the same answer -- so it
                                        # should not lead a card. None means unknown; unknown is never treated as
                                        # trivial.
    span_lo: float | None = None        # the same rung against the MEANEST defence in the league, and against the
    span_hi: float | None = None        # leakiest. Both were already computed to get `span` and then thrown away,
                                        # which left the product's one genuinely distinctive quantity as an
                                        # abstract width nobody could read. With the two ends a card can say what
                                        # the opponent is actually worth: "against the meanest 58%, the leakiest 79%".
    p_start: float | None = None        # his chance to START (docs/55). p_play is the chance to feature, which is
                                        # near 1 for a regular substitute, so a gate on p_play does not catch him.
    # docs/59: his RECORD of starting, which is what the lineup badge is really asking about.
    # `starts_recent` of his club's last `club_recent` matches -- the CLUB's fixtures, so that
    # absences count against him, from his first appearance for them, so that a new signing is not
    # charged for the matches played before he arrived. None = no readable record (see fit): the
    # badge then falls back to the chance-to-play gate rather than calling him a doubt on missing
    # data.
    starts_recent: int | None = None
    # The same record weighted by recency (docs/62). None when the flat pair is None, or when
    # engine.starter_half_life is 0, in which case the badge uses the flat pair as it always has.
    starts_share: float | None = None
    club_recent: int | None = None
    missed_recent: int | None = None    # his club's most recent matches he has missed, in a row
    doubtful: bool = False              # flagged doubtful by the injury feed or the admin


# Availability (docs/22). A player who has not featured in his club's last matches is often injured, suspended or
# dropped. Fitted on StatsBomb 2015/16 (Premier League, Serie A, Ligue 1), history = games he featured in, exactly
# what the live feed gives: logit P = c0 + c1 * logit(usual start rate) + c2*[missed >= 1] + c3*[>= 2] + c4*[>= 3] + c5*[>= 4].
# Held-out gain in log loss per player-game: starts +0.138 (z +38), plays +0.165 (z +41), every league.
ABSENCE_START = (-0.107, 0.719, -1.238, -0.791, -0.356, -1.065)
ABSENCE_PLAY = (1.043, 0.288, -1.219, -0.642, -0.363, -1.036)

# docs/59: how many starters a club's match row must average before the `started` flag is believed
# enough to read a start record off it. A real eleven gives 10 or 11 here (goalkeepers are usually
# excluded by engine.exclude_positions). Well under that means the lineups endpoint is not covered
# for this league, not that the club fielded a team of substitutes.
MIN_STARTERS_SEEN = 7.0


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
                 style_half_life=None, style_opp_adjust=(), style_cap_q=None, player_prior=None, cond_play=False,
                 minutes_floor=0.0,
                 ratings_blend=0.0, script_v2=False, fit_player_r=False, opp_pos_k=0.0, xg_blend=0.0, sot_against=False,
                 player_half_life=0.0, starter_half_life=0.0,
                 personal_lines=False, personal_spread=1):
        self.interactions = interactions
        # Player lines are "if he plays" (docs/27). His chance to play is shown as a lineup badge, not folded into the percentage.
        self.cond_play = bool(cond_play)
        self.minutes_floor = max(0.0, min(0.6, float(minutes_floor or 0.0)))
        self.ratings_blend = float(ratings_blend)   # weight of the attack/defence ratings model in each team count (docs/33)
        # --- docs/37 upgrades. Each is OFF by default and ships only if engine_ab.py passes its gate on real data.
        self.script_v2 = bool(script_v2)        # game state: margin, how lopsided, and the tempo of the fixture
        self.fit_player_r = bool(fit_player_r)  # player dispersion fitted from results instead of a fixed guess
        # docs/52: every entity gets its own line, at the count it clears about half the time. Off by default,
        # like every docs/37 upgrade, so engine_ab.py can judge it before it ships.
        self.personal_lines = bool(personal_lines)
        self.personal_spread = int(personal_spread)
        self.opp_pos_k = float(opp_pos_k)       # >0: what this opponent allows to each position (prior strength)
        self.xg_blend = float(xg_blend)         # weight of an xG-based Dixon-Coles in expected goals
        # On-target is the one market with no opponent of its own. See _dims: by default the engine
        # asks how many SHOTS the opponent concedes and how accurate THIS team usually is, so a
        # defence that gives up 15 shots a game is treated the same whether they fly on target or
        # are blocked -- and a goalkeeper who saves everything is invisible. The column has been
        # collected all along (ingest mirrors the opponent's `sot`) and the team page already draws
        # it as "On target against"; nothing read it.
        self.sot_opp = bool(sot_against)
        self.opp_pos = {}
        self.dc_xg = None
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
            self.team_dims[st_] = (len(SUM_COLS) + 2 * j, len(SUM_COLS) + 1 + 2 * j)
            TEAM_THR.setdefault(st_, list(EXTRA_THR.get(st_, [])))
        self.lineup_l2 = lineup_l2
        self.hl = half_life_rounds
        # A PLAYER'S form and a CLUB's strength do not move at the same speed, and one half-life was
        # governing both. A club's attack is a property of a squad and a system and changes over a
        # season; a player's rate changes when he switches flank, loses the set pieces or gets a new
        # manager -- which is a handful of matches, not twenty. `self.hl` keeps the team GLM's row
        # weights; this governs the player layer alone. 0 means "the same as the team", which is
        # exactly today's behaviour.
        self.player_hl = float(player_half_life) or float(half_life_rounds)
        # 0 keeps the flat count the start record has always been (docs/62).
        self.starter_hl = float(starter_half_life or 0.0)
        self.k = style_k
        self.min_round = min_round
        self.n_draws = n_draws
        self.sigma_team = sigma_team
        self.rng = np.random.default_rng(seed)
        self.r_player = dict(DEFAULT_R_PLAYER)
        self.absence = True                         # availability model (missed recent matches); docs/22
        self.match_context = True                   # results form and stakes on expected goals; docs/22
        self.likely_starter_p = None                # chance to play at or above this = treated as a starter, full minutes
        self.start_window = 10                      # docs/59: club matches the start RECORD is read over (0 = off)
        self.norm_blend = 0.5                       # weight of the normalised team average in team_norm stats
        self.start_model = None                     # context.StartModel, set by set_start_model()
        self.start_on = False                       # applied only when its walk-forward gate passed

    def set_start_model(self, model, enabled: bool = True):
        """Attach a fitted context.StartModel. `enabled` is the stored gate result: when False the
        model is kept (so the page can still show the rotation chip) but start odds are not changed."""
        self.start_model = model
        self.start_on = bool(enabled and model is not None and model.w is not None)
        return self

    # ------------------------------------------------------------ styles
    def _snap(self, S, n, gd, tot=None):
        """Style snapshot: (style matrix, shrunk goal difference a game, shrunk goals a game in the team's matches).
        The third element is the tempo signal used by the game-script features (docs/37)."""
        T = len(n)
        if n.sum() == 0:
            return np.zeros((T, S.shape[1])), np.zeros(T), np.zeros(T)
        league = S.sum(0) / n.sum()
        m = (S + self.k * league) / (n[:, None] + self.k)
        st = np.log(np.maximum(m, 1e-9) / np.maximum(league, 1e-9))
        sot_rate = m[:, 7] / np.maximum(m[:, 0], 1e-9)
        st[:, 7] = np.log(np.maximum(sot_rate, 1e-9) / (league[7] / max(league[0], 1e-9)))
        if tot is None:
            tempo = np.zeros(T)
        else:
            lg_tot = float(tot.sum() / n.sum())              # league average goals in a match
            tempo = (tot + 6.0 * lg_tot) / (n + 6.0)         # shrunk toward the league, not toward zero
        return st, gd / (n + 6.0), tempo

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
        S = np.zeros((T, D)); n = np.zeros(T); gd = np.zeros(T); tot = np.zeros(T)
        S0 = np.zeros(D); n0 = 0.0                       # plain league totals
        g_dec = 0.5 ** (1.0 / self.style_half) if self.style_half else 1.0
        pairs = self._opp_pairs()
        seen = []
        caps = None
        poss_i = self.sum_cols.index("poss") if "poss" in self.sum_cols else -1
        snaps = {}
        for r, g in tg.groupby("round"):
            snaps[r] = self._snap(S, n, gd, tot)
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
                S[u] *= g_dec; n[u] *= g_dec; gd[u] *= g_dec; tot[u] *= g_dec
            np.add.at(S, ti, Xa)
            np.add.at(n, ti, 1.0)
            np.add.at(gd, ti, (g["goals"] - g["goals_against"]).values.astype(float))
            np.add.at(tot, ti, (g["goals"] + g["goals_against"]).values.astype(float))
        snaps[as_of] = self._snap(S, n, gd, tot)
        self.league_mean = {s: float(S0[i] / max(n0, 1)) for s, i in
                            (("shots", 0), ("corners", 2), ("tackles", 4), ("sot", 7))}
        for s_, (i_, _) in self.team_dims.items():
            if s_ not in self.league_mean:
                self.league_mean[s_] = float(S0[i_] / max(n0, 1))
        return snaps

    def _dims(self, stat):
        """(this team's output dimension, the opponent's concession dimension).

        With `sot_against` on, on-target becomes a first-class market measured against what the
        opponent concedes ON TARGET, like shots, corners and tackles already are. Off, it keeps the
        decomposition it has always had: the opponent's SHOTS conceded, times this team's own
        accuracy -- which is why `_acc` below exists and why it must not be added twice.
        """
        if stat == "sot" and self.sot_opp:
            # Only the OPPONENT term changes. On-target is shots x accuracy -- sot = binomial(shots,
            # acc) is literally how it arises -- so the shot-volume channel has to stay on both
            # sides. Replacing the whole thing with sot_for x sot_against was measured and is worse
            # (team sot z -1.35, player sot z -1.18 on the simulated league): it discards the volume
            # that drives most of the count. What this swaps in is the opponent's ON-TARGET conceded
            # in place of their shots conceded, which is the same volume term plus what they concede
            # in accuracy -- a keeper who saves everything, a defence that blocks rather than funnels.
            return self.team_dims["shots"][0], self.sum_cols.index("sot_against")
        return self.team_dims.get(stat, (0, 1))

    def _acc(self, stat, X, st):
        """This team's own accuracy. Kept whichever opponent term is used: it is the other half of
        shots x accuracy, and it describes the attacking side, not the defending one."""
        return float(st[X, self.sum_cols.index("sot")]) if stat == "sot" else 0.0

    def _offset(self, stat, X, Y, snap):
        """Simple baseline in log space: league mean x team's output x
        opponent's concession. The regression only learns corrections."""
        st = snap[0]
        dfor, dag = self._dims(stat)
        return float(np.log(max(self.league_mean[stat], 1e-6)) + st[X, dfor] + st[Y, dag] + self._acc(stat, X, st))

    def _offset_groups(self, stat, X, Y, snap):
        st = snap[0]
        dfor, dag = self._dims(stat)
        return {"own_style": float(st[X, dfor] + self._acc(stat, X, st)), "opponent": float(st[Y, dag])}

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
        tp = snap[2] if len(snap) > 2 else np.zeros_like(rt)
        sx, sy = st[X], st[Y]
        parts = [sx, sy]
        if self.interactions:
            parts.append(np.outer(sx[OWN_I], sy[OPP_I]).ravel())
        margin = rt[X] - rt[Y]
        parts.append([float(home), margin])
        if self.script_v2:
            # docs/37: a lopsided fixture plays differently from a level one (the side in front sits deeper), and an
            # open fixture has more of everything. Both are known before kick-off and both come from the snapshot,
            # so no result from this round leaks in.
            parts.append([abs(margin), 0.5 * (tp[X] + tp[Y])])
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
        if self.script_v2:
            g += ["game_script"] * 2
            l2 += [1.0, 1.0]
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
    def fit(self, matches, tg, pg, as_of, appearances=None):
        """`appearances` (optional): player, team, game_id, round for every match a player actually
        featured in, taken BEFORE the stat-completeness filters. Used only to count the club games
        he missed. Without it that count falls back to `pg`, which is thinned by those filters, so
        an incomplete stat line reads as an absence -- see engine_bridge.build_frames."""
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
        self.mu_fit = {}
        for s in self.stats:
            offs[s] = np.array([self._offset(s, self.tidx[r.team], self.tidx[r.opp], self.snaps[r.round])
                                for r in rows.itertuples()])
            self.glm[s] = NBGLM(l2=l2).fit(Xs, rows[s].values.astype(float), w, offset=offs[s])
            if self.fit_player_r and s in PLAYER_STATS and len(rows):
                mu_hat = self.glm[s].predict_mu(Xs, offs[s])
                self.mu_fit[s] = {(int(gid), int(t)): float(v)
                                  for gid, t, v in zip(rows["game_id"].values, rows["team"].values, mu_hat)}

        # attack / defence ratings per count (docs/33)
        self.rat = {}
        if self.ratings_blend > 0:
            hm = tg[tg["home"] == 1]
            for s in self.stats:
                if s in hm.columns and (s + "_against") in hm.columns:
                    self.rat[s] = RatingsModel(R_HALF.get(s, 60.0), R_LAM.get(s, 12.0)).fit(
                        hm["team"].map(self.tidx).values, hm["opp"].map(self.tidx).values,
                        hm[s].values, hm[s + "_against"].values, as_of - 1 - hm["round"].values, len(self.teams))

        # team strength
        self.dc = DixonColes(xi=self.strength_decay).fit(matches["home"], matches["away"], matches["hg"],
                                   matches["ag"], as_of - 1 - matches["round"].values)

        # team histories for baselines
        self.tg_hist = {t: g.sort_values("round") for t, g in tg.groupby("team")}

        # player layer
        pgp = pg[pg["minutes"] > 0]
        self.rho = {}
        # `rho90`, the positional per-90 mean, was computed here only to shrink the player's own
        # baseline toward. That baseline is now built from the same posterior and the same team
        # total as his forecast, so nothing reads it any more.
        # The markets THIS frame can support. A market needs its own column and its team total, and
        # neither is guaranteed: fouls and goal involvements were added to the engine after some
        # leagues were ingested, and a caller that builds its own frame (the A/B runner, the
        # simulator, a test) has no reason to carry columns for markets it is not studying. The
        # engine fits what it is given rather than crashing on what it is not -- the alternative is
        # a KeyError in the middle of a league run, which is how this was found.
        self.player_stats = [s for s in PLAYER_STATS
                             if s in pgp.columns and ("team_" + s) in pgp.columns]
        for s in self.player_stats:
            E = pgp["team_" + s] * pgp["minutes"] / 90.0
            self.rho[s] = (pgp.groupby("pos")[s].sum() / E.groupby(pgp["pos"]).sum()).to_dict()
        self.pl = {}
        for pid, g in pg.groupby("player"):
            g = g.sort_values("round")
            self.pl[pid] = dict(team=int(g["team"].iloc[-1]), pos=g["pos"].iloc[-1], g=g, pid=pid)
        # club matches in order, and for each player how many of his club's latest matches he has missed
        team_games = {t: list(g.sort_values("round")["game_id"]) for t, g in tg.groupby("team")}
        # Who played, from the unfiltered record when the caller supplied one. `pg` has had every
        # row with an incomplete stat line removed, so counting absences from it answers "which of
        # his club's games do we hold a full stat line for", not "which did he play in" -- and the
        # difference is fed straight into the availability model.
        played = {}
        if appearances is not None and len(appearances):
            ap = appearances[appearances["round"] < as_of]
            for (pid, team), g in ap.groupby(["player", "team"]):
                played[(int(pid), int(team))] = set(g["game_id"])
        n_win = int(self.start_window or 0)          # docs/59: the start-record window, in club matches
        own, club_starts, club_win, own_share = {}, {}, {}, {}
        for pid, info in self.pl.items():
            tgl = team_games.get(info["team"], [])
            mine = played.get((int(pid), int(info["team"])))
            if mine is None:
                mine = set(info["g"].loc[info["g"]["team"] == info["team"], "game_id"])
            missed = 0
            for gid in reversed(tgl):
                if gid in mine:
                    break
                missed += 1
            info["missed"] = missed
            # docs/59: and his record of STARTING over the same window -- see below.
            g_own = info["g"][info["g"]["team"] == info["team"]]
            st = dict(zip(g_own["game_id"].astype(int), g_own["started"].astype(int)))
            w0 = tgl[-n_win:] if n_win > 0 else []
            club_starts[info["team"]] = club_starts.get(info["team"], 0) + sum(
                1 for gid in w0 if st.get(int(gid), 0) == 1)
            first = next((i for i, gid in enumerate(w0) if gid in mine), None)
            w = w0[first:] if first is not None else []
            own[pid] = (sum(1 for gid in w if st.get(int(gid), 0) == 1), len(w))
            # docs/62: the same window, with the recent club matches worth more. Whether a manager
            # picks him is a fact about now -- he has been dropped, or he has come into the side --
            # and measured on 59,644 real Premier League appearances a recency-weighted start record
            # beats a flat one by about a tenth of its log loss, peaking around a four-match
            # half-life. That is ten to thirty times the gain recency is worth on what a player DOES
            # once he is picked, which is why it is applied here and only lightly there.
            if self.starter_hl and w:
                sq = np.array([1.0 if st.get(int(gid), 0) == 1 else 0.0 for gid in w])
                ww = recency_weights(len(sq), float(self.starter_hl))
                sw = float(ww.sum())
                own_share[pid] = float((ww * sq).sum() / sw) if sw > 0 else None
            club_win[info["team"]] = len(w0)

        # docs/59: his recent record of STARTING, which is what the lineup badge asks about.
        #
        # Counted over his CLUB's last `start_window` matches, not over his own appearances. The two
        # are different and only the first answers the question: a player who missed five of the
        # club's last ten and started the five he played started 100% of his appearances and 50% of
        # his club's games. Measured on the demo league, the appearance share passes 84 of 85 player
        # cards at 0.5 and 81 at 0.6 -- it cannot tell a regular from a stand-in, because the games
        # that would have told them apart are exactly the ones it leaves out.
        #
        # `starts_recent` is None when there is no record worth reading, and None means "fall back
        # to the chance-to-play gate", never "unsure". Three cases:
        #   * fewer than half the window of club matches on record at all (early season);
        #   * a window whose rows carry far too few starters. `started` comes from the LINEUPS
        #     endpoint (normalize.normalize_match: `p["started"] = p["ext_id"] in started`), so a
        #     league without that coverage reports eleven substitutes a side -- and a badge keyed
        #     on it would quietly call every player in the league a doubt. That is the same shape
        #     of bug as the unmapped `minutes` key, one column over, so it is guarded here rather
        #     than left to be discovered in production;
        #   * fewer than half the window of club matches since he ARRIVED. The window is trimmed to
        #     start at his first appearance for the club, because a signing has no record of the
        #     matches played before he was there and counting them as games he did not start would
        #     call every new arrival a doubt for his first two months. Trimming changes nothing for
        #     a player who has been at the club all along, which is almost everyone, so absences
        #     still count against him.
        min_games = max(3, (n_win + 1) // 2)
        for pid, info in self.pl.items():
            k, n = own.get(pid, (0, 0))
            n_club = club_win.get(info["team"], 0)
            seen = club_starts.get(info["team"], 0) / n_club if n_club else 0.0
            ok = n_club >= min_games and seen >= MIN_STARTERS_SEEN and n >= min_games
            info["starts_recent"] = int(k) if ok else None
            info["club_recent"] = int(n) if ok else None
            # The weighted share travels beside the whole-game pair, never instead of it: the card
            # prints "started 7 of the club's last 10", which has to stay two countable numbers.
            info["starts_share"] = own_share.get(pid) if ok else None

        self.squads = {}
        for pid, info in self.pl.items():
            self.squads.setdefault(info["team"], {})[pid] = info

        if self.fit_player_r:
            self._fit_player_dispersion()
        if self.opp_pos_k > 0:
            self._fit_opp_pos(pgp)
        if self.xg_blend > 0:
            self._fit_xg(tg)
        if self.lineup:
            self._fit_lineup(rows, pg, w, offs, Xs)
        return self

    # ------------------------------------------------- docs/37: fitted player dispersion
    def _fit_player_dispersion(self):
        """How spread out a player's count is around its mean, fitted from results instead of a fixed guess.

        Two things keep it honest:
          * the player's share is rebuilt WITHOUT the game being scored (leave one out), so the mean never saw
            the number it is judged on;
          * the mean uses the team total the model would have PREDICTED, not the total that actually happened, so
            the spread includes the team-total error a real forecast carries. Scoring against the actual total
            would hide that and leave the engine too confident.
        Too few rows, or no predicted totals, and the current value stays."""
        for st in self.player_stats:
            pred = self.mu_fit.get(st) or {}
            if not pred:
                continue
            mus, ys = [], []
            prior_k = self.player_prior.get(st, 40.0)
            for info in self.pl.values():
                g = info["g"]; ap = g[g["minutes"] > 0]
                if len(ap) < 3:
                    continue
                counts = ap[st].values.astype(float)
                E = (ap["team_" + st] * ap["minutes"] / 90.0).values.astype(float)
                w_ = recency_weights(len(ap), self.player_hl)
                base = self.rho[st].get(info["pos"])
                if base is None or not np.isfinite(base):
                    continue
                alpha = base * prior_k + float(np.sum(w_ * counts))
                beta = prior_k + float(np.sum(w_ * E))
                rate = (alpha - w_ * counts) / np.maximum(beta - w_ * E, 1e-9)       # leave one out
                team_pred = np.array([pred.get((int(gid), int(tm)), np.nan)
                                      for gid, tm in zip(ap["game_id"].values, ap["team"].values)], float)
                mu_i = np.maximum(rate, 1e-6) * team_pred * ap["minutes"].values.astype(float) / 90.0
                ok = np.isfinite(mu_i) & (mu_i > 1e-6)
                if ok.any():
                    mus.append(mu_i[ok]); ys.append(counts[ok])
            if not mus:
                continue
            mu = np.concatenate(mus); y = np.concatenate(ys)
            # above about 100 a negative binomial is a Poisson for our purposes; the cap keeps the number readable
            self.r_player[st] = float(min(fit_dispersion(mu, y, default=self.r_player[st]), 100.0))

    # ------------------------------------------------- docs/37: what an opponent allows to each position
    def _fit_opp_pos(self, pgp):
        """Factor per (opponent, position, stat): what this opponent lets that position do, against what the
        league's players in that position would be expected to do for the same team total and minutes.

        1.0 means average. Shrunk toward 1.0 by `opp_pos_k` units of expected count, so a team with few games
        barely moves. Applied to a player's share, after which the shares are renormalised, so the TEAM total is
        unchanged: this moves the count between players, it does not invent extra shots."""
        self.opp_pos = {}
        if "opp" not in pgp.columns:
            return
        for st in self.player_stats:
            rho = self.rho[st]
            exp = pgp["pos"].map(rho).astype(float) * pgp["team_" + st].astype(float) * pgp["minutes"].astype(float) / 90.0
            df = pd.DataFrame({"opp": pgp["opp"].values, "pos": pgp["pos"].values,
                               "act": pgp[st].astype(float).values, "exp": exp.values})
            df = df[np.isfinite(df["exp"]) & (df["exp"] > 0) & np.isfinite(df["act"])]
            if df.empty:
                continue
            g = df.groupby(["opp", "pos"])[["act", "exp"]].sum()
            k = self.opp_pos_k
            fac = (g["act"] + k) / (g["exp"] + k)
            self.opp_pos[st] = {(int(o), p): float(min(max(v, 0.5), 2.0)) for (o, p), v in fac.items()}

    def _opp_pos_factor(self, stat, opp_idx, pos) -> float:
        return self.opp_pos.get(stat, {}).get((int(opp_idx), pos), 1.0)

    # ------------------------------------------------- docs/37: xG in team strength
    def _fit_xg(self, tg):
        """A second Dixon-Coles fitted on expected goals. Expected goals are a steadier signal of how good a team
        is than goals, which are few and swingy. Only fitted when the feed carries xG for both sides."""
        self.dc_xg = None
        if not {"xg", "home", "goals"} <= set(tg.columns):
            return
        h = tg[tg["home"] == 1].dropna(subset=["xg"])
        rows = h.merge(tg[tg["home"] == 0][["game_id", "team", "xg"]].rename(columns={"team": "away_team", "xg": "xg_away"}),
                       on="game_id", how="inner").dropna(subset=["xg_away"])
        if len(rows) < 60:
            return
        try:
            self.dc_xg = DixonColes(xi=self.strength_decay).fit(rows["team"], rows["away_team"], rows["xg"].astype(float),
                                                                rows["xg_away"].astype(float),
                                                                self.as_of - 1 - rows["round"].values)
        except Exception:
            self.dc_xg = None

    def _xg_mults(self, home, away):
        """Multipliers that move the goal model's expected goals toward the xG model's, in log space."""
        if self.dc_xg is None or self.xg_blend <= 0:
            return 1.0, 1.0
        if home not in self.dc_xg.teams or away not in self.dc_xg.teams:
            return 1.0, 1.0
        lh, la = self.dc.expected_goals(home, away)
        xh, xa = self.dc_xg.expected_goals(home, away)
        w = self.xg_blend
        out = []
        for base, x in ((lh, xh), (la, xa)):
            if base <= 1e-6 or x <= 1e-6:
                out.append(1.0); continue
            out.append(float(np.exp(w * (np.log(x) - np.log(base)))))
        return out[0], out[1]

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

    def _minutes_share(self, m):
        """How much of a full match's expectation a player of `m` minutes gets.

        The engine has always used m/90: twice the time, twice the shots. That is right for the
        expected COUNT and it is the wrong shape for "did he manage one at all", which is what a
        1+ line asks. A substitute comes on to attack, and a starter can have a quiet ninety -- so
        simply being on the pitch is worth something before the clock starts mattering.

        `engine.minutes_floor` is that fixed part. At 0, which is the default, this returns m/90
        and nothing changes. At a, a player gets a + (1-a)*m/90, so a twenty-minute appearance is
        worth more than two ninths of a full one.

        It is deliberately applied in every place minutes scale a rate, Z included, so the players
        on the pitch still share exactly the team's expected total between them.
        """
        f = m / 90.0
        a = self.minutes_floor
        return f if a <= 0 else a + (1.0 - a) * f

    def _opp_log_spread(self, s, snap):
        """How much the league's opponents differ in what they allow for stat `s`, in log space.

        Half the 10-to-90 range of the concession strengths the engine already keeps in its snapshot, so it is the
        league's own spread and not a chosen constant. Used only to measure how sensitive a rung is (docs/56):
        a rung whose likelihood barely moves over this range cannot tell the reader anything about this fixture.

        Returns 0.0 when the snapshot is too thin to say, and the caller then records the span as unknown rather
        than as small -- the difference matters, because unknown must never be read as trivial.
        """
        _, dag = self.team_dims.get(s, (0, 1))
        col = np.asarray(snap[0][:, dag], float)
        if col.size < 4 or not np.all(np.isfinite(col)):
            return 0.0
        return 1.2816 * float(np.std(col))

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
        own = {k: v for k, v in contrib.items() if k in ("role", "opp_role", "opp_lineup", "own_lineup")}
        if contrib.get("minutes", 0.0) < 0:                      # "minutes are high" is true of every starter; only a drag informs
            own["minutes"] = contrib["minutes"]
        lead = top_reasons(own, stat, n=1)
        team = self._reasons(team_contrib, stat, opp_tactics)[:1]
        out = lead + [t for t in team if t not in lead]
        return out[:2] if out else self._reasons(contrib, stat, opp_tactics)[:2]

    def _rate(self, s, mu, X, Y, is_home):
        """Blend a team count with the ratings model (log scale)."""
        rm = self.rat.get(s)
        if rm is None or not rm.ok or self.ratings_blend <= 0:
            return mu
        m = rm.mu(X, Y, is_home)
        w = self.ratings_blend
        return float(np.exp((1 - w) * np.log(max(mu, 1e-6)) + w * np.log(max(m, 1e-6))))

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
                out[team][s] = (self._rate(s, float(self.glm[s].predict_mu(feats, off)[0]), X, Y, is_home), float(self.glm[s].r), float(np.exp(off)))
        return out

    def predict_fixture(self, home, away, lineups=None, xf=None, ctx=None, availability=None, match_ctx=None, team_norm=None):
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
        scen_all, usual_ps, rot, likely_play = {}, {}, {}, {}
        team_norm = team_norm or {}
        for team in (home, away):
            conf = lineups.get(team)
            c = ctx.get(team)
            parts = CX.pressure_parts(c) if c else None
            rot[team] = ((CX.pressure_level(CX.rotation_pressure(c)), self._rotation_sentence(c, parts)) if c else ("low", ""))
            ps_adj, ps_base = self._rotated_starts(team, parts) if conf is None else ({}, {})
            for pid, info in self.squads.get(team, {}).items():
                scen_all[pid] = self._scenarios(info, conf, ps_adj.get(pid))
                usual_ps[pid] = ps_base.get(pid)
                sc0 = scen_all[pid]
                if conf is None and self.likely_starter_p and sc0[0] and sc0[2] >= self.likely_starter_p:
                    likely_play[pid] = sc0[2]                     # likely starter: no chance-to-play discount
                    scen_all[pid] = ([(1.0, sc0[0][0][1])], sc0[0][0][1], 1.0, 1.0)

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
                tn = team_norm.get(team, {}).get(s)
                if tn:
                    mu_team[s] = float(np.exp((1 - self.norm_blend) * np.log(max(mu_team[s], 1e-6)) + self.norm_blend * np.log(tn)))
                mu_team[s] = self._rate(s, mu_team[s], X, Y, is_home)
                grp[s] = self._group_contrib(self.glm[s].contributions(feats))
                for gname, v in self._offset_groups(s, X, Y, snap).items():
                    grp[s][gname] = grp[s].get(gname, 0.0) + v
                grp[s]["own_lineup"] = own_l
                grp[s]["opp_lineup"] = opp_l

            # the team's own normalised average against an average opponent (no venue, no matchup): "usual"
            mu_usual = {}
            for s in self.stats:
                dfor, _ = self._dims(s)
                lu_ = np.log(max(self.league_mean[s], 1e-6)) + snap[0][X, dfor] + self._acc(s, X, snap[0])
                mu_usual[s] = float(np.exp(lu_))
                tu = team_norm.get(team, {}).get(s + "_usual")
                if tu:
                    mu_usual[s] = float(np.exp((1 - self.norm_blend) * lu_ + self.norm_blend * np.log(tu)))

            # ---- team markets
            for s, thrs in TEAM_THR.items():
                if s not in self.stats:
                    continue
                u = self._draws(self.sigma_team)
                thr_own = None
                if self.personal_lines:                   # docs/52: this team's own 50% line, not one line for the league
                    k_own = personal_k(lambda k: nb_sf(k, mu_usual[s], self.glm[s].r))
                    thrs = personal_thrs(k_own, self.personal_spread)
                    thr_own = float(k_own) - 0.5
                dlog = self._opp_log_spread(s, snap)
                for thr in thrs:
                    k = int(np.floor(thr)) + 1
                    p = float(nb_sf(k, mu_team[s], self.glm[s].r))
                    # docs/56: the same rung against the leakiest and the meanest defence in the league
                    # keep the two ends, not only the distance between them
                    s_hi = float(nb_sf(k, mu_team[s] * np.exp(dlog), self.glm[s].r)) if dlog > 1e-6 else None
                    s_lo = float(nb_sf(k, mu_team[s] * np.exp(-dlog), self.glm[s].r)) if dlog > 1e-6 else None
                    span = abs(s_hi - s_lo) if dlog > 1e-6 else None
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
                                        rotation=rot[team][0], rotation_why=rot[team][1], p_usual=p_usual,
                                        thr_personal=thr_own, expected_usual=float(mu_usual[s]), span=span,
                                        span_lo=s_lo, span_hi=s_hi))

            # ---- player markets
            squad = self.squads.get(team, {})
            # Only markets that were FITTED, for the same reason fit() narrows: a market whose
            # columns the frame never carried has no rho, no posterior and no mu, so walking it
            # here would fail on the first lookup instead of simply not being published.
            for s in self.player_stats:
                post = {}
                rate = {}
                opp_pos_f = {}
                for pid, info in squad.items():
                    g = info["g"]; ap = g[g["minutes"] > 0]
                    E = (ap["team_" + s] * ap["minutes"] / 90.0).values
                    post[pid] = shrunk_rate(ap[s].values, E, self.rho[s][info["pos"]], self.player_prior.get(s, 40.0), self.player_hl)
                    # what this opponent allows to his position (docs/37). The shares are renormalised below, so the
                    # team total does not change: this only moves the count between the players on the pitch.
                    opp_pos_f[pid] = self._opp_pos_factor(s, Y, info["pos"]) if self.opp_pos_k > 0 else 1.0
                    rate[pid] = post[pid].mean * opp_pos_f[pid]
                Z = sum(rate[pid] * self._minutes_share(scen_all[pid][1]) for pid in squad)
                if Z <= 0:
                    continue
                dlog = self._opp_log_spread(s, snap)
                for pid, info in squad.items():
                    sc, Em, pplay, ps_start = scen_all[pid]
                    if pplay < 0.15:
                        continue
                    sigma = float(np.sqrt(self.sigma_team ** 2 + post[pid].cv ** 2))
                    u = self._draws(sigma)
                    mus = np.array([mu_team[s] * rate[pid] * self._minutes_share(m) / Z for _, m in sc])
                    probs = np.array([pr for pr, _ in sc])
                    expected = float(np.sum(probs * mus))
                    contrib = dict(grp[s])
                    Em_c = Em / max(pplay, 1e-3) if self.cond_play else Em      # minutes if he plays (docs/27)
                    contrib["minutes"] = float(np.log(max(Em_c, 1.0) / 70.0))
                    contrib["role"] = float(np.log(max(post[pid].mean, 1e-6) / self.rho[s][info["pos"]]))
                    if opp_pos_f[pid] != 1.0:
                        contrib["opp_role"] = float(np.log(opp_pos_f[pid]))
                    g = info["g"]; ap = g[g["minutes"] > 0]
                    # HIS USUAL, BUILT THE SAME WAY AS HIS FORECAST.
                    #
                    # `edge = p - p_usual` ranks the whole feed, is the "-6 pts" chip on every card
                    # and, with personal_lines on, is what the tier itself is graded on. It is a
                    # DIFFERENCE, so it is only as good as the two sides being the same object.
                    # They were not. `mus` above is the player's share of a TEAM TOTAL, normalised
                    # by Z; this line used to be his raw per-90 rate with no normalisation at all,
                    # and the two rates were separately shrunk -- one a share of the team total with
                    # the prior in team-stat units, one a per-90 rate with a flat prior of 4. So the
                    # difference carried a fixed personal offset that never changed between
                    # fixtures, on top of whatever the opponent did.
                    #
                    # Measured (scripts/measure/departure_calibration.py): the opponent can only
                    # reach a player through the team total, so within one club every player's
                    # departure must be the SAME number. It was not -- the share of departure
                    # variance that was genuinely the fixture ran 91% for shots, 95% for tackles and
                    # 59% for shots on target, which has the worst prior mismatch of the three.
                    # Four in ten points of a sot card's "above his usual" were an artefact.
                    #
                    # Now it is `mus` with the fixture set to average: the club's own usual total,
                    # his own share of it, the same minutes and the SAME Z. Z and the minutes cancel
                    # in the ratio, so the departure is log(mu_team / mu_usual) exactly -- a
                    # club-level quantity, which is what the model actually knows. The one per-player
                    # term that survives is opp_pos_f, the opponent's concession to his position,
                    # which is the only legitimate player-specific opponent signal here (and is off
                    # by default: engine.opp_pos_k).
                    mus_b = np.array([mu_usual[s] * post[pid].mean * self._minutes_share(m) / Z
                                      for _, m in sc])
                    reasons = self._player_reasons(contrib, grp[s], s, opp_tac)
                    thrs_p, thr_own = PLAYER_THR[s], None
                    mu_usual_p = float(np.sum(probs * mus_b))      # his own count in this match's minutes
                    if self.personal_lines:                        # docs/52: his own 50% line, not one line for every player
                        k_own = personal_k(lambda k: float(np.sum(probs * nb_sf(k, mus_b, self.r_player[s]))))
                        thrs_p = personal_thrs(k_own, self.personal_spread)
                        thr_own = float(k_own) - 0.5
                    for thr in thrs_p:
                        k = int(np.floor(thr)) + 1
                        pdraw = np.sum(probs[:, None] * nb_sf(k, mus[:, None] * u[None, :], self.r_player[s]), axis=0)
                        p = float(np.sum(probs * nb_sf(k, mus, self.r_player[s])))
                        lo, hi = np.percentile(pdraw, [10, 90])
                        last = ap[s].values[-10:]
                        last40 = ap[s].values[-40:]
                        # docs/62: the same forty appearances, weighted by how recent they are.
                        # The flat count beside this one is kept for DISPLAY -- "19 of his last 20"
                        # has to stay a pair of whole games a reader can check against the strip --
                        # but as an input to the number it was the one layer in the engine that did
                        # not decay at all: a game thirty-nine appearances ago counted as much as
                        # last week's, at up to 40% of the final number.
                        # n_eff is Kish's effective sample size, (sum w)^2 / sum w^2, NOT sum w:
                        # the anchor's own weight is n/(n+K), so using the raw weight total would
                        # claim more games behind the rate than the weighting actually leaves.
                        _w40 = recency_weights(len(last40), self.player_hl) if len(last40) else None
                        if _w40 is not None and float(_w40.sum()) > 0:
                            _cl = (last40 > thr).astype(float)
                            _sw, _sw2 = float(_w40.sum()), float((_w40 * _w40).sum())
                            rec_rate = float((_w40 * _cl).sum() / _sw)
                            rec_neff = float(_sw * _sw / _sw2) if _sw2 > 0 else None
                        else:
                            rec_rate = rec_neff = None
                        p_raw = float((last > thr).mean()) if len(last) else 0.5
                        p_base = float(np.sum(probs * nb_sf(k, mus_b, self.r_player[s])))
                        lo, hi = float(lo), float(hi)
                        # docs/56: the opponent reaches a player through mu_team, so the span is measured by moving
                        # the whole expectation over the league's range of defences, mixture and all.
                        s_hi = float(np.sum(probs * nb_sf(k, mus * np.exp(dlog), self.r_player[s]))) if dlog > 1e-6 else None
                        s_lo = float(np.sum(probs * nb_sf(k, mus * np.exp(-dlog), self.r_player[s]))) if dlog > 1e-6 else None
                        span = abs(s_hi - s_lo) if dlog > 1e-6 else None
                        if self.cond_play:                  # divide out the chance to play: "if he plays" (docs/27)
                            d = max(float(pplay), 1e-3)
                            p, lo, hi, p_base = (min(v / d, 0.999) for v in (p, lo, hi, p_base))
                            if span is not None:            # the span is in the same units as p, so it scales with it
                                span = min(span / d, 1.0)
                                s_lo, s_hi = min(s_lo / d, 1.0), min(s_hi / d, 1.0)
                            expected_c = expected / d
                        else:
                            expected_c = expected
                        out.append(Forecast("player", team, opp, s, thr, expected_c, p, float(lo), float(hi),
                                            player=int(pid), pos=info["pos"], p_play=float(likely_play.get(pid, pplay)),
                                            confirmed=lineups.get(team) is not None, contrib=contrib,
                                            reasons=reasons, opp_tactics=opp_tac, own_tactics=own_tac,
                                            opp_key_players=keys[s], p_raw=p_raw, p_base=p_base,
                                            rotation=rot[team][0], rotation_why=rot[team][1],
                                            p_play_usual=usual_ps.get(pid), p_usual=p_base,
                                            rec_k=int((last40 > thr).sum()), rec_n=int(len(last40)),
                                            rec_rate=rec_rate, rec_neff=rec_neff,
                                            thr_personal=thr_own, span=span, span_lo=s_lo, span_hi=s_hi,
                                            p_start=float(ps_start),
                                            starts_recent=info.get("starts_recent"),
                                            club_recent=info.get("club_recent"),
                                            starts_share=info.get("starts_share"),
                                            missed_recent=int(info.get("missed", 0)),
                                            doubtful=bool(info.get("doubtful")),
                                            expected_usual=(mu_usual_p / max(float(pplay), 1e-3)) if self.cond_play else mu_usual_p))
        mh, ma = (1.0, 1.0)
        if self.match_context and match_ctx:
            mh, ma = context_multipliers(match_ctx.get(home) or {}, match_ctx.get(away) or {})
        xh, xa = self._xg_mults(home, away)                      # expected goals in the strength model (docs/37)
        probs = self.dc.outcome_probs(home, away, mult_h=mh * xh, mult_a=ma * xa)
        probs["context"] = {"mult_home": round(mh, 4), "mult_away": round(ma, 4)}
        if (xh, xa) != (1.0, 1.0):
            probs["context"]["xg_home"] = round(xh, 4)
            probs["context"]["xg_away"] = round(xa, 4)
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
