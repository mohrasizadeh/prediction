// Engine (docs/09, docs/18, docs/19, docs/10 §3.10). Tabs: Brain layers (GET /admin/brain), Calendar import
// (POST /admin/calendar/import), Images (GET /admin/images, /review, sync, approve, reject, upload, take down).
// Lineup effects are locked off and only shown. Runs and forecast hiding need routes that are not built yet.
import { useState } from "react";
import { del, post, putFile } from "../lib/api";
import { useApi } from "../lib/useApi";
import { Confirm, Field, FormError, Tabs, useToast } from "../components/Ui";
import { Empty, ErrorBox, Loading } from "../components/States";
import Icon from "../components/Icon";
import { Card, Chip, DataState, KV, PageHead, Pager, StatTile, num, when } from "./parts";

function Brain() {
  const q = useApi("/admin/brain");
  if (q.loading && !q.data) return <Loading />;
  if (q.error) return <ErrorBox error={q.error} onRetry={q.reload} />;
  const d = q.data;
  const cal = Object.entries(d.calendar_rows_by_competition || {});
  return (
    <div className="a-stack">
      <p className="a-notice"><Icon name="padlock" size={16} />Lineup effects stay off. They failed their test on simulated data.</p>
      <div className="a-tiles-grid">
        <StatTile label="Gate results" value={num(d.gates.length)} testid="brain-gates" />
        <StatTile label="Clubs with a calendar" value={num(d.clubs_with_calendar)} testid="brain-clubs" />
        <StatTile label="Shape layer" value={String(d.shape_layer)} testid="brain-shape" />
      </div>
      <Card title="Latest gate per league and layer" testid="brain-gate-list">
        {d.gates.length ? d.gates.map((g, i) => (
          <details key={i}><summary>League {g.league_iid} · {g.layer} <Chip tone={g.passed ? "up" : "warn"}>{g.passed ? "Passed" : "Not passed"}</Chip><span className="a-muted small">{when(g.at)}</span></summary><KV obj={g} /></details>
        )) : <Empty>No gate results yet. They appear after the engine has run on enough finished matches.</Empty>}
      </Card>
      <Card title="Calendar rows by competition">{cal.length ? <ul className="a-plan-ents">{cal.map(([k, n]) => <li key={k}><span>{k}</span><b>{n}</b></li>)}</ul> : <Empty>No cup or European fixtures imported yet.</Empty>}</Card>
      <details><summary>Brain settings</summary><KV obj={{ ...d.settings, tactic_layers: d.tactic_layers }} /></details>
    </div>
  );
}

function Calendar() {
  const toast = useToast();
  const [text, setText] = useState("");
  const [err, setErr] = useState(null);
  const [res, setRes] = useState(null);
  const go = async (e) => {
    e.preventDefault(); setErr(null); setRes(null);
    try { const rows = JSON.parse(text); setRes(await post("/admin/calendar/import", rows)); toast("Calendar imported"); }
    catch (x) { setErr(x instanceof SyntaxError ? "That is not valid JSON." : x); }
  };
  return (
    <form className="a-card a-form" onSubmit={go} data-testid="calendar-form">
      <p className="a-muted small">Cups and European fixtures for our clubs. A list of <code>{"{team_iid, kickoff, comp, stage}"}</code>. Running it again is safe. Unknown competitions are refused; add them to <code>context.importance</code> first.</p>
      <Field label="Rows (JSON)" as="textarea" rows={8} value={text} onChange={(e) => setText(e.target.value)} placeholder='[{"team_iid": 12, "kickoff": "2026-11-04T20:00:00Z", "comp": "ucl", "stage": "group"}]' testid="calendar-json" />
      <FormError error={err} />
      {res && <KV obj={res} />}
      <button className="btn btn--primary self-start" disabled={!text.trim()} data-testid="calendar-import">Import</button>
    </form>
  );
}

function ReviewRow({ r, onDone }) {
  const toast = useToast();
  const [rm, setRm] = useState(false);
  const act = async (fn, msg) => { try { await fn(); toast(msg); onDone(); } catch (x) { toast(x.message || "Could not do that", "err"); } };
  const upload = (e) => {
    const f = e.target.files?.[0]; e.target.value = "";
    if (f) act(() => putFile(`/admin/images/${r.kind}/${r.our_iid}/upload`, f), "Image uploaded");
  };
  return (
    <li className="a-card a-review" data-testid={`review-${r.kind}-${r.our_iid}`}>
      <div className="a-review-head"><Chip>{r.kind}</Chip><strong>{r.name || r.our_name || `#${r.our_iid}`}</strong>{r.score !== undefined && <span className="a-muted small">best match {Math.round((r.score || 0) * 100)}%</span>}</div>
      <div className="a-btns">
        {(r.candidates || []).map((c) => <button key={c.af_id} className="btn btn--secondary btn--sm" onClick={() => act(() => post(`/admin/images/${r.kind}/${r.our_iid}/approve`, { af_id: c.af_id }), "Approved")} data-testid={`approve-${r.our_iid}-${c.af_id}`}><Icon name="check" size={16} />{c.name} ({Math.round(c.score * 100)}%)</button>)}
        <button className="btn btn--ghost btn--sm" onClick={() => act(() => post(`/admin/images/${r.kind}/${r.our_iid}/reject`), "Rejected")} data-testid={`reject-${r.our_iid}`}>None of these</button>
        <label className="btn btn--ghost btn--sm">Upload<input type="file" accept="image/png,image/jpeg,image/webp" hidden onChange={upload} /></label>
        <button className="btn btn--ghost btn--sm" onClick={() => setRm(true)} data-testid={`takedown-${r.our_iid}`}>Take down</button>
      </div>
      <Confirm open={rm} danger title="Take this image down?" body="The initials badge shows instead." confirmLabel="Take down" onClose={() => setRm(false)} onConfirm={async () => { await del(`/admin/images/${r.kind}/${r.our_iid}`); setRm(false); toast("Taken down"); onDone(); }} testid="takedown-confirm" />
    </li>
  );
}

function Images() {
  const s = useApi("/admin/images");
  const toast = useToast();
  const [kind, setKind] = useState("");
  const [page, setPage] = useState(1);
  const rv = useApi("/admin/images/review", { kind, page });
  const sync = async (refresh) => { try { await post(`/admin/images/sync?refresh=${refresh}`); toast("Image sync queued for the next tick"); } catch (x) { toast(x.message || "Could not queue it", "err"); } };
  if (s.loading && !s.data) return <Loading />;
  if (s.error) return <ErrorBox error={s.error} onRetry={s.reload} />;
  return (
    <div className="a-stack">
      <div className="a-btns">
        <button className="btn btn--primary btn--sm" onClick={() => sync(false)} data-testid="images-sync"><Icon name="refresh" size={16} />Sync images</button>
        <button className="btn btn--secondary btn--sm" onClick={() => sync(true)} data-testid="images-sync-refresh">Sync and re-read squads</button>
      </div>
      <div className="a-tiles-grid">
        {Object.entries(s.data.kinds || {}).map(([k, v]) => <StatTile key={k} label={k === "team" ? "Crests" : k === "player" ? "Player photos" : "League logos"} value={`${num(v.stored)} / ${num(v.ours)}`} sub={`${num(v.review)} to review · ${num(v.none)} not found`} testid={`images-${k}`} />)}
      </div>
      <Card title="Waiting for a person" testid="images-review" actions={<select aria-label="Kind" value={kind} onChange={(e) => { setKind(e.target.value); setPage(1); }} data-testid="images-kind"><option value="">All</option><option value="league">Leagues</option><option value="team">Clubs</option><option value="player">Players</option></select>}>
        <DataState q={rv} empty="Nothing to review.">
          {(d) => <><ul className="a-rows">{d.rows.map((r) => <ReviewRow key={`${r.kind}-${r.our_iid}`} r={r} onDone={() => { rv.reload(); s.reload(); }} />)}</ul><Pager page={d.page} limit={25} total={d.total} onPage={setPage} /></>}
        </DataState>
      </Card>
    </div>
  );
}

export default function Engine() {
  const [tab, setTab] = useState("brain");
  return (
    <div className="a-page" data-testid="admin-engine">
      <PageHead title="Engine" lead="What the forecast brain is using, the cup calendar, and club and player images." />
      <Tabs tabs={[{ id: "brain", label: "Brain layers" }, { id: "calendar", label: "Calendar import" }, { id: "images", label: "Images" }]} value={tab} onChange={setTab} testid="engine-tabs" />
      {tab === "brain" ? <Brain /> : tab === "calendar" ? <Calendar /> : <Images />}
    </div>
  );
}
