# Redesign data gaps

Screens show only what the API returns. Open gaps:

| Screen | Element | Field needed | Status |
|---|---|---|---|
| Footer e-mail | "Every Friday" send day | a newsletter send-day setting | Shows "Free · weekly" |
| Footer e-mail | Preview card | 3 Strong cards from `/api/insights` | Hidden when fewer than 3 Strong cards |
| Desktop shell | Right column with Following and live scores | layout choice | Following is in the left rail; live is the header pill |
| Admin Engine | "Tested effect" per switch and proof link | backtest results per switch (docs 21/22 are not in this project) | Hidden; switches show their help text |
| Admin home | Players to approve | a player approval queue | Not shown (no such queue); photo reviews show as Image items |
| League table | Zones (Europe, relegation) | zone rules per league and season | Built; shown once an admin sets them in Admin > Leagues > Table zones |
| You feed | "Forecast rose to 78%" | previous value per forecast (`p_prev`) | Built; fills in from the next engine run onwards |
| Live | Goal and red card alerts | SportAPI events of type card | Goals verified in data; red cards depend on SportAPI sending card events |

Resolved on 2026-10-28 (R7): usual rate on cards (`usual_p`), Note button in the forecast sheet, record by scope and market,
team last-10 strip, date scroller dots (`/api/match-days`), standings, Streak mode, player league rank (`/api/players/{id}/ranks`),
next forecast in search, half-time recap, predicted eleven (`predicted` in match detail), follow a match + lineup/goal alert
e-mails (`follow_alerts.py`), Biggest rise vs usual, presets per account (`/api/me/presets`), lineup news in the feed,
separate lineup and goal alert switches, chosen leagues first in Explore, Today, Insights, Finder and Search, squad cards
with season numbers (`/api/teams/{id}/squad-season`).
