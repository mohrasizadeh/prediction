// Announcements (docs/10 §3.9): banner text, level, audience, dates, on/off. Shown by GET /api/announcements.
import { useState } from "react";
import { del, post, put } from "../lib/api";
import { useApi } from "../lib/useApi";
import { utc } from "../lib/time";
import { Confirm, Drawer, Field, FormError, Switch, useToast } from "../components/Ui";
import Icon from "../components/Icon";
import { Chip, DataState, PageHead, ResponsiveTable, when } from "./parts";

const toLocal = (s) => { if (!s) return ""; const d = utc(s); return new Date(d.getTime() - d.getTimezoneOffset() * 6e4).toISOString().slice(0, 16); };
const toIso = (v) => (v ? new Date(v).toISOString() : null);

function Editor({ a, onClose, onSaved }) {
  const toast = useToast();
  const [f, setF] = useState({ text: a.text || "", level: a.level || "info", audience: a.audience || "all", starts_at: toLocal(a.starts_at), ends_at: toLocal(a.ends_at), active: a.active ?? true });
  const [err, setErr] = useState(null);
  const save = async () => {
    setErr(null);
    const body = { ...f, starts_at: toIso(f.starts_at), ends_at: toIso(f.ends_at) };
    try { a.id ? await put(`/admin/announcements/${a.id}`, body) : await post("/admin/announcements", body); toast("Announcement saved"); onSaved(); onClose(); } catch (x) { setErr(x); }
  };
  return (
    <Drawer open onClose={onClose} title={a.id ? "Edit announcement" : "New announcement"} testid="ann-drawer" footer={<button className="btn btn--primary" onClick={save} disabled={!f.text.trim()} data-testid="ann-save">Save</button>}>
      <div className="a-stack">
        <Field label={`Text (${f.text.length}/240)`} as="textarea" rows={3} maxLength={240} value={f.text} onChange={(e) => setF({ ...f, text: e.target.value })} testid="ann-text" />
        <div className="a-form-row">
          <Field label="Level" as="select" value={f.level} onChange={(e) => setF({ ...f, level: e.target.value })} testid="ann-level"><option value="info">Info</option><option value="warn">Warning</option></Field>
          <Field label="Who sees it" as="select" value={f.audience} onChange={(e) => setF({ ...f, audience: e.target.value })} testid="ann-audience">{["all", "signed_out", "free", "paid"].map((x) => <option key={x} value={x}>{x.replace("_", " ")}</option>)}</Field>
        </div>
        <div className="a-form-row">
          <Field label="Starts" type="datetime-local" value={f.starts_at} onChange={(e) => setF({ ...f, starts_at: e.target.value })} testid="ann-start" />
          <Field label="Ends" type="datetime-local" value={f.ends_at} onChange={(e) => setF({ ...f, ends_at: e.target.value })} testid="ann-end" />
        </div>
        <Switch label="Showing" checked={f.active} onChange={(v) => setF({ ...f, active: v })} testid="ann-active" />
        <div className={"announce announce--" + f.level}><div className="announce-row"><Icon name={f.level === "warn" ? "alert" : "info"} size={16} /><p>{f.text || "Your text appears here."}</p></div></div>
        <FormError error={err} />
      </div>
    </Drawer>
  );
}

export default function Announcements() {
  const q = useApi("/admin/announcements");
  const toast = useToast();
  const [edit, setEdit] = useState(null);
  const [rm, setRm] = useState(null);
  const cols = [
    { key: "text", label: "Text", primary: true },
    { key: "level", label: "Level", render: (r) => <Chip tone={r.level === "warn" ? "warn" : "brand"}>{r.level}</Chip> },
    { key: "audience", label: "Who" },
    { key: "active", label: "State", render: (r) => (r.active ? <Chip tone="up">On</Chip> : <Chip>Off</Chip>) },
    { key: "ends_at", label: "Ends", render: (r) => (r.ends_at ? when(r.ends_at) : "No end") },
    { key: "x", label: "", render: (r) => <span onClick={(e) => e.stopPropagation()} role="presentation"><button className="a-icon-btn a-icon-btn--sm" aria-label="Delete" onClick={() => setRm(r)} data-testid={`ann-delete-${r.id}`}><Icon name="trash" size={16} /></button></span> },
  ];
  return (
    <div className="a-page" data-testid="admin-announcements">
      <PageHead title="Announcements" lead="A short banner at the top of the site." actions={<button className="btn btn--primary btn--sm" onClick={() => setEdit({})} data-testid="ann-new"><Icon name="plus" size={16} />New</button>} />
      <DataState q={q} empty="No announcements yet.">{(d) => <ResponsiveTable columns={cols} rows={d.rows} onRow={setEdit} testid="ann-table" />}</DataState>
      {edit && <Editor a={edit} onClose={() => setEdit(null)} onSaved={q.reload} />}
      <Confirm open={!!rm} danger title="Delete this announcement?" confirmLabel="Delete" onClose={() => setRm(null)} testid="ann-delete-confirm"
               onConfirm={async () => { await del(`/admin/announcements/${rm.id}`); setRm(null); toast("Deleted"); q.reload(); }} />
    </div>
  );
}
