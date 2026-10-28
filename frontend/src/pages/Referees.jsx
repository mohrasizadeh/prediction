// Referees (docs/25 §5): per league, cards per game normalised for the teams involved, and the referee's factor
// against the teams' usual. Reads GET /api/leagues/{id}/referees.
import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { useApi } from "../lib/useApi";
import { favFirst, useFavLeagues } from "../lib/prefs";
import { useTitle } from "../components/Football";
import { ChipsRow, EmptyState, ErrorState, Skeleton } from "../components/ui";
import { refPath } from "./Referee";

const factorText = (f) => { const p = Math.round((f - 1) * 100); return `${p > 0 ? "+" : p < 0 ? "−" : "±"}${Math.abs(p)}%`; };

function Table({ league }) {
  const q = useApi(`/leagues/${league}/referees`);
  const rows = (q.data || []).filter((r) => r.cards_per_game_normalised != null).sort((a, b) => b.matches - a.matches);
  if (q.loading && !q.data) return <Skeleton shape="row" count={6} testid="referees-loading" />;
  if (q.error) return <ErrorState message="We could not load the referees." onRetry={q.reload} testid="referees-error" />;
  if (!rows.length) return <EmptyState icon="flag" title="No referee numbers yet" testid="referees-lb-empty">Referee numbers appear once matches with a named referee and cards are in.</EmptyState>;
  return (
    <div className="tbl-wrap"><table className="tbl" data-testid="referees-table">
      <thead><tr><th scope="col">Referee</th><th scope="col" aria-sort="descending">Matches</th><th scope="col">Cards per game</th><th scope="col">vs teams' usual</th></tr></thead>
      <tbody>{rows.map((r) => (
        <tr key={r.referee} data-testid="referees-row">
          <td><Link to={refPath(r.referee)} data-testid={`referee-link-${r.referee}`}><b>{r.referee}</b></Link></td>
          <td className="num">{r.matches}</td>
          <td className="num"><b data-testid="referee-norm">{r.cards_per_game_normalised.toFixed(1)}</b><small className="muted sub-note" data-testid="referee-plain">{r.cards_per_game != null ? `${r.cards_per_game.toFixed(1)} plain` : ""}</small></td>
          <td className={`num ${r.factor > 1.03 ? "ref-up" : r.factor < 0.97 ? "ref-down" : ""}`} data-testid="referee-factor">{factorText(r.factor)}</td>
        </tr>
      ))}</tbody>
    </table></div>
  );
}

export default function Referees() {
  useTitle("Referees");
  const lq = useApi("/leagues");
  const fav = useFavLeagues();
  const leagues = useMemo(() => favFirst((lq.data?.countries || []).flatMap((c) => c.leagues), fav, (l) => l.id), [lq.data, fav]);
  const [pick, setPick] = useState("");
  const league = pick || leagues[0]?.id;
  return (
    <section data-testid="referees-page">
      <h1>Referees</h1>
      <p className="muted lead">Cards per game, adjusted for the teams each referee had. "vs teams' usual" compares the cards in their matches with what those teams usually pick up.</p>
      {lq.loading && !lq.data ? <Skeleton shape="row" count={2} testid="referees-leagues-loading" /> : lq.error ? <ErrorState message="We could not load the leagues." onRetry={lq.reload} testid="referees-leagues-error" /> : (
        <>
          <ChipsRow label="League" value={league} onChange={setPick} testid="referees-league" options={leagues.map((l) => ({ id: l.id, label: l.name }))} />
          {league && <Table key={league} league={league} />}
        </>
      )}
    </section>
  );
}
