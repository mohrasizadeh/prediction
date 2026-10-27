# Iteration 12 probe: find which popup field the editor's save trips on (uses saved TEST admin cookie)
import os, sys, json, requests
API = os.environ["REACT_APP_BACKEND_URL"].rstrip("/") + "/api"
s = requests.Session()
s.cookies.update(json.load(open("/tmp/t12_cookies.json"))["admin"])
pid = open("/tmp/t12_pid").read().strip()
meta = s.get(f"{API}/admin/popups/meta").json()
d = s.get(f"{API}/admin/popups/{pid}").json()
print("keys", sorted(d.keys()), "blank keys", sorted(meta["blank"].keys()))
data = {k: v for k, v in d.items() if k in meta["blank"]}
print(json.dumps(data, default=str)[:1500])
r = s.put(f"{API}/admin/popups/{pid}", json={"data": data})
print("unchanged save", r.status_code, r.text[:400])
for patch in [("targeting", "pages_include", ["*"]), ("trigger", "type", "immediate"), ("frequency", "mode", "every_session")]:
    dd = json.loads(json.dumps(data, default=str))
    dd[patch[0]][patch[1]] = patch[2]
    r = s.put(f"{API}/admin/popups/{pid}", json={"data": dd})
    print(patch, r.status_code, r.text[:300])
