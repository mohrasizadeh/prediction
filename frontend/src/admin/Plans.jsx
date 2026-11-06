// Plans (docs/10 §3.5): cards with subscriber counts, editor with entitlements grid and prices. Sync to Stripe stays
// disabled until phase 4b.
import { useState } from "react";
import { post, put } from "../lib/api";
import { useApi } from "../lib/useApi";
import { Drawer, Field, FormError, Switch, useToast } from "../components/Ui";
import { ErrorBox, Loading } from "../components/States";
import Icon from "../components/Icon";
import { Chip, Guard, PageHead } from "./parts";

const lim = (v) => (v === -1 ? "No limit" : typeof v === "boolean" ? (v ? "On" : "Off") : v);

// This creates real products and real prices in the connected Stripe account, and a Stripe price
// cannot be edited afterwards -- only archived and replaced. It was an unguarded ghost button beside
// "Edit", on a screen whose own header comment says the sync is meant to be off.
function SyncButton({ k, name }) {
  const toast = useToast();
  return (
    <Guard className="btn btn--danger btn--sm" label="Sync to Stripe" busyLabel="Syncing…" confirmLabel="Create them in Stripe" danger
           title={`Create ${name || k} and its prices in Stripe?`}
           body={<p>This writes to the connected Stripe account. A price in Stripe cannot be changed once it exists, only archived and replaced, so a wrong amount here leaves a wrong price behind for good. Check the amounts and the currency under <b>Edit</b> first.</p>}
           onRun={async () => { await post(`/admin/plans/${k}/sync`); toast("Plan and prices synced to Stripe"); }}
           testid={`plan-sync-${k}`} />
  );
}

function Editor({ plan, cat, onClose, onSaved }) {
  const toast = useToast();
  const [f, setF] = useState({ name: plan.name, tagline: plan.tagline || "", bullets: (plan.bullets || []).join("\n"), visible: plan.visible, highlight: plan.highlight, sort: plan.sort ?? 0,
    trial_days: plan.trial_days ?? "", entitlements: { ...plan.entitlements }, prices: (plan.prices || []).map((p) => ({ ...p })) });
  const [err, setErr] = useState(null);
  const ent = (k, v) => setF({ ...f, entitlements: { ...f.entitlements, [k]: v } });
  const price = (i, k, v) => setF({ ...f, prices: f.prices.map((p, j) => (j === i ? { ...p, [k]: v } : p)) });
  const save = async () => {
    setErr(null);
    const body = { name: f.name, tagline: f.tagline, bullets: f.bullets.split("\n").map((s) => s.trim()).filter(Boolean), visible: f.visible, highlight: f.highlight, sort: Number(f.sort),
      trial_days: f.trial_days === "" ? null : Number(f.trial_days), entitlements: f.entitlements };
    if (plan.key !== "free") body.prices = f.prices;
    try { await put(`/admin/plans/${plan.key}`, body); toast("Plan saved"); onSaved(); onClose(); } catch (x) { setErr(x); }
  };
  return (
    <Drawer open onClose={onClose} title={`Edit ${plan.name}`} testid="plan-drawer" wide footer={<button className="btn btn--primary" onClick={save} data-testid="plan-save">Save plan</button>}>
      <div className="a-stack">
        <div className="a-form-row"><Field label="Name" maxLength={40} value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} testid="plan-name" /><Field label="Sort" type="number" value={f.sort} onChange={(e) => setF({ ...f, sort: e.target.value })} testid="plan-sort" /></div>
        <Field label="Tagline" maxLength={140} value={f.tagline} onChange={(e) => setF({ ...f, tagline: e.target.value })} testid="plan-tagline" />
        <Field label="Bullets (one per line)" as="textarea" rows={4} value={f.bullets} onChange={(e) => setF({ ...f, bullets: e.target.value })} testid="plan-bullets" />
        <div className="a-form-row">
          <Switch label="Shown on the pricing page" checked={f.visible} onChange={(v) => setF({ ...f, visible: v })} testid="plan-visible" />
          <Switch label="Highlighted" checked={f.highlight} onChange={(v) => setF({ ...f, highlight: v })} testid="plan-highlight" />
        </div>
        <Field label="Trial days (blank = site default)" type="number" min={0} max={365} value={f.trial_days} onChange={(e) => setF({ ...f, trial_days: e.target.value })} testid="plan-trial" />
        <fieldset className="a-node"><legend>What this plan includes</legend>
          <div className="a-ent-grid">
            {Object.entries(cat).map(([k, c]) => (c.kind === "bool"
              ? <Switch key={k} label={c.label} checked={!!f.entitlements[k]} onChange={(v) => ent(k, v)} testid={`ent-${k}`} />
              : <Field key={k} label={`${c.label} (-1 = no limit)`} type="number" min={-1} value={f.entitlements[k] ?? ""} onChange={(e) => ent(k, e.target.value === "" ? "" : Number(e.target.value))} testid={`ent-${k}`} />))}
          </div>
        </fieldset>
        {plan.key !== "free" && (
          <fieldset className="a-node"><legend>Prices</legend>
            <p className="a-notice a-notice--warn"><Icon name="alert" size={16} />A price change makes a new Stripe price and retires the old one. People already subscribed keep their old price.</p>
            {f.prices.map((p, i) => (
              <div key={i} className="a-form-row a-price-row">
                <Field label="Id" value={p.id || ""} onChange={(e) => price(i, "id", e.target.value)} testid={`price-${i}-id`} />
                <Field label="Interval" as="select" value={p.interval || "month"} onChange={(e) => price(i, "interval", e.target.value)} testid={`price-${i}-interval`}><option>month</option><option>year</option></Field>
                <Field label="Amount" type="number" step="0.01" min={0} value={((p.amount_cents || 0) / 100).toFixed(2)} onChange={(e) => price(i, "amount_cents", Math.round(Number(e.target.value) * 100))} testid={`price-${i}-amount`} />
                <Field label="Currency" value={p.currency || "CAD"} maxLength={3} onChange={(e) => price(i, "currency", e.target.value.toUpperCase())} testid={`price-${i}-currency`} />
                <Switch label="Active" checked={p.active !== false} onChange={(v) => price(i, "active", v)} testid={`price-${i}-active`} />
              </div>
            ))}
          </fieldset>
        )}
        <FormError error={err} />
      </div>
    </Drawer>
  );
}

export default function Plans() {
  const q = useApi("/admin/plans");
  const [edit, setEdit] = useState(null);
  if (q.loading && !q.data) return <Loading rows={4} />;
  if (q.error) return <ErrorBox error={q.error} onRetry={q.reload} />;
  const { plans, entitlements } = q.data;
  return (
    <div className="a-page" data-testid="admin-plans">
      <PageHead title="Plans" lead="What each plan includes and costs. After changing prices, press Sync to Stripe so checkout uses them." />
      <div className="a-plan-grid">
        {plans.filter((p) => !p.archived).map((p) => (
          <article key={p.key} className={"a-card a-plan" + (p.highlight ? " is-hi" : "")} data-testid={`plan-${p.key}`}>
            <header><h2>{p.name}</h2>{!p.visible && <Chip>Hidden</Chip>}{p.highlight && <Chip tone="brand">Highlighted</Chip>}</header>
            <p className="a-muted">{p.tagline}</p>
            <p className="a-plan-subs"><strong>{p.subscribers}</strong> subscribed</p>
            <ul className="a-plan-ents">{Object.entries(p.entitlements || {}).slice(0, 6).map(([k, v]) => <li key={k}><span>{entitlements[k]?.label || k}</span><b>{lim(v)}</b></li>)}</ul>
            {p.prices?.length > 0 && <p className="a-plan-prices">{p.prices.map((x) => `${((x.amount_cents || 0) / 100).toFixed(2)} ${x.currency || ""}/${x.interval}`).join(" · ")}</p>}
            <div className="a-btns">
              <button className="btn btn--secondary btn--sm" onClick={() => setEdit(p)} data-testid={`plan-edit-${p.key}`}><Icon name="edit" size={16} />Edit</button>
              {p.key !== "free" && <SyncButton k={p.key} name={p.name} />}
            </div>
          </article>
        ))}
      </div>
      {edit && <Editor plan={edit} cat={entitlements} onClose={() => setEdit(null)} onSaved={q.reload} />}
    </div>
  );
}
