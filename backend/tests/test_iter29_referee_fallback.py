# Iteration 29: match detail must not 500 when referee_stats rows lack normalised fields
import os
import random
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
S = requests.Session()


def _get(path):
    return S.get(f"{BASE_URL}{path}", timeout=30)


# Reported match: legacy referee row -> fallback sentence
def test_reported_match_200():
    r = _get("/api/matches/bde08683-1ffb-4133-83ff-f21cf12fda95")
    assert r.status_code == 200, r.text[:300]
    ref = r.json().get("referee")
    assert ref and ref["referee"] == "Luca Pairetto"
    assert isinstance(ref["sentence"], str) and len(ref["sentence"]) > 10
    print("REF:", ref)


def test_second_match_200():
    r = _get("/api/matches/4530cfaa-3977-4e68-a02f-c22c0e2ad100")
    assert r.status_code == 200, r.text[:300]
    print("REF2:", r.json().get("referee"))


def _collect_ids(obj, out):
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k in ("id", "match_id") and isinstance(v, str) and len(v) == 36 and v.count("-") == 4:
                out.add(v)
            _collect_ids(v, out)
    elif isinstance(obj, list):
        for x in obj:
            _collect_ids(x, out)


# Sample 30 matches from today + leagues and ensure none 500
def test_sample_matches_no_500():
    ids = set()
    # note: /api/today does not exist; sample via leagues detail + fixtures
    lg = _get("/api/leagues")
    d = lg.json() if lg.status_code == 200 else {}
    leagues = [l for c in d.get("countries", []) for l in c.get("leagues", [])]
    for l in leagues[:10]:
        lid = l.get("id") or l.get("iid")
        r = _get(f"/api/leagues/{lid}")
        if r.status_code == 200:
            _collect_ids(r.json(), ids)
        f = _get(f"/api/leagues/{lid}/fixtures")
        if f.status_code == 200:
            _collect_ids(f.json(), ids)
    ids = list(ids)
    random.seed(29)
    sample = random.sample(ids, min(30, len(ids)))
    bad, checked = [], 0
    for mid in sample:
        r = _get(f"/api/matches/{mid}")
        if r.status_code == 404:
            continue  # id may be a team/league id
        checked += 1
        if r.status_code >= 500:
            bad.append((mid, r.status_code))
    print(f"collected={len(ids)} sampled={len(sample)} checked={checked} bad={bad}")
    assert checked >= 15
    assert not bad
