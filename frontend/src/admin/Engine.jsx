// Engine (docs/09, docs/18, docs/19, docs/10 §3.10). Tabs: Brain layers (GET /admin/brain), Calendar import
// (POST /admin/calendar/import), Images (GET /admin/images, /review, sync, approve, reject, upload, take down).
// Lineup effects are locked off and only shown. Runs and the forecast browser live in EngineRuns.jsx.
import { useState } from "react";
import { Forecasts, Runs } from "./EngineRuns";
import Availability from "./Availability";
import { Row as SettingRow, History as SettingHistory } from "./Settings";
import { useAuth } from "../lib/auth";
import { del, post, put, putFile } from "../lib/api";
import { useApi } from "../lib/useApi";
import { Confirm, Field, FormError, Switch, Tabs, useToast } from "../components/Ui";
import { Empty, ErrorBox, Loading } from "../components/States";
import Icon from "../components/Icon";
import { Card, Chip, Cost, DataState, Guard, KV, PageHead, Pager, StatTile, num, when } from "./parts";

function Calibration({ d, reload }) {
  const toast = useToast();
  const [ask, setAsk] = useState(false);
  const c = d.calibration || {};
  const e = d.engine || {};
  const [sw, setSw] = useState(null);
  const set = async (key, value) => { try { await put(`/admin/settings/${key}`, { value }); toast("Saved. It applies from the next engine run."); reload(); } catch (x) { toast(x.message, "err"); } };
  // These three change every percentage on the public site at the next engine run, and they saved
  // the instant the switch moved. A switch is the lightest control in the system driving the
  // heaviest consequence in the product (docs/redesign/v3/audit §3).
  const askSwitch = (key, value, what) => setSw({ key, value, what });
  return (
    <Card title="Percentages and factors" testid="brain-calibration" actions={<Chip tone={c.enabled ? "up" : "warn"} testid="brain-calibration-source">{c.source === "own" ? "Own map" : c.source === "default" ? "Default map" : "Off"}</Chip>}>
      <p className="a-muted small">The map turns the engine's raw likelihood into the percentage people see. Version in use: <b data-testid="brain-calibration-version">{c.version || "none"}</b>. A weekly refit from our own results is kept only if it beats the current map on the newest 30%.</p>
      {/* Two counts, because they are two different things and showing only the first read as
          "23,846 of 5,000" -- a progress bar past its own target, beside a screen still serving the
          shipped map. `eligible` is what a refit may actually learn from: with "if he plays" on, the
          older all-in rows and the non-appearances do not qualify however many there are (docs/27). */}
      <p className="a-muted small" data-testid="brain-calibration-progress">
        {num(c.scored)} forecasts scored. <b>{num(c.eligible)}</b> of them can train a map, against the {num(c.needed)} needed
        {c.eligible >= c.needed ? " — enough." : ` — ${num(Math.max(0, c.needed - (c.eligible || 0)))} to go.`}
      </p>
      {/* The answer to "so why am I still on the shipped map" was already in this payload and drawn
          nowhere. Without it the screen cannot tell "never ran" from "ran and the new map lost". */}
      {c.last_refit && (
        <p className="a-muted small" data-testid="brain-calibration-last">
          Last refit {when(c.last_refit.started_at)}: {
            {off: "turned off, so nothing was fitted.",
             waiting: "not enough eligible results yet.",
             kept_current: "a new map was fitted and did not beat the one in use, so it was thrown away.",
             updated: "a new map won and is now in use."}[c.last_refit.result?.status] || (c.last_refit.result?.status || "no result recorded.")
          }
          {c.last_refit.result?.candidate != null && ` (new ${c.last_refit.result.candidate}, current ${c.last_refit.result.current}; lower is better)`}
        </p>
      )}
      {!c.last_refit && <p className="a-muted small" data-testid="brain-calibration-never">The weekly refit has not run yet.</p>}
      {c.test_logloss && <p className="a-muted small">Last refit test: new {c.test_logloss.new} vs previous {c.test_logloss.previous} ({when(c.created_at)})</p>}
      <Switch label="Show calibrated percentages" checked={!!c.enabled} onChange={(v) => askSwitch("engine.calibration", v, "the calibration map")} testid="brain-sw-calibration" />
      <Switch label="Absences count" hint="Players who missed recent matches are less likely to play" checked={!!e["engine.absence_model"]} onChange={(v) => askSwitch("engine.absence_model", v, "the availability model")} testid="brain-sw-absence" />
      <Switch label="Results form and late-season context" hint="Applied to expected goals" checked={!!e["engine.match_context"]} onChange={(v) => askSwitch("engine.match_context", v, "form and late-season context")} testid="brain-sw-context" />
      <Confirm open={!!sw} danger={!!sw && !sw.value} title={sw ? `${sw.value ? "Switch on" : "Switch off"} ${sw.what}?` : ""}
               confirmLabel={sw?.value ? "Switch it on" : "Switch it off"} onClose={() => setSw(null)} testid="brain-sw-confirm"
               body={<p>Every percentage on the public site is recomputed with {sw?.value ? "this layer in" : "this layer out"} at the next engine run, so numbers readers have already seen will move. Our published record is measured against what we showed, so switching this is a change to the product, not a display option.</p>}
               onConfirm={async () => { await set(sw.key, sw.value); setSw(null); }} />
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
        <button className="btn btn--danger btn--sm" onClick={() => setRm(true)} data-testid={`takedown-${r.our_iid}`}>Take down</button>
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
  const sync = async (refresh) => { await post(`/admin/images/sync?refresh=${refresh}`); toast("Image sync queued for the next tick"); };
  if (s.loading && !s.data) return <Loading />;
  if (s.error) return <ErrorBox error={s.error} onRetry={s.reload} />;
  return (
    <div className="a-stack">
      <div className="a-btns">
        {/* Both spend PitchAPI quota. The second re-reads every squad as well, which is the larger
            of the two by a long way, so it says so and is marked. */}
        <Guard className="btn btn--primary btn--sm" confirmLabel="Queue the sync" title="Sync the missing pictures?"
               body={<Cost lead="This asks PitchAPI for league logos, club crests and player photos we do not hold yet, at one call each. Pictures we already have cost nothing. It runs at the next tick." />}
               onRun={() => sync(false)} testid="images-sync"><Icon name="refresh" size={16} />Sync images</Guard>
        <Guard className="btn btn--danger btn--sm" label="Sync and re-read squads" danger confirmLabel="Re-read every squad"
               title="Re-read every squad and sync pictures?"
               body={<Cost lead="On top of the picture sync, this re-reads the full squad of every club in every league that is on -- one call per club -- whether or not anything has changed. It is the heaviest press on this screen. Use the plain sync unless squads are actually wrong." />}
               onRun={() => sync(true)} testid="images-sync-refresh" />
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

const SWITCHES = [["engine.absence_model", "Availability model"], ["engine.match_context", "Form and situation"], ["engine.calibration", "Calibration"], ["context.start_model", "Start model"]];

function Switches() {
  const q = useApi("/admin/settings");
  const { user } = useAuth();
  const [hist, setHist] = useState(null);
  if (q.loading && !q.data) return <Loading />;
  if (q.error) return <ErrorBox error={q.error} onRetry={q.reload} />;
  const rows = SWITCHES.map(([k, label]) => { const s = q.data.find((r) => r.key === k); return s && { ...s, label }; }).filter(Boolean);
  return (
    <Card title="The four switches that matter" testid="engine-switches">
      <p className="a-muted small">Each change applies when the next engine run starts. Everything else lives in Settings.</p>
      {rows.map((s) => <SettingRow key={s.key + JSON.stringify(s.value)} s={s} canOwner={user?.role === "owner"} onSaved={q.reload} onHistory={setHist} />)}
      <SettingHistory s={hist} onClose={() => setHist(null)} />
    </Card>
  );
}

export default function Engine() {
  const [tab, setTab] = useState("switches");
  const body = { switches: <Switches />, runs: <Runs />, forecasts: <Forecasts />, brain: <Brain />, availability: <Availability />, calendar: <Calendar />, images: <Images /> }[tab];
  return (
    <div className="a-page" data-testid="admin-engine">
      <PageHead title="Engine" lead="Runs, current forecasts you can hide, what the forecast brain is using, the cup calendar, and images." />
      <Tabs tabs={[{ id: "switches", label: "Switches" }, { id: "runs", label: "Runs" }, { id: "forecasts", label: "Forecasts" }, { id: "brain", label: "Brain layers" }, { id: "availability", label: "Availability" }, { id: "calendar", label: "Calendar import" }, { id: "images", label: "Images" }]} value={tab} onChange={setTab} testid="engine-tabs" />
      {body}
    </div>
  );
}
