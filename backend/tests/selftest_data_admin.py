"""Phase 1 data screens over HTTP: explorer allow-list, cache hit vs real call, cost, cache delete, usage, leagues."""
from testkit import *
import routes_data_admin as RDA
from cached_fetch import PitchClient

pitch_calls = []


def pitch(r: httpx.Request):
    pitch_calls.append(r.url.path)
    if r.headers.get("X-API-KEY") != "pk_test_abcdefghijklmnop":
        return httpx.Response(401, json={"error": {"code": "UNAUTHORIZED"}})
    if r.url.path == "/v1/leagues":
        return httpx.Response(200, json={"data": {"leagues": [{"id": "L1", "name": "Test League", "country_code": "GB", "seasons": ["2025/2026", "2024/2025"]}]}})
    if r.url.path == "/v1/matches/missing":
        return httpx.Response(404, json={"error": {"code": "RESOURCE_NOT_FOUND"}})
    return httpx.Response(200, json={"data": {"path": r.url.path}})


RDA.make_client = lambda d: PitchClient(d, http=httpx.Client(base_url="https://api.pitchapi.dev", transport=httpx.MockTransport(pitch)), sleep=lambda s: None)

with TestClient(srv.app) as owner:
    admin, support, analyst = boot(owner)
    anon = TestClient(srv.app)
    ex = lambda c, path, params=None, force=False: c.post("/api/admin/explorer", json={"path": path, "params": params or {}, "force": force})

    check(anon.get("/api/admin/usage").status_code in (401, 403), "signed-out visitors cannot see usage")
    check(support.get("/api/admin/usage").status_code == 403 and analyst.post("/api/admin/explorer", json={"path": "/v1/leagues"}).status_code == 403, "support and analyst have no data tools")

    r = ex(admin, "/v1/leagues")
    check(r.status_code == 400 and r.json()["error"]["code"] == "PITCH_KEY" and not pitch_calls, "no key saved: clear error, nothing sent")
    check(owner.put("/api/admin/keys/pitchapi", json={"key": "pk_test_abcdefghijklmnop"}).status_code == 200, "owner saves a PitchAPI key")

    check(ex(admin, "/v1/matches/1/shots").json()["error"]["code"] == "NOT_ALLOWED", "a 'Never' call is refused")
    check(ex(admin, "/v1/leagues", {"evil": "1"}).json()["error"]["code"] == "NOT_ALLOWED", "unknown parameters are refused")
    check(ex(admin, "https://evil.example/v1/leagues").json()["error"]["code"] == "NOT_ALLOWED", "other hosts are refused")

    r = ex(admin, "/v1/leagues"); j = r.json()
    check(r.status_code == 200 and j["from_cache"] is False and j["cost"] == 1 and j["data"]["leagues"][0]["id"] == "L1", "first call is real and costs 1")
    j = ex(admin, "/v1/leagues").json()
    check(j["from_cache"] is True and j["cost"] == 0 and len(pitch_calls) == 1, "second call comes from the cache and costs 0")
    j = ex(admin, "/v1/leagues", force=True).json()
    check(j["from_cache"] is False and j["cost"] == 1 and len(pitch_calls) == 2, "force refresh makes a real call")
    check(db.audit_log.find_one({"action": "explorer.force"}) is not None, "a forced call is audited")
    check(ex(admin, "/v1/matches/missing").status_code == 404, "a provider 404 is reported as not found")
    ex(admin, "/v1/leagues/L1/matches", {"season": "2025/2026", "status": "all"})

    c = admin.get("/api/admin/cache").json()
    check(c["total"] == 3 and all("data_z" not in row for row in c["rows"]), "cache list shows rows without the stored blobs")
    one = admin.get(f"/api/admin/cache/{c['rows'][-1]['id']}").json()
    check(one["data"] is not None or one["error_code"], "one cache row opens with its JSON")
    check(admin.get("/api/admin/cache", params={"q": "/v1/leagues"}).json()["total"] == 2, "search by path prefix")
    check(admin.delete("/api/admin/cache").status_code == 400, "delete needs a key, prefix or all")
    check(admin.delete("/api/admin/cache", params={"prefix": "/v1/matches"}).json()["deleted"] == 1, "delete by prefix")
    check(admin.delete("/api/admin/cache", params={"all": "true"}).json()["deleted"] == 2, "delete all")

    u = admin.get("/api/admin/usage").json()
    check(u["calls_today"] == 4 and len(u["by_day"]) == 14 and u["by_purpose"].get("explorer") == 4 and u["by_status"].get("404") == 1, "usage counts today's calls by purpose and status")
    check(u["budget"] > 0 and u["breaker"]["open"] is False and u["error_codes"].get("RESOURCE_NOT_FOUND") == 1, "budget, breaker state and error codes")

    import ingest as I
    I.sync_leagues(RDA.make_client(db))
    lg = admin.get("/api/admin/leagues").json()["leagues"]
    check(len(lg) == 1 and lg[0]["enabled"] is False and [s["label"] for s in lg[0]["seasons"]] == ["2025/2026", "2024/2025"], "leagues list with seasons; new leagues start off")
    iid = lg[0]["iid"]
    check(admin.put(f"/api/admin/leagues/{iid}", json={"backfill_seasons": ["1999/2000"]}).status_code == 400, "unknown season refused")
    r = admin.put(f"/api/admin/leagues/{iid}", json={"enabled": True, "backfill_seasons": ["2024/2025"]})
    check(r.status_code == 200 and db.seasons.find_one({"league_iid": iid, "label": "2024/2025"})["queued"] is True, "enable and queue a season for backfill")
    body = admin.get("/api/admin/leagues").json()
    lg = body["leagues"][0]
    # The estimate is read against the SAME per-match figure the route reports, not a literal: it
    # depends on the provider, and a hard-coded 3 (PitchAPI's players + stats + lineups) overstated
    # an API-Football backfill by sixty times, because that provider answers twenty fixtures in one
    # call (docs/81 §1).
    cpm = body["calls_per_match"]

    # ---------------- the Competitions list must say which provider each row came from
    # Every league already in the database arrived through ingest.sync_leagues, which never wrote a
    # provider field, so its ext_id is a PitchAPI id. Listing those unlabelled made the screen look
    # like it was pulling PitchAPI ids into an API-Football list (docs/84).
    body = admin.get("/api/admin/leagues").json()
    check(all(l.get("provider") for l in body["leagues"]), "every league row says where it came from")
    check(body["leagues"][0]["provider"] == "pitchapi",
          "a row with no provider field is reported as PitchAPI's, not left blank or claimed for the new one")
    check(body["by_provider"].get("pitchapi") == len(body["leagues"]),
          "the counts let the screen offer a filter rather than mixing them")
    import af_leagues as AFL
    AFL.confirm(db, AFL.BY_KEY["eng.pl"], {"id": 39, "name": "Premier League", "seasons": [2024]})
    body = admin.get("/api/admin/leagues").json()
    check(body["by_provider"].get("apifootball") == 1 and body["by_provider"].get("pitchapi") == 1,
          "a confirmed API-Football competition is counted apart from the old rows")
    af = next(l for l in body["leagues"] if l["provider"] == "apifootball")
    check(af["role"] == "forecast" and af["kind"] == "league",
          "...and carries the role and kind the old rows cannot have")

    # ---------------- the off switches
    check(body["providers_on"]["pitchapi"] is True, "PitchAPI reports as on, which is what the jobs still use")
    check(body["providers_on"]["sportapi"] is False, "SportAPI reports its own enabled setting")
    r = admin.put("/api/admin/settings/pitchapi.enabled", json={"value": False})
    check(r.status_code == 200, "PitchAPI can be switched off from admin")
    import cached_fetch as CF
    try:
        CF.PitchClient(db, http=None)._check_guards()
        check(False, "a switched-off provider refuses to spend a call")
    except CF.Disabled as e:
        check(True, f"a switched-off provider refuses to spend a call ({e})")
    check(issubclass(CF.Disabled, CF.BreakerOpen),
          "...and the refusal is a BreakerOpen, so jobs.py already handles it")
    admin.put("/api/admin/settings/pitchapi.enabled", json={"value": True})
    check(admin.get("/api/admin/leagues").json()["providers_on"]["pitchapi"] is True,
          "switching it back on is one call and spends nothing")

    body = admin.get("/api/admin/leagues").json()
    lg = next(l for l in body["leagues"] if l["provider"] == "pitchapi")
    check(lg["enabled"] is True and lg["backfill_seasons"] == ["2024/2025"]
          and lg["estimate_calls"] == round(1 + 380 * cpm, 1),
          f"estimate for the queued season, at {cpm} calls a match")
    check(body["provider"] and cpm == (1 / 20 if body["provider"] == "apifootball" else 3.0),
          f"the per-match cost follows the provider in use ({body['provider']})")
    admin.put(f"/api/admin/leagues/{iid}", json={"backfill_seasons": []})
    check(db.seasons.find_one({"league_iid": iid, "label": "2024/2025"})["queued"] is False, "un-picking a season un-queues it")
    check(support.put(f"/api/admin/leagues/{iid}", json={"enabled": False}).status_code == 403, "support cannot change leagues")
    check(db.audit_log.count_documents({"action": "league.update"}) == 2, "league changes are audited")
print("data admin self-test passed")
