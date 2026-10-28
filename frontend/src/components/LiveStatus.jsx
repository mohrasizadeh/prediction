// Status chip for a match (docs/23): "Live 67'", "HT", "Full time", or the kick-off time.
import { utc } from "../lib/time";

const WORDS = { FT: "Full time", AET: "After extra time", PENS: "After penalties", Postponed: "Postponed", Cancelled: "Cancelled", Suspended: "Suspended" };

export default function LiveStatus({ status, minute, kickoff, text, testid = "live-status" }) {
  if (status === "LIVE") {
    const ht = minute === "HT";
    return <span className="live-chip" data-testid={testid} aria-label={ht ? "Live, half-time" : `Live, minute ${minute || ""}`}><span className="live-dot" aria-hidden="true" />{ht ? "HT" : `Live ${minute || ""}`}</span>;
  }
  if (status === "Scheduled" || !status) {
    return <time className="muted" data-testid={testid}>{kickoff ? utc(kickoff).toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" }) : "–"}</time>;
  }
  return <span className={`status-chip ${["Postponed", "Cancelled", "Suspended"].includes(status) ? "status-warn" : ""}`} data-testid={testid}>{text || WORDS[status] || status}</span>;
}
