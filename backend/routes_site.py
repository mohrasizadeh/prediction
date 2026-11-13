"""routes_site.py -- Site Studio, Popup Maker, images, e-mail list, integrations, extra analytics, alerts, admin shell.

Two routers:
  public  /api/site/config  /api/site/assets/{id}  /api/popups  /api/newsletter/*
  admin   /api/admin/site/*  /popups/*  /integrations/*  /analytics/*  /alerts  /newsletter  /shell
Every admin route names its permission. Nothing here returns a secret after it is saved.
"""
from __future__ import annotations

import base64
import binascii
import hashlib
import json
import re
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from pydantic import BaseModel, Field

import accounts as A
import admin_queries as AQ
import admin_shell as SH
import alerts as AL
import analytics as AN
import deps as D
import emailer as E
import integrations as INT
import newsletter as N
import popups as PP
import ratelimit as RL
import reports as R
import security
import seo as SEO
import settings_store as S
import site_studio as SS
import transports as T

public = APIRouter(prefix="/api")
admin = APIRouter(prefix="/api/admin")
perm = D.require_perm


def _ctx(request: Request):
    return getattr(request.state, "ip", None) or "", request.headers.get("user-agent", "")[:200]


def _bad(e: SS.SiteError, status: int = 422):
    return HTTPException(status, detail={"code": "SITE_INVALID", "message": "Some fields need fixing.", "problems": e.problems})


def _staff_from_preview(db, token: str | None):
    uid = SS.read_preview_token(token) if token else None
    u = db.users.find_one({"id": uid}) if uid else None
    return u if u and A.can(u, "site.read") and not u.get("disabled") else None


# ============================================================================= PUBLIC
@public.get("/site/config")
def site_config(request: Request, preview: Optional[str] = None, db=Depends(D.get_db)):
    if preview:
        if not _staff_from_preview(db, preview):
            raise D.err(403, "PREVIEW_EXPIRED", "This preview link has expired. Open the preview again from Site Studio.")
        cfg = SS.public_config(db, draft=True)
        return Response(json.dumps(cfg, default=str), media_type="application/json", headers={"Cache-Control": "no-store", "X-Robots-Tag": "noindex"})
    cfg = SS.public_config(db)
    body = json.dumps(cfg, default=str, sort_keys=True)
    etag = '"' + hashlib.sha1(body.encode()).hexdigest()[:20] + '"'
    if request.headers.get("if-none-match") == etag:
        return Response(status_code=304, headers={"ETag": etag, "Cache-Control": "public, max-age=30, stale-while-revalidate=300"})
    return Response(body, media_type="application/json", headers={"ETag": etag, "Cache-Control": "public, max-age=30, stale-while-revalidate=300"})


# The sitemap and robots (docs/71). Both are public and unauthenticated by definition -- a crawler
# arrives with no session -- and both are cached for an hour: the contents change when a fixture is
# ingested, not between two requests a minute apart.
#
# Why these live under /api when a crawler looks for them at the document root: this service serves
# no HTML, the platform serves the static build, and only /api/* reaches here. The real robots.txt
# is the static file in frontend/public/, and its Sitemap: line points at the route below. That is a
# valid directive and Google follows it. `GET /api/seo/robots.txt` is the live-settings version of
# that static file, so the two can be compared when they disagree.
_SEO_HEAD = {"Cache-Control": "public, max-age=3600", "X-Content-Type-Options": "nosniff"}


@public.get("/seo/sitemap.xml")
def seo_sitemap(db=Depends(D.get_db)):
    return Response(SEO.sitemap_xml(db), media_type="application/xml", headers=_SEO_HEAD)


@public.get("/seo/robots.txt")
def seo_robots(db=Depends(D.get_db)):
    return Response(SEO.robots_txt(db), media_type="text/plain", headers=_SEO_HEAD)


# Public on purpose: this address is what an e-mail, a page or a popup points at (docs/60). Writing
# needs `site.write`; reading needs nothing, or the file would not load in anyone's mail client.
_ASSET_HEAD = {"Cache-Control": "public, max-age=31536000, immutable", "X-Content-Type-Options": "nosniff",
               "Content-Security-Policy": "default-src 'none'; sandbox", "Content-Disposition": "inline",
               "Accept-Ranges": "bytes"}


@public.get("/site/assets/{aid}")
def site_asset(aid: str, request: Request, db=Depends(D.get_db)):
    a = SS.get_asset(db, aid) if re.fullmatch(r"[0-9a-f]{32}", aid) else None
    if not a:
        raise D.err(404, "NOT_FOUND", "No such file.")
    total = int(a.get("bytes") or 0)
    etag = '"' + str(a.get("sha256", ""))[:16] + '"'
    head = {**_ASSET_HEAD, "ETag": etag}
    if request.headers.get("if-none-match") == etag:
        return Response(status_code=304, headers=head)
    # A video needs byte ranges: without them a browser cannot seek, and Safari will not start the
    # file at all. One range only -- multipart/byteranges buys nothing a player asks for.
    rng = (request.headers.get("range") or "").strip()
    m = re.fullmatch(r"bytes=(\d*)-(\d*)", rng) if rng else None
    if m and total:
        lo, hi = m.group(1), m.group(2)
        if not lo:                                           # "bytes=-500": the last 500 bytes
            start, end = max(0, total - int(hi or 0)), total - 1
        else:
            start, end = int(lo), (int(hi) if hi else total - 1)
        if start >= total or start > end:
            return Response(status_code=416, headers={**head, "Content-Range": f"bytes */{total}"})
        end = min(end, total - 1)
        part = SS.asset_bytes(db, a, start, end)
        return Response(part, status_code=206, media_type=a["mime"],
                        headers={**head, "Content-Range": f"bytes {start}-{end}/{total}", "Content-Length": str(len(part))})
    return Response(SS.asset_bytes(db, a), media_type=a["mime"], headers=head)


@public.get("/popups")
def popups_for_page(request: Request, path: str = Query("/", max_length=200), device: str = Query("desktop", pattern="^(desktop|mobile)$"),
                    visitor: str = Query("new", pattern="^(new|returning)$"), vid: str = Query("", max_length=40),
                    preview: Optional[str] = None, popup: Optional[str] = None, user=Depends(D.optional_user), db=Depends(D.get_db)):
    path = AN.clean_path(path)
    if preview and popup:                                    # staff preview of one popup, whatever its status
        if not _staff_from_preview(db, preview):
            raise D.err(403, "PREVIEW_EXPIRED", "This preview link has expired.")
        r = PP.eligible(db, path=path, device=device, user=user, visitor=visitor, vid=vid, only_id=popup)
        return Response(json.dumps({**r, "preview": True}, default=str), media_type="application/json", headers={"Cache-Control": "no-store"})
    out = PP.eligible(db, path=path, device=device, user=user, visitor=visitor, vid=vid)
    return Response(json.dumps(out, default=str), media_type="application/json", headers={"Cache-Control": "private, max-age=60"})


class PopupEvent(BaseModel):
    event: str = Field(max_length=10)


@public.post("/popups/{pid}/event", status_code=204)
def popup_event(pid: str, body: PopupEvent, request: Request, db=Depends(D.get_db)):
    ip, _ = _ctx(request)
    RL.check(db, f"popev:{ip}", 240, 60)
    PP.record(db, pid, body.event)
    return Response(status_code=204)


class FormBody(BaseModel):
    email: str = Field(max_length=254)
    consent: bool = False
    name: str = Field("", max_length=80)
    source: str = Field("", max_length=40)
    # Where the visitor arrived from: the landing URL's utm_* tags and the outside referrer. Sent by
    # the waitlist page only, and used only for counting (docs/68). Ignored under DNT / GPC.
    utm: Optional[dict] = None
    ref: Optional[str] = Field(None, max_length=300)


@public.post("/popups/{pid}/submit")
def popup_submit(pid: str, body: FormBody, request: Request, db=Depends(D.get_db)):
    ip, _ = _ctx(request)
    RL.check(db, f"popsub:{ip}", 10, 3600)
    RL.check(db, f"popsub:{E.to_hash(body.email)}", 3, 3600)
    return {"ok": True, "message": PP.submit(db, pid, body.email, body.consent, ip_hash=hashlib.sha256(ip.encode()).hexdigest()[:16])}


@public.post("/newsletter/subscribe")
def newsletter_subscribe(body: FormBody, request: Request, db=Depends(D.get_db)):
    ip, _ = _ctx(request)
    RL.check(db, f"nlsub:{ip}", 10, 3600)
    RL.check(db, f"nlsub:{E.to_hash(body.email)}", 3, 3600)
    # The waitlist page sends its own source so the two audiences can be told apart later; anything
    # else is the footer form, as before.
    src = "waitlist" if body.source == "waitlist" else "footer"
    dnt = request.headers.get("dnt") == "1" or request.headers.get("sec-gpc") == "1"
    attrib = AN.attribution(body.utm, body.ref) if src == "waitlist" and not dnt else None
    # A sign-up is a NEW person: someone pressing the button again, or already on the list, is not
    # counted twice. An address that had unsubscribed and comes back is new again.
    try:
        prior = db.newsletter.find_one({"email": A.norm_email(body.email)}, {"status": 1}) if src == "waitlist" else None
    except A.AuthError:
        prior = None                                    # subscribe() below refuses the address itself
    is_new = src == "waitlist" and (not prior or prior.get("status") == "unsubscribed")
    N.subscribe(db, body.email, source=src, consent_text=S.get(db, "newsletter.consent_text"),
                consent=body.consent, ip_hash=hashlib.sha256(ip.encode()).hexdigest()[:16], name=body.name, attrib=attrib)
    if is_new:
        # Counted at the moment of asking, whatever the address turns out to be: the dashboard's
        # "sign-ups" is people who filled the form in, and "confirmed" comes from the list itself.
        # A tracking failure must never fail a sign-up the reader has already pressed.
        try:
            AN.track(db, "waitlist_signup", ip=ip, ua=request.headers.get("user-agent", "")[:200], path="/waitlist",
                     ref=None if dnt else body.ref, utm=None if dnt else body.utm, server=True)
        except Exception:
            pass
    return {"ok": True, "message": "Thanks. If that address can join, we sent a link to confirm it."}


@public.get("/newsletter/confirm")
def newsletter_peek(token: str = Query(max_length=200), db=Depends(D.get_db)):
    """A GET never changes anything (mail scanners open links)."""
    p = N.peek(db, token)
    if not p:
        raise D.err(400, "LINK_EXPIRED", "This link has expired or was already used.")
    return p


class TokenBody(BaseModel):
    token: str = Field(max_length=200)


@public.post("/newsletter/confirm")
def newsletter_confirm(body: TokenBody, db=Depends(D.get_db)):
    if not N.confirm(db, body.token):
        raise D.err(400, "LINK_EXPIRED", "This link has expired or was already used.")
    return {"ok": True}


# ============================================================================= ADMIN: shell
@admin.get("/shell")
def shell(user=Depends(D.require_user), db=Depends(D.get_db)):
    if user["role"] not in A.STAFF:
        raise D.err(403, "FORBIDDEN", "Your role cannot do this.")
    return SH.shell(db, user)


class TabsBody(BaseModel):
    ids: list[str] = Field(max_length=6)


@admin.put("/shell/tabs")
def shell_tabs(body: TabsBody, user=Depends(D.require_user), db=Depends(D.get_db)):
    if user["role"] not in A.STAFF:
        raise D.err(403, "FORBIDDEN", "Your role cannot do this.")
    return {"mobile_tabs": SH.set_tabs(db, user, body.ids)}


# ============================================================================= ADMIN: Site Studio
def _meta():
    return {"sections": list(SS.SECTIONS), "fonts": [{"id": k, "label": v["label"], "kind": v["kind"], "self_hosted_file": v["file"]} for k, v in SS.FONTS.items()],
            "icons": list(SS.ICONS), "audiences": list(SS.AUDIENCES), "home_blocks": list(SS.HOME_BLOCKS), "socials": list(SS.SOCIALS), "color_tokens": list(SS.COLOR_TOKENS),
            "button_styles": list(SS.BUTTON_STYLES), "button_variants": list(SS.VARIANTS), "radius_presets": {k: list(v) for k, v in SS.RADIUS.items()},
            "presets": [{"id": k, "label": v["label"], "description": v["description"]} for k, v in SS.PRESETS.items()], "defaults": SS.defaults(),
            "contrast_rules": {"must_pass_4_5": [list(p) for p in SS.BLOCK_PAIRS], "should_pass": [[list(p), n] for p, n in SS.WARN_PAIRS]}}


@admin.get("/site/draft")
def site_draft(user=Depends(perm("site.read")), db=Depends(D.get_db)):
    d, live = SS.get_draft(db), SS.get_live(db)
    return {"draft": d["data"], "dirty": d["dirty"], "updated_by": d["updated_by"], "updated_at": d["updated_at"], "sections_changed": d["sections_changed"],
            "base_v": d["base_v"], "live_v": live["v"], "meta": _meta(), "can_edit_css": A.can(user, "site.custom_css")}


class SectionBody(BaseModel):
    data: dict


@admin.put("/site/draft/{section}")
def site_put(section: str, body: SectionBody, user=Depends(perm("site.write")), db=Depends(D.get_db)):
    if section == "custom_css" and not A.can(user, "site.custom_css"):
        raise D.err(403, "FORBIDDEN", "Only an owner can change custom CSS.")
    try:
        return SS.put_section(db, user["email"], section, body.data)
    except SS.SiteError as e:
        raise _bad(e)


class ResetBody(BaseModel):
    to: str = "live"


@admin.post("/site/draft/{section}/reset")
def site_reset(section: str, body: ResetBody, user=Depends(perm("site.write")), db=Depends(D.get_db)):
    if section == "custom_css" and not A.can(user, "site.custom_css"):
        raise D.err(403, "FORBIDDEN", "Only an owner can change custom CSS.")
    try:
        return SS.reset_section(db, user["email"], section, body.to)
    except SS.SiteError as e:
        raise _bad(e)


class PresetBody(BaseModel):
    key: str = Field(max_length=30)


@admin.post("/site/draft/preset")
def site_preset(body: PresetBody, user=Depends(perm("site.write")), db=Depends(D.get_db)):
    try:
        return SS.apply_preset_to_draft(db, user["email"], body.key)
    except SS.SiteError as e:
        raise _bad(e)


@admin.post("/site/draft/discard")
def site_discard(user=Depends(perm("site.write")), db=Depends(D.get_db)):
    SS.discard_draft(db, user["email"])
    return {"ok": True}


@admin.get("/site/diff")
def site_diff(user=Depends(perm("site.read")), db=Depends(D.get_db)):
    d, live = SS.get_draft(db), SS.get_live(db)
    return {"changed": [{"section": s, "live": live["data"].get(s), "draft": d["data"].get(s)} for s in d["sections_changed"]]}


@admin.post("/site/preview-token")
def site_preview_token(user=Depends(perm("site.read")), db=Depends(D.get_db)):
    t = SS.preview_token(user["id"])
    return {"token": t, "expires_in": 1800, "url": f"{E.base_url()}/?preview={t}"}


class PublishBody(BaseModel):
    note: str = Field("", max_length=200)
    force: bool = False


@admin.post("/site/publish")
def site_publish(body: PublishBody, user=Depends(perm("site.publish")), db=Depends(D.get_db)):
    try:
        return SS.publish(db, user["email"], body.note, body.force)
    except SS.SiteError as e:
        raise _bad(e)
    except SS.Conflict as e:
        raise D.err(409, "PUBLISH_CONFLICT", str(e))


@admin.get("/site/versions")
def site_versions(user=Depends(perm("site.read")), db=Depends(D.get_db)):
    return {"live_v": SS.get_live(db)["v"], "versions": SS.versions(db)}


@admin.get("/site/versions/{v}")
def site_version(v: int, user=Depends(perm("site.read")), db=Depends(D.get_db)):
    row = SS.get_version(db, v)
    if not row:
        raise D.err(404, "NOT_FOUND", "No such version.")
    return {k: row[k] for k in ("v", "data", "note", "by", "at", "changed")}


@admin.post("/site/rollback/{v}")
def site_rollback(v: int, user=Depends(perm("site.publish")), db=Depends(D.get_db)):
    try:
        return SS.rollback(db, user["email"], v)
    except SS.SiteError as e:
        raise _bad(e)


# ---- images
class AssetBody(BaseModel):
    name: str = Field(max_length=80)
    data_b64: str = Field(max_length=800_000)


@admin.get("/site/assets")
def assets(user=Depends(perm("site.read")), db=Depends(D.get_db)):
    return {"assets": SS.list_assets(db), **SS.limits(db)}


@admin.post("/site/assets")
def asset_upload(body: AssetBody, user=Depends(perm("site.write")), db=Depends(D.get_db)):
    try:
        raw = base64.b64decode(body.data_b64, validate=True)
    except (binascii.Error, ValueError):
        raise D.err(400, "BAD_IMAGE", "That file could not be read.")
    try:
        return SS.save_asset(db, user["email"], body.name, raw)
    except ValueError as e:
        raise D.err(400, "BAD_IMAGE", str(e))


@admin.put("/media/upload")
async def media_upload(request: Request, name: str = Query("file", max_length=80), user=Depends(perm("site.write")), db=Depends(D.get_db)):
    """The file as the raw request body. The JSON route above stays for Site Studio and the tests, but
    base64 costs a third more body for every byte, which is the difference between a logo and a video."""
    data = await request.body()
    if not data:
        raise D.err(400, "EMPTY", "That file was empty.")
    try:
        out = SS.save_asset(db, user["email"], name, data)
    except ValueError as e:
        raise D.err(400, "BAD_FILE", str(e))
    AQ.audit(db, user, "site.asset_upload", out["id"])
    return out


@admin.delete("/site/assets/{aid}")
def asset_delete(aid: str, user=Depends(perm("site.write")), db=Depends(D.get_db)):
    if not db.site_assets.find_one({"_id": aid}, {"_id": 1}):
        raise D.err(404, "NOT_FOUND", "That image no longer exists.")
    try:
        SS.delete_asset(db, user["email"], aid)
    except ValueError as e:
        raise D.err(409, "IN_USE", str(e))
    return {"ok": True}


# ============================================================================= ADMIN: Popup Maker
@admin.get("/popups")
def popups_list(user=Depends(perm("popups.read")), db=Depends(D.get_db)):
    return {"popups": PP.list_all(db), "global": {k: S.get(db, k) for k in ("popups.enabled", "popups.max_per_session", "popups.min_gap_seconds")}}


@admin.get("/popups/meta")
def popups_meta(user=Depends(perm("popups.read")), db=Depends(D.get_db)):
    return {"blank": PP.blank(), "kinds": list(PP.KINDS), "triggers": list(PP.TRIGGERS), "audiences": list(PP.AUDIENCES), "frequencies": list(PP.FREQUENCIES),
            "tones": list(PP.TONES), "sizes": list(PP.SIZES), "always_excluded": list(PP.ALWAYS_EXCLUDE),
            "templates": [{"id": k, "label": v["label"]} for k, v in PP.TEMPLATES.items()]}


class PopupBody(BaseModel):
    data: dict = {}
    template: Optional[str] = None


@admin.post("/popups")
def popups_create(body: PopupBody, user=Depends(perm("popups.write")), db=Depends(D.get_db)):
    try:
        if body.template:
            pid, w = PP.create_from_template(db, user["email"], body.template)
        else:
            pid, w = PP.create(db, user["email"], body.data)
    except SS.SiteError as e:
        raise _bad(e)
    except ValueError as e:
        raise D.err(409, "LIMIT", str(e))
    return {"id": pid, "warnings": w}


@admin.get("/popups/{pid}")
def popups_get(pid: str, user=Depends(perm("popups.read")), db=Depends(D.get_db)):
    p = PP.get(db, pid)
    if not p:
        raise D.err(404, "NOT_FOUND", "No such popup.")
    return p


@admin.put("/popups/{pid}")
def popups_update(pid: str, body: PopupBody, user=Depends(perm("popups.write")), db=Depends(D.get_db)):
    try:
        return {"warnings": PP.update(db, user["email"], pid, body.data)}
    except SS.SiteError as e:
        raise _bad(e)


class StatusBody(BaseModel):
    status: str = Field(max_length=10)


@admin.post("/popups/{pid}/status")
def popups_status(pid: str, body: StatusBody, user=Depends(perm("popups.write")), db=Depends(D.get_db)):
    try:
        PP.set_status(db, user["email"], pid, body.status)
    except SS.SiteError as e:
        raise _bad(e)
    return {"ok": True}


@admin.post("/popups/{pid}/duplicate")
def popups_dup(pid: str, user=Depends(perm("popups.write")), db=Depends(D.get_db)):
    try:
        return {"id": PP.duplicate(db, user["email"], pid)}
    except ValueError as e:
        raise D.err(409, "LIMIT", str(e))


@admin.delete("/popups/{pid}")
def popups_delete(pid: str, user=Depends(perm("popups.write")), db=Depends(D.get_db)):
    PP.delete(db, user["email"], pid)
    return {"ok": True}


@admin.get("/popups/{pid}/stats")
def popups_stats(pid: str, days: int = Query(30, ge=1, le=400), user=Depends(perm("popups.read")), db=Depends(D.get_db)):
    return {"totals": PP.totals(db, pid, days), "series": PP.series(db, pid, days)}


@admin.get("/popups-ab/{group}")
def popups_ab(group: str, user=Depends(perm("popups.read")), db=Depends(D.get_db)):
    return PP.ab_report(db, group)


# ============================================================================= ADMIN: e-mail list
@admin.get("/newsletter")
def nl_list(status: Optional[str] = None, page: int = Query(1, ge=1), user=Depends(perm("email.read")), db=Depends(D.get_db)):
    q = {"status": status} if status in ("pending", "confirmed", "unsubscribed") else {}
    return {"counts": N.counts(db), **AQ.paged(db, "newsletter", q, [("created_at", -1)], page, 50, proj={"consent_text": 0, "ip_hash": 0}, pii=A.can(user, "users.pii"))}


@admin.get("/newsletter/export")
def nl_export(user=Depends(perm("users.pii")), db=Depends(D.get_db)):
    rows = [{"email": r["email"], "status": r["status"], "source": r.get("source"), "consent_at": r.get("consent_at"), "confirmed_at": r.get("confirmed_at")} for r in db.newsletter.find({}).sort("created_at", -1)]
    AQ.audit(db, user, "newsletter.export", f"{len(rows)} rows")
    return Response(R.csv_bytes(rows, ["email", "status", "source", "consent_at", "confirmed_at"]), media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": 'attachment; filename="email-list.csv"', "Cache-Control": "no-store"})


class EmailBody(BaseModel):
    email: str = Field(max_length=254)


@admin.post("/newsletter/remove")
def nl_remove(body: EmailBody, user=Depends(perm("email.write")), db=Depends(D.get_db)):
    N.unsubscribed(db, body.email)
    E.suppress(db, body.email, "manual", f"removed by {user['email']}")
    AQ.audit(db, user, "newsletter.remove", E.to_hash(body.email))
    return {"ok": True}


# ============================================================================= ADMIN: waitlist e-mail
@admin.get("/newsletter/waitlist")
def wl_preview(user=Depends(perm("email.read")), db=Depends(D.get_db)):
    """What the match-day e-mail would look like right now, built from today's real forecasts.

    Rendered rather than described, because the one thing the owner needs to see before switching
    this on is the actual three and whether the header graphic found a card (docs/69).
    """
    import waitlist_mail as WL
    return WL.preview(db)


@admin.post("/newsletter/waitlist/send")
def wl_send(user=Depends(perm("email.write")), db=Depends(D.get_db)):
    """Send today's e-mail now, without waiting for the hour.

    It is NOT a second e-mail: the per-address idempotency key is the day, so pressing this after
    the job has already run reports duplicates and sends nothing.
    """
    import waitlist_mail as WL
    out = WL.send_matchday(db)
    AQ.audit(db, user, "waitlist.send", f"{out.get('sent', 0)} sent")
    return out


# ============================================================================= ADMIN: integrations
@admin.get("/integrations")
def integrations_overview(user=Depends(perm("integrations.read")), db=Depends(D.get_db)):
    return INT.overview(db)


class EmailProviderBody(BaseModel):
    provider: str = Field(max_length=12)
    smtp_host: Optional[str] = Field(None, max_length=253)
    smtp_port: Optional[int] = None
    smtp_user: Optional[str] = Field(None, max_length=200)
    smtp_security: Optional[str] = Field(None, max_length=10)


@admin.put("/integrations/email")
def integrations_email(body: EmailProviderBody, user=Depends(perm("keys.write")), db=Depends(D.get_db)):
    # owner only: these settings decide where the stored mail password and every reset link go (docs/36 C1)
    try:
        S.put(db, "email.provider", body.provider, actor=user["email"])
        if body.smtp_host is not None or body.smtp_port is not None:
            if T.set_smtp_target(db, user["email"], host=body.smtp_host, port=body.smtp_port):
                AQ.audit(db, user, "key.delete", "smtp_password", detail="SMTP host changed")
        for k in ("smtp_user", "smtp_security"):
            v = getattr(body, k)
            if v is not None:
                S.put(db, f"email.{k}", v, actor=user["email"])
    except (ValueError, KeyError) as e:
        raise D.err(400, "BAD_SETTING", str(e))
    out = INT.overview(db)["email"]
    out["warning"] = None if out["key_set"] else "No key is saved for this provider yet. Add it in Keys, or e-mail will stay off."
    return out


class TestSendBody(BaseModel):
    to: Optional[str] = Field(None, max_length=254)


@admin.post("/integrations/email/test-send")
def integrations_test_send(body: TestSendBody, user=Depends(perm("integrations.write")), db=Depends(D.get_db)):
    to = A.norm_email(body.to or user["email"])
    if body.to and not db.users.find_one({"email": to, "role": {"$in": list(A.STAFF)}}):
        raise D.err(400, "STAFF_ONLY", "A test can only go to a team member's address.")
    r = E.send_test(db, to)
    AQ.audit(db, user, "email.test_send", E.to_hash(to), {"status": r["status"]})
    return r


class AudienceBody(BaseModel):
    provider: str = Field(max_length=12)
    list_id: str = Field("", max_length=60)


@admin.put("/integrations/audience")
def integrations_audience(body: AudienceBody, user=Depends(perm("integrations.write")), db=Depends(D.get_db)):
    try:
        S.put(db, "integrations.audience_provider", body.provider, actor=user["email"])
        S.put(db, "integrations.audience_list_id", body.list_id.strip(), actor=user["email"])
    except (ValueError, KeyError) as e:
        raise D.err(400, "BAD_SETTING", str(e))
    return INT.overview(db)["audience"]


@admin.post("/integrations/audience/test")
def integrations_audience_test(user=Depends(perm("integrations.write")), db=Depends(D.get_db)):
    return INT.test_audience(db)


@admin.post("/integrations/audience/backfill")
def integrations_audience_backfill(user=Depends(perm("integrations.write")), db=Depends(D.get_db)):
    n = INT.backfill_audience(db)
    AQ.audit(db, user, "audience.backfill", str(n))
    return {"queued": n}


@admin.get("/integrations/audience/jobs")
def integrations_audience_jobs(status: Optional[str] = None, user=Depends(perm("integrations.read")), db=Depends(D.get_db)):
    q = {"kind": "audience", **({"status": status} if status in ("pending", "done", "dead") else {})}
    rows = [{"id": str(r["_id"]), "provider": r["provider"], "action": r["action"], "email": AQ.mask_email(r["email"]) if not A.can(user, "users.pii") else r["email"],
             "status": r["status"], "attempts": r["attempts"], "error": r.get("error"), "next_at": r["next_at"]} for r in db.integration_jobs.find(q).sort("created_at", -1).limit(100)]
    return {"jobs": rows}


class WebhookBody(BaseModel):
    url: str = Field(max_length=500)
    events: list[str] = Field(max_length=12)
    include_email: bool = False
    note: str = Field("", max_length=120)


class WebhookPatch(BaseModel):
    url: Optional[str] = Field(None, max_length=500)
    events: Optional[list[str]] = Field(None, max_length=12)
    include_email: Optional[bool] = None
    active: Optional[bool] = None
    note: Optional[str] = Field(None, max_length=120)


@admin.get("/integrations/webhooks")
def webhooks_list(user=Depends(perm("integrations.read")), db=Depends(D.get_db)):
    return {"endpoints": INT.list_endpoints(db), "events": list(INT.EVENTS), "signature": "X-Webhook-Signature: t=<unix>,v1=<hex HMAC-SHA256 of '<t>.<body>' with the endpoint secret>"}


@admin.post("/integrations/webhooks")
def webhooks_create(body: WebhookBody, user=Depends(perm("integrations.write")), db=Depends(D.get_db)):
    try:
        return INT.create_endpoint(db, user["email"], body.url, body.events, body.include_email, body.note)
    except ValueError as e:
        raise D.err(400, "BAD_WEBHOOK", str(e))


@admin.put("/integrations/webhooks/{eid}")
def webhooks_update(eid: str, body: WebhookPatch, user=Depends(perm("integrations.write")), db=Depends(D.get_db)):
    try:
        return INT.update_endpoint(db, user["email"], eid, url=body.url, events=body.events, active=body.active, include_email=body.include_email, note=body.note)
    except KeyError:
        raise D.err(404, "NOT_FOUND", "No such endpoint.")
    except ValueError as e:
        raise D.err(400, "BAD_WEBHOOK", str(e))


@admin.post("/integrations/webhooks/{eid}/rotate")
def webhooks_rotate(eid: str, user=Depends(perm("integrations.write")), db=Depends(D.get_db)):
    try:
        return INT.rotate_secret(db, user["email"], eid)
    except KeyError:
        raise D.err(404, "NOT_FOUND", "No such endpoint.")


@admin.post("/integrations/webhooks/{eid}/test")
def webhooks_test(eid: str, user=Depends(perm("integrations.write")), db=Depends(D.get_db)):
    try:
        return INT.send_test(db, user["email"], eid)
    except KeyError:
        raise D.err(404, "NOT_FOUND", "No such endpoint.")


@admin.delete("/integrations/webhooks/{eid}")
def webhooks_delete(eid: str, user=Depends(perm("integrations.write")), db=Depends(D.get_db)):
    INT.delete_endpoint(db, user["email"], eid)
    return {"ok": True}


@admin.get("/integrations/webhooks-deliveries")
def webhooks_deliveries(endpoint: Optional[str] = None, user=Depends(perm("integrations.read")), db=Depends(D.get_db)):
    return {"deliveries": INT.deliveries(db, endpoint)}


class TrackingBody(BaseModel):
    enabled: bool
    ga4_id: str = Field("", max_length=20)
    meta_pixel_id: str = Field("", max_length=25)
    google_ads_id: str = Field("", max_length=25)
    require_consent: bool = True


@admin.put("/integrations/tracking")
def tracking_put(body: TrackingBody, user=Depends(perm("tracking.write")), db=Depends(D.get_db)):
    """Owner only. Ad and analytics tags are a privacy decision, so they are never on by accident."""
    try:
        for k, v in (("enabled", body.enabled), ("ga4_id", body.ga4_id.strip()), ("meta_pixel_id", body.meta_pixel_id.strip()),
                     ("google_ads_id", body.google_ads_id.strip()), ("require_consent", body.require_consent)):
            S.put(db, f"tracking.{k}", v, actor=user["email"])
    except ValueError as e:
        raise D.err(400, "BAD_SETTING", str(e))
    warn = []
    if body.enabled and not body.require_consent:
        warn.append("Tags will load before people say yes. That may break privacy law in Canada and the EU.")
    return {**INT.overview(db)["tracking"], "warnings": warn + ["Update your Privacy page to name these tools, and add the listed sources to your Content-Security-Policy."]}


# ============================================================================= ADMIN: analytics extras, alerts, digest
@admin.get("/analytics/realtime")
def an_realtime(user=Depends(perm("analytics.read")), db=Depends(D.get_db)):
    return R.realtime(db)


@admin.get("/analytics/compare")
def an_compare(days: int = Query(30, ge=1, le=200), user=Depends(perm("analytics.read")), db=Depends(D.get_db)):
    c = R.compare(db, days)
    if not A.can(user, "billing.read"):
        c["revenue"] = []
    return c


@admin.get("/analytics/acquisition")
def an_acq(days: int = Query(30, ge=1, le=400), user=Depends(perm("analytics.read")), db=Depends(D.get_db)):
    return R.acquisition(db, days)


@admin.get("/analytics/email")
def an_email(days: int = Query(30, ge=1, le=400), user=Depends(perm("email.read")), db=Depends(D.get_db)):
    return R.email_report(db, days)


@admin.get("/analytics/popups")
def an_popups(user=Depends(perm("popups.read")), db=Depends(D.get_db)):
    return R.popup_report(db)


@admin.get("/analytics/newsletter")
def an_newsletter(days: int = Query(30, ge=1, le=400), user=Depends(perm("analytics.read")), db=Depends(D.get_db)):
    return R.newsletter_report(db, days)


@admin.get("/analytics/export")
def an_export(report: str = Query(max_length=20), days: int = Query(30, ge=1, le=400), user=Depends(perm("analytics.read")), db=Depends(D.get_db)):
    if report == "pages":
        rows = AN.top_pages(db, days, 200)
    elif report == "referrers":
        rows = AN.referrers(db, days, 200)
    elif report == "acquisition":
        rows = R.acquisition(db, days)["rows"]
    elif report == "popups":
        rows = R.popup_report(db)["rows"]
    elif report == "signups":
        rows = AN.series(db, "signup", days)
    elif report == "visitors":
        rows = AN.series(db, "page_view", days)
    else:
        raise D.err(400, "BAD_REPORT", "Reports: pages, referrers, acquisition, popups, signups, visitors.")
    AQ.audit(db, user, "analytics.export", report, {"days": days, "rows": len(rows)})
    return Response(R.csv_bytes(rows), media_type="text/csv; charset=utf-8", headers={"Content-Disposition": f'attachment; filename="{report}-{days}d.csv"', "Cache-Control": "no-store"})


@admin.get("/alerts")
def alerts_list(user=Depends(perm("logs.read")), db=Depends(D.get_db)):
    return {"open": AL.open_alerts(db)}


@admin.post("/alerts/{aid}/resolve")
def alerts_resolve(aid: str, user=Depends(perm("settings.write")), db=Depends(D.get_db)):
    AL.resolve(db, user["email"], aid)
    return {"ok": True}


@admin.post("/alerts/run")
def alerts_run(user=Depends(perm("jobs.run")), db=Depends(D.get_db)):
    return AL.run(db)


@admin.get("/digest/preview")
def digest_preview(user=Depends(perm("analytics.read")), db=Depends(D.get_db)):
    return {"text": AL.build_digest(db)}


@admin.post("/digest/send")
def digest_send(user=Depends(perm("settings.write")), db=Depends(D.get_db)):
    r = AL.send_digest(db)
    AQ.audit(db, user, "digest.send", "weekly", r)
    return r
