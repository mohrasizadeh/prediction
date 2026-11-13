// The match page's side column (docs/24 §3, round 2): what is true of the match whichever tab is open --
// where and when, who referees, where both clubs sit in the table, why the match matters to each, and
// what each plays next. A sticky column beside the tabs on a wide screen; below that, Match.jsx shows the
// same cards once, under the default tab. Every card is drawn only when it has something to say: the
// demo league has no venue or referee, and a card that said "unknown" would be a card of nothing.
//
// Everything here is read as the backend sends it (README: never invent a field):
//   d.match.stadium / round / kickoff, d.referee (referees.for_match), d.context[iid].why and
//   d.rotation[iid].why (match_context), /teams/{id} `league` and `next`, and the league's finished
//   fixtures (the same rows Standings builds its table from).
import { Link } from "react-router-dom";
import { utc } from "../lib/time";
import { num1 } from "./Football";
import { Crest } from "./Media";
import Standings from "./Standings";
import { situationChips } from "./MatchCentre";

const longDay = (s) => utc(s)?.toLocaleDateString(undefined, { weekday: "long", day: "numeric", month: "long", year: "numeric" });
const hhmm = (s) => utc(s)?.toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" });
const shortWhen = (s) => utc(s)?.toLocaleDateString(undefined, { weekday: "short", day: "numeric", month: "short" });
const refPath = (n) => `/referee/${encodeURIComponent(n)}`;

function Card({ title, testid, children, more }) {
  return (
    <section className="card msd-card" data-testid={testid} aria-labelledby={`${testid}-h`}>
      <header className="msd-head"><h2 className="msd-h" id={`${testid}-h`}>{title}</h2>{more}</header>
      {children}
    </section>
  );
}

function Info({ d, league }) {
  const m = d.match;
  return (
    <Card title="Match info" testid="msd-info">
      <dl className="msd-dl">
        {m.stadium && <div><dt>Venue</dt><dd data-testid="msd-venue">{m.stadium}</dd></div>}
        {league && <div><dt>Competition</dt><dd><Link to={`/league/${league.id}`}>{league.name}</Link>{m.round != null && <span className="msd-faint"> · Round {m.round}</span>}</dd></div>}
        <div><dt>Kick-off</dt><dd><time dateTime={m.kickoff} data-testid="msd-kickoff">{longDay(m.kickoff)}, {hhmm(m.kickoff)}</time></dd></div>
      </dl>
    </Card>
  );
}

// "+12%" against the cards the two teams would usually pick up -- the number Referees.jsx shows as
// "vs teams' usual", so the two pages say it in the same words.
const vsUsual = (f) => { const p = Math.round((f - 1) * 100); return `${p > 0 ? "+" : p < 0 ? "−" : "±"}${Math.abs(p)}%`; };

function Referee({ d }) {
  const r = d.referee;
  const name = r?.referee || d.match.referee;
  if (!name) return null;
  const nums = r && r.matches != null;
  return (
    <Card title="Referee" testid="msd-referee">
      <p className="msd-ref"><Link to={refPath(name)} data-testid="msd-referee-link"><b>{name}</b></Link>{nums && <span className="msd-faint"> · {r.matches} {r.matches === 1 ? "match" : "matches"}</span>}</p>
      {nums && (
        <dl className="msd-nums">
          {r.cards_per_game != null && <div><dt>Cards per game</dt><dd>{num1(r.cards_per_game)}</dd></div>}
          {r.cards_per_game_normalised != null && <div><dt>For the teams involved</dt><dd>{num1(r.cards_per_game_normalised)}</dd></div>}
          {r.factor != null && <div><dt>vs teams' usual</dt><dd className={r.factor > 1.03 ? "is-up" : r.factor < 0.97 ? "is-down" : ""}>{vsUsual(r.factor)}</dd></div>}
        </dl>
      )}
      {r?.sentence && <p className="msd-note">{r.sentence}</p>}
    </Card>
  );
}

function Table({ d, league, finals }) {
  if (!league || !finals?.length) return null;
  // Standings returns nothing in compact mode when no match of this season is finished yet.
  if (!finals.some((m) => !d.match.season || !m.season || m.season === d.match.season)) return null;
  return (
    <Card title="Table" testid="msd-table" more={<Link to={`/league/${league.id}`} className="msd-more" data-testid="msd-table-link">Full table</Link>}>
      <Standings matches={finals} season={d.match.season} compact highlight={[d.home.id, d.away.id]} />
    </Card>
  );
}

// Why this match matters to each club, in the engine's own sentences: the situation (relegation, the
// race at the top), the context lines and the rotation note. One block per club, under its crest.
function Insights({ d }) {
  const chips = situationChips(d);
  const clubs = [[d.home, d.match.home_iid], [d.away, d.match.away_iid]].map(([t, iid]) => {
    const lines = [
      ...chips.filter((c) => c.startsWith(`${t.name}: `)).map((c) => c.slice(t.name.length + 2)),
      ...(d.context?.[iid]?.why || []),
      ...(d.rotation?.[iid]?.why ? [d.rotation[iid].why] : []),
    ].filter(Boolean);
    return [t, [...new Set(lines)]];
  }).filter(([, lines]) => lines.length);
  if (!clubs.length) return null;
  return (
    <Card title="Worth knowing" testid="msd-insights">
      {clubs.map(([t, lines]) => (
        <div key={t.id} className="msd-club" data-testid={`msd-insights-${t.id}`}>
          <h3 className="msd-club-h"><Crest team={t} size={20} />{t.name}</h3>
          <ul className="msd-why">{lines.map((w) => <li key={w}>{w}</li>)}</ul>
        </div>
      ))}
    </Card>
  );
}

function NextMatch({ d, teams }) {
  const m = d.match;
  const rows = [d.home, d.away].map((t, i) => {
    const nx = (teams[i]?.next || []).find((x) => x.id !== m.id && utc(x.kickoff) > utc(m.kickoff) && x.home && x.away);
    return nx ? [t, nx] : null;
  }).filter(Boolean);
  if (!rows.length) return null;
  return (
    <Card title="Next match" testid="msd-next">
      <ul className="msd-next">{rows.map(([t, x]) => {
        const home = x.home.id === t.id, opp = home ? x.away : x.home;
        return (
          <li key={t.id}>
            <Link to={`/match/${x.id}`} data-testid={`msd-next-${t.id}`}>
              <Crest team={t} size={20} />
              <span className="msd-next-t"><b>{t.name}</b><small>{home ? "v" : "at"} {opp.name}</small></span>
              <span className="msd-next-when"><time dateTime={x.kickoff}>{shortWhen(x.kickoff)}</time><small>{hhmm(x.kickoff)}</small></span>
              <Crest team={opp} size={20} />
            </Link>
          </li>
        );
      })}</ul>
    </Card>
  );
}

// `teams` is [home club payload, away club payload] from /teams/{id}; `finals` the league's finished
// fixtures. Either may still be loading or have failed: the cards that need them simply wait.
export default function MatchSide({ d, teams = [], finals }) {
  const league = teams[0]?.league || teams[1]?.league || null;
  return (
    <div className="msd" data-testid="match-side">
      <Info d={d} league={league} />
      <Referee d={d} />
      <Table d={d} league={league} finals={finals} />
      <Insights d={d} />
      <NextMatch d={d} teams={teams} />
    </div>
  );
}
