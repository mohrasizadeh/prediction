# Admin Engine + forecast browser + hide/unhide API tests (GET /api/admin/engine, /api/admin/forecasts, POST hide)
import os
import sys

import pytest
import requests

sys.path.insert(0, os.path.dirname(__file__))
from admin_login_helper import admin_session  # noqa: E402

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")


@pytest.fixture(scope="module")
def s():
    return admin_session()


# --- auth guards
@pytest.mark.parametrize("path", ["/api/admin/engine", "/api/admin/forecasts"])
def test_signed_out_get_denied(path):
    r = requests.get(BASE_URL + path)
    assert r.status_code in (401, 403)


def test_signed_out_hide_denied():
    r = requests.post(BASE_URL + "/api/admin/forecasts/x/hide", json={"hidden": True, "reason": "x"})
    assert r.status_code in (401, 403)


# --- engine status
def test_engine_status(s):
    r = s.get(BASE_URL + "/api/admin/engine", params={"limit": 40})
    assert r.status_code == 200
    d = r.json()
    assert isinstance(d["runs"], list) and isinstance(d["leagues"], list)
    assert len(d["leagues"]) > 0
    for lg in d["leagues"]:
        assert {"league_iid", "name", "markets", "forecasts", "hidden"} <= set(lg)
        assert isinstance(lg["markets"], dict)
    total = sum(lg["forecasts"] for lg in d["leagues"])
    print("leagues", [(l["name"], l["forecasts"], l["hidden"]) for l in d["leagues"]], "total", total)
    assert total > 0
    if d["runs"]:
        assert "_id" not in d["runs"][0] and "status" in d["runs"][0]
        assert "league_name" in d["runs"][0]


# --- forecast browser + filters
def test_forecasts_list_and_filters(s):
    d = s.get(BASE_URL + "/api/admin/forecasts").json()
    assert d["total"] > 0 and d["page"] == 1 and d["limit"] == 50
    assert len(d["rows"]) == min(50, d["total"])
    r0 = d["rows"][0]
    assert "id" in r0 and "market" in r0 and 0 <= r0["p"] <= 1
    team = s.get(BASE_URL + "/api/admin/forecasts", params={"scope": "team"}).json()
    player = s.get(BASE_URL + "/api/admin/forecasts", params={"scope": "player"}).json()
    assert all(x["scope"] == "team" for x in team["rows"])
    assert all(x["scope"] == "player" for x in player["rows"])
    print("total", d["total"], "team", team["total"], "player", player["total"])
    assert team["total"] + player["total"] == d["total"]
    yes = s.get(BASE_URL + "/api/admin/forecasts", params={"hidden": "yes"}).json()
    no = s.get(BASE_URL + "/api/admin/forecasts", params={"hidden": "no"}).json()
    assert yes["total"] + no["total"] == d["total"]
    lg = r0["league_iid"]
    byl = s.get(BASE_URL + "/api/admin/forecasts", params={"league_iid": lg}).json()
    assert all(x["league_iid"] == lg for x in byl["rows"])
    m = r0["market"][:3]
    bym = s.get(BASE_URL + "/api/admin/forecasts", params={"market": m}).json()
    assert bym["total"] > 0 and all(x["market"].lower().startswith(m.lower()) for x in bym["rows"])
    # regex-ish chars must not 500
    assert s.get(BASE_URL + "/api/admin/forecasts", params={"market": "2+ (s[*"}).status_code == 200


def test_forecasts_paging(s):
    p1 = s.get(BASE_URL + "/api/admin/forecasts", params={"page": 1, "limit": 20}).json()
    p2 = s.get(BASE_URL + "/api/admin/forecasts", params={"page": 2, "limit": 20}).json()
    assert p2["page"] == 2 and len(p1["rows"]) == 20
    assert not ({x["id"] for x in p1["rows"]} & {x["id"] for x in p2["rows"]})
    big = s.get(BASE_URL + "/api/admin/forecasts", params={"limit": 1000}).json()
    assert big["limit"] == 100


# --- hide/unhide
def test_hide_validation(s):
    fid = s.get(BASE_URL + "/api/admin/forecasts", params={"hidden": "no", "limit": 1}).json()["rows"][0]["id"]
    r = s.post(BASE_URL + f"/api/admin/forecasts/{fid}/hide", json={"hidden": True, "reason": "   "})
    assert r.status_code == 400
    assert "REASON_REQUIRED" in r.text
    r = s.post(BASE_URL + "/api/admin/forecasts/does-not-exist-xyz/hide", json={"hidden": True, "reason": "TEST_x"})
    assert r.status_code == 404
    r = s.post(BASE_URL + f"/api/admin/forecasts/{fid}/hide", json={"hidden": True, "reason": "x" * 301})
    assert r.status_code == 422


def test_hide_then_unhide_roundtrip(s):
    row = s.get(BASE_URL + "/api/admin/forecasts", params={"hidden": "no", "limit": 1, "page": 3}).json()["rows"][0]
    fid = row["id"]
    try:
        r = s.post(BASE_URL + f"/api/admin/forecasts/{fid}/hide", json={"hidden": True, "reason": "TEST_ api hide"})
        assert r.status_code == 200 and r.json() == {"ok": True, "hidden": True}
        ids = []
        page = 1
        while True:
            d = s.get(BASE_URL + "/api/admin/forecasts", params={"hidden": "yes", "limit": 100, "page": page}).json()
            ids += [x for x in d["rows"]]
            if page * 100 >= d["total"]:
                break
            page += 1
        hit = [x for x in ids if x["id"] == fid]
        assert hit and hit[0]["hidden_reason"] == "TEST_ api hide" and hit[0]["hidden_by"] == "test_e1_admin@example.com"
        eng = s.get(BASE_URL + "/api/admin/engine", params={"limit": 1}).json()
        assert any(l["league_iid"] == row["league_iid"] and l["hidden"] >= 1 for l in eng["leagues"])
    finally:
        r = s.post(BASE_URL + f"/api/admin/forecasts/{fid}/hide", json={"hidden": False, "reason": ""})
        assert r.status_code == 200 and r.json()["hidden"] is False
    d = s.get(BASE_URL + "/api/admin/forecasts", params={"hidden": "yes", "limit": 100}).json()
    assert fid not in [x["id"] for x in d["rows"]]
