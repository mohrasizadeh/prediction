# v11 — every screen, captured

**29 public screens** × 2 viewports, taken from `backend/tests/demo_server.py` (the whole app
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

## The nine admin screens are NOT captured

They are in the folders, and they are all the public 404 page. The owner must pass three gates —
sign in, enrol in two-factor, then choose a password — and the harness gets through the first two
but not reliably the third, so the capture runs anonymous and `/admin` falls through to the public
404. **Ignore every `admin-*` file.** Reviewing them would be reviewing a 404 nine times.

That the first sign-in enrols two-factor and every later one is challenged for a code is itself
worth knowing: the harness signs in four times, so a helper that can only enrol gets through once.

## Two things that are NOT design faults

Anyone reviewing these needs to know, or they will file both as bugs:

1. **Crests and player photographs are placeholder shields and initials.** The demo database has no
   images. On the live site these are real.
2. **"Team 0", "Player 702", "Test League"** are simulated names, and the referee page could not be
   captured at all because the demo data has no referees.

## The counts are now measured with a coarse pointer

An earlier run of this harness called `newContext({ viewport })` with no `hasTouch` or `isMobile`,
so every `@media (pointer: coarse)` rule in the stylesheet was inactive and the capture measured
sizes no reader ever sees. Nine such rules exist. Measured both ways on `match`:

| | without the flags | with them (a real phone) |
|---|---|---|
| `a.btn--sm` Sign in / Sign up | 36px | **44px** |
| `.k-chip` | 40px | **44px** |

The flags are set now, and the effect is not small: `match.phone` went from **40** flagged tap
targets to **7**. `.lk-tk` and `.lk-mkt` also carry their own 44px hit area through a `::after`
(`height:44px; left:-6px; right:-6px`), which a bounding box never shows.

## And one caveat on the counts

`smallTapTargets` still counts things that legitimately are not buttons. Of the 7 now flagged on
`match.phone`: the visually-hidden "Skip to content" link, the brand mark (22px wide but 44 tall)
and the footer links (44 tall, narrow) are **not** faults. `a.avatar-btn` at 36×36 and
`button.linkish` "Privacy choices" at 116×31 are worth a look. Check each against the capture.
