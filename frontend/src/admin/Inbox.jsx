// Inbox (docs/10 §3.9): contact-form messages with status and a private note. No auto-reply is sent.
import { useState } from "react";
import { put } from "../lib/api";
import { useApi } from "../lib/useApi";
import { Drawer, Field, FormError, Tabs, useToast } from "../components/Ui";
import { Chip, DataState, PageHead, Pager, ResponsiveTable, when } from "./parts";

const STATUSES = ["new", "read", "replied", "spam", "closed"];
const COLS = [
  { key: "email", label: "From", primary: true, render: (r) => <span className="a-person"><b>{r.name || r.email}</b><small>{(r.message || "").slice(0, 80)}</small></span> },
  { key: "status", label: "Status", render: (r) => <Chip tone={r.status === "new" ? "brand" : "muted"}>{r.status}</Chip> },
  { key: "at", label: "Received", render: (r) => when(r.at || r.created_at) },
];

function Message({ m, onClose, onSaved }) {
  const toast = useToast();
  const [f, setF] = useState({ status: m?.status || "read", note: m?.note || "" });
  const [err, setErr] = useState(null);
  const save = async () => { try { await put(`/admin/inbox/${m.id}`, f); toast("Saved"); onSaved(); onClose(); } catch (x) { setErr(x); } };
  return (
    <Drawer open={!!m} onClose={onClose} title={m?.name || m?.email || "Message"} testid="inbox-drawer"
            footer={<button className="btn btn--primary" onClick={save} data-testid="inbox-save">Save</button>}>
      {m && (
        <div className="a-stack">
          <p className="a-muted">{m.email} · {when(m.at || m.created_at)}</p>
          <blockquote className="a-quote" data-testid="inbox-message">{m.message}</blockquote>
          <Field label="Status" as="select" value={f.status} onChange={(e) => setF({ ...f, status: e.target.value })} testid="inbox-status">{STATUSES.map((s) => <option key={s}>{s}</option>)}</Field>
          <Field label="Private note" as="textarea" rows={4} maxLength={500} value={f.note} onChange={(e) => setF({ ...f, note: e.target.value })} testid="inbox-note" />
          <FormError error={err} />
        </div>
      )}
    </Drawer>
  );
}

export default function Inbox() {
  const [status, setStatus] = useState("");
  const [page, setPage] = useState(1);
  const [open, setOpen] = useState(null);
  const q = useApi("/admin/inbox", { status, page });
  return (
    <div className="a-page" data-testid="admin-inbox">
      <PageHead title="Inbox" lead="Messages from the contact form." />
      <Tabs tabs={[{ id: "", label: "All" }, ...STATUSES.map((s) => ({ id: s, label: s[0].toUpperCase() + s.slice(1) }))]} value={status} onChange={(s) => { setStatus(s); setPage(1); }} testid="inbox-tabs" />
      <DataState q={q} empty="No messages here.">
        {(d) => <><ResponsiveTable columns={COLS} rows={d.rows} onRow={setOpen} testid="inbox-table" /><Pager page={d.page} limit={d.limit} total={d.total} onPage={setPage} /></>}
      </DataState>
      {open && <Message key={open.id} m={open} onClose={() => setOpen(null)} onSaved={q.reload} />}
    </div>
  );
}
