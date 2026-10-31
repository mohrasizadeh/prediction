// Match centre parts (docs/24 §3): the hero and first tab change with the match state, Preview, Forecasts with
// a minimum-likelihood slider and By team / By market, and team Stats as split bars.
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { useApi } from "../lib/useApi";
import { utc } from "../lib/time";
import { Crest } from "./Media";
import { FollowButton } from "./Actions";
import LiveStatus from "./LiveStatus";
import TeamRadar from "./TeamRadar";
import TeamNews from "./TeamNews";
import { ShareCard } from "./Share";
import { num1 } from "./Football";
import BuildForMe from "./BuildForMe";
import { EmptyState, ErrorState, ForecastCard, RangeSlider, Segmented, Skeleton, WdlBar } from "./ui";

const cardsOf = (d) => d.cards || d.forecasts;
export function matchState(d) {
  const m = d.match;
  if (m.status === "postponed" || m.status === "cancelled") return "off";
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
  if (!chips.length && !d.referee?.sentence) return null;
  return (
    <>
      {chips.length > 0 && <div className="mc-situ" data-testid="match-situation">{chips.map((c) => <span key={c} className="k-tag">{c}</span>)}</div>}
      {d.referee?.sentence && <p className="mc-ref k-faint" data-testid="match-referee">{d.referee.sentence}</p>}
    </>
  );
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
      <p className="mc-when" data-testid="match-when">{st === "live" && <span className="k-livedot" aria-hidden="true" />}{utc(m.kickoff).toLocaleString(undefined, { weekday: "short", day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" })}</p>
      <div className="mc-row">
        <Side team={d.home} align="home" />
        <div className="mc-mid">
          {st === "final" ? <><strong className="mc-score" data-testid="match-score">{m.hg} – {m.ag}</strong><span className="status-chip">Full time</span>
              {d.recap?.ht && <small className="k-faint" data-testid="match-ht">Half-time {d.recap.ht[0]} – {d.recap.ht[1]}</small>}</>
            : st === "live" ? <><strong className="mc-score" data-testid="match-live-score">{lv.hs} – {lv.as}</strong><LiveStatus status="LIVE" minute={lv.minute} testid="match-live-status" />
              {last && <small className="mc-last" data-testid="match-last-event">{last.type.replace(/_/g, " ")}{last.player_name ? `, ${last.player_name}` : ""} {last.minute}</small>}</>
            : st === "off" ? <><span className="mc-v">v</span><span className="status-chip status-chip--off" data-testid="match-off">{m.status === "postponed" ? "Postponed" : "Cancelled"}</span>
              <small className="k-faint">{m.status === "postponed" ? "New date to be confirmed" : "This match will not be played"}</small></>
            : <><span className="mc-v">v</span>
              {cd && <span className="mc-cd" data-testid="match-countdown">Kick-off in {cd}</span>}</>}
          {st === "lineups" && <span className="k-tag k-tag--up" data-testid="match-lineups-confirmed">Lineups confirmed</span>}
        </div>
        <Side team={d.away} align="away" />
      </div>
      {st !== "final" && st !== "off" && d.probs && <WdlBar home={d.probs.p_home} draw={d.probs.p_draw} away={d.probs.p_away} homeName={d.home.name} awayName={d.away.name} testid="match-wdl" />}
      {st === "final" && d.recap?.scored > 0 && <p className="mc-recap" data-testid="match-recap">How our forecasts did: <b>{d.recap.hit} of {d.recap.scored}</b> Strong and Solid forecasts came true
        {["Strong", "Solid"].filter((t) => d.recap.by_tier[t][1]).map((t) => ` · ${t} ${d.recap.by_tier[t][0]}/${d.recap.by_tier[t][1]}`).join("")}</p>}
      <div className="mc-foot">
        <div className="mc-meta">
          {d.probs && <small className="k-faint" data-testid="match-xg">Expected goals {num1(d.probs.xg_home)} – {num1(d.probs.xg_away)}</small>}
          {(m.referee || m.stadium) && <small className="k-faint" data-testid="match-meta">{m.referee && <>Referee: <Link to={`/referee/${encodeURIComponent(m.referee)}`} data-testid="match-referee-link">{m.referee}</Link></>}{m.referee && m.stadium ? " · " : ""}{m.stadium}</small>}
        </div>
        <div className="mc-actions">{st !== "final" && st !== "off" && <FollowButton kind="match" refId={m.id} name={`${d.home?.name} v ${d.away?.name}`} />}<ShareCard d={d} /></div>
      </div>
    </section>
  );
}

function useCompare(d) {
  return useApi("/teams/compare", { a: d.home.id, b: d.away.id, as_fixture: true });
}

// Before-kickoff notes that belong next to the lineups: why the match matters, absences and who is likely to miss out.
export function MatchNotes({ d }) {
  const why = [[d.home, d.match.home_iid], [d.away, d.match.away_iid]].flatMap(([t, iid]) => (d.context?.[iid]?.why || []).map((w) => `${t.name}: ${w}`)).slice(0, 3);
  const news = (d.availability || []).length > 0;
  if (!why.length && !news && !d.referee?.sentence) return null;
  return (
    <div className="mc-notes" data-testid="match-preview">
      {why.length > 0 && <section className="card mc-why-card"><h2 className="k-sec">Worth knowing</h2><ul className="mc-why" data-testid="match-why">{why.map((w) => <li key={w}>{w}</li>)}</ul></section>}
      <TeamNews d={d} />
      {d.referee?.sentence && <p className="mc-ref k-faint" data-testid="match-referee">{d.referee.sentence}</p>}
    </div>
  );
}

export function Forecasts({ d, matchId }) {
  const live = !!d.match.live && d.match.live.status !== "Scheduled" && d.match.status !== "postponed";
  const lt = useApi(live && matchId ? `/matches/${matchId}/live-forecasts` : null, undefined, { every: d.match.live?.status === "LIVE" ? 30000 : 0 });
  const track = lt.data?.active ? lt.data.items : null;
  const all = track ? cardsOf(d).flatMap((f) => [f, ...(f.more_lines || [])]) : [];
  const tracked = all.filter((x) => track[x.fkey] && track[x.fkey].state !== "unknown").length;
  const hits = all.filter((x) => track[x.fkey]?.state === "hit").length;
  const [min, setMin] = useState(50);
  const [by, setBy] = useState("team");
  const rows = cardsOf(d).filter((f) => f.p * 100 >= min);
  const groups = by === "team"
    ? [[d.home.name, rows.filter((f) => f.team_iid === d.match.home_iid && !f.stat?.startsWith("match_"))], [d.away.name, rows.filter((f) => f.team_iid === d.match.away_iid && !f.stat?.startsWith("match_"))], ["Both teams", rows.filter((f) => f.stat?.startsWith("match_"))]]
    : [...new Set(rows.map((f) => f.stat))].map((s) => [rows.find((f) => f.stat === s)?.market?.replace(/^\d+\+\s*/, "") || s, rows.filter((f) => f.stat === s)]);
  return (
    <div className="mc-fc" data-testid="match-forecasts">
      {matchId && d.match.status === "scheduled" && cardsOf(d).length > 0 && <div className="cb-buildrow"><BuildForMe matchId={matchId} /><small className="muted">Tap + on a line to start a combo.</small></div>}
      {track && <p className="lv-sum" data-testid="match-live-sum"><span className="k-livedot" aria-hidden="true" />{tracked ? <span><b>{hits} of {tracked}</b> lines we can follow have happened{lt.data.final ? "." : ". Updates every 30 seconds."}</span> : <span>Lines tick green here as cards and match numbers come in.</span>}</p>}
      <div className="mc-fc-bar">
        <Segmented options={[{ id: "team", label: "By team" }, { id: "market", label: "By market" }]} value={by} onChange={setBy} label="Group" testid="fc-group" />
        <div className="mc-fc-min"><RangeSlider min={50} max={95} step={5} value={min} onChange={setMin} label="Minimum likelihood" format={(v) => `${v}%+`} testid="fc-min" /></div>
      </div>
      {!cardsOf(d).length ? <EmptyState icon="target" title="No forecasts yet" testid="fc-empty">They appear once the engine has run for this match.</EmptyState>
        : !rows.length ? <EmptyState icon="target" title={`Nothing at ${min}% or more`} testid="fc-none" action={<button type="button" className="btn btn--secondary btn--sm" onClick={() => setMin(50)} data-testid="fc-reset">Show all</button>}>Lower the minimum likelihood.</EmptyState>
        : groups.filter(([, xs]) => xs.length).map(([title, xs]) => (
          <section key={title} className="mc-fc-group"><h2 className="k-sec">{title} · {xs.length}</h2>
            <div className="fgrid">{xs.map((f) => <ForecastCard key={f.id} f={f} homeIid={d.match.home_iid} showTime={false} track={track} testid={`match-fc-${f.id}`} />)}</div></section>
        ))}
    </div>
  );
}

export function Form({ d }) {
  const c = useCompare(d);
  if (c.loading && !c.data) return <Skeleton shape="row" count={5} testid="match-stats-loading" />;
  if (c.error) return <ErrorState message="We could not load the team numbers." onRetry={c.reload} testid="match-stats-error" />;
  const e = (c.data?.edges || []).filter((x) => ["shots", "sot", "corners", "poss", "xg", "goals"].includes(x.key));
  if (!e.length && !c.data?.radar?.length) return <EmptyState icon="bar-chart" title="No team numbers yet" testid="match-stats-empty">They appear after each club's first finished match this season.</EmptyState>;
  return (
    <div className="mc-form" data-testid="match-stats">
      {e.length > 0 && <div className="card mc-stats">
        <h2 className="k-sec">Per game this season</h2>
        <p className="k-faint k-small">{d.home.name} at home, {d.away.name} away. Numbers from before kick-off.</p>
        <ul className="cp-edges">{e.map((x) => { const t = (x.a || 0) + (x.b || 0) || 1; return (
          <li key={x.key} className={`lean-${x.lean || "none"}`}><b>{num1(x.a)}</b><span className="cp-edge-mid"><small>{x.label}</small><span className="cp-edge-bar" aria-hidden="true"><i className="ea" style={{ width: `${(x.a / t) * 100}%` }} /><i className="eb" style={{ width: `${(x.b / t) * 100}%` }} /></span></span><b>{num1(x.b)}</b></li>); })}</ul>
      </div>}
      {c.data?.radar?.length > 0 && <div className="card mc-radar"><h2 className="k-sec">Style shape</h2><TeamRadar axes={c.data.radar} aName={d.home.name} bName={d.away.name} games={c.data.radar_games} testid="match-radar" /></div>}
    </div>
  );
}
