// SportAPI lineups (docs/23): starters and bench, linked to our player pages where the name was matched.
import { Link } from "react-router-dom";
import { PlayerAvatar } from "./Media";

function Side({ name, block, side }) {
  // Every named player wears his face, here as everywhere else. The lineup feed carries no picture
  // (sportapi.lineups_for returns name, shirt, captain, mins and player_id), so the shared avatar
  // falls back to his initials rather than this file inventing its own.
  const row = (p, i) => (
    <li key={i} className="llu-row"><span className="llu-shirt">{p.shirt ?? ""}</span><PlayerAvatar player={{ id: p.player_id ?? p.name, name: p.name }} size={20} />{p.player_id ? <Link to={`/player/${p.player_id}`}>{p.name}</Link> : <span>{p.name}</span>}{p.captain && <em className="llu-c" title="Captain">C</em>}</li>
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
