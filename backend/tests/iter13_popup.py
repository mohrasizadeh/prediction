# Iteration 13 helper: create a live TEST modal popup with an e-mail form (priority 100), or delete TEST popups
import sys
sys.path.insert(0, __import__("os").path.dirname(__file__))
import iter12_popup_ops as O

if sys.argv[1] == "make":
    print([t["label"] for t in O.meta["templates"]])
    tid = [t["id"] for t in O.meta["templates"] if t.get("kind", "") == "modal" or "sign" in t["label"].lower()][0]
    pid = O.s.post(f"{O.API}/admin/popups", json={"template": tid}).json()["id"]
    O.save(pid, name="TEST iter13 modal", priority=100, targeting__audience="all", targeting__visitors="all",
           targeting__pages_include=["/*"], trigger__type="immediate")
    O.status(pid, "live")
    d = O.data_of(pid)
    print("LIVE", pid, d.get("kind"), d.get("form", {}).get("enabled"), d.get("frequency"))
elif sys.argv[1] == "clean":
    for p in O.lst():
        if p["name"].startswith("TEST") or p["name"] in ("New popup",):
            print("del", p["id"], p["name"], O.s.delete(f"{O.API}/admin/popups/{p['id']}").status_code)
