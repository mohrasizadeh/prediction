// Status chip for a match (docs/23): "Live 67'", "HT", "Full time", or the kick-off time.
import { utc } from "../lib/time";
import { atHalfTime, fxLive, fxState } from "../lib/live";

// Both vocabularies: SportAPI's long words and API-Football's short codes. The codes were missing,
// so a called-off match showed the raw "PST" or "CANC" and lost its warning styling. The server
// sends `text` (status_text) and this is only the fallback -- but a fallback that prints a provider
// code is not a fallback. docs/89.
const WORDS = {
  FT: "Full time", AET: "After extra time", PENS: "After penalties", PEN: "After penalties",
  Postponed: "Postponed", Cancelled: "Cancelled", Suspended: "Suspended",
  PST: "Postponed", CANC: "Cancelled", ABD: "Abandoned", AWD: "Awarded", WO: "Walkover",
  SUSP: "Suspended", INT: "Interrupted", NS: "Not started", TBD: "Not started",
};
// The ones that deserve a warning tone, in either vocabulary.
const WARN = ["Postponed", "Cancelled", "Suspended", "PST", "CANC", "ABD", "SUSP", "INT", "WO"];

// The minute as a reader writes it: 67', 45+2'. The feed sends a number (API-Football) or a label ("67'", SportAPI).
export const minuteText = (m) => {
  if (m == null || m === "") return "";
  const s = String(m).trim();
  return /^\d+(\s*\+\s*\d+)?$/.test(s) ? `${s.replace(/\s+/g, "")}'` : s;
};
// Periods that are still "live" but are not a running clock. API-Football short codes; unknown words fall
// through to the minute, which is the safe direction (docs/42).
const PERIOD = { BT: ["Break", "break before extra time"], P: ["Pens", "penalty shoot-out"], PEN_LIVE: ["Pens", "penalty shoot-out"], INT: ["Paused", "play interrupted"], SUSP: ["Suspended", "suspended"] };

export default function LiveStatus({ status, minute, kickoff, text, state, live, testid = "live-status" }) {
  const f = { status, state, live };
  if (fxLive(f)) {
    const ht = atHalfTime(status, minute);
    const per = PERIOD[String(status || "").toUpperCase()];
    const et = String(status || "").toUpperCase() === "ET";
    const min = minuteText(minute);
    const word = ht ? "HT" : per ? per[0] : `${et ? "ET" : "Live"}${min ? ` ${min}` : ""}`;
    const say = ht ? "Live, half-time" : per ? `Live, ${per[1]}` : `Live${et ? ", extra time" : ""}${min ? `, minute ${min.replace("'", "")}` : ""}`;
    return <span className="live-chip" data-testid={testid} aria-label={say}><span className="live-dot" aria-hidden="true" /><span aria-hidden="true">{word}</span></span>;
  }
  if (fxState(f) === "later") {
    return <time className="muted" data-testid={testid}>{kickoff ? utc(kickoff).toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" }) : "–"}</time>;
  }
  return <span className={`status-chip ${WARN.includes(status) ? "status-warn" : ""}`} data-testid={testid}>{text || WORDS[status] || status}</span>;
}
