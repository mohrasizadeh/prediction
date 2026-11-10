// "Most likely" (docs/63): one screen, one question -- what is likeliest in the next few hours.
//
// The feed answers "what differs most from usual" and leads on the edge. A reader an hour before
// kick-off is asking something else, and answering the second question on a screen built for the
// first is what produced rows reading "56% to take 2 shots", which tell a reader nothing they can
// use. This screen leads on the number, sorts by it, and shows nothing under engine.watch_min.
//
// Three things on it are new and therefore explained in situ, next to a live specimen (the key
// strip): the range bar, the two-tone run strip, and the line stepper.
import { useCallback, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { useApi } from "../lib/useApi";
import { DISCLAIMER, pct } from "../lib/copy";
import { useTitle } from "../components/Football";
import { EmptyState, ErrorState, ForecastRow, Skeleton } from "../components/ui";

const WINDOWS = [4, 12, 24];

export function Likely() {
  useTitle("Most likely", { description: "The forecasts we rate highest right now, across every match we cover." });
  const [win, setWin] = useState(4);
  const [confirmed, setConfirmed] = useState(false);
  const [open, setOpen] = useState(null);
  const q = useApi("/likely", { within_h: win, limit: 60 });
  // Only for the beta line in the footer: until 300 forecasts are scored there is no record to
  // state, and the page says so rather than implying one.
  const rec = useApi("/track-record");
  const toggle = useCallback((id) => setOpen((o) => (o === id ? null : id)), []);

  const floor = q.data?.floor ?? 0.6;
  const rows = useMemo(() => {
    const all = q.data?.rows || [];
    return confirmed ? all.filter((r) => r.lineup_badge === "confirmed" || r.scope === "team") : all;
  }, [q.data, confirmed]);
  const confN = (q.data?.rows || []).filter((r) => r.lineup_badge === "confirmed").length;
  const matches = new Set(rows.map((r) => r.match_iid)).size;

  const head = (
    <>
      <h1 className="h1">Most likely</h1>
      <p className="lk-lede">
        The likeliest <b>things to happen</b> in the <b>{matches} match{matches === 1 ? "" : "es"}</b>{" "}
        kicking off in the next {win} hours{confirmed ? <>, <b>confirmed lineups only</b></> : null}.
      </p>
      <div className="lk-bar" data-testid="lk-filters">
        <button type="button" className="lk-chip" aria-pressed={confirmed} onClick={() => setConfirmed((v) => !v)} data-testid="lk-confirmed">
          Only confirmed starters <small>{confN}</small>
        </button>
        {WINDOWS.map((h) => (
          <button key={h} type="button" className="lk-chip" aria-pressed={win === h} onClick={() => setWin(h)} data-testid={`lk-win-${h}`}>
            Next {h}h
          </button>
        ))}
      </div>
    </>
  );

  if (q.loading) return <section className="lk" data-testid="likely-page">{head}<Skeleton shape="row" count={6} /></section>;
  if (q.error) return <section className="lk" data-testid="likely-page">{head}<ErrorState onRetry={q.reload} /></section>;

  return (
    <section className="lk" data-testid="likely-page">
      {head}
      <div className="lk-key" data-testid="lk-key">
        <span className="lk-keyit">
          <svg width="54" height="9" aria-hidden="true">
            <rect x="0" y="4" width="54" height="1" fill="var(--lk-rule)" />
            <rect x="33" y="1" width="16" height="7" rx="2" fill="var(--brand)" />
          </svg>
          <span><b>The bar is the range</b>, and the number under it says so exactly.</span>
        </span>
        <span className="lk-keyit">
          <svg width="40" height="26" aria-hidden="true">
            <rect x="0" y="12" width="7" height="14" rx="2" fill="var(--brand)" />
            <rect x="0" y="12" width="7" height="3" fill="var(--tier-strong)" />
            <rect x="9" y="19" width="7" height="7" rx="2" fill="var(--lk-rule)" />
            <rect x="18" y="4" width="7" height="22" rx="2" fill="var(--brand)" />
            <rect x="18" y="4" width="7" height="11" fill="var(--tier-strong)" />
            <rect x="27" y="20" width="7" height="6" rx="2" fill="var(--lk-rule)" />
            <rect x="0" y="15" width="40" height="1" fill="var(--text3)" />
          </svg>
          <span><b>Each bar darkens at the line.</b> Dark = what it took to reach it, bright = how far past. A bar entirely grey fell short.</span>
        </span>
        <span className="lk-keyit">
          <span className="lk-steps" aria-hidden="true" style={{ pointerEvents: "none" }}>
            <span className="lk-step" aria-checked="true">1+</span><span className="lk-step">2+</span>
          </span>
          <span><b>Tap to move the line.</b> Everything on the row follows.</span>
        </span>
      </div>

      {!rows.length ? (
        <EmptyState icon="calendar" title={`Nothing here reaches ${pct(floor)}.`}>
          We list a line once it reaches {pct(floor)}, and nothing in the next {win} hours does yet.
          Numbers move as team news arrives, so this often fills up in the last hour.
        </EmptyState>
      ) : (
        <table className="lk-tbl" data-testid="lk-table">
          <colgroup>
            <col className="lk-c-who" /><col className="lk-c-fx" /><col className="lk-c-mk" />
            <col className="lk-c-lk" /><col className="lk-c-run" /><col className="lk-c-lu" />
          </colgroup>
          <thead><tr>
            <th scope="col" className="lk-label">Player</th>
            <th scope="col" className="lk-label">Match</th>
            <th scope="col" className="lk-label">Line</th>
            <th scope="col" className="lk-label" aria-sort="descending">
              <div style={{ textAlign: "right" }}>How likely, and how sure ↓</div>
              <div className="lk-axis">
                <span style={{ left: 31.6 }}>60</span><span style={{ left: 94.8 }}>80</span><span style={{ left: 158 }}>100</span>
              </div>
            </th>
            <th scope="col" className="lk-label">Last 10 against that line</th>
            <th scope="col" className="lk-label">Lineup</th>
          </tr></thead>
          <tbody>
            {rows.map((f, i) => (
              <ForecastRow key={f.id || i} f={f} floor={floor} open={open === f.id} onToggle={() => toggle(f.id)} />
            ))}
          </tbody>
        </table>
      )}

      <p className="lk-foot">
        <span><b>Every percentage here assumes he is on the pitch.</b> Whether he will be is the
          Lineup column&apos;s job — two questions, two answers, so neither one can hide inside the other.</span>
        <span>{DISCLAIMER}</span>
        {!rec.data?.ready && (
          <span>Beta: the <Link to="/track-record">Track Record</Link> page will carry real results
            once {rec.data?.needed ?? 300} forecasts have been scored ({rec.data?.scored ?? 0} so far).</span>
        )}
      </p>
    </section>
  );
}

export default Likely;
