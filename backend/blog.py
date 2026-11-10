"""blog.py -- the daily match posts: planned from our own forecasts, reviewed, then published (docs/72).

WHY THIS IS SERVER-RENDERED AND THE REST OF THE SITE IS NOT. The product is a client-rendered app:
the HTML a crawler receives is `<div id="root"></div>`, and Slack, WhatsApp, X and Facebook never run
JavaScript (docs/71). A blog whose whole purpose is organic arrivals and shared links cannot be part
of that app, so a post is rendered to finished HTML here, by `render_html`, and served as a real
page. It carries no JavaScript at all -- which makes it fast, crawlable, and immune to the CSP
argument a scripted page would start.

WHAT A POST MAY AND MAY NOT SAY. Nothing in this module invents a number, and nothing it writes
reaches a reader unreviewed:

  * Every figure is read off a stored forecast. There is no prose generator inventing a reason:
    the sentences come from the `reasons` list the engine already wrote (engine_bridge), the same
    list the match page shows, so a post cannot claim something the product itself does not.
  * Every string that will be published is passed through textguard. The banned-word list is
    CI-enforced for anything an admin types (docs/03); copy a machine assembles has to clear the
    same bar, and it is the likelier offender -- `units`, `picks` and `hit rate` are ordinary
    football-writing words.
  * A post is created as a DRAFT. Publishing is a separate, deliberate admin action. The public
    route refuses anything not published, so a half-built post cannot be found by guessing a slug.

WHY THREE FORECASTS AND NOT ALL OF THEM. The post exists to earn a visit and a sign-up, so it shows
enough to be worth reading and not enough to replace the product: one Strong, one Solid, and one
lower rung -- which also quietly teaches what the tiers mean. The rest of the match stays behind the
link.

WHAT HAPPENS WHEN THE DAY IS THIN. A tier is not a quota. Most days have no Strong forecast at all
(docs/52: a badge grades the DEPARTURE from a player's usual game, and "no badge" is the commonest
honest answer). So `pick_three` fills what it can and says what it could not fill, and a match with
nothing worth showing produces no post rather than an empty one. Generating 380 near-identical pages
is how a site of its own data gets treated as scaled content abuse (docs/71).
"""
from __future__ import annotations

import re
import unicodedata
from datetime import datetime, timedelta, timezone

import queries as Q
import settings_store as S
import textguard as TG

STATUSES = ("draft", "published")

# The rungs a post shows, in the order it shows them. "lower" is Watch or an ungraded rung: both are
# real answers, and one of them appears on most cards.
SLOTS = ("Strong", "Solid", "lower")

MAX_TITLE = 70          # beyond this Google truncates the title in a result
MAX_DESC = 155          # and the description
MIN_FORECASTS = 2       # a post with one forecast is not worth a page


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def slugify(s: str, limit: int = 80) -> str:
    """A URL-safe slug. Accents are folded rather than dropped, so a club name stays recognisable."""
    s = unicodedata.normalize("NFKD", str(s or "")).encode("ascii", "ignore").decode()
    s = re.sub(r"[^a-zA-Z0-9]+", "-", s).strip("-").lower()
    return s[:limit].strip("-") or "post"


def post_slug(home: str, away: str, kickoff) -> str:
    """`arsenal-v-chelsea-2026-11-14`.

    The date is in the slug on purpose. These clubs meet twice a season, and a slug that collides
    would either overwrite last season's post or force a `-2` suffix nobody can read.
    """
    day = (kickoff.date().isoformat() if isinstance(kickoff, datetime) else str(kickoff or "")[:10])
    return f"{slugify(home, 28)}-v-{slugify(away, 28)}-{day}"


def _pct(p) -> str:
    return f"{round(float(p) * 100)}%"


def _subject(f: dict, home: dict, away: dict) -> str:
    """Who the forecast is about: the player, or the club for a team line."""
    if f.get("player"):
        return f["player"].get("name") or "A player"
    if f.get("team_iid") == home.get("iid"):
        return home.get("name") or "The home side"
    if f.get("team_iid") == away.get("iid"):
        return away.get("name") or "The away side"
    return "Both teams"


def line_label(f: dict) -> str:
    """"2+ shots", "4+ tackles", "Over 3.5 cards" -- the product's own phrasing for a rung."""
    thr = f.get("thr")
    stat = str(f.get("stat") or "").replace("_", " ")
    if thr is None:
        return stat or "this line"
    t = float(thr)
    if abs(t - round(t)) < 1e-9:                       # a whole number: "2+ shots"
        return f"{int(round(t))}+ {stat}"
    return f"over {t:g} {stat}"                         # a half line: "over 3.5 cards"


def tier_of(f: dict) -> str:
    t = f.get("tier")
    return t if t in ("Strong", "Solid", "Watch") else "lower"


def _slot_of(f: dict) -> str:
    t = f.get("tier")
    return t if t in ("Strong", "Solid") else "lower"


def pick_three(cards: list[dict]) -> tuple[list[dict], list[str]]:
    """One Strong, one Solid, one lower rung. Returns (picked, slots it could not fill).

    `cards` arrives in the order the match page shows them, so taking the first of each tier takes
    the one the product itself leads with rather than a second ranking invented here that could
    disagree with the screen. That order is not group_cards' doing -- it appends in group order and
    never sorts. It comes from match_detail, which sorts the forecasts by p descending BEFORE
    grouping, so each group lands at the position of its own likeliest rung. Re-sorting here would
    therefore be the thing that introduced a disagreement, not the thing that prevented one.
    """
    picked, missing, used = [], [], set()
    for slot in SLOTS:
        hit = next((f for f in cards if _slot_of(f) == slot and id(f) not in used), None)
        if hit is None:
            missing.append(slot)
            continue
        used.add(id(hit))
        picked.append(hit)
    return picked, missing


def _reasons(f: dict, limit: int = 3) -> list[str]:
    """The engine's own reasons, cleaned of anything that would fail the copy check."""
    out = []
    for r in (f.get("reasons") or []):
        r = str(r).strip()
        if r and not TG.scan(r):
            out.append(r)
        if len(out) >= limit:
            break
    return out


def build_post(db, match_iid: int, *, now: datetime | None = None) -> dict | None:
    """One post for one fixture, as structured blocks. None when the fixture has too little to say.

    Blocks, not HTML: the admin screen edits them, the renderer turns them into a page, and the two
    cannot drift. It also means a post written today still renders correctly after the palette, the
    brand or the CTA wording changes.
    """
    now = now or utcnow()
    d = Q.match_detail(db, match_iid)
    if not d:
        return None
    m, home, away = d["match"], d["home"], d["away"]
    cards = [c for c in (d.get("cards") or []) if c.get("p") is not None]
    picked, missing = pick_three(cards)
    if len(picked) < MIN_FORECASTS:
        return None

    items = []
    for f in picked:
        items.append({
            "subject": _subject(f, home, away),
            "image": (f.get("player") or {}).get("image") or "",
            "line": line_label(f),
            "p": round(float(f["p"]), 4),
            "pct": _pct(f["p"]),
            "lo": (round(float(f["lo"]), 4) if f.get("lo") is not None else None),
            "hi": (round(float(f["hi"]), 4) if f.get("hi") is not None else None),
            "tier": tier_of(f),
            "usual": (round(float(f["p_usual"]), 4) if f.get("p_usual") is not None else None),
            "reasons": _reasons(f),
        })

    ko = m.get("kickoff")
    when = ko.strftime("%d %B %Y") if isinstance(ko, datetime) else ""
    hn, an = home.get("name") or "Home", away.get("name") or "Away"
    title = f"{hn} v {an} forecasts, {when}".strip().rstrip(",")
    lead = items[0]
    desc = (f"What we expect from {hn} v {an}: {lead['subject']} {lead['line']} at {lead['pct']}, "
            f"and the reasons behind it.")

    post = {
        "slug": post_slug(hn, an, ko),
        "match_iid": int(match_iid),
        "day": (ko.date().isoformat() if isinstance(ko, datetime) else ""),
        "kickoff": ko,
        "status": "draft",
        "title": title[:MAX_TITLE],
        "description": desc[:MAX_DESC],
        "home": {"name": hn, "image": home.get("image") or "", "id": home.get("id")},
        "away": {"name": an, "image": away.get("image") or "", "id": away.get("id")},
        "match_id": m.get("id"),
        "intro": (f"{hn} meet {an} on {when}. Here are three of our forecasts for the match, each with "
                  f"the reasons behind it and how likely we think it is."),
        "items": items,
        # Said in the post rather than hidden: a day with no Strong forecast is the normal case, and a
        # reader who is told that learns what the badge means instead of assuming we had nothing.
        "missing": missing,
        "generated_at": now,
        "published_at": None,
        "published_by": None,
        "edited_by": None,
    }
    # Everything above is assembled from stored data, so this is the gate that decides whether a
    # machine is allowed to have written it.
    TG.require_clean("blog post", {k: post[k] for k in ("title", "description", "intro")})
    TG.require_clean("blog forecasts", items)
    return post


def plan_day(db, day: str | None = None, *, limit: int | None = None, now: datetime | None = None) -> list[dict]:
    """Draft posts for one day's fixtures, best-supported match first.

    The order matters because `limit` cuts the tail: if only six posts are wanted from a
    twelve-match Saturday, they should be the six with the most to say, not the six that happen to
    kick off first.
    """
    now = now or utcnow()
    day = day or now.date().isoformat()
    limit = int(limit if limit is not None else (S.get(db, "blog.max_per_day") or 6))
    ms = Q.fixtures_for_date(db, day)
    out = []
    for m in ms:
        iid = m.get("iid")
        if iid is None:
            continue
        try:
            p = build_post(db, int(iid), now=now)
        except TG.BannedWords:
            # A reason the engine wrote tripped the copy check. Skip the fixture rather than publish
            # it or strip words out of a sentence until it passes; the admin screen shows the gap.
            continue
        if p:
            out.append(p)
    out.sort(key=lambda p: (-len(p["items"]), -sum(1 for i in p["items"] if i["tier"] == "Strong"), p["slug"]))
    return out[:limit]


# ----------------------------------------------------------------- storage

def upsert_draft(db, post: dict) -> str:
    """Store a draft, never touching a post that is already published.

    Re-running the day's generation is expected -- a forecast is refit on every tick -- so a draft is
    replaced with the newer one. A PUBLISHED post is left exactly as it was: it has a URL that may
    already be shared and indexed, and silently rewriting what it says is not a generation concern.
    """
    cur = db.blog_posts.find_one({"slug": post["slug"]}, {"status": 1})
    if cur and cur.get("status") == "published":
        return "kept"
    db.blog_posts.replace_one({"slug": post["slug"]}, post, upsert=True)
    return "replaced" if cur else "created"


def generate(db, day: str | None = None, *, limit: int | None = None, now: datetime | None = None) -> dict:
    counts = {"created": 0, "replaced": 0, "kept": 0}
    for p in plan_day(db, day, limit=limit, now=now):
        counts[upsert_draft(db, p)] += 1
    return counts


def get_public(db, slug: str) -> dict | None:
    """A published post, by slug. The only reader a visitor ever reaches."""
    return db.blog_posts.find_one({"slug": slug, "status": "published"}, {"_id": 0})


def published(db, limit: int = 50) -> list[dict]:
    return list(db.blog_posts.find({"status": "published"}, {"_id": 0})
                .sort([("published_at", -1)]).limit(int(limit)))


def listing(db, status: str | None = None, limit: int = 100) -> list[dict]:
    q = {"status": status} if status in STATUSES else {}
    return list(db.blog_posts.find(q, {"_id": 0, "items": 0})
                .sort([("kickoff", -1), ("generated_at", -1)]).limit(int(limit)))


def publish(db, slug: str, actor: str) -> dict:
    p = db.blog_posts.find_one({"slug": slug}, {"_id": 0})
    if not p:
        return {}
    # Re-checked at the moment of publishing, not only when generated. An admin may have edited the
    # title or the intro in between, and an edit is exactly where a banned word gets in.
    TG.require_clean("blog post", {k: p.get(k) for k in ("title", "description", "intro")})
    TG.require_clean("blog forecasts", p.get("items") or [])
    db.blog_posts.update_one({"slug": slug}, {"$set": {"status": "published", "published_at": utcnow(),
                                                       "published_by": actor}})
    return db.blog_posts.find_one({"slug": slug}, {"_id": 0})


def unpublish(db, slug: str, actor: str) -> dict:
    db.blog_posts.update_one({"slug": slug}, {"$set": {"status": "draft", "published_at": None,
                                                       "published_by": None, "edited_by": actor}})
    return db.blog_posts.find_one({"slug": slug}, {"_id": 0}) or {}


EDITABLE = ("title", "description", "intro")


def edit(db, slug: str, fields: dict, actor: str) -> dict:
    """The three fields an admin may rewrite. The numbers are not among them, by design.

    A reviewer may improve the wording; they may not change what the forecast said. If a figure is
    wrong the fix belongs in the engine, and the post should be regenerated.
    """
    up = {k: str(fields[k]).strip() for k in EDITABLE if k in fields}
    if not up:
        return db.blog_posts.find_one({"slug": slug}, {"_id": 0}) or {}
    up["title"] = up.get("title", "")[:MAX_TITLE] if "title" in up else None
    up = {k: v for k, v in up.items() if v is not None}
    if "description" in up:
        up["description"] = up["description"][:MAX_DESC]
    TG.require_clean("blog post", up)
    up["edited_by"] = actor
    db.blog_posts.update_one({"slug": slug}, {"$set": up})
    return db.blog_posts.find_one({"slug": slug}, {"_id": 0}) or {}


def purge_old_drafts(db, *, days: int = 14, now: datetime | None = None) -> int:
    """Drafts for matches that have been and gone. Nobody reviews a post for last week's fixture."""
    cut = (now or utcnow()) - timedelta(days=int(days))
    return db.blog_posts.delete_many({"status": "draft", "kickoff": {"$lt": cut}}).deleted_count
