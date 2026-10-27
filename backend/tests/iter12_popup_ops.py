# Iteration 12 helper: manipulate popups via API using the saved TEST admin cookie (avoids 2FA re-login rate limits)
import os, sys, json, requests
API = os.environ["REACT_APP_BACKEND_URL"].rstrip("/") + "/api"
s = requests.Session()
s.cookies.update(json.load(open("/tmp/t12_cookies.json"))["admin"])
meta = s.get(f"{API}/admin/popups/meta").json()


def data_of(pid):
    d = s.get(f"{API}/admin/popups/{pid}").json()
    return {k: v for k, v in d.items() if k in meta["blank"]}


def save(pid, **patch):
    d = data_of(pid)
    for path, v in patch.items():
        cur = d
        ks = path.split("__")
        for k in ks[:-1]:
            cur = cur[k]
        cur[ks[-1]] = v
    r = s.put(f"{API}/admin/popups/{pid}", json={"data": d})
    print("save", pid, r.status_code, r.text[:200])


def status(pid, st):
    print("status", pid, st, s.post(f"{API}/admin/popups/{pid}/status", json={"status": st}).status_code)


def lst():
    return s.get(f"{API}/admin/popups").json()["popups"]


def from_template(label):
    tid = [t["id"] for t in meta["templates"] if t["label"] == label][0]
    pid = s.post(f"{API}/admin/popups", json={"template": tid}).json()["id"]
    save(pid, targeting__audience="all", targeting__visitors="all", trigger__type="immediate")
    return pid


if __name__ == "__main__":
    cmd = sys.argv[1]
    if cmd == "list":
        for p in lst():
            print(p["id"], p["name"], p["status"], p["kind"], p.get("ab"), p.get("stats"))
    elif cmd == "ab":
        for p in lst():
            save(p["id"], ab__group="test-t12ab", ab__weight=50)
    elif cmd == "pause_all":
        for p in lst():
            if p["status"] == "live":
                status(p["id"], "paused")
    elif cmd == "only":   # make a template popup the only live one
        for p in lst():
            if p["status"] == "live":
                status(p["id"], "paused")
        pid = from_template(sys.argv[2])
        status(pid, "live")
        print("LIVE", pid)
    elif cmd == "delete_all":
        for p in lst():
            print("del", p["id"], s.delete(f"{API}/admin/popups/{p['id']}").status_code)
