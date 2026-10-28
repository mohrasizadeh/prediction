# Prompt for Emergent: UI/UX redesign

Paste the box below into Emergent. Upload this whole pack first. Then run one phase per conversation, in order.

---

> **Task: rebuild the user-facing screens to match the redesign in `docs/24_ui_redesign.md`.**
>
> **Read first, completely, before writing code:**
> - `docs/24_ui_redesign.md`: the spec, page by page.
> - Every picture in `docs/redesign/mockups/`. Each picture sits under its page in doc 24.
> - `docs/redesign/README.md`: how to read the mock-ups.
> - The rules docs: `EMERGENT.md`, `docs/03_rules_and_compliance.md`, `docs/04_design_system.md`, `docs/15_security_and_privacy.md`. They still override everything.
>
> **What the mock-ups are:**
> - They show layout, order, sizes and colours.
> - They use our real tokens from `frontend/src/styles/tokens.css`. Do not invent new colours.
> - `docs/redesign/mockup_source/*.html` is the HTML/CSS behind them. Use it to read exact spacing, radius and font sizes.
> - Do not copy that HTML into the app. Build real React components.
> - The yellow numbered tags are notes for you, not part of the design.
> - Names, numbers and prices in the pictures are examples. Every number on screen comes from the API.
>
> **Rules for the whole redesign:**
> 1. **Frontend only.** Do not change `backend/` or `backend/soccer_brain/`.
>    - If a screen needs data the API does not return, hide that element. Do not fake it.
>    - Add the gap to `docs/redesign/DATA_GAPS.md` (screen, element, field needed).
>    - Known gaps are listed in `docs/redesign/README.md`.
> 2. **Keep what works.** Keep the logic, routes and API calls in:
>    - `pages/Today.jsx`, `League.jsx`, `Compare.jsx`, `Live.jsx`, `Auth.jsx`;
>    - `components/TeamMatrix.jsx`, `TeamRadar.jsx`, `MatchEvents.jsx`, `LiveStatus.jsx`, `Media.jsx`, `States.jsx`.
>
>    Restyle them; do not rewrite their data code.
> 3. **Forecast lists** render `cards` and `more_lines`, never raw `forecasts` rows (doc 21).
> 4. **Images** only through `Crest`, `LeagueMark`, `PlayerAvatar`. **Times** only through `utc()`. **API** only through `lib/api.js`.
> 5. **Light and dark.** Every screen works in both, using the token variables.
>    - Screenshot each finished screen in both modes.
>    - Screenshot at 390 px and at 1280 px wide.
> 6. **Accessibility:**
>    - 44 px touch targets.
>    - Colour always comes with a word or icon (tiers: colour + word + dots).
>    - Contrast 4.5:1.
>    - Respect "reduce motion".
>    - Charts get screen-reader labels.
> 7. **Wording:**
>    - Analysis only. No betting words (doc 03). Run `yarn check-copy`.
>    - No countdown pressure or "only X left" on Pricing.
> 8. **Every list** has loading (skeletons in the card's shape), empty (why, plus a next step) and error (one sentence plus "Try again") states.
> 9. **After each phase:**
>    - `cd backend && bash run_tests.sh` still shows 17 PASS lines.
>    - Send me the screenshots before you start the next phase.
>
> **Phases (one per conversation):**
>
> **Phase R1: shared components** (doc 24, "Components to build once"; picture `components_light_dark.png`). Build these in `frontend/src/components/ui/`:
> - `ForecastCard` and `ForecastSheet` (picture `forecast_card_and_sheet.png`);
> - `DateScroller`, `ChipsRow`, `Segmented`, `FilterSheet` (bottom sheet), `RangeSlider` (one or two thumbs);
> - `HitStrip`, `WdlBar`, `TierBadge`, `LivePill`, `LiveCard`, `BottomSheet`, `Skeleton`, `EmptyState`, `ErrorState`.
>
> Add a hidden page `/dev/kit` that shows every component in both themes, like the picture. No page changes yet.
>
> **Phase R2: shell and navigation** (doc 24, "Across the whole app").
> - Five items: Today, Insights, Finder, Explore, You.
>   - Bottom tabs on phones; a left rail on computers.
>   - Referees, Teams, Learn, Plans and Track record move under Explore and the footer.
> - Floating live pill on every page while something is live. It opens the live sheet.
> - The header search opens the full-screen search overlay.
> - The footer, and the weekly e-mail box (picture `email_footer_dark.png`).
>   - Keep the existing sign-up route and its consent rules.
>   - Show the consent sentence under the button.
>
> **Phase R3: match-day pages.**
> - **Today** (`today_desktop_light.png`, `today_phone_dark.png`).
> - **Live** sheet and `/live` (`live_sheet_dark.png`).
> - **Insights** (`insights_filters_dark.png`).
> - **Match page** in its four states (`match_states.png`, `match_preview_phone.png`, `match_lineups_pitch.png`).
>   - The hero and first tab change with the match status.
>   - Lineups tab: the pitch view. Use each player's `p_play` for "chance he starts". Dashed and faded below 70%.
>
> **Phase R4: power tools.**
> - **Finder** as a sentence builder (`finder_sentence_builder.png`). Each underlined part opens a small picker. Results update live.
> - **League** tabs: Overview, Table, Teams, Fixtures, Leaders (`league_teams_phone.png`). On phones, Teams shows one stat as ranked bars; the full matrix is behind "Show all stats".
> - **Team** (`team_squad_cards_dark.png`, `team_squad_grid.png`).
> - **Compare** (`compare_dark.png`): edge bars and "What stands out". Keep the radar.
> - **Player** (`player_phone.png`).
>
> **Phase R5: retention and the rest.**
> - **Explore** (`explore_phone.png`).
> - **You / Following** (`following_dark.png`).
> - **Track record** (`track_record.png`): when `ready` is false, show "We publish this after N scored forecasts".
> - **Search** (`search_dark.png`).
> - **Welcome flow** after sign-up (`welcome_flow.png`): 3 steps, each skippable. It saves follows and alert choices through the existing routes.
> - **Pricing** and the locked-feature sheet (`pricing_and_lock_sheet.png`): prices and limits from `GET /api/plans` and entitlements.
> - **Learn** (`learn_dark.png`).
>
> **Phase R6: admin home** (`admin_health_board.png`).
> - Six health tiles and the "Needs you" inbox, using the existing admin routes.
> - Everything else in admin keeps its current screens.
>
> **Done when:**
> - Every screen matches its picture at 390 px and 1280 px, in light and dark.
> - All checks above pass.
> - `docs/redesign/DATA_GAPS.md` lists anything left hidden.

---

## Why not the PDF

A PDF works for a person, but it is weak input for a coding agent:
- The pictures get shrunk.
- Tables and lists turn into broken text.
- The agent cannot open a picture on its own, or read the exact CSS.

This pack gives Emergent:
- the spec as Markdown, which it reads exactly;
- each picture as its own full-size file, named by page;
- the HTML/CSS source behind the pictures, with our real colour tokens.

Put the pack into the repo (or upload the zip). Then point Emergent at the files, as the prompt does.
