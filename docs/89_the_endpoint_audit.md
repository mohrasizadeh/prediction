# 89 — The endpoint audit I was asked for the first time

## Why this exists

docs/87 was supposed to be this. It was not. It audited screens, tokens and accessibility, produced
six findings that were **all my own measurement errors**, and never once asked the question actually
put to me: *which endpoints and requests still reach for a provider we have retired?*

What followed was predictable. The owner found the bugs one at a time — the Competitions error, the
wrong badges, the dead Backfill button — and each time I fixed that one symptom and reported it as
done. That is not an audit; it is being led around the failure by the person who asked me to find
it.

This is the sweep, done mechanically: every route decorator in every `routes_*.py`, and every module
the server reads through, matched against `SP.`, `sportapi`, `PitchClient`, `pitch_photos`,
`make_client`, and the `sportapi_*` collections.

```
routes_admin.py          2 of 75 endpoints
routes_data_admin.py     2 of 15
routes_live.py          12 of 13
queries.py              11 references
```

## The findings

### 1. The Endpoint explorer on the API-Football screen called PitchAPI

`APIFootball.jsx` tab "Endpoint explorer" → `Explorer.jsx` → `POST /admin/explorer` →
`routes_data_admin.explorer` → **`make_client(db)`, which is a `PitchClient`**.

So the explorer on the API-Football screen sent PitchAPI requests, against a PitchAPI allow-list,
and reported PitchAPI errors. It has been sitting on that screen in plain sight. Nothing hid it; I
never looked.

### 2. Live lineups could only ever be empty

`GET /api/live/{sid}/lineups` reads `live_lineups`. `live_af` writes `live_fixtures` and
`live_events` and **never writes `live_lineups`** — the collection has no writer at all now.

The endpoint returns `{"lineups": ...}` built from nothing, with no error: a feature that silently
stopped existing. The live payload does not carry lineups, so they come from the fixture bundle,
which is where the confirmed eleven already comes from for a finished match.

### 3. Eight SportAPI admin endpoints are still registered and still callable

`/admin/sportapi`, `/leagues`, `/teams/{sid}`, `/backfill`, `/live-stats`, `/stats-probe/{sid}`,
`/stats-keys`, and the status root. The screen that called them is deleted, so nothing in the UI
reaches them — but they are mounted, they take a session, and `/stats-probe` builds an
`SP.Client(db)` and **spends a call on a provider we no longer use**.

"Unreachable from the menu" is not "removed". A route that can spend money is reachable.

### 4. `overlay` tells every public page the data came from SportAPI

`sportapi.overlay` is what puts the live score on Today, the match page and the feed. It reads
`live_fixtures` by `match_iid`, which `live_af` does write — so it works. And it stamps
`m["source"] = "sportapi"` on every row it touches.

### 5. `/admin/leagues` reports a `sportapi` flag

A field describing whether a retired provider is enabled, on the screen that lists competitions.

### 6. The Keys screen still offers PitchAPI and SportAPI key types

Harmless in itself, and an invitation to put a key in for a provider nothing calls.

## What this says about the first audit

Every one of these is the same shape: code that still assumes the old provider, found by asking the
code rather than by looking at the screens. docs/87 asked the screens. The six findings it produced
were withdrawn because a regex over JSX is not a test of behaviour — and while I was withdrawing
them, six real ones sat one directory away.

The method that works here is the one used in this file: enumerate the surface mechanically, grep
each entry for the thing being retired, and read what comes back. It took one script.
