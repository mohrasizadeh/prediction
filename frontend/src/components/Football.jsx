// Shared pieces for the public data screens (docs/04 §7): the stat and tactic vocabularies, TacticChip,
// MatchRow, FormPills and the small hooks. Times are parsed with utc(); images only through Media.jsx.
//
// The card itself lives in components/ui/ForecastCard.jsx and the tier badge, likelihood bar and
// win/draw/loss bar in components/ui/Marks.jsx. This file carried its own earlier copies of all four
// (TierBadge, LikelihoodBar, ForecastCard, ProbBar) long after every screen had moved to the kit; they
// had no importers left, so a reader comparing the two had no way to tell which one shipped.
import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { utc } from "../lib/time";
import { Crest } from "./Media";
import { WdlBar } from "./ui/Marks";

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
// The subset `team_match_stats` actually stores a column for (normalize.TEAM_COLS), so the club's
// Quick view only offers stats it can answer game by game. Red cards are forecast but not kept per
// match, and offering them would have drawn an empty strip that reads as a broken screen.
export const TEAM_HISTORY_STATS = TEAM_STATS.filter((s) => s.id !== "red_cards");
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

export const TacticChip = ({ t, prefix }) => <span className="tchip" data-testid={`tactic-${t}`}>{prefix ? `${prefix}: ` : ""}{TACTICS[t] || t.replace(/_/g, " ")}</span>;

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
