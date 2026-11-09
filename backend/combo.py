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

    One line is not a combination, so it skips the cap and the pre-lineup correction and comes back at its own
    chance. "Its own chance" is NOT the number on the card: the card says "if he plays" (docs/27), and a combo
    asks whether the thing happens AT ALL, which for a player means he has to play first. So a 41% card on a
    player who is 85% to start comes back as 35%, and the sheet shows the card's 41% beside it and says why.
    Reported once from a screenshot where the headline read 41% and the row under it read 35%; selftest_combo
    pins all three numbers together now, because the two can only ever disagree by being a bug."""
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


# ------------------------------------------------------------------ the builder (docs/65)
#
# `suggest` answers "give me a combo from THIS match". The builder answers the question people
# actually arrive with -- "build me something across tonight that comes out around here" -- which is
# a different problem: it searches every match in a window, and it is solved against a TARGET for
# the whole combo rather than a floor under each line.
#
# That distinction is the point. A floor under each line is the control a bet builder gives you,
# and it is the wrong one: four lines at 80% do not make an 80% combo, they make about a 41% one,
# which is the number nobody expects and nobody is shown. Here the reader says what the WHOLE thing
# should be worth and the engine finds lines that land there -- and because the search scores
# candidates with `combine()` itself, the target it hits is the real correlation-aware number, not
# a product of percentages that is wrong in a direction that flatters us.

REJECTIONS = ("lineup", "below_floor", "league", "market", "window", "already_used")


def candidates(db, *, leagues=None, stats=None, within_h: float = 24.0, min_leg: float = 0.0,
               allow_unsure: bool = False, exclude=(), now=None, limit: int = 3000):
    """The pool the builder searches, and an honest tally of what it threw away and why.

    The tally is not diagnostics: it is what the waiting screen shows. A progress state that
    describes real work is worth having; one that counts to three while nothing happens is theatre,
    and this product does not get to spend its credibility on theatre.
    """
    from datetime import datetime, timedelta, timezone
    now = now or datetime.now(timezone.utc)
    q = {**Q.NOT_HIDDEN, "tier": {"$ne": None}, "kickoff": {"$gte": now, "$lte": now + timedelta(hours=float(within_h))}}
    if leagues:
        q["league_iid"] = {"$in": list(leagues)}
    if stats:
        q["stat"] = {"$in": list(stats)}
    pool, tally = [], {k: 0 for k in REJECTIONS}
    tally["read"] = 0
    ex = set(exclude or ())
    for d in db.forecasts.find(q, {"_id": 0, "contrib": 0}).limit(limit):
        tally["read"] += 1
        if d["fkey"] in ex:
            tally["already_used"] += 1; continue
        # Never build on a player we are not sure will play. A combo multiplies its weakest
        # assumption by everything else, so one doubtful starter quietly halves the whole thing.
        if d["scope"] == "player" and d.get("lineup_badge") not in (("confirmed", "likely", "unsure") if allow_unsure else ("confirmed", "likely")):
            tally["lineup"] += 1; continue
        if chance(d) < float(min_leg or 0.0):
            tally["below_floor"] += 1; continue
        pool.append(d)
    tally["kept"] = len(pool)
    tally["matches"] = len({d.get("match_iid") for d in pool})
    return pool, tally


def _quality(d: dict) -> float:
    """How much this line is worth having in a combo, before its likelihood is considered.

    A confirmed starter beats a likely one, and a line the engine thinks departs from the player's
    usual game beats a truism at the same likelihood -- "1+ shot" for a striker is near-certain and
    says nothing.
    """
    q = 0.0
    if d.get("lineup_badge") == "confirmed":
        q += 0.25
    q += min(0.5, abs(float(d.get("edge") or 0.0)) * 2.0)
    q += {"Strong": 0.2, "Solid": 0.1}.get(d.get("tier") or "", 0.0)
    return q


def _pick(pool: list[dict], n: int, factors, *, target=None, keep=(), spread: bool = True) -> list[dict]:
    """Choose n lines. Greedy on a per-line score, then local search against the real combine()."""
    chosen = list(keep)
    used = {_entity(d) for d in chosen}
    matches = {d.get("match_iid") for d in chosen}
    # With a target, aim each remaining line near the n-th root of what is left to reach: the
    # product is the dominant term even after the corrections, so it is a good starting point and
    # the local search below fixes the rest.
    def score(d):
        c = chance(d)
        s = _quality(d)
        if target:
            need = max(1, n - len(chosen))
            aim = float(target) ** (1.0 / need)
            s -= 2.5 * abs(c - aim)          # closeness to the aim dominates
        else:
            s += c                            # no target: take the likeliest good lines
        if spread and d.get("match_iid") in matches:
            s -= 0.15                         # prefer another match: independent legs are honest legs
        return s
    rest = [d for d in pool if _entity(d) not in used]
    while len(chosen) < n and rest:
        best = max(rest, key=score)
        chosen.append(best); used.add(_entity(best)); matches.add(best.get("match_iid"))
        rest = [d for d in rest if _entity(d) not in used]
    if not target or len(chosen) < 2:
        return chosen
    # Local search. Scoring a candidate set with combine() itself is the whole reason the target
    # means anything: the same-player exponent and the pre-lineup factors move the answer by more
    # than the rounding people would forgive, and solving against a product would miss by that much.
    keepset = {_entity(d) for d in keep}
    for _ in range(3):
        cur = combine(chosen, "p", factors)
        moved = False
        for i, old in enumerate(list(chosen)):
            if _entity(old) in keepset:
                continue
            others = [d for j, d in enumerate(chosen) if j != i]
            taken = {_entity(d) for d in others}
            for cand in rest + [old]:
                if _entity(cand) in taken:
                    continue
                trial = others + [cand]
                if abs(combine(trial, "p", factors) - target) < abs(cur - target) - 1e-6:
                    chosen, cur, moved = trial, combine(trial, "p", factors), True
                    rest = [d for d in pool if _entity(d) not in {_entity(x) for x in chosen}]
                    break
        if not moved:
            break
    return chosen


def build(db, n: int = 3, *, target=None, leagues=None, stats=None, min_leg=None, within_h: float = 24.0,
          allow_unsure: bool = False, keep_fkeys=(), exclude=(), spread: bool = True, now=None) -> dict:
    """Build a combo of `n` lines across every match in the window.

    `target` is the chance of the WHOLE combo, not of each line. `keep_fkeys` are lines the reader
    pinned, which are never swapped out.
    """
    cap = int(S.get(db, "combo.max_lines") or 6)
    if not (2 <= int(n) <= cap):
        raise ComboError("BAD_N", f"A combo takes 2 to {cap} lines.")
    if target is not None and not (0.01 <= float(target) <= 0.95):
        raise ComboError("BAD_TARGET", "A target for the whole combo has to be between 1% and 95%.")
    factors = list(S.get(db, "combo.pre_factors"))
    pool, tally = candidates(db, leagues=leagues, stats=stats, within_h=within_h,
                             min_leg=min_leg, allow_unsure=allow_unsure, exclude=exclude, now=now)
    keep = [d for d in pool if d["fkey"] in set(keep_fkeys or ())]
    if len(keep) > n:
        raise ComboError("TOO_MANY_KEPT", f"You have pinned {len(keep)} lines but asked for {n}.")
    chosen = _pick(pool, int(n), factors, target=target, keep=keep, spread=spread)
    if len(chosen) < 2:
        return {"lines": [], "searched": tally, "reason": _why_empty(tally, min_leg, within_h),
                "asked": {"n": n, "target": target, "min_leg": min_leg, "within_h": within_h}}
    rep = _with_match(db, _report(Q._decorate(db, chosen), factors))
    rep["searched"] = tally
    rep["asked"] = {"n": n, "target": target, "min_leg": min_leg, "within_h": within_h, "spread": spread}
    if target:
        got = rep["combined"]
        rep["target"] = round(float(target), 4)
        # Say so when the window could not reach the target, rather than handing back a number that
        # looks like an answer to a question nobody asked.
        if abs(got - float(target)) > 0.05:
            rep["notes"].insert(0, f"The closest we could get to {round(float(target) * 100)}% from these "
                                   f"matches is {round(got * 100)}%.")
    if len(chosen) < int(n):
        rep["notes"].insert(0, f"Only {_s(len(chosen), 'line')} met what you asked for, not {n}.")
    return rep


def _why_empty(tally: dict, min_leg, within_h) -> str:
    if not tally["read"]:
        return f"No lines at all in the next {int(within_h)} hours."
    if tally["lineup"] and tally["lineup"] >= tally["read"] * 0.8:
        return "Lineups are not out yet, so there is almost no one here we are sure will play."
    if tally["below_floor"]:
        return (f"{_s(tally['below_floor'], 'line')} fell under {round(float(min_leg or 0) * 100)}% once the "
                "chance to play was counted, and what is left is not two lines on different players.")
    return "There are not two lines here on different players that meet what you asked for."


def alternates(db, keep_fkeys, replace_fkey: str, *, limit: int = 6, within_h: float = 24.0,
               stats=None, leagues=None, allow_unsure: bool = False, now=None) -> dict:
    """Other lines that could take one slot, each with what the combo becomes if it does.

    Ranked by quality, not by how much they flatter the number. A list sorted by "makes your combo
    look best" is a list that teaches the reader to keep clicking until it lies to them.
    """
    factors = list(S.get(db, "combo.pre_factors"))
    rest_keys = [k for k in keep_fkeys if k != replace_fkey]
    held = list(db.forecasts.find({**Q.NOT_HIDDEN, "fkey": {"$in": list(keep_fkeys)}}, {"_id": 0, "contrib": 0}))
    rest = [d for d in held if d["fkey"] in rest_keys]
    cur = combine(held, "p", factors) if held else None
    taken = {_entity(d) for d in rest}
    pool, _ = candidates(db, leagues=leagues, stats=stats, within_h=within_h, allow_unsure=allow_unsure,
                         exclude=list(keep_fkeys), now=now)
    out = []
    for d in pool:
        if _entity(d) in taken:
            continue
        joint = combine(rest + [d], "p", factors)
        out.append((_quality(d) + chance(d), d, joint))
    out.sort(key=lambda t: -t[0])
    rows = []
    for _, d, joint in out[:limit]:
        one = _report(Q._decorate(db, [d]), factors)["lines"][0]
        one["combined_if_swapped"] = round(joint, 4)
        one["delta"] = round(joint - cur, 4) if cur is not None else None
        rows.append(one)
    return {"current": round(cur, 4) if cur is not None else None, "replacing": replace_fkey, "options": rows}


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
