"""fake_pitchapi.py -- a tiny stand-in for api.pitchapi.dev built from simulated data.

Used by selftest.py. The JSON SHAPES follow the PitchAPI guide (envelope, periods/groups/items,
players stats groups, lineups). The KEY NAMES for shots, corners, tackles etc. are INVENTED here
(see TEAM_KEYS and PLAYER_KEYS). The real names are found in check A of 08_pitchapi_data_guide.md.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone

import httpx

TEAM_KEYS = {"poss": "BallPossesion", "xg": "expected_goals", "shots": "total_shots_fake", "sot": "shots_on_target_fake",
             "corners": "corners_fake", "tackles": "tackles_fake", "fouls": None, "yellow_cards": None}
PLAYER_KEYS = {"minutes": {"group": "top_stats", "key": "minutes_played_fake"},
               "shots": {"group": "top_stats", "key": "total_shots"},
               "sot": {"group": "top_stats", "key": "shot_accuracy", "use": "value"},
               "tackles": {"group": "defense", "key": "tackles_fake"},
               "goals": {"group": "top_stats", "key": None}, "assists": {"group": "top_stats", "key": None},
               "xg": {"group": "top_stats", "key": None}, "saves": {"group": "top_stats", "key": None},
               "interceptions": {"group": "defense", "key": None}, "clearances": {"group": "defense", "key": None},
               "fouls_committed": {"group": "duels", "key": "fouls_fake"}, "fouls_won": {"group": "duels", "key": "fouls_won_fake"},
               "passes": {"group": "attack", "key": "accurate_passes_fake", "use": "value"}}
POS_RAW = {"GK": 0, "DEF": 1, "MID": 2, "FWD": 3}


def _env(data): return {"data": data}


class FakePitch:
    def __init__(self, matches, tg, pg, n_final, start=datetime(2025, 8, 9, 15, tzinfo=timezone.utc)):
        self.n_final = n_final            # matches with round < n_final are finished; the rest are upcoming
        self.start = start
        self.log = []                     # every request path, for call counting
        self.m = matches.reset_index(drop=True)
        self.tg = tg.set_index(["game_id", "team"])
        self.pg = pg
        self.fail_next = []               # e.g. [429] queues an error for the next request
        self.confirmed_upcoming = True

    # --- ids
    def tid(self, t): return f"t_{int(t):06d}"
    def pid(self, p): return f"p_{int(p):06d}"
    def mid(self, g): return f"m_{int(g):06d}"
    def kick(self, rnd): return self.start + timedelta(days=7 * int(rnd))

    def transport(self):
        return httpx.MockTransport(self.handle)

    def _match_obj(self, r):
        final = r.round < self.n_final
        return {"id": self.mid(r.game_id), "date": self.kick(r.round).date().isoformat(),
                "time_utc": self.kick(r.round).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "status": "finished" if final else "not_started",
                "home_team": {"id": self.tid(r.home), "name": f"Team {r.home}", "image_url": f"https://cdn.pitchapi.dev/t/{self.tid(r.home)}.png"},
                "away_team": {"id": self.tid(r.away), "name": f"Team {r.away}", "image_url": f"https://cdn.pitchapi.dev/t/{self.tid(r.away)}.png"},
                "score_home": int(r.hg) if final else None, "score_away": int(r.ag) if final else None}

    def handle(self, req: httpx.Request) -> httpx.Response:
        path = req.url.path
        self.log.append(path)
        if self.fail_next:
            code = self.fail_next.pop(0)
            hdr = {"Retry-After": "0"} if code == 429 else {}
            return httpx.Response(code, json={"error": {"code": {429: "RATE_LIMIT_EXCEEDED", 401: "UNAUTHORIZED", 500: "INTERNAL_SERVER_ERROR"}[code], "message": "x"}}, headers=hdr)
        if not req.headers.get("X-API-KEY"):
            return httpx.Response(401, json={"error": {"code": "UNAUTHORIZED", "message": "no key"}})
        if path == "/v1/leagues":
            return httpx.Response(200, json=_env({"leagues": [{"id": "l_000001", "name": "Test League", "country_code": "ENG",
                                                               "image_url": "https://cdn.pitchapi.dev/l.png", "seasons": ["2024/2025", "2025/2026"], "is_free": True}]}))
        mm = re.fullmatch(r"/v1/leagues/(\w+)$", path)
        if mm:
            return httpx.Response(200, json=_env({"id": mm.group(1), "name": "Test League", "country_code": "ENG",
                                                  "season": "2025/2026", "image_url": "https://cdn.pitchapi.dev/l.png"}))
        mm = re.fullmatch(r"/v1/teams/(\w+)$", path)
        if mm:
            return httpx.Response(200, json=_env({"id": mm.group(1), "name": "Team", "image_url": f"https://cdn.pitchapi.dev/t/{mm.group(1)}.png"}))
        mm = re.fullmatch(r"/v1/players/(\w+)$", path)
        if mm:
            return httpx.Response(200, json=_env({"id": mm.group(1), "name": "Player", "short_name": "P",
                                                  "image_url": f"https://cdn.pitchapi.dev/p/{mm.group(1)}.png"}))
        mm = re.fullmatch(r"/v1/leagues/(\w+)/matches", path)
        if mm:
            status = req.url.params.get("status", "played")
            ms = [self._match_obj(r) for r in self.m.itertuples()]
            if status == "played": ms = [x for x in ms if x["status"] == "finished"]
            if status == "upcoming": ms = [x for x in ms if x["status"] == "not_started"]
            return httpx.Response(200, json=_env({"league": {"id": mm.group(1), "name": "Test League", "season": req.url.params.get("season")}, "matches": ms}))
        mm = re.fullmatch(r"/v1/matches/m_(\d+)/(stats|players|lineups)", path)
        if mm:
            g = int(mm.group(1)); kind = mm.group(2)
            row = self.m[self.m["game_id"] == g]
            if row.empty: return httpx.Response(404, json={"error": {"code": "RESOURCE_NOT_FOUND", "message": "no"}})
            r = next(row.itertuples())
            return httpx.Response(200, json=_env(getattr(self, "_" + kind)(r)))
        return httpx.Response(404, json={"error": {"code": "RESOURCE_NOT_FOUND", "message": "no"}})

    # --- payloads
    def _stats(self, r):
        h, a = self.tg.loc[(r.game_id, r.home)], self.tg.loc[(r.game_id, r.away)]
        def item(title, key, hv, av, fmt="integer"): return {"title": title, "key": key, "home": str(hv), "away": str(av), "format_type": fmt}
        items = [item("Ball possession", "BallPossesion", f"{h.poss:.0f}", f"{a.poss:.0f}"),
                 item("Expected goals", "expected_goals", f"{h.goals * 0.9 + 0.3:.2f}", f"{a.goals * 0.9 + 0.3:.2f}", "double"),
                 item("Total shots", "total_shots_fake", f"{int(h.shots)}", f"{int(a.shots)}"),
                 item("Shots on target", "shots_on_target_fake", f"{int(h.sot)} ({int(100 * h.sot / max(h.shots, 1))}%)", f"{int(a.sot)} ({int(100 * a.sot / max(a.shots, 1))}%)", "integerWithPercentage"),
                 item("Corners", "corners_fake", f"{int(h.corners)}", f"{int(a.corners)}"),
                 item("Tackles", "tackles_fake", f"{int(h.tackles)}", f"{int(a.tackles)}")]
        return {"match_id": self.mid(r.game_id), "periods": [
            {"period": "FirstHalf", "groups": []},
            {"period": "All", "groups": [{"group_name": "Top stats", "items": items[:2]}, {"group_name": "Shots", "items": items[2:4]},
                                           {"group_name": "Other", "items": items[4:]}]}]}

    def _players(self, r):
        out = []
        for p in self.pg[self.pg["game_id"] == r.game_id].itertuples():
            if p.minutes <= 0: continue
            top = {"Minutes played": {"key": "minutes_played_fake", "stat": {"type": "integer", "value": int(round(p.minutes))}},
                   "Total shots": {"key": "total_shots", "stat": {"type": "integer", "value": int(p.shots)}},
                   "Shot accuracy": {"key": "shot_accuracy", "stat": {"type": "fractionWithPercentage", "value": int(p.sot), "total": int(p.shots)}}}
            groups = [{"key": "top_stats", "stats": top}]
            if p.pos != "GK":
                groups.append({"key": "defense", "stats": {"Tackles": {"key": "tackles_fake", "stat": {"type": "integer", "value": int(p.tackles)}}}})
                # The simulation does not model passes or fouls, so these are invented from minutes and position.
                # They exist to exercise the shapes the real provider uses -- a made/attempted pair in `attack`, plain
                # counts in `duels` -- not to be realistic football (docs/47).
                mins = max(1, int(round(p.minutes)))
                att = {"DEF": 0.75, "MID": 0.95, "FWD": 0.45}.get(p.pos, 0.6) * mins
                done = int(att * 0.84)
                groups.append({"key": "attack", "stats": {
                    "Accurate passes": {"key": "accurate_passes_fake",
                                        "stat": {"type": "fractionWithPercentage", "value": done, "total": int(att)}}}})
                groups.append({"key": "duels", "stats": {
                    "Fouls committed": {"key": "fouls_fake", "stat": {"type": "integer", "value": (int(p.player) + mins) % 4}},
                    "Fouls won": {"key": "fouls_won_fake", "stat": {"type": "integer", "value": (int(p.player) * 3 + mins) % 5}}}})
            out.append({"player": {"id": self.pid(p.player), "name": f"Player {p.player}", "position_id": POS_RAW[p.pos]},
                        "team_id": self.tid(p.team), "stats": groups})
        return out

    def _lineups(self, r):
        final = r.round < self.n_final
        sub = self.pg[self.pg["game_id"] == r.game_id]
        def side(team):
            s = sub[sub["team"] == team]
            return {"confirmed": True if final else self.confirmed_upcoming, "formation": "4-3-3",
                    "starters": [{"player_id": self.pid(p.player), "shirt_number": "9", "position_id": POS_RAW[p.pos], "pitch_x": 0.5, "pitch_y": 0.5, "is_captain": False}
                                 for p in s[s["started"] == 1].itertuples()],
                    "subs": [{"player_id": self.pid(p.player), "shirt_number": "12", "position_id": POS_RAW[p.pos]} for p in s[s["started"] == 0].itertuples()]}
        return {"match_id": self.mid(r.game_id), "home": side(r.home), "away": side(r.away)}
