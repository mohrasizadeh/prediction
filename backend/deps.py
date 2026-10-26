"""deps.py -- FastAPI dependencies shared by every router: database, cookie, current user, permissions."""
from __future__ import annotations

import os

from fastapi import Depends, HTTPException, Request, Response

import accounts as A

SECURE = os.environ.get("COOKIE_SECURE", "1") == "1"
COOKIE = "__Host-sid" if SECURE else "sid"      # __Host- cookies must be Secure, Path=/, and have no Domain


def get_db(request: Request):
    return request.app.state.db


def err(status: int, code: str, message: str = ""):
    return HTTPException(status, detail={"code": code, "message": message})


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
