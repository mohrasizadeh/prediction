// Screen 7, Team (docs/01 §5, docs/04 SquadGrid): header with crest, form, tactic chips. Tabs Squad grid, Team totals, Against, Fixtures.
import { useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { useApi } from "../lib/useApi";
import { Crest, LeagueMark, PlayerAvatar } from "../components/Media";
import { Empty, ErrorBox, Loading } from "../components/States";
import { Tabs } from "../components/Ui";
import { FormPills, MatchRow, STATS, Seg, Select, TEAM_STATS, TacticChip, num1, posLabel, shortDay, useStored, useTitle } from "../components/Football";
import { FollowButton } from "../components/Actions";
import { ForecastCard, QuickView } from "../components/ui";
import { SubjectHead } from "../components/ui/Subject";
import FirstGoal from "../components/FirstGoal";

const WINDOWS = [{ id: 5, label: "Last 5" }, { id: 10, label: "Last 10" }, { id: 20, label: "Last 20" }];
const LINES = [1, 2, 3, 4, 5].map((n) => ({ id: n, label: `${n}+` }));

function Grid({ id }) {
  const [stat, setStat] = useState("shots");
  const [last, setLast] = useState(10);
  const [line, setLine] = useState(1);
  const q = useApi(`/teams/${id}/squad-grid`, { stat, last });
  const [hidden, setHidden] = useStored(`hide:${id}`, []);
  const all = useMemo(() => {
    const m = new Map();
    (q.data?.rows || []).forEach((r) => r.games.forEach((g) => m.set(g.match_iid, g)));
    return [...m.values()].sort((a, b) => (a.kickoff < b.kickoff ? 1 : -1)).slice(0, last);
  }, [q.data, last]);
  const cols = all.filter((c) => !hidden.includes(c.match_iid));
  const nHidden = all.length - cols.length;
  const avg = (r) => { const v = r.games.filter((g) => !hidden.includes(g.match_iid) && g.v != null).map((g) => g.v); return v.length ? v.reduce((a, b) => a + b, 0) / v.length : null; };
  return (
    <>
      <div className="filters">
        <Select label="Stat" value={stat} onChange={setStat} options={STATS} testid="grid-stat" />
        <Seg label="Window" value={last} onChange={setLast} options={WINDOWS} testid="grid-window" />
        <Seg label="Line" value={line} onChange={(v) => setLine(Number(v))} options={LINES} testid="grid-line" />
      </div>
      {q.data?.capped && <p className="notice small" data-testid="grid-capped">Showing the last {q.data.last} games. Longer windows come with a bigger plan.</p>}
      <p className="muted small grid-hint">Tap a game's × to leave it out of the averages.{nHidden > 0 && <> <button type="button" className="linkish" onClick={() => setHidden([])} data-testid="grid-show-hidden">Show {nHidden} hidden</button></>}</p>
      {q.loading && !q.data ? <Loading /> : q.error ? <ErrorBox error={q.error} onRetry={q.reload} /> : !q.data.rows.length ? <Empty icon="grid">No player data for this club yet.</Empty> : (
        <div className="tbl-wrap"><table className="tbl grid" data-testid="squad-grid">
          <thead><tr><th scope="col" className="sticky">Player</th>{cols.map((c) => <th key={c.match_iid} scope="col" className="gcol" title={`${c.opp?.name || ""} ${shortDay(c.kickoff)}`}><Crest team={c.opp} size={20} /><small>{shortDay(c.kickoff)}</small><button type="button" className="gcol-hide" aria-label={`Hide the game against ${c.opp?.name || "this team"}`} onClick={() => setHidden([...hidden, c.match_iid])} data-testid={`grid-hide-${c.match_iid}`}>×</button></th>)}<th scope="col">Avg</th></tr></thead>
          <tbody>{q.data.rows.map((r) => {
            const by = Object.fromEntries(r.games.map((g) => [g.match_iid, g]));
            return (
              <tr key={r.player_iid}>
                <th scope="row" className="sticky"><Link className="cell-person" to={`/player/${r.player?.id}`}><PlayerAvatar player={r.player} size={28} /><span>{r.player?.name}<small className="muted"> {r.player?.pos || ""}</small></span></Link></th>
                {cols.map((c) => { const g = by[c.match_iid]; const v = g?.v; return <td key={c.match_iid} className={"num gcell" + (v != null && v >= line && stat !== "minutes" ? " hit" : "")}>{g ? num1(v) : <span className="muted">–</span>}</td>; })}
                <td className="num"><b>{num1(avg(r))}</b></td>
              </tr>
            );
          })}</tbody>
        </table></div>
      )}
    </>
  );
}

function Totals({ id }) {
  const [stat, setStat] = useState("shots");
  const [last, setLast] = useState(10);
  const q = useApi(`/teams/${id}/totals`, { stat, last });
  const max = Math.max(1, ...(q.data?.rows || []).flatMap((r) => [r.for || 0, r.against || 0]));
  return (
    <>
      <div className="filters"><Select label="Stat" value={stat} onChange={setStat} options={TEAM_STATS} testid="totals-stat" /><Seg label="Window" value={last} onChange={setLast} options={WINDOWS} testid="totals-window" /></div>
      {q.data?.capped && <p className="notice small" data-testid="totals-capped">Showing the last {q.data.last} games. Longer windows come with a bigger plan.</p>}
      {q.loading && !q.data ? <Loading /> : q.error ? <ErrorBox error={q.error} onRetry={q.reload} /> : !q.data.rows.length ? <Empty icon="activity">No finished matches loaded yet.</Empty> : (
        <ul className="totals card" data-testid="team-totals">{q.data.rows.map((r) => (
          <li key={r.match_iid}>
            <span className="team"><Crest team={r.opp} size={20} /> {r.home ? "v" : "at"} {r.opp?.name || "Opponent"}<small className="muted"> {shortDay(r.kickoff)}</small></span>
            <span className="tbar"><span className="tbar-for" style={{ width: `${((r.for || 0) / max) * 100}%` }} /><b>{num1(r.for)}</b></span>
            <span className="tbar tbar--against"><span className="tbar-ag" style={{ width: `${((r.against || 0) / max) * 100}%` }} /><b>{num1(r.against)}</b></span>
          </li>
        ))}<li className="totals-key muted small"><span /><span>For</span><span>Against</span></li></ul>
      )}
    </>
  );
}

function Against({ id }) {
  const [stat, setStat] = useState("shots");
  const q = useApi(`/teams/${id}/against`, { stat, last: 10 });
  const rows = Object.entries(q.data?.by_position || {}).sort((a, b) => ["GK", "DEF", "MID", "FWD"].indexOf(a[0]) - ["GK", "DEF", "MID", "FWD"].indexOf(b[0]));
  return (
    <>
      <div className="filters"><Select label="Stat" value={stat} onChange={setStat} options={STATS.filter((s) => s.id !== "minutes")} testid="against-stat" /></div>
      {q.loading && !q.data ? <Loading /> : q.error ? <ErrorBox error={q.error} onRetry={q.reload} /> : !rows.length ? <Empty icon="shield">No opponent data yet.</Empty> : (
        <>
          <p className="muted small">What opponents did against this club, by position, over its last {q.data.games} games.</p>
          <div className="tiles4" data-testid="against-tiles">{rows.map(([pos, v]) => <div key={pos} className="stile"><span className="muted small">{posLabel(pos)}</span><b>{num1(v.per_game)}</b><small className="muted">per game · {num1(v.per_player_game)} per player</small></div>)}</div>
        </>
      )}
    </>
  );
}

const SEASON_KEYS = [["apps", "Apps"], ["minutes", "Min"], ["goals", "Goals"], ["shots", "Shots"], ["tackles", "Tackles"], ["yellow_cards", "Cards"]];

function SquadCards({ id }) {
  const q = useApi(`/teams/${id}/squad-season`);
  if (q.loading && !q.data) return <Loading rows={4} />;
  if (q.error) return <ErrorBox error={q.error} onRetry={q.reload} />;
  const rows = q.data.players;
  if (!rows.length) return <Empty icon="users">No appearances recorded this season yet.</Empty>;
  return (
    <ul className="sq-cards" data-testid="squad-cards">{rows.map((r) => (
      <li key={r.player.id}><Link to={`/player/${r.player.id}`} className="sq-card card" data-testid={`squad-card-${r.player.id}`}>
        <PlayerAvatar player={r.player} size={56} />
        <span className="sq-who"><b>{r.player.name}</b><small className="muted">{posLabel(r.pos || r.player.pos)} · {r.starts} start{r.starts === 1 ? "" : "s"}</small></span>
        <dl className="sq-nums">{SEASON_KEYS.map(([k, l]) => <div key={k}><dt>{l}</dt><dd>{Math.round(r[k] || 0)}</dd></div>)}</dl>
      </Link></li>
    ))}</ul>
  );
}

export default function Team() {
  const { id } = useParams();
  const q = useApi(`/teams/${id}`);
  const [tab, setTab] = useState("squad");
  const [squadView, setSquadView] = useState("cards");
  useTitle(q.data?.team?.name || "Team");
  if (q.loading && !q.data) return <Loading rows={5} />;
  if (q.error) return <ErrorBox error={q.error} onRetry={q.reload} />;
  const d = q.data;
  const cards = d.cards || [];
  const nextTeams = d.next?.[0] ? { [d.next[0].home_iid]: d.next[0].home, [d.next[0].away_iid]: d.next[0].away } : {};
  // SubjectHead speaks the forecast shape, so the club is handed to it as one: no player, the club
  // as the subject, and the next fixture for the Home/Away line.
  const n0 = d.next?.[0];
  const headF = { scope: "team", team_iid: d.team.iid, home_iid: n0?.home_iid, match_id: n0?.id, kickoff: n0?.kickoff, stat: "" };
  const headFx = n0
    ? { team: d.team, opp: n0.home_iid === d.team.iid ? n0.away : n0.home, homeFirst: n0.home_iid === d.team.iid,
        text: `${n0.home?.name || ""} v ${n0.away?.name || ""}` }
    : { team: d.team, text: "" };
  return (
    <section data-testid="team-page">
      {/* The same head the player page and the sheet open with. The club head was .phead -- a 64px
          crest centred against a three-row column, 141px against the player's 261px -- so the two
          entity pages did not look like one product. */}
      <SubjectHead f={headF} fx={headFx} size="page" testid="team-head"
                   extraMeta={<>
                     {d.league && <Link to={`/league/${d.league.id}`} className="v2-club"><LeagueMark league={d.league} size={18} /> {d.league.name}</Link>}
                     <FormPills form={d.form} />
                     {(d.style?.tactics || []).map((t) => <TacticChip key={t} t={t} />)}
                   </>}
                   action={<><FollowButton kind="team" refId={d.team.id} name={d.team.name} />
                     <Link to={`/compare?a=${d.team.id}`} className="btn btn--secondary btn--sm" data-testid="team-compare">Compare with…</Link></>} />
      {/* CONSOLIDATION: six tabs became three. "Squad" and "Squad grid" were two renderings of one
          thing -- a view toggle wearing two tabs -- so they are one tab with a toggle. "Team totals",
          "Against" and "First goal" are all the same question, what this club's numbers look like,
          so they are one tab read top to bottom: per match, then by the position it concedes to,
          then who tends to score first. Six tabs scrolled sideways on a phone; three do not. */}
      {/* The club page answered every question except the one a reader arrives with. Following a
          club's card landed on a squad list and fourteen season totals, with no forecast anywhere
          on the page -- while the player page has led with its next match since it was written.
          Same block, same component, same position: the answer first, the season behind it. */}
      <section className="card" data-testid="team-next">
        <header className="v2-sec-head v2-sec-head--card"><h2 className="k-sec v2-sec">What we expect next match</h2></header>
        {!d.next.length ? <p className="muted">No upcoming match loaded.</p>
          : cards.length ? <div className="fgrid">{cards.map((f) => <ForecastCard key={f.id} f={f} teams={nextTeams} homeIid={d.next[0].home_iid} showTime={false} testid={`team-fc-${f.id}`} />)}</div>
          : <p className="muted small">No forecasts for this club yet.</p>}
      </section>
      {/* The interrogation the player page has had since it was written, and the club did not:
          pick a stat, a line, a window and a venue and read the run game by game. QuickView took a
          `playerId` only, so this half of the product had no evidence block at all -- and "what
          about 4+, and only away?" is exactly the question a club line raises. */}
      <section className="card" data-testid="team-quick-view-card">
        <header className="v2-sec-head v2-sec-head--card"><h2 className="h3 v2-sec">The last ten, and any other line</h2></header>
        <QuickView teamId={id} forecasts={d.forecasts || []} testid="team-quick-view" />
      </section>
      <Tabs value={tab} onChange={setTab} testid="team-tabs" tabs={[{ id: "squad", label: "Squad" }, { id: "totals", label: "Numbers" }, { id: "fixtures", label: "Fixtures" }]} />
      {tab === "squad" && (
        <>
          <div className="v2-bar">
            <Seg label="View" value={squadView} onChange={setSquadView} testid="team-squad-view"
                       options={[{ id: "cards", label: "Cards" }, { id: "grid", label: "Grid" }]} />
          </div>
          {squadView === "cards" ? <SquadCards id={id} /> : <Grid id={id} />}
        </>
      )}
      {tab === "totals" && (
        <div className="v2-stack">
          <section><h2 className="k-sec">Match by match</h2><Totals id={id} /></section>
          <section><h2 className="k-sec">What opponents manage, by position</h2><Against id={id} /></section>
          <section><h2 className="k-sec">Who scores first</h2><FirstGoal team={d.team} /></section>
        </div>
      )}
      {tab === "fixtures" && (d.next.length ? <ul className="mlist card">{d.next.map((m) => <MatchRow key={m.id} m={m} />)}</ul> : <Empty icon="calendar">No upcoming fixtures loaded.</Empty>)}
    </section>
  );
}
