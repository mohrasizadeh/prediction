// Admin > Integrations > SportAPI (docs/23 §7.7): status, calls today, league mapping, team review, backfill, run now.
import { useState } from "react";
import { get, post, put } from "../lib/api";
import { useApi } from "../lib/useApi";
import { Field, FormError, useToast } from "../components/Ui";
import { Card, Chip, DataState, KV, StatTile, num, when } from "./parts";

const KINDS = ["date", "events", "final", "lineups", "backfill", "leagues"];

function Status({ s, reload }) {
  const toast = useToast();
  const [busy, setBusy] = useState(false);
  const share = Math.min(100, Math.round((s.calls_today / Math.max(1, s.cap)) * 100));
  const run = async () => { setBusy(true); try { const r = await post("/admin/sportapi/tick"); toast(`Run finished: ${r.status}${r.note ? ` (${r.note})` : ""}`, r.status === "ok" || r.status === "off" ? "ok" : "err"); reload(); } catch (x) { toast(x.message, "err"); } finally { setBusy(false); } };
  return (
    <Card title="SportAPI live data" testid="sportapi-status" actions={<Chip tone={s.enabled && s.key_saved ? "up" : "warn"} testid="sportapi-state">{s.enabled ? (s.key_saved ? "On" : "No key") : "Off"}</Chip>}>
      <p className="muted small">Live scores, match events and lineups. Only the minute job calls SportAPI; visitors never do. Turn it on with <code>sportapi.enabled</code> in Settings once the key and leagues are set.</p>
      <div className="a-tiles-grid">
        <StatTile label="Calls today" value={`${num(s.calls_today)} / ${num(s.cap)}`} sub={`Plan limit ${num(s.plan_limit)}`} testid="sportapi-calls" />
        <StatTile label="Live now" value={num(s.live_now)} testid="sportapi-live-now" />
        <StatTile label="Key saved" value={s.key_saved ? "Yes" : "No"} sub="Admin > Keys" testid="sportapi-key" />
        <StatTile label="Dates backfilled" value={num(s.dates_backfilled)} testid="sportapi-dates" />
      </div>
      <div className="sp-bar" role="progressbar" aria-valuenow={share} aria-valuemin={0} aria-valuemax={100} aria-label="Calls used today" data-testid="sportapi-bar"><span style={{ width: `${share}%` }} className={share > 75 ? "is-tight" : ""} /></div>
      <p className="muted small" data-testid="sportapi-by-kind">{KINDS.map((k) => `${k} ${num(s.by_kind?.[k] || 0)}`).join(" · ")} · resets {(() => { const r = new Date(); r.setUTCHours(24, 0, 0, 0); return r.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }); })()}</p>
      <p className="muted small">Last run: {when(s.last_tick)}{s.last_result ? ` · ${s.last_result.status}${s.last_result.note ? `: ${s.last_result.note}` : ""}` : ""}</p>
      <p className="muted small">Clubs matched: {Object.entries(s.teams || {}).map(([k, v]) => `${k} ${v}`).join(" · ")}</p>
      <button className="btn btn--primary btn--sm self-start" onClick={run} disabled={busy} data-testid="sportapi-run-now">{busy ? "Running" : "Run now"}</button>
    </Card>
  );
}

function Mapping({ s, reload }) {
  const toast = useToast();
  const clubs = useApi("/admin/clubs");
  const [list, setList] = useState(null);
  const [err, setErr] = useState(null);
  const [map, setMap] = useState(() => Object.fromEntries(Object.entries(s.leagues || {}).map(([k, v]) => [k, String(v)])));
  const load = async () => { setErr(null); try { setList((await get("/admin/sportapi/leagues")).leagues); } catch (x) { setErr(x); } };
  const save = async () => {
    const value = Object.fromEntries(Object.entries(map).filter(([, v]) => v && /^\d+$/.test(v)).map(([k, v]) => [k, Number(v)]));
    try { await put("/admin/settings/sportapi.leagues", { value }); toast("League mapping saved"); reload(); } catch (x) { toast(x.message, "err"); }
  };
  return (
    <Card title="League mapping" testid="sportapi-mapping">
      <p className="muted small">Pick the SportAPI league for each of our leagues. Only mapped leagues are followed. The SportAPI list costs 1 call and is kept for a week.</p>
      <button className="btn btn--secondary btn--sm self-start" onClick={load} data-testid="sportapi-load-leagues">Load SportAPI leagues</button>
      <FormError error={err} />
      <DataState q={clubs} empty="No leagues switched on.">
        {(d) => <div className="a-stack">{d.leagues.map((l) => (
          <Field key={l.iid} label={l.country ? `${l.name} (${l.country})` : l.name} as={list ? "select" : "input"} value={map[String(l.iid)] || ""} onChange={(e) => setMap({ ...map, [String(l.iid)]: e.target.value })} placeholder="SportAPI league id, for example 24" testid={`sportapi-map-${l.iid}`}>
            {list && <><option value="">Not followed</option>{list.map((x) => <option key={x.id} value={String(x.id)}>{x.name} · {x.country} (#{x.id})</option>)}</>}
          </Field>
        ))}</div>}
      </DataState>
      <button className="btn btn--primary btn--sm self-start" onClick={save} data-testid="sportapi-map-save">Save mapping</button>
    </Card>
  );
}

function Review({ s, reload }) {
  const toast = useToast();
  const clubs = useApi("/admin/clubs");
  const byIid = Object.fromEntries((clubs.data?.leagues || []).flatMap((l) => l.teams).map((t) => [t.iid, t.id]));
  const act = async (sid, team_id) => { try { await post(`/admin/sportapi/teams/${sid}`, { team_id }); toast(team_id ? "Approved" : "Rejected"); reload(); } catch (x) { toast(x.message, "err"); } };
  return (
    <Card title={`Team review (${(s.review || []).length})`} testid="sportapi-review">
      {(s.review || []).length ? <ul className="a-rows">{s.review.map((r) => (
        <li key={r.sid} className="a-card a-review" data-testid={`sportapi-review-${r.sid}`}>
          <div className="a-review-head"><strong>{r.name}</strong><span className="a-muted small">best match {Math.round((r.score || 0) * 100)}%</span></div>
          <div className="a-btns">
            {(r.candidates || []).map((c) => <button key={c.iid} className="btn btn--secondary btn--sm" disabled={!byIid[c.iid]} onClick={() => act(r.sid, byIid[c.iid])} data-testid={`sportapi-approve-${r.sid}-${c.iid}`}>{c.name} ({Math.round(c.score * 100)}%)</button>)}
            <button className="btn btn--ghost btn--sm" onClick={() => act(r.sid, "")} data-testid={`sportapi-reject-${r.sid}`}>None of these</button>
          </div>
        </li>
      ))}</ul> : <p className="muted small" data-testid="sportapi-review-empty">Nothing to review.</p>}
    </Card>
  );
}

function Backfill({ reload }) {
  const [f, setF] = useState({ start: "", end: "" });
  const [res, setRes] = useState(null);
  const [err, setErr] = useState(null);
  const go = async (e) => { e.preventDefault(); setErr(null); setRes(null); try { setRes(await post("/admin/sportapi/backfill", f)); reload(); } catch (x) { setErr(x); } };
  return (
    <form className="a-card a-form" onSubmit={go} data-testid="sportapi-backfill">
      <h2 className="h3">Backfill past results</h2>
      <p className="muted small">One call per date, at most 60 days per request. Dates already complete cost nothing. It pauses to keep calls for live scores; run it again to carry on.</p>
      <div className="a-grid2">
        <Field label="Start" type="date" value={f.start} onChange={(e) => setF({ ...f, start: e.target.value })} testid="sportapi-backfill-start" />
        <Field label="End" type="date" value={f.end} onChange={(e) => setF({ ...f, end: e.target.value })} testid="sportapi-backfill-end" />
      </div>
      <FormError error={err} />
      {res && <KV obj={{ status: res.status, done: (res.done || []).length, skipped: (res.skipped || []).length, stored: res.stored, next: res.next, calls_left: res.calls_left }} />}
      <button className="btn btn--primary btn--sm self-start" disabled={!f.start || !f.end} data-testid="sportapi-backfill-go">Start</button>
    </form>
  );
}

export default function SportAPI() {
  const q = useApi("/admin/sportapi");
  return (
    <DataState q={q}>{(s) => (
      <div className="a-stack" data-testid="admin-sportapi">
        <Status s={s} reload={q.reload} />
        <Mapping s={s} reload={q.reload} />
        <Review s={s} reload={q.reload} />
        <Backfill reload={q.reload} />
      </div>
    )}</DataState>
  );
}
