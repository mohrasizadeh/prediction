# Phase 5 extras: match events/referee, league referees, extra stats in leaderboards/grid/totals/finder, admin extras
import os
import sys

import pytest
import requests

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
API = f"{BASE_URL}/api"

MATCH = "113a875c-88df-46d4-8e6b-fa52e1c74508"      # Lecce v Juventus, final, has yellow/red/sub/goal
PEN_MATCH = "ad59124d-0527-4f89-916b-f28edb086b56"
OG_MATCH = "48dac464-8712-4f05-816c-05f80721edb3"
SCHED = "76a8f86d-2137-4ec1-8362-6815feb8165f"
SERIE_A = "1e2b1fe0-57a2-4084-9c33-095eb7ad7e49"
OFF_LEAGUE = "636a21df-a780-4b17-a174-eef9b0758ee1"
TEAM = "6b66a173-7dc8-4cad-82ce-edc68eab17e0"
SUB_PLAYER = "6294481b-c588-4aa4-b860-4c15ee89b791"
EXTRA = ["xg", "interceptions", "clearances", "fouls_committed", "fouls_won", "saves", "yellow_cards", "red_cards", "pen_goals"]


# Match detail: referee/stadium + events
class TestMatchEvents:
    def test_final_match_has_meta_and_events(self):
        d = requests.get(f"{API}/matches/{MATCH}").json()
        assert d["match"]["referee"] == "Fabio Maresca"
        assert d["match"]["stadium"]
        ev = d["events"]
        assert len(ev) >= 10
        types = {e["type"] for e in ev}
        assert {"goal", "yellow", "red", "sub"} <= types
        for e in ev:
            assert e["side"] in ("home", "away")
            assert "_id" not in e
        sub = next(e for e in ev if e["type"] == "sub")
        assert (sub.get("player_in") or {}).get("name") or sub.get("in_name")
        goal = next(e for e in ev if e["type"] == "goal")
        assert goal.get("player", {}).get("id")

    def test_minutes_sorted(self):
        ev = requests.get(f"{API}/matches/{MATCH}").json()["events"]
        mins = [(e["minute"] or 0, e.get("added") or 0) for e in ev]
        assert mins == sorted(mins)

    def test_goal_counts_match_score(self):
        d = requests.get(f"{API}/matches/{MATCH}").json()
        g = [e for e in d["events"] if e["type"] == "goal"]
        hg = sum(1 for e in g if (e["side"] == "home") != bool(e["own_goal"]))
        assert (hg, len(g) - hg) == (d["match"]["hg"], d["match"]["ag"])

    def test_penalty_and_own_goal_flags(self):
        assert any(e["penalty"] for e in requests.get(f"{API}/matches/{PEN_MATCH}").json()["events"])
        assert any(e["own_goal"] for e in requests.get(f"{API}/matches/{OG_MATCH}").json()["events"])

    def test_scheduled_match_no_events(self):
        d = requests.get(f"{API}/matches/{SCHED}").json()
        assert d["events"] == []


# League referees
class TestReferees:
    def test_referees_table(self):
        r = requests.get(f"{API}/leagues/{SERIE_A}/referees")
        assert r.status_code == 200
        rows = r.json()
        assert len(rows) > 5
        x = rows[0]
        for k in ("name", "matches", "yellow_pg", "red_pg", "pens_pg", "home_win_pct"):
            assert k in x
        assert 0 <= x["home_win_pct"] <= 1
        assert [r["matches"] for r in rows] == sorted([r["matches"] for r in rows], reverse=True)

    def test_referees_empty_league(self):
        r = requests.get(f"{API}/leagues/{OFF_LEAGUE}/referees")
        assert r.status_code in (200, 404)     # disabled leagues are hidden (404); enabled ones all have referees now
        if r.status_code == 200:
            assert r.json() == []

    def test_referees_404(self):
        assert requests.get(f"{API}/leagues/nope-league/referees").status_code == 404


# Extra stats across endpoints
class TestExtraStats:
    @pytest.mark.parametrize("stat", EXTRA)
    def test_leaderboard(self, stat):
        r = requests.get(f"{API}/leagues/{SERIE_A}/leaderboard", params={"stat": stat, "limit": 5})
        assert r.status_code == 200, r.text
        if stat != "red_cards":
            assert len(r.json()) > 0, f"{stat} leaderboard empty"

    @pytest.mark.parametrize("stat", ["interceptions", "yellow_cards", "xg"])
    def test_squad_grid(self, stat):
        r = requests.get(f"{API}/teams/{TEAM}/squad-grid", params={"stat": stat, "last": 5})
        assert r.status_code == 200
        rows = r.json()["rows"]
        assert rows and any(g.get("v") for x in rows for g in x["games"])

    @pytest.mark.parametrize("stat", ["xg", "yellow_cards", "red_cards"])
    def test_team_totals_for_against(self, stat):
        rows = requests.get(f"{API}/teams/{TEAM}/totals", params={"stat": stat, "last": 5}).json()["rows"]
        assert rows
        assert any(r["for"] is not None for r in rows), f"{stat} for missing"
        assert any(r["against"] is not None for r in rows), f"{stat} against missing (no {stat}_against field)"

    @pytest.mark.parametrize("mode", ["form", "run"])
    def test_finder_extra_stat(self, mode):
        from admin_login_helper import admin_session       # anonymous quota is 3/day, use the staff session
        r = admin_session().get(f"{API}/finder", params={"mode": mode, "stat": "interceptions", "threshold": 2, "scope": "player",
                                                   "last_n": 10, "leagues": SERIE_A, "min_reached": 0.5 if mode == "form" else None})
        assert r.status_code in (200, 429), r.text
        if r.status_code == 200:
            assert isinstance(r.json(), list) and len(r.json()) > 0

    def test_player_history_sub_fields(self):
        d = requests.get(f"{API}/players/{SUB_PLAYER}/history", params={"last": 20}).json()
        g = [x for x in d["games"] if x.get("sub_on") is not None]
        assert g, "no sub_on rows"
        assert g[0].get("replaced", {}).get("name")
        assert "yellow_cards" in d["games"][0]


# Admin extras endpoints
class TestAdminExtras:
    def test_requires_auth(self):
        assert requests.get(f"{API}/admin/ingest/extras").status_code in (401, 403)
        assert requests.post(f"{API}/admin/ingest/extras/backfill").status_code in (401, 403)

    def test_status_and_backfill(self):
        from admin_login_helper import admin_session
        s = admin_session()
        d = s.get(f"{API}/admin/ingest/extras").json()
        assert d["done"] == d["ingested"] and d["done"] >= 430
        assert d["calls_per_new_match"] == 2
        assert d["pending"] == 0
        r = s.post(f"{API}/admin/ingest/extras/backfill")
        assert r.status_code == 200 and r.json()["queued"] == 0
