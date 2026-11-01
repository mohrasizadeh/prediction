# Apple HIG redesign

The public site follows Apple's Human Interface Guidelines (skills in `.claude/skills/hig-*`, project context in
`.claude/apple-design-context.md`). It is still a web app: HIG principles are applied as web patterns, not native APIs.

Pictures: `before_after_phone.png`, `before_after_desktop.png`.

## What changed

| Layer | File | Change |
|---|---|---|
| Default theme | `backend/site_studio.py` | New default palette from HIG semantic system colours (grouped backgrounds, label colours, separators, system tints). System font (San Francisco on Apple devices), heading weight 700, no card shadows, capsule buttons, hover darkens instead of lifting. |
| Presets | `backend/site_studio.py` | New **Apple** preset (the default). The previous look is kept as the **Midnight** preset. Other presets now sit on the HIG neutrals. |
| Tokens | `docs/design_tokens.json` → `frontend/src/styles/tokens.css` | Same palette; HIG text styles listed under `font.hig_text_styles_px`. |
| Fallback | `frontend/src/styles/base.css` | Fallback layer matches the new default. |
| Structure | `frontend/src/styles/hig.css` (loaded last) | Bars on a translucent blurred material, tab bar with tint-only selection, macOS-style sidebar, inset grouped cards with hairline separators, tint-coloured selection for chips, days and tabs, iOS segmented control, filled search field, white form fields on the grouped background, sheets with a dimming scrim, and a pressed state that dims. Only `var(--...)` colours are used, so Site Studio edits still apply. |

## Accessibility

- Every text colour passes 4.5:1 on `bg`, `surface1` and `surface2` in both modes. Where a standard system tint fails, the HIG increased-contrast variant is used (for example light blue `#0066CC`, light green `#1D7A32`, dark blue `#409CFF` with black text).
- Respects `prefers-reduced-transparency` (solid bars), `prefers-contrast: more` (stronger separators and outlines) and `prefers-reduced-motion` (already in place).
- Touch targets stay 44 px or larger; focus rings are unchanged.

## Fixes found on the way

- Header "Sign up free" button showed as a blank brand-coloured pill when the Site Studio CSS was missing: the unlayered `a { color }` rule beat the fallback `.btn--primary`. It is now `a:where(:not(.btn))`.
- `tests/demo_server.py` sent `style-src 'self'`, which blocked the Site Studio `<style>`, so the demo never showed the configured theme. It now matches docs/15 (`'unsafe-inline'` for styles).

## Going back

Admin → Site Studio → Presets → **Midnight**, then Publish.

## Pass 2 (2026-11-01): every remaining screen, popup and the admin

Pass 1 covered the public shell and the shared cards. Pass 2 covers what was left.

| Layer | File | Change |
|---|---|---|
| Accessibility fixes | `frontend/src/styles/hig.css` | The tinted chips pass 1 introduced printed their word in the tint colour, which fails 4.5:1 at a 14% tint (docs/36 A11Y-1). The Beta badge, tier chips, "Lineups confirmed" tag, the selected day's label and the saved-line tag now print in the normal text colour; the dots and the tint still carry the meaning. The segmented control goes back to 44 px on touch (docs/36 A11Y-6). |
| Visitor popups | `frontend/src/styles/hig.css` | All four kinds an admin can build. Modal and slide-in become sheets on the thick material with a hairline instead of a 1 px border and no heavy shadow. Top and bottom banners sit flush as chrome, as HIG asks, rather than floating as cards. |
| Alerts and toasts | `frontend/src/styles/hig.css` | The confirm dialog is a sheet on a phone and a centred 340 px alert on a larger screen, with HIG type sizes. Cancel left, action right, destructive in red: the component already did this. Toasts become a floating capsule on the material. |
| Remaining public screens | `frontend/src/styles/hig.css` | Today, Insights, Match, Live, You, Following, Track record, Learn, Pricing, Compare, Team matrix, Combo builder, Finder and the shared tables: grouped rows with hairline separators, no card borders or shadows, capsule chips, tint for selection, system fills behind bars and meters. |
| Admin | `frontend/src/styles/hig-admin.css` (new) | The admin keeps its own tokens and its own light/dark switch (docs/17), re-pointed to the same Apple system colours as the public site. Every text pair was checked at 4.5:1 or better in both modes. A macOS source-list sidebar, material bars, hairline tables with quiet headers, iOS segmented controls, capsule chips and buttons, and the same reduced-transparency and increased-contrast fallbacks. |
| Fonts | `frontend/src/index.js`, `frontend/package.json` | The admin was the last user of Plus Jakarta Sans and Manrope. With it on the system font, 14 unused `@fontsource-variable` packages go, and with them 134 KB of web fonts that shipped in every build (docs/36 PERF-10). Site Studio's own fonts are separate files in `frontend/public/fonts/` and are untouched, so owner font choices still work. |

### Checked

- Build passes; `yarn check-copy` passes.
- 20 screens across phone-light and desktop-dark, public and admin: no page or console errors.
- Admin palette contrast computed for every text pair in both modes: all at or above 4.5:1.
- Admin screens were verified signed in as the owner (the demo owner must change its first password and enrol two-step sign-in before the admin renders).

### Not done

A full before-and-after image set for all ~50 screens was started and not finished. The baseline is captured; the matching after-set is not. Re-run `axe` for the contrast rules once it is.
