// League Teams tab (update pack part A, docs/24 §7): every club side by side. Phones: one stat as ranked bars,
// the full heat-map behind "Show all stats". Tick two clubs and the Compare tray appears.
import { useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useApi } from "../lib/useApi";
import { Crest } from "./Media";
import { ChipsRow, EmptyState, ErrorState, Segmented, Skeleton } from "./ui";

const WINDOWS = [{ id: "season", label: "Season" }, { id: "last10", label: "Last 10" }, { id: "last5", label: "Last 5" }];
const VENUES = [{ id: "all", label: "All" }, { id: "home", label: "Home" }, { id: "away", label: "Away" }];
const fmt = (v) => (v == null ? "–" : Number.isInteger(v) ? v : v.toFixed(1));
const good = (s, p) => (p == null ? 0 : s.better === "low" ? 1 - p : p);

function Ranked({ d, stat, picked, toggle }) {
  const s = d.stats.find((x) => x.key === stat);
  const rows = [...d.teams].filter((t) => t.values[stat] != null).sort((a, b) => (s.better === "low" ? a.values[stat] - b.values[stat] : b.values[stat] - a.values[stat]));
  const max = Math.max(...rows.map((t) => t.values[stat]), 0.01);
  return (
    <ol className="tm-rank" data-testid="team-matrix-ranked" aria-label={`${s.label}, per game, ${s.better === "low" ? "fewest" : "most"} first`}>
      {rows.map((t, i) => (
        <li key={t.team.id} className={picked.includes(t.team.id) ? "on" : ""}>
          <span className="tm-n">{i + 1}</span>
          <label className="tm-tick"><input type="checkbox" checked={picked.includes(t.team.id)} onChange={() => toggle(t.team.id)} aria-label={`Pick ${t.team.name} to compare`} data-testid={`team-pick-${t.team.id}`} /></label>
          <Link to={`/team/${t.team.id}`} className="tm-team"><Crest team={t.team} size={24} /><span>{t.team.name}</span></Link>
          <span className="tm-bar" aria-hidden="true"><b style={{ width: `${(t.values[stat] / max) * 100}%` }} /></span>
          <b className="tm-v">{fmt(t.values[stat])}</b>
        </li>
      ))}
    </ol>
  );
}

function Grid({ d, picked, toggle }) {
  const [sort, setSort] = useState(null);
  const rows = useMemo(() => {
    if (!sort) return d.teams;
    const s = d.stats.find((x) => x.key === sort);
    const low = s.better === "low";
    return [...d.teams].sort((a, b) => { const x = a.values[sort], y = b.values[sort]; if (x == null) return 1; if (y == null) return -1; return low ? x - y : y - x; });
  }, [d, sort]);
  return (
    <div className="tm-scroll" data-testid="team-matrix-grid">
      <table className="tm-grid">
        <thead><tr><th scope="col" className="tm-sticky">Club</th><th scope="col">Games</th>
          {d.stats.map((s) => <th key={s.key} scope="col"><button type="button" className="tm-sort" aria-pressed={sort === s.key} onClick={() => setSort(sort === s.key ? null : s.key)} data-testid={`team-matrix-sort-${s.key}`}>{s.label}</button></th>)}
        </tr></thead>
        <tbody>{rows.map((t) => (
          <tr key={t.team.id} className={picked.includes(t.team.id) ? "on" : ""}>
            <th scope="row" className="tm-sticky"><span className="tm-cell-team">
              <input type="checkbox" checked={picked.includes(t.team.id)} onChange={() => toggle(t.team.id)} aria-label={`Pick ${t.team.name} to compare`} data-testid={`team-grid-pick-${t.team.id}`} />
              <Link to={`/team/${t.team.id}`}><Crest team={t.team} size={22} />{t.team.name}</Link></span></th>
            <td>{t.games}</td>
            {d.stats.map((s) => <td key={s.key} className="tm-heat" style={{ "--h": good(s, t.pct[s.key]) }}>{fmt(t.values[s.key])}</td>)}
          </tr>
        ))}</tbody>
      </table>
    </div>
  );
}

export default function TeamMatrix({ leagueId }) {
  const [window, setWindow] = useState("season");
  const [venue, setVenue] = useState("all");
  const [stat, setStat] = useState("shots");
  const [all, setAll] = useState(false);
  const [picked, setPicked] = useState([]);
  const nav = useNavigate();
  const q = useApi(`/leagues/${leagueId}/team-matrix`, { window, venue });
  const toggle = (id) => setPicked((p) => (p.includes(id) ? p.filter((x) => x !== id) : [...p.slice(-1), id]));
  const d = q.data;
  return (
    <section className="tm" data-testid="team-matrix">
      <div className="tm-controls">
        <Segmented options={WINDOWS} value={window} onChange={setWindow} label="Games" testid="team-matrix-window" />
        <Segmented options={VENUES} value={venue} onChange={setVenue} label="Venue" testid="team-matrix-venue" />
      </div>
      {q.loading && !d ? <Skeleton shape="row" count={8} testid="team-matrix-loading" /> : q.error && !d ? <ErrorState message="We could not load the clubs." onRetry={q.reload} testid="team-matrix-error" /> : !d.teams.length ? (
        <EmptyState icon="shield" title="No finished matches yet" testid="team-matrix-empty">Club numbers appear after the first round of this season is played. Try the Fixtures tab for what is next.</EmptyState>
      ) : (
        <>
          <p className="tm-legend" aria-hidden="true"><span>Weaker</span><i /><span>Stronger (fewest for "against" numbers)</span></p>
          <p className="sr-only">Per game averages. Darker cells are the better end of the league for that number.</p>
          <div className={all ? "tm-phone-hide" : "tm-phone"}>
            <ChipsRow options={d.stats.map((s) => ({ id: s.key, label: s.label }))} value={stat} onChange={setStat} label="Pick a stat" testid="team-matrix-stat" />
            <Ranked d={d} stat={stat} picked={picked} toggle={toggle} />
            <button type="button" className="btn btn--secondary tm-all" onClick={() => { setAll(true); setTimeout(() => document.querySelector('[data-testid="team-matrix-grid"]')?.scrollIntoView({ block: "start" }), 50); }} data-testid="team-matrix-show-all">Show all stats</button>
          </div>
          <div className={all ? "tm-desk tm-desk--forced" : "tm-desk"}>
            {all && <button type="button" className="k-link tm-back" onClick={() => setAll(false)} data-testid="team-matrix-show-one">Back to one stat</button>}
            <Grid d={d} picked={picked} toggle={toggle} />
          </div>
        </>
      )}
      {picked.length > 0 && (
        <div className="tm-tray" role="region" aria-label="Compare tray" data-testid="compare-tray">
          <span>{picked.length} selected</span>
          <button type="button" className="k-link" onClick={() => setPicked([])} data-testid="compare-tray-clear">Clear</button>
          <button type="button" className="btn btn--primary btn--sm" disabled={picked.length < 2} onClick={() => nav(`/compare?a=${picked[0]}&b=${picked[1]}`)} data-testid="compare-tray-go">{picked.length < 2 ? "Pick one more" : "Compare"}</button>
        </div>
      )}
    </section>
  );
}
