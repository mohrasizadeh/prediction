// Referee page: cards and penalties per game, league breakdown, and every match on record.
import { Link, useParams } from "react-router-dom";
import { useApi } from "../lib/useApi";
import { Crest } from "../components/Media";
import { Empty, ErrorBox, Loading } from "../components/States";
import { kickoff, shortDay, useTitle } from "../components/Football";

const f2 = (v) => (v == null ? "–" : v.toFixed(2));
const pc = (a, b) => (b ? `${Math.round((a / b) * 100)}%` : "–");
export const refPath = (name) => `/referee/${encodeURIComponent(name)}`;

function Tiles({ d }) {
  const t = d.totals;
  return (
    <dl className="ref-tiles" data-testid="referee-tiles">
      <div><dt>Matches</dt><dd>{t.matches}</dd></div>
      <div><dt>Yellows a game</dt><dd data-testid="referee-yellow-pg">{f2(d.per_game.yellow)}</dd></div>
      <div><dt>Reds a game</dt><dd>{f2(d.per_game.red)}</dd></div>
      <div><dt>Penalties a game</dt><dd>{f2(d.per_game.pens)}</dd></div>
      <div><dt>Home wins</dt><dd>{pc(t.home_wins, t.matches)}</dd></div>
      <div><dt>Draws</dt><dd>{pc(t.draws, t.matches)}</dd></div>
    </dl>
  );
}

export default function Referee() {
  const { name } = useParams();
  const q = useApi(`/referees/${encodeURIComponent(name)}`);
  useTitle(name);
  if (q.loading && !q.data) return <Loading rows={4} />;
  if (q.error) return <ErrorBox error={q.error} onRetry={q.reload} />;
  const d = q.data;
  return (
    <section data-testid="referee-page">
      <header className="phead"><span className="ref-badge" aria-hidden="true" /><div className="phead-main"><p className="muted small ref-eyebrow">Referee</p><h1>{d.name}</h1>
        <p className="muted">{d.totals.matches} matches on record{d.totals.with_events < d.totals.matches ? `, ${d.totals.with_events} with card data` : ""}.</p></div></header>
      <Tiles d={d} />
      {d.upcoming.length > 0 && (
        <section className="ref-section"><h2 className="h3">Next matches</h2>
          <ul className="mlist card" data-testid="referee-upcoming">{d.upcoming.map((m) => (
            <li key={m.match_id}><Link className="ref-row" to={`/match/${m.match_id}`}><span className="team"><Crest team={m.home} size={20} />{m.home?.name} v {m.away?.name}<Crest team={m.away} size={20} /></span><small className="muted">{m.league?.name} · {kickoff(m.kickoff)}</small></Link></li>
          ))}</ul>
        </section>
      )}
      {d.leagues.length > 1 && (
        <section className="ref-section"><h2 className="h3">By league</h2>
          <div className="tbl-wrap"><table className="tbl" data-testid="referee-leagues"><thead><tr><th scope="col">League</th><th scope="col">Games</th><th scope="col">Yellows</th><th scope="col">Reds</th><th scope="col">Penalties</th></tr></thead>
            <tbody>{d.leagues.map((r) => <tr key={r.league_iid}><td>{r.league ? <Link to={`/league/${r.league.id}`}>{r.league.name}</Link> : "–"}</td><td className="num">{r.matches}</td><td className="num">{f2(r.yellow_pg)}</td><td className="num">{f2(r.red_pg)}</td><td className="num">{f2(r.pens_pg)}</td></tr>)}</tbody></table></div>
        </section>
      )}
      <section className="ref-section"><h2 className="h3">Matches</h2>
        {!d.games.length ? <Empty icon="flag">No finished matches yet.</Empty> : (
          <div className="tbl-wrap"><table className="tbl" data-testid="referee-games"><thead><tr><th scope="col">Match</th><th scope="col">Score</th><th scope="col">Yellows</th><th scope="col">Reds</th><th scope="col">Penalties</th></tr></thead>
            <tbody>{d.games.map((g) => (
              <tr key={g.match_id} data-testid="referee-game"><td><Link to={`/match/${g.match_id}`} className="team"><Crest team={g.home} size={18} />{g.home?.name} v {g.away?.name}</Link><small className="muted sub-note">{g.league?.name} · {shortDay(g.kickoff)}</small></td>
                <td className="num">{g.score}</td><td className="num">{g.yellow ?? "–"}</td><td className="num">{g.red ?? "–"}</td><td className="num">{g.pens ?? "–"}</td></tr>
            ))}</tbody></table></div>
        )}
      </section>
    </section>
  );
}
