// Leagues (docs/10 §3.10): switch leagues on, pick seasons to backfill, see coverage and the call estimate.
// Leagues arrive from the reference sync switched off. The backfill job picks up queued seasons.
import { useState } from "react";
import { post, put } from "../lib/api";
import { useApi } from "../lib/useApi";
import { Confirm, Drawer, FormError, Switch, useToast } from "../components/Ui";
import { Empty, ErrorBox, Loading } from "../components/States";
import { LeagueMark } from "../components/Media";
import Icon from "../components/Icon";
import { Card, Chip, Cost, Guard, MissingRoutes, PageHead, notMounted, num } from "./parts";

function Seasons({ lg, budget, onClose, onSaved }) {
  const toast = useToast();
  const [pick, setPick] = useState(lg.backfill_seasons);
  const [err, setErr] = useState(null);
  const pending = lg.seasons.filter((s) => pick.includes(s.label) && !s.backfilled);
  const est = pending.reduce((a, s) => a + 1 + (s.matches || 380) * 3, 0);
  const save = async () => {
    setErr(null);
    try { await put(`/admin/leagues/${lg.iid}`, { backfill_seasons: pick }); toast("Seasons saved"); onSaved(); onClose(); } catch (x) { setErr(x); }
  };
  return (
    <Drawer open onClose={onClose} title={`${lg.name}: seasons`} testid="league-drawer" footer={<button className="btn btn--primary" onClick={save} data-testid="league-seasons-save">Save seasons</button>}>
      <div className="a-stack">
        <p className="a-muted">Ticked seasons are queued for the backfill job. Finished seasons are cached for ever, so each is fetched once.</p>
        <ul className="a-season-list">
          {lg.seasons.map((s) => (
            <li key={s.label}>
              <label className="check-row">
                <input type="checkbox" checked={pick.includes(s.label)} disabled={s.backfilled} onChange={(e) => setPick(e.target.checked ? [...pick, s.label] : pick.filter((x) => x !== s.label))} data-testid={`season-${s.label.replace("/", "-")}`} />
                <span className="a-season-name">{s.label}{s.label === lg.current_season && <Chip tone="brand">Current</Chip>}</span>
                <span className="a-season-state">{s.backfilled ? <Chip tone="up">Done · {num(s.matches)} matches</Chip> : s.queued ? <Chip tone="warn">Queued</Chip> : s.matches ? `${num(s.matches)} matches` : ""}</span>
              </label>
            </li>
          ))}
        </ul>
        <div className="a-notice" data-testid="league-estimate"><Icon name="info" size={16} /><span>About <b>{num(est)}</b> calls for the ticked seasons (1 list call plus about 3 per match). That is {budget ? Math.max(1, Math.ceil(est / budget)) : "?"} day(s) at today's budget of {num(budget)}.</span></div>
        <FormError error={err} />
      </div>
    </Drawer>
  );
}

const TONES = [{ id: "top", label: "Top (e.g. Europe)" }, { id: "mid", label: "Middle (e.g. play-offs)" }, { id: "bottom", label: "Bottom (e.g. relegation)" }];

function Zones({ lg, onClose, onSaved }) {
  const toast = useToast();
  const [rows, setRows] = useState(lg.zones || []);
  const set = (i, k, v) => setRows(rows.map((r, j) => (j === i ? { ...r, [k]: k === "start" || k === "end" ? Number(v) : v } : r)));
  const save = async () => {
    try { await put(`/admin/leagues/${lg.iid}`, { zones: rows.filter((r) => r.label.trim()) }); toast("Table zones saved"); onSaved(); onClose(); } catch (x) { toast(x.message || "Could not save", "err"); }
  };
  return (
    <Drawer open title={`Table zones · ${lg.name}`} onClose={onClose} testid="zones-modal">
      <p className="a-muted small">Colour bands on the public league table, for example 1–4 Champions League, 18–20 Relegation. Rules change by season, so set them here.</p>
      {rows.length > 0 && <div className="a-zone-row a-zone-head" aria-hidden="true"><small>From</small><small>To</small><small>Label</small><small>Colour</small><span /></div>}
      {rows.map((r, i) => (
        <div key={i} className="a-zone-row" data-testid={`zone-row-${i}`}>
          <input type="number" min={1} max={40} aria-label="From place" value={r.start} onChange={(e) => set(i, "start", e.target.value)} data-testid={`zone-${i}-start`} />
          <input type="number" min={1} max={40} aria-label="To place" value={r.end} onChange={(e) => set(i, "end", e.target.value)} data-testid={`zone-${i}-end`} />
          <input maxLength={40} aria-label="Label" placeholder="Champions League" value={r.label} onChange={(e) => set(i, "label", e.target.value)} data-testid={`zone-${i}-label`} />
          <select aria-label="Colour" value={r.tone} onChange={(e) => set(i, "tone", e.target.value)} data-testid={`zone-${i}-tone`}>{TONES.map((t) => <option key={t.id} value={t.id}>{t.label}</option>)}</select>
          <button type="button" className="btn btn--ghost btn--sm" onClick={() => setRows(rows.filter((_, j) => j !== i))} data-testid={`zone-${i}-remove`}>Remove</button>
        </div>
      ))}
      <div className="btn-row">
        {rows.length < 8 && <button type="button" className="btn btn--secondary btn--sm" onClick={() => setRows([...rows, rows.length ? { start: 18, end: 20, label: "", tone: "bottom" } : { start: 1, end: 4, label: "", tone: "top" }])} data-testid="zone-add">Add a zone</button>}
        <button type="button" className="btn btn--primary btn--sm" onClick={save} data-testid="zones-save">Save zones</button>
      </div>
    </Drawer>
  );
}

function LeagueCard({ lg, budget, daily, perMatch, onEdit, onZones, onChanged }) {
  const toast = useToast();
  const [ask, setAsk] = useState(false);
  const toggle = async (v) => { try { await put(`/admin/leagues/${lg.iid}`, { enabled: v }); toast(v ? `${lg.name} switched on` : `${lg.name} switched off`); onChanged(); } catch (x) { toast(x.message || "Could not save", "err"); } };
  // Switching ON commits provider calls every day for as long as it stays on, which is the one
  // recurring cost in the admin and had no guard and no number beside it. Switching OFF only stops
  // spending, so it goes through unasked.
  const onChange = (v) => (v ? setAsk(true) : toggle(false));
  const done = lg.seasons.filter((s) => s.backfilled).length;
  return (
    <article className={"a-card a-league" + (lg.enabled ? " is-on" : "")} data-testid={`league-${lg.iid}`}>
      <header className="a-league-head">
        <LeagueMark league={lg} size={36} decorative />
        <div><h2>{lg.name}</h2><small>{lg.country_code || "No data"} · id {lg.ext_id}</small></div>
      </header>
      <Switch label={lg.enabled ? "On" : "Off"} hint={`Fixtures and results sync for leagues that are on · about ${num(daily)} calls a day each`} checked={lg.enabled} onChange={onChange} testid={`league-${lg.iid}-toggle`} />
      <Confirm open={ask} title={`Switch ${lg.name} on?`} confirmLabel="Switch it on" onClose={() => setAsk(false)}
               testid={`league-${lg.iid}-toggle-confirm`}
               body={<Cost calls={daily} left={budget} cap={budget}
                           lead={`Every day it stays on, this league costs about ${num(daily)} list calls, plus about ${num(perMatch)} more for each match that finishes. Switching it off again stops that.`}>
                       {lg.estimate_calls ? <p className="muted small">Its picked backfill seasons would also cost about {num(lg.estimate_calls)} calls, once.</p> : null}
                     </Cost>}
               onConfirm={async () => { await toggle(true); setAsk(false); }} />
      <dl className="a-dl a-dl--tight">
        <div><dt>Seasons</dt><dd>{lg.seasons.length} known · {done} backfilled</dd></div>
        <div><dt>Backfill picked</dt><dd>{lg.backfill_seasons.length ? lg.backfill_seasons.join(", ") : "None"}</dd></div>
        <div><dt>Calls still needed</dt><dd>{num(lg.estimate_calls)}</dd></div>
        <div><dt>Coverage</dt><dd>{lg.coverage.length ? `${lg.coverage.length} fields tracked` : "No data yet"}</dd></div>
      </dl>
      <button className="btn btn--secondary btn--sm self-start" onClick={() => onEdit(lg)} data-testid={`league-${lg.iid}-seasons`}><Icon name="calendar" size={16} />Backfill seasons</button>
      <button className="btn btn--ghost btn--sm self-start" onClick={() => onZones(lg)} data-testid={`league-${lg.iid}-zones`}><Icon name="list" size={16} />Table zones{lg.zones?.length ? ` (${lg.zones.length})` : ""}</button>
    </article>
  );
}

export default function Leagues() {
  const q = useApi("/admin/leagues");
  const toast = useToast();
  const [edit, setEdit] = useState(null);
  const [zones, setZones] = useState(null);
  const [filter, setFilter] = useState("");
  // A full refresh brings back every league PitchAPI covers -- hundreds of them, nearly all off.
  // Search alone cannot answer "which have I actually switched on", which is the question asked
  // every time after the first.
  const [only, setOnly] = useState("all");
  const sync = async () => { await post("/admin/jobs/run?job=reference_sync"); toast("League list refresh queued"); };
  if (q.loading && !q.data) return <Loading rows={5} />;
  if (notMounted(q.error)) return <div className="a-page" data-testid="admin-leagues"><PageHead title="Leagues" lead="Switch leagues on and pick seasons to backfill." /><MissingRoutes /></div>;
  if (q.error) return <ErrorBox error={q.error} onRetry={q.reload} />;
  const list = q.data.leagues
    .filter((l) => (only === "all" ? true : only === "on" ? l.enabled : !l.enabled))
    .filter((l) => (l.name + " " + (l.country_code || "")).toLowerCase().includes(filter.toLowerCase()));
  const on = q.data.leagues.filter((l) => l.enabled).length;
  return (
    <div className="a-page" data-testid="admin-leagues">
      <PageHead title="Leagues" lead={q.data.leagues.length ? `${on} of ${q.data.leagues.length} switched on. New leagues arrive switched off.` : "Switch leagues on and pick seasons to backfill."}
                actions={<Guard className="btn btn--secondary btn--sm" confirmLabel="Queue the refresh" title="Refresh the league list?"
                                 body={<Cost calls={1} left={q.data.budget} cap={q.data.budget} lead="This queues the reference sync, which asks PitchAPI for every league it covers. New leagues arrive switched off, so nothing starts spending on its own." />}
                                 onRun={sync} testid="leagues-sync"><Icon name="refresh" size={16} />Refresh league list</Guard>} />
      {q.data.leagues.length === 0 ? (
        <Card><Empty icon="trophy" testid="leagues-empty">No leagues yet. Save the PitchAPI key in Keys, then use Refresh league list (one call) or run GET /v1/leagues in the Endpoint explorer.</Empty></Card>
      ) : (
        <>
          <div className="a-filters">
            <div className="a-search"><Icon name="search" size={18} /><input type="search" placeholder="Search leagues or country" aria-label="Search leagues" value={filter} onChange={(e) => setFilter(e.target.value)} data-testid="leagues-search" /></div>
            <div className="a-seg" role="group" aria-label="Show">
              {[["all", `All ${q.data.leagues.length}`], ["on", `On ${on}`], ["off", `Off ${q.data.leagues.length - on}`]].map(([id, label]) => (
                <button key={id} type="button" aria-pressed={only === id}
                        onClick={() => setOnly(id)} data-testid={`leagues-only-${id}`}>{label}</button>
              ))}
            </div>
          </div>
          {list.length === 0 ? <Empty>No league matches.</Empty> : <div className="a-key-grid">{list.map((l) => <LeagueCard key={l.iid} lg={l} budget={q.data.budget} daily={q.data.daily_calls_per_league} perMatch={q.data.calls_per_match} onEdit={setEdit} onZones={setZones} onChanged={q.reload} />)}</div>}
        </>
      )}
      {edit && <Seasons lg={edit} budget={q.data.budget} onClose={() => setEdit(null)} onSaved={q.reload} />}
      {zones && <Zones lg={zones} onClose={() => setZones(null)} onSaved={q.reload} />}
    </div>
  );
}
