// Small marks used everywhere (docs/24 "Components to build once"): tier badge, win/draw/loss bar, hit-rate strip.
// Colour never carries meaning alone: tiers show colour + word + dots, the bar prints its numbers.
import { pct, TIER } from "../../lib/copy";

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
