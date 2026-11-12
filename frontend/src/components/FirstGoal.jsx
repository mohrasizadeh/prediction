// First goal record for one team: who scored first, what happened next, and the players who most often open the scoring.
import { Link } from "react-router-dom";
import { useApi } from "../lib/useApi";
import { EmptyState, ErrorState, Skeleton } from "./ui";
import { Crest, PlayerAvatar } from "./Media";
import { pct } from "../lib/copy";

const pc = (a, b) => pct(b ? a / b : null);
const wdl = (r) => `${r.w}W ${r.d}D ${r.l}L`;

export default function FirstGoal({ team, compact, testid = "first-goal" }) {
  const q = useApi(team?.id ? `/teams/${team.id}/first-goal` : null);
  if (q.loading && !q.data) return <Skeleton shape="row" count={2} testid={`${testid}-loading`} />;
  if (q.error) return <ErrorState message="We could not load the first-goal record." onRetry={q.reload} testid={`${testid}-error`} />;
  const d = q.data;
  // Side by side on the match page, two full empty states stacked a screen of nothing; one quiet line says it.
  if (!d?.played && compact) return <p className="fg-empty" data-testid={`${testid}-empty`}><Crest team={team} size={20} />No first-goal records for {team?.name} yet this season.</p>;
  if (!d?.played) return <EmptyState icon="activity" title="No first-goal records yet" testid={`${testid}-empty`}>Nothing for {team?.name} so far this season.</EmptyState>;
  return (
    <section className="fg card" data-testid={testid}>
      <header className="fg-head"><Crest team={team} size={28} /><h3>{team.name}</h3><small className="muted">last {d.played} games</small></header>
      <div className="fg-split" role="img" aria-label={`Scored first ${d.scored_first}, conceded first ${d.conceded_first}, no goals ${d.goalless}`}>
        <span className="fg-us" style={{ flexGrow: d.scored_first || 0.001 }} />
        <span className="fg-none" style={{ flexGrow: d.goalless || 0.001 }} />
        <span className="fg-them" style={{ flexGrow: d.conceded_first || 0.001 }} />
      </div>
      <dl className="fg-stats">
        <div><dt>Scored first</dt><dd data-testid={`${testid}-scored`}>{d.scored_first} <small>({pc(d.scored_first, d.played)})</small></dd></div>
        <div><dt>Conceded first</dt><dd data-testid={`${testid}-conceded`}>{d.conceded_first} <small>({pc(d.conceded_first, d.played)})</small></dd></div>
        <div><dt>After scoring first</dt><dd>{wdl(d.after_scoring)}</dd></div>
        <div><dt>After conceding first</dt><dd>{wdl(d.after_conceding)}</dd></div>
      </dl>
      {d.scorers.length > 0 && (
        <div className="fg-scorers">
          <h4>Most often scores first</h4>
          <ol data-testid={`${testid}-scorers`}>{d.scorers.map((s) => (
            <li key={s.player.id}><PlayerAvatar player={s.player} size={28} /><Link to={`/player/${s.player.id}`}>{s.player.name}</Link><b>{s.n}</b></li>
          ))}</ol>
        </div>
      )}
      {!compact && (
        <ul className="fg-games" data-testid={`${testid}-games`}>{d.games.map((g) => (
          <li key={g.match_id}><Link to={`/match/${g.match_id}`}>
            <span className={`fg-dot fg-dot--${g.who}`} aria-hidden="true" />
            <span className="fg-opp"><Crest team={g.opp} size={20} />{g.home ? "v" : "at"} {g.opp?.name}</span>
            <span className="muted small">{g.who === "none" ? "No goals" : g.who === "us" ? `${g.scorer?.name || "Scored first"}${g.minute != null ? ` ${g.minute}'` : ""}` : `Conceded first${g.minute != null ? ` ${g.minute}'` : ""}`}</span>
            <b className={`fg-res fg-res--${g.result}`}>{g.score}</b>
          </Link></li>
        ))}</ul>
      )}
    </section>
  );
}
