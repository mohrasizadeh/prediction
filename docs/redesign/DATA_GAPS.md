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
| Search overlay | "Next 69%" chip per player | the next forecast per player in `/api/search` | Hidden |
| Footer e-mail | "Every Friday" send day | a newsletter send-day setting | Shows "Free · weekly" |
| Footer e-mail | Preview card | 3 Strong cards from `/api/insights` | Hidden when fewer than 3 Strong cards |
| Desktop shell | Right column with Following and live scores | (layout, phase R3 with Today) | Following is in the left rail; live is the header pill |
| Match hero (finished) | Half-time score, "How our forecasts did: 7 of 9" | half-time score and scored outcomes per match in `/api/matches/{id}` | Hidden |
| Match lineups | Predicted eleven before any lineup arrives | a predicted XI when the lineups table is empty | Empty state until lineups exist |
| Live | "Follow a match" with goal alerts | match follows + alert sending | Hidden |
| Insights | "Biggest rise vs usual" | `usual_p`; sorts by p minus p_base meanwhile | Approximate |
| Finder | Presets saved per account | a presets route | Saved in this browser (localStorage) |
| Finder | Remaining free searches for visitors | usage counter for anonymous users | Shows the daily cap only |
| League table | Zones (Europe, relegation) | competition zone rules per league | Hidden |
| Team | Squad cards / grid redesign details (photos with season numbers) | per-player season totals in one call | Existing squad grid kept, restyled later |
