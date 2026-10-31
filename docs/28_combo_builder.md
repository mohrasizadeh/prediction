# 28. The combo builder: easiest way to put lines together

Goal: a visitor finds a match, taps + on the lines they like, and sees one honest combined chance. No words from the banned list in `docs/03`. No prices. No links to sellers.

Pictures: the Design canvas (9 boards) and `docs/28_boards/*.html`. Open them next to this page.

## 1. The flow

1. **Find a match** (Today, Finder, Insights, or search).
2. **Tap + on a line.** Each match page row has a 44 px round + button. It turns into a tick.
3. **The combo bar** floats above the tab bar: avatars, "3 lines · 46%", "About 1 in 2 · before lineups", and a Review button.
4. **Build one for me** (match page chip): Safer, Balanced, Bolder. Shows the lines and the combined chance. "Use this combo" fills the bar.
5. **Review sheet**: big combined number, range, one row per line (chance including playing), a "Weakest line" tag, alternative lines as chips with the new combined number, notes.
6. **Save / Copy as text / Share image.**
7. **My combos**: coming up (with the chance now), finished (which lines were reached), and a summary on the phone.

One match per combo. Tapping + on a line from another match asks "Start a new combo?" (board 8).

## 2. Screens

| Board | Screen | Notes |
|---|---|---|
| 1 Today | Today | Bottom tabs: Today, Insights, Finder, Combos, More. |
| 2 Match, browse | Match page, lines list | Interactive: tap + and the bar updates. |
| 3 Build for me | Sheet | Three modes. Default Balanced. |
| 4 Lines added | Match page with bar | Selected rows use the brand tint. |
| 5 Review | Sheet | Hero number, rows, alternatives, notes, sticky actions. |
| 6 Save | Confirmation + share picture | The picture is 320 px wide, dark, with the disclaimer line. |
| 7 My combos | List | Waiting / Finished, plus the "How our combined chances did" card. |
| 8 Add from anywhere | Finder with "Start a new combo?" sheet | Keeps the one-match rule. |
| 9 Computer | 1280 wide | Lines on the left, sticky combo panel (380 px) on the right. |

Rules for every screen: tap targets 44 px or more; numbers use tabular figures; a tier is never shown by colour alone (dots plus word); the page works with one thumb; the combo bar never hides the last row (add 76 px bottom padding when it shows).

## 3. Words

Use: combo, line, chance, together, reached, forecast, "About 1 in 2".
Never use: anything on the `docs/03` list, "pick", "slip", "lock", "hit rate", "stake", "units", "edge", prices, or seller names.
The footer line on every shared picture: "Statistical analysis for information and entertainment. Not betting advice." This one sentence is the only place the word "betting" appears, and the copy check already allows that exact sentence (`copy.disclaimer`, `frontend/scripts/check-copy.js`).

Older docs and mockups were cleaned in this update: "Top picks" is now "Standout forecasts", "Hit rate" is now "Usual rate" or "Form", "Edge bars" is now "Gap bars", "Stakes chips" is now "Context chips", and "lock" icons are now "padlock".

## 4. The math (backend/combo.py)

- A line's chance is `p × p_play` for a player and `p` for a team. `p` is the forecast "if he plays" (docs/27).
- Lines on different players or teams are multiplied.
- Before lineups are out, we multiply by a small correction from the setting `combo.pre_factors` = [1.00, 1.11, 1.19, 1.25] for 1, 2, 3, 4 or more players or teams. We fitted it on real data (section 6).
- Two lines on the same player are not multiplied. The smaller chance is raised by the other chances to the power 0.38.
- Two lines on the same player and the same stat are refused (`SAME_STAT`).
- The cap is 97%.
- The range uses `lo` and `hi` through the same steps.
- `plain`: 95% or more is "Very likely", 50% or more is "About N in 10", below that is "About 1 in N".
- Limit: `combo.max_lines` (default 6). One match per combo.
- Tested up to 4 players or teams. Past that a note says so.

### Build one for me

| Mode | Lines | Each line at least | Ranked by |
|---|---|---|---|
| safer | 2 | 80% | chance |
| balanced | 3 | 65% | gap vs usual + 0.25 × chance |
| bolder | 4 | 55% | same |

One line per player or team. We never use a player badged `unsure` or `bench`.

## 5. API

All three are public, no-store. Error body is the usual `{"error": {"code", "message"}}`.

### `POST /api/combo/estimate`
Body: `{"ids": ["..."], "fkeys": ["..."]}` (either list or both, up to 12 items).
Reply:
```json
{"match_iid": 1, "kickoff": "...", "state": "pre", "lines": [
  {"id": "...", "fkey": "...", "scope": "player", "player": {"id","name","image"}, "team": {...}, "opp": {...},
   "stat": "shots", "thr": 2, "market": "2+ shots", "p": 0.74, "p_play": 0.92, "chance": 0.68,
   "badge": "likely", "tier": "solid", "state": "pre"}],
 "combined": 0.46, "range": {"lo": 0.34, "hi": 0.58}, "plain": "About 1 in 2",
 "weakest": "<line id>", "notes": ["2 players not confirmed yet. ..."], "factor": 1.19}
```
Errors: `EMPTY` 400, `TOO_MANY` 409, `NOT_FOUND` 404, `MIXED_MATCHES` 409, `SAME_STAT` 409.

The alternative-line chips on the review sheet call this once per alternative (swap the id) and show `combined`. Debounce 150 ms. Fall back to showing the line's own chance if a call fails.

### `GET /api/matches/{match_id}/combo-suggest?mode=safer|balanced|bolder`
Same reply as estimate plus `"mode"`. If there are not enough confident lines: `{"mode", "lines": [], "reason": "Not enough confident lines for this match yet."}`. Show the reason and hide the "Use this combo" button.

### Saved combos (signed in)
- `PUT /api/me/combos` body `{"ids": [...]}`: saves a snapshot of the lines and the combined chance at that time. Label is "Home v Away". Over the limit: 409 `LIMIT_REACHED` (`saved_max`, same entitlement as saved forecasts).
- `GET /api/me/combos`: `{"items": [...], "limit": n}`. Before kick-off each item has the chance now under `now`. After the match each item has `status` "waiting" or "settled" and `result {reached, of, all}`, and each line has `reached`, `actual`, `played`, read from `forecast_outcomes`.
- `DELETE /api/me/combos/{id}`.
- Combos are deleted with the account and included in the data export (`USER_DATA`).

Signed-out visitors: keep the combo in memory and in `sessionStorage` (wrap in try/catch). Saving asks them to sign in.

## 6. What the tests showed (honest limits)

- Data: three leagues, one season (StatsBomb 2015/16: Premier League, Serie A, Ligue 1), about 237,000 combinations of 2 to 4 entities.
- Plain multiplication under-states the real chance before lineups, because players who start together tend to do well together. The correction table fixes this to within a few points. After lineups are out, no correction is used.
- Lines on the same player are strongly linked. Multiplying them would be wrong by a lot, so we use the soft rule above.
- The correction is empirical. One season only. Re-fit when a second season is in (`docs/validation/multi27.py`).
- Combos longer than 4 players or teams are not tested. The review sheet says so.
- Finder lines outside 50 to 95%: fixed. Every stored line now carries `ladder` (the chance of every line for that player or team and stat). When the Finder asks for a line we did not keep, the row gets a `forecast` with `from_ladder: true`, `p`, `band` ("above" or "below"), `p_display` ("95%+" or "under 50%"), no tier, `id: null` and `addable: false`. Show `p_display` when it is set, hide the tier, and show the + button disabled with the hint "Open the match to add this line". Re-run the engine once so existing rows get their ladder. A player or team with no line at all inside the band still has no row.
- The combined chance is a forecast, not a promise. The review sheet always shows the range.

## 7. "How our combined chances did" (client side, signed-in or not)

On My combos, finished tab: count combos where `result.reached == result.of`, count single lines reached, and show "Expected from our chances: about X combos" = the sum of each combo's saved chance. Always add "Two combos is a small sample." when fewer than 20 combos. Do not compute a win rate or a streak. No colours that suggest gain or loss: use the neutral tick.

## 8. Copy as text

```
Como v Venezia · Sun, Nov 1 · 6:30 AM
A. Douvikas 2+ shots: 68%
N. Paz 1+ shot: 83%
Como 12+ team shots: 68%
All together: 46% (About 1 in 2)
Forecast before lineups. Prediciotn
```
Share image: render the card from board 6 to a PNG in the browser (canvas) and use the Web Share API with a download fallback.

## 9. Settings added

`combo.max_lines` (public, 2 to 10, default 6) and `combo.pre_factors` (list). Both are in the Admin settings page under Engine.

## 10. Acceptance

- [ ] Tap + on 3 lines; the bar shows the same number as `POST /api/combo/estimate`.
- [ ] A line from another match asks "Start a new combo?" and never mixes matches.
- [ ] Two lines on one player show the note; the same stat twice is refused.
- [ ] Safer, Balanced and Bolder return 2, 3 and 4 lines or a clear reason.
- [ ] Save, Copy as text and Share image work on a phone.
- [ ] After a match, My combos shows which lines were reached.
- [ ] A Finder row for a 97% line shows "95%+", no tier, and a disabled +.
- [ ] `frontend/scripts/check-copy.js` passes with the single allow-listed disclaimer.
- [ ] `cd backend && bash run_tests.sh` prints 21 PASS lines.
