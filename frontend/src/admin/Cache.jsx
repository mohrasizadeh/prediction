// Cache and usage (docs/10 §3.10): calls today vs budget, 14-day chart, by purpose and status, breaker state,
// cache table with search, open, delete one, delete by prefix, delete all.
import { useState } from "react";
import { del, post } from "../lib/api";
import { useApi } from "../lib/useApi";
import { Confirm, Drawer, useToast } from "../components/Ui";
import { Empty, ErrorBox, Loading } from "../components/States";
import Icon from "../components/Icon";
import { Bars, Card, Chip, DataState, JsonTree, MissingRoutes, PageHead, Pager, ResponsiveTable, StatTile, notMounted, num, when } from "./parts";

function Counts({ title, obj, testid }) {
  const rows = Object.entries(obj || {}).sort((a, b) => b[1] - a[1]);
  return (
    <Card title={title} testid={testid}>
      {rows.length ? <ul className="a-plan-ents">{rows.map(([k, v]) => <li key={k}><span>{k}</span><b>{v}</b></li>)}</ul> : <Empty>No calls today.</Empty>}
    </Card>
  );
}

function Usage({ q }) {
  const toast = useToast();
  if (q.loading && !q.data) return <Loading rows={4} />;
  if (q.error) return <ErrorBox error={q.error} onRetry={q.reload} />;
  const u = q.data;
  const pct = u.budget ? Math.min(100, Math.round((u.calls_today / u.budget) * 100)) : 0;
  const close = async () => { try { await post("/admin/breaker/close"); toast("Breaker closed"); q.reload(); } catch (x) { toast(x.message || "Could not close it", "err"); } };
  return (
    <>
      <div className="a-tiles-grid">
        <StatTile label="Calls today" value={`${num(u.calls_today)} / ${num(u.budget)}`} sub={`${pct}% of the daily budget`} tone={pct >= 90 ? "down" : undefined} testid="usage-today" />
        <StatTile label="Breaker" value={u.breaker.open ? "Open" : "Closed"} sub={u.breaker.open ? `${u.breaker.reason} · until ${when(u.breaker.until)}` : "Calls are allowed"} tone={u.breaker.open ? "down" : "up"} testid="usage-breaker" />
        <StatTile label="Cached answers" value={num(u.cache_rows)} testid="usage-cache-rows" />
      </div>
      <div className="a-meter" role="meter" aria-valuemin={0} aria-valuemax={u.budget} aria-valuenow={u.calls_today} aria-label="Calls today against budget"><span style={{ width: `${pct}%` }} /></div>
      {u.breaker.open && <button className="btn btn--secondary self-start" onClick={close} data-testid="usage-close-breaker">Close breaker</button>}
      <Bars title="Real calls per day (14 days)" data={u.by_day} testid="usage-chart" />
      <div className="a-split a-split--even">
        <Counts title="Today by purpose" obj={u.by_purpose} testid="usage-purpose" />
        <Counts title="Today by status" obj={u.by_status} testid="usage-status" />
      </div>
      {Object.keys(u.error_codes || {}).length > 0 && <Counts title="Error codes today" obj={u.error_codes} testid="usage-codes" />}
    </>
  );
}

function Row({ id, onClose }) {
  const q = useApi(id ? `/admin/cache/${id}` : null);
  return (
    <Drawer open={!!id} onClose={onClose} title={q.data?.path || "Cached answer"} testid="cache-drawer" wide>
      {q.loading || !q.data ? (q.error ? <ErrorBox error={q.error} /> : <Loading />) : (
        <div className="a-stack">
          <p className="a-muted small">Cache key: <code data-testid="cache-key">{id}</code></p>
          {Object.keys(q.data.params || {}).length > 0 && <code className="a-path">{new URLSearchParams(q.data.params).toString()}</code>}
          {q.data.error_code ? <p className="a-notice a-notice--warn">Stored not-found answer: {q.data.error_code}</p> : <div className="a-jt-wrap"><JsonTree data={q.data.data} /></div>}
        </div>
      )}
    </Drawer>
  );
}

function CacheTable() {
  const toast = useToast();
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(1);
  const [open, setOpen] = useState(null);
  const [ask, setAsk] = useState(null);
  const q = useApi("/admin/cache", { q: search, page });
  const remove = async (params, label) => {
    const r = await del(`/admin/cache?${new URLSearchParams(params)}`);
    setAsk(null); toast(`Deleted ${r.deleted} ${r.deleted === 1 ? "row" : "rows"}${label === "all" ? " from the whole cache" : ""}`); q.reload();
  };
  const cols = [
    { key: "path", label: "Path", primary: true, render: (r) => <span className="a-person"><b className="a-mono">{r.path}</b>{Object.keys(r.params).length > 0 && <small>{new URLSearchParams(r.params).toString()}</small>}</span> },
    { key: "fetched_at", label: "Fetched", render: (r) => when(r.fetched_at) },
    { key: "expires_at", label: "Expires", render: (r) => (r.forever ? <Chip tone="brand">Never</Chip> : r.expired ? <Chip tone="warn">Expired</Chip> : when(r.expires_at)) },
    { key: "error_code", label: "Kind", render: (r) => (r.error_code ? <Chip tone="down">{r.error_code}</Chip> : <Chip>Data</Chip>) },
    { key: "x", label: "", render: (r) => <span onClick={(e) => e.stopPropagation()} role="presentation"><button className="a-icon-btn a-icon-btn--sm" aria-label="Delete this row" onClick={() => setAsk({ title: "Delete this cached answer?", params: { key: r.id } })} data-testid={`cache-delete-${r.id.slice(0, 8)}`}><Icon name="trash" size={16} /></button></span> },
  ];
  return (
    <Card title="Cache" testid="cache-table-card">
      <div className="a-filters">
        <div className="a-search"><Icon name="search" size={18} /><input type="search" placeholder="Path starts with, e.g. /v1/matches" aria-label="Search cache by path" value={search} onChange={(e) => { setSearch(e.target.value); setPage(1); }} data-testid="cache-search" /></div>
        <button className="btn btn--danger btn--sm" disabled={!search.trim()} onClick={() => setAsk({ title: `Delete every row starting with ${search.trim()}?`, params: { prefix: search.trim() }, label: "prefix" })} data-testid="cache-delete-prefix">Delete these</button>
        <button className="btn btn--danger btn--sm" onClick={() => setAsk({ title: "Delete the whole cache?", params: { all: "true" }, typed: "DELETE", label: "all" })} data-testid="cache-delete-all">Delete all</button>
      </div>
      <DataState q={q} empty="The cache is empty. Answers appear here after the first calls.">
        {(d) => <><ResponsiveTable columns={cols} rows={d.rows} onRow={(r) => setOpen(r.id)} testid="cache-table" /><Pager page={d.page} limit={d.limit} total={d.total} onPage={setPage} /></>}
      </DataState>
      <Row id={open} onClose={() => setOpen(null)} />
      <Confirm open={!!ask} danger title={ask?.title} typed={ask?.typed} body="The next call for these will be a real call and cost from the budget." confirmLabel="Delete" onClose={() => setAsk(null)} onConfirm={() => remove(ask.params, ask.label)} testid="cache-confirm" />
    </Card>
  );
}

export default function Cache({ head = true }) {
  const q = useApi("/admin/usage");
  return (
    <div className="a-page" data-testid="admin-cache">
      {head && <PageHead title="Cache and usage" lead="Every PitchAPI answer is cached. Finished matches are kept for ever." />}
      {notMounted(q.error) ? <MissingRoutes /> : <><Usage q={q} /><CacheTable /></>}
    </div>
  );
}
