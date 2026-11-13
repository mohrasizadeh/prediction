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
import { fixtureOf, shortName } from "./ForecastCard";
import { useCombo } from "../../lib/combo";
import Icon from "../Icon";

const RH = 26;                                   // run strip height in px

// `thr` is a 0.5-style line, so 1.5 is the card talking about 2 or more.
const need = (thr) => Math.floor(Number(thr)) + 1;
const nounFor = (f, n) => (n === 1 ? f.noun?.[0] : f.noun?.[1]) || f.stat;
const lineWords = (f, n) => `${n}+ ${nounFor(f, n)}`;
// A row with no verb printed the market's whole label ("1+ goal in the match") beside the line
// control ("1+"), so the number showed twice -- and once the reader stepped the line it showed two
// DIFFERENT numbers, because the label was the lead rung's. The line control owns the number; the
// label is the market's words without it. Falls back to the stat key only when there is no label.
// The label is written for the lead rung, so "1+ goal" stepped to 2 needs its first word plural.
const bareNoun = (f, n) => {
  if (!f.market) return null;
  const w = f.market.replace(/^\s*\d+\+\s*/, "");
  if (n > 1 && need(f.thr) === 1) return w.replace(/^(\S*[^s\s])(?=\s|$)/, "$1s");
  if (n === 1 && need(f.thr) > 1) return w.replace(/^(\S+)s(?=\s|$)/, "$1");
  return w;
};

// The lineup words are about HIM and are facts that can be checked. "Confirmed" never said
// confirmed what; "Lineup not sure" never said who was unsure, and it was us.
//
// They are also SHORT, which is a layout constraint and not a style preference: this word shares a
// 70px column with the favourite star, and a word wider than the cell does not wrap or clip -- it
// paints straight over its neighbour, because the table clips only at its own outer edge. Measured
// at 1366px, "On the bench" crossed by 24px, "Usually starts" by 27px and "No team news yet" by
// 48px; the owner reported exactly that, as a star sitting on top of the word. Nothing is lost by
// the short form because `why` carries the full sentence one tap down.
//
// Budget: 54px of text (the cell is 70px, less a 9px dot and a 7px gap). Check a new word against
// scripts/collide.js before adding it -- six characters is about the limit at this size.
function lineupWords(f) {
  if (f.scope === "team") return { cls: "none", word: "Club line", why: "", sr: "No lineup question: this is a team line." };
  const b = f.lineup_badge;
  const rec = f.starts_recent != null && f.club_recent
    ? `He has started ${f.starts_recent} of his club's last ${f.club_recent}.` : "";
  if (b === "confirmed") return { cls: "confirmed", word: "Starting", why: "He is in the announced eleven." };
  if (b === "bench") return { cls: "bench", word: "Bench", why: "The eleven is out and he is not in it." };
  if (b === "likely") return { cls: "likely", word: "Regular", why: `No lineup yet. ${rec}` };
  if (b === "unsure") {
    // docs/63: which rule fired. A stated doubt and a thin start record are different facts, and
    // the honest word for one is a lie about the other.
    return f.lineup_why === "doubt"
      ? { cls: "doubt", word: "Doubtful", why: "He is carrying a stated doubt, so his record is not the answer here." }
      : { cls: "unsure", word: "Rotated", why: `No lineup yet. ${rec}` };
  }
  return { cls: "none", word: "No news", why: "We have no lineup for this club, and no record of starts we trust enough to read." };
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

function Why({ f, n, p, lo, hi, cleared, played, more = [], topMore = null }) {
  const lu = lineupWords(f);
  // The departure used to sit on the face of the row. v10 takes it off -- it is a "now and then"
  // read, and the row is a sentence plus its evidence -- but it is NOT dropped: it is the more
  // useful half of what the tier badge used to compress (docs/61), and this is where it lands.
  const dep = f.p_usual == null ? null : Math.round((f.p - f.p_usual) * 100);
  const clears = f.p_usual == null || f.lo == null || f.hi == null ? null : (f.lo > f.p_usual || f.hi < f.p_usual);
  const mine = f.scope === "player" ? "his" : "their";
  return (
    <div className="lk-whybox">
      <h4>Why {pct(p / 100)}</h4>
      <ul>
        <li>He has reached {lineWords(f, n)} in {cleared === played ? `all ${played}` : cleared} of his last {played} appearances.</li>
        {dep != null && (
          <li data-testid={`lk-why-dep-${f.id}`}>
            That is <b>{Math.abs(dep)} {Math.abs(dep) === 1 ? "point" : "points"}</b>{" "}
            {dep >= 0 ? "above" : "below"} {mine} usual <b>{pct(f.p_usual)}</b>
            {clears != null && <> &mdash; {clears ? "the likely range is clear of it" : "the likely range still reaches it"}</>}.
          </li>
        )}
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

// What happened, once there is an answer (docs/31 live, docs/73 settled).
//
// `track` is the live feed, counting while the match is on. `f.outcome` is the scored result, read
// off forecast_outcomes after the whistle. The row took `track` as a prop from the day it was
// extracted and never rendered it -- so the match page, which had shown this on the old card, went
// quiet about whether anything happened, and stayed quiet after full time as well.
//
// `actual` is shown when we have it, because "did not happen" and "2, where 3 were needed" are
// different amounts of information and we hold the second.
// A mark and the number (docs/redesign/v10 §1). "Happened -- 3" in a tinted pill was two things --
// a verdict and a count -- wrapped in furniture. The mark carries the verdict, "got 3" carries the
// number, and the mark means colour is never doing that job on its own.
function Result({ t, outcome, needed, id }) {
  if (outcome) {
    if (outcome.played === false) {
      return <span className="lv-chip" data-testid={`${id}-dnp`}>Did not play</span>;
    }
    const got = outcome.actual == null ? null : Math.round(outcome.actual * 10) / 10;
    return outcome.reached
      ? <span className="lv-chip lv-chip--hit" data-testid={`${id}-hit`}><Icon name="check" size={13} />
          {got == null ? "Happened" : `got ${got}`}</span>
      : <span className="lv-chip lv-chip--miss" data-testid={`${id}-missed`}><Icon name="x" size={13} />
          {got == null ? "Did not happen" : `got ${got}`}</span>;
  }
  if (!t || t.state === "unknown") return null;
  if (t.state === "hit") return <span className="lv-chip lv-chip--hit" data-testid={`${id}-hit`}><Icon name="check" size={14} />Happened</span>;
  if (t.state === "missed") return <span className="lv-chip lv-chip--miss" data-testid={`${id}-missed`}>Did not happen</span>;
  return <span className="lv-chip" data-testid={`${id}-live`}><span className="k-livedot" aria-hidden="true" />{t.current} of {t.needed} so far</span>;
}

// The market picker (docs/77). "+5 more markets" opened a list BELOW the row, so changing market
// meant leaving the card, reading a list and coming back. Everything happens on the card now: this
// names the market a reader is looking at -- which at a glance they could not tell before, the word
// being the second half of "2+ tackles" in body text -- and switching redraws the whole row.
//
// Ordered likeliest first, with each market's own number beside it, so the choice is informed. The
// percentages come from the server's `markets`, each one that stat's own lead rung.
function MarketPicker({ markets, stat, onPick, id, noun }) {
  const [open, setOpen] = useState(false);
  const box = useRef(null);
  useEffect(() => {
    if (!open) return undefined;
    const away = (e) => { if (box.current && !box.current.contains(e.target)) setOpen(false); };
    const esc = (e) => { if (e.key === "Escape") setOpen(false); };
    document.addEventListener("pointerdown", away);
    document.addEventListener("keydown", esc);
    return () => { document.removeEventListener("pointerdown", away); document.removeEventListener("keydown", esc); };
  }, [open]);
  const here = markets.find((m) => m.stat === stat) || markets[0];
  // Inside a sentence the control is the NOUN alone -- "tackles" -- because the line is already a
  // word of its own beside it, and "2+ tackles" there would say the number twice. Where the row
  // cannot be a sentence the full label stands on its own, as it always did.
  const label = noun || here?.market || here?.stat || "Market";
  if (markets.length < 2) return <span className="lk-mkt lk-mkt--one">{label}</span>;
  return (
    <span className="lk-mktwrap" ref={box}>
      <button type="button" className={"lk-mkt" + (open ? " on" : "")} aria-expanded={open}
              aria-haspopup="listbox" onClick={() => setOpen(!open)} data-testid={`lk-mkt-${id}`}>
        <em>{label}</em><Icon name="chevron-down" size={13} />
      </button>
      {open && (
        <span className="lk-mktlist" role="listbox" data-testid={`lk-mktlist-${id}`}>
          <span className="lk-mkthd">Market · likeliest first</span>
          {markets.map((m) => (
            <button key={m.stat} type="button" role="option" aria-selected={m.stat === stat}
                    className={m.stat === stat ? "on" : ""}
                    onClick={() => { onPick(m.stat); setOpen(false); }}
                    data-testid={`lk-mktopt-${id}-${m.stat}`}>
              {m.market || m.stat}<em>{pct(m.p)}</em>
            </button>
          ))}
        </span>
      )}
    </span>
  );
}

// The line, as a stepper rather than a fixed row of chips.
//
// It walks the rungs the engine actually answered. It does NOT run past them: a rung we hold no
// forecast for has no number, no range and no grade, and inventing one on a page about uncertainty
// is the single thing this product must not do. The ends are disabled rather than hidden, so the
// control says where the answers stop instead of pretending the line cannot move.
function Stepper({ rows, cur, onPick, noun, id }) {
  const i = rows.findIndex((r) => r.n === cur);
  const go = (d) => { const r = rows[i + d]; if (r) onPick(r.n); };
  const lo = i <= 0, hi = i < 0 || i >= rows.length - 1;
  return (
    <span className="lk-step" role="group" aria-label={`How many ${noun}`}>
      <button type="button" onClick={() => go(-1)} disabled={lo} aria-label={`Fewer ${noun}`}
              title={lo ? "No lower line for this market" : ""} data-testid={`lk-step-down-${id}`}>&minus;</button>
      <b data-testid={`lk-step-n-${id}`}>{cur}+</b>
      <button type="button" onClick={() => go(1)} disabled={hi} aria-label={`More ${noun}`}
              title={hi ? "No higher line for this market" : ""} data-testid={`lk-step-up-${id}`}>+</button>
    </span>
  );
}

// The LINE, as a list of the rungs with their own percentages.
//
// The stepper beside it does the same job by walking one rung at a time, and on a wide screen that
// is the better control: it is three targets and shows the consequence immediately. On a phone the
// line is set as a WORD inside the sentence (docs/redesign/v10 §3), and a word cannot be stepped --
// so there it opens this instead, which is also the more informative of the two: it shows the shape
// of the fall, 94 / 64 / 26, rather than one rung at a time.
//
// Both are rendered and the stylesheet shows one per width. That is duplicated markup on purpose:
// the alternative is a single control that is a stepper at one width and a menu at the other, which
// is two interaction models wearing one set of ARIA.
function LinePicker({ rows, cur, onPick, noun, id }) {
  const [open, setOpen] = useState(false);
  const box = useRef(null);
  useEffect(() => {
    if (!open) return undefined;
    const away = (e) => { if (box.current && !box.current.contains(e.target)) setOpen(false); };
    const esc = (e) => { if (e.key === "Escape") setOpen(false); };
    document.addEventListener("pointerdown", away);
    document.addEventListener("keydown", esc);
    return () => { document.removeEventListener("pointerdown", away); document.removeEventListener("keydown", esc); };
  }, [open]);
  if (rows.length < 2) return <span className="lk-tk lk-tk--one">{cur}+</span>;
  return (
    <span className="lk-tkwrap" ref={box}>
      <button type="button" className={"lk-tk" + (open ? " on" : "")} aria-expanded={open}
              aria-haspopup="listbox" aria-label={`How many ${noun}`}
              onClick={() => setOpen(!open)} data-testid={`lk-line-${id}`}>
        {cur}+<Icon name="chevron-down" size={11} />
      </button>
      {open && (
        <span className="lk-tklist" role="listbox" data-testid={`lk-linelist-${id}`}>
          <span className="lk-mkthd">The line</span>
          {rows.map((r) => (
            <button key={r.n} type="button" role="option" aria-selected={r.n === cur}
                    className={r.n === cur ? "on" : ""}
                    onClick={() => { onPick(r.n); setOpen(false); }}
                    data-testid={`lk-lineopt-${id}-${r.n}`}>
              {r.n}+ {noun}<em>{pct(r.p)}</em>
            </button>
          ))}
        </span>
      )}
    </span>
  );
}

export function ForecastRow({ f, open, onToggle, floor, extras = true, teams, homeIid, track }) {
  // Which market the reader is looking at, and which rung of it. Both start at what the server led
  // with and both are the reader's from then on.
  const [stat, setStat] = useState(null);
  const [pick, setPick] = useState(null);
  const { has, toggle } = useCombo();
  // Most likely's feed carries `team` and `opp` on every row; a match page's forecasts do not,
  // and the card resolved them from a teams map it was handed. Dropping that map is what left
  // this row drawing an empty shield and the bare word "vs" with nobody after it.
  const fx = fixtureOf(f, teams, homeIid);
  // Every market this subject holds, each one complete enough to redraw the row -- its own ladder,
  // its own band and grade per rung, and its own ten-game strip (docs/77). A feed that predates
  // `markets` still works: the lead forecast stands in as the only market.
  const markets = useMemo(() => (f.markets?.length ? f.markets : [f]), [f]);
  // `cur` is the forecast on screen. Everything below reads from it, not from `f` -- reading the
  // lead line while showing another market is how a card ends up contradicting itself.
  //
  // ON THE CARD'S OWN MARKET, `f` WINS. `f` IS that market -- group_cards builds the card from the
  // lead forecast and then lists the same forecast in `markets` -- so the two agree, and where they
  // agree this changes nothing. Where they could ever disagree, `f` is the copy the feed ranked,
  // sorted, filtered and counted on, and the row must not quietly show a different number from the
  // one the list used to place it. Caught by a fixture that set `p` on the row without updating
  // its `markets`: three rows that should have read 64%, 91% and 41% all read 64%.
  const cur = useMemo(() => {
    const st = stat ?? f.stat;
    return st === f.stat ? f : markets.find((m) => m.stat === st) || f;
  }, [markets, stat, f]);
  const lad = useMemo(() => ladderOf(cur), [cur]);
  const chosen = need(cur.thr);
  const n = pick ?? chosen;
  const rung = lad.find((r) => r.n === n);
  const p = Math.round(100 * (n === chosen ? cur.p : rung?.p ?? cur.p));
  // REPORTED: stepping the line moved the percentage and left the range where it was, so the card
  // showed one rung's number beside another rung's spread. It fell back to the LEAD line's band
  // whenever the rung it stepped to had none stored. A rung with no band has no range -- say
  // nothing rather than something borrowed.
  const band = n === chosen ? [cur.lo, cur.hi] : rung?.band || null;
  const lo = band?.[0] == null ? null : Math.round(100 * band[0]);
  const hi = band?.[1] == null ? null : Math.round(100 * band[1]);
  // pct() is the one place a likelihood becomes words (lib/copy), floor included -- a second
  // rounding written out by hand here is how two places on one screen start to disagree.
  const under = p < Math.round(floor * 100) ? pct(floor) : null;
  const lu = lineupWords(cur);
  // the strip is per market: tackles and shots are different ten games
  const known = (cur.run || []).filter((g) => g && g.v != null);
  const cleared = known.filter((g) => g.v >= n).length;
  // A match total ("1+ goal in the match") is stored on the home club, so its row said "Team 0 1+ goal
  // in the match" -- a claim about one club that is really about both. Its subject is the fixture, as
  // ForecastCard's Who already draws it (v10 §5 left this sentence open; the backend sends no verb).
  // With the fixture as subject "in the match" says it twice, and its width cut the fixture to "Team 0 v Te…".
  const matchLine = !f.player && (cur.stat || f.stat || "").startsWith("match_") && !!fx.opp;
  const who = f.player?.name || (matchLine ? fx.text : fx.team?.name);
  const res = n === chosen ? (cur.outcome || f.outcome || null) : null;
  const tk = n === chosen ? track?.[cur.fkey] : null;
  const words = lineWords(cur, n);
  // A settled match showed its KICK-OFF time, so a game played this morning read as one starting
  // at 09:00. The clock is only news before the whistle; afterwards the news is that it is over.
  const done = f.status === "final";
  const ko = done ? "FT" : (f.kickoff ? utc(f.kickoff).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", hour12: false }) : "");
  // The four things ForecastCard carried and this row did not. Same fields, same arithmetic and
  // the same words as the card, so a reader who learnt them there reads them here unchanged.
  const more = [...(f.more_lines || [])].sort((a, b) => b.p - a.p);
  // Named, not teased: a safer line behind "+N more lines" used to be invisible behind a smaller
  // number on the face of the card.
  const topMore = more.length && f.p != null && more[0].p > f.p ? more[0] : null;
  // Changing market changes which rung is the lead one, so a line the reader stepped to in the
  // old market is meaningless in the new one. Reset it with the market rather than carry it over.
  const pickMarket = (st) => { setStat(st); setPick(null); };
  // The grade of the rung on screen: the engine's per-rung tier, or the line's own where this is
  // the rung the forecast is about.
  // The backend keys the ladder with "%g", so 1.5 stays "1.5" and 2.0 becomes "2" -- which is what
  // String() gives for the Numbers ladderOf() parsed them back into.
  const rungTier = (n === chosen && cur.tier) || (cur.ladder_tier || {})[String(rung?.thr)] || null;
  // "vs" with nobody after it is what the match page reported, and six more screens now draw this
  // row from feeds that do not all carry an opponent. No name, no preposition.
  const vs = fx.opp?.name ? `${fx.homeFirst ? "vs" : "at"} ${fx.opp.name}` : "";
  // The sentence the card is about (docs/redesign/v10 §1). The verb belongs to the market and
  // arrives with it, so changing the market rewrites the claim rather than leaving "Linday makes
  // 2+ shots" behind. Where a market cannot be a sentence -- `match_goals` has the match as its
  // subject, and an admin label from copy.market_labels will not compose -- the backend sends no
  // verb and the row falls back to printing the plain label.
  const verb = cur.verb || null;
  return (
    <>
      <tr className={`${open ? "lk-open " : ""}${under ? "lk-under" : ""}`} data-testid={`lk-row-${f.id}`}>
        <td className="lk-cell-say">
          <span className="lk-say">
            {f.player ? (
              <span className="lk-ava">
                <PlayerAvatar player={f.player} size={34} />
                <span className="lk-ava-cr"><Crest team={fx.team} size={14} /></span>
              </span>
            ) : (
              <span className="lk-ava lk-ava--club"><Crest team={fx.team} size={34} /></span>
            )}
            {matchLine ? <span className="lk-name" title={who}>{who}</span>
              : <Link className="lk-name" to={f.player ? `/player/${f.player.id}` : `/team/${fx.team?.id}`} title={who}>{shortName(who)}</Link>}
            {/* The claim -- verb, line, market. One flex line with the name on a wide screen (it
                dissolves there); on a phone it is the card's second line, full width under the
                face and the figure (docs/redesign/v10 §3), so it gets a box of its own. */}
            <span className="lk-claim">
              {verb ? <span className="lk-verb">{verb}</span> : null}
              {/* one control, two shapes: a stepper where there is room, a word where there is not */}
              <span className="lk-onwide"><Stepper rows={lad} cur={n} onPick={setPick} noun={nounFor(cur, 2)} id={f.id} /></span>
              <span className="lk-onnarrow"><LinePicker rows={lad} cur={n} onPick={setPick} noun={nounFor(cur, 2)} id={f.id} /></span>
              <MarketPicker markets={markets} stat={cur.stat} onPick={pickMarket} id={f.id} noun={verb ? nounFor(cur, n) : matchLine ? bareNoun(cur, n)?.replace(/\s+in the match$/, "") : bareNoun(cur, n)} />
            </span>
          </span>
          {/* the fixture, for the phone, where its own column is folded away */}
          <span className="lk-fx-inline">{vs} {ko}</span>
        </td>
        <td className="lk-cell-run">
          <span className="lk-evlabel">Last 10 &middot; did {f.scope === "team" ? "they" : "he"} reach it</span>
          <Run games={cur.run} n={n} />
        </td>
        <td className="lk-cell-res">
          {(res || tk) && <Result t={tk} outcome={res} needed={n} id={`lk-${f.id}`} />}
        </td>
        <td className="lk-cell-lk lk-lk">
          {/* The chance, and only the chance. The range is a "now and then" read and Why already
              closes on it in full -- keeping it here made every row 100px instead of 70px for a
              number almost nobody acts on in a list. */}
          <span className="lk-figure">{p}<u>%</u></span>
          {under && <span className="lk-underw">Below the {under} bar &mdash; not listed by default</span>}
        </td>
        <td className="lk-cell-tier">
          {extras && rungTier && <TierBadge tier={rungTier} testid={`lk-tier-${f.id}`} />}
        </td>
        <td className="lk-cell-why">
          <button type="button" className="lk-why" aria-expanded={open} onClick={onToggle} data-testid={`lk-why-${f.id}`}>
            Why<span className="sr-only"> {who}, {words}, {p} percent</span><Icon name="chevron-down" size={12} />
          </button>
        </td>
        <td className="lk-cell-lu">
          <span className={`lk-lu is-${lu.cls}`} title={lu.why}>
            {lu.cls !== "none" && <s />}{lu.word}
            {lu.sr && <span className="sr-only">{lu.sr}</span>}
          </span>
        </td>
        <td className="lk-cell-act">
          <span className="lk-acts">
            {extras && cur.fkey && <SaveButton fkey={cur.fkey} />}
            {extras && cur.fkey && cur.addable !== false && (
              <button type="button" className={"lk-add" + (has?.(cur.fkey) ? " on" : "")}
                      aria-pressed={!!has?.(cur.fkey)}
                      aria-label={`${has?.(cur.fkey) ? "Remove" : "Add"} ${who} ${cur.market} ${has?.(cur.fkey) ? "from" : "to"} your combo`}
                      onClick={() => toggle({ ...cur, player: f.player, team: f.team || fx.team })} data-testid={`lk-add-${f.id}`}>
                <Icon name={has?.(cur.fkey) ? "check" : "plus"} size={16} />
              </button>
            )}
          </span>
        </td>
      </tr>
      {open && (
        <tr className="lk-whyrow"><td colSpan={8}>
          <Why f={cur} n={n} p={p} lo={lo} hi={hi} cleared={cleared} played={known.length} more={more} topMore={topMore} />
        </td></tr>
      )}
    </>
  );
}
