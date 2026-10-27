// Screens 5 and 6: Leagues (country groups with search) and League (Fixtures, Results, Leaderboards, Teams).
import { useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { useApi } from "../lib/useApi";
import { Crest, LeagueMark, PlayerAvatar } from "../components/Media";
import { Empty, ErrorBox, Loading } from "../components/States";
import { Tabs } from "../components/Ui";
import { MatchRow, STATS, Seg, Select, num1, posLabel, useTitle } from "../components/Football";

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
function Referees({ id }) {
  const q = useApi(`/leagues/${id}/referees`);
  if (q.loading && !q.data) return <Loading />;
  if (q.error) return <ErrorBox error={q.error} onRetry={q.reload} />;
  if (!q.data.length) return <Empty icon="flag" testid="referees-empty">Referee records are still loading for this league.</Empty>;
  return (
    <div className="tbl-wrap"><table className="tbl" data-testid="referee-table">
      <thead><tr><th scope="col">Referee</th><th scope="col">Games</th><th scope="col">Yellows a game</th><th scope="col">Reds a game</th><th scope="col">Penalties a game</th><th scope="col">Home wins</th></tr></thead>
      <tbody>{q.data.map((r) => (
        <tr key={r.name} data-testid="referee-row"><td><b>{r.name}</b></td><td className="num">{r.matches}</td><td className="num">{num1(r.yellow_pg)}</td><td className="num">{r.red_pg == null ? "–" : r.red_pg.toFixed(2)}</td><td className="num">{r.pens_pg == null ? "–" : r.pens_pg.toFixed(2)}</td><td className="num">{pc(r.home_win_pct)}</td></tr>
      ))}</tbody>
    </table></div>
  );
}

function Teams({ id, next }) {
  const q = useApi(`/leagues/${id}/fixtures`, { status: "final", limit: 200 });
  const teams = useMemo(() => {
    const t = new Map();
    [...(next || []), ...(q.data || [])].forEach((m) => [m.home, m.away].forEach((x) => x && t.set(x.id, x)));
    return [...t.values()].sort((a, b) => a.name.localeCompare(b.name));
  }, [q.data, next]);
  if (q.loading && !q.data) return <Loading />;
  if (q.error) return <ErrorBox error={q.error} onRetry={q.reload} />;
  if (!teams.length) return <Empty icon="shield">No clubs loaded yet.</Empty>;
  return <ul className="tgrid" data-testid="league-teams">{teams.map((t) => <li key={t.id}><Link to={`/team/${t.id}`} className="tcard"><Crest team={t} size={40} /><b>{t.name}</b></Link></li>)}</ul>;
}

export default function League() {
  const { id } = useParams();
  const q = useApi(`/leagues/${id}`);
  const [tab, setTab] = useState("fixtures");
  useTitle(q.data?.name || "League");
  if (q.loading && !q.data) return <Loading rows={5} />;
  if (q.error) return <ErrorBox error={q.error} onRetry={q.reload} />;
  const d = q.data;
  return (
    <section data-testid="league-page">
      <header className="phead"><LeagueMark league={d} size={40} decorative={false} /><div><h1>{d.name}</h1><p className="muted">{[d.country, d.current_season].filter(Boolean).join(" · ")}</p></div></header>
      <Tabs value={tab} onChange={setTab} testid="league-tabs" tabs={[{ id: "fixtures", label: "Fixtures" }, { id: "results", label: "Results" }, { id: "leaders", label: "Leaderboards" }, { id: "referees", label: "Referees" }, { id: "teams", label: "Teams" }]} />
      {tab === "fixtures" && <List rows={d.next} empty="No upcoming fixtures loaded." />}
      {tab === "results" && <Results id={id} />}
      {tab === "leaders" && <Leaders id={id} />}
      {tab === "referees" && <Referees id={id} />}
      {tab === "teams" && <Teams id={id} next={d.next} />}
    </section>
  );
}
