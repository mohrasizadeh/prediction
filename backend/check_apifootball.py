"""check_apifootball.py -- three API calls and three image downloads that settle the open questions in doc 19 section 3. Costs 3 of your daily API calls.

    pip install httpx
    APIFOOTBALL_KEY=your_key python check_apifootball.py [league_id] [season]      # default: 39 2024

It prints what it saw. Nothing is written anywhere. Send the output to whoever maintains the sync if a line says CHECK.
"""
import os
import sys

import httpx

BASE, MEDIA = "https://v3.football.api-sports.io", "https://media.api-sports.io/football"
key = os.environ.get("APIFOOTBALL_KEY", "")
league, season = (sys.argv[1] if len(sys.argv) > 1 else "39"), (sys.argv[2] if len(sys.argv) > 2 else "2024")
if not key:
    sys.exit("Set APIFOOTBALL_KEY first.")
H = {"x-apisports-key": key, "accept": "application/json"}


def api(path, **params):
    r = httpx.get(BASE + path, params=params, headers=H, timeout=30)
    left = {k: v for k, v in r.headers.items() if k.lower().startswith("x-ratelimit")}
    return r, left


def say(ok, msg):
    print(("  ok     " if ok else "  CHECK  ") + msg)


r, left = api("/teams", league=league, season=season)
j = r.json()
print(f"/teams?league={league}&season={season} -> HTTP {r.status_code}, results={j.get('results')}, errors={j.get('errors')}")
print("  rate headers:", left or "none seen")
teams = j.get("response") or []
say(bool(teams) and "team" in teams[0] and {"id", "name"} <= set(teams[0]["team"]), "teams answer has response[].team.id and .name")
if not teams:
    sys.exit("No clubs came back. A plan or season problem? Read 'errors' above, try another season.")
tid, tname = teams[0]["team"]["id"], teams[0]["team"]["name"]
before = left.get("x-ratelimit-requests-remaining")

r, left2 = api("/players/squads", team=tid)
j = r.json()
sq = (j.get("response") or [{}])[0]
print(f"/players/squads?team={tid} ({tname}) -> HTTP {r.status_code}, errors={j.get('errors')}")
say(bool(sq.get("players")) and {"id", "name", "position"} <= set(sq["players"][0]), "squad answer has response[0].players[] with id, name, position")
pid = (sq.get("players") or [{}])[0].get("id")

for kind, ident in (("leagues", league), ("teams", tid), ("players", pid)):
    if ident is None:
        continue
    m = httpx.get(f"{MEDIA}/{kind}/{ident}.png", timeout=30)
    ct = m.headers.get("content-type", "")
    magic = m.content[:4]
    say(m.status_code == 200 and (magic[:3] == b"\xff\xd8\xff" or magic == b"\x89PNG" or magic[:4] == b"RIFF"),
        f"media/{kind}/{ident}.png -> HTTP {m.status_code}, {ct}, {len(m.content)} bytes (a real image, not an error page)")

r, left3 = api("/leagues", id=league)
cov = None
try:
    s = r.json()["response"][0]["seasons"]
    cov = next((x for x in s if str(x.get("year")) == str(season)), s[-1]).get("coverage")
except Exception:
    pass
print(f"/leagues?id={league} -> HTTP {r.status_code}; coverage for {season}: {cov}")
after = left3.get("x-ratelimit-requests-remaining")
print()
if before is not None and after is not None:
    used = int(before) - int(after)
    # /teams already counted when `before` was read, so after /squads and /leagues we expect exactly 2 more, and 0 for the 3 image downloads
    say(used == 2, f"daily counter fell by {used} across squads + leagues + 3 image downloads (2 expected: images are free)")
else:
    print("  The daily counter header was not shown; check your dashboard's request count instead (expect 3 used in all).")
