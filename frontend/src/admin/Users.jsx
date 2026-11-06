// Users (docs/10 §3.3): filters, responsive table, user drawer with actions. Every action is checked on the server.
import { useState } from "react";
import { useSearchParams } from "react-router-dom";
import { post, del } from "../lib/api";
import { useAuth } from "../lib/auth";
import { useApi } from "../lib/useApi";
import { Confirm, Drawer, Field, useToast } from "../components/Ui";
import { ErrorBox, Loading, Empty } from "../components/States";
import Icon from "../components/Icon";
import { Chip, DataState, KV, PageHead, Pager, ResponsiveTable, when } from "./parts";

const flags = (r) => (
  <span className="a-flags">
    {r.two_factor && <Chip tone="up">2FA</Chip>}
    {r.disabled && <Chip tone="down">Off</Chip>}
    {!r.email_verified && <Chip tone="warn">Unverified</Chip>}
  </span>
);
const COLS = [
  { key: "email", label: "Person", primary: true, render: (r) => <span className="a-person"><b>{r.display_name || r.email}</b>{r.display_name && <small>{r.email}</small>}</span> },
  { key: "plan", label: "Plan", render: (r) => <Chip>{r.plan}{r.plan_source === "comp" ? " (comp)" : ""}</Chip> },
  { key: "role", label: "Role" },
  { key: "created_at", label: "Created", render: (r) => when(r.created_at) },
  { key: "last_login_at", label: "Last sign-in", render: (r) => when(r.last_login_at) },
  { key: "flags", label: "Flags", render: flags },
];

const DANGER = new Set(["disable", "logout", "uncomp", "reset2fa", "purge"]);

function UserDrawer({ id, onClose, onChanged }) {
  const q = useApi(id ? `/admin/users/${id}` : null);
  const { user: me } = useAuth();
  const toast = useToast();
  const [dlg, setDlg] = useState(null);
  const [comp, setComp] = useState({ plan: "pro", days: 30 });
  const [role, setRole] = useState("support");
  const owner = me?.role === "owner";
  const run = async (fn, msg) => { await fn(); toast(msg); setDlg(null); q.reload(); onChanged(); };
  const d = q.data;
  const p = d?.profile || {};
  const actions = d && [
    ["note", "Add note", "edit", () => setDlg({ title: "Add a note", reason: "Note", ok: "Save note", go: (t) => run(() => post(`/admin/users/${id}/notes`, { text: t }), "Note added") })],
    p.disabled
      ? ["enable", "Turn on", "check", () => run(() => post(`/admin/users/${id}/enable`, { reason: "enabled from admin" }), "Account turned on")]
      : ["disable", "Turn off", "padlock", () => setDlg({ title: "Turn this account off?", body: "They are signed out everywhere.", reason: "Reason (required)", danger: true, ok: "Turn off", go: (t) => run(() => post(`/admin/users/${id}/disable`, { reason: t }), "Account turned off") })],
    // These three reach the member: two put real e-mail in a real inbox and one ends their
    // sessions mid-task. All three used to fire on the first click, in the same grid as "Add note",
    // which asked. The audit called that out as the clearest mis-grading in the admin.
    ["logout", "Sign out everywhere", "log-out", () => setDlg({ title: "Sign this person out everywhere?", body: "Every device signs out at once, including whatever they are in the middle of. They can sign back in with their password.", reason: "Reason (required)", danger: true, ok: "Sign out everywhere", go: (t) => run(() => post(`/admin/users/${id}/logout`, { reason: t }), "Signed out everywhere") })],
    !p.email_verified && ["resend", "Resend verification", "mail", () => setDlg({ title: "Send the verification e-mail again?", body: `This puts a fresh confirmation link in ${p.email}'s inbox. Any earlier link stops working.`, ok: "Send it", go: () => run(() => post(`/admin/users/${id}/resend-verification`), "Verification sent") })],
    ["reset", "Send password-reset e-mail", "key", () => setDlg({ title: "Send a password-reset e-mail?", body: `This puts a reset link in ${p.email}'s inbox. It works once, and it does not change their password by itself.`, ok: "Send it", go: () => run(() => post(`/admin/users/${id}/send-reset`), "Reset e-mail sent") })],
    ["comp", "Give a plan free", "gift", () => setDlg({ title: "Give a plan free", comp: true, reason: "Reason (required)", ok: "Give plan", go: (t) => run(() => post(`/admin/users/${id}/comp`, { plan: comp.plan, days: Number(comp.days), reason: t }), "Plan given") })],
    d.plan?.source === "comp" && ["uncomp", "Remove free plan", "x", () => setDlg({ title: "Remove the free plan?", reason: "Reason (required)", danger: true, ok: "Remove", go: (t) => run(() => post(`/admin/users/${id}/comp/revoke`, { reason: t }), "Free plan removed") })],
    owner && ["role", "Change role", "shield", () => setDlg({ title: "Change role", role: true, ok: "Change role", body: "Changing the role signs the person out.", go: () => run(() => post(`/admin/users/${id}/role`, { role }), "Role changed") })],
    owner && p.two_factor && ["reset2fa", "Reset two-factor", "refresh", () => setDlg({ title: "Reset their two-factor?", danger: true, ok: "Reset", body: "They must set it up again at next sign-in.", go: () => run(() => post(`/admin/users/${id}/reset-2fa`), "Two-factor reset") })],
    owner && ["purge", "Delete their data", "trash", () => setDlg({ title: "Delete this person's data?", danger: true, typed: "DELETE", ok: "Delete for good", body: "Removes the account and personal data. Payment records stay unlinked.", go: async () => { await del(`/admin/users/${id}/purge`); toast("Data deleted"); setDlg(null); onChanged(); onClose(); } })],
  ].filter(Boolean);
  return (
    <Drawer open={!!id} onClose={onClose} title={p.display_name || p.email || "Person"} testid="user-drawer" wide>
      {q.error ? <ErrorBox error={q.error} onRetry={q.reload} /> : (q.loading || !d) ? <Loading /> : (
        <div className="a-stack">
          <div className="a-person-head"><span className="a-avatar">{(p.display_name || p.email || "?")[0].toUpperCase()}</span><div><strong>{p.email}</strong><small>{p.role} · {d.plan?.plan_name} ({d.plan?.source})</small></div>{flags(p)}</div>
          {/* btn--danger on the triggers that destroy or cut something off, so the grid stops
              reading as thirteen equivalent options. */}
          <div className="a-actions-grid">{actions.map(([k, l, i, fn]) => <button key={k} className={"btn btn--sm " + (DANGER.has(k) ? "btn--danger" : "btn--secondary")} onClick={fn} data-testid={`user-action-${k}`}><Icon name={i} size={16} />{l}</button>)}</div>
          <details open><summary>Profile</summary><KV obj={p} /></details>
          <details><summary>Limits in force</summary><KV obj={d.entitlements} /></details>
          <details><summary>Devices ({d.sessions?.length || 0})</summary>{d.sessions?.length ? d.sessions.map((s) => <KV key={s.sid} obj={s} />) : <Empty>No sessions.</Empty>}</details>
          <details><summary>Sign-in history ({d.sign_ins?.length || 0})</summary>{d.sign_ins?.length ? d.sign_ins.map((s, i) => <KV key={i} obj={s} />) : <Empty>No sign-ins yet.</Empty>}</details>
          <details><summary>E-mails sent ({d.emails?.length || 0})</summary>{d.emails?.length ? d.emails.map((s, i) => <KV key={i} obj={s} />) : <Empty>No e-mails.</Empty>}</details>
          <details><summary>Subscriptions and payments</summary>{[...(d.subscriptions || []), ...(d.payments || [])].length ? [...d.subscriptions, ...d.payments].map((s) => <KV key={s.id} obj={s} />) : <Empty>None.</Empty>}</details>
          <details><summary>Notes and counts</summary><KV obj={{ ...(d.counts || {}), notes: (d.notes || []).map((n) => n.text).join(" · ") }} /></details>
        </div>
      )}
      <Confirm open={!!dlg} title={dlg?.title} danger={dlg?.danger} reason={dlg?.reason} typed={dlg?.typed} confirmLabel={dlg?.ok} onClose={() => setDlg(null)} onConfirm={(t) => dlg.go(t)} testid="user-dialog"
               body={<>{dlg?.body && <p>{dlg.body}</p>}
                 {dlg?.comp && <div className="a-form-row"><Field label="Plan" value={comp.plan} onChange={(e) => setComp({ ...comp, plan: e.target.value })} testid="comp-plan" /><Field label="Days" type="number" min={1} max={3650} value={comp.days} onChange={(e) => setComp({ ...comp, days: e.target.value })} testid="comp-days" /></div>}
                 {dlg?.role && <Field label="New role" as="select" value={role} onChange={(e) => setRole(e.target.value)} testid="role-select">{["user", "analyst", "support", "admin", "owner"].map((r) => <option key={r}>{r}</option>)}</Field>}</>} />
    </Drawer>
  );
}

export default function Users() {
  const [f, setF] = useState({ q: "", role: "", plan: "", verified: "", disabled: "", page: 1 });
  const [sp, setSp] = useSearchParams();
  const [open, setOpenRaw] = useState(sp.get("open"));
  const setOpen = (v) => { setOpenRaw(v); if (!v && sp.get("open")) setSp({}, { replace: true }); };
  const q = useApi("/admin/users", f);
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value, page: 1 });
  return (
    <div className="a-page" data-testid="admin-users">
      <PageHead title="Users" lead={q.data ? `${q.data.total.toLocaleString()} ${q.data.total === 1 ? "person" : "people"}` : " "} />
      <div className="a-filters">
        <div className="a-search"><Icon name="search" size={18} /><input type="search" placeholder="Search by name, id or e-mail" aria-label="Search people" value={f.q} onChange={set("q")} data-testid="users-search" /></div>
        <select aria-label="Role" value={f.role} onChange={set("role")} data-testid="users-filter-role"><option value="">Any role</option>{["user", "analyst", "support", "admin", "owner"].map((r) => <option key={r}>{r}</option>)}</select>
        <select aria-label="Plan" value={f.plan} onChange={set("plan")} data-testid="users-filter-plan"><option value="">Any plan</option>{["free", "paid", "trial", "past_due", "comp"].map((r) => <option key={r} value={r}>{r.replace("_", " ")}</option>)}</select>
        <select aria-label="Verified" value={f.verified} onChange={set("verified")} data-testid="users-filter-verified"><option value="">Verified or not</option><option value="true">Verified</option><option value="false">Unverified</option></select>
        <select aria-label="Turned off" value={f.disabled} onChange={set("disabled")} data-testid="users-filter-disabled"><option value="">On or off</option><option value="false">On</option><option value="true">Turned off</option></select>
      </div>
      <DataState q={q} empty="No one matches these filters.">
        {(d) => <><ResponsiveTable columns={COLS} rows={d.rows} onRow={(r) => setOpen(r.id)} testid="users-table" /><Pager page={d.page} limit={d.limit} total={d.total} onPage={(p) => setF({ ...f, page: p })} /></>}
      </DataState>
      <UserDrawer id={open} onClose={() => setOpen(null)} onChanged={q.reload} />
    </div>
  );
}
