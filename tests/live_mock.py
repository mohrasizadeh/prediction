# Mocked /api/live payload builder for the Live sheet UI test (iteration 23)
import json

def payload(hs):
    t = lambda i, n: {"name": n, "short": n, "team": None}
    base = {"league_iid": 61, "league_name": "Italian Serie A", "status_text": "", "winner": None, "updated": "2026-10-28T05:00:00"}
    fx = [
        dict(base, sid=901, match_id="bde08683-1ffb-4133-83ff-f21cf12fda95", kickoff="2026-10-28T04:30:00", status="LIVE", minute=37,
             home=t(1, "Venezia"), away=t(2, "Inter"), score={"home": hs, "away": 1}, events_n=hs + 1),
        dict(base, sid=902, match_id=None, kickoff="2026-10-28T17:30:00", status="Scheduled", minute=None,
             home=t(3, "AC Milan"), away=t(4, "Bologna"), score={"home": None, "away": None}, events_n=0),
        dict(base, sid=903, match_id=None, kickoff="2026-10-28T02:00:00", status="FT", minute=None,
             home=t(5, "Torino"), away=t(6, "Como"), score={"home": 1, "away": 3}, events_n=4),
    ]
    return json.dumps({"live_count": 1, "updated": "2026-10-28T05:00:00", "leagues": [{"league": "Italian Serie A", "fixtures": fx}]})
