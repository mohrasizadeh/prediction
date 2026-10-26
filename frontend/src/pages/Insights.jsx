// Screens 3 and 11: Insights (strongest forecasts across leagues) and Track record (stated vs actual).
import { useState } from "react";
import { useApi } from "../lib/useApi";
import { pct } from "../lib/copy";
import { useAuth } from "../lib/auth";
import { Empty, ErrorBox, Loading } from "../components/States";
import { ForecastCard, Seg, Select, useTitle } from "../components/Football";

const STAT_OPTS = [{ id: "", label: "Every stat" }, { id: "shots", label: "Shots" }, { id: "sot", label: "Shots on target" }, { id: "tackles", label: "Tackles" }, { id: "corners", label: "Corners" }];

export function Insights() {
  const { entitlements } = useAuth();
  const q = useApi("/insights", { limit: 200 });
  const [f, setF] = useState({ stat: "", scope: "all", tier: "all" });
  useTitle("Insights");
  const rows = (q.data || []).filter((x) => (f.stat === "" || x.stat === f.stat) && (f.scope === "all" || x.scope === f.scope) && (f.tier === "all" || x.tier === f.tier));
  const set = (k) => (v) => setF({ ...f, [k]: v });
  const cap = entitlements?.insights_per_day;
  return (
    <section data-testid="insights-page">
      <h1>Insights</h1>
      <p className="muted lead">The strongest forecasts for upcoming matches, across every league we cover.</p>
      <div className="filters">
        <Select label="Stat" value={f.stat} onChange={set("stat")} options={STAT_OPTS} testid="ins-stat" />
        <Seg label="Scope" value={f.scope} onChange={set("scope")} options={[{ id: "all", label: "All" }, { id: "player", label: "Players" }, { id: "team", label: "Teams" }]} testid="ins-scope" />
        <Seg label="Tier" value={f.tier} onChange={set("tier")} options={[{ id: "all", label: "All" }, { id: "Strong", label: "Strong" }, { id: "Solid", label: "Solid" }]} testid="ins-tier" />
      </div>
      {q.loading && !q.data ? <Loading rows={4} /> : q.error ? <ErrorBox error={q.error} onRetry={q.reload} /> : !rows.length ? <Empty icon="sparkles">No insights match these filters. Try another stat or league.</Empty> : (
        <>
          <div className="fgrid">{rows.map((x) => <ForecastCard key={x.id} f={x} showMatch />)}</div>
          {cap >= 0 && (q.data || []).length >= cap && <p className="notice small" data-testid="ins-capped">Your plan shows {cap} insights a day.</p>}
        </>
      )}
    </section>
  );
}

function Bars({ rows }) {
  return (
    <div className="rel" data-testid="tr-bins">{rows.map((b) => (
      <div key={b.from} className="rel-row"><span className="muted small">{pct(b.from)}–{pct(b.to)}</span>
        <span className="rel-track"><span className="rel-stated" style={{ width: `${b.stated * 100}%` }} /><span className="rel-actual" style={{ width: `${b.actual * 100}%` }} /></span>
        <b>{pct(b.actual)}</b></div>
    ))}<p className="muted small"><span className="key key--stated" /> Stated <span className="key key--actual" /> Actual</p></div>
  );
}

export function TrackRecord() {
  const q = useApi("/track-record");
  useTitle("Track record");
  return (
    <section data-testid="track-record-page">
      <h1>Track record</h1>
      <p className="muted lead">Does the model deliver what it says? Every finished forecast is scored against what happened.</p>
      {q.loading && !q.data ? <Loading /> : q.error ? <ErrorBox error={q.error} onRetry={q.reload} /> : !q.data.ready ? (
        <div className="card" data-testid="tr-not-ready">
          <h2 className="h3">Collecting results</h2>
          <p className="muted">We show the record once {q.data.needed} forecasts have been scored, so the numbers mean something. {q.data.scored} so far.</p>
          <div className="lbar-track" style={{ "--tone": "var(--brand)" }}><span className="lbar-fill" style={{ width: `${Math.min(100, (q.data.scored / q.data.needed) * 100)}%` }} /></div>
          <p className="muted small">Beta: tiers and percentages may change as the record grows.</p>
        </div>
      ) : (
        <>
          <div className="tiles4" data-testid="tr-tiers">{Object.entries(q.data.tiers).map(([t, v]) => (
            <div key={t} className="stile"><span className="muted small">{t} · {v.n} forecasts</span><b>{pct(v.actual)}</b><small className="muted">reached · stated {pct(v.stated)}</small></div>
          ))}</div>
          <section className="card"><h2 className="h3">Reliability</h2>{q.data.bins.length ? <Bars rows={q.data.bins} /> : <p className="muted">Not enough forecasts in each band yet.</p>}</section>
          <p className="muted small">{q.data.scored} forecasts scored. Beta.</p>
        </>
      )}
    </section>
  );
}
