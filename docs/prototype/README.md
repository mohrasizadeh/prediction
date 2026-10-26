# Admin prototype

Open `admin_prototype.html` in a browser. No server needed. Data is fake. Use the role switch at the top (Owner, Admin, Support, Analyst) and resize the window, or open it on a phone.

- 1025 px and wider: left rail. 1024 px and narrower: bottom app bar with 4 icons and More.
- Site Studio: pick a look, change colours, fonts, corners, button style, menu items and the phone bottom bar. The preview has Dark/Light and Desktop/Phone. Publish is blocked when text is unreadable.
- Popups: edit a popup and watch the preview (centre, corner, banner). Banned words and HTML disable Save.
- Integrations: e-mail provider, list sync, webhooks, tracking tags (locked for admin).

`template.html` + `build.py` regenerate `admin_prototype.html` from the real code (module list, role permissions, presets, fonts, banned words), so it cannot drift: run `python build.py` from this folder with `backend_reference` next to it.
`screens/` has screenshots.
