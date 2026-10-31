"""live_track.py -- follow a forecast while the match is on (docs/31).

A line is "hit" the moment the live count passes its line (4+ cards: the 4th yellow). Counts come from what SportAPI
gives us and we store:
  * cards (player and match)         from live_events (works today; event types are matched loosely, see YELLOW)
  * team and player shots, shots on target, corners, tackles
                                     from live_stats (needs `sportapi.live_stats` on and a verified key map; see sportapi.fetch_stats)
A line whose count we do not have is "unknown": the page shows no tick, never a false one.
Nothing here calls a provider. Pages read this through GET /api/matches/{id}/live-forecasts.
"""
from __future__ import annotations

import math

FINAL = {"FT", "AET", "PENS"}
EVENT_STATS = {"yellow_cards", "match_yellow_cards"}
STATS_STATS = {"shots", "sot", "corners", "tackles"}


def is_yellow(t: str | None) -> bool:
    t = (t or "").lower()
    return "yellow" in t                                     # yellow_card and second_yellow both count as a booking


def event_counts(db, sid: int) -> dict:
    """{'player': {player_iid: yellows}, 'side': {'home': n, 'away': n}, 'unmatched': n}"""
    out = {"player": {}, "side": {"home": 0, "away": 0}, "unmatched": 0}
    for e in db.live_events.find({"fixture_sid": sid}, {"_id": 0, "type": 1, "side": 1, "player_iid": 1}):
        if not is_yellow(e.get("type")):
            continue
        if e.get("side") in out["side"]:
            out["side"][e["side"]] += 1
        if e.get("player_iid") is not None:
            out["player"][e["player_iid"]] = out["player"].get(e["player_iid"], 0) + 1
        else:
            out["unmatched"] += 1
    return out


def evaluate(db, match_iid: int) -> dict:
    lf = db.live_fixtures.find_one({"match_iid": match_iid}, {"_id": 0})
    if not lf or lf.get("status") in (None, "Scheduled", "Postponed", "Cancelled"):
        return {"active": False, "items": {}}
    final = lf.get("status") in FINAL
    sid = lf["sid"]
    ev = event_counts(db, sid)
    st = db.live_stats.find_one({"fixture_sid": sid}, {"_id": 0}) or {}
    team_side = {lf.get("home_iid"): "home", lf.get("away_iid"): "away"}
    items = {}
    for f in db.forecasts.find({"match_iid": match_iid, "is_current": True, "hidden": {"$ne": True}},
                               {"_id": 0, "fkey": 1, "stat": 1, "scope": 1, "thr": 1, "player_iid": 1, "team_iid": 1}):
        need = int(math.floor(f["thr"])) + 1
        cur, src = None, None
        if f["stat"] == "match_yellow_cards":
            cur, src = ev["side"]["home"] + ev["side"]["away"], "events"
        elif f["stat"] == "yellow_cards" and f["scope"] == "player":
            if f.get("player_iid") is not None and ev["unmatched"] == 0:
                cur, src = ev["player"].get(f["player_iid"], 0), "events"
            elif ev["player"].get(f.get("player_iid"), 0) >= need:
                cur, src = ev["player"][f["player_iid"]], "events"       # a hit is a hit even if another event is unmatched
        elif f["stat"] in STATS_STATS and st:
            if f["scope"] == "team":
                cur = ((st.get("teams") or {}).get(team_side.get(f["team_iid"])) or {}).get(f["stat"])
            else:
                row = next((p for p in st.get("players") or [] if p.get("player_iid") == f.get("player_iid")), None)
                cur = row.get(f["stat"]) if row else None
            src = "stats" if cur is not None else None
        if cur is None:
            items[f["fkey"]] = {"state": "unknown", "needed": need}
            continue
        cur = int(cur)
        state = "hit" if cur >= need else "missed" if final else "live"
        items[f["fkey"]] = {"state": state, "current": cur, "needed": need, "source": src}
    return {"active": True, "final": final, "status": lf.get("status"), "minute": lf.get("minute"),
            "updated": lf.get("polled_at"), "stats_at": st.get("at"), "items": items}
