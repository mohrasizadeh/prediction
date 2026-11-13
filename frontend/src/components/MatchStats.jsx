// Match page, Stats tab: what each side did in a finished match (queries._match_stats -> team_stats,
// player_stats). Possession as one split bar, then grouped paired bars, then every player's numbers.
//
// A value the provider did not send is null and prints "–": a 0 would be a claim we do not hold. A row
// where neither side has a number says nothing, so it is left out, and a group with no rows goes with it.
// The provider's match rating exists only on API-Football data; without one the rating column and the
// pitch badge are not drawn at all.
import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { Crest, PlayerAvatar } from "./Media";
import { Empty } from "./States";
import { Seg, posLabel } from "./Football";

const int = (v) => (v == null ? "–" : String(Math.round(v)));
const dec1 = (v) => (v == null ? "–" : Number(v).toFixed(1));
const dec2 = (v) => (v == null ? "–" : Number(v).toFixed(2));

// ------------------------------------------------------------------ rating
// Bands on the 0-10 scale API-Football uses, coloured with the tier tokens the rest of the site
// already reads as "strong / solid / watch", so no new colour has to be learnt. The words go to
// screen readers; the colour is never the only signal (the number is printed).
export const ratingBand = (r) => (r == null ? null : r >= 8 ? "top" : r >= 7 ? "good" : r >= 6 ? "fair" : "low");
const BAND_WORD = { top: "excellent", good: "good", fair: "average", low: "below average" };

export function RatingBadge({ value, className = "", lead = "" }) {
  const b = ratingBand(value);
  if (!b) return null;
  return (
    <span className={`mst-rate mst-rate--${b} ${className}`.trim()} data-testid="rating-badge">
      <span aria-hidden="true">{dec1(value)}</span>
      <span className="sr-only">{lead}rated {dec1(value)} out of 10, {BAND_WORD[b]}</span>
    </span>
  );
}

// ------------------------------------------------------------------ team bars
const GROUPS = [
  { id: "shots", title: "Shots", rows: [["shots", "Total shots", int], ["sot", "Shots on target", int], ["xg", "Expected goals (xG)", dec2]] },
  { id: "attack", title: "Attacking", rows: [["corners", "Corners", int]] },
  { id: "defence", title: "Defence", rows: [["tackles", "Tackles", int]] },
  { id: "discipline", title: "Discipline", rows: [["fouls", "Fouls", int], ["yellow_cards", "Yellow cards", int]] },
];

function PairRow({ label, h, a, fmt, home, away }) {
  const max = Math.max(h ?? 0, a ?? 0);
  const more = h != null && a != null && h !== a ? (h > a ? "home" : "away") : null;
  const w = (v) => (v == null || max <= 0 ? 0 : (v / max) * 100);
  return (
    <li className="mst-row" data-testid="stats-row">
      <div className="mst-row-top">
        <span className={`mst-val mst-val--home${more === "home" ? " is-more" : ""}`}>{fmt(h)}</span>
        <span className="mst-label">{label}</span>
        <span className={`mst-val mst-val--away${more === "away" ? " is-more" : ""}`}>{fmt(a)}</span>
      </div>
      <div className="mst-bars" aria-hidden="true">
        <span className="mst-track mst-track--home"><i className={more === "home" ? "is-more" : ""} style={{ width: `${w(h)}%` }} /></span>
        <span className="mst-track mst-track--away"><i className={more === "away" ? "is-more" : ""} style={{ width: `${w(a)}%` }} /></span>
      </div>
      <span className="sr-only">{home} {fmt(h)}, {away} {fmt(a)}</span>
    </li>
  );
}

function Possession({ h, a, home, away }) {
  if (h == null && a == null) return null;
  const tot = (h ?? 0) + (a ?? 0) || 1;
  // The two numbers are printed as the provider sent them; the bar splits on their share, so it always
  // fills even when the two do not add to exactly 100.
  const hp = h == null ? 0 : (h / tot) * 100;
  return (
    <section className="mst-poss" aria-labelledby="mst-poss-h" data-testid="stats-possession">
      <h3 className="mst-poss-h" id="mst-poss-h">Ball possession</h3>
      <div className="mst-poss-bar" aria-hidden="true">
        <span className="mst-poss-home" style={{ flexBasis: `${hp}%` }}>{h == null ? "–" : `${Math.round(h)}%`}</span>
        <span className="mst-poss-away" style={{ flexBasis: `${100 - hp}%` }}>{a == null ? "–" : `${Math.round(a)}%`}</span>
      </div>
      <p className="sr-only">{home} {h == null ? "unknown" : `${Math.round(h)}%`}, {away} {a == null ? "unknown" : `${Math.round(a)}%`}</p>
    </section>
  );
}

// ------------------------------------------------------------------ player table
// Every column the Stats tab can draw, in the order it draws them. `fmt` decides the print; sorting
// always uses the raw number.
const COLS = {
  rating: { label: "Rating", abbr: "Rating", title: "The data provider's match rating, out of 10" },
  minutes: { label: "Min", title: "Minutes played", fmt: int },
  goals: { label: "G", title: "Goals", fmt: int },
  assists: { label: "A", title: "Assists", fmt: int },
  shots: { label: "Sh", title: "Shots", fmt: int },
  sot: { label: "SoT", title: "Shots on target", fmt: int },
  xg: { label: "xG", title: "Expected goals", fmt: dec2 },
  passes: { label: "Pass", title: "Passes", fmt: int },
  fouls_won: { label: "FW", title: "Fouls won", fmt: int },
  tackles: { label: "Tkl", title: "Tackles", fmt: int },
  interceptions: { label: "Int", title: "Interceptions", fmt: int },
  clearances: { label: "Clr", title: "Clearances", fmt: int },
  fouls_committed: { label: "Fls", title: "Fouls committed", fmt: int },
  saves: { label: "Sv", title: "Saves", fmt: int },
};
const SETS = [
  { id: "top", label: "Top stats", cols: ["rating", "minutes", "goals", "assists", "shots", "sot", "xg"] },
  { id: "attack", label: "Attack", cols: ["goals", "assists", "shots", "sot", "xg", "passes", "fouls_won"] },
  { id: "defence", label: "Defence", cols: ["tackles", "interceptions", "clearances", "fouls_committed"] },
  { id: "gk", label: "Goalkeeping", cols: ["minutes", "saves"], only: (r) => r.pos === "GK" || r.saves != null },
];

const DEFAULT_SORT = { top: ["minutes"], attack: ["shots", "goals"], defence: ["tackles", "interceptions"], gk: ["saves"] };

function PlayerTable({ d }) {
  const ps = d.player_stats;
  const rows = useMemo(() => ps || [], [ps]);
  // Only columns somebody in this match has a number for, and only sets that keep at least one of them.
  const has = useMemo(() => new Set(Object.keys(COLS).filter((c) => rows.some((r) => r[c] != null))), [rows]);
  const sets = SETS.map((s) => ({ ...s, cols: s.cols.filter((c) => has.has(c)) })).filter((s) => s.cols.length && (s.id !== "gk" || has.has("saves")));
  const [team, setTeam] = useState("both");
  const [setId, setSetId] = useState("top");
  const set = sets.find((s) => s.id === setId) || sets[0];
  const [sort, setSort] = useState(null);                     // { key, dir }; null = the set's natural order
  if (!rows.length || !set) return <Empty icon="users" testid="stats-players-empty">No player numbers for this match yet.</Empty>;
  // Each set opens on its headline column: the rating where there is one, else the number the set is about.
  const key = sort && set.cols.includes(sort.key) ? sort.key : [...(set.cols.includes("rating") ? ["rating"] : []), ...(DEFAULT_SORT[set.id] || [])].find((c) => set.cols.includes(c)) || set.cols[0];
  const dir = sort && sort.key === key ? sort.dir : "desc";
  const shown = rows.filter((r) => (team === "both" || r.side === team) && (!set.only || set.only(r)))
    .slice()
    .sort((x, y) => {
      const a = x[key], b = y[key];
      if (a == null && b == null) return 0;
      if (a == null) return 1;                                  // unknowns last, whichever way
      if (b == null) return -1;
      return dir === "desc" ? b - a : a - b;
    });
  const click = (c) => setSort({ key: c, dir: c === key && dir === "desc" ? "asc" : "desc" });
  const team_ = { home: d.home, away: d.away };
  return (
    <section className="mst-players" aria-labelledby="mst-players-h" data-testid="stats-players">
      <h3 className="k-sec" id="mst-players-h">Players</h3>
      <div className="mst-ctl">
        <Seg label="Team" value={team} onChange={setTeam} testid="stats-team"
          options={[{ id: "both", label: "Both" }, { id: "home", label: d.home.name }, { id: "away", label: d.away.name }]} />
        {sets.length > 1 && (
          <div className="mst-sets" role="group" aria-label="Columns" data-testid="stats-sets">
            {sets.map((s) => (
              <button key={s.id} type="button" className={`chip chip--sm${s.id === set.id ? " chip-on" : ""}`} aria-pressed={s.id === set.id}
                onClick={() => setSetId(s.id)} data-testid={`stats-set-${s.id}`}>{s.label}</button>
            ))}
          </div>
        )}
      </div>
      <div className="tbl-wrap mst-tbl" role="region" aria-labelledby="mst-players-h" tabIndex={0}>
        <table className="tbl" data-testid="stats-players-table">
          <caption className="sr-only">Player numbers for this match, {set.label.toLowerCase()}. Column headers sort the table.</caption>
          <thead><tr>
            <th scope="col" className="sticky">Player</th>
            {set.cols.map((c) => (
              <th key={c} scope="col" className="num" aria-sort={c === key ? (dir === "desc" ? "descending" : "ascending") : "none"}>
                <button type="button" className={`mst-sort${c === key ? " is-on" : ""}`} onClick={() => click(c)} title={COLS[c].title} data-testid={`stats-sort-${c}`}>
                  <span aria-hidden="true">{COLS[c].label}</span><span className="sr-only">{COLS[c].title}</span>
                  <svg className="mst-sort-ico" viewBox="0 0 10 10" width="10" height="10" aria-hidden="true">
                    {c === key ? <path d={dir === "desc" ? "M2 3.5 5 7l3-3.5" : "M2 6.5 5 3l3 3.5"} /> : <path d="M3 4 5 2l2 2M3 6l2 2 2-2" />}
                  </svg>
                </button>
              </th>
            ))}
          </tr></thead>
          <tbody>{shown.map((r) => (
            <tr key={`${r.side}-${r.player?.id || r.player?.name}`}>
              <th scope="row" className="sticky">
                {r.player?.id ? (
                  <Link className="cell-person mst-who" to={`/player/${r.player.id}`}>
                    <PlayerAvatar player={r.player} size={28} />
                    <span className="mst-name"><b>{r.player?.name}</b><small className="muted">{team === "both" && <Crest team={team_[r.side]} size={12} />}{posLabel(r.pos || r.player?.pos)}{r.started === false ? " · sub" : ""}</small></span>
                  </Link>
                ) : <span className="mst-who"><b>{r.player?.name || "Unknown"}</b></span>}
              </th>
              {set.cols.map((c) => (
                <td key={c} className={`num${c === key ? " is-key" : ""}`}>
                  {c === "rating" ? (r.rating == null ? "–" : <RatingBadge value={r.rating} />) : COLS[c].fmt(r[c])}
                </td>
              ))}
            </tr>
          ))}</tbody>
        </table>
      </div>
      {!shown.length && <p className="muted small">No players in this view.</p>}
    </section>
  );
}

// ------------------------------------------------------------------ the tab
export default function MatchStats({ d }) {
  const ts = d.team_stats;
  const H = ts?.home || {}, A = ts?.away || {};
  const names = { home: d.home.name, away: d.away.name };
  const groups = GROUPS.map((g) => ({ ...g, rows: g.rows.filter(([k]) => H[k] != null || A[k] != null) })).filter((g) => g.rows.length);
  return (
    <div className="mst" data-testid="match-stats">
      {ts && (
        <section className="mst-team" aria-label="Team statistics" data-testid="stats-team-block">
          <div className="mst-heads" aria-hidden="true">
            <span className="mst-head mst-head--home"><Crest team={d.home} size={20} /><b>{d.home.name}</b></span>
            <span className="mst-head mst-head--away"><b>{d.away.name}</b><Crest team={d.away} size={20} /></span>
          </div>
          <Possession h={H.poss} a={A.poss} {...names} />
          {groups.map((g) => (
            <section key={g.id} className="mst-group" aria-labelledby={`mst-g-${g.id}`} data-testid={`stats-group-${g.id}`}>
              <h3 className="mst-group-h" id={`mst-g-${g.id}`}>{g.title}</h3>
              <ul className="mst-rows">{g.rows.map(([k, label, fmt]) => <PairRow key={k} label={label} h={H[k]} a={A[k]} fmt={fmt} {...names} />)}</ul>
            </section>
          ))}
          {!groups.length && H.poss == null && A.poss == null && <Empty icon="activity" testid="stats-team-empty">The team numbers for this match have not arrived.</Empty>}
        </section>
      )}
      <PlayerTable d={d} />
    </div>
  );
}
