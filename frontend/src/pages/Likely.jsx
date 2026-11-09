// "Most likely" (docs/63): one screen, one question -- what is likeliest in the next few hours.
//
// The feed answers "what differs most from usual" and leads on the edge. A reader an hour before
// kick-off is asking something else, and answering the second question on a screen built for the
// first is what produced rows reading "56% to take 2 shots", which tell a reader nothing they can
// use. This screen leads on the number, sorts by it, and shows nothing under engine.watch_min.
//
// Three things on it are new and therefore explained in situ, next to a live specimen (the key
// strip): the range bar, the two-tone run strip, and the line stepper.
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { useApi } from "../lib/useApi";
import { DISCLAIMER, pct } from "../lib/copy";
import { utc } from "../lib/time";
import { useTitle } from "../components/Football";
import { Crest, PlayerAvatar } from "../components/Media";
import { EmptyState, ErrorState, Skeleton } from "../components/ui";

const WINDOWS = [4, 12, 24];
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
      {under && <span className="lk-underw">Below the {under}% bar — not listed by default</span>}
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

function Why({ f, n, p, lo, hi, cleared, played }) {
  const lu = lineupWords(f);
  return (
    <div className="lk-whybox">
      <h4>Why {pct(p / 100)}</h4>
      <ul>
        <li>He has reached {lineWords(f, n)} in {cleared === played ? `all ${played}` : cleared} of his last {played} appearances.</li>
        {lu.why && <li>{lu.why}</li>}
        {(f.reasons || []).slice(0, 2).map((r, i) => <li key={i}>{r}</li>)}
      </ul>
      <p>
        Likely range {lo}–{hi}%. That is where the answer most likely sits; we land on one number and
        this is the spread around it. We have not yet measured that spread against results — the{" "}
        <Link to="/track-record">Track Record</Link> page will say when we have.
      </p>
    </div>
  );
}

function Row({ f, open, onToggle, floor }) {
  const [pick, setPick] = useState(null);
  const lad = useMemo(() => ladderOf(f), [f]);
  const chosen = need(f.thr);
  const n = pick ?? chosen;
  const rung = lad.find((r) => r.n === n);
  const p = Math.round(100 * (n === chosen ? f.p : rung?.p ?? f.p));
  const band = n === chosen ? [f.lo, f.hi] : rung?.band || [f.lo, f.hi];
  const lo = Math.round(100 * band[0]);
  const hi = Math.round(100 * band[1]);
  const under = p < Math.round(floor * 100) ? Math.round(floor * 100) : null;
  const lu = lineupWords(f);
  const known = (f.run || []).filter((g) => g && g.v != null);
  const cleared = known.filter((g) => g.v >= n).length;
  const who = f.player?.name || f.team?.name;
  const words = lineWords(f, n);
  const pos = POS[f.pos] || f.pos;
  const ko = f.kickoff ? utc(f.kickoff).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", hour12: false }) : "";
  const fx = `${f.team?.iid === f.home_iid ? "vs" : "at"} ${f.opp?.name || ""}`;
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
                <span className="lk-ava-cr"><Crest team={f.team} size={15} /></span>
              </span>
            ) : (
              <span className="lk-ava lk-ava--club"><Crest team={f.team} size={38} /></span>
            )}
            <Link className="lk-name" to={f.player ? `/player/${f.player.id}` : `/team/${f.team?.id}`}>{who}</Link>
            {pos && <span className="lk-pos">{pos}</span>}
          </span>
        </td>
        <td className="lk-cell-fx lk-fx">{fx}<small>{ko}</small></td>
        <td className="lk-cell-mk">
          <span className="lk-line">
            <span className="lk-claim">{words}<span className="lk-fx-inline"> · {fx} {ko}</span></span>
            <Steps rows={lad} cur={n} onPick={setPick} label={`How many ${nounFor(f, 2)}`} />
          </span>
        </td>
        <td className="lk-cell-lk lk-lk">
          <span className="lk-lk-top"><span className="lk-figure">{p}<u>%</u></span></span>
          <Bar p={p} lo={lo} hi={hi} under={under} />
          <span className="lk-data lk-rg lk-dim">{lo}–{hi}%</span>
        </td>
        <td className="lk-cell-run"><Run games={f.run} n={n} /></td>
        <td className="lk-cell-lu">
          <span className="lk-lucell">
            <span className={`lk-lu is-${lu.cls}`} title={lu.why}>
              {lu.cls !== "none" && <s />}{lu.word}
              {lu.sr && <span className="sr-only">{lu.sr}</span>}
            </span>
            <button type="button" className="lk-why" aria-expanded={open} onClick={onToggle} data-testid={`lk-why-${f.id}`}>
              Why<span className="sr-only"> {who}, {words}, {p} percent</span> {open ? "▴" : "▾"}
            </button>
          </span>
        </td>
      </tr>
      {open && (
        <tr className="lk-whyrow"><td colSpan={6}>
          <Why f={f} n={n} p={p} lo={lo} hi={hi} cleared={cleared} played={known.length} />
        </td></tr>
      )}
    </>
  );
}

const DECADES = [0.9, 0.8, 0.7, 0.6, 0.5];
const BAND_WORDS = { 0.9: "90 and above", 0.8: "80 to 89", 0.7: "70 to 79", 0.6: "60 to 69", 0.5: "Below 60" };

export function Likely() {
  useTitle("Most likely");
  const [win, setWin] = useState(4);
  const [confirmed, setConfirmed] = useState(false);
  const [open, setOpen] = useState(null);
  const q = useApi("/likely", { within_h: win, limit: 60 });
  // The calibration on each band header comes from the product's own scored record, and only once
  // there is one. Until then the band states what it can state -- how many lines sit in it. A
  // figure typed into the page instead would be the one claim on this screen nobody could check.
  const rec = useApi("/track-record");
  const bins = useMemo(() => {
    const out = {};
    if (rec.data?.ready) (rec.data.bins || []).forEach((b) => { out[b.from] = b; });
    return out;
  }, [rec.data]);
  const toggle = useCallback((id) => setOpen((o) => (o === id ? null : id)), []);

  const floor = q.data?.floor ?? 0.6;
  const rows = useMemo(() => {
    const all = q.data?.rows || [];
    return confirmed ? all.filter((r) => r.lineup_badge === "confirmed" || r.scope === "team") : all;
  }, [q.data, confirmed]);
  const confN = (q.data?.rows || []).filter((r) => r.lineup_badge === "confirmed").length;
  const matches = new Set(rows.map((r) => r.match_iid)).size;

  const grouped = useMemo(() => {
    const out = [];
    let cur = null;
    rows.forEach((f) => {
      const d = DECADES.find((x) => f.p >= x) ?? 0.5;
      if (d !== cur) { cur = d; out.push({ band: d, n: rows.filter((r) => (DECADES.find((x) => r.p >= x) ?? 0.5) === d).length }); }
      out.push({ f });
    });
    return out;
  }, [rows]);

  const head = (
    <>
      <h1 className="h1">Most likely</h1>
      <p className="lk-lede">
        The likeliest <b>things to happen</b> in the <b>{matches} match{matches === 1 ? "" : "es"}</b>{" "}
        kicking off in the next {win} hours{confirmed ? <>, <b>confirmed lineups only</b></> : null}.
      </p>
      <div className="lk-bar" data-testid="lk-filters">
        <button type="button" className="lk-chip" aria-pressed={confirmed} onClick={() => setConfirmed((v) => !v)} data-testid="lk-confirmed">
          Only confirmed starters <small>{confN}</small>
        </button>
        {WINDOWS.map((h) => (
          <button key={h} type="button" className="lk-chip" aria-pressed={win === h} onClick={() => setWin(h)} data-testid={`lk-win-${h}`}>
            Next {h}h
          </button>
        ))}
      </div>
    </>
  );

  if (q.loading) return <section className="lk" data-testid="likely-page">{head}<Skeleton shape="row" count={6} /></section>;
  if (q.error) return <section className="lk" data-testid="likely-page">{head}<ErrorState onRetry={q.reload} /></section>;

  return (
    <section className="lk" data-testid="likely-page">
      {head}
      <div className="lk-key" data-testid="lk-key">
        <span className="lk-keyit">
          <svg width="54" height="9" aria-hidden="true">
            <rect x="0" y="4" width="54" height="1" fill="var(--lk-rule)" />
            <rect x="33" y="1" width="16" height="7" rx="2" fill="var(--brand)" />
          </svg>
          <span><b>The bar is the range</b>, and the number under it says so exactly.</span>
        </span>
        <span className="lk-keyit">
          <svg width="40" height="26" aria-hidden="true">
            <rect x="0" y="12" width="7" height="14" rx="2" fill="var(--brand)" />
            <rect x="0" y="12" width="7" height="3" fill="var(--tier-strong)" />
            <rect x="9" y="19" width="7" height="7" rx="2" fill="var(--lk-rule)" />
            <rect x="18" y="4" width="7" height="22" rx="2" fill="var(--brand)" />
            <rect x="18" y="4" width="7" height="11" fill="var(--tier-strong)" />
            <rect x="27" y="20" width="7" height="6" rx="2" fill="var(--lk-rule)" />
            <rect x="0" y="15" width="40" height="1" fill="var(--text3)" />
          </svg>
          <span><b>Each bar darkens at the line.</b> Dark = what it took to reach it, bright = how far past. A bar entirely grey fell short.</span>
        </span>
        <span className="lk-keyit">
          <span className="lk-steps" aria-hidden="true" style={{ pointerEvents: "none" }}>
            <span className="lk-step" aria-checked="true">1+</span><span className="lk-step">2+</span>
          </span>
          <span><b>Tap to move the line.</b> Everything on the row follows.</span>
        </span>
      </div>

      {!rows.length ? (
        <EmptyState icon="calendar" title={`Nothing here reaches ${Math.round(floor * 100)}%.`}>
          We list a line once it reaches {Math.round(floor * 100)}%, and nothing in the next {win} hours does yet.
          Numbers move as team news arrives, so this often fills up in the last hour.
        </EmptyState>
      ) : (
        <table className="lk-tbl" data-testid="lk-table">
          <colgroup>
            <col className="lk-c-who" /><col className="lk-c-fx" /><col className="lk-c-mk" />
            <col className="lk-c-lk" /><col className="lk-c-run" /><col className="lk-c-lu" />
          </colgroup>
          <thead><tr>
            <th scope="col" className="lk-label">Player</th>
            <th scope="col" className="lk-label">Match</th>
            <th scope="col" className="lk-label">Line</th>
            <th scope="col" className="lk-label" aria-sort="descending">
              <div style={{ textAlign: "right" }}>How likely, and how sure ↓</div>
              <div className="lk-axis">
                <span style={{ left: 31.6 }}>60</span><span style={{ left: 94.8 }}>80</span><span style={{ left: 158 }}>100</span>
              </div>
            </th>
            <th scope="col" className="lk-label">Last 10 against that line</th>
            <th scope="col" className="lk-label">Lineup</th>
          </tr></thead>
          <tbody>
            {grouped.map((g, i) => (g.band != null ? (
              <tr className="lk-grp" key={`b${g.band}`}><td colSpan={6}><span className="lk-grpin">
                <b>{BAND_WORDS[g.band]}</b>
                <span>
                  {g.n} line{g.n === 1 ? "" : "s"}
                  {bins[g.band] && ` · ${bins[g.band].n} scored · ${pct(bins[g.band].actual)} happened`}
                </span>
              </span></td></tr>
            ) : (
              <Row key={g.f.id || i} f={g.f} floor={floor} open={open === g.f.id} onToggle={() => toggle(g.f.id)} />
            )))}
          </tbody>
        </table>
      )}

      <p className="lk-foot">
        <span><b>Every percentage here assumes he is on the pitch.</b> Whether he will be is the
          Lineup column&apos;s job — two questions, two answers, so neither one can hide inside the other.</span>
        <span>{DISCLAIMER}</span>
        {!rec.data?.ready && (
          <span>Beta: the <Link to="/track-record">Track Record</Link> page will carry real results
            once {rec.data?.needed ?? 300} forecasts have been scored ({rec.data?.scored ?? 0} so far).</span>
        )}
      </p>
    </section>
  );
}

export default Likely;
