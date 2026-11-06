// Shared pieces for the public data screens (docs/04 §7): TierBadge, LikelihoodBar, TacticChip, ForecastCard,
// MatchRow, ProbBar, FormPills. Times are parsed with utc(); images only through Media.jsx.
import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { pct, TIER } from "../lib/copy";
import { utc } from "../lib/time";
import { Crest, PlayerAvatar } from "./Media";
import { WdlBar } from "./ui/Marks";
import { SaveButton } from "./Actions";

export const kickoff = (s, opts = { weekday: "short", day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" }) => (s ? utc(s).toLocaleString(undefined, opts) : "No date");
export const shortDay = (s) => kickoff(s, { day: "numeric", month: "short" });
export const num1 = (v) => (v === null || v === undefined ? "–" : Number.isInteger(v) ? String(v) : v.toFixed(1));

export const STATS = [
  { id: "shots", label: "Shots", core: true }, { id: "sot", label: "Shots on target", core: true }, { id: "tackles", label: "Tackles", core: true },
  { id: "goals", label: "Goals", core: true }, { id: "assists", label: "Assists", core: true }, { id: "minutes", label: "Minutes", core: true },
  { id: "xg", label: "Expected goals (xG)" }, { id: "interceptions", label: "Interceptions" }, { id: "clearances", label: "Clearances" },
  { id: "fouls_committed", label: "Fouls committed" }, { id: "fouls_won", label: "Fouls won" }, { id: "saves", label: "Saves" },
  { id: "yellow_cards", label: "Yellow cards", core: true }, { id: "red_cards", label: "Red cards" }, { id: "pen_goals", label: "Penalty goals" },
];
export const TEAM_STATS = [{ id: "shots", label: "Shots", core: true }, { id: "sot", label: "Shots on target", core: true }, { id: "corners", label: "Corners", core: true }, { id: "tackles", label: "Tackles", core: true },
  { id: "xg", label: "Expected goals (xG)" }, { id: "yellow_cards", label: "Yellow cards" }, { id: "red_cards", label: "Red cards" }];
export const MATCH_STATS = [{ id: "match_yellow_cards", label: "Yellow cards in the match", core: true }];
const TACTICS = { low_block: "Low block", high_press: "High press", possession: "Possession" };

// Per-browser table preferences (columns shown, hidden games).
export function useStored(key, init) {
  const [v, setV] = useState(() => { try { const s = JSON.parse(localStorage.getItem(key)); return s ?? init; } catch { return init; } });
  const set = (n) => { setV(n); localStorage.setItem(key, JSON.stringify(n)); };
  return [v, set];
}

export function ColumnPicker({ options, value, onChange, testid }) {
  const ref = useRef(null);
  useEffect(() => {
    const off = (e) => { if (ref.current?.open && !ref.current.contains(e.target)) ref.current.open = false; };
    document.addEventListener("pointerdown", off);
    return () => document.removeEventListener("pointerdown", off);
  }, []);
  return (
    <details ref={ref} className="colpick" data-testid={testid}>
      <summary className="btn btn--ghost btn--sm">Columns ({value.length})</summary>
      <div className="colpick-menu">
        {options.map((o) => (
          <label key={o.id} className="check-inline"><input type="checkbox" checked={value.includes(o.id)} data-testid={`${testid}-${o.id}`}
            onChange={(e) => onChange(e.target.checked ? options.map((x) => x.id).filter((id) => id === o.id || value.includes(id)) : value.filter((x) => x !== o.id))} />{o.label}</label>
        ))}
      </div>
    </details>
  );
}
const POS = { GK: "Goalkeeper", DEF: "Defender", MID: "Midfielder", FWD: "Forward" };
export const posLabel = (p) => POS[p] || "Position unknown";

export function useTitle(title) {
  useEffect(() => { if (title) document.title = title; }, [title]);
}

export function TierBadge({ tier }) {
  if (!tier) return null;
  const n = TIER[tier]?.dots || 0;
  return (
    <span className={`tier tier--${tier.toLowerCase()}`} aria-label={`${tier} tier, ${n} of 3`} data-testid="tier-badge">
      <span aria-hidden="true">{"●".repeat(n)}</span>{tier}
    </span>
  );
}

export function LikelihoodBar({ p, lo, hi, tier, confirmed }) {
  const tone = tier ? `var(--tier-${tier.toLowerCase()})` : "var(--text3)";
  return (
    <div className="lbar" style={{ "--tone": tone }}>
      <div className="lbar-top"><strong className="lbar-val">{pct(p)}</strong>{confirmed !== undefined && <span className="muted small">{confirmed ? "Confirmed" : "Predicted"}</span>}</div>
      <div className="lbar-track" aria-hidden="true">
        {lo != null && hi != null && <span className="lbar-band" style={{ left: `${lo * 100}%`, width: `${Math.max(0, hi - lo) * 100}%` }} />}
        <span className="lbar-fill" style={{ width: `${(p || 0) * 100}%` }} />
      </div>
      {lo != null && hi != null && <span className="muted small">{Math.round(lo * 100)} to {Math.round(hi * 100)}</span>}
    </div>
  );
}

export const TacticChip = ({ t, prefix }) => <span className="tchip" data-testid={`tactic-${t}`}>{prefix ? `${prefix}: ` : ""}{TACTICS[t] || t.replace(/_/g, " ")}</span>;

export function ForecastCard({ f, teams = {}, showMatch, homeIid }) {
  const [open, setOpen] = useState(false);
  const team = f.team || teams[f.team_iid];
  const opp = f.opp || teams[f.opp_iid];
  const hid = f.home_iid ?? homeIid;
  const fixture = team && opp ? (hid === f.opp_iid ? `${opp.name} v ${team.name}` : `${team.name} v ${opp.name}`) : team?.name || "";
  const reasons = f.reasons || [];
  const more = f.more_lines || [];
  return (
    <article className="fcard" data-testid={`forecast-${f.id}`}>
      <header className="fcard-head">
        {f.player ? <PlayerAvatar player={f.player} size={40} /> : f.stat?.startsWith("match_") && team && opp ? <span className="fcard-crests">{hid === f.opp_iid ? <><Crest team={opp} size={32} /><Crest team={team} size={32} /></> : <><Crest team={team} size={32} /><Crest team={opp} size={32} /></>}</span> : <Crest team={team} size={40} />}
        <div className="fcard-who">
          {f.player ? <Link to={`/player/${f.player.id}`}><b>{f.player.name}</b></Link> : <b>{f.stat?.startsWith("match_") ? fixture || "Match" : team?.name || ""}</b>}
          <span className="muted small">{f.player && f.pos ? `${posLabel(f.pos)} · ` : ""}{f.stat?.startsWith("match_") ? "Both teams" : fixture}{showMatch ? ` · ${kickoff(f.kickoff)}` : ""}</span>
        </div>
        <TierBadge tier={f.tier} />
        {f.fkey && <SaveButton fkey={f.fkey} />}
      </header>
      <p className="fcard-market">{f.market}</p>
      <LikelihoodBar p={f.p} lo={f.lo} hi={f.hi} tier={f.tier} confirmed={f.scope === "player" ? f.lineup_confirmed : undefined} />
      {(f.opp_tactics || []).length > 0 && <div className="chips">{f.opp_tactics.map((t) => <TacticChip key={t} t={t} prefix="Opponent" />)}</div>}
      {reasons[0] && <p className="fcard-reason">{reasons[0]}</p>}
      {more.length > 0 && (
        <details className="fcard-lines" data-testid={`forecast-more-${f.id}`}>
          <summary className="linkish">Other lines ({more.length})</summary>
          <ul className="fcard-more">{more.map((x) => <li key={x.fkey}><span>{x.market}</span><b>{pct(x.p)}</b></li>)}</ul>
        </details>
      )}
      <button type="button" className="linkish" onClick={() => setOpen(!open)} aria-expanded={open} data-testid={`forecast-why-${f.id}`}>{open ? "Hide the numbers" : "Why"}</button>
      {open && (
        <dl className="fcard-why">
          {reasons.slice(1, 2).map((r) => <dd key={r} className="fcard-reason">{r}</dd>)}
          <div><dt>Expected</dt><dd>{num1(f.expected)}</dd></div>
          {f.p_play != null && f.scope === "player" && <div><dt>Chance to play</dt><dd>{pct(f.p_play)}</dd></div>}
          {f.rotation && <div><dt>Rotation risk</dt><dd>{f.rotation}</dd></div>}
        </dl>
      )}
    </article>
  );
}

export function ProbBar({ probs }) {
  if (!probs) return <span className="muted small">No forecast yet</span>;
  const parts = [["Home", probs.p_home], ["Draw", probs.p_draw], ["Away", probs.p_away]];
  return (
    <div className="prob" aria-label={parts.map(([k, v]) => `${k} ${pct(v)}`).join(", ")} data-testid="prob-bar">
      {parts.map(([k, v]) => <span key={k} className={`prob-${k.toLowerCase()}`} style={{ flexGrow: v || 0.01 }}>{pct(v)}</span>)}
    </div>
  );
}

// One fixture row, used by the league page and anywhere else a list of fixtures appears.
//
// CRITIQUE section 1: the same fixture was drawn two ways. On Today it carried a win/draw/away bar
// and what the forecasts say; here it was time, two club names and a "v". A reader who opened a
// league to decide which match to watch got strictly less than one who stayed on the front page.
// The row now shows the same things, from the same fields, so the two cannot drift apart.
export function MatchRow({ m }) {
  const final = m.status === "final" && m.hg != null;
  const p = m.probs;
  const best = m.best_line;
  // The row was a single anchor to the match, so the club names could not be links -- nesting one
  // anchor inside another is invalid -- and there was no route at all from a league fixture to a
  // club page. The match link is now a stretched hit area behind the row, which keeps the whole
  // row tappable and its testid, and the two club names sit above it as real links.
  const club = (t, end) => (t?.id
    ? <Link to={`/team/${t.id}`} className={"team mrow-club" + (end ? " team--end" : "")} data-testid={`mrow-club-${t.id}`}>
        {end ? <>{t.name} <Crest team={t} size={20} /></> : <><Crest team={t} size={20} /> {t.name}</>}
      </Link>
    : <span className={"team" + (end ? " team--end" : "")}>{end ? <>{"Away"} <Crest team={t} size={20} /></> : <><Crest team={t} size={20} /> {"Home"}</>}</span>);
  return (
    <li className="mrow-li">
      <div className="mrow">
        <Link to={`/match/${m.id}`} className="mrow-hit" aria-label={`${m.home?.name || "Home"} v ${m.away?.name || "Away"}, open the match`} data-testid={`match-row-${m.id}`} />
        <time className="mrow-time">{final ? shortDay(m.kickoff) : kickoff(m.kickoff)}</time>
        {club(m.home, false)}
        <span className="mrow-score">{final ? `${m.hg} – ${m.ag}` : "v"}</span>
        {club(m.away, true)}
        {!final && p && <span className="mrow-bar"><WdlBar home={p.p_home} draw={p.p_draw} away={p.p_away} homeName={m.home?.name} awayName={m.away?.name} testid={`mrow-wdl-${m.id}`} /></span>}
        {/* A count is not a value: every fixture has a similar number of lines, so "14 insights"
            never helped anyone choose. The row says the one line most worth reading instead. */}
        {best?.market && <span className="mrow-best" data-testid={`mrow-best-${m.id}`}>
          <b>{best.who}</b> {best.market} <em>{Math.round((best.p || 0) * 100)}%</em>
        </span>}
      </div>
    </li>
  );
}

export const FormPills = ({ form = [] }) => (
  <ol className="form-pills" aria-label="Last results, newest first" data-testid="form-pills">
    {form.map((g) => <li key={g.match_iid} className={`fp fp--${g.result}`} title={`${g.home ? "Home" : "Away"} v ${g.opp?.name || "opponent"}: ${g.gf}–${g.ga}`}>{g.result}</li>)}
  </ol>
);

export function Select({ label, value, onChange, options, testid }) {
  return (
    <label className="sel">
      <span className="sr-only">{label}</span>
      <select value={value} onChange={(e) => onChange(e.target.value)} aria-label={label} data-testid={testid}>
        {options.map((o) => <option key={o.id} value={o.id}>{o.label}</option>)}
      </select>
    </label>
  );
}

export function Seg({ value, onChange, options, label, testid }) {
  return (
    <div className="seg2" role="group" aria-label={label} data-testid={testid}>
      {options.map((o) => <button type="button" key={o.id} className={String(value) === String(o.id) ? "on" : ""} aria-pressed={String(value) === String(o.id)} onClick={() => onChange(o.id)}>{o.label}</button>)}
    </div>
  );
}
