// Screen 8, Player (docs/01 §5, docs/04 Chart): hero, next-fixture forecasts, Quick view chart, history table.
import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { useApi } from "../lib/useApi";
import { Crest, PlayerAvatar } from "../components/Media";
import { ErrorBox, Loading } from "../components/States";
import { ColumnPicker, ForecastCard, STATS, kickoff, num1, posLabel, shortDay, useStored, useTitle } from "../components/Football";
import { FollowButton } from "../components/Actions";
import { useAuth } from "../lib/auth";
import { del, put } from "../lib/api";
import { useToast } from "../components/Ui";
import { QuickView } from "../components/ui";

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

function History({ id, forecasts }) {
  const [table, setTable] = useState(false);
  const [cols, setCols] = useStored("cols:history", ["minutes", "shots", "sot", "tackles", "goals"]);
  const shown = STATS.filter((s) => cols.includes(s.id));
  // The controls and the strip live in components/ui/QuickView.jsx, shared with the forecast sheet (docs/48).
  return (
    <section className="card" data-testid="quick-view-card">
      <h2 className="h3">Quick view</h2>
      <QuickView playerId={id} forecasts={forecasts} testid="quick-view">{(games) => (
        <>
          <button type="button" className="linkish" onClick={() => setTable(!table)} data-testid="qv-table-toggle">{table ? "Hide table" : "Show table"}</button>
          {table && <ColumnPicker options={STATS} value={cols} onChange={setCols} testid="history-cols" />}
          {table && (
            <div className="tbl-wrap"><table className="tbl" data-testid="history-table">
              <thead><tr><th scope="col">Match</th>{shown.map((st) => <th key={st.id} scope="col">{st.label}</th>)}<th scope="col">Cards</th></tr></thead>
              <tbody>{games.map((g) => (
                <tr key={g.match_iid}><td><span className="team"><Crest team={g.opp} size={20} /> {g.home ? "v" : "at"} {g.opp?.name}<small className="muted"> {shortDay(g.kickoff)}</small></span>
                  {(g.sub_on != null || g.sub_off != null) && <small className="sub-note" data-testid="history-sub">{g.sub_on != null ? `On ${g.sub_on}'${g.replaced ? ` for ${g.replaced.name}` : ""}` : ""}{g.sub_on != null && g.sub_off != null ? " · " : ""}{g.sub_off != null ? `Off ${g.sub_off}'${g.replaced_by ? `, ${g.replaced_by.name} on` : ""}` : ""}</small>}</td>
                  {shown.map((st) => <td key={st.id} className="num">{num1(g[st.id])}</td>)}<td className="num">{Array.from({ length: g.red_cards || 0 }, (_, i) => <span key={`r${i}`} className="card-dot card-dot--r" title="Red card" />)}{Array.from({ length: g.yellow_cards || 0 }, (_, i) => <span key={`y${i}`} className="card-dot card-dot--y" title="Yellow card" />)}{!g.red_cards && !g.yellow_cards ? "–" : null}</td></tr>
              ))}</tbody>
            </table></div>
          )}
        </>
      )}</QuickView>
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
      {/* The head opened with a name and a grey word, then made you scroll past a card to find out
          who he plays next. Position, club and the next fixture are the three things you want
          before anything else, so they are in the head: the club as its crest, and the fixture with
          both crests and whether he is at home or away. */}
      <header className="phead v2-phead">
        {/* The club's mark, blurred right down behind the head, so the page is recognisably about
            this club before a word is read. Decorative only: it carries no information the text
            does not, so it is hidden from assistive technology and sits under everything. */}
        {/* With a crest we blur the real thing; without one (crests arrive from PitchAPI and are
            absent in demo data) the head still gets a quiet tint rather than nothing, so the
            treatment does not appear and disappear with the image. */}
        <span className={"v2-phead-wash" + (team?.image_url ? "" : " is-plain")} aria-hidden="true"
              style={team?.image_url ? { backgroundImage: `url(${team.image_url})` } : undefined} />
        <PlayerAvatar player={p} size={96} decorative={false} />
        <div className="phead-main">
          <h1>{p.name}</h1>
          <p className="v2-phead-sub">
            <span className="v2-pos">{posLabel(p.pos)}</span>
            {team && <Link to={`/team/${team.id}`} className="v2-club"><Crest team={team} size={22} /> {team.name}</Link>}
          </p>
          {nx && (
            <Link to={`/match/${nx.id}`} className="v2-nextfx" data-testid="player-next-fixture">
              <span className="v2-nextfx-at">{nx.home_iid === team?.iid ? "Home" : "Away"}</span>
              <span className="v2-nextfx-t"><Crest team={nx.home} size={24} />{nx.home?.name}</span>
              <span className="v2-nextfx-v">v</span>
              <span className="v2-nextfx-t"><Crest team={nx.away} size={24} />{nx.away?.name}</span>
              <time>{kickoff(nx.kickoff)}</time>
            </Link>
          )}
          <div><FollowButton kind="player" refId={p.id} name={p.name} /></div>
        </div>
      </header>
      <History id={id} forecasts={forecasts} />
      {/* The fixture itself has moved into the head, so this is what it was always for: the lines. */}
      <section className="card" data-testid="player-next">
        <h2 className="k-sec">What we expect next match</h2>
        {!nx ? <p className="muted">No upcoming match loaded.</p>
          : forecasts.length ? <div className="fgrid">{forecasts.map((f) => <ForecastCard key={f.id} f={{ ...f, player: p }} teams={teams} homeIid={nx.home_iid} />)}</div>
          : <p className="muted small">No forecasts for this player yet.</p>}
      </section>
      {/* Asked for: lead with Quick view and drop the "Last 10 games" box. They were two renderings
          of the same ten games stacked on one page -- the four-line overview could not be
          interrogated and the detailed one could not be compared. Quick view now does both jobs,
          because its strip draws the run graph for whichever market and line you choose. */}
      <Ranks id={id} />
      <Note id={id} />
    </section>
  );
}
