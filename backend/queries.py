"""queries.py -- every read the web app needs, as plain functions over pymongo.

The FastAPI routes in 06_api_routes_and_queries.md call these. All of them:
  * exclude _id, return plain dicts,
  * read ONLY our own collections (no PitchAPI call can happen from a page view),
  * never return hidden forecasts.
"""
from __future__ import annotations

import re
import math
from datetime import datetime, timedelta, timezone

import settings_store as S
import referees as RF
import flags as FL
# The one map of stat -> (singular, plural). The "most likely" screen lets a reader move the line,
# so it needs the words for rungs the engine did not pick a label for; building a second copy of
# this map in JavaScript is how the two would come to disagree about "1 shot on target".
from engine_bridge import STAT_LABEL, verb_for

# `carrier` rows exist only so the Finder can answer a line the band did not keep (see
# engine_bridge.select_lines). They are not forecasts the product published and must never be
# displayed, scored or combined -- so the exclusion lives in the constant every display query
# already spreads, rather than in each of the seven places that would otherwise have to remember.
NOT_HIDDEN = {"is_current": True, "hidden": {"$ne": True}, "carrier": {"$ne": True}}
# The one query that DOES want them: the ladder lookup. Carriers carry nothing but a ladder.
ANY_STORED = {"is_current": True, "hidden": {"$ne": True}}
TIER_RANK = {"Strong": 0, "Solid": 1, "Watch": 2, None: 3}


_KIND = {"leagues": "league", "teams": "team", "players": "player"}


def _aware(d):
    return d.replace(tzinfo=timezone.utc) if d is not None and d.tzinfo is None else d


def attach_images(db, coll, docs):
    """Give each record an `image`: our own stored picture (a same-origin URL) or null. The page shows initials or a
    shield when it is null. Provider links are used only if `images.use_provider_urls` is on."""
    docs = list(docs)
    kind = _KIND[coll]
    on = bool(S.get(db, "images.enabled"))
    have = {}
    if on and docs:
        have = {m["iid"]: m["sha256"] for m in db.media.find({"kind": kind, "iid": {"$in": [d["iid"] for d in docs]}}, {"iid": 1, "sha256": 1, "_id": 0})}
    fallback = on and bool(S.get(db, "images.use_provider_urls"))
    for d in docs:
        url = d.pop("image_url", None)
        d["image"] = f"/api/media/{kind}/{d['id']}?v={have[d['iid']][:8]}" if d["iid"] in have and d.get("id") else (url if fallback else None)
    if coll == "teams" and docs:
        # A country is drawn as its round flag, not its federation badge (flags.py). `flag` is set
        # only on teams that have played an international competition, so clubs never get one.
        nat = FL.national_iids(db)
        for d in docs:
            code = FL.code_for(d.get("name")) if d["iid"] in nat else None
            if code:
                d["flag"] = code
    return docs


def _names(db, coll, iids):
    rows = db[coll].find({"iid": {"$in": list(set(iids))}}, {"_id": 0, "iid": 1, "id": 1, "name": 1, "image_url": 1, "pos": 1, "team_iid": 1})
    return {d["iid"]: d for d in attach_images(db, coll, rows)}


class BadDay(ValueError):
    """A day string that is not a day. Carried as its own type so a route can answer 400 instead of
    letting a visitor's typo become a 500."""


def parse_day(day: str) -> datetime:
    """The ONE place a `date=` query parameter becomes a datetime.

    `datetime.fromisoformat` raises on anything it does not like, and these routes take `date` as a
    bare required string with no validation -- so /api/fixtures?date=x and /api/live?date=2026-13-45
    were a 500 from an unauthenticated request. A mangled bookmark or a crawler should get a
    sentence, not a stack trace in the error log.
    """
    try:
        return datetime.fromisoformat(str(day)).replace(tzinfo=timezone.utc)
    except (TypeError, ValueError) as e:
        raise BadDay(f"{day!r} is not a date. Use one like 2026-11-09.") from e


# ------------------------------------------------------------------ Today
def fixtures_for_date(db, day: str, tz_offset_min: int = 0, league_iids=None) -> list[dict]:
    """Matches whose LOCAL date is `day`. tz_offset_min = minutes east of UTC (Toronto in winter: -300)."""
    d0 = parse_day(day) - timedelta(minutes=tz_offset_min)
    d1 = d0 + timedelta(days=1)
    lf = [f["match_iid"] for f in db.live_fixtures.find({"kickoff": {"$gte": d0, "$lt": d1}, "match_iid": {"$ne": None}}, {"match_iid": 1})]
    q = {"$or": [{"kickoff": {"$gte": d0, "$lt": d1}}, {"iid": {"$in": lf}}]}      # SportAPI may have moved the kick-off into or out of the day
    if league_iids:
        q["league_iid"] = {"$in": league_iids}
    import sportapi as SP
    ms = [m for m in SP.overlay(db, list(db.matches.find(q, {"_id": 0}))) if m.get("kickoff") and d0 <= _aware(m["kickoff"]) < d1]
    ms.sort(key=lambda m: m["kickoff"])
    teams = _names(db, "teams", [m["home_iid"] for m in ms] + [m["away_iid"] for m in ms])
    probs = {p["match_iid"]: p for p in db.match_probs.find({"match_iid": {"$in": [m["iid"] for m in ms]}, "is_current": True}, {"_id": 0})}
    counts = {r["_id"]: r["n"] for r in db.forecasts.aggregate([
        {"$match": {"match_iid": {"$in": [m["iid"] for m in ms]}, **NOT_HIDDEN, "tier": {"$in": ["Strong", "Solid"]}}},
        {"$group": {"_id": "$match_iid", "n": {"$sum": 1}}}])}
    lgs = _names(db, "leagues", [m["league_iid"] for m in ms])
    best = _best_lines(db, [m["iid"] for m in ms], S.get(db, "engine.market_weights"),
                       S.get(db, "engine.lift_scale"), S.get(db, "engine.position_weights"),
                       settled={m["iid"] for m in ms if m.get("status") == "final"})
    for m in ms:
        m["home"], m["away"] = teams.get(m["home_iid"]), teams.get(m["away_iid"])
        m["league"] = lgs.get(m["league_iid"])
        m["probs"] = probs.get(m["iid"]); m["insight_count"] = counts.get(m["iid"], 0)
        lines = best.get(m["iid"]) or []
        m["best_lines"] = lines
        m["best_line"] = lines[0] if lines else None
    return ms


def _best_lines(db, match_iids: list[int], weights=None, scale: str = "odds", pos_weights=None, limit: int = 3,
                settled: set | None = None) -> dict:
    """The few lines most worth saying out loud in each match (docs/redesign/v2 CRITIQUE section 1).

    The fixture row carried `insight_count`, and a count is not a value: every match has a similar
    number of lines, so "14 insights" never helped a reader choose which fixture to open. This gives
    the row the same thing the feed leads a card with -- the most prominent line -- so the row can
    say what is interesting rather than how much there is.

    Uses `prominence`, so the fixture row and the feed agree about what "best" means. A row that
    disagreed with the page it links to would be worse than no row at all.
    """
    if not match_iids:
        return {}
    rows = list(db.forecasts.find(
        {"match_iid": {"$in": match_iids}, **NOT_HIDDEN, "tier": {"$in": ["Strong", "Solid"]}},
        {"_id": 0, "id": 1, "match_iid": 1, "scope": 1, "stat": 1, "market": 1, "p": 1, "p_usual": 1,
         "is_personal": 1, "span": 1, "player_iid": 1, "team_iid": 1, "edge": 1, "pos": 1, "tier": 1}))
    if not rows:
        return {}
    pl = _names(db, "players", [r["player_iid"] for r in rows if r.get("player_iid")])
    tm = _names(db, "teams", [r["team_iid"] for r in rows if r.get("team_iid")])
    # Once a match is over the row was still showing what we EXPECTED, on the one line where the
    # answer is already known. That throws away the product's own argument at the moment it could
    # be made, so a finished fixture says whether the line it led with actually happened.
    # `actual` travels with `reached` because a verdict without a measurement is the weakest thing
    # this product can print. "5+ corners -- did not" tells a reader we were wrong; "5+ corners --
    # 38% -- got 3" tells them how wrong, which is the whole of calibration and the only frame in
    # which a published miss reads as rigour rather than as failure. The field is already stored
    # (engine_bridge.score_finished) and already read by proof(); this is one more projected key.
    done = {o["forecast_id"]: o
            for o in db.forecast_outcomes.find({"forecast_id": {"$in": [r.get("id") for r in rows if r.get("id")]}},
                                               {"_id": 0, "forecast_id": 1, "reached": 1, "actual": 1})}
    # One line per match was right while the row only PREDICTED: a reader picking a fixture needs one
    # reason, not three. A finished row is a different object -- the answers are known, and showing
    # one of them throws away the other nineteen we were right or wrong about. So a match carries a
    # few, ranked the same way the feed ranks them, and the row decides how many to draw.
    #
    # Never two lines about the same player or club: three Haaland rungs are one fact repeated, and
    # the second and third would push out the two other subjects the match actually has.
    ranked: dict = {}
    for r in rows:
        # The subject, not just its name. _names already resolves the stored picture through
        # attach_images, and this threw it away one line later -- so the fixture row was the only
        # surface in the app that named a player without being able to show him, while Most likely
        # and the combo builder both draw his face from the very same lookup.
        subj = ((pl.get(r["player_iid"]) if r.get("player_iid") else tm.get(r["team_iid"])) or {})
        who = subj.get("name")
        # No outcome row at all means NOT GRADED YET, which the page draws differently from a miss.
        # `reached` must therefore stay None rather than collapsing to False.
        o = done.get(r.get("id"))
        ranked.setdefault(r["match_iid"], []).append((
            prominence(r, weights, scale, pos_weights),
            ("p", r.get("player_iid")) if r.get("player_iid") else ("t", r.get("team_iid")),
            {"who": who, "market": r.get("market"), "p": float(r.get("p") or 0),
             "tier": r.get("tier"),
             # Enough for the row to draw a face and link it. `kind` travels because a club line
             # wears a crest and a player line a round portrait, and the row cannot tell them
             # apart from the name alone.
             "who_kind": "player" if r.get("player_iid") else "team",
             "who_id": subj.get("id"), "who_image": subj.get("image"),
             "reached": None if o is None else bool(o.get("reached")),
             "actual": None if o is None else o.get("actual")}))
    out: dict = {}
    settled = settled or set()
    for iid, items in ranked.items():
        # BEFORE the whistle, prominence: a reader choosing which fixture to open wants the most
        # surprising thing we said, because that is what makes one match worth opening over
        # another. AFTER it, the same rule makes the row grade itself on its own longest shots --
        # a 31% line is SUPPOSED to miss -- so a finished day read as a column of misses that was
        # a selection artefact rather than the engine's record. A settled row leads with the claim
        # we were most confident about, which is the one worth being judged on.
        items.sort(key=(lambda x: -x[2]["p"]) if iid in settled else (lambda x: -x[0]))
        seen, keep = set(), []
        for _score, ent, line in items:
            if ent in seen:
                continue
            seen.add(ent)
            keep.append(line)
            if len(keep) >= limit:
                break
        out[iid] = keep
    return out


def _best_line(db, match_iids: list[int], weights=None, scale: str = "odds", pos_weights=None) -> dict:
    """The single most prominent line per match, kept under its old name for callers that want one."""
    return {k: v[0] for k, v in _best_lines(db, match_iids, weights, scale, pos_weights, limit=1).items() if v}


# ------------------------------------------------------------------ Match
def match_detail(db, match_iid: int) -> dict | None:
    m = db.matches.find_one({"iid": match_iid}, {"_id": 0})
    if not m:
        return None
    import sportapi as SP
    SP.overlay(db, [m])
    teams = _names(db, "teams", [m["home_iid"], m["away_iid"]])
    fc = list(db.forecasts.find({"match_iid": match_iid, **NOT_HIDDEN}, {"_id": 0, "contrib": 0}).sort([("p", -1)]))
    players = _names(db, "players", [f["player_iid"] for f in fc if f.get("player_iid")])
    for f in fc:
        f["player"] = players.get(f.get("player_iid"))
        # The words the card writes its sentence with (docs/redesign/v10 §6). _decorate attaches them
        # to every other page's forecasts; this one runs _usual alone, so its rows and their `markets`
        # went out with no verb and the match page read "Player 1 2+ shots".
        f["noun"] = list(STAT_LABEL.get(f.get("stat"), (f.get("stat"), f.get("stat"))))
        f["verb"] = verb_for(f.get("scope"), f.get("stat"))
    _usual(db, fc)
    # docs/73: after the whistle, say what happened. The forecasts were already scored into
    # `forecast_outcomes` by score_finished, and _recap below already counts them -- but only in
    # aggregate, so every row on a settled match still read as though the game were hours away.
    # `actual` is carried as well as `reached` because "did not happen" and "2 when 3 were needed"
    # are different amounts of information, and we hold the second one.
    for f in fc:
        f["status"] = m.get("status")
    if m.get("status") == "final":
        outs = {o["forecast_id"]: o for o in db.forecast_outcomes.find(
            {"forecast_id": {"$in": [f["id"] for f in fc if f.get("id")]}},
            {"_id": 0, "forecast_id": 1, "reached": 1, "actual": 1, "player_played": 1})}
        for f in fc:
            o = outs.get(f.get("id"))
            if o:
                f["outcome"] = {"reached": bool(o.get("reached")), "actual": o.get("actual"),
                                "played": o.get("player_played") is not False}
    styles = {s["team_iid"]: s for s in db.team_styles.find({"team_iid": {"$in": [m["home_iid"], m["away_iid"]]}}, {"_id": 0}).sort("as_of", 1)}   # newest wins
    lu = list(db.lineups.find({"match_iid": match_iid, "started": True}, {"_id": 0}))
    lp = _names(db, "players", [x["player_iid"] for x in lu])
    for x in lu:
        x["player"] = lp.get(x["player_iid"])
    team_stats, player_stats = _match_stats(db, m)
    rating = {r["player"]["iid"]: r["rating"] for r in player_stats if r.get("player")}
    for x in lu:
        x["rating"] = rating.get(x["player_iid"])
    ev = (db.match_events.find_one({"match_iid": match_iid}, {"_id": 0, "events": 1}) or {}).get("events") or []
    ep = _names(db, "players", [i for e in ev for i in (e.get("player_iid"), e.get("in_iid")) if i])
    for e in ev:
        e["player"], e["player_in"] = ep.get(e.get("player_iid")), ep.get(e.get("in_iid"))
    return {"match": m, "home": teams[m["home_iid"]], "away": teams[m["away_iid"]], "events": ev,
            "probs": db.match_probs.find_one({"match_iid": match_iid, "is_current": True}, {"_id": 0}),
            "forecasts": fc, "cards": group_cards(fc, float(S.get(db, "engine.feed_max_p")), "player", S.get(db, "engine.market_weights"),
                                                  S.get(db, "engine.lift_scale"), float(S.get(db, "engine.min_span")), S.get(db, "engine.position_weights"),
                                                  S.get(db, "engine.lead_rule"), obvious=float(S.get(db, "engine.obvious_ratio"))),
            "styles": styles, "starters": lu,
            "referee": RF.for_match(db, m),
            "predicted": [] if lu else predicted_xi(db, fc, (m["home_iid"], m["away_iid"])),
            "rotation": {c["team_iid"]: {"level": c.get("level", "low"), "why": c.get("why", ""), "rest_days": c.get("rest_days"), "next_gap": c.get("next_gap")}
                         for c in db.match_context.find({"match_iid": match_iid}, {"_id": 0}) if "level" in c},
            "context": {c["team_iid"]: {"form_vs_expected": c.get("form_fp"), "situation": c.get("stakes"), "games_left": c.get("games_left"), "why": c.get("context_why", [])}
                        for c in db.match_context.find({"match_iid": match_iid}, {"_id": 0}) if "form_fp" in c},
            "h2h": h2h(db, m["home_iid"], m["away_iid"], exclude=match_iid),
            "availability": _availability(db, (m["home_iid"], m["away_iid"])),
            "live": m.get("live"), "live_events": _live_events(db, m), "recap": _recap(db, m, ev),
            "team_stats": team_stats, "player_stats": player_stats, "live_stats": _live_stats(db, m),
            "flow": _flow(db, m, ev),
            # Only API-Football names a coach (ingest.save_lineups); None means "do not show".
            "coach": {"home": (m.get("coach") or {}).get("home"), "away": (m.get("coach") or {}).get("away")}}


# What the Stats tab reads off a player row: PLAYER_COLS as stored, plus the provider's rating
# (display-only, outside PLAYER_COLS -- see ingest.write_match). Named here rather than
# importing PLAYER_COLS so a new engine column does not silently become a public table column.
MATCH_PLAYER_COLS = ("minutes", "goals", "assists", "shots", "sot", "xg", "tackles", "saves", "interceptions",
                     "clearances", "fouls_committed", "fouls_won", "passes", "rating")


def _match_stats(db, m):
    """Finished match: both sides' team_match_stats and every player row. (None, []) otherwise.

    A value the provider did not send stays None so the page can print a dash -- a 0 here would be a
    claim we do not hold.
    """
    if m.get("status") != "final":
        return None, []
    import normalize as N
    side_of = {m["home_iid"]: "home", m["away_iid"]: "away"}
    ts = {side_of[r["team_iid"]]: {c: r.get(c) for c in N.TEAM_COLS}
          for r in db.team_match_stats.find({"match_iid": m["iid"]}, {"_id": 0}) if r.get("team_iid") in side_of}
    team_stats = {"home": ts.get("home"), "away": ts.get("away")} if ts else None
    if team_stats:
        # Keeper saves live on the player rows (write_match stamps the side's total as team_saves).
        for side, tid in (("home", m["home_iid"]), ("away", m["away_iid"])):
            if team_stats.get(side) is not None:
                r = db.player_match_stats.find_one({"match_iid": m["iid"], "team_iid": tid, "team_saves": {"$ne": None}},
                                                   {"_id": 0, "team_saves": 1})
                team_stats[side]["saves"] = (r or {}).get("team_saves")
    rows = [r for r in db.player_match_stats.find({"match_iid": m["iid"]}, {"_id": 0}) if r.get("team_iid") in side_of]
    pl = _names(db, "players", [r["player_iid"] for r in rows])
    out = [{"player": pl.get(r["player_iid"]), "side": side_of[r["team_iid"]], "pos": r.get("pos"),
            "started": r.get("started"), **{c: r.get(c) for c in MATCH_PLAYER_COLS}}
           for r in rows if r.get("minutes") is None or r["minutes"] > 0]
    out.sort(key=lambda r: (r["side"] != "home", not r.get("started"), -(r.get("minutes") or 0)))
    return team_stats, out


def _flow(db, m, ev):
    """Momentum and possession by five minutes (match_flow), from the live tick's own snapshots."""
    import match_flow as MF
    sid = (m.get("live") or {}).get("sid")
    if sid is None:
        sid = ((db.live_fixtures.find_one({"match_iid": m["iid"]}, {"sid": 1}) or {}).get("sid"))
    src = ev or db.live_events.find({"fixture_sid": sid}, {"_id": 0, "type": 1, "side": 1, "minute": 1}) if sid is not None else ev
    goals = [{"minute": e.get("minute"), "side": e.get("side")} for e in (src or []) if e.get("type") == "goal"]
    return MF.flow(db, sid, goals)


def _live_stats(db, m):
    """The team statistics the live tick stored for this match (live_af.live_tick), or None.

    TEAM_COLS per side, the same columns `team_stats` carries after full time, so the Stats tab draws
    one set of bars from either. A column the provider did not send stays None. `at` is when the
    tick stored them, so the page can say how old they are. Player rows stay out: the live table
    is not built, and `live_track` reads them from the collection directly.
    """
    sid = (m.get("live") or {}).get("sid")
    if sid is None:
        lf = db.live_fixtures.find_one({"match_iid": m["iid"]}, {"sid": 1})
        sid = (lf or {}).get("sid")
    if sid is None:
        return None
    st = db.live_stats.find_one({"fixture_sid": sid}, {"_id": 0, "teams": 1, "at": 1})
    teams = (st or {}).get("teams") or {}
    import normalize as N
    # TEAM_COLS PLUS SAVES. `_match_stats` adds the side's keeper saves to the finished row (from
    # `team_saves` on the player rows), and `live_af` stores the same figure in the live block -- but
    # `N.TEAM_COLS` does not list `saves`, so mapping over it alone dropped the column here and the
    # Saves row appeared for the first time at the whistle. A row that turns up only at full time
    # reads as a number that changed when all that changed is which document was read.
    cols = (*N.TEAM_COLS, "saves")
    out = {side: {c: (teams.get(side) or {}).get(c) for c in cols} for side in ("home", "away")}
    if not any(v is not None for s in out.values() for v in s.values()):
        return None
    at = st.get("at")
    if hasattr(at, "isoformat"):
        # Mongo hands back naive UTC; without the offset a browser reads it as local time and the
        # "updated n min ago" line is off by the viewer's timezone.
        at = (at if at.tzinfo else at.replace(tzinfo=timezone.utc)).isoformat()
    out["at"] = at
    return out

# The columns the match page shows, in the order a reader expects them. Possession first because it
# frames everything else; the shot columns together; cards last.
def _recap(db, m, ev):
    """Finished match: half-time score (SportAPI, else goal minutes) and how our Strong/Solid forecasts did."""
    if m.get("status") != "final":
        return None
    ht = None
    lf = db.live_fixtures.find_one({"match_iid": m["iid"]}, {"score": 1})
    sc = (lf or {}).get("score") or {}
    if sc.get("ht_home") is not None:
        ht = [sc["ht_home"], sc["ht_away"]]
    elif ev:
        g = [e for e in ev if e.get("type") == "goal" and (e.get("minute") or 99) <= 45]
        ht = [sum(1 for e in g if e.get("side") == "home"), sum(1 for e in g if e.get("side") == "away")]
    ids = [f["id"] for f in db.forecasts.find({"match_iid": m["iid"], "tier": {"$in": ["Strong", "Solid"]}}, {"id": 1})]
    outs = list(db.forecast_outcomes.find({"forecast_id": {"$in": ids}, "player_played": {"$ne": False}}, {"_id": 0, "reached": 1, "tier": 1}))
    return {"ht": ht, "scored": len(outs), "hit": sum(1 for o in outs if o.get("reached")),
            "by_tier": {t: [sum(1 for o in outs if o["tier"] == t and o.get("reached")), sum(1 for o in outs if o["tier"] == t)] for t in ("Strong", "Solid")}}


def _live_events(db, m):
    """Goals, cards and substitutions from SportAPI when the match is followed (docs/23)."""
    sid = (m.get("live") or {}).get("sid")
    if not sid:
        return []
    import sportapi as SP
    return SP.events_for(db, sid)


def _availability(db, teams):
    import availability as AV
    return AV.public_list(db, teams)


# ----------------------------------------------------------- cards (docs/21, docs/46)
def _logit(x: float) -> float:
    x = min(max(float(x), 1e-4), 1 - 1e-4)
    return math.log(x / (1 - x))


def lift(f: dict, scale: str = "odds") -> float:
    """How unusual this line is, on a scale that is fair between markets (docs/48).

    `edge` is p minus what this player or team usually does, in percentage points, and that is the right thing to
    SHOW. It is the wrong thing to RANK by, because how far a line can move depends on where it sits: one that is
    usually 90% cannot gain more than 10 points, one usually 30% has 70 to play with. Measured on our own
    forecasts, median |edge| runs 0.196 for lines usually under 40% against 0.029 for lines usually over 80%. So
    ranking on points quietly promotes whichever markets happen to sit mid-table -- shots on target over shots,
    every time, whatever the market weights say.

    "odds" compares the change in log-odds instead, so "twice as likely as usual" counts the same wherever it
    starts. "points" restores the old behaviour.
    """
    pu = f.get("p_usual")
    if pu is None:
        return max(0.0, float(f.get("edge") or 0.0))
    # docs/52: at an entity's own half-way line a fall is as much a forecast as a rise -- "well short of
    # his normal game against this defence" is worth reading, and a one-sided measure would tier it
    # Strong and then sort it last. Only a personal line is read both ways; without one, a line below
    # usual still has nothing to recommend it.
    both = bool(f.get("is_personal"))
    keep = (lambda d: abs(d)) if both else (lambda d: max(0.0, d))
    if scale == "points":
        return keep(float(f.get("p") or 0.0) - float(pu))
    return keep(_logit(f.get("p") or 0.0) - _logit(pu))


def is_trivial(f: dict, min_span: float) -> bool:
    """Would this rung give nearly the same answer against every opponent in the league? (docs/56)

    Reported, repeatedly and correctly: "PSG 9+ shots 88%" and "Kane 1+ shot 90%" are true statements nobody
    needs, and nobody pays for a statement they can read off the fixture list. What makes them useless is not that
    they are likely -- it is that they are **insensitive**. Measured on the engine's own numbers, Kane's 1+ shot
    rung moves about 4 likelihood points between the leakiest and the meanest defence in the league, while his
    5+ rung moves about 32. A rung that cannot move with the opponent carries no information about THIS fixture,
    whatever its percentage, so it must not lead a card.

    `span` is that movement, in likelihood points, computed in the engine from the league's own spread of
    concession strengths (`_opp_log_spread`). A line whose span is **unknown** (None) is never trivial: that is
    an absence of information, not evidence of insensitivity, and a missing field must never silently hide a card.
    Setting `min_span` to 0 switches the whole gate off.
    """
    if min_span <= 0:
        return False
    sp = f.get("span")
    if sp is None:
        return False
    return abs(float(sp)) < float(min_span)


def is_obvious(f: dict, ratio: float) -> bool:
    """Is this line far below what the player (or team) usually does? (owner, with a screenshot)

    "If Yamal is making 3 shots a game, giving him 1+ shot as a leading card doesn't make any
    sense" -- and the same for a keeper making four saves a game shown "1+ save". The line is true
    and the number is high, and that is exactly why it says nothing: anyone who follows football
    already knows it.

    A line is obvious when the count it asks for is at most `ratio` times his usual count
    (`expected_usual`, his own expectation in an ordinary match). At 0.4 a player averaging 3.9
    shots has 1+ obvious and 2+ not; a player averaging 2 shots keeps 1+ as a real question. Like
    the triviality gate, this is a demotion, not a deletion: the line stays on the ladder, in the
    Finder and available to a combo; it only cannot LEAD a card or take one of the lines a card
    carries while a real question is available. Setting the ratio to 0 switches it off.
    """
    if not ratio or ratio <= 0:
        return False
    u = f.get("expected_usual")
    if u is None or f.get("thr") is None or f.get("stat") == "match_goals":
        return False
    k = int(float(f["thr"]) // 1) + 1
    return k <= float(ratio) * float(u)


def prominence(f: dict, weights: dict | None = None, scale: str = "odds", pos_weights: dict | None = None) -> float:
    """How much this line is worth saying out loud.

    Reported: "mbappe one shot or benfica 7 shots are not that much great insights those are almost given".
    They were leading cards because the lead was picked on raw likelihood, which after docs/44 is always the
    dullest line a player owns. A near-certainty that is also usual carries no information.

    Four things decide it, multiplied, so a line has to have all of them (docs/46):
      * how much the market matters   -- the owner's own order, engine.market_weights;
      * how much it matters FOR HIM   -- engine.position_weights, below;
      * how unusual this line is      -- its lift over what this player or team usually does;
      * how likely it is              -- an unusual line nobody can act on is not an insight either.

    A line with no lift scores 0, so "1+ shot, usually 93%" cannot lead a card while anything else has something
    to say. When nothing in the group has any lift, the caller falls back to likelihood.

    POSITION. Reported with a screenshot: a forward's card led with "1+ tackle" at 54%, with his
    "1+ shot" at 69% collapsed underneath it. Measured across the demo league, 10 of 48 forward
    cards led on tackles, and tackles was 41% of every player line produced. Nothing in this
    function read `pos`, although every forecast carries it.

    The cause was not one bug but a chain. `stake` cannot discriminate between the rungs of a
    personal card -- by construction they all sit near 0.5, so it is flat at about 0.93 -- which
    leaves `lift` deciding alone, and lift has no idea what a market MEANS for the player in front
    of it. engine.market_weights then made it worse by rating tackles 1.3 against shots 1.0: those
    numbers came from the priority table in docs/39, which is a BUILD BACKLOG -- what is live,
    what is not built yet -- and shots is absent from it only because it was already shipped, so
    it fell to the unlisted floor of 1.0. The product's most-wanted player market was weighted
    last by an accident of how a roadmap was read.

    So relevance is its own term. It is kept out of market_weights deliberately: what a market is
    worth at all and what it is worth for a centre-back are different questions, and three tests
    and a measurement script read that key's scope->stat shape.
    """
    w = ((weights or {}).get(f.get("scope")) or {}).get(f.get("stat"), 1.0)
    # `pos` is None on every team and match line, so they are unaffected with no special case.
    rel = ((pos_weights or {}).get(f.get("pos")) or {}).get(f.get("stat"), 1.0)
    p = float(f.get("p") or 0.0)
    # docs/52: once a line is the entity's OWN half-way count, a high p is not a virtue -- it is the
    # message. What should carry weight is how much is actually at stake in the sentence, which is
    # largest where the outcome is open and nil at either end. 4p(1-p) is exactly that, normalised.
    # Without a personal line the old reading still holds: an unusual line nobody can act on is not
    # an insight either.
    stake = 4.0 * p * (1.0 - p) if f.get("is_personal") else p
    return float(w) * float(rel) * lift(f, scale) * stake


# How a card chooses which of its lines to lead with. `prominence` above is one answer; this is the
# switch between it and the other one.
#
# Reported: "lead with better, higher percentages and better forecasts". Both answers are defensible
# and they are answering different questions, which is why this is a setting and not a fix:
#
#   "prominence"  lead with what is most WORTH SAYING. A near-certainty that is also usual carries
#                 no information, so it is demoted however high it reads. This is docs/46 and it was
#                 itself a response to a complaint -- "mbappe one shot is not a great insight".
#   "confident"   lead with the strongest number the card can honestly stand behind.
#   "relevance"   pick the MARKET first, by what it is worth for his position, and only then the
#                 line within it. Asked for directly: "for a player like mbappe, sot and goal come
#                 first, before shots. For a defender, tackles comes first."
#
# Why "relevance" needs its own branch rather than a bigger weight. Measured on the demo league,
# of 117 cards only 11 are a contest the weights can decide: 77 have exactly ONE market available,
# and on 29 more at least one side has zero lift, so prominence is 0 or group_cards falls through
# to raw likelihood -- and in BOTH of those the weights multiply nothing. On the 11 that remain,
# `lift` supplies +118% of the winning margin and the weights -24%, pointing at the runner-up in 7.
# Squaring the weights moves 3 cards; raising them to the fourth power moves 6. A multiplier cannot
# reach a comparison it is absent from, so the market has to be chosen before the lines are scored.
#
# The reason "confident" is not simply a return to ranking on p -- which is what docs/44 did, and
# what produced the Mbappe complaint in the first place -- is that the two guards in group_cards now
# do that work independently of the score. `max_p` keeps a line above engine.feed_max_p from leading
# while any other line can, and is_trivial keeps a rung that reads the same against every opponent
# in the league from leading while any other line can. Mbappe's 1+ shot moves about 4 points across
# the league's defences against 32 for his 5+ rung, so the triviality gate demotes it before this
# function is ever consulted. What is left to choose between is lines that COULD have come out
# differently tonight, and picking the likeliest of those is a different thing from picking the
# likeliest line on the card.
#
# Position weights are kept in both rules -- what a market is worth FOR A CENTRE-BACK is true
# whichever question the lead is answering, and it is the guard that stops a forward's card leading
# on tackles. Market weights are not: see lead_score.
LEAD_RULES = ("prominence", "confident", "relevance")


def market_score(stat: str, scope: str, pos: str | None,
                 weights: dict | None, pos_weights: dict | None) -> float:
    """How much this MARKET is worth for this player, before any line in it is considered.

    `engine.market_weights` x `engine.position_weights`: what the market is worth at all, times
    what it is worth for someone in his position. For a forward that is on-target 1.4 x 1.5 = 2.10
    against shots 1.0 x 1.4 = 1.40; for a defender, tackles 1.3 x 1.5 = 1.95 against shots
    1.0 x 0.6 = 0.60.
    """
    w = ((weights or {}).get(scope) or {}).get(stat, 1.0)
    rel = ((pos_weights or {}).get(pos) or {}).get(stat, 1.0)
    return float(w) * float(rel)


def lead_score(f: dict, rule: str, weights: dict | None = None, scale: str = "odds",
               pos_weights: dict | None = None) -> float:
    if rule == "confident":
        # POSITION weight yes, MARKET weight no, and the difference is the rule's whole meaning.
        # engine.position_weights is a correctness guard -- it is what stops a forward's card
        # leading on tackles -- so it belongs in any rule. engine.market_weights says which market
        # is more INTERESTING, which is the question "prominence" is for; left in here it rates
        # on-target at 1.4 against shots at 1.0 and leads with "1+ on target 78%" over "1+ shot
        # 95%", outvoting seventeen points of likelihood. A rule that does that is not a confidence
        # rule.
        rel = ((pos_weights or {}).get(f.get("pos")) or {}).get(f.get("stat"), 1.0)
        return float(rel) * float(f.get("p") or 0.0)
    return prominence(f, weights, scale, pos_weights)


def _card_key(f: dict, group: str):
    base = (f["match_iid"], f["scope"], f["team_iid"], f.get("player_iid"))
    if group == "line":
        return (*base, f.get("fkey"))
    if group == "player":
        return base
    return (*base, f.get("stat"))                      # player_market: shots and on-target are separate cards


def group_cards(fc: list[dict], max_p: float = 1.0, group: str = "player", weights: dict | None = None, scale: str = "odds",
                min_span: float = 0.0, pos_weights: dict | None = None, rule: str = "prominence",
                obvious: float = 0.0) -> list[dict]:
    """One card per player (or team) per match, per market when `group` is "player_market" (docs/46).

    The line that leads is chosen by `lead_score` above: with engine.lead_rule "prominence" (the
    default) the one with the most to say, with "confident" the strongest number the card can stand
    behind. Both sit behind the same two guards below, which is what makes the second one safe.
    The rest go into `more_lines`, most likely first, so what is near-certain is still one glance away and still
    available to a combo. Lines above `max_p` never lead while another line can (docs/25).

    `min_span` adds the triviality gate (docs/56): a rung that would give nearly the same answer against every
    opponent in the league cannot lead while any other line in the group can. It is a **demotion, not a deletion**
    -- the line keeps its place in `more_lines`, stays in the ladder and stays available to the Finder and to a
    combo. If every line in a group is trivial, the group still produces a card: hiding the group would be worse
    than leading it with a dull line, and an empty feed is not an improvement on a boring one.
    """
    groups: dict = {}
    for f in fc:
        groups.setdefault(_card_key(f, group), []).append(f)
    out = []
    for g in groups.values():
        lead = [f for f in g if f["p"] <= max_p] or g
        # docs/56: prefer rungs that could have come out differently against a different opponent. "or lead"
        # is the floor that keeps a card from vanishing when every rung in it is insensitive.
        lead = [f for f in lead if not is_trivial(f, min_span)] or lead
        # And never lead with a line far below his usual game while a real question is available.
        lead = [f for f in lead if not is_obvious(f, obvious)] or lead
        # docs/60: choose the MARKET first, then the line inside it. Only meaningful when a card
        # holds more than one market, so it is a no-op for group="player_market" and for teams.
        if rule == "relevance":
            pos = next((f.get("pos") for f in lead if f.get("pos")), None)
            top = max({f["stat"] for f in lead},
                      key=lambda st: (market_score(st, lead[0]["scope"], pos, weights, pos_weights), st))
            lead = [f for f in lead if f["stat"] == top] or lead
        # docs/76: the entity's OWN half-way line no longer wins the card automatically.
        #
        # It used to (docs/52), because the badge graded the departure from that player's usual game
        # and the own rung was the only one that question could be asked about. The badge grades the
        # likelihood now, and the own rung sits at about a half by construction -- so letting it lead
        # would put an ungradeable number on the face of every card and leave the feed untiered.
        #
        # The lines are all still here, the own one among them, and `lead_score` picks between them
        # on the configured rule. What the own line was protecting against -- a near-certain line
        # leading the card -- is handled above, per rung and measured: `max_p` and the triviality
        # gate have both already run.
        best = max(lead_score(f, rule, weights, scale, pos_weights) for f in lead)
        # Nothing in this group is saying anything unusual: fall back to the likeliest, as before.
        # Under "confident" the score is already the likelihood, so this never fires -- it is the
        # "prominence" rule's escape hatch for a group where every line has zero lift.
        head = (max(lead, key=lambda f: (lead_score(f, rule, weights, scale, pos_weights), f["p"], f["thr"])) if best > 0
                else max(lead, key=lambda f: (f["p"], f["thr"])))
        card = dict(head)
        card["more_lines"] = sorted(({k: f.get(k) for k in ("fkey", "stat", "thr", "market", "p", "lo", "hi", "tier", "p_usual", "edge", "ladder", "pos", "span", "expected_usual")}
                                     for f in g if f is not head), key=lambda x: (-x["p"], x["stat"], x["thr"]))
        # the best percentage anywhere in the card, so a "show me 90%+" filter can see past the lead line
        card["best_p"] = max(f["p"] for f in g)
        card["markets"] = _markets(g, rule, weights, scale, pos_weights, obvious)
        out.append(card)
    return out


# What the card needs to switch market without asking the server again (docs/77).
#
# `more_lines` was a teaser: enough to list what else this subject holds, not enough to DRAW it. The
# standard card changes market on the card itself, and a market brings its own ten-game strip, its
# own ladder, its own band per rung and its own grade per rung -- none of which `more_lines` carries.
#
# One entry per STAT, not per rung. The rungs are already inside each entry's ladder, so sending a
# row per rung would be three to six times the payload for data the ladder already holds: measured
# on a six-market card, eighteen rows against six.
_MARKET_KEYS = ("id", "fkey", "scope", "stat", "market", "noun", "verb", "thr", "p", "lo", "hi", "tier",
                "tier_note", "p_usual", "edge", "span", "pos", "ladder", "ladder_band", "ladder_tier",
                "run", "streak", "usual_p", "usual_n", "lineup_badge", "reasons", "is_personal",
                "starts_recent", "club_recent", "lineup_why", "addable")


def _markets(g: list[dict], rule: str, weights, scale: str, pos_weights, obvious: float = 0.0) -> list[dict]:
    """One complete forecast per stat: the rung that stat leads with, with everything to redraw the card.
    An obvious rung (is_obvious) leads its market only when the market has nothing else."""
    best: dict = {}
    key = lambda f: (not is_obvious(f, obvious), lead_score(f, rule, weights, scale, pos_weights), f["p"], f["thr"])
    for f in g:
        st = f.get("stat")
        cur = best.get(st)
        if cur is None or key(f) > key(cur):
            best[st] = f
    return sorted(({k: f.get(k) for k in _MARKET_KEYS} for f in best.values()),
                  key=lambda x: (-(x["p"] or 0), x["stat"] or ""))


def lead_stat(fs):
    """The stat with the largest lift over usual leads the card."""
    return max(fs, key=lambda f: (f.get("edge") or 0.0))["stat"]


CONFIDENT = {"Strong": 0, "Solid": 0, "Watch": 1, None: 2}
# "edge" ranks on the same fair scale the cards use, not on raw percentage points (docs/48).
# Each sort takes the forecast AND the tables, because the default one ranks by `prominence`, which
# needs them. v8: "edge" used to rank by raw `lift`, which is market-blind and position-blind -- so a
# centre-back's tackles line with a big departure outranked a striker's shot line, and the feed
# contradicted the card sitting in it. `prominence` already knew tackles is worth 0.5 to a forward
# and 1.5 to a defender (engine.position_weights); it decided which line LEADS a card and was never
# wired to the order the cards come in. That half-fix is what "random markets for a player" was.
FEED_SORTS = {
    "edge": lambda f, w, sc, pw: (CONFIDENT[f["tier"]], -prominence(f, w, sc, pw), -f["p"]),
    "likely": lambda f, w, sc, pw: (TIER_RANK[f["tier"]], -f["p"]),
    "kickoff": lambda f, w, sc, pw: (f["kickoff"], TIER_RANK[f["tier"]], -f["p"]),
}


def h2h(db, a: int, b: int, limit: int = 20, exclude: int | None = None) -> dict:
    """The finished meetings of clubs a and b, newest first, with what they add up to.

    `exclude`: the match being viewed, so a finished match's own result is not counted as its own
    history (the page filtered it out of the list, but the counts above the list still included it).
    `summary` / `insights` come from h2h_summary over the same meetings the list shows; each match row
    also carries its `league` {id, name} so the list can say which competition it was.
    """
    import h2h_summary as HS
    q = {"status": "final", "hg": {"$ne": None}, "$or": [{"home_iid": a, "away_iid": b}, {"home_iid": b, "away_iid": a}]}
    if exclude is not None:
        q["iid"] = {"$ne": exclude}
    ms = list(db.matches.find(q, {"_id": 0}).sort("kickoff", -1).limit(limit))
    ms = [m for m in ms if m.get("hg") is not None and m.get("ag") is not None]
    wa = sum(1 for m in ms if (m["home_iid"] == a and m["hg"] > m["ag"]) or (m["away_iid"] == a and m["ag"] > m["hg"]))
    wb = sum(1 for m in ms if (m["home_iid"] == b and m["hg"] > m["ag"]) or (m["away_iid"] == b and m["ag"] > m["hg"]))
    summary, insights = HS.summarize(db, a, b, ms)
    _with_teams(db, ms)
    lg = {d["iid"]: {"id": d.get("id"), "name": d.get("name")}
          for d in db.leagues.find({"iid": {"$in": list({m.get("league_iid") for m in ms})}}, {"_id": 0, "iid": 1, "id": 1, "name": 1})}
    for m in ms:
        m["league"] = lg.get(m.get("league_iid"))
    return {"a_wins": wa, "b_wins": wb, "draws": len(ms) - wa - wb, "matches": ms, "summary": summary, "insights": insights}


def _with_teams(db, ms: list[dict]) -> list[dict]:
    """Add home / away {id, name, image} to match rows (our database only)."""
    import sportapi as SP
    SP.overlay(db, ms)
    teams = _names(db, "teams", [m["home_iid"] for m in ms] + [m["away_iid"] for m in ms])
    for m in ms:
        m["home"], m["away"] = teams.get(m["home_iid"]), teams.get(m["away_iid"])
    return ms


def _with_opp(db, rows: list[dict]) -> list[dict]:
    opp = _names(db, "teams", [r["opp_iid"] for r in rows if r.get("opp_iid") is not None])
    for r in rows:
        r["opp"] = opp.get(r.get("opp_iid"))
    return rows


def team_form(db, team_iid: int, n: int = 5) -> list[dict]:
    ms = db.matches.find({"status": "final", "$or": [{"home_iid": team_iid}, {"away_iid": team_iid}]}, {"_id": 0}).sort("kickoff", -1).limit(n)
    out = []
    for m in ms:
        home = m["home_iid"] == team_iid
        gf, ga = (m["hg"], m["ag"]) if home else (m["ag"], m["hg"])
        out.append({"match_iid": m["iid"], "match_id": m.get("id"), "kickoff": m["kickoff"], "home": home, "gf": gf, "ga": ga,
                    "opp_iid": m["away_iid"] if home else m["home_iid"],
                    "result": "W" if gf > ga else ("D" if gf == ga else "L")})
    return _with_opp(db, out)


# ----------------------------------------------------------- Insights feed
def insights_feed(db, limit=50, tiers=("Strong", "Solid"), league_iids=None, stat=None, scope=None, now=None, sort=None,
                  player_iids=None, team_iids=None, min_p=None, within_h=None) -> list[dict]:
    """`sort`: "edge" (default, settings engine.feed_sort) | "likely" | "kickoff".

    `player_iids` / `team_iids` narrow the feed to those players or clubs (docs/52). A club filter
    takes its own team lines and the lines of its players, which is what a reader picking a club
    off the list means by it.

    `min_p` keeps only lines at or above that likelihood, and `within_h` only matches kicking off
    within that many hours (docs/63). The "most likely" screen is a different question from this
    feed's usual one -- not "what differs most from usual" but "what is likeliest in the next few
    hours" -- and both of its filters belong in the query rather than in the page, which would
    otherwise be filtering a fixed 200-row pool and silently losing rows past it."""
    now = now or datetime.now(timezone.utc)
    q = {**NOT_HIDDEN, "tier": {"$in": list(tiers)}, "kickoff": {"$gte": now}}
    if within_h:
        q["kickoff"] = {"$gte": now, "$lte": now + timedelta(hours=float(within_h))}
    if min_p is not None:
        q["p"] = {"$gte": float(min_p)}
    if league_iids: q["league_iid"] = {"$in": league_iids}
    if stat: q["stat"] = stat
    if scope: q["scope"] = scope
    if player_iids: q["player_iid"] = {"$in": list(player_iids)}
    if team_iids: q["team_iid"] = {"$in": list(team_iids)}
    fc = list(db.forecasts.find(q, {"_id": 0, "contrib": 0}).limit(3000))
    # The feed admits Strong and Solid only, so the grouping below never sees a player's Watch rungs:
    # a forward averaging 2.7 shots whose only Solid line is "1+ shot 93%" got a card leading with
    # it, the line the owner called pointless. An obvious line (is_obvious) is not a recommendation,
    # so it is not in the feed at all -- it is still on his card's ladder and in the Finder.
    ob = float(S.get(db, "engine.obvious_ratio"))
    fc = [f for f in fc if not is_obvious(f, ob)]
    grp = S.get(db, "engine.feed_group")
    weights, scale = S.get(db, "engine.market_weights"), S.get(db, "engine.lift_scale")
    pos_weights = S.get(db, "engine.position_weights")
    if grp in ("player", "player_market"):
        fc = group_cards(fc, float(S.get(db, "engine.feed_max_p")), grp, weights,
                         scale, float(S.get(db, "engine.min_span")), pos_weights, S.get(db, "engine.lead_rule"), obvious=float(S.get(db, "engine.obvious_ratio")))
    key = FEED_SORTS.get(sort or S.get(db, "engine.feed_sort"), FEED_SORTS["edge"])
    fc.sort(key=lambda f: key(f, weights, scale, pos_weights))
    fc = fc[:limit]
    # This used to repeat _decorate's body inline, which is how the feed came to be the one caller
    # that never got `match_id` -- and how a change to _homes could break `home_iid` in one place
    # and not the other. One decorator, one set of fields.
    return _decorate(db, fc)


# --------------------------------------------------------------- Squad grid
STAT_FIELDS = {"shots", "sot", "tackles", "goals", "assists", "minutes", "interceptions", "clearances", "saves", "fouls_committed", "fouls_won", "xg",
               "yellow_cards", "red_cards", "pen_goals", "match_yellow_cards"}


def squad_grid(db, team_iid: int, stat: str, last_n: int = 10, venue: str | None = None) -> list[dict]:
    """One row per player: the stat in each of the team's last N games, newest first."""
    assert stat in STAT_FIELDS
    match = {"team_iid": team_iid}
    if venue in ("home", "away"):
        match["home"] = venue == "home"
    games = [g["match_iid"] for g in db.team_match_stats.find(match, {"match_iid": 1}).sort("kickoff", -1).limit(last_n)]
    match = {"team_iid": team_iid, "match_iid": {"$in": games}}   # the team's last N matches, not each player's
    pipeline = [{"$match": match}, {"$sort": {"kickoff": -1}},
                {"$group": {"_id": "$player_iid",
                            "games": {"$push": {"match_iid": "$match_iid", "kickoff": "$kickoff", "opp_iid": "$opp_iid",
                                                "v": "$" + stat, "minutes": "$minutes", "started": "$started"}}}},
                {"$project": {"games": {"$slice": ["$games", last_n]}}}]
    rows = list(db.player_match_stats.aggregate(pipeline))
    names = _names(db, "players", [r["_id"] for r in rows])
    _with_opp(db, [g for r in rows for g in r["games"]])
    out = []
    for r in rows:
        games = r["games"]
        vals = [g["v"] for g in games if g["v"] is not None]
        out.append({"player": names.get(r["_id"]), "player_iid": r["_id"], "games": games,
                    "avg": sum(vals) / len(vals) if vals else None, "total": sum(vals)})
    out.sort(key=lambda x: -(x["avg"] or 0))
    return out


def team_totals_grid(db, team_iid: int, stat: str, last_n: int = 10) -> list[dict]:
    rows = list(db.team_match_stats.find({"team_iid": team_iid}, {"_id": 0}).sort("kickoff", -1).limit(last_n))
    return _with_opp(db, [{"match_iid": r["match_iid"], "kickoff": r["kickoff"], "opp_iid": r["opp_iid"], "home": r["home"],
                           "for": r.get(stat), "against": r.get(stat + "_against")} for r in rows])


# ---------------------------------------------------------- Forecast Finder
def finder(db, mode: str, stat: str, threshold: float, last_n: int = 10, league_iids=None, scope="player",
           min_p: float = 0.0, limit: int = 100, now=None, venue: str | None = None, started: bool = False,
           min_minutes: float = 0, positions=None, min_reached: float = 0.0,
           day: str | None = None, tz_offset_min: int = 0) -> list[dict]:
    """mode 'likelihood': rank upcoming forecasts by p.
       mode 'form': in the last N games, how often did the stat reach `threshold` or more. Joined to the next fixture.
       mode 'run':  current run of games in a row reaching the threshold.
       Filters venue ('home'|'away'), started, min_minutes apply to the past games (form, run).
       positions and min_p apply to every mode. min_reached (0 to 1) filters form.
       day ('YYYY-MM-DD', user's local date) + tz_offset_min: only players/teams whose match kicks off that day."""
    now = now or datetime.now(timezone.utc)
    lo_t, hi_t, playing = now, None, None
    if day:
        d0 = parse_day(day) - timedelta(minutes=tz_offset_min)
        lo_t, hi_t = max(d0, now - timedelta(hours=1)) if d0 < now else d0, d0 + timedelta(days=1)
        mq = {"status": "scheduled", "kickoff": {"$gte": d0, "$lt": hi_t}}
        if league_iids: mq["league_iid"] = {"$in": league_iids}
        day_matches = list(db.matches.find(mq, {"_id": 0, "iid": 1, "id": 1, "kickoff": 1, "home_iid": 1, "away_iid": 1}))
        playing = {}
        for m in day_matches:
            playing[m["home_iid"]] = m; playing[m["away_iid"]] = m
    if mode == "likelihood":
        q = {**NOT_HIDDEN, "scope": scope, "stat": stat, "thr": threshold - 0.5, "kickoff": {"$gte": lo_t, **({"$lt": hi_t} if hi_t else {})}, "p": {"$gte": min_p}}
        if league_iids: q["league_iid"] = {"$in": league_iids}
        if positions and scope == "player": q["pos"] = {"$in": list(positions)}
        rows = list(db.forecasts.find(q, {"_id": 0, "contrib": 0}).sort("p", -1).limit(limit))
        return _decorate(db, rows)
    coll, idf = ("player_match_stats", "player_iid") if scope == "player" else ("team_match_stats", "team_iid")
    m = {stat: {"$ne": None}}
    if league_iids: m["league_iid"] = {"$in": league_iids}
    if venue in ("home", "away"): m["home"] = venue == "home"
    if scope == "player":
        if started: m["started"] = True
    # A GAME HE DID NOT PLAY IN IS NOT ONE OF "HIS LAST TEN GAMES".
    #
    # Reported: a player missed one match through injury, kept a perfect run either side of it, and
    # the Finder said his streak was two. ingest.py writes a row for every player the provider
    # returns and an unused substitute comes back with `minutes: 0` -- and the stat is then
    # zero-filled, because a 0 from a player who was on the pitch is a real 0. The window read that
    # row as a game he played and failed, so one absence cut a run of ten down to two.
    #
    # The test is `minutes == 0` and NOT `minutes > 0`, which is the version that looks right and
    # would be a far worse bug: `provider.pitchapi.player_keys.minutes.key` ships unset, so where
    # minutes is unmapped every row holds None and requiring an appearance would empty the Finder
    # for the whole league. Excluding what we know is a non-appearance is safe either way.
        m["minutes"] = {"$gte": min_minutes} if min_minutes else {"$ne": 0}
        if positions: m["pos"] = {"$in": list(positions)}
    # One projected sub-document per game instead of one number. The strip drew ten filled-or-empty
    # squares because that is all this returned: `$push` took the scalar and dropped the minutes,
    # the opponent and the venue that were sitting on the same documents. Same scan, same rows,
    # five more projected fields -- the shape /players/{id}/history already returns, so one
    # component can draw a Finder row and a player page.
    gf = {"match_iid": "$match_iid", "kickoff": "$kickoff", "opp_iid": "$opp_iid",
          "home": "$home", stat: "$" + stat}
    if scope == "player":
        gf.update({"minutes": "$minutes", "pos": "$pos"})
    pipeline = [{"$match": m}, {"$sort": {"kickoff": -1}},
                {"$group": {"_id": "$" + idf, "vals": {"$push": "$" + stat}, "gs": {"$push": gf},
                            "team": {"$first": "$team_iid"}}},
                {"$project": {"vals": {"$slice": ["$vals", last_n]}, "gs": {"$slice": ["$gs", last_n]}, "team": 1}}]
    out = []
    for r in db[coll].aggregate(pipeline):
        vals = r["vals"]
        if len(vals) < min(last_n, 3):
            continue
        reached = sum(1 for v in vals if v >= threshold)
        run = 0
        for v in vals:
            if v >= threshold: run += 1
            else: break
        # "6 of the last 10" is a COUNT, and it was compared as a ratio against however many games
        # the row happened to have: with the floor at three, two hits in three games satisfied
        # "6 of the last 10", and the strip then drew three squares under it. Worse, because
        # min_minutes and started filter rows OUT of the window before this, asking for 60+ minutes
        # made the denominator smaller and the search LOOSER -- measured on the demo league, a
        # stricter filter returned 86 rows where no filter returned 75.
        #
        # The bar is now what the reader asked for: `min_reached` is still a share of the window
        # they named, but it is multiplied by that window, not by what survived.
        need = math.ceil(min_reached * last_n - 1e-9)
        if mode == "form" and reached < need:
            continue
        score = reached / last_n if mode == "form" else run
        if mode == "run" and run == 0:
            continue
        out.append({"id": r["_id"], "team_iid": r["team"], "games": len(vals), "reached": reached, "run": run, "score": score,
                    "hits": [v >= threshold for v in vals], "gs": r.get("gs") or []})
    # A player's club is a property of the PLAYER, not of the games this search happened to count.
    #
    # `team` above is `$first` over his match rows, so it is the club he played those games for. For
    # anyone who has transferred that is his OLD club -- and because everything below keys off it,
    # the row then named the wrong club, looked up THAT club's next fixture, and found no forecast
    # for him in it, because he is not in that squad any more. The missing percentage and the wrong
    # badge were the same bug wearing two faces.
    #
    # `players.team_iid` is the current club and is already maintained carefully: upsert_player
    # guards it with `team_as_of` so an older match ingested later cannot move it back (docs/41).
    # That fix was made for the player record and never reached here.
    if scope == "player" and out:
        cur = _names(db, "players", [o["id"] for o in out])
        for o in out:
            o["player"] = cur.get(o["id"])
            o["hist_team_iid"] = o["team_iid"]
            o["team_iid"] = (o["player"] or {}).get("team_iid") or o["team_iid"]
    # ...and "is he playing today?" has to be asked of the club he is at now, so this filter runs
    # after the correction rather than before it.
    if playing is not None:
        out = [o for o in out if o["team_iid"] in playing]
    # Ties are everywhere -- every player who cleared it every time scores the same -- so without a
    # last key the same search returned a different hundred each time it ran.
    out.sort(key=lambda x: (-x["score"], -x["games"], str(x["id"])))
    out = out[:limit]
    # attach the next fixture and its forecast
    for o in out:
        nxt = playing[o["team_iid"]] if playing is not None else db.matches.find_one(
            {"status": "scheduled", "kickoff": {"$gte": now}, "$or": [{"home_iid": o["team_iid"]}, {"away_iid": o["team_iid"]}]},
            {"_id": 0, "iid": 1, "id": 1, "kickoff": 1, "home_iid": 1, "away_iid": 1}, sort=[("kickoff", 1)])
        o["next_match"] = nxt
        if nxt:
            f = db.forecasts.find_one({"match_iid": nxt["iid"], **NOT_HIDDEN, "scope": scope, "stat": stat, "thr": threshold - 0.5,
                                       **({"player_iid": o["id"]} if scope == "player" else {"team_iid": o["id"]})}, {"_id": 0, "contrib": 0})
            if f is None:
                f = _from_ladder(db, nxt["iid"], scope, stat, threshold - 0.5, o["id"])
            o["forecast"] = f
    # One batched lookup for the opponents the strip draws, after the limit rather than before it.
    opp_ids = {g["opp_iid"] for o in out for g in o["gs"] if g.get("opp_iid")}
    opps = _names(db, "teams", list(opp_ids)) if opp_ids else {}
    for o in out:
        for g in o["gs"]:
            g["opp"] = opps.get(g.get("opp_iid"))
    teams = _names(db, "teams", [o["team_iid"] for o in out])
    for o in out:
        o["team"] = teams.get(o["team_iid"])
    _with_teams(db, [o["next_match"] for o in out if o.get("next_match")])
    return out


USUAL_N = 10


def _usual(db, fc):
    """usual_p = share of the last 10 games (before this match) where the player or team got past this line.

    The same walk also builds `run`: those ten games as the card draws them -- opponent, minutes and
    what they actually did, oldest first. Reported repeatedly, and in the competitive read of the
    counting tools: a percentage with nothing behind it asks to be taken on trust, and the evidence
    for it is already in the rows this function reads. Taking it here costs one extra projected field
    per row and no extra query.

    `minutes` is the half of it a count alone throws away. A shot in 28 minutes is evidence FOR a
    player, and the raw strip reads it as evidence against; carrying minutes lets the card show the
    same ten games per 90 without asking anyone to do the arithmetic.
    """
    stats = {f["stat"] for f in fc}
    if not stats:
        return fc
    proj = {"_id": 0, "kickoff": 1, "minutes": 1, "opp_iid": 1, "home": 1, "pos": 1, **{s: 1 for s in stats}}
    hist = {}
    pids = list({f["player_iid"] for f in fc if f.get("scope") == "player" and f.get("player_iid")})
    tids = list({f["team_iid"] for f in fc if f.get("scope") == "team"})
    if pids:
        for r in db.player_match_stats.find({"player_iid": {"$in": pids}, "minutes": {"$gt": 0}}, {**proj, "player_iid": 1}).sort("kickoff", -1):
            hist.setdefault(("player", r["player_iid"]), []).append(r)
    if tids:
        for r in db.team_match_stats.find({"team_iid": {"$in": tids}}, {**proj, "team_iid": 1}).sort("kickoff", -1):
            hist.setdefault(("team", r["team_iid"]), []).append(r)
    for f in fc:
        key = ("player", f.get("player_iid")) if f.get("scope") == "player" else ("team", f["team_iid"])
        ko = f.get("kickoff")
        ko = ko.replace(tzinfo=None) if ko is not None and getattr(ko, "tzinfo", None) else ko
        past = [r for r in hist.get(key, []) if r.get(f["stat"]) is not None and (ko is None or r["kickoff"].replace(tzinfo=None) < ko)][:USUAL_N]
        vals = [r[f["stat"]] for r in past]
        f["usual_n"] = len(vals)
        f["usual_p"] = round(sum(1 for v in vals if v > f["thr"]) / len(vals), 4) if len(vals) >= 5 else None
        # `vals` is newest first, so the run of leading hits IS the current streak. The counting
        # tools lead with this number, searching every market, line and window length until one of
        # them reads 15/15. We state it second, under a forecast, and never let it choose the line:
        # a streak has no opponent in it, which is exactly what `span` measures and a streak cannot.
        streak = 0
        for v in vals:
            if v <= f["thr"]:
                break
            streak += 1
        f["streak"] = streak
        # oldest first, because the strip is read left to right and ends at tonight
        f["run"] = [{"opp_iid": r.get("opp_iid"), "m": r.get("minutes"), "v": r[f["stat"]],
                     "home": r.get("home"), "pos": r.get("pos")}
                    for r in reversed(past)]
    _run_opponents(db, fc)
    return fc


def _run_opponents(db, fc):
    """Put a name on each game in every `run`, in one lookup for the whole page."""
    ids = {g["opp_iid"] for f in fc for g in f.get("run") or [] if g.get("opp_iid")}
    if not ids:
        return
    names = _names(db, "teams", list(ids))
    for f in fc:
        for g in f.get("run") or []:
            g["opp"] = names.get(g.get("opp_iid"))


def _from_ladder(db, match_iid, scope, stat, thr, ent):
    """The exact line was not kept (outside the likelihood band), but every kept line of that player or team and stat
    carries the whole ladder. Answer from it: `band` says "above" (very likely) or "below" (unlikely). No tier, no id."""
    q = {**ANY_STORED, "match_iid": match_iid, "scope": scope, "stat": stat, "ladder": {"$exists": True},
         **({"player_iid": ent} if scope == "player" else {"team_iid": ent})}
    d = db.forecasts.find_one(q, {"_id": 0, "contrib": 0})
    key = f"{thr:g}"
    if not d or key not in d.get("ladder", {}):
        return None
    p = d["ladder"][key]
    keep = ("match_iid", "league_iid", "kickoff", "scope", "team_iid", "opp_iid", "player_iid", "pos", "stat", "p_play", "lineup_badge", "state")
    f = {k: d.get(k) for k in keep}
    f.update({"id": None, "fkey": None, "thr": float(thr), "p": p, "lo": None, "hi": None, "tier": None, "from_ladder": True,
              "band": "above" if p > 0.5 else "below", "addable": False, "p_display": ("95%+" if p > 0.95 else "under 50%" if p < 0.5 else None)})
    return _decorate(db, [f])[0]


def _decorate(db, fc):
    _usual(db, fc)
    pl = _names(db, "players", [f["player_iid"] for f in fc if f.get("player_iid")])
    tm = _names(db, "teams", [f["team_iid"] for f in fc] + [f["opp_iid"] for f in fc])
    homes = _homes(db, fc)
    lgs = _names(db, "leagues", [f["league_iid"] for f in fc if f.get("league_iid")])
    for f in fc:
        f["player"] = pl.get(f.get("player_iid")); f["team"] = tm.get(f["team_iid"]); f["opp"] = tm.get(f["opp_iid"])
        m = homes.get(f["match_iid"]) or {}
        f["home_iid"] = m.get("home_iid")
        f["match_id"] = m.get("id")
        f["league_name"] = (lgs.get(f.get("league_iid")) or {}).get("name")
        f["league_id"] = (lgs.get(f.get("league_iid")) or {}).get("id")
        f["noun"] = list(STAT_LABEL.get(f.get("stat"), (f.get("stat"), f.get("stat"))))
        # The verb travels with the noun, so the card can write the line as a sentence and rewrite
        # it when the reader changes market (docs/redesign/v10). None where the market cannot be
        # one -- the card falls back to the plain label.
        f["verb"] = verb_for(f.get("scope"), f.get("stat"))
    return fc


def _homes(db, fc) -> dict:
    """match iid -> {home team iid, public match id}, so cards can print home v away and link the fixture.

    The public `id` was never put on a forecast, yet three places read `f.match_id`: the Insights
    "Match page" link (which silently fell back to the internal iid and produced a dead URL), the
    sheet's Share, and the fixture line in SubjectHead. One extra projected field on a lookup the
    page already makes.
    """
    return {m["iid"]: m for m in db.matches.find({"iid": {"$in": list({f["match_iid"] for f in fc})}},
                                                 {"_id": 0, "iid": 1, "home_iid": 1, "id": 1})}


# ------------------------------------------------------------ Leaderboards
def team_first_goal(db, team_iid: int, last_n: int = 20) -> dict:
    """Who scored first in this team's recent finished matches, what happened next, and who scores first most."""
    ms = list(db.matches.find({"$or": [{"home_iid": team_iid}, {"away_iid": team_iid}], "status": "final", "first_goal_side": {"$ne": None}},
                              {"_id": 0, "iid": 1, "id": 1, "home_iid": 1, "away_iid": 1, "hg": 1, "ag": 1, "kickoff": 1, "first_goal_side": 1, "first_scorer_iid": 1})
              .sort("kickoff", -1).limit(last_n))
    out = {"played": len(ms), "scored_first": 0, "conceded_first": 0, "goalless": 0,
           "after_scoring": {"w": 0, "d": 0, "l": 0}, "after_conceding": {"w": 0, "d": 0, "l": 0}, "games": [], "scorers": []}
    cnt = {}
    ev = {d["match_iid"]: d["events"] for d in db.match_events.find({"match_iid": {"$in": [m["iid"] for m in ms]}}, {"match_iid": 1, "events": 1})}
    opp = _names(db, "teams", [m["away_iid"] if m["home_iid"] == team_iid else m["home_iid"] for m in ms])
    for m in ms:
        home = m["home_iid"] == team_iid
        side = "home" if home else "away"
        gf, ga = (m["hg"], m["ag"]) if home else (m["ag"], m["hg"])
        res = "w" if gf > ga else "d" if gf == ga else "l"
        fg = m["first_goal_side"]
        who = "none" if fg == "none" else "us" if fg == side else "them"
        if who == "us":
            out["scored_first"] += 1; out["after_scoring"][res] += 1
            if m.get("first_scorer_iid"): cnt[m["first_scorer_iid"]] = cnt.get(m["first_scorer_iid"], 0) + 1
        elif who == "them":
            out["conceded_first"] += 1; out["after_conceding"][res] += 1
        else:
            out["goalless"] += 1
        g = next((e for e in ev.get(m["iid"], []) if e["type"] == "goal"), None)
        out["games"].append({"match_id": m["id"], "kickoff": m["kickoff"], "home": home, "opp": opp.get(m["away_iid"] if home else m["home_iid"]),
                             "who": who, "minute": g and g["minute"], "score": f"{gf}-{ga}", "result": res, "scorer_iid": m.get("first_scorer_iid") if who == "us" else None})
    pl = _names(db, "players", list(cnt) + [g["scorer_iid"] for g in out["games"] if g["scorer_iid"]])
    for g in out["games"]:
        g["scorer"] = pl.get(g.pop("scorer_iid"))
    out["scorers"] = [{"player": pl.get(p), "n": n} for p, n in sorted(cnt.items(), key=lambda x: -x[1])[:5] if pl.get(p)]
    return out


def referee_leaderboard(db, min_matches: int = 3) -> list[dict]:
    """Every referee across the enabled leagues, cards and penalties per game (weighted by games with card data)."""
    lg = {d["iid"]: {"id": d["id"], "name": d["name"]} for d in db.leagues.find({"enabled": True}, {"iid": 1, "id": 1, "name": 1})}
    agg = {}
    for r in db.referee_stats.find({"league_iid": {"$in": list(lg)}}, {"_id": 0}):
        a = agg.setdefault(r["referee"], {"name": r["referee"], "matches": 0, "y": 0.0, "r": 0.0, "p": 0.0, "hw": 0.0, "leagues": [], "last_match": None})
        a["matches"] += r["matches"]
        a["y"] += (r.get("yellow_pg") or 0) * r["matches"]; a["r"] += (r.get("red_pg") or 0) * r["matches"]; a["p"] += (r.get("pens_pg") or 0) * r["matches"]
        a["hw"] += (r.get("home_win_pct") or 0) * r["matches"]
        a["leagues"].append(lg[r["league_iid"]])
        a["last_match"] = max(filter(None, [a["last_match"], r.get("last_match")]), default=None)
    out = []
    for a in agg.values():
        if a["matches"] < min_matches:
            continue
        n = a["matches"]
        out.append({"name": a["name"], "matches": n, "yellow_pg": a["y"] / n, "red_pg": a["r"] / n, "pens_pg": a["p"] / n,
                    "home_win_pct": a["hw"] / n, "leagues": a["leagues"], "last_match": a["last_match"]})
    return sorted(out, key=lambda x: -x["yellow_pg"])


def referee_detail(db, name: str, limit: int = 60) -> dict | None:
    ms = list(db.matches.find({"referee": name, "status": "final"}, {"_id": 0, "iid": 1, "id": 1, "league_iid": 1, "home_iid": 1, "away_iid": 1,
                                                                       "hg": 1, "ag": 1, "kickoff": 1}).sort("kickoff", -1).limit(limit))
    up = list(db.matches.find({"referee": name, "status": "scheduled"}, {"_id": 0, "id": 1, "league_iid": 1, "home_iid": 1, "away_iid": 1, "kickoff": 1}).sort("kickoff", 1).limit(5))
    if not ms and not up:
        return None
    ev = {d["match_iid"]: d["events"] for d in db.match_events.find({"match_iid": {"$in": [m["iid"] for m in ms]}}, {"match_iid": 1, "events": 1})}
    tm = _names(db, "teams", [t for m in ms + up for t in (m["home_iid"], m["away_iid"])])
    lg = {d["iid"]: {"id": d["id"], "name": d["name"]} for d in db.leagues.find({"iid": {"$in": list({m["league_iid"] for m in ms + up})}}, {"iid": 1, "id": 1, "name": 1})}
    tot = {"matches": len(ms), "with_events": 0, "yellow": 0, "red": 0, "pens": 0, "home_wins": 0, "draws": 0, "away_wins": 0}
    games = []
    for m in ms:
        e = ev.get(m["iid"])
        c = {"yellow": None, "red": None, "pens": None}
        if e is not None:
            tot["with_events"] += 1
            c = {"yellow": sum(x["type"] == "yellow" for x in e), "red": sum(x["type"] == "red" for x in e), "pens": sum(x["type"] == "goal" and x["penalty"] for x in e)}
            for k in c: tot[k] += c[k]
        tot["home_wins" if m["hg"] > m["ag"] else "draws" if m["hg"] == m["ag"] else "away_wins"] += 1
        games.append({"match_id": m["id"], "kickoff": m["kickoff"], "league": lg.get(m["league_iid"]), "home": tm.get(m["home_iid"]), "away": tm.get(m["away_iid"]),
                      "score": f"{m['hg']}-{m['ag']}", **c})
    n = tot["with_events"] or None
    per = {k: (tot[k] / n if n else None) for k in ("yellow", "red", "pens")}
    leagues = [{**r, "league": lg.get(r["league_iid"])} for r in db.referee_stats.find({"referee": name}, {"_id": 0})]
    return {"name": name, "totals": tot, "per_game": per, "leagues": leagues, "games": games,
            "upcoming": [{"match_id": m["id"], "kickoff": m["kickoff"], "league": lg.get(m["league_iid"]), "home": tm.get(m["home_iid"]), "away": tm.get(m["away_iid"])} for m in up]}


def booking_risk(db, league_iid: int, days: int = 8, limit: int = 25) -> dict:
    """Current 'Gets a yellow card' forecasts for the league's next round (matches in the next `days`)."""
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    first = db.matches.find_one({"league_iid": league_iid, "status": "scheduled", "kickoff": {"$gte": now}}, sort=[("kickoff", 1)])
    if not first:
        return {"rows": [], "from": None, "to": None}
    end = first["kickoff"] + timedelta(days=days)
    fc = list(db.forecasts.find({**NOT_HIDDEN, "league_iid": league_iid, "is_current": True, "stat": "yellow_cards", "scope": "player",
                                 "kickoff": {"$gte": now, "$lte": end}}, {"_id": 0}).sort("kickoff", 1))
    seen = set()
    fc = [f for f in fc if not (f["player_iid"] in seen or seen.add(f["player_iid"]))]   # each player's next match only
    fc = sorted(fc, key=lambda f: -f["p"])[:limit]
    _decorate(db, fc)
    ms = {m["iid"]: m for m in db.matches.find({"iid": {"$in": list({f["match_iid"] for f in fc})}}, {"iid": 1, "id": 1, "referee": 1, "home_iid": 1})}
    for f in fc:
        m = ms.get(f["match_iid"], {})
        f["match_id"], f["referee"], f["home_iid"] = m.get("id"), m.get("referee"), m.get("home_iid")
    return {"rows": fc, "from": first["kickoff"], "to": end}


def leaderboard(db, league_iid: int, stat: str, per90: bool = False, min_minutes: int = 450, limit: int = 50) -> list[dict]:
    assert stat in STAT_FIELDS
    rows = list(db.player_match_stats.aggregate([
        {"$match": {"league_iid": league_iid, stat: {"$ne": None}}},
        {"$group": {"_id": "$player_iid", "total": {"$sum": "$" + stat}, "minutes": {"$sum": "$minutes"}, "games": {"$sum": 1},
                    "team": {"$last": "$team_iid"}}},
        {"$match": {"minutes": {"$gte": min_minutes}, "total": {"$gt": 0}}}]))
    for r in rows:
        r["per90"] = r["total"] / r["minutes"] * 90 if r["minutes"] else 0.0
    rows.sort(key=lambda r: -(r["per90"] if per90 else r["total"]))
    rows = rows[:limit]
    names = _names(db, "players", [r["_id"] for r in rows])
    for r in rows: r["player"] = names.get(r["_id"])
    return rows


# -------------------------------------------------------------- Against stats
def against_by_position(db, team_iid: int, stat: str, last_n: int = 10) -> dict:
    """What opponents' players did against this team, by position, over its last N games."""
    games = [g["match_iid"] for g in db.team_match_stats.find({"team_iid": team_iid}, {"match_iid": 1}).sort("kickoff", -1).limit(last_n)]
    rows = list(db.player_match_stats.aggregate([
        {"$match": {"match_iid": {"$in": games}, "opp_iid": team_iid, stat: {"$ne": None}, "pos": {"$ne": None}}},
        {"$group": {"_id": "$pos", "total": {"$sum": "$" + stat}, "player_games": {"$sum": 1}}}]))
    n = max(len(games), 1)
    return {"games": len(games), "by_position": {r["_id"]: {"per_game": r["total"] / n, "per_player_game": r["total"] / r["player_games"]} for r in rows}}


# -------------------------------------------------------------- Track record
def proof(db, limit: int = 12, min_p: float = 0.7, days: int = 10) -> list[dict]:
    """Recent forecasts that were published, scored, and CAME IN -- with what actually happened.

    This is the strongest material the product owns for a landing page, and it costs nothing to
    keep fresh: it is yesterday's work, already graded. A claim a reader can check beats any
    sentence about a method.

    Only lines where the player PLAYED are eligible. A forecast on someone who never came on was
    not right about football, and dressing it as a hit on a page whose whole argument is honesty
    would be the one unforced error available here.
    """
    since = datetime.now(timezone.utc) - timedelta(days=int(days))
    outs = list(db.forecast_outcomes.find(
        {"reached": True, "player_played": True, "p": {"$gte": float(min_p)}, "scored_at": {"$gte": since}},
        {"_id": 0}).sort("scored_at", -1).limit(int(limit) * 6))
    if not outs:
        return []
    fc = {f["id"]: f for f in db.forecasts.find({"id": {"$in": [o["forecast_id"] for o in outs]}},
                                                {"_id": 0, "contrib": 0})}
    rows, seen = [], set()
    for o in outs:
        f = fc.get(o["forecast_id"])
        if not f:
            continue
        key = f.get("player_iid") or ("t", f.get("team_iid"))
        if key in seen:                       # one line per player, so the strip is not one striker six times
            continue
        seen.add(key)
        rows.append({**f, "_actual": o["actual"], "_p": o["p"], "_thr": o["thr"], "_scored_at": o.get("scored_at")})
        if len(rows) >= int(limit):
            break
    _decorate(db, rows)
    # lo/hi, the ten-game run and the position travel too. The waitlist page falls back to the most
    # recent settled line when no fixture is inside its window, and its drawings are built from
    # exactly those fields -- without them the fallback card could be drawn but the curve, the run
    # strip and the range bar beside it could not.
    return [{"fkey": r["fkey"], "market": r["market"], "stat": r["stat"], "scope": r["scope"],
             "player": r.get("player"), 
             "team": r.get("team"), "opp": r.get("opp"), "kickoff": r.get("kickoff"),
             "p": round(float(r["_p"]), 4), "thr": r["_thr"], "actual": r["_actual"],
             "lo": r.get("lo"), "hi": r.get("hi"), "run": r.get("run"), "pos": r.get("pos"),
             "lineup_badge": r.get("lineup_badge"),
             "tier": r.get("tier"), "scored_at": r.get("_scored_at"),
             "league_name": r.get("league_name")} for r in rows]


def track_record(db, league_iid=None, min_n: int = 300, stat=None, scope=None) -> dict:
    q = {"league_iid": league_iid} if league_iid else {}
    if stat:
        q["stat"] = stat
    if scope:
        q["scope"] = scope
    # What this page counts, said once here so the screen can say it too. A line where the player
    # never appeared is EXCLUDED, so the question answered is "when he played, were we right?".
    # tiering.Record earns a tier against the whole chance and scores a non-appearance as a miss,
    # so the two are not the same measurement. Both are fair; the page may not print one and label
    # it with the other, so the count left out travels with the answer.
    rows = list(db.forecast_outcomes.find({**q, "player_played": True},
                                          {"_id": 0, "tier": 1, "p": 1, "reached": 1, "scored_at": 1,
                                           "is_personal": 1, "tier_rule": 1}))
    not_played = db.forecast_outcomes.count_documents({**q, "player_played": False})
    if len(rows) < min_n:
        return {"ready": False, "scored": len(rows), "needed": min_n, "not_played": not_played}
    # THE TIER BREAKDOWN COUNTS ROWS WHOSE TIER MEANS WHAT THE PAGE SAYS IT MEANS (docs/61, docs/76).
    #
    # One rule grades every line now, so a personal line's Solid is the same promise as any other
    # Solid and belongs in the same bucket. What does not belong is a row scored under the engine
    # that graded personal lines on the GAP from the player's usual game: those sit at about 50% by
    # construction and were still badged Solid or Strong, so pooling them with lines that had to
    # clear 80% would publish a figure about neither population.
    #
    # `tier_rule` is written on every row scored since the rule changed (engine_bridge.score_finished).
    # Its absence on a personal row is what marks the old grading, and the only exact marker there
    # is: `lo` is not stored, so the tier cannot be recomputed, and a date cutoff would hard-code a
    # deploy. An ordinary row needs no marker -- it was graded on the number under both engines.
    # This filter empties itself as the old rows age out of engine.keep_days.
    comparable = [r for r in rows if not r.get("is_personal") or r.get("tier_rule") == "likelihood"]
    tiers = {}
    for t in ("Strong", "Solid", "Watch"):
        g = [r for r in comparable if r["tier"] == t]
        if g:
            tiers[t] = {"n": len(g), "stated": sum(r["p"] for r in g) / len(g), "actual": sum(r["reached"] for r in g) / len(g)}
    bins = []
    for lo in (0.5, 0.6, 0.7, 0.8, 0.9):
        g = [r for r in rows if lo <= r["p"] < lo + 0.1]
        if len(g) >= 30:
            bins.append({"from": lo, "to": round(lo + 0.1, 1), "n": len(g), "stated": sum(r["p"] for r in g) / len(g), "actual": sum(r["reached"] for r in g) / len(g)})
    since = min((r["scored_at"] for r in rows if r.get("scored_at")), default=None)
    overall = {"n": len(rows), "stated": sum(r["p"] for r in rows) / len(rows),
               "actual": sum(r["reached"] for r in rows) / len(rows)}
    # The record over the lines the product actually makes a strong statement about.
    #
    # `overall` cannot lead this page, and the reason is not that it is unflattering -- it is that
    # a mean over every band can be right while every band inside it is wrong. Being overconfident
    # at the top and underconfident at the bottom cancels to a two-point gap that reads as healthy.
    # It is also dominated by the mass of low-likelihood lines, where saying 20% and seeing 22% is
    # neither a skill nor a claim anyone acted on.
    #
    # HIGH is the band a reader actually uses: when the product says something is likely, how often
    # was it? It is stated as calibration -- how close we were -- not as a win rate, because "we
    # said 93% and it happened 92% of the time" is the honest shape of a good answer here, and a
    # page that framed it as a score would be inviting the reader to read 92 as a grade.
    hi_p = float(S.get(db, "engine.record_high_p"))
    hg = [r for r in rows if r["p"] >= hi_p]
    high = ({"n": len(hg), "from": hi_p, "stated": sum(r["p"] for r in hg) / len(hg),
             "actual": sum(r["reached"] for r in hg) / len(hg)} if len(hg) >= 30 else None)
    return {"ready": True, "scored": len(rows), "tiers": tiers, "bins": bins, "since": since,
            "overall": overall, "high": high, "not_played": not_played,
            # What the tier figures above are computed over, so the page can say so rather than
            # imply the tiers cover everything we published.
            "tiers_scope": {"counted": len(comparable), "left_out": len(rows) - len(comparable)}}


# --------------------------------------------------------------------- Search
def search(db, q: str, limit: int = 8) -> dict:
    rx = {"$regex": re.escape(q.strip()), "$options": "i"}
    players = attach_images(db, "players", db.players.find({"name": rx}, {"_id": 0, "iid": 1, "id": 1, "name": 1, "image_url": 1, "pos": 1, "team_iid": 1}).limit(limit))
    nxt = {g["_id"]: g for g in db.forecasts.aggregate([
        {"$match": {**NOT_HIDDEN, "scope": "player", "player_iid": {"$in": [p["iid"] for p in players]}, "kickoff": {"$gte": datetime.now(timezone.utc)}}},
        {"$sort": {"kickoff": 1, "p": -1}}, {"$group": {"_id": "$player_iid", "p": {"$first": "$p"}, "market": {"$first": "$market"}, "tier": {"$first": "$tier"}}}])}
    for p in players:
        g = nxt.get(p["iid"])
        p["next"] = {"p": g["p"], "market": g["market"], "tier": g.get("tier")} if g else None
    return {"teams": attach_images(db, "teams", db.teams.find({"name": rx}, {"_id": 0, "iid": 1, "id": 1, "name": 1, "image_url": 1}).limit(limit)),
            "players": players}


# ---------------------------------------------------------------- Referees
def referee_assignments(db, league_iid: int, days: int = 8) -> dict:
    """The league's next round: each fixture with its referee (once named) and that referee's card averages here."""
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    first = db.matches.find_one({"league_iid": league_iid, "status": "scheduled", "kickoff": {"$gte": now}}, sort=[("kickoff", 1)])
    if not first:
        return {"rows": [], "from": None}
    ms = list(db.matches.find({"league_iid": league_iid, "status": "scheduled", "kickoff": {"$gte": now, "$lte": first["kickoff"] + timedelta(days=days)}},
                              {"_id": 0, "id": 1, "home_iid": 1, "away_iid": 1, "kickoff": 1, "referee": 1}).sort("kickoff", 1))
    tm = _names(db, "teams", [t for m in ms for t in (m["home_iid"], m["away_iid"])])
    seen, one = set(), []
    for m in ms:                                  # one round: stop when a club already listed plays again
        if m["home_iid"] in seen or m["away_iid"] in seen:
            break
        seen |= {m["home_iid"], m["away_iid"]}; one.append(m)
    ms = one
    refs = {r["referee"]: r for r in db.referee_stats.find({"league_iid": league_iid, "referee": {"$in": [m["referee"] for m in ms if m.get("referee")]}}, {"_id": 0})}
    avg = list(db.referee_stats.aggregate([{"$match": {"league_iid": league_iid, "yellow_pg": {"$ne": None}}},
                                           {"$group": {"_id": None, "y": {"$avg": "$yellow_pg"}, "p": {"$avg": "$pens_pg"}}}]))
    rows = [{"match_id": m["id"], "kickoff": m["kickoff"], "home": tm.get(m["home_iid"]), "away": tm.get(m["away_iid"]),
             "referee": m.get("referee"), "stats": refs.get(m.get("referee"))} for m in ms]
    return {"rows": rows, "from": first["kickoff"], "league_avg": {"yellow_pg": avg[0]["y"], "pens_pg": avg[0]["p"]} if avg else None}


def referee_table(db, league_iid: int) -> list[dict]:
    """Needs ingest.match_extra_detail on (referee name) and match_extra_events (cards)."""
    return list(db.referee_stats.find({"league_iid": league_iid}, {"_id": 0}).sort("matches", -1))


# ------------------------------------------------------------ id helpers
def iid_of(db, coll: str, public_id: str) -> int | None:
    """URLs carry the uuid `id`. The engine tables use the integer `iid`."""
    d = db[coll].find_one({"id": public_id}, {"iid": 1})
    return d["iid"] if d else None


# ------------------------------------------------------------ Player page
def player_history(db, player_iid: int, last_n: int = 20, venue: str | None = None, started: bool = False,
                   min_minutes: float = 0, thresholds=(1, 2, 3, 4, 5)) -> dict:
    """Newest first. `reached[stat][t]` = games (of those shown) with the stat t or more."""
    m = {"player_iid": player_iid}
    if venue in ("home", "away"): m["home"] = venue == "home"
    if started: m["started"] = True
    # The same rule as the Finder's window, for the same reason: the ten-game strip on the player
    # page drew a 0 for a match he was not involved in. See finder().
    m["minutes"] = {"$gte": min_minutes} if min_minutes else {"$ne": 0}
    rows = list(db.player_match_stats.find(m, {"_id": 0}).sort("kickoff", -1).limit(last_n))
    opp = _names(db, "teams", [r["opp_iid"] for r in rows])
    reached = {}
    for stat in ("shots", "sot", "tackles", "goals", "assists"):
        vals = [r[stat] for r in rows if r.get(stat) is not None]
        reached[stat] = {str(t): sum(1 for v in vals if v >= t) for t in thresholds}
        reached[stat]["games"] = len(vals)
    for r in rows: r["opp"] = opp.get(r["opp_iid"])
    sw = _names(db, "players", [i for r in rows for i in (r.get("replaced_iid"), r.get("replaced_by_iid")) if i])
    for r in rows:
        r["replaced"], r["replaced_by"] = sw.get(r.get("replaced_iid")), sw.get(r.get("replaced_by_iid"))
    return {"games": rows, "reached": reached}


LINE_X = {"GK": 0.03, "DEF": 0.28, "MID": 0.58, "FWD": 0.88}


def predicted_xi(db, fc, team_iids) -> list[dict]:
    """Before lineups arrive: each side's 11 most likely starters (1 keeper + 10) from the forecasts' chance to play.
    The engine makes no keeper forecasts, so the keeper is the club's most-started goalkeeper in its last 10 games."""
    out = []
    for tid in team_iids:
        best = {}
        for f in fc:
            if f.get("scope") == "player" and f["team_iid"] == tid and f.get("p_play") is not None and f.get("player"):
                if f["p_play"] > best.get(f["player_iid"], {}).get("p_play", -1):
                    best[f["player_iid"]] = f
        ranked = sorted(best.values(), key=lambda f: -f["p_play"])
        gk = [f for f in ranked if f.get("pos") == "GK"][:1]
        if not gk and ranked:
            recent = list(db.player_match_stats.find({"team_iid": tid, "pos": "GK", "started": True}, {"_id": 0, "player_iid": 1}).sort("kickoff", -1).limit(10))
            if recent:
                top = max({r["player_iid"] for r in recent}, key=lambda i: sum(1 for r in recent if r["player_iid"] == i))
                p = _names(db, "players", [top]).get(top)
                if p:
                    gk = [{"player_iid": top, "player": p, "pos": "GK", "p_play": sum(1 for r in recent if r["player_iid"] == top) / len(recent)}]
        xi = gk + [f for f in ranked if f.get("pos") != "GK"][:11 - len(gk)]
        lines: dict = {}
        for f in xi:
            lines.setdefault(f.get("pos") if f.get("pos") in LINE_X else "MID", []).append(f)
        for pos, fs in lines.items():
            for i, f in enumerate(fs):
                out.append({"team_iid": tid, "player_iid": f["player_iid"], "player": f["player"], "pos": pos, "p_play": f["p_play"],
                            "pitch_x": LINE_X[pos], "pitch_y": (i + 1) / (len(fs) + 1), "predicted": True})
    return out


def team_history(db, team_iid: int, stat: str, last_n: int = 10, venue: str = "") -> dict:
    """Last `last_n` games for one stat, newest first.

    `venue` ("home" or "away") is the club's half of the player Quick view's own filter. Without it
    the Venue control on a club's Quick view was a lie -- and "only when they are at home" is the
    most-asked question a club line has, because a club's corner and shot counts swing with venue
    more than with anything else we hold.
    """
    q: dict = {"team_iid": team_iid, stat: {"$ne": None}}
    if venue in ("home", "away"):
        q["home"] = (venue == "home")
    rows = list(db.team_match_stats.find(q, {"_id": 0, "kickoff": 1, "opp_iid": 1, "home": 1, stat: 1}).sort("kickoff", -1).limit(last_n))
    opp = _names(db, "teams", [r["opp_iid"] for r in rows])
    return {"games": [{**r, "opp": opp.get(r["opp_iid"])} for r in rows]}


RANK_STATS = ("shots", "sot", "tackles", "goals", "assists")


def _season_start(db, league_iid):
    lg = db.leagues.find_one({"iid": league_iid}, {"current_season": 1}) or {}
    m = db.matches.find_one({"league_iid": league_iid, "season": lg.get("current_season")}, {"kickoff": 1}, sort=[("kickoff", 1)])
    return m["kickoff"] if m else None


def player_ranks(db, player_iid: int, min_minutes: int = 270) -> dict:
    """Per-90 rank in the player's league this season for the main stats, e.g. 3rd of 61 for shots."""
    last = db.player_match_stats.find_one({"player_iid": player_iid}, {"league_iid": 1}, sort=[("kickoff", -1)])
    if not last:
        return {"ranks": []}
    lg = last["league_iid"]
    q = {"league_iid": lg}
    start = _season_start(db, lg)
    if start:
        q["kickoff"] = {"$gte": start}
    rows = list(db.player_match_stats.aggregate([{"$match": q}, {"$group": {"_id": "$player_iid", "minutes": {"$sum": {"$ifNull": ["$minutes", 0]}},
                                                                              **{s: {"$sum": {"$ifNull": [f"${s}", 0]}} for s in RANK_STATS}}},
                                                 {"$match": {"minutes": {"$gte": min_minutes}}}]))
    me = next((r for r in rows if r["_id"] == player_iid), None)
    if not me:
        return {"ranks": [], "min_minutes": min_minutes}
    out = []
    for s in RANK_STATS:
        per = lambda r: r[s] * 90 / r["minutes"]   # noqa: E731
        mine = per(me)
        if mine <= 0:
            continue
        out.append({"stat": s, "rank": 1 + sum(1 for r in rows if per(r) > mine), "of": len(rows), "per90": round(mine, 2)})
    name = (db.leagues.find_one({"iid": lg}, {"name": 1}) or {}).get("name")
    return {"league": name, "ranks": out, "min_minutes": min_minutes}


def match_days(db, start: datetime, days: int, tz_offset_min: int = 0) -> dict:
    """Which local days (YYYY-MM-DD) in the window have matches, and which leagues play on each one.

    `days` is the list of days with at least one match. `leagues` maps a day to the leagues playing that day,
    most matches first, each with its crest, so the date strip can show whose games they are (docs/24)."""
    win = {"kickoff": {"$gte": start, "$lt": start + timedelta(days=days)}}
    shift = timedelta(minutes=tz_offset_min)
    out: dict = {}
    import sportapi as SP
    # A called-off fixture puts no crest on the date strip. Every spelling the provider uses counts, not the two
    # words that were named here (docs/42).
    for coll, extra in ((db.matches, {}), (db.live_fixtures, {"status": {"$nin": sorted(SP.DEAD)}})):
        for r in coll.find({**win, **extra}, {"_id": 0, "kickoff": 1, "league_iid": 1, "match_iid": 1, "iid": 1}):
            day = (_aware(r["kickoff"]) + shift).strftime("%Y-%m-%d")
            d = out.setdefault(day, {})
            lg = r.get("league_iid")
            if lg is not None:
                # a SportAPI row and our own row for the same match must not count twice
                key = r.get("match_iid") or r.get("iid")
                d.setdefault(lg, set()).add(key)
    names = _names(db, "leagues", [lg for d in out.values() for lg in d])
    leagues = {}
    for day, d in out.items():
        rows = sorted(((len(ids), lg) for lg, ids in d.items()), key=lambda x: (-x[0], x[1]))
        leagues[day] = [{**{k: v for k, v in (names.get(lg) or {}).items() if k in ("id", "name", "image")}, "matches": n}
                        for n, lg in rows if names.get(lg)]
    return {"days": sorted(out), "leagues": leagues}


def squad_season(db, team_iid: int) -> dict:
    """One card per player: this season's apps, starts, minutes and main totals for this club."""
    t = db.teams.find_one({"iid": team_iid}, {"league_iid": 1}) or {}
    last = db.team_match_stats.find_one({"team_iid": team_iid}, {"league_iid": 1}, sort=[("kickoff", -1)]) or {}
    lg = t.get("league_iid") or last.get("league_iid")
    q = {"team_iid": team_iid}
    start = _season_start(db, lg) if lg else None
    if start:
        q["kickoff"] = {"$gte": start}
    keys = ("goals", "assists", "shots", "sot", "tackles", "yellow_cards")
    rows = list(db.player_match_stats.aggregate([{"$match": q}, {"$sort": {"kickoff": 1}}, {"$group": {"_id": "$player_iid", "apps": {"$sum": {"$cond": [{"$gt": ["$minutes", 0]}, 1, 0]}},
                                                                              "starts": {"$sum": {"$cond": ["$started", 1, 0]}}, "minutes": {"$sum": {"$ifNull": ["$minutes", 0]}},
                                                                              "pos": {"$last": "$pos"}, **{k: {"$sum": {"$ifNull": [f"${k}", 0]}} for k in keys}}},
                                                 {"$match": {"apps": {"$gt": 0}}}, {"$sort": {"minutes": -1}}]))
    names = _names(db, "players", [r["_id"] for r in rows])
    order = {"GK": 0, "DEF": 1, "MID": 2, "FWD": 3}
    out = [{**{k: v for k, v in r.items() if k != "_id"}, "player": names[r["_id"]]} for r in rows if r["_id"] in names]
    out.sort(key=lambda r: (order.get(r.get("pos"), 4), -r["minutes"]))
    return {"since": start, "players": out}


def player_detail(db, player_iid: int, now=None) -> dict | None:
    now = now or datetime.now(timezone.utc)
    p = db.players.find_one({"iid": player_iid}, {"_id": 0})
    if not p: return None
    team = db.teams.find_one({"iid": p["team_iid"]}, {"_id": 0})
    nxt = db.matches.find_one({"status": "scheduled", "kickoff": {"$gte": now},
                               "$or": [{"home_iid": p["team_iid"]}, {"away_iid": p["team_iid"]}]}, {"_id": 0}, sort=[("kickoff", 1)])
    # only the lines for the match the page calls "next": finished matches keep is_current rows for a while (docs/36 H8)
    fc = list(db.forecasts.find({"player_iid": player_iid, "match_iid": nxt["iid"], **NOT_HIDDEN}, {"_id": 0, "contrib": 0}).sort("p", -1)) if nxt else []
    # _decorate runs _usual and also attaches team, opp and home_iid. Without those the page's own
    # cards had no baseline and no run, and the head could not say whether the fixture is home or
    # away -- the same gap team_detail had. The card has to be the same object on every screen.
    _decorate(db, fc)
    p = attach_images(db, "players", [p])[0]
    team = attach_images(db, "teams", [team])[0] if team else None
    if nxt:
        _with_teams(db, [nxt])
    return {"player": p, "team": team, "next_match": nxt,
            "forecasts": fc, "cards": group_cards(fc, float(S.get(db, "engine.feed_max_p")), "player", S.get(db, "engine.market_weights"),
                                                  S.get(db, "engine.lift_scale"), float(S.get(db, "engine.min_span")), S.get(db, "engine.position_weights"),
                                                  S.get(db, "engine.lead_rule"), obvious=float(S.get(db, "engine.obvious_ratio")))}


# -------------------------------------------------------------- Team page
def team_detail(db, team_iid: int, now=None) -> dict | None:
    now = now or datetime.now(timezone.utc)
    t = db.teams.find_one({"iid": team_iid}, {"_id": 0})
    if not t: return None
    style = db.team_styles.find_one({"team_iid": team_iid}, {"_id": 0}, sort=[("as_of", -1)])
    nxt = list(db.matches.find({"status": "scheduled", "kickoff": {"$gte": now},
                                "$or": [{"home_iid": team_iid}, {"away_iid": team_iid}]}, {"_id": 0}).sort("kickoff", 1).limit(5))
    t = attach_images(db, "teams", [t])[0]
    lg = _names(db, "leagues", [t["league_iid"]]).get(t.get("league_iid")) if t.get("league_iid") is not None else None
    # The club page could not answer the question a reader arrives with. player_detail has returned
    # the next match's lines since it was written; team_detail returned the squad, the season totals
    # and the style, and no forecast anywhere -- so following a club card led to a page that could
    # not say what we expect of that club. Same shape as player_detail, so one card component and
    # one set of fields serve both.
    fc = list(db.forecasts.find({"team_iid": team_iid, "scope": "team", "match_iid": nxt[0]["iid"], **NOT_HIDDEN},
                                {"_id": 0, "contrib": 0}).sort("p", -1)) if nxt else []
    # _decorate runs _usual and also attaches team, opp and home_iid -- without those the shared
    # card cannot name the club or the opponent and renders a blank subtitle, the same fault the
    # match page's Forecasts tab had.
    _decorate(db, fc)
    cards = group_cards(fc, float(S.get(db, "engine.feed_max_p")), "team", S.get(db, "engine.market_weights"),
                        S.get(db, "engine.lift_scale"), float(S.get(db, "engine.min_span")), S.get(db, "engine.position_weights"),
                        S.get(db, "engine.lead_rule"), obvious=float(S.get(db, "engine.obvious_ratio")))
    nxt = _with_teams(db, nxt)
    # The same MatchRow draws a win/draw/loss bar and a named line on the league page and two bare
    # club names here, because those two fields were never attached to this fixture list.
    probs = {x["match_iid"]: x for x in db.match_probs.find({"match_iid": {"$in": [m["iid"] for m in nxt]}, "is_current": True}, {"_id": 0})}
    best = _best_line(db, [m["iid"] for m in nxt], S.get(db, "engine.market_weights"),
                      S.get(db, "engine.lift_scale"), S.get(db, "engine.position_weights"))
    for m in nxt:
        m["probs"] = probs.get(m["iid"])
        m["best_line"] = best.get(m["iid"])
    return {"team": t, "league": lg, "style": style, "next": nxt, "form": team_form(db, team_iid, 5),
            "forecasts": fc, "cards": cards}


# ------------------------------------------------------------ League page
def league_matches(db, league_iid: int, status: str = "scheduled", limit: int = 50, now=None) -> list[dict]:
    now = now or datetime.now(timezone.utc)
    q = {"league_iid": league_iid, "status": status}
    q["kickoff"] = {"$gte": now} if status == "scheduled" else {"$lt": now}
    ms = list(db.matches.find(q, {"_id": 0}).sort("kickoff", 1 if status == "scheduled" else -1).limit(limit))
    ms = _with_teams(db, ms)
    # CRITIQUE section 1: the same fixture was rendered two ways in two places -- a result bar and
    # the best line on Today, a bare row of two club names on the league page -- and the weaker one
    # was on the page a reader reaches when they want to know about a league. The league's rows now
    # carry the same fields, so one component can render both and they cannot drift apart again.
    iids = [m["iid"] for m in ms]
    probs = {p["match_iid"]: p for p in db.match_probs.find({"match_iid": {"$in": iids}, "is_current": True}, {"_id": 0})}
    counts = {r["_id"]: r["n"] for r in db.forecasts.aggregate([
        {"$match": {"match_iid": {"$in": iids}, **NOT_HIDDEN, "tier": {"$in": ["Strong", "Solid"]}}},
        {"$group": {"_id": "$match_iid", "n": {"$sum": 1}}}])}
    best = _best_line(db, iids, S.get(db, "engine.market_weights"),
                      S.get(db, "engine.lift_scale"), S.get(db, "engine.position_weights"))
    for m in ms:
        m["probs"] = probs.get(m["iid"])
        m["insight_count"] = counts.get(m["iid"], 0)
        m["best_line"] = best.get(m["iid"])
    return ms
