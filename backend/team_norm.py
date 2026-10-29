"""Opponent-adjusted (normalised) team averages for any team_match_stats count (corners, fouls).
A team's corners against a side that concedes many count for less; recent games count more (half-life)."""
from __future__ import annotations

from referees import TeamCards


class TeamRate(TeamCards):
    def L(self):
        return max(self.tot / self.cnt, 1e-3) if self.cnt else 1.0

    def usual(self, team):
        """The team's normalised average against an average opponent."""
        return self.L() * self.rel(team)[0]


def build(db, league_iid: int, field: str, half: float = 20.0, k: float = 6.0) -> TeamRate:
    tm = TeamRate(k=k, half=half)
    by_match: dict = {}
    for r in db.team_match_stats.find({"league_iid": league_iid, field: {"$ne": None}},
                                      {"_id": 0, "match_iid": 1, "team_iid": 1, "kickoff": 1, field: 1}):
        by_match.setdefault(r["match_iid"], []).append(r)
    pairs = sorted((g for g in by_match.values() if len(g) == 2), key=lambda g: str(g[0].get("kickoff") or ""))
    for a, b in pairs:
        va, vb = float(a[field]), float(b[field])
        tm.tot += va + vb; tm.cnt += 2
        tm.add(a["team_iid"], b["team_iid"], va, vb); tm.add(b["team_iid"], a["team_iid"], vb, va)
    return tm
