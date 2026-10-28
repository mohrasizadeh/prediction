// Chips row (scrolls sideways, single or multi pick, count badge) and Segmented control (2 to 3 options). docs/24.
export function ChipsRow({ options, value, onChange, multi = false, label, testid = "ui-chips" }) {
  const on = (id) => (multi ? (value || []).includes(id) : value === id);
  const tap = (id) => {
    if (!multi) return onChange(id);
    const v = value || [];
    onChange(v.includes(id) ? v.filter((x) => x !== id) : [...v, id]);
  };
  return (
    <div className="k-chips" role="group" aria-label={label} data-testid={testid}>
      {options.map((o) => (
        <button key={o.id} type="button" className={`k-chip${on(o.id) ? " on" : ""}${o.accent ? " br" : ""}`} aria-pressed={on(o.id)} onClick={() => (o.onClick ? o.onClick() : tap(o.id))} data-testid={`${testid}-${o.id}`}>
          {o.label}{o.count != null && <span className="k-badge" aria-label={`${o.count} selected`}>{o.count}</span>}
        </button>
      ))}
    </div>
  );
}

export function Segmented({ options, value, onChange, label, testid = "ui-seg" }) {
  return (
    <div className="k-seg" role="radiogroup" aria-label={label} data-testid={testid}>
      {options.map((o) => (
        <button key={o.id} type="button" role="radio" aria-checked={String(value) === String(o.id)} className={String(value) === String(o.id) ? "on" : ""} onClick={() => onChange(o.id)} data-testid={`${testid}-${o.id}`}>{o.label}</button>
      ))}
    </div>
  );
}
