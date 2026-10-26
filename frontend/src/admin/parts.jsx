// Shared admin parts (docs/17 §8): page head, responsive table (table >=1025 px, cards below), stat tile, bar chart
// with a text table behind "Show table", pager, chips, key/value view.
import { useEffect, useState } from "react";
import { utc } from "../lib/time";
import Icon from "../components/Icon";
import { Empty, ErrorBox, Loading } from "../components/States";

export function useWide(q = "(min-width: 1025px)") {
  const [wide, setWide] = useState(() => window.matchMedia(q).matches);
  useEffect(() => {
    const mq = window.matchMedia(q);
    const h = () => setWide(mq.matches);
    mq.addEventListener("change", h);
    return () => mq.removeEventListener("change", h);
  }, [q]);
  return wide;
}

export const when = (s) => (s ? utc(s).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" }) : "No data");
export const num = (n) => (n === null || n === undefined ? "No data" : typeof n === "number" ? n.toLocaleString() : String(n));

export function PageHead({ title, lead, actions, testid }) {
  return (
    <header className="a-head" data-testid={testid}>
      <div><h1>{title}</h1>{lead && <p className="a-lead">{lead}</p>}</div>
      {actions && <div className="a-head-actions">{actions}</div>}
    </header>
  );
}

export function Chip({ children, tone = "muted", testid }) {
  return <span className={"a-chip a-chip--" + tone} data-testid={testid}>{children}</span>;
}

export function StatTile({ label, value, sub, tone, testid }) {
  return (
    <div className={"a-tile" + (tone ? " a-tile--" + tone : "")} data-testid={testid}>
      <span className="a-tile-label">{label}</span>
      <strong className="a-tile-value">{value}</strong>
      {sub && <span className="a-tile-sub">{sub}</span>}
    </div>
  );
}

export function Bars({ title, data = [], x = "day", y = "count", testid }) {
  const [table, setTable] = useState(false);
  const max = Math.max(1, ...data.map((d) => d[y] || 0));
  const total = data.reduce((a, d) => a + (d[y] || 0), 0);
  return (
    <figure className="a-card a-chart" data-testid={testid}>
      <figcaption><span>{title}</span><button className="a-link-btn" onClick={() => setTable((t) => !t)} data-testid={`${testid}-toggle`}>{table ? "Show chart" : "Show table"}</button></figcaption>
      <p className="a-chart-total">{total.toLocaleString()} <small>in {data.length} days</small></p>
      {table ? (
        <div className="a-scroll-y"><table className="a-mini-table"><tbody>{data.map((d) => <tr key={d[x]}><td>{d[x]}</td><td>{d[y]}</td></tr>)}</tbody></table></div>
      ) : (
        <div className="a-bars" role="img" aria-label={`${title}: ${total} in ${data.length} days, highest ${max} in a day`}>
          {data.map((d) => <span key={d[x]} style={{ height: `${Math.max(3, ((d[y] || 0) / max) * 100)}%` }} title={`${d[x]}: ${d[y]}`} />)}
        </div>
      )}
    </figure>
  );
}

// One column definition: {label, key, primary?, render?}
export function ResponsiveTable({ columns, rows, onRow, testid = "table", rowKey = (r) => r.id }) {
  const wide = useWide();
  if (wide) {
    return (
      <div className="a-table-wrap">
        <table className="a-table" data-testid={testid}>
          <thead><tr>{columns.map((c) => <th key={c.key} scope="col">{c.label}</th>)}</tr></thead>
          <tbody>
            {rows.map((r) => (
              <tr key={rowKey(r)} onClick={onRow ? () => onRow(r) : undefined} className={onRow ? "is-click" : ""} data-testid={`${testid}-row-${rowKey(r)}`}
                  tabIndex={onRow ? 0 : undefined} onKeyDown={onRow ? (e) => e.key === "Enter" && onRow(r) : undefined}>
                {columns.map((c) => <td key={c.key}>{c.render ? c.render(r) : num(r[c.key])}</td>)}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    );
  }
  const primary = columns.find((c) => c.primary) || columns[0];
  return (
    <ul className="a-cards" data-testid={testid}>
      {rows.map((r) => (
        <li key={rowKey(r)}>
          <button type="button" className="a-rowcard" onClick={onRow ? () => onRow(r) : undefined} disabled={!onRow} data-testid={`${testid}-row-${rowKey(r)}`}>
            <strong>{primary.render ? primary.render(r) : num(r[primary.key])}</strong>
            <span className="a-rowcard-chips">
              {columns.filter((c) => c !== primary).map((c) => <span key={c.key} className="a-kv"><em>{c.label}</em>{c.render ? c.render(r) : num(r[c.key])}</span>)}
            </span>
            {onRow && <Icon name="chevron-right" size={18} className="a-rowcard-go" />}
          </button>
        </li>
      ))}
    </ul>
  );
}

export function DataState({ q, empty = "Nothing here yet.", children }) {
  if (q.loading && !q.data) return <Loading />;
  if (q.error) return <ErrorBox error={q.error} onRetry={q.reload} />;
  const rows = q.data?.rows;
  if (Array.isArray(rows) && rows.length === 0) return <Empty>{empty}</Empty>;
  return children(q.data);
}

export function Pager({ page, limit, total, onPage }) {
  const pages = Math.max(1, Math.ceil((total || 0) / (limit || 25)));
  if (pages <= 1) return null;
  return (
    <nav className="a-pager" aria-label="Pages" data-testid="pager">
      <button className="btn btn--secondary btn--sm" disabled={page <= 1} onClick={() => onPage(page - 1)} data-testid="pager-prev"><Icon name="chevron-left" size={16} />Previous</button>
      <span>Page {page} of {pages}</span>
      <button className="btn btn--secondary btn--sm" disabled={page >= pages} onClick={() => onPage(page + 1)} data-testid="pager-next">Next<Icon name="chevron-right" size={16} /></button>
    </nav>
  );
}

const show = (v) => (v === null || v === undefined || v === "" ? "No data" : typeof v === "object" ? JSON.stringify(v) : /^\d{4}-\d\d-\d\dT/.test(String(v)) ? when(v) : String(v));
export function KV({ obj, skip = [] }) {
  return (
    <dl className="a-dl">
      {Object.entries(obj || {}).filter(([k]) => !skip.includes(k)).map(([k, v]) => <div key={k}><dt>{k.replace(/_/g, " ")}</dt><dd>{show(v)}</dd></div>)}
    </dl>
  );
}

export function Card({ title, children, actions, testid, className = "" }) {
  return (
    <section className={"a-card " + className} data-testid={testid}>
      {(title || actions) && <header className="a-card-head">{title && <h2>{title}</h2>}{actions}</header>}
      {children}
    </section>
  );
}
