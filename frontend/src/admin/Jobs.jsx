// Ingest and jobs (docs/07, docs/10 §3.10): last run per job, queue counts, lock, manual runs, recent runs.
// Jobs run inside POST /api/jobs/tick, which an outside pinger calls every 5 minutes with X-CRON-SECRET.
import { useState } from "react";
import { post } from "../lib/api";
import { useApi } from "../lib/useApi";
import { Confirm, useToast } from "../components/Ui";
import { Empty, ErrorBox, Loading } from "../components/States";
import Icon from "../components/Icon";
import { Card, Chip, MissingRoutes, PageHead, ResponsiveTable, StatTile, notMounted, num, when } from "./parts";

const JOBS = [
  ["reference_sync", "League list", "1 call. Adds new leagues, switched off."],
  ["fixtures_sync", "Fixtures", "1 call per league that is on."],
  ["results_sync", "Results", "1 fresh call per league; queues new finished matches."],
  ["backfill", "Backfill", "Fetches the seasons ticked in Leagues."],
  ["engine", "Engine", "Recomputes forecasts for leagues that are on."],
  ["images", "Images", "PitchAPI league logos, club crests and player photos."],
];
const tone = (s) => (s === "ok" ? "up" : s === "error" ? "down" : s === "running" ? "brand" : "warn");
const RECENT = [
  { key: "job", label: "Job", primary: true },
  { key: "status", label: "Status", render: (r) => <Chip tone={tone(r.status)}>{r.status}</Chip> },
  { key: "started_at", label: "Started", render: (r) => when(r.started_at) },
  { key: "finished_at", label: "Finished", render: (r) => when(r.finished_at) },
  { key: "error", label: "Error", render: (r) => r.error || "None" },
];

function Extras() {
  const toast = useToast();
  const q = useApi("/admin/ingest/extras");
  if (!q.data) return null;
  const x = q.data;
  const go = async () => { try { const r = await post("/admin/ingest/extras/backfill"); toast(`${r.queued} matches queued`); q.reload(); } catch (e) { toast(e.message, "err"); } };
  return (
    <Card title="Referees, cards and substitutions" testid="jobs-extras" actions={<button className="btn btn--secondary btn--sm" onClick={go} data-testid="extras-backfill">Queue missing matches</button>}>
      <p className="muted small">{x.detail || x.events ? `On. Each finished match costs ${x.calls_per_new_match} extra PitchAPI calls.` : "Off. Turn on ingest.match_extra_detail and ingest.match_extra_events in Settings."} {x.pending ? `About ${x.calls_needed} calls left for the backlog (daily budget ${x.daily_budget}).` : ""}</p>
      <div className="a-tiles"><StatTile label="Matches done" value={`${x.done} / ${x.ingested}`} testid="extras-done" /><StatTile label="Waiting" value={x.pending} testid="extras-pending" /></div>
    </Card>
  );
}

export default function Jobs() {
  const q = useApi("/admin/jobs");
  const toast = useToast();
  const [ask, setAsk] = useState(null);
  if (q.loading && !q.data) return <Loading rows={5} />;
  if (notMounted(q.error)) return <div className="a-page" data-testid="admin-jobs"><PageHead title="Jobs" /><MissingRoutes /></div>;
  if (q.error) return <ErrorBox error={q.error} onRetry={q.reload} />;
  const d = q.data;
  const queue = Object.entries(d.queue || {});
  const run = async (job) => { await post(`/admin/jobs/run?job=${job}`); setAsk(null); toast("Queued. It runs at the next tick."); q.reload(); };
  return (
    <div className="a-page" data-testid="admin-jobs">
      <PageHead title="Jobs" lead="Everything runs inside the tick, which an outside pinger calls every 5 minutes. Manual runs wait for the next tick."
                actions={<button className="btn btn--secondary btn--sm" onClick={q.reload} data-testid="jobs-refresh"><Icon name="refresh" size={16} />Refresh</button>} />
      {d.paused_reason && <p className="a-notice a-notice--warn" data-testid="jobs-paused"><Icon name="alert" size={16} />Calls are paused: {d.paused_reason}</p>}
      <Extras />
      <div className="a-tiles-grid">
        <StatTile label="Leagues on" value={num(d.enabled_leagues)} testid="jobs-leagues" />
        <StatTile label="Seasons queued" value={num(d.seasons_queued)} testid="jobs-seasons" />
        <StatTile label="Tick" value={d.tick.running ? "Running" : "Idle"} sub={d.tick.running ? `since ${when(d.tick.since)}` : "No tick in progress"} tone={d.tick.running ? "brand" : undefined} testid="jobs-tick" />
        <StatTile label="Waiting requests" value={num(d.requests.length)} testid="jobs-requests" />
      </div>
      <div className="a-key-grid">
        {JOBS.map(([id, label, hint]) => {
          const l = id === "engine" ? Object.entries(d.last).filter(([k]) => k.startsWith("engine:")).map(([, v]) => v).sort((a, b) => String(b.started_at).localeCompare(String(a.started_at)))[0] : d.last[id];
          const waiting = d.requests.some((r) => r.job === id);
          return (
            <article key={id} className="a-card a-job" data-testid={`job-${id}`}>
              <header className="a-key-head"><span className="a-key-ico"><Icon name="clock" size={18} /></span><div><h2>{label}</h2><small>{hint}</small></div>{l && <Chip tone={tone(l.status)}>{l.status}</Chip>}</header>
              <p className="a-muted small">{l ? `Last run ${when(l.started_at)}${l.error ? ` · ${l.error}` : ""}` : "Never run"}</p>
              <button className="btn btn--secondary btn--sm self-start" disabled={waiting} onClick={() => setAsk({ id, label, hint })} data-testid={`job-${id}-run`}>{waiting ? "Waiting for the tick" : "Run now"}</button>
            </article>
          );
        })}
      </div>
      <Card title="Queue" testid="jobs-queue">
        {queue.length ? <ul className="a-plan-ents">{queue.map(([task, by]) => <li key={task}><span>{task}</span><b>{Object.entries(by).map(([s, n]) => `${n} ${s}`).join(" · ")}</b></li>)}</ul> : <Empty>The queue is empty.</Empty>}
      </Card>
      <Card title="Recent runs" testid="jobs-recent">
        {d.recent.length ? <ResponsiveTable columns={RECENT} rows={d.recent} testid="jobs-recent-table" /> : <Empty icon="clock">No runs yet. The first tick starts them.</Empty>}
      </Card>
      <Confirm open={!!ask} title={`Run ${ask?.label} now?`} body={`${ask?.hint || ""} Calls count toward today's budget.`} confirmLabel="Queue it" onClose={() => setAsk(null)} onConfirm={() => run(ask.id)} testid="job-confirm" />
    </div>
  );
}
