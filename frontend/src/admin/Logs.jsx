// Logs (docs/10 §3.14): one screen, tabs per source, time range, paged. Personal data is masked by the server.
import { useState } from "react";
import { useApi } from "../lib/useApi";
import { Tabs } from "../components/Ui";
import { DataState, KV, PageHead, Pager, when } from "./parts";

const KINDS = [["audit", "Audit"], ["auth", "Sign-ins"], ["app", "Application"], ["api", "Provider calls"], ["webhooks", "Webhooks"], ["jobs", "Jobs"], ["issues", "Data issues"], ["email", "E-mail"]];
const RANGES = [["", "Any time"], ["24", "Last 24 hours"], ["168", "Last 7 days"], ["720", "Last 30 days"]];
const head = (r) => r.action || r.event || r.path || r.type || r.job || r.template || r.kind || r.purpose || "Entry";
const at = (r) => r.at || r.received_at || r.started_at || r.created_at;

export default function Logs() {
  const [kind, setKind] = useState("audit");
  const [since, setSince] = useState("");
  const [page, setPage] = useState(1);
  const q = useApi(`/admin/logs/${kind}`, { page, limit: 50, since_hours: since });
  return (
    <div className="a-page" data-testid="admin-logs">
      <PageHead title="Logs" lead="Quote a request id from an error page to find its row." actions={
        <select aria-label="Time range" value={since} onChange={(e) => { setSince(e.target.value); setPage(1); }} data-testid="logs-range">{RANGES.map(([v, l]) => <option key={v} value={v}>{l}</option>)}</select>} />
      <Tabs tabs={KINDS.map(([id, label]) => ({ id, label }))} value={kind} onChange={(k) => { setKind(k); setPage(1); }} testid="logs-tabs" />
      <DataState q={q} empty="No entries in this range.">
        {(d) => (
          <>
            <ul className="a-log-list" data-testid="logs-list">
              {d.rows.map((r, i) => (
                <li key={r.id || i} className="a-card a-log">
                  <details>
                    <summary><strong>{head(r)}</strong><span className="a-muted">{when(at(r))}</span>{r.status !== undefined && <span className="a-log-status">{String(r.status)}</span>}</summary>
                    <KV obj={r} skip={["id"]} />
                  </details>
                </li>
              ))}
            </ul>
            <Pager page={d.page} limit={d.limit} total={d.total} onPage={setPage} />
          </>
        )}
      </DataState>
    </div>
  );
}
