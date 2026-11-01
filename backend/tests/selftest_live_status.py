"""selftest_live_status.py -- one rule for "is this match being played" (docs/42).

Reported: live events were not all pulling, and forecasts did not tick green during a match. The cause was that
several places named the provider's status words one by one. SportAPI's exact vocabulary is not verified (docs/08),
so a half-time, extra-time, break or penalties word we had never seen fell through every list: the match stopped
looking live, its events stopped refreshing, and no line could tick.

Proves: in_play covers any in-play word and still excludes the ones that mean "not being played"; phase_of and
status_text never leave an in-play match without a phase or print a raw code; the scoreboard, the admin count and
live_track all agree; and the admin can see which followed fixtures reach no page at all.
"""
import datetime as dt
import testkit as K
from testkit import check, db
import sportapi as SP, live_track as LT

UTC = dt.timezone.utc
now = dt.datetime.now(UTC)

# ---------------------------------------------------------------- in_play: the single rule
ON = ["LIVE", "1H", "2H", "HT", "ET", "BT", "P", "Half Time", "Extra Time", "Break Time", "Penalty In Progress",
      "Suspended", "Interrupted", "In Progress", "Something We Have Never Seen"]
OFF = ["Scheduled", "NS", "Not Started", "TBD", "TBA", "Delayed", "Deferred", "FT", "AET", "PENS", "PEN", "AP",
       "Full Time", "Match Finished", "Postponed", "PST", "Cancelled", "Canceled", "CANC", "Abandoned", "ABD",
       "Awarded", "AWD", "WO", "Walkover", "Technical Loss", "full_time", "match finished", "ft", None, ""]
for s in ON:
    check(SP.in_play(s) is True, f"being played: {s!r}")
for s in OFF:
    check(SP.in_play(s) is False, f"not being played: {s!r}")
check(SP.in_play("HT") and not SP.in_play("FT"),
      "half time is being played and full time is not: the pair that broke events refreshing")

# ---------------------------------------------------------------- phase_of and status_text
check(SP.phase_of("HT") == "live", "half time has a phase, so the match still looks live on every screen")
check(SP.phase_of("ET") == "live" and SP.phase_of("P") == "live", "extra time and penalties too")
check(SP.phase_of("Scheduled") == "scheduled" and SP.phase_of("FT") == "final", "the known words are unchanged")
check(SP.phase_of("Postponed") == "postponed" and SP.phase_of("Cancelled") == "cancelled", "...including the called-off ones")
check(SP.phase_of("TBD") is None and SP.phase_of(None) is None, "a word that means 'not being played' still has no live phase")
check(SP.status_text("HT") == "Live", "an in-play word we do not know reads as Live, never as the raw code")
check(SP.status_text("FT") == "Full time" and SP.status_text("Scheduled") == "Not started", "the known wordings are unchanged")
check(SP.status_text(None) == "Not started", "nothing at all reads as not started")
check(SP.status_text("Deferred") == "Deferred", "a word that means 'not started' is shown as it came, not as Live")
check(SP.in_play("ft") is False and SP.in_play("Full Time") is False and SP.in_play("full_time") is False,
      "case, spaces and punctuation are ignored, so one provider's spelling of a word is every provider's")

# finished and called off, told apart from each other
check(SP.is_final("PEN") and SP.is_final("After Penalties") and SP.is_final("ft"), "a decided match is final however it is spelled")
check(SP.is_final("Postponed") is False and SP.is_final("HT") is False, "a called-off or ongoing match is not final")
check(SP.is_over("Cancelled") and SP.is_over("WO") and SP.is_over("FT"), "finished or called off: over for good")
check(SP.is_over("Scheduled") is False and SP.is_over("HT") is False, "not yet played, or being played: not over")

# ---------------------------------------------------------------- the screens agree
db.teams.insert_many([{"iid": i, "id": f"t{i}", "ext_id": i, "name": n} for i, n in ((1, "Como"), (2, "Venezia"), (3, "Parma"), (4, "Genoa"))])
db.matches.insert_many([{"iid": 5, "id": "m5", "ext_id": 5, "home_iid": 1, "away_iid": 2, "kickoff": now, "status": "scheduled", "league_iid": 1},
                        {"iid": 6, "id": "m6", "ext_id": 6, "home_iid": 3, "away_iid": 4, "kickoff": now, "status": "scheduled", "league_iid": 1}])
db.live_fixtures.insert_many([
    {"sid": 77, "match_iid": 5, "league_iid": 1, "league_name": "Serie A", "status": "HT", "minute": "45'", "home_iid": 1, "away_iid": 2,
     "home_name": "Como", "away_name": "Venezia", "kickoff": now, "polled_at": now, "hs": 1, "as": 0, "date": now.strftime("%Y-%m-%d")},
    {"sid": 78, "match_iid": 6, "league_iid": 1, "league_name": "Serie A", "status": "Scheduled", "home_iid": 3, "away_iid": 4,
     "home_name": "Parma", "away_name": "Genoa", "kickoff": now + dt.timedelta(hours=3), "date": now.strftime("%Y-%m-%d")}])
sb = SP.scoreboard(db, now=now)
check(sb["live_count"] == 1, f"the scoreboard counts the half-time match as live: {sb['live_count']}")
fx = [f for l in sb["leagues"] for f in l["fixtures"]]
check(fx[0]["sid"] == 77, "...and puts it above the one that has not kicked off")
check(fx[0]["status_text"] == "Live", "...and the page is given a word, not 'HT'")
st = SP.status(db, now=now)
check(st["live_now"] == 1, "the admin's 'Live now' counts it too")

# a forecast on that match can be judged, which it could not be when half time was not "on"
db.forecasts.insert_one({"fkey": "c4", "match_iid": 5, "is_current": True, "hidden": False, "scope": "team",
                         "stat": "match_yellow_cards", "thr": 1.5, "team_iid": 1})
db.live_events.insert_many([{"fixture_sid": 77, "eid": i, "type": "yellow_card", "side": "home", "player_name": "X",
                             "player_iid": None, "minute": f"{10 + i}'", "minute_num": 10 + i} for i in range(2)])
ev = LT.evaluate(db, 5)
check(ev["active"] is True and ev["final"] is False, "live_track follows a match at half time: this is what stopped lines ticking")
check(ev["items"]["c4"]["state"] == "hit", "...so the 2nd card turns the line green while the players are in the dressing room")
for s in ("Scheduled", "TBD", "Postponed", "Abandoned", None):
    db.live_fixtures.update_one({"sid": 77}, {"$set": {"status": s}})
    check(LT.evaluate(db, 5)["active"] is False, f"live_track tracks nothing for {s!r}")
db.live_fixtures.update_one({"sid": 77}, {"$set": {"status": "AET"}})
ev = LT.evaluate(db, 5)
check(ev["active"] is True and ev["final"] is True, "a match decided in extra time is still judged, and judged as over")

# ---------------------------------------------------------------- what the browser is told
db.live_fixtures.update_one({"sid": 77}, {"$set": {"status": "ET"}})
pf = {f["sid"]: f for l in SP.scoreboard(db, now=now)["leagues"] for f in l["fixtures"]}
check(pf[77]["state"] == "live" and pf[77]["live"] is True,
      "a fixture in extra time is sent to the browser as live, so it is never the browser's job to know the word")
check(pf[78]["state"] == "later", "one that has not kicked off is 'later'")
db.live_fixtures.update_one({"sid": 78}, {"$set": {"status": "PEN"}})
check({f["sid"]: f["state"] for l in SP.scoreboard(db, now=now)["leagues"] for f in l["fixtures"]}[78] == "done",
      "...and a decided one is 'done', so the Live sheet files it under Finished and nothing else does")
db.live_fixtures.update_one({"sid": 78}, {"$set": {"status": "Postponed"}})
check({f["sid"]: f["state"] for l in SP.scoreboard(db, now=now)["leagues"] for f in l["fixtures"]}[78] == "done",
      "a called-off match is 'done' too: it is not coming")
m = SP.overlay(db, [dict(db.matches.find_one({"iid": 5}, {"_id": 0}))])[0]
check(m["live"]["playing"] is True and m["live"]["state"] == "live" and m["phase"] == "live",
      "a match row carries the same answer, which is what makes the match page keep asking what has happened")
db.live_fixtures.update_one({"sid": 77}, {"$set": {"status": "FT", "hs": 2, "as": 1}})
m = SP.overlay(db, [dict(db.matches.find_one({"iid": 5}, {"_id": 0}))])[0]
check(m["live"]["playing"] is False and m["status"] == "final", "at full time it stops being played and the match is final")
db.live_fixtures.update_one({"sid": 77}, {"$set": {"status": "HT"}})

# ---------------------------------------------------------------- which fixtures reach no page
db.live_fixtures.insert_many([
    {"sid": 79, "match_iid": None, "league_iid": 1, "league_name": "Serie A", "status": "LIVE", "home_iid": 1, "away_iid": 2,
     "home_name": "Como", "away_name": "Venezia", "kickoff": now},
    {"sid": 80, "match_iid": None, "league_iid": 1, "league_name": "Serie A", "status": "Scheduled", "home_iid": None, "away_iid": None,
     "home_name": "Unknown FC", "away_name": "Other FC", "kickoff": now + dt.timedelta(days=2)},
    {"sid": 81, "match_iid": None, "league_iid": 1, "status": "Scheduled", "home_name": "Far", "away_name": "Away",
     "kickoff": now + dt.timedelta(days=90)}])
f = SP.fixture_links(db, now=now)
check(f["total"] == 4 and f["linked"] == 2, f"a fixture far outside the window is not counted: {f['total']} followed, {f['linked']} matched")
check(f["unlinked"] == 2, "the two fixtures inside the window that reach no page are counted")
check(f["unlinked_live"] == 1, "...and the one being played right now is called out, because live data is being lost")
rows = {r["sid"]: r for r in f["rows"]}
check(set(rows) == {79, 80}, f"the admin is shown exactly those two: {sorted(rows)}")
check(rows[79]["clubs_known"] is True, "a fixture whose clubs we know but whose match we do not hold")
check(rows[80]["clubs_known"] is False, "...and one that needs a club matched first")
check(SP.status(db, now=now)["fixtures"]["unlinked"] == 2, "the admin screen is given all of this")

print("\nALL LIVE STATUS CHECKS PASSED")
