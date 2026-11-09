// E-mail list (docs/16 §4): counts, filter, export (needs full-address permission), remove with suppression.
import { useState } from "react";
import { getBlob, post } from "../lib/api";
import { useApi } from "../lib/useApi";
import { Confirm, useToast } from "../components/Ui";
import { Card, Chip, DataState, Guard, MissingRoutes, PageHead, Pager, ResponsiveTable, StatTile, notMounted, when } from "./parts";

const TONE = { confirmed: "up", pending: "warn", unsubscribed: "muted" };

export async function download(path, name) {
  const b = await getBlob(`/api${path}`);
  const a = document.createElement("a");
  a.href = URL.createObjectURL(b); a.download = name; a.click();
  setTimeout(() => URL.revokeObjectURL(a.href), 2000);
}

// docs/69. The match-day e-mail is the one thing on this screen that writes to a real reader
// without anyone pressing anything, so it has to be legible BEFORE it is switched on: the actual
// three it would send today, the actual graphic it found, and the reason when there is nothing to
// send. Describing it in prose and hoping would be the wrong trade for a daily send.
function Waitlist() {
  const toast = useToast();
  const q = useApi("/admin/newsletter/waitlist");
  const [busy, setBusy] = useState(false);
  if (notMounted(q.error)) return <MissingRoutes testid="wl-missing" />;
  const d = q.data;
  const send = async () => {
    setBusy(true);
    try {
      const r = await post("/admin/newsletter/waitlist/send");
      toast(r.sent ? `Sent to ${r.sent}` : `Nothing sent: ${r.skipped || "already sent today"}`, r.sent ? "ok" : "err");
      q.reload();
    } finally { setBusy(false); }
  };
  return (
    // Send now is offered only when pressing it would do something: three forecasts to send, and
    // somebody to send them to. A Send now above an empty list is a button whose only possible
    // outcome is "nothing sent".
    <Card title="Match-day e-mail" testid="wl-card"
          actions={d?.ready && d?.members > 0 && <Guard className="btn btn--primary btn--sm" label="Send now" busyLabel="Sending…"
                                      confirmLabel="Send the whole list" danger typed="SEND" disabled={busy}
                                      title={`Send today's three to ${(d.members || 0).toLocaleString()} people?`}
                                      body="It goes out now and stops at the daily cap. Sending twice on the same day sends one e-mail: the second run is skipped per address."
                                      onRun={send} testid="wl-send" />}>
      <DataState q={q} empty="Nothing to show yet.">{(w) => (
        <>
          <div className="a-tiles">
            <StatTile label="On the waitlist" value={(w.members ?? 0).toLocaleString()} testid="wl-members" />
            <StatTile label="Found for today" value={`${w.found ?? 0} of 3`} tone={w.ready ? "up" : "warn"} testid="wl-found" />
            <StatTile label="Last sent" value={w.last ? w.last._id : "Never"} sub={w.last ? `${(w.last.sent || 0).toLocaleString()} e-mails` : undefined} testid="wl-last" />
          </div>
          <p className="muted small">
            {!w.enabled && <>Switched off. Turn on <b>Send the waitlist match-day e-mail</b> under Settings &gt; Marketing to let it go out on its own. </>}
            {w.enabled && <>It goes out on its own from {String(w.hour).padStart(2, "0")}:00, once a day. </>}
            {w.ready
              ? <>Today it would send these three{w.with_image ? ", with the card below as its header." : ". No post is queued for today, so it would have no header graphic."}</>
              : <>Not enough above the floor today ({w.found ?? 0} of 3), so nothing would go out. That is the intended behaviour on a day with little football.</>}
          </p>
          {/* The real thing, rendered -- including the header graphic, so there is no second copy
              of it on this screen to disagree with what the e-mail actually carries. Sandboxed because it is an e-mail body: it must not be able
              to reach this page's session, and an e-mail has no business running anything. */}
          <iframe className="wl-frame" title="Match-day e-mail preview" sandbox="" srcDoc={w.html} data-testid="wl-preview" />
          <p className="muted small"><b>Subject:</b> {w.subject}</p>
        </>
      )}</DataState>
    </Card>
  );
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
    { key: "x", label: "", render: (r) => r.status !== "unsubscribed" && <span onClick={(e) => e.stopPropagation()} role="presentation"><button className="btn btn--danger btn--sm" onClick={() => setGone(r)} data-testid={`nl-remove-${r.id}`}>Remove</button></span> },
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
      <Waitlist />
      <div className="a-filters"><select aria-label="Status" value={status} onChange={(e) => { setStatus(e.target.value); setPage(1); }} data-testid="nl-status"><option value="">Every status</option>{["confirmed", "pending", "unsubscribed"].map((s) => <option key={s}>{s}</option>)}</select></div>
      <DataState q={q} empty="Nobody on the list yet. The footer form and e-mail popups add people here.">{(d) => <><ResponsiveTable columns={cols} rows={d.rows} testid="nl-table" /><Pager page={d.page} limit={d.limit} total={d.total} onPage={setPage} /></>}</DataState>
      <Confirm open={!!gone} danger title="Remove this address?" body="They stop getting list e-mails and can't be added back by accident." confirmLabel="Remove" onClose={() => setGone(null)} testid="nl-remove-confirm"
               onConfirm={async () => { await post("/admin/newsletter/remove", { email: gone.email }); toast("Removed"); setGone(null); q.reload(); }} />
    </div>
  );
}
