"""blog_render.py -- a blog post as a finished HTML page (docs/72).

This is the only page in the product that is rendered on the server, and the reason is narrow: a
post exists to be found by a search engine and to survive being pasted into a chat. The app cannot
do either -- it is client-rendered, so a crawler receives `<div id="root"></div>`, and no social
crawler runs JavaScript (docs/71). So the post is assembled here, as HTML, and served as a page.

THREE DECISIONS WORTH KNOWING:

  * NO JAVASCRIPT. Not "very little": none. A page with no script is fast on a phone, impossible to
    get wrong in a crawler, and needs no argument with the Content-Security-Policy -- the route sets
    its own, allowing images and one inline stylesheet and nothing else.

  * THE PALETTE IS THE LIVE ONE. The CSS variables come from Site Studio's compiled theme, the same
    string the app loads at runtime, so a post follows the brand without being regenerated. The
    forecast card markup mirrors the agreed row (docs/61) rather than inventing a second visual
    language for the one page a stranger sees first.

  * THE CTA IS THE POINT. The post gives three forecasts and the reasons; the product has the other
    twenty for that match, every other match, the Finder and the record. So the call to action is
    not a footer afterthought -- it sits after the forecasts, where a reader who has just found the
    reasoning useful is most likely to act, and again at the end.

Every value interpolated below is escaped. Club and player names come from a provider, and a stray
`<` in one would otherwise end the document early.
"""
from __future__ import annotations

from datetime import datetime
from html import escape as esc
from urllib.parse import quote

import settings_store as S
import site_studio as SS
from tiering import TIER_LABEL as TG_LABEL

# Images and one inline stylesheet. No script, no frames, no fonts from anywhere else. The default
# app CSP is `default-src 'none'`, which would blank this page, so the route sets this instead.
# `script-src 'none'` is stated rather than left to default-src, because this page does carry one
# <script type="application/ld+json"> block. That is a DATA block: browsers never execute a script
# of a non-JavaScript type, so CSP does not apply to it and the no-JavaScript rule above holds. Being
# explicit here means a future edit that adds real script is refused by the browser, not shipped.
CSP = ("default-src 'none'; script-src 'none'; img-src 'self' https: data:; style-src 'unsafe-inline'; "
       "form-action 'self'; base-uri 'none'; frame-ancestors 'none'")

# The reader's words, from the one place that decides them (tiering.TIER_LABEL, mirrored in the app
# by lib/copy.js). A post is the FIRST place most readers meet the badge, so it must not teach a
# vocabulary the app then contradicts.
TIER_WORD = {**TG_LABEL, "lower": "No badge"}

# Why each tier is what it is, in a sentence, because a stranger has never seen the badge before and
# the post is where they meet it. These match docs/52 and the Learn article: the badge grades the
# DEPARTURE from a player's usual game, never the percentage beside it.
# What each badge means, in a sentence, because a post is the first place most readers meet one.
#
# These describe the LIKELIHOOD grading, which is what the words say and what the engine does unless
# `engine.personal_lines` is on. With that setting on the badge grades the departure from the
# player's usual game instead, and these sentences would be wrong -- so `_tier_help` picks the right
# set rather than printing one of them regardless (docs/75).
TIER_HELP = {
    "Strong": "we make this 90% or more likely, and the low end of the range clears 84% too",
    "Solid": "80% or more, with the low end of the range above 70%",
    "Watch": "worth a card, but under the bar Solid asks for",
    "lower": "nothing here clears the Watch bar, which is an honest answer and a common one",
}
TIER_HELP_DEPARTURE = {
    "Strong": "a big gap between tonight and this player's usual game, with the likely range clear of it",
    "Solid": "a gap worth saying, though the likely range still reaches their usual",
    "Watch": "a small gap \u2014 tonight looks close to any other night",
    "lower": "tonight looks like any other night for them, which is the commonest honest answer",
}


def _tier_help(db, tier: str) -> str:
    """The sentence that matches the rule actually in force, not the one that reads better."""
    try:
        import settings_store as _S
        departure = bool(_S.get(db, "engine.personal_lines"))
    except Exception:
        departure = False
    return (TIER_HELP_DEPARTURE if departure else TIER_HELP).get(tier, "")

STYLE = """
/* Token names are Site Studio's own (COLOR_TOKENS in site_studio.py): --border, not --line;
   --font-body, not --font; --on-brand for text sitting on a brand fill; --tier-strong/-solid/-watch
   for the badges. compile_css() has already set the body font, background and heading family above,
   so nothing here restates them -- a second opinion about the font is how the one page a stranger
   sees first stops looking like the product. */
*,*::before,*::after{box-sizing:border-box}
body{margin:0;line-height:1.6;-webkit-text-size-adjust:100%}
.wrap{max-width:720px;margin:0 auto;padding:16px}
a{color:var(--brand)}
header.top{display:flex;align-items:center;gap:10px;padding:14px 0;border-bottom:1px solid var(--border)}
header.top a{text-decoration:none;color:var(--text);font-weight:700;font-size:17px}
h1{font-size:28px;line-height:1.22;margin:22px 0 6px;letter-spacing:-.01em}
.kick{color:var(--text3);font-size:14px;margin:0 0 18px}
.lead{font-size:17px;color:var(--text2)}
.fx{display:flex;align-items:center;gap:12px;background:var(--surface1);border:1px solid var(--border);
  border-radius:var(--radius-lg,14px);padding:14px;margin:18px 0}
.fx .side{display:flex;align-items:center;gap:8px;flex:1;min-width:0}
.fx .side.away{justify-content:flex-end}
.fx .side span{font-weight:700;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.fx img{width:30px;height:30px;object-fit:contain;flex:none}
.fx .v{color:var(--text3);font-size:13px;flex:none}
h2{font-size:21px;margin:30px 0 4px}
.card{background:var(--surface1);border:1px solid var(--border);border-radius:var(--radius-lg,14px);padding:14px;margin:14px 0}
.card .who{display:flex;align-items:center;gap:10px;margin-bottom:10px}
.card .who img{width:38px;height:38px;border-radius:50%;object-fit:cover;background:var(--surface2);flex:none}
.card .who b{font-size:16px}
.card .who small{display:block;color:var(--text3);font-size:13px}
.row{display:flex;align-items:baseline;gap:10px;justify-content:space-between}
.row .p{font-size:30px;font-weight:800;letter-spacing:-.02em}
.bar{height:8px;border-radius:99px;background:var(--surface2);overflow:hidden;margin:8px 0 4px}
.bar i{display:block;height:100%;background:var(--brand)}
.rng{color:var(--text3);font-size:13px;margin:0}
/* The ten-game strip, same rules as the card's (likely.css .lk-run*). */
.runwrap{display:flex;align-items:flex-end;gap:14px;margin:12px 0 10px}
.runbox{position:relative;padding-left:18px}
.need{position:absolute;left:0;font-size:11px;font-weight:700;color:var(--text3);line-height:1}
.run{position:relative;display:flex;align-items:flex-end;gap:4px;height:44px}
.rule{position:absolute;left:0;right:0;border-top:1px dashed var(--border);height:0}
.run i{display:block;width:11px;border-radius:2px 2px 0 0}
.runcnt{font-size:13px;color:var(--text2);font-weight:700;line-height:1.25}
.runcnt small{display:block;font-size:11.5px;font-weight:500;color:var(--text3)}
.badge{display:inline-block;font-size:12px;font-weight:700;padding:3px 9px;border-radius:99px;
  border:1px solid var(--border);color:var(--text2);background:var(--surface2);white-space:nowrap}
.badge--strong{border-color:var(--tier-strong);color:var(--tier-strong)}
.badge--solid{border-color:var(--tier-solid);color:var(--tier-solid)}
.badge--watch{border-color:var(--tier-watch);color:var(--tier-watch)}
.why{margin:10px 0 0;padding-left:18px;color:var(--text2);font-size:15px}
.why li{margin:3px 0}
.cta{background:var(--brand);color:var(--on-brand);border-radius:var(--radius-lg,16px);padding:22px;margin:28px 0;text-align:center}
.cta h3{margin:0 0 6px;font-size:21px;color:var(--on-brand)}
.cta p{margin:0 0 16px;font-size:15px;opacity:.92}
.cta a{display:inline-flex;align-items:center;justify-content:center;background:var(--on-brand);color:var(--brand);
  font-weight:800;text-decoration:none;padding:0 26px;min-height:var(--btn-h-lg,48px);
  border-radius:var(--btn-radius,99px);font-size:16px}
.grid{display:grid;grid-template-columns:1fr 1fr;gap:12px;margin:18px 0}
.box{background:var(--surface1);border:1px solid var(--border);border-radius:var(--radius-md,14px);padding:14px}
.box b{display:block;margin-bottom:4px;font-size:15px}
.box span{color:var(--text2);font-size:14px}
.res{margin:0 0 6px;font-size:14px;font-weight:700}
.res--hit{color:var(--up)}
.res--miss{color:var(--text3)}
.res--dnp{color:var(--text3);font-weight:600}
.sc{flex:none;text-align:center;font-size:22px;font-weight:800;letter-spacing:-.01em;line-height:1.1}
.sc small{display:block;font-size:11px;font-weight:700;letter-spacing:.06em;color:var(--text3)}
.share{border:1px solid var(--border);border-radius:var(--radius-md,14px);padding:14px;margin:22px 0}
.share b{display:block;margin-bottom:9px;font-size:15px}
.sh-row{display:flex;flex-wrap:wrap;gap:8px}
.sh{display:inline-flex;align-items:center;min-height:40px;padding:0 14px;border-radius:99px;
  border:1px solid var(--border);background:var(--surface2);color:var(--text);text-decoration:none;
  font-size:14px;font-weight:700}
.sh-url{margin:10px 0 0;font-size:12.5px;color:var(--text3);word-break:break-all;user-select:all}
.note{color:var(--text3);font-size:14px;background:var(--surface2);border-radius:var(--radius-md,12px);padding:12px;margin:18px 0}
footer{border-top:1px solid var(--border);margin-top:34px;padding:18px 0 40px;color:var(--text3);font-size:13px}
footer a{color:var(--text3)}
footer p{margin:6px 0}
.posts{list-style:none;padding:0}
.posts li{border-bottom:1px solid var(--border);padding:14px 0}
.posts a{font-weight:700;font-size:17px;text-decoration:none;color:var(--text)}
.posts small{display:block;color:var(--text3)}
@media (max-width:420px){h1{font-size:24px}.grid{grid-template-columns:1fr}}
"""


def _theme_css(db) -> str:
    """The live palette, as the app loads it. A post follows the brand with no regeneration."""
    try:
        return SS.compile_css((SS.get_live(db) or {}).get("data") or {})
    except Exception:
        return ""


def _brand(db) -> dict:
    d = (SS.get_live(db) or {}).get("data") or {}
    return d.get("brand") or {}


def _img(url: str) -> str:
    """Only our own media or an https address. A provider URL on http would break the padlock."""
    u = str(url or "")
    if u.startswith("/api/") or u.startswith("https://"):
        return u
    return ""


def _crest(url: str, alt: str) -> str:
    u = _img(url)
    return f'<img src="{esc(u)}" alt="{esc(alt)}" width="30" height="30" loading="lazy">' if u else ""


def _face(url: str, alt: str) -> str:
    u = _img(url)
    return f'<img src="{esc(u)}" alt="{esc(alt)}" width="38" height="38" loading="lazy">' if u else ""


def _card(it: dict, db=None) -> str:
    tier = it.get("tier") or "lower"
    word = TIER_WORD.get(tier, "No badge")
    help_ = _tier_help(db, tier)
    pct = int(round(float(it.get("p") or 0) * 100))
    cls = f" badge--{tier.lower()}" if tier in ("Strong", "Solid", "Watch") else ""
    rng = ""
    if it.get("lo") is not None and it.get("hi") is not None:
        rng = f"<p class=\"rng\">Likely range {int(round(it['lo'] * 100))}% to {int(round(it['hi'] * 100))}%.</p>"
    usual = ""
    if it.get("usual") is not None:
        usual = f"<p class=\"rng\">In their usual game this line comes in about {int(round(it['usual'] * 100))}% of the time.</p>"
    # Evidence first, opinion second. The record and the swing are checkable against the strip
    # above them; the engine's reasons are the model's read of the fixture. A stranger should not be
    # asked to accept the second before they have been shown the first.
    why = ""
    lines = list(it.get("evidence") or []) + list(it.get("reasons") or [])
    if lines:
        why = "<ul class=\"why\">" + "".join(f"<li>{esc(r)}</li>" for r in lines) + "</ul>"
    # What happened, when the match has been played and the forecast scored.
    res = ""
    r = it.get("result")
    if r:
        if r.get("played") is False:
            res = '<p class="res res--dnp">He did not play, so this one was never scored.</p>'
        else:
            got = None if r.get("actual") is None else (round(float(r["actual"]) * 10) / 10)
            got = int(got) if got is not None and float(got).is_integer() else got
            need = it.get("needed")
            if r.get("reached"):
                tail = f" \u2014 {got}" if got is not None else ""
                res = f'<p class="res res--hit">Happened{esc(str(tail))}</p>'
            else:
                verb = "was" if need == 1 else "were"
                tail = f" \u2014 {got}, where {need} {verb} needed" if got is not None and need is not None else ""
                res = f'<p class="res res--miss">Did not happen{esc(str(tail))}</p>'

    return f"""<article class="card">
  <div class="who">{_face(it.get('image'), it.get('subject') or '')}
    <div><b>{esc(it.get('subject') or '')}</b><small>{esc(it.get('line') or '')}</small></div>
  </div>
  <div class="row"><span class="p">{pct}%</span><span class="badge{cls}">{esc(word)}</span></div>
  <div class="bar"><i style="width:{pct}%"></i></div>
  {res}{_runstrip(it)}{rng}{usual}{why}
  <p class="rng">{esc(word)}: {esc(help_)}.</p>
</article>"""


RH = 44                 # run strip height in px. Taller than the card's 26: this page has a
                        # column to itself, and it is the first time a reader has seen the strip.


def _runstrip(it: dict) -> str:
    """The last ten games on this line, as the product's own card draws them (ForecastRow's Run).

    The same shape and the same rules, in CSS rather than JSX, because this page runs no script:
      * bars scaled to the taller of the line and the biggest count, so the rule is always on screen
      * the threshold drawn BEHIND the bars, so it shows in the gaps and above a bar that fell
        short, and never reads as a strikethrough across a bar that cleared it
      * a bar that cleared the line is two-tone, splitting AT the rule, so the level reads across
        the strip at one height
      * fewer than three known games draws nothing: that is not evidence of anything

    This is the half of a forecast a reader can check for themselves, which is why it belongs in a
    post that is trying to earn their trust before it asks for their e-mail address.
    """
    run, need = it.get("run") or [], it.get("needed")
    if need is None or len(run) < 3:
        return ""
    mx = max([need] + [g["v"] for g in run])
    y = max(1, round((need / mx) * RH))
    bars = []
    for g in run:
        h = max(2, round((g["v"] / mx) * RH))
        hit = g["v"] >= need
        fill = (f"linear-gradient(to top, var(--brand) 0 {min(h, y)}px, var(--tier-strong) {min(h, y)}px 100%)"
                if hit else "var(--surface3, var(--text3))")
        where = ("home to " if g.get("home") else "away at ") if g.get("opp") else ""
        label = f'{g["v"]} {where}{g["opp"]}'.strip() if g.get("opp") else str(g["v"])
        bars.append(f'<i style="height:{h}px;background:{fill}" title="{esc(label)}"></i>')
    cleared, played = it.get("cleared") or 0, it.get("played_n") or len(run)
    return f"""<div class="runwrap">
  <div class="runbox" role="img" aria-label="Reached it in {cleared} of the last {played}.">
    <span class="need" style="bottom:{y - 1}px">{need}</span>
    <span class="run"><span class="rule" style="bottom:{y}px"></span>{''.join(bars)}</span>
  </div>
  <span class="runcnt"><b>{cleared}</b> of {played}<small>last {played} games on this line</small></span>
</div>"""


def _cta(db, brand: dict, where: str) -> str:
    base = SS.base_url()
    head = S.get(db, "blog.cta_title") or "See every forecast for this match"
    body = S.get(db, "blog.cta_body") or (
        "This post shows three. The app has the rest of this match, every other match we cover, "
        "and the reasons behind each one.")
    label = S.get(db, "blog.cta_button") or "Create a free account"
    # A distinct `from` per position, so the analytics can say which of the two earned the sign-up
    # rather than crediting whichever one happens to be first in the markup.
    href = f"{base}/sign-up?from=blog-{esc(where)}"
    return f"""<section class="cta">
  <h3>{esc(head)}</h3>
  <p>{esc(body)}</p>
  <a href="{href}">{esc(label)}</a>
</section>"""


def _share(title: str, url: str) -> str:
    """A share row, with NO JavaScript.

    The obvious build is a button calling navigator.share, and it would cost this page the one
    property that makes it worth having: a script tag, which means a CSP that allows script, on the
    only page in the product a stranger meets first. Plain links to each network's share endpoint
    need no script at all, open the native app on a phone, and work in a browser with JS switched
    off -- which is also, not coincidentally, the state every crawler reads this page in.

    The address is printed as text beside them because a reader who wants to paste it somewhere we
    have not listed should not have to fish it out of the address bar, and `Copy` is the one control
    here that genuinely cannot work without script.
    """
    t = quote(title)
    u = quote(url)
    nets = [
        ("X", f"https://twitter.com/intent/tweet?text={t}&url={u}"),
        ("WhatsApp", f"https://wa.me/?text={quote(title + ' ' + url)}"),
        ("Facebook", f"https://www.facebook.com/sharer/sharer.php?u={u}"),
        ("Reddit", f"https://www.reddit.com/submit?url={u}&title={t}"),
        ("Email", f"mailto:?subject={t}&body={quote(title + chr(10) + chr(10) + url)}"),
    ]
    links = "".join(
        f'<a class="sh" href="{esc(href)}" target="_blank" rel="noopener noreferrer nofollow">{esc(name)}</a>'
        for name, href in nets)
    return f"""<section class="share">
  <b>Share this</b>
  <div class="sh-row">{links}</div>
  <p class="sh-url">{esc(url)}</p>
</section>"""


def _benefits(db) -> str:
    rows = [
        ("Every forecast carries its reasons", "The numbers are shown with what drove them, so you can disagree with the reasoning rather than take it on trust."),
        ("Graded, not just ranked", "Strong, Solid and Watch grade how much a forecast has to say \u2014 the gap between tonight and a player's usual game."),
        ("The record is public", "Every forecast we publish is scored and kept, including the ones that were not reached."),
        ("Ask your own question", "The Finder answers any player or club line you can think of, not just the ones we chose to write about."),
    ]
    return "<div class=\"grid\">" + "".join(
        f"<div class=\"box\"><b>{esc(a)}</b><span>{esc(b)}</span></div>" for a, b in rows) + "</div>"


def _head(db, *, title: str, desc: str, url: str, brand: dict, image: str = "", kind: str = "article") -> str:
    name = brand.get("name") or "Forecast Zone"
    og_img = _img(image) or _img((((SS.get_live(db) or {}).get("data") or {}).get("seo") or {}).get("og_image") or "")
    if og_img:
        img_tags = (f'<meta property="og:image" content="{esc(og_img)}">'
                    f'<meta name="twitter:card" content="summary_large_image">')
    else:
        img_tags = '<meta name="twitter:card" content="summary">'
    return f"""<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(title)}</title>
<meta name="description" content="{esc(desc)}">
<link rel="canonical" href="{esc(url)}">
<meta property="og:site_name" content="{esc(name)}">
<meta property="og:title" content="{esc(title)}">
<meta property="og:description" content="{esc(desc)}">
<meta property="og:url" content="{esc(url)}">
<meta property="og:type" content="{esc(kind)}">
{img_tags}
<meta name="twitter:title" content="{esc(title)}">
<meta name="twitter:description" content="{esc(desc)}">
<style>{_theme_css(db)}{STYLE}</style>"""


def _chrome(db, brand: dict) -> tuple[str, str]:
    base = SS.base_url()
    name = brand.get("name") or "Forecast Zone"
    site = brand.get("site") or ""
    top = f"""<header class="top"><a href="{esc(base)}/"><b>{esc(name)}</b></a></header>"""
    foot = f"""<footer>
  <p><a href="{esc(base)}/">{esc(name)}</a>{(' &middot; ' + esc(site)) if site else ''}</p>
  <p>Statistical analysis for information and entertainment. Not betting advice.</p>
  <p><a href="{esc(base)}/legal/terms">Terms</a> &middot; <a href="{esc(base)}/legal/privacy">Privacy</a>
     &middot; <a href="{esc(base)}/track-record">Track record</a></p>
</footer>"""
    return top, foot


def post_url(slug: str) -> str:
    """Where a post lives.

    Under /api because only /api reaches this service -- the platform serves the static app at every
    other path, and this page has to come from the server to be worth anything (docs/71, docs/72).
    One rewrite rule from /blog/* to /api/blog/* is all it would take to make this pretty; until
    then, this is the address that works, and it is the one in the sitemap and in og:url so there is
    never a second URL for the same post.
    """
    return f"{SS.base_url()}/api/blog/{slug}"


def _jsonld(post: dict, brand: dict, url: str) -> str:
    """Article structured data. Google reads it for the headline, the dates and the publisher.

    Written by hand rather than with json.dumps on purpose: `</script>` inside a JSON string ends the
    block in an HTML parser, so every value goes through the HTML escaper like everything else.
    """
    pub = post.get("published_at")
    when = pub.isoformat() if isinstance(pub, datetime) else ""
    rows = [
        ('"@context"', '"https://schema.org"'),
        ('"@type"', '"NewsArticle"'),
        ('"headline"', f'"{esc(post.get("title") or "")}"'),
        ('"description"', f'"{esc(post.get("description") or "")}"'),
        ('"mainEntityOfPage"', f'"{esc(url)}"'),
        ('"datePublished"', f'"{esc(when)}"'),
        ('"publisher"', '{"@type":"Organization","name":"%s"}' % esc(brand.get("name") or "Forecast Zone")),
    ]
    body = ",".join(f"{k}:{v}" for k, v in rows)
    return f'<script type="application/ld+json">{{{body}}}</script>'


def render_post(db, post: dict) -> str:
    brand = _brand(db)
    url = post_url(post.get("slug") or "")
    top, foot = _chrome(db, brand)
    ko = post.get("kickoff")
    when = (f"{ko.strftime('%A')} {ko.day} {ko.strftime('%B %Y, %H:%M')} UTC"
            if isinstance(ko, datetime) else (post.get("day") or ""))
    if post.get("final"):
        when = ((f"{ko.strftime('%A')} {ko.day} {ko.strftime('%B %Y')}" if isinstance(ko, datetime)
                 else (post.get("day") or "")) + " \u2014 full time")
    heading = "What we said, and what happened" if post.get("final") else "Three forecasts, and why"
    # The tally is stated plainly, win or lose. A forecasting site that only publishes its hits is
    # not publishing a record, and the one thing a stranger cannot check is the thing we most need
    # them to believe.
    tally = ""
    if post.get("final") and post.get("scored_n"):
        tally = (f'<p class="note">{post["came_in"]} of the {post["scored_n"]} forecasts in this post came in. '
                 f'Every forecast we publish is scored and kept, including the ones that were not reached.</p>')
    h, a = post.get("home") or {}, post.get("away") or {}
    base = SS.base_url()

    # A played match shows its score where an upcoming one shows "v". A post about a game that has
    # been played must not present itself as a preview of it.
    mid = f'<div class="sc">{esc(post.get("score") or "")}<small>FT</small></div>' if post.get("final") and post.get("score") else (
        '<div class="sc"><small>FT</small></div>' if post.get("final") else '<div class="v">v</div>')
    fixture = f"""<div class="fx">
  <div class="side">{_crest(h.get('image'), h.get('name') or '')}<span>{esc(h.get('name') or '')}</span></div>
  {mid}
  <div class="side away"><span>{esc(a.get('name') or '')}</span>{_crest(a.get('image'), a.get('name') or '')}</div>
</div>"""

    cards = "".join(_card(it, db) for it in (post.get("items") or []))

    # A missing tier is stated, not hidden. Most days have no Strong forecast at all, and a reader
    # told so learns what the badge means; a reader not told assumes we had nothing to say.
    gap = ""
    miss = [m for m in (post.get("missing") or []) if m in ("Strong", "Solid")]
    if miss:
        # The reader's words, not the stored ones: "No Strong forecast" means nothing to someone who
        # has never seen the old badge.
        words = " or ".join(esc(TIER_WORD.get(m, m).lower()) for m in miss)
        gap = (f'<p class="note">No {words} forecast for this match. That is the ordinary case rather than '
               f'a gap in the data: the badge grades how far tonight sits from a player\'s usual game, and '
               f'most nights sit close to it.</p>')

    link = (f'<p><a href="{esc(base)}/match/{esc(post.get("match_id") or "")}">'
            f'Open the full match on {esc(brand.get("name") or "the app")}</a></p>') if post.get("match_id") else ""

    return f"""<!doctype html>
<html lang="en"><head>
{_head(db, title=post.get('title') or '', desc=post.get('description') or '', url=url, brand=brand)}
{_jsonld(post, brand, url)}
</head><body><div class="wrap">
{top}
<h1>{esc(post.get('title') or '')}</h1>
<p class="kick">{esc(when)}</p>
{fixture}
<p class="lead">{esc(post.get('intro') or '')}</p>
<h2>{heading}</h2>
{tally}
{cards}
{gap}
{_share(post.get('title') or '', url)}
{_cta(db, brand, 'mid')}
<h2>What you get with an account</h2>
{_benefits(db)}
{link}
{_cta(db, brand, 'end')}
{foot}
</div></body></html>"""


def render_index(db, posts: list[dict]) -> str:
    brand = _brand(db)
    base = SS.base_url()
    url = f"{base}/api/blog"
    top, foot = _chrome(db, brand)
    title = f"Match forecasts | {brand.get('name') or 'Forecast Zone'}"
    desc = "Our forecasts for the day's football, each with the reasons behind it."
    if posts:
        rows = "".join(
            f'<li><a href="{esc(post_url(p.get("slug") or ""))}">{esc(p.get("title") or "")}</a>'
            f'<small>{esc(p.get("description") or "")}</small></li>' for p in posts)
        body = f'<ul class="posts">{rows}</ul>'
    else:
        body = '<p class="note">No posts yet. They appear the day of each match.</p>'
    return f"""<!doctype html>
<html lang="en"><head>
{_head(db, title=title, desc=desc, url=url, brand=brand, kind='website')}
</head><body><div class="wrap">
{top}
<h1>Match forecasts</h1>
<p class="lead">{esc(desc)}</p>
{body}
{_cta(db, brand, 'index')}
{foot}
</div></body></html>"""
