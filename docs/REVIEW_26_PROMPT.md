# Prompt for Emergent: design review 26

**Before you start:** install update 25 first (`UPDATE_25_PROMPT.md`). Items 3, 8, 9 and 10 below need its data.

Upload `review_26_pack.zip`, then paste the box below.

---

> **Task: apply the design review in `docs/26_design_review.md` to Today, Insights, Finder and Explore.**
>
> **Read first, completely, before writing code:**
> - `docs/26_design_review.md`;
> - every picture in `docs/review/pictures/`. Each one sits under its section in doc 26;
> - `docs/24_ui_redesign.md` for the shared components;
> - `EMERGENT.md` and `docs/03_rules_and_compliance.md`. Their rules still apply.
>
> **About the pictures:**
> - Files ending in `_now_marked.png` are our current screens, with numbered red marks on each problem.
> - The other files are the target design. Yellow numbered pins match the numbered list under each picture.
> - `docs/review/mockup_source/review_mockups.html` is the HTML/CSS behind them, using our real colour tokens. Use it to read spacing and sizes. Do not paste it into the app; build real React components.
> - Names and numbers in the pictures are examples. Every number on screen comes from the API.
>
> **Rules:**
> - Frontend only. Do not change anything in `backend/`.
> - If a field the design needs is missing, hide that element and add a line to `docs/redesign/DATA_GAPS.md`. Never fake data.
> - Keep the data logic of the existing pages; change layout and components.
> - Images through `Crest` / `PlayerAvatar`. Times through `utc()`. API through `lib/api.js`.
> - Never show our internal `round` to users.
>
> **Do the 18 items in the fix list (doc 26, last section) in order, in 4 batches. Stop after each batch and send me screenshots** at 390 px and 1280 px wide, in light and dark mode:
> - **Batch 1, items 1 to 5:** match row states, remove "Round N", zero chips and counts, bottom tab bar on phones. Item 3 is update 25: check it is installed.
> - **Batch 2, items 6 to 8:** Today: our-call chip, summary line, Top picks.
> - **Batch 3, items 9 to 14:** Insights filters and card; Finder tokens, pre-picked league, mode tabs, limit bar.
> - **Batch 4, items 15 to 18:** Explore list, follow card, tools; the computer right column.
>
> **Before you finish:**
> - `cd frontend && yarn check-copy` passes.
> - `cd backend && bash run_tests.sh` shows 18 PASS lines.

---

## Why a zip and not the PDF

A coding agent reads Markdown exactly. It can open each picture full size, and it can read the CSS behind the pictures. A PDF shrinks the pictures and breaks the tables.
