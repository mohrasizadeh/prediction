// Admin > Waitlist (docs/68 "Measuring it"): is the page an advert points at doing its one job?
//
// Read top to bottom as the visitor travels: how many came, how far they read, where they dropped
// out between arriving and signing up, and which source sent the ones who signed up. Every number is
// our own first-party count (backend/waitlist_stats.py); nothing here comes from a third-party tag.
import { useState } from "react";
import { useApi } from "../lib/useApi";
import { useToast } from "../components/Ui";
import Icon from "../components/Icon";
import { Bars, Card, DataState, PageHead, ResponsiveTable, StatTile, num } from "./parts";

const pct = (v) => (v == null ? "–" : `${(v * 100).toFixed(v > 0 && v < 0.1 ? 1 : 0)}%`);
const change = (c) => (c == null ? "No earlier data" : `${c > 0 ? "+" : ""}${Math.round(c * 100)}% vs the period before`);
const SOURCES = ["instagram", "x", "facebook", "tiktok", "reddit", "whatsapp", "newsletter"];

/** One labelled bar. Width is the share; the count is printed beside it, so the bar never has to
 *  carry the number on its own. */
function Meter({ label, share, count, testid }) {
  return (
    <li className="wl-meter" data-testid={testid}>
      <span className="wl-meter-label">{label}</span>
      <span className="wl-meter-track" aria-hidden="true"><span style={{ width: `${Math.max(0, Math.min(1, share || 0)) * 100}%` }} /></span>
      <span className="wl-meter-val"><b>{pct(share)}</b><small>{num(count)}</small></span>
    </li>
  );
}

/** Tagged links, so the sources table below has something to tell apart. Without utm_source a post
 *  on Instagram opened in the Instagram app usually arrives with no referrer and reads as "direct". */
function LinkBuilder() {
  const toast = useToast();
  const [source, setSource] = useState("instagram");
  const [campaign, setCampaign] = useState("");
  const base = `${window.location.origin}/waitlist`;
  const clean = (s) => s.toLowerCase().replace(/[^a-z0-9_.-]+/g, "-").replace(/^-|-$/g, "").slice(0, 40);
  const q = new URLSearchParams({ utm_source: clean(source) || "direct", utm_medium: "social", ...(clean(campaign) ? { utm_campaign: clean(campaign) } : {}) });
  const url = `${base}?${q}`;
  const copy = async () => { try { await navigator.clipboard.writeText(url); toast("Link copied"); } catch { toast("Select the link and copy it", "err"); } };
  return (
    <Card title="A link for each place you post" testid="wl-links">
      <p className="muted small">Instagram, TikTok and WhatsApp usually send no referrer, so their visitors look like “direct”. Put the tagged link in the bio or the post and they count under their own name.</p>
      <div className="wl-link-row">
        <label className="field"><span>Where</span>
          <input list="wl-sources" value={source} onChange={(e) => setSource(e.target.value)} maxLength={40} data-testid="wl-link-source" />
          <datalist id="wl-sources">{SOURCES.map((s) => <option key={s} value={s} />)}</datalist></label>
        <label className="field"><span>Campaign (optional)</span>
          <input value={campaign} onChange={(e) => setCampaign(e.target.value)} placeholder="e.g. derby-weekend" maxLength={40} data-testid="wl-link-campaign" /></label>
      </div>
      <div className="wl-link-out">
        <code data-testid="wl-link-url">{url}</code>
        <button className="btn btn--secondary btn--sm" onClick={copy} data-testid="wl-link-copy"><Icon name="copy" size={16} />Copy</button>
      </div>
    </Card>
  );
}

export default function WaitlistStats() {
  const [days, setDays] = useState(30);
  const q = useApi("/admin/waitlist/analytics", { days });
  return (
    <div className="a-page" data-testid="admin-waitlist">
      <PageHead title="Waitlist" lead="The landing page adverts point at: who came, how far they read, where they came from, and who signed up."
        actions={<div className="a-inline-actions">
          <select aria-label="Period" value={days} onChange={(e) => setDays(Number(e.target.value))} data-testid="wl-days">
            {[7, 30, 90].map((d) => <option key={d} value={d}>Last {d} days</option>)}</select>
          <button className="btn btn--secondary btn--sm" onClick={q.reload} data-testid="wl-refresh"><Icon name="refresh" size={16} />Refresh</button>
          <a className="btn btn--secondary btn--sm" href="/waitlist" target="_blank" rel="noreferrer" data-testid="wl-open"><Icon name="external" size={16} />Open the page</a>
        </div>} />
      <DataState q={q}>{(d) => {
        const t = d.totals;
        const quiet = !t.views && !t.signups;
        return (
          <>
            <div className="a-tiles-grid">
              <StatTile label="Visitors" value={num(t.visitors)} sub={change(d.change.visitors)} tone={d.change.visitors < 0 ? "down" : undefined} testid="wl-tile-visitors" />
              <StatTile label="Page views" value={num(t.views)} sub={change(d.change.views)} testid="wl-tile-views" />
              <StatTile label="Sign-ups" value={num(t.signups)} sub={change(d.change.signups)} tone={d.change.signups < 0 ? "down" : t.signups ? "up" : undefined} testid="wl-tile-signups" />
              <StatTile label="Sign-up rate" value={pct(t.conversion)} sub={d.previous.conversion == null ? "No earlier data" : `${pct(d.previous.conversion)} the period before`} testid="wl-tile-rate" />
              <StatTile label="On the list" value={num(t.members)} sub={`${num(t.confirmed)} confirmed in this period · ${num(t.waiting)} waiting`} testid="wl-tile-members" />
              <StatTile label="Right now" value={num(t.live)} sub="on the page in the last 30 minutes" testid="wl-tile-live" />
            </div>
            {quiet && <p className="muted" data-testid="wl-quiet">No visits recorded in the last {d.window_days} days. Visits are counted from the moment this version of the page went live; share a tagged link below and they will start to appear.</p>}
            <div className="a-grid2">
              <Bars title="Visitors per day" data={d.by_day} y="visitors" testid="wl-chart-visitors" />
              <Bars title="Sign-ups per day" data={d.by_day} y="signups" testid="wl-chart-signups" />

              <Card title="From visit to sign-up" testid="wl-funnel">
                <ul className="wl-meters">
                  {d.funnel.map((f) => <Meter key={f.step} label={f.step} share={f.of_visitors} count={f.count} testid={`wl-funnel-${f.step.split(" ")[0].toLowerCase()}`} />)}
                </ul>
                <p className="muted small">Each step is a share of everyone who visited.{t.signups ? ` ${pct(t.conversion)} of visitors signed up.` : ""}</p>
              </Card>

              <Card title="How far people read" testid="wl-scroll">
                <ul className="wl-meters">
                  {d.scroll.map((s) => <Meter key={s.depth} label={s.depth === 100 ? "To the end" : `${s.depth}% of the page`} share={s.share} count={s.visitors} testid={`wl-depth-${s.depth}`} />)}
                </ul>
                <h3 className="wl-sub">Sections they reached</h3>
                <ul className="wl-meters">
                  {d.sections.map((s) => <Meter key={s.section} label={s.label} share={s.share} count={s.visitors} testid={`wl-section-${s.section}`} />)}
                </ul>
              </Card>

              <Card title="Where they came from" testid="wl-sources">
                {d.sources.length ? (
                  <ResponsiveTable testid="wl-sources-table" rowKey={(r) => r.source} rows={d.sources} columns={[
                    { key: "source", label: "Source", primary: true, render: (r) => <b>{r.source}</b> },
                    { key: "visitors", label: "Visitors", render: (r) => num(r.visitors) },
                    { key: "signups", label: "Sign-ups", render: (r) => num(r.signups) },
                    { key: "rate", label: "Rate", render: (r) => pct(r.rate) },
                    { key: "confirmed", label: "Confirmed", render: (r) => num(r.confirmed) },
                  ]} />
                ) : <p className="muted">No visits in this period yet.</p>}
                {Object.keys(d.devices).length > 0 && (
                  <p className="muted small" data-testid="wl-devices">
                    {Object.entries(d.devices).sort((a, b) => b[1] - a[1]).map(([k, v]) => `${k} ${pct(v / Math.max(1, t.visitors))}`).join(" · ")}
                  </p>
                )}
              </Card>

              <Card title="Campaigns" testid="wl-campaigns">
                {d.campaigns.length ? (
                  <ResponsiveTable testid="wl-campaigns-table" rowKey={(r) => r.source + r.campaign} rows={d.campaigns} columns={[
                    { key: "campaign", label: "Campaign", primary: true, render: (r) => <span className="a-person"><b>{r.campaign}</b><small>{r.source}</small></span> },
                    { key: "visitors", label: "Visitors", render: (r) => num(r.visitors) },
                    { key: "signups", label: "Sign-ups", render: (r) => num(r.signups) },
                    { key: "rate", label: "Rate", render: (r) => pct(r.rate) },
                  ]} />
                ) : <p className="muted">No campaign links used yet. Add a campaign name in the link builder to compare posts.</p>}
              </Card>

              <LinkBuilder />
            </div>
            <p className="muted small" data-testid="wl-note">{d.note}</p>
          </>
        );
      }}</DataState>
    </div>
  );
}
