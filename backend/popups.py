"""popups.py -- the Popup Maker.

A popup is a small, accessible message the site shows at the right moment to the right people:
a centred modal, a corner slide-in, or a top or bottom banner. The owner builds it in the admin (no code).

Division of work
  Server  decides WHO may see it: live, inside its dates, the page, the audience (signed out, free, paid, trial), device,
          new or returning visitor, and which A/B version. It sends only the popups that qualify.
  Browser decides WHEN: the trigger (immediately, after N seconds, scrolled N%, mouse leaving the page, N pages viewed,
          or a button click), the frequency memory, and the session limits. It reports view / click / dismiss / submit.

Safety rules built in
  * Plain text only. No HTML, no scripts. Buttons are links we validated.
  * Never on /admin, sign-in, sign-up, reset, verification or checkout pages (ALWAYS_EXCLUDE).
  * Every modal and slide-in has a close button. Full-screen takeovers do not exist.
  * An e-mail field needs the consent sentence, and goes through newsletter.subscribe (double opt-in).
  * The words in doc 03 are refused, as everywhere else.
  * A global switch (`popups.enabled`) and session limits (`popups.max_per_session`, `popups.min_gap_seconds`).
"""
from __future__ import annotations

import copy
import hashlib
import re
from datetime import datetime, timedelta, timezone

from bson import ObjectId

import accounts as A
import plans as P
import settings_store as S
import site_studio as SS
import textguard

KINDS = ("modal", "slide_in", "banner_top", "banner_bottom")
TRIGGERS = ("immediate", "delay", "scroll", "exit_intent", "pageviews", "click")
AUDIENCES = ("all", "signed_out", "signed_in", "free", "paid", "trial")
FREQUENCIES = ("once", "every_n_days", "every_session", "until_action")
DEVICES = ("desktop", "mobile")
VISITORS = ("all", "new", "returning")
TONES = ("default", "brand", "info", "warn")
SIZES = ("sm", "md", "lg")
STATUSES = ("draft", "live", "paused")
EVENTS = ("view", "click", "dismiss", "submit")
ALWAYS_EXCLUDE = ("/admin", "/signin", "/sign-in", "/login", "/signup", "/sign-up", "/reset", "/verify", "/checkout", "/account/billing", "/newsletter/confirm", "/maintenance")
MAX_POPUPS = 60


def utcnow():
    return datetime.now(timezone.utc)


def _aware(d):
    return d.replace(tzinfo=timezone.utc) if d is not None and d.tzinfo is None else d


def blank() -> dict:
    return copy.deepcopy({
        "name": "New popup", "status": "draft", "kind": "modal", "priority": 50,
        "content": {"title": "", "body": "", "image": "", "image_alt": "", "buttons": [{"label": "Learn more", "action": "link", "route": "/pricing", "style": "primary"}]},
        "form": {"enabled": False, "placeholder": "Your e-mail", "button_label": "Subscribe", "consent_text": "", "success_text": "Thanks. Check your inbox to confirm."},
        "design": {"size": "md", "align": "left", "tone": "default", "position": "bottom_right", "show_close": True, "backdrop_close": True},
        "trigger": {"type": "delay", "delay_s": 8, "scroll_pct": 50, "pageviews": 2},
        "targeting": {"pages_include": ["/*"], "pages_exclude": [], "audience": "all", "devices": ["desktop", "mobile"], "visitors": "all"},
        "frequency": {"mode": "every_n_days", "n_days": 7, "after_action_days": 90},
        "schedule": {"starts_at": None, "ends_at": None},
        "ab": {"group": "", "weight": 50},
    })


def _p(problems, path, msg):
    problems.append({"path": path, "message": msg})


def _pattern_ok(s) -> bool:
    return isinstance(s, str) and re.fullmatch(r"/[A-Za-z0-9/_\-.*]{0,120}", s) is not None


def _dt(v):
    if v in (None, ""):
        return None
    if isinstance(v, datetime):
        return _aware(v)
    try:
        d = datetime.fromisoformat(str(v).replace("Z", "+00:00"))
        return _aware(d)
    except ValueError:
        return "bad"


def validate(data: dict) -> tuple[dict, list]:
    """Returns (clean popup, warnings) or raises SiteError with every problem."""
    problems: list = []
    warns: list = []
    base = blank()
    if not isinstance(data, dict):
        raise SS.SiteError([{"path": "popup", "message": "Must be an object."}])
    for k in data:
        if k not in base:
            _p(problems, k, "Unknown field.")
    d = {}
    for k, v in base.items():
        d[k] = copy.deepcopy(data.get(k, v))
        if isinstance(v, dict) and isinstance(d[k], dict):
            for kk in d[k]:
                if kk not in v:
                    _p(problems, f"{k}.{kk}", "Unknown field.")
            d[k] = {kk: d[k].get(kk, vv) for kk, vv in v.items()}
    if not (isinstance(d["name"], str) and 1 <= len(d["name"].strip()) <= 60): _p(problems, "name", "1 to 60 characters (only staff see it).")
    if d["status"] not in STATUSES: _p(problems, "status", "draft, live or paused.")
    if d["kind"] not in KINDS: _p(problems, "kind", f"One of {', '.join(KINDS)}.")
    if not SS._intr(d["priority"], 0, 100): _p(problems, "priority", "0 to 100. Higher shows first.")

    c = d["content"]
    if not (isinstance(c["title"], str) and len(c["title"]) <= 80): _p(problems, "content.title", "Up to 80 characters.")
    if not (isinstance(c["body"], str) and len(c["body"]) <= 400): _p(problems, "content.body", "Up to 400 characters, plain text.")
    if re.search(r"<[^>]*>", (c["title"] or "") + (c["body"] or "")): _p(problems, "content.body", "No HTML. Plain text only.")
    if not SS.valid_image(c["image"]): _p(problems, "content.image", "Use an uploaded image or an https address.")
    if c["image"] and not (isinstance(c["image_alt"], str) and 3 <= len(c["image_alt"]) <= 100): _p(problems, "content.image_alt", "Describe the image in 3 to 100 characters (screen readers read it).")
    if not (c["title"] or c["body"]): _p(problems, "content", "Add a title or some text.")
    btns = c["buttons"]
    if not isinstance(btns, list) or len(btns) > 2: _p(problems, "content.buttons", "Up to 2 buttons."); btns = []
    for i, b in enumerate(btns):
        if not isinstance(b, dict) or set(b) != {"label", "action", "route", "style"}:
            _p(problems, f"content.buttons[{i}]", "Needs label, action, route, style."); continue
        if not SS._str(b["label"], 1, 24): _p(problems, f"content.buttons[{i}].label", "1 to 24 characters.")
        if b["action"] not in ("link", "close"): _p(problems, f"content.buttons[{i}].action", "link or close.")
        if b["action"] == "link" and not SS.valid_route(b["route"]): _p(problems, f"content.buttons[{i}].route", "Use /path or an https address.")
        if b["style"] not in ("primary", "secondary", "ghost"): _p(problems, f"content.buttons[{i}].style", "primary, secondary or ghost.")

    f = d["form"]
    if not isinstance(f["enabled"], bool): _p(problems, "form.enabled", "true or false.")
    elif f["enabled"]:
        if not SS._str(f["placeholder"], 1, 40): _p(problems, "form.placeholder", "1 to 40 characters.")
        if not SS._str(f["button_label"], 1, 24): _p(problems, "form.button_label", "1 to 24 characters.")
        if not (isinstance(f["consent_text"], str) and 20 <= len(f["consent_text"].strip()) <= 240):
            _p(problems, "form.consent_text", "Write the sentence people agree to, for example 'Yes, send me the weekly forecast e-mail. I can unsubscribe any time.' (20 to 240 characters)")
        if not SS._str(f["success_text"], 1, 120): _p(problems, "form.success_text", "1 to 120 characters.")
        if len(btns) > 1: warns.append({"path": "content.buttons", "message": "A form plus two buttons is a lot for one popup. Keep one action."})

    g = d["design"]
    if g["size"] not in SIZES: _p(problems, "design.size", "sm, md or lg.")
    if g["align"] not in ("left", "center"): _p(problems, "design.align", "left or center.")
    if g["tone"] not in TONES: _p(problems, "design.tone", f"One of {', '.join(TONES)}.")
    if g["position"] not in ("bottom_right", "bottom_left"): _p(problems, "design.position", "bottom_right or bottom_left.")
    if not isinstance(g["show_close"], bool) or not isinstance(g["backdrop_close"], bool): _p(problems, "design", "show_close and backdrop_close must be true or false.")
    elif d["kind"] in ("modal", "slide_in") and not g["show_close"] and not any(b.get("action") == "close" for b in btns if isinstance(b, dict)):
        _p(problems, "design.show_close", "Every popup needs a way to close it: show the close button or add a close button.")

    t = d["trigger"]
    if t["type"] not in TRIGGERS: _p(problems, "trigger.type", f"One of {', '.join(TRIGGERS)}.")
    if not SS._intr(t["delay_s"], 0, 300): _p(problems, "trigger.delay_s", "0 to 300 seconds.")
    if not SS._intr(t["scroll_pct"], 5, 100): _p(problems, "trigger.scroll_pct", "5 to 100.")
    if not SS._intr(t["pageviews"], 1, 20): _p(problems, "trigger.pageviews", "1 to 20.")
    if t["type"] == "immediate" and d["kind"] in ("modal",):
        warns.append({"path": "trigger.type", "message": "A modal that opens the moment the page loads annoys people, and on phones search engines can mark the page down. Try a delay or a scroll trigger."})
    if t["type"] == "delay" and isinstance(t["delay_s"], int) and t["delay_s"] < 3 and d["kind"] == "modal":
        warns.append({"path": "trigger.delay_s", "message": "Under 3 seconds feels like an ambush."})
    if t["type"] == "exit_intent":
        warns.append({"path": "trigger.type", "message": "Exit intent only works with a mouse. On phones this popup never shows."})

    tg = d["targeting"]
    for k in ("pages_include", "pages_exclude"):
        if not isinstance(tg[k], list) or len(tg[k]) > 30 or not all(_pattern_ok(x) for x in tg[k]):
            _p(problems, f"targeting.{k}", "Up to 30 paths like /finder or /teams/* (star = anything).")
    if isinstance(tg["pages_include"], list) and not tg["pages_include"]: _p(problems, "targeting.pages_include", "Add at least one page, or /* for all pages.")
    if tg["audience"] not in AUDIENCES: _p(problems, "targeting.audience", f"One of {', '.join(AUDIENCES)}.")
    if not isinstance(tg["devices"], list) or not tg["devices"] or any(x not in DEVICES for x in tg["devices"]): _p(problems, "targeting.devices", "desktop and/or mobile.")
    if tg["visitors"] not in VISITORS: _p(problems, "targeting.visitors", "all, new or returning.")

    fq = d["frequency"]
    if fq["mode"] not in FREQUENCIES: _p(problems, "frequency.mode", f"One of {', '.join(FREQUENCIES)}.")
    if not SS._intr(fq["n_days"], 1, 365): _p(problems, "frequency.n_days", "1 to 365.")
    if not SS._intr(fq["after_action_days"], 1, 365): _p(problems, "frequency.after_action_days", "1 to 365.")
    if fq["mode"] == "until_action" and d["kind"] == "modal": warns.append({"path": "frequency.mode", "message": "A modal on every visit until someone acts can feel pushy."})

    sc = d["schedule"]
    s0, s1 = _dt(sc["starts_at"]), _dt(sc["ends_at"])
    if s0 == "bad": _p(problems, "schedule.starts_at", "Use a date like 2026-11-01 or 2026-11-01T09:00:00Z.")
    if s1 == "bad": _p(problems, "schedule.ends_at", "Use a date like 2026-11-30.")
    if s0 not in (None, "bad") and s1 not in (None, "bad") and s1 <= s0: _p(problems, "schedule.ends_at", "The end must be after the start.")
    ab = d["ab"]
    if not (isinstance(ab["group"], str) and re.fullmatch(r"[a-z0-9-]{0,30}", ab["group"])): _p(problems, "ab.group", "a-z, 0-9 and dashes, up to 30. Popups with the same group name compete: each visitor sees one.")
    if not SS._intr(ab["weight"], 1, 100): _p(problems, "ab.weight", "1 to 100.")

    if not problems:
        bad = textguard.find({k: d[k] for k in ("content", "form")})
        if bad: _p(problems, "content", f"These words are not allowed on the site: {', '.join(bad)}.")
    if problems:
        raise SS.SiteError(problems)
    d["schedule"] = {"starts_at": s0, "ends_at": s1}
    return d, warns


# ----------------------------------------------------------------------------- storage
def _public_id(doc) -> str:
    return str(doc["_id"])


def _row(doc: dict, stats: dict | None = None) -> dict:
    out = {k: v for k, v in doc.items() if k != "_id"}
    out["id"] = _public_id(doc)
    out["state"] = state_of(doc)
    if stats is not None:
        out["stats"] = stats
    return out


def state_of(doc: dict, now=None) -> str:
    now = now or utcnow()
    if doc["status"] == "draft": return "draft"
    if doc["status"] == "paused": return "paused"
    s0, s1 = _aware(doc["schedule"].get("starts_at")), _aware(doc["schedule"].get("ends_at"))
    if s0 and now < s0: return "scheduled"
    if s1 and now >= s1: return "ended"
    return "running"


def create(db, actor: str, data: dict | None = None) -> tuple[str, list]:
    if db.popups.count_documents({}) >= MAX_POPUPS:
        raise ValueError("You have 60 popups. Delete old ones first.")
    clean, warns = validate({**blank(), **(data or {})})
    now = utcnow()
    pid = db.popups.insert_one({**clean, "created_at": now, "updated_at": now, "created_by": actor, "updated_by": actor}).inserted_id
    db.audit_log.insert_one({"actor": actor, "action": "popup.create", "target": str(pid), "at": now})
    return str(pid), warns


def _oid(pid: str):
    try:
        return ObjectId(pid)
    except Exception:
        raise A.AuthError("NOT_FOUND", 404, "No such popup.")


def update(db, actor: str, pid: str, data: dict) -> list:
    cur = db.popups.find_one({"_id": _oid(pid)})
    if not cur:
        raise A.AuthError("NOT_FOUND", 404, "No such popup.")
    merged = {k: v for k, v in cur.items() if k not in ("_id", "created_at", "updated_at", "created_by", "updated_by")}
    for k, v in data.items():
        merged[k] = v if not isinstance(v, dict) or not isinstance(merged.get(k), dict) else {**merged[k], **v}
    clean, warns = validate(merged)
    db.popups.update_one({"_id": cur["_id"]}, {"$set": {**clean, "updated_at": utcnow(), "updated_by": actor}})
    db.audit_log.insert_one({"actor": actor, "action": "popup.update", "target": pid, "at": utcnow()})
    return warns


def set_status(db, actor: str, pid: str, status: str) -> None:
    if status not in STATUSES:
        raise A.AuthError("BAD_STATUS", 400)
    cur = db.popups.find_one({"_id": _oid(pid)})
    if not cur:
        raise A.AuthError("NOT_FOUND", 404, "No such popup.")
    if status == "live":
        validate({k: v for k, v in cur.items() if k not in ("_id", "created_at", "updated_at", "created_by", "updated_by")})
    db.popups.update_one({"_id": cur["_id"]}, {"$set": {"status": status, "updated_at": utcnow(), "updated_by": actor}})
    db.audit_log.insert_one({"actor": actor, "action": f"popup.{status}", "target": pid, "at": utcnow()})


def duplicate(db, actor: str, pid: str) -> str:
    cur = db.popups.find_one({"_id": _oid(pid)})
    if not cur:
        raise A.AuthError("NOT_FOUND", 404, "No such popup.")
    data = {k: v for k, v in cur.items() if k not in ("_id", "created_at", "updated_at", "created_by", "updated_by")}
    data["name"] = (data["name"] + " copy")[:60]
    data["status"] = "draft"
    new, _ = create(db, actor, data)
    return new


def delete(db, actor: str, pid: str) -> None:
    db.popups.delete_one({"_id": _oid(pid)})
    db.popup_stats.delete_many({"popup_id": pid})
    db.audit_log.insert_one({"actor": actor, "action": "popup.delete", "target": pid, "at": utcnow()})


def get(db, pid: str) -> dict | None:
    try:
        doc = db.popups.find_one({"_id": ObjectId(pid)})
    except Exception:
        return None
    return _row(doc, totals(db, pid)) if doc else None


def list_all(db) -> list[dict]:
    tot = all_totals(db)
    return [_row(d, tot.get(str(d["_id"]), _zero())) for d in db.popups.find({}).sort([("priority", -1), ("created_at", -1)])]


# ----------------------------------------------------------------------------- who may see it
def _match(patterns: list[str], path: str) -> bool:
    for p in patterns:
        rx = "^" + re.escape(p).replace(r"\*", ".*") + "$"
        if re.match(rx, path):
            return True
        if p.endswith("/*") and path == p[:-2]:          # /teams/* also matches /teams
            return True
    return False


def audience_class(db, user: dict | None) -> str:
    if user is None:
        return "signed_out"
    ep = P.effective_plan(db, user)
    if ep["source"] in ("subscription", "comp"):
        return "trial" if ep.get("status") == "trialing" else "paid"
    return "free"                          # includes 'billing off': nobody pays, so everybody is 'free' for targeting


def _aud_ok(want: str, have: str) -> bool:
    return want == "all" or want == have or (want == "signed_in" and have != "signed_out")


def _bucket(vid: str, group: str) -> float:
    return int(hashlib.sha256(f"{vid}|{group}".encode()).hexdigest()[:8], 16) / 0xFFFFFFFF


def eligible(db, *, path: str, device: str, user: dict | None, visitor: str = "new", vid: str = "", now=None, only_id: str | None = None) -> dict:
    """What the browser may show on this page for this person. The browser applies trigger, frequency and limits."""
    now = now or utcnow()
    limits = {"max_per_session": int(S.get(db, "popups.max_per_session")), "min_gap_seconds": int(S.get(db, "popups.min_gap_seconds"))}
    if not S.get(db, "popups.enabled") or S.get(db, "features.maintenance"):
        return {"popups": [], "limits": limits}
    if _match(list(ALWAYS_EXCLUDE) + [p + "/*" for p in ALWAYS_EXCLUDE], path) or path.startswith("/api"):
        return {"popups": [], "limits": limits}
    if only_id:                                              # staff preview: show exactly this popup, ignore targeting
        try:
            d = db.popups.find_one({"_id": ObjectId(only_id)})
        except Exception:
            d = None
        return {"popups": [public_view(d)] if d else [], "limits": limits}
    have = audience_class(db, user)
    q = {"status": "live"}
    cand = []
    for d in db.popups.find(q):
        if state_of(d, now) != "running":
            continue
        tg = d["targeting"]
        if not _match(tg["pages_include"], path) or _match(tg["pages_exclude"], path):
            continue
        if not _aud_ok(tg["audience"], have) or device not in tg["devices"]:
            continue
        if tg["visitors"] != "all" and tg["visitors"] != visitor:
            continue
        if d["trigger"]["type"] == "exit_intent" and device != "desktop":
            continue
        cand.append(d)
    # A/B groups: popups sharing a group name compete. One winner per visitor, by weight, stable for that visitor.
    out, groups = [], {}
    for d in cand:
        g = d["ab"]["group"]
        if g:
            groups.setdefault(g, []).append(d)
        else:
            out.append(d)
    for g, ds in groups.items():
        total = sum(x["ab"]["weight"] for x in ds)
        r, acc = _bucket(vid or "anon", g) * total, 0
        for x in sorted(ds, key=lambda y: str(y["_id"])):
            acc += x["ab"]["weight"]
            if r <= acc:
                out.append(x)
                break
    out.sort(key=lambda d: (-d["priority"], str(d["_id"])))
    return {"popups": [public_view(d) for d in out[:3]], "limits": limits}


def public_view(d: dict) -> dict:
    f = d["form"]
    return {"id": _public_id(d), "kind": d["kind"], "content": d["content"],
            "form": {k: f[k] for k in ("enabled", "placeholder", "button_label", "consent_text", "success_text")} if f["enabled"] else {"enabled": False},
            "design": d["design"], "trigger": d["trigger"], "frequency": d["frequency"], "ab_group": d["ab"]["group"] or None}


# ----------------------------------------------------------------------------- counting
def _zero() -> dict:
    return {"view": 0, "click": 0, "dismiss": 0, "submit": 0}


def record(db, pid: str, event: str, now=None) -> bool:
    if event not in EVENTS:
        return False
    try:
        oid = ObjectId(pid)
    except Exception:
        return False
    d = db.popups.find_one({"_id": oid}, {"status": 1})
    if not d or d["status"] == "draft":
        return False
    now = now or utcnow()
    db.popup_stats.update_one({"popup_id": pid, "day": now.strftime("%Y-%m-%d")},
                              {"$inc": {event: 1}, "$setOnInsert": {"expires_at": now + timedelta(days=800)}}, upsert=True)
    return True


def totals(db, pid: str, days: int | None = None, now=None) -> dict:
    q: dict = {"popup_id": pid}
    if days:
        q["day"] = {"$gte": ((now or utcnow()) - timedelta(days=days - 1)).strftime("%Y-%m-%d")}
    t = _zero()
    for r in db.popup_stats.find(q):
        for k in t:
            t[k] += int(r.get(k, 0))
    return _with_rates(t)


def _with_rates(t: dict) -> dict:
    v = t["view"]
    t["click_rate"] = round(t["click"] / v, 4) if v else None
    t["submit_rate"] = round(t["submit"] / v, 4) if v else None
    t["dismiss_rate"] = round(t["dismiss"] / v, 4) if v else None
    return t


def all_totals(db) -> dict:
    out: dict = {}
    for r in db.popup_stats.find({}):
        t = out.setdefault(r["popup_id"], _zero())
        for k in ("view", "click", "dismiss", "submit"):
            t[k] += int(r.get(k, 0))
    return {k: _with_rates(v) for k, v in out.items()}


def series(db, pid: str, days: int = 30, now=None) -> list[dict]:
    now = now or utcnow()
    ds = [(now - timedelta(days=i)).strftime("%Y-%m-%d") for i in range(days - 1, -1, -1)]
    rows = {r["day"]: r for r in db.popup_stats.find({"popup_id": pid, "day": {"$gte": ds[0]}})}
    return [{"day": d, **{k: int(rows.get(d, {}).get(k, 0)) for k in EVENTS}} for d in ds]


def ab_report(db, group: str) -> dict:
    """Compare the popups in one A/B group. Says 'too early' until each has 200 views. Not a statistical test; a guide."""
    rows = []
    for d in db.popups.find({"ab.group": group}):
        t = totals(db, str(d["_id"]))
        rows.append({"id": str(d["_id"]), "name": d["name"], "weight": d["ab"]["weight"], **t})
    ready = bool(rows) and all(r["view"] >= 200 for r in rows)
    lead = max(rows, key=lambda r: (r["submit_rate"] or 0, r["click_rate"] or 0), default=None) if ready else None
    return {"group": group, "variants": rows, "ready": ready, "leader": lead and lead["id"],
            "note": "Enough views to compare." if ready else "Too early. Wait until every version has at least 200 views."}


# ----------------------------------------------------------------------------- e-mail form
def submit(db, pid: str, email: str, consent: bool, *, ip_hash: str | None = None) -> str:
    """Public. Returns the success text. Always the same answer for new, known and blocked addresses."""
    import newsletter as N
    d = db.popups.find_one({"_id": ObjectId(pid)})
    if not d or d["status"] != "live" or not d["form"]["enabled"]:
        raise A.AuthError("NOT_FOUND", 404, "This form is not available.")
    N.subscribe(db, email, source=f"popup:{pid}", consent_text=d["form"]["consent_text"], consent=consent, ip_hash=ip_hash)
    record(db, pid, "submit")
    try:
        import integrations as INT
        INT.emit(db, "popup.submitted", {"popup": d["name"]}, email=A.norm_email(email))
    except Exception:
        pass
    return d["form"]["success_text"]


# ----------------------------------------------------------------------------- starter templates (the "Start from" gallery)
TEMPLATES = {
    "newsletter_modal": {"label": "E-mail sign-up (centre popup)", "data": {
        "name": "Newsletter sign-up", "kind": "modal",
        "content": {"title": "Get the weekly forecast e-mail", "body": "One short e-mail each week with the best statistical reads and the reasons behind them.", "image": "", "image_alt": "", "buttons": []},
        "form": {"enabled": True, "placeholder": "Your e-mail", "button_label": "Sign me up", "consent_text": "Yes, send me the weekly forecast e-mail. I can unsubscribe at any time.", "success_text": "Thanks. Check your inbox to confirm."},
        "trigger": {"type": "scroll", "delay_s": 8, "scroll_pct": 45, "pageviews": 2},
        "targeting": {"pages_include": ["/*"], "pages_exclude": [], "audience": "signed_out", "devices": ["desktop", "mobile"], "visitors": "all"},
        "frequency": {"mode": "every_n_days", "n_days": 14, "after_action_days": 180}}},
    "newsletter_slide": {"label": "E-mail sign-up (corner slide-in)", "data": {
        "name": "Newsletter slide-in", "kind": "slide_in",
        "content": {"title": "Weekly forecast e-mail", "body": "The best reads of the week, with reasons.", "image": "", "image_alt": "", "buttons": []},
        "form": {"enabled": True, "placeholder": "Your e-mail", "button_label": "Join", "consent_text": "Yes, send me the weekly forecast e-mail. I can unsubscribe at any time.", "success_text": "Thanks. Check your inbox to confirm."},
        "trigger": {"type": "delay", "delay_s": 20, "scroll_pct": 50, "pageviews": 2},
        "targeting": {"pages_include": ["/*"], "pages_exclude": [], "audience": "signed_out", "devices": ["desktop", "mobile"], "visitors": "returning"},
        "frequency": {"mode": "every_n_days", "n_days": 21, "after_action_days": 180}}},
    "upgrade_banner": {"label": "Upgrade banner (bottom)", "data": {
        "name": "Upgrade banner", "kind": "banner_bottom",
        "content": {"title": "See more of every match", "body": "Pro unlocks the Matchup tab and unlimited Finder searches.", "image": "", "image_alt": "", "buttons": [{"label": "See plans", "action": "link", "route": "/pricing", "style": "primary"}]},
        "design": {"size": "md", "align": "left", "tone": "brand", "position": "bottom_right", "show_close": True, "backdrop_close": True},
        "trigger": {"type": "pageviews", "delay_s": 8, "scroll_pct": 50, "pageviews": 4},
        "targeting": {"pages_include": ["/finder*", "/insights*", "/teams/*"], "pages_exclude": [], "audience": "free", "devices": ["desktop", "mobile"], "visitors": "all"},
        "frequency": {"mode": "every_n_days", "n_days": 7, "after_action_days": 90}}},
    "announcement_bar": {"label": "Announcement bar (top)", "data": {
        "name": "Announcement bar", "kind": "banner_top",
        "content": {"title": "", "body": "New this week: team style matchups on every match page.", "image": "", "image_alt": "", "buttons": [{"label": "Take a look", "action": "link", "route": "/", "style": "ghost"}]},
        "design": {"size": "sm", "align": "center", "tone": "info", "position": "bottom_right", "show_close": True, "backdrop_close": True},
        "trigger": {"type": "immediate", "delay_s": 0, "scroll_pct": 50, "pageviews": 1},
        "frequency": {"mode": "every_n_days", "n_days": 3, "after_action_days": 30}}},
    "feature_slide_in": {"label": "Feature spotlight (slide-in)", "data": {
        "name": "Feature spotlight", "kind": "slide_in",
        "content": {"title": "New: the Matchup tab", "body": "See how each team's style meets the other's, and why it moves the forecast.", "image": "", "image_alt": "", "buttons": [{"label": "Try it", "action": "link", "route": "/", "style": "primary"}, {"label": "Not now", "action": "close", "route": "", "style": "ghost"}]},
        "trigger": {"type": "delay", "delay_s": 12, "scroll_pct": 50, "pageviews": 2},
        "targeting": {"pages_include": ["/*"], "pages_exclude": [], "audience": "signed_in", "devices": ["desktop", "mobile"], "visitors": "all"},
        "frequency": {"mode": "once", "n_days": 7, "after_action_days": 90}}},
}


def template_data(key: str) -> dict:
    if key not in TEMPLATES:
        raise A.AuthError("NOT_FOUND", 404, "No such template.")
    d = copy.deepcopy(TEMPLATES[key]["data"])
    for k, v in d.items():
        if isinstance(v, dict) and isinstance(blank().get(k), dict):
            d[k] = {**blank()[k], **v}
    return d


def create_from_template(db, actor: str, key: str) -> tuple[str, list]:
    return create(db, actor, template_data(key))
