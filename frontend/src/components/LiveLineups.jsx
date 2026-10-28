// SportAPI lineups (docs/23): starters and bench, linked to our player pages where the name was matched.
import { Link } from "react-router-dom";

function Side({ name, block, side }) {
  const row = (p, i) => (
    <li key={i} className="llu-row"><span className="llu-shirt">{p.shirt ?? ""}</span>{p.player_id ? <Link to={`/player/${p.player_id}`}>{p.name}</Link> : <span>{p.name}</span>}{p.captain && <em className="llu-c" title="Captain">C</em>}</li>
  );
  return (
    <div className="llu-side" data-testid={`live-lineup-${side}`}>
      <h3 className="h3">{name}</h3>
      <ol className="llu-list">{(block.starters || []).map(row)}</ol>
      {(block.subs || []).length > 0 && <><p className="muted small llu-bench">Bench</p><ol className="llu-list llu-list--bench">{block.subs.map(row)}</ol></>}
    </div>
  );
}

export default function LiveLineups({ lineups, home, away }) {
  if (!lineups || (!lineups.home && !lineups.away)) return null;
  return (
    <div className="llu" data-testid="live-lineups">
      {lineups.home && <Side name={home} block={lineups.home} side="home" />}
      {lineups.away && <Side name={away} block={lineups.away} side="away" />}
    </div>
  );
}
