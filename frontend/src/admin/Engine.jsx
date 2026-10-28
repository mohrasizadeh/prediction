// Engine (docs/09, docs/18, docs/19, docs/10 §3.10). Tabs: Brain layers (GET /admin/brain), Calendar import
// (POST /admin/calendar/import), Images (GET /admin/images, /review, sync, approve, reject, upload, take down).
// Lineup effects are locked off and only shown. Runs and the forecast browser live in EngineRuns.jsx.
import { useState } from "react";
import { Forecasts, Runs } from "./EngineRuns";
import Availability from "./Availability";
import { del, post, put, putFile } from "../lib/api";
import { useApi } from "../lib/useApi";
import { Confirm, Field, FormError, Switch, Tabs, useToast } from "../components/Ui";
import { Empty, ErrorBox, Loading } from "../components/States";
import Icon from "../components/Icon";
import { Card, Chip, DataState, KV, PageHead, Pager, StatTile, num, when } from "./parts";

function Calibration({ d, reload }) {
  const toast = useToast();
  const [ask, setAsk] = useState(false);
  const c = d.calibration || {};
  const e = d.engine || {};
  const set = async (key, value) => { try { await put(`/admin/settings/${key}`, { value }); toast("Saved. It applies from the next engine run."); reload(); } catch (x) { toast(x.message, "err"); } };
  return (
    <Card title="Percentages and factors" testid="brain-calibration" actions={<Chip tone={c.enabled ? "up" : "warn"} testid="brain-calibration-source">{c.source === "own" ? "Own map" : c.source === "default" ? "Default map" : "Off"}</Chip>}>
      <p className="a-muted small">The map turns the engine's raw likelihood into the percentage people see. Version in use: <b data-testid="brain-calibration-version">{c.version || "none"}</b>. A weekly refit from our own results is kept only if it beats the current map ({num(c.scored)} of {num(c.needed)} scored forecasts so far).</p>
      {c.test_logloss && <p className="a-muted small">Last refit test: new {c.test_logloss.new} vs previous {c.test_logloss.previous} ({when(c.created_at)})</p>}
      <Switch label="Show calibrated percentages" checked={!!c.enabled} onChange={(v) => set("engine.calibration", v)} testid="brain-sw-calibration" />
      <Switch label="Absences count" hint="Players who missed recent matches are less likely to play" checked={!!e["engine.absence_model"]} onChange={(v) => set("engine.absence_model", v)} testid="brain-sw-absence" />
      <Switch label="Results form and late-season context" hint="Applied to expected goals" checked={!!e["engine.match_context"]} onChange={(v) => set("engine.match_context", v)} testid="brain-sw-context" />
      <Field as="select" label="How fast old results fade" value={String(e["engine.strength_decay"] ?? 0.01)} onChange={(x) => set("engine.strength_decay", Number(x.target.value))} testid="brain-decay">
        {[0.005, 0.01, 0.02, 0.03].map((v) => <option key={v} value={String(v)}>{v === 0.01 ? "0.01 (recommended)" : String(v)}</option>)}
      </Field>
      <button className="btn btn--secondary btn--sm self-start" onClick={() => setAsk(true)} disabled={c.source !== "own"} data-testid="brain-calibration-rollback">Back to default map</button>
      <Confirm open={ask} title="Go back to the default map?" body="New forecasts use the shipped map from the next engine run." confirmLabel="Go back" onClose={() => setAsk(false)} onConfirm={async () => { try { await post("/admin/calibration/rollback"); toast("Default map in use"); reload(); } catch (x) { toast(x.message, "err"); } setAsk(false); }} testid="brain-rollback-confirm" />
    </Card>
  );
}

function Brain() {
  const q = useApi("/admin/brain");
  if (q.loading && !q.data) return <Loading />;
  if (q.error) return <ErrorBox error={q.error} onRetry={q.reload} />;
  const d = q.data;
  const cal = Object.entries(d.calendar_rows_by_competition || {});
  return (
    <div className="a-stack">
      <p className="a-notice"><Icon name="padlock" size={16} />Lineup effects stay off. They failed their test on simulated data.</p>
      <Calibration d={d} reload={q.reload} />
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
  const [tab, setTab] = useState("runs");
  const body = { runs: <Runs />, forecasts: <Forecasts />, brain: <Brain />, availability: <Availability />, calendar: <Calendar />, images: <Images /> }[tab];
  return (
    <div className="a-page" data-testid="admin-engine">
      <PageHead title="Engine" lead="Runs, current forecasts you can hide, what the forecast brain is using, the cup calendar, and images." />
      <Tabs tabs={[{ id: "runs", label: "Runs" }, { id: "forecasts", label: "Forecasts" }, { id: "brain", label: "Brain layers" }, { id: "availability", label: "Availability" }, { id: "calendar", label: "Calendar import" }, { id: "images", label: "Images" }]} value={tab} onChange={setTab} testid="engine-tabs" />
      {body}
    </div>
  );
}
