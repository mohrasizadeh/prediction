"""load.py -- read openfootball (public domain) text files into one table of matches.

Output columns: season, comp, stage, dt, home, away, hg, ag, h_eng, a_eng
  hg/ag are the 90-minute score (extra time and shoot-outs are NOT counted).
  home/away are normalised club names (see norm()).
"""
import re, os, glob
from datetime import datetime, timedelta
import pandas as pd

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
MONTHS = {m: i for i, m in enumerate(["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"], 1)}

DATE_RE = re.compile(r"^\s*(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun)\s+(?:(\w{3})\s+(\d{1,2})|(\d{1,2})\s+(\w{3}))(?:\s+(\d{4}))?\s*$")
STAGE_RE = re.compile(r"^\s*[▪»]\s*(.+?)\s*$")
TIME_RE = re.compile(r"^\s*(\d{1,2}):(\d{2})\s+")
SCORE_RE = re.compile(r"\s+(\d+)-(\d+)\b(.*)$")


def norm(name: str) -> str:
    n = re.sub(r"\s*\([A-Z]{3}\)\s*$", "", name.strip())
    n = n.lower()
    n = re.sub(r"\ba\.?f\.?c\.?\b", "", n)
    n = re.sub(r"\bf\.?c\.?\b", "", n)
    n = re.sub(r"\bcity of\b", "", n)
    n = re.sub(r"[^a-z0-9& ]+", " ", n)
    n = re.sub(r"\s+", " ", n).strip()
    alias = {"wolverhampton wanderers": "wolves", "wolverhampton": "wolves",
             "brighton hove albion": "brighton", "brighton & hove albion": "brighton",
             "manchester utd": "manchester united", "man united": "manchester united",
             "man city": "manchester city", "newcastle utd": "newcastle united",
             "west bromwich albion": "west brom", "queens park rangers": "qpr",
             "tottenham hotspur": "tottenham", "leeds united": "leeds",
             "leicester city": "leicester", "norwich city": "norwich", "stoke city": "stoke",
             "swansea city": "swansea", "cardiff city": "cardiff", "hull city": "hull",
             "huddersfield town": "huddersfield", "west ham united": "west ham",
             "sheffield united": "sheffield utd", "nottingham forest": "forest",
             "luton town": "luton", "ipswich town": "ipswich", "bournemouth": "bournemouth",
             "newcastle united": "newcastle", "manchester united": "man utd", "manchester city": "man city",
             "crystal palace": "palace", "aston villa": "villa", "wigan athletic": "wigan",
             "bolton wanderers": "bolton", "blackburn rovers": "blackburn", "sunderland": "sunderland",
             "reading": "reading", "birmingham city": "birmingham", "watford": "watford",
             "burnley": "burnley", "southampton": "southampton", "everton": "everton",
             "liverpool": "liverpool", "chelsea": "chelsea", "arsenal": "arsenal",
             "brentford": "brentford", "fulham": "fulham", "middlesbrough": "middlesbrough"}
    return alias.get(n, n)


def _season_start(season: str) -> int:
    return int(season[:4])


def _parse_date(m, season_year, last):
    if m.group(1):
        mon, day = MONTHS.get(m.group(1)), int(m.group(2))
    else:
        mon, day = MONTHS.get(m.group(4)), int(m.group(3))
    if mon is None:
        return None
    yr = int(m.group(5)) if m.group(5) else (season_year if mon >= 7 else season_year + 1)
    return datetime(yr, mon, day)


def _ninety(rest: str, hg: int, ag: int):
    """90-minute score. If the line carries '(x-y, z-w)' the first pair is full time."""
    t = re.search(r"\((\d+)-(\d+),\s*(\d+)-(\d+)\)", rest)
    if t:
        return int(t.group(1)), int(t.group(2))
    return hg, ag


def parse_file(path, season, comp):
    rows = []
    stage, cur_date, cur_time = "", None, (20, 0)
    sy = _season_start(season)
    with open(path, encoding="utf-8") as f:
        for raw in f:
            line = raw.rstrip("\n")
            if not line.strip() or line.lstrip().startswith("#") or line.startswith("="):
                continue
            sm = STAGE_RE.match(line)
            if sm:
                stage = sm.group(1)
                continue
            dm = DATE_RE.match(line)
            if dm:
                d = _parse_date(dm, sy, cur_date)
                if d:
                    cur_date, cur_time = d, (20, 0)
                continue
            if cur_date is None:
                continue
            tm = TIME_RE.match(line)
            body = line
            if tm:
                cur_time = (int(tm.group(1)), int(tm.group(2)))
                body = line[tm.end():]
            body = body.strip()
            home = away = None
            vm = re.search(r"\s+v\s+", body)
            if vm:                                   # "A v B  2-1 (1-0)"
                home = body[:vm.start()]
                rest = body[vm.end():]
                sc = SCORE_RE.search(rest)
                if not sc:
                    continue                          # not played yet
                away = rest[:sc.start()]
                hg, ag = int(sc.group(1)), int(sc.group(2))
                tail = sc.group(3)
            else:                                    # "A  2-1 (1-0)  B"
                sc = re.search(r"^(.*?)\s+(\d+)-(\d+)\s*(\([^)]*\))?\s+(\S.*)$", body)
                if not sc:
                    continue
                home, hg, ag, tail, away = sc.group(1), int(sc.group(2)), int(sc.group(3)), (sc.group(4) or ""), sc.group(5)
            hg, ag = _ninety(tail, hg, ag)
            dt = cur_date.replace(hour=cur_time[0], minute=cur_time[1])
            rows.append(dict(season=season, comp=comp, stage=stage, dt=dt,
                             home=norm(home), away=norm(away),
                             h_eng=home.strip().endswith("(ENG)"), a_eng=away.strip().endswith("(ENG)"),
                             home_raw=home.strip(), away_raw=away.strip(), hg=hg, ag=ag))
    return rows


def load_all():
    rows = []
    seasons = sorted(d for d in os.listdir(os.path.join(ROOT, "openfootball_england")) if re.match(r"\d{4}-\d{2}$", d))
    for s in seasons:
        base = os.path.join(ROOT, "openfootball_england", s)
        for fn, comp in (("1-premierleague.txt", "PL"), ("2-championship.txt", "CH"), ("3-league1.txt", "L1"),
                         ("4-league2.txt", "L2"), ("5-nationalleague.txt", "NL"), ("eflcup.txt", "EFL"), ("facup.txt", "FA")):
            p = os.path.join(base, fn)
            if os.path.exists(p):
                rows += parse_file(p, s, comp)
        cb = os.path.join(ROOT, "openfootball_champions-league", s)
        for fn, comp in (("cl.txt", "UCL"), ("el.txt", "UEL"), ("conf.txt", "UECL")):
            p = os.path.join(cb, fn)
            if os.path.exists(p):
                rows += parse_file(p, s, comp)
    df = pd.DataFrame(rows)
    return df.sort_values("dt").reset_index(drop=True)


if __name__ == "__main__":
    df = load_all()
    print(df.groupby(["season", "comp"]).size().unstack(fill_value=0))
    df.to_pickle(os.path.join(ROOT, "all.pkl"))
