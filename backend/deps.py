"""deps.py -- FastAPI dependencies shared by every router: database, cookie, current user, permissions."""
from __future__ import annotations

import hashlib
import os

from fastapi import Depends, HTTPException, Request, Response

import accounts as A

SECURE = os.environ.get("COOKIE_SECURE", "1") == "1"
COOKIE = "__Host-sid" if SECURE else "sid"      # __Host- cookies must be Secure, Path=/, and have no Domain


def get_db(request: Request):
    return request.app.state.db


def anon_subject(request: Request) -> str:
    ip = getattr(request.state, "ip", "") or ""
    return "ip:" + hashlib.sha256((ip + request.headers.get("user-agent", "")).encode()).hexdigest()[:16]


def err(status: int, code: str, message: str = ""):
    return HTTPException(status, detail={"code": code, "message": message})


# An upstream service refused us -- a data provider, mostly. This is deliberately NOT a 5xx.
#
# 502 was the obvious choice and it cost a day of blind guessing. A hosting ingress replaces the
# BODY of a 5xx with its own error page, so our
#     {"error": {"code": "PROVIDER", "message": "<what the provider actually said>"}}
# never reached the browser. `lib/api.js` then fell back to "SERVER_ERROR", which is what it says
# when a body will not parse -- so the admin screen reported a fault in OUR server for a refusal by
# THEIRS, and the one useful sentence was thrown away in transit. The app log showed 502 with an
# empty trace and no reason, because a deliberate error is not a crash.
#
# 409 is what the provider errors that DO arrive intact already use (budget spent, breaker open,
# key rejected, plan limited), which is the evidence that it passes through. The status here is
# read by an operator looking at a screen, and what they need is the reason, not the number.
#
# docs/86.
UPSTREAM = 409


def upstream(code: str, message: str = ""):
    """An upstream said no. Carries their reason through to the screen; see UPSTREAM."""
    return err(UPSTREAM, code, message)


def set_session_cookie(response: Response, token: str, max_age: int | None = None) -> None:
    response.set_cookie(COOKIE, token, httponly=True, secure=SECURE, samesite="lax", path="/", max_age=max_age)


def clear_session_cookie(response: Response) -> None:
    response.delete_cookie(COOKIE, path="/", secure=SECURE, httponly=True, samesite="lax")


def session_token(request: Request) -> str | None:
    return request.cookies.get(COOKIE)


def current(request: Request, db=Depends(get_db)):
    """(user, session) for any valid session, including an enrol-2FA-only one. (None, None) when signed out."""
    if not hasattr(request.state, "auth"):
        request.state.auth = A.load_session(db, session_token(request))
        if request.state.auth[0]:
            request.state.user_id = request.state.auth[0]["id"]
    return request.state.auth


def optional_user(auth=Depends(current)):
    u, s = auth
    return u if u and s["scope"] == "full" else None


def any_session_user(auth=Depends(current)):
    u, s = auth
    if not u:
        raise err(401, "SIGN_IN_REQUIRED", "Sign in to continue.")
    return u


def require_user(auth=Depends(current)):
    u, s = auth
    if not u:
        raise err(401, "SIGN_IN_REQUIRED", "Sign in to continue.")
    if s["scope"] != "full":
        raise err(403, "ENROLL_2FA_REQUIRED", "Set up two-factor sign-in to continue.")
    return u


def require_perm(perm: str):
    """Staff only, full session, and the role must hold `perm`. Checked on the server on every request."""
    def dep(user=Depends(require_user)):
        if user["role"] not in A.STAFF or not A.can(user, perm):
            raise err(403, "FORBIDDEN", "Your role cannot do this.")
        return user
    return dep
