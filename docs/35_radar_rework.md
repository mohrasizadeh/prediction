# 35 · Style radar rework

**What was wrong.** The two-club radar ranked each club's plain per-game average inside its league (`team_insights.compare`). That gave wrong shapes for some clubs:
- a club with no expected-goals number from the feed got a zero on Attack and Defence, so the shape collapsed;
- early in the season a club's average rests on two or three games, so the rank jumped about;
- a soft run of fixtures made a club look strong (no opponent adjustment);
- in the fixture view the home club was ranked on home games only and the away club on away games only, each on a handful of matches. Our walk-forward test (docs/33) shows venue-specific numbers predict worse than one league-wide home factor.

**What it does now** (`team_insights.league_radar`). Every club in a league is rated together from all stored matches with the same attack/defence ratings model the engine uses (`soccer_brain/ratings.py`): older games count less, few games pull a club toward the league average, and each club is judged against the opponents it met. The spoke is the club's place among that season's clubs (0 bottom, 1 top).
- Attack: expected goals (goals when fewer than 80% of matches have expected goals). Defence: the same model's concession rating, flipped so outward is tighter.
- Shots, On target, Possession, Corners: each from its own rating.
- The reply carries a plain-words meaning for each spoke and each club's games this season; the page shows "What the spokes mean" and a note when a club has played fewer than 5 games.
- A missing value draws mid-way, never at the centre. Too little history falls back to the old view.
- Cached for 10 minutes per league.

**Tests.** `tests/selftest_radar.py`.
**Open.** Possession is fitted as a count, which is fine for ranking; a proper share model could replace it. Needs a look on production data: open a few Premier League fixtures and check each spoke against the club's table position and style.
