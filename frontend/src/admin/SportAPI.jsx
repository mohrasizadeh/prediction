// Admin > Integrations > SportAPI (docs/23 §7.7): status, calls today, league mapping, team review, backfill, run now.
import { useState } from "react";
import { get, post, put } from "../lib/api";
import { useApi } from "../lib/useApi";
import { Field, FormError, useToast } from "../components/Ui";
import { Card, Chip, DataState, JsonTree, KV, StatTile, num, when } from "./parts";

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

// Live statistics decide whether shot, tackle and corner forecasts tick green while a match is on. The provider's
// names for those counts are not documented, so this panel shows what the last answers actually contained, lets you
// probe one fixture for a single call, and lets you teach us a name we could not place (docs/38).
function LiveStats() {
  const q = useApi("/admin/sportapi/live-stats");
  const toast = useToast();
  const [sid, setSid] = useState("");
  const [probe, setProbe] = useState(null);
  const [busy, setBusy] = useState(false);
  const [raw, setRaw] = useState(false);
  const d = q.data;
  const run = async () => {
    if (!sid) return;
    setBusy(true); setProbe(null);
    try { const r = await get(`/admin/sportapi/stats-probe/${sid}`); setProbe(r); }
    catch (x) { toast(x.message, "err"); }
    finally { setBusy(false); }
  };
  const toggle = async (on) => {
    try { await put("/admin/settings/sportapi.live_stats", { value: on }); toast(on ? "Live statistics on" : "Live statistics off"); q.reload(); }
    catch (x) { toast(x.message, "err"); }
  };
  const teach = async (stat, name) => {
    try {
      await post("/admin/sportapi/stats-keys", { stat, name });
      toast(`"${name}" now counts as ${stat}`);
      setProbe(null); q.reload();
    } catch (x) { toast(x.message, "err"); }
  };
  const found = probe?.found || d?.coverage?.found || {};
  const unmatched = probe?.unmatched ?? d?.coverage?.unmatched ?? [];
  return (
    <DataState q={q}>{() => (
      <Card title="Live statistics" testid="sportapi-livestats"
        actions={<Chip tone={d.enabled ? "up" : "warn"} testid="livestats-state">{d.enabled ? "On" : "Off"}</Chip>}>
        <p className="muted small">
          Cards tick green from match events, which always load. Shots, shots on target, corners and tackles need these
          statistics. A count we cannot read shows no tick, never a wrong one.
        </p>
        <div className="a-tiles-grid">
          {(d.stats || []).map((k) => (
            <StatTile key={k} label={k === "sot" ? "Shots on target" : k[0].toUpperCase() + k.slice(1)}
              value={found[k] ? "Found" : "Not seen"} tone={found[k] ? "up" : undefined}
              sub={found[k] ? "ticks green" : "no tick yet"} testid={`livestats-found-${k}`} />
          ))}
        </div>
        <p className="muted small" data-testid="livestats-when">
          {d.coverage?.at ? `Last answer read ${when(d.coverage.at)}.` : "No statistics answer has been read yet."}
          {" "}Refresh every {d.refresh_s}s while a match is on. Events refresh every {d.events_refresh_s}s.
        </p>

        <div className="a-form-row">
          <Field label="Check one fixture" as="select" value={sid} onChange={(e) => setSid(e.target.value)} testid="livestats-fixture">
            <option value="">Pick a fixture</option>
            {(d.fixtures || []).map((f) => (
              <option key={f.sid} value={f.sid}>
                {f.live ? "● " : ""}{f.home || "?"} v {f.away || "?"} · {f.status || "?"}{f.minute ? ` ${f.minute}` : ""}
              </option>
            ))}
          </Field>
          <button className="btn btn--secondary btn--sm self-start" onClick={run} disabled={!sid || busy} data-testid="livestats-probe">
            {busy ? "Checking" : "Check (1 call)"}
          </button>
          <button className={"btn btn--sm self-start " + (d.enabled ? "btn--secondary" : "btn--primary")} onClick={() => toggle(!d.enabled)} data-testid="livestats-toggle">
            {d.enabled ? "Turn off" : "Turn on live statistics"}
          </button>
        </div>

        {probe && (
          <p className="muted small" data-testid="livestats-probe-result">
            Fixture {probe.sid}: read {Object.values(probe.found).filter(Boolean).length} of 4 counts
            {probe.players ? `, and ${probe.players} players` : ", no per-player rows"}.
          </p>
        )}

        {unmatched.length > 0 && (
          <>
            <h3 className="a-h3">Names we could not place</h3>
            <p className="muted small">Pick the count a name belongs to. Anything that is not one of our four (possession, offsides) can be left alone.</p>
            <ul className="a-rows" data-testid="livestats-unmatched">
              {unmatched.map((n) => (
                <li key={n} className="a-list-item a-inline-actions">
                  <code className="a-mono">{n}</code>
                  <span className="a-inline-actions">
                    {(d.stats || []).map((k) => (
                      <button key={k} className="btn btn--secondary btn--sm" onClick={() => teach(k, n)} data-testid={`livestats-map-${k}`}>
                        {k === "sot" ? "on target" : k}
                      </button>
                    ))}
                  </span>
                </li>
              ))}
            </ul>
          </>
        )}

        {probe && (
          <>
            <button className="a-link-btn" onClick={() => setRaw(!raw)} aria-expanded={raw} data-testid="livestats-raw-toggle">
              {raw ? "Hide the provider's answer" : "Show the provider's answer"}
            </button>
            {raw && <div className="a-jt-wrap"><JsonTree data={probe.raw} name="stats" /></div>}
          </>
        )}
      </Card>
    )}</DataState>
  );
}

export default function SportAPI() {
  const q = useApi("/admin/sportapi");
  return (
    <DataState q={q}>{(s) => (
      <div className="a-stack" data-testid="admin-sportapi">
        <Status s={s} reload={q.reload} />
        <LiveStats />
        <Mapping s={s} reload={q.reload} />
        <Review s={s} reload={q.reload} />
        <Backfill reload={q.reload} />
      </div>
    )}</DataState>
  );
}
