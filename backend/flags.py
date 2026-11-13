"""flags.py -- which teams are countries, and which flag each one flies.

A national team's provider "logo" is its federation badge, and next to club crests it reads as one
more club. Countries are drawn as a round flag instead (frontend Crest), so the flag has to be
known here: `attach_images` gives every team a `flag` code -- an ISO 3166 code, or gb-eng etc. for
the four home nations -- when, and only when, the team is a country. The SVGs ship with the app
(frontend/public/flags, from the MIT-licensed flag-icons package), so a flag is a same-origin file
like every other picture we show (docs/19 section 5).

"Is a country" is decided by the fixtures, not the name: a team that has played in a competition
marked `kind == "international"` (af_leagues). A club called "Brazil" or "Malta" is still a club.
The name is used only to choose the flag, and a country whose name we cannot map keeps its badge.
"""
from __future__ import annotations

import re
import time
import unicodedata

# flag-icons' own names (country.json), then the spellings API-Football and FIFA use.
_NAMES = {
    "Afghanistan": "af",
    "Aland Islands": "ax",
    "Albania": "al",
    "Algeria": "dz",
    "American Samoa": "as",
    "Andorra": "ad",
    "Angola": "ao",
    "Anguilla": "ai",
    "Antarctica": "aq",
    "Antigua and Barbuda": "ag",
    "Argentina": "ar",
    "Armenia": "am",
    "Aruba": "aw",
    "Australia": "au",
    "Austria": "at",
    "Azerbaijan": "az",
    "Bahamas": "bs",
    "Bahrain": "bh",
    "Bangladesh": "bd",
    "Barbados": "bb",
    "Belarus": "by",
    "Belgium": "be",
    "Belize": "bz",
    "Benin": "bj",
    "Bermuda": "bm",
    "Bhutan": "bt",
    "Bolivia": "bo",
    "Bonaire, Sint Eustatius and Saba": "bq",
    "Bosnia and Herzegovina": "ba",
    "Botswana": "bw",
    "Bouvet Island": "bv",
    "Brazil": "br",
    "British Indian Ocean Territory": "io",
    "Brunei Darussalam": "bn",
    "Bulgaria": "bg",
    "Burkina Faso": "bf",
    "Burundi": "bi",
    "Cabo Verde": "cv",
    "Cambodia": "kh",
    "Cameroon": "cm",
    "Canada": "ca",
    "Cayman Islands": "ky",
    "Central African Republic": "cf",
    "Chad": "td",
    "Chile": "cl",
    "China": "cn",
    "Christmas Island": "cx",
    "Cocos (Keeling) Islands": "cc",
    "Colombia": "co",
    "Comoros": "km",
    "Cook Islands": "ck",
    "Costa Rica": "cr",
    "Croatia": "hr",
    "Cuba": "cu",
    "Curaçao": "cw",
    "Cyprus": "cy",
    "Czech Republic": "cz",
    "Côte d'Ivoire": "ci",
    "Democratic Republic of the Congo": "cd",
    "Denmark": "dk",
    "Djibouti": "dj",
    "Dominica": "dm",
    "Dominican Republic": "do",
    "Ecuador": "ec",
    "Egypt": "eg",
    "El Salvador": "sv",
    "England": "gb-eng",
    "Equatorial Guinea": "gq",
    "Eritrea": "er",
    "Estonia": "ee",
    "Eswatini": "sz",
    "Ethiopia": "et",
    "Falkland Islands": "fk",
    "Faroe Islands": "fo",
    "Federated States of Micronesia": "fm",
    "Fiji": "fj",
    "Finland": "fi",
    "France": "fr",
    "French Guiana": "gf",
    "French Polynesia": "pf",
    "French Southern Territories": "tf",
    "Gabon": "ga",
    "Gambia": "gm",
    "Georgia": "ge",
    "Germany": "de",
    "Ghana": "gh",
    "Gibraltar": "gi",
    "Greece": "gr",
    "Greenland": "gl",
    "Grenada": "gd",
    "Guadeloupe": "gp",
    "Guam": "gu",
    "Guatemala": "gt",
    "Guernsey": "gg",
    "Guinea": "gn",
    "Guinea-Bissau": "gw",
    "Guyana": "gy",
    "Haiti": "ht",
    "Heard Island and McDonald Islands": "hm",
    "Holy See": "va",
    "Honduras": "hn",
    "Hong Kong": "hk",
    "Hungary": "hu",
    "Iceland": "is",
    "India": "in",
    "Indonesia": "id",
    "Iran": "ir",
    "Iraq": "iq",
    "Ireland": "ie",
    "Isle of Man": "im",
    "Israel": "il",
    "Italy": "it",
    "Jamaica": "jm",
    "Japan": "jp",
    "Jersey": "je",
    "Jordan": "jo",
    "Kazakhstan": "kz",
    "Kenya": "ke",
    "Kiribati": "ki",
    "Kosovo": "xk",
    "Kuwait": "kw",
    "Kyrgyzstan": "kg",
    "Laos": "la",
    "Latvia": "lv",
    "Lebanon": "lb",
    "Lesotho": "ls",
    "Liberia": "lr",
    "Libya": "ly",
    "Liechtenstein": "li",
    "Lithuania": "lt",
    "Luxembourg": "lu",
    "Macau": "mo",
    "Madagascar": "mg",
    "Malawi": "mw",
    "Malaysia": "my",
    "Maldives": "mv",
    "Mali": "ml",
    "Malta": "mt",
    "Marshall Islands": "mh",
    "Martinique": "mq",
    "Mauritania": "mr",
    "Mauritius": "mu",
    "Mayotte": "yt",
    "Mexico": "mx",
    "Moldova": "md",
    "Monaco": "mc",
    "Mongolia": "mn",
    "Montenegro": "me",
    "Montserrat": "ms",
    "Morocco": "ma",
    "Mozambique": "mz",
    "Myanmar": "mm",
    "Namibia": "na",
    "Nauru": "nr",
    "Nepal": "np",
    "Netherlands": "nl",
    "New Caledonia": "nc",
    "New Zealand": "nz",
    "Nicaragua": "ni",
    "Niger": "ne",
    "Nigeria": "ng",
    "Niue": "nu",
    "Norfolk Island": "nf",
    "North Korea": "kp",
    "North Macedonia": "mk",
    "Northern Ireland": "gb-nir",
    "Northern Mariana Islands": "mp",
    "Norway": "no",
    "Oman": "om",
    "Pakistan": "pk",
    "Palau": "pw",
    "Panama": "pa",
    "Papua New Guinea": "pg",
    "Paraguay": "py",
    "Peru": "pe",
    "Philippines": "ph",
    "Pitcairn": "pn",
    "Poland": "pl",
    "Portugal": "pt",
    "Puerto Rico": "pr",
    "Qatar": "qa",
    "Republic of the Congo": "cg",
    "Romania": "ro",
    "Russia": "ru",
    "Rwanda": "rw",
    "Réunion": "re",
    "Saint Barthélemy": "bl",
    "Saint Helena, Ascension and Tristan da Cunha": "sh",
    "Saint Kitts and Nevis": "kn",
    "Saint Lucia": "lc",
    "Saint Martin": "mf",
    "Saint Pierre and Miquelon": "pm",
    "Saint Vincent and the Grenadines": "vc",
    "Samoa": "ws",
    "San Marino": "sm",
    "Sao Tome and Principe": "st",
    "Saudi Arabia": "sa",
    "Scotland": "gb-sct",
    "Senegal": "sn",
    "Serbia": "rs",
    "Seychelles": "sc",
    "Sierra Leone": "sl",
    "Singapore": "sg",
    "Sint Maarten": "sx",
    "Slovakia": "sk",
    "Slovenia": "si",
    "Solomon Islands": "sb",
    "Somalia": "so",
    "South Africa": "za",
    "South Georgia and the South Sandwich Islands": "gs",
    "South Korea": "kr",
    "South Sudan": "ss",
    "Spain": "es",
    "Sri Lanka": "lk",
    "State of Palestine": "ps",
    "Sudan": "sd",
    "Suriname": "sr",
    "Svalbard and Jan Mayen": "sj",
    "Sweden": "se",
    "Switzerland": "ch",
    "Syria": "sy",
    "Taiwan": "tw",
    "Tajikistan": "tj",
    "Tanzania": "tz",
    "Thailand": "th",
    "Timor-Leste": "tl",
    "Togo": "tg",
    "Tokelau": "tk",
    "Tonga": "to",
    "Trinidad and Tobago": "tt",
    "Tunisia": "tn",
    "Turkmenistan": "tm",
    "Turks and Caicos Islands": "tc",
    "Tuvalu": "tv",
    "Türkiye": "tr",
    "Uganda": "ug",
    "Ukraine": "ua",
    "United Arab Emirates": "ae",
    "United Kingdom": "gb",
    "United States Minor Outlying Islands": "um",
    "United States of America": "us",
    "Uruguay": "uy",
    "Uzbekistan": "uz",
    "Vanuatu": "vu",
    "Venezuela": "ve",
    "Vietnam": "vn",
    "Virgin Islands (British)": "vg",
    "Virgin Islands (U.S.)": "vi",
    "Wales": "gb-wls",
    "Wallis and Futuna": "wf",
    "Western Sahara": "eh",
    "Yemen": "ye",
    "Zambia": "zm",
    "Zimbabwe": "zw",}
_ALIASES = {
    "USA": "us", "United States": "us", "Korea Republic": "kr", "Korea": "kr", "Korea DPR": "kp",
    "IR Iran": "ir", "Ivory Coast": "ci", "Cote dIvoire": "ci", "Czechia": "cz", "Turkey": "tr",
    "Cape Verde": "cv", "Cape Verde Islands": "cv", "China PR": "cn", "Congo DR": "cd", "DR Congo": "cd",
    "Congo": "cg", "Macedonia": "mk", "FYR Macedonia": "mk", "Republic of Ireland": "ie",
    "Chinese Taipei": "tw", "Curacao": "cw", "Kyrgyz Republic": "kg", "St Kitts and Nevis": "kn",
    "St Lucia": "lc", "St Vincent and the Grenadines": "vc", "St Vincent": "vc", "Brunei": "bn",
    "Viet Nam": "vn", "Palestine": "ps", "Macao": "mo", "Swaziland": "sz", "East Timor": "tl",
    "Guinea Bissau": "gw", "Sao Tome e Principe": "st", "US Virgin Islands": "vi",
    "British Virgin Islands": "vg", "Kosovo": "xk", "The Gambia": "gm", "Gambia": "gm",
    "Bahamas": "bs", "Laos": "la", "Micronesia": "fm", "Tahiti": "pf", "Holland": "nl",
    "Syria": "sy", "Russia": "ru", "Moldova": "md", "Bolivia": "bo", "Venezuela": "ve",
    "Tanzania": "tz", "Vietnam": "vn", "Northern Ireland": "gb-nir", "England": "gb-eng",
    "Scotland": "gb-sct", "Wales": "gb-wls", "Great Britain": "gb", "UAE": "ae",
}
# "England W", "Spain U21", "Brazil Women", "Japan Olympic": the same country, the same flag.
_SUFFIX = re.compile(r"\s+(w|women|u-?\d{2}|olympic|olympics|b)$", re.I)


def _key(name: str) -> str:
    s = unicodedata.normalize("NFKD", name or "").encode("ascii", "ignore").decode()
    s = _SUFFIX.sub("", s.strip()).replace("&", " and ")
    return re.sub(r"[^a-z0-9]+", "", s.lower())


_BY_KEY = {_key(k): v for k, v in {**_NAMES, **_ALIASES}.items()}


def code_for(name: str | None) -> str | None:
    """The flag for a country's team name, or None when we do not know it."""
    for _ in range(2):
        c = _BY_KEY.get(_key(name or ""))
        if c:
            return c
        name = _SUFFIX.sub("", (name or "").strip())   # "Spain U21 W" -> strip twice
    return None


# Which teams have played an international competition. Asked on every team lookup, so it is kept
# for a minute: a team becomes a country only when a new competition is enabled, and a minute's
# delay in drawing its flag costs nothing.
_TTL = 60.0
_cache: dict = {}


def national_iids(db) -> frozenset:
    key = id(db)
    hit = _cache.get(key)
    now = time.monotonic()
    if hit and now - hit[0] < _TTL:
        return hit[1]
    intl = [lg["iid"] for lg in db.leagues.find({"kind": "international"}, {"_id": 0, "iid": 1})]
    out: set = set()
    if intl:
        for m in db.matches.find({"league_iid": {"$in": intl}}, {"_id": 0, "home_iid": 1, "away_iid": 1}):
            out.update((m.get("home_iid"), m.get("away_iid")))
    out.discard(None)
    val = frozenset(out)
    _cache[key] = (now, val)
    return val


def forget(db=None) -> None:
    """Drop the cache (tests, and after a competition is enabled)."""
    if db is None:
        _cache.clear()
    else:
        _cache.pop(id(db), None)
