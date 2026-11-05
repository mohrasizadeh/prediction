// Small marks used everywhere (docs/24 "Components to build once"): tier badge, win/draw/loss bar, hit-rate strip.
// Colour never carries meaning alone: tiers show colour + word + dots, the bar prints its numbers.
import { pct, TIER } from "../../lib/copy";
import { Crest } from "../Media";

export function TierBadge({ tier, testid = "ui-tier" }) {
  if (!tier) return null;
  const n = TIER[tier]?.dots || 0;
  return (
    <span className={`k-tier k-tier--${tier.toLowerCase()}`} aria-label={`${tier}, ${n} of 3`} data-testid={testid}>
      <span className="k-dots" aria-hidden="true">{[1, 2, 3].map((i) => <i key={i} className={i > n ? "o" : ""} />)}</span>{tier}
    </span>
  );
}

export function WdlBar({ home, draw, away, homeName = "Home", awayName = "Away", testid = "ui-wdl" }) {
  if (home == null || away == null) return null;
  const fav = home >= away ? "home" : "away";
  const label = `${homeName} ${pct(home)}, draw ${pct(draw)}, ${awayName} ${pct(away)}`;
  return (
    <div className="k-wdl" role="img" aria-label={label} data-testid={testid}>
      <div className="k-wdl-bar" aria-hidden="true">
        <span className="h" style={{ flexGrow: home || 0.01 }} /><span className="d" style={{ flexGrow: draw || 0.01 }} /><span className="a" style={{ flexGrow: away || 0.01 }} />
      </div>
      <div className="k-wdl-txt" aria-hidden="true">
        <span className={fav === "home" ? "k-wdl-fav" : ""}>{homeName} {pct(home)}</span>
        <span className={fav === "away" ? "k-wdl-fav k-wdl-fav--a" : ""}>{awayName} {pct(away)}</span>
      </div>
    </div>
  );
}

// hits: booleans oldest -> newest (true = line reached, null = no data)
export function HitStrip({ hits = [], label, testid = "ui-hitstrip" }) {
  if (!hits.length) return null;
  const n = hits.filter(Boolean).length;
  return (
    <div className="k-strip" role="img" aria-label={`${label ? `${label}: ` : ""}reached in ${n} of ${hits.length} games, oldest first`} data-testid={testid}>
      <span className="k-strip-sq" aria-hidden="true">{hits.map((h, i) => <i key={i} className={h ? "h" : h === null ? "x" : ""} />)}</span>
      <b>{n}/{hits.length}</b>
    </div>
  );
}


// One column per game, oldest to newest: minutes on top, the figure in the middle, the opponent's crest below.
// A column the player reached the line in is filled; one he did not is quiet; a game with no figure says so.
// The crest answers "who against", which the plain squares of HitStrip never could, and the minutes say whether
// a low figure means a quiet game or ten minutes off the bench (docs/45).
//
// `games` are the API's own rows, newest first, as /players/{id}/history and /teams/{id}/history return them.
// Team rows carry no minutes, so that line is simply left off for them.
export function GameStrip({ games = [], stat, line, label, note = true, testid = "ui-gamestrip" }) {
  const rows = [...games].reverse();
  if (!rows.length) return null;
  const known = rows.filter((g) => g[stat] != null);
  const hits = known.filter((g) => g[stat] >= line).length;
  // v2: each column stands to its own figure, so the run has a shape and the line can be read
  // across it. Ten identical boxes could not tell a quiet game from a busy one.
  const vmax = Math.max(1, ...known.map((g) => g[stat]));
  const word = (label || stat).toLowerCase();
  const anyMins = rows.some((g) => g.minutes != null);
  return (
    <div className="pgs" data-testid={testid}>
      <ol className="pgs-row" aria-label={`${label || stat}, game by game, oldest first`}>
        {rows.map((g, i) => {
          const v = g[stat];
          const hit = v != null && v >= line;
          const mins = g.minutes;
          const who = g.opp?.name || "the opponent";
          return (
            <li key={g.match_iid ?? g.kickoff ?? i} className={"pgs-g" + (hit ? " on" : "") + (v == null ? " nd" : "")}
                style={{ "--v": v == null ? 0 : v, "--vmax": vmax }}
                data-testid={`${testid}-${g.match_iid ?? i}`}>
              {anyMins && <span className="pgs-min" title="Minutes played">{mins == null ? "–" : `${Math.round(mins)}'`}</span>}
              <span className="pgs-v" aria-hidden="true">{v == null ? "–" : v}</span>
              <span className="pgs-opp"><Crest team={g.opp} size={22} /></span>
              <span className="sr-only">{`Against ${who}: ${v == null ? "no figure" : `${v} ${word}`}${mins == null ? "" : `, ${Math.round(mins)} minutes`}.`}</span>
            </li>
          );
        })}
      </ol>
      {/* The columns say most of this themselves; the count is the part worth printing. */}
      {note && <p className="pgs-key k-faint k-small">{known.length ? `${hits} of ${known.length} reached this line. ` : "No figures yet. "}{anyMins ? "Minutes above each column, opponent below." : "Opponent below each column."}</p>}
    </div>
  );
}
