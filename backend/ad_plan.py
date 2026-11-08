"""ad_plan.py -- the twenty ads waiting for you when you open the builder (docs/60 section 3).

The owner posts the night before, so the batch is built for TOMORROW's fixtures: a post needs the
evening and the morning to earn its reach. The planner decides WHAT each ad says; the browser still
draws it, because that is where the fonts and the crests are.

What it is actually solving is variety. Twenty ads pulled naively off the feed are twenty forwards
with a shots line, because that is what the feed ranks highest, and a reader scrolling an account
sees the same post twenty times. So the plan spends its slots deliberately:

  * no player twice, and at most two ads per club
  * leagues round-robin, so a smaller league is never crowded out by the richest one
  * markets round-robin across every (scope, stat) we really hold -- shots, on target, tackles,
    corners, cards -- rather than whatever ranks highest
  * templates and sizes rotate, and light and dark alternate
  * the famous players first WITHIN those constraints, because a name a reader knows is what earns
    the click, and fame here is measured, not a list someone has to maintain

Nothing in this module invents a number. A record ad is refused unless its slice has enough scored
forecasts behind it (`ads.record_min_n`), and it is phrased as calibration -- "we said 84%, it
happened 86% of the time" -- because that is the honest shape of the answer (docs/03, queries.py
track_record) and a win rate is not what this product measures.
"""
from __future__ import annotations

import datetime as dt
from collections import defaultdict

import engine_bridge as EB
import queries as Q
import settings_store as S

# Square and vertical only. A landscape ad is for a link preview, not for a feed, and the owner
# posts to feeds and stories. `story` carries Instagram's safe area (see SAFE in the renderer).
SIZES = ("square", "portrait", "story")
DEFAULT_COUNT = 20
MIN_COUNT, MAX_COUNT = 4, 40

# Which template answers which kind of slot. The planner fills slots, not a flat list, so the batch
# always contains the mix the owner asked for rather than whatever the feed happened to rank.
RECIPE = [
    ("card", 5),        # one forecast, whole -- the workhorse
    ("run", 4),         # the ten-game shape, the most recognisable thing we draw
    ("table", 2),       # the strongest tomorrow, one per leading league
    ("fixture", 2),     # the biggest match of the day
    ("teamstat", 2),    # a club's own numbers, for and against
    ("record", 2),      # how we did, by league and by market
    ("curiosity", 2),   # a question whose answer is on the site
    ("cta", 1),         # the ask
]


def _market_words(stat: str) -> str:
    """The plural words for a market, from the one place the rest of the app keeps them."""
    pair = EB.STAT_LABEL.get(stat)
    return (pair[1] if pair else str(stat).replace("_", " ")).capitalize()


def _day_window(day: str, tz_offset_min: int = 0) -> tuple[dt.datetime, dt.datetime]:
    d0 = dt.datetime.fromisoformat(day).replace(tzinfo=dt.timezone.utc) - dt.timedelta(minutes=tz_offset_min)
    return d0, d0 + dt.timedelta(days=1)


def _kicker(d0: dt.datetime, tz_offset_min: int) -> str:
    """The date, not the word "tonight". An ad posted the night before is read the next morning, so
    "tonight" is wrong by the time anyone sees it, and wrong again for every reader in another
    time zone."""
    local = d0 + dt.timedelta(minutes=tz_offset_min)
    return local.strftime("%a %-d %b").upper()


def fame(db, league_iids=None) -> tuple[dict, dict]:
    """How well known a player and a club are, measured rather than listed.

    A hand-kept list of "big clubs" goes stale the first time someone is promoted, and it cannot
    know the owner's leagues. Season volume is the signal that is actually in the data: the players
    with the most goals, assists and shots in a league are the ones a scrolling reader recognises,
    and the clubs that score the most are the big ones nearly everywhere.
    """
    m = {"league_iid": {"$in": list(league_iids)}} if league_iids else {}
    pl: dict = defaultdict(float)
    for r in db.player_match_stats.aggregate([{"$match": m}, {"$group": {
            "_id": "$player_iid", "g": {"$sum": "$goals"}, "a": {"$sum": "$assists"},
            "s": {"$sum": "$shots"}, "mins": {"$sum": "$minutes"}}}]):
        if r["_id"] is None:
            continue
        # Goals and assists carry fame; shots and minutes keep a regular starter who does not score
        # from reading as a nobody.
        pl[r["_id"]] = (r.get("g") or 0) * 4.0 + (r.get("a") or 0) * 2.5 + (r.get("s") or 0) * 0.25 + (r.get("mins") or 0) / 400.0
    tm: dict = defaultdict(float)
    for r in db.team_match_stats.aggregate([{"$match": m}, {"$group": {
            "_id": "$team_iid", "g": {"$sum": "$goals"}, "s": {"$sum": "$shots"}}}]):
        if r["_id"] is None:
            continue
        tm[r["_id"]] = (r.get("g") or 0) * 1.0 + (r.get("s") or 0) * 0.06
    def norm(d):
        hi = max(d.values()) if d else 0.0
        return {k: (v / hi if hi else 0.0) for k, v in d.items()}
    return norm(pl), norm(tm)


def cards_for_day(db, day: str, tz_offset_min: int = 0) -> list[dict]:
    """Every card whose match kicks off on that local day, grouped and decorated the way the feed
    does it, so an ad draws the same object the site draws."""
    d0, d1 = _day_window(day, tz_offset_min)
    q = {**Q.NOT_HIDDEN, "tier": {"$in": ["Strong", "Solid", "Watch"]}, "kickoff": {"$gte": d0, "$lt": d1}}
    fc = list(db.forecasts.find(q, {"_id": 0, "contrib": 0}).limit(4000))
    if not fc:
        return []
    fc = Q.group_cards(fc, float(S.get(db, "engine.feed_max_p")), S.get(db, "engine.feed_group") or "player_market",
                       S.get(db, "engine.market_weights"), S.get(db, "engine.lift_scale"),
                       float(S.get(db, "engine.min_span")), S.get(db, "engine.position_weights"),
                       S.get(db, "engine.lead_rule"))
    return Q._decorate(db, fc)


def next_day_with_fixtures(db, after: str, tz_offset_min: int = 0, within: int = 10) -> str | None:
    """The first local day from `after` onward that has a forecast on it. A batch built for an empty
    Tuesday is twenty ads about nothing, so the screen is told where the football actually is."""
    for i in range(within):
        d = (dt.date.fromisoformat(after) + dt.timedelta(days=i)).isoformat()
        d0, d1 = _day_window(d, tz_offset_min)
        if db.forecasts.count_documents({**Q.NOT_HIDDEN, "kickoff": {"$gte": d0, "$lt": d1}}, limit=1):
            return d
    return None


def record_slices(db, min_n: int) -> list[dict]:
    """How we did, split by league and by market, best first.

    Only slices with `min_n` scored forecasts behind them come back. A 97% from forty forecasts is
    not a finding, and putting one on a public image is the sort of claim this product exists not to
    make. The sample size travels with every slice so the ad can print it.
    """
    out = []
    for r in db.forecast_outcomes.aggregate([
            {"$match": {"player_played": True, "p": {"$gte": 0.6}}},
            {"$group": {"_id": {"l": "$league_iid", "s": "$stat", "sc": "$scope"},
                        "n": {"$sum": 1}, "stated": {"$avg": "$p"}, "actual": {"$avg": {"$cond": ["$reached", 1, 0]}}}},
            {"$match": {"n": {"$gte": int(min_n)}}}]):
        k = r["_id"]
        out.append({"league_iid": k.get("l"), "stat": k.get("s"), "scope": k.get("sc"),
                    "n": r["n"], "stated": r["stated"], "actual": r["actual"]})
    lg = Q._names(db, "leagues", [s["league_iid"] for s in out if s["league_iid"]])
    for s in out:
        info = lg.get(s["league_iid"]) or {}
        s["league_name"] = info.get("name") or ""
        s["league_image"] = info.get("image")
    # Highest first, but a slice we were WRONG about is never an ad: the gap between what we said
    # and what happened has to be small, or the number is luck rather than a record.
    out = [s for s in out if s["actual"] >= 0.6 and abs(s["actual"] - s["stated"]) <= 0.12]
    out.sort(key=lambda s: (-s["actual"], -s["n"]))
    return out


def team_lines(db, cards: list[dict], fame_tm: dict, want: int) -> list[dict]:
    """A club's own numbers, for and against, over its recent matches. The team ads the owner asked
    for are not forecasts: they are the evidence a reader can check."""
    seen, out = set(), []
    for c in sorted(cards, key=lambda c: -fame_tm.get(c.get("team_iid"), 0.0)):
        tid = c.get("team_iid")
        if tid is None or tid in seen or not c.get("team"):
            continue
        rows = list(db.team_match_stats.find({"team_iid": tid}, {"_id": 0}).sort("kickoff", -1).limit(10))
        if len(rows) < 5:
            continue
        stats = []
        for stat, label in (("shots", "Shots"), ("sot", "On target"), ("corners", "Corners"), ("tackles", "Tackles")):
            vals = [r.get(stat) for r in rows if r.get(stat) is not None]
            ag = [r.get(stat + "_against") for r in rows if r.get(stat + "_against") is not None]
            if len(vals) >= 5:
                stats.append({"stat": stat, "label": label, "avg": sum(vals) / len(vals),
                              "against": (sum(ag) / len(ag)) if ag else None})
        if not stats:
            continue
        seen.add(tid)
        out.append({"team": c["team"], "opp": c.get("opp"), "league_name": c.get("league_name"),
                    "games": len(rows), "stats": stats, "fkey": c.get("fkey")})
        if len(out) >= want:
            break
    return out


# Questions whose answer is on the site. Each one is a real thing the product can answer, so the
# curiosity is paid off rather than baited -- `{n}` is filled from the day's own cards.
CURIOUS = [
    ("Which {n} players are we most sure about tomorrow?", "Every one of them with the ten games behind it."),
    ("Who takes a shot in all ten of his last ten?", "The shortest list on the site, and the hardest to argue with."),
    ("Which defenders tackle more than most forwards shoot?", "Pick the position, pick the number, read the answer."),
    ("What do we think happens, and why?", "Every forecast shows its reasons. No number arrives on its own."),
    ("Who is on a run right now?", "A streak that ends the moment it ends. Tomorrow's is up."),
]
CTA = [
    ("See tomorrow's forecasts", "Every number, with the ten games behind it."),
    ("Follow a player, get the forecast", "Pick who you watch. We do the counting."),
    ("Ask it yourself", "Build the question one word at a time, and read the answer."),
]


def plan(db, day: str, tz_offset_min: int = 0, count: int = DEFAULT_COUNT) -> dict:
    """The batch. Returns designs the browser can draw without asking anything else."""
    count = max(MIN_COUNT, min(int(count or DEFAULT_COUNT), MAX_COUNT))
    d0, _ = _day_window(day, tz_offset_min)
    kicker = _kicker(d0, tz_offset_min)
    cards = cards_for_day(db, day, tz_offset_min)
    lgs = {c.get("league_iid") for c in cards if c.get("league_iid")}
    fame_pl, fame_tm = fame(db, lgs or None)
    # league mark, which a forecast carries the id of but not the image
    lmap = Q._names(db, "leagues", list(lgs)) if lgs else {}
    for c in cards:
        c["league_image"] = (lmap.get(c.get("league_iid")) or {}).get("image")
        c["_fame"] = max(fame_pl.get(c.get("player_iid"), 0.0), fame_tm.get(c.get("team_iid"), 0.0) * 0.8)

    ads: list[dict] = []
    used_players: set = set()
    per_club: dict = defaultdict(int)
    per_league: dict = defaultdict(int)
    per_market: dict = defaultdict(int)

    def pick(pool, want_stat=None):
        """The most famous card that keeps the batch varied."""
        best, score = None, -1e9
        for c in pool:
            pid = c.get("player_iid")
            if pid is not None and pid in used_players:
                continue
            if per_club[c.get("team_iid")] >= 2:
                continue
            if want_stat and c.get("stat") != want_stat:
                continue
            s = (c.get("_fame", 0.0) * 2.0 + float(c.get("p") or 0)
                 - per_league[c.get("league_iid")] * 0.45 - per_market[c.get("stat")] * 0.6)
            if s > score:
                best, score = c, s
        if best is not None:
            if best.get("player_iid") is not None:
                used_players.add(best["player_iid"])
            per_club[best.get("team_iid")] += 1
            per_league[best.get("league_iid")] += 1
            per_market[best.get("stat")] += 1
        return best

    def add(template, **kw):
        n = len(ads)
        ads.append({"template": template, "size": SIZES[n % len(SIZES)], "mode": "light" if n % 3 == 1 else "dark",
                    "kicker": kicker, "headline": "", "subhead": "", "cta": "", "finder_q": "", "stat_value": "",
                    "fkeys": [], "accent": "", **kw})

    # every market we really hold a forecast for, so the batch is not all shots
    markets = sorted({c.get("stat") for c in cards if c.get("stat")},
                     key=lambda s: -sum(1 for c in cards if c.get("stat") == s))
    mi = 0
    slots = [(t, n) for t, n in RECIPE]
    # scale the recipe to the count asked for
    total = sum(n for _, n in slots)
    slots = [(t, max(1, round(n * count / total))) for t, n in slots]

    for template, n in slots:
        for _ in range(n):
            if len(ads) >= count:
                break
            if template in ("card", "run"):
                stat = markets[mi % len(markets)] if markets else None
                mi += 1
                c = pick(cards, stat) or pick(cards)
                if not c:
                    continue
                add(template, fkeys=[c["fkey"]],
                    subhead="" if template == "card" else "Each bar is one game. The dashed column is this match.")
            elif template == "table":
                top = sorted(cards, key=lambda c: -(c.get("p") or 0))[:8]
                if len(top) < 3:
                    continue
                add("table", fkeys=[c["fkey"] for c in top],
                    headline="The strongest forecasts tomorrow",
                    subhead=f"{len(cards)} forecasts across {len(lgs)} leagues. Every one scored after the match.")
            elif template == "fixture":
                c = pick(sorted(cards, key=lambda c: -(fame_tm.get(c.get("team_iid"), 0.0) + fame_tm.get(c.get("opp_iid"), 0.0))))
                if not c:
                    continue
                add("fixture", fkeys=[c["fkey"]], headline="", subhead="")
            elif template == "teamstat":
                for t in team_lines(db, cards, fame_tm, 1):
                    add("teamstat", fkeys=[t["fkey"]] if t.get("fkey") else [], team_stat=t,
                        headline=f"{t['team']['name']}, last {t['games']}")
            elif template == "record":
                for s in record_slices(db, int(S.get(db, "ads.record_min_n") or 150))[:1]:
                    add("record", record=s, stat_value=f"{round(s['actual'] * 100)}%",
                        headline=f"{_market_words(s['stat'])} in {s['league_name']}".strip(),
                        subhead=f"We said {round(s['stated'] * 100)}%. It happened {round(s['actual'] * 100)}% of the time, over {s['n']:,} forecasts.")
            elif template == "curiosity":
                qn, sub = CURIOUS[len(ads) % len(CURIOUS)]
                add("curiosity", headline=qn.replace("{n}", str(min(len(cards), 20))), subhead=sub, cta="See the answer")
            elif template == "cta":
                h, sub = CTA[len(ads) % len(CTA)]
                add("cta", headline=h, subhead=sub, cta=h)

    # If a slot could not be filled (no record yet, no team stats), top up with the thing we always
    # have: another forecast. Twenty was asked for; nineteen with a gap is not an answer.
    while len(ads) < count:
        stat = markets[mi % len(markets)] if markets else None
        mi += 1
        c = pick(cards, stat) or pick(cards)
        if not c:
            break
        add("card" if len(ads) % 2 else "run", fkeys=[c["fkey"]])

    return {"day": day, "kicker": kicker, "count": len(ads), "asked": count,
            "cards": cards, "ads": ads,
            "leagues": sorted({c.get("league_name") for c in cards if c.get("league_name")}),
            "markets": markets}
