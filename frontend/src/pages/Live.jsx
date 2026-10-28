// Live scores (docs/23). Reads GET /api/live from our own server every 30 seconds while the tab is visible.
// The server refreshes from SportAPI on its own schedule; this page never talks to SportAPI.
import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { get } from "../lib/api";
import { utc } from "../lib/time";
import { Crest } from "../components/Media";
import LiveStatus from "../components/LiveStatus";
import MatchEvents from "../components/MatchEvents";
import LiveLineups from "../components/LiveLineups";
import { useTitle } from "../components/Football";
import { Empty, ErrorBox, Loading } from "../components/States";

const iso = (d) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;

function useLive(date) {
  const [state, setState] = useState({ data: null, error: null, loading: true });
  const [n, setN] = useState(0);
  useEffect(() => {
    let stop = false, timer = null;
    const tz = -new Date().getTimezoneOffset();
    const load = () => get("/live", { date, tz })
      .then((data) => { if (!stop) setState({ data, error: null, loading: false }); })
      .catch((error) => { if (!stop) setState((s) => ({ ...s, error, loading: false })); });
    const loop = () => { if (document.visibilityState === "visible") load(); timer = setTimeout(loop, 30000); };
    setState((s) => ({ ...s, loading: !s.data }));
    load(); timer = setTimeout(loop, 30000);
    const onVis = () => { if (document.visibilityState === "visible") load(); };
    document.addEventListener("visibilitychange", onVis);
    return () => { stop = true; clearTimeout(timer); document.removeEventListener("visibilitychange", onVis); };
  }, [date, n]);
  return { ...state, reload: () => setN((x) => x + 1) };
}

function Detail({ f }) {
  const [events, setEvents] = useState(null);
  const [lineups, setLineups] = useState(null);
  useEffect(() => {
    get(`/live/${f.sid}/events`).then((r) => setEvents(r.events)).catch(() => setEvents([]));
    get(`/live/${f.sid}/lineups`).then((r) => setLineups(r.lineups)).catch(() => setLineups({}));
  }, [f.sid, f.events_n]);
  const sc = f.score || {};
  return (
    <div className="live-detail" data-testid={`live-detail-${f.sid}`}>
      {sc.ht_home != null && <p className="muted small">Half-time {sc.ht_home} – {sc.ht_away}</p>}
      {events === null ? <Loading label="Events" rows={2} /> : <MatchEvents events={events} testid={`live-events-${f.sid}`} />}
      <LiveLineups lineups={lineups} home={f.home.team?.name || f.home.name} away={f.away.team?.name || f.away.name} />
      {f.match_id && <Link className="btn btn--secondary btn--sm live-link" to={`/match/${f.match_id}`} data-testid={`live-match-link-${f.sid}`}>Forecasts and stats for this match</Link>}
    </div>
  );
}

function Row({ f }) {
  const [open, setOpen] = useState(false);
  const sc = f.score || {};
  const show = f.status !== "Scheduled" && sc.home != null;
  return (
    <li className={`live-row ${f.status === "LIVE" ? "is-live" : ""} ${open ? "is-open" : ""}`}>
      <button type="button" className="live-main" aria-expanded={open} onClick={() => setOpen((o) => !o)} data-testid={`live-row-${f.sid}`}>
        <span className="live-status"><LiveStatus status={f.status} minute={f.minute} kickoff={f.kickoff} text={f.status_text} testid={`live-status-${f.sid}`} /></span>
        <span className="live-team"><Crest team={f.home.team} size={22} /><span>{f.home.team?.name || f.home.name}</span></span>
        <span className="live-score" data-testid={`live-score-${f.sid}`} aria-label={show ? `${sc.home} to ${sc.away}` : "not started"}>
          {show ? <>{sc.home}<i>–</i>{sc.away}</> : <i>v</i>}
          {sc.pen_home != null && <small>({sc.pen_home}–{sc.pen_away} pens)</small>}
        </span>
        <span className="live-team live-team--away"><span>{f.away.team?.name || f.away.name}</span><Crest team={f.away.team} size={22} /></span>
      </button>
      {open && <Detail f={f} />}
    </li>
  );
}

const LABELS = ["Yesterday", "Today", "Tomorrow"];

export default function Live() {
  useTitle("Live scores");
  const [day, setDay] = useState(iso(new Date()));
  const days = useMemo(() => [-1, 0, 1].map((i) => { const d = new Date(); d.setDate(d.getDate() + i); return d; }), []);
  const q = useLive(day);
  return (
    <section className="live-page" data-testid="live-page">
      <div className="live-head">
        <h1>Live scores</h1>
        {q.data?.live_count > 0 && <span className="live-chip live-chip--lg" data-testid="live-count"><span className="live-dot" aria-hidden="true" />{q.data.live_count} live now</span>}
      </div>
      <div className="date-strip" role="tablist" aria-label="Day">
        {days.map((d, i) => (
          <button key={iso(d)} type="button" role="tab" aria-selected={iso(d) === day} className={iso(d) === day ? "chip chip-on" : "chip"} onClick={() => setDay(iso(d))} data-testid={`live-day-${LABELS[i].toLowerCase()}`}>{LABELS[i]}</button>
        ))}
      </div>
      {q.loading ? <Loading rows={4} /> : q.error && !q.data ? <ErrorBox error={q.error} onRetry={q.reload} /> : !q.data.leagues.length ? (
        <Empty icon="clock" testid="live-empty">No matches in the leagues we follow live on this day.</Empty>
      ) : q.data.leagues.map((g) => (
        <div key={g.league} className="card live-group" data-testid="live-league">
          <h2 className="league-head">{g.league}</h2>
          <ul className="live-list">{g.fixtures.map((f) => <Row key={f.sid} f={f} />)}</ul>
        </div>
      ))}
      {q.data?.updated && <p className="muted small" data-testid="live-updated">Updated {utc(q.data.updated).toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" })}. Scores refresh every 30 seconds.</p>}
    </section>
  );
}
