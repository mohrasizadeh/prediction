"""referees.py -- normalised referee card numbers (docs/25).

Why not the plain average: one 8-card derby moves a referee's "cards per game" a lot, and a referee who gets the
league's angriest fixtures looks strict even when he is not. On 5,295 Premier League matches (2010/11-2024/25,
walk-forward), using the plain average made match card forecasts WORSE (log-lik -19.9 milli per match, z -4.5).
What works:
  1. Expected cards from the two teams first (each team's cards and cards drawn, recent games counting more,
     judged against the opponents faced).
  2. The referee's factor = (cards he gave + c) / (cards the teams predicted + c), so a referee with few games
     sits near 1.0 (c = 80 cards, about 20 matches).
  3. His older games fade (half-life 60 of his matches); one game's total is capped at the league's 99th percentile.
  Result: +4.0 milli per match vs teams only (z +2.5), every later season positive. Factors run about 0.88 to 1.12.

Input: final matches with `referee` (name) and both sides' yellow cards in team_match_stats (`yellow`).
Output: one referee_stats row per referee and league.
"""
from __future__ import annotations

from datetime import datetime, timezone

import numpy as np

import settings_store as S

CARD_FIELDS = ("yellow", "yellow_cards", "yellows")


def _card(doc):
    for f in CARD_FIELDS:
        v = doc.get(f)
        if v is not None:
            return float(v)
    return None


class TeamCards:
    """Running card rate per team: own cards and cards the opponent picks up, decayed and opponent-adjusted."""

    def __init__(self, k=6.0, half=20.0):
        self.k, self.g = k, 0.5 ** (1.0 / half)
        self.F, self.A, self.n = {}, {}, {}
        self.tot, self.cnt = 0.0, 0

    def L(self):
        if self.cnt < 20:                                  # too little to know the league yet: a typical value
            return 1.8
        return max(self.tot / self.cnt, 0.1)

    def rel(self, t):
        L = self.L()
        n = self.n.get(t, 0.0)
        return (self.F.get(t, 0.0) + self.k * L) / (n + self.k) / L, (self.A.get(t, 0.0) + self.k * L) / (n + self.k) / L

    def predict(self, team, opp):
        return self.L() * self.rel(team)[0] * self.rel(opp)[1]

    def add(self, team, opp, own, drawn):
        o_att, o_def = self.rel(opp)
        for D in (self.F, self.A, self.n):
            if team in D:
                D[team] *= self.g
        self.F[team] = self.F.get(team, 0.0) + own / max(o_def, 0.3)
        self.A[team] = self.A.get(team, 0.0) + drawn / max(o_att, 0.3)
        self.n[team] = self.n.get(team, 0.0) + 1.0


def compute(rows, c=80.0, half=60.0, cap_q=0.99):
    """rows: date-ordered dicts {referee, home, away, hy, ay}. Returns {referee: stats} and the team model."""
    tm = TeamCards()
    g = 0.5 ** (1.0 / half) if half else 1.0
    O, E, N, raw_sum, raw_n, last = {}, {}, {}, {}, {}, {}
    totals = []
    for r in rows:
        ref, h, a = r["referee"], r["home"], r["away"]
        y = r["hy"] + r["ay"]
        exp_ = tm.predict(h, a) + tm.predict(a, h)
        yc = min(y, float(np.quantile(totals[-3000:], cap_q))) if (cap_q and len(totals) >= 200) else y
        if ref:
            if ref in O:
                O[ref] *= g; E[ref] *= g; N[ref] *= g
            O[ref] = O.get(ref, 0.0) + yc
            E[ref] = E.get(ref, 0.0) + exp_
            N[ref] = N.get(ref, 0.0) + 1.0
            raw_sum[ref] = raw_sum.get(ref, 0.0) + y
            raw_n[ref] = raw_n.get(ref, 0) + 1
            last[ref] = r.get("kickoff")
        totals.append(y)
        tm.tot += r["hy"] + r["ay"]; tm.cnt += 2
        tm.add(h, a, r["hy"], r["ay"]); tm.add(a, h, r["ay"], r["hy"])
    league_avg = float(np.mean(totals)) if totals else 0.0
    out = {}
    for ref in O:
        f = (O[ref] + c) / (E[ref] + c)
        out[ref] = {"matches": raw_n[ref], "cards_per_game": raw_sum[ref] / raw_n[ref],
                    "factor": float(f), "cards_per_game_normalised": league_avg * float(f),
                    "league_cards_per_game": league_avg, "last_match": last.get(ref)}
    return out, tm


def sentence(name, f, n):
    if n < 5:
        return f"Few matches with {name} so far, so we treat this referee as average."
    pct = round((f - 1.0) * 100)
    if abs(pct) < 4:
        return f"{name} gives about the number of cards the teams usually pick up."
    more = "more" if pct > 0 else "fewer"
    return f"{name} gives about {abs(pct)}% {more} cards than the teams would usually pick up."


def rows_for_league(db, league_iid: int):
    ms = list(db.matches.find({"league_iid": league_iid, "status": "final", "referee": {"$nin": [None, ""]}},
                              {"_id": 0, "iid": 1, "referee": 1, "home_iid": 1, "away_iid": 1, "kickoff": 1}).sort("kickoff", 1))
    if not ms:
        return []
    ts = {}
    for d in db.team_match_stats.find({"match_iid": {"$in": [m["iid"] for m in ms]}}, {"_id": 0}):
        ts[(d["match_iid"], d["team_iid"])] = _card(d)
    rows = []
    for m in ms:
        hy, ay = ts.get((m["iid"], m["home_iid"])), ts.get((m["iid"], m["away_iid"]))
        if hy is None or ay is None:
            continue
        rows.append({"referee": str(m["referee"]).strip(), "home": m["home_iid"], "away": m["away_iid"],
                     "hy": hy, "ay": ay, "kickoff": m["kickoff"]})
    return rows


def refresh(db, league_iid: int) -> dict:
    """Recompute referee_stats for one league. Called by the `referees` job."""
    rows = rows_for_league(db, league_iid)
    if not rows:
        return {"league_iid": league_iid, "referees": 0, "note": "no matches with a referee and both sides' cards"}
    stats, _ = compute(rows, c=float(S.get(db, "referees.prior_cards")), half=float(S.get(db, "referees.half_life")),
                       cap_q=float(S.get(db, "referees.cap_q")) or None)
    now = datetime.now(timezone.utc)
    for ref, st in stats.items():
        db.referee_stats.update_one({"referee": ref, "league_iid": league_iid},
                                    {"$set": {**{k: (round(v, 4) if isinstance(v, float) else v) for k, v in st.items()},
                                              "sentence": sentence(ref, st["factor"], st["matches"]), "at": now}}, upsert=True)
    return {"league_iid": league_iid, "referees": len(stats), "matches": len(rows)}


def for_match(db, match: dict) -> dict | None:
    """The referee line for a match page, when the referee is known."""
    ref = (match or {}).get("referee")
    if not ref:
        return None
    st = db.referee_stats.find_one({"referee": str(ref).strip(), "league_iid": match.get("league_iid")}, {"_id": 0})
    if not st:
        return {"referee": ref, "factor": 1.0, "sentence": f"No history with {ref} yet, so we treat this referee as average."}
    return {"referee": ref, "factor": st["factor"], "matches": st["matches"], "cards_per_game": st["cards_per_game"],
            "cards_per_game_normalised": st["cards_per_game_normalised"], "sentence": st["sentence"]}
