# Prompt for Emergent: update 28 (the combo builder)

**Before you start:** install update 27 first (`UPDATE_27_PROMPT.md`). Upload `update_28_pack.zip`, then paste the box below.

---

> **Task: install update 28. Read `docs/28_combo_builder.md` completely first. Then open the pictures in `docs/28_boards/` (PNG and HTML, 9 screens).**
>
> **Context:** our users want one thing: put lines from one match together and see an honest combined chance, fast, on a phone. The math and the API are built and tested. You build the screens. Never use a word from `docs/03`, never show prices, never link to sellers.
>
> **Step 1: backend. Copy these files exactly, at the same paths. Do not rewrite or "simplify" them.**
> - `backend/combo.py` (new), `backend/engine_bridge.py`, `backend/queries.py`, `backend/tests/selftest_lines.py`, `backend/tests/selftest_queries.py`
> - `backend/routes_data.py`, `backend/routes_me.py`, `backend/accounts.py`, `backend/mongo_init.py`
> - `backend/settings_registry.json`, `backend/settings_store.py`, `docs/11_settings_registry.json`
> - `backend/tests/selftest_combo.py` (new), `backend/run_tests.sh`
> - `docs/28_combo_builder.md`, `docs/28_boards/*`, `docs/validation/*`
> - `EMERGENT.md`
> - the older docs and mockups that had banned words fixed (listed in `docs/28` §3)
>
> If any of these was changed in this project since the last pack, show me the difference before replacing it.
>
> Then run `cd backend && bash run_tests.sh`. It must show **21 PASS lines**. Stop and show me the log if not.
>
> **Step 2: screens (docs/28 §1, §2 and the boards). Build in this order and stop after each one so I can look:**
> 1. **Match page lines list:** a 44 px round + on every row; it becomes a tick. Selected rows get the brand tint. Group by team.
> 2. **Combo bar** above the tab bar: avatars, "N lines · X%", "About 1 in N · before lineups", Review button. It calls `POST /api/combo/estimate` after each tap (debounce 150 ms). Add 76 px bottom padding to the page while it shows.
> 3. **Review sheet:** hero number, range, rows with "N% if he plays · M% to play" and the chance including playing, the "Weakest line" tag (`weakest`), alternative-line chips (one estimate call per chip), `notes`, sticky actions.
> 4. **Build one for me** sheet: Safer, Balanced, Bolder from `GET /api/matches/{id}/combo-suggest`. Handle `lines: []` with the `reason`.
> 5. **Save, Copy as text, Share image** (docs/28 §8). Signed out: ask to sign in, keep the combo in sessionStorage.
> 6. **My combos** page and the "How our combined chances did" card (docs/28 §7). Add the Combos tab with a count badge.
> 7. **Add from anywhere:** + on Finder and Insights rows. A line from another match opens "Start a new combo?".
> 7b. **Finder rows with `forecast.from_ladder`:** show `p_display` when set ("95%+"), no tier, disabled + (docs/28 §6). After copying the backend, run `engine` once per league so every row gets its ladder.
> 8. **Computer layout:** lines left, sticky 380 px combo panel right (breakpoint 1024 px).
>
> **Rules:**
> - Do not change the engine, `combo.py` or the correction numbers. If a number looks wrong, tell me.
> - The only allowed use of "betting" is the footer sentence in `copy.disclaimer`. Run `node frontend/scripts/check-copy.js`; it must pass.
> - Show a tier with dots and a word, never colour alone. Tap targets 44 px or more.
> - Errors: show the `message` from the API in plain words. No stack traces.
>
> **Step 3: check and report.** Walk through `docs/28` §10 and tick each item. Show me a screenshot of each screen at 390 px and the computer layout. List anything you could not do.
