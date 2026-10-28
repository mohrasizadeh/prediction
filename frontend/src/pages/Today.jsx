// Today (docs/24 §1): day scroller, Top 3 for the day, live strip, filter chips, fixtures by league with a
// win/draw/loss bar and an insight chip. Data: GET /api/fixtures (the same call as before) and GET /api/insights.
import { useMemo, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { useApi } from "../lib/useApi";
import { useAuth } from "../lib/auth";
import { utc } from "../lib/time";
import { Crest, LeagueMark } from "../components/Media";
import { favFirst, useFavLeagues, useGameDays } from "../lib/prefs";
import LiveStatus from "../components/LiveStatus";
import Icon from "../components/Icon";
import { useTitle } from "../components/Football";
import { ChipsRow, DateScroller, EmptyState, ErrorState, ForecastCard, Skeleton, WdlBar, isoDay, useSessionDay } from "../components/ui";

const isLive = (m) => m.live?.status === "LIVE" && m.status !== "final";
const localDay = (s) => isoDay(utc(s));
const shift = (day, n) => { const d = new Date(`${day}T12:00:00`); d.setDate(d.getDate() + n); return isoDay(d); };
function until(s) {
  const min = Math.round((utc(s).getTime() - Date.now()) / 60000);
  if (min <= 0 || min > 24 * 60) return null;
  return min < 60 ? `in ${min} min` : `in ${Math.floor(min / 60)}h ${min % 60}m`;
}

function Top3({ day }) {
  const q = useApi("/insights", { limit: 200 });
  const rows = (q.data || []).filter((x) => localDay(x.kickoff) === day);
  if (q.loading && !q.data) return <Skeleton shape="card" count={3} testid="today-top3-loading" />;
  if (!rows.length) return null;
  return (
    <section className="td-top" aria-label="Top 3 for this day" data-testid="today-top3">
      <div className="td-sec-head"><h2 className="k-sec">Top 3 for {day === isoDay(new Date()) ? "today" : utc(`${day}T12:00:00Z`).toLocaleDateString(undefined, { weekday: "long" })}</h2>
        <Link to={`/insights?day=${day}`} className="k-link" data-testid="today-see-all">See all {rows.length} →</Link></div>
      <div className="td-carousel">{rows.slice(0, 3).map((f) => <ForecastCard key={f.id} f={f} testid={`today-top-${f.id}`} />)}</div>
    </section>
  );
}

function Row({ m }) {
  const live = isLive(m);
  const started = m.status === "final" || (m.live && m.live.status !== "Scheduled" && m.live.hs != null);
  const hs = m.status === "final" ? m.hg : m.live?.hs, as = m.status === "final" ? m.ag : m.live?.as;
  const p = m.probs;
  return (
    <li>
      <Link to={`/match/${m.id}`} className={`td-row${live ? " is-live" : ""}`} data-testid={`today-row-${m.id}`}>
        <span className="td-time">
          {live ? <LiveStatus status="LIVE" minute={m.live.minute} testid={`today-live-status-${m.id}`} />
            : m.status === "final" ? <span className="status-chip">Full time</span>
            : <><b>{utc(m.kickoff).toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" })}</b>{until(m.kickoff) && <small>{until(m.kickoff)}</small>}</>}
        </span>
        <span className="td-teams">
          <span><Crest team={m.home} size={22} /><span className="td-name">{m.home?.name}</span>{started && <b className="td-sc" data-testid={`today-live-${m.id}`}>{hs}</b>}</span>
          <span><Crest team={m.away} size={22} /><span className="td-name">{m.away?.name}</span>{started && <b className="td-sc">{as}</b>}</span>
        </span>
        <span className="td-bar">{p ? <WdlBar home={p.p_home} draw={p.p_draw} away={p.p_away} homeName={m.home?.name} awayName={m.away?.name} testid={`today-wdl-${m.id}`} /> : <small className="k-faint">No forecast yet</small>}</span>
        {m.insight_count > 0 ? <span className="td-ins" data-testid={`today-insights-${m.id}`}>{m.insight_count} insight{m.insight_count === 1 ? "" : "s"} ›</span> : <span className="td-ins td-ins--none" aria-hidden="true" />}
      </Link>
    </li>
  );
}

function Group({ league, rows }) {
  const [open, setOpen] = useState(true);
  const n = rows.reduce((a, m) => a + (m.insight_count || 0), 0);
  return (
    <section className="td-group card" data-testid={`today-league-${league?.id || "other"}`}>
      <button type="button" className="td-ghead" aria-expanded={open} onClick={() => setOpen(!open)} data-testid={`today-league-toggle-${league?.id || "other"}`}>
        <LeagueMark league={league} size={24} /><b>{league?.name || "Other"}</b>
        <small>{rows.length} match{rows.length === 1 ? "" : "es"}{n ? ` · ${n} insight${n === 1 ? "" : "s"}` : ""}</small><Icon name="chevron-down" size={18} />
      </button>
      {open && <ul className="td-list">{rows.map((m) => <Row key={m.id} m={m} />)}</ul>}
    </section>
  );
}

export default function Today() {
  useTitle("Today");
  const [day, setDay] = useSessionDay("today-day");
  const [chip, setChip] = useState("all");
  const { user } = useAuth();
  const tz = -new Date().getTimezoneOffset();
  const fx = useApi("/fixtures", { date: day, tz });
  const fol = useApi(user ? "/me/follows" : null);
  const touch = useRef(null);
  const followed = useMemo(() => new Set((fol.data?.items || []).filter((x) => x.kind === "team" || x.kind === "league").map((x) => x.id)), [fol.data]);
  const all = fx.data || [];
  const isFol = (m) => followed.has(m.home?.id) || followed.has(m.away?.id) || followed.has(m.league?.id);
  const pick = { all: () => true, following: isFol, live: isLive, insights: (m) => m.insight_count > 0 }[chip];
  const fav = useFavLeagues();
  const gameDays = useGameDays(-1, 7);
  const groups = useMemo(() => {
    const g = new Map();
    all.filter(pick).forEach((m) => { const k = m.league?.id || "other"; if (!g.has(k)) g.set(k, { league: m.league, rows: [], fol: false }); g.get(k).rows.push(m); if (isFol(m)) g.get(k).fol = true; });
    return favFirst([...g.values()].sort((a, b) => Number(b.fol) - Number(a.fol)), fav, (x) => x.league?.id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [all, chip, followed, fav]);
  const live = all.filter(isLive);
  const chips = [{ id: "all", label: "All", count: all.length }, ...(user ? [{ id: "following", label: "Following", count: all.filter(isFol).length }] : []),
    { id: "live", label: "Live now", count: live.length }, { id: "insights", label: "Has insights", count: all.filter((m) => m.insight_count > 0).length }];
  const swipe = { onTouchStart: (e) => { touch.current = e.touches[0].clientX; }, onTouchEnd: (e) => { const dx = e.changedTouches[0].clientX - (touch.current ?? 0); if (Math.abs(dx) > 70) setDay(shift(day, dx < 0 ? 1 : -1)); } };
  return (
    <section className="td" data-testid="today-page">
      <h1 className="sr-only">Today</h1>
      <DateScroller value={day} onChange={setDay} gameDays={gameDays} testid="today-dates" />
      <Top3 day={day} />
      {live.length > 0 && <div className="td-livestrip" aria-label="Live now" data-testid="today-livestrip">{live.map((m) => (
        <Link key={m.id} to={`/match/${m.id}`} className="td-livechip" data-testid={`today-livechip-${m.id}`}><span className="k-livedot" aria-hidden="true" /><b>{m.live.minute}</b>{m.home?.name} {m.live.hs}–{m.live.as} {m.away?.name}</Link>
      ))}</div>}
      <div className="td-chips"><ChipsRow options={chips} value={chip} onChange={setChip} label="Show" testid="today-filter" /></div>
      <div {...swipe}>
        {fx.loading && !fx.data ? <Skeleton shape="match" count={4} testid="today-loading" />
          : fx.error && !fx.data ? <ErrorState message="We could not load the fixtures." onRetry={fx.reload} testid="today-error" />
          : !groups.length ? (
            <EmptyState title={chip === "all" ? "No games on this day" : "Nothing matches this filter"} testid="today-empty"
              action={chip === "all" ? <button type="button" className="btn btn--secondary btn--sm" onClick={() => setDay(shift(day, 1))} data-testid="today-next-day">See the next day</button>
                : <button type="button" className="btn btn--secondary btn--sm" onClick={() => setChip("all")} data-testid="today-show-all">Show all matches</button>}>
              {chip === "all" ? "There are no matches in the leagues we cover on this day." : "Try All to see every match on this day."}
            </EmptyState>
          ) : groups.map((g) => <Group key={g.league?.id || "other"} league={g.league} rows={g.rows} />)}
        {fx.data && <p className="k-faint k-small td-pct">Percentages are our win, draw and loss likelihoods for each match.</p>}
      </div>
    </section>
  );
}
