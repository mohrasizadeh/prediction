# iter26 R6: admin home (tiles + needs), shell tabs, settings provenance, availability image + cycle,
# engine switch settings present, provider status by_kind, photo_plan removal, permissions.
import os, sys, pytest, requests

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
BASE = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/") or open("/app/frontend/.env").read().split("REACT_APP_BACKEND_URL=")[1].split()[0].rstrip("/")
os.environ["REACT_APP_BACKEND_URL"] = BASE
from admin_login_helper import admin_session  # noqa: E402

USER = {"email": "test_e1_user@example.com", "password": "Test-User-Pass-2026!q"}


@pytest.fixture(scope="module")
def admin():
    try:
        return admin_session()
    except Exception as e:
        pytest.skip(f"admin login failed: {e}")


@pytest.fixture(scope="module")
def user():
    s = requests.Session(); s.headers["User-Agent"] = "TEST_ua_iter26_user"
    r = s.post(f"{BASE}/api/auth/login", json=USER)
    if r.status_code != 200:
        pytest.skip(f"user login failed {r.status_code}")
    return s


@pytest.fixture(scope="module")
def home(admin):
    r = admin.get(f"{BASE}/api/admin/home"); assert r.status_code == 200, r.text
    return r.json()


# home: shape + tiles
def test_home_shape(home):
    assert set(["now", "name", "tiles", "needs"]) <= set(home)
    ids = [t["id"] for t in home["tiles"]]
    assert ids == ["data", "live", "engine", "images", "users", "money"]
    for t in home["tiles"]:
        assert t["tone"] in ("green", "amber", "red", "off")
        assert t["module"] in ("jobs", "integrations", "engine", "users", "subscriptions")
    assert "_id" not in str(home)


def test_home_name_uses_display_name(home):
    # admin was created with display_name "TEST Admin"
    assert home["name"] == "TEST", f"home name = {home['name']!r}; expected display_name first word"


def test_data_tile_budget(home):
    d = home["tiles"][0]
    assert d["provider"] == "PitchAPI" and isinstance(d["used"], int) and d["cap"] > 0
    assert d["reset_at"].startswith(home["now"][:4]) and "T00:00:00" in d["reset_at"]
    if d["used"] >= d["cap"]:
        assert d["tone"] == "red"
    live = home["tiles"][1]
    assert live["provider"] == "SportAPI" and isinstance(live["by_kind"], dict)
    assert live["tone"] == ("off" if not live["enabled"] else live["tone"])


def test_needs_items(home):
    for n in home["needs"]:
        assert n["kind"] in ("match", "image", "job", "alert", "issue", "inbox") and n["key"]
        if n["kind"] == "issue":
            assert n["ids"] and isinstance(n["ids"], list)
            if len(n["ids"]) > 1:
                assert f"({len(n['ids'])} times)" in n["text"]


# permissions
def test_home_perms(user):
    assert requests.get(f"{BASE}/api/admin/home").status_code == 401
    assert user.get(f"{BASE}/api/admin/home").status_code == 403


# shell: modules + default tabs
def test_shell_tabs(admin):
    d = admin.get(f"{BASE}/api/admin/shell").json()
    ids = {m["id"]: m for m in d["modules"]}
    assert ids["dashboard"]["route"] == "/admin" and ids["dashboard"]["label"] == "Home"
    assert ids["needs"]["route"] == "/admin/needs" and ids["stats"]["route"] == "/admin/stats"
    assert d["mobile_tabs"] == ["dashboard", "needs", "jobs", "engine"], d["mobile_tabs"]


# settings provenance
def test_settings_provenance(admin):
    rows = admin.get(f"{BASE}/api/admin/settings").json()
    assert all("updated_by" in r and "updated_at" in r and "default" in r for r in rows)
    keys = {r["key"] for r in rows}
    for k in ("engine.absence_model", "engine.match_context", "engine.calibration", "context.start_model"):
        assert k in keys, k
    changed = [r for r in rows if not r.get("is_default")]
    assert any(r["updated_by"] for r in changed) or not changed


# sportapi by_kind
def test_sportapi_status(admin):
    r = admin.get(f"{BASE}/api/admin/sportapi")
    if r.status_code == 404:
        pytest.skip("no sportapi status route")
    assert r.status_code == 200 and "by_kind" in r.json()


# availability: image field, cycle + restore
def test_availability_cycle(admin):
    clubs = admin.get(f"{BASE}/api/admin/clubs").json()
    team = clubs["leagues"][0]["teams"][0]["id"]
    pl = admin.get(f"{BASE}/api/admin/availability", params={"team": team}).json()["players"]
    assert pl and all("image" in p for p in pl)
    p = next(x for x in pl if x["status"] == "available")
    try:
        r = admin.put(f"{BASE}/api/admin/availability", json={"player_id": p["id"], "status": "doubtful", "reason": "TEST_ knock", "until": None})
        assert r.status_code == 200, r.text
        got = {x["id"]: x for x in admin.get(f"{BASE}/api/admin/availability", params={"team": team}).json()["players"]}[p["id"]]
        assert got["status"] == "doubtful" and got["reason"] == "TEST_ knock"
        assert admin.put(f"{BASE}/api/admin/availability", json={"player_id": p["id"], "status": "out", "reason": "", "until": "2020-01-01T00:00:00Z"}).status_code == 400
    finally:
        admin.put(f"{BASE}/api/admin/availability", json={"player_id": p["id"], "status": "available", "reason": "", "until": None})
    got = {x["id"]: x for x in admin.get(f"{BASE}/api/admin/availability", params={"team": team}).json()["players"]}[p["id"]]
    assert got["status"] == "available"


# regression, INVERTED: `photo_plan` is gone, and this test asserted that it had run OK.
#
# It was written when player photographs came from cdn.pitchapi.dev, a call per player, planned by a
# `photo_plan` job. Pictures now come from api-football.com only -- the logo is a URL on the entity
# itself, so there is nothing to plan -- and `jobs.tick` deliberately has no such step (see the
# comment there). A test that requires a removed job to have run is a test that can only ever fail,
# and it fails for the one reason that is not a bug. What is worth pinning is the removal: nothing
# should be scheduling it, and the thing that replaced it should be the only image path.
def test_photo_plan_is_gone():
    sys.path.insert(0, "/app/backend")
    import jobs
    src = open(os.path.join(os.path.dirname(jobs.__file__), "jobs.py")).read()
    code = "\n".join(ln for ln in src.splitlines() if not ln.lstrip().startswith("#"))
    assert "photo_plan" not in code, "jobs.tick schedules photo_plan again"
    assert "images" in code, "the image step that replaced it is missing"
