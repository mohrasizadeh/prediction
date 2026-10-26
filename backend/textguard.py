"""textguard.py -- one place for the word rules (see 03_rules_and_compliance.md).

Anything an admin can type that visitors will see goes through `require_clean`:
site text, nav labels, popups, announcements, content pages, e-mail templates, public settings.
The only allowed use of a banned word is the exact disclaimer sentence.
"""
from __future__ import annotations

import re

DISCLAIMER = "Statistical analysis for information and entertainment. Not betting advice."

BANNED = re.compile(
    r"\b(bet|bets|betting|bettors?|bookies?|bookmakers?|sportsbooks?|odds|wagers?|wagering|parlays?|accumulators?|"
    r"stakes?|punt|punters?|tipsters?|locks?|bankers?|units|hit rate|picks|props)\b", re.I)


def scan(text: str) -> list[str]:
    """Banned words found in `text`, ignoring the exact disclaimer sentence."""
    if not isinstance(text, str) or not text:
        return []
    t = text.replace(DISCLAIMER, " ")
    return sorted({m.group(0).lower() for m in BANNED.finditer(t)})


def strings(obj, _depth: int = 0):
    """Every string value inside nested dicts and lists (keys are not scanned)."""
    if _depth > 8:
        return
    if isinstance(obj, str):
        yield obj
    elif isinstance(obj, dict):
        for v in obj.values():
            yield from strings(v, _depth + 1)
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            yield from strings(v, _depth + 1)


def find(obj) -> list[str]:
    out: set[str] = set()
    for s in strings(obj):
        out.update(scan(s))
    return sorted(out)


class BannedWords(ValueError):
    """Raised by require_clean. A ValueError, so older callers still catch it; the app also maps it to a clear 400 everywhere."""


def require_clean(label: str, obj) -> None:
    bad = find(obj)
    if bad:
        raise BannedWords(f"{label}: these words are not allowed here: {', '.join(bad)}.")
