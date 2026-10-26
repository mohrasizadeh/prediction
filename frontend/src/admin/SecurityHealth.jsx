// Security (docs/10 §3.15) and Health (§3.16).
import { useApi } from "../lib/useApi";
import { ErrorBox, Loading, Empty } from "../components/States";
import { AlertList } from "./Dashboard";
import { Bars, Card, Chip, KV, PageHead, ResponsiveTable, StatTile, num, when } from "./parts";

export function Security() {
  const q = useApi("/admin/security");
  if (q.loading && !q.data) return <Loading rows={5} />;
  if (q.error) return <ErrorBox error={q.error} onRetry={q.reload} />;
  const d = q.data;
  const hours = Object.entries(d.failed_by_hour || {}).map(([day, count]) => ({ day, count }));
  return (
    <div className="a-page" data-testid="admin-security">
      <PageHead title="Security" lead="The last 24 hours." />
      <div className="a-tiles-grid">
        <StatTile label="Failed sign-ins" value={num(d.failed_logins_24h)} tone={d.failed_logins_24h > 20 ? "down" : undefined} testid="sec-failed" />
        <StatTile label="Locked accounts" value={num(d.locked_accounts)} testid="sec-locked" />
        <StatTile label="Rate-limited" value={num(d.rate_limited_24h)} testid="sec-ratelimited" />
        <StatTile label="Blocked (bad origin)" value={num(d.bad_origin_24h)} testid="sec-origin" />
        <StatTile label="Staff without 2FA" value={num(d.staff_without_2fa)} tone={d.staff_without_2fa ? "down" : "up"} testid="sec-no2fa" />
        <StatTile label="Active staff sessions" value={num(d.active_staff_sessions)} testid="sec-sessions" />
      </div>
      {hours.length ? <Bars title="Failed sign-ins by hour" data={hours} testid="chart-failed" /> : <Card title="Failed sign-ins by hour"><Empty icon="check">None in the last 24 hours.</Empty></Card>}
      <Card title="Checklist" testid="sec-checklist">
        <ul className="a-checklist">
          <li className={d.staff_without_2fa ? "is-bad" : "is-ok"}>Every staff member uses two-factor sign-in</li>
          <li className="is-info">Owner changed the first password (forced at first sign-in)</li>
          <li className="is-info">Billing stays in test mode until the owner decides</li>
        </ul>
      </Card>
      <Card title="Staff" testid="sec-staff">
        <ResponsiveTable rows={d.staff} testid="sec-staff-table" columns={[{ key: "email", label: "Person", primary: true }, { key: "role", label: "Role" },
          { key: "two_factor", label: "2FA", render: (r) => (r.two_factor ? <Chip tone="up">On</Chip> : <Chip tone="down">Off</Chip>) }, { key: "last_login_at", label: "Last sign-in", render: (r) => when(r.last_login_at) }]} />
      </Card>
      <Card title="Last staff actions" testid="sec-actions">
        {d.recent_staff_actions?.length ? d.recent_staff_actions.map((r, i) => <KV key={i} obj={r} skip={["_id"]} />) : <Empty>No staff actions yet.</Empty>}
      </Card>
    </div>
  );
}

export function Health() {
  const q = useApi("/admin/health");
  if (q.loading && !q.data) return <Loading rows={5} />;
  if (q.error) return <ErrorBox error={q.error} onRetry={q.reload} />;
  const h = q.data;
  return (
    <div className="a-page" data-testid="admin-health">
      <PageHead title="Health" actions={<button className="btn btn--secondary btn--sm" onClick={q.reload} data-testid="health-refresh">Refresh</button>} />
      <Card title="Alerts" testid="health-alerts"><AlertList alerts={h.alerts} /></Card>
      <div className="a-tiles-grid">
        <StatTile label="Database" value={h.db_ok ? "OK" : "Down"} tone={h.db_ok ? "up" : "down"} testid="health-db" />
        <StatTile label="Last job" value={h.last_job_run ? when(h.last_job_run.started_at || h.last_job_run.at) : "None yet"} sub={h.last_job_run?.job} testid="health-job" />
        <StatTile label="Data breaker" value={h.breaker_open ? "Open" : "Closed"} tone={h.breaker_open ? "down" : "up"} testid="health-breaker" />
        <StatTile label="API calls today" value={`${num(h.api_calls_today)} / ${num(h.api_budget)}`} testid="health-api" />
        <StatTile label="E-mails today" value={`${num(h.emails_today)} / ${num(h.email_cap)}`} testid="health-email" />
        <StatTile label="Webhook errors 24 h" value={num(h.webhook_errors_24h)} tone={h.webhook_errors_24h ? "down" : undefined} testid="health-webhooks" />
        <StatTile label="Server errors 24 h" value={num(h.server_errors_24h)} tone={h.server_errors_24h > 5 ? "down" : undefined} testid="health-errors" />
        <StatTile label="People" value={num(h.users)} testid="health-users" />
      </div>
      <Card title="Queue" testid="health-queue">{Object.keys(h.queue || {}).length ? <KV obj={h.queue} /> : <Empty>The queue is empty.</Empty>}</Card>
    </div>
  );
}
