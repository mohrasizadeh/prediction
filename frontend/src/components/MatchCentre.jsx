// Match centre parts (docs/24 §3): the hero and first tab change with the match state, Preview, Forecasts with
// a minimum-likelihood slider and By team / By market, and team Stats as split bars.
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { useApi } from "../lib/useApi";
import { utc } from "../lib/time";
import { Crest } from "./Media";
import LiveStatus from "./LiveStatus";
import TeamRadar from "./TeamRadar";
import TeamNews from "./TeamNews";
import { ShareCard } from "./Share";
import { num1 } from "./Football";
import { EmptyState, ErrorState, ForecastCard, RangeSlider, Segmented, Skeleton, WdlBar } from "./ui";

const cardsOf = (d) => d.cards || d.forecasts;
export function matchState(d) {
  const m = d.match;
  if (m.status === "final" && m.hg != null) return "final";
  if (m.live && m.live.status === "LIVE") return "live";
  return (d.starters || []).length && d.starters.every((s) => s.confirmed) ? "lineups" : "before";
}

function useCountdown(ko) {
  const [now, setNow] = useState(Date.now());
  useEffect(() => { const t = setInterval(() => setNow(Date.now()), 30000); return () => clearInterval(t); }, []);
  const min = Math.round((utc(ko).getTime() - now) / 60000);
  if (min <= 0) return null;
  const dd = Math.floor(min / 1440), h = Math.floor((min % 1440) / 60), mm = min % 60;
  return dd ? `${dd}d ${h}h` : h ? `${h}h ${mm}m` : `${mm} min`;
}

const SITUATION = { rel: "Relegation fight", race: "In the race at the top", dead: "Nothing left to play for" };
function Situation({ d }) {
  const chips = [[d.home, d.match.home_iid], [d.away, d.match.away_iid]].flatMap(([t, iid]) => Object.entries(d.context?.[iid]?.situation || {}).filter(([, v]) => v).map(([k]) => `${t.name}: ${SITUATION[k] || k}`));
  if (!chips.length) return null;
  return <div className="mc-situ" data-testid="match-situation">{chips.map((c) => <span key={c} className="k-tag">{c}</span>)}</div>;
}

function Side({ team, align }) {
  return <Link to={`/team/${team.id}`} className={`mc-team mc-team--${align}`} data-testid={`match-team-${align}`}><Crest team={team} size={64} eager /><b>{team.name}</b></Link>;
}

export function Hero({ d }) {
  const m = d.match, st = matchState(d), lv = m.live;
  const cd = useCountdown(m.kickoff);
  const last = (d.live_events || []).filter((e) => e.type !== "substitution").slice(-1)[0];
  return (
    <section className={`mc-hero card mc-hero--${st}`} data-testid="match-hero">
      <div className="mc-row">
        <Side team={d.home} align="home" />
        <div className="mc-mid">
          {st === "final" ? <><strong className="mc-score" data-testid="match-score">{m.hg} – {m.ag}</strong><span className="status-chip">Full time</span></>
            : st === "live" ? <><strong className="mc-score" data-testid="match-live-score">{lv.hs} – {lv.as}</strong><LiveStatus status="LIVE" minute={lv.minute} testid="match-live-status" />
              {last && <small className="mc-last" data-testid="match-last-event">{last.type.replace(/_/g, " ")}{last.player_name ? `, ${last.player_name}` : ""} {last.minute}</small>}</>
            : <><span className="mc-v">v</span><time className="mc-ko">{utc(m.kickoff).toLocaleString(undefined, { weekday: "short", day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" })}</time>
              {cd && <span className="mc-cd" data-testid="match-countdown">Kick-off in {cd}</span>}</>}
          {st === "lineups" && <span className="k-tag k-tag--up" data-testid="match-lineups-confirmed">Lineups confirmed</span>}
        </div>
        <Side team={d.away} align="away" />
      </div>
      {st !== "final" && d.probs && <WdlBar home={d.probs.p_home} draw={d.probs.p_draw} away={d.probs.p_away} homeName={d.home.name} awayName={d.away.name} testid="match-wdl" />}
      {st !== "final" && <Situation d={d} />}
      {d.probs && <p className="k-faint k-small">Expected goals {num1(d.probs.xg_home)} – {num1(d.probs.xg_away)}</p>}
      {(m.referee || m.stadium) && <p className="k-faint k-small" data-testid="match-meta">{m.referee && <>Referee: <Link to={`/referee/${encodeURIComponent(m.referee)}`} data-testid="match-referee-link">{m.referee}</Link></>}{m.referee && m.stadium ? " · " : ""}{m.stadium}</p>}
      <ShareCard d={d} />
    </section>
  );
}

function useCompare(d) {
  return useApi("/teams/compare", { a: d.home.id, b: d.away.id, as_fixture: true });
}

export function Preview({ d }) {
  const c = useCompare(d);
  const why = [[d.home, d.match.home_iid], [d.away, d.match.away_iid]].flatMap(([t, iid]) => (d.context?.[iid]?.why || []).map((w) => `${t.name}: ${w}`)).slice(0, 3);
  return (
    <div className="mc-preview" data-testid="match-preview">
      {why.length > 0 && <ul className="mc-why card" data-testid="match-why">{why.map((w) => <li key={w}>{w}</li>)}</ul>}
      <TeamNews d={d} />
      {c.loading && !c.data ? <Skeleton shape="card" count={1} /> : c.data?.radar?.length ? <div className="card mc-radar"><h2 className="k-sec">{d.home.name} at home v {d.away.name} away</h2><TeamRadar axes={c.data.radar} aName={d.home.name} bName={d.away.name} testid="match-radar" /></div> : null}
      {!why.length && !(d.availability || []).length && !c.data?.radar?.length && !c.loading && <EmptyState icon="info" title="No preview yet" testid="match-preview-empty">Form, absences and the radar appear once both clubs have played this season.</EmptyState>}
    </div>
  );
}

export function Forecasts({ d }) {
  const [min, setMin] = useState(50);
  const [by, setBy] = useState("team");
  const rows = cardsOf(d).filter((f) => f.p * 100 >= min);
  const groups = by === "team"
    ? [[d.home.name, rows.filter((f) => f.team_iid === d.match.home_iid && !f.stat?.startsWith("match_"))], [d.away.name, rows.filter((f) => f.team_iid === d.match.away_iid && !f.stat?.startsWith("match_"))], ["Both teams", rows.filter((f) => f.stat?.startsWith("match_"))]]
    : [...new Set(rows.map((f) => f.stat))].map((s) => [rows.find((f) => f.stat === s)?.market?.replace(/^\d+\+\s*/, "") || s, rows.filter((f) => f.stat === s)]);
  return (
    <div className="mc-fc" data-testid="match-forecasts">
      <div className="mc-fc-bar">
        <Segmented options={[{ id: "team", label: "By team" }, { id: "market", label: "By market" }]} value={by} onChange={setBy} label="Group" testid="fc-group" />
        <div className="mc-fc-min"><RangeSlider min={50} max={95} step={5} value={min} onChange={setMin} label="Minimum likelihood" format={(v) => `${v}%+`} testid="fc-min" /></div>
      </div>
      {!cardsOf(d).length ? <EmptyState icon="target" title="No forecasts yet" testid="fc-empty">They appear once the engine has run for this match.</EmptyState>
        : !rows.length ? <EmptyState icon="target" title={`Nothing at ${min}% or more`} testid="fc-none" action={<button type="button" className="btn btn--secondary btn--sm" onClick={() => setMin(50)} data-testid="fc-reset">Show all</button>}>Lower the minimum likelihood.</EmptyState>
        : groups.filter(([, xs]) => xs.length).map(([title, xs]) => (
          <section key={title} className="mc-fc-group"><h2 className="k-sec">{title} · {xs.length}</h2>
            <div className="fgrid">{xs.map((f) => <ForecastCard key={f.id} f={f} homeIid={d.match.home_iid} showTime={false} testid={`match-fc-${f.id}`} />)}</div></section>
        ))}
    </div>
  );
}

export function Stats({ d }) {
  const c = useCompare(d);
  if (c.loading && !c.data) return <Skeleton shape="row" count={5} testid="match-stats-loading" />;
  if (c.error) return <ErrorState message="We could not load the team numbers." onRetry={c.reload} testid="match-stats-error" />;
  const e = (c.data?.edges || []).filter((x) => ["shots", "sot", "corners", "poss", "xg", "goals"].includes(x.key));
  if (!e.length) return <EmptyState icon="bar-chart" title="No team numbers yet" testid="match-stats-empty">They appear after each club's first finished match this season.</EmptyState>;
  return (
    <div className="card mc-stats" data-testid="match-stats">
      <h2 className="k-sec">Per game this season · {d.home.name} at home, {d.away.name} away</h2>
      <ul className="cp-edges">{e.map((x) => { const t = (x.a || 0) + (x.b || 0) || 1; return (
        <li key={x.key} className={`lean-${x.lean || "none"}`}><b>{num1(x.a)}</b><span className="cp-edge-mid"><small>{x.label}</small><span className="cp-edge-bar" aria-hidden="true"><i className="ea" style={{ width: `${(x.a / t) * 100}%` }} /><i className="eb" style={{ width: `${(x.b / t) * 100}%` }} /></span></span><b>{num1(x.b)}</b></li>); })}</ul>
    </div>
  );
}
