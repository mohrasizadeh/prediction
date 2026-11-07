"""site_studio.py -- everything an owner can change about how the site looks and navigates, safely.

Sections (one JSON document each, inside one versioned config):
  brand        name, tagline, logo (light/dark), favicon, share image
  theme        default mode, mode toggle, 25 colour tokens per mode, fonts, scale, radius, density, shadows, motion
  buttons      shape, size, weight, case, shadow, hover, focus ring, style of each variant
  nav          menu items (label, icon, route, who sees it), phone bottom bar, header button
  footer       link columns, social links, legal line (the disclaimer can never be removed)
  seo          title and description templates, share image, robots, redirects
  cookies      banner text and buttons
  home         which blocks show on the home page and in what order
  custom_css   owner only, strictly filtered

How it works
  * Edits go to a DRAFT. Nothing visitors see changes until someone presses Publish.
  * Publish validates everything, compiles the CSS, and saves an immutable VERSION (last 50 kept).
  * Rollback publishes an old version again as a new version. History is never rewritten.
  * Preview: a short-lived signed token lets the front end show the draft (also in a phone browser).
  * Every colour pair that is text on a background is checked for contrast (WCAG 2.2 AA). Failing pairs block Publish.
  * The browser only ever receives compiled CSS built from a fixed list of tokens, never free-form HTML or script.
"""
from __future__ import annotations

import base64
import copy
import hashlib
import hmac
import json
import re
import time
import uuid
from datetime import datetime, timezone

from pymongo import ReturnDocument

import security
import settings_store as S
import textguard

SECTIONS = ("brand", "theme", "buttons", "nav", "footer", "seo", "cookies", "home", "custom_css")
KEEP_VERSIONS = 50
MAX_ASSET_BYTES = 512 * 1024
MAX_ASSETS = 100


class SiteError(Exception):
    """Carries a list of {path, message}. The route turns it into a 422 the editor can show field by field."""
    def __init__(self, problems: list[dict]):
        super().__init__("; ".join(f"{p['path']}: {p['message']}" for p in problems))
        self.problems = problems


def utcnow():
    return datetime.now(timezone.utc)


# ----------------------------------------------------------------------------- defaults
COLOR_TOKENS = ("bg", "surface1", "surface2", "surface3", "border", "borderStrong", "text", "text2", "text3",
                "brand", "onBrand", "accent", "onAccent", "tierStrong", "tierSolid", "tierWatch", "up", "down", "onDown",
                "chart1", "chart2", "chart3", "chart4", "chart5", "chart6")

# Default palette: the owner's seven -- Forest #034737, Sprout #A9FF9B, Stone #979C94,
# Pitch #22281E, Chalk #F4F7F3, White #FFFFFF, Mint #38D996.
#
# The seven are used exactly where they are legible, and the two modes take opposite halves of the
# set. Measured: Forest is 9.92 on Chalk and Mint is 1.69 on it, so Forest carries light mode and
# Mint cannot; Mint is 8.30 on Pitch and Sprout 12.56, so those two carry dark mode. Stone passes
# as small text on the dark surfaces (4.84) and fails on the light ones (2.59), so light mode uses
# it shaded toward Pitch. Every surface and border step between them is a blend of two of the
# seven -- no step is a hue the owner did not choose.
#
# ONE colour is added, and it is worth being plain about why. The seven contain no red, and this
# product needs one: "did not happen" is half of what a tracked forecast says, and a destructive
# admin action has to read as destructive. Green cannot carry that meaning and grey would read as
# "unknown", which already means something else here. #FF8A7A is that red in dark and #A8372B in
# light, both chosen to sit with the greens rather than against them.
#
# There is no amber either, so Watch -- the tier that means "we are not sure yet" -- is Stone. The
# least coloured tier for the least certain claim, which is the right way round, and TierBadge
# draws one, two or three dots so colour is never the only signal.
#
# Every pair in BLOCK_PAIRS and WARN_PAIRS was measured in both modes before this was committed;
# the worst in either mode is 4.37 against a 3.0 bar and 4.84 against a 4.5 bar.
DARK = {"bg": "#22281E", "surface1": "#2A3026", "surface2": "#32382F", "surface3": "#3C4238",
        "border": "#3C4238", "borderStrong": "#575C53",
        "text": "#F4F7F3", "text2": "#DDE0DB", "text3": "#979C94",
        "brand": "#38D996", "onBrand": "#22281E", "accent": "#A9FF9B", "onAccent": "#22281E",
        "tierStrong": "#A9FF9B", "tierSolid": "#38D996", "tierWatch": "#979C94",
        "up": "#38D996", "down": "#FF8A7A", "onDown": "#22281E",
        "chart1": "#38D996", "chart2": "#A9FF9B", "chart3": "#979C94",
        "chart4": "#FF8A7A", "chart5": "#6FBF9B", "chart6": "#F4F7F3"}
LIGHT = {"bg": "#F4F7F3", "surface1": "#FFFFFF", "surface2": "#EBEEEA", "surface3": "#E0E3DE",
         "border": "#D3D7D2", "borderStrong": "#AAAEA7",
         "text": "#22281E", "text2": "#3C4238", "text3": "#62685F",
         "brand": "#034737", "onBrand": "#FFFFFF", "accent": "#A9FF9B", "onAccent": "#22281E",
         "tierStrong": "#1B8962", "tierSolid": "#034737", "tierWatch": "#62685F",
         "up": "#106C4F", "down": "#A8372B", "onDown": "#FFFFFF",
         "chart1": "#034737", "chart2": "#1B8962", "chart3": "#62685F",
         "chart4": "#A8372B", "chart5": "#6FBF9B", "chart6": "#22281E"}

# The palette that was the default before this one: Carbon, Mist, Electric, Violet, Lime, Steel.
# Kept as a preset, the way Apple and Midnight were when they were replaced.
CARBON_DARK = {"bg": "#101114", "surface1": "#18191C", "surface2": "#212224", "surface3": "#2B2C2F",
        "border": "#313235", "borderStrong": "#494A4C",
        "text": "#EEF0F2", "text2": "#C6CBD2", "text3": "#8E97A2",
        "brand": "#6079EE", "onBrand": "#101114", "accent": "#C6F04A", "onAccent": "#101114",
        "tierStrong": "#C6F04A", "tierSolid": "#6079EE", "tierWatch": "#8F6FD6",
        "up": "#C6F04A", "down": "#F2555F", "onDown": "#101114",
        "chart1": "#6079EE", "chart2": "#C6F04A", "chart3": "#8F6FD6",
        "chart4": "#F2555F", "chart5": "#7A838D", "chart6": "#EEF0F2"}
CARBON_LIGHT = {"bg": "#EEF0F2", "surface1": "#FFFFFF", "surface2": "#E4E7EB", "surface3": "#D7DBE0",
         "border": "#D2D6DC", "borderStrong": "#AFB6BF",
         "text": "#101114", "text2": "#2C3238", "text3": "#55606D",
         "brand": "#2547E8", "onBrand": "#EEF0F2", "accent": "#C6F04A", "onAccent": "#101114",
         "tierStrong": "#697F27", "tierSolid": "#2547E8", "tierWatch": "#5F31C4",
         "up": "#697F27", "down": "#BD424A", "onDown": "#EEF0F2",
         "chart1": "#2547E8", "chart2": "#697F27", "chart3": "#5F31C4",
         "chart4": "#BD424A", "chart5": "#55606D", "chart6": "#101114"}

# The "chalk on slate" palette that preceded this one. Kept as a preset, as Apple and Midnight were.
CHALK_DARK = {"bg": "#0D1620", "surface1": "#13202C", "surface2": "#1A2938", "surface3": "#22344A", "border": "#243546",
        "borderStrong": "#38506A", "text": "#E8EEF2", "text2": "#C4D2DC", "text3": "#9FB0BE", "brand": "#E8EEF2",
        "onBrand": "#0D1620", "accent": "#7FD3F2", "onAccent": "#0D1620", "tierStrong": "#35C27E", "tierSolid": "#7FD3F2", "tierWatch": "#E8B23A", "up": "#35C27E",
        "down": "#FF6B6B", "onDown": "#0D1620", "chart1": "#7FD3F2", "chart2": "#35C27E", "chart3": "#E8B23A",
        "chart4": "#FF6B6B", "chart5": "#B9A3F0", "chart6": "#9FB0BE"}
CHALK_LIGHT = {"bg": "#EEF2F5", "surface1": "#FFFFFF", "surface2": "#E7ECF1", "surface3": "#DBE2E9", "border": "#D3DBE3",
         "borderStrong": "#AEBBC7", "text": "#111A22", "text2": "#2E3C47", "text3": "#55646F", "brand": "#111A22",
         "onBrand": "#FFFFFF", "accent": "#7FD3F2", "onAccent": "#111A22", "tierStrong": "#0F7A4A", "tierSolid": "#0B6E92", "tierWatch": "#8A6100", "up": "#0F7A4A",
         "down": "#C0392B", "onDown": "#FFFFFF", "chart1": "#0B6E92", "chart2": "#0F7A4A", "chart3": "#8A6100",
         "chart4": "#C0392B", "chart5": "#5B4AA8", "chart6": "#55646F"}

# The palette that was the default until the v2 pass: Apple Human Interface Guidelines semantic system
# colours. Kept as a preset, the way Midnight was when it was replaced.
APPLE_DARK = {"bg": "#000000", "surface1": "#1C1C1E", "surface2": "#2C2C2E", "surface3": "#3A3A3C", "border": "#38383A",
        "borderStrong": "#545458", "text": "#FFFFFF", "text2": "#EBEBF5", "text3": "#98989F", "brand": "#409CFF",
        "onBrand": "#000000", "accent": "#30D158", "onAccent": "#000000", "tierStrong": "#30D158", "tierSolid": "#64D2FF", "tierWatch": "#FF9F0A", "up": "#30D158",
        "down": "#FF6961", "onDown": "#000000", "chart1": "#409CFF", "chart2": "#30D158", "chart3": "#FF9F0A",
        "chart4": "#FF375F", "chart5": "#5E5CE6", "chart6": "#BF5AF2"}
APPLE_LIGHT = {"bg": "#F2F2F7", "surface1": "#FFFFFF", "surface2": "#F2F2F7", "surface3": "#E5E5EA", "border": "#E5E5EA",
         "borderStrong": "#C7C7CC", "text": "#000000", "text2": "#3C3C43", "text3": "#6C6C70", "brand": "#0066CC",
         "onBrand": "#FFFFFF", "accent": "#30D158", "onAccent": "#000000", "tierStrong": "#1D7A32", "tierSolid": "#0071A4", "tierWatch": "#B25000", "up": "#1D7A32",
         "down": "#D70015", "onDown": "#FFFFFF", "chart1": "#0066CC", "chart2": "#1D7A32", "chart3": "#B25000",
         "chart4": "#D30F45", "chart5": "#5856D6", "chart6": "#8944AB"}

# The previous default ("Midnight"): calm dark navy with an indigo accent. Kept as a preset.
MIDNIGHT_DARK = {"bg": "#0A0E17", "surface1": "#111827", "surface2": "#182033", "surface3": "#212B42", "border": "#243049",
        "borderStrong": "#33415F", "text": "#E9EEF7", "text2": "#A3AFC6", "text3": "#75819B", "brand": "#7C83FF",
        "onBrand": "#0A0E17", "accent": "#A3E635", "onAccent": "#0A0E17", "tierStrong": "#2DD4BF", "tierSolid": "#60A5FA", "tierWatch": "#FBBF24", "up": "#34D399",
        "down": "#F87171", "onDown": "#0A0E17", "chart1": "#7C83FF", "chart2": "#2DD4BF", "chart3": "#FBBF24",
        "chart4": "#F472B6", "chart5": "#60A5FA", "chart6": "#A3E635"}
MIDNIGHT_LIGHT = {"bg": "#F5F7FB", "surface1": "#FFFFFF", "surface2": "#F0F3F9", "surface3": "#E6EBF4", "border": "#E2E8F2",
         "borderStrong": "#C9D2E3", "text": "#0B1220", "text2": "#475269", "text3": "#6B7690", "brand": "#4F46E5",
         "onBrand": "#FFFFFF", "accent": "#A3E635", "onAccent": "#0B1220", "tierStrong": "#0D9488", "tierSolid": "#2563EB", "tierWatch": "#B45309", "up": "#059669",
         "down": "#DC2626", "onDown": "#FFFFFF", "chart1": "#4F46E5", "chart2": "#0D9488", "chart3": "#B45309",
         "chart4": "#DB2777", "chart5": "#2563EB", "chart6": "#4D7C0F"}

# Fonts the owner can pick. `file` is the self-hosted variable font the builder copies into /public/fonts/
# (npm package @fontsource-variable/<slug>, latin subset). Nothing is loaded from Google at runtime.
FONTS = {
    "system": {"label": "System default (San Francisco on Apple devices)", "stack": "-apple-system,BlinkMacSystemFont,system-ui,'Segoe UI',Roboto,sans-serif", "file": None, "kind": "sans"},
    # The only face here with a WIDTH axis, which is what the v2 type scale uses to carry hierarchy
    # from a condensed data label to an extended headline without a second family (docs/redesign/v2).
    "archivo": {"label": "Archivo", "stack": "'Archivo v2',system-ui,sans-serif", "file": "archivo-latin-var.woff2", "kind": "sans"},
    "inter": {"label": "Inter", "stack": "'Inter',system-ui,sans-serif", "file": "inter-latin-wght-normal.woff2", "kind": "sans"},
    "manrope": {"label": "Manrope", "stack": "'Manrope',system-ui,sans-serif", "file": "manrope-latin-wght-normal.woff2", "kind": "sans"},
    "dm-sans": {"label": "DM Sans", "stack": "'DM Sans',system-ui,sans-serif", "file": "dm-sans-latin-wght-normal.woff2", "kind": "sans"},
    "plus-jakarta-sans": {"label": "Plus Jakarta Sans", "stack": "'Plus Jakarta Sans',system-ui,sans-serif", "file": "plus-jakarta-sans-latin-wght-normal.woff2", "kind": "sans"},
    "nunito": {"label": "Nunito", "stack": "'Nunito',system-ui,sans-serif", "file": "nunito-latin-wght-normal.woff2", "kind": "sans"},
    "work-sans": {"label": "Work Sans", "stack": "'Work Sans',system-ui,sans-serif", "file": "work-sans-latin-wght-normal.woff2", "kind": "sans"},
    "source-sans-3": {"label": "Source Sans 3", "stack": "'Source Sans 3',system-ui,sans-serif", "file": "source-sans-3-latin-wght-normal.woff2", "kind": "sans"},
    "open-sans": {"label": "Open Sans", "stack": "'Open Sans',system-ui,sans-serif", "file": "open-sans-latin-wght-normal.woff2", "kind": "sans"},
    "roboto": {"label": "Roboto", "stack": "'Roboto',system-ui,sans-serif", "file": "roboto-latin-wght-normal.woff2", "kind": "sans"},
    "space-grotesk": {"label": "Space Grotesk", "stack": "'Space Grotesk',system-ui,sans-serif", "file": "space-grotesk-latin-wght-normal.woff2", "kind": "sans"},
    "outfit": {"label": "Outfit", "stack": "'Outfit',system-ui,sans-serif", "file": "outfit-latin-wght-normal.woff2", "kind": "sans"},
    "merriweather": {"label": "Merriweather", "stack": "'Merriweather',Georgia,serif", "file": "merriweather-latin-wght-normal.woff2", "kind": "serif"},
    "playfair-display": {"label": "Playfair Display", "stack": "'Playfair Display',Georgia,serif", "file": "playfair-display-latin-wght-normal.woff2", "kind": "serif"},
    "lora": {"label": "Lora", "stack": "'Lora',Georgia,serif", "file": "lora-latin-wght-normal.woff2", "kind": "serif"},
}
ICONS = ("calendar", "search", "sparkles", "users", "user", "shield", "trophy", "chart", "bar-chart", "list", "star", "heart",
         "bookmark", "bell", "book", "info", "home", "settings", "credit-card", "target", "flag", "map", "mail", "help-circle",
         "grid", "layers", "activity", "trending-up", "clock", "tag", "gift", "zap", "compass", "newspaper", "more")
RADIUS = {"sharp": (4, 6, 8), "default": (8, 12, 16), "round": (12, 18, 26)}
AUDIENCES = ("all", "signed_out", "signed_in", "free", "paid")
HOME_BLOCKS = ("today_fixtures", "top_insights", "finder_shortcut", "track_record", "following", "learn", "newsletter")
SOCIALS = ("x", "instagram", "facebook", "youtube", "tiktok", "linkedin", "github", "discord", "telegram", "reddit")
BUTTON_STYLES = ("solid", "outline", "soft", "ghost")
VARIANTS = ("primary", "secondary", "ghost", "danger")


def defaults() -> dict:
    return copy.deepcopy({
        "brand": {"name": "Forecast", "tagline": "Football forecasts with the reasons shown.", "logo_light": "", "logo_dark": "",
                  "favicon": "", "og_image": ""},
        "theme": {"default_mode": "system", "allow_toggle": True,
                  "colors": {"dark": DARK, "light": LIGHT},
                  "font_body": "archivo", "font_heading": "archivo", "base_px": 16, "heading_weight": 600,
                  "radius": "default", "density": "comfortable", "shadows": "none", "motion": "full", "max_width_px": 1200},
        "buttons": {"radius_px": 999, "height_px": {"sm": 36, "md": 44, "lg": 52}, "font_weight": 600, "uppercase": False,
                    "shadow": "none", "hover": "darken", "press": True, "focus_ring_px": 3,
                    "variants": {"primary": "solid", "secondary": "soft", "ghost": "ghost", "danger": "solid"}},
        "nav": {"items": [
            {"id": "today", "label": "Today", "icon": "calendar", "route": "/", "enabled": True, "audience": "all", "badge": ""},
            {"id": "finder", "label": "Finder", "icon": "search", "route": "/finder", "enabled": True, "audience": "all", "badge": ""},
            {"id": "insights", "label": "Insights", "icon": "sparkles", "route": "/insights", "enabled": True, "audience": "all", "badge": ""},
            {"id": "teams", "label": "Teams", "icon": "users", "route": "/teams", "enabled": True, "audience": "all", "badge": ""},
            {"id": "following", "label": "Following", "icon": "star", "route": "/following", "enabled": True, "audience": "signed_in", "badge": ""},
            {"id": "learn", "label": "Learn", "icon": "book", "route": "/learn", "enabled": True, "audience": "all", "badge": ""},
            {"id": "pricing", "label": "Plans", "icon": "credit-card", "route": "/pricing", "enabled": True, "audience": "signed_out", "badge": ""},
        ], "mobile_tabs": ["today", "finder", "insights", "following"], "mobile_more": True, "desktop_layout": "rail",
            "show_search": True, "header_cta": {"enabled": True, "label": "Sign up free", "route": "/signup", "audience": "signed_out"}},
        "footer": {"columns": [
            {"title": "Product", "links": [{"label": "Today", "route": "/"}, {"label": "Forecast Finder", "route": "/finder"}, {"label": "Track record", "route": "/track-record"}]},
            {"title": "Company", "links": [{"label": "About", "route": "/about"}, {"label": "Contact", "route": "/contact"}]},
            {"title": "Legal", "links": [{"label": "Terms", "route": "/terms"}, {"label": "Privacy", "route": "/privacy"}]},
        ], "social": [], "legal_line": "", "show_data_credit": True},
        "seo": {"title_template": "{name}: {team1} vs {team2} forecasts", "description_template": "Forecasts, tactics and the reasons behind them for {team1} vs {team2}.",
                "og_image": "", "robots_index": True, "sitemap": True, "redirects": []},
        "cookies": {"banner": True, "text": "We count visits with no cookies and no ads. Optional tools only run if you allow them.",
                    "accept_label": "Allow optional", "reject_label": "No thanks", "policy_route": "/privacy"},
        "home": {"blocks": [{"id": b, "enabled": b in ("today_fixtures", "top_insights", "finder_shortcut", "track_record", "newsletter")} for b in HOME_BLOCKS]},
        "custom_css": {"css": ""},
    })


# ----------------------------------------------------------------------------- colour maths
_HEX = re.compile(r"^#[0-9A-Fa-f]{6}$")


def _lum(h: str) -> float:
    def ch(i):
        v = int(h[i:i + 2], 16) / 255
        return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4
    return 0.2126 * ch(1) + 0.7152 * ch(3) + 0.0722 * ch(5)


def contrast(a: str, b: str) -> float:
    la, lb = _lum(a), _lum(b)
    hi, lo = max(la, lb), min(la, lb)
    return (hi + 0.05) / (lo + 0.05)


# pairs that must pass 4.5:1 (text on its background) and pairs that only warn
BLOCK_PAIRS = (("text", "bg"), ("text", "surface1"), ("text", "surface2"), ("text2", "surface1"), ("onBrand", "brand"),
               ("onAccent", "accent"), ("onDown", "down"))
# icons, dots and large numbers need 3:1; small text needs 4.5:1
WARN_PAIRS = ((("text3", "surface1"), 4.5), (("brand", "bg"), 3.0), (("up", "surface1"), 3.0), (("down", "surface1"), 3.0),
              (("tierStrong", "surface1"), 3.0), (("tierSolid", "surface1"), 3.0), (("tierWatch", "surface1"), 3.0))


# ----------------------------------------------------------------------------- validation helpers
def _p(problems, path, msg):
    problems.append({"path": path, "message": msg})


def _str(v, lo, hi):
    return isinstance(v, str) and lo <= len(v.strip()) <= hi


def valid_route(r) -> bool:
    """Internal path (/a/b), or https URL. Never javascript:, data:, protocol-relative //, or spaces."""
    if not isinstance(r, str) or not r or len(r) > 300 or re.search(r"[\s<>\"'\\]", r):
        return False
    if r.startswith("/"):
        return not r.startswith("//")
    return r.startswith("https://") and len(r) > 12


def valid_image(u) -> bool:
    if u == "":
        return True
    if not isinstance(u, str) or len(u) > 400 or re.search(r"[\s<>\"'\\]", u):
        return False
    return (u.startswith("/") and not u.startswith("//")) or u.startswith("https://")


def _intr(v, lo, hi):
    return isinstance(v, int) and not isinstance(v, bool) and lo <= v <= hi


def _merge_known(base: dict, new: dict, path: str, problems: list) -> dict:
    """Reject unknown keys so a typo never silently does nothing."""
    for k in new:
        if k not in base:
            _p(problems, f"{path}.{k}", "Unknown field.")
    return {k: new.get(k, base[k]) for k in base}


def _validate_brand(d, problems):
    base = defaults()["brand"]
    d = _merge_known(base, d, "brand", problems)
    if not _str(d["name"], 1, 40): _p(problems, "brand.name", "1 to 40 characters.")
    if not isinstance(d["tagline"], str) or len(d["tagline"]) > 120: _p(problems, "brand.tagline", "Up to 120 characters.")
    for k in ("logo_light", "logo_dark", "favicon", "og_image"):
        if not valid_image(d[k]): _p(problems, f"brand.{k}", "Use an uploaded image (starts with /) or an https address.")
    return d


def _validate_theme(d, problems, warnings):
    base = defaults()["theme"]
    d = _merge_known(base, d, "theme", problems)
    if d["default_mode"] not in ("light", "dark", "system"): _p(problems, "theme.default_mode", "light, dark or system.")
    if not isinstance(d["allow_toggle"], bool): _p(problems, "theme.allow_toggle", "true or false.")
    cols = d["colors"]
    if not isinstance(cols, dict) or set(cols) != {"dark", "light"}:
        _p(problems, "theme.colors", "Needs both 'dark' and 'light'.")
    else:
        for mode in ("dark", "light"):
            c = cols[mode]
            if not isinstance(c, dict):
                _p(problems, f"theme.colors.{mode}", "Must be an object."); continue
            for t in c:
                if t not in COLOR_TOKENS: _p(problems, f"theme.colors.{mode}.{t}", "Unknown colour token.")
            for t in COLOR_TOKENS:
                if t not in c: _p(problems, f"theme.colors.{mode}.{t}", "Missing.")
                elif not isinstance(c[t], str) or not _HEX.match(c[t]): _p(problems, f"theme.colors.{mode}.{t}", "Use a colour like #1A2B3C.")
            if not any(p["path"].startswith(f"theme.colors.{mode}") for p in problems):
                for a, b in BLOCK_PAIRS:
                    r = contrast(c[a], c[b])
                    if r < 4.5: _p(problems, f"theme.colors.{mode}.{a}", f"{a} on {b} is {r:.1f}:1. Text needs at least 4.5:1.")
                for (a, b), need in WARN_PAIRS:
                    r = contrast(c[a], c[b])
                    if r < need: warnings.append({"path": f"theme.colors.{mode}.{a}", "message": f"{a} on {b} is {r:.1f}:1. Aim for {need}:1 or more."})
    for k in ("font_body", "font_heading"):
        if d[k] not in FONTS: _p(problems, f"theme.{k}", "Pick a font from the list.")
    if not _intr(d["base_px"], 14, 18): _p(problems, "theme.base_px", "14 to 18.")
    if not _intr(d["heading_weight"], 500, 800): _p(problems, "theme.heading_weight", "500 to 800.")
    if d["radius"] not in RADIUS: _p(problems, "theme.radius", "sharp, default or round.")
    if d["density"] not in ("comfortable", "compact"): _p(problems, "theme.density", "comfortable or compact.")
    if d["shadows"] not in ("none", "soft", "strong"): _p(problems, "theme.shadows", "none, soft or strong.")
    if d["motion"] not in ("full", "reduced"): _p(problems, "theme.motion", "full or reduced.")
    if not _intr(d["max_width_px"], 960, 1600): _p(problems, "theme.max_width_px", "960 to 1600.")
    return d


def _validate_buttons(d, problems, warnings):
    base = defaults()["buttons"]
    d = _merge_known(base, d, "buttons", problems)
    if not _intr(d["radius_px"], 0, 999): _p(problems, "buttons.radius_px", "0 to 999.")
    h = d["height_px"]
    if not isinstance(h, dict) or set(h) != {"sm", "md", "lg"} or not all(_intr(h[k], 28, 64) for k in h if k in ("sm", "md", "lg")):
        _p(problems, "buttons.height_px", "sm, md and lg, each 28 to 64.")
    elif h["md"] < 40: _p(problems, "buttons.height_px.md", "The normal button must be at least 40 px high (44 px on touch screens is added for you).")
    elif not h["sm"] <= h["md"] <= h["lg"]: _p(problems, "buttons.height_px", "Sizes must grow: sm, md, lg.")
    if not _intr(d["font_weight"], 400, 800): _p(problems, "buttons.font_weight", "400 to 800.")
    for k in ("uppercase", "press"):
        if not isinstance(d[k], bool): _p(problems, f"buttons.{k}", "true or false.")
    if d["shadow"] not in ("none", "soft"): _p(problems, "buttons.shadow", "none or soft.")
    if d["hover"] not in ("lift", "darken", "none"): _p(problems, "buttons.hover", "lift, darken or none.")
    if not _intr(d["focus_ring_px"], 2, 5): _p(problems, "buttons.focus_ring_px", "2 to 5. The keyboard focus ring cannot be turned off.")
    v = d["variants"]
    if not isinstance(v, dict) or set(v) != set(VARIANTS) or any(x not in BUTTON_STYLES for x in v.values()):
        _p(problems, "buttons.variants", f"Each of {', '.join(VARIANTS)} needs a style: {', '.join(BUTTON_STYLES)}.")
    elif v["primary"] == "ghost": _p(problems, "buttons.variants.primary", "The main button cannot be a ghost button. People must be able to see it.")
    return d


def _validate_nav(d, problems, warnings):
    base = defaults()["nav"]
    d = _merge_known(base, d, "nav", problems)
    items = d["items"]
    ids: set[str] = set()
    if not isinstance(items, list) or not 1 <= len(items) <= 14:
        _p(problems, "nav.items", "1 to 14 items.")
        items = []
    for i, it in enumerate(items):
        pth = f"nav.items[{i}]"
        if not isinstance(it, dict): _p(problems, pth, "Must be an object."); continue
        for k in it:
            if k not in ("id", "label", "icon", "route", "enabled", "audience", "badge"): _p(problems, f"{pth}.{k}", "Unknown field.")
        if not isinstance(it.get("id"), str) or not re.fullmatch(r"[a-z0-9-]{1,24}", it.get("id", "")): _p(problems, f"{pth}.id", "a-z, 0-9 and dashes, up to 24.")
        elif it["id"] in ids: _p(problems, f"{pth}.id", "Used twice.")
        else: ids.add(it["id"])
        if not _str(it.get("label"), 1, 20): _p(problems, f"{pth}.label", "1 to 20 characters.")
        if it.get("icon") not in ICONS: _p(problems, f"{pth}.icon", "Pick an icon from the list.")
        if not valid_route(it.get("route")): _p(problems, f"{pth}.route", "Use /path or an https address.")
        if not isinstance(it.get("enabled"), bool): _p(problems, f"{pth}.enabled", "true or false.")
        if it.get("audience") not in AUDIENCES: _p(problems, f"{pth}.audience", f"One of {', '.join(AUDIENCES)}.")
        if not isinstance(it.get("badge", ""), str) or len(it.get("badge", "")) > 8: _p(problems, f"{pth}.badge", "Up to 8 characters, for example 'New'.")
    tabs = d["mobile_tabs"]
    if not isinstance(tabs, list) or not 2 <= len(tabs) <= 4:
        _p(problems, "nav.mobile_tabs", "Pick 2 to 4 items for the bottom bar. A 5th slot is the 'More' button.")
    else:
        for t in tabs:
            it = next((x for x in items if isinstance(x, dict) and x.get("id") == t), None)
            if it is None: _p(problems, "nav.mobile_tabs", f"'{t}' is not a menu item.")
            elif not it.get("enabled"): _p(problems, "nav.mobile_tabs", f"'{t}' is switched off.")
        if len(set(tabs)) != len(tabs): _p(problems, "nav.mobile_tabs", "An item is listed twice.")
    if not isinstance(d["mobile_more"], bool): _p(problems, "nav.mobile_more", "true or false.")
    if isinstance(items, list) and isinstance(tabs, list):
        left = [x for x in items if isinstance(x, dict) and x.get("enabled") and x.get("id") not in tabs]
        if left and not d["mobile_more"]: warnings.append({"path": "nav.mobile_more", "message": f"{len(left)} enabled item(s) cannot be reached on phones without the More button."})
    if d["desktop_layout"] not in ("rail", "top"): _p(problems, "nav.desktop_layout", "rail or top.")
    if not isinstance(d["show_search"], bool): _p(problems, "nav.show_search", "true or false.")
    c = d["header_cta"]
    if not isinstance(c, dict) or set(c) != {"enabled", "label", "route", "audience"}: _p(problems, "nav.header_cta", "Needs enabled, label, route, audience.")
    else:
        if not isinstance(c["enabled"], bool): _p(problems, "nav.header_cta.enabled", "true or false.")
        if not _str(c["label"], 1, 24): _p(problems, "nav.header_cta.label", "1 to 24 characters.")
        if not valid_route(c["route"]): _p(problems, "nav.header_cta.route", "Use /path or an https address.")
        if c["audience"] not in AUDIENCES: _p(problems, "nav.header_cta.audience", f"One of {', '.join(AUDIENCES)}.")
    return d


def _validate_footer(d, problems, warnings):
    base = defaults()["footer"]
    d = _merge_known(base, d, "footer", problems)
    cols = d["columns"]
    if not isinstance(cols, list) or len(cols) > 5: _p(problems, "footer.columns", "Up to 5 columns."); cols = []
    all_routes = []
    for i, c in enumerate(cols):
        if not isinstance(c, dict) or set(c) != {"title", "links"}: _p(problems, f"footer.columns[{i}]", "Needs title and links."); continue
        if not _str(c["title"], 1, 24): _p(problems, f"footer.columns[{i}].title", "1 to 24 characters.")
        if not isinstance(c["links"], list) or len(c["links"]) > 8: _p(problems, f"footer.columns[{i}].links", "Up to 8 links."); continue
        for j, l in enumerate(c["links"]):
            if not isinstance(l, dict) or set(l) != {"label", "route"}: _p(problems, f"footer.columns[{i}].links[{j}]", "Needs label and route."); continue
            if not _str(l["label"], 1, 30): _p(problems, f"footer.columns[{i}].links[{j}].label", "1 to 30 characters.")
            if not valid_route(l["route"]): _p(problems, f"footer.columns[{i}].links[{j}].route", "Use /path or an https address.")
            else: all_routes.append(l["route"])
    soc = d["social"]
    if not isinstance(soc, list) or len(soc) > 8: _p(problems, "footer.social", "Up to 8 links."); soc = []
    for i, s in enumerate(soc):
        if not isinstance(s, dict) or set(s) != {"kind", "url"} or s["kind"] not in SOCIALS or not (isinstance(s["url"], str) and s["url"].startswith("https://") and len(s["url"]) < 300 and not re.search(r"[\s<>\"']", s["url"])):
            _p(problems, f"footer.social[{i}]", f"kind ({', '.join(SOCIALS)}) and an https url.")
    if not isinstance(d["legal_line"], str) or len(d["legal_line"]) > 200: _p(problems, "footer.legal_line", "Up to 200 characters.")
    if not isinstance(d["show_data_credit"], bool): _p(problems, "footer.show_data_credit", "true or false.")
    for need in ("/terms", "/privacy"):
        if need not in all_routes: warnings.append({"path": "footer.columns", "message": f"No link to {need}. Most payment and e-mail providers expect one."})
    return d


def _validate_seo(d, problems, warnings):
    base = defaults()["seo"]
    d = _merge_known(base, d, "seo", problems)
    for k, hi in (("title_template", 120), ("description_template", 300)):
        if not _str(d[k], 1, hi): _p(problems, f"seo.{k}", f"1 to {hi} characters.")
        else:
            bad = set(re.findall(r"\{(\w+)\}", d[k])) - {"name", "team1", "team2", "page", "player", "league"}
            if bad: _p(problems, f"seo.{k}", f"Unknown placeholder: {', '.join(sorted(bad))}.")
    if not valid_image(d["og_image"]): _p(problems, "seo.og_image", "Use an uploaded image or an https address.")
    for k in ("robots_index", "sitemap"):
        if not isinstance(d[k], bool): _p(problems, f"seo.{k}", "true or false.")
    if d["robots_index"] is False: warnings.append({"path": "seo.robots_index", "message": "Search engines are told NOT to index the site."})
    rd = d["redirects"]
    if not isinstance(rd, list) or len(rd) > 200: _p(problems, "seo.redirects", "Up to 200 redirects."); rd = []
    seen = {}
    for i, r in enumerate(rd):
        if not isinstance(r, dict) or set(r) != {"from", "to", "code"}: _p(problems, f"seo.redirects[{i}]", "Needs from, to, code."); continue
        if not (isinstance(r["from"], str) and re.fullmatch(r"/[A-Za-z0-9/_\-.]{0,200}", r["from"])): _p(problems, f"seo.redirects[{i}].from", "A path like /old-page.")
        elif r["from"] in seen: _p(problems, f"seo.redirects[{i}].from", "Already redirected above.")
        else: seen[r["from"]] = r["to"]
        if not valid_route(r["to"]): _p(problems, f"seo.redirects[{i}].to", "Use /path or an https address.")
        if r["code"] not in (301, 302): _p(problems, f"seo.redirects[{i}].code", "301 or 302.")
        if r["from"] == r["to"]: _p(problems, f"seo.redirects[{i}]", "Redirects to itself.")
    for a, b in seen.items():                     # loops: a -> b -> a
        if seen.get(b) == a: _p(problems, "seo.redirects", f"{a} and {b} send people round in a circle.")
    for a in seen:
        if a.startswith("/admin") or a.startswith("/api"): _p(problems, "seo.redirects", f"{a} cannot be redirected.")
    return d


def _validate_cookies(d, problems, warnings):
    base = defaults()["cookies"]
    d = _merge_known(base, d, "cookies", problems)
    if not isinstance(d["banner"], bool): _p(problems, "cookies.banner", "true or false.")
    if not _str(d["text"], 1, 240): _p(problems, "cookies.text", "1 to 240 characters.")
    if not _str(d["accept_label"], 1, 24): _p(problems, "cookies.accept_label", "1 to 24 characters.")
    if not _str(d["reject_label"], 1, 24): _p(problems, "cookies.reject_label", "A 'no' button is required, 1 to 24 characters.")
    if not valid_route(d["policy_route"]): _p(problems, "cookies.policy_route", "Use /path.")
    return d


def _validate_home(d, problems, warnings):
    base = defaults()["home"]
    d = _merge_known(base, d, "home", problems)
    bl = d["blocks"]
    if not isinstance(bl, list) or not bl: _p(problems, "home.blocks", "Needs at least one block."); return d
    ids = []
    for i, b in enumerate(bl):
        if not isinstance(b, dict) or set(b) != {"id", "enabled"} or b["id"] not in HOME_BLOCKS or not isinstance(b["enabled"], bool):
            _p(problems, f"home.blocks[{i}]", f"id one of {', '.join(HOME_BLOCKS)} and enabled true/false.")
        else: ids.append(b["id"])
    if len(set(ids)) != len(ids): _p(problems, "home.blocks", "A block is listed twice.")
    if not any(isinstance(b, dict) and b.get("enabled") for b in bl): _p(problems, "home.blocks", "Switch at least one block on.")
    return d


_CSS_BAD = re.compile(r"@import|@charset|@namespace|@font-face|expression\s*\(|behavior\s*:|-moz-binding|javascript:|vbscript:|[<>]|\\0|\\00|@property", re.I)
_CSS_URL = re.compile(r"url\(\s*(['\"]?)([^)'\"]*)\1\s*\)", re.I)


def clean_css(css: str) -> str:
    """Owner-only free CSS. Blocks imports, scripts, external urls and font loading. Returns the css or raises ValueError."""
    if len(css) > 20000: raise ValueError("Custom CSS is limited to 20,000 characters.")
    if _CSS_BAD.search(css): raise ValueError("Custom CSS cannot use @import, @font-face, scripts, angle brackets or other unsafe parts.")
    if css.count("{") != css.count("}"): raise ValueError("Custom CSS has unbalanced braces.")
    for m in _CSS_URL.finditer(css):
        u = m.group(2).strip()
        if not (u.startswith("/") and not u.startswith("//")): raise ValueError("Custom CSS can only use url() with a path on this site, like url(/images/bg.png).")
    return css


def _validate_custom_css(d, problems, warnings):
    base = defaults()["custom_css"]
    d = _merge_known(base, d, "custom_css", problems)
    if not isinstance(d["css"], str): _p(problems, "custom_css.css", "Must be text."); return d
    try:
        clean_css(d["css"])
    except ValueError as e:
        _p(problems, "custom_css.css", str(e))
    return d


_VALID = {"brand": lambda d, p, w: _validate_brand(d, p), "theme": _validate_theme, "buttons": _validate_buttons, "nav": _validate_nav,
          "footer": _validate_footer, "seo": _validate_seo, "cookies": _validate_cookies, "home": _validate_home,
          "custom_css": _validate_custom_css}


def validate_section(section: str, data) -> tuple[dict, list]:
    """Returns (clean section, warnings). Raises SiteError with every problem found."""
    if section not in SECTIONS:
        raise SiteError([{"path": section, "message": "Unknown section."}])
    if not isinstance(data, dict):
        raise SiteError([{"path": section, "message": "Must be an object."}])
    problems: list = []
    warnings: list = []
    clean = _VALID[section](copy.deepcopy(data), problems, warnings)
    if section != "custom_css" and not problems:
        bad = textguard.find(clean)
        if bad: _p(problems, section, f"These words are not allowed on the site: {', '.join(bad)}.")
    if problems:
        raise SiteError(problems)
    return clean, warnings


def validate_all(data: dict) -> list:
    """Whole-document check (used by Publish). Returns warnings or raises SiteError."""
    problems: list = []
    warnings: list = []
    for s in SECTIONS:
        try:
            _, w = validate_section(s, data.get(s))
            warnings += w
        except SiteError as e:
            problems += e.problems
    if problems:
        raise SiteError(problems)
    return warnings


# ----------------------------------------------------------------------------- CSS
def _css_vars(c: dict) -> str:
    return ";".join(f"--{re.sub(r'([A-Z])', lambda m: '-' + m.group(1).lower(), k)}:{v}" for k, v in c.items())


def compile_css(data: dict) -> str:
    """Builds the CSS the browser loads. Only whitelisted tokens and numbers go in, so nothing the owner types can break out."""
    t, b = data["theme"], data["buttons"]
    dark, light = _css_vars(t["colors"]["dark"]), _css_vars(t["colors"]["light"])
    mode = t["default_mode"]
    rs, rm, rl = RADIUS[t["radius"]]
    body, head = FONTS[t["font_body"]], FONTS[t["font_heading"]]
    shadow = {"none": ("none", "none"), "soft": ("0 1px 2px rgba(11,18,32,.06),0 8px 24px rgba(11,18,32,.06)", "0 1px 0 rgba(255,255,255,.03) inset,0 8px 24px rgba(0,0,0,.35)"),
              "strong": ("0 2px 4px rgba(11,18,32,.10),0 14px 36px rgba(11,18,32,.14)", "0 1px 0 rgba(255,255,255,.04) inset,0 14px 40px rgba(0,0,0,.55)")}[t["shadows"]]
    out = [f":root{{--font-body:{body['stack']};--font-heading:{head['stack']};--base-px:{t['base_px']}px;--heading-weight:{t['heading_weight']};"
           f"--radius-sm:{rs}px;--radius-md:{rm}px;--radius-lg:{rl}px;--max-width:{t['max_width_px']}px;"
           f"--row-h:{44 if t['density'] == 'comfortable' else 36}px;--btn-radius:{b['radius_px']}px;--btn-h-sm:{b['height_px']['sm']}px;"
           f"--btn-h-md:{b['height_px']['md']}px;--btn-h-lg:{b['height_px']['lg']}px;--btn-weight:{b['font_weight']};"
           f"--btn-case:{'uppercase' if b['uppercase'] else 'none'};--btn-ring:{b['focus_ring_px']}px;"
           f"--btn-shadow:{'0 1px 2px rgba(0,0,0,.25)' if b['shadow'] == 'soft' else 'none'};--tab-h:64px;--header-h:56px}}"]
    if mode == "dark":
        out.append(f":root{{{dark};--card-shadow:{shadow[1]};color-scheme:dark}}")
        out.append(f':root[data-theme="light"]{{{light};--card-shadow:{shadow[0]};color-scheme:light}}')
    elif mode == "light":
        out.append(f":root{{{light};--card-shadow:{shadow[0]};color-scheme:light}}")
        out.append(f':root[data-theme="dark"]{{{dark};--card-shadow:{shadow[1]};color-scheme:dark}}')
    else:
        out.append(f":root{{{light};--card-shadow:{shadow[0]};color-scheme:light}}")
        out.append(f'@media (prefers-color-scheme:dark){{:root:not([data-theme="light"]){{{dark};--card-shadow:{shadow[1]};color-scheme:dark}}}}')
        out.append(f':root[data-theme="dark"]{{{dark};--card-shadow:{shadow[1]};color-scheme:dark}}')
    out.append("html{font-size:var(--base-px)}body{font-family:var(--font-body);background:var(--bg);color:var(--text)}"
               "h1,h2,h3,h4{font-family:var(--font-heading);font-weight:var(--heading-weight)}")
    out.append(".btn{display:inline-flex;align-items:center;justify-content:center;gap:8px;min-height:var(--btn-h-md);padding:0 18px;"
               "border-radius:var(--btn-radius);font-weight:var(--btn-weight);text-transform:var(--btn-case);box-shadow:var(--btn-shadow);"
               "border:1px solid transparent;cursor:pointer;transition:transform .15s,filter .15s,background .15s}"
               ".btn--sm{min-height:var(--btn-h-sm);padding:0 12px}.btn--lg{min-height:var(--btn-h-lg);padding:0 24px}"
               "@media (pointer:coarse){.btn{min-height:max(var(--btn-h-md),44px)}.btn--sm{min-height:max(var(--btn-h-sm),44px)}}"
               ".btn:focus-visible{outline:var(--btn-ring) solid var(--brand);outline-offset:2px}.btn[disabled]{opacity:.5;cursor:not-allowed}")
    srcs = {"primary": ("brand", "on-brand"), "secondary": ("text", "on-brand"), "ghost": ("text", "on-brand"), "danger": ("down", "on-down")}
    for v, style in b["variants"].items():
        tok, on = srcs[v]
        if v == "secondary" and style == "solid":
            rule = "background:var(--surface3);color:var(--text);border-color:var(--border-strong)"
        elif style == "solid":
            rule = f"background:var(--{tok});color:var(--{on});border-color:var(--{tok})"
        elif style == "outline":
            rule = f"background:transparent;color:var(--{tok});border-color:var(--{tok})"
        elif style == "soft":
            rule = f"background:color-mix(in srgb,var(--{tok}) 14%,transparent);color:var(--{tok});border-color:transparent"
        else:
            rule = f"background:transparent;color:var(--{tok});border-color:transparent"
        out.append(f".btn--{v}{{{rule}}}")
    if b["hover"] == "lift":
        out.append(".btn:hover:not([disabled]){transform:translateY(-1px);filter:brightness(1.05)}")
    elif b["hover"] == "darken":
        out.append(".btn:hover:not([disabled]){filter:brightness(.92)}")
    if b["press"]:
        out.append(".btn:active:not([disabled]){transform:scale(.98)}")
    if t["motion"] == "reduced":
        out.append("*,*::before,*::after{animation-duration:.01ms!important;transition-duration:.01ms!important}")
    else:
        out.append("@media (prefers-reduced-motion:reduce){*,*::before,*::after{animation-duration:.01ms!important;transition-duration:.01ms!important}}")
    css = "".join(out)
    extra = data["custom_css"]["css"].strip()
    if extra:
        css += "@layer custom{" + extra + "}"
    return css


def font_faces(data: dict) -> list[dict]:
    """The @font-face the front end needs. Only fonts in use. Files live at /fonts/<file> (self-hosted)."""
    t = data["theme"]
    out, seen = [], set()
    for k in (t["font_body"], t["font_heading"]):
        f = FONTS[k]
        if f["file"] and k not in seen:
            seen.add(k)
            out.append({"slug": k, "family": f["label"], "url": f"/fonts/{f['file']}", "weight": "100 900", "display": "swap"})
    return out


# ----------------------------------------------------------------------------- presets
def _preset(label, desc, mode, dark=None, light=None, radius="default", buttons=None):
    return {"label": label, "description": desc, "default_mode": mode, "dark": dark or {}, "light": light or {}, "radius": radius, "buttons": buttons or {}}


PRESETS = {
    "forest": _preset("Forest", "The default. Forest and Chalk by day, Pitch and Mint by night.", "system"),
    "carbon": _preset("Carbon", "The previous default. Carbon and Mist, with Electric, Violet and Lime.", "system",
                      dark=CARBON_DARK, light=CARBON_LIGHT),
    "chalk": _preset("Chalk", "Chalk on slate: a hued blue slate, chalk ink, and colour reserved for meaning.", "system",
                     dark=CHALK_DARK, light=CHALK_LIGHT),
    "apple": _preset("Apple", "The previous default. Apple Human Interface Guidelines system colours, capsule buttons.", "system",
                     dark=APPLE_DARK, light=APPLE_LIGHT),
    "midnight": _preset("Midnight", "The previous default. Calm dark navy, indigo accent.", "system",
                        dark=MIDNIGHT_DARK, light=MIDNIGHT_LIGHT, buttons={"radius_px": 12, "hover": "lift"}),
    "daylight": _preset("Daylight", "Opens in light mode. Same indigo accent.", "light"),
    "pitch": _preset("Pitch green", "Green accent, rounded corners.", "system",
                     dark={"brand": "#34D399", "onBrand": "#04281C", "accent": "#A7F3D0", "onAccent": "#04281C", "chart1": "#34D399"},
                     light={"brand": "#047857", "onBrand": "#FFFFFF", "accent": "#A7F3D0", "onAccent": "#04281C", "chart1": "#047857"}, radius="round"),
    "sunset": _preset("Sunset", "Warm orange accent, soft shapes.", "dark",
                      dark={"brand": "#FB923C", "onBrand": "#1F1004", "accent": "#FED7AA", "onAccent": "#1F1004", "chart1": "#FB923C"},
                      light={"brand": "#C2410C", "onBrand": "#FFFFFF", "accent": "#FED7AA", "onAccent": "#1F1004", "chart1": "#C2410C"}, radius="round"),
    "ocean": _preset("Ocean", "Cool blue accent, sharp corners.", "system",
                     dark={"brand": "#38BDF8", "onBrand": "#04202E", "accent": "#BAE6FD", "onAccent": "#04202E", "chart1": "#38BDF8"},
                     light={"brand": "#0369A1", "onBrand": "#FFFFFF", "accent": "#BAE6FD", "onAccent": "#04202E", "chart1": "#0369A1"}, radius="sharp",
                     buttons={"radius_px": 6}),
    "contrast": _preset("High contrast", "Maximum readability. Pure black and white text.", "dark",
                        dark={"bg": "#000000", "surface1": "#0B0B0B", "surface2": "#141414", "surface3": "#1E1E1E", "border": "#4B4B4B", "borderStrong": "#8A8A8A",
                              "text": "#FFFFFF", "text2": "#E0E0E0", "text3": "#BDBDBD", "brand": "#FFD60A", "onBrand": "#000000",
                              "accent": "#FFD60A", "onAccent": "#000000"},
                        light={"bg": "#FFFFFF", "surface1": "#FFFFFF", "surface2": "#F2F2F2", "surface3": "#E4E4E4", "border": "#6B6B6B", "borderStrong": "#222222",
                               "text": "#000000", "text2": "#1F1F1F", "text3": "#3D3D3D", "brand": "#0000CC", "onBrand": "#FFFFFF",
                               "accent": "#FFD60A", "onAccent": "#000000"},
                        buttons={"focus_ring_px": 4}),
}


def apply_preset(theme: dict, buttons: dict, key: str) -> tuple[dict, dict]:
    p = PRESETS[key]
    th, bt = copy.deepcopy(theme), copy.deepcopy(buttons)
    base = defaults()["theme"]["colors"]
    th["colors"] = {"dark": {**base["dark"], **p["dark"]}, "light": {**base["light"], **p["light"]}}
    th["default_mode"], th["radius"] = p["default_mode"], p["radius"]
    bt.update(p["buttons"])
    return th, bt


# ----------------------------------------------------------------------------- state: draft, live, versions
def _state(db) -> dict:
    return db.site_state.find_one({"_id": "state"}) or {"_id": "state", "live_v": 0, "draft": None}


def get_live(db) -> dict:
    s = _state(db)
    if s["live_v"]:
        v = db.site_versions.find_one({"v": s["live_v"]}, {"_id": 0})
        if v:
            return v
    d = defaults()
    return {"v": 0, "data": d, "css": compile_css(d), "note": "Built-in defaults", "by": "system", "at": None}


def get_draft(db) -> dict:
    """Draft data (or a copy of live when nobody started one) plus who touched it."""
    s = _state(db)
    live = get_live(db)
    if s.get("draft") is None:
        return {"data": copy.deepcopy(live["data"]), "dirty": False, "base_v": live["v"], "updated_by": None, "updated_at": None, "sections_changed": []}
    return {"data": s["draft"], "dirty": True, "base_v": s.get("draft_base_v", live["v"]), "updated_by": s.get("draft_by"),
            "updated_at": s.get("draft_at"), "sections_changed": diff(s["draft"], live["data"])}


def diff(a: dict, b: dict) -> list[str]:
    return [s for s in SECTIONS if json.dumps(a.get(s), sort_keys=True) != json.dumps(b.get(s), sort_keys=True)]


def put_section(db, actor: str, section: str, data) -> dict:
    clean, warnings = validate_section(section, data)
    cur = get_draft(db)
    doc = cur["data"]
    doc[section] = clean
    now = utcnow()
    live = get_live(db)
    db.site_state.update_one({"_id": "state"}, {"$set": {"draft": doc, "draft_base_v": cur["base_v"] if cur["dirty"] else live["v"], "draft_by": actor, "draft_at": now},
                                                 "$setOnInsert": {"live_v": live["v"]}}, upsert=True)
    db.audit_log.insert_one({"actor": actor, "action": "site.draft_save", "target": section, "at": now})
    return {"section": section, "warnings": warnings, "sections_changed": diff(doc, live["data"])}


def reset_section(db, actor: str, section: str, to: str = "live") -> dict:
    if section not in SECTIONS or to not in ("live", "default"):
        raise SiteError([{"path": section, "message": "Unknown section or target."}])
    src = get_live(db)["data"] if to == "live" else defaults()
    cur = get_draft(db)
    doc = cur["data"]
    doc[section] = copy.deepcopy(src[section])
    live = get_live(db)
    db.site_state.update_one({"_id": "state"}, {"$set": {"draft": doc, "draft_base_v": live["v"], "draft_by": actor, "draft_at": utcnow()}, "$setOnInsert": {"live_v": live["v"]}}, upsert=True)
    db.audit_log.insert_one({"actor": actor, "action": "site.draft_reset", "target": f"{section}:{to}", "at": utcnow()})
    return {"section": section, "sections_changed": diff(doc, live["data"])}


def apply_preset_to_draft(db, actor: str, key: str) -> dict:
    if key not in PRESETS:
        raise SiteError([{"path": "preset", "message": "Unknown preset."}])
    cur = get_draft(db)
    th, bt = apply_preset(cur["data"]["theme"], cur["data"]["buttons"], key)
    validate_section("theme", th)
    validate_section("buttons", bt)
    put_section(db, actor, "theme", th)
    return put_section(db, actor, "buttons", bt)


def discard_draft(db, actor: str) -> None:
    db.site_state.update_one({"_id": "state"}, {"$set": {"draft": None, "draft_by": None, "draft_at": None}})
    db.audit_log.insert_one({"actor": actor, "action": "site.draft_discard", "target": "draft", "at": utcnow()})


class Conflict(Exception):
    pass


def publish(db, actor: str, note: str = "", force: bool = False) -> dict:
    s = _state(db)
    if s.get("draft") is None:
        raise SiteError([{"path": "draft", "message": "Nothing to publish. There are no unsaved changes."}])
    live = get_live(db)
    if s.get("draft_base_v", live["v"]) != live["v"] and not force:
        raise Conflict("Someone published while this draft was open. Review the differences, then publish again with 'force'.")
    data = s["draft"]
    warnings = validate_all(data)
    css = compile_css(data)
    n = db.site_counter.find_one_and_update({"_id": "version"}, {"$inc": {"n": 1}}, upsert=True, return_document=ReturnDocument.AFTER)["n"]
    now = utcnow()
    db.site_versions.insert_one({"v": n, "data": data, "css": css, "note": (note or "")[:200], "by": actor, "at": now, "changed": diff(data, live["data"])})
    db.site_state.update_one({"_id": "state"}, {"$set": {"live_v": n, "draft": None, "draft_by": None, "draft_at": None}}, upsert=True)
    old = [r["v"] for r in db.site_versions.find({}, {"v": 1}).sort("v", -1).skip(KEEP_VERSIONS)]
    if old:
        db.site_versions.delete_many({"v": {"$in": old}})
    db.audit_log.insert_one({"actor": actor, "action": "site.publish", "target": f"v{n}", "detail": {"changed": diff(data, live["data"]), "note": (note or "")[:200]}, "at": now})
    return {"v": n, "warnings": warnings}


def rollback(db, actor: str, v: int) -> dict:
    old = db.site_versions.find_one({"v": v})
    if not old:
        raise SiteError([{"path": "v", "message": "No such version (only the last 50 are kept)."}])
    db.site_state.update_one({"_id": "state"}, {"$set": {"draft": old["data"], "draft_base_v": get_live(db)["v"], "draft_by": actor, "draft_at": utcnow()}}, upsert=True)
    return publish(db, actor, note=f"Rollback to v{v}", force=True)


def versions(db, limit: int = 50) -> list[dict]:
    return list(db.site_versions.find({}, {"_id": 0, "data": 0, "css": 0}).sort("v", -1).limit(limit))


def get_version(db, v: int) -> dict | None:
    return db.site_versions.find_one({"v": v}, {"_id": 0})


def brand_name(db) -> str:
    try:
        return get_live(db)["data"]["brand"]["name"] or "Forecast"
    except Exception:
        return "Forecast"


# ----------------------------------------------------------------------------- preview tokens
def _pkey() -> bytes:
    return hashlib.sha256(b"site-preview|" + base64.b64decode(__import__("os").environ["APP_ENCRYPTION_KEY"])).digest()


def preview_token(user_id: str, minutes: int = 30, now: float | None = None) -> str:
    exp = int((now or time.time()) + minutes * 60)
    body = base64.urlsafe_b64encode(f"{exp}|{user_id}".encode()).decode().rstrip("=")
    sig = hmac.new(_pkey(), body.encode(), hashlib.sha256).hexdigest()[:32]
    return f"{body}.{sig}"


def read_preview_token(tok: str, now: float | None = None) -> str | None:
    try:
        body, sig = tok.split(".", 1)
        if not hmac.compare_digest(sig, hmac.new(_pkey(), body.encode(), hashlib.sha256).hexdigest()[:32]):
            return None
        exp, uid = base64.urlsafe_b64decode(body + "=" * (-len(body) % 4)).decode().split("|", 1)
        return uid if int(exp) >= (now or time.time()) else None
    except Exception:
        return None


# ----------------------------------------------------------------------------- what the browser gets
def public_config(db, draft: bool = False) -> dict:
    """The one JSON the front end loads at start. Cached by ETag. Contains nothing secret."""
    if draft:
        d = get_draft(db)["data"]
        v, css = -1, compile_css(d)
    else:
        live = get_live(db)
        d, v, css = live["data"], live["v"], live["css"]
    pub = S.public(db)
    trk = {k: S.get(db, k) for k in ("tracking.enabled", "tracking.ga4_id", "tracking.meta_pixel_id", "tracking.google_ads_id", "tracking.require_consent")}
    return {
        "v": v, "preview": bool(draft),
        "brand": d["brand"],
        "theme": {"default_mode": d["theme"]["default_mode"], "allow_toggle": d["theme"]["allow_toggle"], "fonts": font_faces(d), "css": css,
                  "density": d["theme"]["density"]},
        "nav": d["nav"], "footer": d["footer"],
        "seo": {k: d["seo"][k] for k in ("title_template", "description_template", "og_image", "robots_index", "sitemap")},
        "redirects": d["seo"]["redirects"],
        "cookies": d["cookies"], "home": d["home"],
        "tracking": {"enabled": bool(trk["tracking.enabled"]), "ga4_id": trk["tracking.ga4_id"] if trk["tracking.enabled"] else "",
                     "meta_pixel_id": trk["tracking.meta_pixel_id"] if trk["tracking.enabled"] else "",
                     "google_ads_id": trk["tracking.google_ads_id"] if trk["tracking.enabled"] else "",
                     "require_consent": bool(trk["tracking.require_consent"])},
        "popups_enabled": bool(S.get(db, "popups.enabled")),
        "maintenance": {"on": bool(pub.get("features.maintenance")), "message": pub.get("site.maintenance_message", "")},
        "disclaimer": pub.get("copy.disclaimer", textguard.DISCLAIMER),
        "data_credit": pub.get("copy.data_credit", "") if d["footer"]["show_data_credit"] else "",
        # Crests and player photos belong to their clubs. The wording for that sat in `images.credit_text`
        # from the day the setting was written and reached no screen, so the product showed other people's
        # marks with no notice at all. It travels with the footer now and is removed by emptying it.
        "image_credit": pub.get("images.credit_text", ""),
    }


# ----------------------------------------------------------------------------- images the owner uploads
_MAGIC = ((b"\x89PNG\r\n\x1a\n", "image/png"), (b"\xff\xd8\xff", "image/jpeg"), (b"GIF87a", "image/gif"), (b"GIF89a", "image/gif"),
          (b"\x00\x00\x01\x00", "image/x-icon"))


def sniff(data: bytes) -> str | None:
    for m, mime in _MAGIC:
        if data.startswith(m):
            return mime
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return None


def save_asset(db, actor: str, name: str, data: bytes) -> dict:
    if len(data) > MAX_ASSET_BYTES:
        raise ValueError("Images are limited to 512 KB. Resize it first.")
    mime = sniff(data)
    if not mime:
        raise ValueError("Use a PNG, JPEG, GIF, WebP or ICO image. SVG files are not accepted.")
    if db.site_assets.count_documents({}) >= MAX_ASSETS:
        raise ValueError("Image library is full (100). Delete one first.")
    aid = uuid.uuid4().hex
    db.site_assets.insert_one({"_id": aid, "name": re.sub(r"[^\w.\- ]", "_", name)[:80], "mime": mime, "data": data, "bytes": len(data),
                               "sha256": hashlib.sha256(data).hexdigest(), "by": actor, "at": utcnow()})
    db.audit_log.insert_one({"actor": actor, "action": "site.asset_upload", "target": aid, "at": utcnow()})
    return {"id": aid, "url": f"/api/site/assets/{aid}", "mime": mime, "bytes": len(data), "name": name[:80]}


def get_asset(db, aid: str) -> dict | None:
    return db.site_assets.find_one({"_id": aid})


def list_assets(db) -> list[dict]:
    return [{"id": r["_id"], "url": f"/api/site/assets/{r['_id']}", "name": r["name"], "mime": r["mime"], "bytes": r["bytes"], "at": r["at"], "by": r["by"]}
            for r in db.site_assets.find({}, {"data": 0}).sort("at", -1)]


def asset_in_use(db, aid: str) -> bool:
    url = f"/api/site/assets/{aid}"
    texts = [json.dumps(get_draft(db)["data"]), json.dumps(get_live(db)["data"])]
    if any(url in t for t in texts):
        return True
    return db.popups.count_documents({"$or": [{"content.image": url}]}) > 0 if "popups" in db.list_collection_names() else False


def delete_asset(db, actor: str, aid: str) -> None:
    if asset_in_use(db, aid):
        raise ValueError("This image is used by the site or a popup. Replace it there first.")
    db.site_assets.delete_one({"_id": aid})
    db.audit_log.insert_one({"actor": actor, "action": "site.asset_delete", "target": aid, "at": utcnow()})
