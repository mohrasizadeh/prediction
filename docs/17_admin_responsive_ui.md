# 17. Admin panel on every screen: the responsive shell

The admin works on a computer, a tablet and a phone. On a phone the menu becomes an **app bar at the bottom** of the screen, like a mobile app. Open `prototype/admin_prototype.html` in a browser, switch the role at the top, and resize the window (or open it on a phone) to see it. It is a reference for layout and behaviour. It is not production code and its data is fake.

The prototype was checked in a real browser at 390 px, 820 px and 1280 px: no sideways scroll on any page, every bottom-bar target at least 44 px tall, no console errors, and the checks listed in §9.

## 1. Breakpoints

| Width | Layout |
|---|---|
| 1025 px and wider | Left **rail** (248 px) with every module in groups. Top bar with the page title, role and theme switch. Tables are tables. Editors open in a side panel or beside a live preview. |
| 1024 px and narrower (tablets, phones) | No rail. A fixed **bottom app bar**: 4 icons plus **More**. Tables become cards. Side panels become full-screen sheets. Editors stack: form first, preview below. |

Use one breakpoint. Do not make a third layout. A tablet in portrait gets the phone layout, with 4 columns of tiles in the More sheet instead of 3.

## 2. The menu comes from the server

`GET /api/admin/shell` →

```json
{ "user": {"id":"…","email":"…","role":"admin","display_name":""},
  "groups": ["Overview","People","Growth","Site","Money","E-mail","Connect","Data","System"],
  "modules": [{"id":"studio","label":"Site Studio","group":"Site","icon":"palette","route":"/admin/studio"}, …],
  "mobile_tabs": ["dashboard","users","analytics","studio"],
  "open_alerts": 2, "billing_mode": "test" }
```

- `modules` holds **only what this person may use** (32 modules exist in all, listed in `admin_shell.py`). Draw the rail and the More sheet from it. Never hard-code the menu.
- Hiding a module is a convenience. Every route still checks the permission on the server.
- `open_alerts` drives the red badge on Dashboard (phone) and Health (rail).
- Defaults for `mobile_tabs` are the first four allowed of: dashboard, users, analytics, studio, popups, inbox, subscriptions, logs. So an analyst gets Dashboard, Users, Analytics, Popups; support gets Users, Inbox, Subscriptions, Logs.

### Staff choose their own bar

`PUT /api/admin/shell/tabs {"ids": ["dashboard","studio","popups","analytics"]}`: 2 to 4 different modules the person may use; otherwise `400 BAD_TABS`. Saved on the person. In the More sheet a **Customize bar** button shows a pin on every tile (min 36 px). Pinning a fifth shows "Bottom bar holds 4. Unpin one first." Keep at least 2.

## 3. The bottom app bar (phones and tablets)

- Fixed to the bottom. Height 64 px plus the safe area (`padding-bottom: env(safe-area-inset-bottom)`). Page content gets bottom padding of the bar height + 28 px so nothing hides behind it.
- 5 equal buttons: the 4 tabs and **More**. Each at least 44 × 52 px. Icon 24 px, label 11 px bold, one line (shorten "Site Studio" to "Studio").
- Active tab: brand colour icon and label, plus a 3 px bar above the icon. `aria-current="page"`. If the current page is not one of the 4, **More** is the active one.
- Badge: a small red dot with a number on the icon (alerts).
- Background is the card colour at 94% with a blur, a 1 px top border. Respect `prefers-reduced-motion`.
- Label text must pass 4.5:1; the inactive grey is `text2`.

## 4. The More sheet

Opens from **More** (and from the menu button in the top bar on phones). A full-screen sheet, not a pop-over.

- Header: title "All tools", **Customize bar**, close (×, 44 px). Esc closes. Focus goes to the search box on open and returns to **More** on close. The page behind does not scroll.
- Search box (filters by name, live). Nothing matches → "Nothing matches."
- Tiles grouped by `groups`: 3 per row on phones, 4 on tablets. Tile: icon 26 px, label, at least 84 px tall. The current page is outlined.
- Bottom of the sheet: a Dark/Light switch for the admin itself (in the prototype) and Sign out (the builder adds it).
- Role-filtered: a tool the person may not use is not drawn at all (the test checks "search `pop` finds nothing for support").

## 5. Page patterns

| Pattern | Computer | Phone |
|---|---|---|
| **Table** (users, payments, logs) | Real table, sortable, filters in a row above | Each row becomes a card: the main field in bold, the others as small labelled chips. Filters collapse into a **Filters** sheet. Never a sideways-scrolling table. |
| **Detail** (a user, a payment) | Side drawer 480 px | Full-screen sheet with a back arrow. Actions at the bottom, sticky. |
| **Form** | Two columns when wide | One column. Inputs 44 px tall, 16 px text (stops iOS zoom). |
| **Charts** | 2 per row | 1 per row, full width. Every chart has a text title and an `aria-label` summary. |
| **Editors with preview** (Site Studio, Popups) | Form left, live preview right | Form first, preview below. The preview has its own Desktop / Phone switch and Dark / Light switch. |
| **Confirm dialogs** | Centred | Bottom sheet. The danger button is on the right, never the default focus. |
| **Toasts** | Bottom left | Above the bottom bar. `role="status"`. |
| **Publish bar** (Studio) | A bar at the top of the page: state, Preview link, Publish | Same, wraps to two lines. Publish is disabled with a short reason when blocked (for example unreadable colours). |

## 6. Touch and layout rules

- Targets at least 44 × 44 px (icon buttons, switches' tap area, tabs, tiles). Chips that act as buttons at least 36 px with 8 px between.
- No horizontal page scroll at 320 px. Only the tab strip inside a page may scroll sideways, with its scrollbar hidden.
- Grids use `minmax(0, 1fr)`, never plain `1fr` (a long word or a 360 px preview would stretch the page).
- Sticky top bar, 60 px. The bottom bar never covers the last row (content padding above).
- Safe areas: `viewport-fit=cover` in the viewport meta; use `env(safe-area-inset-*)` on the top bar, bottom bar and sheets.
- Text 15 px minimum in the admin (inputs 16 px). Numbers that matter 22 to 26 px.
- Dark and light for the admin itself, independent of the public site's theme. Default to the system setting; remember the choice per person.
- Keyboard: every control reachable, visible 3 px focus ring, sheets trap focus, Esc closes.
- Icons are inline SVG that inherit `currentColor` (the prototype has the full set used by the 32 modules).

## 7. Admin-only look

The admin does **not** use the visitor's Site Studio theme. It has its own small token set (the same names as the design system: `bg`, `surface1`, `surface2`, `surface3`, `border`, `text`, `text2`, `brand`, `up`, `down`, `warn`). A bad colour choice in Site Studio can never make the admin unreadable.

## 8. What the builder must build

1. The shell: rail, top bar, bottom bar, More sheet, role switch hidden in production (it exists in the prototype to demonstrate).
2. A `useAdminShell()` hook calling `GET /api/admin/shell` once at sign-in, plus the Customize bar flow.
3. A `<ResponsiveTable>` that renders a table at ≥1025 px and cards below, from one column definition (`{label, key, primary?, render?}`).
4. A `<Drawer>` that is a side panel at ≥1025 px and a full-screen sheet below.
5. The Site Studio, Popup Maker, Integrations, Analytics extras and E-mail list screens from `16`, and the existing screens from `10`, all built on those parts.
6. The shared screen states: loading skeletons, empty, error with the request id.

## 9. What was tested in the prototype

In a real Chromium, with the screen sizes 320, 360, 390, 820, 1024, 1025 and 1280 px (sideways-scroll and menu checks at all seven, screenshots at 390, 820 and 1280):

- Left rail from 1025 px up; bottom bar at 1024 px and below; they never show together.
- No sideways page scroll on Dashboard, Analytics, Users, Studio, Popups, Integrations and a stub page at 390 px.
- All bottom-bar buttons at least 44 px.
- Roles: admin sees Integrations but not Staff; support sees Users but not Studio; analyst sees Analytics but not Settings; owner sees everything. The bottom bar only ever holds tools the role may use.
- More sheet: search hides tools the role cannot use; Esc closes; pinning a fifth tool is refused; unpin then pin works.
- Studio: every preset passes the readability gate; an unreadable text colour disables Publish and shows why; fixing it re-enables Publish; the preview's phone bar changes when menu items are moved, hidden or pinned; the 5th phone-bar item is refused.
- Popup editor: a banned word or HTML disables Save and says why; the preview switches between centre, corner and banner.
- Tracking tags are locked for admin and available to the owner.

What the prototype does **not** prove: real data, real routes, screen-reader behaviour (labels and roles are in place; test with VoiceOver and TalkBack), or performance on a slow phone.
