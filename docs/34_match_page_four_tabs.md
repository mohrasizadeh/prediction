# 34 · Match page: four tabs, and a sharper Top 3

**Top 3 for today** (`pages/Today.jsx`, `topRated`): only Strong and Solid lines; Strong before Solid, then the whole chance (his chance to play counted for players), then the low end of the range. At most two per match. Nothing below Solid appears; if nothing qualifies the block hides. "See all" still opens the full list.

**Match page** (`pages/Match.jsx`). Ten tabs became four.

| Tab | When | What is in it |
|---|---|---|
| Live / Recap | Live while the match is on, Recap after full time. Opens first. Not shown before kick-off. | Live: our lines that already happened (green), then the events feed and live lineups. Recap: goals, cards, subs with filter. |
| Forecasts | Always. Opens first before kick-off. Count badge. | Unchanged: slider, by team or by market, live ticks. |
| Lineups | Always. Tick when the eleven is confirmed. | Pitch (predicted or confirmed) beside "Worth knowing", absences and the referee line. Replaces Preview. |
| Analysis | Always. | Jump chips, then Form (per-game bars and style radar from one fetch), Head to head, Who scores first, Shots by player, Playing style. |

Stats, First goal, Players, H2H, Matchup, Preview and Events are no longer tabs. Season numbers sit in Analysis and say they are from before kick-off.

**Layout.** Sticky underline tab bar that fits four tabs on a phone. Hero shortened: small print and Follow/Share share one row, situation chips moved into "Worth knowing". Two columns on desktop for Lineups and Form. Section jump chips are sticky in Analysis.

**Not done.** Live team stats (shots, corners) need `sportapi.live_stats` switched on and verified (doc 31); the Live tab can show them once that exists. The demo data has no pitch coordinates, so the pitch looked off there; check with real lineups.
