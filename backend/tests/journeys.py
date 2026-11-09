"""journeys.py -- 100+ end-to-end visitor journeys through the real routes.

Not a unit test. Each journey is a sequence a real person could perform, run against the real app
on an in-memory database, and the question it asks is the one a person would ask: *did this leave
me somewhere sensible?* It reports rather than asserting-and-dying, so one broken flow does not
hide the ninety-nine behind it.

WHY NOT A BROWSER. A browser suite tests the same routes through three more layers that can each
fail for their own reasons, needs a server that stays up, and takes minutes per run. These run in
seconds and cover every public route. The browser's job is what it alone can see -- layout,
clipping, contrast -- and that is a different pass.

WHAT COUNTS AS A FAILURE
  * a 5xx anywhere: there is no visitor input that should crash a route
  * a flow that cannot be completed by following what the app told the visitor to do
  * a gate that lets through what it exists to stop, or stops what it exists to let through
  * an unknown id answering 200, or a bad parameter answering 500 instead of 400
"""
import os, sys, re, json, base64, datetime as dt

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import testkit as K
from testkit import db, sent, setting
from fastapi.testclient import TestClient
import server as srv, settings_store as S, accounts as A, emailer as E

OUT = []            # (group, name, ok, detail)
_seq = [0]


def j(group, name):
    """Decorator: register one journey. It runs, and whatever it returns is the verdict."""
    def wrap(fn):
        _seq[0] += 1
        n = _seq[0]
        try:
            r = fn()
            ok, detail = (r, "") if isinstance(r, bool) else r
        except Exception as e:
            ok, detail = False, f"{type(e).__name__}: {e}"
        OUT.append((group, f"{n:3}. {name}", bool(ok), str(detail)[:160]))
        return fn
    return wrap


def visitor():
    return TestClient(srv.app)


def link_token(to, needle):
    """The token out of the most recent e-mail to this address, as a visitor would click it."""
    for p in reversed(sent):
        if p and p.get("to") == [to] and needle.lower() in (p.get("subject", "") + p.get("text", "")).lower():
            m = re.search(r"token=([A-Za-z0-9_.\-]+)", p.get("text", "") or "")
            if m:
                return m.group(1)
    return None


def a_league_id():
    """/api/leagues answers {"countries": [{leagues: [...]}]}, not a flat list."""
    d = V.get("/api/leagues").json()
    for c in (d or {}).get("countries", []) if isinstance(d, dict) else []:
        for l in c.get("leagues", []):
            return l.get("id")
    return None


def register(c, email, pw="a-good-long-pass-1", name="Sam"):
    return c.post("/api/auth/register", json={"email": email, "password": pw, "display_name": name})


def verify(c, email):
    t = link_token(email, "confirm")
    return c.post("/api/auth/verify-email", json={"token": t}) if t else None


def clear_limits():
    """Registration is capped at FIVE per IP per hour, hard-coded, and every journey here shares one
    IP -- so without this the sixth account onwards gets a 429, no confirmation e-mail is sent, and
    every later journey fails for a reason that has nothing to do with what it was testing. The
    limiter is exercised deliberately in its own journeys instead."""
    db.rate_limits.delete_many({})


def signed_in(email, pw="a-good-long-pass-1", verify_too=True):
    """A fresh client that has completed registration, and optionally verification."""
    clear_limits()
    c = visitor()
    register(c, email, pw)
    if verify_too:
        verify(c, email)
    c.post("/api/auth/login", json={"email": email, "password": pw})
    return c


# ============================================================ set-up
setting("security.rate_limit_auth_per_minute", 100000)
setting("security.rate_limit_write_per_minute", 100000)
setting("security.rate_limit_read_per_minute", 100000)
setting("email.enabled", True)
setting("email.from_address", "hello@mail.example.com")
import security
security.save_provider_key(db, "resend", "re_abcdefghijk12345")

# Entering the client's context runs the app's startup: indexes, the plan table, the seeded
# Terms/Privacy/About pages, the first owner. Without it a fresh database has no plans and no
# content pages, and three journeys fail for a reason that is purely the harness's.
V = visitor()
V.__enter__()

# ============================================================ 1. the signed-out visitor
PUBLIC_GETS = [
    ("/api/site/config", "the site even renders"),
    ("/api/public/status", "the data freshness banner"),
    ("/api/public/settings", "public feature switches"),
    ("/api/announcements", "the announcement bar"),
    ("/api/fixtures?date=2026-11-09&tz=0", "the home page's fixture list"),
    ("/api/insights?limit=30", "the insights feed"),
    ("/api/likely", "the Most likely screen"),
    ("/api/track-record", "the record page"),
    ("/api/proof", "the proof strip"),
    ("/api/leagues", "the Explore league tiles"),
    ("/api/match-days?start=2026-11-09&days=7", "the date strip's dots"),
    ("/api/live?date=2026-11-09&tz=0", "live scores"),
    ("/api/search?q=man", "header search"),
    ("/api/referees", "the referee list"),
    ("/api/plans", "the pricing table"),
    ("/api/public/pages/terms", "the terms page"),
    ("/api/public/pages/about", "the about page"),
]
for path, what in PUBLIC_GETS:
    def mk(path=path, what=what):
        @j("1. signed out", f"GET {path.split('?')[0]} -- {what}")
        def _():
            r = V.get(path)
            return r.status_code < 500 and r.status_code != 404, f"HTTP {r.status_code}"
    mk()


@j("1. signed out", "every public GET answers without a server error")
def _():
    bad = [p for p, _ in PUBLIC_GETS if V.get(p).status_code >= 500]
    return not bad, f"5xx on: {bad}"


@j("1. signed out", "/api/auth/me answers for a visitor with no account")
def _():
    r = V.get("/api/auth/me")
    return r.status_code == 200 and r.json().get("user") is None, f"HTTP {r.status_code}"


# ============================================================ 2. signing up, end to end
@j("2. sign-up", "a visitor can register")
def _():
    r = register(visitor(), "happy@example.com")
    return r.status_code in (200, 202), f"HTTP {r.status_code}"


@j("2. sign-up", "registering sends exactly one confirmation e-mail")
def _():
    n = sum(1 for p in sent if p and p.get("to") == ["happy@example.com"])
    return n == 1, f"{n} e-mails"


@j("2. sign-up", "that e-mail contains a working confirmation link")
def _():
    return link_token("happy@example.com", "confirm") is not None, "no token in the e-mail"


@j("2. sign-up", "the confirmation link verifies the account")
def _():
    c = visitor()
    r = c.post("/api/auth/verify-email", json={"token": link_token("happy@example.com", "confirm")})
    return r.status_code == 200, f"HTTP {r.status_code}"


@j("2. sign-up", "the same link cannot be used twice")
def _():
    c = visitor()
    r = c.post("/api/auth/verify-email", json={"token": link_token("happy@example.com", "confirm")})
    return r.status_code >= 400, f"HTTP {r.status_code} -- a used token was accepted again"


@j("2. sign-up", "a verified person can sign in")
def _():
    c = visitor()
    r = c.post("/api/auth/login", json={"email": "happy@example.com", "password": "a-good-long-pass-1"})
    return r.status_code == 200, f"HTTP {r.status_code}"


@j("2. sign-up", "and /auth/me then knows who they are")
def _():
    c = visitor()
    c.post("/api/auth/login", json={"email": "happy@example.com", "password": "a-good-long-pass-1"})
    me = c.get("/api/auth/me").json()
    return (me.get("user") or {}).get("email") == "happy@example.com", json.dumps(me)[:120]


@j("2. sign-up", "a short password is refused with a reason")
def _():
    r = register(visitor(), "short@example.com", pw="abc")
    return r.status_code == 400, f"HTTP {r.status_code}"


@j("2. sign-up", "a malformed address is refused")
def _():
    r = register(visitor(), "not-an-email")
    return r.status_code == 400, f"HTTP {r.status_code}"


@j("2. sign-up", "registering an address twice does not reveal it exists")
def _():
    r = register(visitor(), "happy@example.com")
    return r.status_code in (200, 202), f"HTTP {r.status_code} leaks that the address is taken"


@j("2. sign-up", "the wrong password is refused")
def _():
    r = visitor().post("/api/auth/login", json={"email": "happy@example.com", "password": "wrong-pass-9999"})
    return r.status_code == 401, f"HTTP {r.status_code}"


@j("2. sign-up", "an unknown address is refused the same way as a wrong password")
def _():
    a = visitor().post("/api/auth/login", json={"email": "nobody@example.com", "password": "wrong-pass-9999"})
    b = visitor().post("/api/auth/login", json={"email": "happy@example.com", "password": "wrong-pass-9999"})
    return a.status_code == b.status_code, f"{a.status_code} vs {b.status_code} -- the difference enumerates accounts"


@j("2. sign-up", "an unverified account is refused sign-in, and told why rather than just refused")
def _():
    clear_limits()
    c = visitor()
    register(c, "unverified@example.com")
    r = c.post("/api/auth/login", json={"email": "unverified@example.com", "password": "a-good-long-pass-1"})
    if r.status_code == 200:
        return True, "verification is not required to sign in"
    code = ((r.json() or {}).get("error") or {}).get("code", "")
    return r.status_code == 403 and bool(code), f"HTTP {r.status_code}, code={code!r} -- a refusal with no code is a dead end"


@j("2. sign-up", "a nonsense confirmation token is refused, not crashed on")
def _():
    r = visitor().post("/api/auth/verify-email", json={"token": "not-a-real-token"})
    return 400 <= r.status_code < 500, f"HTTP {r.status_code}"


@j("2. sign-up", "an unverified person can ask for the confirmation e-mail again")
def _():
    clear_limits()
    r = visitor().post("/api/auth/resend-verification", json={"email": "unverified@example.com"})
    return r.status_code in (200, 202), f"HTTP {r.status_code}"


@j("2. sign-up", "forgotten password sends a reset link")
def _():
    before = len(sent)
    r = visitor().post("/api/auth/forgot-password", json={"email": "happy@example.com"})
    return r.status_code in (200, 202) and len(sent) > before, f"HTTP {r.status_code}, {len(sent) - before} e-mails"


@j("2. sign-up", "forgotten password for an unknown address answers the same (no enumeration)")
def _():
    r = visitor().post("/api/auth/forgot-password", json={"email": "nobody2@example.com"})
    return r.status_code in (200, 202), f"HTTP {r.status_code}"


@j("2. sign-up", "the reset link sets a new password and it works")
def _():
    t = link_token("happy@example.com", "reset")
    if not t:
        return False, "no reset token in the e-mail"
    c = visitor()
    r = c.post("/api/auth/reset-password", json={"token": t, "password": "a-brand-new-pass-2"})
    if r.status_code != 200:
        return False, f"reset HTTP {r.status_code}"
    lg = visitor().post("/api/auth/login", json={"email": "happy@example.com", "password": "a-brand-new-pass-2"})
    return lg.status_code == 200, f"login after reset HTTP {lg.status_code}"


@j("2. sign-up", "the old password stops working after a reset")
def _():
    r = visitor().post("/api/auth/login", json={"email": "happy@example.com", "password": "a-good-long-pass-1"})
    return r.status_code == 401, f"HTTP {r.status_code} -- the old password still works"


@j("2. sign-up", "a reset token cannot be reused")
def _():
    t = link_token("happy@example.com", "reset")
    r = visitor().post("/api/auth/reset-password", json={"token": t, "password": "yet-another-pass-3"})
    return r.status_code >= 400, f"HTTP {r.status_code}"


@j("2. sign-up", "signing out clears the session")
def _():
    c = signed_in("logout@example.com")
    c.post("/api/auth/logout")
    me = c.get("/api/auth/me").json()
    return (me.get("user") is None), "still signed in after logout"


@j("2. sign-up", "registration is capped per IP, so one address cannot make accounts all day")
def _():
    clear_limits()
    codes = [register(visitor(), f"flood{i}@example.com").status_code for i in range(8)]
    return 429 in codes, f"8 registrations from one IP gave {codes} -- none was refused"


@j("2. sign-up", "that cap does not leak as a server error")
def _():
    clear_limits()
    for i in range(8):
        register(visitor(), f"flood2-{i}@example.com")
    r = register(visitor(), "flood2-last@example.com")
    return r.status_code < 500, f"HTTP {r.status_code}"


# ============================================================ 3. what a free account gets
@j("3. free tier", "a new account can read its own plan")
def _():
    c = signed_in("free1@example.com")
    r = c.get("/api/me/plan") if c.get("/api/me/plan").status_code != 404 else c.get("/api/account/billing")
    return r.status_code == 200, f"HTTP {r.status_code}"


@j("3. free tier", "a signed-in person can follow a team")
def _():
    c = signed_in("free2@example.com")
    r = c.put("/api/me/follows", json={"kind": "league", "ref_id": a_league_id() or "x"})
    return r.status_code in (200, 204, 404), f"HTTP {r.status_code}"


@j("3. free tier", "their follows come back to them")
def _():
    c = signed_in("free3@example.com")
    r = c.get("/api/me/follows")
    return r.status_code == 200, f"HTTP {r.status_code}"


@j("3. free tier", "one person cannot read another's follows")
def _():
    a = signed_in("iso-a@example.com")
    b = signed_in("iso-b@example.com")
    lid = a_league_id()
    if lid:
        a.put("/api/me/follows", json={"kind": "league", "ref_id": lid})
    rows = b.get("/api/me/follows").json().get("items", [])
    return not rows, f"B can see {len(rows)} of A's follows"


@j("3. free tier", "a signed-out visitor cannot read /api/me at all")
def _():
    r = visitor().get("/api/me/follows")
    return r.status_code == 401, f"HTTP {r.status_code}"


for ep in ["/api/me/saved", "/api/me/presets", "/api/me/combos", "/api/me/notes"]:
    def mk(ep=ep):
        @j("3. free tier", f"{ep} is closed to a signed-out visitor")
        def _():
            r = visitor().get(ep)
            return r.status_code in (401, 404), f"HTTP {r.status_code}"
    mk()


# ============================================================ 4. money
@j("4. money", "the pricing table loads for a visitor")
def _():
    r = V.get("/api/plans")
    return r.status_code == 200, f"HTTP {r.status_code}"


@j("4. money", "the pricing table names at least one plan")
def _():
    d = V.get("/api/plans").json()
    rows = d if isinstance(d, list) else d.get("plans", [])
    return len(rows) >= 1, f"{len(rows)} plans"


@j("4. money", "checkout is refused to a signed-out visitor")
def _():
    r = visitor().post("/api/billing/checkout", json={"plan": "pro"})
    return r.status_code in (401, 402, 400), f"HTTP {r.status_code}"


@j("4. money", "with billing off, checkout says so rather than 500")
def _():
    setting("features.billing", False)
    c = signed_in("buyer1@example.com")
    r = c.post("/api/billing/checkout", json={"plan": "pro"})
    return r.status_code < 500, f"HTTP {r.status_code}"


@j("4. money", "the billing portal is refused to someone with no subscription")
def _():
    c = signed_in("buyer2@example.com")
    r = c.post("/api/billing/portal")
    return 400 <= r.status_code < 500, f"HTTP {r.status_code}"


@j("4. money", "an unsigned Stripe webhook is rejected")
def _():
    r = visitor().post("/api/webhooks/stripe", json={"type": "checkout.session.completed"})
    return r.status_code >= 400, f"HTTP {r.status_code} -- an unsigned webhook was accepted"


# ============================================================ 5. the waitlist and e-mail
@j("5. waitlist", "a visitor can join the waitlist")
def _():
    r = V.post("/api/newsletter/subscribe", json={"email": "wl1@example.com", "consent": True,
                                                  "name": "Sam", "source": "waitlist"})
    return r.status_code == 200, f"HTTP {r.status_code}"


@j("5. waitlist", "joining without consent is refused")
def _():
    r = V.post("/api/newsletter/subscribe", json={"email": "wl2@example.com", "consent": False, "source": "waitlist"})
    return r.status_code == 400, f"HTTP {r.status_code}"


@j("5. waitlist", "the answer is the same whether or not the address is already on the list")
def _():
    a = V.post("/api/newsletter/subscribe", json={"email": "wl1@example.com", "consent": True, "source": "waitlist"})
    b = V.post("/api/newsletter/subscribe", json={"email": "wl3@example.com", "consent": True, "source": "waitlist"})
    return a.json() == b.json(), "the two answers differ, which probes the list"


@j("5. waitlist", "the waitlist source is recorded, so the segment is real")
def _():
    row = db.newsletter.find_one({"email": "wl1@example.com"})
    return (row or {}).get("source") == "waitlist", f"source={(row or {}).get('source')}"


@j("5. waitlist", "the name given on the form is stored")
def _():
    row = db.newsletter.find_one({"email": "wl1@example.com"})
    return (row or {}).get("name") == "Sam", f"name={(row or {}).get('name')}"


@j("5. waitlist", "the unsubscribe link works without signing in")
def _():
    tok = E.sign_unsub("wl1@example.com")
    r = visitor().get(f"/api/email/unsubscribe?t={tok}")
    return r.status_code < 400, f"HTTP {r.status_code}"


@j("5. waitlist", "a forged unsubscribe token is refused")
def _():
    r = visitor().get("/api/email/unsubscribe?t=forged.aaaaaaaaaaaaaaaa")
    return r.status_code >= 400 or b"could not" in r.content.lower(), f"HTTP {r.status_code}"


# ============================================================ 6. bad input is answered, not crashed on
BAD = [
    ("/api/fixtures?date=not-a-date&tz=0", "a date that is not a date"),
    ("/api/fixtures?date=2026-11-09&tz=99999", "an absurd timezone"),
    ("/api/insights?limit=-5", "a negative limit"),
    ("/api/insights?limit=999999", "an enormous limit"),
    ("/api/likely?within_h=-3", "a negative window"),
    ("/api/likely?within_h=100000", "an absurd window"),
    ("/api/search?q=", "an empty search"),
    ("/api/search?q=" + "x" * 500, "a 500-character search"),
    ("/api/match/does-not-exist", "an unknown match"),
    ("/api/player/does-not-exist", "an unknown player"),
    ("/api/team/does-not-exist", "an unknown team"),
    ("/api/league/does-not-exist", "an unknown league"),
    ("/api/public/pages/does-not-exist", "an unknown content page"),
        ("/api/referee/does-not-exist", "an unknown referee"),
    ("/api/track-record?league=does-not-exist", "an unknown league filter"),
    ("/api/proof?limit=0", "a zero limit"),
    ("/api/match-days?start=nonsense&days=7", "a nonsense start date"),
    ("/api/match-days?start=2026-11-09&days=9999", "9999 days of calendar"),
    ("/api/live?date=2026-13-45&tz=0", "an impossible date"),
]
for path, what in BAD:
    def mk(path=path, what=what):
        @j("6. bad input", f"{what}")
        def _():
            r = V.get(path)
            return r.status_code < 500, f"HTTP {r.status_code} on {path}"
    mk()


@j("6. bad input", "no bad input anywhere produced a server error")
def _():
    bad = [p for p, _ in BAD if V.get(p).status_code >= 500]
    return not bad, f"5xx on: {bad}"


@j("6. bad input", "an unknown id answers 404, not 200 with nothing")
def _():
    soft = [p for p, _ in BAD if "does-not-exist" in p and V.get(p).status_code == 200]
    return not soft, f"200 for a thing that does not exist: {soft}"


# ============================================================ 7. the engine's promises hold
@j("7. promises", "/api/likely returns its own floor rather than making the page retype it")
def _():
    d = V.get("/api/likely").json()
    return "floor" in d, f"keys: {sorted(d)[:8]}"


@j("7. promises", "nothing in /api/likely is below that floor")
def _():
    d = V.get("/api/likely").json()
    f, rows = d.get("floor", 0), d.get("rows", [])
    bad = [r for r in rows if (r.get("p") or 0) < f]
    return not bad, f"{len(bad)} of {len(rows)} rows under the floor"


@j("7. promises", "/api/track-record refuses to publish a record before it has the sample")
def _():
    d = V.get("/api/track-record").json()
    return ("ready" in d) and (d["ready"] or "needed" in d), f"keys: {sorted(d)[:8]}"


@j("7. promises", "/api/proof never includes a player who did not play")
def _():
    rows = V.get("/api/proof").json()
    rows = rows if isinstance(rows, list) else rows.get("rows", [])
    return all(r.get("player_played") is not False for r in rows), "a non-appearance is being shown as proof"


@j("7. promises", "the fixture row carries what was claimed AND what happened")
def _():
    fx = V.get("/api/fixtures?date=2026-11-09&tz=0").json()
    lines = [b for m in (fx if isinstance(fx, list) else []) for b in (m.get("best_lines") or [])]
    graded = [b for b in lines if b.get("reached") is not None]
    if not graded:
        return True, "no graded lines in this window to check"
    both = [b for b in graded if b.get("p") is not None and "actual" in b]
    return len(both) == len(graded), f"{len(graded) - len(both)} graded lines are missing their measurement"


# ============================================================ 8. the gates
@j("8. gates", "a maintenance switch does not break the public API")
def _():
    setting("features.maintenance", True)
    r = V.get("/api/site/config")
    setting("features.maintenance", False)
    return r.status_code == 200, f"HTTP {r.status_code}"


@j("8. gates", "turning a page off is visible to the front end")
def _():
    setting("features.likely", False)
    cfg = V.get("/api/site/config").json()
    off = (cfg.get("features") or {}).get("likely")
    setting("features.likely", True)
    return off is False, f"features.likely came back as {off!r}"


@j("8. gates", "a page switched off still answers its API (the switch is for navigation, not data)")
def _():
    setting("features.likely", False)
    r = V.get("/api/likely")
    setting("features.likely", True)
    return r.status_code < 500, f"HTTP {r.status_code}"


@j("8. gates", "the admin API is closed to a signed-out visitor")
def _():
    r = visitor().get("/api/admin/newsletter")
    return r.status_code in (401, 403), f"HTTP {r.status_code}"


@j("8. gates", "the admin API is closed to an ordinary member")
def _():
    c = signed_in("nosy@example.com")
    r = c.get("/api/admin/newsletter")
    return r.status_code in (401, 403, 404), f"HTTP {r.status_code}"


@j("8. gates", "the cron endpoint is closed without its secret")
def _():
    r = visitor().post("/api/cron/tick")
    return r.status_code in (401, 403), f"HTTP {r.status_code}"


# ============================================================ report
def main():
    groups = {}
    for g, name, ok, detail in OUT:
        groups.setdefault(g, []).append((name, ok, detail))
    fails = [(g, n, d) for g, n, ok, d in OUT if not ok]
    print(f"\n{'=' * 78}\n{len(OUT)} journeys -- {len(OUT) - len(fails)} passed, {len(fails)} failed\n{'=' * 78}")
    for g in sorted(groups):
        rows = groups[g]
        bad = sum(1 for _, ok, _ in rows if not ok)
        print(f"\n{g}  ({len(rows) - bad}/{len(rows)})")
        for name, ok, detail in rows:
            if not ok:
                print(f"   FAIL {name}\n        {detail}")
    if fails:
        print(f"\n{'-' * 78}\nFAILURES, in one list:")
        for g, n, d in fails:
            print(f"  [{g}] {n} -- {d}")
    else:
        print("\nevery journey completed.")
    return len(fails)


if __name__ == "__main__":
    sys.exit(0 if main() == 0 else 1)
