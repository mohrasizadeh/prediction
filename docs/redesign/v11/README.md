# v11 — every screen, captured

38 screens × 2 viewports = 76 page-views, taken from `backend/tests/demo_server.py` (the whole app
on simulated data, no keys and no MongoDB). Regenerate with the demo server running on :8011:

    cd backend && PORT=8011 python3 tests/demo_server.py      # terminal 1
    node scripts/capture.js && node scripts/capture_fold.js && node scripts/capture_index.js

## What is here

| path | what it is |
|---|---|
| `index.html` | **start here.** Every screen, both viewports, beside its measured numbers |
| `fold/*.png` | the first screen only, at real viewport height — what a reader judges in one second |
| `shots/*.png` | the whole page, top to bottom (a match page runs to 22,000px) |
| `html/*.html` | the rendered DOM, standalone: opens in a browser with no server and no build |
| `html/page.css` | the computed stylesheet all the captures share |
| `inventory.json` | per screen: every font size, colour, background, radius, gap in use; tap targets under 44px; text under 12px; headings; landmarks; JS errors |

The HTML is the **rendered DOM**, not the JSX. The source is ~90 components across twenty
stylesheets with runtime themes; what a reader sees is the computed result, and that is the only
thing worth reviewing.

## Read the numbers before the pictures

Measured across the phone captures:

- **no horizontal overflow on any screen**, no image without `alt`, no button without an accessible
  name, no JavaScript errors
- **39 distinct font sizes**, including 10px, 10.5px, 12.5px, 13.5px, 14.5px, 18.48px, 28.56px —
  the un-rounded values suggest `rem` or `clamp()` arithmetic rather than a chosen scale
- **9 text colours but 42 background colours** — the asymmetry is the signal
- **15 radii and 31 gap values**

## Two things that are NOT design faults

Anyone reviewing these needs to know, or they will file both as bugs:

1. **Crests and player photographs are placeholder shields and initials.** The demo database has no
   images. On the live site these are real.
2. **"Team 0", "Player 702", "Test League"** are simulated names, and the referee page could not be
   captured at all because the demo data has no referees.

## And one caveat on the counts

`smallTapTargets` counts everything tappable under 44×44, which includes things that legitimately
are not buttons. On `match.phone`, of the 40 flagged: the `k-chip` filters (40px tall), the
`lk-tk` / `lk-mkt` chips (33px) and the `btn--sm` Sign in / Sign up buttons (36px) are **real**
misses; the visually-hidden "Skip to content" link and inline links inside sentences are **not**.
Check each one against the capture before acting on it.
