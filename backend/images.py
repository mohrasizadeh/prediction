"""images.py -- one-time sync of league logos, club crests and player photos from API-Football (api-sports.io).

The idea: we ask API-Football WHICH image belongs to each of our leagues, clubs and players, download each
image ONCE, keep it in our own database, and serve it from our own address. The app never links to the
provider's image server, so pages stay fast, nothing breaks if the provider changes, and one switch removes an image.

Flow (all steps are safe to repeat; a second run does only what is missing):
  1. leagues   our league  -> API-Football league id (admin sets `images.leagues` once; ids are listed in the help text)
  2. teams     one call per league lists its clubs. We match by NAME inside that league only.
  3. players   one call per matched club lists its squad. We match by surname + first initial + position.
  4. download  media.api-sports.io/football/{leagues|teams|players}/{id}.png, checked and stored in `media`.

Matching never guesses: a wrong photo is worse than no photo. Below `images.min_confidence` the pair goes to a
review list (`image_map.status == "review"`); an admin approves or rejects it.

Budget: the free plan allows 100 API calls a day. One run costs 1 call per league, 1 per league for clubs and 1 per club
for squads (about 22 per league), so five leagues take two days on the free plan. Image downloads from the media server
are not API calls. The run stops cleanly when the day's budget is used and carries on the next time.

Safety: only https://media.api-sports.io is ever downloaded from. Bytes are checked (PNG, JPEG or WebP by their first
bytes, size cap). SVG is refused. Nothing from the provider is stored except image bytes and ids.
"""
from __future__ import annotations

import difflib
import hashlib
import re
import time
import unicodedata
from datetime import datetime, timedelta, timezone

import httpx
from bson.binary import Binary

import security
import settings_store as S

AF_BASE = "https://v3.football.api-sports.io"
MEDIA_HOST = "media.api-sports.io"
MEDIA_PATH = {"league": "leagues", "team": "teams", "player": "players"}
KINDS = ("league", "team", "player")
PROVIDER = "apifootball"
KEY_RE = r"^[A-Za-z0-9]{20,64}$"

_FACTORY = lambda: httpx.Client(timeout=20.0, follow_redirects=False)
_SLEEP = time.sleep


def set_http_factory(f):
    global _FACTORY
    _FACTORY = f


def set_sleep(f):
    global _SLEEP
    _SLEEP = f


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class ImageError(Exception):
    pass


class BudgetExhausted(ImageError):
    pass


class NoKey(ImageError):
    pass


# ------------------------------------------------------------------ names
_STOP = {"fc", "afc", "cf", "sc", "ac", "as", "ssc", "fk", "sv", "vfb", "vfl", "rb", "us", "ud", "cd", "rc", "the", "club", "de", "calcio", "1899", "1909", "1846", "04"}
ALIASES = {"man utd": "manchester united", "man united": "manchester united", "man city": "manchester city", "spurs": "tottenham hotspur",
           "tottenham": "tottenham hotspur", "wolves": "wolverhampton wanderers", "wolverhampton": "wolverhampton wanderers",
           "newcastle": "newcastle united", "brighton": "brighton and hove albion", "west ham": "west ham united",
           "nottm forest": "nottingham forest", "nottingham": "nottingham forest", "leeds": "leeds united", "leicester": "leicester city",
           "sheffield utd": "sheffield united", "west brom": "west bromwich albion", "inter": "internazionale", "inter milan": "internazionale",
           "bayern": "bayern munich", "bayern munchen": "bayern munich", "dortmund": "borussia dortmund", "leverkusen": "bayer leverkusen",
           "gladbach": "borussia monchengladbach", "psg": "paris saint germain", "paris sg": "paris saint germain", "atletico": "atletico madrid",
           "athletic": "athletic club", "betis": "real betis", "sociedad": "real sociedad"}


_FOLD = str.maketrans({"ø": "o", "Ø": "O", "æ": "ae", "Æ": "AE", "ß": "ss", "đ": "d", "Đ": "D", "ł": "l", "Ł": "L", "œ": "oe", "Œ": "OE", "ı": "i"})


def norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", (s or "").translate(_FOLD)).encode("ascii", "ignore").decode().lower()
    s = s.replace("&", " and ").replace("-", " ")
    s = re.sub(r"[^a-z0-9 ]", " ", s)
    toks = [t for t in s.split() if t not in _STOP]
    return " ".join(toks)


def team_norm(s: str, extra: dict | None = None) -> str:
    n = norm(s)
    table = {**ALIASES, **{norm(k): norm(v) for k, v in (extra or {}).items()}}
    return table.get(n, n)


def team_score(a: str, b: str, extra=None) -> float:
    a, b = team_norm(a, extra), team_norm(b, extra)
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    ta, tb = set(a.split()), set(b.split())
    sub = 0.92 if (ta <= tb or tb <= ta) and min(len(ta), len(tb)) >= 1 and len(a) >= 4 and len(b) >= 4 else 0.0
    return max(difflib.SequenceMatcher(None, a, b).ratio(), sub)


POS_AF = {"goalkeeper": "GK", "defender": "DEF", "midfielder": "MID", "attacker": "FWD", "forward": "FWD"}


def split_name(name: str):
    """-> (first initial or '', surname). 'B. Saka' -> ('b','saka'); 'Bukayo Saka' -> ('b','saka'); 'Saka' -> ('','saka')."""
    toks = norm(name).split()
    if not toks:
        return "", ""
    if len(toks) == 1:
        return "", toks[0]
    return toks[0][0], " ".join(toks[1:]) if len(toks[0]) > 1 else " ".join(toks[1:])


def player_score(ours: str, ours_pos: str | None, theirs: str, theirs_pos: str | None) -> float:
    fi_o, sn_o = split_name(ours)
    fi_t, sn_t = split_name(theirs)
    if not sn_o or not sn_t:
        return 0.0
    full = difflib.SequenceMatcher(None, norm(ours), norm(theirs)).ratio()
    if sn_o == sn_t:
        score = 0.97 if (fi_o and fi_t and fi_o == fi_t) else (0.8 if not (fi_o and fi_t) else 0.55)
    else:
        score = full if full >= 0.9 else min(full, 0.7)
        if sn_o.split()[-1] == sn_t.split()[-1] and fi_o == fi_t and fi_o:
            score = max(score, 0.85)
    pt = POS_AF.get((theirs_pos or "").lower())
    if pt and ours_pos and pt != ours_pos:
        score -= 0.12
    return round(max(score, 0.0), 3)


# ------------------------------------------------------------------ the API-Football client
def calls_today(db) -> int:
    d = db.image_api_calls.find_one({"_id": utcnow().strftime("%Y-%m-%d")})
    return int(d["n"]) if d else 0


class AFClient:
    def __init__(self, db, http: httpx.Client | None = None):
        self.db = db
        self.http = http or _FACTORY()
        self.key = security.get_provider_key(db, PROVIDER, env_fallback="APIFOOTBALL_KEY")
        if not self.key:
            raise NoKey("No API-Football key saved (Admin > Keys).")

    def _today(self):
        return utcnow().strftime("%Y-%m-%d")

    def calls_today(self) -> int:
        return calls_today(self.db)

    def _read_limits(self, r) -> None:
        """Keep the provider's own counters: `x-ratelimit-requests-remaining` (daily) and `x-ratelimit-remaining` (per minute).
        Header names are case-insensitive. Missing or odd values are ignored."""
        def num(name):
            try:
                return int(r.headers.get(name))
            except (TypeError, ValueError):
                return None
        daily, minute = num("x-ratelimit-requests-remaining"), num("x-ratelimit-remaining")
        if daily is not None:
            self.db.image_api_calls.update_one({"_id": self._today()}, {"$set": {"remaining": daily}}, upsert=True)
        if minute is not None and minute <= 0:
            _SLEEP(5.0)                                             # a short pause lets the per-minute window move on

    def get(self, path: str, params: dict | None = None, fresh: bool = False) -> dict:
        """One API call, cached for 30 days (`fresh` skips the cache). Raises BudgetExhausted before the daily budget is passed."""
        params = {k: v for k, v in sorted((params or {}).items())}
        ck = path + "?" + "&".join(f"{k}={v}" for k, v in params.items())
        hit = None if fresh else self.db.image_api_cache.find_one({"_id": ck, "expires_at": {"$gt": utcnow().replace(tzinfo=None)}})
        if hit:
            return hit["payload"]
        day = self.db.image_api_calls.find_one({"_id": self._today()}) or {}
        if int(day.get("n", 0)) >= int(S.get(self.db, "images.daily_calls")):
            raise BudgetExhausted("Daily API-Football budget used.")
        if day.get("remaining") is not None and int(day["remaining"]) <= 0:
            raise BudgetExhausted("API-Football says today's quota is used.")      # the provider's own count wins over ours
        r = None
        for attempt in (0, 1):                                      # one retry on a timeout (499), a server error (500) or a dropped connection
            try:
                r = self.http.get(AF_BASE + path, params=params, headers={"x-apisports-key": self.key, "accept": "application/json"})
            except httpx.HTTPError:
                r = None
            self.db.image_api_calls.update_one({"_id": self._today()}, {"$inc": {"n": 1}, "$set": {"at": utcnow()}}, upsert=True)
            # LOG IT WHERE THE ADMIN LOOKS, TOO. This counter is private to the image code, and the
            # Data and Live tiles, the usage screen and the API log all read `api_call_log` -- so
            # every crest, photo and injury call was spent against the one real API-Football quota
            # while being invisible in every place that reports what we are spending. Two private
            # budgets against one provider allowance, with the admin showing only one of them, is
            # how "my quota is gone and the screen says it isn't" happens.
            self.db.api_call_log.insert_one({"at": utcnow(), "path": path,
                                             "status": "ok" if (r is not None and r.status_code == 200) else "error",
                                             "code": (r.status_code if r is not None else None),
                                             "ms": None, "purpose": "images", "provider": PROVIDER})
            if r is not None and r.status_code not in (499, 500, 502, 503, 504):
                break
            if attempt == 0:
                _SLEEP(2.0)
        if r is None:
            raise ImageError("API-Football could not be reached.")
        self._read_limits(r)
        if r.status_code in (401, 403):
            raise ImageError("API-Football refused the key.")
        if r.status_code == 429:
            raise BudgetExhausted("API-Football rate limit reached.")
        if r.status_code != 200:
            raise ImageError(f"API-Football answered {r.status_code}.")
        data = r.json()
        errs = data.get("errors")
        if errs and (errs if isinstance(errs, dict) else {"x": errs}):
            msg = "; ".join(f"{k}: {v}" for k, v in (errs.items() if isinstance(errs, dict) else [("error", errs)]))
            if "limit" in msg.lower() or "request" in msg.lower():
                raise BudgetExhausted(msg)
            if "access" in (errs if isinstance(errs, dict) else {}) or "suspended" in msg.lower():
                raise ImageError(f"API-Football account problem: {msg}")   # never cached: retried once the account is fixed
            data = {"response": [], "errors": errs}                  # for example, a season the plan cannot read
        self.db.image_api_cache.update_one({"_id": ck}, {"$set": {"payload": data, "expires_at": utcnow().replace(tzinfo=None) + timedelta(days=30)}}, upsert=True)
        return data


# ------------------------------------------------------------------ image bytes
def sniff(data: bytes) -> str | None:
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if data[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return None                                                     # includes SVG and anything else


def store_media(db, kind: str, iid: int, data: bytes, source: str, af_id: int | None = None) -> dict:
    if kind not in KINDS:
        raise ImageError("Unknown kind.")
    if len(data) > int(S.get(db, "images.max_bytes")):
        raise ImageError("Image is too large.")
    mime = sniff(data)
    if not mime:
        raise ImageError("Only PNG, JPEG or WebP images are accepted.")
    sha = hashlib.sha256(data).hexdigest()
    doc = {"kind": kind, "iid": int(iid), "mime": mime, "data": Binary(data), "sha256": sha, "size": len(data), "source": source,
           "af_id": af_id, "fetched_at": utcnow()}
    db.media.update_one({"kind": kind, "iid": int(iid)}, {"$set": doc}, upsert=True)
    return {"kind": kind, "iid": int(iid), "sha256": sha, "size": len(data), "mime": mime}


def download(db, kind: str, our_iid: int, af_id: int, http=None) -> str:
    """Fetch one image from the provider's media host and store it.

    Returns 'stored', 'missing', 'bad' or 'retry'.

    'MISSING' AND 'RETRY' ARE NOT THE SAME ANSWER, and conflating them cost real pictures. Every
    failure used to come back as 'missing' -- a dropped connection, a 503 while their media host
    was restarting, a 429 for asking too fast -- and the caller writes that verdict onto the
    `image_map` row, where it is then checked as `if m.get("missing"): continue`. Permanently. So a
    single blip during one sync denied a club its crest or a player his photograph for good, and the
    only cure was an admin clearing the row by hand. Nothing in the product could recover on its
    own, and it looks exactly like a provider that has no image for the player.

    A 404 is the provider saying it has no such picture, which is worth remembering. Nothing else is.
    """
    url = f"https://{MEDIA_HOST}/football/{MEDIA_PATH[kind]}/{int(af_id)}.png"
    own = http is None
    http = http or _FACTORY()
    try:
        r = http.get(url, headers={"accept": "image/*"})
    except httpx.HTTPError:
        return "retry"                               # never reached it: we have learned nothing
    finally:
        if own:
            try:
                http.close()
            except Exception:
                pass
    if r.status_code == 404:
        return "missing"                             # their answer: there is no such image
    if r.status_code == 200:
        try:
            store_media(db, kind, our_iid, r.content, source="apifootball", af_id=af_id)
        except ImageError:
            return "bad"                             # it arrived and it is not a usable image
        return "stored"
    return "retry"                                   # 429, 5xx, anything else: ask again later


# ------------------------------------------------------------------ mapping
def _put_map(db, kind, our_iid, **f):
    f["at"] = utcnow()
    db.image_map.update_one({"kind": kind, "our_iid": int(our_iid)}, {"$set": f}, upsert=True)


def _status_for(score, runner_up, min_conf):
    if score >= min_conf and (runner_up is None or score - runner_up >= 0.04):
        return "auto"
    if score >= 0.7:
        return "review"
    return "none"


def _season_candidates(db, league: dict) -> list[int]:
    s = int(S.get(db, "images.season"))
    if s:
        return [s, s - 1]
    m = re.match(r"(\d{4})", str(league.get("current_season") or ""))
    y = int(m.group(1)) if m else utcnow().year - 1
    return [y, y - 1, y - 2]


def drop_orphaned_photo_tasks(db) -> int:
    """Clear the `league_logo` / `team_crest` / `player_photo` queue, which nothing drains any more.

    `pitch_photos.plan` wrote these and `ingest.process_queue` worked them; the tick runs neither
    now -- pictures come from api-football.com through this module and nowhere else (docs/88). The
    tasks are therefore unreachable, and they are not harmless: the Jobs screen counts the queue, so
    it reported "19 pending" for ever, which reads as work in progress rather than work that cannot
    happen. A number nobody can act on is worse than no number.
    """
    return db.ingest_queue.delete_many(
        {"task": {"$in": ["league_logo", "team_crest", "player_photo"]},
         "status": {"$ne": "done"}}).deleted_count


def identity_map(db) -> dict:
    """When the entities CAME FROM API-Football, their id is already ours. No matching, no calls.

    Everything below this function -- `images.leagues`, the name scoring, `images.team_aliases`,
    `images.min_confidence`, the review queue on the mapping screen -- exists for one reason: the
    entities came from PitchAPI, so nothing we held carried an API-Football id and the only way to
    find one was to ask for a league's clubs and match them by name. That is guesswork, it costs a
    call per league and per club, and it is what the "Statistic names" review queue is for.

    Ingested from API-Football, `leagues.ext_id`, `teams.ext_id` and `players.ext_id` ARE the
    API-Football ids. So the map is an identity and is written directly: no calls, no scoring, no
    review, and no class of bug where two clubs with similar names swap crests.

    Only rows whose provider is API-Football are touched, so a database still holding PitchAPI
    entities keeps the matching path for those.
    """
    n = {"league": 0, "team": 0, "player": 0}
    # What is already mapped to the same id is left alone. This runs at the start of EVERY picture
    # run, and the picture run now goes every tick while a backlog remains, so rewriting tens of
    # thousands of unchanged player rows each time would be most of what the run did.
    done = {(m["kind"], m["our_iid"]): m.get("af_id") for m in db.image_map.find(
        {"status": {"$in": ["auto", "approved"]}}, {"_id": 0, "kind": 1, "our_iid": 1, "af_id": 1})}
    _put = _put_map

    def _put_map_once(db_, kind, our_iid, **f):
        if done.get((kind, int(our_iid))) == f.get("af_id") and f.get("af_id") is not None:
            return
        _put(db_, kind, our_iid, **f)
    leagues = {l["iid"]: l for l in db.leagues.find({"provider": "apifootball"}, {"iid": 1, "ext_id": 1, "name": 1})}
    if not leagues:
        return n          # nothing came from API-Football yet: leave every row to the matching below
    for lg in leagues.values():
        if str(lg.get("ext_id", "")).isdigit():
            _put_map_once(db, "league", lg["iid"], af_id=int(lg["ext_id"]), our_name=lg.get("name"),
                     status="auto", score=1.0, note="ingested from API-Football: the id is ours")
            n["league"] += 1
    # THE GUARD HAS TO PROVE PROVENANCE, not just that the id looks like a number.
    #
    # A PitchAPI club can have a numeric ext_id too, and mapping one of those would write an
    # API-Football id that belongs to a DIFFERENT club -- a real crest on the wrong team, which is
    # the exact bug this whole module was rewritten over. So an entity is only mapped when it can be
    # traced to an API-Football league, and anything that cannot be traced is left to the name
    # matching below. The first version let a player with no club through, because the check was
    # `if tm and ...`: no team meant no `tm`, so the guard did not fire and the row was mapped.
    af_leagues = set(leagues)
    team_ok = {}
    for row in db.teams.find({}, {"iid": 1, "ext_id": 1, "name": 1, "league_iid": 1}):
        ok = row.get("league_iid") in af_leagues and str(row.get("ext_id", "")).isdigit()
        team_ok[row["iid"]] = ok
        if not ok:
            continue
        _put_map_once(db, "team", row["iid"], af_id=int(row["ext_id"]), our_name=row.get("name"),
                 league_iid=row.get("league_iid"), status="auto", score=1.0,
                 note="ingested from API-Football: the id is ours")
        n["team"] += 1
    for row in db.players.find({}, {"iid": 1, "ext_id": 1, "name": 1, "team_iid": 1}):
        # No club, or a club we cannot trace to an API-Football league: not ours to claim.
        if not team_ok.get(row.get("team_iid")) or not str(row.get("ext_id", "")).isdigit():
            continue
        # `team_iid` MATTERS. run_sync already skips the squad call for a club whose players are
        # mapped -- `count_documents({"kind": "player", "team_iid": ...})` -- and this wrote the row
        # without that field, so the count was always 0 and every club paid a /players/squads call
        # to discover ids we had already written one line above. The guard was there; the row was
        # not answering it.
        _put_map_once(db, "player", row["iid"], af_id=int(row["ext_id"]), our_name=row.get("name"),
                 team_iid=row.get("team_iid"),
                 status="auto", score=1.0, note="ingested from API-Football: the id is ours")
        n["player"] += 1
    return n


def map_league(db, client: AFClient, league: dict) -> dict:
    """Set the league's API-Football id from `images.leagues` and fill the logo."""
    table = S.get(db, "images.leagues")
    af = table.get(str(league["iid"]))
    if not af:
        _put_map(db, "league", league["iid"], af_id=None, our_name=league["name"], status="none", score=0.0, note="no API-Football id in images.leagues")
        return {"status": "none"}
    _put_map(db, "league", league["iid"], af_id=int(af), our_name=league["name"], af_name=None, score=1.0, status="approved")
    return {"status": "approved", "af_id": int(af)}


def map_teams(db, client: AFClient, league: dict) -> dict:
    """One API call lists the clubs of the league. Match ours by name, inside that league only."""
    lm = db.image_map.find_one({"kind": "league", "our_iid": league["iid"]})
    if not lm or not lm.get("af_id"):
        return {"matched": 0, "review": 0, "none": 0, "skipped": "league has no API-Football id"}
    extra = S.get(db, "images.team_aliases")
    min_conf = float(S.get(db, "images.min_confidence"))
    teams = None
    for season in _season_candidates(db, league):
        data = client.get("/teams", {"league": lm["af_id"], "season": season})
        resp = data.get("response") or []
        if resp:
            teams = [{"id": x["team"]["id"], "name": x["team"]["name"]} for x in resp if x.get("team")]
            break
    if not teams:
        return {"matched": 0, "review": 0, "none": 0, "skipped": "API-Football returned no clubs (season not on your plan?)"}
    out = {"matched": 0, "review": 0, "none": 0}
    ours = list(db.teams.find({"league_iid": league["iid"]}, {"_id": 0, "iid": 1, "name": 1}))
    for t in ours:
        prev = db.image_map.find_one({"kind": "team", "our_iid": t["iid"]})
        if prev and prev["status"] in ("approved", "rejected"):
            continue
        sc = sorted(((team_score(t["name"], c["name"], extra), c) for c in teams), key=lambda x: -x[0])
        best, runner = sc[0], (sc[1][0] if len(sc) > 1 else None)
        status = _status_for(best[0], runner, min_conf)
        cands = [{"af_id": c["id"], "name": c["name"], "score": round(s, 3)} for s, c in sc[:3] if s >= 0.5]
        _put_map(db, "team", t["iid"], af_id=best[1]["id"] if status != "none" else None, our_name=t["name"], af_name=best[1]["name"] if status != "none" else None,
                 score=round(best[0], 3), status=status, candidates=cands, league_iid=league["iid"])
        out["matched" if status == "auto" else status] += 1
    return out


def map_players(db, client: AFClient, team_iid: int, fresh: bool = False) -> dict:
    tm = db.image_map.find_one({"kind": "team", "our_iid": team_iid})
    if not tm or not tm.get("af_id") or tm["status"] not in ("auto", "approved"):
        return {"matched": 0, "review": 0, "none": 0, "skipped": "club not matched"}
    ours = list(db.players.find({"team_iid": team_iid}, {"_id": 0, "iid": 1, "name": 1, "pos": 1}))
    if not ours:
        return {"matched": 0, "review": 0, "none": 0, "skipped": "no players of ours at this club yet"}      # no call spent
    data = client.get("/players/squads", {"team": tm["af_id"]}, fresh=fresh)
    squad = []
    for blk in data.get("response") or []:
        squad += [{"id": p["id"], "name": p.get("name") or "", "pos": p.get("position")} for p in blk.get("players", []) if p.get("id")]
    min_conf = float(S.get(db, "images.min_confidence"))
    out = {"matched": 0, "review": 0, "none": 0}
    chosen: dict[int, list] = {}
    rows = []
    for p in ours:
        prev = db.image_map.find_one({"kind": "player", "our_iid": p["iid"]})
        if prev and prev["status"] in ("approved", "rejected"):
            continue
        sc = sorted(((player_score(p["name"], p.get("pos"), c["name"], c["pos"]), c) for c in squad), key=lambda x: -x[0])
        if not sc:
            continue
        best, runner = sc[0], (sc[1][0] if len(sc) > 1 else None)
        status = _status_for(best[0], runner, min_conf)
        rows.append((p, best, sc, status))
        if status != "none":
            chosen.setdefault(best[1]["id"], []).append(p["iid"])
    for p, best, sc, status in rows:
        if status != "none" and len(chosen.get(best[1]["id"], [])) > 1:
            status = "review"                                       # two of ours claim one photo: a person decides
        cands = [{"af_id": c["id"], "name": c["name"], "score": s} for s, c in sc[:3] if s >= 0.5]
        _put_map(db, "player", p["iid"], af_id=best[1]["id"] if status != "none" else None, our_name=p["name"],
                 af_name=best[1]["name"] if status != "none" else None, score=best[0], status=status, candidates=cands, team_iid=team_iid)
        out["matched" if status == "auto" else status] += 1
    return out


# ------------------------------------------------------------------ the run
def _have(db, kind, iid) -> bool:
    return db.media.count_documents({"kind": kind, "iid": int(iid)}, limit=1) > 0


def _fetch_pending(db, kind, deadline, http, stats):
    q = {"kind": kind, "status": {"$in": ["auto", "approved"]}, "af_id": {"$ne": None}}
    for m in db.image_map.find(q):
        if time.monotonic() > deadline:
            stats["stopped"] = "time"
            return
        if m.get("missing") or _have(db, kind, m["our_iid"]):
            continue
        res = download(db, kind, m["our_iid"], m["af_id"], http=http)
        stats[res] = stats.get(res, 0) + 1
        # Only a verdict we believe is written down. `retry` is deliberately NOT persisted: the row
        # stays eligible and the next sync tries it again.
        if res in ("missing", "bad"):
            db.image_map.update_one({"_id": m["_id"]}, {"$set": {"missing": res, "missing_at": utcnow()}})
        _SLEEP(0.05)                                                # the media server limits bursts


def run_sync(db, client: AFClient | None = None, http=None, max_seconds: float = 40.0, refresh: bool = False) -> dict:
    """Do whatever is still missing, then stop. Call again (Run now) until `done` is true.
    `refresh=True` asks every matched club for its squad again (1 call per club) to pick up new signings."""
    stats: dict = {"api_calls_before": 0}
    deadline = time.monotonic() + max_seconds
    client = client or AFClient(db)
    stats["api_calls_before"] = client.calls_today()
    http = http or _FACTORY()
    try:
        leagues = list(db.leagues.find({"enabled": True}, {"_id": 0}))
        # Their id IS ours, so there is nothing to match. Unconditional: pictures come from
        # api-football.com and nowhere else, so there is no case where the name scoring below is
        # the right answer for a row that carries an API-Football id. It still runs for anything
        # left over from a previous provider, which is the only reason it survives at all.
        stats["identity"] = identity_map(db)
        stats["orphans_cleared"] = drop_orphaned_photo_tasks(db)
        for lg in leagues:
            if db.image_map.find_one({"kind": "league", "our_iid": lg["iid"], "af_id": {"$ne": None}}):
                continue
            map_league(db, client, lg)
        _fetch_pending(db, "league", deadline, http, stats)
        for lg in leagues:
            if time.monotonic() > deadline:
                stats["stopped"] = "time"; break
            if db.image_map.find_one({"kind": "league", "our_iid": lg["iid"], "af_id": {"$ne": None}}) is None:
                continue
            if not db.image_map.count_documents({"kind": "team", "league_iid": lg["iid"]}):
                try:
                    map_teams(db, client, lg)
                except BudgetExhausted:
                    stats["stopped"] = "budget"; break
        _fetch_pending(db, "team", deadline, http, stats)
        if S.get(db, "images.players") and "stopped" not in stats:
            for t in db.image_map.find({"kind": "team", "status": {"$in": ["auto", "approved"]}}):
                if time.monotonic() > deadline:
                    stats["stopped"] = "time"; break
                if not refresh and db.image_map.count_documents({"kind": "player", "team_iid": t["our_iid"]}):
                    continue
                try:
                    map_players(db, client, t["our_iid"], fresh=refresh)
                except BudgetExhausted:
                    stats["stopped"] = "budget"; break
            _fetch_pending(db, "player", deadline, http, stats)
    finally:
        try:
            http.close()
        except Exception:
            pass
    stats["api_calls_after"] = client.calls_today()
    stats["done"] = "stopped" not in stats
    db.image_runs.insert_one({"at": utcnow(), **{k: v for k, v in stats.items()}})
    return stats


# ------------------------------------------------------------------ admin actions
def approve(db, kind: str, our_iid: int, af_id: int | None = None, http=None) -> str:
    m = db.image_map.find_one({"kind": kind, "our_iid": int(our_iid)})
    if not m:
        raise ImageError("Nothing to approve.")
    af = int(af_id) if af_id else m.get("af_id")
    if not af:
        raise ImageError("Pick one of the candidates.")
    if af_id and af not in [c["af_id"] for c in m.get("candidates", [])] and af != m.get("af_id"):
        raise ImageError("That id is not one of the candidates.")
    _put_map(db, kind, our_iid, af_id=af, status="approved", missing=None)
    res = download(db, kind, our_iid, af, http=http)
    # Same rule as the sync loop: a transient failure is not written down, so the admin's approval
    # is not quietly undone by a 503 in the second between the two.
    if res in ("missing", "bad"):
        db.image_map.update_one({"kind": kind, "our_iid": int(our_iid)}, {"$set": {"missing": res, "missing_at": utcnow()}})
    return res


def reject(db, kind: str, our_iid: int) -> None:
    db.image_map.update_one({"kind": kind, "our_iid": int(our_iid)}, {"$set": {"status": "rejected", "at": utcnow()}}, upsert=True)
    db.media.delete_one({"kind": kind, "iid": int(our_iid)})


def remove(db, kind: str, our_iid: int) -> bool:
    """Take an image down (a rights holder asks, or it is wrong). It will not be fetched again."""
    r = db.media.delete_one({"kind": kind, "iid": int(our_iid)})
    db.image_map.update_one({"kind": kind, "our_iid": int(our_iid)}, {"$set": {"status": "rejected", "at": utcnow()}}, upsert=True)
    return r.deleted_count > 0


def status(db) -> dict:
    out = {"kinds": {}}
    for k in KINDS:
        total = {"league": "leagues", "team": "teams", "player": "players"}[k]
        n_ours = db[total].count_documents({}) if k != "league" else db.leagues.count_documents({"enabled": True})
        by = {s: db.image_map.count_documents({"kind": k, "status": s}) for s in ("auto", "approved", "review", "none", "rejected")}
        out["kinds"][k] = {"ours": n_ours, "stored": db.media.count_documents({"kind": k}), **by}
    out["bytes_stored"] = sum(d.get("size", 0) for d in db.media.find({}, {"size": 1}))
    out["api_calls_today"] = calls_today(db)
    out["api_budget"] = int(S.get(db, "images.daily_calls"))
    out["has_key"] = bool(security.get_provider_key(db, PROVIDER, env_fallback="APIFOOTBALL_KEY"))
    last = db.image_runs.find_one({}, {"_id": 0}, sort=[("at", -1)])
    out["last_run"] = last
    return out


# ------------------------------------------------------------------ for the public side
def media_url(kind: str, public_id: str, sha: str) -> str:
    return f"/api/media/{kind}/{public_id}?v={sha[:8]}"
