// League table (docs/24 §7), drawn the way the competition runs (backend/standings.py): one table,
// several groups (Nations League tiers, World Cup groups), knockout rounds, or no table at all. Only a
// plain league the provider has no standings for yet falls back to a table built from our results --
// that fallback is what used to put every Nations League side into one ranking.
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

// A club the provider lists in a table that we never ingested (a group opponent from a league we do
// not carry) still gets its row, just without a link to a page we do not have.
const TeamLink = ({ team, children, className }) => (team?.id ? <Link to={`/team/${team.id}`} className={className}>{children}</Link> : <span className={className}>{children}</span>);

// The provider's own note on a row ("Promotion - Champions League (Group Stage)", "Relegation",
// "Next round") as one of the three zone tones the table already draws.
const toneOf = (desc = "") => (/relegat|demot/i.test(desc) ? "bottom" : /promot|champions|qualif|next round|knockout|round of|play-?off|final|europa|conference|libertadores|sudamericana/i.test(desc) ? "top" : "mid");

const CUPS = new Set(["cup", "continental", "international"]);

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
function Compact({ rows, hl, caption = "League table from finished matches this season", title }) {
  const box = useRef(null);
  const keep = near(rows, hl);
  useEffect(() => {
    const el = box.current, row = el?.querySelector("tr.is-hl");
    if (el && row && el.scrollHeight > el.clientHeight) el.scrollTop = Math.max(0, row.offsetTop - 44 * 2);
  }, [rows.length]);
  let prev = -1;
  return (
    <div className="st-compact" ref={box} data-testid="league-table">
      {title && <p className="st-group-name st-group-name--compact" data-testid="league-table-group">{title}</p>}
      <table className="st-ctbl">
        <caption className="sr-only">{caption}</caption>
        <thead><tr><th scope="col">#</th><th scope="col" className="st-c-club">Club</th><th scope="col"><abbr title="Played">P</abbr></th><th scope="col"><abbr title="Goal difference">GD</abbr></th><th scope="col"><abbr title="Points">Pts</abbr></th></tr></thead>
        <tbody>{rows.map((r, i) => {
          const on = hl.includes(r.team.id), far = !keep.has(i), gap = !far && prev >= 0 && i - prev > 1;
          if (!far) prev = i;
          return (
            <tr key={r.team.id || r.team.name} className={`${on ? "is-hl" : ""}${far ? " st-far" : ""}${gap ? " st-gap" : ""}`.trim() || undefined} aria-current={on ? "true" : undefined} data-testid={`table-row-${r.team.id}`}>
              <td>{r.rank || i + 1}</td>
              <th scope="row" className="st-c-club"><TeamLink team={r.team}><Crest team={r.team} size={18} /><span>{r.team.name}</span></TeamLink></th>
              <td>{r.p}</td><td>{r.gd > 0 ? `+${r.gd}` : r.gd}</td><td><b>{r.pts}</b></td>
            </tr>
          );
        })}</tbody>
      </table>
    </div>
  );
}

function FullTable({ rows, zones = [], caption, provider }) {
  // Admin zones are positions in ONE table; a group table colours from the provider's own row notes.
  const zoneOf = (r, i) => (provider ? (r.description ? { tone: toneOf(r.description), label: r.description } : null) : zones.find((x) => i + 1 >= x.start && i + 1 <= x.end));
  const legend = provider ? [...new Map(rows.filter((r) => r.description).map((r) => [r.description, { label: r.description, tone: toneOf(r.description) }])).values()] : zones;
  return (
    <>
      <table className="tm-grid st-table">
        <caption className="sr-only">{caption}</caption>
        <thead><tr><th scope="col">#</th><th scope="col" className="tm-sticky">Club</th><th scope="col">P</th><th scope="col" className="st-wdl">W</th><th scope="col" className="st-wdl">D</th><th scope="col" className="st-wdl">L</th><th scope="col">GD</th><th scope="col">Pts</th><th scope="col">Form</th></tr></thead>
        <tbody>{rows.map((r, i) => { const z = zoneOf(r, i); const form = Array.isArray(r.form) ? r.form : [...(r.form || "")]; return (
          <tr key={r.team.id || r.team.name} className={z ? `st-zone st-zone--${z.tone}` : undefined} title={z?.label} data-testid={`table-row-${r.team.id || r.team.name}`}>
            <td>{r.rank || i + 1}</td>
            <th scope="row" className="tm-sticky"><TeamLink team={r.team} className="tm-cell-team"><Crest team={r.team} size={22} />{r.team.name}</TeamLink></th>
            <td>{r.p ?? "–"}</td><td className="st-wdl">{r.w ?? "–"}</td><td className="st-wdl">{r.d ?? "–"}</td><td className="st-wdl">{r.l ?? "–"}</td><td>{r.gd > 0 ? `+${r.gd}` : r.gd ?? "–"}</td><td><b>{r.pts ?? "–"}</b></td>
            <td><span className="st-form" aria-label={`Last results: ${form.join(", ")}`}>{form.map((k, j) => <i key={j} className={`st-${k}`}>{k}</i>)}</span></td>
          </tr>
        ); })}</tbody>
      </table>
      {legend.length > 0 && <ul className="st-legend" data-testid="table-zones">{legend.map((z) => <li key={`${z.start || ""}-${z.label}`} className={`st-zone--${z.tone}`}><i aria-hidden="true" />{z.label}{z.start ? ` (${z.start === z.end ? z.start : `${z.start}–${z.end}`})` : ""}</li>)}</ul>}
    </>
  );
}

const score = (m) => (m.hg == null ? "v" : `${m.hg}–${m.ag}${m.pen_home != null ? ` (${m.pen_home}–${m.pen_away} pens)` : ""}`);

function Rounds({ rounds }) {
  return (
    <div className="st-rounds" data-testid="table-rounds">
      {[...rounds].reverse().map((r) => (
        <section key={r.name} className="st-round" data-testid="table-round">
          <h3 className="st-group-name">{r.name}</h3>
          <ul className="st-ties">{r.matches.map((m, i) => (
            <li key={m.id || i}>
              <Link to={m.id ? `/match/${m.id}` : "#"} className="st-tie">
                <span className="st-tie-team"><Crest team={m.home} size={20} />{m.home?.name}</span>
                <b className="st-tie-score">{score(m)}</b>
                <span className="st-tie-team st-tie-team--a">{m.away?.name}<Crest team={m.away} size={20} /></span>
              </Link>
            </li>
          ))}</ul>
        </section>
      ))}
    </div>
  );
}

// `matches` lets a page that already holds the league's finished fixtures (the match page, for form
// as well) pass them in, for the one case that still builds a table from results.
export default function Standings({ id, season, zones = [], matches, compact = false, highlight = [] }) {
  const sq = useApi(`/leagues/${id}/standings`, season ? { season } : undefined);
  const s = sq.data;
  const results = !s ? false : !s.groups?.length && !(s.rounds?.length) && !CUPS.has(s.kind);
  const q = useApi(results && !matches ? `/leagues/${id}/fixtures` : null, { status: "final", limit: 400 });
  if (sq.loading && !s) return <Skeleton shape="row" count={compact ? 6 : 10} testid="table-loading" />;
  if (sq.error) return compact ? null : <ErrorState message="We could not load the table." onRetry={sq.reload} testid="table-error" />;

  if (s.groups?.length) {
    const many = s.groups.length > 1;
    if (compact) {
      // The match page shows the group these two clubs are in, not the first group of the competition.
      const g = s.groups.find((x) => x.rows.some((r) => highlight.includes(r.team.id))) || (many ? null : s.groups[0]);
      return g ? <Compact rows={g.rows} hl={highlight} title={many ? g.name : null} caption={many ? g.name : "League table"} /> : null;
    }
    return (
      <div className="st-wrap" data-testid="league-standings" data-format={s.format}>
        {s.groups.map((g) => (
          <section key={g.name || "table"} className="st-group" data-testid={many ? "table-group" : "league-table"}>
            {many && <h3 className="st-group-name">{g.name}</h3>}
            <div className="tm-scroll"><FullTable rows={g.rows} provider caption={g.name || "League table"} /></div>
          </section>
        ))}
        {s.rounds?.length > 0 && <><h2 className="k-sec st-ko-head">Knockout rounds</h2><Rounds rounds={s.rounds} /></>}
      </div>
    );
  }
  if (s.rounds?.length) {
    if (compact) return null;
    return <div className="st-wrap" data-testid="league-standings" data-format="knockout"><p className="k-faint k-small">A knockout competition: no table, round by round instead.</p><Rounds rounds={s.rounds} /></div>;
  }
  if (!results) return compact ? null : <EmptyState icon="list" title="No table for this competition" testid="table-none">It is not played as a league, and the rounds will show here once its fixtures are in.</EmptyState>;

  const data = matches || q.data;
  if (!matches && q.loading && !q.data) return <Skeleton shape="row" count={compact ? 6 : 10} testid="table-loading" />;
  if (!matches && q.error) return <ErrorState message="We could not load the table." onRetry={q.reload} testid="table-error" />;
  const rows = build((data || []).filter((m) => !season || !m.season || m.season === season));
  if (!rows.length) return compact ? null : <EmptyState icon="list" title="No table yet" testid="table-empty">The table appears after the first finished round of the season.</EmptyState>;
  if (compact) return <Compact rows={rows} hl={highlight} />;
  return <div className="tm-scroll" data-testid="league-table"><FullTable rows={rows} zones={zones} caption="League table from finished matches this season" /></div>;
}
