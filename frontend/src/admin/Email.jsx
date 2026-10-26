// Admin E-mail (docs/14 §4): Templates (edit, reset, preview, send test to me), Blocked addresses, Campaigns.
import { useState } from "react";
import { del, get, post, put } from "../lib/api";
import { useApi } from "../lib/useApi";
import { Confirm, Drawer, Field, FormError, useToast } from "../components/Ui";
import { Chip, DataState, PageHead, Pager, ResponsiveTable, when } from "./parts";

function Editor({ k, onClose, onSaved }) {
  const toast = useToast();
  const q = useApi(k ? `/admin/email/templates/${k}` : null);
  const [edit, setEdit] = useState(null);
  const [err, setErr] = useState(null);
  const [prev, setPrev] = useState(null);
  const t = { ...(q.data || {}), ...(edit || {}) };
  const fields = ["subject", "html", "text"].filter((f) => f in (q.data || {}));
  const act = async (fn, msg) => { setErr(null); try { const r = await fn(); if (r?.status && r.status !== "sent" && r.status !== "ok" && msg.startsWith("Test")) { setErr(r.status === "skipped_disabled" ? "E-mail sending is off. Switch it on in Settings and save the e-mail key first." : `Not sent: ${r.status}`); return; } toast(msg); onSaved(); } catch (x) { setErr(x); } };
  return (
    <Drawer open={!!k} onClose={() => { setEdit(null); setPrev(null); onClose(); }} title={`Template: ${k || ""}`} wide testid="tpl-drawer"
            footer={<div className="a-btns">
              <button className="btn btn--primary" disabled={!edit} onClick={() => act(() => put(`/admin/email/templates/${k}`, Object.fromEntries(fields.map((f) => [f, t[f]]))), "Template saved")} data-testid="tpl-save">Save</button>
              <button className="btn btn--secondary" onClick={() => act(async () => setPrev(await get(`/admin/email/templates/${k}/preview`)), "Preview ready")} data-testid="tpl-preview">Preview</button>
              <button className="btn btn--ghost" onClick={() => act(() => post(`/admin/email/templates/${k}/test`), "Test sent to your inbox")} data-testid="tpl-test">Send test to me</button>
              <button className="btn btn--ghost" onClick={() => act(async () => { await post(`/admin/email/templates/${k}/reset`); setEdit(null); q.reload(); }, "Reset to the default")} data-testid="tpl-reset">Reset</button>
            </div>}>
      {q.loading && !q.data ? <p className="a-muted">Loading…</p> : (
        <div className="a-form">
          {q.data?.vars?.length > 0 && <p className="a-muted small">You can use: {q.data.vars.map((v) => <code key={v}>{`{{${v}}}`} </code>)}</p>}
          {fields.map((f) => <Field key={f} label={f === "html" ? "HTML body" : f === "text" ? "Plain text body" : "Subject"} as={f === "subject" ? "input" : "textarea"} rows={f === "subject" ? undefined : 8} value={t[f] || ""} onChange={(e) => setEdit({ ...(edit || {}), [f]: e.target.value })} testid={`tpl-${f}`} />)}
          <FormError error={err} />
          {prev && <div className="a-card" data-testid="tpl-preview-box"><b>{prev.subject}</b><iframe title="Preview" sandbox="" srcDoc={prev.html || ""} className="tpl-frame" /></div>}
        </div>
      )}
    </Drawer>
  );
}

export function Templates() {
  const q = useApi("/admin/email/templates");
  const [k, setK] = useState(null);
  const cols = [
    { key: "key", label: "Template", primary: true, render: (r) => <span className="a-person"><b>{r.key}</b><small>{r.subject}</small></span> },
    { key: "category", label: "Kind" },
    { key: "customised", label: "", render: (r) => (r.customised ? <Chip tone="warn">Edited</Chip> : <Chip>Default</Chip>) },
  ];
  return (
    <div className="a-page" data-testid="admin-templates">
      <PageHead title="E-mail templates" lead="The messages the site sends. Sending needs the e-mail key in Keys and e-mail switched on in Settings." />
      <DataState q={q} empty="No templates.">{(d) => <ResponsiveTable columns={cols} rows={d.templates} rowKey={(r) => r.key} onRow={(r) => setK(r.key)} testid="tpl-table" />}</DataState>
      <Editor k={k} onClose={() => setK(null)} onSaved={q.reload} />
    </div>
  );
}

export function Suppressions() {
  const toast = useToast();
  const [page, setPage] = useState(1);
  const [pick, setPick] = useState(null);
  const q = useApi("/admin/email/suppressions", { page });
  const cols = [
    { key: "email", label: "Address", primary: true },
    { key: "reason", label: "Why", render: (r) => <Chip tone="warn">{r.reason || "blocked"}</Chip> },
    { key: "at", label: "Since", render: (r) => when(r.at) },
    { key: "x", label: "", render: (r) => <span onClick={(e) => e.stopPropagation()} role="presentation"><button className="btn btn--ghost btn--sm" onClick={() => setPick(r)} data-testid={`unblock-${r.email}`}>Unblock</button></span> },
  ];
  return (
    <div className="a-page" data-testid="admin-suppressions">
      <PageHead title="Blocked addresses" lead="Addresses that bounced, complained or unsubscribed. We never e-mail them." />
      <DataState q={q} empty="No blocked addresses.">{(d) => <><ResponsiveTable columns={cols} rows={d.rows} rowKey={(r) => r.email} testid="supp-table" /><Pager page={d.page} limit={d.limit} total={d.total} onPage={setPage} /></>}</DataState>
      <Confirm open={!!pick} title={`Unblock ${pick?.email}?`} body="Only do this if the person asked for e-mail again." confirmLabel="Unblock" onClose={() => setPick(null)} onConfirm={async () => { await del(`/admin/email/suppressions/${encodeURIComponent(pick.email)}`); setPick(null); toast("Unblocked"); q.reload(); }} testid="unblock-confirm" />
    </div>
  );
}

export function Campaigns() {
  const toast = useToast();
  const q = useApi("/admin/email/campaigns");
  const [open, setOpen] = useState(false);
  const [f, setF] = useState({ subject: "", html: "", segment: "all" });
  const [err, setErr] = useState(null);
  const [send, setSend] = useState(null);
  const create = async () => { setErr(null); try { await post("/admin/email/campaigns", f); toast("Draft saved"); setOpen(false); q.reload(); } catch (x) { setErr(x); } };
  const cols = [
    { key: "subject", label: "Campaign", primary: true, render: (r) => <span className="a-person"><b>{r.subject}</b><small>{r.segment}</small></span> },
    { key: "status", label: "Status", render: (r) => <Chip tone={r.status === "sent" ? "up" : "muted"}>{r.status || "draft"}</Chip> },
    { key: "created_at", label: "Created", render: (r) => when(r.created_at) },
    { key: "x", label: "", render: (r) => r.status !== "sent" && <span onClick={(e) => e.stopPropagation()} role="presentation"><button className="btn btn--secondary btn--sm" onClick={() => setSend(r)} data-testid={`camp-send-${r.id}`}>Send</button></span> },
  ];
  return (
    <div className="a-page" data-testid="admin-campaigns">
      <PageHead title="Campaigns" lead="One-off e-mails to people who said yes to news. Needs marketing e-mail and a footer address in Settings." actions={<button className="btn btn--primary btn--sm" onClick={() => setOpen(true)} data-testid="camp-new">New campaign</button>} />
      <DataState q={q} empty="No campaigns yet.">{(d) => <ResponsiveTable columns={cols} rows={d.rows} testid="camp-table" />}</DataState>
      <Drawer open={open} onClose={() => setOpen(false)} title="New campaign" wide testid="camp-drawer" footer={<button className="btn btn--primary" disabled={!f.subject || !f.html} onClick={create} data-testid="camp-save">Save draft</button>}>
        <div className="a-form">
          <Field label="Subject" value={f.subject} onChange={(e) => setF({ ...f, subject: e.target.value })} testid="camp-subject" />
          <Field label="Who" as="select" value={f.segment} onChange={(e) => setF({ ...f, segment: e.target.value })} testid="camp-segment"><option value="all">Everyone who opted in</option><option value="free">Free members</option><option value="paid">Paying members</option></Field>
          <Field label="HTML body" as="textarea" rows={10} value={f.html} onChange={(e) => setF({ ...f, html: e.target.value })} testid="camp-html" />
          <FormError error={err} />
        </div>
      </Drawer>
      <Confirm open={!!send} danger title={`Send "${send?.subject}"?`} body="It goes out now and stops at the daily cap." typed="SEND" confirmLabel="Send" onClose={() => setSend(null)} onConfirm={async () => { await post(`/admin/email/campaigns/${send.id}/send`); setSend(null); toast("Sending started"); q.reload(); }} testid="camp-confirm" />
    </div>
  );
}
