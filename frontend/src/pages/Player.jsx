// Screen 8, Player (docs/01 §5, docs/04 Chart): hero, next-fixture forecasts, Quick view chart, history table.
import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { useApi } from "../lib/useApi";
import { Crest, PlayerAvatar } from "../components/Media";
import { Empty, ErrorBox, Loading } from "../components/States";
import { ForecastCard, STATS, Seg, Select, kickoff, num1, posLabel, shortDay, useTitle } from "../components/Football";

function Chart({ games, stat, line }) {
  const rows = [...games].reverse();
  const max = Math.max(line + 1, ...rows.map((g) => g[stat] || 0));
  const hits = rows.filter((g) => g[stat] != null && g[stat] >= line).length;
  const known = rows.filter((g) => g[stat] != null).length;
  return (
    <>
      <p className="muted small" data-testid="chart-summary">{known ? `${line} or more in ${hits} of ${known} games.` : "No data for this stat."}</p>
      <div className="chart" role="img" aria-label={`${hits} of ${known} games at ${line} or more`} data-testid="quick-chart">
        <span className="chart-line" style={{ bottom: `${(line / max) * 100}%` }} aria-hidden="true" />
        {rows.map((g) => {
          const v = g[stat];
          return <span key={g.match_iid} className={"chart-bar" + (v != null && v >= line ? " hit" : "")} style={{ height: `${v ? (v / max) * 100 : 2}%` }} title={`${g.opp?.name || ""} ${shortDay(g.kickoff)}: ${v ?? "No data"}`}><i>{v ?? ""}</i></span>;
        })}
      </div>
    </>
  );
}

function History({ id }) {
  const [stat, setStat] = useState("shots");
  const [last, setLast] = useState(10);
  const [line, setLine] = useState(1);
  const [venue, setVenue] = useState("all");
  const [started, setStarted] = useState(false);
  const [table, setTable] = useState(false);
  const q = useApi(`/players/${id}/history`, { last, started, ...(venue !== "all" ? { venue } : {}) });
  return (
    <section className="card" data-testid="quick-view">
      <h2 className="h3">Quick view</h2>
      <div className="filters">
        <Select label="Stat" value={stat} onChange={setStat} options={STATS} testid="qv-stat" />
        <Seg label="Window" value={last} onChange={setLast} options={[5, 10, 20].map((n) => ({ id: n, label: `Last ${n}` }))} testid="qv-window" />
        <Seg label="Line" value={line} onChange={(v) => setLine(Number(v))} options={[1, 2, 3, 4, 5].map((n) => ({ id: n, label: `${n}+` }))} testid="qv-line" />
        <Seg label="Venue" value={venue} onChange={setVenue} options={[{ id: "all", label: "All" }, { id: "home", label: "Home" }, { id: "away", label: "Away" }]} testid="qv-venue" />
        <label className="check-inline"><input type="checkbox" checked={started} onChange={(e) => setStarted(e.target.checked)} data-testid="qv-started" /> Started only</label>
      </div>
      {q.loading && !q.data ? <Loading /> : q.error ? <ErrorBox error={q.error} onRetry={q.reload} /> : !q.data.games.length ? <Empty icon="activity">No games match these filters.</Empty> : (
        <>
          <Chart games={q.data.games} stat={stat} line={line} />
          <button type="button" className="linkish" onClick={() => setTable(!table)} data-testid="qv-table-toggle">{table ? "Hide table" : "Show table"}</button>
          {table && (
            <div className="tbl-wrap"><table className="tbl" data-testid="history-table">
              <thead><tr><th scope="col">Match</th><th scope="col">Min</th><th scope="col">Shots</th><th scope="col">On target</th><th scope="col">Tackles</th><th scope="col">Goals</th></tr></thead>
              <tbody>{q.data.games.map((g) => (
                <tr key={g.match_iid}><td><span className="team"><Crest team={g.opp} size={20} /> {g.home ? "v" : "at"} {g.opp?.name}<small className="muted"> {shortDay(g.kickoff)}</small></span></td>
                  <td className="num">{num1(g.minutes)}</td><td className="num">{num1(g.shots)}</td><td className="num">{num1(g.sot)}</td><td className="num">{num1(g.tackles)}</td><td className="num">{num1(g.goals)}</td></tr>
              ))}</tbody>
            </table></div>
          )}
        </>
      )}
    </section>
  );
}

export default function Player() {
  const { id } = useParams();
  const q = useApi(`/players/${id}`);
  useTitle(q.data?.player?.name || "Player");
  if (q.loading && !q.data) return <Loading rows={5} />;
  if (q.error) return <ErrorBox error={q.error} onRetry={q.reload} />;
  const { player: p, team, next_match: nx, forecasts } = q.data;
  const teams = nx ? { [nx.home_iid]: nx.home, [nx.away_iid]: nx.away } : {};
  return (
    <section data-testid="player-page">
      <header className="phead">
        <PlayerAvatar player={p} size={96} decorative={false} />
        <div className="phead-main">
          <h1>{p.name}</h1>
          <p className="muted">{posLabel(p.pos)}</p>
          {team && <Link to={`/team/${team.id}`} className="inline"><Crest team={team} size={20} /> {team.name}</Link>}
        </div>
      </header>
      <section className="card" data-testid="player-next">
        <h2 className="h3">Next match</h2>
        {nx ? <Link to={`/match/${nx.id}`} className="next-link"><span className="team"><Crest team={nx.home} size={20} />{nx.home?.name}</span><span className="muted">v</span><span className="team"><Crest team={nx.away} size={20} />{nx.away?.name}</span><time className="muted small">{kickoff(nx.kickoff)}</time></Link>
          : <p className="muted">No upcoming match loaded.</p>}
        {nx && (forecasts.length ? <div className="fgrid">{forecasts.map((f) => <ForecastCard key={f.id} f={{ ...f, player: p }} teams={teams} />)}</div>
          : <p className="muted small">No forecasts for this player yet.</p>)}
      </section>
      <History id={id} />
    </section>
  );
}
