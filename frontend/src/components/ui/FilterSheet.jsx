// Filter sheet (docs/24): a bottom sheet of sliders, segmented controls and switches with "Reset" and
// "Show N results" (the live count comes from the page).
import { BottomSheet } from "./BottomSheet";

export function FilterGroup({ label, children }) {
  return <section className="k-fgroup"><h3 className="k-sec">{label}</h3>{children}</section>;
}

export function FilterSheet({ open, onClose, onReset, count, title = "More filters", children, testid = "ui-filters" }) {
  const footer = (
    <>
      <button type="button" className="btn btn--secondary" onClick={onReset} data-testid={`${testid}-reset`}>Reset</button>
      <button type="button" className="btn btn--primary k-grow" onClick={onClose} data-testid={`${testid}-apply`}>
        {count == null ? "Show results" : count === 0 ? "No results" : `Show ${count} result${count === 1 ? "" : "s"}`}
      </button>
    </>
  );
  return <BottomSheet open={open} onClose={onClose} title={title} footer={footer} testid={testid}>{children}</BottomSheet>;
}
