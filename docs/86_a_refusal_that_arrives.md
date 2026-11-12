# 86 — A refusal that arrives

## The symptom

The Competitions screen showed `SERVER_ERROR` in a toast when "Refresh the list" was pressed. No
detail, nothing to act on, and the string points at our own server.

## What was actually happening

Nothing was broken in the sync. The chain works: `sync_catalog` was run against the real
`apifootball.Client` with the HTTP layer stubbed, and against eight malformed competition shapes
(null seasons, null coverage, missing league block, missing country block, null name, type and
year). All of it survives. The route, `catalog_page`, `catalog_meta`, the filters, the paging and
the per-row switch all work.

What happened was this:

1. API-Football refused the call and said why.
2. `routes_data_admin` translated that into `502` with a proper JSON body —
   `{"error": {"code": "PROVIDER", "message": "<their words>", "request_id": "..."}}`.
3. Something between the app and the browser **replaced the body of that 5xx with its own error
   page**. This is ordinary hosting-ingress behaviour and we do not control it.
4. `lib/api.js` could not parse the body, so `(data && data.error) || {}` was empty and
   `e.code || "SERVER_ERROR"` produced `SERVER_ERROR`.
5. The app log recorded `502` with an **empty trace**, because a deliberate `D.err` is not a crash.

So the screen blamed our server for a refusal by theirs, the only useful sentence was destroyed in
transit, and the log had a status with no reason. Three different places each told a half-truth and
the three together pointed away from the cause.

## The rule

**An upstream's refusal is reported below 500.** `deps.upstream()` exists for exactly this and is
fixed at `409`.

This is not a theory about HTTP semantics. It is evidence: the four provider errors that already
used `409` — budget spent, breaker open, key rejected, plan limited — arrived intact the whole
time. Only the generic `APIFootballError` used `502`, and only that one was being eaten.

The status on these routes is read by an operator looking at a screen. What they need is the
reason. A status that is technically apt and destroys the message is the wrong status.

## What changed

* `deps.upstream(code, message)` — one helper, `409`, with the reasoning at the definition.
* `routes_data_admin.py` and `routes_live.py` use it for every provider refusal. No `502` remains
  in either.
* `lib/api.js` no longer calls an unparseable body `SERVER_ERROR`. It is `UNREADABLE_ERROR`, it
  carries the real status and it names where the request id can be found. The two facts — *our
  server reported a fault* and *the reply could not be read* — are different, and conflating them
  is what sent the search in the wrong direction.
* `apifootball._check_guards` guards `expires_at` the way `fetch` always did. A breaker row without
  that field raised `KeyError`, and one holding `null` raised `TypeError`; neither is an
  `APIFootballError`, so no route could translate it and it surfaced as a bare 500 with an empty
  trace. A row whose expiry cannot be read is treated as expired: the breaker opens on evidence,
  not on a damaged row.

## The tests

Both were checked by reverting the fix and watching them fail, which is the only thing that
distinguishes a test from a comment.

* `selftest_apifootball.t_breaker_row_without_an_expiry` — fails with `KeyError` and `TypeError`
  against the old guard, and still proves an unexpired breaker stops the call.
* `selftest_data_admin` — asserts, for a provider error, a rejected key, a spent budget and a plan
  limit, that the status is **below 500** and that the body carries the provider's own words.
  Fails with `got 502` against the old route.

## What this does not fix

It does not tell you why API-Football refused. That answer is in **Admin → Logs → the API tab**,
which records every provider call with the HTTP status they returned and their first error key.
With this change the reason also reaches the toast, so the log is a second opinion rather than the
only one.

`routes_billing.py` and the Stripe path in `routes_admin.py` still use `502` and have the same
weakness. They are left alone deliberately: they are user-facing payment flows with their own
fixed, friendly copy, and changing a status there interacts with retry behaviour that wants
thinking about separately.
