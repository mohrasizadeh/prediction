// Screen 2, Match (docs/34): hero with win/draw/loss, then four tabs: Live or Recap (while on / after), Forecasts, Lineups (pitch + notes), Analysis (form, H2H, first goal, players, style).
import { useEffect, useRef, useState } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import { useApi } from "../lib/useApi";
import { Crest, PlayerAvatar } from "../components/Media";
import { Empty, ErrorBox, Loading } from "../components/States";
import { Tabs } from "../components/Ui";
import { MatchRow, Seg, TacticChip, num1, posLabel, useTitle } from "../components/Football";
import FirstGoal from "../components/FirstGoal";
import { Forecasts, Form, Hero, MatchNotes, MiniBar, matchState } from "../components/MatchCentre";
import MatchEvents from "../components/MatchEvents";
import LiveLineups from "../components/LiveLineups";
import { ProLock } from "../components/ui";
import { isLiveNow } from "../lib/live";
import { pct } from "../lib/copy";

const cardsOf = (d) => d.cards || d.forecasts;

function LiveTab({ d }) {
  const sid = d.live?.sid;
  const q = useApi(`/live/${sid}/lineups`);
  return (
    <div className="live-detail" data-testid="match-live">
      <MatchEvents events={d.live_events || []} testid="match-live-events" />
      {q.loading ? <Loading rows={2} /> : q.error ? <ErrorBox error={q.error} onRetry={q.reload} /> : <LiveLineups lineups={q.data.lineups} home={d.home.name} away={d.away.name} />}
    </div>
  );
}

function Pitch({ d }) {
  const pp = {};
  (d.forecasts || []).forEach((f) => { if (f.player_iid != null && f.p_play != null) pp[f.player_iid] = Math.max(pp[f.player_iid] || 0, f.p_play); });
  const predicted = !d.starters.length;
  const list = predicted ? d.predicted || [] : d.starters;
  const by = (iid) => {
    const xs = list.filter((s) => s.team_iid === iid);
    const seen = new Set();
    return xs.filter((s) => !seen.has(s.player_iid) && seen.add(s.player_iid)).sort((a, b) => Number(!!b.confirmed) - Number(!!a.confirmed) || (pp[b.player_iid] ?? 1) - (pp[a.player_iid] ?? 1)).slice(0, 11);
  };
  if (!list.length) return <Empty icon="users">No lineups yet. They usually arrive about an hour before kickoff.</Empty>;
  const sides = [[d.home, by(d.match.home_iid), "home"], [d.away, by(d.match.away_iid), "away"]];
  const conf = !predicted && d.starters.every((s) => s.confirmed);
  return (
    <>
      <p className="muted small" data-testid={predicted ? "pitch-predicted" : "pitch-lineups"}>{conf ? <span className="k-tag k-tag--up">Lineups confirmed</span> : predicted ? "Our predicted eleven: the most likely starters from each player's chance to play. The real lineups replace it about an hour before kickoff" : "Predicted eleven, with each player's chance to start"}{!predicted && <> · {sides.map(([t, xs]) => `${t.name} ${xs[0]?.formation || ""}`).join(" · ")}</>}</p>
      <div className="pitch" data-testid="pitch">
        <span className="pitch-half" aria-hidden="true" /><span className="pitch-circle" aria-hidden="true" />
        {sides.map(([t, xs, k]) => { const used = {}; return xs.map((s) => {
          const top = k === "home" ? (s.pitch_x || 0) * 48 + 2 : 98 - (s.pitch_x || 0) * 48;
          const base = k === "home" ? (s.pitch_y ?? 0.5) * 100 : 100 - (s.pitch_y ?? 0.5) * 100;
          const key = `${Math.round(top / 7)}-${Math.round(base / 12)}`;
          const n = used[key] = (used[key] || 0) + 1;
          const left = Math.min(94, Math.max(6, base + (n > 1 ? (n % 2 ? -1 : 1) * Math.ceil((n - 1) / 2) * 12 : 0)));
          return (
            <Link key={`${k}-${s.player_iid}`} to={s.player ? `/player/${s.player.id}` : "#"} className={`pp pp--${k}${!conf && pp[s.player_iid] != null && pp[s.player_iid] < 0.7 ? " pp--unsure" : ""}`} style={{ top: `${top}%`, left: `${left}%` }} title={s.player?.name} data-testid={`pitch-player-${s.player_iid}`}>
              <PlayerAvatar player={s.player} size={32} />
              <span className="pp-name">{s.shirt_number ? `${s.shirt_number} ` : ""}{(s.player?.name || "").split(" ").slice(-1)[0]}</span>
              {!conf && pp[s.player_iid] != null && <span className="pp-pct">{pct(pp[s.player_iid])}</span>}
            </Link>
          );
        }); })}
      </div>
    </>
  );
}

function Players({ d }) {
  const [team, setTeam] = useState("home");
  const t = team === "home" ? d.home : d.away;
  const q = useApi(`/teams/${t.id}/squad-grid`, { stat: "shots", last: 10 });
  return (
    <>
      <Seg label="Team" value={team} onChange={setTeam} options={[{ id: "home", label: d.home.name }, { id: "away", label: d.away.name }]} testid="players-team" />
      {q.loading ? <Loading /> : q.error ? <ErrorBox error={q.error} onRetry={q.reload} /> : !q.data.rows.length ? <Empty icon="users">No player data for this club yet.</Empty> : (
        <div className="tbl-wrap"><table className="tbl" data-testid="players-table">
          <thead><tr><th scope="col">Player</th><th scope="col">Games</th><th scope="col">Shots avg</th><th scope="col">Shots total</th></tr></thead>
          <tbody>{q.data.rows.map((r) => (
            <tr key={r.player_iid}><td><Link className="cell-person" to={`/player/${r.player?.id}`}><PlayerAvatar player={r.player} size={28} /><span>{r.player?.name}<small className="muted"> {posLabel(r.player?.pos)}</small></span></Link></td>
              <td className="num">{r.games.length}</td><td className="num">{num1(r.avg)}</td><td className="num">{num1(r.total)}</td></tr>
          ))}</tbody>
        </table></div>
      )}
    </>
  );
}

function H2H({ d }) {
  const h = d.h2h;
  if (!h.matches.length) return <Empty icon="clock">These clubs have not met in the matches we hold.</Empty>;
  return (
    <>
      <div className="h2h-sum" data-testid="h2h-summary"><span><b>{h.a_wins}</b><Crest team={d.home} size={20} />{d.home.name}</span><span><b>{h.draws}</b>Draws</span><span><b>{h.b_wins}</b><Crest team={d.away} size={20} />{d.away.name}</span></div>
      <ul className="mlist">{h.matches.map((m) => <MatchRow key={m.iid} m={m} />)}</ul>
    </>
  );
}

const EV = { goal: ["ball", "Goal"], yellow: ["card-y", "Yellow card"], red: ["card-r", "Red card"], sub: ["swap", "Substitution"] };
const mins = (e) => `${e.minute}${e.added ? `+${e.added}` : ""}'`;

function Events({ d }) {
  const [only, setOnly] = useState("all");
  const ev = d.events.filter((e) => only === "all" || (only === "cards" ? e.type === "yellow" || e.type === "red" : e.type === only));
  const count = (s, t) => d.events.filter((e) => e.side === s && (t === "cards" ? e.type === "yellow" || e.type === "red" : e.type === t)).length;
  if (!d.events.length) return <Empty icon="clock" testid="events-empty">{d.match.status === "final" ? "Goals, cards and substitutions for this match are still loading." : "Goals, cards and substitutions show here after full time."}</Empty>;
  return (
    <>
      <div className="ev-sum" data-testid="events-summary">
        {[["goal", "Goals"], ["cards", "Cards"], ["sub", "Subs"]].map(([t, l]) => <span key={t}><b>{count("home", t)}</b><em>{l}</em><b>{count("away", t)}</b></span>)}
      </div>
      <Seg label="Show" value={only} onChange={setOnly} options={[{ id: "all", label: "All" }, { id: "goal", label: "Goals" }, { id: "cards", label: "Cards" }, { id: "sub", label: "Subs" }]} testid="events-filter" />
      <ol className="ev-list" data-testid="events-list">
        {ev.map((e, i) => (
          <li key={i} className={`ev ev--${e.side} ev--${e.type}`} data-testid={`event-${i}`}>
            <span className="ev-min">{mins(e)}</span>
            <span className={`ev-ico ev-ico--${e.type}`} aria-label={EV[e.type][1]} role="img" />
            <span className="ev-txt">
              {e.type === "sub" ? <><b>{e.player_in?.id ? <Link to={`/player/${e.player_in.id}`}>{e.player_in.name}</Link> : e.in_name}</b><small>on for {e.player?.id ? <Link to={`/player/${e.player.id}`}>{e.player.name}</Link> : e.player_name}</small></>
                : <><b>{e.player?.id ? <Link to={`/player/${e.player.id}`}>{e.player.name}</Link> : e.player_name}</b><small>{EV[e.type][1]}{e.penalty ? " (penalty)" : ""}{e.own_goal ? " (own goal)" : ""}</small></>}
            </span>
          </li>
        ))}
      </ol>
    </>
  );
}

function Lineups({ d }) {
  return (
    <div className="mc-lineups" data-testid="match-lineups">
      <div className="mc-pitchcol"><Pitch d={d} /></div>
      <MatchNotes d={d} />
    </div>
  );
}

const JUMPS = [["form", "Form"], ["h2h", "Head to head"], ["first", "First goal"], ["players", "Players"], ["style", "Style"]];
function Analysis({ d }) {
  const go = (id) => document.getElementById(`an-${id}`)?.scrollIntoView({ behavior: "smooth", block: "start" });
  return (
    <div className="mc-an" data-testid="match-analysis">
      <nav className="an-jump" aria-label="Jump to a section">{JUMPS.map(([id, label]) => <button key={id} type="button" className="chip" onClick={() => go(id)} data-testid={`an-jump-${id}`}>{label}</button>)}</nav>
      <section id="an-form" className="an-sec"><Form d={d} /></section>
      <section id="an-h2h" className="an-sec"><h2 className="k-sec">Head to head</h2><H2H d={d} /></section>
      <section id="an-first" className="an-sec"><h2 className="k-sec">Who scores first</h2><div className="fg-pair" data-testid="match-first-goal"><FirstGoal team={d.home} compact testid="first-goal-home" /><FirstGoal team={d.away} compact testid="first-goal-away" /></div></section>
      <section id="an-players" className="an-sec"><h2 className="k-sec">Shots by player · last 10 games</h2><Players d={d} /></section>
      <section id="an-style" className="an-sec"><h2 className="k-sec">Playing style</h2>
        {d.matchup_locked ? <Empty icon="padlock" testid="matchup-locked">The style comparison is part of a bigger plan. <ProLock testid="matchup-pro" /></Empty>
          : <div className="split2">{[d.home, d.away].map((t, i) => <div key={t.id} className="card"><h3 className="h3 team"><Crest team={t} size={22} />{t.name}</h3><div className="chips">{(d.styles?.[i ? d.match.away_iid : d.match.home_iid]?.tactics || []).map((x) => <TacticChip key={x} t={x} />)}{!(d.styles?.[i ? d.match.away_iid : d.match.home_iid]?.tactics || []).length && <span className="k-faint">No clear style yet</span>}</div></div>)}</div>}
      </section>
    </div>
  );
}

export default function Match() {
  const { id } = useParams();
  const [poll, setPoll] = useState(0);
  const q = useApi(`/matches/${id}`, undefined, { every: poll });
  // The tab lives in the URL (?tab=), so a tab can be linked to and shared, a reload keeps it, and
  // Back returns to the tab before -- each switch is a history entry, the way a reader treats a
  // tab that changes the whole page below the hero. The default tab is NOT written: a plain
  // /match/:id always opens on the tab its state calls for, and that changes as the match does.
  const [sp, setSp] = useSearchParams();
  const pick = sp.get("tab");
  const d = q.data;
  const isLive = isLiveNow(d?.match);
  useEffect(() => setPoll(isLive ? 30000 : 0), [isLive]);                  // live score, events and minute refresh by themselves
  const st = d ? matchState(d) : "before";
  // Once the hero has scrolled under the header, a compact score bar takes its place above the tabs.
  const heroRef = useRef(null);
  const [mini, setMini] = useState(false);
  const hasD = !!d;
  useEffect(() => {
    const el = heroRef.current?.querySelector("[data-testid='match-hero']");
    if (!el || typeof IntersectionObserver === "undefined") return undefined;
    const hh = parseInt(getComputedStyle(document.documentElement).getPropertyValue("--header-h"), 10) || 64;
    const io = new IntersectionObserver(([e]) => setMini(!e.isIntersecting && e.boundingClientRect.top < hh), { rootMargin: `-${hh}px 0px 0px 0px` });
    io.observe(el);
    return () => io.disconnect();
  }, [hasD, id]);
  // Four tabs. The first one is the match itself while it is on (Live) or over (Recap); before kick-off it is the forecasts.
  const first = st === "live" ? "live" : st === "final" ? "recap" : null;
  // The one page seo.title_template was written for, so it is the one that supplies {team1}/{team2}.
  useTitle(d ? `${d.home.name} v ${d.away.name}` : "Match", {
    type: "article",
    vars: d ? { team1: d.home.name, team2: d.away.name } : undefined,
    description: d ? `How likely each forecast is for ${d.home.name} v ${d.away.name}, and the reasons behind it.` : undefined,
  });
  const paneRef = useRef(null);
  if (q.loading && !d) return <Loading rows={5} />;
  if (q.error) return <ErrorBox error={q.error} onRetry={q.reload} />;
  const n = cardsOf(d).filter((f) => f.p >= 0.5).length;
  const confirmed = (d.starters || []).length > 0 && d.starters.every((s) => s.confirmed);
  const tabs = [
    ...(first ? [{ id: first, label: first === "live" ? "Live" : "Recap" }] : []),
    { id: "forecasts", label: "Forecasts", badge: n || null, badgeLabel: n ? `${n} forecasts` : undefined },
    { id: "lineups", label: "Lineups", badge: confirmed ? "✓" : null, badgeLabel: "confirmed" },
    { id: "analysis", label: "Analysis" },
  ];
  // A ?tab= this state does not have (recap on a match not yet played, an old link) opens the default.
  const def = first || "forecasts";
  const tab = tabs.some((t) => t.id === pick) ? pick : def;
  const setTab = (t) => {
    if (t === tab) return;
    const next = new URLSearchParams(sp);
    if (t === def) next.delete("tab"); else next.set("tab", t);
    setSp(next, { preventScrollReset: true });
    // Switching while deep in a long tab used to leave the reader wherever the old tab's height put
    // them -- often in the footer of the new one. Keep the tab bar where it is and start the new tab
    // at its top, the way an app's segmented tabs behave. Above that point nothing moves.
    const pane = paneRef.current;
    if (pane && mini) {
      const top = pane.getBoundingClientRect().top + window.scrollY - (document.querySelector(".mc-sticky")?.offsetHeight || 0) - (parseInt(getComputedStyle(document.documentElement).getPropertyValue("--header-h"), 10) || 64);
      if (window.scrollY > top) requestAnimationFrame(() => window.scrollTo({ top, behavior: "auto" }));
    }
  };
  return (
    <section className={`mc-page${mini ? " is-mini" : ""}`} data-testid="match-page">
      <h1 className="sr-only">{d.home.name} v {d.away.name}</h1>
      <div ref={heroRef}><Hero d={d} /></div>
      <div className="mc-sticky">
        <MiniBar d={d} shown={mini} />
        <Tabs value={tab} onChange={setTab} testid="match-tabs" className="mc-tabs" tabs={tabs} label="Match sections" panel="match-panel" />
      </div>
      <div className="mc-pane" role="tabpanel" id="match-panel" aria-labelledby={`match-tabs-tab-${tab}`} ref={paneRef} data-testid={`match-pane-${tab}`}>
        {tab === "live" && (d.live?.sid ? <LiveTab d={d} /> : <Events d={d} />)}
        {tab === "recap" && <Events d={d} />}
        {tab === "forecasts" && <Forecasts d={d} matchId={id} />}
        {tab === "lineups" && <Lineups d={d} />}
        {tab === "analysis" && <Analysis d={d} />}
      </div>
    </section>
  );
}
