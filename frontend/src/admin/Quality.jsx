// Data quality (docs/10 §3.10): ingest issues with Resolve, coverage matrix league × field, and a mapping check of the
// provider.* settings against a saved PitchAPI answer (cache key or an Explorer fixture file). Edit mappings in Settings.
import { useState } from "react";
import { Link } from "react-router-dom";
import { post } from "../lib/api";
import { useApi } from "../lib/useApi";
import { Confirm, Field, FormError, Tabs, useToast } from "../components/Ui";
import { Empty, ErrorBox, Loading } from "../components/States";
import Icon from "../components/Icon";
import { Card, Chip, DataState, KV, MissingRoutes, PageHead, Pager, ResponsiveTable, notMounted, when } from "./parts";

function Issues() {
  const toast = useToast();
  const [resolved, setResolved] = useState(false);
  const [kind, setKind] = useState("");
  const [page, setPage] = useState(1);
  const [pick, setPick] = useState(null);
  const q = useApi("/admin/issues", { resolved, kind, page });
  if (notMounted(q.error)) return <MissingRoutes />;
  const cols = [
    { key: "kind", label: "Kind", primary: true, render: (r) => <span className="a-person"><b>{r.kind}</b><small>{r.detail}</small></span> },
    { key: "at", label: "Found", render: (r) => when(r.at) },
    { key: "match_iid", label: "Match", render: (r) => r.match_iid ?? "None" },
    { key: "x", label: "", render: (r) => (r.resolved ? <Chip tone="up">Resolved</Chip> : <span onClick={(e) => e.stopPropagation()} role="presentation"><button className="btn btn--secondary btn--sm" onClick={() => setPick(r)} data-testid={`issue-resolve-${r.id}`}>Resolve</button></span>) },
  ];
  return (
    <>
      <div className="a-filters">
        <select aria-label="Open or resolved" value={String(resolved)} onChange={(e) => { setResolved(e.target.value === "true"); setPage(1); }} data-testid="issues-state"><option value="false">Open</option><option value="true">Resolved</option></select>
        <select aria-label="Kind" value={kind} onChange={(e) => { setKind(e.target.value); setPage(1); }} data-testid="issues-kind"><option value="">Every kind</option>{(q.data?.kinds || []).map((k) => <option key={k}>{k}</option>)}</select>
      </div>
      <DataState q={q} empty={resolved ? "No resolved issues." : "No open issues. Ingest looks clean."}>
        {(d) => <><ResponsiveTable columns={cols} rows={d.rows} onRow={setPick} testid="issues-table" /><Pager page={d.page} limit={d.limit} total={d.total} onPage={setPage} /></>}
      </DataState>
      <Confirm open={!!pick} title={pick?.resolved ? "Issue" : "Mark this issue resolved?"} body={pick && <KV obj={pick} skip={["id"]} />} reason={pick?.resolved ? undefined : "What did you do? (optional note)"}
               confirmLabel={pick?.resolved ? "Close" : "Resolve"} onClose={() => setPick(null)} testid="issue-confirm"
               onConfirm={async (note) => { if (pick.resolved) return setPick(null); await post(`/admin/issues/${pick.id}/resolve`, { note }); setPick(null); toast("Resolved"); q.reload(); }} />
    </>
  );
}

const pct = (s) => (s === null || s === undefined ? "No data" : `${Math.round(s * 100)}%`);
function Coverage() {
  const q = useApi("/admin/coverage");
  if (q.loading && !q.data) return <Loading />;
  if (notMounted(q.error)) return <MissingRoutes />;
  if (q.error) return <ErrorBox error={q.error} onRetry={q.reload} />;
  const { fields, leagues, min_share: min } = q.data;
  if (!leagues.length) return <Empty icon="trophy" testid="coverage-empty">No league is switched on. Switch one on in <Link to="/admin/data/leagues">Leagues</Link>.</Empty>;
  return (
    <>
      <p className="a-muted small">Share of rows that have each field. Markets need at least {pct(min)}; cells below that are marked.</p>
      <div className="a-table-wrap a-matrix" data-testid="coverage-matrix">
        <table className="a-table">
          <thead><tr><th scope="col">League</th>{fields.map((f) => <th key={f} scope="col">{f.replace("team_match_stats.", "team ").replace("player_match_stats.", "player ")}</th>)}</tr></thead>
          <tbody>{leagues.map((l) => (
            <tr key={l.iid}><td><b>{l.name}</b></td>{fields.map((f) => { const c = l.cells[f]; const low = c && c.share < min; return <td key={f} className={"a-center a-cov" + (c ? (low ? " is-low" : " is-ok") : "")}>{c ? pct(c.share) : "No data"}{low && <span className="sr-only"> below the minimum</span>}</td>; })}</tr>
          ))}</tbody>
        </table>
      </div>
    </>
  );
}

function Mapping() {
  const [f, setF] = useState({ kind: "stats", cache_key: "", text: "" });
  const [res, setRes] = useState(null);
  const [err, setErr] = useState(null);
  const [busy, setBusy] = useState(false);
  const run = async (e) => {
    e.preventDefault(); setErr(null); setBusy(true);
    try {
      const body = { kind: f.kind };
      if (f.cache_key.trim()) body.cache_key = f.cache_key.trim(); else body.data = JSON.parse(f.text);
      setRes(await post("/admin/mapping/check", body));
    } catch (x) { setErr(x instanceof SyntaxError ? "That is not valid JSON." : x); setRes(null); } finally { setBusy(false); }
  };
  const fileIn = (e) => { const file = e.target.files?.[0]; if (file) file.text().then((t) => setF((x) => ({ ...x, text: t, cache_key: "" }))); };
  if (notMounted(err)) return <MissingRoutes />;
  return (
    <div className="a-stack">
      <p className="a-muted small">Check the <code>provider.*</code> settings against a real saved answer. Get one by running <b>Match team stats</b> or <b>Match player stats</b> in the <Link to="/admin/data/explorer">Endpoint explorer</Link> (Save as fixture), or copy its key from <Link to="/admin/data/cache">Cache</Link>. Change the mappings in <Link to="/admin/settings">Settings</Link> (group Provider).</p>
      <form className="a-card a-form" onSubmit={run} data-testid="mapping-form">
        <div className="a-form-row">
          <Field label="Answer type" as="select" value={f.kind} onChange={(e) => setF({ ...f, kind: e.target.value })} testid="mapping-kind"><option value="stats">Match team stats</option><option value="players">Match player stats</option></Field>
          <Field label="Cache key (optional)" value={f.cache_key} onChange={(e) => setF({ ...f, cache_key: e.target.value })} testid="mapping-key" />
        </div>
        <Field label="Or paste the saved JSON" as="textarea" rows={5} value={f.text} onChange={(e) => setF({ ...f, text: e.target.value })} testid="mapping-json" />
        <label className="btn btn--ghost btn--sm self-start">Load a fixture file<input type="file" accept="application/json,.json" hidden onChange={fileIn} data-testid="mapping-file" /></label>
        <FormError error={err} />
        <button className="btn btn--primary self-start" disabled={busy || (!f.cache_key.trim() && !f.text.trim())} data-testid="mapping-run">{busy ? "Checking…" : "Check mapping"}</button>
      </form>
      {res && (
        <Card title="Result" testid="mapping-result">
          {res.missing.length ? <p className="a-notice a-notice--warn" data-testid="mapping-missing"><Icon name="alert" size={16} />No value found for: {res.missing.join(", ")}. Point these at a key below.</p>
            : <p className="a-notice" data-testid="mapping-ok"><Icon name="check" size={16} />Every column found a value.</p>}
          {res.unmapped_positions?.length > 0 && <p className="a-notice a-notice--warn"><Icon name="alert" size={16} />Positions with no mapping: {res.unmapped_positions.join(", ")} (provider.position_map).</p>}
          <details open><summary>What the mapping reads now</summary>
            {res.kind === "stats" ? <div className="a-split a-split--even"><KV obj={res.mapped.home} /><KV obj={res.mapped.away} /></div>
              : <ResponsiveTable rowKey={(r) => r.ext_id} testid="mapping-players" rows={res.mapped} columns={[{ key: "name", label: "Player", primary: true }, { key: "pos_raw", label: "Raw pos" }, { key: "pos", label: "Pos" }, { key: "minutes", label: "Min" }, { key: "shots", label: "Shots" }, { key: "sot", label: "On target" }, { key: "tackles", label: "Tackles" }]} />}
          </details>
          <details><summary>Keys the provider sent ({res.available.length})</summary>
            <ResponsiveTable rowKey={(r) => (r.group || "") + r.key} testid="mapping-available" rows={res.available} columns={[{ key: "key", label: "Key", primary: true, render: (r) => <code>{r.key}</code> }, { key: "title", label: "Title" }, { key: "group", label: "Group" }, ...(res.kind === "stats" ? [{ key: "home", label: "Home" }, { key: "away", label: "Away" }] : [])]} />
          </details>
        </Card>
      )}
    </div>
  );
}

export default function Quality({ head = true }) {
  const [tab, setTab] = useState("issues");
  return (
    <div className="a-page" data-testid="admin-quality">
      {head && <PageHead title="Data quality" lead="Problems found while ingesting, how complete each league is, and whether the field mapping reads the right keys." />}
      <Tabs tabs={[{ id: "issues", label: "Issues" }, { id: "coverage", label: "Coverage" }, { id: "mapping", label: "Mapping check" }]} value={tab} onChange={setTab} testid="quality-tabs" />
      {tab === "issues" ? <Issues /> : tab === "coverage" ? <Coverage /> : <Mapping />}
    </div>
  );
}
