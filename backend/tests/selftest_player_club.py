"""A player's club follows his latest match, even when matches are ingested out of order (docs/41).

Reported: a player on loan still showed his old club, with that club's next match and no forecasts.

Cause: the club was taken from whichever match the queue happened to process last. The queue sorts by priority
and retries failed tasks later, so it does not run in date order; an older match ingested after a recent one put
the player back at the club he had left.
"""
import os, sys, base64
import datetime as dt
os.environ.setdefault("APP_ENCRYPTION_KEY", base64.b64encode(os.urandom(32)).decode())
HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(HERE, "soccer_brain")); sys.path.insert(0, os.path.join(HERE, "tests"))
import mongomock, mongo_init
import ingest as I
import queries as Q


def check(c, m):
    if not c:
        print("  FAIL", m); sys.exit(1)
    print("  ok  ", m)


UTC = dt.timezone.utc
db = mongomock.MongoClient()["pc"]; mongo_init.ensure_indexes(db)
OLD = dt.datetime(2026, 8, 20, tzinfo=UTC)        # at his old club
NEW = dt.datetime(2026, 10, 25, tzinfo=UTC)       # after the loan
db.teams.insert_many([{"iid": 1, "id": "t1", "ext_id": "rm", "name": "Old Club", "league_iid": 1},
                      {"iid": 2, "id": "t2", "ext_id": "fi", "name": "New Club", "league_iid": 2}])
P = {"ext_id": "p77", "name": "A Player", "pos": "FWD", "pos_raw": "F"}

# ---------------------------------------------------------------- out of order: the recent match wins
pid = I.upsert_player(db, P, 2, NEW)              # newest first, as a backfill or a retry may deliver it
check(db.players.find_one({"iid": pid})["team_iid"] == 2, "his latest match puts him at the new club")
I.upsert_player(db, P, 1, OLD)                    # an older match arrives afterwards
check(db.players.find_one({"iid": pid})["team_iid"] == 2,
      "an OLDER match ingested afterwards does not move him back: this was the bug")
check(db.players.find_one({"iid": pid})["name"] == "A Player", "...while his name and position still update")

# ---------------------------------------------------------------- in order: a real move is followed
db.players.delete_many({})
pid = I.upsert_player(db, P, 1, OLD)
check(db.players.find_one({"iid": pid})["team_iid"] == 1, "first match: the club is set")
I.upsert_player(db, P, 2, NEW)
check(db.players.find_one({"iid": pid})["team_iid"] == 2, "a later match moves him, so a real transfer is followed")
check(db.players.find_one({"iid": pid})["team_as_of"].replace(tzinfo=UTC) == NEW, "...and we record which match the club came from")

# ---------------------------------------------------------------- repairing rows written before the fix
db.players.update_one({"iid": pid}, {"$set": {"team_iid": 1}, "$unset": {"team_as_of": ""}})
db.player_match_stats.insert_many([
    {"player_iid": pid, "team_iid": 1, "league_iid": 1, "kickoff": OLD, "match_iid": 10},
    {"player_iid": pid, "team_iid": 2, "league_iid": 2, "kickoff": NEW, "match_iid": 11}])
n = I.refresh_player_clubs(db)
check(n == 1 and db.players.find_one({"iid": pid})["team_iid"] == 2,
      "the repair pass puts an already-wrong player at the club he last played for")
check(I.refresh_player_clubs(db) == 0, "...and changes nothing on a second run")

# ---------------------------------------------------------------- what the player page then shows
db.matches.insert_many([
    {"iid": 20, "id": "m20", "ext_id": "m20", "status": "scheduled", "home_iid": 1, "away_iid": 9,
     "kickoff": dt.datetime.now(UTC) + dt.timedelta(days=2), "league_iid": 1},
    {"iid": 21, "id": "m21", "ext_id": "m21", "status": "scheduled", "home_iid": 2, "away_iid": 8,
     "kickoff": dt.datetime.now(UTC) + dt.timedelta(days=3), "league_iid": 2}])
db.teams.insert_many([{"iid": 9, "id": "t9", "ext_id": "x9", "name": "Someone"}, {"iid": 8, "id": "t8", "ext_id": "x8", "name": "Other"}])
d = Q.player_detail(db, pid)
check(d["team"]["name"] == "New Club", f"the profile names the club he plays for now: {d['team']['name']}")
check(d["next_match"]["iid"] == 21, "...and the next match is his new club's, not his old club's")

print("\nALL PLAYER CLUB CHECKS PASSED")
