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
import { ChipsRow, EmptyState, ErrorState, Skeleton } from "../components/ui";
import { fxLive, fxStarted } from "../lib/live";

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
  const home = f.home.team?.name || f.home.name, away = f.away.team?.name || f.away.name;
  // Half-time and full time are dividers inside the timeline now, with the score at that point.
  return (
    <div className="live-detail" data-testid={`live-detail-${f.sid}`}>
      {events === null ? <Skeleton shape="row" count={2} testid={`live-events-loading-${f.sid}`} />
        : <MatchEvents events={events} testid={`live-events-${f.sid}`} phase={fxLive(f) ? "live" : "final"} status={f.status} home={home} away={away}
            score={sc} emptyText={fxStarted(f) ? "Nothing yet from the match feed." : "Goals, cards and substitutions appear here once the match starts."} />}
      {/* Two elevens and two benches are a screen and a half on a phone: one tap away, not in the way of the events. */}
      {lineups && (lineups.home || lineups.away) && (
        <details className="live-lu" data-testid={`live-lineups-toggle-${f.sid}`}>
          <summary>Lineups</summary>
          <LiveLineups lineups={lineups} home={home} away={away} testid={`live-lineups-${f.sid}`} title={null} />
        </details>
      )}
      {f.match_id && <Link className="btn btn--secondary btn--sm live-link" to={`/match/${f.match_id}`} data-testid={`live-match-link-${f.sid}`}>Forecasts and stats for this match</Link>}
    </div>
  );
}

function Row({ f }) {
  const [open, setOpen] = useState(false);
  const sc = f.score || {};
  const show = fxStarted(f) && sc.home != null;
  return (
    <li className={`live-row ${fxLive(f) ? "is-live" : ""} ${open ? "is-open" : ""}`}>
      <button type="button" className="live-main" aria-expanded={open} onClick={() => setOpen((o) => !o)} data-testid={`live-row-${f.sid}`}>
        <span className="live-status"><LiveStatus status={f.status} state={f.state} live={f.live} minute={f.minute} kickoff={f.kickoff} text={f.status_text} testid={`live-status-${f.sid}`} /></span>
        <span className="live-team"><Crest team={f.home.team} size={22} /><span className="lvr-name">{f.home.team?.name || f.home.name}</span></span>
        <span className="live-score" data-testid={`live-score-${f.sid}`} aria-label={show ? `${sc.home} to ${sc.away}` : "not started"}>
          <span className="live-score-n">{show ? <>{sc.home}<i>–</i>{sc.away}</> : <i>v</i>}</span>
          {sc.pen_home != null && <small>({sc.pen_home}–{sc.pen_away} pens)</small>}
        </span>
        <span className="live-team live-team--away"><span className="lvr-name">{f.away.team?.name || f.away.name}</span><Crest team={f.away.team} size={22} /></span>
      </button>
      {open && <Detail f={f} />}
    </li>
  );
}

// When the scores were last read, and a plain warning when that was a while ago or the last refresh failed.
// A failed refresh keeps the last answer on screen (useLive), so without this a dropped feed looked current.
function Updated({ q }) {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => { const t = setInterval(() => setNow(Date.now()), 30000); return () => clearInterval(t); }, []);
  const at = utc(q.data?.updated);
  if (!at && !q.error) return null;
  const min = at ? Math.floor((now - at.getTime()) / 60000) : null;
  const stale = q.data?.live_count > 0 && min != null && min >= 3;
  const time = at ? at.toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" }) : null;
  if (q.error || stale) {
    return (
      <p className="tl-stale" role="status" data-testid="live-stale"><span className="tl-stale-dot" aria-hidden="true" />
        {q.error ? `We could not refresh the scores${time ? `; these are from ${time}` : ""}. We will try again in 30 seconds.` : `The match feed last updated at ${time}, ${min} minutes ago. Scores may be behind.`}
        {q.error && <button type="button" className="k-link" onClick={q.reload} data-testid="live-retry">Try now</button>}
      </p>
    );
  }
  return <p className="muted small" data-testid="live-updated">Updated {time}. Scores refresh every 30 seconds.</p>;
}

const LABELS = ["Yesterday", "Today", "Tomorrow"];

export default function Live() {
  useTitle("Live scores");
  const [day, setDay] = useState(iso(new Date()));
  // The three days as ISO strings, chosen through the shared chip row rather than a tablist of
  // hand-rolled `.chip` buttons: every other screen picks a day or a filter with ChipsRow, and the
  // ids stay the day's word so the published testids ("live-day-today") are unchanged.
  const days = useMemo(() => [-1, 0, 1].map((i) => { const d = new Date(); d.setDate(d.getDate() + i); return iso(d); }), []);
  const sel = LABELS[days.indexOf(day)]?.toLowerCase() || "today";
  const q = useLive(day);
  return (
    <section className="live-page" data-testid="live-page">
      <div className="live-head">
        <h1>Live scores</h1>
        {q.data?.live_count > 0 && <span className="live-chip live-chip--lg" data-testid="live-count"><span className="live-dot" aria-hidden="true" />{q.data.live_count} live now</span>}
      </div>
      <div className="date-strip">
        <ChipsRow label="Day" value={sel} onChange={(id) => setDay(days[LABELS.findIndex((l) => l.toLowerCase() === id)])}
                  options={LABELS.map((l) => ({ id: l.toLowerCase(), label: l }))} testid="live-day" />
      </div>
      {q.loading ? <Skeleton shape="match" count={4} testid="live-loading" /> : q.error && !q.data ? <ErrorState message="We could not load the live scores." onRetry={q.reload} testid="live-error" /> : !q.data.leagues.length ? (
        <EmptyState icon="clock" title="No matches on this day" testid="live-empty">Nothing in the leagues we follow live. Try another day.</EmptyState>
      ) : q.data.leagues.map((g) => (
        <div key={g.league} className="card live-group" data-testid="live-league">
          <h2 className="league-head">{g.league}</h2>
          <ul className="live-list">{g.fixtures.map((f) => <Row key={f.sid} f={f} />)}</ul>
        </div>
      ))}
      <Updated q={q} />
    </section>
  );
}
