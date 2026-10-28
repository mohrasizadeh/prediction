// Screen 8, Player (docs/01 §5, docs/04 Chart): hero, next-fixture forecasts, Quick view chart, history table.
import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { useApi } from "../lib/useApi";
import { Crest, PlayerAvatar } from "../components/Media";
import { Empty, ErrorBox, Loading } from "../components/States";
import { ColumnPicker, ForecastCard, STATS, Seg, Select, kickoff, num1, posLabel, shortDay, useStored, useTitle } from "../components/Football";
import { FollowButton } from "../components/Actions";
import { useAuth } from "../lib/auth";
import { del, put } from "../lib/api";
import { useToast } from "../components/Ui";
import { HitStrip } from "../components/ui";

function Note({ id }) {
  const { user } = useAuth();
  const toast = useToast();
  const q = useApi(user ? `/me/notes/${id}` : null);
  const [text, setText] = useState(null);
  if (!user) return null;
  const val = text ?? q.data?.text ?? "";
  const save = async () => {
    try {
      if (val.trim()) { await put(`/me/notes/${id}`, { text: val }); toast("Note saved"); }
      else { await del(`/me/notes/${id}`); toast("Note removed"); }
    } catch (x) { toast(x.message || "Could not save the note", "err"); }
  };
  return (
    <section className="card" data-testid="player-note">
      <h2 className="h3">Your note</h2>
      {q.loading && !q.data ? <Loading rows={1} /> : q.error ? <ErrorBox error={q.error} onRetry={q.reload} /> : (
        <><textarea className="note-in" rows={3} maxLength={1000} value={val} onChange={(e) => setText(e.target.value)} placeholder="Only you can see this." aria-label="Your note" data-testid="note-input" />
          <button type="button" className="btn btn--secondary btn--sm" onClick={save} data-testid="note-save">Save note</button></>
      )}
    </section>
  );
}

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
      <div className="chart-x" aria-hidden="true">{rows.map((g) => <span key={g.match_iid}><Crest team={g.opp} size={16} /><small>{shortDay(g.kickoff)}</small></span>)}</div>
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
  const [cols, setCols] = useStored("cols:history", ["minutes", "shots", "sot", "tackles", "goals"]);
  const shown = STATS.filter((s) => cols.includes(s.id));
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
          {table && <ColumnPicker options={STATS} value={cols} onChange={setCols} testid="history-cols" />}
          {table && (
            <div className="tbl-wrap"><table className="tbl" data-testid="history-table">
              <thead><tr><th scope="col">Match</th>{shown.map((s) => <th key={s.id} scope="col">{s.label}</th>)}<th scope="col">Cards</th></tr></thead>
              <tbody>{q.data.games.map((g) => (
                <tr key={g.match_iid}><td><span className="team"><Crest team={g.opp} size={20} /> {g.home ? "v" : "at"} {g.opp?.name}<small className="muted"> {shortDay(g.kickoff)}</small></span>
                  {(g.sub_on != null || g.sub_off != null) && <small className="sub-note" data-testid="history-sub">{g.sub_on != null ? `On ${g.sub_on}'${g.replaced ? ` for ${g.replaced.name}` : ""}` : ""}{g.sub_on != null && g.sub_off != null ? " · " : ""}{g.sub_off != null ? `Off ${g.sub_off}'${g.replaced_by ? `, ${g.replaced_by.name} on` : ""}` : ""}</small>}</td>
                  {shown.map((s) => <td key={s.id} className="num">{num1(g[s.id])}</td>)}<td className="num">{Array.from({ length: g.red_cards || 0 }, (_, i) => <span key={`r${i}`} className="card-dot card-dot--r" title="Red card" />)}{Array.from({ length: g.yellow_cards || 0 }, (_, i) => <span key={`y${i}`} className="card-dot card-dot--y" title="Yellow card" />)}{!g.red_cards && !g.yellow_cards ? "–" : null}</td></tr>
              ))}</tbody>
            </table></div>
          )}
        </>
      )}
    </section>
  );
}

function FormStrips({ id }) {
  const q = useApi(`/players/${id}/history`, { last: 10 });
  const games = q.data?.games || [];
  if (!games.length) return null;
  const lines = [["shots", 1, "1+ shots"], ["shots", 2, "2+ shots"], ["sot", 1, "1+ on target"], ["tackles", 2, "2+ tackles"]];
  return (
    <section className="card pl-form" data-testid="player-form">
      <h2 className="k-sec">Last {games.length} games</h2>
      <ul>{lines.map(([s, n, label]) => { const hits = games.filter((g) => g[s] != null).map((g) => g[s] >= n).reverse(); return hits.length ? <li key={label}><span>{label}</span><HitStrip hits={hits} label={label} testid={`player-strip-${s}-${n}`} /></li> : null; })}</ul>
    </section>
  );
}

const RANK_LABEL = { shots: "shots", sot: "shots on target", tackles: "tackles", goals: "goals", assists: "assists" };
const nth = (n) => `${n}${["th", "st", "nd", "rd"][(n % 100 > 10 && n % 100 < 14) || n % 10 > 3 ? 0 : n % 10]}`;

function Ranks({ id }) {
  const q = useApi(`/players/${id}/ranks`);
  const r = q.data?.ranks || [];
  if (!r.length) return null;
  return (
    <section className="card pl-ranks" data-testid="player-ranks">
      <h2 className="k-sec">{q.data.league} rank this season · per 90 minutes</h2>
      <ul>{r.map((x) => <li key={x.stat} data-testid={`player-rank-${x.stat}`}><b>{nth(x.rank)}</b><span> of {x.of}</span><small className="k-faint">{RANK_LABEL[x.stat]} · {x.per90}</small></li>)}</ul>
      <p className="k-faint k-small">Among players with at least {q.data.min_minutes} minutes.</p>
    </section>
  );
}

export default function Player() {
  const { id } = useParams();
  const q = useApi(`/players/${id}`);
  useTitle(q.data?.player?.name || "Player");
  if (q.loading && !q.data) return <Loading rows={5} />;
  if (q.error) return <ErrorBox error={q.error} onRetry={q.reload} />;
  const { player: p, team, next_match: nx } = q.data;
  const forecasts = q.data.cards || q.data.forecasts;
  const teams = nx ? { [nx.home_iid]: nx.home, [nx.away_iid]: nx.away } : {};
  return (
    <section data-testid="player-page">
      <header className="phead">
        <PlayerAvatar player={p} size={96} decorative={false} />
        <div className="phead-main">
          <h1>{p.name}</h1>
          <p className="muted">{posLabel(p.pos)}</p>
          {team && <Link to={`/team/${team.id}`} className="inline"><Crest team={team} size={20} /> {team.name}</Link>}
          <div><FollowButton kind="player" refId={p.id} name={p.name} /></div>
        </div>
      </header>
      <section className="card" data-testid="player-next">
        <h2 className="h3">Next match</h2>
        {nx ? <Link to={`/match/${nx.id}`} className="next-link"><span className="team"><Crest team={nx.home} size={20} />{nx.home?.name}</span><span className="muted">v</span><span className="team"><Crest team={nx.away} size={20} />{nx.away?.name}</span><time className="muted small">{kickoff(nx.kickoff)}</time></Link>
          : <p className="muted">No upcoming match loaded.</p>}
        {nx && (forecasts.length ? <div className="fgrid">{forecasts.map((f) => <ForecastCard key={f.id} f={{ ...f, player: p }} teams={teams} homeIid={nx.home_iid} />)}</div>
          : <p className="muted small">No forecasts for this player yet.</p>)}
      </section>
      <Ranks id={id} />
      <FormStrips id={id} />
      <History id={id} />
      <Note id={id} />
    </section>
  );
}
