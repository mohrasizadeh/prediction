// Referee leaderboard across every enabled league: cards and penalties per game, sortable.
import { useState } from "react";
import { Link } from "react-router-dom";
import { useApi } from "../lib/useApi";
import { Empty, ErrorBox, Loading } from "../components/States";
import { Seg, useTitle } from "../components/Football";
import { refPath } from "./Referee";

const COLS = [{ id: "yellow_pg", label: "Yellows" }, { id: "red_pg", label: "Reds" }, { id: "pens_pg", label: "Penalties" }, { id: "matches", label: "Games" }];
const f2 = (v) => (v == null ? "–" : v.toFixed(2));

export default function Referees() {
  useTitle("Referees");
  const [min, setMin] = useState("5");
  const [sort, setSort] = useState("yellow_pg");
  const q = useApi("/referees", { min_matches: min });
  const rows = [...(q.data || [])].sort((a, b) => b[sort] - a[sort]);
  const top = rows[0]?.[sort] || 1;
  return (
    <section data-testid="referees-page">
      <h1>Referees</h1>
      <p className="muted lead">Who shows the most cards and gives the most penalties, across all our leagues. Per game, from matches with card data.</p>
      <div className="filters">
        <Seg label="Sort by" value={sort} onChange={setSort} options={COLS} testid="referees-sort" />
        <Seg label="At least" value={min} onChange={setMin} options={[{ id: "1", label: "1 game" }, { id: "3", label: "3 games" }, { id: "5", label: "5 games" }]} testid="referees-min" />
      </div>
      {q.loading && !q.data ? <Loading rows={5} /> : q.error ? <ErrorBox error={q.error} onRetry={q.reload} /> : !rows.length ? <Empty icon="flag" testid="referees-lb-empty">No referees with that many games yet.</Empty> : (
        <div className="tbl-wrap"><table className="tbl" data-testid="referees-table">
          <thead><tr><th scope="col">#</th><th scope="col">Referee</th>{COLS.map((c) => <th key={c.id} scope="col" aria-sort={sort === c.id ? "descending" : undefined}>{c.label}{c.id !== "matches" ? " a game" : ""}</th>)}<th scope="col">Home wins</th></tr></thead>
          <tbody>{rows.map((r, i) => (
            <tr key={r.name} data-testid="referees-row">
              <td className="num">{i + 1}</td>
              <td><Link to={refPath(r.name)}><b>{r.name}</b></Link><small className="muted sub-note">{r.leagues.map((l) => l.name).join(", ")}</small></td>
              {COLS.map((c) => <td key={c.id} className="num">{c.id === "matches" ? r.matches : f2(r[c.id])}{sort === c.id && c.id !== "matches" && <span className="book-bar ref-bar"><i style={{ width: `${Math.round((r[c.id] / top) * 100)}%` }} /></span>}</td>)}
              <td className="num">{Math.round(r.home_win_pct * 100)}%</td>
            </tr>
          ))}</tbody>
        </table></div>
      )}
    </section>
  );
}
