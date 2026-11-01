// Is a match being played? (docs/42)
//
// The browser must not test the provider's status word itself. SportAPI's vocabulary is not documented for us, and
// a match at half time, in extra time, in the break before it or in a word we have never seen is still being
// played. Every screen here used to test `status === "LIVE"`, so for all of those periods the live dot went out,
// the score stopped refreshing, the Live sheet filed the match under Finished and the match page stopped asking
// which forecasts had happened — which is why lines did not turn green as they happened.
//
// The server decides and sends the answer: `state` ("live" | "later" | "done") and `live` on a fixture, `playing`
// inside a match's `live` block. The word is only read as a fallback, for a payload cached before those existed.

export const fxState = (f) => f?.state || (f?.status === "LIVE" ? "live" : f?.status === "Scheduled" || !f?.status ? "later" : "done");
export const fxLive = (f) => (typeof f?.live === "boolean" ? f.live : fxState(f) === "live");
export const fxStarted = (f) => fxState(f) !== "later";

// A match row from /matches or /matches/{id}: SportAPI's own view of it sits in `m.live`, with `m.phase` beside it.
export const mLive = (m) => (typeof m?.live?.playing === "boolean" ? m.live.playing : m?.phase === "live" || m?.live?.status === "LIVE");
// Being played AND not already settled on our side: what the screens mean by "live now".
export const isLiveNow = (m) => mLive(m) && m?.status !== "final" && m?.status !== "postponed" && m?.status !== "cancelled";
// Half time, whichever of the two fields the provider puts it in.
export const atHalfTime = (status, minute) => minute === "HT" || status === "HT" || status === "Half Time";
