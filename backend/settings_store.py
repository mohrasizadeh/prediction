"""settings_store.py -- every tunable value lives in the `settings` collection.

The registry (settings_registry.json) is the source of defaults. A row in
`settings` overrides the default. Admin edits write the row and a history row.
Code never hard-codes a number that appears in the registry: call get().
"""
from __future__ import annotations

import json
import pathlib
import re
from datetime import datetime, timezone

import textguard

_REG_PATH = pathlib.Path(__file__).with_name("settings_registry.json")
_REGISTRY = {r["key"]: r for r in json.loads(_REG_PATH.read_text())}


def registry() -> dict:
    return _REGISTRY


def get(db, key: str):
    row = db.settings.find_one({"key": key}, {"_id": 0, "value": 1})
    if row is not None:
        return row["value"]
    if key not in _REGISTRY:
        raise KeyError(f"unknown setting: {key}")
    return _REGISTRY[key]["default"]


def get_many(db, prefix: str) -> dict:
    """All settings under a prefix, defaults merged with overrides."""
    out = {k: r["default"] for k, r in _REGISTRY.items() if k.startswith(prefix)}
    for row in db.settings.find({"key": {"$regex": "^" + prefix.replace(".", r"\.")}}, {"_id": 0}):
        out[row["key"]] = row["value"]
    return out


_ENUMS = {"engine.feed_sort": ("edge", "likely", "kickoff"), "email.provider": ("emergent", "resend", "postmark", "sendgrid", "brevo", "smtp"), "integrations.audience_provider": ("none", "mailchimp", "brevo", "mailerlite"),
          "email.smtp_security": ("starttls", "ssl"), "billing.mode": ("test", "live"),
          "context.start_model": ("off", "auto", "on"), "engine.tactic_layers": ("off", "auto", "on"), "engine.shape_layer": ("off", "auto", "on")}
_RANGES = {"email.smtp_port": (1, 65535), "popups.max_per_session": (0, 10), "popups.min_gap_seconds": (0, 3600), "admin.alert_signup_drop_pct": (10, 100),
           "waitlist.email_hour": (0, 23), "waitlist.email_tz_offset_min": (-900, 900),
           "admin.alert_errors_per_hour": (1, 10000), "admin.alert_failed_payments": (1, 1000), "admin.alert_cooldown_hours": (1, 168),
           "images.min_confidence": (0.7, 1.0), "images.daily_calls": (1, 100000), "images.max_bytes": (20000, 2000000), "images.season": (0, 2100),
           "context.gate_z": (0, 10), "context.holdout_share": (0.1, 0.5), "context.min_rows": (500, 1000000), "context.calendar_days": (1, 30), "engine.calib_min_scored": (500, 10000000), "injuries.stale_days": (1, 30), "engine.strength_decay": (0.0, 0.1), "sportapi.daily_calls": (0, 2000), "sportapi.live_interval_s": (30, 3600), "sportapi.idle_interval_s": (60, 86400), "sportapi.quiet_interval_s": (600, 86400), "sportapi.events_refresh_s": (60, 3600), "sportapi.window_before_min": (0, 180), "sportapi.min_confidence": (0.7, 1.0), "sportapi.backfill_max_days": (1, 366), "sportapi.reserve_for_live": (0, 2000), "engine.max_lines_per_stat": (1, 6), "engine.likely_starter_p": (0.5, 1.0), "engine.min_p_play": (0.0, 1.0), "combo.max_lines": (2, 10), "engine.style_half_life": (0, 200), "engine.style_cap_q": (0.0, 1.0), "engine.feed_max_p": (0.5, 1.0), "referees.prior_cards": (0, 1000), "referees.half_life": (0, 1000), "referees.cap_q": (0.0, 1.0),
           # Below ~0.6 the "high" band stops being the band a reader acts on and becomes the
           # whole record again, which is the thing the page is deliberately not leading on.
           "engine.record_high_p": (0.6, 0.99)}
_PATTERNS = {"tracking.ga4_id": r"(G-[A-Z0-9]{6,12})?", "tracking.meta_pixel_id": r"(\d{8,20})?", "tracking.google_ads_id": r"(AW-\d{6,14})?",
             "email.smtp_host": r"[A-Za-z0-9.\-]{0,253}", "email.smtp_user": r".{0,200}", "integrations.audience_list_id": r"[A-Za-z0-9_\-]{0,60}"}


def validate(key: str, value) -> None:
    """Refuse a value of the wrong kind, so a typo in the admin panel cannot crash the app."""
    t = _REGISTRY[key]["type"]
    ok = {"boolean": lambda v: isinstance(v, bool),
          "int": lambda v: isinstance(v, int) and not isinstance(v, bool),
          "float": lambda v: isinstance(v, (int, float)) and not isinstance(v, bool),
          "number": lambda v: isinstance(v, (int, float)) and not isinstance(v, bool),
          "string": lambda v: isinstance(v, str) and len(v) <= 2000,
          "enum": lambda v: isinstance(v, str) and len(v) <= 100,
          "url": lambda v: isinstance(v, str) and (v == "" or v.startswith(("https://", "http://", "/"))),
          "list": lambda v: isinstance(v, list) and len(v) <= 200 and all(isinstance(x, (str, int, float)) for x in v),
          "json": lambda v: True}[t]
    if not ok(value):
        raise ValueError(f"{key} must be of type {t}")
    if key in _ENUMS and value not in _ENUMS[key]:
        raise ValueError(f"{key} must be one of: {', '.join(_ENUMS[key])}")
    if key in _RANGES and not _RANGES[key][0] <= value <= _RANGES[key][1]:
        raise ValueError(f"{key} must be between {_RANGES[key][0]} and {_RANGES[key][1]}")
    if key in _PATTERNS and not re.fullmatch(_PATTERNS[key], value):
        raise ValueError(f"{key} does not look right")
    if _REGISTRY[key]["public"] and key != "copy.disclaimer":
        textguard.require_clean(key, value)


def put(db, key: str, value, actor: str = "system") -> None:
    if key not in _REGISTRY:
        raise KeyError(f"unknown setting: {key}")
    validate(key, value)
    if key == "engine.lineup_effects":
        # locked setting: see 03_rules_and_compliance.md
        if value:
            raise ValueError(f"{key} is locked off")
    now = datetime.now(timezone.utc)
    if key == "features.live":              # the live switch drives the SportAPI job (docs/23)
        db.settings.update_one({"key": "sportapi.enabled"}, {"$set": {"value": bool(value), "updated_at": now, "updated_by": actor}}, upsert=True)
    old = db.settings.find_one({"key": key})
    db.settings.update_one({"key": key}, {"$set": {"value": value, "updated_at": now, "updated_by": actor}}, upsert=True)
    db.settings_history.insert_one({"key": key, "old": old["value"] if old else _REGISTRY[key]["default"],
                                    "new": value, "by": actor, "at": now})
    db.audit_log.insert_one({"actor": actor, "action": "settings.put", "target": key, "at": now})


def reset(db, key: str, actor: str = "system") -> None:
    db.settings.delete_one({"key": key})
    if key == "features.live":
        db.settings.delete_one({"key": "sportapi.enabled"})
    db.audit_log.insert_one({"actor": actor, "action": "settings.reset", "target": key,
                             "at": datetime.now(timezone.utc)})


def public(db) -> dict:
    """What the browser may read: settings flagged public, nothing else."""
    out = {k: r["default"] for k, r in _REGISTRY.items() if r["public"]}
    keys = [k for k, r in _REGISTRY.items() if r["public"]]
    for row in db.settings.find({"key": {"$in": keys}}, {"_id": 0, "key": 1, "value": 1}):
        out[row["key"]] = row["value"]
    return out
