# v6 — the items the v3 audits and the v4 specs left open

Written after the v3/v4/v5 rounds shipped. Every item below was named in
`docs/redesign/v3/audit/*` or `docs/redesign/v4/*` and left undone there; this file records what
was done about each and why, plus the one that is not mine to decide.

---

## 1. Sign-in told an attacker which e-mails have accounts

`backend/accounts.py`. The lockout was read **before** the password, and only an address that
exists has a user record to read it from. So five wrong passwords against a real address turned the
reply from `401 BAD_CREDENTIALS` into `429 LOCKED`, while an address nobody holds stayed on 401 for
ever: six requests named whoever holds an e-mail.

Everything else on that screen was already blind to it — `register` hashes before the lookup and
answers the same either way, `request_reset` always answers 202, and `verify_password` runs one
bcrypt comparison against a dummy hash when there is no user, so the timing matches. This was the
one hole left.

The lock is now read **after** the credentials. A wrong password is 401 whatever the state of the
account, and only someone who typed the right password is told the account is held. The lockout is
exactly as strong — the right password still does not sign in while the lock stands — and the
message stays where it is useful, on the one person who can act on it. The `429` is now logged with
`reason: "locked"`, which it was not before.

`selftest_accounts.py` asserts a wrong password on a held account is indistinguishable from a wrong
password on an unknown address, and that the right password still hits the lock.

## 2. P-33 drew a working form on a dead link

`SCREENS-auth.md` finding 5. With no token, an expired token or a spent token, the reset screen
rendered a complete, enabled, confident form. The reader invented a password, typed it twice, and
*then* learned the link was dead — on a screen with no way to ask for a new one.

- New `POST /auth/reset-password/check` reads the token with `peek_token` (which does not spend it;
  `consume_token` does) and answers `{valid}`. POST rather than GET so the token does not land in
  an access log or a referrer a second time. Rate limited, though guessing a 32-byte random token
  is not a route anyone can walk.
- `ResetPassword` asks before it draws anything. Three states: asking, good, dead. A network error
  answering the check is our fault, not the reader's, so it falls through to the form.
- A dead link now offers the one useful thing: another link. The e-mail field and the resend button
  post to the same `/auth/forgot-password` the forgot screen uses, so the reader does not go back a
  step.
- `NewPasswordForm` gained `noValidate` and states the 10-character rule itself (finding 9). The
  raw Chromium bubble — grey-and-orange OS chrome over a dark form — was covering the hint that
  says the rule.

`selftest_server.py` asserts a live link reads live, a link nobody issued reads dead, reading does
not spend the link, and a spent link reads dead.

## 3. Eighteen admin actions that spent money, mailed real people or destroyed work, with no dialog

`SCREENS-admin.md` §3 counted them, and several sat beside a **guarded** action of lower
consequence: delete-a-webhook asked, rotate-its-secret did not; delete-a-popup asked,
publish-it-to-every-visitor did not; add-a-note asked, e-mail-the-member did not.

The answer is not a dialog on everything — a guard that is identical everywhere is one people learn
to click through, which is worse than none. So there is now one component, `Guard` in
`frontend/src/admin/parts.jsx`, and one ladder graded by cost, so a new button cannot quietly land
on the wrong rung:

| Rung | For | Examples now on it |
|---|---|---|
| nothing | cheap, reversible, scoped to you | cached Explorer run, "Send me a test", Pause a popup |
| confirm | reversible, but other people see it | popup **Go live**, template **Reset**, webhook **New secret** |
| + the number | spends quota or money | every job **Run now**, SportAPI **Run now** and **Backfill**, image sync, **Refresh league list**, switch a league **on**, **Queue missing matches** |
| + a reason | a reader sees it, or it touches their account | **Sign out everywhere** |
| typed phrase | irreversible destruction, bulk sends | **Send everyone now** (`SEND`), **Run now** on a season backfill (`RUN`) |

`Cost` prints what the press costs next to what is left, which is what the six Run-now buttons were
missing: they shared one sentence for a 1-call league-list refresh and a season backfill of a
thousand calls or more. New server numbers back it — `/admin/jobs` returns `costs` per job and
today's remaining budget, `/admin/leagues` returns the per-league daily call cost, and
`/admin/integrations` returns the confirmed-list count so "Send everyone now" can say how many
people that is.

Also:

- **Settings** saved on the first click of any control, up to and including `billing.mode`. The
  owner-only prefixes (`security.`, `billing.`, `auth.`, `tracking.`, `email.provider`) are already
  the product's own statement of which settings are consequential, so those now ask before saving,
  and **Reset to default** asks on every row. The other ~230 keep saving as they did: 252 rows of
  equal friction is 252 rows of nobody reading.
- **The three engine switches** (`calibration`, `absence_model`, `match_context`) changed every
  public percentage at the next run from the lightest control in the system. They now say so.
- **`btn--danger` was used exactly once in the whole admin** (Cache → Delete all). Every other
  destructive trigger was `btn--ghost`, pixel-identical to "History" and "Preview". It is now on
  every one of them, and `adminhome.css` no longer overrides the class's text colour with a literal
  `#fff` — which was the one hardcoded colour left on it, and the wrong pair on a light palette.
- `POST /admin/users/{id}/logout` now accepts and audits a reason, because the screen asks for one.

## 4. The club had no evidence block

`v4/TEAMS.md` findings 3 and 5, the biggest remaining asymmetry between the two entity types.

- **`QuickView` takes a club.** It took `playerId` only, so the club sheet fell back to a fixed
  ten-game strip for whichever line had been tapped, and the club page had no evidence block at
  all — while "what about 4+, and only away?" is exactly the question a club line raises. It now
  takes `teamId`, offers the stats `team_match_stats` actually holds, and drops "Started only",
  which is a player idea. `stat` is a query parameter for a club and not for a player, because
  `/players/{id}/history` returns every stat per game and `/teams/{id}/history` returns one; that is
  commented at the call so nobody optimises it away.
- **`venue` on `/teams/{id}/history`.** Without it the Venue control was a lie.
- **The club sheet** uses the same QuickView and links to the club page, the way the player sheet
  does. A **match** line keeps the plain strip: it is stored with scope `team` against the home
  side, but it is about the fixture, so there is no entity to interrogate. One helper,
  `isMatchLine`, makes that distinction once.
- **The blank minutes row.** A club has no minutes, so `.v2-cr-m` was ten columns of nothing — a
  blank band across the card — and `.pgs-min` the same in the strip. Both now carry **H** or **A**
  from `run[].home` / `games[].home`, which was stored on every row and drawn nowhere. A club's
  shot and corner counts swing with venue more than with anything else we hold. Away is set in a
  lighter weight so a column of H with one A reads without a legend — weight only, never opacity or
  colour, because the row is 0.5rem and thinning the ink would drop it under the contrast floor
  this palette is measured against. The screen-reader line says "at home against" / "away against"
  in full, so nothing depends on seeing the difference at all.
- **`expected` beside `expected_usual`.** The card said *"their average 4.8"* and it is not an
  average of anything they have done (`METRICS.md` §4.2) — it is the count their usual game implies
  for this line, so the label invited the reader to check it against the strip's own numbers and
  find the card wrong about itself. `f.expected`, the count expected against *this* opponent, was
  stored on every forecast and drawn nowhere. It now reads **6.1 tonight · usually 4.8**: the
  headline restated in counts, counted the same way the strip underneath counts.

## 5. The match page had lost its "what they are playing for" chips

Found while clearing the build's lint warnings, not from an audit. A `Situation` component rendered
the league-situation chips ("Relegation fight", "In the race at the top") and a referee line; a
redesign stopped rendering it, the referee line was taken into `MatchNotes`, and the chips simply
stopped appearing while the engine kept computing them. They are back, beside "Worth knowing",
which is the same kind of claim. `CI=true npm run build` now compiles with no warnings.

---

## Not done, and why

**Merge Insights and Finder.** `GLOBAL.md` finding 2 and the core-screens audit both say merge, and
the ranking argument is sound: two of five phone tabs spend themselves on "show me lines", and the
freed slot should go to `/track-record`, which is the product's own evidence and today has no
primary entry point at all.

It is not a design change I should make on my own. It deletes a route, moves entitlements that are
attached to Finder's query powers, and changes the tab bar every reader has learned. That is an
owner's call, and it wants its own round rather than a line in a clean-up pass.

**Owner-only, unchanged.** `engine.likely_starter_p` is 0.99, against the stated intent of about
0.85, and `scripts/measure/minutes_within_player.py` has not been run against production. Both
need the real database, not the demo.

---

## What was checked, and how

The 41 self-tests and `CI=true npm run build` (which now compiles with no warnings) pass. Twelve
checks are new: two in `selftest_accounts.py` for the enumeration oracle, three in
`selftest_server.py` for the reset-link check (live reads live, reading does not spend it, a spent
link reads dead), three in `selftest_admin.py` for the sign-out reason (with a body, without one,
and the reason reaching the audit row), and four in `selftest_queries.py` for the venue filter.
Beyond
that, every guard was driven in a browser against the demo server, signed in as the owner through
the real 2FA flow, and the dialog's text read back:

| Guard | Dialog seen |
|---|---|
| Jobs → each **Run now** | "About 1 provider call. 1,632 of 2,000 left in today's budget." — per job |
| Jobs → **Run now** on Engine | "makes no provider calls at all; it recomputes from what we already hold" |
| Jobs → **Run now** on Backfill with nothing ticked | "Nothing is waiting for this job right now" |
| Leagues → **Refresh league list** | queues the reference sync, with the call |
| SportAPI → **Run now** | the tick, with the budget |
| Engine → **Sync images** / **Sync and re-read squads** | the second names the per-club squad re-read |
| Studio → **Reset section** / a **preset** | names the section / the preset and says a draft has no history |
| Templates → **Reset** | names the template |
| Plans → **Sync to Stripe** | names the plan and that a Stripe price cannot be edited |
| Popups → **Go live** | names the popup and the format every matching visitor will see |
| Users → **Sign out everywhere** / **Send password-reset e-mail** | the first requires a reason |
| Integrations → **Send everyone now** | states the count and requires `SEND` typed |
| Settings → an owner-only key | names the key, the old value and the new one |

The club surfaces were measured as well as looked at: the club page and the club sheet both report
`document.scrollWidth` 390 at a 390px viewport. They did not at first — a club's ladder is sixteen
rungs where a player's is three to five, and sixteen chips in the Line control pushed the Quick
view's grid column to **857px inside a 390px phone**, dragging the strip, the head and the filters
out with it. Two fixes, both right on their own merits: the control offers a window of eight rungs
around the line the reader arrived on, and `.qv` is `grid-template-columns: minmax(0, 1fr)` so a
grid item's automatic minimum size can never widen the page again.
