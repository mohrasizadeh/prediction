// Screen 2, Match (docs/34): hero with win/draw/loss, then four tabs: Live or Recap (while on / after), Forecasts, Lineups (pitch + notes), Analysis (form, H2H, first goal, players, style).
import { useEffect, useRef, useState } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import { useApi } from "../lib/useApi";
import { Crest, PlayerAvatar } from "../components/Media";
import { Empty, ErrorBox, Loading } from "../components/States";
import { Tabs } from "../components/Ui";
import { Seg, TacticChip, num1, posLabel, useTitle } from "../components/Football";
import FirstGoal from "../components/FirstGoal";
import { Forecasts, Form, Hero, MiniBar, matchState } from "../components/MatchCentre";
import MatchSide from "../components/MatchSide";
import MatchEvents, { GOALS, Momentum, normEvent } from "../components/MatchEvents";
import LiveLineups, { PitchView, lineOf } from "../components/LiveLineups";
import MatchStats from "../components/MatchStats";
import { utc } from "../lib/time";
import { ForecastList, ProLock, Skeleton } from "../components/ui";
import { tierLabel } from "../lib/copy";
import { isLiveNow } from "../lib/live";
import { pct } from "../lib/copy";

const cardsOf = (d) => d.cards || d.forecasts;

// ------------------------------------------------------------------ Live and Recap
// The provider's score block, in the shape MatchEvents reads (sportapi.overlay -> match.live).
const feedScore = (d) => { const l = d.match.live || d.live || {}; return { home: l.hs, away: l.as, ht_home: l.ht_home, ht_away: l.ht_away, pen_home: l.pen_home, pen_away: l.pen_away }; };

// A clock for "updated n minutes ago": the page polls every 30 seconds, and a poll that fails keeps the
// last answer on screen (useApi), so without this the score would sit there looking current after the feed
// or our server went quiet.
function useNow(every = 30000) {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => { const t = setInterval(() => setNow(Date.now()), every); return () => clearInterval(t); }, [every]);
  return now;
}

function Stale({ at, testid = "match-live-stale" }) {
  const now = useNow();
  const t = utc(at);
  if (!t) return null;
  const min = Math.floor((now - t.getTime()) / 60000);
  if (min < 3) return null;
  return (
    <p className="tl-stale" role="status" data-testid={testid}>
      <span className="tl-stale-dot" aria-hidden="true" />
      Last update from the match feed {min < 60 ? `${min} minutes` : "over an hour"} ago. The score and events may be behind.
    </p>
  );
}

function LiveTab({ d }) {
  const sid = d.live?.sid;
  const q = useApi(sid ? `/live/${sid}/lineups` : null);
  const ev = d.live_events || [];
  const names = { home: d.home.name, away: d.away.name };
  return (
    <div className="live-detail mc-live" data-testid="match-live">
      <Stale at={d.match.live?.at || d.live?.at} />
      <Momentum events={ev} testid="match-momentum" {...names} />
      <MatchEvents events={ev} testid="match-live-events" phase="live" score={feedScore(d)} status={d.match.live?.status} {...names}
        emptyText="Goals, cards and substitutions appear here as they happen. This page refreshes every 30 seconds." />
      {q.loading ? <Loading rows={2} /> : q.error
        ? <p className="muted small" data-testid="match-live-lineups-error">The lineups from the match feed did not load. <button type="button" className="k-link" onClick={q.reload}>Try again</button></p>
        : (q.data?.lineups?.home || q.data?.lineups?.away) && (
          // The elevens are on the Lineups tab's pitch; here they are one tap away, not between the reader and the events.
          <details className="live-lu" data-testid="match-live-lineups-toggle"><summary>Lineups from the match feed</summary>
            <LiveLineups lineups={q.data.lineups} home={d.home.name} away={d.away.name} testid="match-live-lineups" title={null} />
          </details>
        )}
    </div>
  );
}

const ONLY = { all: () => true, goal: (k) => GOALS.has(k), cards: (k) => ["yellow", "second_yellow", "red", "card"].includes(k), sub: (k) => k === "sub" };

function Events({ d }) {
  const [only, setOnly] = useState("all");
  const live = matchState(d) === "live";
  const ev = d.events || [];
  const norm = ev.map(normEvent);
  const count = (s, t) => norm.filter((e) => (t === "goal" ? e.scorer === s : e.side === s && ONLY[t](e.kind))).length;
  if (!ev.length) {
    return <Empty icon="clock" testid="events-empty">{live ? "Goals, cards and substitutions show here once the match feed sends them." : d.match.status === "final" ? "Goals, cards and substitutions for this match are still loading." : "Goals, cards and substitutions show here after full time."}</Empty>;
  }
  const r = d.recap?.ht;
  const score = { home: d.match.hg, away: d.match.ag, ht_home: r?.[0], ht_away: r?.[1], pen_home: d.match.live?.pen_home, pen_away: d.match.live?.pen_away };
  return (
    <div className="mc-recap" data-testid="match-recap">
      <table className="ev-sum2" data-testid="events-summary">
        <caption className="sr-only">Match totals</caption>
        <thead><tr><th scope="col"><Crest team={d.home} size={18} /><span>{d.home.name}</span></th><th scope="col"><span className="sr-only">Count</span></th><th scope="col"><span>{d.away.name}</span><Crest team={d.away} size={18} /></th></tr></thead>
        <tbody>{[["goal", "Goals"], ["cards", "Cards"], ["sub", "Substitutions"]].map(([t, l]) => {
          const h = count("home", t), a = count("away", t);
          return <tr key={t}><td className={h > a ? "is-more" : ""}>{h}</td><th scope="row">{l}</th><td className={a > h ? "is-more" : ""}>{a}</td></tr>;
        })}</tbody>
      </table>
      <Seg label="Show" value={only} onChange={setOnly} options={[{ id: "all", label: "All" }, { id: "goal", label: "Goals" }, { id: "cards", label: "Cards" }, { id: "sub", label: "Subs" }]} testid="events-filter" />
      <MatchEvents events={ev} testid="events-list" phase={live ? "live" : "final"} score={score} home={d.home.name} away={d.away.name} show={ONLY[only]} />
    </div>
  );
}

// ------------------------------------------------------------------ Facts (finished match)
// The match's own numbers first, the way a reader checks a result: five paired bars from the stored
// team stats (queries.match_detail `team_stats`, null until the match is final), the timeline, each
// club's form going in, and how our forecasts did. A value we do not hold is "–", never 0, and a row
// with neither side known is left out.
const TOP = [
  ["xg", "Expected goals (xG)", (v) => v.toFixed(2)],
  ["shots", "Total shots", (v) => String(Math.round(v))],
  ["sot", "Shots on target", (v) => String(Math.round(v))],
  ["corners", "Corners", (v) => String(Math.round(v))],
];
const known = (v) => typeof v === "number" && Number.isFinite(v);
const dash = (v, fmt) => (known(v) ? fmt(v) : "–");

// Drawn with the Stats tab's own classes (matchstats.css, `.mst-*`), so a number reads the same in
// both places and "All stats" opens onto rows that look like these ones, with more of them.
function TopStats({ d, onAll }) {
  const ts = d.team_stats;
  if (!ts) return null;
  const rows = TOP.filter(([k]) => known(ts.home?.[k]) || known(ts.away?.[k]));
  const ph = ts.home?.poss, pa = ts.away?.poss, poss = known(ph) && known(pa) && ph + pa > 0;
  if (!rows.length && !poss) return null;
  return (
    <section className="mfx-sec mst-team" aria-labelledby="mfx-top-h" data-testid="facts-top-stats">
      <header className="mfx-head">
        <h2 className="k-sec" id="mfx-top-h">Top stats</h2>
        {onAll && <button type="button" className="btn btn--secondary btn--sm" onClick={onAll} data-testid="facts-all-stats">All stats</button>}
      </header>
      {poss && (
        <div className="mst-poss" data-testid="facts-stat-poss">
          <p className="mst-poss-h">Possession</p>
          <div className="mst-poss-bar" role="img" aria-label={`Possession: ${d.home.name} ${Math.round(ph)}%, ${d.away.name} ${Math.round(pa)}%`}>
            <span className="mst-poss-home" style={{ flexBasis: `${(ph / (ph + pa)) * 100}%` }}>{Math.round(ph)}%</span>
            <span className="mst-poss-away" style={{ flexBasis: `${(pa / (ph + pa)) * 100}%` }}>{Math.round(pa)}%</span>
          </div>
        </div>
      )}
      {rows.length > 0 && <ul className="mst-rows">{rows.map(([k, label, fmt]) => {
        const h = ts.home?.[k], a = ts.away?.[k];
        const max = Math.max(known(h) ? h : 0, known(a) ? a : 0);
        const more = known(h) && known(a) && h !== a ? (h > a ? "home" : "away") : null;
        const w = (v) => (!known(v) || max <= 0 ? 0 : (v / max) * 100);
        return (
          <li key={k} className="mst-row" data-testid={`facts-stat-${k}`}>
            <div className="mst-row-top" aria-hidden="true">
              <span className={`mst-val mst-val--home${more === "home" ? " is-more" : ""}`}>{dash(h, fmt)}</span>
              <span className="mst-label">{label}</span>
              <span className={`mst-val mst-val--away${more === "away" ? " is-more" : ""}`}>{dash(a, fmt)}</span>
            </div>
            <div className="mst-bars" aria-hidden="true">
              <span className="mst-track mst-track--home"><i className={more === "home" ? "is-more" : ""} style={{ width: `${w(h)}%` }} /></span>
              <span className="mst-track mst-track--away"><i className={more === "away" ? "is-more" : ""} style={{ width: `${w(a)}%` }} /></span>
            </div>
            <span className="sr-only">{label}: {d.home.name} {dash(h, fmt)}, {d.away.name} {dash(a, fmt)}</span>
          </li>
        );
      })}</ul>}
    </section>
  );
}

// Each club's last five league results before this match, oldest to newest, from the league's
// finished fixtures (the rows the side column's table is built from). Cup matches are not in them,
// so the heading says "league". Each result is a link to that match.
function formBefore(finals, team, kickoff) {
  const t0 = utc(kickoff);
  return (finals || []).filter((m) => m.hg != null && (m.home?.id === team.id || m.away?.id === team.id) && utc(m.kickoff) < t0)
    .sort((a, b) => utc(b.kickoff) - utc(a.kickoff)).slice(0, 5).reverse()
    .map((m) => {
      const home = m.home.id === team.id, gf = home ? m.hg : m.ag, ga = home ? m.ag : m.hg;
      return { id: m.id, opp: home ? m.away : m.home, home, gf, ga, r: gf > ga ? "W" : gf < ga ? "L" : "D" };
    });
}
const RES = { W: "Won", D: "Drew", L: "Lost" };

function FactsForm({ d, finals }) {
  if (!finals) return <Skeleton shape="row" count={2} testid="facts-form-loading" />;
  const clubs = [d.home, d.away].map((t) => [t, formBefore(finals, t, d.match.kickoff)]).filter(([, xs]) => xs.length);
  if (!clubs.length) return null;
  return (
    <section className="mfx-sec card" aria-labelledby="mfx-form-h" data-testid="facts-form">
      <header className="mfx-head"><h2 className="k-sec" id="mfx-form-h">League form before this match</h2></header>
      {clubs.map(([t, xs]) => (
        <div key={t.id} className="mfx-form" data-testid={`facts-form-${t.id}`}>
          <span className="mfx-form-t"><Crest team={t} size={22} /><b>{t.name}</b></span>
          <ol className="mfx-form-list" aria-label={`${t.name}, last ${xs.length} league results, oldest first`}>{xs.map((g) => (
            <li key={g.id}><Link to={`/match/${g.id}`} className={`mfx-res mfx-res--${g.r}`} aria-label={`${RES[g.r]} ${g.gf}–${g.ga} ${g.home ? "at home to" : "away at"} ${g.opp.name}`}>
              <span className="mfx-score">{g.gf}–{g.ga}</span><Crest team={g.opp} size={18} />
            </Link></li>
          ))}</ol>
        </div>
      ))}
    </section>
  );
}

// Our own recap: the hero says the count, this lists the Strong and Solid lines with their outcome
// (forecast_outcomes, attached as `outcome` after the whistle) through the same row the Forecasts tab uses.
function ForecastRecap({ d, onAll }) {
  const r = d.recap;
  const lines = cardsOf(d).filter((f) => (f.tier === "Strong" || f.tier === "Solid") && f.outcome).slice(0, 8);
  if (!r?.scored && !lines.length) return null;
  return (
    <section className="mfx-sec" aria-labelledby="mfx-fc-h" data-testid="facts-forecasts">
      <header className="mfx-head">
        <h2 className="k-sec" id="mfx-fc-h">How our forecasts did</h2>
        <button type="button" className="k-link" onClick={onAll} data-testid="facts-all-forecasts">All forecasts</button>
      </header>
      {r?.scored > 0 && <p className="mfx-fc-sum"><b>{r.hit} of {r.scored}</b> Strong and Solid forecasts came true
        {["Strong", "Solid"].filter((t) => r.by_tier?.[t]?.[1]).map((t) => <span key={t} className="mfx-faint"> · {tierLabel(t)} {r.by_tier[t][0]}/{r.by_tier[t][1]}</span>)}</p>}
      {lines.length > 0 && <ForecastList rows={lines} teams={{ [d.match.home_iid]: d.home, [d.match.away_iid]: d.away }} homeIid={d.match.home_iid} testid="facts-fc-list" />}
    </section>
  );
}

function Facts({ d, finals, onStats, onForecasts }) {
  return (
    <div className="mc-facts" data-testid="match-facts">
      <TopStats d={d} onAll={onStats} />
      <section className="mfx-sec" aria-labelledby="mfx-ev-h"><h2 className="k-sec" id="mfx-ev-h">Timeline</h2><Events d={d} /></section>
      <FactsForm d={d} finals={finals} />
      <ForecastRecap d={d} onAll={onForecasts} />
    </div>
  );
}

// ------------------------------------------------------------------ Lineups
// What happened to each player, from the saved events (match_extras: player_iid / in_iid), for the pitch badges
// and the "came on" list. Live events carry no player ids (sportapi.events_for), so the pitch stays clean while
// the match is on rather than guessing by name.
function playerMarks(events = []) {
  const by = {};
  const get = (iid) => (by[iid] = by[iid] || { goals: 0, og: 0, yellow: 0, red: 0, off: null });
  events.forEach((e) => {
    if (!e.player_iid) return;
    const n = normEvent(e);
    if (n.kind === "goal" || n.kind === "pen_goal") get(e.player_iid).goals += 1;
    else if (n.kind === "own_goal") get(e.player_iid).og += 1;
    else if (n.kind === "yellow") get(e.player_iid).yellow += 1;
    else if (n.kind === "red" || n.kind === "second_yellow") get(e.player_iid).red += 1;
    else if (n.kind === "sub") get(e.player_iid).off = n.label.replace("'", "");
  });
  return by;
}

function CameOn({ d }) {
  const subs = (d.events || []).map((e) => [e, normEvent(e)]).filter(([, n]) => n.kind === "sub" && n.side);
  if (!subs.length) return null;
  return (
    <section className="lu-on" data-testid="lineups-came-on">
      <h3 className="k-sec">Came on</h3>
      <div className="lu-on-cols">
        {["home", "away"].map((s) => (
          <ul key={s} className="lu-on-list" aria-label={`${d[s].name}, substitutes used`}>
            <li className="lu-on-team"><Crest team={d[s]} size={18} />{d[s].name}</li>
            {subs.filter(([, n]) => n.side === s).map(([e, n], i) => (
              <li key={i}>
                <span className="lu-on-min">{n.label}</span>
                <span className="lu-on-who"><b>{n.id ? <Link to={`/player/${n.id}`}>{n.name}</Link> : n.name}</b>{n.out && <small>for {n.outId ? <Link to={`/player/${n.outId}`}>{n.out}</Link> : n.out}</small>}</span>
              </li>
            ))}
            {!subs.some(([, n]) => n.side === s) && <li className="k-faint">No changes</li>}
          </ul>
        ))}
      </div>
    </section>
  );
}

function LiveBench({ d }) {
  const q = useApi(d.live?.sid ? `/live/${d.live.sid}/lineups` : null);
  if (!d.live?.sid || q.loading || q.error) return null;
  return <LiveLineups lineups={q.data?.lineups} home={d.home.name} away={d.away.name} bench testid="lineups-bench" />;
}

// Who will not play or may not, from the availability list (availability.public_list: status "out" or
// "doubtful", a free-text reason, an optional return date). It says nothing about the bench, so it is
// grouped by club and stops there. Hidden when nobody is listed: "no absences" from a feed that may
// simply not cover this league would be a claim we cannot make.
function Absences({ d }) {
  const av = d.availability || [];
  if (!av.length) return null;
  const clubs = [[d.home, d.match.home_iid], [d.away, d.match.away_iid]].map(([t, iid]) => [t, av.filter((r) => r.team_iid === iid)]).filter(([, xs]) => xs.length);
  if (!clubs.length) return null;
  return (
    <section className="lu-abs" aria-labelledby="lu-abs-h" data-testid="lineups-absences">
      <h3 className="k-sec" id="lu-abs-h">Injured and suspended</h3>
      <div className="lu-on-cols">{clubs.map(([t, xs]) => (
        <ul key={t.id} className="lu-abs-list" aria-label={`${t.name}, out or doubtful`}>
          <li className="lu-on-team"><Crest team={t} size={18} />{t.name}</li>
          {xs.map((r) => (
            <li key={r.player_iid} data-testid={`absence-${r.player?.id || r.player_iid}`}>
              <span className="lu-abs-who">{r.player?.id ? <Link to={`/player/${r.player.id}`}>{r.player.name}</Link> : <span>{r.player?.name || "Player"}</span>}
                {(r.reason || r.until) && <small>{r.reason}{r.reason && r.until ? " · " : ""}{r.until && `until ${utc(r.until)?.toLocaleDateString(undefined, { day: "numeric", month: "short" })}`}</small>}</span>
              <span className={`lu-abs-tag lu-abs-tag--${r.status}`}>{r.status === "out" ? "Out" : "Doubtful"}</span>
            </li>
          ))}
        </ul>
      ))}</div>
    </section>
  );
}

function Lineups({ d }) {
  const pp = {};
  (d.forecasts || []).forEach((f) => { if (f.player_iid != null && f.p_play != null) pp[f.player_iid] = Math.max(pp[f.player_iid] || 0, f.p_play); });
  const predicted = !(d.starters || []).length;
  const list = predicted ? d.predicted || [] : d.starters;
  const conf = !predicted && d.starters.every((s) => s.confirmed);
  const marks = conf ? playerMarks(d.events) : {};
  const by = (iid) => {
    const seen = new Set();
    return list.filter((s) => s.team_iid === iid).filter((s) => !seen.has(s.player_iid) && seen.add(s.player_iid))
      .sort((a, b) => Number(!!b.confirmed) - Number(!!a.confirmed) || (pp[b.player_iid] ?? b.p_play ?? 1) - (pp[a.player_iid] ?? a.p_play ?? 1)).slice(0, 11);
  };
  if (!list.length) return (
    <div className="mc-lineups mc-lineups--v3" data-testid="match-lineups">
      <Empty icon="users" testid="lineups-empty">No lineups yet. They usually arrive about an hour before kickoff.</Empty>
      <LiveBench d={d} />
      <Absences d={d} />
    </div>
  );
  const side = (key, team, iid) => {
    const xs = by(iid);
    return {
      key, team, formation: xs.find((s) => s.formation)?.formation || null, coach: d.coach?.[key] || null,
      players: xs.map((s) => {
        const p = pp[s.player_iid] ?? s.p_play;
        return {
          key: `${key}-${s.player_iid}`, id: s.player?.id, name: s.player?.name || "", image: s.player?.image, shirt: s.shirt_number,
          captain: !!s.is_captain, line: lineOf(s.position_id, s.pos, s.player?.pos), grid: s.grid,
          x: typeof s.pitch_x === "number" ? s.pitch_x : undefined, y: typeof s.pitch_y === "number" ? s.pitch_y : undefined,
          pct: !conf && p != null ? pct(p) : null, unsure: !conf && p != null && p < 0.7, badges: marks[s.player_iid], rating: s.rating ?? null,
        };
      }),
    };
  };
  const sides = [side("home", d.home, d.match.home_iid), side("away", d.away, d.match.away_iid)];
  return (
    <div className="mc-lineups mc-lineups--v3" data-testid="match-lineups">
      <div className="lu-head">
        {conf ? <span className="k-tag k-tag--up" data-testid="pitch-lineups"><span aria-hidden="true">✓ </span>Lineups confirmed</span>
          : <span className="k-tag lu-tag--pred" data-testid={predicted ? "pitch-predicted" : "pitch-lineups"}>{predicted ? "Predicted" : "Expected"} · not confirmed</span>}
        <p className="muted small">{conf ? "The announced starting elevens." : predicted
          ? "Our most likely eleven from each player's chance to start. Percent = chance he starts; faded = under 70%. The real lineups replace it about an hour before kickoff."
          : "The expected elevens, with each player's chance to start; faded = under 70%."}</p>
      </div>
      <PitchView sides={sides} testid="pitch" />
      <CameOn d={d} />
      <LiveBench d={d} />
      <Absences d={d} />
    </div>
  );
}

// ------------------------------------------------------------------ Analysis
function Players({ d }) {
  const [team, setTeam] = useState("home");
  const t = team === "home" ? d.home : d.away;
  const q = useApi(`/teams/${t.id}/squad-grid`, { stat: "shots", last: 10 });
  return (
    <>
      <Seg label="Team" value={team} onChange={setTeam} options={[{ id: "home", label: d.home.name }, { id: "away", label: d.away.name }]} testid="players-team" />
      {q.loading ? <Loading /> : q.error ? <ErrorBox error={q.error} onRetry={q.reload} /> : !q.data.rows.length ? <Empty icon="users">No player data for this club yet.</Empty> : (
        <div className="tbl-wrap an-tbl" role="region" aria-label={`Shots by player, ${t.name}`} tabIndex={0}>
          <table className="tbl" data-testid="players-table">
            <thead><tr><th scope="col" className="sticky">Player</th><th scope="col" className="num"><abbr title="Games played of the last 10">Games</abbr></th><th scope="col" className="num"><abbr title="Shots per game">Per game</abbr></th><th scope="col" className="num">Total</th></tr></thead>
            <tbody>{q.data.rows.map((r) => (
              <tr key={r.player_iid}>
                <th scope="row" className="sticky"><Link className="cell-person" to={`/player/${r.player?.id}`}><PlayerAvatar player={r.player} size={28} /><span className="an-who"><b>{r.player?.name}</b><small className="muted">{posLabel(r.player?.pos)}</small></span></Link></th>
                <td className="num">{r.games.length}</td><td className="num">{num1(r.avg)}</td><td className="num">{num1(r.total)}</td>
              </tr>
            ))}</tbody>
          </table>
        </div>
      )}
    </>
  );
}

const shortDay = (s) => utc(s)?.toLocaleDateString(undefined, { day: "numeric", month: "short", year: "2-digit" });

function H2H({ d }) {
  const h = d.h2h;
  if (!h.matches.length) return <Empty icon="clock">These clubs have not met in the matches we hold.</Empty>;
  const tot = h.a_wins + h.draws + h.b_wins || 1;
  return (
    <>
      <div className="h2h-sum" data-testid="h2h-summary">
        <span className={h.a_wins > h.b_wins ? "is-more" : ""}><b>{h.a_wins}</b><Crest team={d.home} size={20} />{d.home.name} wins</span>
        <span><b>{h.draws}</b>Draws</span>
        <span className={h.b_wins > h.a_wins ? "is-more" : ""}><b>{h.b_wins}</b><Crest team={d.away} size={20} />{d.away.name} wins</span>
      </div>
      <div className="h2h-bar" aria-hidden="true"><i className="h2h-bar-a" style={{ flexGrow: h.a_wins / tot || 0.001 }} /><i className="h2h-bar-d" style={{ flexGrow: h.draws / tot || 0.001 }} /><i className="h2h-bar-b" style={{ flexGrow: h.b_wins / tot || 0.001 }} /></div>
      <ul className="h2h-list" aria-label="Past meetings, newest first" data-testid="h2h-list">{h.matches.map((m) => {
        const hw = m.hg > m.ag, aw = m.ag > m.hg;
        return (
          <li key={m.id}><Link to={`/match/${m.id}`} data-testid={`h2h-match-${m.id}`}>
            <time className="h2h-when">{shortDay(m.kickoff)}</time>
            <span className={`h2h-t h2h-t--h${hw ? " is-win" : ""}`}><span>{m.home?.name}</span><Crest team={m.home} size={20} /></span>
            <b className="h2h-score">{m.hg}–{m.ag}</b>
            <span className={`h2h-t${aw ? " is-win" : ""}`}><Crest team={m.away} size={20} /><span>{m.away?.name}</span></span>
          </Link></li>
        );
      })}</ul>
    </>
  );
}

const JUMPS = [["form", "Form"], ["h2h", "Head to head"], ["first", "First goal"], ["players", "Players"], ["style", "Style"]];
function Analysis({ d }) {
  const go = (id) => document.getElementById(`an-${id}`)?.scrollIntoView({ behavior: window.matchMedia?.("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth", block: "start" });
  return (
    <div className="mc-an" data-testid="match-analysis">
      <nav className="an-jump" aria-label="Jump to a section">{JUMPS.map(([id, label]) => <button key={id} type="button" className="chip" onClick={() => go(id)} data-testid={`an-jump-${id}`}>{label}</button>)}</nav>
      <section id="an-form" className="an-sec"><Form d={d} /></section>
      <section id="an-h2h" className="an-sec"><h2 className="k-sec">Head to head</h2><H2H d={d} /></section>
      <section id="an-first" className="an-sec"><h2 className="k-sec">Who scores first</h2><div className="fg-pair" data-testid="match-first-goal"><FirstGoal team={d.home} compact testid="first-goal-home" /><FirstGoal team={d.away} compact testid="first-goal-away" /></div></section>
      <section id="an-players" className="an-sec"><h2 className="k-sec">Shots by player · last 10 games</h2><Players d={d} /></section>
      <section id="an-style" className="an-sec"><h2 className="k-sec">Playing style</h2>
        {d.matchup_locked ? <Empty icon="padlock" testid="matchup-locked">The style comparison is part of a bigger plan. <ProLock testid="matchup-pro" /></Empty>
          : <div className="split2">{[d.home, d.away].map((t, i) => <div key={t.id} className="card"><h3 className="h3 team"><Crest team={t} size={22} />{t.name}</h3><div className="chips">{(d.styles?.[i ? d.match.away_iid : d.match.home_iid]?.tactics || []).map((x) => <TacticChip key={x} t={x} />)}{!(d.styles?.[i ? d.match.away_iid : d.match.home_iid]?.tactics || []).length && <span className="k-faint">No clear style yet</span>}</div></div>)}</div>}
      </section>
    </div>
  );
}

export default function Match() {
  const { id } = useParams();
  const [poll, setPoll] = useState(0);
  const q = useApi(`/matches/${id}`, undefined, { every: poll });
  // The tab lives in the URL (?tab=), so a tab can be linked to and shared, a reload keeps it, and
  // Back returns to the tab before -- each switch is a history entry, the way a reader treats a
  // tab that changes the whole page below the hero. The default tab is NOT written: a plain
  // /match/:id always opens on the tab its state calls for, and that changes as the match does.
  const [sp, setSp] = useSearchParams();
  const pick = sp.get("tab");
  const d = q.data;
  const isLive = isLiveNow(d?.match);
  useEffect(() => setPoll(isLive ? 30000 : 0), [isLive]);                  // live score, events and minute refresh by themselves
  const st = d ? matchState(d) : "before";
  // Both clubs (competition, form, next fixtures) and the league's finished matches (table, form
  // going in), asked once here for the hero, the side column and Facts alike.
  const th = useApi(d ? `/teams/${d.home.id}` : null);
  const ta = useApi(d ? `/teams/${d.away.id}` : null);
  const lid = th.data?.league?.id || ta.data?.league?.id;
  const fin = useApi(lid ? `/leagues/${lid}/fixtures` : null, { status: "final", limit: 400 });
  // null while it may still come; [] once it cannot (no league from either club, or the call failed).
  const finals = fin.data || (fin.error || (!lid && !th.loading && !ta.loading) ? [] : null);
  // Once the hero has scrolled under the header, a compact score bar takes its place above the tabs.
  const heroRef = useRef(null);
  const [mini, setMini] = useState(false);
  const hasD = !!d;
  useEffect(() => {
    const el = heroRef.current?.querySelector("[data-testid='match-hero']");
    if (!el || typeof IntersectionObserver === "undefined") return undefined;
    const hh = parseInt(getComputedStyle(document.documentElement).getPropertyValue("--header-h"), 10) || 64;
    const io = new IntersectionObserver(([e]) => setMini(!e.isIntersecting && e.boundingClientRect.top < hh), { rootMargin: `-${hh}px 0px 0px 0px` });
    io.observe(el);
    return () => io.disconnect();
  }, [hasD, id]);
  // Four tabs. The first one is the match itself while it is on (Live) or over (Facts); before kick-off it is the forecasts.
  const first = st === "live" ? "live" : st === "final" ? "facts" : null;
  // The one page seo.title_template was written for, so it is the one that supplies {team1}/{team2}.
  useTitle(d ? `${d.home.name} v ${d.away.name}` : "Match", {
    type: "article",
    vars: d ? { team1: d.home.name, team2: d.away.name } : undefined,
    description: d ? `How likely each forecast is for ${d.home.name} v ${d.away.name}, and the reasons behind it.` : undefined,
  });
  const paneRef = useRef(null);
  if (q.loading && !d) return <Loading rows={5} />;
  if (q.error) return <ErrorBox error={q.error} onRetry={q.reload} />;
  const n = cardsOf(d).filter((f) => f.p >= 0.5).length;
  const confirmed = (d.starters || []).length > 0 && d.starters.every((s) => s.confirmed);
  const tabs = [
    ...(first ? [{ id: first, label: first === "live" ? "Live" : "Facts" }] : []),
    { id: "forecasts", label: "Forecasts", badge: n || null, badgeLabel: n ? `${n} forecasts` : undefined },
    { id: "lineups", label: "Lineups", badge: confirmed ? "✓" : null, badgeLabel: "confirmed" },
    // What each side did, once it is over and the provider's numbers are in (queries._match_stats).
    ...(d.match.status === "final" && d.team_stats ? [{ id: "stats", label: "Stats" }] : []),
    { id: "analysis", label: "Analysis" },
  ];
  // A ?tab= this state does not have (recap on a match not yet played, an old link) opens the default.
  const def = first || "forecasts";
  // The finished match's first tab was called Recap; links shared with ?tab=recap still open it.
  const asked = pick === "recap" ? "facts" : pick;
  const tab = tabs.some((t) => t.id === asked) ? asked : def;
  const setTab = (t) => {
    if (t === tab) return;
    const next = new URLSearchParams(sp);
    if (t === def) next.delete("tab"); else next.set("tab", t);
    setSp(next, { preventScrollReset: true });
    // Switching while deep in a long tab used to leave the reader wherever the old tab's height put
    // them -- often in the footer of the new one. Keep the tab bar where it is and start the new tab
    // at its top, the way an app's segmented tabs behave. Above that point nothing moves.
    const pane = paneRef.current;
    if (pane && mini) {
      const top = pane.getBoundingClientRect().top + window.scrollY - (document.querySelector(".mc-sticky")?.offsetHeight || 0) - (parseInt(getComputedStyle(document.documentElement).getPropertyValue("--header-h"), 10) || 64) - 12;
      if (window.scrollY > top) requestAnimationFrame(() => window.scrollTo({ top, behavior: "auto" }));
    }
  };
  return (
    <section className={`mc-page mc-page--side${mini ? " is-mini" : ""}`} data-testid="match-page">
      <h1 className="sr-only">{d.home.name} v {d.away.name}</h1>
      <div className="mc-main">
        <div ref={heroRef}><Hero d={d} teams={[th, ta]} /></div>
        <div className="mc-sticky">
          <Tabs value={tab} onChange={setTab} testid="match-tabs" className="mc-tabs" tabs={tabs} label="Match sections" panel="match-panel" />
          <MiniBar d={d} shown={mini} />
        </div>
        <div className="mc-pane" role="tabpanel" id="match-panel" aria-labelledby={`match-tabs-tab-${tab}`} ref={paneRef} data-testid={`match-pane-${tab}`}>
          {tab === "live" && (d.live?.sid ? <LiveTab d={d} /> : <Events d={d} />)}
          {tab === "facts" && <Facts d={d} finals={finals} onStats={tabs.some((t) => t.id === "stats") ? () => setTab("stats") : null} onForecasts={() => setTab("forecasts")} />}
          {tab === "forecasts" && <Forecasts d={d} matchId={id} />}
          {tab === "lineups" && <Lineups d={d} />}
          {tab === "stats" && <MatchStats d={d} />}
          {tab === "analysis" && <Analysis d={d} />}
        </div>
      </div>
      {/* The side column: beside the tabs from 1280px (matchday.css), every tab. Narrower, it falls
          under the pane and shows only on the default tab -- the cards once, not under every tab.
          It stays mounted while hidden, so switching back does not ask the server again. */}
      <aside className={`mc-aside${tab === def ? "" : " is-away"}`} aria-label="About this match" data-testid="match-aside">
        <MatchSide d={d} teams={[th.data, ta.data]} finals={finals} />
      </aside>
    </section>
  );
}
