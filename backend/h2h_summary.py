"""h2h_summary.py -- what the meetings between two clubs add up to (queries.h2h -> `summary`, `insights`).

Read only from what we store: the finished `matches` rows (score, home club, kickoff, league), their
`team_match_stats` (shots, corners, cards ...), and the goal events / `first_goal_side` for who scored
first. Nothing here is a forecast: it is a description of past meetings, so every figure is a count or
an average of those meetings, and every field is None when the meetings do not carry what it needs
(a club with no stored stats has no shots average, not an average of zero).

`a` and `b` are the two clubs as queries.h2h was called; match_detail calls it (home, away), so on the
match page `a` is this fixture's home club and `venue` is "meetings at this club's ground".

Insights are ranked by how unusual they are, not by which sounds best: each candidate sentence is scored
by how unlikely its count would be if these meetings went like an ordinary match in the same league
(-ln of the one-sided tail probability; binomial for "k of n" counts, Poisson for goal totals, a fair
split for stat totals). A sentence whose count a coin would produce a third of the time says nothing,
so it is left out; one per family is kept, so "won 5 of 6" and "won the last 5" do not both appear.
"""
from __future__ import annotations

import math

# Used when the league holds too few finished matches to measure its own rates.
DEFAULTS = {"draw": 0.26, "home": 0.45, "away": 0.29, "both": 0.50, "three": 0.50, "nil": 0.08, "mu": 2.7}
MIN_BASE = 30          # finished matches a league needs before its own rates replace DEFAULTS
MAX_TAIL = 0.30        # a count at least this ordinary is not worth a sentence
MAX_INSIGHTS = 5
STAT_WEIGHT = 0.7
STAT_AVG = ("shots", "sot", "corners", "fouls", "yellow_cards", "poss", "xg")
# The stats the comparison sentences may speak about, with the words they use.
STAT_WORDS = {"shots": "shots", "corners": "corners", "yellow_cards": "yellow cards"}


def _binom_tail(k: int, n: int, p: float, upper: bool = True) -> float:
    p = min(max(p, 1e-6), 1 - 1e-6)
    ks = range(k, n + 1) if upper else range(0, k + 1)
    return min(1.0, sum(math.comb(n, i) * p ** i * (1 - p) ** (n - i) for i in ks))


def _pois_tail(t: int, lam: float, upper: bool = True) -> float:
    lam = max(lam, 1e-6)
    below = sum(math.exp(-lam) * lam ** i / math.factorial(i) for i in range(0, t + (0 if upper else 1)))
    return max(0.0, 1.0 - below) if upper else min(1.0, below)


def _score(tail: float) -> float:
    return -math.log(max(tail, 1e-12))


def _of(k: int, n: int) -> str:
    """'5 of the last 6' / 'all 4' / 'both' -- the count a sentence leans on, in words that read."""
    if k == n:
        return "both" if n == 2 else f"all {n}"
    return f"{k} of the last {n}"


def baseline(db, league_iids) -> dict:
    """The league's own rates over its stored finished matches, or DEFAULTS when it holds too few."""
    rows = list(db.matches.find({"status": "final", "league_iid": {"$in": list(league_iids)}, "hg": {"$ne": None}},
                                {"_id": 0, "hg": 1, "ag": 1}).sort("kickoff", -1).limit(3000))
    rows = [r for r in rows if r.get("hg") is not None and r.get("ag") is not None]
    if len(rows) < MIN_BASE:
        return dict(DEFAULTS)
    n = len(rows)
    return {"draw": sum(r["hg"] == r["ag"] for r in rows) / n, "home": sum(r["hg"] > r["ag"] for r in rows) / n,
            "away": sum(r["hg"] < r["ag"] for r in rows) / n, "both": sum(r["hg"] > 0 and r["ag"] > 0 for r in rows) / n,
            "three": sum(r["hg"] + r["ag"] >= 3 for r in rows) / n, "nil": sum(r["hg"] + r["ag"] == 0 for r in rows) / n,
            "mu": sum(r["hg"] + r["ag"] for r in rows) / n}


def _first_side(m: dict, events: list[dict] | None) -> str | None:
    """'home' | 'away' | 'none' (goalless) | None (not known). The stored field first, then the events."""
    fg = m.get("first_goal_side")
    if fg in ("home", "away", "none"):
        return fg
    if (m.get("hg") or 0) + (m.get("ag") or 0) == 0:
        return "none"
    g = next((e for e in (events or []) if e.get("type") == "goal" and e.get("side") in ("home", "away")), None)
    if not g:
        return None
    return ("away" if g["side"] == "home" else "home") if g.get("own_goal") else g["side"]


def _avg(xs):
    xs = [x for x in xs if x is not None]
    return round(sum(xs) / len(xs), 2) if xs else None


def summarize(db, a: int, b: int, ms: list[dict]) -> tuple[dict | None, list[dict]]:
    """-> (summary, insights) over the meetings `ms` (newest first, finished, with a score). (None, []) if none."""
    ms = [m for m in ms if m.get("hg") is not None and m.get("ag") is not None]
    if not ms:
        return None, []
    n = len(ms)
    iids = [m["iid"] for m in ms]
    ev = {d["match_iid"]: d.get("events") or [] for d in db.match_events.find({"match_iid": {"$in": iids}}, {"_id": 0, "match_iid": 1, "events": 1})}
    ts: dict = {}
    for r in db.team_match_stats.find({"match_iid": {"$in": iids}, "team_iid": {"$in": [a, b]}}, {"_id": 0}):
        ts.setdefault(r["match_iid"], {})[r["team_iid"]] = r
    names = {d["iid"]: d for d in db.teams.find({"iid": {"$in": [a, b]}}, {"_id": 0, "iid": 1, "id": 1, "name": 1})}

    def gfga(m, t):
        return (m["hg"], m["ag"]) if m["home_iid"] == t else (m["ag"], m["hg"])

    res = []                                    # a's result per meeting, newest first: "w" | "d" | "l"
    for m in ms:
        gf, ga = gfga(m, a)
        res.append("w" if gf > ga else "d" if gf == ga else "l")

    def side(t, flip):
        wins = res.count("l" if flip else "w")
        goals = sum(gfga(m, t)[0] for m in ms)
        best = None
        for m in ms:
            gf, ga = gfga(m, t)
            if gf > ga and (best is None or (gf - ga, gf) > (best["gf"] - best["ga"], best["gf"])):
                best = {"match_id": m.get("id"), "kickoff": m.get("kickoff"), "gf": gf, "ga": ga, "home": m["home_iid"] == t}
        hm = [m for m in ms if m["home_iid"] == t]
        stats_rows = [ts[m["iid"]][t] for m in ms if t in ts.get(m["iid"], {})]
        fs = [_first_side(m, ev.get(m["iid"])) for m in ms]
        own = ["home" if m["home_iid"] == t else "away" for m in ms]
        return {"team_id": (names.get(t) or {}).get("id"), "wins": wins, "goals": goals, "goals_pm": round(goals / n, 2),
                "clean_sheets": sum(1 for m in ms if gfga(m, t)[1] == 0),
                "scored_first": sum(1 for f, o in zip(fs, own) if f == o) if any(f is not None for f in fs) else None,
                "biggest_win": best,
                "at_home": {"played": len(hm), "wins": sum(1 for m in hm if gfga(m, t)[0] > gfga(m, t)[1]),
                            "draws": sum(1 for m in hm if m["hg"] == m["ag"]),
                            "losses": sum(1 for m in hm if gfga(m, t)[0] < gfga(m, t)[1])},
                "stats": ({c: _avg([r.get(c) for r in stats_rows]) for c in STAT_AVG} if stats_rows else None)}

    sa, sb = side(a, False), side(b, True)
    draws = res.count("d")
    fs = [_first_side(m, ev.get(m["iid"])) for m in ms]
    known = [(f, m) for f, m in zip(fs, ms) if f is not None]
    first_goal = None
    if known:
        def by(t):
            return sum(1 for f, m in known if f in ("home", "away") and (m["home_iid"] if f == "home" else m["away_iid"]) == t)
        first_goal = {"known": len(known), "a": by(a), "b": by(b), "none": sum(1 for f, _ in known if f == "none")}

    # The current run, newest meeting first, from whichever side it favours.
    streak = None
    def run(ok):
        k = 0
        for r in res:
            if r not in ok:
                break
            k += 1
        return k
    cands = [("a", "won", run("w")), ("b", "won", run("l")), (None, "drawn", run("d")),
             ("a", "unbeaten", run("wd")), ("b", "unbeaten", run("ld"))]
    order = {"drawn": 0, "won": 1, "unbeaten": 2}         # on a tie the plainer statement wins
    cands = [c for c in cands if c[2] >= 2 and not (c[1] == "unbeaten" and c[2] == run("d"))]
    if cands:
        s, kind, k = max(cands, key=lambda c: (c[2], -order[c[1]]))
        streak = {"side": s, "kind": kind, "n": k}

    last = ms[0]
    lr = res[0]
    with_stats = sum(1 for m in ms if len(ts.get(m["iid"], {})) == 2)
    total = sum(m["hg"] + m["ag"] for m in ms)
    summary = {
        "meetings": n, "first": ms[-1].get("kickoff"), "last": ms[0].get("kickoff"),
        "a": sa, "b": sb, "draws": draws,
        "goals": total, "goals_pm": round(total / n, 2),
        "both_scored": sum(1 for m in ms if m["hg"] > 0 and m["ag"] > 0),
        "three_plus": sum(1 for m in ms if m["hg"] + m["ag"] >= 3),
        "goalless": sum(1 for m in ms if m["hg"] + m["ag"] == 0),
        # "At this venue": the meetings with this same club at home (a, the fixture's home side on the match page).
        "venue": {"home": "a", "played": sa["at_home"]["played"], "a_wins": sa["at_home"]["wins"],
                  "draws": sa["at_home"]["draws"], "b_wins": sa["at_home"]["losses"]},
        "first_goal": first_goal,
        "stats_meetings": with_stats,
        "last_meeting": {"match_id": last.get("id"), "kickoff": last.get("kickoff"), "hg": last["hg"], "ag": last["ag"],
                         "home": "a" if last["home_iid"] == a else "b",
                         "result": "a" if lr == "w" else "b" if lr == "l" else "draw"},
        "streak": streak,
    }
    base = baseline(db, {m["league_iid"] for m in ms if m.get("league_iid") is not None})
    nm = {a: (names.get(a) or {}).get("name") or "The home club", b: (names.get(b) or {}).get("name") or "The away club"}
    return summary, _insights(summary, base, nm[a], nm[b], ms, ts, a, b)


def _insights(s: dict, base: dict, na: str, nb: str, ms, ts, a, b) -> list[dict]:
    n = s["meetings"]
    if n < 2:
        return []
    out = []                                   # (score, family, kind, text)

    def add(tail, family, kind, text):
        if tail <= MAX_TAIL:
            out.append((_score(tail), family, kind, text))

    p_win = (1 - base["draw"]) / 2
    for nm, sd in ((na, s["a"]), (nb, s["b"])):
        k = sd["wins"]
        if k * 2 > n:
            add(_binom_tail(k, n, p_win), "wins", "wins", f"{nm} won {_of(k, n)} meetings.")
    st = s["streak"]
    if st and (st["n"] < n or st["kind"] != "won"):     # "won all 4" is already the wins sentence
        k, who = st["n"], (na if st["side"] == "a" else nb)
        if st["kind"] == "won":
            add(p_win ** k, "wins", "streak", f"{who} won the last {k} meetings.")
        elif st["kind"] == "unbeaten" and k >= 3:
            add((1 - p_win) ** k, "wins", "streak", f"{who} have not lost in the last {k} meetings.")
        elif st["kind"] == "drawn":
            add(base["draw"] ** k, "draws", "streak", f"The last {k} meetings all ended level.")
    if s["draws"] >= 2:
        add(_binom_tail(s["draws"], n, base["draw"]), "draws", "draws", f"{_of(s['draws'], n).capitalize()} meetings ended level.")

    k = s["both_scored"]
    if k / n > base["both"]:
        add(_binom_tail(k, n, base["both"]), "both", "both_scored", f"Both clubs scored in {_of(k, n)} meetings.")
    elif k == 0:
        add(_binom_tail(0, n, base["both"], upper=False), "both", "both_scored",
            f"At least one club kept a clean sheet in {_of(n, n)} meetings.")
    elif k / n < base["both"]:
        add(_binom_tail(k, n, base["both"], upper=False), "both", "both_scored", f"Both clubs scored in only {k} of the last {n} meetings.")

    k = s["three_plus"]
    if k / n > base["three"]:
        add(_binom_tail(k, n, base["three"]), "goals", "three_plus", f"{_of(k, n).capitalize()} meetings had 3 or more goals.")
    elif k == 0:
        add(_binom_tail(0, n, base["three"], upper=False), "goals", "three_plus", f"None of the last {n} meetings had more than 2 goals.")
    elif k / n < base["three"]:
        add(_binom_tail(k, n, base["three"], upper=False), "goals", "three_plus", f"Only {k} of the last {n} meetings had 3 or more goals.")
    lam = base["mu"] * n
    t = s["goals"]
    up = t > lam
    add(_pois_tail(t, lam, upper=up), "goals", "goals_pm",
        f"These meetings averaged {s['goals_pm']:.1f} goals, against {base['mu']:.1f} across the league.")

    v = s["venue"]
    if v["played"] >= 2:
        if v["a_wins"] * 2 > v["played"]:
            add(_binom_tail(v["a_wins"], v["played"], base["home"]), "venue", "venue",
                f"{na} won {v['a_wins']} of {v['played']} meetings at home.")
        elif v["b_wins"] * 2 > v["played"]:
            add(_binom_tail(v["b_wins"], v["played"], base["away"]), "venue", "venue",
                f"{nb} won {v['b_wins']} of {v['played']} visits to {na}.")

    fg = s["first_goal"]
    if fg and fg["known"] >= 2:
        p_first = (1 - base["nil"]) / 2
        for nm, k in ((na, fg["a"]), (nb, fg["b"])):
            if k * 2 > fg["known"]:
                add(_binom_tail(k, fg["known"], p_first), "first", "first_goal",
                    f"{nm} scored first in {_of(k, fg['known'])} meetings.")

    paired = [ts[m["iid"]] for m in ms if len(ts.get(m["iid"], {})) == 2]
    if len(paired) >= 2:
        for col, word in STAT_WORDS.items():
            xa = [r[a].get(col) for r in paired if r[a].get(col) is not None and r[b].get(col) is not None]
            xb = [r[b].get(col) for r in paired if r[a].get(col) is not None and r[b].get(col) is not None]
            if len(xa) < 2:
                continue
            ta, tb = sum(xa), sum(xb)
            if ta == tb:
                continue
            # Scored per meeting (how many meetings the side with more had more in), not on the totals:
            # thirty shots are not thirty independent coin flips, and on totals every gap looked rare.
            more = sum(1 for x, y in zip(xa, xb) if (x > y if ta > tb else y > x))
            less = sum(1 for x, y in zip(xa, xb) if (x < y if ta > tb else y < x))
            if more + less < 2:
                continue
            hi, lo, nhi, nlo = (ta, tb, na, nb) if ta > tb else (tb, ta, nb, na)
            # A better side out-shooting a weaker one is the usual thing, so a stat gap counts for less
            # than a result run of the same rarity (STAT_WEIGHT on the tail's log).
            add(_binom_tail(more, more + less, 0.5) ** STAT_WEIGHT, "stat", col,
                f"{nhi} averaged {hi / len(xa):.1f} {word} to {nlo}'s {lo / len(xa):.1f} in these meetings.")

    # One sentence per family, except the stat comparisons, which may take two places: they are each
    # about a different number, but five of them would crowd out the results.
    best: dict = {}
    stat = sorted((x for x in out if x[1] == "stat"), key=lambda x: -x[0])[:2]
    for sc, fam, kind, text in [x for x in out if x[1] != "stat"] + stat:
        key = f"{fam}:{kind}" if fam == "stat" else fam
        if key not in best or sc > best[key][0]:
            best[key] = (sc, kind, text)
    ranked = sorted(best.values(), key=lambda x: -x[0])[:MAX_INSIGHTS]
    return [{"text": text, "kind": kind, "score": round(sc, 2)} for sc, kind, text in ranked]
