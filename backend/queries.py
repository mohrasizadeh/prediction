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

NOT_HIDDEN = {"is_current": True, "hidden": {"$ne": True}}
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
    return docs


def _names(db, coll, iids):
    rows = db[coll].find({"iid": {"$in": list(set(iids))}}, {"_id": 0, "iid": 1, "id": 1, "name": 1, "image_url": 1, "pos": 1, "team_iid": 1})
    return {d["iid"]: d for d in attach_images(db, coll, rows)}


# ------------------------------------------------------------------ Today
def fixtures_for_date(db, day: str, tz_offset_min: int = 0, league_iids=None) -> list[dict]:
    """Matches whose LOCAL date is `day`. tz_offset_min = minutes east of UTC (Toronto in winter: -300)."""
    d0 = datetime.fromisoformat(day).replace(tzinfo=timezone.utc) - timedelta(minutes=tz_offset_min)
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
    best = _best_line(db, [m["iid"] for m in ms])
    for m in ms:
        m["home"], m["away"] = teams.get(m["home_iid"]), teams.get(m["away_iid"])
        m["league"] = lgs.get(m["league_iid"])
        m["probs"] = probs.get(m["iid"]); m["insight_count"] = counts.get(m["iid"], 0)
        m["best_line"] = best.get(m["iid"])
    return ms


def _best_line(db, match_iids: list[int]) -> dict:
    """The single line most worth saying out loud in each match (docs/redesign/v2 CRITIQUE section 1).

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
         "is_personal": 1, "span": 1, "player_iid": 1, "team_iid": 1, "edge": 1}))
    if not rows:
        return {}
    pl = _names(db, "players", [r["player_iid"] for r in rows if r.get("player_iid")])
    tm = _names(db, "teams", [r["team_iid"] for r in rows if r.get("team_iid")])
    # Once a match is over the row was still showing what we EXPECTED, on the one line where the
    # answer is already known. That throws away the product's own argument at the moment it could
    # be made, so a finished fixture says whether the line it led with actually happened.
    done = {o["forecast_id"]: bool(o.get("reached"))
            for o in db.forecast_outcomes.find({"forecast_id": {"$in": [r.get("id") for r in rows if r.get("id")]}},
                                               {"_id": 0, "forecast_id": 1, "reached": 1})}
    out: dict = {}
    for r in rows:
        cur = out.get(r["match_iid"])
        if cur is None or prominence(r) > cur[0]:
            who = (pl.get(r["player_iid"]) or {}).get("name") if r.get("player_iid") else (tm.get(r["team_iid"]) or {}).get("name")
            out[r["match_iid"]] = (prominence(r), {"who": who, "market": r.get("market"),
                                                    "p": float(r.get("p") or 0),
                                                    "reached": done.get(r.get("id"))})
    return {k: v[1] for k, v in out.items()}


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
    _usual(db, fc)
    styles = {s["team_iid"]: s for s in db.team_styles.find({"team_iid": {"$in": [m["home_iid"], m["away_iid"]]}}, {"_id": 0}).sort("as_of", 1)}   # newest wins
    lu = list(db.lineups.find({"match_iid": match_iid, "started": True}, {"_id": 0}))
    lp = _names(db, "players", [x["player_iid"] for x in lu])
    for x in lu:
        x["player"] = lp.get(x["player_iid"])
    ev = (db.match_events.find_one({"match_iid": match_iid}, {"_id": 0, "events": 1}) or {}).get("events") or []
    ep = _names(db, "players", [i for e in ev for i in (e.get("player_iid"), e.get("in_iid")) if i])
    for e in ev:
        e["player"], e["player_in"] = ep.get(e.get("player_iid")), ep.get(e.get("in_iid"))
    return {"match": m, "home": teams[m["home_iid"]], "away": teams[m["away_iid"]], "events": ev,
            "probs": db.match_probs.find_one({"match_iid": match_iid, "is_current": True}, {"_id": 0}),
            "forecasts": fc, "cards": group_cards(fc, float(S.get(db, "engine.feed_max_p")), "player", S.get(db, "engine.market_weights"),
                                                  S.get(db, "engine.lift_scale"), float(S.get(db, "engine.min_span"))),
            "styles": styles, "starters": lu,
            "referee": RF.for_match(db, m),
            "predicted": [] if lu else predicted_xi(db, fc, (m["home_iid"], m["away_iid"])),
            "rotation": {c["team_iid"]: {"level": c.get("level", "low"), "why": c.get("why", ""), "rest_days": c.get("rest_days"), "next_gap": c.get("next_gap")}
                         for c in db.match_context.find({"match_iid": match_iid}, {"_id": 0}) if "level" in c},
            "context": {c["team_iid"]: {"form_vs_expected": c.get("form_fp"), "situation": c.get("stakes"), "games_left": c.get("games_left"), "why": c.get("context_why", [])}
                        for c in db.match_context.find({"match_iid": match_iid}, {"_id": 0}) if "form_fp" in c},
            "h2h": h2h(db, m["home_iid"], m["away_iid"]),
            "availability": _availability(db, (m["home_iid"], m["away_iid"])),
            "live": m.get("live"), "live_events": _live_events(db, m), "recap": _recap(db, m, ev)}


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


def prominence(f: dict, weights: dict | None = None, scale: str = "odds") -> float:
    """How much this line is worth saying out loud.

    Reported: "mbappe one shot or benfica 7 shots are not that much great insights those are almost given".
    They were leading cards because the lead was picked on raw likelihood, which after docs/44 is always the
    dullest line a player owns. A near-certainty that is also usual carries no information.

    Three things decide it, multiplied, so a line has to have all three (docs/46):
      * how much the market matters   -- the owner's own order, engine.market_weights;
      * how unusual this line is      -- its lift over what this player or team usually does;
      * how likely it is              -- an unusual line nobody can act on is not an insight either.

    A line with no lift scores 0 on the second term, so "1+ shot, usually 93%" cannot lead a card while anything
    else has something to say. When nothing in the group has any lift, the caller falls back to likelihood.
    """
    w = ((weights or {}).get(f.get("scope")) or {}).get(f.get("stat"), 1.0)
    p = float(f.get("p") or 0.0)
    # docs/52: once a line is the entity's OWN half-way count, a high p is not a virtue -- it is the
    # message. What should carry weight is how much is actually at stake in the sentence, which is
    # largest where the outcome is open and nil at either end. 4p(1-p) is exactly that, normalised.
    # Without a personal line the old reading still holds: an unusual line nobody can act on is not
    # an insight either.
    stake = 4.0 * p * (1.0 - p) if f.get("is_personal") else p
    return float(w) * lift(f, scale) * stake


def _card_key(f: dict, group: str):
    base = (f["match_iid"], f["scope"], f["team_iid"], f.get("player_iid"))
    if group == "line":
        return (*base, f.get("fkey"))
    if group == "player":
        return base
    return (*base, f.get("stat"))                      # player_market: shots and on-target are separate cards


def group_cards(fc: list[dict], max_p: float = 1.0, group: str = "player", weights: dict | None = None, scale: str = "odds",
                min_span: float = 0.0) -> list[dict]:
    """One card per player (or team) per match, per market when `group` is "player_market" (docs/46).

    The line that leads is the one with the most to say -- `prominence` above -- not the highest percentage.
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
        own = [f for f in lead if f.get("is_personal")]
        if own:
            # docs/52: when the entity has its own line there is nothing to choose between -- that line
            # is the question worth asking about it, and the neighbours exist only to answer follow-ups.
            head = max(own, key=lambda f: (prominence(f, weights, scale), f["p"], f["thr"]))
            card = dict(head)
            card["more_lines"] = sorted(({k: f.get(k) for k in ("fkey", "stat", "thr", "market", "p", "lo", "hi", "tier", "p_usual", "edge", "ladder")}
                                         for f in g if f is not head), key=lambda x: (-x["p"], x["stat"], x["thr"]))
            card["best_p"] = max(f["p"] for f in g)
            out.append(card)
            continue
        best = max(prominence(f, weights, scale) for f in lead)
        # nothing in this group is saying anything unusual: fall back to the likeliest, as before
        head = (max(lead, key=lambda f: (prominence(f, weights, scale), f["p"], f["thr"])) if best > 0
                else max(lead, key=lambda f: (f["p"], f["thr"])))
        card = dict(head)
        card["more_lines"] = sorted(({k: f.get(k) for k in ("fkey", "stat", "thr", "market", "p", "lo", "hi", "tier", "p_usual", "edge", "ladder")}
                                     for f in g if f is not head), key=lambda x: (-x["p"], x["stat"], x["thr"]))
        # the best percentage anywhere in the card, so a "show me 90%+" filter can see past the lead line
        card["best_p"] = max(f["p"] for f in g)
        out.append(card)
    return out


def lead_stat(fs):
    """The stat with the largest lift over usual leads the card."""
    return max(fs, key=lambda f: (f.get("edge") or 0.0))["stat"]


CONFIDENT = {"Strong": 0, "Solid": 0, "Watch": 1, None: 2}
# "edge" ranks on the same fair scale the cards use, not on raw percentage points (docs/48).
FEED_SORTS = {
    "edge": lambda f: (CONFIDENT[f["tier"]], -lift(f), -f["p"]),
    "likely": lambda f: (TIER_RANK[f["tier"]], -f["p"]),
    "kickoff": lambda f: (f["kickoff"], TIER_RANK[f["tier"]], -f["p"]),
}


def h2h(db, a: int, b: int, limit: int = 10) -> dict:
    ms = list(db.matches.find({"status": "final", "$or": [{"home_iid": a, "away_iid": b}, {"home_iid": b, "away_iid": a}]},
                              {"_id": 0}).sort("kickoff", -1).limit(limit))
    wa = sum(1 for m in ms if (m["home_iid"] == a and m["hg"] > m["ag"]) or (m["away_iid"] == a and m["ag"] > m["hg"]))
    wb = sum(1 for m in ms if (m["home_iid"] == b and m["hg"] > m["ag"]) or (m["away_iid"] == b and m["ag"] > m["hg"]))
    _with_teams(db, ms)
    return {"a_wins": wa, "b_wins": wb, "draws": len(ms) - wa - wb, "matches": ms}


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
                  player_iids=None, team_iids=None) -> list[dict]:
    """`sort`: "edge" (default, settings engine.feed_sort) | "likely" | "kickoff".

    `player_iids` / `team_iids` narrow the feed to those players or clubs (docs/52). A club filter
    takes its own team lines and the lines of its players, which is what a reader picking a club
    off the list means by it."""
    now = now or datetime.now(timezone.utc)
    q = {**NOT_HIDDEN, "tier": {"$in": list(tiers)}, "kickoff": {"$gte": now}}
    if league_iids: q["league_iid"] = {"$in": league_iids}
    if stat: q["stat"] = stat
    if scope: q["scope"] = scope
    if player_iids: q["player_iid"] = {"$in": list(player_iids)}
    if team_iids: q["team_iid"] = {"$in": list(team_iids)}
    fc = list(db.forecasts.find(q, {"_id": 0, "contrib": 0}).limit(3000))
    grp = S.get(db, "engine.feed_group")
    if grp in ("player", "player_market"):
        fc = group_cards(fc, float(S.get(db, "engine.feed_max_p")), grp, S.get(db, "engine.market_weights"),
                         S.get(db, "engine.lift_scale"), float(S.get(db, "engine.min_span")))
    fc.sort(key=FEED_SORTS.get(sort or S.get(db, "engine.feed_sort"), FEED_SORTS["edge"]))
    fc = fc[:limit]
    _usual(db, fc)
    pl = _names(db, "players", [f["player_iid"] for f in fc if f.get("player_iid")])
    tm = _names(db, "teams", [f["team_iid"] for f in fc] + [f["opp_iid"] for f in fc])
    homes = _homes(db, fc)
    lgs = _names(db, "leagues", [f["league_iid"] for f in fc if f.get("league_iid")])
    for f in fc:
        f["home_iid"] = homes.get(f["match_iid"])
        f["league_name"] = (lgs.get(f.get("league_iid")) or {}).get("name")
        f["league_id"] = (lgs.get(f.get("league_iid")) or {}).get("id")
        f["player"] = pl.get(f.get("player_iid")); f["team"] = tm.get(f["team_iid"]); f["opp"] = tm.get(f["opp_iid"])
    return fc


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
        d0 = datetime.fromisoformat(day).replace(tzinfo=timezone.utc) - timedelta(minutes=tz_offset_min)
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
        if min_minutes: m["minutes"] = {"$gte": min_minutes}
        if positions: m["pos"] = {"$in": list(positions)}
    pipeline = [{"$match": m}, {"$sort": {"kickoff": -1}},
                {"$group": {"_id": "$" + idf, "vals": {"$push": "$" + stat}, "team": {"$first": "$team_iid"}}},
                {"$project": {"vals": {"$slice": ["$vals", last_n]}, "team": 1}}]
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
        score = reached / len(vals) if mode == "form" else run
        if mode == "form" and score < min_reached:
            continue
        if mode == "run" and run == 0:
            continue
        if playing is not None and r["team"] not in playing:
            continue
        out.append({"id": r["_id"], "team_iid": r["team"], "games": len(vals), "reached": reached, "run": run, "score": score,
                    "hits": [v >= threshold for v in vals]})
    out.sort(key=lambda x: (-x["score"], -x["games"]))
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
    if scope == "player":
        names = _names(db, "players", [o["id"] for o in out])
        for o in out: o["player"] = names.get(o["id"])
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
    proj = {"_id": 0, "kickoff": 1, "minutes": 1, "opp_iid": 1, "home": 1, **{s: 1 for s in stats}}
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
        # oldest first, because the strip is read left to right and ends at tonight
        f["run"] = [{"opp_iid": r.get("opp_iid"), "m": r.get("minutes"), "v": r[f["stat"]], "home": r.get("home")}
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
    q = {**NOT_HIDDEN, "match_iid": match_iid, "scope": scope, "stat": stat, "ladder": {"$exists": True},
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
        f["home_iid"] = homes.get(f["match_iid"])
        f["league_name"] = (lgs.get(f.get("league_iid")) or {}).get("name")
        f["league_id"] = (lgs.get(f.get("league_iid")) or {}).get("id")
    return fc


def _homes(db, fc) -> dict:
    """match iid -> home team iid, so cards can print home v away."""
    return {m["iid"]: m["home_iid"] for m in db.matches.find({"iid": {"$in": list({f["match_iid"] for f in fc})}}, {"iid": 1, "home_iid": 1})}


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
    rows = list(db.forecast_outcomes.find({**q, "player_played": True}, {"_id": 0, "tier": 1, "p": 1, "reached": 1, "scored_at": 1}))
    not_played = db.forecast_outcomes.count_documents({**q, "player_played": False})
    if len(rows) < min_n:
        return {"ready": False, "scored": len(rows), "needed": min_n, "not_played": not_played}
    tiers = {}
    for t in ("Strong", "Solid", "Watch"):
        g = [r for r in rows if r["tier"] == t]
        if g:
            tiers[t] = {"n": len(g), "stated": sum(r["p"] for r in g) / len(g), "actual": sum(r["reached"] for r in g) / len(g)}
    bins = []
    for lo in (0.5, 0.6, 0.7, 0.8, 0.9):
        g = [r for r in rows if lo <= r["p"] < lo + 0.1]
        if len(g) >= 30:
            bins.append({"from": lo, "to": round(lo + 0.1, 1), "n": len(g), "stated": sum(r["p"] for r in g) / len(g), "actual": sum(r["reached"] for r in g) / len(g)})
    since = min((r["scored_at"] for r in rows if r.get("scored_at")), default=None)
    # The whole record, over every scored row rather than over the bands that survived the 30-row
    # floor. The page led on a single band picked for having the most rows, which in this product
    # is always the 0.90-1.00 band -- the one where being right proves least.
    overall = {"n": len(rows), "stated": sum(r["p"] for r in rows) / len(rows),
               "actual": sum(r["reached"] for r in rows) / len(rows)}
    return {"ready": True, "scored": len(rows), "tiers": tiers, "bins": bins, "since": since,
            "overall": overall, "not_played": not_played}


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
    if min_minutes: m["minutes"] = {"$gte": min_minutes}
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


def team_history(db, team_iid: int, stat: str, last_n: int = 10) -> dict:
    rows = list(db.team_match_stats.find({"team_iid": team_iid, stat: {"$ne": None}}, {"_id": 0, "kickoff": 1, "opp_iid": 1, "home": 1, stat: 1}).sort("kickoff", -1).limit(last_n))
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
    # Without this the page's own cards had no p_usual and no run, so the one card a reader sees
    # after tapping through from anywhere else was drawn in the old style. The card has to be the
    # same object on every screen that shows it.
    _usual(db, fc)
    p = attach_images(db, "players", [p])[0]
    team = attach_images(db, "teams", [team])[0] if team else None
    if nxt:
        _with_teams(db, [nxt])
    return {"player": p, "team": team, "next_match": nxt,
            "forecasts": fc, "cards": group_cards(fc, float(S.get(db, "engine.feed_max_p")), "player", S.get(db, "engine.market_weights"),
                                                  S.get(db, "engine.lift_scale"), float(S.get(db, "engine.min_span")))}


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
    return {"team": t, "league": lg, "style": style, "next": _with_teams(db, nxt), "form": team_form(db, team_iid, 5)}


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
    best = _best_line(db, iids)
    for m in ms:
        m["probs"] = probs.get(m["iid"])
        m["insight_count"] = counts.get(m["iid"], 0)
        m["best_line"] = best.get(m["iid"])
    return ms
