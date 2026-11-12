// Screen 8, Player (docs/01 §5, docs/04 Chart): hero, next-fixture forecasts, Quick view chart, history table.
import { useState } from "react";
import { useParams } from "react-router-dom";
import { useApi } from "../lib/useApi";
import { Crest } from "../components/Media";
import { ErrorBox, Loading } from "../components/States";
import { ColumnPicker, STATS, num1, shortDay, useStored, useTitle } from "../components/Football";
import { FollowButton } from "../components/Actions";
import { useAuth } from "../lib/auth";
import { del, put } from "../lib/api";
import { useToast } from "../components/Ui";
// The page used Football.jsx's ForecastCard while every other screen used the one in ui/. Tapping
// a card anywhere landed on a player page whose own cards were a different component with a
// different layout, which is exactly the inconsistency reported. One card, everywhere.
import { QuickView } from "../components/ui";
import { AnswerBlock, BADGE, LadderList, SubjectHead, WhyList } from "../components/ui/Subject";
import { fixtureOf, timeOf } from "../components/ui/ForecastCard";
import { pct } from "../lib/copy";

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

function History({ id, forecasts, stat, line }) {
  const [table, setTable] = useState(false);
  const [cols, setCols] = useStored("cols:history", ["minutes", "shots", "sot", "tackles", "goals"]);
  const shown = STATS.filter((s) => cols.includes(s.id));
  // The controls and the strip live in components/ui/QuickView.jsx, shared with the forecast sheet (docs/48).
  return (
    <section className="card" data-testid="quick-view-card">
      {/* "Quick view" named the widget. The block is a tool, so it says what it is for -- and the
          answer above it means it no longer needs to state the likelihood a second time. */}
      <header className="v2-sec-head v2-sec-head--card"><h2 className="h3 v2-sec">The last ten, and any other line</h2></header>
      <QuickView playerId={id} forecasts={forecasts} stat={stat} line={line} showForecast={false} testid="quick-view">{(games) => (
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

const RANK_LABEL = { shots: "Shots", sot: "On target", tackles: "Tackles", goals: "Goals", assists: "Assists" };
const nth = (n) => `${n}${["th", "st", "nd", "rd"][(n % 100 > 10 && n % 100 < 14) || n % 10 > 3 ? 0 : n % 10]}`;

// docs/24 §10 "Season numbers": the per-90 figure is the tile, the rank is its context. The tiles
// led with a 22px "164th" and printed the actual number at 11px behind a dot, so the one thing a
// reader comes to compare was the hardest thing to read. Only `rank` and `of` come back -- no
// position split -- so the rank says "of 180", never "of 61 forwards".
// Two places under 1 (0.23 assists is not 0.2), one above, as the mockup's 3.9.
const per90 = (v) => (v == null ? "–" : v < 1 ? v.toFixed(2) : v.toFixed(1));
function Ranks({ id }) {
  const q = useApi(`/players/${id}/ranks`);
  const r = q.data?.ranks || [];
  if (!r.length) return null;
  return (
    <section className="card pl-ranks" data-testid="player-ranks">
      <header className="v2-sec-head v2-sec-head--card"><h2 className="h3 v2-sec">This season, per 90 minutes</h2></header>
      <ul>{r.map((x) => (
        <li key={x.stat} data-testid={`player-rank-${x.stat}`}>
          <span className="pl-rk-k">{RANK_LABEL[x.stat] || x.stat}</span>
          <b className="pl-rk-v">{per90(x.per90)}</b>
          <span className="pl-rk-r"><span>{nth(x.rank)}</span> of {x.of}</span>
        </li>
      ))}</ul>
      <p className="k-faint k-small">Rank among {q.data.league ? `${q.data.league} players` : "players in his league"} with at least {q.data.min_minutes} minutes.</p>
    </section>
  );
}

export default function Player() {
  const { id } = useParams();
  const q = useApi(`/players/${id}`);
  const pl = q.data?.player;
  // docs/75. The title used to be the bare name, which competes with every page on the internet
  // that mentions him and answers none of the questions people actually type. These pages hold the
  // per-game stat history and a forward-looking number, so the title says so: "stats, shots per game
  // and what we expect next" is three long-tail searches in one line, and nothing here is a word the
  // copy rules forbid.
  const pTitle = pl?.name ? `${pl.name} stats, shots per game and what we expect next` : "Player";
  useTitle(pTitle, {
    type: "profile",
    image: pl?.image,
    vars: pl?.name ? { player: pl.name } : undefined,
    description: pl?.name
      ? `${pl.name}: shots, shots on target, tackles and cards per game over his last ten, how likely he is to reach each line in his next match, and the reasons behind it.`
      : undefined,
  });
  if (q.loading && !q.data) return <Loading rows={5} />;
  if (q.error) return <ErrorBox error={q.error} onRetry={q.reload} />;
  const { player: p, team, next_match: nx } = q.data;
  const cards = q.data.cards || q.data.forecasts || [];
  // The Quick view resolves ANY market and line from the ladder, so it needs every stored line.
  // It was handed `cards`, which is one grouped card per player -- a single stat -- so picking any
  // other market said "No forecast" however many the engine had actually produced.
  const forecasts = q.data.forecasts || cards;
  const teams = nx ? { [nx.home_iid]: nx.home, [nx.away_iid]: nx.away } : {};
  // The card the page leads with, and every rung behind it, so the ladder can be read and kept.
  const lead = cards.length ? { ...cards[0], player: p, team, match_id: nx?.id } : null;
  // With no current line the head was handed `null`, and SubjectHead, finding no player, drew the
  // CLUB: "Team 0", a crest and no position. The player is the subject whether or not the engine
  // has a line for him, so the head always gets him, and the next fixture from next_match.
  const oppIid = nx && p.team_iid != null ? (nx.home_iid === p.team_iid ? nx.away_iid : nx.home_iid) : null;
  const subject = lead || {
    scope: "player", player: p, team, pos: p.pos, team_iid: p.team_iid,
    ...(nx && oppIid != null ? { opp_iid: oppIid, home_iid: nx.home_iid, match_id: nx.id, kickoff: nx.kickoff } : {}),
  };
  // fixtureOf falls back to the club's name as its "fixture" text; with no next match that put a
  // second "Team 0" under the club chip, so the head gets no fixture line at all.
  const lfx = { ...fixtureOf(subject, teams, nx?.home_iid), ...(nx ? {} : { text: "" }) };
  // Availability belongs in the hero (docs/24 §10, mockup callout 1), not as 12px grey text under
  // the reasons. It is a fact about the match, so it is only stated when a forecast carries it.
  const avail = lead?.scope === "player" ? (BADGE[lead.lineup_badge] || (lead.lineup_confirmed ? BADGE.confirmed : null)) : null;
  const plays = lead?.p_play != null && lead.p_play < 1 ? lead.p_play : null;
  // The forecast is a sentence (docs/redesign/v10 §1): subject, verb, line. The verb ships with the
  // market; a market that will not compose (no verb) falls back to its plain label.
  const say = lead ? (lead.verb ? `${p.name} ${lead.verb} ${lead.market}` : lead.market) : null;
  const when = nx?.kickoff ? timeOf(nx.kickoff) : "";
  const vs = lfx.opp?.name ? `${lfx.homeFirst ? "vs" : "at"} ${lfx.opp.name}` : "";
  const allLines = lead
    ? [{ fkey: lead.fkey, market: lead.market, stat: lead.stat, thr: lead.thr, p: lead.p, lo: lead.lo, hi: lead.hi, tier: lead.tier },
       ...(lead.more_lines || [])]
    : [];
  return (
    <section className="pl-page" data-testid="player-page">
      {/* The head opened with a name and a grey word, then made you scroll past a card to find out
          who he plays next. Position, club and the next fixture are the three things you want
          before anything else, so they are in the head: the club as its crest, and the fixture with
          both crests and whether he is at home or away. */}
      {/* The same head the sheet opens with (docs/redesign/v4/SHEET.md). The two surfaces were
          about 80% the same material drawn two different ways; this is the block that makes them
          one. v2-ph2 stays in the stylesheet for the club page until that adopts it too. */}
      <SubjectHead f={subject} fx={lfx} size="page" fixtureTestid="player-next-fixture"
                   extraMeta={avail ? <span className="k-tag pl-avail" data-testid="player-avail">{avail}{plays != null && <> · plays {pct(plays)}</>}</span> : null}
                   action={<FollowButton kind="player" refId={p.id} name={p.name} />} testid="player-head" />
      {/* The fixture itself has moved into the head, so this is what it was always for: the lines. */}
      {/* Was a ForecastCard, which carried a second copy of the same ten games the Quick view
          below already draws -- the identical run in two idioms, 550px apart. The card is a
          ranking object for a feed; this page is the answer, so it states it directly. */}
      <section className="card pl-next" data-testid="player-next">
        <header className="v2-sec-head v2-sec-head--card">
          <h2 className="k-sec v2-sec">Next match</h2>
          {nx && (vs || when) && <span className="pl-next-when" data-testid="player-next-when">{[vs, when].filter(Boolean).join(" · ")}</span>}
        </header>
        {!nx ? <p className="muted">No upcoming match for {p.name} yet.</p>
          : lead ? <>
              <p className="pl-say" data-testid="player-say">{say}</p>
              {/* The reasons live inside the answer block now, as the evidence for the figure
                  above them rather than as a loose list after it. */}
              <AnswerBlock f={lead} size="page" testid="player-answer">
                <WhyList reasons={lead.reasons} testid="player-why" />
              </AnswerBlock>
              <LadderList lines={allLines} current={lead.fkey} parent={lead} actions testid="player-ladder" />
            </>
          : <p className="muted">No forecast for {p.name} in this match yet.</p>}
      </section>
      {/* The tool sits under the answer, not above it: measured, the answer began 889px down
          because the Quick view's controls came first. */}
      {/* It opens on the line the page leads with, so "2+ shots, 62%" above is followed by the ten
          games for 2+ shots rather than for 1+. A keeper with no line opens on saves, not on a
          shots strip of ten zeros. With no forecasts at all it gets none, so it does not repeat
          the "no forecast" the card above has already said. */}
      <History id={id} forecasts={forecasts.length ? forecasts : undefined}
               stat={lead?.stat || (p.pos === "GK" ? "saves" : "shots")}
               line={lead?.thr != null ? Math.floor(lead.thr) + 1 : 1} />
      {/* Asked for: lead with Quick view and drop the "Last 10 games" box. They were two renderings
          of the same ten games stacked on one page -- the four-line overview could not be
          interrogated and the detailed one could not be compared. Quick view now does both jobs,
          because its strip draws the run graph for whichever market and line you choose. */}
      <Ranks id={id} />
      <Note id={id} />
    </section>
  );
}
