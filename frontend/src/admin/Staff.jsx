// Staff (docs/10 §3.4): list with 2FA status, invite (owner), role matrix.
import { useState } from "react";
import { post } from "../lib/api";
import { useAuth } from "../lib/auth";
import { useApi } from "../lib/useApi";
import { Field, FormError, useToast } from "../components/Ui";
import { ErrorBox, Loading } from "../components/States";
import { Card, Chip, PageHead, ResponsiveTable, when } from "./parts";

const COLS = [
  { key: "email", label: "Person", primary: true },
  { key: "role", label: "Role", render: (r) => <Chip tone="brand">{r.role}</Chip> },
  { key: "two_factor", label: "Two-factor", render: (r) => (r.two_factor ? <Chip tone="up">On</Chip> : <Chip tone="down">Not set up</Chip>) },
  { key: "last_login_at", label: "Last sign-in", render: (r) => when(r.last_login_at) },
  { key: "disabled", label: "State", render: (r) => (r.disabled ? "Turned off" : "Active") },
];

function Invite({ onDone }) {
  const toast = useToast();
  const [f, setF] = useState({ email: "", role: "support" });
  const [err, setErr] = useState(null);
  const [link, setLink] = useState(null);
  const submit = async (e) => {
    e.preventDefault(); setErr(null); setLink(null);
    try {
      const r = await post("/admin/staff/invite", f);
      if (r.link) setLink(r.link); else toast("Invite sent");
      setF({ ...f, email: "" }); onDone();
    } catch (x) { setErr(x); }
  };
  return (
    <form className="a-form" onSubmit={submit} data-testid="staff-invite-form">
      <div className="a-form-row">
        <Field label="E-mail" type="email" required value={f.email} onChange={(e) => setF({ ...f, email: e.target.value })} testid="staff-invite-email" />
        <Field label="Role" as="select" value={f.role} onChange={(e) => setF({ ...f, role: e.target.value })} testid="staff-invite-role">{["admin", "support", "analyst"].map((r) => <option key={r}>{r}</option>)}</Field>
      </div>
      <FormError error={err} />
      {link && <div className="a-notice a-notice--warn" data-testid="staff-invite-link"><p>E-mail is off, so here is the set-password link. It is shown once and works once.</p><code className="a-break">{link}</code></div>}
      <button className="btn btn--primary self-start" data-testid="staff-invite-submit">Send invite</button>
    </form>
  );
}

export default function Staff() {
  const q = useApi("/admin/staff");
  const { user } = useAuth();
  if (q.loading && !q.data) return <Loading />;
  if (q.error) return <ErrorBox error={q.error} onRetry={q.reload} />;
  const roles = q.data.roles || {};
  const perms = [...new Set(Object.values(roles).flat().filter((p) => p !== "*"))].sort();
  return (
    <div className="a-page" data-testid="admin-staff">
      <PageHead title="Staff" lead="One person, one account, each with two-factor sign-in." />
      <ResponsiveTable columns={COLS} rows={q.data.staff} testid="staff-table" />
      {user?.role === "owner" && <Card title="Invite a team member" testid="staff-invite"><Invite onDone={q.reload} /></Card>}
      <Card title="What each role can do" testid="role-matrix">
        <div className="a-table-wrap a-matrix">
          <table className="a-table">
            <thead><tr><th scope="col">Permission</th>{Object.keys(roles).map((r) => <th key={r} scope="col">{r}</th>)}</tr></thead>
            <tbody>{perms.map((p) => <tr key={p}><td><code>{p}</code></td>{Object.entries(roles).map(([r, list]) => <td key={r} className="a-center">{list.includes("*") || list.includes(p) ? <span aria-label="yes" className="a-yes">●</span> : <span aria-label="no" className="a-no">·</span>}</td>)}</tr>)}</tbody>
          </table>
        </div>
      </Card>
    </div>
  );
}
