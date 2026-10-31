# Prompt for Emergent: update 27 ("if he plays" and the lineup badge)

**Before you start:** install update 25 first (`UPDATE_25_PROMPT.md`). Upload `update_27_pack.zip`, then paste the box below.

---

> **Task: install update 27. Read `docs/27_if_he_plays_and_lineup_badge.md` completely first.**
>
> **Context:** a card said "1+ shot 82%" for a striker who had a shot in 9 of 9 games. The 82% mixed "will he play" with "will he shoot if he plays". On 140,000 real forecasts, players rated 80 to 85% reached the line about 90% of the time. We now show the number "if he plays", and his chance to play becomes a lineup badge. The engine is fixed and tested. Copy the backend files as they are and update the screens.
>
> **Step 1: backend. Copy these files exactly, at the same paths. Do not rewrite or "simplify" them.**
> - `backend/soccer_brain/engine.py`
> - `backend/engine_bridge.py`
> - `backend/calibration.py`
> - `backend/soccer_brain/calibration_default.json` (replaced)
> - `backend/soccer_brain/calibration_default_allin.json` (new)
> - `backend/settings_registry.json`
> - `backend/settings_store.py`
> - `backend/tests/selftest_lines.py`
> - `backend/tests/selftest_calibration.py`
> - `docs/11_settings_registry.json`
> - `docs/27_if_he_plays_and_lineup_badge.md`
> - `docs/validation/*` (research scripts)
> - `EMERGENT.md`
>
> If any of these files was changed in this project since the last pack, show me the difference before replacing it.
>
> Then run `cd backend && bash run_tests.sh`. It must show **18 PASS lines**. Stop and show me the log if not.
>
> **Step 2: re-run the engine.**
> - In Admin → Jobs, run `engine` for each enabled league.
> - In Admin → Settings, check: `engine.condition_on_play` = on, `engine.min_p_play` = 0.5. Keep them unless I say otherwise.
>
> **Step 3: screens (doc 27 §6). Change only these:**
> 1. **Lineup badge on every player card**, from `lineup_badge`:
>    - `confirmed` → "Confirmed starter";
>    - `likely` → "Likely lineup";
>    - `unsure` → "Lineup not sure" (muted);
>    - `bench` → "On the bench" (muted).
>
>    It replaces the "Likely starter" chip from update 25. Team cards show no badge.
> 2. **Caption under the percentage on player cards:** "if he plays", small and muted. Team cards show nothing.
> 3. **Detail sheet:** add "Chance he plays: {p_play}%". Show it only there. The percentage on the card never changes with it.
> 4. **Finder rows:** show the same small badge next to "Next {p}%", using `forecast.lineup_badge`. Hide it if it is missing.
> 5. **Insights filter chip** "Confirmed or likely lineup": filter the response on `lineup_badge` in (`confirmed`, `likely`).
>
> **Rules:**
> - Analysis only, no betting words. `yarn check-copy` must pass.
> - Times through `utc()`, images through `Crest` / `PlayerAvatar`, API through `lib/api.js`.
> - Do not change anything else in `backend/`.
> - Test at 390 px and 1280 px, light and dark.
>
> **Done when:**
> - 18 PASS lines.
> - A regular starter with a long run at the line shows a higher percentage than before, with the "Likely lineup" badge.
> - A player with a 40% chance to play has no card before lineups.
> - A player on the bench of a confirmed lineup shows "On the bench" and Watch at most.
>
> Send me screenshots of Insights, one match page, and the Finder.

---

## If you want the old behaviour back

In Admin → Settings:
- `engine.condition_on_play` off. This also switches to the old calibration map.
- Re-run `engine`.
