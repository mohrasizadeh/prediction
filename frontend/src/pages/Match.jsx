// Screen 2, Match (docs/01 §5): hero with win/draw/loss and tactic chips; tabs Forecasts, Lineups, Players, H2H, Matchup.
import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { useApi } from "../lib/useApi";
import { PlayerAvatar } from "../components/Media";
import { Empty, ErrorBox, Loading } from "../components/States";
import { Tabs } from "../components/Ui";
import { MatchRow, Seg, TacticChip, num1, posLabel, useTitle } from "../components/Football";
import FirstGoal from "../components/FirstGoal";
import { Forecasts, Hero, Preview, Stats, matchState } from "../components/MatchCentre";
import MatchEvents from "../components/MatchEvents";
import LiveLineups from "../components/LiveLineups";
import { ProLock } from "../components/ui";

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
  const by = (iid) => {
    const xs = d.starters.filter((s) => s.team_iid === iid);
    const seen = new Set();
    return xs.filter((s) => !seen.has(s.player_iid) && seen.add(s.player_iid)).sort((a, b) => Number(!!b.confirmed) - Number(!!a.confirmed) || (pp[b.player_iid] ?? 1) - (pp[a.player_iid] ?? 1)).slice(0, 11);
  };
  if (!d.starters.length) return <Empty icon="users">No lineups yet. They usually arrive about an hour before kickoff.</Empty>;
  const sides = [[d.home, by(d.match.home_iid), "home"], [d.away, by(d.match.away_iid), "away"]];
  const conf = d.starters.every((s) => s.confirmed);
  return (
    <>
      <p className="muted small">{conf ? <span className="k-tag k-tag--up">Lineups confirmed</span> : "Predicted eleven, with each player's chance to start"} · {sides.map(([t, xs]) => `${t.name} ${xs[0]?.formation || ""}`).join(" · ")}</p>
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
              {!conf && pp[s.player_iid] != null && <span className="pp-pct">{Math.round(pp[s.player_iid] * 100)}%</span>}
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
      <div className="h2h-sum" data-testid="h2h-summary"><span><b>{h.a_wins}</b>{d.home.name}</span><span><b>{h.draws}</b>Draws</span><span><b>{h.b_wins}</b>{d.away.name}</span></div>
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

export default function Match() {
  const { id } = useParams();
  const q = useApi(`/matches/${id}`);
  const [pick, setTab] = useState(null);
  const d = q.data;
  const st = d ? matchState(d) : "before";
  const tab = pick || (st === "live" && d?.live?.sid ? "live" : st === "final" ? "events" : "preview");
  useTitle(d ? `${d.home.name} v ${d.away.name}` : "Match");
  if (q.loading && !d) return <Loading rows={5} />;
  if (q.error) return <ErrorBox error={q.error} onRetry={q.reload} />;
  return (
    <section data-testid="match-page">
      <h1 className="sr-only">{d.home.name} v {d.away.name}</h1>
      <Hero d={d} />
      <Tabs value={tab} onChange={setTab} testid="match-tabs" tabs={[...(st === "live" && d.live?.sid ? [{ id: "live", label: "Live" }] : []), ...(st === "final" ? [{ id: "events", label: "Recap" }] : []), { id: "preview", label: "Preview" }, { id: "forecasts", label: `Forecasts (${cardsOf(d).filter((f) => f.p >= 0.5).length})` }, { id: "lineups", label: "Lineups" }, { id: "stats", label: "Stats" }, ...(st !== "final" ? [{ id: "events", label: "Events" }] : []), { id: "first", label: "First goal" }, { id: "players", label: "Players" }, { id: "h2h", label: "H2H" }, { id: "matchup", label: "Matchup" }]} />
      {tab === "preview" && <Preview d={d} />}
      {tab === "forecasts" && <Forecasts d={d} />}
      {tab === "stats" && <Stats d={d} />}
      {tab === "live" && d.live?.sid && <LiveTab d={d} />}
      {tab === "lineups" && <Pitch d={d} />}
      {tab === "events" && <Events d={d} />}
      {tab === "first" && <div className="fg-pair" data-testid="match-first-goal"><FirstGoal team={d.home} compact testid="first-goal-home" /><FirstGoal team={d.away} compact testid="first-goal-away" /></div>}
      {tab === "players" && <Players d={d} />}
      {tab === "h2h" && <H2H d={d} />}
      {tab === "matchup" && (d.matchup_locked ? <Empty icon="padlock" testid="matchup-locked">The style comparison is part of a bigger plan. <ProLock testid="matchup-pro" /></Empty>
        : <div className="split2">{[d.home, d.away].map((t, i) => <div key={t.id} className="card"><h2 className="h3">{t.name}</h2><div className="chips">{(d.styles?.[i ? d.match.away_iid : d.match.home_iid]?.tactics || []).map((x) => <TacticChip key={x} t={x} />)}</div></div>)}</div>)}
    </section>
  );
}
