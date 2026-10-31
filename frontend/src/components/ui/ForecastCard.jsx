// Forecast card (docs/24, docs/25 §5). Takes one CARD (docs/21: headline + more_lines), never raw forecast rows.
// Tap opens the detail sheet. The tick on the bar sits at p_usual (the player's or team's normalised usual).
import { useState } from "react";
import { Link } from "react-router-dom";
import { pct } from "../../lib/copy";
import { utc } from "../../lib/time";
import { Crest, PlayerAvatar } from "../Media";
import { TierBadge } from "./Marks";
import { ForecastSheet } from "./ForecastSheet";
import { useCombo } from "../../lib/combo";
import Icon from "../Icon";

// Lineup badge (docs/27): a player's percentage is "if he plays"; whether he plays is this badge.
const BADGE = { confirmed: "Confirmed starter", likely: "Likely lineup", unsure: "Lineup not sure", bench: "On the bench" };

export const fixtureOf = (f, teams = {}, homeIid) => {
  const team = f.team || teams[f.team_iid];
  const opp = f.opp || teams[f.opp_iid];
  const hid = f.home_iid ?? homeIid;
  const homeFirst = hid !== f.opp_iid;
  return { team, opp, homeFirst, text: team && opp ? (homeFirst ? `${team.name} v ${opp.name}` : `${opp.name} v ${team.name}`) : team?.name || "" };
};
export const timeOf = (s) => (s ? utc(s).toLocaleString(undefined, { weekday: "short", hour: "2-digit", minute: "2-digit" }) : "");
const tone = (t) => (t ? `var(--tier-${t.toLowerCase()})` : "var(--text3)");
// Shorten the first name, never the surname: "Rasmus Højlund" -> "R. Højlund".
export const shortName = (n) => { const p = (n || "").trim().split(/\s+/); return n && n.length > 16 && p.length > 1 ? `${p[0][0]}. ${p.slice(1).join(" ")}` : n; };

function Who({ f, fx }) {
  if (f.player) return <PlayerAvatar player={f.player} size={44} />;
  if (f.stat?.startsWith("match_") && fx.team && fx.opp) {
    return <span className="k-fc-crests">{fx.homeFirst ? <><Crest team={fx.team} size={30} /><Crest team={fx.opp} size={30} /></> : <><Crest team={fx.opp} size={30} /><Crest team={fx.team} size={30} /></>}</span>;
  }
  return <Crest team={fx.team} size={44} />;
}

// Live tracking (docs/31): hit = it has happened, live = counting, missed = full time and it did not, unknown = no count.
function Track({ t, id }) {
  if (!t || t.state === "unknown") return null;
  if (t.state === "hit") return <span className="lv-chip lv-chip--hit" data-testid={`${id}-hit`}><Icon name="check" size={14} />Happened</span>;
  if (t.state === "missed") return <span className="lv-chip lv-chip--miss" data-testid={`${id}-missed`}>Did not happen</span>;
  return <span className="lv-chip" data-testid={`${id}-live`}><span className="k-livedot" aria-hidden="true" />{t.current} of {t.needed} so far</span>;
}

export function ForecastCard({ f, teams, homeIid, showTime = true, testid, track }) {
  const [open, setOpen] = useState(false);
  const [sheet, setSheet] = useState(false);
  const fx = fixtureOf(f, teams, homeIid);
  const more = [...(f.more_lines || [])].sort((a, b) => b.p - a.p);
  const venueKnown = (f.home_iid ?? homeIid) != null;
  const sub = f.stat?.startsWith("match_") ? "Both teams"
    : [f.player && fx.team?.name, fx.opp ? `vs ${fx.opp.name}` : fx.text, !f.player && venueKnown && fx.opp ? (fx.homeFirst ? "home" : "away") : null].filter(Boolean).join(" · ");
  const id = testid || `fc-${f.id || f.fkey}`;
  const name = f.player ? shortName(f.player.name) : (f.stat?.startsWith("match_") ? fx.text || "Both teams" : fx.team?.name || f.team?.name || "");
  const lineup = f.scope === "player" ? (f.lineup_badge ? BADGE[f.lineup_badge] : f.lineup_confirmed ? "Confirmed starter" : f.tier_basis === "likely_starter" ? "Likely lineup" : "Lineup not sure") : null;
  const sure = f.lineup_badge ? f.lineup_badge === "confirmed" : !!f.lineup_confirmed;
  const muted = f.lineup_badge === "unsure" || f.lineup_badge === "bench";
  const { has, toggle } = useCombo();
  const canAdd = !!f.fkey && f.match_iid != null && f.addable !== false && !f.from_ladder && !(f.kickoff && utc(f.kickoff).getTime() < Date.now());
  const on = canAdd && has(f.fkey);
  const shown = f.p_display || pct(f.p);
  const tk = track?.[f.fkey];
  return (
    <article className={"k-fc" + (canAdd ? " k-fc--add" : "") + (tk?.state === "hit" ? " k-fc--hit" : tk?.state === "missed" ? " k-fc--missed" : "")} style={{ "--tone": tone(f.tier) }} data-testid={id}>
      <button type="button" className="k-fc-main" onClick={() => setSheet(true)} aria-label={`${name}, ${f.market}, ${shown}${f.tier ? `, ${f.tier}` : ""}. Open details`} data-testid={`${id}-open`}>
        <header className="k-fc-head">
          <Who f={f} fx={fx} />
          <span className="k-fc-who"><b>{name}</b><small data-testid={`${id}-fixture`}>{sub}</small></span>
          <span className="k-fc-tier"><TierBadge tier={f.tier} testid={`${id}-tier`} />{f.tier_note && <small className="k-fc-note" data-testid={`${id}-tier-note`}>{f.tier_note}</small>}</span>
        </header>
        <div className="k-fc-line"><span className="k-fc-market">{f.market}</span><b className="k-fc-p" data-testid={`${id}-p`}>{shown}</b></div>
        {tk && tk.state !== "unknown" && <div className="lv-row"><Track t={tk} id={id} /></div>}
        <span className="k-fc-bar" aria-hidden="true"><b style={{ width: `${Math.round((f.p || 0) * 100)}%` }} />{f.p_usual != null && <i className="k-fc-usual" style={{ left: `${Math.round(f.p_usual * 100)}%` }} />}</span>
        {f.p_usual != null && <small className="k-fc-vs" data-testid={`${id}-usual`}>Usually {pct(f.p_usual)}</small>}
        {f.reasons?.[0] && <p className="k-fc-why">{f.reasons[0]}</p>}
      </button>
      {(more.length > 0 || lineup || (showTime && f.kickoff)) && (
        <footer className="k-fc-foot">
          {more.length > 0 ? <button type="button" className="k-link" aria-expanded={open} onClick={() => setOpen(!open)} data-testid={`${id}-more`}>{open ? "Hide other lines" : `+${more.length} more line${more.length === 1 ? "" : "s"}`}</button> : <span />}
          <span className="k-fc-foot-r">{lineup && <span className={`k-tag${sure ? " k-tag--up" : ""}${muted ? " k-tag--muted" : ""}`} data-testid={`${id}-badge`}>{lineup}</span>}
            {showTime && f.kickoff && <small className="k-fc-date" data-testid={`${id}-date`}>{timeOf(f.kickoff)}</small>}</span>
        </footer>
      )}
      {open && (
        <ul className="k-fc-lines" data-testid={`${id}-lines`}>
          {more.map((x) => <li key={x.fkey} style={{ "--tone": tone(x.tier) }}><span>{x.market}{track?.[x.fkey]?.state === "hit" && <span className="lv-tick" aria-label="Happened"><Icon name="check" size={14} /></span>}</span><b>{pct(x.p)}</b></li>)}
        </ul>
      )}
      {canAdd && (
        <button type="button" className={"cb-add" + (on ? " on" : "")} aria-pressed={on} aria-label={`${on ? "Remove" : "Add"} ${name} ${f.market} ${on ? "from" : "to"} your combo`} onClick={() => toggle({ ...f, team: f.team || fx.team })} data-testid={`${id}-add`}>
          <Icon name={on ? "check" : "plus"} size={20} />
        </button>
      )}
      {f.from_ladder && <small className="k-fc-vs" data-testid={`${id}-ladder`}>Open the match to add this line.</small>}
      {f.player && <Link className="sr-only" to={`/player/${f.player.id}`}>{f.player.name} player page</Link>}
      <ForecastSheet open={sheet} onClose={() => setSheet(false)} f={f} fx={fx} testid={`${id}-sheet`} />
    </article>
  );
}
