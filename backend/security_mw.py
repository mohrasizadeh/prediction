"""security_mw.py -- one middleware that gives every request the same protections.

    import security_mw; security_mw.install(app, get_db)

What it does, in order, for every /api request:
  1. request id (X-Request-ID) and the real client IP (trusted-proxy aware)
  2. body size cap (Content-Length)
  3. CSRF defence: Origin must be ours on state-changing requests (plus Sec-Fetch-Site)
  4. rate limit per IP (auth / write / read buckets, numbers come from settings)
  5. runs the route; any crash becomes a generic 500 with a request id and NO detail
  6. security headers on every response
  7. writes a row to app_logs for errors, 401/403/429 and admin writes

Cookies are HttpOnly, Secure, SameSite=Lax. Lax + the Origin check + JSON-only bodies is the CSRF plan.
"""
from __future__ import annotations

import time
import traceback
import uuid
from datetime import datetime, timezone

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.base import BaseHTTPMiddleware

import accounts
import textguard
import ratelimit
import settings_store as S

SAFE = ("GET", "HEAD", "OPTIONS")
ORIGIN_EXEMPT = ("/api/webhooks/", "/api/jobs/tick", "/api/jobs/live", "/api/email/unsubscribe")     # no browser cookie involved
# The image route sends a base64 JSON body (512 KB image = about 700 KB). /api/admin/media/upload
# sends the file itself, so its cap is the video cap plus a little room (docs/60).
BIG_BODY = {"/api/admin/site/assets": 900 * 1024, "/api/admin/media/upload": 32 * 1024 * 1024}
RATE_EXEMPT = ("/api/webhooks/", "/api/jobs/tick", "/api/jobs/live", "/api/media/")
_cache: dict = {"at": 0.0, "cfg": None}


def cfg(db) -> dict:
    """security.* settings, cached for 10 seconds so we do not hit the DB on every request."""
    if _cache["cfg"] is None or time.time() - _cache["at"] > 10:
        _cache["cfg"] = S.get_many(db, "security.")
        _cache["at"] = time.time()
    return _cache["cfg"]


def clear_cache() -> None:
    _cache["cfg"] = None


def client_ip(request: Request, trusted: int) -> str:
    """With N trusted proxies the real client is the Nth address from the right of X-Forwarded-For.
    Anything the client put further left is ignored, so it cannot be spoofed."""
    peer = request.client.host if request.client else "0.0.0.0"
    if trusted <= 0:
        return peer
    parts = [p.strip() for p in request.headers.get("x-forwarded-for", "").split(",") if p.strip()]
    return parts[-trusted] if len(parts) >= trusted else peer


def _origin_ok(request: Request, allowed: list[str]) -> bool:
    origin = request.headers.get("origin")
    if origin is None:
        return request.headers.get("sec-fetch-site", "same-origin") in ("same-origin", "same-site", "none")
    host = request.headers.get("x-forwarded-host") or request.headers.get("host", "")
    proto = request.headers.get("x-forwarded-proto") or request.url.scheme
    ours = {f"{proto}://{host}"} | {o.rstrip("/") for o in allowed}
    return origin.rstrip("/") in ours


def _err(status: int, code: str, message: str, rid: str | None = None, headers=None, extra: dict | None = None) -> JSONResponse:
    body = {"error": {"code": code, "message": message}}
    if extra:
        body["error"].update(extra)
    if rid:
        body["error"]["request_id"] = rid
    return JSONResponse(body, status_code=status, headers=headers)


class SecurityMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, get_db):
        super().__init__(app)
        self.get_db = get_db

    async def dispatch(self, request: Request, call_next):
        t0 = time.time()
        db = self.get_db(request)
        rid = request.headers.get("x-request-id", "")[:40] or uuid.uuid4().hex[:16]
        request.state.request_id = rid
        c = await run_in_threadpool(cfg, db)
        ip = client_ip(request, int(c["security.trusted_proxy_count"]))
        request.state.ip = ip
        path, method = request.url.path, request.method
        api = path.startswith("/api/")
        response, exc_text = None, None
        if api:
            cl = request.headers.get("content-length")
            # Was POST-only. /api/admin/media/upload is a PUT, because the body IS the file and
            # there is nothing to post around it, so a PUT measured against security.max_body_kb
            # would have refused every video before the route was reached.
            cap = BIG_BODY.get(path, 0) if method in ("POST", "PUT") else 0
            if cl and cl.isdigit() and int(cl) > max(cap, int(c["security.max_body_kb"]) * 1024):
                response = _err(413, "TOO_LARGE", "That request is too large.", rid)
            elif method not in SAFE and not path.startswith(ORIGIN_EXEMPT) and not _origin_ok(request, c["security.allowed_origins"]):
                response = _err(403, "BAD_ORIGIN", "This request came from somewhere we do not trust.", rid)
            elif not path.startswith(RATE_EXEMPT):
                grp = "auth" if path.startswith("/api/auth/") and not (method == "GET" and path == "/api/auth/me") else ("read" if method in SAFE else "write")
                limit = int(c[f"security.rate_limit_{grp}_per_minute"])
                ok, retry = await run_in_threadpool(ratelimit.hit, db, f"{grp}:{ip}", limit, 60)
                if not ok:
                    response = _err(429, "RATE_LIMITED", "Too many requests. Slow down and try again.", rid, {"Retry-After": str(retry)})
        if response is None:
            try:
                response = await call_next(request)
            except Exception as e:                               # a bug: tell the client nothing useful
                exc_text = "".join(traceback.format_exception(type(e), e, e.__traceback__))[-4000:]
                response = _err(500, "SERVER_ERROR", "Something went wrong on our side.", rid)
        self._headers(request, response, rid, path)
        await run_in_threadpool(self._log, db, request, response, exc_text, ip, path, method, t0)
        return response

    @staticmethod
    def _headers(request, response, rid, path):
        h = response.headers
        h["X-Request-ID"] = rid
        h["X-Content-Type-Options"] = "nosniff"
        h["Referrer-Policy"] = "strict-origin-when-cross-origin"
        h["Permissions-Policy"] = "camera=(), microphone=(), geolocation=(), payment=()"
        h["Cross-Origin-Opener-Policy"] = "same-origin"
        if "content-security-policy" not in h:                     # a route may set a stricter one (uploaded images use "sandbox")
            h["Content-Security-Policy"] = "default-src 'none'; frame-ancestors 'none'; base-uri 'none'"
        h["X-Frame-Options"] = "DENY"
        if (request.headers.get("x-forwarded-proto") or request.url.scheme) == "https":
            h["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        if path.startswith(("/api/auth/", "/api/account", "/api/admin", "/api/billing")):
            h["Cache-Control"] = "no-store"

    @staticmethod
    def _log(db, request, response, exc_text, ip, path, method, t0):
        st = response.status_code
        admin_write = path.startswith("/api/admin") and method not in SAFE
        if not (st >= 500 or st in (401, 403, 429) or admin_write):
            return
        db.app_logs.insert_one({"at": datetime.now(timezone.utc), "level": "error" if st >= 500 else ("info" if st < 400 else "warn"),
                                "request_id": request.state.request_id, "method": method, "path": path[:200], "status": st,
                                "ms": int((time.time() - t0) * 1000), "user_id": getattr(request.state, "user_id", None),
                                "ip": ip, "ua": request.headers.get("user-agent", "")[:120], "trace": exc_text})


def install(app, get_db) -> None:
    """get_db(request) -> database. Adds the middleware, CORS and the error shapes."""
    app.add_middleware(SecurityMiddleware, get_db=get_db)

    @app.exception_handler(StarletteHTTPException)
    async def _http(request, exc):
        d = exc.detail
        if isinstance(d, dict) and "code" in d:
            return _err(exc.status_code, d["code"], d.get("message", ""), getattr(request.state, "request_id", None),
                        extra={k: d[k] for k in ("problems", "warnings") if k in d})
        return _err(exc.status_code, f"HTTP_{exc.status_code}", str(d), getattr(request.state, "request_id", None))

    @app.exception_handler(RequestValidationError)
    async def _val(request, exc):
        fields = [{"field": ".".join(str(x) for x in e["loc"][1:]), "problem": e["type"]} for e in exc.errors()]
        return JSONResponse({"error": {"code": "BAD_REQUEST", "message": "Check the form and try again.", "fields": fields,
                                       "request_id": getattr(request.state, "request_id", None)}}, status_code=422)

    @app.exception_handler(accounts.AuthError)
    async def _auth(request, exc):
        return _err(exc.status, exc.code, exc.message, getattr(request.state, "request_id", None))

    @app.exception_handler(textguard.BannedWords)
    async def _words(request, exc):
        return _err(400, "BANNED_WORDS", str(exc), getattr(request.state, "request_id", None))

    @app.exception_handler(ratelimit.RateLimited)
    async def _rl(request, exc):
        return _err(429, "RATE_LIMITED", "Too many requests. Try again soon.", getattr(request.state, "request_id", None),
                    {"Retry-After": str(exc.retry_after)})


def add_cors(app, origins: list[str]) -> None:
    """Call after install(), with the origins read from settings at startup. Empty list = no CORS."""
    if origins:
        app.add_middleware(CORSMiddleware, allow_origins=origins, allow_credentials=True,
                           allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"], allow_headers=["Content-Type", "X-Request-ID"],
                           max_age=600)
