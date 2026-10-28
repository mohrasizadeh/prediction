# Data gaps (redesign, docs/24)

Elements hidden because the API does not return the data yet. Add a row whenever a screen hides something.

| Screen | Element | Field needed | Status |
|---|---|---|---|
| Forecast card | "Usual" tick on the bar, "+20 pts" vs usual | the player's usual hit rate for that line on each card (`usual_p`) | Hidden |
| Forecast sheet | Note button | a notes route for a forecast or player | Hidden (Save and Share shown) |
| Forecast sheet | "Our record on this kind of forecast" split by player/team and market | track record by tier AND scope/market (`/api/track-record` gives tier only) | Shown by tier only, and only when `ready` is true |
| Forecast sheet | Last 10 games strip for team forecasts | team history per stat | Shown for player forecasts only |
| Date scroller | Dots on days with games | a per-day match count route for followed leagues | The page passes `gameDays` when it has it; otherwise there are no dots |
| League | Table tab (standings) | standings route | Hidden (from README) |
| League overview | "Hot right now" | results-form change per team | Shown only when `context` has it (from README) |
| Live card | Momentum bar | `live_events` by minute | Hidden below 3 events (from README) |
| Finder | "Streak" mode | streak support in `/api/finder` | Hidden until supported (from README) |
| Player | League rank ("3rd of 61") | rank from the leaderboard | Use the leaderboard if it covers the stat, else hidden (from README) |
