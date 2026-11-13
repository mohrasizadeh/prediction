// Screen 7, Team (docs/01 §5, docs/04 SquadGrid): header with crest, form, tactic chips. Tabs Squad grid, Team totals, Against, Fixtures.
import { useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { useApi } from "../lib/useApi";
import { Crest, LeagueMark, PlayerAvatar } from "../components/Media";
import { Empty, ErrorBox, Loading } from "../components/States";
import { Tabs } from "../components/Ui";
import { FormPills, MatchRow, STATS, Seg, Select, TEAM_STATS, TacticChip, num1, posLabel, shortDay, useStored, useTitle } from "../components/Football";
import { FollowButton } from "../components/Actions";
import { ChipsRow, ForecastList, QuickView } from "../components/ui";
import { SubjectHead } from "../components/ui/Subject";
import FirstGoal from "../components/FirstGoal";

const WINDOWS = [{ id: 5, label: "Last 5" }, { id: 10, label: "Last 10" }, { id: 20, label: "Last 20" }];
const LINES = [1, 2, 3, 4, 5].map((n) => ({ id: n, label: `${n}+` }));
const POS_ORDER = ["GK", "DEF", "MID", "FWD"];
const POS_PLURAL = { GK: "Goalkeepers", DEF: "Defenders", MID: "Midfielders", FWD: "Forwards" };

// A plan caps the window server-side (`capped`, `last`). The control used to keep "Last 10" lit
// while the rows under it were five games, so the screen contradicted itself. The control now
// shows the window actually drawn, and the note says why and where to get more.
function CapNote({ data, testid }) {
  if (!data?.capped) return null;
  return <p className="notice small team-cap" data-testid={testid}><span>Your plan shows the last {data.last} games. <Link to="/pricing">See plans</Link> for longer windows.</span></p>;
}
const shownWindow = (data, asked) => (data?.capped ? data.last : asked);

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
  // docs/24 §8 grid: "HIT" is the column people read first -- how often he reached the line, out of
  // the games he played in the columns shown. Minutes has no line, so it has no hit count either.
  const counted = stat !== "minutes";
  const colIds = new Set(cols.map((c) => c.match_iid));
  const hitOf = (r) => { const p = r.games.filter((g) => colIds.has(g.match_iid) && g.v != null); return { h: p.filter((g) => g.v >= line).length, n: p.length }; };
  return (
    <>
      <div className="filters">
        <Select label="Stat" value={stat} onChange={setStat} options={STATS} testid="grid-stat" />
        <Seg label="Window" value={shownWindow(q.data, last)} onChange={setLast} options={WINDOWS} testid="grid-window" />
        {counted && <Seg label="Line" value={line} onChange={(v) => setLine(Number(v))} options={LINES} testid="grid-line" />}
      </div>
      <CapNote data={q.data} testid="grid-capped" />
      <p className="muted small grid-hint">{counted && <>Filled cells reached {line}+; darker is well past it. A dashed cell means he did not play. </>}Tap a game's × to leave it out.{nHidden > 0 && <> <button type="button" className="linkish" onClick={() => setHidden([])} data-testid="grid-show-hidden">Show {nHidden} hidden</button></>}</p>
      {q.loading && !q.data ? <Loading /> : q.error ? <ErrorBox error={q.error} onRetry={q.reload} /> : !q.data.rows.length ? <Empty icon="grid">No player data for this club yet.</Empty> : (
        <div className="tbl-wrap"><table className="tbl grid" data-testid="squad-grid">
          <thead><tr><th scope="col" className="sticky">Player</th>{cols.map((c) => <th key={c.match_iid} scope="col" className="gcol" title={`${c.opp?.name || ""} ${shortDay(c.kickoff)}`}><Crest team={c.opp} size={20} /><small>{shortDay(c.kickoff)}</small><button type="button" className="gcol-hide" aria-label={`Hide the game against ${c.opp?.name || "this team"}`} onClick={() => setHidden([...hidden, c.match_iid])} data-testid={`grid-hide-${c.match_iid}`}>×</button></th>)}<th scope="col" className="num">Avg</th>{counted && <th scope="col" className="num">Hit</th>}</tr></thead>
          <tbody>{q.data.rows.map((r) => {
            const by = Object.fromEntries(r.games.map((g) => [g.match_iid, g]));
            return (
              <tr key={r.player_iid}>
                <th scope="row" className="sticky"><Link className="cell-person" to={`/player/${r.player?.id}`}><PlayerAvatar player={r.player} size={28} /><span>{r.player?.name}<small className="muted"> {r.player?.pos || ""}</small></span></Link></th>
                {cols.map((c) => { const g = by[c.match_iid]; const v = g?.v; return <td key={c.match_iid} className={"num gcell" + (!g || v == null ? " dnp" : counted && v >= line ? (v >= line * 2 ? " hit hit--2" : " hit") : "")}>{g && v != null ? num1(v) : <span className="sr-only">Did not play</span>}</td>; })}
                <td className="num"><b>{num1(avg(r))}</b></td>
                {counted && (() => { const { h, n } = hitOf(r); return <td className="num gcell-hit" data-testid={`grid-hit-${r.player_iid}`}>{n ? <><b>{h}</b>/{n}</> : "–"}</td>; })()}
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
      <div className="filters"><Select label="Stat" value={stat} onChange={setStat} options={TEAM_STATS} testid="totals-stat" /><Seg label="Window" value={shownWindow(q.data, last)} onChange={setLast} options={WINDOWS} testid="totals-window" /></div>
      <CapNote data={q.data} testid="totals-capped" />
      {q.loading && !q.data ? <Loading /> : q.error ? <ErrorBox error={q.error} onRetry={q.reload} /> : !q.data.rows.length ? <Empty icon="activity">No finished matches loaded yet.</Empty> : (
        // The key sat under the last row, so a reader met five pairs of unlabelled bars before learning
        // which was which; and each number was printed on top of its own fill, at under 3:1 on the
        // darker bars. Key first, numbers beside the bars on the plain track colour.
        <div className="card team-totals">
          <p className="totals-key small" aria-hidden="true"><span><i className="tk tk--for" />For</span><span><i className="tk tk--ag" />Against</span></p>
          <ul className="totals" data-testid="team-totals">{q.data.rows.map((r) => (
            <li key={r.match_iid}>
              <span className="team"><Crest team={r.opp} size={20} /><span className="totals-opp">{r.home ? "v" : "at"} {r.opp?.name || "Opponent"}</span><small className="muted">{shortDay(r.kickoff)}</small></span>
              <span className="tbar"><span className="tbar-track"><span className="tbar-for" style={{ width: `${((r.for || 0) / max) * 100}%` }} /></span><b><span className="sr-only">For </span>{num1(r.for)}</b></span>
              <span className="tbar tbar--against"><span className="tbar-track"><span className="tbar-ag" style={{ width: `${((r.against || 0) / max) * 100}%` }} /></span><b><span className="sr-only">Against </span>{num1(r.against)}</b></span>
            </li>
          ))}</ul>
        </div>
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

// The cards answer the mockup's question (docs/24 §8, team_squad_cards_dark.png): who in this squad
// does the thing, lately. Season totals alone could not say that -- a forward with 40 shots in
// September and none since read the same as one in form -- so each card carries the last five club
// games for the chosen stat, from the same squad-grid route the Grid view reads. Grouped by
// position, because a goalkeeper's zero shots beside a forward's six is noise, not information.
const CARD_STATS = [{ id: "shots", label: "Shots" }, { id: "sot", label: "On target" }, { id: "tackles", label: "Tackles" }, { id: "goals", label: "Goals" }];

function Spark({ games, max, label }) {
  const said = games.map((g) => (g.v == null ? "did not play" : num1(g.v))).join(", ");
  return (
    <span className="sq-spark" role="img" aria-label={`${label}, last ${games.length} games, oldest first: ${said}`}>
      <span className="sq-bars" aria-hidden="true">{games.map((g, i) => <i key={i} className={g.v == null ? "dnp" : g.v > 0 ? "on" : ""} style={{ "--h": g.v ? Math.max(0.12, g.v / max) : 0 }} />)}</span>
      <small aria-hidden="true">last {games.length}</small>
    </span>
  );
}

function SquadCards({ id }) {
  const [stat, setStat] = useState("shots");
  const q = useApi(`/teams/${id}/squad-season`);
  const g = useApi(`/teams/${id}/squad-grid`, { stat, last: 5 });
  // The club's last five games, oldest on the left like every other strip in the product, and the
  // same five columns for every card so a gap reads as "did not play", not as a shorter run.
  const runs = useMemo(() => {
    const rows = g.data?.rows || [];
    const m = new Map();
    rows.forEach((r) => r.games.forEach((x) => m.set(x.match_iid, x)));
    const cols = [...m.values()].sort((a, b) => (a.kickoff < b.kickoff ? 1 : -1)).slice(0, 5).reverse();
    const out = {};
    let max = 1;
    rows.forEach((r) => {
      const by = Object.fromEntries(r.games.map((x) => [x.match_iid, x.v]));
      out[r.player_iid] = cols.map((c) => ({ v: by[c.match_iid] ?? null }));
      out[r.player_iid].forEach((x) => { if (x.v > max) max = x.v; });
    });
    return { by: out, max, n: cols.length };
  }, [g.data]);
  if (q.loading && !q.data) return <Loading rows={4} />;
  if (q.error) return <ErrorBox error={q.error} onRetry={q.reload} />;
  const rows = q.data.players;
  if (!rows.length) return <Empty icon="users">No appearances recorded this season yet.</Empty>;
  const groups = POS_ORDER.map((p) => [p, rows.filter((r) => (r.pos || r.player.pos) === p)])
    .concat([["other", rows.filter((r) => !POS_ORDER.includes(r.pos || r.player.pos))]])
    .filter(([, list]) => list.length);
  const statLabel = CARD_STATS.find((s) => s.id === stat)?.label || "";
  return (
    <>
      <ChipsRow options={CARD_STATS} value={stat} onChange={setStat} label="Stat on the cards" testid="squad-card-stat" />
      <div className="sq-groups" data-testid="squad-cards">{groups.map(([pos, list]) => (
        <section key={pos} className="sq-group" aria-labelledby={`sq-h-${pos}`}>
          <h3 className="k-sec sq-pos" id={`sq-h-${pos}`}>{POS_PLURAL[pos] || "Others"}</h3>
          <ul className="sq-cards">{list.map((r) => {
            const run = runs.by[r.player.iid];
            return (
              <li key={r.player.id}><Link to={`/player/${r.player.id}`} className="sq-card card" data-testid={`squad-card-${r.player.id}`}>
                <PlayerAvatar player={r.player} size={48} />
                <span className="sq-who"><b>{r.player.name}</b><small className="muted">{posLabel(r.pos || r.player.pos)} · {r.starts} start{r.starts === 1 ? "" : "s"}</small></span>
                {run && runs.n > 0 ? <Spark games={run} max={runs.max} label={statLabel} /> : <span className="sq-spark sq-spark--none" aria-hidden="true" />}
                <dl className="sq-nums">{SEASON_KEYS.map(([k, l]) => <div key={k}><dt>{l}</dt><dd>{Math.round(r[k] || 0)}</dd></div>)}</dl>
              </Link></li>
            );
          })}</ul>
        </section>
      ))}</div>
    </>
  );
}

// docs/24 §8 Fixtures: "past results as chips (W/D/L and score)". The tab listed only what is next,
// so the five results the head summarises as letters had no score, no opponent and no way through
// to the match. `form` already carries all of it.
function Results({ form }) {
  if (!form?.length) return null;
  return (
    <ul className="mlist card team-results" data-testid="team-results">{form.map((g) => (
      <li key={g.match_iid}>
        <Link to={`/match/${g.match_id}`} className="team-res" data-testid={`team-result-${g.match_iid}`}>
          <span className={`fp fp--${g.result}`} aria-label={{ W: "Won", D: "Drew", L: "Lost" }[g.result] || g.result}>{g.result}</span>
          <span className="team-res-opp"><Crest team={g.opp} size={20} /><span>{g.home ? "v" : "at"} {g.opp?.name || "Opponent"}</span></span>
          <b className="team-res-score">{g.gf}–{g.ga}</b>
          <time className="muted small">{shortDay(g.kickoff)}</time>
        </Link>
      </li>
    ))}</ul>
  );
}

const TABS = [{ id: "squad", label: "Squad" }, { id: "totals", label: "Stats" }, { id: "fixtures", label: "Fixtures" }];

export default function Team() {
  const { id } = useParams();
  const q = useApi(`/teams/${id}`);
  const [tab, setTab] = useState("squad");
  const [squadView, setSquadView] = useState("cards");
  const tm = q.data?.team;
  // docs/75 cluster E: the per-game team shape -- shots, corners, cards, and what they concede --
  // is what people search for, and this page holds all of it beside the next fixture.
  useTitle(tm?.name ? `${tm.name} stats, shots and cards per game` : "Team", {
    image: tm?.image,
    description: tm?.name
      ? `${tm.name}: shots, corners and cards per game, what they concede, the squad, and our forecasts for their next fixture with the reasons shown.`
      : undefined,
  });
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
    <section className="team-page" data-testid="team-page">
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
          : cards.length ? <ForecastList rows={cards} teams={nextTeams} homeIid={d.next[0].home_iid} testid="team-fc" />
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
      {/* docs/24 §8 names this tab Stats; "Numbers" was the only place in the product it was called that. */}
      <Tabs value={tab} onChange={setTab} testid="team-tabs" tabs={TABS} />
      <div role="tabpanel" aria-label={TABS.find((t) => t.id === tab)?.label} className="team-panel" data-testid={`team-panel-${tab}`}>
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
      {tab === "fixtures" && (
        <div className="v2-stack">
          <section><h2 className="k-sec">Next</h2>
            {d.next.length ? <ul className="mlist card">{d.next.map((m) => <MatchRow key={m.id} m={m} />)}</ul> : <Empty icon="calendar">No upcoming fixtures loaded.</Empty>}</section>
          {d.form?.length > 0 && <section><h2 className="k-sec">Recent results</h2><Results form={d.form} /></section>}
        </div>
      )}
      </div>
    </section>
  );
}
