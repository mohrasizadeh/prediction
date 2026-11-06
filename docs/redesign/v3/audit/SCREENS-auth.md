# SCREENS-auth — sign-in journeys (P-28…P-37) and account (A-01…A-06)

Audited 2026-11-06 against the running build. Screen IDs from `docs/57_screen_inventory.md`.

**Verdict in one line.** Most of these screens are fine-but-dull — competent forms in a layout the
rest of the app outgrew. Five are genuinely broken: **P-34** is an inescapable trap, **P-30** ends
the sign-up journey by telling the reader "You're in" and then making them sign in again, **P-33**
presents a fully working form on a dead link, **A-06**'s delete confirmation is covered by the
cookie banner so the question is invisible while the red button is not, and **the product has no
sign-out control for readers anywhere**. The rest of this document spends its words on those.

Two notes on evidence. The `before/` set is complete and real (the account sections are rendered
as the signed-in owner). It does **not** contain P-31, P-34 or P-37 — the harness has no entry for
them — and P-30, P-33 and P-36 are captured with **no token in the URL**, which is the least
interesting of their three states. Everything in this audit marked *(driven)* was reached by
driving the flows against a private instance of `backend/tests/demo_server.py`; those renders live
in the session scratchpad, not the repository. Section 12 lists every state I could **not** reach.

---

## The ten changes, ranked

| # | Change | Screens | Why it is this high |
|---|---|---|---|
| 1 | **Give readers a way to sign out.** | all signed-in | There is no sign-out control anywhere on the reader-facing site. `signOut` is imported in exactly one place (`Account.jsx:221`) and used only to finish an account deletion. The admin shell has one (`AdminApp.jsx:132,191`); the reader does not — not in the header, the footer, the bottom tabs, or A-03. A-03 even offers "Sign out" on every row **except** the current device, which gets a "This device" chip instead. Reader sessions last 14 days (`auth.session_days`). This one omission also causes #3. |
| 2 | **Lift modal dialogs above the cookie banner.** | A-06, every `Confirm` | Measured on a 390px phone: `.overlay` is `z-index: 60`, `.cookie` is `z-index: 70`. The delete dialog occupies y 691–844; the banner occupies y 619–768. It covers the `<h2>` "Delete your account?" (711–731) and the body "This cannot be undone." (745–766) exactly, leaving only `.dialog-actions` (780–824) visible. The reader sees a grey **Cancel** and a red **Delete for good** and no question. |
| 3 | **Make P-34 escapable and explain why it is happening.** | P-34, P-35 | `Gates` (`App.js:47-48`) bounces every path to `/change-password`. Driven: `/forgot-password`, `/account/security` and even `/sign-in` all redirect back. With no sign-out (#1), a person who cannot reproduce the temporary password has no exit but clearing cookies, and nothing on the page says so. |
| 4 | **Sign the reader in at the end of verification.** | P-30 | "You're in" is false at the moment it is shown. The token is proof of e-mail control and `verify_email()` already returns the user row; the page could issue a session. Instead the reader types the password a second time, 60 seconds after a SPA state change that often prevents the browser's save-password prompt from firing. |
| 5 | **Check the reset token on arrival; borrow P-30's recovery pattern.** | P-33 | With no token, an expired token or a used token, P-33 renders a complete, enabled, confident form. The reader invents a password, types it twice, and *then* learns the link is dead — on a screen with no way to ask for a new one. P-30 already does this correctly; P-33 is the same component family and does not. |
| 6 | **Close the lockout enumeration oracle.** | P-28 | `_lock_check` runs only for a found user (`accounts.py:246-248`). Five wrong passwords against a **real** address return `LOCKED` / 429; five against a **fake** one keep returning `BAD_CREDENTIALS` / 401. The generic "Wrong e-mail or password." is undone by the next request. The per-e-mail rate limit does not cover it: lockout fires at 5, `RATE_LIMITED` at 10. |
| 7 | **Clear the site furniture off these seventeen screens.** | all | Every one of them carries the newsletter sign-up block, the five-item bottom tab bar, the desktop rail, the footer and the disclaimer. Consequences: two e-mail inputs and two blue buttons on the sign-up page; a subscribe form directly under the unsubscribe button on P-36; a mailing-list pitch on P-34 to someone whose account is frozen; tab bars on P-34/P-35 whose every destination silently bounces back. `NO_BANNER` (`Layout.jsx:98`) already excludes the auth routes from the cookie banner — it does not exclude `/account/*`, `/unsubscribe`, `/newsletter/confirm` or `/welcome`, and the banner lands over the form in every one. |
| 8 | **Fix five pieces of copy that are not true.** | A-06, A-02, P-31, P-35 | Listed with the exact wording in §11. Security copy that overstates is the one thing this product cannot afford. |
| 9 | **`noValidate` on every auth form; move rules into the field; use field-level errors.** | P-29, P-33, P-34, A-02 | `SignIn` sets `noValidate`; `SignUp` and `NewPasswordForm` do not, so a 5-character password raises a raw Chromium bubble — grey-and-orange OS chrome in the middle of a dark themed form — covering the hint that says the rule. `Field` supports an `error` prop; **no auth screen passes it**, so on the three-field P-34 nothing says which field is wrong. |
| 10 | **Run the v2 pass over these screens.** | all | `frontend/src/styles/v2.css` — the current design layer — touches **zero** auth classes and exactly one account class (`.plan-hero`, incidentally, in the shadow-stripping rule at line 182). Specifics in §13. |

---

## 1. Shared faults (they recur on every screen below)

Listed once here; per-screen sections name only what is particular to that screen.

- **S1 No document title.** `Auth.jsx`, `Account.jsx` and `EmailLinks.jsx` are the only page files
  with no `useTitle` call. Every other page sets one, and `useTitle` never resets, so arriving at
  sign-in from Insights leaves the browser tab reading "Insights". Seventeen screens, zero titles.
- **S2 Full site chrome.** See ranked change #7.
- **S3 The cookie banner.** See #7. On A-01…A-06 it lands over the form; on A-06 over the dialog.
- **S4 Three button scales in one journey.** `btn--lg btn--block` (P-28…P-35, full width — on
  desktop A-02 that is an 840px-wide "Change password" button), `btn--secondary self-start`
  (A-01, A-02's e-mail form, 520px), and a small left-aligned pill (P-36, P-37). On desktop A-02
  three different widths appear in one column.
- **S5 Form-level errors only.** No `Field` in this set receives `error`. Every message is a banner.
- **S6 Hints are not associated.** `<small className="field-hint">` is a sibling of `.field`, not a
  child, so it is outside the `aria-describedby` that `Field` builds. The password rule is invisible
  to a screen reader on P-29, P-33, P-34 and A-02.
- **S7 No "how long".** `LOCKED`, `RATE_LIMITED` and `CHALLENGE_EXPIRED` never state a duration,
  although the server knows all three (15 minutes, 15 minutes, 5 minutes).

---

## 2. P-28 `/sign-in` — Sign in

**Purpose.** Let a returning reader get back into their account, with a second step when the
account has one.

### Inventory

| Item | Verdict | Reason |
|---|---|---|
| `.auth-ico` 48px brand-tinted icon chip | **change** | A rounded-square tinted glyph is the single commonest generated-page tell, and v2.css §6 names exactly this pattern as a default rather than a decision. Replace with the brand mark or nothing. |
| H1 "Sign in" | keep | |
| Lead "Welcome back. Follow teams, save forecasts and get more Finder searches." | keep | Three concrete reasons. Better than the lead on P-29, which is the page that needs one. |
| E-mail field | **change** | No `autoFocus`. The 2FA step has it; the first step does not. |
| `PasswordField` + eye toggle | keep | 46px target, correct `aria-label` swap. |
| "Forgot password?" right-aligned link | **move** | It sits *above* the error. When BAD_CREDENTIALS fires, the one useful action is already behind the reader's eye. |
| `FormError` banner | keep, re-word | See below. |
| Conditional `ResendButton` on `EMAIL_NOT_VERIFIED` | keep | The best conditional recovery in the set. |
| "New here? Create an account" | keep | |
| `.auth-aside` (desktop) | **change** | `aria-hidden="true"` hides the only persuasion on the page from screen readers. The pitch-line drawing and the lime kicker are the most on-brand thing in these seventeen screens; the two radial gradients behind them are the decoration v2.css §6 rejects, and are nearly invisible in dark anyway. Keep the drawing and the words, drop the gradients, drop `aria-hidden`. |
| Header "Sign in" button | **delete here** | A sign-in button on the sign-in page. On desktop the header also carries "Sign up free", so the screen shows three sign-in/sign-up affordances. |
| Newsletter block + bottom tabs + footer | **delete here** | S2. |

### Faults in the render

1. *(driven)* **The lockout leaks account existence.** Ranked #6.
2. "Wrong e-mail or password." says what went wrong and not how to fix it. No "check caps lock",
   no reset link inside the error.
3. "Too many attempts. Try again later." and "Too many requests. Try again shortly." are two
   different sentences for the same reader experience, neither giving a duration (S7).
4. `phone-dark`: the page is one continuous scroll holding two e-mail inputs and two full-width
   blue buttons — "Sign in" and "Send me the e-mail". A reader can type their address into the
   wrong one and get a mailing-list confirmation instead of a session.
5. S1, S4, S5.

### The 2FA step *(driven)*

Same `AuthCard`, title "Enter your code". Auto-submits on six digits, accepts a recovery code in
the same box — both good.

- No indication of **which account** is being challenged. The e-mail is not shown.
- Nothing says the challenge expires in five minutes; when it does, the message is "Sign in again."
  which explains nothing. After five wrong codes: "Too many wrong codes. Sign in again."
- "That code is not right." never mentions **clock drift**, the commonest real cause of a correct
  TOTP being rejected.
- Nothing says what to do having lost both the phone and the recovery codes. Staff *can* reset it
  (`routes_admin.py:258`), so there is a true sentence available: say it.
- "Back to sign in" is the only other control and it simply loops.

### Proposals, ranked

1. Make `LOCKED` indistinguishable from `BAD_CREDENTIALS` on the wire (same status, same body), or
   apply the lockout to unknown addresses too.
2. Move the reset route into the error: "Wrong e-mail or password. <u>Set a new password</u>".
3. State durations: "Too many attempts. Try again in 15 minutes." / "This code expired. Sign in
   again — the step only stays open for five minutes."
4. On the 2FA step, show the address being signed in to, and add one line: "Lost your phone and
   your codes? <u>Contact us</u> and we can turn the second step off."
5. Add `autoFocus` to the e-mail field; drop the header sign-in button on this route.

---

## 3. P-29 `/sign-up` — Create an account

**Purpose.** Open an account with an e-mail and a password.

### Inventory

| Item | Verdict | Reason |
|---|---|---|
| Lead "E-mail and password. That is all we need." | **change** | It describes the cost and never the benefit. P-28, the page for people already convinced, lists three reasons to be here; P-29, the page that has to sell, lists none. |
| E-mail / Password / Name (optional) | keep | Three fields is right. |
| `minLength={10}` on the password input | **change** | Causes the native bubble (below). Validate on submit instead. |
| Hint "At least 10 characters. A short phrase works well." | **move** | Into the field (S6), and say the real rule. |
| Terms / privacy / "For adults 18+" | keep | Accurate and in the right place. |
| "Already have one? Sign in" | keep | |
| `sent` state: "Check your inbox" + resend + "Go to sign in" | keep, fix | See fault 3. |
| Newsletter block below the fold | **delete here** | Second e-mail input on the page; S2. |

### Faults in the render

1. **The browser's own validation bubble.** `SignUp` has no `noValidate`, so a short password
   produces Chromium's grey-and-orange tooltip — "Please lengthen this text to 10 characters or
   more (you are currently using 5 characters)" — floating over the dark form and covering the
   hint that states the rule. `SignIn` sets `noValidate` nine lines earlier. *(driven)*
2. **A dead end for an address that already has an account.** `register()` returns `(None, None)`
   and nothing is sent (`accounts.py:181-183`), which is the right privacy choice, but the reader
   is then shown "Check your inbox… we sent a link to you@example.com", and their one recovery —
   "Send the link again" — calls `/auth/resend-verification`, which also returns `(None, None)`
   for a verified account. The button starts a 60-second countdown and nothing ever arrives.
   Forever. *(driven, `P-29-existing`)*
3. The password rule is thin. `check_password_policy` enforces ten characters, four distinct
   characters, and a thirteen-entry blocklist. `password12` passes. The copy does not overclaim,
   so this is not a security-copy fault — but "That password is too easy to guess." will almost
   never fire, which makes it decorative.
4. S1, S2, S3, S5, S6.

### Proposals, ranked

1. Add `noValidate`; validate on submit through `FormError` and a field-level error.
2. Replace the lead with what the reader gets. P-28's own lead is a better starting point than
   P-29's.
3. On the `sent` screen, add a line that works for both cases without leaking either: "If you
   already have an account with this address, no link was sent — <u>sign in</u> instead."
4. Live password feedback against the real rule (length and distinct characters), so "too easy to
   guess" stops being a surprise at submit time.

---

## 4. P-30 `/verify-email` — Confirm e-mail

**Purpose.** Turn the link in the sign-up e-mail into a confirmed address.

### Inventory

| Item | Verdict | Reason |
|---|---|---|
| Explicit "Confirm" button rather than a GET that acts | **keep** | Deliberate and correct — mail scanners open links. The header comment in `EmailLinks.jsx` explains it; this page does not explain it to the reader. |
| Lead "One click and your account is ready." | **change** | Still displayed above an error saying the link is dead. |
| Error state: message + e-mail field + "Send the link again" | **keep — the model for the set** | It names the problem and offers the fix in place. P-31, P-33 and P-34 should copy this. |
| `ok` state: "You're in" + "Sign in" | **change** | Ranked #4. |
| Disabled Confirm when `?token` is missing | keep | Prevents the P-33 failure mode. |

### Faults in the render

1. **"You're in" is false.** *(driven)* Ranked #4. The ok state is a title, a button and ~400px of
   dead space before the newsletter block. It shows no name, no address, and no sense of what the
   account now is.
2. The lead contradicts the error when the error is showing.
3. The disabled resend button is a flat grey slab indistinguishable from the enabled secondary
   button used elsewhere.
4. S1, S2, S5.

### Proposals, ranked

1. Issue a session on successful verification and land the reader on `/welcome`. Nothing about the
   token's security properties prevents it.
2. If that is refused, at minimum pre-fill the address on the sign-in page and change the title
   from "You're in" to "E-mail confirmed".
3. Swap the lead for the error state, and add one line on the idle state saying why there is a
   button at all: "We ask you to press this rather than act on the link itself, because e-mail
   scanners open links automatically."

---

## 5. P-31 `/confirm-email` — Confirm a new address

**Purpose.** Finish the e-mail change started in A-02.

### Inventory

| Item | Verdict | Reason |
|---|---|---|
| Shared `TokenAction` with P-30 | keep | |
| Error state | **change** | Identical message to P-30 — "This link is not valid any more. Ask for a new one." — but **with no resend**, because the resend branch is keyed to `path === "/auth/verify-email"` (`Auth.jsx:146`). The reader is told to ask for a new one and given nothing to ask with. |
| `ok` state: "E-mail changed / Your new address is now the one you sign in with." + "Back to your account" | **change** | See fault 1. |

### Faults in the render

1. **The success state hides that every session was destroyed.** *(driven)* `confirm_email_change`
   calls `revoke_all(db, u["id"])` (`accounts.py:409`) with no `keep_token`. "Back to your account"
   goes to the sign-in page. P-33's success state says "Every device was signed out." — the product
   already owns the sentence and omits it exactly where it also applies.
2. The new address is never shown, so the reader cannot confirm the change landed on the right one.
3. S1, S2, S5.

### Proposals, ranked

1. Add the missing sentence and name the address: "**name@example.com** is now the address you
   sign in with. Every device was signed out, including this one."
2. Change the button to "Sign in" — which is where it goes.
3. Give the error state a route back: a link to `/account/security`, with a line saying the change
   has to be started again from there.

---

## 6. P-32 `/forgot-password` — Ask for a reset link

**Purpose.** Send a one-use reset link.

The best-behaved screen in the set. Keep almost everything.

### Inventory

| Item | Verdict | Reason |
|---|---|---|
| Single e-mail field, one button | keep | |
| `sent` state: "If that address can be used, we sent a link. It works once, for 60 minutes." | **keep** | Non-leaking *and* it states the lifetime — the only screen here that does. Make it the house style. |
| "Back to sign in" | keep | |

### Faults

1. The sent state has no resend and no countdown, so a reader whose mail is slow has only the
   browser back button, and repeating the request burns against `forgot:{hash}` (3/hour) with no
   warning. *(driven)*
2. S1, S2, S3.

### Proposals

1. Add a 60-second resend on the `sent` state, like P-29 and P-30 have.
2. Say where it went: "…we sent a link to **you@example.com**." The address was just typed, so
   echoing it leaks nothing.

---

## 7. P-33 `/reset-password` — Set a new password

**Purpose.** Replace a forgotten password from a one-use e-mail link.

### Inventory

| Item | Verdict | Reason |
|---|---|---|
| No token pre-flight | **change** | Ranked #5. |
| Lead "This link works once." | **change** | True but incomplete — it does not say *how long*, which P-32 does say in the e-mail that led here. |
| `NewPasswordForm` (new + repeat) | keep | Not asking for the current password is right here. |
| Client-side mismatch check | keep | Fires before the network, which is right; but see fault 3. |
| `ok`: "Password set / Every device was signed out. Sign in with your new password." | **keep** | Accurate: `confirm_reset` calls `revoke_all` with no `keep_token`. The model P-31 should follow. |
| Enabled Save button on a dead link | **change** | |

### Faults in the render

1. *(driven)* **A working form on a dead link.** With `?token` missing, invalid, expired or already
   used, the page renders identically to the live one and the Save button is enabled. The reader
   invents a password, types it twice, presses Save, and gets "This link is not valid any more.
   Ask for a new one." The Save button stays enabled and still says "Save password", inviting a
   retry that cannot work. There is **no link to `/forgot-password` on the screen**.
2. The two passwords they typed stay in the fields after the failure.
3. "The two passwords are not the same." is a form-level banner, not attached to the second field
   (S5).
4. The weak-password error (`PASSWORD_TOO_COMMON`) arrives from the server only after a round trip,
   although the token is *not* burned by it — `confirm_reset` peeks before it consumes
   (`accounts.py:363-370`). Good behaviour that nothing tells the reader about.
5. S1, S2, S3, S6.

### Proposals, ranked

1. `GET`-peek the token on mount. If it is dead, render P-30's error layout: the message, an e-mail
   field and "Send me a new link" — not a form.
2. If a pre-flight is unacceptable, at minimum turn the failure state into P-30's: replace the form
   with the error and a "Send me a new link" button.
3. Put the lifetime in the lead: "This link works once, within 60 minutes of being sent."
4. Field-level error on the repeat field for the mismatch.

---

## 8. P-34 `/change-password` — The forced first change

**Purpose.** Make someone replace a password an owner set for them, before they can use anything.

This is the worst screen in the set. Answer to question 3 is "no" on both counts.

### Inventory

| Item | Verdict | Reason |
|---|---|---|
| Title "Choose your own password" | keep | Warm, and the only warm thing here. |
| Lead "You signed in with a first password. Replace it now; other devices will be signed out." | **change** | "a first password" is internal jargon. It does not say **who** set it, **when**, or **why** it must go. And the first fact offered is a consequence that sounds like a threat. |
| "Current password" field | **change** | It asks the reader to re-type, from memory, the temporary password they entered ten seconds earlier on the sign-in page — a password that arrived out of band and that no password manager has saved. |
| New / repeat fields + "At least 10 characters." | keep | |
| "Save and continue" | keep | |
| Which account this is | **add** | The e-mail is never shown. An owner who set up two accounts cannot tell which one they are fixing. |
| A way out | **add** | Ranked #3. |
| Header avatar, search, bell; bottom tabs; desktop rail | **delete here** | Every one of them bounces back. On desktop that is six rail items, a search box and a bell, all inert. |
| Newsletter sign-up block | **delete here** | A mailing-list pitch to someone whose account is frozen. |

### Faults in the render

1. *(driven)* **It is a trap.** From this state `/forgot-password` → `/change-password`,
   `/account/security` → `/change-password`, `/sign-in` → `/change-password`. There is no sign-out
   (#1). The only exit is clearing cookies, and nothing says so.
2. *(driven)* "Your current password is not right." blames the reader, and offers no recovery —
   not "ask whoever set it up", not "sign out and start again", not a reset route.
3. The lead never explains the situation. A support agent handed a temporary password over the
   phone has to explain this screen themselves.
4. S1, S2, S3, S5 — and S5 bites hardest here, because this is the only three-password-field form
   in the product and the banner never says which of the three is wrong.

### Proposals, ranked

1. **Add "Sign out" to this screen** (and to P-35, and to the account area — #1). One link turns a
   trap into a dead end you can walk out of.
2. Rewrite the lead to explain, name the account, and put the reason before the consequence:
   > **Choose your own password**
   > Someone on the team set a temporary password for **name@example.com** so you could get in.
   > It only works once, so pick your own now. Your other devices will be signed out.
3. Drop the "Current password" field. The session is already proof — `must_change_password` is set,
   the reader is authenticated, and `change_password` re-checks the hash only because the generic
   endpoint is shared. Keep it if the shared endpoint must stay, but then pre-fill it from the
   sign-in step or say where the password came from.
4. Add recovery to the wrong-password error: "That is not the temporary password. Ask whoever set
   up your account for a new one, or <u>sign out</u>."
5. Field-level errors; strip the furniture.

---

## 9. P-35 `/enroll-2fa` — Set up two-factor

**Purpose.** Enrol an authenticator, and for staff, pass the gate that blocks everything else.

### Inventory

| Item | Verdict | Reason |
|---|---|---|
| `<ol className="steps">` holding **one** `<li>` | **change** | It renders as "1." with no 2 or 3. The real step 2 ("Then enter the 6-digit code it shows") is a field label outside the list; step 3 (recovery codes) is a separate screen with no warning. A numbered list of one is worse than no numbering. |
| QR block | **change** | `.qr { background: #fff }` in `base.css:209` and `bgColor="#FFFFFF" fgColor="#0A0E17"` passed to `QRCodeSVG` in `Auth.jsx:271`. Two literal colours, one of them in a component. In dark mode it is a hard white rectangle in the middle of the page. Use `var(--qr-bg)` / `var(--qr-fg)` tokens that resolve to a light pair in both themes. |
| "Can't scan? Type this key" `<details>` | keep | |
| Six-digit field, auto-strips non-digits | keep | |
| "Turn on two-factor sign-in" (disabled until 6 digits) | keep | |
| Recovery-codes step | keep, fix | See below. |
| "I saved them" checkbox gating Continue | **keep** | Good friction in the right place. |
| A "not now" / cancel for readers | **add** | A reader who reaches this from A-02 and changes their mind has no way back except the browser. |
| Title through the whole flow | **change** | It stays "Set up two-factor sign-in / Add a second step to your sign-in." on the recovery-codes screen, which is a different task. No step indicator. |

### Faults in the render

1. *(driven)* The recovery-code instruction — "Each code works once if you lose your phone. We show
   them only now. Keep them somewhere safe and offline." — is accurate, well-written, and the most
   important sentence in the flow. It has **no heading**, and sits under a title describing the
   previous step.
2. Nothing says what happens if the phone **and** the codes are lost. The copy implies the codes
   are the safety net and stops there. Staff can reset 2FA (`routes_admin.py:258`), so there is a
   true thing to say.
3. For staff, the lead changes to "Staff accounts must use a second step. It takes a minute." —
   accurate, but the screen is a gate with the same no-exit problem as P-34 (#1, #3).
4. "Download as a text file" is a flat grey secondary button that reads as disabled.
5. S1, S2, S3.

### Proposals, ranked

1. Give the flow two titled steps and a "Step 1 of 2" marker; give the codes screen its own
   heading ("Save your recovery codes").
2. Tokenise the QR colours; remove both literals.
3. Add one true sentence: "If you lose your phone **and** these codes, contact us — we can turn the
   second step off after checking who you are."
4. Add "Not now" for readers; add "Sign out" for staff.

---

## 10. P-36 `/unsubscribe` and P-37 `/newsletter/confirm`

**Purpose.** P-36: leave the mailing list from a link in an e-mail. P-37: double opt-in.

These two share `LinkPage` and are the only screens in this set wrapped in a real `.card`. That is
the inconsistency, not a virtue: P-28…P-35 have no container at all.

### Inventory

| Item | Verdict | Reason |
|---|---|---|
| GET shows, POST acts | **keep** | Correct and well-commented. |
| Masked address (`u***@example.com`) | keep | Does not leak the address from a forwarded link. Costs the reader certainty about *which* of their addresses this is; the right trade. |
| P-36 ask: "Stop non-essential e-mails to …? Account and payment e-mails still arrive." | **keep** | Accurate, and it sets the right expectation. |
| P-36 done: "Done. You won't get these e-mails any more." | keep | |
| P-37 title "Confirm your sign-up" | **change** | Ambiguous — a reader may read "sign-up" as their account. Say "Confirm the weekly e-mail". |
| Small left-aligned pill buttons | **change** | S4 — a third button scale. |
| Cookie banner | **delete here** | `NO_BANNER` does not cover these routes. A consent banner in front of an unsubscribe link is the worst place in the product for one. *(driven)* |
| The newsletter sign-up block below | **delete here** | On P-36 it sits directly under the unsubscribe button, asking the reader to join the list they are leaving. |
| "Go to the home page" on done | keep | |

### Faults

1. The cookie banner and the subscribe form, as above. Both visible in the same render.
2. The P-36 done state offers no "I changed my mind" — except the subscribe form underneath it,
   which is an accident rather than a design.
3. No-token state is handled by synthesising an error object inline rather than rendering anything
   explanatory ("This link is not valid." / "This link has expired or was already used."). Fine,
   but the reader is given no route: there is no "manage your e-mails in your account" link.
4. S1, S2.

### Proposals, ranked

1. Add `/unsubscribe` and `/newsletter/confirm` to `NO_BANNER`, and suppress the footer newsletter
   block on both.
2. Make the unsubscribe page a single-purpose page: no tabs, no rail, no footer links.
3. On the done state, add "Changed your mind? <u>Join again</u>" as a deliberate control.
4. Retitle P-37; match the button scale to the rest of the journey.

---

## 11. A-01…A-06 `/account/*`

**Purposes.** A-01 name, time zone, theme. A-02 password, e-mail, two-factor. A-03 signed-in
sessions. A-04 which e-mails arrive. A-05 subscription and invoices. A-06 export and deletion.

### Shared inventory

| Item | Verdict | Reason |
|---|---|---|
| `.acc-nav` horizontal scroller on phone | **change** | *(driven)* At 390px the row shows **Profile, Security, Devices** and half the Notifications bell. Plan and Privacy are off-screen. `scrollbar-width: none` removes the only cue, and nothing scrolls the active link into view — so standing on Privacy, the row still shows Profile first and nothing marks where you are. Three of six sections are effectively undiscoverable on a phone. |
| `.acc-section` card | **change** | The last card in the product still carrying `box-shadow: var(--card-shadow)`; v2.css strips it from `.fcard, .sq-card, .ln-card, .a-card, .nl, .nl2, .plan-hero, .hero, .pcard--hi` and misses this one. |
| Page head "Account" | keep | |
| A sign-out control | **add** | #1. |
| Newsletter block, bottom tabs, cookie banner | **delete here** | S2, S3. |

### A-01 Profile

- "Signed in as you@example.com" is grey, small, wrapped over two lines, and **not editable here** —
  the e-mail change lives in A-02. A reader looking for "change my e-mail" starts at Profile.
  Add a link: "Change it under Security".
- "Use this device's time zone" is `btn--ghost btn--sm` and renders as a centred bold text line with
  no button affordance at all.
- Theme segmented control is good; it is the only account control that matches the rest of the app.
- Save is a small left-aligned `btn--primary` while every auth screen uses a full-width `btn--lg`.

### A-02 Security

- On desktop, `NewPasswordForm` has no `form--wide`, so its fields and its "Change password" button
  run the full 840px column, while the e-mail form beside it is capped at 520px. Three button
  widths and two field widths on one screen (S4).
- **The e-mail-change toast says something that may not be true.** `EmailChange` fires
  `toast("We sent a link to the new address")` unconditionally (`Account.jsx:70`). The server
  returns `(u, None)` and sends nothing when the address already belongs to someone
  (`accounts.py:396-397`), and its own message is the careful "If that address can be used, we sent
  a link to it." The client throws that away and asserts the send. Use the server's sentence.
- No sign-in history, although `auth_log` is kept for 90 days and the admin has a screen for it. A
  reader cannot see "last signed in from…", which is the one thing a security tab is for.
- "Changing it signs out your other devices." — accurate (`revoke_all` with `keep_token`).
- "On. Staff accounts cannot turn it off." — accurate.
- The disable form asks for password *and* current code — correct, and the error "Password or code
  is not right." is correctly ambiguous about which.

### A-03 Devices

- **No way to end the current session** — the row you are sitting on gets a "This device" chip
  instead of a button (`Account.jsx:135`). Combined with #1, a reader on a shared computer cannot
  get out.
- "Sign out all other devices" is shown even when there are no other devices.
- The raw IP (`127.0.0.1` in the render) is honest but useless to most readers; label it rather
  than hide it: "Last used from 127.0.0.1".
- Nothing states how long a session lasts (14 days), so a device vanishing from the list has no
  explanation.
- There is no "this wasn't me" route — no link to change the password from here.

### A-04 Notifications

The best-made section. Two faults.

- The master switch ("Alert e-mails") and the two switches it governs ("Lineup alerts", "Goal and
  red card alerts") sit at the same indent with no grouping, and turning the master off neither
  disables nor dims the children — so the screen implies they still fire.
- **The weekly e-mail is not here.** The newsletter is a separate list, reachable only from the
  footer form or an unsubscribe link. A-04's stated job is "Which alerts and e-mails to receive",
  and it omits the one e-mail the product pushes hardest. Add a row backed by
  `/newsletter/subscribe` and the unsubscribe token.
- "Receipts and security e-mails cannot be turned off." is correct and well placed.

### A-05 Plan and billing

- "Paid plans are not open yet. Every signed-in person gets the full plan for now." — honest, clear,
  keep exactly.
- **"Manage billing" is disabled with its only explanation in a `title` attribute** — which never
  appears on a touch device. On a phone the sole button on the screen is dead and unexplained.
  Move "Available once you have a paid plan" into visible text.
- `plan-hero` is the one account surface v2.css touches, so it is shadowless while the sections
  around it are shadowed — a visible seam.
- The `past_due`, `trialing`, `cancel_at_period_end`, populated-invoice and `Confirming…` states
  could not be reached (see §12).

### A-06 Privacy — export and deletion

| Item | Verdict | Reason |
|---|---|---|
| Section title "Download my data" | keep | |
| Lead "A JSON file with everything we hold about you." | **change** | Not true. `export_account` returns profile, the six `USER_DATA` collections, subscriptions, payments, an e-mail log and 200 sign-in rows. It omits `events` (analytics rows keyed to the user) and `admin_notes` (support notes *about* the reader, which deletion removes but export does not reveal). |
| Secondary grey "Download my data" button | **change** | Reads as disabled; this is a primary action for the section. |
| No feedback on success | **add** | The file downloads silently; failure produces a toast. Success produces nothing. |
| Section title "Delete my account" | keep | |
| Delete lead | **change** | See below. |
| Password field then `Confirm` dialog | keep the shape | |
| `Confirm` with `typed` unused | **change** | The component supports "type DELETE to confirm" and the single irreversible action in the product does not use it. |
| Dialog body "This cannot be undone." | **change** | True, and invisible — see ranked #2. |

**Faults.**

1. *(driven, measured)* **The confirmation question is covered by the cookie banner.** Ranked #2.
   The reader confirms permanent deletion from a strip showing only "Cancel" and "Delete for good".
2. **The delete copy is honest about the right things and silent about two.** It says: "Removes
   your account, follows, saved forecasts, notes, alerts, sessions and links. Payment records stay
   for tax law, unlinked from your name. Any subscription is cancelled first." Checked against
   `delete_account` (`accounts.py:539-564`): all of that is true. What it does not say —
   - the **sign-in log is not deleted**. `db.auth_log` rows survive untouched, carrying `user_id`,
     the e-mail and the IP of every sign-in, for the 90 days of
     `security.auth_log_retention_days`. The copy's "sessions" means live sessions, not this.
   - the **e-mail log rows survive** with the address nulled — the record that a message was sent
     stays.
   - it never says **when**. There is no grace period, no cooling-off, no recovery window:
     the user row is replaced in the same request.
   - "links" is meaningless to a reader.
3. The two sections are adjacent and unlinked: nothing prompts "download your data first".
4. "Delete my account" is a destructive section rendered in the same neutral card as the export,
   with no warning tone until the red button.
5. The `LAST_OWNER` refusal only surfaces after the password is typed and the dialog confirmed.
6. The password typed into the delete field stays in state after Cancel.
7. S1, S2, S3.

**Proposals, ranked.**

1. Fix the z-index so the dialog sits above the banner; suppress the banner on `/account/*`.
2. Rewrite the two leads to be true:
   > **Download my data** — A JSON file with your profile, what you follow, your saved forecasts
   > and notes, your payments, and your last 200 sign-ins.
   >
   > **Delete my account** — Deletes your account and everything in it straight away: follows,
   > saved forecasts, notes, alerts, and every signed-in device. There is no way to get it back.
   > Two things stay: payment records, which tax law requires us to keep, with your name removed;
   > and the sign-in log, for up to 90 days, which is how we investigate account trouble.
   > Any subscription is cancelled first.
3. Use `typed` on the dialog and repeat the one-line consequence in the dialog body.
4. Put "Download my data" above the delete section as a step, with a line linking them.
5. Give the export a visible success state and a hint that the file may take a moment.
6. Check `LAST_OWNER` before showing the form.

---

## 12. States I could not reach

Nothing in this audit covers these. Treat any claim about them as unverified.

**Not reachable without waiting or external systems**
- A genuinely **expired** (as opposed to invalid or already-used) verify, reset, e-mail-change or
  newsletter token. All four produce the same code path and the same copy, so the render is
  believed identical — but I did not wait out 60 minutes / 48 hours / 3 days to prove it.
- The 2FA challenge expiring after five minutes, and the "Too many wrong codes" path after five.
- The account lockout **ending** after 15 minutes.
- Any **e-mail as the reader sees it**. I captured the links and the templates in
  `emailer.DEFAULTS`, never a rendered message in a client.

**Not present in demo data**
- A-05 with billing on: `past_due`, `trialing`, `cancel_at_period_end`, a populated invoice list,
  the `Confirming…` poll after checkout, and an enabled "Manage billing" button.
- A-06 deletion with a live subscription, including the `BILLING_UNAVAILABLE` refusal.
- A-05 `comp` ("Included until …").

**Deliberately not attempted, to avoid changing shared state**
- A-06 deletion as the last owner (`LAST_OWNER`). Read from code only.
- Any real deletion of a demo account.

**Audited from code only, not rendered**
- The staff variants: A-02's "On. Staff accounts cannot turn it off.", A-04's `admin_alerts` and
  `admin_digest` rows, and P-35's staff lead reached through the `enroll_2fa` gate. I drove P-34
  and P-35 as a reader with the same gate conditions.
- `auth.google_enabled` — specified in the settings registry, not coded. No Google sign-in exists.
- Account recovery after losing both the phone and the recovery codes: **no reader-facing path
  exists**, so there is no state to capture.

**A note for whoever re-runs the capture harness**
- `scripts/shots3.js` has no entry for **P-31**, **P-34** or **P-37**, so those three never appear
  in a `before/` set. P-30, P-33 and P-36 are captured with no token in the URL, which renders the
  least informative of their three states.
- A freshly bootstrapped demo owner has `must_change_password: true` and, with
  `security.require_staff_2fa` at its default, logs in with `scope: "enroll_2fa"` — so a harness
  that signs in and navigates will capture `/enroll-2fa` for every account and admin screen. The
  `before/` set in this repository was taken after that had been cleared, and the demo owner's
  password on the running instance is no longer `demo-owner-pass-1`.

---

## 13. The five questions

### 1. Error states — does every form say what went wrong *and* how to fix it, without blaming the reader and without leaking whether an address exists?

**No, on all three counts, with a clear split.**

*Leaking.* The deliberate non-leaking work is good and consistent: sign-up, resend, forgot-password
and e-mail-change all answer 202 with "If that address can be used…", and `register` hashes the
password before the lookup so the timing matches. **One oracle survives**: the account lockout. Five
wrong passwords against a real address return `LOCKED`/429; five against an unknown address keep
returning `BAD_CREDENTIALS`/401. That is account enumeration in six requests, and it undoes the
generic message on the same screen. One other, milder: the client's e-mail-change toast asserts "We
sent a link to the new address" even when nothing was sent — not a leak, but a false statement.

*What went wrong.* Mostly yes. The messages are plain, short and in the product's voice.

*How to fix it.* Mostly no. Only **two** errors in seventeen screens carry a recovery control:
`EMAIL_NOT_VERIFIED` on P-28 (resend) and the dead-link state on P-30 (resend). Everywhere else the
reader is told to do something and given nothing to do it with — P-31 says "Ask for a new one" with
no way to ask, P-33 says the same on a screen with no link to `/forgot-password`, P-34 says the
current password is wrong on a screen you cannot leave. And nothing that imposes a wait says how
long: `LOCKED`, `RATE_LIMITED` and `CHALLENGE_EXPIRED` all omit a duration the server knows.

*Blame.* Two offenders. "Your current password is not right." and "Your password is not right."
both put *your* in front of the fault. "Wrong e-mail or password." gets it right; copy that.

*Structurally.* `Field` accepts an `error` prop and **no screen in this set passes it**. Every error
is a form-level banner, so on P-34 — three password fields — nothing says which one is wrong. And
`SignUp` and `NewPasswordForm` lack `noValidate`, so the first error many readers see is not the
product's at all, but Chromium's grey tooltip.

### 2. The journey — sign-up → verify → welcome, end to end, and every point a real person drops out

1. **Entry.** Header "Sign in"; on desktop also "Sign up free".
2. **P-29.** → *The lead sells nothing.* "E-mail and password. That is all we need." describes the
   cost. P-28, the page for people already convinced, is the one that lists benefits.
3. **Typing the password.** → *A raw browser validation bubble* on anything under ten characters,
   covering the hint that states the rule.
4. **Submit with an address that already has an account.** → *A silent dead end.* The reader is
   told a link was sent. None was. "Send the link again" starts a 60-second countdown and sends
   nothing, forever, because `resend_verification` also returns nothing for a verified account.
5. **"Check your inbox".** → *Deliverability and a 48-hour window,* and the form unmounts without a
   navigation, so the browser's save-password prompt often never fires. The reader may now not have
   the password they set 30 seconds ago.
6. **The e-mail.** → *Standard inbox attrition.*
7. **P-30 with a token.** → *An unexplained extra click.* The reader clicked a link and is asked to
   click "Confirm". The reason (mail scanners open links) is in a code comment, not on the page.
8. **P-30 success — the big one.** → *"You're in", then sign in again.* The product says the
   opposite of what it does. Combined with (5), some fraction of readers are now in the reset flow
   — which is P-32 → P-33, and P-33 is the screen that lets you fill in a form on a dead link.
9. **Signing in again.** → Anyone who hit the lockout while guessing their own password now waits
   15 minutes without being told it is 15 minutes.
10. **P-22 Welcome, step 1.** → *The cookie banner lands over the card.*
11. **Step 2, "Pick 3 teams to follow".** → The clubs come from the selected league's next and
    recent fixtures; a thin league gives "No clubs listed yet". The "3" is never enforced or
    counted against.
12. **Step 3.** → *A paywall as the last impression.* A brand-new free reader is shown alerts they
    cannot have, behind a `ProLock`, immediately before "Start".
13. **Staff or temporary-password accounts** never reach any of this: the gates divert them to
    P-35 or P-34, and P-34 has no exit.

The worst single step is (8). The cheapest fix in the whole journey is also (8): issue a session on
verification and land on `/welcome`.

### 3. The forced password change (P-34) — is it humane and clear about why it is happening?

**No to both.**

Not humane: it is a trap. `Gates` redirects every route back to it, including `/forgot-password`
and `/sign-in`, and the product has no sign-out — so a person who cannot reproduce the temporary
password has no exit but clearing cookies, and nothing on the screen tells them that. The error for
a mistyped temporary password is "Your current password is not right.", which blames them and
offers no next step. Meanwhile the screen keeps a header avatar, a search box, a notification bell,
six rail items and five bottom tabs, every one of which silently bounces back, and a mailing-list
sign-up form underneath.

Not clear: "You signed in with a first password" is internal vocabulary. The copy never says who
set the password, when, why it has to go now, or what happens if they close the tab. It does not
show which account is being fixed. And it leads with the consequence ("other devices will be signed
out") rather than the reason.

It also asks for the temporary password a second time, ten seconds after it was typed on the
sign-in page, from a password no manager has saved.

### 4. Account deletion and data export (A-06) — honest, findable, correct expectations?

**Findable: adequate.** Six account sections, and deletion is in the one called "Privacy" — a
defensible home, though "Privacy" is a weak signpost for "delete my account". It is undermined on a
phone, where the section row shows three of six tabs and Privacy is off-screen behind a hidden
scroller with no cue.

**Honest about deletion: mostly, with two real gaps.** What the copy says is true, and unusually
specific for this kind of copy — it names what goes, it admits payment records stay for tax law,
and it says the subscription is cancelled first (the code really does refuse the deletion if Stripe
is unreachable). The gaps: it does not mention that the **sign-in log survives untouched**, with
e-mail and IP per row, for up to 90 days; it does not mention that **e-mail-log rows survive** with
the address nulled; and it never says **when** — there is no grace period, nothing is queued,
nothing is recoverable, and the copy's "This cannot be undone." carries that weight alone.

**Honest about export: no.** "A JSON file with everything we hold about you" overstates. The export
omits the analytics `events` keyed to the user and, more pointedly, the `admin_notes` that staff
write *about* the reader — which deletion removes and export never shows.

**Correct expectations: undermined by a rendering fault.** On a 390px phone the confirmation dialog
is covered by the cookie banner: the question "Delete your account?" and the line "This cannot be
undone." are both hidden, and the only visible part of the dialog is the button row with a red
"Delete for good". The product also owns a typed-confirmation mode in the same component and does
not use it here. And the two sections — export and delete — sit next to each other with nothing
suggesting you do the first before the second.

### 5. Consistency — do these look like the rest of this app, or like a different one?

**Like a different one, and the reason is traceable to a single file.** `frontend/src/styles/v2.css`
is the current design layer, loaded last. It matches **zero** auth class names and exactly one
account class — `.plan-hero`, swept up incidentally by the shadow-stripping rule at line 182. These
seventeen screens never received the v2 pass. Named divergences:

1. **Shadows.** v2 §6 says "the soft grey shadow under every raised thing" is a template tell and
   strips it from nine card classes. `.acc-section` is not among them, so the account sections are
   the last shadowed cards in the product — and they sit beside `.plan-hero`, which *is* in the
   list, so the seam is visible inside one screen.
2. **Radius.** v2 redefines `--radius-md: 10px` and `--radius-lg: 12px` and declares that radius
   should vary with what a thing is. These screens use literal pixels and ignore the tokens:
   `.auth-ico` 14px, `.codes` 14px, `.qr` 16px, `.row-card` 14px, `.form-error` 12px, `.dialog`
   20px, `.auth-aside` 28px. The uniform soft radius v2 rejected lives on here.
3. **Decoration.** `.auth-aside` is two radial gradients plus a surface — exactly "the gradient
   wash used as decoration" that v2 §6 names as a default rather than a decision. It is also the
   only gradient left on any reader-facing page.
4. **Containers.** `.auth-card` has no background, border or padding — the sign-in form floats on
   the page. But P-36 and P-37 use `.link-page card`. So two screens in the same journey set are in
   a card and eight are not.
5. **Buttons.** Three scales in one journey (S4), and on desktop A-02 three widths in one column:
   an 840px "Change password", a 520px "Send confirmation link", an 840px "Turn on". The large
   full-width pill primary does not appear anywhere else in the product at that size.
6. **Literal colours.** `base.css:209` `.qr { background: #fff }`, `base.css:115` `.overlay {
   background: rgba(4, 7, 14, .62) }`, and in a component, `Auth.jsx:271` `bgColor="#FFFFFF"
   fgColor="#0A0E17"`. The house rule is `var(--token)` only.
7. **Titles.** `Auth.jsx`, `Account.jsx` and `EmailLinks.jsx` are the only page files with no
   `useTitle`. Every other page sets one and none of them reset it, so these seventeen screens
   inherit whatever the previous page left in the tab.
8. **Typography.** v2's whole concept is the Archivo width axis — `font-stretch` on kickers, scores,
   data labels. Not one auth or account class uses it, so these screens are the only place the
   product's typographic idea is absent.
9. **Layout.** Every other reader screen has a page-level identity. These share one `AuthCard`,
   and the only thing that changes between "Sign in", "Set a new password" and "Set up two-factor"
   is a 22px icon glyph in a tinted square.

The content is in better shape than the shell. The copy on P-32, A-04, A-05 and the recovery-codes
step is some of the clearest writing in the product. It is wearing last season's chrome.
