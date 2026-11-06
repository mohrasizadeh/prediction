// Admin Money (docs/10 §3.5, docs/14 §3): Subscriptions (cancel / resume), Payments (refund with a reason), Coupons, Revenue.
import { useState } from "react";
import { Link } from "react-router-dom";
import { post } from "../lib/api";
import { useApi } from "../lib/useApi";
import { Confirm, Drawer, Field, FormError, useToast } from "../components/Ui";
import { ErrorBox, Loading, Empty } from "../components/States";
import { Chip, DataState, KV, PageHead, Pager, ResponsiveTable, StatTile, num, when } from "./parts";

const cents = (c, cur) => (c == null ? "No data" : `${(c / 100).toFixed(2)} ${String(cur || "").toUpperCase()}`);
const TONE = { active: "up", trialing: "up", past_due: "warn", canceled: "muted", succeeded: "up", paid: "up", refunded: "warn", failed: "down" };

const Who = ({ r, onOpen }) => (r.user_id && r.email !== "Deleted member"
  ? <button type="button" className="a-link" onClick={(e) => { e.stopPropagation(); onOpen(r.user_id); }} data-testid={`member-open-${r.id}`}>{r.email || r.user_id}</button>
  : <span>{r.email || "Deleted member"}</span>);

function MemberPanel({ id, onClose }) {
  const q = useApi(id ? `/admin/users/${id}` : null);
  const d = q.data;
  const p = d?.profile || {};
  return (
    <Drawer open={!!id} onClose={onClose} title={p.email || "Member"} testid="member-panel" wide>
      {q.error ? <ErrorBox error={q.error} onRetry={q.reload} /> : (q.loading || !d) ? <Loading /> : (
        <div className="a-stack">
          <div className="a-person-head"><span className="a-avatar">{(p.display_name || p.email || "?")[0].toUpperCase()}</span><div><strong data-testid="member-email">{p.email}</strong><small data-testid="member-plan">{d.plan?.plan_name} ({d.plan?.source})</small></div></div>
          <Link className="btn btn--secondary btn--sm" to={`/admin/users?open=${id}`} data-testid="member-full-profile">Open full profile</Link>
          <h3 className="a-h3">Subscriptions ({d.subscriptions?.length || 0})</h3>
          {d.subscriptions?.length ? <ResponsiveTable testid="member-subs" rows={d.subscriptions} columns={[
            { key: "plan_key", label: "Plan", primary: true, render: (s) => <b>{s.plan_key} · {s.interval || "month"}</b> },
            { key: "status", label: "Status", render: (s) => <Chip tone={TONE[s.status] || "muted"}>{s.status}{s.cancel_at_period_end ? " (ends)" : ""}</Chip> },
            { key: "end", label: "Period ends", render: (s) => when(s.current_period_end || s.period_end) },
          ]} /> : <Empty>No subscriptions.</Empty>}
          <h3 className="a-h3">Payments ({d.payments?.length || 0})</h3>
          {d.payments?.length ? <ResponsiveTable testid="member-pays" rows={d.payments} columns={[
            { key: "amt", label: "Amount", primary: true, render: (x) => <b>{cents(x.amount_cents ?? x.amount_paid, x.currency)}</b> },
            { key: "status", label: "Status", render: (x) => <Chip tone={TONE[x.status] || "muted"}>{x.status}</Chip> },
            { key: "at", label: "When", render: (x) => when(x.created_at) },
          ]} /> : <Empty>No payments.</Empty>}
        </div>
      )}
    </Drawer>
  );
}

export function Subscriptions() {
  const [member, setMember] = useState(null);
  const toast = useToast();
  const [status, setStatus] = useState("");
  const [page, setPage] = useState(1);
  const [act, setAct] = useState(null);
  const q = useApi("/admin/subscriptions", { status, page });
  const cols = [
    { key: "user", label: "Member", primary: true, render: (r) => <span className="a-person"><b><Who r={r} onOpen={setMember} /></b><small>{r.plan_key} · {r.interval}</small></span> },
    { key: "status", label: "Status", render: (r) => <Chip tone={TONE[r.status] || "muted"}>{r.status}{r.cancel_at_period_end ? " (ends)" : ""}</Chip> },
    { key: "amount", label: "Amount", render: (r) => cents(r.amount_cents ?? r.amount, r.currency) },
    { key: "period_end", label: "Period ends", render: (r) => when(r.period_end || r.current_period_end) },
    { key: "x", label: "", render: (r) => <span onClick={(e) => e.stopPropagation()} role="presentation">{r.cancel_at_period_end
      ? <button className="btn btn--secondary btn--sm" onClick={() => setAct({ r, kind: "resume" })} data-testid={`sub-resume-${r.id}`}>Resume</button>
      : r.status !== "canceled" && <button className="btn btn--ghost btn--sm" onClick={() => setAct({ r, kind: "cancel" })} data-testid={`sub-cancel-${r.id}`}>Cancel at period end</button>}</span> },
  ];
  const go = async () => {
    await post(`/admin/subscriptions/${act.r.id}/${act.kind}`);
    toast(act.kind === "cancel" ? "Cancel sent. The status updates when Stripe confirms." : "Resumed"); setAct(null); q.reload();
  };
  return (
    <div className="a-page" data-testid="admin-subscriptions">
      <PageHead title="Subscriptions" lead="Who pays, on which plan, and when it renews. Test mode." />
      <div className="a-filters"><select aria-label="Status" value={status} onChange={(e) => { setStatus(e.target.value); setPage(1); }} data-testid="sub-status"><option value="">Every status</option>{["active", "trialing", "past_due", "canceled"].map((s) => <option key={s}>{s}</option>)}</select></div>
      <DataState q={q} empty="No subscriptions yet.">{(d) => <><ResponsiveTable columns={cols} rows={d.rows} testid="sub-table" /><Pager page={d.page} limit={d.limit} total={d.total} onPage={setPage} /></>}</DataState>
      <Confirm open={!!act} danger={act?.kind === "cancel"} title={act?.kind === "cancel" ? "Cancel at the end of the period?" : "Resume this subscription?"} body="The member keeps access until the period ends." confirmLabel={act?.kind === "cancel" ? "Cancel subscription" : "Resume"} onClose={() => setAct(null)} onConfirm={go} testid="sub-confirm" />
      <MemberPanel id={member} onClose={() => setMember(null)} />
    </div>
  );
}

export function Payments() {
  const toast = useToast();
  const [member, setMember] = useState(null);
  const [page, setPage] = useState(1);
  const [pick, setPick] = useState(null);
  const [amt, setAmt] = useState("");
  const q = useApi("/admin/payments", { page });
  const cols = [
    { key: "who", label: "Payment", primary: true, render: (r) => <span className="a-person"><b>{cents(r.amount_cents ?? r.amount_paid, r.currency)}</b><small><Who r={r} onOpen={setMember} /> {r.number || ""}</small></span> },
    { key: "status", label: "Status", render: (r) => <Chip tone={TONE[r.status] || "muted"}>{r.status}</Chip> },
    { key: "refunded", label: "Refunded", render: (r) => (r.refunded_cents ? cents(r.refunded_cents, r.currency) : "None") },
    { key: "at", label: "When", render: (r) => when(r.at || r.created_at) },
    { key: "x", label: "", render: (r) => <span onClick={(e) => e.stopPropagation()} role="presentation"><button className="btn btn--ghost btn--sm" disabled={r.status !== "succeeded" && r.status !== "paid"} onClick={() => { setPick(r); setAmt(""); }} data-testid={`pay-refund-${r.id}`}>Refund</button></span> },
  ];
  const go = async (reason) => {
    const amount_cents = amt ? Math.round(Number(amt) * 100) : undefined;
    await post(`/admin/payments/${pick.id}/refund`, { reason, ...(amount_cents ? { amount_cents } : {}) });
    toast("Refund sent to Stripe"); setPick(null); q.reload();
  };
  return (
    <div className="a-page" data-testid="admin-payments">
      <PageHead title="Payments" lead="Every charge from Stripe. Refunds need a reason and go to the audit log." />
      <DataState q={q} empty="No payments yet.">{(d) => <><ResponsiveTable columns={cols} rows={d.rows} testid="pay-table" /><Pager page={d.page} limit={d.limit} total={d.total} onPage={setPage} /></>}</DataState>
      <Confirm open={!!pick} danger title="Refund this payment?" reason="Reason (required)" confirmLabel="Refund" onClose={() => setPick(null)} onConfirm={go} testid="refund-confirm"
               body={pick && <><p>{cents(pick.amount_cents ?? pick.amount_paid, pick.currency)}</p><Field label="Amount to refund (empty = full)" value={amt} onChange={(e) => setAmt(e.target.value.replace(/[^\d.]/g, ""))} inputMode="decimal" testid="refund-amount" /></>} />
      <MemberPanel id={member} onClose={() => setMember(null)} />
    </div>
  );
}

export function Coupons() {
  const toast = useToast();
  const q = useApi("/admin/coupons");
  const [open, setOpen] = useState(false);
  const [f, setF] = useState({ code: "", name: "", percent_off: "", duration: "once" });
  const [err, setErr] = useState(null);
  const [off, setOff] = useState(null);
  const create = async () => {
    setErr(null);
    try { await post("/admin/coupons", { code: f.code.trim().toUpperCase(), name: f.name, percent_off: Number(f.percent_off), duration: f.duration }); toast("Coupon created"); setOpen(false); q.reload(); }
    catch (x) { setErr(x); }
  };
  const cols = [
    { key: "code", label: "Code", primary: true, render: (r) => <span className="a-person"><b>{r.code}</b><small>{r.name}</small></span> },
    { key: "off", label: "Off", render: (r) => (r.percent_off ? `${r.percent_off}%` : cents(r.amount_off_cents, r.currency)) },
    { key: "active", label: "State", render: (r) => <Chip tone={r.active !== false ? "up" : "muted"}>{r.active !== false ? "Active" : "Off"}</Chip> },
    { key: "x", label: "", render: (r) => r.active !== false && <span onClick={(e) => e.stopPropagation()} role="presentation"><button className="btn btn--danger btn--sm" onClick={() => setOff(r)} data-testid={`coupon-off-${r.code}`}>Switch off</button></span> },
  ];
  return (
    <div className="a-page" data-testid="admin-coupons">
      <PageHead title="Coupons" lead="Discount codes people can enter on the Stripe checkout page." actions={<button className="btn btn--primary btn--sm" onClick={() => setOpen(true)} data-testid="coupon-new">New coupon</button>} />
      <DataState q={q} empty="No coupons yet.">{(d) => (d.coupons.length ? <ResponsiveTable columns={cols} rows={d.coupons} rowKey={(r) => r.code} testid="coupon-table" /> : <p className="a-muted">No coupons yet.</p>)}</DataState>
      <Drawer open={open} onClose={() => setOpen(false)} title="New coupon" testid="coupon-drawer" footer={<button className="btn btn--primary" onClick={create} disabled={!f.code || !f.percent_off} data-testid="coupon-save">Create</button>}>
        <div className="a-form">
          <Field label="Code" value={f.code} onChange={(e) => setF({ ...f, code: e.target.value })} testid="coupon-code" />
          <Field label="Name" value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} testid="coupon-name" />
          <Field label="Percent off" value={f.percent_off} inputMode="decimal" onChange={(e) => setF({ ...f, percent_off: e.target.value.replace(/[^\d.]/g, "") })} testid="coupon-percent" />
          <Field label="Duration" as="select" value={f.duration} onChange={(e) => setF({ ...f, duration: e.target.value })} testid="coupon-duration"><option value="once">First payment</option><option value="forever">Every payment</option></Field>
          <FormError error={err} />
        </div>
      </Drawer>
      <Confirm open={!!off} danger title={`Switch off ${off?.code}?`} body="New checkouts can no longer use it." confirmLabel="Switch off" onClose={() => setOff(null)} onConfirm={async () => { await post(`/admin/coupons/${off.code}/deactivate`); setOff(null); toast("Coupon switched off"); q.reload(); }} testid="coupon-confirm" />
    </div>
  );
}

export function Revenue() {
  const [days, setDays] = useState(30);
  const q = useApi("/admin/analytics/revenue", { days });
  return (
    <div className="a-page" data-testid="admin-revenue">
      <PageHead title="Revenue" lead="Monthly recurring revenue, money collected and refunds, per currency. Test mode." actions={<select aria-label="Days" value={days} onChange={(e) => setDays(Number(e.target.value))} data-testid="rev-days">{[7, 30, 90, 365].map((n) => <option key={n} value={n}>Last {n} days</option>)}</select>} />
      <DataState q={q} empty="No revenue yet.">{(d) => (
        <>
          {(d.by_currency || []).length ? d.by_currency.map((c) => (
            <div key={c.currency} className="a-tiles-grid" data-testid={`rev-${c.currency}`}>
              <StatTile label={`MRR (${c.currency.toUpperCase()})`} value={cents(c.mrr_cents, c.currency)} />
              <StatTile label="Paying members" value={num(c.paying)} />
              <StatTile label="Collected" value={cents(c.collected_cents, c.currency)} />
              <StatTile label="Refunded" value={cents(c.refunded_cents, c.currency)} sub={`${num(c.failed_payments)} failed payments`} />
            </div>
          )) : <p className="a-muted">No paying members yet.</p>}
          <details><summary>All numbers</summary><KV obj={d} skip={["by_currency"]} /></details>
        </>
      )}</DataState>
    </div>
  );
}
