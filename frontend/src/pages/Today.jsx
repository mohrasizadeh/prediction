// Screen 1, Today (docs/01 section 5, docs/04). Built as the working example of a data screen:
// date strip, fixtures grouped by league, crests, win/draw/loss bar, insight count.
import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { useApi } from "../lib/useApi";
import { pct } from "../lib/copy";
import { utc } from "../lib/time";
import { Crest, LeagueMark } from "../components/Media";
import { Empty, ErrorBox, Loading } from "../components/States";
import LiveStatus from "../components/LiveStatus";

const iso = (d) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;

function DateStrip({ value, onChange }) {
  const days = useMemo(() => [...Array(7)].map((_, i) => { const d = new Date(); d.setDate(d.getDate() + i - 1); return d; }), []);
  return (
    <div className="date-strip" role="tablist" aria-label="Day">
      {days.map((d) => (
        <button key={iso(d)} role="tab" aria-selected={iso(d) === value} className={iso(d) === value ? "chip chip-on" : "chip"} onClick={() => onChange(iso(d))}>
          {d.toLocaleDateString(undefined, { weekday: "short", day: "numeric" })}
        </button>
      ))}
    </div>
  );
}

function ProbBar({ probs }) {
  if (!probs) return <span className="muted">No forecast yet</span>;
  const parts = [["Home", probs.p_home], ["Draw", probs.p_draw], ["Away", probs.p_away]];
  return (
    <div className="prob" aria-label={parts.map(([k, v]) => `${k} ${pct(v)}`).join(", ")}>
      {parts.map(([k, v]) => <span key={k} className={`prob-${k.toLowerCase()}`} style={{ flexGrow: v || 0.01 }}>{pct(v)}</span>)}
    </div>
  );
}

export default function Today() {
  const [day, setDay] = useState(iso(new Date()));
  const tz = -new Date().getTimezoneOffset();
  const fx = useApi("/fixtures", { date: day, tz });
  const groups = useMemo(() => {
    const g = new Map();
    (fx.data || []).forEach((m) => { const k = m.league?.name || "Other"; if (!g.has(k)) g.set(k, { league: m.league, rows: [] }); g.get(k).rows.push(m); });
    return [...g.values()];
  }, [fx.data]);
  return (
    <section>
      <h1>Today</h1>
      <DateStrip value={day} onChange={setDay} />
      {fx.loading ? <Loading /> : fx.error ? <ErrorBox error={fx.error} onRetry={fx.reload} /> : groups.length === 0 ? (
        <Empty>No matches on this day in the leagues we cover.</Empty>
      ) : groups.map(({ league, rows }) => (
        <div key={league?.id || "other"} className="card league-group">
          <h2 className="league-head"><LeagueMark league={league} /> {league?.name || "Other"}</h2>
          <ul className="fixtures">
            {rows.map((m) => (
              <li key={m.id || m.iid}>
                <Link to={`/match/${m.id}`} className="fixture-row">
                  {m.live && m.live.status && m.live.status !== "Scheduled" && m.status !== "final"
                    ? <span className="fx-live" data-testid={`today-live-${m.id}`}><LiveStatus status={m.live.status} minute={m.live.minute} kickoff={m.kickoff} testid={`today-live-status-${m.id}`} /> <strong>{m.live.hs} - {m.live.as}</strong></span>
                    : <time>{utc(m.kickoff).toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" })}</time>}
                  <span className="team"><Crest team={m.home} size={20} /> {m.home?.name}</span>
                  <span className="team"><Crest team={m.away} size={20} /> {m.away?.name}</span>
                  <ProbBar probs={m.probs} />
                  {m.insight_count > 0 && <span className="badge">{m.insight_count} insights</span>}
                </Link>
              </li>
            ))}
          </ul>
        </div>
      ))}
    </section>
  );
}
