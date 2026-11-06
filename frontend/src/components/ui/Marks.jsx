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

// The run (docs/redesign/v2). The signature graphic of the product, and the answer to the thing
// HitStrip could never show: ten filled-or-empty squares cannot tell a quiet game from a busy one,
// so a player who clears his line every week draws ten identical marks -- a picture of nothing.
//
// Each column stands to its own figure and the line is drawn across the run as a single rule. A
// rule cutting through the middle of the run is a forecast. A rule lying under every column is a
// truism, and now that is visible without reading a number, which is the whole argument of docs/56.
//
// `values` are oldest -> newest; null means the game has no figure.
export function RunStrip({ values = [], line, label, caption = true, testid = "ui-run" }) {
  const known = values.filter((v) => v != null);
  if (!known.length) return null;
  const vmax = Math.max(1, ...known);
  const hits = known.filter((v) => v >= line).length;
  const rule = Math.min(100, (line / vmax) * 100);
  return (
    <div className="v2-run" data-testid={testid}
         role="img" aria-label={`${label ? `${label}: ` : ""}${known.map((v) => v).join(", ")}; the line is ${line}; reached in ${hits} of ${known.length} games, oldest first`}>
      <div className="v2-run-plot" aria-hidden="true">
        <span className="v2-run-rule" style={{ bottom: `${rule}%` }}><em>{line}+</em></span>
        {values.map((v, i) => (
          <span key={i} className={"v2-run-col" + (v == null ? " nd" : v >= line ? " on" : "")}>
            <b style={{ height: `${v == null ? 0 : Math.max(3, (v / vmax) * 100)}%` }} />
            <i className="v2-run-v">{v == null ? "" : v}</i>
          </span>
        ))}
      </div>
      {caption && <p className="v2-run-cap k-faint k-small">{hits} of {known.length}</p>}
    </div>
  );
}

// A club in three characters. Slicing the name gave "TEA" for every side in a league of "Team 1",
// "Team 2"; a digit in the name is the part that identifies it, so it is the part to keep.
const abbr = (name) => {
  const t = String(name || "").replace(/[^\p{L}\p{N} ]/gu, " ").trim().split(/\s+/).filter(Boolean);
  if (!t.length) return "";
  const num = t.find((x) => /^\d+$/.test(x));
  if (num) return ((t.find((x) => !/^\d+$/.test(x)) || "")[0] || "" ).toUpperCase() + num;
  if (t[0].length >= 4) return t[0].slice(0, 3).toUpperCase();
  return t.join("").slice(0, 3).toUpperCase();
};

// The card's own run: the ten games behind a forecast, compact enough to sit in a feed card, ending
// in TONIGHT. GameStrip (below) is the same object at reading size on the player page; this is the
// glanceable one, and the two must agree, because a reader who taps a card expects the thing that
// grows to be the thing they tapped.
//
// Why the eleventh column: ten past bars leave the reader to join the history to the forecast
// themselves. Tonight is drawn as the line itself, dashed, with the likelihood underneath, so the
// strip ends at the question instead of stopping just before it.
//
// `games` are {v, m, opp} oldest -> newest, as queries._usual builds them.
export function CardRun({ games = [], line, pct: shown, opp, down, who = "his", testid = "ui-cardrun" }) {
  const known = games.filter((g) => g && g.v != null);
  if (known.length < 3) return null;                       // too few games to be evidence of anything
  const cleared = known.filter((g) => g.v > line).length;
  const vmax = Math.max(1, line + 1, ...known.map((g) => g.v));
  const need = Math.floor(line) + 1;                       // thr 2.5 -> the card is talking about 3+
  // A club has no minutes, so this row was ten columns of nothing -- a blank band across the card,
  // measured at about 10px. It has a better use: where the game was played. A club's corner and
  // shot counts swing with venue more than with anything else here, and `run[].home` was already
  // stored on every entry and drawn nowhere. For a player the minutes keep the row, because
  // "81', 79', 23'" is the thing that decides whether the figure beside it means anything.
  const slot = (g) => (g.m != null ? `${Math.round(g.m)}'` : g.home == null ? "" : g.home ? "H" : "A");
  const venues = known.some((g) => g.m == null && g.home != null);
  return (
    <div className={"v2-cr" + (down ? " is-down" : "")} data-testid={testid}
         role="img" aria-label={`Last ${known.length} games: ${known.map((g) => `${g.v}${g.m == null && g.home != null ? (g.home ? " at home" : " away") : ""}`).join(", ")}. Reached ${need} or more in ${cleared} of them. Tonight ${shown}.`}>
      <ol className="v2-cr-row" aria-hidden="true">
        {games.map((g, i) => (
          <li key={i} className={"v2-cr-g" + (g.v == null ? " nd" : g.v > line ? " on" : "")}>
            <b style={{ height: `${g.v == null ? 2 : Math.max(6, (g.v / vmax) * 100)}%` }} />
            <i className="v2-cr-v">{g.v == null ? "\u2013" : g.v}</i>
            <i className={"v2-cr-m" + (g.m != null && g.m < 70 ? " low" : "") + (g.m == null && g.home === false ? " away" : "")}>{slot(g)}</i>
            <i className="v2-cr-o">{g.opp?.image ? <Crest team={g.opp} size={13} /> : abbr(g.opp?.name || g.opp)}</i>
          </li>
        ))}
        <li className="v2-cr-g v2-cr-now">
          <b style={{ height: `${Math.max(6, (need / vmax) * 100)}%` }} />
          <i className="v2-cr-v">{need}+</i>
          <i className="v2-cr-m">{shown}</i>
          <i className="v2-cr-o">{opp?.image ? <Crest team={opp} size={13} /> : abbr(opp?.name || opp)}</i>
        </li>
      </ol>
      <p className="v2-cr-cap k-small">
        <span className="v2-cr-tag">Last {known.length}</span>
        <b>{cleared} cleared {need}+</b>
        {/* A club has no minutes, so that row is empty and the hint described a line that is not
            drawn. Say only what is there. */}
        <span className="v2-cr-hint">{known.some((g) => g.m != null) ? "minutes above, opponent below" : venues ? "home or away above, opponent below" : "opponent below"}</span>
      </p>
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
  const word = (label || stat).toLowerCase();
  const anyMins = rows.some((g) => g.minutes != null);
  // A club has no minutes, so this row was a blank band here too. Same answer as on the card:
  // where the game was played, which is the filter a club line is most often read through.
  const anyVenue = !anyMins && rows.some((g) => g.home != null);
  // docs/redesign/v2: each column stands to its own figure and the line is drawn across the whole
  // run, so this is the run graph and the game-by-game detail in one object rather than two
  // renderings of the same ten games stacked on a page.
  const vmax = Math.max(1, ...known.map((g) => g[stat]));
  const rule = Math.min(1, line / vmax);
  return (
    <div className="pgs" data-testid={testid}>
      <ol className="pgs-row" style={{ "--rule": rule }} aria-label={`${label || stat}, game by game, oldest first`}>
        <li className="v2-gs-rule" aria-hidden="true"><em>{line}+</em></li>
        {rows.map((g, i) => {
          const v = g[stat];
          const hit = v != null && v >= line;
          const mins = g.minutes;
          const who = g.opp?.name || "the opponent";
          return (
            <li key={g.match_iid ?? g.kickoff ?? i} className={"pgs-g" + (hit ? " on" : "") + (v == null ? " nd" : "")}
                data-testid={`${testid}-${g.match_iid ?? i}`}>
              {/* Always rendered, blank when the entity has no minutes. A club has none, so this
                  span used to disappear and every column lost a row: the line rule, positioned
                  against the column box, then landed BELOW all ten bars and the strip showed ten
                  of ten clearing a line its own caption said six had. A strip that contradicts its
                  caption is worse than no strip. */}
              <span className={"pgs-min" + (anyVenue && g.home === false ? " away" : "")} title={anyMins ? "Minutes played" : anyVenue ? "Home or away" : undefined} aria-hidden={anyMins || anyVenue ? undefined : "true"}>
                {anyMins ? (mins == null ? "\u2013" : `${Math.round(mins)}'`) : anyVenue ? (g.home == null ? "\u2013" : g.home ? "H" : "A") : "\u00a0"}</span>
              <span className="pgs-v" aria-hidden="true">{v == null ? "\u2013" : v}</span>
              <span className="v2-gs-bar" aria-hidden="true"><b style={{ height: `${v == null ? 0 : Math.max(2, (v / vmax) * 100)}%` }} /></span>
              <span className="pgs-opp"><Crest team={g.opp} size={22} /></span>
              <span className="sr-only">{`${g.home == null ? "Against" : g.home ? "At home against" : "Away against"} ${who}: ${v == null ? "no figure" : `${v} ${word}`}${mins == null ? "" : `, ${Math.round(mins)} minutes`}.`}</span>
            </li>
          );
        })}
      </ol>
      {note && <p className="pgs-key k-faint k-small">{known.length ? `${hits} of ${known.length} reached this line. ` : "No figures yet. "}{anyMins ? "Minutes above each column, opponent below." : anyVenue ? "Home or away above each column, opponent below." : "Opponent below each column."}</p>}
    </div>
  );
}

