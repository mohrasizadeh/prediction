// E-mail list (docs/16 §4): counts, filter, export (needs full-address permission), remove with suppression.
import { useState } from "react";
import { getBlob, post } from "../lib/api";
import { useApi } from "../lib/useApi";
import { Confirm, useToast } from "../components/Ui";
import { Chip, DataState, PageHead, Pager, ResponsiveTable, StatTile, when } from "./parts";

const TONE = { confirmed: "up", pending: "warn", unsubscribed: "muted" };

export async function download(path, name) {
  const b = await getBlob(`/api${path}`);
  const a = document.createElement("a");
  a.href = URL.createObjectURL(b); a.download = name; a.click();
  setTimeout(() => URL.revokeObjectURL(a.href), 2000);
}

export default function Newsletter() {
  const toast = useToast();
  const [status, setStatus] = useState("");
  const [page, setPage] = useState(1);
  const [gone, setGone] = useState(null);
  const q = useApi("/admin/newsletter", { status, page });
  const c = q.data?.counts || {};
  const cols = [
    { key: "email", label: "Address", primary: true, render: (r) => <span className="a-person"><b>{r.email}</b><small>{r.source}</small></span> },
    { key: "status", label: "Status", render: (r) => <Chip tone={TONE[r.status] || "muted"}>{r.status}</Chip> },
    { key: "consent_at", label: "Agreed", render: (r) => when(r.consent_at) },
    { key: "confirmed_at", label: "Confirmed", render: (r) => when(r.confirmed_at) },
    { key: "x", label: "", render: (r) => r.status !== "unsubscribed" && <span onClick={(e) => e.stopPropagation()} role="presentation"><button className="btn btn--ghost btn--sm" onClick={() => setGone(r)} data-testid={`nl-remove-${r.id}`}>Remove</button></span> },
  ];
  const exp = async () => { try { await download("/admin/newsletter/export", "email-list.csv"); } catch (x) { toast(x.status === 403 ? "Your role can't export full addresses." : x.message, "err"); } };
  return (
    <div className="a-page" data-testid="admin-newsletter">
      <PageHead title="E-mail list" lead="People who said yes to the weekly e-mail. Nobody joins until they confirm by e-mail."
                actions={<button className="btn btn--secondary btn--sm" onClick={exp} data-testid="nl-export">Export CSV</button>} />
      <div className="a-tiles">
        <StatTile label="Confirmed" value={(c.confirmed ?? 0).toLocaleString()} tone="up" testid="nl-count-confirmed" />
        <StatTile label="Waiting to confirm" value={(c.pending ?? 0).toLocaleString()} testid="nl-count-pending" />
        <StatTile label="Unsubscribed" value={(c.unsubscribed ?? 0).toLocaleString()} testid="nl-count-unsubscribed" />
      </div>
      <div className="a-filters"><select aria-label="Status" value={status} onChange={(e) => { setStatus(e.target.value); setPage(1); }} data-testid="nl-status"><option value="">Every status</option>{["confirmed", "pending", "unsubscribed"].map((s) => <option key={s}>{s}</option>)}</select></div>
      <DataState q={q} empty="Nobody on the list yet. The footer form and e-mail popups add people here.">{(d) => <><ResponsiveTable columns={cols} rows={d.rows} testid="nl-table" /><Pager page={d.page} limit={d.limit} total={d.total} onPage={setPage} /></>}</DataState>
      <Confirm open={!!gone} danger title="Remove this address?" body="They stop getting list e-mails and can't be added back by accident." confirmLabel="Remove" onClose={() => setGone(null)} testid="nl-remove-confirm"
               onConfirm={async () => { await post("/admin/newsletter/remove", { email: gone.email }); toast("Removed"); setGone(null); q.reload(); }} />
    </div>
  );
}
