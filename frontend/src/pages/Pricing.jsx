// Pricing (docs/13 §2, docs/14): plans from GET /api/plans; checkout is Stripe-hosted (POST /api/billing/checkout returns {url}).
import { useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { post } from "../lib/api";
import { useApi } from "../lib/useApi";
import { useAuth } from "../lib/auth";
import { Empty, ErrorBox, Loading } from "../components/States";
import { FormError } from "../components/Ui";
import Icon from "../components/Icon";
import { Seg, useTitle } from "../components/Football";

const money = (c, cur) => new Intl.NumberFormat(undefined, { style: "currency", currency: (cur || "usd").toUpperCase() }).format(c / 100);

function PlanCard({ p, interval, current, onBuy, busy }) {
  const price = (p.prices || []).find((x) => x.interval === interval && x.active !== false);
  const free = !p.prices?.length;
  return (
    <article className={"pcard" + (p.highlight ? " pcard--hi" : "")} data-testid={`plan-${p.key}`}>
      {p.highlight && <span className="chip-tag chip-tag--brand pcard-tag">Most complete</span>}
      <h2>{p.name}</h2>
      {p.tagline && <p className="muted">{p.tagline}</p>}
      <p className="pcard-price">{free ? money(0, "usd").replace(/[\d.,]+/, "0") : price ? <>{money(price.amount_cents, price.currency)}<small> / {price.interval}</small></> : "Not offered"}</p>
      {price?.interval === "year" && <p className="muted small">{money(Math.round(price.amount_cents / 12), price.currency)} a month, billed yearly</p>}
      <ul className="pcard-list">{(p.bullets || []).map((b) => <li key={b}><Icon name="check" size={16} />{b}</li>)}</ul>
      {current ? <span className="btn btn--secondary btn--block" aria-disabled="true" data-testid={`plan-current-${p.key}`}>Your plan</span>
        : !free && price && <button className="btn btn--primary btn--block" disabled={busy} onClick={() => onBuy(p, price)} data-testid={`plan-buy-${p.key}`}>{busy ? "Opening checkout…" : `Choose ${p.name}`}</button>}
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
  useTitle("Pricing");
  const buy = async (p, price) => {
    if (!user) return nav("/sign-in?next=/pricing");
    setState({ busy: p.key, err: null });
    try { const r = await post("/billing/checkout", { plan: p.key, price: price.id }); window.location.assign(r.url); }
    catch (x) { setState({ busy: null, err: x }); }
  };
  if (q.loading && !q.data) return <Loading rows={4} />;
  if (q.error) return <ErrorBox error={q.error} onRetry={q.reload} />;
  const d = q.data;
  const yearly = d.plans.some((p) => (p.prices || []).some((x) => x.interval === "year"));
  return (
    <section data-testid="pricing-page">
      <h1>Pricing</h1>
      <p className="muted lead">Pick the plan that fits how deep you go. Cancel any time from your account.</p>
      {sp.get("status") === "cancelled" && <p className="notice" data-testid="checkout-cancelled"><Icon name="info" size={16} />Checkout was cancelled. Nothing was charged.</p>}
      {!d.billing_enabled ? <Empty icon="tag" testid="pricing-off">Paid plans are not open yet. Every signed-in person gets the full plan for now.</Empty> : (
        <>
          {yearly && <Seg label="Billing period" value={interval} onChange={setInterval} options={[{ id: "month", label: "Monthly" }, { id: "year", label: "Yearly" }]} testid="pricing-interval" />}
          <FormError error={state.err} />
          <div className="pgrid">{d.plans.map((p) => <PlanCard key={p.key} p={p} interval={interval} current={user && me?.plan?.plan_key === p.key} onBuy={buy} busy={state.busy === p.key} />)}</div>
          <p className="muted small">Payments are handled by Stripe on its own secure page. Test mode: use card 4242 4242 4242 4242. {user ? <Link to="/account/plan">Manage your plan</Link> : <Link to="/sign-in?next=/pricing">Sign in to choose a plan</Link>}</p>
        </>
      )}
    </section>
  );
}
