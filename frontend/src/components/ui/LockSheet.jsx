// Locked features (docs/24 §15): a small "Part of Pro" tag that opens the plan as a bottom sheet, not a new page.
import { useState } from "react";
import { Link } from "react-router-dom";
import { useApi } from "../../lib/useApi";
import Icon from "../Icon";
import { BottomSheet } from "./BottomSheet";

const money = (c, cur) => new Intl.NumberFormat(undefined, { style: "currency", currency: (cur || "usd").toUpperCase() }).format(c / 100);

export function LockSheet({ open, onClose, title, testid = "pro-sheet" }) {
  const q = useApi(open ? "/plans" : null);
  const plans = q.data?.plans || [];
  const pro = plans.find((p) => p.highlight) || plans[plans.length - 1];
  const price = (pro?.prices || []).find((x) => x.interval === "month" && x.active !== false);
  return (
    <BottomSheet open={open} onClose={onClose} title={title || `Part of ${pro?.name || "Pro"}`} testid={testid}
      footer={<><Link to="/pricing" className="btn btn--primary" onClick={onClose} data-testid={`${testid}-see`}>See {pro?.name || "plans"}{price ? ` · ${money(price.amount_cents, price.currency)} a month` : ""}</Link>
        <button type="button" className="btn btn--ghost" onClick={onClose} data-testid={`${testid}-later`}>Not now</button></>}>
      {q.loading && !q.data ? <p className="k-faint">Loading the plan…</p> : q.error ? <p className="k-faint">We could not load the plan. <Link to="/pricing">See plans</Link></p> : (
        <>
          {pro?.tagline && <p className="k-faint">{pro.tagline}</p>}
          <ul className="lk-list" data-testid={`${testid}-list`}>{(pro?.bullets || []).map((b) => <li key={b}><Icon name="check" size={16} />{b}</li>)}</ul>
          {pro?.trial_days > 0 && <p className="k-faint k-small">{pro.trial_days}-day free trial. Cancel any time from your account.</p>}
        </>
      )}
    </BottomSheet>
  );
}

export function ProLock({ label = "Part of Pro", title, testid = "pro-tag" }) {
  const [open, setOpen] = useState(false);
  return (
    <>
      <button type="button" className="lk-tag" onClick={() => setOpen(true)} data-testid={testid}><Icon name="padlock" size={14} />{label}</button>
      <LockSheet open={open} onClose={() => setOpen(false)} title={title} testid={`${testid}-sheet`} />
    </>
  );
}
