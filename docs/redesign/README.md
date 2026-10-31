# Redesign mock-ups: how to read them

- **Spec:** `docs/24_ui_redesign.md`. The pictures here belong to its sections.
- **`mockups/`:** 25 full-size pictures, named by page. Phone pictures are 390 px wide; computer pictures are 1180 px wide. Both are shown at 2x.
- **`mockup_source/`:** the HTML and CSS that drew the pictures.
  - Open one in a browser to inspect spacing, radius and font sizes.
  - The colour variables match `frontend/src/styles/tokens.css`:
    - light `--bg #F5F7FB`, `--brand #4F46E5`, `--strong #0D9488`;
    - dark `--bg #0A0E17`, `--brand #7C83FF`, `--strong #2DD4BF`.
  - This is reference only. Build real React components; do not paste this markup into the app.
- **Yellow numbered tags** are notes, not design.
- **Names, numbers and prices** are examples. The app shows API data only.

## Picture to page

| Picture | Page / component | Route |
|---|---|---|
| `components_light_dark.png`, `forecast_card_and_sheet.png` | Shared components | all |
| `today_desktop_light.png`, `today_phone_dark.png` | Today | `/` |
| `live_sheet_dark.png` | Live sheet and page | live pill, `/live` |
| `match_states.png`, `match_preview_phone.png`, `match_lineups_pitch.png` | Match centre | `/match/:id` |
| `insights_filters_dark.png` | Insights | `/insights` |
| `finder_sentence_builder.png` | Finder | `/finder` |
| `explore_phone.png` | Explore | `/leagues` (named Explore) |
| `league_teams_phone.png` | League | `/league/:id` |
| `team_squad_cards_dark.png`, `team_squad_grid.png` | Team | `/team/:id` |
| `compare_dark.png` | Compare | `/compare` |
| `player_phone.png` | Player | `/player/:id` |
| `following_dark.png` | You / Following | `/following` |
| `track_record.png` | Track record | `/track-record` |
| `search_dark.png` | Search overlay | header, `/search` |
| `welcome_flow.png` | Welcome after sign-up | after `/sign-up` |
| `pricing_and_lock_sheet.png` | Pricing and locked items | `/pricing` |
| `learn_dark.png` | Learn | `/learn` |
| `states_loading_empty_error.png` | Loading, empty, error | every list |
| `email_footer_dark.png` | Weekly e-mail box and footer | every page |
| `admin_health_board.png` | Admin home | `/admin` |

## Known data gaps (hide these until the API provides them)

| Element | Needs | Status |
|---|---|---|
| "Usual" tick on the forecast card bar | the player's usual rate for that line | Not in the card yet. Hide the tick. |
| League **Table** tab (standings) | a standings route | Not built. Hide the tab, or compute it from results only if a route is added later. |
| League Overview "Hot right now" | results-form change per team | Partly in `context`. Show only when present. |
| Live "momentum" bar | events by minute | Use `live_events`. Hide if there are fewer than 3 events. |
| Finder "Streak" mode | the streak from the finder route | Show the mode only if `/api/finder` accepts it. |
| Player league rank ("3rd of 61") | rank in leaderboard | Use `GET /api/leagues/{id}/leaderboard` if it covers the stat; otherwise hide. |

Already available and used:
- `why` (reason sentences);
- `p_play` (chance he plays; pitch view);
- `availability` and `context`/`stakes` (match page);
- `cards` and `more_lines`;
- `track-record` `tiers` and `bins`;
- `following-feed`;
- `live` and `live_events`.

Emergent adds any new gap to `DATA_GAPS.md` in this folder.
