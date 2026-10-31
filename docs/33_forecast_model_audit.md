# 33 · Forecast model audit — what is best for each market

**Data.** Public match tables (goals, shots, shots on target, corners, fouls, yellows, bookmaker odds) for the top five leagues, 2012 to 2026. Walk-forward: every forecast uses only games before it. Scripts: `docs/validation/ratings_walkforward.py`, `ratings_engine_ab.py`. No tackles or player data in this set, so those are unchanged and still rest on the StatsBomb checks in docs 18, 22, 25.

**Findings**
1. **No separate home and away rating per club.** It made every count worse in every league (z −4 to −13). One home factor for the league is better.
2. **Recent games should count more for shots, fouls, yellows.** Faster decay and a stronger ridge beat the old settings (shots +8, fouls +14 per 1,000 log-lik, z up to +19).
3. **Our team-total regression lost to a simple attack/defence ratings model** on 2,272 Premier League games: shots −43, shots on target −32, corners −19, fouls −31, yellows −10 per 1,000 (z −2.5 to −6.5). Blending the engine back in added nothing significant.
4. **Fix, tested in the real engine** (same games, blend 0.7 on vs off): shots +50, SOT +33, corners +21, fouls +38, yellows +13 per 1,000 (z +4.5 to +9.2).
5. **Match result.** Best results-only setup is slow decay, light ridge, small draw correction. It is about 0.017 log loss behind the bookmakers (0.985 vs 0.967). Adding shots on target, Elo or club splits did not close that. Closing it needs lineup and injury news or odds as an input.
6. **Match yellow totals.** New ratings beat the old all-time average (0.649 vs 0.658 log loss at 3.5+, all five leagues). The "last 10 games" rate is worse than the league average (0.672 vs 0.663).

**Shipped.** `soccer_brain/ratings.py`; `engine.ratings_blend` (0.7) blends it into every team total; `engine.cards_ratings_blend` (0.7) does the same for match cards.

**Not shown by this test.** Player markets, tackles and referee effects. The engine run had no possession or normalised-average inputs, so the true gain in production may be smaller. Run `engine_audit.py` on production data before and after the next engine run.
