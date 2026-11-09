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

function Chart({ bins, hi }) {
  const maxN = Math.max(...bins.map((b) => b.n));
  const ticks = [0.4, 0.6, 0.8, 1];
  return (
    <figure className="tr-chart card" data-testid="tr-chart">
      <figcaption className="tr-chart-head"><h2 className="k-sec">Said vs happened</h2><small className="k-faint">Dots on the dashed line = honest numbers</small></figcaption>
      <svg viewBox="0 0 320 240" role="img" aria-label={bins.map((b) => `${pct(b.stated)} said, ${pct(b.actual)} happened`).join("; ")}>
        {/* The reference's chart: a soft wash under the line rather than bare dots on a grid, and
            the gridlines running vertically from the axis a reader reads across. The dashed
            diagonal stays, because on this chart it is not decoration -- it is the line a
            perfectly calibrated model sits on, and the whole figure is "how far from it are we". */}
        <defs>
          <linearGradient id="tr-fill" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" className="tr-fill-top" />
            <stop offset="100%" className="tr-fill-bot" />
          </linearGradient>
        </defs>
        {ticks.map((t) => (
          <g key={t}>
            <line x1={X(t)} x2={X(t)} y1={Y(1)} y2={Y(LO)} className="tr-vgrid" />
            <text x="34" y={Y(t) + 4} textAnchor="end">{of100(t)}%</text>
            <text x={X(t)} y="232" textAnchor="middle">{of100(t)}%</text>
          </g>
        ))}
        <polygon className="tr-area"
                 points={`${X(bins[0].stated)},${Y(LO)} ${bins.map((b) => `${X(b.stated)},${Y(b.actual)}`).join(" ")} ${X(bins[bins.length - 1].stated)},${Y(LO)}`} />
        <line x1={X(LO)} y1={Y(LO)} x2={X(1)} y2={Y(1)} className="tr-diag" />
        <polyline points={bins.map((b) => `${X(b.stated)},${Y(b.actual)}`).join(" ")} className="tr-line" />
        {bins.map((b) => <circle key={b.from} cx={X(b.stated)} cy={Y(b.actual)} r={4 + 6 * Math.sqrt(b.n / maxN)} className="tr-dot" data-testid={`tr-dot-${b.from}`} />)}
        {/* The band the page leads on, marked where it sits, the way the reference marks its
            figure on the curve. */}
        {hi && <g className="tr-mark">
          <circle cx={X(hi.stated)} cy={Y(hi.actual)} r="5" className="tr-mark-dot" />
          <rect x={X(hi.stated) - 26} y={Y(hi.actual) - 30} width="52" height="19" rx="9.5" className="tr-mark-pill" />
          <text x={X(hi.stated)} y={Y(hi.actual) - 17} textAnchor="middle" className="tr-mark-tx">{of100(hi.actual)}%</text>
        </g>}
      </svg>
      <p className="k-faint k-small">Each dot is a group of forecasts by what we said (across) and how often it happened (up). Bigger dots hold more forecasts.</p>
    </figure>
  );
}

// The tile used to take the tier's own colour, so the biggest number read as the best one. On real
// data a lime "90 of 100" can be WORSE calibrated than a violet "64 of 100": the colour was grading
// magnitude, not accuracy. It now says whether the gap is inside what a sample this size produces.
//
// It says it in a WORD as well as in a colour. Three states told apart by hue alone is the one
// thing docs/03 forbids everywhere else in this product (the tier badge prints its name, the run
// strip prints its count, the fixture row draws a tick), and the state being graded here -- are we
// honest about this tier -- is the whole reason the page exists.
function calOf(v) {
  const se = Math.sqrt(Math.max(v.stated * (1 - v.stated), 1e-6) / Math.max(v.n, 1));
  if (Math.abs(v.actual - v.stated) <= 1.96 * se) return { cls: "tr-cal tr-cal--ok", word: "in line with what we said" };
  return v.actual < v.stated
    ? { cls: "tr-cal tr-cal--under", word: "less often than we said" }
    : { cls: "tr-cal tr-cal--over", word: "more often than we said" };
}

// How much of a said-vs-happened gap is real, and how much is the sample being small.
function Reliability({ b, whole }) {
  const se = Math.sqrt(Math.max(b.stated * (1 - b.stated), 1e-6) / Math.max(b.n, 1));
  const margin = 1.96 * se;                       // the band chance alone would produce
  const gap = b.actual - b.stated;
  const real = Math.abs(gap) > margin;
  const dir = gap > 0 ? "more often than we said" : "less often than we said";
  return (
    <p className="tr-rel" data-testid="tr-reliability">
      From <b>{b.n.toLocaleString()}</b> forecast{b.n === 1 ? "" : "s"}{whole ? "" : " in that band"}, so the margin is
      about <b>±{Math.round(margin * 100)} points</b>.{" "}
      {real
        ? <>The gap is wider than that: these happen {dir}{gap > 0 ? ", so the number is cautious" : ", which is the gap to watch"}.</>
        : <>The gap is inside that margin, so it is what a sample this size produces on its own.</>}
    </p>
  );
}

function Body({ d }) {
  // The headline rested on the whole record: "we said 29% on average, it happened 31%". Two
  // faults, and the second is the serious one.
  //
  // It is dominated by the mass of low-likelihood lines, where saying 20% and seeing 22% is
  // neither a skill nor a claim anyone acted on -- a conservative model scores well there by
  // being timid. And a mean over every band can be RIGHT while every band inside it is wrong:
  // overconfident at the top and underconfident at the bottom cancel to a two-point gap that
  // reads as healthy. So the number that looked like the strongest summary was the one that
  // could hide the most.
  //
  // The page now leads on the band a reader actually uses -- when we said something was likely,
  // how often was it -- and keeps the whole record underneath as context rather than as the
  // claim. Stated as calibration, not as a score: "we said 93%, it happened 92%" is the honest
  // shape of a good answer, and framing it as a win rate would invite 92 to be read as a grade.
  const all = d.overall;
  const hi = d.high;
  const since = d.since ? utc(d.since).toLocaleDateString(undefined, { month: "long", year: "numeric" }) : null;
  return (
    <>
      <div className="tr-hero">
        {hi ? <p className="tr-head" data-testid="tr-headline">When we said <b>{pct(hi.from)}</b> or more, it happened <em>{pct(hi.actual)}</em> of the time. We said <b>{pct(hi.stated)}</b> on those <b>{hi.n.toLocaleString()}</b> forecasts.</p>
          : all ? <p className="tr-head" data-testid="tr-headline">Across <b>{all.n.toLocaleString()}</b> settled forecasts we said <b>{pct(all.stated)}</b> on average. It happened <em>{pct(all.actual)}</em> of the time.</p>
          : <p className="tr-head" data-testid="tr-headline">{d.scored} forecasts scored so far.</p>}
        {/* A gap between what we said and what happened means nothing without the count behind it.
            At 30 forecasts a 14-point gap is what chance alone produces; at 100 it is real. The
            page held `n` and printed only the total, so a reader could not tell the two apart and
            had to assume the worst. It now says the count, the margin, and which of the two this
            is -- and names the direction, because promising less than we deliver is the safe
            side of a miss and reads as a fault when it is not. */}
        {hi ? <Reliability b={hi} whole /> : all ? <Reliability b={all} whole /> : null}
        {hi && all && (
          <p className="k-faint tr-all" data-testid="tr-overall">
            Across all <b>{all.n.toLocaleString()}</b> settled forecasts, including the unlikely ones, we said{" "}
            <b>{pct(all.stated)}</b> and it happened <b>{pct(all.actual)}</b>. That average is the weaker
            measure: most lines sit low, and being right about an unlikely thing is easy to do by being timid.
          </p>
        )}
        <p className="k-faint">{since ? `Since ${since}. ` : ""}Counted when the player appeared{d.not_played ? <>; <b>{d.not_played.toLocaleString()}</b> line{d.not_played === 1 ? "" : "s"} where he did not play are left out of this page, and counted as missed when a tier is earned</> : null}.</p>
      </div>
      <div className="tr-grid2">
        {d.bins.length ? <Chart bins={d.bins} hi={hi} /> : <EmptyState icon="bar-chart" title="Not enough in each band yet" testid="tr-no-bins">We draw the chart once each band holds 30 forecasts.</EmptyState>}
        <div className="tr-tiers" data-testid="tr-tiers">
          {Object.entries(d.tiers).map(([t, v]) => {
            const cal = calOf(v);
            return (
              <div key={t} className="tr-tier card" style={{ "--tone": `var(--tier-${t.toLowerCase()})` }} data-testid={`tr-tier-${t}`}>
                <span><TierBadge tier={t} testid={`tr-tier-badge-${t}`} /><small className="k-faint">{v.n.toLocaleString()} forecasts</small></span>
                <span className="tr-of">
                  <b className={cal.cls}>{v.n >= 100 ? `${of100(v.actual)} of 100` : `${Math.round(v.actual * v.n)} of ${v.n}`}</b>
                  <small className="k-faint">came true · we said {pct(v.stated)}</small>
                  <small className="k-faint" data-testid={`tr-tier-cal-${t}`}>{cal.word}</small>
                </span>
              </div>
            );
          })}
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
      {/* The filters only appear once there is something to filter. Nine controls over "0 so far"
          is the screen that has to establish trust opening by asking the reader to narrow nothing. */}
      {q.data?.ready && <div className="tr-filters">
        <ChipsRow label="League" value={league} onChange={(v) => set("league", v)} testid="tr-league" options={[{ id: "", label: "All leagues" }, ...leagues.map((l) => ({ id: l.id, label: l.name }))]} />
        <ChipsRow label="Market" value={stat} onChange={(v) => set("stat", v)} testid="tr-market" options={MARKETS} />
      </div>}
      {q.loading && !q.data ? <Skeleton shape="card" count={3} testid="tr-loading" />
        : q.error ? <ErrorState message="We could not load the track record." onRetry={q.reload} testid="tr-error" />
        /* "Nothing to show yet, and here is why" is an empty state, and the kit has one. This was a
           card of its own with its own heading, its own grey paragraph class and its own left edge,
           sitting where every other screen in the product puts an EmptyState -- on the page whose
           job is to look like the rest of the product only more carefully. The progress bar and the
           way out stay; they are the empty state's "next step". */
        : !q.data.ready ? (
          <EmptyState icon="clock" title="Collecting results" testid="tr-not-ready" action={<>
            <div className="lbar-track" style={{ "--tone": "var(--brand)", width: "min(320px, 100%)" }}><span className="lbar-fill" style={{ width: `${Math.min(100, (q.data.scored / q.data.needed) * 100)}%` }} /></div>
            {(league || stat) && <button type="button" className="btn btn--secondary btn--sm" onClick={() => setSp({}, { replace: true })} data-testid="tr-clear">Show all leagues and markets</button>}
          </>}>
            We show the record once {q.data.needed} forecasts{league || stat ? " for this pick" : ""} have been scored, so the numbers mean something. {q.data.scored} so far.
          </EmptyState>
        ) : <Body d={q.data} />}
    </section>
  );
}
