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

// Usage leads. The question on opening this screen is "what is it doing and what has it cost me
// today", which is a thing that changes hourly; the key and the quota ceiling are settings, and a
// setting does not earn the first tab. The fallback below opens here too, so /admin/data/apifootball
// with no tab lands on the answer rather than on the configuration.
const TABS = [
  { id: "usage", label: "Usage and cache" },
  { id: "status", label: "Key and quota" },
  { id: "mapping", label: "Statistic names" },
  { id: "fresh", label: "Fresh start" },
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
      <div className="a-stack">
      <Card>
        <h2>No working key yet</h2>
        <p className="a-muted">{d.reason === "key" ? "API-Football refused the key." : d.reason}{d.detail ? ` — ${d.detail}` : ""}</p>
        <p className="a-muted small">Save the key in Keys. Saving a new one also clears the pause and the breaker that a refused key sets.</p>
        <button className="btn btn--secondary btn--sm self-start" disabled={busy} onClick={test} data-testid="af-key-test">
          <Icon name="refresh" size={16} />{busy ? "Testing…" : "Test the key"}
        </button>
      </Card>
      <OtherProviders />
      </div>
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
      <OtherProviders />
    </div>
  );
}

// The two providers API-Football replaces, with their switches. They are still running -- jobs.py
// calls PitchClient and the live tick calls SportAPI (docs/81 section 4) -- so turning either off
// stops the site getting that data. The switches exist so the owner can retire them deliberately,
// in order, once the replacement is backfilling.
// The two providers this one replaced. A CARD OF FACT, not a control.
//
// It used to offer a switch for each, reading `providers_on` from /admin/leagues. Both ends of that
// went stale: the route hard-codes `sportapi: false` now, so the chip read "Off" for ever and the
// button read "Turn SportAPI back on" -- and pressing it SUCCEEDED, because `sportapi.enabled` is
// still a registered setting. It toasted "Switched on", changed nothing a tick reads, and quietly
// desynced the setting from `features.live`, which settings_store keeps it mirrored to. A switch
// that reports success and does nothing is worse than one that 404s.
//
// Nothing calls either provider now (docs/88, docs/89), so there is nothing to turn on or off.
function OtherProviders() {
  return (
    <Card>
      <h2>The providers this one replaces</h2>
      <p className="a-muted small" data-testid="off-retired">
        PitchAPI and SportAPI are retired. Every football pull — history, the backfill, live scores,
        match events, lineups, crests and player photos — comes from API-Football and from nowhere
        else. Their screens and their calls are gone, so there is nothing here to switch.
      </p>
    </Card>
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


// Usage and cache, for THIS provider. The existing /usage counts every row in api_call_log and
// reads PitchAPI's breaker, which was right while one provider wrote that log.
function Usage() {
  const q = useApi("/admin/apifootball/usage");
  if (q.loading && !q.data) return <Loading rows={4} />;
  if (q.error) return <ErrorBox error={q.error} onRetry={q.reload} />;
  const d = q.data;
  const days = Object.entries(d.by_day || {});
  const peak = Math.max(1, ...days.map(([, n]) => n));
  const b = d.budget || {};
  return (
    <div className="a-stack">
      {d.paused_reason && <Card><h2>Ingest is paused</h2><p className="a-muted">{d.paused_reason}</p>
        <p className="a-muted small">Saving a key in Keys clears this and the breaker with it.</p></Card>}
      <Card>
        <h2>Today</h2>
        <dl className="a-dl a-dl--tight">
          <div><dt>Calls</dt><dd>{num(d.calls_today)} of {num(b.today)} we will spend</dd></div>
          <div><dt>Their count</dt><dd>{(d.quota || {}).day_remaining == null ? "Not seen yet" : `${num(d.quota.day_remaining)} left of ${num(d.quota.day_limit)}`}</dd></div>
          <div><dt>Kept in reserve</dt><dd>{num(b.reserve)} — so a live tick still has calls on a busy day</dd></div>
          <div><dt>Pace allowed</dt><dd>{b.per_minute ? `${num(b.per_minute)} a minute · ${b.per_second} a second` : "Not seen yet"}</dd></div>
          <div><dt>Answer time</dt><dd>{d.ms?.median == null ? "No calls yet" : `${num(d.ms.median)} ms median, ${num(d.ms.max)} ms slowest`}</dd></div>
        </dl>
        {/* Their per-second ceiling is in no header: it is derived from the per-minute figure
            (docs/82 section 2), which is why it can be shown at all. */}
        <p className="a-muted small">The per-second figure is derived from the per-minute one: the provider publishes it in their plan table but sends it in no header.</p>
      </Card>
      <Card>
        <h2>Last 14 days</h2>
        <ul className="a-bars" data-testid="af-usage-days">
          {days.map(([day, n]) => (
            <li key={day}><span className="a-bars-label">{day.slice(5)}</span>
              <span className="a-bars-track"><span className="a-bars-fill" style={{ width: `${(n / peak) * 100}%` }} /></span>
              <span className="a-bars-value">{num(n)}</span></li>
          ))}
        </ul>
      </Card>
      <Card>
        <h2>What today's calls were for</h2>
        {Object.keys(d.by_purpose || {}).length === 0 ? <p className="a-muted">No calls today.</p> : (
          <dl className="a-dl a-dl--tight">
            {Object.entries(d.by_purpose).sort((a, b2) => b2[1] - a[1]).map(([k, n]) => (
              <div key={k}><dt><code>{k}</code></dt><dd>{num(n)}</dd></div>
            ))}
          </dl>
        )}
        {Object.keys(d.by_status || {}).length > 0 && (
          <p className="a-muted small">Answers: {Object.entries(d.by_status).map(([k, n]) => `${k} x${n}`).join(" · ")}</p>
        )}
        {Object.keys(d.error_codes || {}).length > 0 && (
          <p className="small" data-testid="af-usage-errors">Errors: {Object.entries(d.error_codes).map(([k, n]) => `${k} x${n}`).join(" · ")}</p>
        )}
      </Card>
      <Card>
        <h2>Cache and breaker</h2>
        <dl className="a-dl a-dl--tight">
          <div><dt>Cached answers</dt><dd>{num(d.cache?.rows)} rows · {num(d.cache?.forever)} kept for ever · {num(d.cache?.expired)} stale</dd></div>
          <div><dt>Breaker</dt><dd>{d.breaker?.open ? `Open — ${d.breaker.reason}` : "Closed"}</dd></div>
          {d.other_provider_rows ? <div><dt>Older rows</dt><dd>{num(d.other_provider_rows)} from PitchAPI, which stop growing once the ingest moves</dd></div> : null}
        </dl>
        <p className="a-muted small">A finished match is cached for ever: it cannot change, so it is fetched once.</p>
      </Card>
    </div>
  );
}

// Fresh start. The owner's instinct was to have the host discard the database; this clears the
// football data and leaves the sign-in, the settings, the keys, the images, the Site Studio and
// billing alone (docs/83).
function Fresh() {
  const toast = useToast();
  const [mine, setMine] = useState(false);
  const q = useApi(`/admin/purge/plan?include_mine=${mine}`);
  const [typed, setTyped] = useState("");
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState(null);
  if (q.loading && !q.data) return <Loading rows={5} />;
  if (q.error) return <ErrorBox error={q.error} onRetry={q.reload} />;
  const d = q.data;
  const go = async () => {
    setBusy(true);
    try {
      const r = await post("/admin/purge", { confirm: typed, include_mine: mine });
      setDone(r); setTyped(""); toast(`${r.documents} rows cleared`); q.reload();
    } catch (x) { toast(x.message || "Could not clear", "err"); } finally { setBusy(false); }
  };
  return (
    <div className="a-stack">
      {done && <Card><h2>Cleared</h2><p>{num(done.documents)} rows across {Object.keys(done.by_collection || {}).length} collections.</p>
        <p className="a-muted small">Next: add competitions under Competitions, switch them on, and pick seasons to backfill.</p></Card>}
      <Card>
        <h2>Clear the football data</h2>
        <p className="a-muted">
          Everything a provider gave us, and everything the engine computed from it, including the
          crests, logos and player photos. The ids differ between providers, so none of it can be
          carried across — it is re-fetched, not migrated.
        </p>
        <p className="a-muted small">
          This is not a database drop. Your sign-in, the {num((d.keep || []).length)} kept collections
          below, your settings, your keys, the images already downloaded, the Site Studio and billing
          are all left alone. Your own uploaded images and video are in the Media library and stay;
          what goes is the crests and photos downloaded from a provider, which are keyed on ids that
          are about to change.
        </p>
        <dl className="a-dl a-dl--tight">
          <div><dt>Rows to clear</dt><dd>{num(d.total)} across {(d.clear || []).length} collections</dd></div>
          <div><dt>Ids</dt><dd>Never reused — the next league carries on from the last, so no kept row can resolve to a different entity</dd></div>
        </dl>
        {(d.unknown || []).length > 0 && (
          <div data-testid="af-purge-unknown">
            <h3>Collections nobody has classified ({d.unknown.length})</h3>
            <p className="a-muted small">These are left alone, because guessing wrong either keeps old data or deletes something that matters. Tell me about them and I will put them in a group.</p>
            <ul className="a-list">{d.unknown.map((c) => <li key={c}><code>{c}</code></li>)}</ul>
          </div>
        )}
        <details>
          <summary>What gets cleared ({(d.clear || []).length})</summary>
          <ul className="a-list">
            {(d.clear || []).map((r) => (
              <li key={r.collection}><code>{r.collection}</code> · {num(r.documents)} · <span className="a-muted">{r.group}</span></li>
            ))}
          </ul>
        </details>
        <details>
          <summary>What is kept ({(d.keep || []).length})</summary>
          <ul className="a-list">
            {(d.keep || []).map((r) => <li key={r.collection}><code>{r.collection}</code> · {num(r.documents)}</li>)}
          </ul>
        </details>
        <label className="check-row">
          <input type="checkbox" checked={mine} onChange={(e) => { setMine(e.target.checked); setTyped(""); }} data-testid="af-purge-mine" />
          Also clear what people saved: follows, notes, saved cards, combos and alerts ({num(d.mine_total)} rows)
        </label>
        <p className="a-muted small">Those point at ids that will not exist afterwards, so they would be dead links. They are the one group nobody can re-fetch, which is why they are a separate choice.</p>
        <label className="a-field">
          <span>Type <code>{d.confirm_phrase}</code> to confirm</span>
          <input value={typed} onChange={(e) => setTyped(e.target.value)} placeholder={d.confirm_phrase}
                 autoComplete="off" spellCheck={false} data-testid="af-purge-confirm" />
        </label>
        <button className="btn btn--danger self-start" disabled={busy || typed !== d.confirm_phrase}
                onClick={go} data-testid="af-purge-run">
          <Icon name="trash" size={16} />{busy ? "Clearing…" : `Clear ${num(d.total)} rows`}
        </button>
      </Card>
    </div>
  );
}

export default function APIFootball() {
  const { tab } = useParams();
  const nav = useNavigate();
  const pick = TABS.some((t) => t.id === tab) ? tab : "usage";
  const Body = { status: Status, usage: Usage, mapping: Mapping, fresh: Fresh, explorer: Explorer }[pick];
  return (
    <div className="a-page" data-testid="admin-apifootball">
      <PageHead title="API-Football" lead="Fixtures, statistics, lineups, live scores, injuries and images — one provider for all of it. Competitions are added and switched on under Leagues." />
      <Tabs tabs={TABS} value={pick} onChange={(t) => nav(`/admin/data/apifootball/${t}`)} testid="apifootball-tabs" />
      <Body head={false} />
    </div>
  );
}
