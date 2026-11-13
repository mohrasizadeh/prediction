// The match page's Preview (round 3): what a reader checks before kick-off that is not a forecast --
// who tends to score first, how each side plays, and every meeting we hold between the two. It sits
// under the Forecasts tab and only before kick-off; once the match is on, the match itself is the
// news and these are history. It replaced the Analysis tab, which held the same three things behind
// a fifth tab, between a jump bar and a per-player shots table that said less than the forecasts do.
//
// Round 4: the head-to-head list moved to its own H2H tab (MatchH2H.jsx), and this Preview is hidden
// behind SHOW_ANALYSIS in pages/Match.jsx until the analysis is developed.
//
// Everything is read as the backend sends it (README: never invent a field): d.styles[iid].tactics and
// d.matchup_locked from queries.match_detail, and /teams/{id}/first-goal through FirstGoal. A block with
// nothing to say is left out rather than drawn as "unknown" (docs/redesign/README, data gaps).
import { Crest } from "./Media";
import { TacticChip } from "./Football";
import FirstGoal from "./FirstGoal";
import { ProLock } from "./ui";

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

export default function MatchPreview({ d }) {
  return (
    <section className="mpv" aria-labelledby="mpv-h" data-testid="match-preview">
      <header className="mpv-head">
        <h2 className="mpv-title" id="mpv-h">Preview</h2>
        <p className="mpv-sub">Before kick-off: who tends to score first and how each side plays.</p>
      </header>
      <FirstGoals d={d} />
      <Style d={d} />
    </section>
  );
}
