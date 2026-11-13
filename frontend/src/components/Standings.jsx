// League table (docs/24 §7): built from the finished matches we already store. 3 points a win, 1 a draw.
import { useEffect, useRef } from "react";
import { Link } from "react-router-dom";
import { useApi } from "../lib/useApi";
import { Crest } from "./Media";
import { EmptyState, ErrorState, Skeleton } from "./ui";

export function build(rows) {
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

// The rows a phone shows around the clubs in `hl` (the match page's two): the six around them when
// they sit close, else each club with its neighbours either side. A Set of table indexes.
function near(rows, hl, n = 6) {
  const at = rows.map((r, i) => (hl.includes(r.team.id) ? i : -1)).filter((i) => i >= 0);
  if (!at.length) return new Set(rows.slice(0, n).map((_, i) => i));
  const lo = Math.min(...at), hi = Math.max(...at);
  if (hi - lo < n - 1) {
    const start = Math.max(0, Math.min(lo - Math.floor((n - 1 - (hi - lo)) / 2), rows.length - n));
    return new Set(Array.from({ length: Math.min(n, rows.length) }, (_, k) => start + k));
  }
  return new Set(at.flatMap((i) => [i - 1, i, i + 1]).filter((i) => i >= 0 && i < rows.length));
}

// The match page's sidebar table: position, club, played, goal difference, points, with both clubs
// marked. Every row is rendered; a phone hides the far ones (`st-far`, matchside.css) and the desktop
// sidebar scrolls the whole table inside its card, opened at the first marked club.
function Compact({ rows, hl }) {
  const box = useRef(null);
  const keep = near(rows, hl);
  useEffect(() => {
    const el = box.current, row = el?.querySelector("tr.is-hl");
    if (el && row && el.scrollHeight > el.clientHeight) el.scrollTop = Math.max(0, row.offsetTop - 44 * 2);
  }, [rows.length]);
  let prev = -1;
  return (
    <div className="st-compact" ref={box} data-testid="league-table">
      <table className="st-ctbl">
        <caption className="sr-only">League table from finished matches this season</caption>
        <thead><tr><th scope="col">#</th><th scope="col" className="st-c-club">Club</th><th scope="col"><abbr title="Played">P</abbr></th><th scope="col"><abbr title="Goal difference">GD</abbr></th><th scope="col"><abbr title="Points">Pts</abbr></th></tr></thead>
        <tbody>{rows.map((r, i) => {
          const on = hl.includes(r.team.id), far = !keep.has(i), gap = !far && prev >= 0 && i - prev > 1;
          if (!far) prev = i;
          return (
            <tr key={r.team.id} className={`${on ? "is-hl" : ""}${far ? " st-far" : ""}${gap ? " st-gap" : ""}`.trim() || undefined} aria-current={on ? "true" : undefined} data-testid={`table-row-${r.team.id}`}>
              <td>{i + 1}</td>
              <th scope="row" className="st-c-club"><Link to={`/team/${r.team.id}`}><Crest team={r.team} size={18} /><span>{r.team.name}</span></Link></th>
              <td>{r.p}</td><td>{r.gd > 0 ? `+${r.gd}` : r.gd}</td><td><b>{r.pts}</b></td>
            </tr>
          );
        })}</tbody>
      </table>
    </div>
  );
}

// `matches` lets a page that already holds the league's finished fixtures (the match page, for form
// as well) pass them in rather than asking the server twice.
export default function Standings({ id, season, zones = [], matches, compact = false, highlight = [] }) {
  const q = useApi(matches ? null : `/leagues/${id}/fixtures`, { status: "final", limit: 400 });
  const data = matches || q.data;
  if (!matches && q.loading && !q.data) return <Skeleton shape="row" count={compact ? 6 : 10} testid="table-loading" />;
  if (!matches && q.error) return <ErrorState message="We could not load the table." onRetry={q.reload} testid="table-error" />;
  const rows = build((data || []).filter((m) => !season || !m.season || m.season === season));
  if (!rows.length) return compact ? null : <EmptyState icon="list" title="No table yet" testid="table-empty">The table appears after the first finished round of the season.</EmptyState>;
  if (compact) return <Compact rows={rows} hl={highlight} />;
  return (
    <div className="tm-scroll" data-testid="league-table">
      <table className="tm-grid st-table">
        <caption className="sr-only">League table from finished matches this season</caption>
        <thead><tr><th scope="col">#</th><th scope="col" className="tm-sticky">Club</th><th scope="col">P</th><th scope="col" className="st-wdl">W</th><th scope="col" className="st-wdl">D</th><th scope="col" className="st-wdl">L</th><th scope="col">GD</th><th scope="col">Pts</th><th scope="col">Form</th></tr></thead>
        <tbody>{rows.map((r, i) => { const z = zones.find((x) => i + 1 >= x.start && i + 1 <= x.end); return (
          <tr key={r.team.id} className={z ? `st-zone st-zone--${z.tone}` : undefined} title={z?.label} data-testid={`table-row-${r.team.id}`}>
            <td>{i + 1}</td>
            <th scope="row" className="tm-sticky"><Link to={`/team/${r.team.id}`} className="tm-cell-team"><Crest team={r.team} size={22} />{r.team.name}</Link></th>
            <td>{r.p}</td><td className="st-wdl">{r.w}</td><td className="st-wdl">{r.d}</td><td className="st-wdl">{r.l}</td><td>{r.gd > 0 ? `+${r.gd}` : r.gd}</td><td><b>{r.pts}</b></td>
            <td><span className="st-form" aria-label={`Last results: ${r.form.join(", ")}`}>{r.form.map((k, j) => <i key={j} className={`st-${k}`}>{k}</i>)}</span></td>
          </tr>
        ); })}</tbody>
      </table>
      {zones.length > 0 && <ul className="st-legend" data-testid="table-zones">{zones.map((z) => <li key={`${z.start}-${z.label}`} className={`st-zone--${z.tone}`}><i aria-hidden="true" />{z.label} ({z.start === z.end ? z.start : `${z.start}–${z.end}`})</li>)}</ul>}
    </div>
  );
}
