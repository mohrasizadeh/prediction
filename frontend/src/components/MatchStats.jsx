// Match page: what each side did. Two sources, one set of bars:
//   * while the match is on, `live_stats` -- the team numbers the live tick stored (queries._live_stats),
//     refreshed by the page's own 30-second poll, with how old they are printed beside them; drawn on
//     the Live tab under the timeline;
//   * after full time, `team_stats` and `player_stats` (queries._match_stats), drawn on the Facts tab:
//     the team block, then every player's numbers.
// There used to be a Stats tab for these, beside a Facts tab whose "Top stats" were five of the same
// rows: the owner could not tell the two apart (round 4), so the numbers now live on the one tab that
// tells the match, and nowhere else.
// Possession as two figures over one split bar, then grouped paired bars, then the player table.
//
// A value the provider did not send is null and prints "–": a 0 would be a claim we do not hold. A row
// where neither side has a number says nothing, so it is left out, and a group with no rows goes with it.
// The provider's match rating exists only on API-Football data; without one the rating column and the
// pitch badge are not drawn at all. There is no live player table: the endpoint sends no live player rows.
//
// Drawn in the locked v10 vocabulary (docs/redesign/v10): a 16px-radius card with a 1px border and 16px
// padding, uppercase micro-labels, tabular figures with a small unit, 44px targets 8px apart.
import { useEffect, useMemo, useState } from "react";
import { utc } from "../lib/time";
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

export function PairRow({ label, h, a, fmt, home, away }) {
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

export function Possession({ h, a, home, away }) {
  if (h == null && a == null) return null;
  const tot = (h ?? 0) + (a ?? 0) || 1;
  // The two numbers are printed as the provider sent them; the bar splits on their share, so it always
  // fills even when the two do not add to exactly 100.
  const hp = h == null ? 0 : (h / tot) * 100;
  const fig = (v) => (v == null ? "–" : <>{Math.round(v)}<u>%</u></>);
  return (
    <section className="mst-poss mst-poss--fig" aria-labelledby="mst-poss-h" data-testid="stats-possession">
      <div className="mst-poss-top">
        <span className="mst-fig" aria-hidden="true">{fig(h)}</span>
        <h3 className="mst-micro" id="mst-poss-h">Ball possession</h3>
        <span className="mst-fig" aria-hidden="true">{fig(a)}</span>
      </div>
      <div className="mst-split" aria-hidden="true">
        <i className="mst-split-home" style={{ flexBasis: `${hp}%` }} />
        <i className="mst-split-away" style={{ flexBasis: `${100 - hp}%` }} />
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

export function PlayerTable({ d }) {
  const ps = d.player_stats;
  const rows = useMemo(() => ps || [], [ps]);
  // Only columns somebody in this match has a number for, and only sets that keep at least one of them.
  const has = useMemo(() => new Set(Object.keys(COLS).filter((c) => rows.some((r) => r[c] != null))), [rows]);
  const sets = SETS.map((s) => ({ ...s, cols: s.cols.filter((c) => has.has(c)) })).filter((s) => s.cols.length && (s.id !== "gk" || has.has("saves")));
  const [team, setTeam] = useState("both");
  const [setId, setSetId] = useState("top");
  const set = sets.find((s) => s.id === setId) || sets[0];
  const [sort, setSort] = useState(null);                     // { key, dir }; null = the set's natural order
  // On Facts the timeline and the team block already say the match; an empty players card under them
  // would only say that a feed did not send something, so it is left out.
  if (!rows.length || !set) return null;
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
      <h2 className="mst-micro" id="mst-players-h">Player stats</h2>
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
// "Updated n min ago" has to move on its own: the page polls every 30 seconds and a poll that fails
// keeps the last answer on screen, so a fixed label would go on claiming a fresh number.
function useNow(every = 30000) {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => { const t = setInterval(() => setNow(Date.now()), every); return () => clearInterval(t); }, [every]);
  return now;
}

function Updated({ at, lead }) {
  const now = useNow();
  const t = utc(at);
  const min = t ? Math.max(0, Math.floor((now - t.getTime()) / 60000)) : null;
  const ago = min == null ? null : min < 1 ? "updated just now" : min < 60 ? `updated ${min} min ago` : "updated over an hour ago";
  return (
    <p className={`mst-when${min != null && min >= 3 ? " is-old" : ""}`} data-testid="stats-updated">
      {lead === "Live" && <span className="live-dot" aria-hidden="true" />}
      <span>{lead}{ago ? ` · ${ago}` : ""}</span>
    </p>
  );
}

function TeamStats({ d, ts, mode }) {
  const H = ts?.home || {}, A = ts?.away || {};
  const names = { home: d.home.name, away: d.away.name };
  const groups = GROUPS.map((g) => ({ ...g, rows: g.rows.filter(([k]) => H[k] != null || A[k] != null) })).filter((g) => g.rows.length);
  return (
    <section className="mst-team" aria-labelledby="mst-team-h" data-testid="stats-team-block" data-mode={mode}>
      <header className="mst-cardhead">
        <h2 className="mst-micro" id="mst-team-h">Team stats</h2>
        {mode === "final" ? <p className="mst-when" data-testid="stats-updated">Full time</p>
          : <Updated at={ts.at} lead={mode === "live" ? "Live" : "From the match feed"} />}
      </header>
      <div className="mst-heads" aria-hidden="true">
        <span className="mst-head mst-head--home"><Crest team={d.home} size={20} /><b>{d.home.name}</b></span>
        <span className="mst-head mst-head--away"><b>{d.away.name}</b><Crest team={d.away} size={20} /></span>
      </div>
      <Possession h={H.poss} a={A.poss} {...names} />
      {groups.map((g) => (
        <section key={g.id} className="mst-group" aria-labelledby={`mst-g-${g.id}`} data-testid={`stats-group-${g.id}`}>
          <h3 className="mst-group-h mst-micro" id={`mst-g-${g.id}`}>{g.title}</h3>
          <ul className="mst-rows">{g.rows.map(([k, label, fmt]) => <PairRow key={k} label={label} h={H[k]} a={A[k]} fmt={fmt} {...names} />)}</ul>
        </section>
      ))}
      {!groups.length && H.poss == null && A.poss == null && <Empty icon="activity" testid="stats-team-empty">The team numbers for this match have not arrived.</Empty>}
    </section>
  );
}

// Which numbers the page draws: the stored full-time ones once they are in; until then, while the match
// is on (or just over, before the full-time numbers are ingested), the live feed's. null = none at all.
export const statsMode = (d) => (d?.match?.status === "final" && d.team_stats ? "final"
  : d?.live_stats && (d.live_stats.home || d.live_stats.away) ? (d.match?.status === "final" ? "feed" : "live") : null);

// The team block for whichever numbers exist (Live tab while on, Facts after), or nothing.
export function TeamBlock({ d }) {
  const mode = statsMode(d);
  if (!mode) return null;
  return (
    <>
      <TeamStats d={d} ts={mode === "final" ? d.team_stats : d.live_stats} mode={mode} />
      {mode === "live" && <p className="mst-note muted small" data-testid="stats-live-note">Numbers from the match feed. They refresh by themselves while the match is on; each player&rsquo;s numbers follow after full time.</p>}
    </>
  );
}
