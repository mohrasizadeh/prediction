# Iteration 21: an admin's Hide on a yellow-card forecast must survive the next cards_model run (scratch DB only)
import os
import sys
import datetime

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
from dotenv import load_dotenv  # noqa: E402
load_dotenv(os.path.join(os.path.dirname(HERE), ".env"))
from pymongo import MongoClient  # noqa: E402
import cards_model as CM  # noqa: E402

MC = MongoClient(os.environ["MONGO_URL"])


@pytest.fixture
def scratch():
    name = "test_iter21_scratch_cards"
    MC.drop_database(name)
    db = MC[name]
    yield db
    MC.drop_database(name)


def test_hidden_match_yellow_survives_rerun(scratch):
    db = scratch
    now = datetime.datetime.now(datetime.timezone.utc)
    m = {"iid": 1, "league_iid": 9, "home_iid": 11, "away_iid": 12, "kickoff": now + datetime.timedelta(days=1), "status": "scheduled", "referee": None}
    db.matches.insert_one(dict(m))
    db.teams.insert_many([{"iid": 11, "name": "TEST_A"}, {"iid": 12, "name": "TEST_B"}])
    thr = CM.MATCH_THR[0]
    fkey = f"1:team:11:0:match_yellow_cards:{thr:g}"
    db.forecasts.insert_one({"fkey": fkey, "match_iid": 1, "stat": "match_yellow_cards", "scope": "team", "hidden": True,
                             "hidden_reason": "TEST", "hidden_by": "t", "hidden_at": now, "created_at": now, "is_current": True})
    ln = {"team": {}, "avg_team": 2.0, "ids": set(), "pos90": {"DEF": 0.2}}
    CM.run_match(db, m, "run-x", now, ln)
    row = db.forecasts.find_one({"fkey": fkey})
    assert row is not None
    assert row.get("hidden") is True, "admin Hide was lost: run_match deletes old rows before _kept() reads them"
