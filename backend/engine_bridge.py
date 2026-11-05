"""engine_bridge.py -- Mongo in, forecasts out. Runs the soccer_brain engine for one league.

Setup (see 09_engine_integration.md):
  * Copy the `engine/` folder next to this file as `soccer_brain/` (flat modules).
  * Do NOT add __init__.py to the parent. The engine imports flat: `from core import ...`.
  * pip install numpy scipy pandas
"""
from __future__ import annotations

import os
import sys
import uuid
from datetime import timedelta

import numpy as np
import pandas as pd

import settings_store as S
from cached_fetch import utcnow

_ENGINE_DIR = os.environ.get("SOCCER_BRAIN_DIR") or os.path.join(os.path.dirname(__file__), "soccer_brain")
if _ENGINE_DIR not in sys.path:
    sys.path.insert(0, _ENGINE_DIR)

import engine as E            # noqa: E402  (soccer_brain/engine.py)
import context as CX          # noqa: E402  (soccer_brain/context.py)
from core import tier         # noqa: E402
import calibration as CAL
import tiering as TI     # noqa: E402  (backend/calibration.py)
import availability as AV     # noqa: E402  (backend/availability.py)
import match_context as MC    # noqa: E402  (backend/match_context.py)

MARKET_COVERAGE = {"player.shots": "player_match_stats.shots", "player.sot": "player_match_stats.sot",
                   "player.tackles": "player_match_stats.tackles", "team.corners": "team_match_stats.corners",
                   "team.shots": "team_match_stats.shots", "team.sot": "team_match_stats.sot"}
# Total goals in the match come from the team-strength model, not from the statistics feed, so they need no
# coverage check: a finished match always has a score (docs/39).
NO_COVERAGE_MARKETS = ("team.goals",)
TEAM_REQUIRED = ["shots", "sot", "corners", "tackles", "poss", "shots_against", "corners_against", "tackles_against"]
PLAYER_REQUIRED = ["minutes", "shots", "sot", "tackles", "team_shots", "team_sot", "team_tackles"]


# ------------------------------------------------------------------ frames
def build_frames(db, league_iid: int, history_rounds: int):
    ms = pd.DataFrame(list(db.matches.find({"league_iid": league_iid, "status": "final", "round": {"$ne": None},
                                            "ingested_at": {"$ne": None}},
                                           {"_id": 0, "iid": 1, "round": 1, "home_iid": 1, "away_iid": 1, "hg": 1, "ag": 1})))
    if ms.empty:
        return None
    ms = ms.rename(columns={"iid": "game_id", "home_iid": "home", "away_iid": "away"})
    ms = ms[ms["round"] > ms["round"].max() - history_rounds]
    ids = set(ms["game_id"])

    tg = pd.DataFrame(list(db.team_match_stats.find({"match_iid": {"$in": list(ids)}}, {"_id": 0})))
    tg = tg.rename(columns={"match_iid": "game_id", "team_iid": "team", "opp_iid": "opp"})
    tg["home"] = tg["home"].astype(int)
    tg = tg.merge(ms[["game_id", "round"]], on="game_id")
    tg = tg.dropna(subset=TEAM_REQUIRED)
    ok = tg.groupby("game_id")["team"].transform("count") == 2        # keep matches with both sides complete
    tg = tg[ok]
    ms = ms[ms["game_id"].isin(set(tg["game_id"]))]

    pg = pd.DataFrame(list(db.player_match_stats.find({"match_iid": {"$in": list(set(tg["game_id"]))}}, {"_id": 0})))
    excl = set(S.get(db, "engine.exclude_positions"))
    pg = pg.rename(columns={"match_iid": "game_id", "team_iid": "team", "opp_iid": "opp", "player_iid": "player"})
    pg = pg[pg["pos"].notna() & ~pg["pos"].isin(excl)]
    pg = pg.dropna(subset=PLAYER_REQUIRED)
    pg = pg.merge(ms[["game_id", "round"]], on="game_id")
    pg["started"] = pg["started"].astype(int)
    for c in ("team", "opp", "player"):
        pg[c] = pg[c].astype(int)
    for c in ("team", "opp"):
        tg[c] = tg[c].astype(int)
    return ms.reset_index(drop=True), tg.reset_index(drop=True), pg.reset_index(drop=True)


# ----------------------------------------------------------------- engine
def configure_engine(db) -> E.SoccerEngine:
    """Constants are module-level in the engine: mutate in place, before fit()."""
    auto = bool(S.get(db, "engine.auto_lines"))
    pk, tk = ("engine.player_ladder", "engine.team_ladder") if auto else ("engine.player_thresholds", "engine.team_thresholds")
    E.PLAYER_THR.clear(); E.PLAYER_THR.update({k: list(v) for k, v in S.get(db, pk).items()})
    E.TEAM_THR.clear(); E.TEAM_THR.update({k: list(v) for k, v in S.get(db, tk).items()})
    eng = E.SoccerEngine(interactions=S.get(db, "engine.interactions"),
                         lineup=False,                                   # LOCKED off: see 03_rules_and_compliance.md
                         half_life_rounds=float(S.get(db, "engine.half_life_rounds")),
                         style_k=float(S.get(db, "engine.style_k")),
                         n_draws=int(S.get(db, "engine.n_draws")),
                         sigma_team=float(S.get(db, "engine.sigma_team")), seed=0,
                         strength_decay=float(S.get(db, "engine.strength_decay")),
                         # normalised averages (docs/25)
                         style_half_life=(float(S.get(db, "engine.style_half_life")) or None),
                         ratings_blend=float(S.get(db, "engine.ratings_blend")),
                         style_opp_adjust=tuple(S.get(db, "engine.style_opp_adjust")),
                         style_cap_q=(float(S.get(db, "engine.style_cap_q")) or None),
                         player_prior=dict(S.get(db, "engine.player_prior")),
                         cond_play=bool(S.get(db, "engine.condition_on_play")),     # "if he plays" (docs/27)
                         minutes_floor=float(S.get(db, "engine.minutes_floor")),     # docs/58

                         # docs/37 upgrades. Each default is off; switch one on only after engine_ab.py passes it.
                         script_v2=bool(S.get(db, "engine.script_v2")),
                         fit_player_r=bool(S.get(db, "engine.fit_player_r")),
                         # docs/52: each player and team gets its own line
                         personal_lines=bool(S.get(db, "engine.personal_lines")),
                         personal_spread=int(S.get(db, "engine.personal_spread")),
                         opp_pos_k=float(S.get(db, "engine.opp_pos_k") or 0.0),
                         xg_blend=float(S.get(db, "engine.xg_blend") or 0.0))
    eng.r_player = dict(S.get(db, "engine.r_player"))      # fit_player_r replaces these during fit() when it is on
    eng.absence = bool(S.get(db, "engine.absence_model"))              # missed recent matches -> likely out (docs/22)
    eng.match_context = bool(S.get(db, "engine.match_context"))        # results form and stakes on expected goals (docs/22)
    eng.likely_starter_p = float(S.get(db, "engine.likely_starter_p"))   # likely starters get full minutes, no chance-to-play discount
    return eng


def enabled_markets(db, league_iid: int) -> dict:
    """market -> bool. Off if the admin switched it off OR its data coverage is too thin."""
    floor = S.get(db, "engine.coverage_min")
    flags = S.get(db, "engine.markets_enabled")
    out = {}
    for m, field in MARKET_COVERAGE.items():
        cov = db.data_coverage.find_one({"league_iid": league_iid, "field": field})
        out[m] = bool(flags.get(m, True)) and bool(cov) and cov["share"] >= floor
    for m in NO_COVERAGE_MARKETS:
        out[m] = bool(flags.get(m, True))
    return out


STAT_LABEL = {"shots": ("shot", "shots"), "sot": ("shot on target", "shots on target"), "tackles": ("tackle", "tackles"),
              "corners": ("corner", "corners"), "fouls": ("foul", "fouls"), "yellow": ("yellow card", "yellow cards"),
              "goals": ("goal", "goals"), "match_goals": ("goal", "goals")}


def label_for(db, scope, stat, thr, labels) -> str:
    """Words for a line. An admin label in copy.market_labels wins; otherwise the words are built (docs/25)."""
    key = f"{stat}:{thr:g}" if scope == "player" else f"team_{stat}:{thr:g}"
    if key in labels:
        return labels[key]
    if scope == "team" and f"{stat}:{thr:g}" in labels and stat != "shots":
        return labels[f"{stat}:{thr:g}"]
    n = int(np.floor(thr)) + 1
    one, many = STAT_LABEL.get(stat, (stat, stat))
    if stat == "match_goals":
        return f"{n}+ {one if n == 1 else many} in the match"
    return f"{n}+ {one if n == 1 else many}"


def select_lines(docs: list[dict], band, max_lines: int) -> list[dict]:
    """Automatic lines (docs/25): per player (or team) and stat, keep only lines whose likelihood sits inside `band`,
    and of those the `max_lines` **most likely**.

    This used to keep the most ambitious lines instead -- the highest thresholds in the band. That threw away the
    near-certain end of every ladder before it ever reached the database: a striker with 1+ shot at 95% showed
    "4+ shots 52%, 5+ 40%, 6+ 26%" and his 1+ and 2+ lines existed nowhere in the app (docs/44). It is the wrong
    way round for the people this app is for, who want to know what is close to certain, and it quietly undid
    docs/39, which had widened the band precisely so that 90%+ lines could exist.

    Ambition is now the band's job: `engine.line_band`'s lower end decides how far down the ladder we are willing
    to go, and this keeps the likeliest of whatever that leaves. The whole ladder is still stored on every line,
    so the Finder can still answer any threshold the band excluded.
    """
    lo, hi = float(band[0]), float(band[1])
    groups: dict = {}
    for d in docs:
        groups.setdefault((d["scope"], d["team_iid"], d.get("player_iid"), d["stat"]), []).append(d)
    out = []
    for g in groups.values():
        personal = [d for d in g if d.get("is_personal")]
        if personal:
            # docs/52: the band was a way of guessing where a line is worth reading. When the entity has
            # its own line there is nothing to guess, so the band does not apply to it -- it IS the answer.
            rest = sorted((d for d in g if not d.get("is_personal") and lo <= d["p"] <= hi),
                          key=lambda d: abs(d["p"] - 0.5))
            keep = (personal + rest)[:max_lines]
        else:
            # -p first, then -thr: of two lines equally likely, the more ambitious one is worth more to the reader
            keep = sorted((d for d in g if lo <= d["p"] <= hi), key=lambda d: (-d["p"], -d["thr"]))[:max_lines]
        ladder = {f"{d['thr']:g}": round(float(d["p"]), 4) for d in g}   # the whole ladder, so the Finder can answer any line
        for d in keep:
            d["ladder"] = ladder
        out += keep
    return out


def _goal_lines(db, m, probs, run_id, now, labels, usual=None) -> list[dict]:
    """Total goals in the match, read off the team-strength model's own scoreline matrix (docs/39).

    No statistics feed is involved, so this market works in a league where shots or tackles are missing, and the
    draw correction and match context are already inside the numbers. The band in engine.line_band applies, as for
    every other line."""
    tot = (probs or {}).get("totals") or {}
    if not tot:
        return []
    ladder = {str(k): round(float(v), 4) for k, v in tot.items()}
    out = []
    # the same source every other team line uses: configure_engine filled it from the ladder, or from the fixed
    # thresholds when engine.auto_lines is off, so this market follows that switch too
    for thr in E.TEAM_THR.get("goals", []):
        p = tot.get(f"{float(thr):g}")
        if p is None:
            continue
        p = float(min(max(p, 0.0), float(S.get(db, "engine.p_cap"))))
        pu = (usual or {}).get(f"{float(thr):g}")                 # the same line in an average fixture here
        pu = float(min(max(pu, 0.0), 1.0)) if pu is not None else None
        lo, hi = max(0.0, p - 0.06), min(1.0, p + 0.06)       # the strength model's own spread, as for the 1x2
        out.append({"id": str(uuid.uuid4()), "fkey": f"{m['iid']}:team:{m['home_iid']}:0:match_goals:{float(thr):g}",
                    "run_id": run_id, "match_iid": m["iid"], "league_iid": m["league_iid"], "kickoff": m["kickoff"],
                    "scope": "team", "team_iid": int(m["home_iid"]), "opp_iid": int(m["away_iid"]), "player_iid": None, "pos": None,
                    "stat": "match_goals", "thr": float(thr), "market": label_for(db, "team", "match_goals", float(thr), labels),
                    "expected": float(probs.get("xg_home", 0) + probs.get("xg_away", 0)),
                    "p": p, "lo": float(lo), "hi": float(hi), "p_model": p, "p_pre_anchor": p,
                    "rec_k": None, "rec_n": None, "state": "pre", "calibration": None,
                    "p_play": 1.0, "lineup_confirmed": False, "lineup_badge": None, "p_basis": "all",
                    "tier": None, "tier_basis": "team", "tier_note": None,
                    "p_usual": pu, "edge": (p - pu) if pu is not None else 0.0,
                    "reasons": [], "opp_tactics": [], "own_tactics": [], "opp_key_players": [], "contrib": {},
                    "rotation": None, "rotation_why": None, "p_play_usual": None, "p_raw": p, "p_base": p,
                    # docs/52: a match total belongs to the fixture, not to one team, so "the count this entity
                    # usually manages" has no meaning here. The keys exist so every line has the same shape.
                    "thr_personal": None, "is_personal": False, "expected_usual": None,
                    # docs/56: a match total has no single opponent to be sensitive to, so its span is unknown
                    # rather than small. Unknown is never treated as trivial.
                    "span": None, "p_start": None,
                    "ladder": ladder, "model": "strength", "is_current": True, "hidden": False, "created_at": now})
    return out


def run_league(db, league_iid: int, now=None) -> dict:
    now = now or utcnow()
    run_id = str(uuid.uuid4())
    run = {"run_id": run_id, "league_iid": league_iid, "started_at": utcnow(), "status": "running"}   # real clock: jobs.py compares it with ingest times
    db.engine_runs.insert_one(dict(run))

    markets = enabled_markets(db, league_iid)
    if not any(markets.values()):
        db.engine_runs.update_one({"run_id": run_id}, {"$set": {"status": "skipped", "note": "no market has enough data coverage",
                                                                 "finished_at": utcnow()}})
        return {"run_id": run_id, "status": "skipped", "forecasts": 0}
    frames = build_frames(db, league_iid, int(S.get(db, "engine.history_rounds")))
    if frames is None:
        db.engine_runs.update_one({"run_id": run_id}, {"$set": {"status": "skipped", "note": "no data", "finished_at": utcnow()}})
        return {"run_id": run_id, "status": "skipped", "forecasts": 0}
    ms, tg, pg = frames
    if len(ms) < 20:
        db.engine_runs.update_one({"run_id": run_id}, {"$set": {"status": "skipped", "note": "fewer than 20 matches", "finished_at": utcnow()}})
        return {"run_id": run_id, "status": "skipped", "forecasts": 0}

    eng = configure_engine(db)
    as_of = int(ms["round"].max()) + 1
    eng.fit(ms, tg, pg, as_of)

    # --- calendar context: who may rest, and (if the held-out test passes) who is expected to start
    cal, gate = None, None
    if S.get(db, "context.enabled"):
        team_ids = set(int(t) for t in eng.teams)
        cal = build_calendar(db, team_ids, now)
        gate = fit_start_model(db, league_iid, ms, pg, cal)
        eng.set_start_model(gate["model"], enabled=(gate["mode"] == "on" or gate["passed"]))
        db.engine_gates.insert_one({"league_iid": league_iid, "run_id": run_id, "layer": "start_model", "mode": gate["mode"],
                                    "passed": gate["passed"], "applied": bool(eng.start_on), "n_train": gate["n_train"],
                                    "n_test": gate["n_test"], "gain": gate["gain"], "se": gate["se"], "z": gate["z"],
                                    "reason": gate["reason"], "coefficients": gate["model"].coefficients() if gate["model"] else {},
                                    "at": now})

    # the same goal lines in an average fixture here, so each one can show its lift over usual (docs/39)
    goal_usual = eng.dc.baseline_totals() if getattr(eng, "dc", None) is not None else {}

    # --- team styles and tactic labels (for the Matchup and Team pages)
    snap = eng.snaps[as_of]
    z = eng.tactic_labels(snap)
    for t in eng.teams:
        i = eng.tidx[t]
        db.team_styles.update_one({"league_iid": league_iid, "team_iid": int(t), "as_of": as_of},
                                  {"$set": {"style": [float(x) for x in snap[0][i]],
                                            "tactic_z": {k: float(v[i]) for k, v in z.items()},
                                            "tactics": [k for k, v in z.items() if v[i] >= 1.0], "at": now}}, upsert=True)

    window = S.get(db, "engine.window_days")
    upcoming = list(db.matches.find({"league_iid": league_iid, "status": "scheduled",
                                     "kickoff": {"$gte": now - timedelta(hours=1), "$lte": now + timedelta(days=window)}}))
    strong = tuple(S.get(db, "engine.tier_strong")); solid = tuple(S.get(db, "engine.tier_solid"))
    labels = S.get(db, "copy.market_labels")
    likely_gate = float(S.get(db, "engine.likely_starter_p"))
    min_play = float(S.get(db, "engine.min_p_play")); cond = bool(S.get(db, "engine.condition_on_play"))
    min_start = float(S.get(db, "engine.min_p_start"))   # docs/55: a regular substitute features in nearly every
                                                         # match, so a gate on the chance to FEATURE never catches him
    auto_lines = bool(S.get(db, "engine.auto_lines"))
    line_band = S.get(db, "engine.line_band"); max_lines = int(S.get(db, "engine.max_lines_per_stat"))
    earned = S.get(db, "engine.tier_mode") == "earned"
    rec = TI.Record(db, min_n=int(S.get(db, "engine.earned_min_n")), k=float(S.get(db, "engine.earned_prior_k"))) if earned else None
    strong_lineup = bool(S.get(db, "engine.strong_needs_lineup"))
    anchor = bool(S.get(db, "engine.player_anchor")); anchor_min = int(S.get(db, "engine.anchor_min_games"))
    anchor_k = float(S.get(db, "engine.anchor_k")); anchor_w = float(S.get(db, "engine.anchor_max_w")); p_cap = float(S.get(db, "engine.p_cap"))
    pmap = CAL.current(db)         # raw likelihood -> the percentage people see (docs/21); None = off
    lgdoc = db.leagues.find_one({"iid": league_iid}, {"_id": 0}) or {"iid": league_iid}
    lctx = MC.league_context(db, lgdoc, now) if S.get(db, "engine.match_context") else {}   # results form and stakes (docs/22)
    import team_norm as TN
    cn = TN.build(db, league_iid, "corners", half=float(S.get(db, "engine.style_half_life")) or 20.0) if "corners" in eng.stats else None
    n_f = 0
    for m in upcoming:
        h, a = m["home_iid"], m["away_iid"]
        if h not in eng.tidx or a not in eng.tidx:
            db.ingest_issues.insert_one({"at": now, "kind": "team_not_in_history", "detail": str(m["ext_id"]), "resolved": False})
            continue
        lineups = {}
        for team in (h, a):
            rows = list(db.lineups.find({"match_iid": m["iid"], "team_iid": team, "started": True, "confirmed": True}, {"player_iid": 1}))
            if len(rows) >= 11:
                lineups[team] = {r["player_iid"] for r in rows}
        ctx = context_for_match(cal, m) if cal is not None else None
        avail = AV.for_match(db, (h, a), m["kickoff"])                  # injuries and suspensions (feed or admin)
        mctx = {t: lctx.get(t) for t in (h, a) if lctx.get(t)}
        tnorm = ({t: {"corners": cn.predict(t, o), "corners_usual": cn.usual(t)} for t, o in ((h, a), (a, h))}
                 if cn is not None and cn.cnt >= 20 else None)       # normalised corner averages (opponent-adjusted)
        fcs, probs = eng.predict_fixture(h, a, lineups, ctx=ctx, availability=avail, match_ctx=mctx, team_norm=tnorm)
        for t in (h, a):
            if lctx.get(t):
                c_ = lctx[t]
                db.match_context.update_one({"match_iid": m["iid"], "team_iid": int(t)},
                                            {"$set": {"league_iid": league_iid, "form_fp": c_["fp"], "stakes": {k: c_[k] for k in ("dead", "rel", "race")},
                                                      "games_left": c_["left"], "context_why": c_["why"], "at": now}}, upsert=True)
        if ctx:
            for team, c in ctx.items():
                level = CX.pressure_level(CX.rotation_pressure(c))
                db.match_context.update_one({"match_iid": m["iid"], "team_iid": int(team)},
                                            {"$set": {"league_iid": league_iid, "level": level,
                                                      "why": E.SoccerEngine._rotation_sentence(c, CX.pressure_parts(c)),
                                                      "rest_days": c["rest_days"], "next_gap": c["next_gap"],
                                                      "next_comp": c["next_comp"], "n14": c["n14"], "at": now}}, upsert=True)
        db.match_probs.update_many({"match_iid": m["iid"], "is_current": True}, {"$set": {"is_current": False}})
        db.match_probs.insert_one({"match_iid": m["iid"], "run_id": run_id, "is_current": True, "at": now, **probs})
        goal_lines = _goal_lines(db, m, probs, run_id, now, labels, goal_usual) if markets.get("team.goals") else []
        kept = {d["fkey"]: d for d in db.forecasts.find({"match_iid": m["iid"], "is_current": True, "hidden": True},
                                                         {"_id": 0, "fkey": 1, "hidden_reason": 1, "hidden_by": 1, "hidden_at": 1})}
        before = {d["fkey"]: d for d in db.forecasts.find({"match_iid": m["iid"]}, {"_id": 0, "fkey": 1, "p": 1, "created_at": 1, "p_prev": 1, "p_prev_at": 1})}
        docs = []
        for f in fcs:
            mk = f"{f.scope}.{f.stat}"
            if not markets.get(mk, False):
                continue
            confirmed = True if f.scope == "team" else bool(f.confirmed)
            state = "lineup" if (f.confirmed if f.scope == "player" else lineups.get(f.team)) else "pre"
            p = CAL.apply(pmap, f.p, state, f.scope); lo = CAL.apply(pmap, f.lo, state, f.scope); hi = CAL.apply(pmap, f.hi, state, f.scope)
            p_pre_anchor = p
            # Lineup badge (docs/27). A player's percentage is "if he plays"; whether he plays is the badge.
            #   confirmed: in the announced eleven   bench: lineup out, he is not in it
            #   likely:    chance to play >= likely_starter_p before lineups (Solid and Strong allowed)
            #   unsure:    anything else (Watch at most)
            if f.scope == "team":
                badge = None
            elif state == "lineup":
                badge = "confirmed" if float(f.p_play) >= 0.999 else "bench"
            else:
                badge = "likely" if float(f.p_play) >= likely_gate else "unsure"
            # His own record counts (docs/32), but only when he is expected to start: the record comes mostly from
            # starts, so for a substitute it pulled a short-minutes chance far above the model (docs/36 H9).
            if anchor and badge in ("confirmed", "likely") and f.rec_n is not None and f.rec_n >= anchor_min:
                p, lo, hi = TI.anchor(p, lo, hi, f.rec_k, f.rec_n, anchor_k, anchor_w, p_cap)
            if cond and badge == "unsure" and float(f.p_play) < min_play:
                continue                                         # rarely plays: no card, however high the "if he plays" number
            # docs/55: measured over 165 players, the median chance to feature is 0.93 in every class, including
            # fringe players whose chance to start is 0.41 -- so min_p_play lets them through and their card is then
            # built from a 46-minute blend and shown beside a strip of starts. This gate asks the right question.
            if min_start > 0 and badge == "unsure" and f.p_start is not None and float(f.p_start) < min_start:
                continue
            # docs/52: is this the entity's own half-way line, or one of the neighbours kept for the Finder?
            is_own = f.thr_personal is not None and abs(float(f.thr) - float(f.thr_personal)) < 1e-9
            p_usual_raw = CAL.apply(pmap, f.p_usual, state, f.scope) if f.p_usual is not None else None
            solid_ok = badge in (None, "confirmed", "likely")
            basis = {None: "team", "confirmed": "lineup", "likely": "likely_starter"}.get(badge, "pre")
            if earned:                                           # docs/31: the label is earned from the whole chance and our results
                t, tier_note = TI.assign(db, rec, {"p": p, "lo": lo, "hi": hi, "scope": f.scope, "stat": f.stat,
                                                   "p_play": float(f.p_play), "lineup_badge": badge,
                                                   # docs/52: the departure tier needs to know which rung this is
                                                   "is_personal": is_own, "p_usual": p_usual_raw}, strong_lineup)
            else:
                t = tier(p, lo, solid_ok, strong=strong, solid=solid)
                t_full = tier(p, lo, True, strong=strong, solid=solid)
                tier_note = ("On the bench: Watch only" if badge == "bench" else "Watch until lineups are out") if (not solid_ok and t_full != t) else None
            # docs/52: with personal lines on, only the entity's own rung is a forecast worth grading. The
            # neighbours exist so the Finder can answer "what about 2+?" -- they are not insights, and if they
            # keep a tier the feed falls back to them the moment the entity's own line has nothing to say,
            # which is exactly the near-certain card this change exists to stop.
            if f.thr_personal is not None and not is_own:
                t, tier_note = None, None
            p_usual = p_usual_raw
            fkey = f"{m['iid']}:{f.scope}:{f.team}:{f.player or 0}:{f.stat}:{f.thr:g}"
            docs.append({"id": str(uuid.uuid4()), "fkey": fkey, "run_id": run_id, "match_iid": m["iid"], "league_iid": league_iid,
                         "kickoff": m["kickoff"], "scope": f.scope, "team_iid": int(f.team), "opp_iid": int(f.opp),
                         "player_iid": int(f.player) if f.player is not None else None, "pos": f.pos,
                         "stat": f.stat, "thr": float(f.thr), "market": label_for(db, f.scope, f.stat, f.thr, labels),
                         "expected": float(f.expected), "p": float(p), "lo": float(lo), "hi": float(hi),
                         "p_model": float(f.p), "p_pre_anchor": float(p_pre_anchor), "rec_k": f.rec_k, "rec_n": f.rec_n, "state": state, "calibration": (pmap or {}).get("version"),
                         "p_play": float(f.p_play), "lineup_confirmed": confirmed, "lineup_badge": badge,
                         "p_basis": "played" if (cond and f.scope == "player") else "all", "tier": t,
                         "tier_basis": basis, "tier_note": tier_note,
                         "p_usual": p_usual, "edge": (float(p) - p_usual) if p_usual is not None else 0.0,
                         "reasons": list(f.reasons), "opp_tactics": list(f.opp_tactics), "own_tactics": list(f.own_tactics),
                         "opp_key_players": [[int(p), float(v)] for p, v in f.opp_key_players],
                         "contrib": {k: round(float(v), 4) for k, v in f.contrib.items()},
                         "rotation": f.rotation, "rotation_why": f.rotation_why, "p_play_usual": f.p_play_usual,
                         "p_raw": f.p_raw, "p_base": f.p_base, "is_current": True, "hidden": False, "created_at": now,
                         # docs/52: the entity's own 50% line, and the count it manages in its usual game
                         # docs/56: how far this rung's likelihood moves across the league's range of opponents
                         "span": (float(f.span) if f.span is not None else None),
                         "p_start": (float(f.p_start) if f.p_start is not None else None),
                         "thr_personal": (float(f.thr_personal) if f.thr_personal is not None else None),
                         "is_personal": (f.thr_personal is not None and abs(float(f.thr) - float(f.thr_personal)) < 1e-9),
                         "expected_usual": (float(f.expected_usual) if f.expected_usual is not None else None)})
        docs += goal_lines
        if auto_lines:
            docs = select_lines(docs, line_band, max_lines)
        for d in docs:   # an admin's Hide survives the next run
            if d["fkey"] in kept:
                d.update(kept[d["fkey"]], hidden=True)
            old = before.get(d["fkey"])   # keep the last real move so the feed can say "rose from 66% to 78%"
            if old and abs(old.get("p", d["p"]) - d["p"]) >= 0.005:
                d["p_prev"], d["p_prev_at"] = float(old["p"]), old.get("created_at")
            elif old and old.get("p_prev") is not None:
                d["p_prev"], d["p_prev_at"] = old["p_prev"], old.get("p_prev_at")
        if docs:
            db.forecasts.insert_many(docs)
        # one row per forecast: the new run replaces every earlier row for this match (no duplicates, ever)
        db.forecasts.delete_many({"match_iid": m["iid"], "run_id": {"$ne": run_id}})
        n_f += len(docs)
    import cards_model as CM   # separate yellow-card model (owner's choice: soccer_brain untouched)
    n_f += CM.run_league(db, league_iid, run_id, now)
    db.engine_runs.update_one({"run_id": run_id}, {"$set": {"status": "done", "finished_at": utcnow(), "as_of": as_of,
                                                             "matches_in_fit": int(len(ms)), "fixtures": len(upcoming), "forecasts": n_f}})
    return {"run_id": run_id, "status": "done", "forecasts": n_f, "fixtures": len(upcoming)}


# ------------------------------------------------------- calendar and rotation
def import_calendar(db, rows, source: str = "import") -> dict:
    """Upsert matches of ANY competition a club plays (cups, Europe). One row per club per match:
    {team_iid, kickoff, comp, stage?}. `comp` is a key of context.importance (league, ucl, uel, uecl, fa_cup,
    league_cup, domestic_cup, super_cup, friendly, other). League matches of tracked leagues are read from
    `matches` and need not be imported."""
    n = 0
    for r in rows:
        comp = str(r.get("comp") or "other")
        db.club_calendar.update_one({"team_iid": int(r["team_iid"]), "kickoff": r["kickoff"], "comp": comp},
                                    {"$set": {"stage": str(r.get("stage") or ""), "source": source, "at": utcnow()}}, upsert=True)
        n += 1
    return {"rows": n}


def build_calendar(db, team_iids, now=None):
    """context.Calendar for the given clubs: their league matches (from `matches`, every status, all tracked
    leagues) plus everything in `club_calendar`. Past rows cost nothing extra: they are already stored."""
    teams = [int(t) for t in team_iids]
    rows = []
    for m in db.matches.find({"$or": [{"home_iid": {"$in": teams}}, {"away_iid": {"$in": teams}}], "kickoff": {"$ne": None}},
                             {"_id": 0, "home_iid": 1, "away_iid": 1, "kickoff": 1}):
        for t in (m["home_iid"], m["away_iid"]):
            if t in teams:
                rows.append((int(t), m["kickoff"], "league", ""))
    for c in db.club_calendar.find({"team_iid": {"$in": teams}}, {"_id": 0}):
        rows.append((int(c["team_iid"]), c["kickoff"], c["comp"], c.get("stage", "")))
    df = pd.DataFrame(rows, columns=["team", "kickoff", "comp", "stage"])
    if df.empty:
        df = pd.DataFrame({"team": [], "kickoff": [], "comp": [], "stage": []})
    df = df.drop_duplicates(["team", "kickoff", "comp"])
    return CX.Calendar(df, table=S.get(db, "context.importance"))


def _ll(p, y):
    p = np.clip(p, 1e-4, 1 - 1e-4)
    return y * np.log(p) + (1 - y) * np.log(1 - p)


def fit_start_model(db, league_iid: int, ms, pg, cal) -> dict:
    """Learn how the calendar changes who starts, and decide with a held-out test whether to use it.

    Test: fit on the older matches, score the newest `context.holdout_share` of them. The model is used (in
    mode "auto") only if it beats the plain usual-start-rate by `context.gate_z` standard errors.
    Returns {model, passed, mode, n_train, n_test, gain, se, z, reason}."""
    mode = S.get(db, "context.start_model")
    out = {"model": None, "passed": False, "mode": mode, "n_train": 0, "n_test": 0, "gain": None, "se": None, "z": None, "reason": ""}
    if mode == "off" or not S.get(db, "context.enabled"):
        out["reason"] = "switched off"
        return out
    kick = {d["iid"]: d["kickoff"] for d in db.matches.find({"league_iid": league_iid}, {"iid": 1, "kickoff": 1})}
    rows = CX.prior_and_regularity(pg[["game_id", "round", "team", "player", "started"]].copy())
    parts = []
    for (gid, team), _ in rows.groupby(["game_id", "team"]):
        k = kick.get(gid)
        if k is None:
            continue
        c = cal.context(team, k, "league", "")
        d = CX.pressure_parts(c); d.update(game_id=gid, team=team)
        parts.append(d)
    if not parts:
        out["reason"] = "no kickoff times"
        return out
    rows = rows.merge(pd.DataFrame(parts), on=["game_id", "team"], how="inner")
    rows = rows[(rows["regular"] > 0) | (rows["started"] == 1)]
    rows = rows[rows["round"] >= rows["round"].min() + 8]
    if len(rows) < int(S.get(db, "context.min_rows")):
        out["reason"] = f"only {len(rows)} player-match rows"
        if mode != "on":
            return out
    cut = rows["round"].quantile(1.0 - float(S.get(db, "context.holdout_share")))
    tr, te = rows[rows["round"] <= cut], rows[rows["round"] > cut]
    if len(tr) < 200 or len(te) < 200:
        out["reason"] = "too few rows to test"
        if mode != "on":
            return out
        out["model"] = CX.StartModel().fit(rows)
        out["passed"] = True
        return out
    m = CX.StartModel().fit(tr)
    X = m.design(te, te["regular"].values)
    p1 = 1 / (1 + np.exp(-(m._logit(te["prior"].values) + X @ m.w)))
    y = te["started"].values.astype(float)
    d = _ll(p1, y) - _ll(te["prior"].values, y)
    se = float(d.std(ddof=1) / np.sqrt(len(d)))
    z = float(d.mean() / se) if se > 0 else 0.0
    passed = bool(d.mean() > 0 and z >= float(S.get(db, "context.gate_z")))
    out.update(n_train=int(len(tr)), n_test=int(len(te)), gain=float(d.mean()), se=se, z=z, passed=passed,
               reason="passed" if passed else "did not beat the plain start rate on held-out matches")
    out["model"] = CX.StartModel().fit(rows)            # final fit on everything
    return out


def context_for_match(cal, m) -> dict:
    """{team: calendar numbers} for both clubs of an upcoming fixture."""
    return {t: cal.context(t, m["kickoff"], "league", "") for t in (m["home_iid"], m["away_iid"])}


# --------------------------------------------------------------- scoring
def score_finished(db) -> int:
    """After results arrive: store what actually happened next to each forecast (feeds Track Record)."""
    n = 0
    cur = db.forecasts.find({"kickoff": {"$lt": utcnow()}, "is_current": True})
    for f in cur:
        if db.forecast_outcomes.find_one({"$or": [{"forecast_id": f["id"]}, {"fkey": f["fkey"]}]}):
            continue                                          # one outcome per forecast, even if old rows linger
        m = db.matches.find_one({"iid": f["match_iid"], "status": "final"})
        if not m or not m.get("ingested_at"):
            continue
        if f["scope"] == "player":
            if f["stat"] in ("yellow_cards", "red_cards") and not m.get("extras_at"):
                continue                                               # cards arrive with the match-extras call
            r = db.player_match_stats.find_one({"match_iid": f["match_iid"], "player_iid": f["player_iid"]})
            actual = (r or {}).get(f["stat"]) if r else 0.0           # did not play: 0 and flagged
            played = r is not None
        elif f["stat"] == "match_goals":
            actual = (m.get("hg") + m.get("ag")) if m.get("hg") is not None and m.get("ag") is not None else None
            played = True
        elif f["stat"] == "match_yellow_cards":
            rows = [r.get("yellow_cards") for r in db.team_match_stats.find({"match_iid": f["match_iid"]}, {"yellow_cards": 1})]
            actual = sum(rows) if len(rows) == 2 and None not in rows else None; played = True
        else:
            r = db.team_match_stats.find_one({"match_iid": f["match_iid"], "team_iid": f["team_iid"]})
            actual = (r or {}).get(f["stat"]); played = True
        if actual is None:
            continue
        db.forecast_outcomes.insert_one({"forecast_id": f["id"], "fkey": f["fkey"], "run_id": f["run_id"], "league_iid": f["league_iid"],
                                         "stat": f["stat"], "scope": f["scope"], "tier": f["tier"], "p": f["p"],
                                         "thr": f["thr"], "actual": float(actual), "reached": bool(actual > f["thr"]),
                                         "p_model": f.get("p_model", f["p"]), "state": f.get("state"),
                                         "player_played": played, "p_basis": f.get("p_basis", "all"), "p_play": f.get("p_play"),
                                         "lineup_badge": f.get("lineup_badge"), "kickoff": f.get("kickoff"), "scored_at": utcnow()})
        n += 1
    return n


def cleanup(db, now=None) -> dict:
    """Daily. Drop old forecasts whose outcome is already stored. Facts and outcomes are never deleted."""
    now = now or utcnow()
    cut = now - timedelta(days=int(S.get(db, "engine.keep_days")))
    ids = [o["forecast_id"] for o in db.forecast_outcomes.find({}, {"forecast_id": 1})]
    r = db.forecasts.delete_many({"kickoff": {"$lt": cut}, "id": {"$in": ids}})
    return {"forecasts_deleted": r.deleted_count}
