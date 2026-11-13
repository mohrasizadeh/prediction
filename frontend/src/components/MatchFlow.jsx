// Momentum and possession across the match (backend/match_flow.py), drawn from the live tick's own
// minute-by-minute snapshots: API-Football publishes running totals and nothing per minute.
//
// Momentum: each five-minute window, the shots, shots on target and corners each side added in it.
// Home above the line, away below, so the side on top is the side that was attacking. Goals sit on
// the axis where they fell. Possession: the home side's share inside each window, around 50%.
// The numbers are written out in the accessible label and in the hover title of every bar, so the
// colour never carries the meaning alone. A match the live tick did not follow has no flow, and
// then nothing is drawn.

const W = 600, H = 120, MID = H / 2, PH = 56;

export default function MatchFlow({ flow, home = "Home", away = "Away", testid = "match-flow" }) {
  if (!flow || !flow.windows?.length) return null;
  const total = flow.minutes || 90;
  const x = (m) => (m / total) * W;
  const known = flow.windows.filter((w) => w.known);
  const peak = flow.peak || 1;
  const bw = Math.max(2, x(flow.window) - 3);
  const poss = known.filter((w) => w.poss_home != null);
  // 25% to 75% fills the height: a match is almost never outside it, and on a 0-100 scale every
  // swing that matters drew as a flat line. Anything beyond is clamped to the edge.
  const pY = (v) => PH - ((Math.min(75, Math.max(25, v)) - 25) / 50) * PH;
  const pLine = poss.map((w, i) => `${i ? "L" : "M"}${(x(w.from) + x(w.to)) / 2},${pY(w.poss_home)}`).join(" ");
  const sideTotal = (s) => known.reduce((a, w) => a + w[s].shots + w[s].sot + 0.5 * w[s].corners, 0);
  const hT = sideTotal("home"), aT = sideTotal("away");
  const lead = hT === aT ? "Neither side had more of the attacking." : `${hT > aT ? home : away} had more of the attacking.`;
  const ticks = [0, 15, 30, 45, 60, 75, 90].filter((m) => m <= total);
  const label = (w) => `${w.from}–${w.to}': ${home} ${w.home.shots} shots (${w.home.sot} on target), ${w.home.corners} corners; ${away} ${w.away.shots} shots (${w.away.sot} on target), ${w.away.corners} corners${w.poss_home != null ? `; possession ${Math.round(w.poss_home)}–${Math.round(100 - w.poss_home)}` : ""}`;
  return (
    <section className="mfx-sec card mflow" aria-labelledby={`${testid}-h`} data-testid={testid}>
      <header className="mfx-head"><h2 className="k-sec" id={`${testid}-h`}>Momentum</h2></header>
      <p className="k-faint k-small mflow-lead">Shots, shots on target and corners in each five minutes. {lead}</p>
      <svg className="mflow-chart" viewBox={`0 0 ${W} ${H + 16}`} role="img" aria-label={`Momentum by five minutes. ${known.map(label).join(". ")}`} data-testid={`${testid}-momentum`}>
        <line x1="0" x2={W} y1={MID} y2={MID} className="mflow-axis" />
        {total > 45 && <line x1={x(45)} x2={x(45)} y1="4" y2={H - 4} className="mflow-ht" />}
        {known.map((w) => {
          const hv = w.home.shots + w.home.sot + 0.5 * w.home.corners, av = w.away.shots + w.away.sot + 0.5 * w.away.corners;
          const hh = (hv / peak) * (MID - 6), ah = (av / peak) * (MID - 6);
          return (
            <g key={w.from}>
              <title>{label(w)}</title>
              {hh > 0 && <rect className="mflow-h" x={x(w.from) + 1.5} y={MID - hh} width={bw} height={hh} rx="2" />}
              {ah > 0 && <rect className="mflow-a" x={x(w.from) + 1.5} y={MID} width={bw} height={ah} rx="2" />}
            </g>
          );
        })}
        {(flow.goals || []).filter((g) => g.minute != null).map((g, i) => (
          <g key={i} className={`mflow-goal mflow-goal--${g.side}`} transform={`translate(${x(Math.min(total, g.minute))},${g.side === "home" ? 9 : H - 9})`}>
            <title>{`Goal, ${g.side === "home" ? home : away}, ${g.minute}'`}</title>
            <circle r="6" /><circle r="2.2" className="mflow-goal-dot" />
          </g>
        ))}
        {ticks.map((m) => <text key={m} x={Math.min(W - 10, Math.max(8, x(m)))} y={H + 13} className="mflow-tick" textAnchor="middle">{m}'</text>)}
      </svg>
      <div className="mflow-key" aria-hidden="true"><span className="mflow-kh">{home}</span><span className="mflow-kg">Goal</span><span className="mflow-ka">{away}</span></div>
      {poss.length >= 3 && (
        <>
          <h3 className="mflow-sub">Possession, {home} share</h3>
          <svg className="mflow-chart mflow-poss" viewBox={`0 0 ${W} ${PH + 6}`} role="img" data-testid={`${testid}-possession`}
            aria-label={`${home} possession by five minutes: ${poss.map((w) => `${w.from}–${w.to}' ${Math.round(w.poss_home)}%`).join(", ")}`}>
            <line x1="0" x2={W} y1={pY(50)} y2={pY(50)} className="mflow-axis mflow-axis--dash" />
            <path d={`${pLine} L${(x(poss[poss.length - 1].from) + x(poss[poss.length - 1].to)) / 2},${pY(50)} L${(x(poss[0].from) + x(poss[0].to)) / 2},${pY(50)} Z`} className="mflow-poss-area" />
            <path d={pLine} className="mflow-poss-line" />
            <text x="4" y="10" className="mflow-tick" textAnchor="start">75%</text>
            <text x="4" y={PH + 2} className="mflow-tick" textAnchor="start">25%</text>
          </svg>
        </>
      )}
    </section>
  );
}
