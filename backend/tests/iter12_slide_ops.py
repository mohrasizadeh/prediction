# Iteration 12 helper: turn the TEST copy into a live slide-in (immediate) and pause the TEST modal; "cleanup" deletes all non-owner popups
import os, sys, json, requests
API = os.environ["REACT_APP_BACKEND_URL"].rstrip("/") + "/api"
OWN = {"6ae01bc88f38f65403cf2974", "6ae01b996b81e54c91bf4ee2", "6ae01aabb9a354f428999af6"}
s = requests.Session()
s.cookies.update(json.load(open("/tmp/t12_cookies.json"))["admin"])
meta = s.get(f"{API}/admin/popups/meta").json()
mine = [p for p in s.get(f"{API}/admin/popups").json()["popups"] if p["id"] not in OWN]
print([(p["id"], p["name"], p["status"]) for p in mine])
if sys.argv[1:] == ["cleanup"]:
    for p in mine:
        assert p["name"].startswith("TEST"), p
        print("del", p["id"], s.delete(f"{API}/admin/popups/{p['id']}").status_code)
    sys.exit()
for p in mine:
    if p["name"] == "TEST modal t12":
        print("pause modal", s.post(f"{API}/admin/popups/{p['id']}/status", json={"status": "paused"}).status_code)
    elif "copy" in p["name"]:
        d = s.get(f"{API}/admin/popups/{p['id']}").json()
        data = {k: v for k, v in d.items() if k in meta["blank"]}
        data["name"] = "TEST slide t12"; data["kind"] = "slide_in"; data["content"]["title"] = "TEST slide-in"
        r = s.put(f"{API}/admin/popups/{p['id']}", json={"data": data}); print("save", r.status_code, r.text[:200])
        print("live", s.post(f"{API}/admin/popups/{p['id']}/status", json={"status": "live"}).status_code)
