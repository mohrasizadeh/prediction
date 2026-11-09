// ForecastRow -- the one way this product draws a forecast in a list.
//
// This lived inside pages/Likely.jsx, which is why the match page, Insights, the player page and
// the club page all went on drawing the older card instead: the agreed presentation was never
// shared, so there was nothing for them to reach for. Everything below is moved verbatim from
// that page -- same markup, same `lk-` classes, same likely.css, so Most likely renders byte for
// byte as it did -- plus the four things ForecastCard carried and the row did not: the tier, the
// departure from usual, the other lines this subject holds, and the save control.
//
// It renders a <tr>, so a caller supplies the <table>.
import { useEffect, useMemo, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { pct } from "../../lib/copy";
import { utc } from "../../lib/time";
import { Crest, PlayerAvatar } from "../Media";
import { SaveButton } from "../Actions";
import { TierBadge } from "./Marks";
import { LineActions } from "./Subject";
import { fixtureOf } from "./ForecastCard";
import { useCombo } from "../../lib/combo";
import Icon from "../Icon";

const LO = 50;                                   // the bar's fixed scale: every row, every filter
const RH = 26;                                   // run strip height in px
const POS = { G: "GK", D: "DEF", M: "MID", F: "FWD" };

// `thr` is a 0.5-style line, so 1.5 is the card talking about 2 or more.
const need = (thr) => Math.floor(Number(thr)) + 1;
const nounFor = (f, n) => (n === 1 ? f.noun?.[0] : f.noun?.[1]) || f.stat;
const lineWords = (f, n) => `${n}+ ${nounFor(f, n)}`;

// The lineup words are about HIM and are facts that can be checked. "Confirmed" never said
// confirmed what; "Lineup not sure" never said who was unsure, and it was us.
function lineupWords(f) {
  if (f.scope === "team") return { cls: "none", word: "Club line", why: "", sr: "No lineup question: this is a team line." };
  const b = f.lineup_badge;
  const rec = f.starts_recent != null && f.club_recent
    ? `He has started ${f.starts_recent} of his club's last ${f.club_recent}.` : "";
  if (b === "confirmed") return { cls: "confirmed", word: "Starting", why: "He is in the announced eleven." };
  if (b === "bench") return { cls: "bench", word: "On the bench", why: "The eleven is out and he is not in it." };
  if (b === "likely") return { cls: "likely", word: "Usually starts", why: `No lineup yet. ${rec}` };
  if (b === "unsure") {
    // docs/63: which rule fired. A stated doubt and a thin start record are different facts, and
    // the honest word for one is a lie about the other.
    return f.lineup_why === "doubt"
      ? { cls: "doubt", word: "Doubtful", why: "He is carrying a stated doubt, so his record is not the answer here." }
      : { cls: "unsure", word: "Rotated", why: `No lineup yet. ${rec}` };
  }
  return { cls: "none", word: "No team news yet", why: "We have no lineup for this club, and no record of starts we trust enough to read." };
}

// The ladder the engine already stores, trimmed to the rungs worth offering: up to one beyond his
// best in the last ten. A fixed 1..6 would print "6+ shots, 1%" down the page, which is dead ink
// and makes the control feel broken.
function ladderOf(f) {
  const lad = f.ladder || {};
  const best = Math.max(0, ...(f.run || []).map((g) => (g && g.v != null ? g.v : 0)));
  const picked = need(f.thr);
  return Object.keys(lad)
    .map((k) => ({ thr: Number(k), n: need(k), p: lad[k], band: (f.ladder_band || {})[k] }))
    .filter((r) => Number.isFinite(r.p) && (r.n <= best + 1 || r.n === picked))
    .sort((a, b) => a.n - b.n);
}

function Bar({ p, lo, hi, under }) {
  const x = Math.max(0, ((lo - LO) / (100 - LO)) * 100);
  const w = Math.max(0, ((hi - lo) / (100 - LO)) * 100);
  const span = hi - lo;
  const judge = span <= 10 ? "Narrow, so this number is well settled."
    : span >= 18 ? "Wide, so this number is less settled than most on this list." : "";
  return (
    <span className="lk-band" role="img" aria-label={`${p} percent. Likely range ${lo} to ${hi} per cent. ${judge}`}>
      <i style={{ left: `${x.toFixed(2)}%`, width: `${w.toFixed(2)}%` }} />
      {under && <span className="lk-underw">Below the {under} bar — not listed by default</span>}
    </span>
  );
}

// Nothing is drawn over a bar. The level is carried by each bar's own two-tone split, which lands
// at the same height across the strip; the dashed rule sits BEHIND the bars, so it shows only in
// the gaps and above a bar that fell short. Drawn in front it crossed the fill and read as a
// strikethrough.
function Run({ games, n }) {
  const known = (games || []).filter((g) => g && g.v != null);
  if (known.length < 3) return null;              // too few games to be evidence of anything
  const mx = Math.max(n, ...known.map((g) => g.v));
  const y = Math.max(1, Math.round((n / mx) * RH));
  const cleared = known.filter((g) => g.v >= n).length;
  return (
    <span className="lk-runwrap">
      <span className="lk-runbox">
        <span className="lk-need" style={{ bottom: y - 1 }} aria-hidden="true">{n}</span>
        <span className="lk-run" role="img" aria-label={`He reached ${n} or more in ${cleared} of his last ${known.length}.`}>
          <span className="lk-rule" style={{ bottom: y }} aria-hidden="true" />
          {known.map((g, i) => {
            const h = Math.max(2, Math.round((g.v / mx) * RH));
            const hit = g.v >= n;
            return <i key={i} style={{ height: h, background: hit
              ? `linear-gradient(to top, var(--brand) 0 ${Math.min(h, y)}px, var(--tier-strong) ${Math.min(h, y)}px 100%)`
              : "var(--lk-rule)" }} />;
          })}
        </span>
      </span>
      <span className="lk-data lk-cnt lk-dim"><b>{cleared}</b> of {known.length}</span>
    </span>
  );
}

function Steps({ rows, cur, onPick, label }) {
  const el = useRef(null);
  // The fade means "there is more to the right", so it is set by MEASURING overflow. Counting
  // chips fades a chip that is the last one, which is a lie about there being more.
  useEffect(() => {
    const node = el.current;
    if (!node) return undefined;
    const fit = () => node.classList.toggle("lk-more", node.scrollWidth - node.clientWidth - node.scrollLeft > 2);
    fit();
    node.addEventListener("scroll", fit, { passive: true });
    window.addEventListener("resize", fit);
    return () => { node.removeEventListener("scroll", fit); window.removeEventListener("resize", fit); };
  }, [rows.length]);
  if (rows.length < 2) return null;
  return (
    <span className="lk-steps" ref={el} role="radiogroup" aria-label={label}>
      {rows.map((r) => (
        <button key={r.n} type="button" role="radio" aria-checked={r.n === cur} className="lk-step"
          onClick={() => onPick(r.n)} data-testid={`lk-step-${r.n}`}>{r.n}+</button>
      ))}
    </span>
  );
}

function Why({ f, n, p, lo, hi, cleared, played, more = [], topMore = null }) {
  const lu = lineupWords(f);
  return (
    <div className="lk-whybox">
      <h4>Why {pct(p / 100)}</h4>
      <ul>
        <li>He has reached {lineWords(f, n)} in {cleared === played ? `all ${played}` : cleared} of his last {played} appearances.</li>
        {lu.why && <li>{lu.why}</li>}
        {(f.reasons || []).slice(0, 2).map((r, i) => <li key={i}>{r}</li>)}
        {topMore?.market && (
          <li data-testid={`lk-alt-${f.id}`}>
            {f.scope === "player" ? "His" : "Their"} likeliest line here is <b>{topMore.market}</b> at <b>{pct(topMore.p)}</b>.
          </li>
        )}
        {more.length > 0 && (
          <li data-testid={`lk-more-${f.id}`}>
            {more.length} other line{more.length === 1 ? "" : "s"} on this subject in this match.
          </li>
        )}
      </ul>
      <p>
        Likely range {lo}–{hi}%. That is where the answer most likely sits; we land on one number and
        this is the spread around it. We have not yet measured that spread against results — the{" "}
        <Link to="/track-record">Track Record</Link> page will say when we have.
      </p>
    </div>
  );
}

export function ForecastRow({ f, open, onToggle, floor, extras = true, teams, homeIid, track }) {
  const [pick, setPick] = useState(null);
  const [lines, setLines] = useState(false);
  const { has, toggle } = useCombo();
  // Most likely's feed carries `team` and `opp` on every row; a match page's forecasts do not,
  // and the card resolved them from a teams map it was handed. Dropping that map is what left
  // this row drawing an empty shield and the bare word "vs" with nobody after it.
  const fx = fixtureOf(f, teams, homeIid);
  const lad = useMemo(() => ladderOf(f), [f]);
  const chosen = need(f.thr);
  const n = pick ?? chosen;
  const rung = lad.find((r) => r.n === n);
  const p = Math.round(100 * (n === chosen ? f.p : rung?.p ?? f.p));
  const band = n === chosen ? [f.lo, f.hi] : rung?.band || [f.lo, f.hi];
  const lo = Math.round(100 * band[0]);
  const hi = Math.round(100 * band[1]);
  // pct() is the one place a likelihood becomes words (lib/copy), floor included -- a second
  // rounding written out by hand here is how two places on one screen start to disagree.
  const under = p < Math.round(floor * 100) ? pct(floor) : null;
  const lu = lineupWords(f);
  const known = (f.run || []).filter((g) => g && g.v != null);
  const cleared = known.filter((g) => g.v >= n).length;
  const who = f.player?.name || fx.team?.name;
  const words = lineWords(f, n);
  const pos = POS[f.pos] || f.pos;
  const ko = f.kickoff ? utc(f.kickoff).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", hour12: false }) : "";
  // The four things ForecastCard carried and this row did not. Same fields, same arithmetic and
  // the same words as the card, so a reader who learnt them there reads them here unchanged.
  const dep = f.p_usual == null ? null : Math.round((f.p - f.p_usual) * 100);
  const dir = f.p_usual == null ? "" : f.p >= f.p_usual ? "is-up" : "is-down";
  const clears = f.p_usual == null || f.lo == null || f.hi == null ? null : (f.lo > f.p_usual || f.hi < f.p_usual);
  const more = [...(f.more_lines || [])].sort((a, b) => b.p - a.p);
  // Named, not teased: a safer line behind "+N more lines" used to be invisible behind a smaller
  // number on the face of the card.
  const topMore = more.length && f.p != null && more[0].p > f.p ? more[0] : null;
  const mine = f.scope === "player" ? "his" : "their";
  const vs = `${fx.homeFirst ? "vs" : "at"} ${fx.opp?.name || ""}`;
  return (
    <>
      <tr className={`${open ? "lk-open " : ""}${under ? "lk-under" : ""}`} data-testid={`lk-row-${f.id}`}>
        <td className="lk-cell-who">
          <span className="lk-who">
            {/* A team line has no player, so it wears its crest at full size. Giving it a round
                player avatar with its own crest pinned to the corner said "this is a person at
                this club" about a club. */}
            {f.player ? (
              <span className="lk-ava">
                <PlayerAvatar player={f.player} size={38} />
                <span className="lk-ava-cr"><Crest team={fx.team} size={15} /></span>
              </span>
            ) : (
              <span className="lk-ava lk-ava--club"><Crest team={fx.team} size={38} /></span>
            )}
            <Link className="lk-name" to={f.player ? `/player/${f.player.id}` : `/team/${fx.team?.id}`}>{who}</Link>
            {pos && <span className="lk-pos">{pos}</span>}
          </span>
        </td>
        <td className="lk-cell-fx lk-fx">{vs}<small>{ko}</small></td>
        <td className="lk-cell-mk">
          <span className="lk-line">
            <span className="lk-claim">
              {pos && <span className="lk-pos-inline">{pos} · </span>}{words}
              <span className="lk-fx-inline"> · {vs} {ko}</span>
              {/* The ladder below steps the LINE (2+ shots to 3+); this steps the MARKET (shots to
                  tackles to fouls). It sits with the market words because that is what it changes,
                  and because the actions cell cannot hold a fourth control without clipping. */}
              {extras && more.length > 0 && (
                <button type="button" className="lk-morebtn" aria-expanded={lines}
                        onClick={() => setLines(!lines)} data-testid={`lk-more-btn-${f.id}`}>
                  {lines ? "Fewer markets" : `+${more.length} more market${more.length === 1 ? "" : "s"}`}
                </button>
              )}
            </span>
            {/* Only on the rung the forecast is actually about: `p_usual` is that rung's usual, so
                printing it beside a rung the reader stepped to would compare two different lines. */}
            {extras && n === chosen && dep != null && (
              <span className={"lk-dep " + dir} data-testid={`lk-dep-${f.id}`}>
                <i aria-hidden="true">{dep > 0 ? "\u25b2" : dep < 0 ? "\u25bc" : "\u2013"}</i>
                <b>{Math.abs(dep)} {Math.abs(dep) === 1 ? "point" : "points"}</b> {dep >= 0 ? "above" : "below"} {mine} usual <b>{pct(f.p_usual)}</b>
                {clears != null && <> &middot; {clears ? "clear of it" : "the likely range still reaches it"}</>}
              </span>
            )}
            <span className="lk-steps-desk"><Steps rows={lad} cur={n} onPick={setPick} label={`How many ${nounFor(f, 2)}`} /></span>
          </span>
        </td>
        <td className="lk-cell-lk lk-lk">
          <span className="lk-lk-top"><span className="lk-figure">{p}<u>%</u></span></span>
          <Bar p={p} lo={lo} hi={hi} under={under} />
          <span className="lk-data lk-rg lk-dim">{lo}–{hi}%</span>
          {/* Under the figure, not beside it. `.lk-lk-top` is a right-flushed flex, so a badge
              sharing that line pushes the number left by the badge's own width -- and the badge's
              width is the length of the word, so "Solid" and "Watch" put the figures of two rows
              at different x. Measured before this: 651 against 639. The tier still grades the
              number; it just does it from the line below. */}
          {extras && n === chosen && f.tier && (
            <span className="lk-tiercell"><TierBadge tier={f.tier} testid={`lk-tier-${f.id}`} /></span>
          )}
        </td>
        <td className="lk-cell-run"><Run games={f.run} n={n} /></td>
        <td className="lk-cell-lu">
          {/* on a phone the ladder gets its own band here, under the evidence: beside the market
              words its width changed with the number of rungs, and every object after it moved. */}
          <span className="lk-steps-phone"><Steps rows={lad} cur={n} onPick={setPick} label={`How many ${nounFor(f, 2)}`} /></span>
          <span className="lk-lucell">
            <span className={`lk-lu is-${lu.cls}`} title={lu.why}>
              {lu.cls !== "none" && <s />}{lu.word}
              {lu.sr && <span className="sr-only">{lu.sr}</span>}
            </span>
            <span className="lk-acts">
            <button type="button" className="lk-why" aria-expanded={open} onClick={onToggle} data-testid={`lk-why-${f.id}`}>
              Why<span className="sr-only"> {who}, {words}, {p} percent</span> {open ? "▴" : "▾"}
            </button>
            {/* The card's two controls, which this row lost when it was extracted: follow the
                line, and put it in a combo. A row that can be read but not kept is a worse row
                than the card it replaced. */}
            {extras && f.fkey && <SaveButton fkey={f.fkey} />}
            {extras && f.fkey && f.addable !== false && (
              <button type="button" className={"lk-add" + (has?.(f.fkey) ? " on" : "")}
                      aria-pressed={!!has?.(f.fkey)}
                      aria-label={`${has?.(f.fkey) ? "Remove" : "Add"} ${who} ${f.market} ${has?.(f.fkey) ? "from" : "to"} your combo`}
                      onClick={() => toggle({ ...f, team: f.team || fx.team })} data-testid={`lk-add-${f.id}`}>
                <Icon name={has?.(f.fkey) ? "check" : "plus"} size={16} />
              </button>
            )}
            </span>
          </span>
        </td>
      </tr>
      {lines && (
        <tr className="lk-whyrow lk-linesrow"><td colSpan={6}>
          <ul className="k-fc-lines has-act" data-testid={`lk-lines-${f.id}`}>
            {more.map((x) => (
              <li key={x.fkey}>
                <span>{x.market}</span>
                <b>{pct(x.p)}</b>
                <LineActions line={x} parent={{ ...f, team: f.team || fx.team }} testid={`lk-lines-${f.id}`} />
              </li>
            ))}
          </ul>
        </td></tr>
      )}
      {open && (
        <tr className="lk-whyrow"><td colSpan={6}>
          <Why f={f} n={n} p={p} lo={lo} hi={hi} cleared={cleared} played={known.length} more={more} topMore={topMore} />
        </td></tr>
      )}
    </>
  );
}
