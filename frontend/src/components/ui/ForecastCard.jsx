// Forecast card (docs/24, docs/25 §5). Takes one CARD (docs/21: headline + more_lines), never raw forecast rows.
// Tap opens the detail sheet. The tick on the bar sits at p_usual (the player's or team's normalised usual).
import { useState } from "react";
import { Link } from "react-router-dom";
import { pct, range } from "../../lib/copy";
import { utc } from "../../lib/time";
import { Crest, PlayerAvatar } from "../Media";
import { TierBadge, CardRun } from "./Marks";
import { LineActions } from "./Subject";
import { SaveButton } from "../Actions";
import { ForecastSheet } from "./ForecastSheet";
import { useCombo } from "../../lib/combo";
import Icon from "../Icon";

// Lineup badge (docs/27): a player's percentage is "if he plays"; whether he plays is this badge.
// engine.min_span's default (docs/56): a line whose likelihood moves less than six points between
// the league's leakiest and meanest defence is saying something about the league, not about tonight.
const DULL_SPAN = 0.06;

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
  // The lead line is the one with the most to say, which is often not the likeliest one this
  // player has. Reported: a safer line sitting at 92% was invisible behind "+3 more lines", so the
  // card looked like the player's best was the number on its face. The control now says what is
  // behind it whenever something behind it is likelier.
  const topMore = more.length && f.p != null && more[0].p > f.p ? more[0] : null;
  const venueKnown = (f.home_iid ?? homeIid) != null;
  const venue = !f.player && venueKnown && fx.opp ? (fx.homeFirst ? "home" : "away") : null;
  // The position he is expected to play. The run strip underneath has carried it per game since v8,
  // so the card could say which role the whole forecast assumes and did not -- "2+ tackles" means
  // something different for a full-back and for a striker, and the reader had to open the sheet to
  // find out which one they were looking at.
  const pos = f.scope === "player" && f.pos ? String(f.pos).toUpperCase() : null;
  const sub = f.stat?.startsWith("match_") ? "Both teams"
    : [f.player && fx.team?.name, pos, fx.opp ? `vs ${fx.opp.name}` : fx.text, venue].filter(Boolean).join(" · ");
  // The same line as JSX, so the club can carry its crest. The club was named on every player card
  // and drawn on none of them, which is the one identifier a reader recognises before they have read
  // a word. `sub` above is the string the card is ANNOUNCED with, so a screen reader gets the club,
  // the position and the fixture in words rather than a crest it cannot read.
  // Each piece carries its own TRAILING separator, inside a nowrap span. Leading separators put a
  // lone "\u00b7" at the start of the wrapped second line, which reads as a bullet for a list that
  // is not there.
  const segs = f.stat?.startsWith("match_") ? [] : [
    f.player && fx.team ? <><Crest team={fx.team} size={15} />{fx.team.name}</> : null,
    pos ? <em className="k-fc-pos">{pos}</em> : null,
    fx.opp ? `vs ${fx.opp.name}` : fx.text || null,
    venue,
  ].filter(Boolean);
  const subLine = f.stat?.startsWith("match_") ? "Both teams"
    : segs.map((x, i) => <span className="k-fc-seg" key={i}>{x}{i < segs.length - 1 && <span className="k-fc-sep" aria-hidden="true">·</span>}</span>);
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
  const run = !f.p_display && (f.run || []).filter((g) => g && g.v != null).length >= 3 ? f.run : null;
  const dir = f.p_usual == null ? "" : f.p >= f.p_usual ? "is-up" : "is-down";
    const dep = f.p_usual == null ? null : Math.round((f.p - f.p_usual) * 100);
  // Does the likely range sit clear of their usual, or still reach it? This is exactly the
  // Strong/Solid test in backend/tiering._departure_tier, said on the card instead of left for the
  // reader to work out by holding "43 to 64" against "48".
  const clears = f.p_usual == null || f.lo == null || f.hi == null ? null : (f.lo > f.p_usual || f.hi < f.p_usual);
  const shown = f.p_display || pct(f.p);
  const rng = f.p_display ? null : range(f.lo, f.hi);          // docs/03 §4.4: show the band with the number
  const tk = track?.[f.fkey];
  return (
    <article className={"k-fc" + (canAdd ? " k-fc--add" : "") + (tk?.state === "hit" ? " k-fc--hit" : tk?.state === "missed" ? " k-fc--missed" : "")} style={{ "--tone": tone(f.tier) }} data-testid={id}>
      <button type="button" className="k-fc-main" onClick={() => setSheet(true)} aria-label={`${name}, ${sub}, ${f.market}, ${shown}${rng ? `, likely range ${rng}` : ""}${f.tier ? `, ${f.tier}${f.tier_note ? `: ${f.tier_note}` : ""}` : ""}. Open details`} data-testid={`${id}-open`}>
        <header className="k-fc-head v2-fch">
          <Who f={f} fx={fx} />
          <span className="k-fc-who"><b>{name}</b><small className="k-fc-sub" data-testid={`${id}-fixture`}>{subLine}</small></span>
          {/* The likelihood is the anchor and belongs in the one place a reader's eye goes first.
              Moving it out cost the card its reference point, and the tier badge that took its slot
              squeezed the name into an ellipsis. Tier is a label for the number, so it sits with
              the market underneath it. */}
          <span className="k-fc-pwrap v2-fch-p"><b className="k-fc-p" data-testid={`${id}-p`}>{shown}</b>
            {rng && <small className="k-fc-range" data-testid={`${id}-range`}>{rng}</small>}</span>
        </header>
        <div className="k-fc-line"><span className="k-fc-market">{f.market}</span></div>
        {/* The claim, in the words a person would use. docs/redesign/v2 CRITIQUE: the hero slot ranks
            cards, and p cannot rank them -- "3+ shots 34%" and "1+ shot 93%" answer different
            questions, so the same big number means something different on every card. The departure
            from the player's own usual game is the one quantity that is comparable down a feed, and
            as a frequency it reads as a finding instead of as a weak number. */}
        {/* The card used to say "usually" about two different quantities a few lines apart: this
            one, which is their own rate for the line smoothed over a season, and the raw count in
            the strip below. On a card where those happened to disagree -- 57% here, 4 of the last
            10 there -- it read as the card contradicting itself. They are both real; they are not
            the same measurement, so they no longer share a word. This is "Usual". The strip is
            "Last 10". */}
        {/* THE VERDICT (docs/61). This row was four marks saying one thing: the badge, its note,
            `Usual 48%` and a `+8 pts` pill -- and the badge sat beside the PERCENTAGE while grading
            something else entirely, so a reader bound the two and read "57% Watch" next to "56%
            Solid" as the product contradicting itself. Measured across 200 cards, the badge and the
            number it sat next to correlated +0.09: on a player card the badge was, to a reader,
            noise attached to the wrong quantity.
            It is one sentence now, and the badge sits with the gap it actually grades. Nothing is
            lost: the usual is still printed, the gap is still in points, and the Strong/Solid
            distinction -- does the likely range clear their usual, or still reach it -- is said in
            words instead of left for the reader to derive from `43 to 64` against `48`. */}
        {(f.tier || (f.p_usual != null && dep != null)) && (
          <div className="v2-cmp" data-testid={`${id}-cmp`}>
            {f.p_usual != null && dep != null ? (
              <span className={"v2-verdict " + dir} data-testid={`${id}-dep`}>
                <i aria-hidden="true">{dep > 0 ? "\u25b2" : dep < 0 ? "\u25bc" : "\u2013"}</i>
                <b>{Math.abs(dep)} {Math.abs(dep) === 1 ? "point" : "points"}</b> {dep >= 0 ? "above" : "below"}{" "}
                {f.scope === "player" ? "his" : "their"} usual <b>{pct(f.p_usual)}</b>
                {clears != null && <> &middot; {clears ? "clear of it" : "the likely range still reaches it"}</>}
              </span>
            ) : <span />}
            <TierBadge tier={f.tier} testid={`${id}-tier`} />
          </div>
        )}
        {/* The record notes survive: "Similar lines happened 71% of the time" is our own measured record and
            is not said anywhere else. The DEPARTURE note is dropped, because the sentence above now
            says the same thing in the same breath as the gap it is about. */}
        {f.tier_note && !f.is_personal && <small className="k-fc-note" data-testid={`${id}-tier-note`}>{f.tier_note}</small>}
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
                         who={f.scope === "team" ? "their" : "his"}
                         streak={f.streak} recK={f.rec_k} recN={f.rec_n}
                         atHome={f.team_iid != null && f.home_iid != null ? f.team_iid === f.home_iid : undefined}
                         pos={f.pos} testid={`${id}-run`} />}
        {!run && <span className="k-fc-bar" aria-hidden="true"
              data-dir={f.p_usual == null ? undefined : (f.p >= f.p_usual ? "up" : "down")}>
          {rng && <i className="k-fc-band" style={{ left: `${Math.round(f.lo * 100)}%`, width: `${Math.max(0, Math.round((f.hi - f.lo) * 100))}%` }} />}
          <b style={f.p_usual == null
              ? { left: `${Math.round((f.p || 0) * 100)}%` }
              : { left: `${Math.round(Math.min(f.p, f.p_usual) * 100)}%`, width: `${Math.max(0.6, Math.abs((f.p - f.p_usual)) * 100)}%` }} />
          {f.p_usual != null && <i className="k-fc-usual" style={{ left: `${Math.round(f.p_usual * 100)}%` }} />}
        </span>}
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
        {/* The strongest line the card holds, NAMED, with the reason it is not the headline (docs/61).
            The footer used to tease `up to 94%`: a bigger number, no market, no explanation, in the
            smallest text on the card. Both readers we tested called that burying the good one, and
            27% of cards lead with something lower than they hold. Leading on prominence is right --
            a line that barely moves against any defence is a fact about the league, not a forecast
            -- but the card has to say so out loud rather than hint at it. `span` is how far the line
            moves across the league's defences, which is the whole argument. */}
        {topMore?.market && (
          <p className="v2-alt" data-testid={`${id}-alt`}>
            {f.scope === "player" ? "His" : "Their"} likeliest line here is <b>{topMore.market}</b> at <b>{pct(topMore.p)}</b>
            {topMore.span != null && Math.abs(topMore.span) < DULL_SPAN ? " \u2014 much the same against any defence." : "."}
          </p>
        )}
      </button>
      {(more.length > 0 || lineup || f.fkey || (showTime && f.kickoff)) && (
        <footer className="k-fc-foot">
          {more.length > 0 ? <button type="button" className="k-link" aria-expanded={open} onClick={() => setOpen(!open)} data-testid={`${id}-more`}>{open ? "Hide other lines" : `+${more.length} more line${more.length === 1 ? "" : "s"}`}</button> : <span />}
          <span className="k-fc-foot-r">{lineup && <span className={`k-tag${sure ? " k-tag--up" : ""}${muted ? " k-tag--muted" : ""}`} data-testid={`${id}-badge`}>{lineup}</span>}
            {showTime && f.kickoff && <small className="k-fc-date" data-testid={`${id}-date`}>{timeOf(f.kickoff)}</small>}
            {/* Every rung under "+N more lines" could be kept and the headline line -- the one the
                card is about -- could not, so the only way to follow what you were looking at was to
                open the sheet. Same control, same place in the row, as the rungs use. */}
            {f.fkey && <SaveButton fkey={f.fkey} />}</span>
        </footer>
      )}
      {open && (
        <ul className="k-fc-lines has-act" data-testid={`${id}-lines`}>
          {/* Reported: the card leads with 4+ shots at 70% while 2+ shots at 90% sits under it,
              and the reader could read the second but not keep it. Each rung carries its own fkey,
              so each one can now be saved, and added to a combo where the line is still open. */}
          {more.map((x) => <li key={x.fkey} style={{ "--tone": tone(x.tier) }}>
            <span>{x.market}{track?.[x.fkey]?.state === "hit" && <span className="lv-tick" aria-label="Happened"><Icon name="check" size={14} /></span>}</span>
            <b>{pct(x.p)}{range(x.lo, x.hi) && <small className="k-fc-range"> ({range(x.lo, x.hi)})</small>}</b>
            <LineActions line={x} parent={{ ...f, team: f.team || fx.team }} testid={`${id}-lines`} />
          </li>)}
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
