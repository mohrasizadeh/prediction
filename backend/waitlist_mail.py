"""waitlist_mail.py -- the e-mail sequence the waitlist page promises (docs/69).

The landing page makes one promise in one sentence: *our top three strong reads every match day
until we launch*. Everything here exists to keep that promise literally, and to keep it without a
person in the loop on a Saturday.

Two e-mails, and no more:

  * `waitlist_welcome`, once, the moment the address is confirmed. It says what the engine does and
    when the three start arriving, because a confirmation that says nothing is a wasted open and a
    reader who has forgotten who we are by the first match day.
  * `waitlist_matchday`, once a day, and only on a day that HAS football. "Every match day" is the
    promise; an empty Tuesday e-mail saying there is nothing today keeps the cadence and breaks the
    reason anyone opted in.

WHERE THE HEADER GRAPHIC COMES FROM. The ad builder already renders the day's cards in the browser,
uploads each PNG to the media library for a public URL, and queues it for Instagram (docs/64). That
URL is a plain https address on this install that stays reachable, which is exactly what an e-mail
client needs -- so this module reuses it rather than drawing anything. One render, two destinations.
It PREFERS the post whose forecast is one of the three in the e-mail, so "the related card" is true
rather than "whatever was first that day"; that is what `fkeys` on a queued post is for.

A missing graphic is not an error. The e-mail is built from numbers and reads perfectly as text, so
a day with no batch queued still goes out -- just without a picture at the top.

WHAT THIS MODULE WILL NOT DO:
  * It will not invent a record. The "how we have done" line is omitted entirely until
    `track_record` says `ready`, and it is phrased as calibration, never as a score (docs/03).
  * It will not send to someone who joined by the footer form. They asked for a different thing.
  * It will not exceed `email.daily_send_cap`; `_deliver` enforces that, and what is left over is
    counted and reported rather than silently dropped.
  * Every subject and body goes through textguard, including the parts built from match data.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import emailer as E
import queries as Q
import settings_store as S
import site_studio as SS
import textguard as TG

SOURCE = "waitlist"          # newsletter.source, set by the /waitlist form (routes_site)
WANT = 3                     # "top three" is the promise; it is not a tunable


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


# ----------------------------------------------------------------------------- the audience
def members(db):
    """Confirmed waitlist sign-ups, as the shape `_deliver` wants.

    They are list members, not account holders: consent is the row in `newsletter`, which carries
    the sentence they agreed to and when. `marketing_emails` is True for the same reason it is in
    emailer._list_member -- saying yes on that form IS the opt-in.
    """
    for r in db.newsletter.find({"status": "confirmed", "source": SOURCE}, {"email": 1, "name": 1}):
        yield {"id": "wl-" + E.to_hash(r["email"]), "email": r["email"],
               "display_name": (r.get("name") or "").strip(),
               "prefs": {"marketing_emails": True, "product_emails": False}}


def count(db) -> int:
    return db.newsletter.count_documents({"status": "confirmed", "source": SOURCE})


# ----------------------------------------------------------------------------- the three
def window_h(db, now) -> float:
    """How far ahead today's e-mail may look: to the end of the local day, and no further.

    This used to be a flat 30 hours, which was wrong in a way the first render showed immediately.
    An e-mail headed "Saturday 14 November" listed a 09:00 kick-off that was on the Sunday, because
    30 hours from a Saturday morning reaches into Sunday. The reader cannot see that, and a time
    with the wrong day on it is worse than no time.

    The end of the local day is also exactly what the promise means by "today", and it is still far
    enough for a morning send to name a 20:45 kick-off. A send scheduled for late evening has a
    short window and may find nothing -- which is the honest outcome, not a bug: there is no
    football left today to write about.
    """
    tz = int(S.get(db, "waitlist.email_tz_offset_min") or 0)
    local = now + timedelta(minutes=tz)
    end_local = local.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
    return max(0.0, (end_local - local).total_seconds() / 3600.0)


def strongest(db, n: int = WANT, now=None) -> list[dict]:
    """The three likeliest forecasts kicking off between now and the end of the local day.

    It asks the same question the "most likely" screen asks, through the same function, with the
    same floor -- so the e-mail cannot disagree with the page it links to. `insights_feed` already
    groups by player, so the de-duplication below is only a guard for the team lines.
    """
    now = now or utcnow()
    floor = float(S.get(db, "engine.watch_min"))
    rows = Q.insights_feed(db, limit=40, tiers=("Strong", "Solid"), now=now, sort="likely",
                           min_p=floor, within_h=window_h(db, now))
    out, seen = [], set()
    for f in rows:
        key = f.get("player_iid") or ("t", f.get("team_iid"), f.get("stat"), f.get("thr"))
        if key in seen:
            continue
        seen.add(key)
        out.append(f)
        if len(out) >= int(n):
            break
    return out


def is_match_day(db, now=None) -> bool:
    """Whether there is enough football to keep the promise. Fewer than three and we say nothing."""
    return len(strongest(db, WANT, now)) >= WANT


# ----------------------------------------------------------------------------- the header graphic
def header_image(db, rows: list[dict], now=None) -> tuple[str, str] | None:
    """A public URL for the top of the e-mail, and words for it, from today's queued posts.

    Preference order, and the reason for each:
      1. a post carrying one of THESE three forecasts -- the reader sees the same card twice, in
         two places, about the same player, which is the point of making it once;
      2. any other post queued for today -- still today's design, still on brand;
      3. nothing. The e-mail is fine without it.

    The post's own CAPTION comes back with it, and becomes the image's alt text. That is not a
    nicety: most e-mail clients block remote images until the reader asks for them, so the alt text
    is what is actually on the screen when the e-mail opens. An empty alt would leave a blank box
    at the top of every one. The caption was written from the words already on the image
    (ad_plan._caption) and has been through textguard twice, so it describes the picture and
    carries nothing this product does not publish.

    A cancelled post is skipped: the owner took it out of the day deliberately.
    """
    now = now or utcnow()
    # "Today" here has to mean the same day the e-mail is dated, which is the LOCAL day. Using UTC
    # midnight instead would, at an offset like -300, count a post scheduled 02:00 UTC -- 21:00 the
    # previous evening where the owner is -- as one of today's.
    tz = int(S.get(db, "waitlist.email_tz_offset_min") or 0)
    local0 = (now + timedelta(minutes=tz)).replace(hour=0, minute=0, second=0, microsecond=0)
    d0 = local0 - timedelta(minutes=tz)
    want = {f.get("fkey") for f in rows if f.get("fkey")}
    best = None
    for p in db.social_posts.find({"status": {"$nin": ["cancelled"]},
                                   "scheduled_at": {"$gte": d0, "$lt": d0 + timedelta(days=1)}},
                                  {"media": 1, "fkeys": 1, "caption": 1}).sort("scheduled_at", 1):
        url = (p.get("media") or [None])[0]
        if not url or not str(url).lower().startswith("https://"):
            continue                      # an e-mail client will not load http, and neither will we send it
        # One line of it: a caption can run to 2,200 characters, and alt text is read aloud.
        alt = (p.get("caption") or "").strip().split("\n")[0][:180]
        if want & set(p.get("fkeys") or []):
            return url, alt
        best = best or (url, alt)
    return best


# ----------------------------------------------------------------------------- the HTML
# E-mail HTML, not web HTML: tables, inline styles, no class names and no flexbox. Gmail strips a
# <style> block on mobile, Outlook renders a <div> grid as one column, and both ignore CSS
# variables -- so the brand colours are written out as hex here and nowhere else.
C = {"ink": "#111827", "mute": "#6b7280", "brand": "#034737", "strong": "#1B8962",
     "line": "#E6E9E5", "warm": "#FDF8F7", "mint": "#E8F4EE"}


def _pct(p) -> str:
    return f"{round(float(p) * 100)}%"


def _when(ko, tz_offset_min: int = 0) -> str:
    if not isinstance(ko, datetime):
        return ""
    d = ko if ko.tzinfo else ko.replace(tzinfo=timezone.utc)
    d += timedelta(minutes=int(tz_offset_min))
    return d.strftime("%H:%M")           # 24-hour: docs/63, and it needs no AM/PM in every locale


def row_html(f: dict, tz_offset_min: int = 0) -> str:
    """One forecast, as a bordered row. Every field is escaped: player and club names come from the
    data feed, which this app does not author."""
    who = E.esc(f.get("player", {}).get("name") if isinstance(f.get("player"), dict) else (f.get("player") or ""))
    team = E.esc((f.get("team") or {}).get("name") or "")
    opp = E.esc((f.get("opp") or {}).get("name") or "")
    if not who:
        who = team                        # a team line: the club IS the subject
    market = E.esc(f.get("market") or "")
    lg = E.esc(f.get("league_name") or "")
    ko = E.esc(_when(f.get("kickoff"), tz_offset_min))
    fixture = " v ".join(x for x in (team, opp) if x)
    return (
        f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" '
        f'style="border:1px solid {C["line"]};border-radius:14px;margin:0 0 10px"><tr>'
        f'<td style="padding:13px 15px">'
        f'<div style="font-size:16px;font-weight:700;color:{C["ink"]};line-height:1.3">{who}</div>'
        f'<div style="font-size:15px;color:{C["brand"]};font-weight:600;padding-top:3px">{market}</div>'
        f'<div style="font-size:13px;color:{C["mute"]};padding-top:6px">{fixture}</div>'
        + (f'<div style="font-size:13px;color:{C["mute"]};padding-top:2px">'
           + " &middot; ".join(x for x in (ko, lg) if x) + '</div>' if (ko or lg) else '')
        + f'</td>'
        f'<td width="74" align="right" valign="top" style="padding:13px 15px 13px 0">'
        f'<span style="display:inline-block;background:{C["mint"]};color:{C["brand"]};'
        f'font-size:17px;font-weight:700;padding:5px 10px;border-radius:999px;white-space:nowrap">'
        f'{_pct(f.get("p"))}</span>'
        f'</td></tr></table>')


def body_html(db, rows: list[dict], image, tz_offset_min: int = 0) -> str:
    """The part of the match-day e-mail this module builds: picture, three rows, record line.

    `image` is what header_image returned: (url, alt) or None.
    """
    out = []
    if image:
        url, alt = image if isinstance(image, (tuple, list)) else (image, "")
        # No width beyond 100%: the ads are square at 1080, and a fixed pixel width is what makes
        # an e-mail scroll sideways on a phone.
        out.append(f'<img src="{E.esc(url)}" alt="{E.esc(alt)}" width="512" '
                   f'style="width:100%;max-width:512px;height:auto;display:block;border-radius:16px;margin:0 0 18px">')
    out += [row_html(f, tz_offset_min) for f in rows]
    tr = Q.track_record(db)
    if tr.get("ready") and tr.get("high"):
        h = tr["high"]
        out.append(
            f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" '
            f'style="background:{C["warm"]};border:1px solid {C["line"]};border-radius:14px;margin:16px 0 0">'
            f'<tr><td style="padding:13px 15px;font-size:13px;color:{C["mute"]};line-height:1.55">'
            f'When we have said something is at least {_pct(h["from"])} likely, we have said '
            f'{_pct(h["stated"])} on average and it has happened '
            f'<strong style="color:{C["ink"]}">{_pct(h["actual"])}</strong> of the time, '
            f'over {h["n"]:,} scored forecasts.</td></tr></table>')
    return "".join(out)


def body_text(rows: list[dict], tz_offset_min: int = 0) -> str:
    """The plain-text half. Not an afterthought: it is what a screen reader and a text-only client
    get, and it is what lands in the spam score if it is missing."""
    lines = []
    for f in rows:
        who = (f.get("player") or {}).get("name") if isinstance(f.get("player"), dict) else (f.get("player") or "")
        who = who or (f.get("team") or {}).get("name") or ""
        fixture = " v ".join(x for x in ((f.get("team") or {}).get("name") or "",
                                         (f.get("opp") or {}).get("name") or "") if x)
        ko = _when(f.get("kickoff"), tz_offset_min)
        lines.append(f"{who} -- {f.get('market') or ''} -- {_pct(f.get('p'))}\n  {fixture}"
                     + (f", {ko}" if ko else ""))
    return "\n\n".join(lines)


# ----------------------------------------------------------------------------- sending
def send_welcome(db, email: str, name: str = "", client=None) -> dict:
    """Once, when the address is confirmed. Called from newsletter._confirmed_side_effects.

    The idempotency key is the address alone, with no date in it, so this is once per address ever
    rather than once per sign-up. Somebody who unsubscribes and comes back does not get the "here
    is what you will get" e-mail a second time -- they know, and they will get the next match day's
    three like everyone else.
    """
    u = {"id": "wl-" + E.to_hash(email), "email": email, "display_name": (name or "").strip(),
         "prefs": {"marketing_emails": True, "product_emails": False}}
    return E.send_template(db, "waitlist_welcome", to=email, user=u,
                           vars={"link": f"{SS.base_url()}/waitlist", "count": WANT},
                           idem=f"wlw-{E.to_hash(email)}", client=client)


def send_matchday(db, now=None, client=None) -> dict:
    """Today's three, to everyone on the waitlist.

    It does NOT check the hour: `due` owns that, so the job waits for it and the admin screen's
    Send now does not. What stops a second e-mail is the per-address idempotency key, which is the
    local day -- so running this twice on the same day is safe from anywhere, and a run that died
    half way through the list resumes on the next tick instead of writing to everyone again.
    """
    now = now or utcnow()
    if not S.get(db, "waitlist.email_enabled"):
        return {"sent": 0, "skipped": "waitlist e-mail is off"}
    if not S.get(db, "email.enabled") or not S.get(db, "email.marketing_enabled"):
        return {"sent": 0, "skipped": "e-mail or marketing e-mail is off in settings"}
    if not S.get(db, "email.footer_address").strip():
        return {"sent": 0, "skipped": "marketing e-mail needs a postal address in the footer"}
    rows = strongest(db, WANT, now)
    if len(rows) < WANT:
        return {"sent": 0, "skipped": f"only {len(rows)} forecasts above the floor today"}
    tz = int(S.get(db, "waitlist.email_tz_offset_min") or 0)
    image = header_image(db, rows, now)
    html = body_html(db, rows, image, tz)
    text = body_text(rows, tz)
    # The one place the generated half could carry a word this product does not publish. Nobody
    # reads every match-day e-mail, and a club or a market label is data we did not write.
    bad = TG.find([html, text])
    if bad:
        return {"sent": 0, "skipped": f"today's three use words we do not publish: {', '.join(bad)}"}
    day = (now + timedelta(minutes=tz)).strftime("%Y-%m-%d")
    pretty = (now + timedelta(minutes=tz)).strftime("%A %d %B")
    sent = failed = skipped = left = 0
    for u in members(db):
        r = E.send_template(db, "waitlist_matchday", to=u["email"], user=u,
                            vars={"rows_html": html, "rows_text": text, "date": pretty,
                                  "link": f"{SS.base_url()}/", "count": len(rows)},
                            idem=f"wlm-{day}-{E.to_hash(u['email'])}", client=client)
        st = r["status"]
        if st == "sent":
            sent += 1
        elif st == "failed":
            failed += 1
        elif st == "skipped_cap":
            left += 1
        else:
            skipped += 1
    # One row per local day, keyed BY the day, so "have we sent today" is a primary-key lookup
    # rather than a query over job history -- and so a send started from the admin screen counts
    # exactly as much as one started by the job.
    db.waitlist_sends.update_one({"_id": day}, {"$set": {"at": utcnow(), "with_image": bool(image)},
                                                "$inc": {"sent": sent, "failed": failed,
                                                         "left_for_tomorrow": left}}, upsert=True)
    return {"sent": sent, "failed": failed, "skipped": skipped, "left_for_tomorrow": left,
            "day": day, "with_image": bool(image)}


def due(db, now=None) -> bool:
    """Whether the daily send should run on this tick.

    Two conditions, both needed: the local hour has arrived, and we have not already sent today.
    The per-address idempotency key would catch a second run anyway, but walking the whole list
    every five minutes to discover that is work nobody asked for.
    """
    now = now or utcnow()
    if not S.get(db, "waitlist.email_enabled"):
        return False
    tz = int(S.get(db, "waitlist.email_tz_offset_min") or 0)
    local = now + timedelta(minutes=tz)
    if local.hour < int(S.get(db, "waitlist.email_hour")):
        return False
    row = db.waitlist_sends.find_one({"_id": local.strftime("%Y-%m-%d")})
    # A day whose run reached nobody (the cap was already spent, every address suppressed) is not
    # done: it should be tried again on the next tick rather than written off until tomorrow.
    return not (row and row.get("sent"))


def last_send(db) -> dict | None:
    """The most recent day this went out, for the admin screen."""
    return db.waitlist_sends.find_one({}, sort=[("_id", -1)])


def preview(db, now=None) -> dict:
    """What the admin screen shows before anything is sent: the real three, the real graphic."""
    now = now or utcnow()
    rows = strongest(db, WANT, now)
    tz = int(S.get(db, "waitlist.email_tz_offset_min") or 0)
    image = header_image(db, rows, now) if rows else None
    t = E.get_template(db, "waitlist_matchday")
    v = {"brand": SS.brand_name(db), "name": "there", "date": (now + timedelta(minutes=tz)).strftime("%A %d %B"),
         "link": f"{SS.base_url()}/", "count": len(rows),
         "rows_html": body_html(db, rows, image, tz) if rows else "", "rows_text": body_text(rows, tz)}
    return {"ready": len(rows) >= WANT, "found": len(rows), "members": count(db),
            "with_image": bool(image), "image": image and image[0], "due": due(db, now),
            "last": last_send(db), "hour": int(S.get(db, "waitlist.email_hour")),
            "enabled": bool(S.get(db, "waitlist.email_enabled")),
            "subject": E.render(t["subject"], v, False),
            "html": E.layout(db, E.render(t["html"], v, True), t["category"],
                             f"{SS.base_url()}/unsubscribe-preview")}
