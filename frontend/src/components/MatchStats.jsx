// This match's own numbers, home against away. docs/90.
//
// The match page had none. `match_detail` returned forecasts, events, lineups, a style model and a
// recap, and no statistics at all -- so the page a reader opens to see what happened could not tell
// them how many shots there had been. What the Analysis tab labels as team style is `team_styles`,
// a historical model the engine rebuilds; by design it does not move during a match.
//
// Two sources, one shape: `live_stats` while the match is being played, `team_match_stats` once it
// has been ingested. Both carry the same columns now, so the rows do not change at the whistle --
// only the caption under them does.
//
// The bar reuses the kit's own home/away pairing (`--brand` and `--tier-strong`, kit.css) and the
// flex-grow technique `FirstGoal` and `Momentum` already use. Nothing new was invented here.
import { Crest } from "./Media";
import { TEAM_STATS, STATS } from "./Football";

// Possession first because it frames everything else, then the shot columns together, then the
// discipline ones. `poss` is the only percentage, so it is the only one with a unit.
const ROWS = [
  { id: "poss", label: "Possession", pct: true },
  { id: "shots" }, { id: "sot" }, { id: "corners" },
  { id: "saves" }, { id: "tackles" },
  // `fouls` is the TEAM column name; the registries carry `fouls_committed`/`fouls_won` for a
  // PLAYER, so there is nothing to look up and the fallback rendered a lowercase "fouls" among
  // sentence-case neighbours. Name it here.
  { id: "fouls", label: "Fouls" },
  { id: "yellow_cards" }, { id: "xg", dp: 2 },
];
const LABEL = Object.fromEntries([...TEAM_STATS, ...STATS].map((s) => [s.id, s.label]));
const labelOf = (r) => r.label || LABEL[r.id] || r.id.replace(/_/g, " ");

const num = (v, dp = 0) => (v === null || v === undefined ? null : Number(v).toFixed(dp));

export default function MatchStats({ d, testid = "match-stats" }) {
  const s = d.stats;
  if (!s) return null;
  // A row is shown only when at least one side has a number for it. A match whose feed carried no
  // corner count should not display an empty "Corners" row that reads as nil-nil.
  const rows = ROWS.filter((r) => s.home?.[r.id] != null || s.away?.[r.id] != null);
  if (!rows.length) return null;
  return (
    <section className="card ms" data-testid={testid}>
      <header className="ms-head">
        <Crest team={d.home} size={22} />
        <h3 className="h3">{s.source === "live" ? "Statistics so far" : "Match statistics"}</h3>
        <Crest team={d.away} size={22} />
      </header>
      <ol className="ms-rows">
        {rows.map((r) => {
          const dp = r.dp || 0;
          const h = s.home?.[r.id], a = s.away?.[r.id];
          const hv = Number(h) || 0, av = Number(a) || 0;
          const unit = r.pct ? "%" : "";
          return (
            <li className="ms-row" key={r.id} data-testid={`${testid}-${r.id}`}>
              <b className="ms-v">{num(h, dp) ?? "–"}{h != null ? unit : ""}</b>
              <span className="ms-mid">
                <small>{labelOf(r)}</small>
                <span className="ms-bar" role="img"
                      aria-label={`${labelOf(r)}: ${d.home.name} ${num(h, dp) ?? "no figure"}${unit}, ${d.away.name} ${num(a, dp) ?? "no figure"}${unit}`}>
                  {/* Both sides zero would collapse the bar to nothing and read as missing data,
                      so each half keeps a hairline. */}
                  <i className="ms-bh" style={{ flexGrow: hv || (av ? 0.001 : 1) }} />
                  <i className="ms-ba" style={{ flexGrow: av || (hv ? 0.001 : 1) }} />
                </span>
              </span>
              <b className="ms-v ms-v--a">{num(a, dp) ?? "–"}{a != null ? unit : ""}</b>
            </li>
          );
        })}
      </ol>
      {/* Say which it is. A reader looking at a match still being played should know the numbers
          are mid-match, and one looking at a finished match should know they are not. */}
      <p className="muted small ms-note">
        {s.source === "live" ? "While the match is on, these update every few minutes." : "Final figures for this match."}
      </p>
    </section>
  );
}
