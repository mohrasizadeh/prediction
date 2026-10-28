// Integrations (docs/16 §5-6): e-mail provider, list sync, outbound webhooks, tracking tags (owner only).
import { useEffect, useState } from "react";
import { del, post, put } from "../lib/api";
import { useApi } from "../lib/useApi";
import { useAuth } from "../lib/auth";
import { Confirm, Drawer, Field, FormError, Switch, useToast } from "../components/Ui";
import { Card, Chip, DataState, PageHead, ResponsiveTable, when } from "./parts";
import SportAPI from "./SportAPI";

function EmailCard({ e, reload }) {
  const toast = useToast();
  const [p, setP] = useState(e.provider);
  const save = async () => { try { const r = await put("/admin/integrations/email", { provider: p }); toast(r.warning || "Provider saved", r.warning ? "err" : "ok"); reload(); } catch (x) { toast(x.message, "err"); } };
  const test = async () => { try { const r = await post("/admin/integrations/email/test-send", {}); toast(r.status === "sent" ? "Test e-mail sent to you" : `Not sent: ${r.status}${r.error ? ` (${r.error})` : ""}`, r.status === "sent" ? "ok" : "err"); } catch (x) { toast(x.message, "err"); } };
  return (
    <Card title="E-mail sending" testid="int-email" actions={<Chip tone={e.enabled && e.key_set ? "up" : "warn"}>{e.enabled ? (e.key_set ? "Sending" : "No key") : "Off"}</Chip>}>
      <p className="muted small">Account, payment and confirm e-mails go through {e.label}. {e.provider === "emergent" ? "This service can't send campaigns; pick your own provider for those." : ""}</p>
      <Field as="select" label="Provider" value={p} onChange={(x) => setP(x.target.value)} testid="int-email-provider">{e.providers.map((x) => <option key={x.id} value={x.id}>{x.label}</option>)}</Field>
      {p !== "emergent" && p !== e.provider && <p className="a-warn">Save the provider's key under Keys first, or e-mail stops.</p>}
      <div className="a-inline-actions"><button className="btn btn--primary btn--sm" onClick={save} disabled={p === e.provider} data-testid="int-email-save">Save</button><button className="btn btn--secondary btn--sm" onClick={test} data-testid="int-email-test">Send me a test</button></div>
    </Card>
  );
}

function AudienceCard({ a, reload }) {
  const toast = useToast();
  const [f, setF] = useState({ provider: a.provider, list_id: "" });
  const run = async (fn, ok) => { try { const r = await fn(); toast(ok(r)); reload(); } catch (x) { toast(x.message, "err"); } };
  return (
    <Card title="E-mail list sync" testid="int-audience" actions={<Chip tone={a.provider !== "none" && a.key_set ? "up" : "muted"}>{a.provider === "none" ? "Off" : a.key_set ? "Connected" : "No key"}</Chip>}>
      <p className="muted small">Copies confirmed sign-ups to your marketing tool. Jobs: {a.jobs.pending} waiting, {a.jobs.done} done, {a.jobs.dead} failed.</p>
      <Field as="select" label="Send the list to" value={f.provider} onChange={(e) => setF({ ...f, provider: e.target.value })} testid="int-audience-provider"><option value="none">Nowhere</option>{a.providers.map((x) => <option key={x.id} value={x.id}>{x.label}</option>)}</Field>
      {f.provider !== "none" && <Field label="List or audience id" value={f.list_id} onChange={(e) => setF({ ...f, list_id: e.target.value })} hint={a.list_id_set ? "An id is saved. Type a new one to change it." : "From your provider's list settings."} maxLength={60} testid="int-audience-list" />}
      <div className="a-inline-actions">
        <button className="btn btn--primary btn--sm" onClick={() => run(() => put("/admin/integrations/audience", f), () => "Saved")} data-testid="int-audience-save">Save</button>
        {a.provider !== "none" && <><button className="btn btn--secondary btn--sm" onClick={() => run(() => post("/admin/integrations/audience/test"), (r) => (r.ok ? "Connection works" : `Not working: ${r.code}`))} data-testid="int-audience-test">Test</button>
          <button className="btn btn--ghost btn--sm" onClick={() => run(() => post("/admin/integrations/audience/backfill"), (r) => `${r.queued} addresses queued`)} data-testid="int-audience-backfill">Send everyone now</button></>}
      </div>
    </Card>
  );
}

function HookForm({ events, onClose, onMade }) {
  const [f, setF] = useState({ url: "", events: [], include_email: false, note: "" });
  const [err, setErr] = useState(null);
  const go = async () => { setErr(null); try { onMade(await post("/admin/integrations/webhooks", f)); } catch (x) { setErr(x); } };
  return (
    <Drawer open onClose={onClose} title="New webhook" testid="hook-form" footer={<><button className="btn btn--secondary" onClick={onClose}>Cancel</button><button className="btn btn--primary" onClick={go} disabled={!f.url || !f.events.length} data-testid="hook-save">Add</button></>}>
      <div className="a-stack">
        <Field label="Address (https)" value={f.url} onChange={(e) => setF({ ...f, url: e.target.value })} placeholder="https://hooks.zapier.com/..." testid="hook-url" />
        <fieldset className="a-checks"><legend>Send these events</legend>{events.map((ev) => <label key={ev}><input type="checkbox" checked={f.events.includes(ev)} onChange={(e) => setF({ ...f, events: e.target.checked ? [...f.events, ev] : f.events.filter((x) => x !== ev) })} data-testid={`hook-ev-${ev}`} />{ev}</label>)}</fieldset>
        <Switch label="Include the person's e-mail" hint="Off by default. Only turn on if the receiving tool needs it." checked={f.include_email} onChange={(v) => setF({ ...f, include_email: v })} />
        <Field label="Note (optional)" value={f.note} onChange={(e) => setF({ ...f, note: e.target.value })} maxLength={120} />
        <FormError error={err} />
      </div>
    </Drawer>
  );
}

function Webhooks() {
  const toast = useToast();
  const q = useApi("/admin/integrations/webhooks");
  const dl = useApi("/admin/integrations/webhooks-deliveries");
  const [form, setForm] = useState(false);
  const [secret, setSecret] = useState(null);
  const [gone, setGone] = useState(null);
  const run = async (fn, msg) => { try { const r = await fn(); if (r?.secret) setSecret(r.secret); else toast(typeof msg === "function" ? msg(r) : msg); q.reload(); dl.reload(); } catch (x) { toast(x.message, "err"); } };
  const cols = [
    { key: "url", label: "Address", primary: true, render: (r) => <span className="a-person"><b className="a-wrap">{r.url}</b><small>{r.events.join(", ")}</small></span> },
    { key: "s", label: "State", render: (r) => <Chip tone={!r.active ? "muted" : r.fail_streak >= 3 ? "down" : "up"}>{!r.active ? "Off" : r.fail_streak >= 3 ? "Failing" : "On"}</Chip> },
    { key: "last", label: "Last sent", render: (r) => (r.last_at ? `${when(r.last_at)} (${r.last_status})` : "Never") },
    { key: "x", label: "", render: (r) => <span className="a-inline-actions" onClick={(e) => e.stopPropagation()} role="presentation">
      <button className="btn btn--ghost btn--sm" onClick={() => run(() => post(`/admin/integrations/webhooks/${r.id}/test`), (x) => (x.ok ? "Test delivered" : `Test failed (${x.status || x.info})`))} data-testid={`hook-test-${r.id}`}>Test</button>
      <button className="btn btn--ghost btn--sm" onClick={() => run(() => put(`/admin/integrations/webhooks/${r.id}`, { active: !r.active }), r.active ? "Turned off" : "Turned on")} data-testid={`hook-toggle-${r.id}`}>{r.active ? "Turn off" : "Turn on"}</button>
      <button className="btn btn--ghost btn--sm" onClick={() => run(() => post(`/admin/integrations/webhooks/${r.id}/rotate`))} data-testid={`hook-rotate-${r.id}`}>New secret</button>
      <button className="btn btn--ghost btn--sm" onClick={() => setGone(r)} data-testid={`hook-delete-${r.id}`}>Delete</button></span> },
  ];
  return (
    <Card title="Webhooks (Zapier, Make, n8n, Slack)" testid="int-webhooks" actions={<button className="btn btn--secondary btn--sm" onClick={() => setForm(true)} data-testid="hook-new">Add webhook</button>}>
      <DataState q={q} empty="No webhooks yet.">{(d) => <><p className="muted small">Each delivery is signed: {d.signature}</p>{d.endpoints.length ? <ResponsiveTable columns={cols} rows={d.endpoints} testid="hook-table" /> : <p className="muted">No webhooks yet.</p>}
        {form && <HookForm events={d.events} onClose={() => setForm(false)} onMade={(r) => { setForm(false); setSecret(r.secret); q.reload(); }} />}</>}</DataState>
      <details><summary>Recent deliveries</summary><DataState q={dl} empty="Nothing sent yet.">{(d) => (d.deliveries.length ? <ResponsiveTable testid="hook-deliveries" rowKey={(r) => `${r.endpoint_id}${r.at}`} rows={d.deliveries} columns={[{ key: "event", label: "Event", primary: true, render: (r) => <b>{r.event || r.type}</b> }, { key: "status", label: "Status" }, { key: "at", label: "When", render: (r) => when(r.at) }]} /> : <p className="muted">Nothing sent yet.</p>)}</DataState></details>
      <Confirm open={!!secret} title="Copy the signing secret now" body={<><p>It is shown only once. Paste it into the receiving tool to check signatures.</p><code className="a-secret" data-testid="hook-secret">{secret}</code></>} confirmLabel="I copied it" onClose={() => setSecret(null)} onConfirm={() => setSecret(null)} testid="hook-secret-dialog" />
      <Confirm open={!!gone} danger title="Delete this webhook?" confirmLabel="Delete" onClose={() => setGone(null)} testid="hook-delete-confirm" onConfirm={async () => { await del(`/admin/integrations/webhooks/${gone.id}`); setGone(null); toast("Deleted"); q.reload(); }} />
    </Card>
  );
}

function TrackingCard({ t, reload }) {
  const toast = useToast();
  const { user } = useAuth();
  const owner = user?.role === "owner";
  const [f, setF] = useState({ enabled: t.enabled, ga4_id: "", meta_pixel_id: "", google_ads_id: "", require_consent: t.require_consent });
  const [warn, setWarn] = useState([]);
  useEffect(() => { setF((x) => ({ ...x, enabled: t.enabled, require_consent: t.require_consent })); }, [t.enabled, t.require_consent]);
  const save = async () => { try { const r = await put("/admin/integrations/tracking", f); setWarn(r.warnings || []); toast("Tracking saved"); reload(); } catch (x) { toast(x.message, "err"); } };
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value });
  return (
    <Card title="Tracking tags" testid="int-tracking" actions={<Chip tone={t.enabled ? "warn" : "muted"}>{t.enabled ? "On" : "Off"}</Chip>}>
      <p className="muted small">Google Analytics, Meta Pixel and Google Ads. They load only after a visitor taps "Allow optional", never with Do Not Track or Global Privacy Control, and never on sign-in, admin or billing pages. Saved: {[t.ga4 && "GA4", t.meta && "Meta", t.google_ads && "Google Ads"].filter(Boolean).join(", ") || "none"}.</p>
      {!owner ? <p className="a-warn" data-testid="int-tracking-owner-only">Only the owner can change tracking.</p> : <>
        <Switch label="Load tracking tags" checked={f.enabled} onChange={(v) => setF({ ...f, enabled: v })} testid="int-tracking-enabled" />
        <Field label="Google Analytics 4 id" value={f.ga4_id} onChange={set("ga4_id")} placeholder="G-XXXXXXX" maxLength={20} hint="Leave empty to keep the saved one off." testid="int-tracking-ga4" />
        <Field label="Meta Pixel id" value={f.meta_pixel_id} onChange={set("meta_pixel_id")} placeholder="1234567890" maxLength={25} testid="int-tracking-meta" />
        <Field label="Google Ads id" value={f.google_ads_id} onChange={set("google_ads_id")} placeholder="AW-XXXXXXX" maxLength={25} testid="int-tracking-ads" />
        <Switch label="Wait for cookie consent" hint="Keep this on in Canada and the EU." checked={f.require_consent} onChange={(v) => setF({ ...f, require_consent: v })} testid="int-tracking-consent" />
        {warn.map((w) => <p key={w} className="a-warn" data-testid="int-tracking-warning">{w}</p>)}
        <button className="btn btn--primary btn--sm" onClick={save} data-testid="int-tracking-save">Save</button>
      </>}
    </Card>
  );
}

export default function Integrations() {
  const q = useApi("/admin/integrations");
  return (
    <div className="a-page" data-testid="admin-integrations">
      <PageHead title="Integrations" lead="Connect e-mail, your marketing list, automation tools and ad tags. Keys live under Keys." />
      <DataState q={q}>{(d) => <div className="a-grid2">
        <EmailCard e={d.email} reload={q.reload} />
        <AudienceCard a={d.audience} reload={q.reload} />
        <TrackingCard t={d.tracking} reload={q.reload} />
        <Webhooks />
      </div>}</DataState>
      <h2 className="h3 a-section-title">SportAPI</h2>
      <SportAPI />
    </div>
  );
}
