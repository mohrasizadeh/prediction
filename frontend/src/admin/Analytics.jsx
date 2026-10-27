// Analytics extras (docs/16 §7): right now, this period vs the last, where people come from, e-mail health, popups, list growth, CSV export.
import { useState } from "react";
import { useApi } from "../lib/useApi";
import { useToast } from "../components/Ui";
import { Card, DataState, PageHead, ResponsiveTable, StatTile } from "./parts";
import { download } from "./Newsletter";

const pct = (v) => (v == null ? "No data" : `${(v * 100).toFixed(1)}%`);
const ch = (v) => (v == null ? "New" : `${v > 0 ? "+" : ""}${(v * 100).toFixed(0)}%`);
const LABEL = { visitors: "Visitors", page_views: "Page views", signups: "Sign-ups", verified: "Verified", checkouts_started: "Checkouts started", subscribed: "New subscribers", finder_searches: "Finder searches", newsletter_joins: "List sign-ups" };
const REPORTS = ["visitors", "pages", "referrers", "acquisition", "signups", "popups"];

function Realtime() {
  const q = useApi("/admin/analytics/realtime");
  return <Card title="Right now" testid="an-realtime" actions={<button className="a-link-btn" onClick={q.reload} data-testid="an-realtime-refresh">Refresh</button>}>
    <DataState q={q}>{(d) => <><div className="a-tiles"><StatTile label={`Active in the last ${d.window_minutes} minutes`} value={d.active_now} testid="an-active" /><StatTile label="Signed in" value={d.signed_in} />{Object.entries(d.devices).map(([k, v]) => <StatTile key={k} label={k} value={v} />)}</div>
      {d.pages.length ? <ResponsiveTable testid="an-rt-pages" rowKey={(r) => r.path} rows={d.pages} columns={[{ key: "path", label: "Page", primary: true }, { key: "visitors", label: "Visitors" }]} /> : <p className="muted">No page views in the last few minutes.</p>}</>}</DataState>
  </Card>;
}

function Compare({ days }) {
  const q = useApi("/admin/analytics/compare", { days });
  return <Card title={`Last ${days} days vs the ${days} before`} testid="an-compare"><DataState q={q}>{(d) => <>
    <ResponsiveTable testid="an-compare-table" rowKey={(r) => r.metric} rows={d.metrics} columns={[{ key: "metric", label: "Measure", primary: true, render: (r) => <b>{LABEL[r.metric] || r.metric}</b> }, { key: "now", label: "Now" }, { key: "previous", label: "Before" }, { key: "change", label: "Change", render: (r) => <span className={r.change > 0 ? "up" : r.change < 0 ? "down" : ""}>{ch(r.change)}</span> }]} />
    {!!d.revenue.length && <ResponsiveTable testid="an-compare-revenue" rowKey={(r) => r.currency} rows={d.revenue} columns={[{ key: "currency", label: "Revenue", primary: true, render: (r) => <b>{r.currency.toUpperCase()}</b> }, { key: "n", label: "Now", render: (r) => (r.now_cents / 100).toFixed(2) }, { key: "p", label: "Before", render: (r) => (r.previous_cents / 100).toFixed(2) }, { key: "c", label: "Change", render: (r) => ch(r.change) }]} />}
  </>}</DataState></Card>;
}

function Sources({ days }) {
  const q = useApi("/admin/analytics/acquisition", { days });
  return <Card title="Where people come from" testid="an-sources"><DataState q={q} empty="No campaign links yet. Add utm_source to links you share, for example ?utm_source=twitter.">{(d) => <><p className="muted small">{d.note}</p>{d.rows.length ? <ResponsiveTable testid="an-sources-table" rowKey={(r) => r.source + r.medium + r.campaign} rows={d.rows} columns={[{ key: "source", label: "Source", primary: true, render: (r) => <span className="a-person"><b>{r.source}</b><small>{r.medium} · {r.campaign}</small></span> }, { key: "visitors", label: "Visitors" }, { key: "signups", label: "Sign-ups" }, { key: "paid", label: "Paying" }, { key: "r", label: "Sign-up rate", render: (r) => pct(r.signup_rate) }]} /> : <p className="muted">No campaign links or referrals yet. Add utm_source to links you share.</p>}</>}</DataState></Card>;
}

function EmailHealth({ days }) {
  const q = useApi("/admin/analytics/email", { days });
  return <Card title="E-mail health" testid="an-email"><DataState q={q}>{(d) => <><div className="a-tiles"><StatTile label="Sent" value={d.sent} testid="an-email-sent" /><StatTile label="Bounce rate" value={pct(d.bounce_rate)} tone={d.bounce_rate > 0.02 ? "down" : undefined} /><StatTile label="Complaint rate" value={pct(d.complaint_rate)} tone={d.complaint_rate > 0.001 ? "down" : undefined} /><StatTile label="Blocked addresses" value={d.suppressed} /></div><p className="muted small">{d.note}</p>
    {d.templates.length > 0 && <ResponsiveTable testid="an-email-table" rowKey={(r) => r.template} rows={d.templates} columns={[{ key: "template", label: "E-mail", primary: true }, { key: "sent", label: "Sent" }, { key: "failed", label: "Failed" }, { key: "skipped", label: "Skipped" }, { key: "bounced", label: "Bounced" }]} />}</>}</DataState></Card>;
}

function PopupsList() {
  const q = useApi("/admin/analytics/popups");
  return <Card title="Popups side by side" testid="an-popups"><DataState q={q}>{(d) => (d.rows.length ? <ResponsiveTable testid="an-popups-table" rows={d.rows} columns={[{ key: "name", label: "Popup", primary: true, render: (r) => <span className="a-person"><b>{r.name}</b><small>{r.state}{r.ab_group ? ` · A/B ${r.ab_group}` : ""}</small></span> }, { key: "view", label: "Views" }, { key: "c", label: "Click rate", render: (r) => pct(r.click_rate) }, { key: "s", label: "Sign-up rate", render: (r) => pct(r.submit_rate) }, { key: "d", label: "Closed", render: (r) => pct(r.dismiss_rate) }]} /> : <p className="muted">No popups yet.</p>)}</DataState></Card>;
}

function ListGrowth({ days }) {
  const q = useApi("/admin/analytics/newsletter", { days });
  return <Card title="E-mail list growth" testid="an-list"><DataState q={q}>{(d) => <><div className="a-tiles"><StatTile label="Confirmed" value={d.counts.confirmed} tone="up" /><StatTile label="Waiting" value={d.counts.pending} /><StatTile label="Unsubscribed" value={d.counts.unsubscribed} /></div>
    {d.by_source.length ? <ResponsiveTable testid="an-list-table" rowKey={(r) => r.source} rows={d.by_source} columns={[{ key: "source", label: "From", primary: true }, { key: "started", label: "Signed up" }, { key: "confirmed", label: "Confirmed" }]} /> : <p className="muted">No sign-ups in this period.</p>}</>}</DataState></Card>;
}

export default function Analytics() {
  const toast = useToast();
  const [days, setDays] = useState(30);
  const [rep, setRep] = useState("visitors");
  const exp = async () => { try { await download(`/admin/analytics/export?report=${rep}&days=${days}`, `${rep}-${days}d.csv`); } catch (x) { toast(x.message, "err"); } };
  return (
    <div className="a-page" data-testid="admin-analytics">
      <PageHead title="Analytics" lead="Our own counts, no third-party trackers. Do Not Track is respected."
        actions={<div className="a-inline-actions">
          <select aria-label="Period" value={days} onChange={(e) => setDays(Number(e.target.value))} data-testid="an-days">{[7, 30, 90].map((d) => <option key={d} value={d}>Last {d} days</option>)}</select>
          <select aria-label="Report to export" value={rep} onChange={(e) => setRep(e.target.value)} data-testid="an-report">{REPORTS.map((r) => <option key={r}>{r}</option>)}</select>
          <button className="btn btn--secondary btn--sm" onClick={exp} data-testid="an-export">Export CSV</button></div>} />
      <div className="a-grid2">
        <Realtime />
        <Compare days={days} />
        <Sources days={days} />
        <ListGrowth days={days} />
        <EmailHealth days={days} />
        <PopupsList />
      </div>
    </div>
  );
}
