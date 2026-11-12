// Admin > Football data > API-Football (docs/81): one screen for the one provider.
// Replaces the two it takes over from: PitchAPI did history and depth, SportAPI did live, and this
// provider does both plus images and injuries. Three tabs, the tab in the URL so Back works.
import { useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { post } from "../lib/api";
import { useApi } from "../lib/useApi";
import { Tabs, useToast } from "../components/Ui";
import { ErrorBox, Loading } from "../components/States";
import Icon from "../components/Icon";
import { Card, Chip, PageHead, num } from "./parts";
import Explorer from "./Explorer";

const TABS = [
  { id: "status", label: "Key and quota" },
  { id: "mapping", label: "Statistic names" },
  { id: "explorer", label: "Endpoint explorer" },
];

function pct(used, cap) {
  if (!cap) return 0;
  return Math.min(100, Math.round((used / cap) * 100));
}

function Status() {
  const q = useApi("/admin/apifootball/status");
  const toast = useToast();
  const [busy, setBusy] = useState(false);
  const test = async () => {
    setBusy(true);
    try { const r = await post("/admin/keys/apifootball/test"); toast(r.ok ? `Key works · ${r.plan || "plan unknown"}` : "The key was refused", r.ok ? "ok" : "err"); q.reload(); }
    catch (x) { toast(x.message || "Could not test the key", "err"); } finally { setBusy(false); }
  };
  if (q.loading && !q.data) return <Loading rows={3} />;
  if (q.error) return <ErrorBox error={q.error} onRetry={q.reload} />;
  const d = q.data;
  if (!d.ok) {
    return (
      <Card>
        <h2>No working key yet</h2>
        <p className="a-muted">{d.reason === "key" ? "API-Football refused the key." : d.reason}{d.detail ? ` — ${d.detail}` : ""}</p>
        <p className="a-muted small">Save the key in Keys. Saving a new one also clears the pause and the breaker that a refused key sets.</p>
        <button className="btn btn--secondary btn--sm self-start" disabled={busy} onClick={test} data-testid="af-key-test">
          <Icon name="refresh" size={16} />{busy ? "Testing…" : "Test the key"}
        </button>
      </Card>
    );
  }
  const qt = d.quota || {};
  return (
    <div className="a-stack">
      <Card>
        <div className="a-row a-row--between">
          <div><h2>{d.plan || "Plan unknown"}</h2><small className="a-muted">{d.active ? "Active" : "Not active"}{d.ends ? ` · ends ${String(d.ends).slice(0, 10)}` : ""}</small></div>
          <Chip tone={d.active ? "ok" : "warn"}>{d.active ? "Active" : "Check it"}</Chip>
        </div>
        <dl className="a-dl a-dl--tight">
          <div><dt>Used today</dt><dd>{num(d.used_today)} of {num(d.limit_day)} ({pct(d.used_today, d.limit_day)}%)</dd></div>
          <div><dt>Their count, this minute</dt><dd>{qt.min_remaining == null ? "Not seen yet" : `${num(qt.min_remaining)} of ${num(qt.min_limit)} left`}</dd></div>
          <div><dt>Their count, today</dt><dd>{qt.day_remaining == null ? "Not seen yet" : `${num(qt.day_remaining)} left`}</dd></div>
        </dl>
        {/* Their rate-limit policy blocks spikes rather than throttling them, so the per-minute
            number is the one that matters operationally, not the daily one. */}
        <p className="a-muted small">
          The provider's own numbers, read from the headers of the last answer. They win over ours:
          if they say nothing is left, the next call is not sent. A spike can get a key blocked
          rather than throttled, so an empty per-minute allowance is a full stop.
        </p>
        <button className="btn btn--secondary btn--sm self-start" disabled={busy} onClick={test} data-testid="af-key-test">
          <Icon name="refresh" size={16} />{busy ? "Testing…" : "Test the key"}
        </button>
        <p className="a-muted small">Testing is free: it calls /status, which does not count against the quota it reports.</p>
      </Card>
    </div>
  );
}

function Mapping() {
  const q = useApi("/admin/apifootball/types");
  if (q.loading && !q.data) return <Loading rows={4} />;
  if (q.error) return <ErrorBox error={q.error} onRetry={q.reload} />;
  const d = q.data;
  if (!d.ok) {
    return (
      <Card>
        <h2>Nothing to check yet</h2>
        <p className="a-muted">
          {d.reason === "no_forecast_league" ? d.detail
            : d.reason === "no_finished_fixture" ? "That competition has no finished match yet, so there are no statistics to read."
            : `${d.reason}${d.detail ? ` — ${d.detail}` : ""}`}
        </p>
      </Card>
    );
  }
  return (
    <div className="a-stack">
      <Card>
        <h2>What a real answer carried</h2>
        <p className="a-muted small">
          This provider names a statistic with a display string, not a stable id, so a rename is
          invisible: the column goes null, the market drops under the coverage floor, and the feed
          looks like a quiet week. So the map is checked against a finished match rather than
          trusted. Read from league {d.league}, season {d.season}, fixture {d.fixture}.
        </p>
        {d.missing.length > 0 && (
          <div data-testid="af-types-missing">
            <h3>Mapped, but not in this match ({d.missing.length})</h3>
            <p className="a-muted small">Either renamed by the provider, or not tracked in this competition. Check one before changing the map.</p>
            <ul className="a-list">{d.missing.map((n) => <li key={n}><code>{n}</code></li>)}</ul>
          </div>
        )}
        {d.unmapped.length > 0 && (
          <div data-testid="af-types-unmapped">
            <h3>In this match, mapped to nothing ({d.unmapped.length})</h3>
            <p className="a-muted small">A free column we are not reading — or the new name of something in the list above.</p>
            <ul className="a-list">{d.unmapped.map((n) => <li key={n}><code>{n}</code></li>)}</ul>
          </div>
        )}
        {d.columns_unmapped.length > 0 && (
          <div data-testid="af-types-cols">
            <h3>Our columns with no name set ({d.columns_unmapped.length})</h3>
            <p className="a-muted small">
              <code>tackles</code> is deliberate: there is no team tackles statistic here, and the
              team total is summed from the players instead.
            </p>
            <ul className="a-list">{d.columns_unmapped.map((n) => <li key={n}><code>{n}</code></li>)}</ul>
          </div>
        )}
        {d.missing.length === 0 && d.unmapped.length === 0 && (
          <p data-testid="af-types-clean">Every name we map was in this match, and every name it carried is mapped.</p>
        )}
      </Card>
      <Card>
        <h2>The map</h2>
        <p className="a-muted small">Change it in Settings under Provider (<code>provider.apifootball.team_keys</code>).</p>
        <dl className="a-dl a-dl--tight">
          {Object.entries(d.map).map(([col, name]) => (
            <div key={col}><dt><code>{col}</code></dt><dd>{name ? <code>{name}</code> : <span className="a-muted">not set</span>}</dd></div>
          ))}
        </dl>
      </Card>
    </div>
  );
}

export default function APIFootball() {
  const { tab } = useParams();
  const nav = useNavigate();
  const pick = TABS.some((t) => t.id === tab) ? tab : "status";
  const Body = { status: Status, mapping: Mapping, explorer: Explorer }[pick];
  return (
    <div className="a-page" data-testid="admin-apifootball">
      <PageHead title="API-Football" lead="Fixtures, statistics, lineups, live scores, injuries and images — one provider for all of it. Competitions are added and switched on under Leagues." />
      <Tabs tabs={TABS} value={pick} onChange={(t) => nav(`/admin/data/apifootball/${t}`)} testid="apifootball-tabs" />
      <Body head={false} />
    </div>
  );
}
