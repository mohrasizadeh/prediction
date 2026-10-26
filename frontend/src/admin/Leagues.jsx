// Leagues (docs/10 §3.10): switch leagues on, pick seasons to backfill, see coverage and the call estimate.
// Leagues arrive from the reference sync switched off. The backfill job picks up queued seasons.
import { useState } from "react";
import { post, put } from "../lib/api";
import { useApi } from "../lib/useApi";
import { Drawer, FormError, Switch, useToast } from "../components/Ui";
import { Empty, ErrorBox, Loading } from "../components/States";
import { LeagueMark } from "../components/Media";
import Icon from "../components/Icon";
import { Card, Chip, MissingRoutes, PageHead, notMounted, num } from "./parts";

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

function LeagueCard({ lg, budget, onEdit, onChanged }) {
  const toast = useToast();
  const toggle = async (v) => { try { await put(`/admin/leagues/${lg.iid}`, { enabled: v }); toast(v ? `${lg.name} switched on` : `${lg.name} switched off`); onChanged(); } catch (x) { toast(x.message || "Could not save", "err"); } };
  const done = lg.seasons.filter((s) => s.backfilled).length;
  return (
    <article className={"a-card a-league" + (lg.enabled ? " is-on" : "")} data-testid={`league-${lg.iid}`}>
      <header className="a-league-head">
        <LeagueMark league={lg} size={36} decorative />
        <div><h2>{lg.name}</h2><small>{lg.country_code || "No data"} · id {lg.ext_id}</small></div>
      </header>
      <Switch label={lg.enabled ? "On" : "Off"} hint="Fixtures and results sync for leagues that are on" checked={lg.enabled} onChange={toggle} testid={`league-${lg.iid}-toggle`} />
      <dl className="a-dl a-dl--tight">
        <div><dt>Seasons</dt><dd>{lg.seasons.length} known · {done} backfilled</dd></div>
        <div><dt>Backfill picked</dt><dd>{lg.backfill_seasons.length ? lg.backfill_seasons.join(", ") : "None"}</dd></div>
        <div><dt>Calls still needed</dt><dd>{num(lg.estimate_calls)}</dd></div>
        <div><dt>Coverage</dt><dd>{lg.coverage.length ? `${lg.coverage.length} fields tracked` : "No data yet"}</dd></div>
      </dl>
      <button className="btn btn--secondary btn--sm self-start" onClick={() => onEdit(lg)} data-testid={`league-${lg.iid}-seasons`}><Icon name="calendar" size={16} />Backfill seasons</button>
    </article>
  );
}

export default function Leagues() {
  const q = useApi("/admin/leagues");
  const toast = useToast();
  const [edit, setEdit] = useState(null);
  const [filter, setFilter] = useState("");
  const sync = async () => { try { await post("/admin/jobs/run?job=reference_sync"); toast("League list refresh queued"); } catch (x) { toast(x.message || "Could not queue it", "err"); } };
  if (q.loading && !q.data) return <Loading rows={5} />;
  if (notMounted(q.error)) return <div className="a-page" data-testid="admin-leagues"><PageHead title="Leagues" /><MissingRoutes /></div>;
  if (q.error) return <ErrorBox error={q.error} onRetry={q.reload} />;
  const list = q.data.leagues.filter((l) => (l.name + " " + (l.country_code || "")).toLowerCase().includes(filter.toLowerCase()));
  const on = q.data.leagues.filter((l) => l.enabled).length;
  return (
    <div className="a-page" data-testid="admin-leagues">
      <PageHead title="Leagues" lead={`${on} of ${q.data.leagues.length} switched on. New leagues arrive switched off.`}
                actions={<button className="btn btn--secondary btn--sm" onClick={sync} data-testid="leagues-sync"><Icon name="refresh" size={16} />Refresh league list</button>} />
      {q.data.leagues.length === 0 ? (
        <Card><Empty icon="trophy" testid="leagues-empty">No leagues yet. Save the PitchAPI key in Keys, then use Refresh league list (one call) or run GET /v1/leagues in the Endpoint explorer.</Empty></Card>
      ) : (
        <>
          <div className="a-filters"><div className="a-search"><Icon name="search" size={18} /><input type="search" placeholder="Search leagues or country" aria-label="Search leagues" value={filter} onChange={(e) => setFilter(e.target.value)} data-testid="leagues-search" /></div></div>
          {list.length === 0 ? <Empty>No league matches.</Empty> : <div className="a-key-grid">{list.map((l) => <LeagueCard key={l.iid} lg={l} budget={q.data.budget} onEdit={setEdit} onChanged={q.reload} />)}</div>}
        </>
      )}
      {edit && <Seasons lg={edit} budget={q.data.budget} onClose={() => setEdit(null)} onSaved={q.reload} />}
    </div>
  );
}
