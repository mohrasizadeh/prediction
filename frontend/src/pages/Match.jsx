// Screen 2, Match (docs/01 §5): hero with win/draw/loss and tactic chips; tabs Forecasts, Lineups, Players, H2H, Matchup.
import { useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { useApi } from "../lib/useApi";
import { Crest, PlayerAvatar } from "../components/Media";
import { Empty, ErrorBox, Loading } from "../components/States";
import { Tabs } from "../components/Ui";
import { ForecastCard, MatchRow, ProbBar, Seg, TacticChip, kickoff, num1, posLabel, useTitle } from "../components/Football";
import { ShareCard } from "../components/Share";

function Side({ team, rot, tactics, align }) {
  return (
    <Link to={`/team/${team.id}`} className={`hero-team hero-team--${align}`} data-testid={`match-team-${align}`}>
      <Crest team={team} size={64} eager />
      <b>{team.name}</b>
      <div className="chips">{(tactics || []).map((t) => <TacticChip key={t} t={t} />)}</div>
      {rot && rot.level !== "low" && <span className="tchip tchip--warn" title={rot.why}>Rotation risk: {rot.level}</span>}
    </Link>
  );
}

function Hero({ d }) {
  const m = d.match;
  const final = m.status === "final" && m.hg != null;
  return (
    <section className="hero card" data-testid="match-hero">
      <div className="hero-row">
        <Side team={d.home} rot={d.rotation?.[m.home_iid]} tactics={d.styles?.[m.home_iid]?.tactics} align="home" />
        <div className="hero-mid">
          {final ? <strong className="hero-score" data-testid="match-score">{m.hg} – {m.ag}</strong> : <span className="hero-v">v</span>}
          <time className="muted small">{kickoff(m.kickoff)}</time>
          <span className="chip-tag">{final ? "Full time" : m.status === "scheduled" ? "Not started" : m.status}</span>
        </div>
        <Side team={d.away} rot={d.rotation?.[m.away_iid]} tactics={d.styles?.[m.away_iid]?.tactics} align="away" />
      </div>
      <ProbBar probs={d.probs} />
      {d.probs && <p className="muted small hero-xg">Expected goals {num1(d.probs.xg_home)} – {num1(d.probs.xg_away)}</p>}
      <ShareCard d={d} />
    </section>
  );
}

function Forecasts({ d, teams }) {
  const [side, setSide] = useState("all");
  const [scope, setScope] = useState("all");
  const [shown, setShown] = useState(24);
  const rows = d.forecasts.filter((f) => (side === "all" || f.team_iid === (side === "home" ? d.match.home_iid : d.match.away_iid)) && (scope === "all" || f.scope === scope));
  return (
    <>
      <div className="filters">
        <Seg label="Team" value={side} onChange={setSide} options={[{ id: "all", label: "Both" }, { id: "home", label: d.home.name }, { id: "away", label: d.away.name }]} testid="fc-side" />
        <Seg label="Scope" value={scope} onChange={setScope} options={[{ id: "all", label: "All" }, { id: "player", label: "Players" }, { id: "team", label: "Teams" }]} testid="fc-scope" />
      </div>
      {rows.length ? <><div className="fgrid">{rows.slice(0, shown).map((f) => <ForecastCard key={f.id} f={f} teams={teams} homeIid={d.match.home_iid} />)}</div>
        {rows.length > shown && <button type="button" className="btn btn--secondary more-btn" onClick={() => setShown(shown + 24)} data-testid="fc-more">Show more ({rows.length - shown} left)</button>}</>
        : <Empty icon="target">No forecasts for this match yet. They appear once the engine has run.</Empty>}
    </>
  );
}

function Pitch({ d }) {
  const by = (iid) => d.starters.filter((s) => s.team_iid === iid);
  if (!d.starters.length) return <Empty icon="users">No lineups yet. They usually arrive about an hour before kickoff.</Empty>;
  const sides = [[d.home, by(d.match.home_iid), "home"], [d.away, by(d.match.away_iid), "away"]];
  const conf = d.starters.every((s) => s.confirmed);
  return (
    <>
      <p className="muted small">{conf ? "Confirmed lineups" : "Predicted lineups"} · {sides.map(([t, xs]) => `${t.name} ${xs[0]?.formation || ""}`).join(" · ")}</p>
      <div className="pitch" data-testid="pitch">
        <span className="pitch-half" aria-hidden="true" /><span className="pitch-circle" aria-hidden="true" />
        {sides.map(([t, xs, k]) => xs.map((s) => {
          const top = k === "home" ? (s.pitch_x || 0) * 48 + 2 : 98 - (s.pitch_x || 0) * 48;
          const left = k === "home" ? (s.pitch_y ?? 0.5) * 100 : 100 - (s.pitch_y ?? 0.5) * 100;
          return (
            <Link key={`${k}-${s.player_iid}`} to={s.player ? `/player/${s.player.id}` : "#"} className={`pp pp--${k}`} style={{ top: `${top}%`, left: `${left}%` }} title={s.player?.name}>
              <PlayerAvatar player={s.player} size={32} />
              <span className="pp-name">{s.shirt_number ? `${s.shirt_number} ` : ""}{(s.player?.name || "").split(" ").slice(-1)[0]}</span>
            </Link>
          );
        }))}
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

export default function Match() {
  const { id } = useParams();
  const q = useApi(`/matches/${id}`);
  const [tab, setTab] = useState("forecasts");
  const d = q.data;
  const teams = useMemo(() => (d ? { [d.match.home_iid]: d.home, [d.match.away_iid]: d.away } : {}), [d]);
  useTitle(d ? `${d.home.name} v ${d.away.name}` : "Match");
  if (q.loading && !d) return <Loading rows={5} />;
  if (q.error) return <ErrorBox error={q.error} onRetry={q.reload} />;
  return (
    <section data-testid="match-page">
      <h1 className="sr-only">{d.home.name} v {d.away.name}</h1>
      <Hero d={d} />
      <Tabs value={tab} onChange={setTab} testid="match-tabs" tabs={[{ id: "forecasts", label: `Forecasts (${d.forecasts.length})` }, { id: "lineups", label: "Lineups" }, { id: "players", label: "Players" }, { id: "h2h", label: "H2H" }, { id: "matchup", label: "Matchup" }]} />
      {tab === "forecasts" && <Forecasts d={d} teams={teams} />}
      {tab === "lineups" && <Pitch d={d} />}
      {tab === "players" && <Players d={d} />}
      {tab === "h2h" && <H2H d={d} />}
      {tab === "matchup" && (d.matchup_locked ? <Empty icon="padlock" testid="matchup-locked">The style comparison is part of a bigger plan.</Empty>
        : <div className="split2">{[d.home, d.away].map((t, i) => <div key={t.id} className="card"><h2 className="h3">{t.name}</h2><div className="chips">{(d.styles?.[i ? d.match.away_iid : d.match.home_iid]?.tactics || []).map((x) => <TacticChip key={x} t={x} />)}</div></div>)}</div>)}
    </section>
  );
}
