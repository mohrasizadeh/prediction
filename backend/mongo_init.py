"""mongo_init.py -- create every collection index the app needs. Safe to run many times.

Run once after the first deploy and again after any schema change:
    python mongo_init.py

Works with pymongo (sync). Reads MONGO_URL and DB_NAME from the environment,
the same names Emergent's template provides.
"""
from __future__ import annotations

import os

from pymongo import ASCENDING as ASC, DESCENDING as DESC


def ensure_indexes(db) -> list[str]:
    done: list[str] = []

    def ix(coll, keys, **kw):
        db[coll].create_index(keys, **kw)
        done.append(f"{coll}: {keys} {kw or ''}".strip())

    # ---- counters (integer ids the engine needs) ------------------------
    # documents look like {_id: "teams", seq: 123}; see next_iid() in cached_fetch.py

    # ---- accounts and config --------------------------------------------
    ix("users", [("email", ASC)], unique=True)
    ix("settings", [("key", ASC)], unique=True)
    ix("settings_history", [("key", ASC), ("at", DESC)])
    ix("content_pages", [("slug", ASC)], unique=True)
    ix("provider_keys", [("provider", ASC)], unique=True)
    ix("audit_log", [("at", DESC)])
    ix("audit_log", [("actor", ASC), ("at", DESC)])

    # ---- cache -----------------------------------------------------------
    ix("api_cache", [("expires_at", ASC)], expireAfterSeconds=0)   # Mongo deletes expired rows itself
    ix("api_cache", [("path", ASC)])
    ix("api_call_log", [("at", DESC)])
    ix("api_call_log", [("at", ASC)], expireAfterSeconds=60 * 60 * 24 * 45)  # keep 45 days

    # ---- reference data ---------------------------------------------------
    ix("leagues", [("ext_id", ASC)], unique=True)
    ix("leagues", [("iid", ASC)], unique=True)
    ix("seasons", [("league_iid", ASC), ("label", ASC)], unique=True)
    ix("teams", [("ext_id", ASC)], unique=True)
    ix("teams", [("iid", ASC)], unique=True)
    ix("teams", [("name", ASC)])
    ix("players", [("ext_id", ASC)], unique=True)
    ix("players", [("iid", ASC)], unique=True)
    ix("players", [("team_iid", ASC)])
    ix("players", [("name", ASC)])

    # ---- facts ------------------------------------------------------------
    ix("matches", [("ext_id", ASC)], unique=True)
    ix("matches", [("iid", ASC)], unique=True)
    ix("matches", [("league_iid", ASC), ("kickoff", ASC)])
    ix("matches", [("status", ASC), ("kickoff", ASC)])
    ix("matches", [("home_iid", ASC), ("kickoff", DESC)])
    ix("matches", [("away_iid", ASC), ("kickoff", DESC)])
    ix("matches", [("referee", ASC), ("kickoff", DESC)])
    ix("team_match_stats", [("match_iid", ASC), ("team_iid", ASC)], unique=True)
    ix("team_match_stats", [("team_iid", ASC), ("kickoff", DESC)])
    ix("player_match_stats", [("match_iid", ASC), ("player_iid", ASC)], unique=True)
    ix("player_match_stats", [("player_iid", ASC), ("kickoff", DESC)])
    ix("player_match_stats", [("team_iid", ASC), ("kickoff", DESC)])
    ix("player_match_stats", [("opp_iid", ASC), ("kickoff", DESC)])
    ix("lineups", [("match_iid", ASC), ("team_iid", ASC), ("player_iid", ASC)], unique=True)
    ix("match_events", [("match_iid", ASC), ("minute", ASC)])
    ix("match_events", [("player_iid", ASC), ("event_type", ASC)])

    # ---- jobs --------------------------------------------------------------
    ix("ingest_queue", [("task", ASC), ("key", ASC)], unique=True)
    ix("ingest_queue", [("status", ASC), ("priority", ASC), ("next_run_at", ASC)])
    ix("ingest_issues", [("at", DESC)])
    ix("ingest_issues", [("resolved", ASC), ("at", DESC)])
    ix("job_runs", [("job", ASC), ("started_at", DESC)])
    ix("job_requests", [("status", ASC), ("requested_at", ASC)])
    ix("job_locks", [("expires_at", ASC)], expireAfterSeconds=0)
    ix("data_coverage", [("league_iid", ASC), ("field", ASC)], unique=True)

    # ---- engine output ------------------------------------------------------
    ix("engine_runs", [("league_iid", ASC), ("started_at", DESC)])
    ix("media", [("kind", ASC), ("iid", ASC)], unique=True)                                  # stored images (bytes live here)
    ix("image_map", [("kind", ASC), ("our_iid", ASC)], unique=True)
    ix("image_map", [("status", ASC), ("kind", ASC), ("score", DESC)])
    ix("image_api_cache", [("expires_at", ASC)], expireAfterSeconds=0)
    ix("image_runs", [("at", DESC)])
    ix("team_styles", [("league_iid", ASC), ("team_iid", ASC), ("as_of", DESC)])
    ix("club_calendar", [("team_iid", ASC), ("kickoff", ASC), ("comp", ASC)], unique=True)   # every competition a club plays
    ix("club_calendar", [("kickoff", ASC)])
    ix("match_context", [("match_iid", ASC), ("team_iid", ASC)], unique=True)                  # rotation level per club per match
    ix("engine_gates", [("league_iid", ASC), ("layer", ASC), ("at", DESC)])                    # walk-forward gate results
    ix("match_probs", [("match_iid", ASC), ("is_current", ASC)])
    ix("forecasts", [("match_iid", ASC), ("is_current", ASC), ("hidden", ASC)])
    ix("forecasts", [("is_current", ASC), ("tier", ASC), ("p", DESC)])
    ix("forecasts", [("player_iid", ASC), ("is_current", ASC)])
    ix("forecasts", [("fkey", ASC), ("run_id", ASC)], unique=True)
    ix("forecast_outcomes", [("forecast_id", ASC)], unique=True)
    ix("forecast_outcomes", [("scored_at", DESC)])
    ix("referee_stats", [("referee", ASC), ("league_iid", ASC)], unique=True)

    # ---- users' things --------------------------------------------------------
    ix("follows", [("user_id", ASC), ("kind", ASC), ("ref_iid", ASC)], unique=True)
    ix("saved_forecasts", [("user_id", ASC), ("fkey", ASC)], unique=True)
    ix("notes", [("user_id", ASC), ("player_iid", ASC)], unique=True)
    ix("alert_subscriptions", [("user_id", ASC)])
    ix("newsletter", [("email", ASC)], unique=True)
    ix("finder_usage", [("subject", ASC), ("day", ASC), ("name", ASC)], unique=True)   # daily quota counters
    ix("finder_usage", [("expires_at", ASC)], expireAfterSeconds=0)

    # ---- accounts, sessions, security ------------------------------------------
    ix("users", [("id", ASC)], unique=True)
    ix("users", [("role", ASC)])
    ix("users", [("created_at", DESC)])
    ix("users", [("stripe_customer_id", ASC)], sparse=True)
    ix("sessions", [("user_id", ASC)])
    ix("sessions", [("expires_at", ASC)], expireAfterSeconds=0)      # Mongo removes dead sessions
    ix("sessions", [("sid", ASC)], unique=True)
    ix("auth_tokens", [("expires_at", ASC)], expireAfterSeconds=0)
    ix("auth_tokens", [("user_id", ASC), ("kind", ASC)])
    ix("rate_limits", [("expires_at", ASC)], expireAfterSeconds=0)
    ix("auth_log", [("at", DESC)])
    ix("auth_log", [("user_id", ASC), ("at", DESC)])
    ix("auth_log", [("at", ASC)], expireAfterSeconds=60 * 60 * 24 * 90)   # default 90 days
    ix("app_logs", [("at", DESC)])
    ix("app_logs", [("level", ASC), ("at", DESC)])
    ix("app_logs", [("at", ASC)], expireAfterSeconds=60 * 60 * 24 * 30)   # default 30 days
    ix("admin_notes", [("user_id", ASC), ("at", DESC)])

    # ---- plans and billing --------------------------------------------------------
    ix("plans", [("key", ASC)], unique=True)
    ix("subscriptions", [("user_id", ASC), ("status", ASC)])
    ix("subscriptions", [("customer_id", ASC)])
    ix("subscriptions", [("status", ASC), ("current_period_end", ASC)])
    ix("payments", [("user_id", ASC), ("created_at", DESC)])
    ix("payments", [("created_at", DESC)])
    ix("payments", [("payment_intent", ASC)], sparse=True)
    ix("payments", [("charge", ASC)], sparse=True)
    ix("webhook_events", [("provider", ASC), ("received_at", DESC)])
    ix("webhook_events", [("status", ASC), ("received_at", DESC)])
    ix("webhook_events", [("received_at", ASC)], expireAfterSeconds=60 * 60 * 24 * 90)
    ix("coupons", [("code", ASC)], unique=True, sparse=True)

    # ---- e-mail -----------------------------------------------------------------------
    ix("email_templates", [("key", ASC)], unique=True)
    ix("email_log", [("at", DESC)])
    ix("email_log", [("user_id", ASC), ("at", DESC)])
    ix("email_log", [("provider_id", ASC)], sparse=True)
    ix("email_log", [("status", ASC), ("at", DESC)])
    ix("email_log", [("campaign_id", ASC), ("to_hash", ASC)], sparse=True)
    ix("email_log", [("idem", ASC)], sparse=True)
    ix("email_suppressions", [("email", ASC)], unique=True)
    ix("email_campaigns", [("created_at", DESC)])

    # ---- analytics, content, inbox -------------------------------------------------------
    ix("events", [("day", ASC), ("name", ASC)])
    ix("events", [("at", DESC)])
    ix("events", [("user_id", ASC), ("at", DESC)], sparse=True)
    ix("events", [("at", ASC)], expireAfterSeconds=60 * 60 * 24 * 400)      # default 400 days
    ix("announcements", [("active", ASC), ("starts_at", ASC)])
    ix("contact_messages", [("status", ASC), ("at", DESC)])

    # ---- site studio, popups, newsletter, integrations, alerts ---------------------------------
    ix("site_versions", [("v", DESC)], unique=True)
    ix("site_assets", [("at", DESC)])
    ix("popups", [("status", ASC), ("priority", DESC)])
    ix("popups", [("ab.group", ASC)], sparse=True)
    ix("popup_stats", [("popup_id", ASC), ("day", ASC)], unique=True)
    ix("popup_stats", [("expires_at", ASC)], expireAfterSeconds=0)
    ix("newsletter", [("status", ASC), ("created_at", DESC)])
    ix("integration_jobs", [("kind", ASC), ("status", ASC), ("next_at", ASC)])
    ix("integration_jobs", [("expires_at", ASC)], expireAfterSeconds=0)
    ix("webhook_endpoints", [("active", ASC), ("events", ASC)])
    ix("webhook_outbox", [("status", ASC), ("next_at", ASC)])
    ix("webhook_outbox", [("endpoint_id", ASC), ("status", ASC)])
    ix("webhook_outbox", [("expires_at", ASC)], expireAfterSeconds=0)
    ix("webhook_deliveries", [("endpoint_id", ASC), ("at", DESC)])
    ix("webhook_deliveries", [("expires_at", ASC)], expireAfterSeconds=0)
    ix("admin_alerts", [("key", ASC), ("resolved", ASC)])
    ix("admin_alerts", [("created_at", DESC)])
    return done


if __name__ == "__main__":
    from pymongo import MongoClient

    client = MongoClient(os.environ["MONGO_URL"])
    database = client[os.environ["DB_NAME"]]
    for line in ensure_indexes(database):
        print("ok", line)
