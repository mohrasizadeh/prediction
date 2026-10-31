# Prompt for Emergent: update 28 (the combo builder), already built

The screens, the backend and the tests for update 28 are already in this repo (branch `main`). Pull them. Do not rebuild them. Read `docs/28_combo_builder.md` first, then paste the box below.

---

> **Task: pull the latest `main` and check update 28. Do not rewrite or "simplify" any file listed below.**
>
> **Already built (read only):**
> - Backend: `backend/combo.py`, the combo routes in `backend/routes_data.py` and `backend/routes_me.py`, `backend/engine_bridge.py` (the stored `ladder`), `backend/queries.py` (`_from_ladder`).
> - Screens: `frontend/src/lib/combo.jsx` (open combo), `components/ComboHost.jsx` (combo bar, review sheet, "Start a new combo?"), `components/BuildForMe.jsx`, `pages/Combos.jsx` (route `/combos`), the + button and lineup badge in `components/ui/ForecastCard.jsx`, the Combos tab in `components/Layout.jsx`, styles in `styles/combo.css`.
>
> **Step 1.** Run `cd backend && bash run_tests.sh`. It must print **21 PASS lines**. Run `cd frontend && node scripts/check-copy.js`. It must pass. Show me both logs.
>
> **Step 2.** In Admin → Jobs, run `engine` once for each enabled league, so every forecast gets its `ladder`.
>
> **Step 3.** Open a match in the preview, on a phone and on a computer, and tick each line of `docs/28_combo_builder.md` §10. Show me a screenshot of: the match Forecasts tab with + buttons, the combo bar, the review sheet, "Build one for me", My combos (coming up and finished), and a Finder row for a line above 95%.
>
> **Step 4.** Tell me anything that does not match the boards in `docs/28_boards/`. Fix only what I approve.
>
> **Rules:** never use a word from `docs/03`; the only allowed use of "betting" is the footer sentence in `copy.disclaimer`; do not change the engine, `combo.py` or the correction numbers.
