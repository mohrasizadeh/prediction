// Plans (docs/24 §15, docs/14): plain rows with ticks built from each plan's limits. Checkout is Stripe-hosted.
// No countdowns or scarcity copy (doc 03).
import { useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { post } from "../lib/api";
import { useApi } from "../lib/useApi";
import { useAuth } from "../lib/auth";
import { FormError } from "../components/Ui";
import Icon from "../components/Icon";
import { useTitle } from "../components/Football";
import { EmptyState, ErrorState, Segmented, Skeleton } from "../components/ui";

const money = (c, cur) => new Intl.NumberFormat(undefined, { style: "currency", currency: (cur || "usd").toUpperCase(), maximumFractionDigits: c % 100 ? 2 : 0 }).format(c / 100);
const ROWS = [
  ["Today, Live and match pages", () => true], ["Finder searches a day", "finder_searches_per_day"], ["Leagues in one Finder search", "finder_leagues"],
  ["Insights a day", "insights_per_day"], ["Games in the squad grid", "grid_games"], ["Follows", "follows_max"], ["Saved forecasts", "saved_max"],
  ["Player notes", "notes_max"], ["Alerts for teams and players", "alerts"], ["Tactical matchup tab", "matchup_tab"], ["CSV export", "export"],
];

function Val({ v }) {
  if (v === true) return <Icon name="check" size={18} />;
  if (v === false || v == null || v === 0) return <span aria-label="Not included">—</span>;
  return v < 0 ? <b className="pr-unl">Unlimited</b> : <b>{v}</b>;
}

function PlanCard({ p, interval, current, onBuy, busy, currency, signedIn }) {
  const price = (p.prices || []).find((x) => x.interval === interval && x.active !== false);
  const free = !p.prices?.length;
  const e = p.entitlements || {};
  return (
    <article className={`pr-card card${p.highlight ? " pr-card--hi" : ""}`} data-testid={`plan-${p.key}`}>
      <header><h2>{p.name}</h2>{p.highlight && <span className="k-tag">Most complete</span>}</header>
      <p className="pr-price">{free ? <>{money(0, currency)}<small> forever</small></> : price ? (price.interval === "year"
        ? <>{money(Math.round(price.amount_cents / 12), price.currency)}<small> a month, billed yearly ({money(price.amount_cents, price.currency)})</small></>
        : <>{money(price.amount_cents, price.currency)}<small> a month</small></>) : "Not offered"}</p>
      {p.tagline && <p className="k-faint">{p.tagline}</p>}
      {!free && p.trial_days > 0 && <p className="k-faint k-small" data-testid={`plan-trial-${p.key}`}>{p.trial_days}-day free trial</p>}
      <ul className="pr-rows">{ROWS.map(([label, k]) => {
        const v = typeof k === "function" ? k() : e[k];
        const off = v === false || v == null || v === 0;
        return <li key={label} className={off ? "off" : ""} data-testid={`plan-${p.key}-row-${typeof k === "string" ? k : "pages"}`}><span>{label}</span><Val v={v} /></li>;
      })}</ul>
      {current ? <span className="btn btn--secondary btn--block" aria-disabled="true" data-testid={`plan-current-${p.key}`}>Current plan</span>
        : free ? (!signedIn && <Link to="/sign-up" className="btn btn--secondary btn--block" data-testid={`plan-start-${p.key}`}>Start free</Link>)
        : price && <button type="button" className="btn btn--primary btn--block" disabled={busy} onClick={() => onBuy(p, price)} data-testid={`plan-buy-${p.key}`}>{busy ? "Opening checkout…" : `Choose ${p.name}`}</button>}
    </article>
  );
}

export default function Pricing() {
  const q = useApi("/plans");
  const { user, me } = useAuth();
  const nav = useNavigate();
  const [sp] = useSearchParams();
  const [interval, setInterval] = useState("month");
  const [state, setState] = useState({ busy: null, err: null });
  useTitle("Plans");
  const buy = async (p, price) => {
    if (!user) return nav("/sign-in?next=/pricing");
    setState({ busy: p.key, err: null });
    try { const r = await post("/billing/checkout", { plan: p.key, price: price.id }); window.location.assign(r.url); }
    catch (x) { setState({ busy: null, err: x }); }
  };
  const d = q.data;
  const yearly = d?.plans.some((p) => (p.prices || []).some((x) => x.interval === "year"));
  return (
    <section className="pr" data-testid="pricing-page">
      <h1>Plans</h1>
      <p className="k-faint lead">Start free. Upgrade when you want more depth.</p>
      {sp.get("status") === "cancelled" && <p className="notice" data-testid="checkout-cancelled"><Icon name="info" size={16} />Checkout was cancelled. Nothing was charged.</p>}
      {q.loading && !d ? <Skeleton shape="card" count={2} testid="pricing-loading" /> : q.error ? <ErrorState message="We could not load the plans." onRetry={q.reload} testid="pricing-error" />
        : !d.billing_enabled ? <EmptyState icon="tag" title="Paid plans are not open yet" testid="pricing-off">Every signed-in person gets the full plan for now.</EmptyState>
        : !d.plans.length ? <EmptyState icon="tag" title="No plans listed" testid="pricing-empty">Check back soon.</EmptyState> : (
          <>
            {yearly && <Segmented label="Billing period" value={interval} onChange={setInterval} options={[{ id: "month", label: "Monthly" }, { id: "year", label: "Yearly" }]} testid="pricing-interval" />}
            <FormError error={state.err} />
            <div className="pr-grid">{d.plans.map((p) => <PlanCard key={p.key} p={p} interval={interval} currency={d.currency} signedIn={!!user}
              current={user && (me?.plan?.plan_key === p.key)} onBuy={buy} busy={state.busy === p.key} />)}</div>
            <p className="k-faint k-small">Cancel any time from your account. Prices in {(d.currency || "usd").toUpperCase()}. Payments are handled by Stripe on its own secure page. {user ? <Link to="/account/plan" data-testid="pricing-manage">Manage your plan</Link> : <Link to="/sign-in?next=/pricing" data-testid="pricing-signin">Sign in to choose a plan</Link>}</p>
          </>
        )}
    </section>
  );
}
