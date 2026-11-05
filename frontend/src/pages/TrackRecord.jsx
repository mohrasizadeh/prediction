// Track record (docs/24 §12): one sentence anyone can read, a said-vs-happened chart, and each tier "of 100".
// Everything is read from scored forecasts; nothing shows until enough are scored.
import { useMemo } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { useApi } from "../lib/useApi";
import { pct } from "../lib/copy";
import { utc } from "../lib/time";
import { useTitle } from "../components/Football";
import { ChipsRow, EmptyState, ErrorState, Skeleton, TierBadge } from "../components/ui";

const MARKETS = [{ id: "", label: "All markets" }, { id: "shots", label: "Shots" }, { id: "sot", label: "On target" }, { id: "tackles", label: "Tackles" },
  { id: "corners", label: "Corners" }, { id: "yellow_cards", label: "Cards" }];
const LO = 0.4;
const X = (v) => 40 + ((Math.max(LO, Math.min(1, v)) - LO) / (1 - LO)) * 270;
const Y = (v) => 210 - ((Math.max(LO, Math.min(1, v)) - LO) / (1 - LO)) * 190;
const of100 = (v) => Math.round(v * 100);

function Chart({ bins }) {
  const maxN = Math.max(...bins.map((b) => b.n));
  const ticks = [0.4, 0.6, 0.8, 1];
  return (
    <figure className="tr-chart card" data-testid="tr-chart">
      <figcaption className="tr-chart-head"><h2 className="k-sec">Said vs happened</h2><small className="k-faint">Dots on the dashed line = honest numbers</small></figcaption>
      <svg viewBox="0 0 320 240" role="img" aria-label={bins.map((b) => `${pct(b.stated)} said, ${pct(b.actual)} happened`).join("; ")}>
        {ticks.map((t) => <g key={t}><line x1="40" x2="310" y1={Y(t)} y2={Y(t)} className="tr-grid" /><text x="34" y={Y(t) + 4} textAnchor="end">{of100(t)}%</text><text x={X(t)} y="232" textAnchor="middle">{of100(t)}%</text></g>)}
        <line x1={X(LO)} y1={Y(LO)} x2={X(1)} y2={Y(1)} className="tr-diag" />
        <polyline points={bins.map((b) => `${X(b.stated)},${Y(b.actual)}`).join(" ")} className="tr-line" />
        {bins.map((b) => <circle key={b.from} cx={X(b.stated)} cy={Y(b.actual)} r={4 + 6 * Math.sqrt(b.n / maxN)} className="tr-dot" data-testid={`tr-dot-${b.from}`} />)}
      </svg>
      <p className="k-faint k-small">Each dot is a group of forecasts by what we said (across) and how often it happened (up). Bigger dots hold more forecasts.</p>
    </figure>
  );
}

function Body({ d }) {
  const head = d.bins.find((b) => b.from === 0.7) || [...d.bins].sort((a, b) => b.n - a.n)[0];
  const since = d.since ? utc(d.since).toLocaleDateString(undefined, { month: "long", year: "numeric" }) : null;
  return (
    <>
      <div className="tr-hero">
        {head ? <p className="tr-head" data-testid="tr-headline">When we say {pct(head.stated)}, it happens <em>{pct(head.actual)}</em> of the time.</p>
          : <p className="tr-head" data-testid="tr-headline">{d.scored} forecasts scored so far.</p>}
        <p className="k-faint">Based on {d.scored.toLocaleString()} scored forecasts{since ? ` since ${since}` : ""}.</p>
      </div>
      <div className="tr-grid2">
        {d.bins.length ? <Chart bins={d.bins} /> : <EmptyState icon="bar-chart" title="Not enough in each band yet" testid="tr-no-bins">We draw the chart once each band holds 30 forecasts.</EmptyState>}
        <div className="tr-tiers" data-testid="tr-tiers">
          {Object.entries(d.tiers).map(([t, v]) => (
            <div key={t} className="tr-tier card" style={{ "--tone": `var(--tier-${t.toLowerCase()})` }} data-testid={`tr-tier-${t}`}>
              <span><TierBadge tier={t} testid={`tr-tier-badge-${t}`} /><small className="k-faint">{v.n.toLocaleString()} forecasts</small></span>
              <span className="tr-of"><b>{v.n >= 100 ? `${of100(v.actual)} of 100` : `${Math.round(v.actual * v.n)} of ${v.n}`}</b><small className="k-faint">came true</small></span>
            </div>
          ))}
          {!Object.keys(d.tiers).length ? <p className="k-faint">No forecasts with a tier have been scored yet.</p>
            : <p className="k-faint k-small" data-testid="tr-tier-note">{Object.values(d.tiers).reduce((s, v) => s + v.n, 0).toLocaleString()} of the {d.scored.toLocaleString()} scored forecasts had a tier; the rest are counted in the chart only.</p>}
          <Link to="/learn/how-we-score" className="k-link" data-testid="tr-how">How we score this</Link>
        </div>
      </div>
    </>
  );
}

export default function TrackRecord() {
  const [sp, setSp] = useSearchParams();
  const league = sp.get("league") || "";
  const stat = sp.get("stat") || "";
  const q = useApi("/track-record", { league: league || undefined, stat: stat || undefined });
  const lg = useApi("/leagues");
  const leagues = useMemo(() => (lg.data?.countries || []).flatMap((c) => c.leagues), [lg.data]);
  const set = (k, v) => { const n = new URLSearchParams(sp); if (v) n.set(k, v); else n.delete(k); setSp(n, { replace: true }); };
  useTitle("Track record");
  return (
    <section className="tr" data-testid="track-record-page">
      {/* The page had no visible title: the h1 was screen-reader only and the page opened with a
          small caption, so the one screen whose job is to establish trust began by whispering. */}
      <h1>Track record</h1>
      <p className="k-faint tr-sub">Updated as matches finish.</p>
      <div className="tr-filters">
        <ChipsRow label="League" value={league} onChange={(v) => set("league", v)} testid="tr-league" options={[{ id: "", label: "All leagues" }, ...leagues.map((l) => ({ id: l.id, label: l.name }))]} />
        <ChipsRow label="Market" value={stat} onChange={(v) => set("stat", v)} testid="tr-market" options={MARKETS} />
      </div>
      {q.loading && !q.data ? <Skeleton shape="card" count={3} testid="tr-loading" />
        : q.error ? <ErrorState message="We could not load the track record." onRetry={q.reload} testid="tr-error" />
        : !q.data.ready ? (
          <div className="card tr-wait" data-testid="tr-not-ready">
            <h2 className="h3">Collecting results</h2>
            <p className="muted">We show the record once {q.data.needed} forecasts{league || stat ? " for this pick" : ""} have been scored, so the numbers mean something. {q.data.scored} so far.</p>
            <div className="lbar-track" style={{ "--tone": "var(--brand)" }}><span className="lbar-fill" style={{ width: `${Math.min(100, (q.data.scored / q.data.needed) * 100)}%` }} /></div>
            {(league || stat) && <button type="button" className="btn btn--secondary btn--sm" onClick={() => setSp({}, { replace: true })} data-testid="tr-clear">Show all leagues and markets</button>}
          </div>
        ) : <Body d={q.data} />}
    </section>
  );
}
