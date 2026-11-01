"""combo.py -- the combined chance of several lines in one match, and a suggested combo (docs/28).

Why this exists. People want to look at several forecasts for one match together. Multiplying the chances is
right only after the lineup is out. We tested it on 237,000 random combinations of 2, 3 and 4 lines from real
matches (StatsBomb 2015/16: Premier League, Serie A, Ligue 1; walk-forward; scripts in docs/validation):

                      real / multiplied, 2 lines   3 lines   4 lines
    after lineups            0.99                   1.00      1.01     -> multiply, nothing else
    before lineups           1.11                   1.19      1.25     -> multiply, then apply `combo.pre_factors`

Before lineups the multiplied number is low in every league (stable: 1.10 to 1.13 for 2 lines in each).
Two lines on the SAME player are not independent (1+ shot and 1+ on target happen together far more often than
the product says): their joint chance is the harder line times the easier line to the power 0.38 (log loss .632
against .662 for the plain product; docs/28 section 2).

A line's chance of happening is `p * p_play` for a player (p is "if he plays", docs/27) and `p` for a team.
No prices, no stakes: this module only combines forecasts we already made.
"""
from __future__ import annotations

import settings_store as S
import queries as Q

SAME_PLAYER_EXP = 0.38
TESTED_ENTITIES = 4                 # combinations of up to 4 players or teams were tested; more is extrapolation
CAP = 0.97                          # like calibration.CAP: football always leaves room for a surprise

MODES = {                           # the "build one for me" choices
    "safer":    {"n": 2, "min_q": 0.80, "rank": "q"},
    "balanced": {"n": 3, "min_q": 0.65, "rank": "edge"},
    "bolder":   {"n": 4, "min_q": 0.55, "rank": "edge"},
}


class ComboError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code, self.message = code, message


def includes_play(f: dict) -> bool:
    """True when p already counts the chance he plays (yellow-card lines from cards_model), so it must not be
    multiplied by p_play again. Other player lines are "if he plays". (docs/36 H6)"""
    return f.get("p_basis") == "all" or f.get("model") == "cards"


def chance(f: dict, key: str = "p") -> float:
    """How likely this line is to happen at all: a player has to play first."""
    v = float(f[key])
    if f["scope"] == "player" and not includes_play(f):
        v *= float(f.get("p_play", 1.0))
    return min(max(v, 0.0), 1.0)


def _entity(f: dict):
    return ("p", f["player_iid"]) if f["scope"] == "player" else ("t", f["team_iid"])


def _factor(n_entities: int, pre: bool, factors) -> float:
    if not pre or n_entities <= 1:
        return 1.0
    i = min(n_entities, len(factors)) - 1
    return float(factors[i])


def combine(docs: list[dict], key: str = "p", factors=(1.0, 1.11, 1.19, 1.25)) -> float:
    """Joint chance of every line in `docs` (all from one match, no two lines on the same stat for one entity)."""
    groups: dict = {}
    for f in docs:
        groups.setdefault(_entity(f), []).append(chance(f, key))
    out = 1.0
    for qs in groups.values():
        qs = sorted(qs)
        g = qs[0]
        for x in qs[1:]:
            g *= x ** SAME_PLAYER_EXP
        out *= g
    pre = any(f.get("state") == "pre" for f in docs)
    return min(out * _factor(len(groups), pre, factors), CAP)


def plain(c: float) -> str:
    if c >= 0.95:
        return "Very likely"
    if c >= 0.5:
        return f"About {round(c * 10)} in 10"
    return f"About 1 in {max(2, round(1 / max(c, 0.001)))}"


def _ref(x) -> dict | None:
    """What a screen needs to draw a player or a club: the public id, the name and the image."""
    if not x:
        return None
    return {"id": x.get("id"), "name": x.get("name"), "image": x.get("image") or x.get("image_url")}


def _name(x) -> str:
    return (x or {}).get("name") or ""


def _s(n: int, word: str) -> str:
    return f"{n} {word}" + ("" if n == 1 else "s")


def _with_match(db, rep: dict) -> dict:
    """Add the match's public id and its "Home v Away" label, so the screens can name and link the combo."""
    m = db.matches.find_one({"iid": rep["match_iid"]}, {"_id": 0, "id": 1, "home_iid": 1, "away_iid": 1})
    if m:
        names = Q._names(db, "teams", [m["home_iid"], m["away_iid"]])
        rep["match_id"] = m.get("id")
        rep["label"] = f"{(names.get(m['home_iid']) or {}).get('name')} v {(names.get(m['away_iid']) or {}).get('name')}"
    return rep


def estimate(db, ids=None, fkeys=None) -> dict:
    ids = [i for i in (ids or []) if i]; fkeys = [k for k in (fkeys or []) if k]
    if not ids and not fkeys:
        raise ComboError("EMPTY", "Add at least one line.")
    max_lines = int(S.get(db, "combo.max_lines")); factors = list(S.get(db, "combo.pre_factors"))
    if len(ids) + len(fkeys) > max_lines:
        raise ComboError("TOO_MANY", f"A combo holds up to {max_lines} lines.")
    q = {**Q.NOT_HIDDEN, "$or": [{"id": {"$in": ids}}, {"fkey": {"$in": fkeys}}]}
    docs = list(db.forecasts.find(q, {"_id": 0, "contrib": 0}))
    found = {d["id"] for d in docs} | {d["fkey"] for d in docs}
    if [x for x in (*ids, *fkeys) if x not in found]:
        raise ComboError("NOT_FOUND", "One of those lines is no longer available.")
    if len({d["match_iid"] for d in docs}) > 1:
        raise ComboError("MIXED_MATCHES", "A combo holds lines from one match.")
    seen = set()
    for d in docs:
        k = (_entity(d), d["stat"])
        if k in seen:
            raise ComboError("SAME_STAT", "Keep one line per stat for each player or team.")
        seen.add(k)
    docs = Q._decorate(db, docs)
    return _with_match(db, _report(docs, factors))


def _report(docs: list[dict], factors) -> dict:
    lines = []
    for d in docs:
        lines.append({"id": d["id"], "fkey": d["fkey"], "scope": d["scope"], "player": _ref(d.get("player")), "team": _ref(d.get("team")),
                      "opp": _ref(d.get("opp")), "stat": d["stat"], "thr": d["thr"], "market": d["market"], "p": round(float(d["p"]), 4),
                      "p_play": round(float(d.get("p_play", 1.0)), 4), "chance": round(chance(d), 4), "includes_play": includes_play(d),
                      "badge": d.get("lineup_badge"), "tier": d.get("tier"), "state": d.get("state")})
    c = combine(docs, "p", factors)
    lo = combine(docs, "lo", factors); hi = combine(docs, "hi", factors)
    state = "pre" if any(d.get("state") == "pre" for d in docs) else "lineup"
    ents = {_entity(d) for d in docs}
    notes = []
    unc = [d for d in docs if d["scope"] == "player" and d.get("lineup_badge") in ("likely", "unsure")]
    if unc:
        notes.append(f"{_s(len(unc), 'player')} not confirmed yet. The chances move when the lineup is out.")
    for d in docs:
        if d.get("lineup_badge") == "bench":
            notes.append(f"{_name(d.get('player')) or 'A player'} is on the bench, so his lines are less likely.")
    dep = {e for e in ents if sum(1 for d in docs if _entity(d) == e) > 1}
    for d in docs:
        if _entity(d) in dep:
            notes.append(f"{_name(d.get('player')) or _name(d.get('team'))}: two lines that usually happen together. We do not just multiply them.")
            dep.discard(_entity(d))
    if len(ents) > TESTED_ENTITIES:
        notes.append(f"We tested combos of up to {TESTED_ENTITIES} players or teams. Longer ones are less certain.")
    weakest = min(lines, key=lambda x: x["chance"])["id"] if lines else None
    return {"match_iid": docs[0]["match_iid"], "kickoff": docs[0]["kickoff"], "state": state, "lines": lines,
            "combined": round(c, 4), "range": {"lo": round(min(lo, c), 4), "hi": round(max(hi, c), 4)}, "plain": plain(c),
            "weakest": weakest, "notes": notes, "factor": _factor(len(ents), state == "pre", factors)}


def suggest(db, match_iid: int, mode: str = "balanced") -> dict:
    """A short combo of lines from this match that we are confident in and that are not the same player twice."""
    if mode not in MODES:
        raise ComboError("BAD_MODE", "Mode is safer, balanced or bolder.")
    m = MODES[mode]
    cand = list(db.forecasts.find({**Q.NOT_HIDDEN, "match_iid": match_iid, "tier": {"$ne": None}}, {"_id": 0, "contrib": 0}))
    ok = []
    for d in cand:
        if d["scope"] == "player" and d.get("lineup_badge") not in ("confirmed", "likely"):
            continue                                              # never suggest a player we are unsure will play
        c = chance(d)
        if c >= m["min_q"]:
            ok.append((c if m["rank"] == "q" else float(d.get("edge", 0.0)) + 0.25 * c, d))
    ok.sort(key=lambda t: -t[0])
    chosen, used = [], set()
    for _, d in ok:
        e = _entity(d)
        if e in used:
            continue
        chosen.append(d); used.add(e)
        if len(chosen) == m["n"]:
            break
    if len(chosen) < 2:
        return {"mode": mode, "lines": [], "reason": "Not enough confident lines for this match yet."}
    est = _with_match(db, _report(Q._decorate(db, chosen), list(S.get(db, "combo.pre_factors"))))
    est["mode"] = mode
    return est
