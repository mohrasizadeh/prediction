// Live pill and live card (docs/24). The pill floats while something is live and opens the live sheet.
// The card reads the public fixture shape of GET /api/live (sportapi.public_fixture) and, optionally, its events.
import { Crest } from "../Media";
import LiveStatus from "../LiveStatus";

export function LivePill({ count, onClick, floating = false, testid = "ui-live-pill" }) {
  if (!count) return null;
  return (
    <button type="button" className={`k-livepill${floating ? " k-livepill--float" : ""}`} onClick={onClick} data-testid={testid} aria-label={`${count} live, open live scores`}>
      <span className="k-livedot" aria-hidden="true" />{count} live
    </button>
  );
}

const WORD = { goal: "Goal", own_goal: "Own goal", penalty: "Penalty goal", yellow_card: "Yellow card", red_card: "Red card", second_yellow: "Second yellow", substitution: "Substitution", missed_penalty: "Penalty missed" };

function Momentum({ events }) {
  const n = (side, half) => events.filter((e) => e.side === side && (half === 1 ? e.minute_num <= 45 : e.minute_num > 45)).length;
  if (events.length < 3) return null;
  const parts = [1, 2].map((h) => [n("home", h), n("away", h)]);
  return (
    <div className="k-momentum" role="img" aria-label={parts.map(([a, b], i) => `Half ${i + 1}: home ${a} events, away ${b}`).join(". ")}>
      {parts.map(([a, b], i) => <span key={i} aria-hidden="true"><b style={{ flexGrow: a || 0.01 }} /><i style={{ flexGrow: b || 0.01 }} /></span>)}
    </div>
  );
}

export function LiveCard({ f, events = [], flash = false, onOpen, testid }) {
  const sc = f.score || {};
  const last = [...events].reverse().find((e) => e.type !== "substitution") || events[events.length - 1];
  const id = testid || `ui-live-card-${f.sid}`;
  const started = f.status !== "Scheduled" && sc.home != null;
  return (
    <button type="button" className={`k-livecard${f.status === "LIVE" ? " is-live" : ""}${flash ? " is-flash" : ""}`} onClick={onOpen} data-testid={id}>
      <div className="k-livecard-top"><LiveStatus status={f.status} minute={f.minute} kickoff={f.kickoff} text={f.status_text} testid={`${id}-status`} /><span className="k-faint">{f.league_name}</span></div>
      <div className="k-livecard-row">
        <span className="k-lc-team"><Crest team={f.home.team} size={24} /><span>{f.home.team?.name || f.home.name}</span></span>
        <b className="k-lc-score" data-testid={`${id}-score`}>{started ? `${sc.home}–${sc.away}` : "v"}</b>
        <span className="k-lc-team k-lc-team--a"><span>{f.away.team?.name || f.away.name}</span><Crest team={f.away.team} size={24} /></span>
      </div>
      {last && <p className="k-lc-last">{WORD[last.type] || (last.type || "Event").replace(/_/g, " ")}{last.player_name ? `, ${last.player_name}` : ""} {last.minute}</p>}
      <Momentum events={events} />
    </button>
  );
}
