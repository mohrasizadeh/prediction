// Live pill and live card (docs/24). The pill floats while something is live and opens the live sheet.
// The card reads the public fixture shape of GET /api/live and, optionally, its events.
import { Crest } from "../Media";
import LiveStatus from "../LiveStatus";
import { fxLive, fxStarted } from "../../lib/live";
import { EvIcon, kindLabel, normEvent } from "../MatchEvents";

export function LivePill({ count, onClick, floating = false, testid = "ui-live-pill" }) {
  if (!count) return null;
  return (
    <button type="button" className={`k-livepill${floating ? " k-livepill--float" : ""}`} onClick={onClick} data-testid={testid} aria-label={`${count} live, open live scores`}>
      <span className="k-livedot" aria-hidden="true" />{count} live
    </button>
  );
}

// Goals and cards per half for each side: the thin "who is pushing" strip (docs/24 §2). It is drawn only from
// three events up: with one or two the bar would just restate the last event (docs/redesign/README data gaps).
// Events are read through MatchEvents' reader, so a card from either feed lands on the right side and half.
function Momentum({ events }) {
  const ev = events.map(normEvent).filter((e) => e.side && e.base != null && e.kind !== "sub");
  if (ev.length < 3) return null;
  const n = (side, half) => ev.filter((e) => e.side === side && (half === 1 ? e.base <= 45 : e.base > 45)).length;
  const parts = [1, 2].map((h) => [n("home", h), n("away", h)]);
  return (
    <div className="k-momentum" role="img" aria-label={parts.map(([a, b], i) => `Half ${i + 1}: home ${a} goals and cards, away ${b}`).join(". ")}>
      {parts.map(([a, b], i) => <span key={i} aria-hidden="true"><b style={{ flexGrow: a || 0.01 }} /><i style={{ flexGrow: b || 0.01 }} /></span>)}
    </div>
  );
}

export function LiveCard({ f, events = [], flash = false, onOpen, testid }) {
  const playing = fxLive(f);
  const sc = f.score || {};
  const all = events.map(normEvent).sort((a, b) => a.order - b.order);
  const last = [...all].reverse().find((e) => e.kind !== "sub") || all[all.length - 1];
  const id = testid || `ui-live-card-${f.sid}`;
  const started = fxStarted(f) && sc.home != null;
  return (
    <button type="button" className={`k-livecard${playing ? " is-live" : ""}${flash ? " is-flash" : ""}`} onClick={onOpen} data-testid={id}>
      <div className="k-livecard-top"><LiveStatus status={f.status} state={f.state} live={f.live} minute={f.minute} kickoff={f.kickoff} text={f.status_text} testid={`${id}-status`} /><span className="k-faint">{f.league_name}</span></div>
      <div className="k-livecard-row">
        <span className="k-lc-team"><Crest team={f.home.team} size={24} /><span>{f.home.team?.name || f.home.name}</span></span>
        <b className="k-lc-score" data-testid={`${id}-score`}>{started ? `${sc.home}–${sc.away}` : "v"}</b>
        <span className="k-lc-team k-lc-team--a"><span>{f.away.team?.name || f.away.name}</span><Crest team={f.away.team} size={24} /></span>
      </div>
      {last && <p className="k-lc-last" data-testid={`${id}-last`}><EvIcon kind={last.kind} size={16} /><span>{kindLabel(last.kind)}{last.name ? `, ${last.name}` : ""} {last.label}{last.assist ? ` · assist ${last.assist}` : ""}</span></p>}
      <Momentum events={events} />
    </button>
  );
}
