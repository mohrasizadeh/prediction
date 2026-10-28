// League table (docs/24 §7): built from the finished matches we already store. 3 points a win, 1 a draw.
import { Link } from "react-router-dom";
import { useApi } from "../lib/useApi";
import { Crest } from "./Media";
import { EmptyState, ErrorState, Skeleton } from "./ui";

function build(rows) {
  const t = new Map();
  const get = (team) => { if (!t.has(team.id)) t.set(team.id, { team, p: 0, w: 0, d: 0, l: 0, gf: 0, ga: 0, form: [] }); return t.get(team.id); };
  [...rows].sort((a, b) => new Date(a.kickoff) - new Date(b.kickoff)).forEach((m) => {
    if (m.hg == null || !m.home || !m.away) return;
    const h = get(m.home), a = get(m.away);
    h.p++; a.p++; h.gf += m.hg; h.ga += m.ag; a.gf += m.ag; a.ga += m.hg;
    const r = m.hg > m.ag ? ["W", "L"] : m.hg < m.ag ? ["L", "W"] : ["D", "D"];
    [[h, r[0]], [a, r[1]]].forEach(([x, k]) => { x[k === "W" ? "w" : k === "D" ? "d" : "l"]++; x.form.push(k); });
  });
  return [...t.values()].map((x) => ({ ...x, pts: x.w * 3 + x.d, gd: x.gf - x.ga, form: x.form.slice(-5) }))
    .sort((a, b) => b.pts - a.pts || b.gd - a.gd || b.gf - a.gf || a.team.name.localeCompare(b.team.name));
}

export default function Standings({ id, season, zones = [] }) {
  const q = useApi(`/leagues/${id}/fixtures`, { status: "final", limit: 400 });
  if (q.loading && !q.data) return <Skeleton shape="row" count={10} testid="table-loading" />;
  if (q.error) return <ErrorState message="We could not load the table." onRetry={q.reload} testid="table-error" />;
  const rows = build((q.data || []).filter((m) => !season || !m.season || m.season === season));
  if (!rows.length) return <EmptyState icon="list" title="No table yet" testid="table-empty">The table appears after the first finished round of the season.</EmptyState>;
  return (
    <div className="tm-scroll" data-testid="league-table">
      <table className="tm-grid st-table">
        <caption className="sr-only">League table from finished matches this season</caption>
        <thead><tr><th scope="col">#</th><th scope="col" className="tm-sticky">Club</th><th scope="col">P</th><th scope="col">W</th><th scope="col">D</th><th scope="col">L</th><th scope="col">GD</th><th scope="col">Pts</th><th scope="col">Form</th></tr></thead>
        <tbody>{rows.map((r, i) => { const z = zones.find((x) => i + 1 >= x.start && i + 1 <= x.end); return (
          <tr key={r.team.id} className={z ? `st-zone st-zone--${z.tone}` : undefined} title={z?.label} data-testid={`table-row-${r.team.id}`}>
            <td>{i + 1}</td>
            <th scope="row" className="tm-sticky"><Link to={`/team/${r.team.id}`} className="tm-cell-team"><Crest team={r.team} size={22} />{r.team.name}</Link></th>
            <td>{r.p}</td><td>{r.w}</td><td>{r.d}</td><td>{r.l}</td><td>{r.gd > 0 ? `+${r.gd}` : r.gd}</td><td><b>{r.pts}</b></td>
            <td><span className="st-form" aria-label={`Last results: ${r.form.join(", ")}`}>{r.form.map((k, j) => <i key={j} className={`st-${k}`}>{k}</i>)}</span></td>
          </tr>
        ); })}</tbody>
      </table>
      {zones.length > 0 && <ul className="st-legend" data-testid="table-zones">{zones.map((z) => <li key={`${z.start}-${z.label}`} className={`st-zone--${z.tone}`}><i aria-hidden="true" />{z.label} ({z.start === z.end ? z.start : `${z.start}–${z.end}`})</li>)}</ul>}
    </div>
  );
}
