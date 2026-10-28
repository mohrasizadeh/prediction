// Forecast card (docs/24, picture forecast_card_and_sheet.png). Takes one CARD (docs/21: headline + more_lines),
// never raw forecast rows. Tap opens the detail sheet. The "usual rate" tick is hidden until the API sends it (DATA_GAPS).
import { useState } from "react";
import { Link } from "react-router-dom";
import { pct } from "../../lib/copy";
import { utc } from "../../lib/time";
import { Crest, PlayerAvatar } from "../Media";
import { TierBadge } from "./Marks";
import { ForecastSheet } from "./ForecastSheet";

export const fixtureOf = (f, teams = {}, homeIid) => {
  const team = f.team || teams[f.team_iid];
  const opp = f.opp || teams[f.opp_iid];
  const hid = f.home_iid ?? homeIid;
  const homeFirst = hid !== f.opp_iid;
  return { team, opp, homeFirst, text: team && opp ? (homeFirst ? `${team.name} v ${opp.name}` : `${opp.name} v ${team.name}`) : team?.name || "" };
};
export const timeOf = (s) => (s ? utc(s).toLocaleString(undefined, { weekday: "short", hour: "2-digit", minute: "2-digit" }) : "");
const tone = (t) => (t ? `var(--tier-${t.toLowerCase()})` : "var(--text3)");

function Who({ f, fx }) {
  if (f.player) return <PlayerAvatar player={f.player} size={44} />;
  if (f.stat?.startsWith("match_") && fx.team && fx.opp) {
    return <span className="k-fc-crests">{fx.homeFirst ? <><Crest team={fx.team} size={30} /><Crest team={fx.opp} size={30} /></> : <><Crest team={fx.opp} size={30} /><Crest team={fx.team} size={30} /></>}</span>;
  }
  return <Crest team={fx.team} size={44} />;
}

export function ForecastCard({ f, teams, homeIid, showTime = true, testid }) {
  const [open, setOpen] = useState(false);
  const [sheet, setSheet] = useState(false);
  const fx = fixtureOf(f, teams, homeIid);
  const more = f.more_lines || [];
  const id = testid || `fc-${f.id || f.fkey}`;
  const name = f.player?.name || (f.stat?.startsWith("match_") ? fx.text || "Match" : fx.team?.name || "Team");
  const lineup = f.scope === "player" ? (f.lineup_confirmed ? "Lineup confirmed" : "Lineup likely") : null;
  return (
    <article className="k-fc" style={{ "--tone": tone(f.tier) }} data-testid={id}>
      <button type="button" className="k-fc-main" onClick={() => setSheet(true)} aria-label={`${name}, ${f.market}, ${pct(f.p)}${f.tier ? `, ${f.tier}` : ""}. Open details`} data-testid={`${id}-open`}>
        <header className="k-fc-head">
          <Who f={f} fx={fx} />
          <span className="k-fc-who"><b>{name}</b><small>{f.stat?.startsWith("match_") ? "Both teams" : fx.text}{showTime && f.kickoff ? ` · ${timeOf(f.kickoff)}` : ""}</small></span>
          <TierBadge tier={f.tier} testid={`${id}-tier`} />
        </header>
        <div className="k-fc-line"><span className="k-fc-market">{f.market}</span><b className="k-fc-p" data-testid={`${id}-p`}>{pct(f.p)}</b></div>
        <span className="k-fc-bar" aria-hidden="true"><b style={{ width: `${Math.round((f.p || 0) * 100)}%` }} /></span>
        {f.reasons?.[0] && <p className="k-fc-why">{f.reasons[0]}</p>}
      </button>
      {(more.length > 0 || lineup) && (
        <footer className="k-fc-foot">
          {more.length > 0 ? <button type="button" className="k-link" aria-expanded={open} onClick={() => setOpen(!open)} data-testid={`${id}-more`}>{open ? "Hide other lines" : `+${more.length} more line${more.length === 1 ? "" : "s"}`}</button> : <span />}
          {lineup && <span className={`k-tag${f.lineup_confirmed ? " k-tag--up" : ""}`}>{lineup}</span>}
        </footer>
      )}
      {open && (
        <ul className="k-fc-lines" data-testid={`${id}-lines`}>
          {more.map((x) => <li key={x.fkey} style={{ "--tone": tone(x.tier) }}><span>{x.market}</span><b>{pct(x.p)}</b></li>)}
        </ul>
      )}
      {f.player && <Link className="sr-only" to={`/player/${f.player.id}`}>{f.player.name} player page</Link>}
      <ForecastSheet open={sheet} onClose={() => setSheet(false)} f={f} fx={fx} testid={`${id}-sheet`} />
    </article>
  );
}
