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
