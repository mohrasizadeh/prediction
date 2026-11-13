// Engine reveal: a short overlay that walks the engine layers that built a forecast, then shows it.
// Honest by design (docs/03 §4): the forecast is already computed. Each stage names a real layer of
// backend/soccer_brain/engine.py and prints that forecast's own value, never a made-up one. It never
// says the work is happening "now". The lineup-effects layer is locked off, so it is not shown.
//
// Pacing: the first time a forecast is opened in this tab, the layers take about 2 s and the result holds
// for 0.9 s; after that 0.6 s plus 0.35 s. Instant with prefers-reduced-motion. A tap or Esc skips. It never
// closes before the data is ready.
import { useEffect, useMemo, useRef, useState } from "react";

const pct = (x) => (x == null ? null : `${Math.round(x * 100)}%`);
const band = (f) => (f?.p == null ? "No data" : f.lo != null && f.hi != null ? `${pct(f.p)} (${Math.round(f.lo * 100)} to ${Math.round(f.hi * 100)})` : pct(f.p));
const LINEUP = { confirmed: "Confirmed lineup", likely: "Likely lineup", unsure: "Lineup not sure", bench: "Expected on the bench" };
const DOTS = { Strong: "●●●", Solid: "●●○", Watch: "●○○" };

// One row per real engine step. `value` reads only fields the forecast already carries.
export function stagesFor(f) {
  const team = f?.team?.name, opp = f?.opp?.name;
  return [
    { key: "strength", name: "Team strength", how: "Dixon-Coles ratings", value: team && opp ? `${team} v ${opp}` : "No data" },
    { key: "style", name: "Opponent style", how: "Rebuilt from past games", value: f?.opp_tactic || (opp ? `${opp} profile` : "No data") },
    { key: "totals", name: "Team totals", how: "Negative binomial model", value: f?.noun || f?.stat || "No data" },
    { key: "minutes", name: "Minutes", how: f?.scope === "player" ? "Lineup scenarios" : "Match context",
      value: f?.scope === "player" ? (LINEUP[f?.lineup_badge] || (f?.lineup_confirmed ? LINEUP.confirmed : "Predicted lineup")) + (f?.p_play != null ? ` · ${pct(f.p_play)} to play` : "") : "Team level" },
    { key: "band", name: "Likelihood band", how: "Credible interval", value: band(f) },
  ];
}

const seenKey = (f) => `er:${f?.fkey || f?.id || "x"}`;
function wasSeen(f) { try { return sessionStorage.getItem(seenKey(f)) === "1"; } catch { return false; } }
function markSeen(f) { try { sessionStorage.setItem(seenKey(f), "1"); } catch { /* private mode: fine */ } }
const reduced = () => typeof window !== "undefined" && window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;

// Network drawing: five columns, one per stage; the last column is the single output node.
const COLS = [3, 4, 4, 3, 1];
const W = 300, H = 132;
const nodes = COLS.map((n, c) => [...Array(n)].map((_, i) => ({ x: 22 + c * ((W - 44) / (COLS.length - 1)), y: H / 2 + (i - (n - 1) / 2) * 30 })));

function Network({ at }) {
  return (
    <svg className="er-net" viewBox={`0 0 ${W} ${H}`} aria-hidden="true">
      {nodes.slice(0, -1).map((col, c) => col.flatMap((a, i) => nodes[c + 1].map((b, j) => (
        <line key={`${c}-${i}-${j}`} x1={a.x} y1={a.y} x2={b.x} y2={b.y}
          className={`er-edge${c < at - 1 ? " is-done" : c === at - 1 ? " is-live" : ""}`} />
      ))))}
      {nodes.map((col, c) => col.map((n, i) => (
        <circle key={`${c}-${i}`} cx={n.x} cy={n.y} r={c === COLS.length - 1 ? 9 : 6}
          className={`er-node${c < at ? " is-done" : c === at ? " is-live" : ""}`} style={{ animationDelay: `${i * 90}ms` }} />
      )))}
    </svg>
  );
}

export default function EngineReveal({ forecast, ready = true, onDone, firstMs = 2000, repeatMs = 600, holdMs = 900, testid = "engine-reveal" }) {
  const stages = useMemo(() => stagesFor(forecast), [forecast]);
  const seen = useMemo(() => wasSeen(forecast), [forecast]);
  const total = useMemo(() => (reduced() ? 0 : seen ? repeatMs : firstMs), [seen, firstMs, repeatMs]);
  const hold = total ? (seen ? Math.round(holdMs * 0.4) : holdMs) : 0;
  const [at, setAt] = useState(total ? 0 : stages.length);   // stage index; stages.length = all done
  const [shut, setShut] = useState(false);
  const done = useRef(false);
  const box = useRef(null);

  const finish = () => { if (done.current || !ready) return; done.current = true; markSeen(forecast); setShut(true); setTimeout(() => onDone?.(), total ? 260 : 0); };

  useEffect(() => {                                           // step through the stages
    if (at >= stages.length) return undefined;
    const t = setTimeout(() => setAt((x) => x + 1), total / stages.length);
    return () => clearTimeout(t);
  }, [at, stages.length, total]);
  useEffect(() => {                                           // hold the result a beat, then close
    if (at < stages.length || !ready) return undefined;
    const t = setTimeout(finish, hold);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [at, ready]);
  useEffect(() => {
    box.current?.focus();                                    // focus the dialog, not Skip, so no ring flashes
    const k = (e) => e.key === "Escape" && skip();
    window.addEventListener("keydown", k);
    return () => window.removeEventListener("keydown", k);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  const skip = () => { setAt(stages.length); if (ready) finish(); };

  const result = at >= stages.length && ready;
  return (
    <div className={`er-scrim${shut ? " is-shut" : ""}`} data-testid={testid}>
      <div ref={box} tabIndex={-1} className="er-box" role="dialog" aria-modal="true" aria-labelledby="er-title" aria-describedby="er-sub">
        <div className="er-head">
          <span className="er-chip">Forecast engine</span>
          <button className="er-skip" onClick={skip} data-testid={`${testid}-skip`}>Skip</button>
        </div>
        <h2 id="er-title" className="er-title">{result ? (forecast?.market || "Forecast") : "Reading the layers behind this forecast"}</h2>
        <p id="er-sub" className="er-sub">Built from data before kickoff{forecast?.player?.name ? ` · ${forecast.player.name}` : ""}</p>
        <Network at={at} />
        <ol className="er-steps" aria-live="polite">
          {stages.map((s, i) => (
            <li key={s.key} className={`er-step${i < at ? " is-done" : i === at ? " is-live" : ""}`} data-testid={`${testid}-${s.key}`}>
              <span className="er-tick" aria-hidden="true" />
              <span className="er-name">{s.name}<small>{s.how}</small></span>
              <span className="er-val">{i < at ? s.value : ""}</span>
            </li>
          ))}
        </ol>
        <div className={`er-result${result ? " is-in" : ""}`} aria-hidden={!result} data-testid={`${testid}-result`}>
          <strong className="er-p">{pct(forecast?.p) || "No data"}</strong>
          <span className="er-band">{forecast?.lo != null ? `Band ${Math.round(forecast.lo * 100)} to ${Math.round(forecast.hi * 100)}` : ""}</span>
          {forecast?.tier && <span className="er-tier"><span className={`er-dots er-dots--${forecast.tier.toLowerCase()}`} aria-hidden="true">{DOTS[forecast.tier]}</span> {forecast.tier}</span>}
          {forecast?.reasons?.[0] && <p className="er-reason">{forecast.reasons[0]}</p>}
        </div>
      </div>
    </div>
  );
}
