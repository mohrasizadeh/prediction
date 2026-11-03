// Screens 5 and 6: Leagues (country groups with search) and League (Fixtures, Results, Leaderboards, Teams).
import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { useApi } from "../lib/useApi";
import { Crest, LeagueMark, PlayerAvatar } from "../components/Media";
import { Empty, ErrorBox, Loading } from "../components/States";
import { Tabs } from "../components/Ui";
import TeamMatrix from "../components/TeamMatrix";
import Standings from "../components/Standings";
import { Segmented } from "../components/ui";
import { MatchRow, STATS, Seg, Select, kickoff, num1, posLabel, useTitle } from "../components/Football";
import { refPath } from "./Referee";

export function Leagues() {
  const [q, setQ] = useState("");
  const r = useApi("/leagues", { q });
  useTitle("Leagues");
  return (
    <section data-testid="leagues-page">
      <h1>Leagues</h1>
      <input className="search-in" type="search" placeholder="Search leagues" value={q} onChange={(e) => setQ(e.target.value)} aria-label="Search leagues" data-testid="leagues-search" />
      {r.loading && !r.data ? <Loading /> : r.error ? <ErrorBox error={r.error} onRetry={r.reload} /> : !r.data.countries.length ? <Empty icon="trophy">No league matches that search.</Empty> : r.data.countries.map((c) => (
        <div key={c.country} className="card">
          <h2 className="h3">{c.country}</h2>
          <ul className="llist">{c.leagues.map((l) => (
            <li key={l.id}><Link to={`/league/${l.id}`} className="lrow" data-testid={`league-link-${l.id}`}><LeagueMark league={l} size={28} /><span><b>{l.name}</b><small className="muted">{l.current_season}</small></span></Link></li>
          ))}</ul>
        </div>
      ))}
    </section>
  );
}

function List({ rows, empty }) {
  return rows.length ? <ul className="mlist card">{rows.map((m) => <MatchRow key={m.id} m={m} />)}</ul> : <Empty icon="calendar">{empty}</Empty>;
}

function Results({ id }) {
  const q = useApi(`/leagues/${id}/fixtures`, { status: "final", limit: 60 });
  if (q.loading && !q.data) return <Loading />;
  if (q.error) return <ErrorBox error={q.error} onRetry={q.reload} />;
  return <List rows={q.data} empty="No results loaded yet." />;
}

function Leaders({ id }) {
  const [stat, setStat] = useState("shots");
  const [per90, setPer90] = useState(false);
  const q = useApi(`/leagues/${id}/leaderboard`, { stat, per90, limit: 30 });
  return (
    <>
      <div className="filters">
        <Select label="Stat" value={stat} onChange={setStat} options={STATS.filter((s) => s.id !== "minutes")} testid="leader-stat" />
        <Seg label="Count" value={String(per90)} onChange={(v) => setPer90(v === "true")} options={[{ id: "false", label: "Total" }, { id: "true", label: "Per 90" }]} testid="leader-per90" />
      </div>
      {q.loading && !q.data ? <Loading /> : q.error ? <ErrorBox error={q.error} onRetry={q.reload} /> : !q.data.length ? <Empty icon="trophy">Not enough minutes played yet. Players need 450 minutes to appear.</Empty> : (
        <div className="tbl-wrap"><table className="tbl" data-testid="leader-table">
          <thead><tr><th scope="col">#</th><th scope="col">Player</th><th scope="col">Games</th><th scope="col">{per90 ? "Per 90" : "Total"}</th></tr></thead>
          <tbody>{q.data.map((r, i) => (
            <tr key={r._id}><td className="num muted">{i + 1}</td><td><Link className="cell-person" to={`/player/${r.player?.id}`}><PlayerAvatar player={r.player} size={28} /><span>{r.player?.name}<small className="muted"> {posLabel(r.player?.pos)}</small></span></Link></td>
              <td className="num">{r.games}</td><td className="num"><b>{num1(per90 ? r.per90 : r.total)}</b></td></tr>
          ))}</tbody>
        </table></div>
      )}
    </>
  );
}

const pc = (v) => (v == null ? "–" : `${Math.round(v * 100)}%`);
function Assignments({ id }) {
  const q = useApi(`/leagues/${id}/referee-assignments`);
  if (q.loading && !q.data) return <Loading rows={2} />;
  if (q.error) return <ErrorBox error={q.error} onRetry={q.reload} />;
  const d = q.data;
  if (!d.rows.length) return null;
  const avg = d.league_avg;
  return (
    <section className="ref-assign" data-testid="referee-assignments">
      <h3 className="h3">Next round referees</h3>
      <p className="muted small">Referees are usually named a day or two before kickoff.{avg?.yellow_pg != null ? ` League average: ${avg.yellow_pg.toFixed(2)} yellows and ${(avg.pens_pg || 0).toFixed(2)} penalties a game.` : ""}</p>
      <ul className="ra-list">{d.rows.map((r) => (
        <li key={r.match_id} className="ra-row" data-testid={`assign-${r.match_id}`}>
          <Link to={`/match/${r.match_id}`} className="ra-fix"><span className="team"><Crest team={r.home} size={18} />{r.home?.name}</span><span className="team"><Crest team={r.away} size={18} />{r.away?.name}</span><small className="muted">{kickoff(r.kickoff)}</small></Link>
          {r.referee ? (
            <span className="ra-ref"><Link to={refPath(r.referee)} data-testid="assign-referee"><b>{r.referee}</b></Link>
              <small className="muted">{r.stats?.yellow_pg != null ? `${r.stats.yellow_pg.toFixed(2)} yellows · ${(r.stats.pens_pg || 0).toFixed(2)} pens a game · ${r.stats.matches} games` : "No games here yet"}</small>
              {r.stats?.yellow_pg != null && avg && r.stats.matches >= 5 && <span className={`ra-tag ${r.stats.yellow_pg > avg.yellow_pg * 1.1 ? "is-high" : r.stats.yellow_pg < avg.yellow_pg * 0.9 ? "is-low" : ""}`}>{r.stats.yellow_pg > avg.yellow_pg * 1.1 ? "Cards above average" : r.stats.yellow_pg < avg.yellow_pg * 0.9 ? "Cards below average" : "Around average"}</span>}</span>
          ) : <span className="ra-ref muted small" data-testid="assign-tbc">Referee not named yet</span>}
        </li>
      ))}</ul>
    </section>
  );
}

function Referees({ id }) {
  const q = useApi(`/leagues/${id}/referees`);
  if (q.loading && !q.data) return <Loading />;
  if (q.error) return <ErrorBox error={q.error} onRetry={q.reload} />;
  if (!q.data.length) return <Empty icon="flag" testid="referees-empty">Referee records are still loading for this league.</Empty>;
  return (
    <>
    <Assignments id={id} />
    <p className="muted small"><Link to="/referees" data-testid="referees-all-link">Compare referees across all leagues</Link></p>
    <div className="tbl-wrap"><table className="tbl" data-testid="referee-table">
      <thead><tr><th scope="col">Referee</th><th scope="col">Games</th><th scope="col">Yellows a game</th><th scope="col">Reds a game</th><th scope="col">Penalties a game</th><th scope="col">Home wins</th></tr></thead>
      <tbody>{q.data.map((r) => (
        <tr key={r.name} data-testid="referee-row"><td><Link to={refPath(r.name)} data-testid="referee-link"><b>{r.name}</b></Link></td><td className="num">{r.matches}</td><td className="num">{r.yellow_pg == null ? "–" : r.yellow_pg.toFixed(2)}</td><td className="num">{r.red_pg == null ? "–" : r.red_pg.toFixed(2)}</td><td className="num">{r.pens_pg == null ? "–" : r.pens_pg.toFixed(2)}</td><td className="num">{pc(r.home_win_pct)}</td></tr>
      ))}</tbody>
    </table></div>
    </>
  );
}

function Bookings({ id }) {
  const q = useApi(`/leagues/${id}/booking-risk`);
  if (q.loading && !q.data) return <Loading />;
  if (q.error) return <ErrorBox error={q.error} onRetry={q.reload} />;
  if (!q.data.rows.length) return <Empty icon="flag" testid="bookings-empty">No card forecasts for the next round yet. They appear once the next matches are loaded.</Empty>;
  return (
    <>
      <p className="muted small" data-testid="bookings-range">Players most likely to get a yellow card in the next round, {kickoff(q.data.from)} onwards. Uses each player's card rate, the opponent and the referee when named.</p>
      <ol className="book-list" data-testid="bookings-list">{q.data.rows.map((f, i) => (
        <li key={f.id} className="book-row" data-testid={`booking-${i}`}>
          <span className="book-rank">{i + 1}</span>
          <PlayerAvatar player={f.player} size={36} />
          <span className="book-who"><Link to={`/player/${f.player?.id}`}><b>{f.player?.name}</b></Link>
            <small className="muted">{f.team?.name} {f.home_iid === f.team_iid ? "v" : "at"} <Link to={`/match/${f.match_id}`}>{f.opp?.name}</Link>{f.referee ? <> · <Link to={refPath(f.referee)}>{f.referee}</Link></> : ""}</small></span>
          <span className="book-p"><b>{Math.round(f.p * 100)}%</b><span className="book-bar"><i style={{ width: `${Math.round(f.p * 100)}%` }} /></span></span>
        </li>
      ))}</ol>
    </>
  );
}

function Teams({ id }) {
  return <TeamMatrix leagueId={id} />;
}

function Overview({ id, d }) {
  return (
    <div className="lg-ov" data-testid="league-overview">
      <section><h2 className="k-sec">Next up</h2><List rows={(d.next || []).slice(0, 6)} empty="No upcoming fixtures loaded." /></section>
      <Assignments id={id} />
    </div>
  );
}

function FixturesTab({ id, d }) {
  const [v, setV] = useState("next");
  return <><Segmented options={[{ id: "next", label: "Upcoming" }, { id: "results", label: "Results" }]} value={v} onChange={setV} label="Fixtures" testid="league-fixtures-view" />
    {v === "next" ? <List rows={d.next} empty="No upcoming fixtures loaded." /> : <Results id={id} />}</>;
}

function LeadersTab({ id }) {
  const [v, setV] = useState("players");
  return <><Segmented options={[{ id: "players", label: "Players" }, { id: "bookings", label: "Bookings" }, { id: "referees", label: "Referees" }]} value={v} onChange={setV} label="Leaders" testid="league-leaders-view" />
    {v === "players" ? <Leaders id={id} /> : v === "bookings" ? <Bookings id={id} /> : <Referees id={id} />}</>;
}

export default function League() {
  const { id } = useParams();
  const q = useApi(`/leagues/${id}`);
  const [tab, setTab] = useState("overview");
  useTitle(q.data?.name || "League");
  if (q.loading && !q.data) return <Loading rows={5} />;
  if (q.error) return <ErrorBox error={q.error} onRetry={q.reload} />;
  const d = q.data;
  return (
    <section data-testid="league-page">
      <header className="phead"><LeagueMark league={d} size={40} decorative={false} /><div><h1>{d.name}</h1><p className="muted">{[d.country, d.current_season].filter(Boolean).join(" · ")}</p></div></header>
      <Tabs value={tab} onChange={setTab} testid="league-tabs" tabs={[{ id: "overview", label: "Overview" }, { id: "table", label: "Table" }, { id: "teams", label: "Teams" }, { id: "fixtures", label: "Fixtures" }, { id: "leaders", label: "Leaders" }]} />
      <div className="lg-tab">
        {tab === "overview" && <Overview id={id} d={d} />}
        {tab === "table" && <Standings id={id} season={d.current_season} zones={d.zones || []} />}
        {tab === "teams" && <Teams id={id} />}
        {tab === "fixtures" && <FixturesTab id={id} d={d} />}
        {tab === "leaders" && <LeadersTab id={id} />}
      </div>
    </section>
  );
}
