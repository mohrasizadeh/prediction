// The Overview tab of Analytics (docs/10 §3.1, docs/43): stat tiles, sign-ups and visitors per day, alerts from
// health. It was a separate menu entry called Dashboard, beside Home and Analytics, which gave three names to
// roughly one job.
import { Link } from "react-router-dom";
import { useApi } from "../lib/useApi";
import Icon from "../components/Icon";
import { ErrorBox, Loading, Empty } from "../components/States";
import { Bars, Card, PageHead, StatTile, num } from "./parts";

const pctChange = (c) => (c === null || c === undefined ? "No earlier data" : `${c > 0 ? "+" : ""}${Math.round(c * 100)}% vs last period`);

export function AlertList({ alerts, testid = "alert-list" }) {
  if (!alerts?.length) return <Empty icon="check" testid={`${testid}-empty`}>No alerts. Everything looks fine.</Empty>;
  const sorted = [...alerts].sort((a, b) => (a.level === "red" ? -1 : 0) - (b.level === "red" ? -1 : 0));
  return (
    <ul className="a-alerts" data-testid={testid}>
      {sorted.map((a, i) => <li key={i} className={"a-alert a-alert--" + a.level}><Icon name="alert" size={18} /><span>{a.message}</span></li>)}
    </ul>
  );
}

export default function Dashboard({ head = true }) {
  const q = useApi("/admin/dashboard");
  if (q.loading && !q.data) return <Loading rows={6} />;
  if (q.error) return <ErrorBox error={q.error} onRetry={q.reload} />;
  const o = q.data.overview, h = q.data.health;
  const mrr = (o.revenue?.by_currency || []).map((r) => `${((r.mrr_cents || 0) / 100).toLocaleString()} ${String(r.currency || "").toUpperCase()}`).join(" · ") || "No data";
  return (
    <div className="a-page" data-testid="admin-dashboard">
      {head && <PageHead title="Dashboard" lead={`Last ${o.window_days} days`} actions={<button className="btn btn--secondary btn--sm" onClick={q.reload} data-testid="dashboard-refresh"><Icon name="refresh" size={16} />Refresh</button>} />}
      <div className="a-tiles-grid">
        <StatTile label="People" value={num(o.people.total)} sub={`${num(o.people.free)} free · ${num(o.people.paid)} paid · ${num(o.people.comp)} comp`} testid="tile-people" />
        <StatTile label="Active today" value={num(o.active.dau)} sub={`${num(o.active.wau)} this week · ${num(o.active.mau)} this month`} testid="tile-active" />
        <StatTile label="New sign-ups" value={num(o.signups.now)} sub={pctChange(o.signups.change)} tone={o.signups.change < 0 ? "down" : undefined} testid="tile-signups" />
        <StatTile label="Page views" value={num(o.page_views)} testid="tile-views" />
        <StatTile label="Monthly revenue" value={mrr} sub="Billing is off until the owner turns it on" testid="tile-mrr" />
        <StatTile label="Churn" value={o.revenue?.churn?.rate === null || o.revenue?.churn?.rate === undefined ? "No data" : `${Math.round(o.revenue.churn.rate * 100)}%`} sub={`${num(o.revenue?.trialing)} on trial · ${num(o.revenue?.past_due)} past due`} testid="tile-churn" />
      </div>
      <div className="a-split">
        <div className="a-stack">
          <Bars title="Sign-ups per day" data={o.signups_by_day} testid="chart-signups" />
          <Bars title="Visitors per day" data={o.visitors_by_day} y="uniques" testid="chart-visitors" />
        </div>
        <Card title="Alerts" testid="dashboard-alerts" actions={<Link to="/admin/health" className="a-link-btn">Health</Link>}>
          <AlertList alerts={h.alerts} />
          <dl className="a-dl a-dl--tight">
            <div><dt>API calls today</dt><dd>{num(h.api_calls_today)} of {num(h.api_budget)}</dd></div>
            <div><dt>E-mails today</dt><dd>{num(h.emails_today)} of {num(h.email_cap)}</dd></div>
            <div><dt>Server errors 24 h</dt><dd>{num(h.server_errors_24h)}</dd></div>
            <div><dt>Database</dt><dd>{h.db_ok ? "OK" : "Not reachable"}</dd></div>
          </dl>
        </Card>
      </div>
    </div>
  );
}
