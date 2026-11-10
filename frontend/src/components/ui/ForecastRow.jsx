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

// What happened, once there is an answer (docs/31 live, docs/73 settled).
//
// `track` is the live feed, counting while the match is on. `f.outcome` is the scored result, read
// off forecast_outcomes after the whistle. The row took `track` as a prop from the day it was
// extracted and never rendered it -- so the match page, which had shown this on the old card, went
// quiet about whether anything happened, and stayed quiet after full time as well.
//
// `actual` is shown when we have it, because "did not happen" and "2, where 3 were needed" are
// different amounts of information and we hold the second.
function Result({ t, outcome, needed, id }) {
  if (outcome) {
    if (outcome.played === false) {
      return <span className="lv-chip" data-testid={`${id}-dnp`}>Did not play</span>;
    }
    const got = outcome.actual == null ? null : Math.round(outcome.actual * 10) / 10;
    return outcome.reached
      ? <span className="lv-chip lv-chip--hit" data-testid={`${id}-hit`}><Icon name="check" size={14} />
          Happened{got == null ? "" : ` \u2014 ${got}`}</span>
      : <span className="lv-chip lv-chip--miss" data-testid={`${id}-missed`}>
          Did not happen{got == null ? "" : ` \u2014 ${got} of ${needed}`}</span>;
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
function MarketPicker({ markets, stat, onPick, id }) {
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
  const label = here?.market || here?.stat || "Market";
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
  const cur = useMemo(() => markets.find((m) => m.stat === (stat ?? f.stat)) || f, [markets, stat, f]);
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
  const who = f.player?.name || fx.team?.name;
  const res = n === chosen ? (cur.outcome || f.outcome || null) : null;
  const tk = n === chosen ? track?.[cur.fkey] : null;
  const words = lineWords(cur, n);
  const pos = POS[f.pos] || f.pos;
  // A settled match showed its KICK-OFF time, so a game played this morning read as one starting
  // at 09:00. The clock is only news before the whistle; afterwards the news is that it is over.
  const done = f.status === "final";
  const ko = done ? "FT" : (f.kickoff ? utc(f.kickoff).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", hour12: false }) : "");
  // The four things ForecastCard carried and this row did not. Same fields, same arithmetic and
  // the same words as the card, so a reader who learnt them there reads them here unchanged.
  const dep = cur.p_usual == null ? null : Math.round((cur.p - cur.p_usual) * 100);
  const dir = cur.p_usual == null ? "" : cur.p >= cur.p_usual ? "is-up" : "is-down";
  const clears = cur.p_usual == null || cur.lo == null || cur.hi == null ? null : (cur.lo > cur.p_usual || cur.hi < cur.p_usual);
  const more = [...(f.more_lines || [])].sort((a, b) => b.p - a.p);
  // Named, not teased: a safer line behind "+N more lines" used to be invisible behind a smaller
  // number on the face of the card.
  const topMore = more.length && f.p != null && more[0].p > f.p ? more[0] : null;
  const mine = f.scope === "player" ? "his" : "their";
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
            <Link className="lk-name" to={f.player ? `/player/${f.player.id}` : `/team/${fx.team?.id}`} title={who}>{shortName(who)}</Link>
            {pos && <span className="lk-pos">{pos}</span>}
          </span>
        </td>
        <td className="lk-cell-fx lk-fx">{vs}<small>{ko}</small></td>
        <td className="lk-cell-mk">
          <span className="lk-line">
            <span className="lk-q">
              <MarketPicker markets={markets} stat={cur.stat} onPick={pickMarket} id={f.id} />
              <Stepper rows={lad} cur={n} onPick={setPick} noun={nounFor(cur, 2)} id={f.id} />
            </span>
            {/* the fixture, for the phone, where the fixture cell is folded away */}
            <span className="lk-fx-inline">{vs} {ko}</span>
            {/* Only on the rung the forecast is actually about: `p_usual` is that rung's usual, so
                printing it beside a rung the reader stepped to would compare two different lines. */}
            {extras && n === chosen && dep != null && (
              <span className={"lk-dep " + dir} data-testid={`lk-dep-${f.id}`}>
                <i aria-hidden="true">{dep > 0 ? "\u25b2" : dep < 0 ? "\u25bc" : "\u2013"}</i>
                <b>{Math.abs(dep)} {Math.abs(dep) === 1 ? "point" : "points"}</b> {dep >= 0 ? "above" : "below"} {mine} usual <b>{pct(cur.p_usual)}</b>
                {clears != null && <> &middot; {clears ? "clear of it" : "the likely range still reaches it"}</>}
              </span>
            )}
          </span>
        </td>
        <td className="lk-cell-lk lk-lk">
          {/* Badge ON TOP of the number, and the block anchored to its bottom. Anchored to the top
              instead, a row carrying a badge would push its figure lower than a row without one and
              the percentages would stop lining up down the column -- the alignment docs/61 exists to
              protect. Bottom-anchored, every figure sits at one height whether or not a badge sits
              above it. Measured across eight rows: 27px from the row's bottom, all of them. */}
          <span className="lk-tiercell">
            {extras && rungTier && <TierBadge tier={rungTier} testid={`lk-tier-${f.id}`} />}
          </span>
          <span className="lk-lk-top"><span className="lk-figure">{p}<u>%</u></span></span>
          {lo != null && hi != null && (
            <span className="lk-data lk-rg lk-dim">{lo}&ndash;{hi}%</span>
          )}
          {under && <span className="lk-underw">Below the {under} bar &mdash; not listed by default</span>}
          {(res || tk) && (
            <span className="lk-rescell"><Result t={tk} outcome={res} needed={n} id={`lk-${f.id}`} /></span>
          )}
        </td>
        <td className="lk-cell-run"><Run games={cur.run} n={n} /></td>
        <td className="lk-cell-lu">
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
            {extras && cur.fkey && <SaveButton fkey={cur.fkey} />}
            {extras && cur.fkey && cur.addable !== false && (
              <button type="button" className={"lk-add" + (has?.(cur.fkey) ? " on" : "")}
                      aria-pressed={!!has?.(cur.fkey)}
                      aria-label={`${has?.(cur.fkey) ? "Remove" : "Add"} ${who} ${cur.market} ${has?.(cur.fkey) ? "from" : "to"} your combo`}
                      onClick={() => toggle({ ...cur, player: f.player, team: f.team || fx.team })} data-testid={`lk-add-${f.id}`}>
                <Icon name={has?.(f.fkey) ? "check" : "plus"} size={16} />
              </button>
            )}
            </span>
          </span>
        </td>
      </tr>
      {open && (
        <tr className="lk-whyrow"><td colSpan={6}>
          <Why f={cur} n={n} p={p} lo={lo} hi={hi} cleared={cleared} played={known.length} more={more} topMore={topMore} />
        </td></tr>
      )}
    </>
  );
}
