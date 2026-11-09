// Team news on the match page (docs/22): who is out or doubtful, and short context sentences per club.
import { Link } from "react-router-dom";
import { utc } from "../lib/time";
import { Crest, PlayerAvatar } from "./Media";

function Club({ team, rows, why, side }) {
  return (
    <div data-testid={`team-news-${side}`}>
      {/* The club is named here, so it wears its crest, at full size -- and each player named below
          wears the round face he wears in every other list. The availability feed carries no picture
          (availability.public_list returns id and name), so the shared avatar falls back to initials. */}
      <h3 className="h3"><Crest team={team} size={22} />{team.name}</h3>
      {rows.length ? (
        <ul className="tnews-list">{rows.map((r) => (
          <li key={r.player_iid} data-testid={`team-news-player-${r.player?.id || r.player_iid}`}>
            <span className={`tnews-tag tnews-tag--${r.status}`}>{r.status === "out" ? "Out" : "Doubtful"}</span>
            <PlayerAvatar player={r.player?.id ? r.player : { id: r.player_iid, name: r.player?.name || "Player" }} size={22} />
            {r.player?.id ? <Link to={`/player/${r.player.id}`}>{r.player.name}</Link> : <span>{r.player?.name || "Player"}</span>}
            {r.reason && <span className="muted small">{r.reason}</span>}
            {r.until && <span className="muted small">until {utc(r.until).toLocaleDateString(undefined, { day: "numeric", month: "short" })}</span>}
          </li>
        ))}</ul>
      ) : <p className="muted small">No absences known.</p>}
      {why.length > 0 && <ul className="tnews-why">{why.map((w) => <li key={w}>{w}</li>)}</ul>}
    </div>
  );
}

export default function TeamNews({ d }) {
  const av = d.availability || [];
  const ctx = d.context || {};
  const m = d.match;
  const whyOf = (iid) => ctx[iid]?.why || [];
  if (!av.length && !whyOf(m.home_iid).length && !whyOf(m.away_iid).length) return null;
  return (
    <section className="card tnews" aria-label="Team news" data-testid="team-news">
      <Club team={d.home} side="home" rows={av.filter((r) => r.team_iid === m.home_iid)} why={whyOf(m.home_iid)} />
      <Club team={d.away} side="away" rows={av.filter((r) => r.team_iid === m.away_iid)} why={whyOf(m.away_iid)} />
    </section>
  );
}
