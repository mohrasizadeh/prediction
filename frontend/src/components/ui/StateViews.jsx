// Loading, empty and error states (docs/24): skeletons in the card's shape, empty says why plus a next step,
// error is one sentence and "Try again" (the last good data can stay on screen above it).
import Icon from "../Icon";
import { utc } from "../../lib/time";

const SHAPES = {
  card: ["k-sk-row", "k-sk-big", "k-sk-bar", "k-sk-line"],
  row: ["k-sk-line"],
  match: ["k-sk-line", "k-sk-bar"],
};

export function Skeleton({ shape = "card", count = 3, testid = "ui-skeleton" }) {
  return (
    <div className={`k-sk-list k-sk-list--${shape}`} role="status" aria-label="Loading" data-testid={testid}>
      {[...Array(count)].map((_, i) => (
        <div key={i} className={`k-sk k-sk--${shape}`} aria-hidden="true">{SHAPES[shape].map((c, j) => <span key={j} className={c} />)}</div>
      ))}
    </div>
  );
}

export function EmptyState({ icon = "calendar", title, children, action, testid = "ui-empty" }) {
  return (
    <div className="k-state" data-testid={testid}>
      <span className="k-state-ico" aria-hidden="true"><Icon name={icon} size={22} /></span>
      {title && <h3>{title}</h3>}
      {children && <p>{children}</p>}
      {action}
    </div>
  );
}

export function ErrorState({ message = "We could not load this.", onRetry, updated, testid = "ui-error" }) {
  return (
    <div className="k-state k-state--err" role="alert" data-testid={testid}>
      <span className="k-state-ico" aria-hidden="true"><Icon name="alert" size={22} /></span>
      <p>{message}{updated && <> Showing what we had at {utc(updated).toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" })}.</>}</p>
      {onRetry && <button type="button" className="btn btn--primary btn--sm" onClick={onRetry} data-testid={`${testid}-retry`}>Try again</button>}
    </div>
  );
}
