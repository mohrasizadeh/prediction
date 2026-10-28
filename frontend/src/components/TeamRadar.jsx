// Two-club radar (update pack part A). Each axis is the club's place in its league, 0 = bottom, 1 = top
// (defence is flipped so outward is always better). Screen readers get every value as text.
const R = 110, C = 140;
const pt = (i, n, v) => { const a = (Math.PI * 2 * i) / n - Math.PI / 2; return [C + Math.cos(a) * R * v, C + Math.sin(a) * R * v]; };
const poly = (axes, side) => axes.map((x, i) => pt(i, axes.length, x[side] ?? 0).join(",")).join(" ");

export default function TeamRadar({ axes = [], aName, bName, testid = "team-radar" }) {
  if (!axes.length) return null;
  const n = axes.length;
  const label = axes.map((x) => `${x.label}: ${aName} ${Math.round((x.a ?? 0) * 100)}, ${bName} ${Math.round((x.b ?? 0) * 100)} out of 100`).join(". ");
  return (
    <figure className="tr" data-testid={testid}>
      <svg viewBox="0 0 280 280" role="img" aria-label={`Radar. ${label}`}>
        {[0.25, 0.5, 0.75, 1].map((r) => <polygon key={r} points={axes.map((_, i) => pt(i, n, r).join(",")).join(" ")} className="tr-grid" />)}
        {axes.map((x, i) => { const [x2, y2] = pt(i, n, 1); return <line key={x.key} x1={C} y1={C} x2={x2} y2={y2} className="tr-grid" />; })}
        <polygon points={poly(axes, "a")} className="tr-a" />
        <polygon points={poly(axes, "b")} className="tr-b" />
        {axes.map((x, i) => { const [lx, ly] = pt(i, n, 1.2); return <text key={x.key} x={lx} y={ly} textAnchor="middle" dominantBaseline="middle" className="tr-lbl">{x.label}</text>; })}
      </svg>
      <figcaption className="tr-legend"><span><i className="tr-key tr-key--a" />{aName}</span><span><i className="tr-key tr-key--b" />{bName}</span></figcaption>
    </figure>
  );
}
