// A harness that renders the REAL ForecastRow, not a mockup, in the states the six screens produce.
// Dropped into src/ so CRA builds it, rendered by Playwright, then removed.
import { useState } from "react";
import { ForecastList } from "./components/ui/ForecastList";

const run = (vals) => vals.map((v, i) => ({ v, m: 90, opp: { id: "o" + i, name: "Atalanta" }, home: i % 2 === 0 }));
const ladder = (o) => Object.fromEntries(Object.entries(o).map(([k, v]) => [k, v]));

// Grade every rung the way tiering.assign does after docs/76 -- on the NUMBER. The fixture used to
// pin a tier per market and leave it on every rung, which put "Solid" beside 41% and 11%: exactly
// the contradiction the tier change exists to remove, and not something the product can now produce.
const grade = (p, lo) => (p >= 0.9 && lo >= 0.84 ? "Strong" : p >= 0.8 && lo >= 0.7 ? "Solid" : p >= 0.6 ? "Watch" : null);

const VERBS = { tackles: "makes", shots: "takes", sot: "has", fouls: "commits" };
const market = (stat, label, noun, thr, p, lo, hi, tier, usual, vals, extra = {}) => ({
  id: `f-${stat}`, fkey: `k-${stat}`, scope: "player", stat, market: label, noun,
  verb: VERBS[stat] || "has",
  thr, p, lo, hi, tier, p_usual: usual, edge: p - usual, span: 0.24, pos: "M",
  ladder: ladder({ "0.5": Math.min(0.99, p + 0.3), [String(thr)]: p, [String(thr + 1)]: Math.max(0.05, p - 0.26) }),
  ladder_band: { "0.5": [Math.min(0.97, p + 0.24), 0.99], [String(thr)]: [lo, hi],
                 [String(thr + 1)]: [Math.max(0.02, p - 0.33), Math.max(0.06, p - 0.19)] },
  ladder_tier: { "0.5": grade(Math.min(0.99, p + 0.3), Math.min(0.97, p + 0.24)),
                 [String(thr)]: grade(p, lo),
                 [String(thr + 1)]: grade(Math.max(0.05, p - 0.26), Math.max(0.02, p - 0.33)) },
  run: run(vals), lineup_badge: "confirmed", reasons: ["The opponent gives up more " + noun[1] + " to players in his position"],
  ...extra,
});

const BASE = {
  ...market("tackles", "2+ tackles", ["tackle", "tackles"], 1.5, 0.64, 0.58, 0.71, "Solid", 0.58, [1, 3, 2, 0, 2, 1, 3, 2, 1, 2]),
  player: { id: "p1", name: "Marcus Linday", image: null }, team_iid: 1, opp_iid: 2, home_iid: 1,
  kickoff: "2026-11-08T15:00:00Z", status: "final", outcome: { reached: true, actual: 3, played: true },
};
// The OLD row read `more_lines` and showed "+N more markets"; the NEW one reads `markets` and puts
// a picker on the card. The fixture carries BOTH, so each version is shown doing its own real
// thing rather than one of them being starved of its data.
BASE.markets = [
  market("tackles", "2+ tackles", ["tackle", "tackles"], 1.5, 0.64, 0.58, 0.71, "Solid", 0.58, [1, 3, 2, 0, 2, 1, 3, 2, 1, 2]),
  market("shots", "2+ shots", ["shot", "shots"], 1.5, 0.72, 0.64, 0.79, "Solid", 0.61, [3, 2, 1, 2, 4, 2, 2, 1, 3, 2]),
  market("sot", "1+ on target", ["shot on target", "shots on target"], 0.5, 0.91, 0.86, 0.95, "Strong", 0.77, [2, 1, 1, 2, 0, 1, 3, 1, 2, 1]),
  market("fouls", "1+ foul", ["foul", "fouls"], 0.5, 0.52, 0.45, 0.60, null, 0.49, [1, 0, 2, 1, 1, 2, 0, 1, 1, 2]),
];

BASE.more_lines = BASE.markets.slice(1).map((m) => ({
  fkey: m.fkey, stat: m.stat, thr: m.thr, market: m.market, p: m.p, lo: m.lo, hi: m.hi,
  tier: m.tier, p_usual: m.p_usual, edge: m.edge, ladder: m.ladder, pos: m.pos, span: m.span,
}));

const ROWS = [
  BASE,
  { ...BASE, id: "f2", fkey: "k2", player: { id: "p2", name: "Thom van den Berg" },
    p: 0.91, lo: 0.86, hi: 0.95, tier: grade(0.91, 0.86), ladder_tier: { "2": grade(0.91, 0.86) },
    outcome: { reached: false, actual: 0, played: true } },
  { ...BASE, id: "f3", fkey: "k3", player: { id: "p3", name: "Sem Steijn" },
    p: 0.41, lo: 0.34, hi: 0.49, tier: grade(0.41, 0.34), ladder_tier: { "2": grade(0.41, 0.34) },
    lineup_badge: "bench", outcome: { reached: true, actual: 1, played: true } },
  // a club line: no player, no "he"
  { ...BASE, id: "f4", fkey: "k4", player: null, scope: "team", markets: undefined, market: "11+ shots",
    p: 0.66, lo: 0.60, hi: 0.72, tier: grade(0.66, 0.60), ladder_tier: { "11": grade(0.66, 0.60) },
    outcome: null, status: "scheduled" },
  // no run data at all, and a market with one entry
  { ...BASE, id: "f5", fkey: "k5", player: { id: "p5", name: "Pawel Bochniewicz" }, run: [], markets: undefined,
    p: 0.73, lo: 0.66, hi: 0.80, tier: grade(0.73, 0.66), ladder_tier: { "2": grade(0.73, 0.66) },
    outcome: null, status: "scheduled" },
  // A ONE-DIGIT RANGE. Every other row reads "58-71%"; this one reads "9-14%". With the answer
  // cell shrink-wrapping its contents instead of taking its column, this row's figure sat at a
  // different x from the rest -- and with five rows of equal-width captions nothing noticed.
  { ...BASE, id: "f6", fkey: "k6", player: { id: "p6", name: "Ibrahim Sangare" }, markets: undefined,
    p: 0.11, lo: 0.09, hi: 0.14, tier: grade(0.11, 0.09), ladder_tier: { "2": grade(0.11, 0.09) },
    outcome: null, status: "scheduled" },
];
const TEAMS = { 1: { id: "t1", name: "SC Heerenveen" }, 2: { id: "t2", name: "Feyenoord" } };

export default function CardHarness() {
  const [n] = useState(0);
  return (
    <div style={{ padding: 0 }} data-testid="harness" data-n={n}>
      <ForecastList rows={ROWS} teams={TEAMS} homeIid={1} testid="harness-list" />
    </div>
  );
}
