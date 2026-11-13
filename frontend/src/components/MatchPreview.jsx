// The match page's Preview (round 3): what a reader checks before kick-off that is not a forecast --
// who tends to score first, how each side plays, and every meeting we hold between the two. It sits
// under the Forecasts tab and only before kick-off; once the match is on, the match itself is the
// news and these are history. It replaced the Analysis tab, which held the same three things behind
// a fifth tab, between a jump bar and a per-player shots table that said less than the forecasts do.
//
// Everything is read as the backend sends it (README: never invent a field): d.h2h from
// queries.match_detail (a_wins / draws / b_wins, `matches` newest first), d.styles[iid].tactics and
// d.matchup_locked from the same payload, and /teams/{id}/first-goal through FirstGoal. A block with
// nothing to say is left out rather than drawn as "unknown" (docs/redesign/README, data gaps).
import { Link } from "react-router-dom";
import { utc } from "../lib/time";
import { Crest } from "./Media";
import { TacticChip } from "./Football";
import FirstGoal from "./FirstGoal";
import { ProLock } from "./ui";

const day = (s) => utc(s)?.toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" });

function Block({ id, label, aside, children, testid }) {
  return (
    <section className="mpv-card" aria-labelledby={`mpv-${id}-h`} data-testid={testid}>
      <header className="mpv-cardhead"><h3 className="mpv-label" id={`mpv-${id}-h`}>{label}</h3>{aside}</header>
      {children}
    </section>
  );
}

function FirstGoals({ d }) {
  return (
    <Block id="fg" label="Who scores first · this season" testid="match-first-goal">
      <div className="mpv-pair">
        <FirstGoal team={d.home} compact testid="first-goal-home" />
        <FirstGoal team={d.away} compact testid="first-goal-away" />
      </div>
    </Block>
  );
}

// Playing style: the engine's tactic tags per club (styles.tactics). Locked on plans without the
// matchup comparison; left out when neither club has a tag, since two "no clear style" lines are a
// card of nothing.
function Style({ d }) {
  const sides = [[d.home, d.match.home_iid], [d.away, d.match.away_iid]].map(([t, iid]) => [t, d.styles?.[iid]?.tactics || []]);
  if (d.matchup_locked) {
    return (
      <Block id="style" label="Playing style" testid="match-style">
        <p className="mpv-note" data-testid="matchup-locked">The style comparison is part of a bigger plan. <ProLock testid="matchup-pro" /></p>
      </Block>
    );
  }
  if (!sides.some(([, xs]) => xs.length)) return null;
  return (
    <Block id="style" label="Playing style" testid="match-style">
      <ul className="mpv-style">{sides.map(([t, xs]) => (
        <li key={t.id} data-testid={`match-style-${t.id}`}>
          <span className="mpv-club"><Crest team={t} size={20} /><b>{t.name}</b></span>
          {xs.length ? <span className="chips">{xs.map((x) => <TacticChip key={x} t={x} />)}</span> : <span className="mpv-faint">No clear style yet</span>}
        </li>
      ))}</ul>
    </Block>
  );
}

// Head to head: the three counts as figures, the split as a bar, then every meeting as a link to
// that match. The two counts that belong to a club wear its crest, so the figures read without
// their labels; the larger one is set in the brand colour, never by colour alone (it is also the
// bigger number).
function H2H({ d }) {
  const h = d.h2h;
  const games = (h?.matches || []).filter((m) => m.id !== d.match.id && m.hg != null);
  if (!games.length) {
    return (
      <Block id="h2h" label="Head to head" testid="h2h">
        <p className="mpv-note" data-testid="h2h-empty">These clubs have not met in the matches we hold.</p>
      </Block>
    );
  }
  const tot = h.a_wins + h.draws + h.b_wins || 1;
  const figs = [
    [h.a_wins, `${d.home.name} wins`, d.home, h.a_wins > h.b_wins],
    [h.draws, h.draws === 1 ? "Draw" : "Draws", null, false],
    [h.b_wins, `${d.away.name} wins`, d.away, h.b_wins > h.a_wins],
  ];
  return (
    <Block id="h2h" label={`Head to head · last ${games.length === 1 ? "meeting" : `${games.length} meetings`}`} testid="h2h">
      <dl className="mpv-h2h-sum" data-testid="h2h-summary">{figs.map(([n, label, club, more]) => (
        <div key={label} className={more ? "is-more" : ""}>
          <dt>{club && <Crest team={club} size={16} />}<span>{label}</span></dt>
          <dd>{n}</dd>
        </div>
      ))}</dl>
      <div className="mpv-h2h-bar" aria-hidden="true">
        <i className="mpv-h2h-a" style={{ flexGrow: h.a_wins / tot }} /><i className="mpv-h2h-d" style={{ flexGrow: h.draws / tot }} /><i className="mpv-h2h-b" style={{ flexGrow: h.b_wins / tot }} />
      </div>
      <ul className="mpv-h2h-list" aria-label="Past meetings, newest first" data-testid="h2h-list">{games.map((m) => {
        const hw = m.hg > m.ag, aw = m.ag > m.hg;
        return (
          <li key={m.id}><Link to={`/match/${m.id}`} data-testid={`h2h-match-${m.id}`}
            aria-label={`${day(m.kickoff)}: ${m.home?.name} ${m.hg}, ${m.away?.name} ${m.ag}`}>
            <time className="mpv-when" dateTime={m.kickoff}>{day(m.kickoff)}</time>
            <span className={`mpv-t mpv-t--h${hw ? " is-win" : ""}`}><span>{m.home?.name}</span><Crest team={m.home} size={20} /></span>
            <b className="mpv-score">{m.hg}–{m.ag}</b>
            <span className={`mpv-t${aw ? " is-win" : ""}`}><Crest team={m.away} size={20} /><span>{m.away?.name}</span></span>
          </Link></li>
        );
      })}</ul>
    </Block>
  );
}

export default function MatchPreview({ d }) {
  return (
    <section className="mpv" aria-labelledby="mpv-h" data-testid="match-preview">
      <header className="mpv-head">
        <h2 className="mpv-title" id="mpv-h">Preview</h2>
        <p className="mpv-sub">Before kick-off: who tends to score first, how each side plays, and the meetings we hold.</p>
      </header>
      <FirstGoals d={d} />
      <Style d={d} />
      <H2H d={d} />
    </section>
  );
}
