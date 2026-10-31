# Prompt for Emergent: update 25 (fitted lines, normalised averages, referees)

Upload `update_25_pack.zip`, then paste the box below.

---

> **Task: install update 25. Read `docs/25_lines_normalised_averages_referees.md` completely first.**
>
> **Context:** forecasts looked generic. Everyone got "12+ shots" or "1+ shot", likely starters were stuck at Watch, and averages let one big game push them around. The engine and bridge are fixed and tested. Your job is to copy the backend files in as they are and update the screens.
>
> **Step 1: backend. Copy these files exactly, at the same paths. Do not rewrite or "simplify" them.**
> - `backend/soccer_brain/engine.py`
> - `backend/engine_bridge.py`
> - `backend/queries.py`
> - `backend/server.py`
> - `backend/jobs.py`
> - `backend/referees.py` (new)
> - `backend/settings_registry.json`
> - `backend/settings_store.py`
> - `backend/tests/selftest_lines.py` (new)
> - `docs/11_settings_registry.json`
> - `docs/25_lines_normalised_averages_referees.md`
> - `docs/validation/*` (research scripts)
>
> If any of these files was changed in this project since the last pack, show me the difference before replacing it.
>
> Then run `cd backend && bash run_tests.sh`. It must show **18 PASS lines**. Stop and show me the log if not.
>
> **Step 2: re-run the engine.**
> - In Admin → Jobs, run `engine` for each enabled league.
> - Then run `referees`.
> - In Admin → Settings, check these values. The pack sets them; keep them unless I say otherwise:
>   - `engine.auto_lines` = on;
>   - `engine.feed_sort` = edge;
>   - `engine.likely_starter_p` = 0.85;
>   - `engine.style_half_life` = 20.
>
> **Step 3: screens (doc 25 §5). Change only these:**
> 1. **Forecast card "usual" line:**
>    - Show `Usually {p_usual}%`.
>    - Delete the "−27 pts vs usual (100% in last 10)" line and any use of `p_raw` on cards.
>    - The tick on the bar sits at `p_usual`.
> 2. **Tier note:** if `tier_note` is set, show it under the tier badge (small, muted).
> 3. **Likely starter:** if `tier_basis` is `likely_starter`, the lineup chip says "Likely starter".
> 4. **Team cards:**
>    - Show the club name (`team`) and its crest through `Crest`.
>    - Never show the word "Team" as a name.
> 5. **Names:** shorten the first name, never the surname ("R. Højlund").
> 6. **Insights sort control** (segmented):
>    - "Different from usual" (default) passes `sort=edge`;
>    - "Most likely" passes `sort=likely`;
>    - "Kick-off" passes `sort=kickoff`.
>
>    `GET /api/insights` also accepts `stat`, `scope`, `leagues`, `tiers`. Use them for the filter chips instead of filtering in the browser.
> 7. **Match page:** if `referee` is present, show `referee.sentence` under the context chips.
> 8. **Referees page:**
>    - Use `GET /api/leagues/{id}/referees`.
>    - Columns: Referee, Matches, Cards per game (`cards_per_game_normalised`, one decimal), vs teams' usual (`factor` as +6% / −4%).
>    - The plain `cards_per_game` goes in small grey text under the normalised number.
>    - Sort by Matches.
>    - If the list is empty, the empty state says: "Referee numbers appear once matches with a named referee and cards are in."
> 9. **Reasons:** the card shows `reasons[0]`; the detail sheet shows all of `reasons`. Never write your own reason text.
>
> **Rules:**
> - Analysis only, no betting words. `yarn check-copy` must pass.
> - Times through `utc()`, images through `Crest` / `PlayerAvatar`, API through `lib/api.js`.
> - Test at 390 px and 1280 px, light and dark.
>
> **Done when:**
> - 18 PASS lines.
> - Insights shows varied lines (for example "4+ shots", "15+ shots", "7+ corners", not only 12+ / 5+ / 1+).
> - A likely starter can show Solid or Strong before lineups.
> - The card says "Usually X%".
> - The referees table shows normalised numbers.
>
> Send me screenshots of Insights, one match page, and the Referees page.

---

## If you want the old behaviour back

These are all in Admin → Settings:
- `engine.auto_lines` off;
- `engine.feed_sort` = likely;
- `engine.likely_starter_p` = 1.0;
- `engine.style_half_life` = 0, `engine.style_opp_adjust` = [], `engine.style_cap_q` = 0.
