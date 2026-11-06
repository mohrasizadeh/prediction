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


def _one_match(docs: list[dict], key: str, factors) -> float:
    """Joint chance of lines that all belong to ONE match. This is where the measured numbers apply: two lines on
    the same player happen together far more often than the product says, and before the lineup every line in the
    match shares the same team news, game state and referee, which is what `combo.pre_factors` corrects for."""
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
    return out * _factor(len(groups), pre, factors)


def combine(docs: list[dict], key: str = "p", factors=(1.0, 1.11, 1.19, 1.25)) -> float:
    """Joint chance of every line in `docs`, which may come from several matches (docs/40).

    Lines in the same match lean on each other: the same team news, the same game state, the same referee. That is
    what we measured, and `_one_match` applies it. Lines in DIFFERENT matches share none of those causes, so the
    matches multiply plainly. Stretching the within-match correction across matches would inflate the number for a
    dependence that is not there.

    One line is not a combination: it is returned as it is, so the builder never changes a number you were
    already looking at."""
    by_match: dict = {}
    for f in docs:
        by_match.setdefault(f.get("match_iid"), []).append(f)
    out = 1.0
    for ds in by_match.values():
        out *= _one_match(ds, key, factors)
    if len(docs) <= 1:
        return min(max(out, 0.0), 1.0)
    return min(out, CAP)


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


def _s(n: int, word: str, plural: str | None = None) -> str:
    """'1 match', '2 matches'. A bare 's' gives 'matchs', so words that hiss take 'es' (or an explicit plural)."""
    if n == 1:
        return f"{n} {word}"
    return f"{n} {plural}" if plural else f"{n} {word}" + ("es" if word.endswith(("ch", "sh", "s", "x", "z")) else "s")


def _with_match(db, rep: dict) -> dict:
    """Name and link every match the combo touches. `matches` is the list, newest kick-off last. `match_iid`,
    `match_id` and `label` stay as the first match so older screens and saved combos keep working; with more than
    one match the label counts them instead."""
    iids = [m["match_iid"] for m in rep.get("matches", [])] or ([rep["match_iid"]] if rep.get("match_iid") else [])
    rows = {m["iid"]: m for m in db.matches.find({"iid": {"$in": iids}}, {"_id": 0, "iid": 1, "id": 1, "home_iid": 1, "away_iid": 1})}
    names = Q._names(db, "teams", [t for m in rows.values() for t in (m["home_iid"], m["away_iid"])])
    for entry in rep.get("matches", []):
        m = rows.get(entry["match_iid"])
        if not m:
            continue
        entry["match_id"] = m.get("id")
        entry["label"] = f"{(names.get(m['home_iid']) or {}).get('name')} v {(names.get(m['away_iid']) or {}).get('name')}"
    first = (rep.get("matches") or [{}])[0]
    rep["match_id"] = first.get("match_id")
    rep["label"] = first.get("label") if len(rep.get("matches", [])) <= 1 else f"{_s(len(rep['matches']), 'match')}"
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
                      "badge": d.get("lineup_badge"), "tier": d.get("tier"), "state": d.get("state"),
                      "match_iid": d.get("match_iid"), "kickoff": d.get("kickoff")})
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
    # one entry per match, earliest kick-off first, each with its own joint chance
    by_match: dict = {}
    for d in docs:
        by_match.setdefault(d["match_iid"], []).append(d)
    matches = sorted(({"match_iid": iid, "kickoff": ds[0]["kickoff"],
                       "fkeys": [d["fkey"] for d in ds],
                       "combined": round(min(_one_match(ds, "p", factors), 1.0), 4),
                       "state": "pre" if any(d.get("state") == "pre" for d in ds) else "lineup"}
                      for iid, ds in by_match.items()), key=lambda e: (e["kickoff"] is None, e["kickoff"]))
    if len(matches) > 1:
        notes.append(f"Lines from {_s(len(matches), 'different match', 'different matches')}. Different matches do not lean on each other, "
                     "so their chances multiply plainly.")
    return {"match_iid": matches[0]["match_iid"], "kickoff": matches[0]["kickoff"],
            "last_kickoff": matches[-1]["kickoff"], "matches": matches,
            "state": state, "lines": lines,
            "combined": round(c, 4), "range": {"lo": round(min(lo, c), 4), "hi": round(max(hi, c), 4)}, "plain": plain(c),
            "weakest": weakest, "notes": notes,
            "factor": max((_factor(len({_entity(d) for d in ds}), e["state"] == "pre", factors)
                           for e, ds in zip(matches, (by_match[e["match_iid"]] for e in matches))), default=1.0)}


def suggest(db, match_iid: int, mode: str = "balanced") -> dict:
    """A short combo of lines from this match that we are confident in and that are not the same player twice."""
    if mode not in MODES:
        raise ComboError("BAD_MODE", "Mode is safer, balanced or bolder.")
    m = MODES[mode]
    cand = list(db.forecasts.find({**Q.NOT_HIDDEN, "match_iid": match_iid, "tier": {"$ne": None}}, {"_id": 0, "contrib": 0}))
    ok, gated, reachable = [], 0, []
    for d in cand:
        if d["scope"] == "player" and d.get("lineup_badge") not in ("confirmed", "likely"):
            gated += 1
            continue                                              # never suggest a player we are unsure will play
        c = chance(d)
        reachable.append(c)
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
        # "None yet" read as "we have not worked it out", so the reader went looking for the lines
        # they could see on the cards. Nothing is missing: this match simply has no two lines that
        # clear the bar once the chance to play is counted. Say which, and how close it gets.
        best = max(reachable) if reachable else None
        if best is None and gated:
            reason = "Lineups are not out, so there is no one here we are sure will play."
        elif best is None:
            reason = "No lines for this match yet."
        else:
            reason = (f"No two lines in this match reach {round(m['min_q'] * 100)}% once the chance to play "
                      f"is counted. The best single line is {round(best * 100)}%.")
            if gated:
                reason += f" {_s(gated, 'line')} left out because the lineup is not sure."
        return {"mode": mode, "lines": [], "reason": reason,
                "best": round(best, 4) if best is not None else None, "min_q": m["min_q"]}
    est = _with_match(db, _report(Q._decorate(db, chosen), list(S.get(db, "combo.pre_factors"))))
    est["mode"] = mode
    return est
