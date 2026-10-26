// Loading, empty and error states (docs/04 states). Every data view uses these three.
import { sayError } from "../lib/errors";
import Icon from "./Icon";

export const Loading = ({ label = "Loading", rows = 3 }) => (
  <div className="state state-loading" role="status" aria-live="polite" data-testid="state-loading">
    <span className="sr-only">{label}…</span>
    {[...Array(rows)].map((_, i) => <span key={i} className="skel" style={{ width: `${92 - i * 14}%` }} />)}
  </div>
);
export const Empty = ({ children, icon = "layers", testid = "state-empty" }) => (
  <div className="state state-empty" data-testid={testid}><span className="state-ico"><Icon name={icon} size={22} /></span><p>{children}</p></div>
);
export const ErrorBox = ({ error, onRetry }) => (
  <div className="state state-error" role="alert" data-testid="state-error">
    <span className="state-ico"><Icon name="alert" size={22} /></span>
    <p>{sayError(error)}</p>
    {onRetry && <button className="btn btn--secondary btn--sm" onClick={onRetry} data-testid="state-retry">Try again</button>}
  </div>
);
