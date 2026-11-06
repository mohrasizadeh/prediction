// Shared admin parts (docs/17 §8): page head, responsive table (table >=1025 px, cards below), stat tile, bar chart
// with a text table behind "Show table", pager, chips, key/value view.
import { useEffect, useState } from "react";
import { utc } from "../lib/time";
import Icon from "../components/Icon";
import { Empty, ErrorBox, Loading } from "../components/States";
import { Confirm } from "../components/Ui";

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

// API budget bar: calls today against the limit, split by kind, with the reset time (docs/24 Admin).
export function Budget({ used = 0, cap, reset, byKind, label, testid }) {
  const share = cap ? Math.min(100, Math.round((used / cap) * 100)) : 0;
  const tone = share >= 100 ? "red" : share >= 80 ? "amber" : "green";
  const kinds = Object.entries(byKind || {}).filter(([, v]) => v).map(([k, v]) => `${k} ${num(v)}`).join(" · ");
  const r = reset ? utc(reset).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }) : null;
  return (
    <span className="a-budget" data-testid={testid}>
      <span className="a-budget-bar" role="progressbar" aria-label={label} aria-valuenow={share} aria-valuemin={0} aria-valuemax={100}><i className={`is-${tone}`} style={{ width: `${share}%` }} /></span>
      {(kinds || r) && <small className="a-muted">{kinds}{kinds && r ? " · " : ""}{r ? `resets ${r}` : ""}</small>}
    </span>
  );
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
          {(() => { const Tag = onRow ? "button" : "div"; return (
          <Tag {...(onRow ? { type: "button", onClick: () => onRow(r) } : {})} className="a-rowcard" data-testid={`${testid}-row-${rowKey(r)}`}>
            <strong>{primary.render ? primary.render(r) : num(r[primary.key])}</strong>
            <span className="a-rowcard-chips">
              {columns.filter((c) => c !== primary).map((c) => (c.label
                ? <span key={c.key} className="a-kv"><em>{c.label}</em>{c.render ? c.render(r) : num(r[c.key])}</span>
                : <span key={c.key}>{c.render ? c.render(r) : num(r[c.key])}</span>))}
            </span>
            {onRow && <Icon name="chevron-right" size={18} className="a-rowcard-go" />}
          </Tag>); })()}
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

// Collapsible JSON viewer for raw API answers. Large arrays show the first 50 items.
export function JsonTree({ data, name = "data", depth = 0 }) {
  if (data === null || typeof data !== "object") {
    return <div className="a-jt-leaf"><span className="a-jt-key">{name}</span><span className={"a-jt-v a-jt-" + (data === null ? "null" : typeof data)}>{JSON.stringify(data)}</span></div>;
  }
  const entries = Array.isArray(data) ? data.slice(0, 50).map((v, i) => [i, v]) : Object.entries(data);
  const size = Array.isArray(data) ? `[${data.length}]` : `{${entries.length}}`;
  return (
    <details className="a-jt" open={depth < 2}>
      <summary><span className="a-jt-key">{name}</span><span className="a-jt-size">{size}</span></summary>
      <div className="a-jt-body">
        {entries.map(([k, v]) => <JsonTree key={k} name={String(k)} data={v} depth={depth + 1} />)}
        {Array.isArray(data) && data.length > 50 && <p className="a-muted small">…and {data.length - 50} more</p>}
      </div>
    </details>
  );
}

// Phase 1 data routes are proposed (proposals/phase1_backend) but not mounted on the server yet.
export const notMounted = (e) => e?.code === "HTTP_404";
export function MissingRoutes({ testid = "routes-missing" }) {
  return (
    <div className="a-card a-soon" data-testid={testid}>
      <span className="a-soon-ico"><Icon name="plug" size={28} /></span>
      <h2>Waiting for the server routes</h2>
      <p>This screen is ready. The server does not have its routes yet, because the backend change is waiting for the owner's OK.</p>
    </div>
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


// The guard ladder (docs/redesign/v3/audit/SCREENS-admin.md §3). The audit counted eighteen admin
// actions that spend quota, send mail to a real reader, change what every visitor sees, or destroy
// work that no Versions list holds -- with no dialog at all. Several sat beside a *guarded* action
// of lower consequence: delete-a-webhook asked, rotate-its-secret did not; delete-a-popup asked,
// publish-it-to-every-visitor did not; add-a-note asked, e-mail-the-member did not.
//
// The fix is not "add a dialog everywhere": a guard that is identical everywhere is one people learn
// to click through, which is worse than none. So the rungs are graded by cost, and the trigger now
// carries btn--danger whenever the action destroys something -- a class the whole admin used exactly
// once before this.
//
//   nothing      cheap, reversible, scoped to you (a cached explorer call, "send me a test")
//   confirm      reversible but other people see it      -> <Guard>
//   + the number anything that spends quota or money      -> <Guard body={<Cost .../>}>
//   + a reason   anything a reader sees or that touches their account
//   typed phrase irreversible destruction and bulk sends
//
// This is the one component for all of it, so a new button cannot quietly land on the wrong rung.
export function Guard({ label, busyLabel, title, body, confirmLabel, danger, reason, typed,
                        onRun, className = "btn btn--ghost", disabled, children, testid }) {
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  return (
    <>
      <button type="button" className={className} disabled={disabled || busy} onClick={() => setOpen(true)} data-testid={testid}>
        {busy ? (busyLabel || "Working…") : (children || label)}
      </button>
      <Confirm open={open} title={title || label} body={body} confirmLabel={confirmLabel || label} danger={danger}
               reason={reason} typed={typed} busy={busy} onClose={() => setOpen(false)}
               testid={testid ? `${testid}-confirm` : undefined}
               onConfirm={async (text) => {
                 setBusy(true);
                 // A throw is left to travel: Confirm catches it and prints it in the dialog, which
                 // stays open. Closing on failure would read as success.
                 try { await onRun(text); setOpen(false); } finally { setBusy(false); }
               }} />
    </>
  );
}

// What this press costs, in the dialog, next to what is left. The audit's complaint about the six
// job buttons was not that they lacked a guard but that all six shared one sentence, so a 1-call
// sync and a ~1,140-call season backfill read identically.
export function Cost({ calls, left, cap, lead, children }) {
  return (
    <>
      {lead && <p>{lead}</p>}
      {/* "About 0 provider calls" is not a cost, it is a non-sentence. A press that spends nothing
          says so in words, and the caller explains WHY it is nothing. */}
      {calls ? <p><b>About {num(calls)} provider {calls === 1 ? "call" : "calls"}.</b>{left != null ? ` ${num(left)} of ${num(cap)} left in today's budget.` : ""}</p> : null}
      {!calls && left != null && <p>{num(left)} of {num(cap)} provider calls left in today's budget.</p>}
      {children}
    </>
  );
}
