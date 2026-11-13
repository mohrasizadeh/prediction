"""normalize_af.py -- API-Football JSON in, the same plain dicts normalize.py returns. docs/85.

The contract is deliberately identical to `normalize.normalize_match`, so `ingest.py` changes only
in which client it calls and which endpoint it reads. Everything downstream -- the frames, the
engine, the cards -- never learns that the provider changed.

Input is one element of `/fixtures?ids=` (docs/81 §1), which carries the fixture, its teams, its
score, its events, its lineups, its team statistics and its player statistics in one answer.

Three things in here are not transcription, and each one is a decision:

1. ABSENT-OR-ZERO, rebuilt. The provider omits a count that is zero, and says so: "absence alone
   does not tell you which of the two applies" (docs/82). That ambiguity is the bug that deleted
   appearances, read a deleted appearance as an absence, halved `p_play` and dropped every card of
   the players it hit -- position-correlated, because a forward is who records no tackle (568 stored
   rows fell to 395).

   PitchAPI's guard asked whether the stat's GROUP was present on that player. The replacement asks
   the actual question, and asks it at two scales that both matter:

     * per PROVIDER BLOCK, not per leaf. `goals.total`, `goals.assists` and `goals.saves` are three
       leaves of one `goals` object the provider either sends or does not, as are `shots.total` and
       `shots.on`. If any number from that object arrived for anybody, the object is being sent, so
       a null leaf inside it is a real zero. Leaf by leaf, a match in which no goal was credited
       with an assist read as "assists not tracked" and nulled every goal involvement in it.
     * per SIDE, not per fixture. The two teams are two separate answers and one can come back
       empty on its own; the other side's numbers must never stand as proof for it.

   `_tracked_in_fixture` answers it for a set of blocks, `_tracked_by_team` splits them by side.

2. KEEPERS KEEP THEIR TACKLES. `normalize.players` blanks a goalkeeper's tackles, because PitchAPI
   sent keepers no defence group at all, so a 0 there would have been invented. API-Football puts
   every player's tackles in the same object, so a keeper's 0 is a real 0 -- and reproducing the old
   blanking would put `None` in a column that is in `engine_bridge.PLAYER_REQUIRED`, which is what
   deletes keeper rows on a flat dropna (docs/70). The old behaviour was a provider artefact, not a
   rule, and carrying it over would cost us the saves market.

3. EXTRA TIME IS FLAGGED, and by default excluded from the fitting frame. `statistics` is the whole
   match including extra time, with nothing to say so, so a 120-minute cup tie reports its shots,
   corners and tackles as one inflated number. Fitted beside 90-minute matches it drags every
   team-total model upward and makes cup fixtures look fast-paced. `provider.apifootball.exclude_extra_time`
   defaults on: the match is still ingested, still shown, still graded -- it is only kept out of the
   frames the engine fits. Keeping it costs one cup tie in ten; including it biases every model.

Two columns API-Football does not carry at all, and both are unused (docs/80 §1): `xg`, which needs
an add-on nobody is on, and `clearances`. They are stored as None, as a missing value always is.
"""
from __future__ import annotations

from normalize import MissingField, PLAYER_COLS, TEAM_COLS, _num

# Our column <- where it lives in a player's statistics block. (group, field) into the nested dicts
# the provider sends; None means the provider has no such number.
PLAYER_PATHS = {
    "minutes": ("games", "minutes"),
    "shots": ("shots", "total"),
    "sot": ("shots", "on"),
    "goals": ("goals", "total"),
    "assists": ("goals", "assists"),
    "saves": ("goals", "saves"),
    "tackles": ("tackles", "total"),
    "interceptions": ("tackles", "interceptions"),
    "fouls_committed": ("fouls", "committed"),
    "fouls_won": ("fouls", "drawn"),
    "passes": ("passes", "total"),
    "xg": None,              # Expected Goals add-on only, and engine.xg_blend is 0 (docs/80 §1)
    "clearances": None,      # not carried; unused by any market or required column
}

# A count the provider omits when it is zero. Same list as normalize.ZERO_WHEN_ABSENT, for the same
# reason, plus the two that only exist here.
ZERO_WHEN_ABSENT = ("shots", "sot", "goals", "assists", "tackles", "interceptions",
                    "fouls_committed", "fouls_won", "passes", "saves")

# Their fixture status shorts, to ours. normalize.status_of's vocabulary: final | scheduled | other.
FINAL_SHORTS = {"FT", "AET", "PEN"}
SCHEDULED_SHORTS = {"NS", "TBD"}
EXTRA_TIME_SHORTS = {"AET", "PEN"}       # reached extra time, so its totals cover more than 90'


def status_of(short: str | None) -> str:
    s = str(short or "").upper()
    return "final" if s in FINAL_SHORTS else "scheduled" if s in SCHEDULED_SHORTS else "other"


def went_to_extra_time(fixture: dict) -> bool:
    """Did this match run past 90 minutes? Read from the status, not from the clock, because the
    clock stops reporting once a match is over."""
    short = (((fixture or {}).get("fixture") or {}).get("status") or {}).get("short")
    return str(short or "").upper() in EXTRA_TIME_SHORTS


# ------------------------------------------------------------------ values
def parse_team_value(v):
    """'59%' -> 59.0 ; '295' -> 295.0 ; None or '' -> None.

    Possession and the pass percentage arrive with a per-cent sign; everything else is a bare
    number as a string or an int.
    """
    if v is None or v == "":
        return None
    s = str(v).strip().rstrip("%").strip()
    try:
        return float(s)
    except ValueError:
        return None


def team_items(fixture: dict) -> dict:
    """{team ext id: {statistic name: value}} for one fixture.

    Their `statistics` is a list per team of `{type, value}`, where `type` is a DISPLAY STRING and
    not a stable id -- which is why the map lives in settings and the admin screen checks it against
    a real answer (docs/81 §3).
    """
    out = {}
    for block in (fixture.get("statistics") or []):
        tid = ((block.get("team") or {}).get("id"))
        if tid is None:
            continue
        got = {}
        for st in (block.get("statistics") or []):
            if st.get("type"):
                got[str(st["type"])] = parse_team_value(st.get("value"))
        out[str(tid)] = got
    return out


# A team statistic whose true value is zero. The provider sends `{"type": "Corner Kicks", "value":
# null}` for a side that won no corner, exactly as it does for Offsides and Red Cards -- the key is
# PRESENT and only the value is empty. `got.get(name)` cannot tell that apart from a key the feed
# never sent, so a 0-corner side read as "corners unknown".
#
# That was not a cosmetic loss. `corners` and `poss` are both in `engine_bridge.TEAM_REQUIRED`, and
# `build_frames` does `tg.dropna(subset=TEAM_REQUIRED)` and then drops any match missing a side --
# so ONE null corner count deleted the entire match from every frame, both teams and all 26 player
# rows with it, without an exception, a log line or an ingest issue. Measured with 15% of
# team-matches carrying a null `corners`: 96 matches in, 76 out, 672 player rows gone, and
# `run_league` still returned `status: done`. The bias runs one way, because the matches it deletes
# are the low-corner ones.
#
# DELIBERATELY NARROW. Only columns whose true value is OFTEN zero and that have no other way of
# being recovered:
#
#   corners, fouls, yellow_cards   a side really can win no corner and collect no card, and nothing
#                                  else in the feed can tell us it did.
#
# Everything else is left alone, for a specific reason each:
#
#   shots, sot   a null is far likelier to be a gap than a real zero -- a side that played 90
#                minutes and had no shot at all is close to impossible -- and both already have a
#                safety net: `_sum_team` adds up the players' own numbers (and `shots` is
#                REQUIRED_TEAM, the one column we refuse a whole match over, so reading a gap as a
#                confident 0 here would be the worst possible place to guess).
#   poss         a side cannot have had 0% of the ball; it is mirrored from the other side below.
#   xg           an absent xG is an absent add-on, not a goalless chance count.
ZERO_WHEN_SENT = ("corners", "fouls", "yellow_cards")


def team_stats(fixture: dict, team_keys: dict, home_ext: str, away_ext: str) -> dict:
    items = team_items(fixture)
    out = {"home": {}, "away": {}}
    for side, ext in (("home", str(home_ext)), ("away", str(away_ext))):
        got = items.get(str(ext), {})
        for col in TEAM_COLS:
            name = team_keys.get(col)
            v = got.get(name) if name else None
            # `name in got` is the whole point: sent-but-null is a zero, never-sent stays None so
            # that a wrong or renamed key in the map still shows up as missing rather than as a
            # confident 0 (docs/80 §6 warns the display strings can be renamed).
            if v is None and name and name in got and col in ZERO_WHEN_SENT:
                v = 0.0
            out[side][col] = v
    # Possession is one number shared between two sides: if we have one, we have both. Without this
    # a single null `Ball Possession` deleted the match the same way a null corner count did.
    hp, ap = out["home"].get("poss"), out["away"].get("poss")
    if hp is None and ap is not None:
        out["home"]["poss"] = round(100.0 - float(ap), 1)
    elif ap is None and hp is not None:
        out["away"]["poss"] = round(100.0 - float(hp), 1)
    return out


# ------------------------------------------------------------------ players
def _player_blocks(fixture: dict) -> list[tuple[str, dict, dict]]:
    """(team ext id, player, that player's one statistics block) for everyone who featured."""
    rows = []
    for block in (fixture.get("players") or []):
        tid = ((block.get("team") or {}).get("id"))
        for p in (block.get("players") or []):
            stats = (p.get("statistics") or [{}])
            rows.append((str(tid), p.get("player") or {}, stats[0] if stats else {}))
    return rows


def _raw(stat: dict, path):
    if not path:
        return None
    group, field = path
    return _num(((stat.get(group) or {}) or {}).get(field))


def _tracked_in_fixture(blocks) -> dict:
    """{column: was this number recorded for ANYONE in these blocks}.

    The replacement for PitchAPI's group check, and a direct test of the question rather than a
    proxy for it: if any player has a tackle count, tackles were tracked, so a null for another
    player is a real zero. If nobody does, it was not tracked and null stays None.

    Call it PER SIDE (see `_tracked_by_team`), never across the whole fixture.
    """
    # TRACKEDNESS IS A PROPERTY OF THE PROVIDER'S BLOCK, NOT OF THE LEAF INSIDE IT.
    #
    # This asked the question one leaf at a time, and that is wrong for every leaf whose true value
    # is usually zero. `goals.total`, `goals.assists` and `goals.saves` are three leaves of ONE
    # `goals` object that the provider either sends or does not. In a 3-1 where no goal was credited
    # with an assist -- penalties, own goals, solo goals, and plain 0-0 draws -- `goals.assists` is
    # null for all 26 players. Leaf by leaf that reads "this match did not track assists", so every
    # assist stayed None, and `goal_involvements` below went None WITH IT -- for the four
    # goalscorers too, whose `goals` was a confirmed 1.0.
    #
    # Measured over a 96-match season: 10% of real goal involvements thrown away, 28% of player rows
    # carrying a NaN, and the team total 10% low. Worse than low: `engine_bridge` builds the team
    # total with a pandas `.sum()`, and pandas sums an all-NaN group to 0.0 rather than NaN, so an
    # untracked fixture became a CONFIDENT team total of zero that the frame's null guard could not
    # see. `score_finished` then skipped those rows, so they were never graded either.
    #
    # The same bug hit `shots.on`: a fixture in which nobody managed a shot on target left `sot`
    # None for everyone, and `sot` is in PLAYER_REQUIRED, so the dropna deleted the whole fixture's
    # player rows -- biasing the shots models high, because the lowest-output matches are precisely
    # the ones that got removed.
    #
    # Asking per block is both the correct question and the cheaper one: if the provider sent ANY
    # number out of a player's `goals` object in this match, it is sending that object, and a null
    # leaf inside it is a real zero.
    present_blocks = set()
    for _, _, stat in blocks:
        for group, body in (stat or {}).items():
            if isinstance(body, dict):
                if any(v is not None for v in body.values()):
                    present_blocks.add(group)
            elif body is not None:
                present_blocks.add(group)
    seen = {}
    for col, path in PLAYER_PATHS.items():
        seen[col] = bool(path) and path[0] in present_blocks
    return seen


def _tracked_by_team(blocks) -> dict:
    """{team ext id: {column: tracked for THAT side}}.

    PER SIDE, not per fixture. Asking across both teams at once sounds harmless -- "did this match
    track tackles" -- but the two sides are two separate answers from the provider and one of them
    can come back empty on its own. When that happened, the OTHER side's numbers stood as proof that
    the statistic was tracked, and all eleven of the empty side's starters were filled to 0.0:
    zero shots, zero tackles, zero everything, for a side whose own team-statistics block plainly
    said ten shots. Nothing downstream could tell that from a real performance. `TEAM_REQUIRED` was
    satisfied (0.0 is not null), so the match was not dropped either -- it was fitted, with a team
    that made no tackles and a front line that had no shots.
    """
    by_team: dict = {}
    for team_ext, p, stat in blocks:
        by_team.setdefault(team_ext, []).append((team_ext, p, stat))
    return {t: _tracked_in_fixture(bs) for t, bs in by_team.items()}


def players(fixture: dict, position_map: dict) -> list[dict]:
    blocks = _player_blocks(fixture)
    by_team = _tracked_by_team(blocks)
    rows = []
    for team_ext, p, stat in blocks:
        tracked = by_team.get(team_ext, {})
        games = stat.get("games") or {}
        if not stat:                      # listed with no statistics block at all: never on the pitch
            continue
        # AN UNUSED SUBSTITUTE IS NOT A MATCH HE PLAYED, so he gets no match row.
        #
        # API-Football sends a man who sat on the bench all game a FULL `statistics` block with
        # `games.minutes: null`, which is a different shape from PitchAPI's `minutes: 0` and defeats
        # both readers that were written against it. `queries.finder` and `queries.player_history`
        # exclude a non-appearance with `{"$ne": 0}` -- and in MongoDB `{$ne: 0}` MATCHES null, so a
        # bench row counted as a game he played and failed. That is the bug the comment in
        # `queries.finder` describes as fixed ("one absence cut a run of ten down to two"): it came
        # straight back under the new provider, in a shape the guard could not see. Proven on a
        # player who took 3 shots in each of 4 appearances and sat out 2: the strip read 4 of 6.
        #
        # The readers are NOT the right place to fix it. That comment explains why `$gt: 0` is the
        # worse version -- where minutes is unmapped every row is null and requiring an appearance
        # empties the league. So remove the fabricated row instead and both readers keep working,
        # for both providers, unchanged. `score_finished` is fixed by the same stroke: it infers
        # "did he play" from whether a row exists, so a bench row made a non-appearance into a
        # counted MISS in the track record and in the calibration map.
        #
        # Deliberately narrow: only a player the provider itself flags as a substitute, who also has
        # no minutes. A starter with null minutes is a feed gap on a man who did play, and he keeps
        # his row. He is still on record as named -- `db.lineups` holds the bench.
        if games.get("minutes") is None and games.get("substitute") is True:
            continue
        raw_pos = games.get("position")
        row = {
            "ext_id": str(p.get("id")) if p.get("id") is not None else None,
            "name": p.get("name"), "team_ext_id": team_ext,
            "pos_raw": raw_pos,
            "pos": position_map.get(str(raw_pos)) if raw_pos is not None else None,
            # their own flag, so the started flag needs no lineups cross-reference the way
            # normalize.normalize_match had to build one
            "started": (games.get("substitute") is False) or None,
            "shirt": games.get("number"), "rating": _num(games.get("rating")),
            "captain": bool(games.get("captain")),
        }
        for col in PLAYER_COLS:
            row[col] = _raw(stat, PLAYER_PATHS.get(col))
        # the guard: a null is a zero only where the match recorded that number for somebody
        for col in ZERO_WHEN_ABSENT:
            if row.get(col) is None and tracked.get(col):
                row[col] = 0.0
        # A keeper's tackles are a real 0 here, unlike PitchAPI: see the header, point 2.
        # Either half is enough. Requiring BOTH meant one missing half nulled the whole figure,
        # including for a player whose goal is not in doubt. With the block check above both halves
        # are normally filled, so this is the belt to that braces: if only one number survives, a
        # goal involvement is still at least that number, and `None` only when neither is known.
        g, a = row.get("goals"), row.get("assists")
        row["goal_involvements"] = (None if g is None and a is None
                                    else float(g or 0.0) + float(a or 0.0))
        if row["ext_id"]:
            rows.append(row)
    return rows


# ------------------------------------------------------------------ lineups
def lineups(fixture: dict, position_map: dict) -> dict:
    """The official eleven and bench, per side.

    Theirs are the published lineups (20 to 40 minutes before kick-off), so a lineup that is here
    IS confirmed -- there is no predicted-versus-official distinction to carry, which is what
    PitchAPI's `lineup_type` existed for.
    """
    teams = fixture.get("teams") or {}
    want = {str((teams.get("home") or {}).get("id")): "home",
            str((teams.get("away") or {}).get("id")): "away"}
    out = {"home": {"confirmed": False, "formation": None, "lineup_type": None, "players": []},
           "away": {"confirmed": False, "formation": None, "lineup_type": None, "players": []}}
    for block in (fixture.get("lineups") or []):
        side = want.get(str(((block.get("team") or {}).get("id"))))
        if side is None:
            continue
        people = []
        for kind, started in (("startXI", True), ("substitutes", False)):
            for x in (block.get(kind) or []):
                pl = x.get("player") or {}
                people.append({
                    "ext_id": str(pl.get("id")) if pl.get("id") is not None else None,
                    "started": started, "shirt_number": pl.get("number"),
                    "position_id": pl.get("pos"),
                    "pos": position_map.get(str(pl.get("pos"))) if pl.get("pos") else None,
                    # "1:1", "2:4" -- row:column on the pitch grid, their own notation
                    "grid": pl.get("grid"), "pitch_x": None, "pitch_y": None,
                    "is_captain": False, "name": pl.get("name"),
                })
        _place(people)
        out[side] = {"confirmed": bool(people), "formation": block.get("formation"),
                     "lineup_type": "official" if people else None,
                     "coach": ((block.get("coach") or {}).get("name")),
                     "coach_ext_id": ((block.get("coach") or {}).get("id")),
                     "players": people}
    return out


# The depth of the goalkeeper's line and of the furthest-forward line, matching `queries.LINE_X` so
# a real lineup and a predicted one are drawn on the same pitch.
GK_DEPTH, FWD_DEPTH = 0.03, 0.88


def _place(people: list[dict]) -> None:
    """Turn their `grid` into `pitch_x` / `pitch_y`, in place.

    These two were written as a hard `None`, with the grid string stored beside them and nothing
    ever reading it. `Match.jsx` draws a player at `(pitch_x || 0) * 48` across and `pitch_y ?? 0.5`
    down, so a null put every single one of the eleven on the goal line at the same height: the
    moment a real lineup arrived, the pitch graphic collapsed into one pile of names. The predicted
    lineup looked right, because `queries` computes its own coordinates -- so the graphic worked
    until the teamsheet was published and then broke, which is the worst way round.

    Their notation is "row:column", row 1 being the keeper's line and counting up towards the
    opponent, column counting across. Depth is the row's rank among the rows this side actually
    fielded, so a 4-4-2 and a 3-4-2-1 both fill the pitch instead of one of them bunching up.
    """
    grids = {}
    for p in people:
        if not p.get("started"):
            continue                        # a substitute has no place on the pitch
        try:
            row, col = (int(v) for v in str(p.get("grid") or "").split(":")[:2])
        except (ValueError, TypeError):
            continue
        grids[id(p)] = (row, col)
    if not grids:
        return
    rows = sorted({r for r, _ in grids.values()})
    span = (FWD_DEPTH - GK_DEPTH)
    depth = {r: (GK_DEPTH + span * (i / (len(rows) - 1)) if len(rows) > 1 else GK_DEPTH)
             for i, r in enumerate(rows)}
    width = {}
    for r, c in grids.values():
        width[r] = max(width.get(r, 0), c)
    for p in people:
        g = grids.get(id(p))
        if not g:
            continue
        row, col = g
        p["pitch_x"] = round(depth[row], 4)
        p["pitch_y"] = round(col / (width[row] + 1), 4)


# ------------------------------------------------------------------ one match
REQUIRED_TEAM = ["shots"]


def _sum_team(pl, team_ext, col):
    vals = [p[col] for p in pl if p["team_ext_id"] == str(team_ext) and p.get(col) is not None]
    return float(sum(vals)) if vals else None


# Their event words -> ours. `match_extras._kind` does the same for PitchAPI and the vocabulary has
# to agree, because `queries.py` and `cards_model.py` read the stored list by these names.
#
# THIS FUNCTION IS NOW THE ONLY TRANSLATOR FOR BOTH THE LIVE AND THE HISTORICAL PATH, so a wrong
# word here is wrong everywhere at once, for every league, with no second implementation left to
# disagree with it visibly. `EVENT_TYPES` below is the contract; `selftest_audit_v11` asserts that
# every consumer's vocabulary contains it.
EVENT_KIND = {"goal": "goal", "card": None, "subst": "sub"}
# A MISSED PENALTY IS NOT A GOAL. They report one as `{"type": "Goal", "detail": "Missed Penalty"}`,
# and keying on `type` alone made it byte-identical to a converted penalty: same `type: "goal"`, same
# `penalty: True`. A 5th-minute miss therefore became the match's first goal -- `first_goal_side`
# and `first_scorer_iid` both named the player who MISSED -- credited him `pen_goals += 1` and an
# entry in `goal_minutes`, and inflated the referee's penalty rate. The front end has had a
# `missed_penalty` label waiting for a word this never produced.
GOAL_DETAIL = {"missed penalty": "missed_penalty"}
CARD_DETAIL = {"yellow card": "yellow", "second yellow card": "red", "red card": "red"}
# Both second-yellow details collapse to `red`, because every counter downstream wants "he was sent
# off". The distinction only matters for what a follower is TOLD, so it rides along as a flag rather
# than as a fourth type nothing else would recognise.
SECOND_YELLOW = "second yellow card"

# The complete set of words `events()` can emit. Every reader of a stored event -- `follow_alerts`,
# `live_track`, `match_extras._apply`, `MatchEvents.jsx`, `LiveBits.jsx` -- must understand all of
# them. Three of those five did not, and each failed silently: a red card matched no alert query, and
# `red` and `sub` fell through the front end's grey "unknown" fallback.
EVENT_TYPES = frozenset({"goal", "missed_penalty", "yellow", "red", "sub"})


def events(fixture: dict, home_ext: str, away_ext: str) -> list[dict]:
    """Their inline events in the shape `match_extras.normalize_events` returns.

    These arrive FREE, attached to the same bundled answer as the statistics. On PitchAPI they were
    a call per match behind `ingest.match_extra_detail`, which is why that setting exists and why
    the referee model could go hungry when the budget was tight. Here there is nothing to switch on.
    """
    out = []
    for e in (fixture.get("events") or []):
        typ = str(e.get("type") or "").strip().lower()
        detail = str(e.get("detail") or "").strip().lower()
        if typ == "card":
            kind = CARD_DETAIL.get(detail)
        elif typ == "goal":
            kind = GOAL_DETAIL.get(detail) or EVENT_KIND.get(typ)
        else:
            kind = EVENT_KIND.get(typ)
        if not kind:
            continue
        tid = str((e.get("team") or {}).get("id"))
        side = "home" if tid == str(home_ext) else "away" if tid == str(away_ext) else None
        if side is None:
            continue
        t = e.get("time") or {}
        p, asst = e.get("player") or {}, e.get("assist") or {}
        # On a substitution THEY put the player coming OFF in `player` and the one coming ON in
        # `assist`, which is the opposite of what the field names suggest.
        out.append({
            "type": kind, "minute": t.get("elapsed"), "added": t.get("extra") or 0, "side": side,
            "player_ext": str(p.get("id")) if p.get("id") is not None else None,
            "player_name": p.get("name"),
            "in_ext": str(asst.get("id")) if (kind == "sub" and asst.get("id") is not None) else None,
            "in_name": asst.get("name") if kind == "sub" else None,
            "own_goal": detail == "own goal",
            "penalty": "penalty" in detail,
            "second_yellow": typ == "card" and detail == SECOND_YELLOW,
        })
    out.sort(key=lambda x: ((x["minute"] or 0), x["added"], x["type"] == "red"))
    return out


def normalize_match(fixture: dict, settings: dict) -> dict:
    """One bundled fixture -> the same shape `normalize.normalize_match` returns, plus `extra_time`.

    settings: team_keys, position_map, exclude_extra_time.
    """
    teams = fixture.get("teams") or {}
    home_ext = str((teams.get("home") or {}).get("id"))
    away_ext = str((teams.get("away") or {}).get("id"))
    issues = []

    ev = events(fixture, home_ext, away_ext)
    ts = team_stats(fixture, settings["team_keys"], home_ext, away_ext)
    pl = players(fixture, settings["position_map"])
    lu = lineups(fixture, settings["position_map"])

    et = went_to_extra_time(fixture)
    if et:
        issues.append({"kind": "extra_time",
                       "detail": "totals cover more than 90 minutes; "
                                 + ("kept out of the engine's frames" if settings.get("exclude_extra_time", True)
                                    else "INCLUDED in the frames, which biases team totals upward")})

    for side, ext in (("home", home_ext), ("away", away_ext)):
        for col in REQUIRED_TEAM:
            if ts[side][col] is None:
                tot = _sum_team(pl, ext, col)
                if tot is None:
                    raise MissingField(f"team {col} missing for {side}")
                ts[side][col] = tot
                issues.append({"kind": "team_stat_from_players", "detail": col})

    gaps = [p["ext_id"] for p in pl if p.get("minutes") is None or p.get("shots") is None]
    if gaps:
        issues.append({"kind": "player_stat_missing",
                       "detail": f"{len(gaps)} players without minutes or shots: " + ", ".join(gaps[:10])})

    # A starter flag we could not read from `games.substitute` falls back to the lineup, as
    # normalize.normalize_match always did.
    started = {x["ext_id"] for s in ("home", "away") for x in lu[s]["players"] if x["started"]}
    for p in pl:
        if p.get("started") is None:
            p["started"] = p["ext_id"] in started

    # A position the player row did not carry comes from the lineup, which has one per player.
    lpos = {x["ext_id"]: x["pos"] for s in ("home", "away") for x in lu[s]["players"] if x.get("pos")}
    for p in pl:
        if p.get("pos") is None:
            p["pos"] = lpos.get(p["ext_id"])

    totals = {}
    for side, ext in (("home", home_ext), ("away", away_ext)):
        # Only the stats whose TEAM total sits on the player row, because the engine builds a
        # player's rate as his share of it (docs/70).
        totals[side] = {c: _sum_team(pl, ext, c)
                        for c in ("shots", "sot", "tackles", "fouls_committed", "goal_involvements",
                                  "saves")}
        # No team tackles statistic exists here, so the team total IS the sum of the players'
        # (docs/80 §2). The same fallback normalize.py has always used.
        for col in ("tackles", "sot"):
            if ts[side][col] is None:
                ts[side][col] = totals[side][col]
        s_stats, s_sum = ts[side]["shots"], totals[side]["shots"]
        if s_sum is not None and s_stats is not None and abs(s_stats - s_sum) > 1:
            issues.append({"kind": "team_player_shots_gap", "detail": f"{side}: stats {s_stats} vs players {s_sum}"})

    return {"team": ts, "players": pl, "lineups": lu, "team_totals": totals,
            # Free, on the same answer as the statistics -- see `events()`. The PitchAPI path pays
            # a call per match for these and hides them behind `ingest.match_extra_detail`.
            "events": ev,
            "extra_time": et, "issues": issues}


# ------------------------------------------------------------------ the fixture listing
def match_row(fixture: dict) -> dict:
    """One fixture's own row, for `matches`. The shape `normalize.match_row` returns."""
    fx = fixture.get("fixture") or {}
    lg = fixture.get("league") or {}
    teams = fixture.get("teams") or {}
    goals = fixture.get("goals") or {}
    short = ((fx.get("status") or {}).get("short"))
    return {
        "ext_id": str(fx.get("id")),
        "league_ext": str(lg.get("id")) if lg.get("id") is not None else None,
        "season": str(lg.get("season")) if lg.get("season") is not None else None,
        "round": lg.get("round"),
        "kickoff_iso": fx.get("date"),
        "provider_status": short, "status": status_of(short),
        "extra_time": str(short or "").upper() in EXTRA_TIME_SHORTS,
        "home_ext": str((teams.get("home") or {}).get("id")),
        "home_name": (teams.get("home") or {}).get("name"),
        "away_ext": str((teams.get("away") or {}).get("id")),
        "away_name": (teams.get("away") or {}).get("name"),
        "hg": goals.get("home"), "ag": goals.get("away"),
        # Free here, where PitchAPI needed a per-match detail call for it (docs/80 §2), so
        # referees.py gets fed without ingest.match_extra_detail.
        "referee": fx.get("referee"),
        "venue": ((fx.get("venue") or {}).get("name")),
        "elapsed": ((fx.get("status") or {}).get("elapsed")),
    }
