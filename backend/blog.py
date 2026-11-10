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

import math
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


def need_of(thr) -> int | None:
    """How many it takes to reach the line.

    `floor(thr) + 1`, which is the SAME arithmetic as the card's `need()` in ForecastRow and as the
    scoring rule in forecast_outcomes (`reached = actual > thr`). Getting this wrong by one is not a
    rounding nicety: the first build read a 2.0 threshold as "2+ shots" while the evidence line under
    it said "reached 3+ in 6 of the last 10", so the card contradicted its own reasons. A reader
    notices that before they notice anything else on the page.
    """
    if thr is None:
        return None
    return int(math.floor(float(thr))) + 1


def line_label(f: dict) -> str:
    """"3+ shots", "4+ tackles" -- worded exactly as the card words it (ForecastRow lineWords)."""
    stat = str(f.get("stat") or "").replace("_", " ")
    n = need_of(f.get("thr"))
    if n is None:
        return stat or "this line"
    return f"{n}+ {stat}"


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


# Reasons the engine writes that are about AVAILABILITY rather than about why the count should be
# what it is. "Expected minutes are limited" is a real cause of a lower count and stays; a sentence
# that only says someone is likely to be on the pitch answers a different question from the one a
# post titled "why we think this" is asking, and a reader notices.
_NOT_A_REASON = ("he is in the announced eleven", "he has started", "usually starts",
                 "no lineup yet", "no team news")


def _reasons(f: dict, limit: int = 3) -> list[str]:
    """The engine's own reasons, cleaned of anything that would fail the copy check.

    These come from core.top_reasons, which reads the model's own feature contributions and words
    them from a fixed vocabulary -- "The opponent's style allows more shots", "The opponent gives up
    more shots to players in his position", "The expected game state lifts shots". They are the
    actual drivers, not a narrative written around the number afterwards, which is why nothing in
    this module invents a sentence.
    """
    out = []
    for r in (f.get("reasons") or []):
        r = str(r).strip()
        if not r or TG.scan(r):
            continue
        if any(k in r.lower() for k in _NOT_A_REASON):
            continue
        out.append(r)
        if len(out) >= limit:
            break
    return out


def evidence(it: dict, scope: str) -> list[str]:
    """The checkable sentences that go ABOVE the engine's reasons.

    A reader who has never heard of us will not take "the opponent's shape allows more shots" on
    trust, and should not have to: the record on this line and how much it moves between opponents
    are both things they can verify from the strip beside them. Opinion follows evidence, not the
    other way round.
    """
    out = []
    need, cleared, played = it.get("needed"), it.get("cleared"), it.get("played_n")
    who = "He" if scope == "player" else "They"
    if need is not None and played:
        word = "games" if played != 1 else "game"
        out.append(f"{who} reached {need}+ in {cleared} of the last {played} {word}.")
    if (it.get("streak") or 0) >= 3:
        out.append(f"That is {it['streak']} in a row.")
    # docs/56: a rung that answers the same against every defence in the league says nothing about
    # THIS fixture. Saying so is the difference between a forecast and a table of averages.
    sp = it.get("span")
    if sp is not None:
        if sp >= 0.18:
            out.append(f"This line swings about {round(sp * 100)} points depending on the opponent, "
                       f"so the fixture is doing real work here.")
        elif sp <= 0.06:
            out.append("This line barely moves whoever the opponent is, so it is more about the "
                       "player than the fixture.")
    return out


def _fit(limit: int, *candidates: str) -> str:
    """The first candidate that fits, else the last one trimmed at a word boundary.

    A hard slice is what produced "Brighton & Hove Albion 0-0 Wolverhampton Wanderers: how our
    prediction" -- a title cut mid-word, in a search result, on the two clubs with the longest names
    in the league. Candidates go longest to shortest so the full phrasing is used wherever it fits
    and the bare fixture is the floor; the trim is the last resort and ends on a word.
    """
    for c in candidates:
        c = c.strip()
        if len(c) <= limit:
            return c
    last = (candidates[-1] if candidates else "").strip()
    if len(last) <= limit:
        return last
    cut = last[:limit].rstrip()
    sp = cut.rfind(" ")
    return (cut[:sp] if sp > limit * 0.6 else cut).rstrip(" ,.:;-\u2014")


def words(*, final: bool, hn: str, an: str, when: str, score: str, scored_n: int,
          came_in: int, lead: dict) -> tuple[str, str, str]:
    """Title, search description and opening paragraph, for both states of a post.

    One function rather than two, because the two states are the same post at different times and
    the wording has to turn over together: a settled post that kept its preview title promises a
    forecast for a game already played, which is the fault that was reported on the match page.
    """
    if final:
        # The score goes in the TITLE: it is what someone searching afterwards types.
        # Post-match the search changes: people look for the score and the stats, so the title leads
        # with the result and still says what the page uniquely holds.
        head = f"{hn} {score} {an}" if score else f"{hn} vs {an}"
        title = _fit(MAX_TITLE, f"{head}: stats and how our predictions did",
                     f"{head}: how our predictions did", f"{head}: our predictions", head)
        if scored_n:
            desc = (f"{hn} {score} {an}. Of the {scored_n} forecasts in this post, {came_in} came in. "
                    f"Every one is shown either way, with the reasons we gave.")
        else:
            desc = f"{hn} {score} {an}, and the forecasts we published before it, with the reasons we gave."
        intro = (f"{hn} played {an} on {when}"
                 + (f", finishing {score}" if score else "")
                 + ". These are forecasts we published before kick-off, shown with what actually "
                 + "happened \u2014 the ones that came in and the ones that did not.")
        return title, _fit(MAX_DESC, desc), intro
    # "vs", not "v", and "prediction", not "forecasts" (docs/75). Both are what people actually
    # type, and both clear the copy rules: only the transaction words -- odds, picks, props and the
    # rest -- are banned (textguard.BANNED). "Forecast" is our word for the thing; "prediction" is
    # the word someone uses to look for it, and a title that does not contain the search is a page
    # that does not answer it.
    title = _fit(MAX_TITLE, f"{hn} vs {an} prediction, stats and team news",
                 f"{hn} vs {an} prediction and stats", f"{hn} vs {an} prediction", f"{hn} vs {an}")
    desc = (f"{hn} vs {an} forecasts with the reasons shown: {lead['subject']} {lead['line']} at "
            f"{lead['pct']}, and what the last ten games say. {when}.")
    intro = (f"{hn} meet {an} on {when}. Here are three of our forecasts for the match, each with "
             f"the reasons behind it and how likely we think it is.")
    return title, _fit(MAX_DESC, desc), intro


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

    # docs/73: a post for a match already played must say what happened. Without this a post
    # generated for a past fixture reads in the future tense, with no score and no results -- the
    # same fault reported on the match page, in a second place. It is also the whole differentiator:
    # everyone else's forecast page becomes a dead wrong page the moment the whistle goes, and this
    # one becomes a record of what we said and what followed.
    final = m.get("status") == "final"
    outs = {}
    if final:
        outs = {o["forecast_id"]: o for o in db.forecast_outcomes.find(
            {"forecast_id": {"$in": [f["id"] for f in picked if f.get("id")]}},
            {"_id": 0, "forecast_id": 1, "reached": 1, "actual": 1, "player_played": 1})}

    items = []
    for f in picked:
        o = outs.get(f.get("id"))
        need = need_of(f.get("thr"))
        known = [g for g in (f.get("run") or []) if g and g.get("v") is not None]
        run = [{"v": g["v"], "opp": (g.get("opp") or {}).get("name") or "", "m": g.get("m"),
                "home": bool(g.get("home"))} for g in known]
        cleared = sum(1 for g in known if need is not None and g["v"] >= need)
        items.append({
            # Which forecast this was. refresh_settled() attaches results by this id rather than
            # rebuilding the post, so a published post always shows the forecasts AS PUBLISHED.
            "fid": f.get("id"),
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
            # `actual` as well as `reached`: "did not happen" and "2, where 3 were needed" are
            # different amounts of information and we hold the second.
            "result": ({"reached": bool(o.get("reached")), "actual": o.get("actual"),
                        "played": o.get("player_played") is not False} if o else None),
            "needed": need,
            # The ten games the card draws, oldest first, exactly as queries._usual built them.
            # Carried onto the post rather than recomputed, so the strip in a post and the strip on
            # the match page are the same ten numbers and cannot drift.
            "run": run,
            "cleared": cleared,
            "played_n": len(known),
            "streak": int(f.get("streak") or 0),
            # docs/56: how far this rung moves across the league's defences. A line that answers the
            # same against everyone is a fact about the player; one that moves is a fact about the
            # fixture, and only the second is a reason to read this post rather than a table.
            "span": (round(float(f["span"]), 4) if f.get("span") is not None else None),
        })
        items[-1]["evidence"] = evidence(items[-1], f.get("scope") or "player")

    ko = m.get("kickoff")
    # "%d" zero-pads, so the 8th read as "08 November". Nobody writes a date that way in a sentence.
    when = f"{ko.day} {ko.strftime('%B %Y')}" if isinstance(ko, datetime) else ""
    hn, an = home.get("name") or "Home", away.get("name") or "Away"
    lead = items[0]
    scored = [i for i in items if i["result"] and i["result"]["played"]]
    came_in = sum(1 for i in scored if i["result"]["reached"])
    hg, ag = m.get("hg"), m.get("ag")
    score = f"{hg}\u2013{ag}" if final and hg is not None and ag is not None else ""

    title, desc, intro = words(final=final, hn=hn, an=an, when=when, score=score,
                               scored_n=len(scored), came_in=came_in, lead=lead)

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
        "intro": intro,
        "final": final,
        "score": score,
        "came_in": came_in,
        "scored_n": len(scored),
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

    WHICH DAY, WHEN `day` IS NOT GIVEN: TOMORROW'S.

    A post exists to be found before the match, by someone searching the fixture, and to give a
    reader a reason to open the site that evening. Search interest in a fixture peaks in the day or
    two before kick-off; a post published on the morning of the match is too late to be crawled and
    too late to bring anyone in, and one published afterwards has missed the entire point. So the
    batch is built for tomorrow, reviewed today, and published this evening -- the same reasoning,
    and the same choice, as the ad planner (ad_plan.py: "the owner posts the night before").

    A post then UPDATES after the whistle rather than being replaced: same URL, same slug, now
    carrying what happened (docs/73). Before the match it earns the visit; afterwards it earns the
    link, because it is one of the few forecast pages anywhere that stays honest about how it did.

    The order matters because `limit` cuts the tail: if only six posts are wanted from a
    twelve-match Saturday, they should be the six with the most to say, not the six that happen to
    kick off first.
    """
    now = now or utcnow()
    day = day or (now + timedelta(days=1)).date().isoformat()
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


def refresh_settled(db, *, now: datetime | None = None) -> int:
    """Turn a post about a match that has now been played into a post about what happened.

    This is the half of the lifecycle that makes the whole thing worth building. A post is published
    the evening before, where it earns the visit; after the whistle the SAME URL carries what
    happened, which is what earns the link -- almost no forecast page anywhere stays honest about
    how it did, and ours is the record we already publish.

    It updates the stored post IN PLACE, attaching results by the `fid` on each item. It deliberately
    does NOT rebuild from match_detail: the post should show the forecasts exactly as they were
    published, not as they look after a refit, and rebuilding would also fail once the forecasts stop
    being current.

    The title, description and opening paragraph are rewritten by words() above, which supersedes an
    admin's pre-match edit to those three fields. That is intended: a preview title on a settled post
    is a broken promise, and the admin screen can be used to reword it again afterwards.
    """
    now = now or utcnow()
    n = 0
    for post in db.blog_posts.find({"status": "published", "final": {"$ne": True},
                                    "kickoff": {"$lt": now}}, {"_id": 0}):
        m = db.matches.find_one({"iid": post.get("match_iid")},
                                {"_id": 0, "status": 1, "hg": 1, "ag": 1, "kickoff": 1})
        if not m or m.get("status") != "final":
            continue
        fids = [i.get("fid") for i in (post.get("items") or []) if i.get("fid")]
        outs = {o["forecast_id"]: o for o in db.forecast_outcomes.find(
            {"forecast_id": {"$in": fids}},
            {"_id": 0, "forecast_id": 1, "reached": 1, "actual": 1, "player_played": 1})}
        if not outs:
            # Final, but nothing scored yet. Leave it as a preview rather than publish a post that
            # says the match is over and then shows no results; the next tick will pick it up.
            continue
        items = []
        for i in post.get("items") or []:
            o = outs.get(i.get("fid"))
            items.append({**i, "result": ({"reached": bool(o.get("reached")), "actual": o.get("actual"),
                                           "played": o.get("player_played") is not False} if o else None)})
        scored = [i for i in items if i["result"] and i["result"]["played"]]
        came_in = sum(1 for i in scored if i["result"]["reached"])
        hg, ag = m.get("hg"), m.get("ag")
        score = f"{hg}\u2013{ag}" if hg is not None and ag is not None else ""
        ko = m.get("kickoff") or post.get("kickoff")
        when = f"{ko.day} {ko.strftime('%B %Y')}" if isinstance(ko, datetime) else (post.get("day") or "")
        hn = (post.get("home") or {}).get("name") or "Home"
        an = (post.get("away") or {}).get("name") or "Away"
        title, desc, intro = words(final=True, hn=hn, an=an, when=when, score=score,
                                   scored_n=len(scored), came_in=came_in, lead=items[0] if items else {})
        up = {"items": items, "final": True, "score": score, "came_in": came_in,
              "scored_n": len(scored), "title": title, "description": desc, "intro": intro,
              "settled_at": now}
        try:
            TG.require_clean("blog post", {k: up[k] for k in ("title", "description", "intro")})
            TG.require_clean("blog forecasts", items)
        except TG.BannedWords:
            continue
        db.blog_posts.update_one({"slug": post["slug"]}, {"$set": up})
        n += 1
    return n


def purge_old_drafts(db, *, days: int = 14, now: datetime | None = None) -> int:
    """Drafts for matches that have been and gone. Nobody reviews a post for last week's fixture."""
    cut = (now or utcnow()) - timedelta(days=int(days))
    return db.blog_posts.delete_many({"status": "draft", "kickoff": {"$lt": cut}}).deleted_count
