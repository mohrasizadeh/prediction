// One- or two-thumb slider (docs/24). Value shown above each thumb, 44 px touch targets, native inputs for keyboard
// and screen readers. `value` is a number (one thumb) or [low, high] (two thumbs).
const pos = (v, min, max) => ((v - min) / (max - min)) * 100;
const at = (p) => `calc(13px + (100% - 26px) * ${p / 100})`;

export function RangeSlider({ min, max, step = 1, value, onChange, format = (v) => v, label, testid = "ui-range" }) {
  const two = Array.isArray(value);
  const [lo, hi] = two ? value : [min, value];
  const set = (i) => (e) => {
    const v = Number(e.target.value);
    if (!two) return onChange(v);
    onChange(i === 0 ? [Math.min(v, hi), hi] : [lo, Math.max(v, lo)]);
  };
  const thumbs = two ? [[0, lo], [1, hi]] : [[1, hi]];
  return (
    <div className="k-range" data-testid={testid}>
      <div className="k-range-track" aria-hidden="true"><b style={{ left: `${two ? pos(lo, min, max) : 0}%`, width: `${pos(hi, min, max) - (two ? pos(lo, min, max) : 0)}%` }} /></div>
      {thumbs.map(([i, v]) => (
        <span key={i} className="k-range-tip" style={{ left: at(pos(v, min, max)), transform: `translateX(${pos(v, min, max) < 8 ? "-13px" : pos(v, min, max) > 92 ? "calc(-100% + 13px)" : "-50%"})` }} aria-hidden="true">{format(v, i)}</span>
      ))}
      {thumbs.map(([i, v]) => (
        <input key={i} type="range" min={min} max={max} step={step} value={v} onChange={set(i)} className={`k-range-in k-range-in--${i}${two ? "" : " k-range-in--one"}`}
          aria-label={two ? `${label} ${i === 0 ? "from" : "to"}` : label} aria-valuetext={String(format(v, i))} data-testid={`${testid}-${i === 0 ? "low" : "high"}`} />
      ))}
    </div>
  );
}
