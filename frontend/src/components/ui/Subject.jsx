// The shared spine (docs/redesign/v4/SHEET.md). Reported: "in insights when click on the player it
// shows up like this — this must look and feel like the player page of sorts."
//
// The sheet and the player page were already about 80% the same material — a head, one percentage,
// the reasons, the same ten games, the same ladder — drawn two different ways. That is a
// consistency fault, not an architecture one, so these are the blocks both surfaces are built from.
// `size` is the only thing that differs: "sheet" is the compact edition, "page" the full one.
//
// Every class here is new and prefixed v2-sh-/v2-ans-; nothing existing is renamed or removed, and
// the testids the sheet already published are carried through onto their new homes.
import { Link } from "react-router-dom";
import { pct, range } from "../../lib/copy";
import { useCombo } from "../../lib/combo";
import { SaveButton } from "../Actions";
import { Crest, PlayerAvatar } from "../Media";
import { posLabel } from "../Football";
import { TierBadge } from "./Marks";

const BADGE = { confirmed: "Confirmed starter", likely: "Likely lineup", unsure: "Lineup not sure", bench: "On the bench" };

// docs/56 calls `span` the quantity that separates a forecast from a count: how far this rung moves
// between the meanest defence in the league and the leakiest. It was computed on every line, used
// only as a hidden gate, and had no frontend reference at all -- the product's most distinctive
// number was invisible. This says it.
//
// Only the WIDTH and the POSITION are shown, never the two raw ends. The ends are the model's own
// output while the published likelihood has been calibrated and anchored, so printing them beside
// it produced a "leakiest" figure below the headline. A width and a position are scale-free and
// survive that difference; the ends stay in the record for the engine's own use.
const MIN_SPAN = 0.05;
function spanLine(f) {
  if (f.span == null) return null;                       // unknown is not the same as small
  const pts = Math.round(Math.abs(f.span) * 100);
  if (Math.abs(f.span) < MIN_SPAN) {
    return `Much the same against any defence in the league — about ${pts} point${pts === 1 ? "" : "s"} between the hardest and the easiest.`;
  }
  const pos = f.span_pos;
  const where = pos == null ? null
    : pos >= 0.67 ? "and tonight's is a kinder one than most"
    : pos <= 0.33 ? "and tonight's is a harder one than most"
    : "and tonight's is about average";
  return `The defence is worth about ${pts} points on this line${where ? `, ${where}` : ""}.`;
}

// Who this is about. A club line used to open a panel that never named the club and never linked to
// it; a match line named neither side. The subject is always named, and always reachable.
export function SubjectHead({ f, fx, size = "sheet", action, testid = "ui-subject-head" }) {
  const isMatch = !!f.stat?.startsWith("match_");
  const team = fx?.team;
  const name = f.player?.name || (isMatch ? (fx?.text || "Both teams") : team?.name || "");
  const to = f.player?.id ? `/player/${f.player.id}` : isMatch ? null : team?.id ? `/team/${team.id}` : null;
  const big = size === "page";
  const av = big ? 84 : 56;
  return (
    <header className={`v2-sh v2-sh--${size}`} data-testid={testid}>
      {/* attach_images pops image_url and emits `image`; reading the wrong one is why this wash
          has never rendered a crest on any build. */}
      {/* The wash is clipped by its own layer, not by the head. The head is a grid item in
          .k-sheet-body, and overflow:hidden on a grid item zeroes its automatic minimum size --
          measured, the row resolved to 22px against 107px of content and cut the portrait and the
          name in half. */}
      <span className="v2-sh-bg" aria-hidden="true">
        <span className={"v2-phead-wash" + (team?.image ? "" : " is-plain")}
              style={team?.image ? { backgroundImage: `url(${team.image})` } : undefined} />
      </span>
      <div className="v2-sh-row">
      <span className="v2-sh-face">
        {f.player ? <PlayerAvatar player={f.player} size={av} decorative={false} />
          : isMatch && fx?.team && fx?.opp
            ? <span className="k-fc-crests"><Crest team={fx.homeFirst ? fx.team : fx.opp} size={av * 0.62} /><Crest team={fx.homeFirst ? fx.opp : fx.team} size={av * 0.62} /></span>
            : <Crest team={team} size={av} decorative={false} />}
      </span>
      <div className="v2-sh-main">
        <h2 className="v2-sh-name" data-testid={`${testid}-name`}>
          {to ? <Link to={to} data-testid={`${testid}-player-link`}>{name}</Link> : name}
        </h2>
        <p className="v2-sh-meta">
          {!isMatch && team?.id && f.player && <Link to={`/team/${team.id}`} className="v2-club" onClick={(e) => e.stopPropagation()}><Crest team={team} size={big ? 20 : 18} /> {team.name}</Link>}
          {f.pos && <span className="v2-pos">{posLabel(f.pos)}</span>}
        </p>
        {(fx?.text || f.kickoff) && (
          <FixtureLine f={f} fx={fx} link={big} testid={testid} />
        )}
        {action ? <div className="v2-sh-act">{action}</div> : null}
      </div>
      </div>
    </header>
  );
}

function FixtureLine({ f, fx, link, testid }) {
  const at = f.team_iid != null && f.home_iid != null ? (f.team_iid === f.home_iid ? "Home" : "Away") : null;
  const body = (
    <>
      {at && <span className="v2-nextfx-at">{at}</span>}
      <span className="v2-sh-fx-t">{fx?.text}</span>
    </>
  );
  // In a modal a link out strands the reader mid-task, so the sheet states the fixture and the
  // page links it.
  return link && f.match_id
    ? <Link to={`/match/${f.match_id}`} className="v2-sh-fx" data-testid={`${testid}-fixture`}>{body}</Link>
    : <p className="v2-sh-fx" data-testid={`${testid}-fixture`}>{body}</p>;
}

// The claim, stated once. This replaces the sheet's head percentage, its "Chance he plays / If he
// plays" tiles and the standing paragraph explaining the bracket: measured, the headline appeared
// four times in one panel, and one tile read "Chance he plays 100%" beside "If he plays 84%".
export function AnswerBlock({ f, size = "sheet", testid = "ui-answer" }) {
  const rng = f.p_display ? null : range(f.lo, f.hi);
  const dep = f.p_usual == null || f.p_display ? null : Math.round((f.p - f.p_usual) * 100);
  const dir = dep == null ? "" : dep >= 0 ? "is-up" : "is-down";
  const lineup = f.scope === "player"
    ? (f.lineup_badge ? BADGE[f.lineup_badge] : f.lineup_confirmed ? "Confirmed starter" : null)
    : null;
  const plays = f.scope === "player" && f.p_play != null && f.p_play < 1 ? f.p_play : null;
  return (
    <section className={`v2-ans v2-ans--${size}`} style={{ "--tone": f.tier ? `var(--tier-${f.tier.toLowerCase()})` : "var(--text3)" }} data-testid={testid}>
      <div className="v2-ans-top">
        <span className="v2-ans-mkt">{f.market}</span>
        <TierBadge tier={f.tier} testid={`${testid}-tier`} />
      </div>
      <p className="v2-ans-p">
        <b className="k-fc-p" data-testid={`${testid}-p`}>{f.p_display || pct(f.p)}</b>
        {rng && <small className="k-fc-range" data-testid={`${testid}-range`}>{rng}</small>}
      </p>
      {f.p_usual != null && !f.p_display && (
        <p className="v2-ans-cmp" data-testid={`${testid}-usual`}>
          <span>Usual <b>{pct(f.p_usual)}</b></span>
          {dep != null && <b className={`v2-cmp-d ${dir}`}>{dep > 0 ? "+" : ""}{dep}</b>}
        </p>
      )}
      {/* What the opponent is actually worth here. */}
      {spanLine(f) && <p className="v2-ans-span" data-testid={`${testid}-span`}>{spanLine(f)}</p>}
      {(lineup || plays != null) && (
        <p className="v2-ans-lineup">
          {lineup}
          {plays != null && <> · he plays <b data-testid={`${testid}-pplay`}>{pct(plays)}</b> of the time</>}
        </p>
      )}
    </section>
  );
}

// The reasons. The one thing on the card a counting tool cannot produce, so it keeps its place.
export function WhyList({ reasons, max = 2, heading, testid = "ui-why" }) {
  const rs = (reasons || []).slice(0, max);
  if (!rs.length) return null;
  return (
    <section data-testid={testid}>
      {heading && <h3 className="k-sec">{heading}</h3>}
      <ul className="k-fs-why">{rs.map((r) => <li key={r}>{r}</li>)}</ul>
    </section>
  );
}

// Reported: a card leads with "4+ shots 70%" while the same player has "2+ shots 90%" underneath,
// and the reader could read the second but not keep it. Every rung carries its own fkey and
// /me/saved keys on fkey alone, so following one has always been possible -- it was simply never
// offered. These are the controls, on every rung, for players and for clubs alike.
//
// A rung carries only its own figures (fkey, stat, thr, market, p, lo, hi, tier). The combo needs
// match_iid, scope and the entity, which live on the card it came from, so the parent is merged
// underneath it. `id` is cleared on purpose: the parent's forecast id belongs to a different line.
export function LineActions({ line, parent, testid }) {
  const { has, toggle } = useCombo();
  if (!line?.fkey) return null;                       // a rung read off the ladder has no stored line to keep
  const full = { ...(parent || {}), ...line, id: line.id ?? null };
  const canAdd = full.match_iid != null && full.addable !== false && !full.from_ladder;
  const on = canAdd && has(line.fkey);
  return (
    <span className="v2-ll-act">
      <SaveButton fkey={line.fkey} />
      {canAdd && (
        <button type="button" className={"icon-btn icon-btn--sm" + (on ? " is-on" : "")} aria-pressed={on}
                aria-label={on ? `Remove ${line.market} from the combo` : `Add ${line.market} to the combo`}
                onClick={(e) => { e.stopPropagation(); toggle(full); }}
                data-testid={testid ? `${testid}-add-${line.fkey}` : undefined}>
          <span aria-hidden="true">{on ? "\u2212" : "+"}</span>
        </button>
      )}
    </span>
  );
}

// Every line for this subject, in ladder order rather than sorted by likelihood, so the shape of
// the night reads as a curve instead of a leaderboard. Promoted to sit under the run: measured,
// the sheet opened on 2+ at 84% while the player's best line sat below two screenfuls.
export function LadderList({ lines, current, parent, actions = false, heading = "All lines", testid = "ui-ladder" }) {
  const rows = (lines || []).filter((x) => x && x.market).slice().sort((a, b) => (a.thr ?? 0) - (b.thr ?? 0));
  if (rows.length < 2) return null;
  return (
    <section data-testid={testid}>
      {heading && <h3 className="k-sec">{heading}</h3>}
      <ul className={"k-fc-lines" + (actions ? " has-act" : "")}>
        {rows.map((x) => {
          const here = current != null && x.fkey === current;
          return (
            <li key={x.fkey || x.market} className={here ? "is-here" : undefined} aria-current={here ? "true" : undefined}
                style={{ "--tone": x.tier ? `var(--tier-${x.tier.toLowerCase()})` : "var(--text3)" }}>
              <span>{x.market}</span>
              <b>{pct(x.p)}{range(x.lo, x.hi) && <small className="k-fc-range"> ({range(x.lo, x.hi)})</small>}</b>
              {actions && <LineActions line={x} parent={parent} testid={testid} />}
            </li>
          );
        })}
      </ul>
    </section>
  );
}
