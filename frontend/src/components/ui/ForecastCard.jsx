// Forecast card (docs/24, docs/25 §5). Takes one CARD (docs/21: headline + more_lines), never raw forecast rows.
// Tap opens the detail sheet. The tick on the bar sits at p_usual (the player's or team's normalised usual).
import { useState } from "react";
import { Link } from "react-router-dom";
import { pct, range } from "../../lib/copy";
import { utc } from "../../lib/time";
import { Crest, PlayerAvatar } from "../Media";
import { TierBadge, CardRun } from "./Marks";
import { ForecastSheet } from "./ForecastSheet";
import { useCombo } from "../../lib/combo";
import Icon from "../Icon";

// Lineup badge (docs/27): a player's percentage is "if he plays"; whether he plays is this badge.
const BADGE = { confirmed: "Confirmed starter", likely: "Likely lineup", unsure: "Lineup not sure", bench: "On the bench" };

// A likelihood said as a frequency. "1 game in 3" is read as information; "34%" is read as a
// failure, and they are the same fact. The percentage keeps its place on the card as evidence --
// this is only the claim, and a claim is what the hero slot is for.
// Above a half the denominator stays at ten, because "1 game in 1" is not a sentence and it
// flattened 79% and 92% into the same words -- the exact failure the claim exists to avoid.
const oneIn = (p) => {
  if (p == null) return null;
  if (p >= 0.95) return "almost every game";
  if (p <= 0.04) return "almost never";
  if (p > 0.5) return `${Math.round(p * 10)} games in 10`;
  return `1 game in ${Math.round(1 / p)}`;
};

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
  // The run only earns its place when there is enough of it AND the card has a baseline to compare
  // against; without p_usual the claim sentence has nothing to say and the strip would be decoration.
  const run = !f.p_display && f.p_usual != null && (f.run || []).filter((g) => g && g.v != null).length >= 3 ? f.run : null;
  const usualWord = run ? oneIn(f.p_usual) : null;
  const nowWord = run ? oneIn(f.p) : null;
  const dir = f.p_usual == null ? "" : f.p >= f.p_usual ? "is-up" : "is-down";
  const dep = f.p_usual == null ? null : Math.round((f.p - f.p_usual) * 100);
  const shown = f.p_display || pct(f.p);
  const rng = f.p_display ? null : range(f.lo, f.hi);          // docs/03 §4.4: show the band with the number
  const tk = track?.[f.fkey];
  return (
    <article className={"k-fc" + (canAdd ? " k-fc--add" : "") + (tk?.state === "hit" ? " k-fc--hit" : tk?.state === "missed" ? " k-fc--missed" : "")} style={{ "--tone": tone(f.tier) }} data-testid={id}>
      <button type="button" className="k-fc-main" onClick={() => setSheet(true)} aria-label={`${name}, ${f.market}, ${shown}${rng ? `, likely range ${rng}` : ""}${f.tier ? `, ${f.tier}` : ""}. Open details`} data-testid={`${id}-open`}>
        <header className="k-fc-head">
          <Who f={f} fx={fx} />
          <span className="k-fc-who"><b>{name}</b><small data-testid={`${id}-fixture`}>{sub}</small></span>
          <span className="k-fc-tier"><TierBadge tier={f.tier} testid={`${id}-tier`} />{f.tier_note && <small className="k-fc-note" data-testid={`${id}-tier-note`}>{f.tier_note}</small>}</span>
        </header>
        <div className="k-fc-line"><span className="k-fc-market">{f.market}</span>
          {!run && <span className="k-fc-pwrap"><b className="k-fc-p" data-testid={`${id}-p`}>{shown}</b>{rng && <small className="k-fc-range" data-testid={`${id}-range`}>{rng}</small>}</span>}</div>
        {/* The claim, in the words a person would use. docs/redesign/v2 CRITIQUE: the hero slot ranks
            cards, and p cannot rank them -- "3+ shots 34%" and "1+ shot 93%" answer different
            questions, so the same big number means something different on every card. The departure
            from the player's own usual game is the one quantity that is comparable down a feed, and
            as a frequency it reads as a finding instead of as a weak number. */}
        {run && usualWord && (usualWord === nowWord
          ? <p className="v2-claim" data-testid={`${id}-claim`}><b>{nowWord}</b>, same as usual.</p>
          : <p className="v2-claim" data-testid={`${id}-claim`}>
              Usually <b>{usualWord}</b>. Here, <b className={dir}>{nowWord}</b>.</p>)}
        {tk && tk.state !== "unknown" && <div className="lv-row"><Track t={tk} id={id} /></div>}
        {/* v2 (docs/redesign/v2/PLAN.md): this was a filled meter, and a filled meter says "this number
            is big" -- the one thing a reader must not conclude, because a big number is exactly what a
            truism looks like. It now reads as a measurement on a 0-100 axis:
              band     the likely range, so uncertainty has width;
              segment  from what they USUALLY do to what they do in this fixture -- the length of that
                       segment is the size of the claim, and its colour is the direction;
              tick     their usual, kept visible so the segment has somewhere to start.
            A card with almost no segment is describing a normal game. That is the product's whole
            thesis (docs/50, docs/56) and it was previously only a sentence in small grey text. */}
        {run && <CardRun games={run} line={f.thr} pct={shown} opp={f.opp} down={dir === "is-down"}
                         who={f.scope === "team" ? "their" : "his"} testid={`${id}-run`} />}
        {run && <div className="v2-ev"><b className="k-fc-p v2-ev-p" data-testid={`${id}-p`}>{shown}</b>
          {rng && <small className="k-fc-range" data-testid={`${id}-range`}>{rng}</small>}
          {dep != null && <b className={"v2-ev-d " + dir} data-testid={`${id}-dep`}>{dep > 0 ? "+" : ""}{dep} {Math.abs(dep) === 1 ? "pt" : "pts"} vs usual</b>}</div>}
        {!run && <span className="k-fc-bar" aria-hidden="true"
              data-dir={f.p_usual == null ? undefined : (f.p >= f.p_usual ? "up" : "down")}>
          {rng && <i className="k-fc-band" style={{ left: `${Math.round(f.lo * 100)}%`, width: `${Math.max(0, Math.round((f.hi - f.lo) * 100))}%` }} />}
          <b style={f.p_usual == null
              ? { left: `${Math.round((f.p || 0) * 100)}%` }
              : { left: `${Math.round(Math.min(f.p, f.p_usual) * 100)}%`, width: `${Math.max(0.6, Math.abs((f.p - f.p_usual)) * 100)}%` }} />
          {f.p_usual != null && <i className="k-fc-usual" style={{ left: `${Math.round(f.p_usual * 100)}%` }} />}
        </span>}
        {f.is_personal && f.expected_usual != null
          ? <small className="k-fc-vs" data-testid={`${id}-usual`}>
              {f.scope === "player" ? "His usual game is " : "They usually manage "}
              <b>{f.expected_usual.toFixed(1)}</b>
              {f.p_usual != null && <> · this line lands {pct(f.p_usual)} of the time for {f.scope === "player" ? "him" : "them"}</>}
            </small>
          : null}
        {/* UX_AUDIT decision 6. "Usually 79%" and "Hit in 19 of his last 20 games" both restate what
            the bar now draws: the tick is their usual and the segment is the distance from it. Three
            sayings of one thing, stacked, on every card in a grid of twenty. The record keeps its place
            in the detail sheet, where the whole run is shown game by game and can actually be read. */}
        {/* docs/55: the number assumes he plays, and the ten-game strip beside it is made of starts. Saying so
            stops a reader reading a careful number as a wrong one. Nothing to say once the lineup is out. */}
        {f.scope === "player" && f.p_basis === "played" && !sure && (
          <small className="k-fc-vs" data-testid={`${id}-basis`}>
            Assumes he plays
            {f.p_start != null && f.p_start < 0.8 && <> · he starts {pct(f.p_start)} of the time</>}
          </small>
        )}
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
          {more.map((x) => <li key={x.fkey} style={{ "--tone": tone(x.tier) }}><span>{x.market}{track?.[x.fkey]?.state === "hit" && <span className="lv-tick" aria-label="Happened"><Icon name="check" size={14} /></span>}</span><b>{pct(x.p)}{range(x.lo, x.hi) && <small className="k-fc-range"> ({range(x.lo, x.hi)})</small>}</b></li>)}
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
