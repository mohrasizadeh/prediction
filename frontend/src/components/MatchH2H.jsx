// The match page's H2H tab (round 4): every meeting we hold between the two clubs, and what those
// meetings add up to. It replaced the head-to-head list that sat in the Preview under Forecasts, which
// gave the three counts and the list and nothing about how the games went.
//
// Read as the backend sends it (README: never invent a field): d.h2h from queries.h2h --
// a_wins / draws / b_wins, `matches` newest first (each with `league`), `summary` and `insights` from
// h2h_summary.py. On the match page `a` is this fixture's home club and `b` the away club, and
// summary.venue counts the meetings with this same club at home. Every summary field is null when the
// meetings do not carry it (no stored stats, no goal events), and a block with nothing to say is left
// out rather than drawn as "unknown" (docs/redesign/README, data gaps).
//
// Order: the result split first (what a reader asks first), then the sentences that stand out, then
// the side-by-side averages, then the meetings themselves. The insights are already ranked by the
// server by how unusual each one is; the page keeps that order.
//
// Same card system as the rest of the page (docs/redesign/v10): 16px radius and padding, a 1px border,
// uppercase micro-label heads, 800-weight tabular figures, 22px chips, 44px targets. Home is --chart1
// and away --chart2, the pair the stat bars and the pitch use.
import { useState } from "react";
import { Link } from "react-router-dom";
import { utc } from "../lib/time";
import { Crest } from "./Media";
import { Seg } from "./Football";
import { PairRow } from "./MatchStats";

const day = (s) => utc(s)?.toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" });
const monthYear = (s) => utc(s)?.toLocaleDateString(undefined, { month: "short", year: "numeric" });
const int = (v) => (v == null ? "–" : String(Math.round(v)));
const dec1 = (v) => (v == null ? "–" : Number(v).toFixed(1));

function Card({ id, label, aside, children, testid, className = "" }) {
  return (
    <section className={`mh2-card ${className}`.trim()} aria-labelledby={`mh2-${id}-h`} data-testid={testid}>
      <header className="mh2-head"><h3 className="mh2-label" id={`mh2-${id}-h`}>{label}</h3>{aside}</header>
      {children}
    </section>
  );
}

// "Team 1 have not lost in the last 4 meetings" -- the run the newest meetings make, in words.
function streakText(st, d) {
  if (!st) return null;
  const who = st.side === "a" ? d.home.name : st.side === "b" ? d.away.name : null;
  if (st.kind === "won") return `${who} won the last ${st.n} meetings`;
  if (st.kind === "unbeaten") return `${who} have not lost in the last ${st.n} meetings`;
  if (st.kind === "drawn") return `The last ${st.n} meetings ended level`;
  return null;
}

// The split: both clubs' wins and the draws as big figures over one bar. The club with more wins is
// marked by its figure's size AND a ring, never by colour alone.
function Summary({ d, h, s, n }) {
  const tot = h.a_wins + h.draws + h.b_wins || 1;
  const cols = [
    { k: "a", n: h.a_wins, label: h.a_wins === 1 ? "win" : "wins", team: d.home, more: h.a_wins > h.b_wins },
    { k: "d", n: h.draws, label: h.draws === 1 ? "draw" : "draws", team: null, more: false },
    { k: "b", n: h.b_wins, label: h.b_wins === 1 ? "win" : "wins", team: d.away, more: h.b_wins > h.a_wins },
  ];
  const span = s?.first && s?.last && s.first !== s.last ? `${monthYear(s.first)} – ${monthYear(s.last)}` : s?.last ? monthYear(s.last) : null;
  const tiles = s ? [
    ["Goals a meeting", dec1(s.goals_pm), null, "h2h-goals-pm"],
    ["Both clubs scored", s.both_scored, `of ${n}`, "h2h-both"],
    ["3 or more goals", s.three_plus, `of ${n}`, "h2h-three"],
  ] : [];
  const best = s ? [[d.home, s.a?.biggest_win], [d.away, s.b?.biggest_win]].filter(([, w]) => w) : [];
  const run = streakText(s?.streak, d);
  return (
    <Card id="sum" label={`Head to head · ${n === 1 ? "last meeting" : `last ${n} meetings`}`} testid="h2h-summary-card" className="mh2-sum"
      aside={span && <span className="mh2-aside" data-testid="h2h-span">{span}</span>}>
      <dl className="mh2-wdw" data-testid="h2h-summary">{cols.map((c) => (
        <div key={c.k} className={`mh2-wdw-col mh2-wdw-col--${c.k}${c.more ? " is-more" : ""}`} data-testid={`h2h-count-${c.k}`}>
          <dt>{c.team ? <><Crest team={c.team} size={28} /><span className="mh2-wdw-name">{c.team.name}</span></> : <span className="mh2-wdw-name mh2-wdw-name--d">{h.draws === 1 ? "Draw" : "Draws"}</span>}</dt>
          <dd><span className="mh2-fig">{c.n}</span>{c.team && <span className="mh2-unit">{c.label}</span>}</dd>
        </div>
      ))}</dl>
      <div className="mh2-split" aria-hidden="true">
        {h.a_wins > 0 && <i className="mh2-split-a" style={{ flexGrow: h.a_wins / tot }} />}
        {h.draws > 0 && <i className="mh2-split-d" style={{ flexGrow: h.draws / tot }} />}
        {h.b_wins > 0 && <i className="mh2-split-b" style={{ flexGrow: h.b_wins / tot }} />}
      </div>
      {tiles.length > 0 && n > 1 && (
        <dl className="mh2-tiles" data-testid="h2h-tiles">{tiles.map(([label, v, unit, tid]) => (
          <div key={label} data-testid={tid}><dt>{label}</dt><dd>{v}{unit && <small> {unit}</small>}</dd></div>
        ))}</dl>
      )}
      {(run || best.length > 0) && (
        <ul className="mh2-facts" data-testid="h2h-facts">
          {run && <li data-testid="h2h-streak"><span className="mh2-fact-k">Current run</span><span>{run}</span></li>}
          {best.map(([t, w]) => (
            <li key={t.id} data-testid={`h2h-best-${t.id}`}>
              <span className="mh2-fact-k">Biggest win</span>
              <span><b>{t.name}</b> {w.gf}–{w.ga}{w.home ? " at home" : " away"}{w.kickoff && <>, <time dateTime={w.kickoff}>{monthYear(w.kickoff)}</time></>}</span>
              {w.match_id && <Link className="mh2-more" to={`/match/${w.match_id}`} aria-label={`Open ${t.name} ${w.gf}–${w.ga}, ${day(w.kickoff)}`}>Open</Link>}
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}

function Insights({ list }) {
  if (!list?.length) return null;
  return (
    <Card id="ins" label="What stands out" testid="h2h-insights">
      <ul className="mh2-ins">{list.map((x) => <li key={x.text} data-testid={`h2h-insight-${x.kind}`}>{x.text}</li>)}</ul>
    </Card>
  );
}

// Side by side: what each club averaged in these meetings. Goals come from the scores and are always
// there; the rest come from team_match_stats and are left out when neither club has them stored.
const AVG_ROWS = [["shots", "Shots"], ["sot", "Shots on target"], ["corners", "Corners"], ["fouls", "Fouls"], ["yellow_cards", "Yellow cards"]];

function Compare({ d, s, n }) {
  if (!s || n < 1) return null;
  const sa = s.a?.stats || {}, sb = s.b?.stats || {};
  const avg = AVG_ROWS.filter(([k]) => sa[k] != null || sb[k] != null);
  const counts = [["Clean sheets", s.a?.clean_sheets, s.b?.clean_sheets], ["Scored first", s.a?.scored_first, s.b?.scored_first]]
    .filter(([, x, y]) => x != null || y != null);
  const shown = s.stats_meetings || 0;
  return (
    <Card id="cmp" label="Side by side · a meeting" testid="h2h-compare">
      <div className="mh2-heads" aria-hidden="true">
        <span className="mh2-head"><Crest team={d.home} size={20} /><b>{d.home.name}</b></span>
        <span className="mh2-head mh2-head--away"><b>{d.away.name}</b><Crest team={d.away} size={20} /></span>
      </div>
      <ul className="mst-rows mh2-rows">
        <PairRow label="Goals" h={s.a?.goals_pm} a={s.b?.goals_pm} fmt={dec1} home={d.home.name} away={d.away.name} />
        {avg.map(([k, label]) => <PairRow key={k} label={label} h={sa[k]} a={sb[k]} fmt={dec1} home={d.home.name} away={d.away.name} />)}
      </ul>
      {counts.length > 0 && (
        <div className="mh2-group">
          <h4 className="mh2-label">{n === 1 ? "In the meeting" : `In ${n} meetings`}</h4>
          <ul className="mst-rows mh2-rows">{counts.map(([label, x, y]) => <PairRow key={label} label={label} h={x} a={y} fmt={int} home={d.home.name} away={d.away.name} />)}</ul>
        </div>
      )}
      {avg.length > 0 && shown < n && <p className="mh2-note" data-testid="h2h-stats-note">Shots, corners and cards from {shown} of the {n} meetings; we hold no match numbers for the others.</p>}
    </Card>
  );
}

function Meetings({ d, games }) {
  const [where, setWhere] = useState("all");
  const homeIid = d.match.home_iid;
  const here = games.filter((m) => m.home_iid === homeIid);
  const showSeg = here.length > 0 && here.length < games.length;
  const list = where === "here" && showSeg ? here : games;
  const res = (m) => {
    const gf = m.home_iid === homeIid ? m.hg : m.ag, ga = m.home_iid === homeIid ? m.ag : m.hg;
    return gf > ga ? "W" : gf === ga ? "D" : "L";
  };
  const resWord = { W: "win", D: "draw", L: "loss" };
  return (
    <Card id="list" label="Meetings · newest first" testid="h2h-meetings"
      aside={showSeg && <Seg value={where} onChange={setWhere} label="Which meetings" testid="h2h-venue"
        options={[{ id: "all", label: `All · ${games.length}` }, { id: "here", label: `At ${d.home.name} · ${here.length}` }]} />}>
      <ul className="mh2-list" aria-label="Past meetings, newest first" data-testid="h2h-list">{list.map((m) => {
        const hw = m.hg > m.ag, aw = m.ag > m.hg, r = res(m);
        return (
          <li key={m.id}><Link to={`/match/${m.id}`} data-testid={`h2h-match-${m.id}`}
            aria-label={`${day(m.kickoff)}${m.league?.name ? `, ${m.league.name}` : ""}: ${m.home?.name} ${m.hg}, ${m.away?.name} ${m.ag}. ${d.home.name} ${resWord[r]}`}>
            <span className="mh2-when" aria-hidden="true"><time dateTime={m.kickoff}>{day(m.kickoff)}</time>{m.league?.name && <small>{m.league.name}</small>}</span>
            <span className={`mh2-t mh2-t--h${hw ? " is-win" : ""}`} aria-hidden="true"><span>{m.home?.name}</span><Crest team={m.home} size={20} /></span>
            <b className="mh2-score" aria-hidden="true">{m.hg}–{m.ag}</b>
            <span className={`mh2-t${aw ? " is-win" : ""}`} aria-hidden="true"><Crest team={m.away} size={20} /><span>{m.away?.name}</span></span>
            <span className={`mh2-res mh2-res--${r}`} aria-hidden="true" title={`${d.home.name} ${resWord[r]}`}>{r}</span>
          </Link></li>
        );
      })}</ul>
    </Card>
  );
}

export default function MatchH2H({ d }) {
  const h = d.h2h;
  const games = (h?.matches || []).filter((m) => m.id !== d.match.id && m.hg != null && m.ag != null);
  if (!games.length) {
    return (
      <div className="mh2" data-testid="match-h2h">
        <Card id="none" label="Head to head" testid="h2h-empty-card">
          <p className="mh2-note" data-testid="h2h-empty">{d.home.name} and {d.away.name} have not met in the matches we hold. Their meetings will appear here once they have played each other.</p>
        </Card>
      </div>
    );
  }
  const s = h.summary, n = games.length;
  return (
    <div className="mh2" data-testid="match-h2h">
      <Summary d={d} h={h} s={s} n={n} />
      <Insights list={h.insights} />
      <Compare d={d} s={s} n={n} />
      <Meetings d={d} games={games} />
    </div>
  );
}
